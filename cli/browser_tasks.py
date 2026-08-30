"""
Browser automation controller for Hermes Story Video Generation (v2).

Supported actions:
    python -m cli.browser_tasks gemini "<prompt>"
    python -m cli.browser_tasks gemini_file "<prompt-file>"
    python -m cli.browser_tasks gemini_clipboard
    python -m cli.browser_tasks notebooklm
    python -m cli.browser_tasks grok_imagine
    python -m cli.browser_tasks status
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import io
import json
import os
import re
import shutil
import sys
import time
import subprocess
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

import config

GEMINI_URL = getattr(config, "GEMINI_URL", None) or "https://gemini.google.com/"
NOTEBOOKLM_URL = getattr(config, "NOTEBOOKLM_URL", None) or "https://notebooklm.google.com/"
GROK_IMAGINE_URL = getattr(config, "GROK_IMAGINE_URL", None) or "https://grok.com/imagine"
DEFAULT_TIMEOUT_MS = 30_000
GENERATION_TIMEOUT_MS = 180_000
NOTEBOOKLM_COVER_TIMES = 3
NOTEBOOKLM_PROMPT_MIN_CHARS = 200
NOTEBOOKLM_READY_MIN_S = 45
NOTEBOOKLM_READY_TIMEOUT_S = 12 * 60
INFOGRAPHIC_PREVIEW_LOAD_TIMEOUT_S = 30.0
INFOGRAPHIC_POPUP_OPEN_TIMEOUT_S = 12.0

# Per ``handle_gemini`` run: sidebar star only once at open.
_GEMINI_SIDEBAR_DONE = False


def log(message: str) -> None:
    print(f"[browser_tasks] {message}", file=sys.stderr, flush=True)


def _chrome_cdp_user_data_dir() -> str:
    path = (getattr(config, "CHROME_CDP_USER_DATA_DIR", "") or "").strip()
    if path:
        return path
    return str(Path.home() / "AppData" / "Local" / "HermesChromeCDP")


def _profile_email_from_local_state(dirname: str, user_data: str) -> str:
    """Read logged-in email for a Chrome profile folder under HermesChromeCDP."""
    local_state = Path(user_data) / "Local State"
    if not local_state.is_file():
        return ""
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
        info = ((data.get("profile") or {}).get("info_cache") or {}).get(dirname) or {}
        if not isinstance(info, dict):
            return ""
        return str(info.get("user_name") or "").strip()
    except Exception:
        return ""


def _resolve_profile_dir_from_local_state(email: str, user_data: str) -> str:
    """Map account email → actual ``--profile-directory`` in HermesChromeCDP."""
    want = (email or "").strip().lower()
    if not want:
        return ""
    local_state = Path(user_data) / "Local State"
    if not local_state.is_file():
        return ""
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
        cache = (data.get("profile") or {}).get("info_cache") or {}
        if not isinstance(cache, dict):
            return ""
        for dirname, info in cache.items():
            if not isinstance(info, dict):
                continue
            user_name = str(info.get("user_name") or "").strip().lower()
            gaia = str(info.get("gaia_name") or "").strip().lower()
            if want == user_name or want in user_name or want.split("@")[0] in gaia:
                return str(dirname)
    except Exception as exc:
        log(f"could not read HermesChromeCDP Local State: {exc}")
    return ""


def resolve_chrome_profile_directory(profile_email: str = "") -> str:
    """Map ``GEMINI_CHROME_PROFILE`` (email) to Chrome ``--profile-directory``."""
    want = (profile_email or getattr(config, "GEMINI_CHROME_PROFILE", "") or "").strip()
    user_data = _chrome_cdp_user_data_dir()

    for item in getattr(config, "list_gemini_chrome_profiles", lambda: [])():
        if item.get("label", "").strip().lower() == want.lower():
            configured = (item.get("directory") or "").strip() or "Default"
            actual = _resolve_profile_dir_from_local_state(want, user_data)
            if actual and not _profile_dirs_match(actual, configured):
                log(
                    f"profile {want}: config says {configured}, "
                    f"HermesChromeCDP Local State says {actual} — using {actual}"
                )
                return actual
            log(f"profile list: {want} → --profile-directory={configured}")
            return configured

    explicit = (getattr(config, "GEMINI_CHROME_PROFILE_DIRECTORY", "") or "").strip()
    if explicit:
        return explicit

    want_low = want.lower()
    actual = _resolve_profile_dir_from_local_state(want, user_data)
    if actual:
        log(f"resolved {want} → --profile-directory={actual} (Local State)")
        return actual

    if want_low:
        local_state = Path(user_data) / "Local State"
        if local_state.is_file():
            try:
                data = json.loads(local_state.read_text(encoding="utf-8"))
                cache = (data.get("profile") or {}).get("info_cache") or {}
                if isinstance(cache, dict):
                    for dirname, info in cache.items():
                        if not isinstance(info, dict):
                            continue
                        fields = [
                            info.get("user_name"),
                            info.get("gaia_name"),
                            info.get("name"),
                        ]
                        blob = " ".join(str(x) for x in fields if x).lower()
                        if want_low and want_low in blob:
                            log(
                                f"resolved {profile_email or want} → --profile-directory={dirname}"
                            )
                            return str(dirname)
            except Exception as exc:
                log(f"could not read Chrome Local State: {exc}")

    listed = getattr(config, "list_gemini_chrome_profiles", lambda: [])()
    if listed:
        fallback = (listed[0].get("directory") or "").strip() or "Default"
        log(f"profile fallback → --profile-directory={fallback}")
        return fallback
    return "Default"


def cdp_ready(port: int | None = None) -> bool:
    port = int(port or getattr(config, "CHROME_REMOTE_DEBUGGING_PORT", 9222) or 9222)
    try:
        import urllib.request

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/version",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return getattr(resp, "status", 200) == 200
    except Exception:
        return False


def _chrome_process_running() -> bool:
    """True when any chrome.exe process is alive."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (result.stdout or "").lower()
        return "chrome.exe" in out
    except Exception as exc:
        log(f"chrome process probe failed: {exc}")
        return False


def _kill_all_chrome() -> None:
    """Force-close all Chrome processes (for a clean CDP launch)."""
    if sys.platform != "win32" or not _chrome_process_running():
        return
    log("taskkill chrome.exe for clean Grok CDP launch")
    try:
        subprocess.run(
            ["taskkill", "/IM", "chrome.exe", "/F"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        log(f"taskkill chrome.exe failed: {exc}")
    time.sleep(2.0)


def _wait_chrome_closed(timeout_s: float = 25.0) -> None:
    """Wait until no chrome.exe remains."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _chrome_process_running():
            time.sleep(1.0)
            if not _chrome_process_running():
                return
        time.sleep(0.5)
    raise RuntimeError(
        "Chrome 仍在运行。请在任务管理器结束所有 chrome.exe，再重发 grv 1。"
    )


def _hermes_cdp_session_path() -> str:
    return getattr(config, "HERMES_CDP_ACTIVE_PROFILE_JSON", "") or ""


def load_hermes_cdp_session() -> dict:
    empty = {"profile_dir": "", "profile": "", "launched_at": ""}
    path = _hermes_cdp_session_path()
    if not path or not os.path.isfile(path):
        return dict(empty)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    return {
        "profile_dir": str(data.get("profile_dir") or "").strip(),
        "profile": str(data.get("profile") or "").strip(),
        "launched_at": str(data.get("launched_at") or ""),
    }


def save_hermes_cdp_session(*, profile_dir: str, profile: str) -> dict:
    from datetime import datetime, timezone

    payload = {
        "profile_dir": (profile_dir or "").strip(),
        "profile": (profile or "").strip(),
        "launched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path = _hermes_cdp_session_path()
    if path:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass
    return payload


def clear_hermes_cdp_session() -> None:
    path = _hermes_cdp_session_path()
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _read_profile_devtools_port(user_data: str, profile_dir: str) -> int | None:
    """Read Chrome ``DevToolsActivePort`` written under the profile folder."""
    port_file = Path(user_data) / profile_dir / "DevToolsActivePort"
    if not port_file.is_file():
        return None
    try:
        lines = port_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if lines and str(lines[0]).strip().isdigit():
            return int(str(lines[0]).strip())
    except Exception as exc:
        log(f"read DevToolsActivePort failed: {exc}")
    return None


def _profile_dirs_match(a: str, b: str) -> bool:
    x = (a or "").strip().lower()
    y = (b or "").strip().lower()
    return bool(x and y and x == y)


def _iter_chrome_profile_dirs(user_data: str) -> list[str]:
    names: list[str] = []
    for item in getattr(config, "list_gemini_chrome_profiles", lambda: [])():
        d = (item.get("directory") or "").strip() or "Default"
        if d not in names:
            names.append(d)
    root = Path(user_data or "")
    extras = ["Default"]
    try:
        extras.extend(p.name for p in sorted(root.glob("Profile *")) if p.is_dir())
    except Exception:
        pass
    for extra in extras:
        if extra and extra not in names:
            names.append(extra)
    return names


def _hermes_cdp_active_profile(
    user_data: str, preferred: int | None = None
) -> tuple[int | None, str]:
    """Live HermesChromeCDP port and which ``--profile-directory`` owns it."""
    for dirname in _iter_chrome_profile_dirs(user_data):
        port = _read_profile_devtools_port(user_data, dirname)
        if port and cdp_ready(port):
            log(f"HermesChromeCDP live port={port} profile={dirname}")
            return port, dirname
    root_port_file = Path(user_data) / "DevToolsActivePort"
    if root_port_file.is_file():
        try:
            lines = root_port_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if lines and str(lines[0]).strip().isdigit():
                port = int(str(lines[0]).strip())
                if cdp_ready(port):
                    session_dir = load_hermes_cdp_session().get("profile_dir") or ""
                    if session_dir:
                        log(
                            f"HermesChromeCDP live port={port} "
                            f"profile={session_dir} (session)"
                        )
                        return port, session_dir
                    log(f"HermesChromeCDP live port={port} profile=unknown")
                    return port, ""
        except Exception:
            pass
    if preferred and cdp_ready(int(preferred)):
        session_dir = load_hermes_cdp_session().get("profile_dir") or ""
        if session_dir:
            log(
                f"HermesChromeCDP live port={preferred} "
                f"profile={session_dir} (session)"
            )
            return int(preferred), session_dir
        return int(preferred), ""
    return None, ""


def _kill_hermes_cdp_chrome(user_data: str = "") -> None:
    """Close only the HermesChromeCDP instance — do not kill daily Chrome."""
    root = os.path.normcase(os.path.abspath(user_data or _chrome_cdp_user_data_dir()))
    token = Path(root).name
    if not token:
        return
    log(f"closing HermesChromeCDP chrome to switch profile ({token})")
    clear_hermes_cdp_session()
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        f"Where-Object {{ $_.CommandLine -and $_.CommandLine -like '*{token}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        log(f"kill HermesChromeCDP failed: {exc}")
    port = _grok_cdp_port()
    if cdp_ready(port):
        try:
            subprocess.run(
                [
                    "wmic",
                    "process",
                    "where",
                    f"name='chrome.exe' and CommandLine like '%{token}%'",
                    "call",
                    "terminate",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            log(f"wmic terminate HermesChromeCDP failed: {exc}")
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if not cdp_ready(port):
            time.sleep(1.0)
            return
        time.sleep(0.4)
    log("HermesChromeCDP port still up after kill; continuing")
    clear_hermes_cdp_session()


def _wait_cdp_port_after_launch(preferred: int, *, timeout_s: float = 90.0) -> int:
    """Wait until *preferred* CDP answers after we just spawned Chrome."""
    port = int(preferred)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if cdp_ready(port):
            time.sleep(1.0)
            log(f"HermesChromeCDP ready on {port}")
            return port
        time.sleep(0.5)
    return 0


def _discover_grok_cdp_port(
    user_data: str, profile_dir: str, preferred: int | None = None
) -> int | None:
    """Return a working CDP port for *profile_dir*, not some other Hermes profile."""
    discovered = _read_profile_devtools_port(user_data, profile_dir)
    if discovered and cdp_ready(discovered):
        log(f"Grok CDP on {discovered} (DevToolsActivePort {profile_dir})")
        return discovered
    if not preferred or not cdp_ready(int(preferred)):
        return None
    session_dir = load_hermes_cdp_session().get("profile_dir") or ""
    if session_dir:
        if _profile_dirs_match(session_dir, profile_dir):
            log(f"Grok CDP on {preferred} (session {session_dir})")
            return int(preferred)
        log(
            f"Grok CDP on {preferred} but session profile is {session_dir}, "
            f"want {profile_dir}"
        )
        return None
    for dirname in _iter_chrome_profile_dirs(user_data):
        if _profile_dirs_match(dirname, profile_dir):
            continue
        other = _read_profile_devtools_port(user_data, dirname)
        if (
            other
            and int(other) != int(preferred)
            and cdp_ready(other)
        ):
            return None
    return int(preferred)


def _wait_grok_cdp_port(
    user_data: str,
    profile_dir: str,
    preferred: int | None,
    *,
    timeout_s: float = 90.0,
) -> int:
    """After spawning Chrome, wait only for the configured CDP port."""
    _ = user_data
    _ = profile_dir
    return _wait_cdp_port_after_launch(int(preferred or _grok_cdp_port()), timeout_s=timeout_s)


def _spawn_grok_chrome_window(
    pages: list[str],
    *,
    user_data: str,
    profile_dir: str,
    debug_port: int = 0,
) -> None:
    """Start daily Chrome with Grok tab(s). Does not wait for CDP."""
    exe = (getattr(config, "CHROME_EXE", "") or "").strip()
    if not exe or not Path(exe).is_file():
        raise RuntimeError(f"Chrome executable not found: {exe}")
    profile_label = (getattr(config, "GEMINI_CHROME_PROFILE", "") or "").strip()
    args = [
        exe,
        f"--user-data-dir={user_data}",
        f"--profile-directory={profile_dir}",
        f"--remote-debugging-port={int(debug_port)}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        *pages,
    ]
    log(
        f"spawn Grok Chrome debug_port={debug_port}: "
        f"profile={profile_dir} account={profile_label!r} tabs={len(pages)}"
    )
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _grok_cdp_port() -> int:
    return int(getattr(config, "GROK_CDP_PORT", 9222) or 9222)


def _hermes_cdp_port_live() -> int | None:
    """CDP port if HermesChromeCDP is already up (shared by grv / nbi / itc)."""
    port = _grok_cdp_port()
    user_data = _chrome_cdp_user_data_dir()
    profile_dir = resolve_chrome_profile_directory(
        getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    return _discover_grok_cdp_port(user_data, profile_dir, port)


def _resolve_hermes_cdp_attach_port(*, attach_only: bool = True) -> int:
    """Connect to HermesChromeCDP on 9222 — no profile verification.

    User may launch Chrome manually with any ``--profile-directory``; attach
    paths must not kill, relaunch, or reject based on session/profile mismatch.
    """
    preferred = int(_grok_cdp_port())
    if cdp_ready(preferred):
        log(
            f"HermesChromeCDP attach-only: port {preferred} "
            f"(skip profile verify — use whatever Chrome you opened)"
        )
        return preferred
    if attach_only:
        raise RuntimeError(
            f"HermesChromeCDP 未在 {preferred} 监听。"
            "请用 --remote-debugging-port=9222 "
            "--user-data-dir=%LOCALAPPDATA%\\HermesChromeCDP 启动 Chrome，"
            "并保持 NotebookLM 标签页打开。"
        )
    return 0


def hermes_cdp_is_open() -> bool:
    """True when port 9222 answers — regardless of which profile owns it."""
    return cdp_ready(int(_grok_cdp_port()))


def _hermes_cdp_open_urls(port: int, urls: list[str]) -> None:
    """Bring an existing tab to front or open a new tab on HermesChromeCDP."""
    pages = [u.strip() for u in urls if (u or "").strip()]
    if not pages:
        return
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        if not browser.contexts:
            return
        ctx = browser.contexts[0]
        for url in pages:
            key = url.split("?")[0].rstrip("/").lower()
            hit = False
            for pg in ctx.pages:
                pg_url = (pg.url or "").split("?")[0].rstrip("/").lower()
                if key in pg_url or pg_url in key:
                    try:
                        pg.bring_to_front()
                    except Exception:
                        pass
                    hit = True
                    break
            if not hit:
                pg = ctx.new_page()
                pg.goto(url, wait_until="domcontentloaded", timeout=60_000)


def ensure_hermes_cdp_chrome(
    *urls: str,
    timeout_s: float = 45.0,
    attach_only: bool = False,
) -> int:
    """Attach to or launch HermesChromeCDP on GROK_CDP_PORT (9222).

    Same Chrome instance for ``grv``, ``nbi``, and ``itc`` **only when the
    selected ``GEMINI_CHROME_PROFILE`` already owns that instance**. Chrome
    ignores ``--profile-directory`` if HermesChromeCDP is already running, so
    a mismatch (e.g. ``nbi 2`` while ocreativeteen is on 9222) must restart.

    ``attach_only=True``: never kill/relaunch — connect to whatever is already
    on 9222 (used by ``nbif`` / ``itc`` / resume after manual review).
    """
    exe = (getattr(config, "CHROME_EXE", "") or "").strip()
    if not exe or not Path(exe).is_file():
        if attach_only:
            live = _hermes_cdp_port_live()
            if live and cdp_ready(live):
                if urls:
                    _hermes_cdp_open_urls(live, list(urls))
                return live
        raise RuntimeError(f"Chrome executable not found: {exe}")

    user_data = _chrome_cdp_user_data_dir()
    Path(user_data).mkdir(parents=True, exist_ok=True)
    profile_dir = resolve_chrome_profile_directory(
        getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    profile_label = (getattr(config, "GEMINI_CHROME_PROFILE", "") or "").strip()
    preferred = _grok_cdp_port()

    live_port, live_dir = _hermes_cdp_active_profile(user_data, preferred)
    session_dir = load_hermes_cdp_session().get("profile_dir") or ""
    active_dir = live_dir or session_dir

    if attach_only:
        port = live_port or (preferred if cdp_ready(preferred) else None)
        if not port:
            raise RuntimeError(
                f"HermesChromeCDP 未在 {preferred} 运行。"
                "请保持已打开的 NotebookLM Chrome，不要关闭。"
            )
        log(
            f"HermesChromeCDP attach-only on {port} "
            f"(live profile={active_dir or 'unknown'}; want {profile_dir})"
        )
        if urls:
            _hermes_cdp_open_urls(port, list(urls))
        return port

    if live_port and _profile_dirs_match(active_dir, profile_dir):
        log(
            f"HermesChromeCDP reuse on {live_port} "
            f"profile={profile_dir} ({profile_label})"
        )
        if live_dir:
            save_hermes_cdp_session(profile_dir=profile_dir, profile=profile_label)
        if urls:
            _hermes_cdp_open_urls(live_port, list(urls))
        return live_port
    if live_port:
        log(
            f"HermesChromeCDP is {active_dir or 'unknown'} on {live_port}, "
            f"but this command wants {profile_dir} ({profile_label}) — restarting"
        )
        _kill_hermes_cdp_chrome(user_data)

    pages = [u.strip() for u in urls if (u or "").strip()]
    if pages:
        log(
            f"launch HermesChromeCDP port={preferred} profile={profile_dir} "
            f"account={profile_label!r} urls={pages}"
        )
        _spawn_grok_chrome_window(
            pages,
            user_data=user_data,
            profile_dir=profile_dir,
            debug_port=preferred,
        )
    else:
        args = [
            exe,
            f"--remote-debugging-port={preferred}",
            f"--user-data-dir={user_data}",
            f"--profile-directory={profile_dir}",
            "--remote-allow-origins=*",
            "--remote-debugging-address=127.0.0.1",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        log(
            f"launch HermesChromeCDP port={preferred} user-data-dir={user_data} "
            f"profile={profile_dir} account={profile_label!r}"
        )
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    port = _wait_grok_cdp_port(user_data, profile_dir, preferred, timeout_s=timeout_s)
    if not port:
        raise RuntimeError(
            f"HermesChromeCDP 未在 {preferred} 就绪。\n"
            f"user-data-dir={user_data}\n"
            f"profile-directory={profile_dir}\n"
            f"account={profile_label}\n"
            "请确认 CHROME_EXE 路径，或手工运行 D:\\Hermes\\run_grok_imagine.bat 验证。"
        )
    save_hermes_cdp_session(profile_dir=profile_dir, profile=profile_label)
    return port


def ensure_grok_cdp(*urls: str, timeout_s: float = 30.0) -> int:
    """Launch HermesChromeCDP Chrome with CDP (same model as D:\\Hermes\\grok_paste)."""
    return ensure_hermes_cdp_chrome(*urls, timeout_s=timeout_s)


def _grok_attach_cdp_port(*, allow_launch: bool = False) -> int:
    """Attach to HermesChromeCDP. ``grv`` may launch/switch profile; others reuse only."""
    user_data = _chrome_cdp_user_data_dir()
    profile_dir = resolve_chrome_profile_directory(
        getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    profile_label = (getattr(config, "GEMINI_CHROME_PROFILE", "") or "").strip()
    preferred = _grok_cdp_port()

    if allow_launch:
        return ensure_hermes_cdp_chrome(GROK_IMAGINE_URL)

    live_port, live_dir = _hermes_cdp_active_profile(user_data, preferred)
    session_dir = load_hermes_cdp_session().get("profile_dir") or ""
    active_dir = live_dir or session_dir
    port = live_port or _discover_grok_cdp_port(user_data, profile_dir, preferred)
    if port and _profile_dirs_match(active_dir, profile_dir):
        log(f"HermesChromeCDP reuse on {port} (no launch)")
        return port
    if port:
        raise RuntimeError(
            f"Grok Chrome 当前是 {active_dir or 'unknown'}，"
            f"但需要 {profile_dir} ({profile_label})。"
            f"请先 grv N 切换 profile。"
        )
    raise RuntimeError(
        "Grok Imagine 还没打开。请先 grv 1 开标签并贴好封面图，再发 gri。"
        f"（HermesChromeCDP 端口 {preferred} 未连接）"
    )


def _grok_resolve_cdp_port(*urls: str, timeout_s: float = 30.0) -> int:
    """Reuse existing Grok CDP (do not launch). Used by grv prep."""
    return _grok_attach_cdp_port(allow_launch=False)


def ensure_chrome_cdp() -> None:
    """Legacy alias — always HermesChromeCDP + profile-aware launch."""
    ensure_hermes_cdp_chrome(GEMINI_URL)


def _grok_imagine_pages(ctx: BrowserContext) -> list[Page]:
    """Imagine tabs in real browser tab order (same CDP Chrome as ``grv``)."""
    return [
        pg
        for pg in ctx.pages
        if "grok.com/imagine" in (pg.url or "")
    ]


def _grok_open_imagine_tabs(
    port: int, n: int, *, fresh: bool = False
) -> list[Page]:
    """Open or ensure *n* ``grok.com/imagine`` tabs on the CDP Chrome."""
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        if not browser.contexts:
            raise RuntimeError("Grok CDP connected but no browser context")
        ctx = browser.contexts[0]
        if fresh:
            pages: list[Page] = []
            for _ in range(n):
                pg = ctx.new_page()
                pg.goto(GROK_IMAGINE_URL, wait_until="domcontentloaded", timeout=60_000)
                pages.append(pg)
                time.sleep(0.5)
            log(f"Grok CDP: opened {len(pages)} fresh imagine tab(s)")
            return pages
        pages = _grok_imagine_pages(ctx)
        need = max(0, n - len(pages))
        log(f"Grok CDP port {port}: have {len(pages)} imagine tab(s), need {need} more")
        for _ in range(need):
            pg = ctx.new_page()
            pg.goto(GROK_IMAGINE_URL, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(0.6)
        pages = _grok_imagine_pages(ctx)
        if len(pages) < n:
            raise RuntimeError(
                f"Grok CDP opened {len(pages)} tab(s), expected {n}."
            )
        return pages


def ensure_gemini_cdp(timeout_s: float = 30.0) -> int:
    """HermesChromeCDP for Gemini — same profile-aware launch as nbi/grv."""
    return ensure_hermes_cdp_chrome(GEMINI_URL, timeout_s=timeout_s)


def _gemini_profile_index() -> int:
    """Gemini always uses profile 1 (ocreativeteen), not the last ``nbi`` pick."""
    return 1


def _ensure_gemini_chrome_profile() -> str:
    """Pin Gemini to profile 1 so ``nbi 2`` does not leave ``gem`` on another account."""
    import config

    selected = config.set_gemini_chrome_profile(_gemini_profile_index())
    label = (selected.get("label") or "").strip()
    log(f"gem profile → {_gemini_profile_index()} ({label})")
    return label


def _gemini_login_help(profile_label: str = "") -> str:
    user_data = _chrome_cdp_user_data_dir()
    profile_dir = resolve_chrome_profile_directory(
        profile_label or getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    return (
        "这个 Chrome 还没登录 Google（HermesChromeCDP，不是日常 Chrome）。\n"
        f"user-data-dir={user_data}\n"
        f"profile-directory={profile_dir}\n"
        f"账号={profile_label or getattr(config, 'GEMINI_CHROME_PROFILE', '')}\n"
        "请在 **gem 刚弹出的那个窗口** 里登录一次；登录会保存在 HermesChromeCDP。\n"
        "日常 Chrome 里登过不算。nbi 换号会重启 HermesChromeCDP，但各 Profile 的登录各自保留。"
    )


def write_windows_clipboard(text: str) -> None:
    script = (
        "$t = [Console]::In.ReadToEnd(); "
        "Set-Clipboard -Value $t"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        input=text or "",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Set-Clipboard failed")


class BrowserController:
    def __init__(self, playwright: Playwright):
        self.p = playwright
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.owned_context = False

    def connect(self) -> BrowserContext:
        """
        Attach to existing Chrome first via CDP. If CDP is unavailable, launch a
        persistent browser profile.
        """
        cdp_url = os.environ.get("HERMES_CDP_URL", "").strip()
        if not cdp_url:
            port = int(getattr(config, "CHROME_REMOTE_DEBUGGING_PORT", 9222) or 9222)
            cdp_url = f"http://127.0.0.1:{port}"

        if cdp_url:
            try:
                log(f"connecting to existing Chrome via CDP: {cdp_url}")
                self.browser = self.p.chromium.connect_over_cdp(cdp_url)

                contexts = self.browser.contexts
                if not contexts:
                    raise RuntimeError("CDP Chrome has no browser context")

                self.context = contexts[0]
                self.owned_context = False
                log("attached to existing Chrome")
                return self.context
            except Exception as exc:
                log(f"CDP connection failed: {exc}")

        user_data_dir = (
            os.environ.get("HERMES_CHROME_USER_DATA_DIR", "").strip()
            or _chrome_cdp_user_data_dir()
        )
        profile = (
            os.environ.get("HERMES_CHROME_PROFILE", "").strip()
            or resolve_chrome_profile_directory(
                getattr(config, "GEMINI_CHROME_PROFILE", "")
            )
        )
        channel = os.environ.get("HERMES_BROWSER_CHANNEL", "").strip() or None

        launch_args = {}
        if profile:
            launch_args["args"] = [f"--profile-directory={profile}"]

        log(f"launching persistent HermesChromeCDP profile: {user_data_dir}")

        try:
            self.context = self.p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel=channel,
                viewport=None,
                **launch_args,
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not launch persistent Chrome profile. "
                "If your normal Chrome is already open, use CDP attachment "
                "(HERMES_CDP_URL or --remote-debugging-port=9222) or close Chrome "
                "before using the profile."
            ) from exc

        self.owned_context = True
        return self.context

    def close(self) -> None:
        if os.environ.get("HERMES_KEEP_BROWSER", "true").lower() in {
            "0", "false", "no"
        }:
            if self.owned_context and self.context:
                try:
                    self.context.close()
                except Exception:
                    pass

    def find_or_create_page(self, url: str) -> Page:
        assert self.context is not None

        for page in self.context.pages:
            try:
                if "gemini.google.com" in page.url:
                    page.bring_to_front()
                    return page
            except Exception:
                pass

        page = self.context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
        return page


def wait_for_gemini_input(page: Page) -> Any:
    """Find Gemini's prompt box (home pill or active chat). Playwright DOM, not mouse coords."""
    deadline = time.monotonic() + DEFAULT_TIMEOUT_MS / 1000

    def _pick(loc) -> Any | None:
        try:
            if loc.count() == 0:
                return None
            target = loc.last if loc.count() > 1 else loc.first
            if target.is_visible():
                return target
        except Exception:
            pass
        return None

    placeholder_patterns = (
        re.compile(r"ask gemini", re.I),
        re.compile(r"enter a prompt", re.I),
        re.compile(r"向 Gemini", re.I),
        re.compile(r"询问 Gemini", re.I),
    )
    selectors = (
        "rich-textarea",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "textarea",
        "div.ql-editor",
        "[aria-label*='prompt' i]",
        "[aria-label*='Ask Gemini' i]",
        "[data-placeholder*='Ask Gemini' i]",
    )

    while time.monotonic() < deadline:
        try:
            loc = page.get_by_role("textbox")
            hit = _pick(loc)
            if hit:
                log("gemini input: role=textbox")
                return hit
        except Exception:
            pass
        for pat in placeholder_patterns:
            try:
                hit = _pick(page.get_by_placeholder(pat))
                if hit:
                    log(f"gemini input: placeholder {pat.pattern}")
                    return hit
            except Exception:
                pass
        for sel in selectors:
            try:
                hit = _pick(page.locator(sel))
                if hit:
                    log(f"gemini input: {sel}")
                    return hit
            except Exception:
                pass
        time.sleep(0.35)

    raise RuntimeError(
        "Gemini input was not found. The browser may be logged out, "
        "blocked by a consent page, or the Gemini UI may have changed."
    )


def is_login_page(page: Page) -> bool:
    """True only when Gemini chat UI is missing (not sidebar 'Sign in to save')."""
    try:
        loc = page.get_by_role("textbox")
        if loc.count() and loc.last.is_visible():
            return False
    except Exception:
        pass
    for sel in (
        "rich-textarea",
        "div[contenteditable='true'][role='textbox']",
        "[data-placeholder*='Ask Gemini' i]",
    ):
        try:
            loc = page.locator(sel).last
            if loc.count() and loc.is_visible():
                return False
        except Exception:
            continue
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        return False
    if "where should we start" in text or "ask gemini" in text:
        return False
    login_markers = (
        "choose an account",
        "use another account",
        "选择账号",
    )
    if any(marker in text for marker in login_markers):
        return True
    # Primary Sign in wall (ignore sidebar "sign in to save activity")
    if "sign in to save" in text:
        return False
    return bool(re.search(r"\bsign in\b", text) or re.search(r"\blog in\b", text))


def _editor_text(editor) -> str:
    try:
        return (editor.inner_text(timeout=2000) or "").strip()
    except Exception:
        return ""


def _click_send_button(page: Page) -> bool:
    """Click the up-arrow send button by DOM, never by screen coordinates."""
    for selector in (
        'button.send-button',
        'button[aria-label*="Send" i]',
        'button[aria-label*="发送"]',
        'button[data-test-id*="send"]',
        'button[mattooltip*="Send" i]',
    ):
        try:
            loc = page.locator(selector).last
            if loc.count() and loc.is_visible() and loc.is_enabled():
                loc.click(timeout=3000)
                log(f"gem: clicked send via {selector}")
                return True
        except Exception:
            continue
    return False


def submit_gemini_prompt(page: Page, prompt: str) -> None:
    """Put the prompt in the box and start generation. DOM only — no mouse coords."""
    editor = wait_for_gemini_input(page)
    editor.click(timeout=5000)
    time.sleep(0.15)

    filled = False
    try:
        editor.fill(prompt, timeout=8000)
        filled = _editor_text(editor)[:60] == prompt.strip()[:60]
    except Exception as exc:
        log(f"editor.fill failed: {exc}")
    if not filled:
        try:
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.insert_text(prompt)
            filled = _editor_text(editor)[:60] == prompt.strip()[:60]
        except Exception as exc:
            log(f"insert_text failed: {exc}")
    if not filled:
        raise RuntimeError("提示词没能写进 Gemini 输入框（DOM 层）。")

    log(f"gem: prompt in editor ({len(prompt)} chars)")

    # Sent == the editor clears. Try Enter, then the send button, then Enter again.
    for attempt in range(3):
        if attempt == 1:
            _click_send_button(page)
        else:
            editor.press("Enter")
            log(f"gem: pressed Enter (try {attempt + 1})")
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if len(_editor_text(editor)) < 20:
                log("gem: prompt submitted (editor cleared)")
                return
            time.sleep(0.25)

    raise RuntimeError(
        "提示词已贴进输入框，但 Gemini 没有开始生成。请手工按一次回车，再发 gem_copy。"
    )


def response_texts(page: Page) -> list[str]:
    selectors = [
        ".model-response-text",
        "[data-message-author-role='model']",
        "main .markdown",
        "message-content",
        "code",
        "pre",
        "[class*='response']",
    ]

    results: list[str] = []
    for selector in selectors:
        try:
            loc = page.locator(selector)
            count = loc.count()
            for i in range(count):
                try:
                    txt = loc.nth(i).inner_text(timeout=2000).strip()
                    if txt:
                        results.append(txt)
                except Exception:
                    pass
        except Exception:
            pass

    if not results:
        try:
            txt = page.locator("main").inner_text(timeout=2000).strip()
            if txt:
                results.append(txt)
        except Exception:
            pass

    seen = set()
    unique = []
    for txt in results:
        if txt not in seen:
            unique.append(txt)
            seen.add(txt)
    return unique


def extract_json_array(text: str) -> Optional[list[Any]]:
    if not text:
        return None

    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "").strip()

    # Fast path
    try:
        value = json.loads(cleaned)
        if isinstance(value, list):
            return value
    except Exception:
        pass

    # Search for the first valid JSON array
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\[", cleaned):
        start = match.start()
        try:
            value, end = decoder.raw_decode(cleaned[start:])
            if isinstance(value, list):
                return value
        except Exception:
            continue

    return None


def _expected_scene_count(prompt_text: str = "") -> int:
    from utility.telegram_session import story_scene_count

    return story_scene_count(prompt_text=prompt_text)


def validate_scene_json(value: Any, expected: int | None = None) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Gemini output is not a JSON array")

    exp = int(expected) if expected is not None and int(expected) >= 1 else _expected_scene_count()
    if exp < 1:
        raise ValueError(
            "还没有记下 LM 场景数。先在 SCENE 发 lm（如 lm 4），再跑 gem。"
        )
    if len(value) != exp:
        raise ValueError(f"Expected {exp} scenes, received {len(value)}")

    for index, scene in enumerate(value, start=1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} is not a JSON object")

    return value


def _gemini_is_generating(page: Page) -> bool:
    """A stop/pause control is present only while the answer is streaming."""
    for selector in (
        'button[aria-label*="Stop" i]',
        'button[aria-label*="停止"]',
        'button.stop-button',
    ):
        try:
            loc = page.locator(selector).last
            if loc.count() and loc.is_visible():
                return True
        except Exception:
            continue
    return False


def _gemini_code_block_texts(page: Page) -> list[str]:
    """Read the rendered code blocks straight out of the DOM."""
    out: list[str] = []
    try:
        out = page.evaluate(
            """() => {
                const nodes = document.querySelectorAll(
                    'code-block pre, code-block code, pre code, pre'
                );
                return Array.from(nodes)
                    .map(n => n.innerText || n.textContent || '')
                    .filter(t => t && t.trim().length > 40);
            }"""
        ) or []
    except Exception as exc:
        log(f"code block read failed: {exc}")
    return [str(t) for t in out]


def wait_for_gemini_json(page: Page, expected: int | None = None) -> list[Any]:
    """Poll the DOM until a valid N-scene JSON array is fully rendered.

    Reads the code block text directly, so no Copy icon click is needed.
    """
    exp = int(expected) if expected is not None and int(expected) >= 1 else _expected_scene_count()
    if exp < 1:
        raise RuntimeError(
            "还没有记下 LM 场景数。先在 SCENE 发 lm（如 lm 4），再跑 gem。"
        )
    deadline = time.monotonic() + GENERATION_TIMEOUT_MS / 1000
    stable: list[Any] | None = None
    stable_since = 0.0

    while time.monotonic() < deadline:
        candidates = _gemini_code_block_texts(page)
        if not candidates:
            candidates = response_texts(page)

        parsed: list[Any] | None = None
        for text in reversed(candidates):
            found = extract_json_array(text)
            if found is None:
                continue
            try:
                parsed = validate_scene_json(found, exp)
                break
            except ValueError:
                continue

        if parsed is not None and not _gemini_is_generating(page):
            if stable is not None and json.dumps(
                stable, ensure_ascii=False, sort_keys=True
            ) == json.dumps(parsed, ensure_ascii=False, sort_keys=True):
                if time.monotonic() - stable_since >= 1.5:
                    log(f"gem: JSON ready — {len(parsed)} scenes (DOM)")
                    return parsed
            else:
                stable = parsed
                stable_since = time.monotonic()
        else:
            state = "generating" if _gemini_is_generating(page) else "no valid JSON yet"
            log(f"gem: waiting — {state}")

        time.sleep(1.2)

    raise RuntimeError(
        f"Gemini did not produce a valid {exp}-scene JSON array within "
        f"{GENERATION_TIMEOUT_MS // 1000} seconds."
    )


def read_windows_clipboard() -> str:
    commands = [
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw",
        ],
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw",
        ],
    ]

    last_error = None
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if result.returncode == 0:
                value = result.stdout.strip()
                if value:
                    return value
            last_error = result.stderr.strip() or f"exit={result.returncode}"
        except Exception as exp:
            last_error = str(exp)

    raise RuntimeError(f"Windows clipboard is empty/unreadable: {last_error}")


def handle_gemini_clipboard() -> str:
    prompt_text = read_windows_clipboard()

    if len(prompt_text) < 400:
        raise RuntimeError(
            f"Clipboard content is too short for the Story prompt "
            f"({len(prompt_text)} chars). Refusing to send. "
            "Make sure 'select_4step' succeeded and the long prompt is on the clipboard."
        )

    log(f"clipboard prompt loaded: {len(prompt_text)} characters")
    return handle_gemini(prompt_text)


def _find_gemini_chrome_hwnd() -> Optional[int]:
    """Only a window whose title looks like Gemini. Never a random Chrome tab."""
    from cli.win_gui_tasks import enum_windows_safe

    for sub in ("Gemini", "gemini.google", "Google Gemini"):
        hits = enum_windows_safe(sub=sub)
        if hits:
            return hits[-1][0]
    return None


def _wait_for_gemini_hwnd(timeout_s: float = 20.0) -> Optional[int]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hwnd = _find_gemini_chrome_hwnd()
        if hwnd:
            return hwnd
        time.sleep(0.4)
    return _find_gemini_chrome_hwnd()


def _force_english_ime() -> None:
    """Chinese IME does not block Chrome CDP, but can swallow Enter after paste."""
    try:
        user32 = ctypes.windll.user32
        hkl = user32.LoadKeyboardLayoutW("00000409", 1)
        if hkl:
            user32.ActivateKeyboardLayout(hkl, 0)
    except Exception:
        pass


def _click_gemini_new_chat(hwnd: int) -> None:
    """Click the circular New chat on the collapsed left rail (not the + inside Ask Gemini)."""
    import pyautogui

    try:
        import uiautomation as auto

        root = auto.ControlFromHandle(hwnd)
        if root:
            for name in ("New chat", "新对话", "新聊天"):
                try:
                    btn = root.ButtonControl(searchDepth=8, Name=name)
                    if btn.Exists(0.25, 0.05):
                        rect = btn.BoundingRectangle
                        if rect and rect.width() > 0:
                            pyautogui.click(
                                rect.left + rect.width() // 2,
                                rect.top + rect.height() // 2,
                            )
                            log(f"clicked Gemini '{name}'")
                            time.sleep(1.2)
                            return
                except Exception:
                    continue
    except Exception:
        pass

    left, top, width, height = _gemini_window_size(hwnd)
    # Collapsed rail (~48px): Gemini sparkle / New chat, just under Chrome chrome.
    for x_r, y_r in ((0.028, 0.13), (0.022, 0.12), (0.035, 0.15)):
        x, y = left + int(width * x_r), top + int(height * y_r)
        log(f"click Gemini New chat at ({x},{y})")
        pyautogui.click(x, y)
        time.sleep(0.3)
    time.sleep(0.5)


def _instant_click(x: int, y: int) -> None:
    """Teleport cursor and click once — no pyautogui glide."""
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP


def _gemini_client_size(hwnd: int) -> tuple[int, int]:
    try:
        from cli.win_gui_tasks import win32gui

        if win32gui is not None:
            _l, _t, right, bottom = win32gui.GetClientRect(hwnd)
            if right > 0 and bottom > 0:
                return int(right), int(bottom)
    except Exception:
        pass
    _l, _t, w, h = _gemini_window_size(hwnd)
    return int(w), int(h)


def _gemini_client_to_screen(hwnd: int, cx: int, cy: int) -> tuple[int, int]:
    try:
        from cli.win_gui_tasks import win32gui

        if win32gui is not None:
            sx, sy = win32gui.ClientToScreen(hwnd, (int(cx), int(cy)))
            return int(sx), int(sy)
    except Exception:
        pass
    left, top, _w, _h = _gemini_window_size(hwnd)
    return left + int(cx), top + int(cy)


def _reset_gemini_layout_session() -> None:
    global _GEMINI_SIDEBAR_DONE
    _GEMINI_SIDEBAR_DONE = False


def _foreground_gemini(hwnd: int) -> None:
    """Maximize + bring Gemini to front — no sidebar click."""
    from cli.win_gui_tasks import set_foreground, win32con, win32gui

    if win32gui is not None and win32con is not None:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        except Exception:
            pass
    set_foreground(hwnd)
    time.sleep(0.08)


def _prepare_gemini_window(hwnd: int) -> None:
    """Once per gem run: foreground + expand sidebar if collapsed."""
    _foreground_gemini(hwnd)
    _ensure_gemini_sidebar_expanded(hwnd)


def _gemini_sidebar_expanded(hwnd: int) -> bool:
    """True when the left rail shows New chat (expanded). Avoid toggling it closed."""
    try:
        import uiautomation as auto

        root = auto.ControlFromHandle(hwnd)
        if not root:
            return False
        for name in ("New chat", "新对话", "Search chats", "搜索对话"):
            try:
                ctrl = root.TextControl(searchDepth=12, Name=name)
                if ctrl.Exists(0.12, 0.04):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _ensure_gemini_sidebar_expanded(hwnd: int) -> None:
    global _GEMINI_SIDEBAR_DONE
    if _GEMINI_SIDEBAR_DONE:
        return
    if _gemini_sidebar_expanded(hwnd):
        _GEMINI_SIDEBAR_DONE = True
        log("gem step1: sidebar already open")
        return
    cw, ch = _gemini_client_size(hwnd)
    cx = max(28, int(cw * 0.015))
    cy = max(72, int(ch * 0.10))
    x, y = _gemini_client_to_screen(hwnd, cx, cy)
    log(f"gem step1: expand sidebar star ({x},{y})")
    _instant_click(x, y)
    time.sleep(0.45)
    _GEMINI_SIDEBAR_DONE = True


def _ask_gemini_pill_point(hwnd: int, *, y_ratio: float = 0.58) -> tuple[int, int]:
    """Step 2: Ask Gemini pill — main pane center (sidebar already expanded)."""
    cw, ch = _gemini_client_size(hwnd)
    sidebar_w = max(260, int(cw * 0.17))
    cx = sidebar_w + (cw - sidebar_w) // 2
    cy = int(ch * y_ratio)
    return _gemini_client_to_screen(hwnd, cx, cy)


def _json_copy_icon_points(hwnd: int) -> list[tuple[int, int]]:
    """Step 3: copy icon top-right of JSON code block (screenshot red circle)."""
    cw, ch = _gemini_client_size(hwnd)
    sidebar_w = max(260, int(cw * 0.17))
    main_w = cw - sidebar_w
    ratios = (
        (0.84, 0.27),
        (0.80, 0.27),
        (0.84, 0.30),
        (0.78, 0.28),
    )
    return [
        _gemini_client_to_screen(hwnd, sidebar_w + int(main_w * xr), int(ch * yr))
        for xr, yr in ratios
    ]


def _paste_and_submit_gemini(prompt_text: str, x: int, y: int) -> None:
    """一次点击 → 粘贴 → 立刻 Enter，不再二次点鼠标或 Ctrl+A 验证。"""
    import pyautogui

    write_windows_clipboard(prompt_text)
    _instant_click(x, y)
    time.sleep(0.1)
    _force_english_ime()
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.12)
    _force_english_ime()
    pyautogui.press("enter")
    log(f"gem step2: pasted {len(prompt_text)} chars + Enter")


def _scroll_gemini_to_response(hwnd: int) -> None:
    import pyautogui
    from cli.win_gui_tasks import set_foreground

    set_foreground(hwnd)
    time.sleep(0.08)
    pyautogui.press("home")
    time.sleep(0.2)


def paste_prompt_into_gemini_window(prompt_text: str) -> None:
    """Step 1 expand sidebar → step 2 paste + Enter."""
    try:
        import pyautogui
    except Exception as exc:
        raise RuntimeError(f"pyautogui is required to paste into Gemini: {exc}") from exc

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    pyautogui.MINIMUM_DURATION = 0
    hwnd = _find_gemini_chrome_hwnd()
    if not hwnd:
        raise RuntimeError("Chrome/Gemini window not found — cannot paste prompt")

    _prepare_gemini_window(hwnd)

    x, y = _ask_gemini_pill_point(hwnd, y_ratio=0.58)
    log(f"gem step2: Ask Gemini ({x},{y})")
    _paste_and_submit_gemini(prompt_text, x, y)


def _open_fresh_gemini_tab(hwnd: int) -> None:
    """New Chrome tab → gemini.google.com home. Do not reuse the last /app/ session."""
    import pyautogui
    from cli.win_gui_tasks import set_foreground

    set_foreground(hwnd)
    time.sleep(0.2)
    _force_english_ime()
    write_windows_clipboard(GEMINI_URL)
    pyautogui.hotkey("ctrl", "t")
    time.sleep(0.45)
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.15)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.12)
    pyautogui.press("enter")
    log(f"opened new tab → {GEMINI_URL}")
    time.sleep(1.0)
    ready = _wait_for_gemini_hwnd(18.0)
    if ready:
        hwnd = ready
        set_foreground(hwnd)
    time.sleep(2.5)
    _click_gemini_new_chat(hwnd)


_SCENE_JSON_KEYS = {"caption", "voiceover", "visual", "speaking", "actor"}


def _clipboard_is_prompt(text: str, prompt_text: str) -> bool:
    t = (text or "").strip()
    p = (prompt_text or "").strip()
    if not t:
        return False
    if t.startswith("You are a psychological"):
        return True
    if not p:
        return False
    if t == p:
        return True
    if len(t) > 200 and (t.startswith(p[:240]) or p.startswith(t[:240])):
        return True
    return False


def parse_ready_scene_json(
    text: str,
    prompt_text: str = "",
    expected: int | None = None,
) -> Optional[list[Any]]:
    """Return an N-scene array only when clipboard is finished Gemini JSON."""
    if _clipboard_is_prompt(text, prompt_text):
        return None
    parsed = extract_json_array(text)
    if parsed is None:
        return None
    exp = (
        int(expected)
        if expected is not None and int(expected) >= 1
        else _expected_scene_count(prompt_text)
    )
    try:
        validate_scene_json(parsed, exp if exp >= 1 else None)
    except ValueError:
        return None
    first = parsed[0]
    if not isinstance(first, dict):
        return None
    if not (_SCENE_JSON_KEYS & set(first.keys())):
        return None
    return parsed


def _find_copy_button_fast(hwnd: int):
    """One-shot name search for the code-block Copy icon. No tree walk."""
    try:
        import uiautomation as auto
    except Exception:
        return None
    try:
        root = auto.ControlFromHandle(hwnd)
        if not root:
            return None
        for kwargs in (
            {"Name": "Copy code"},
            {"Name": "Copy"},
            {"Name": "复制代码"},
            {"Name": "复制"},
        ):
            try:
                btn = root.ButtonControl(searchDepth=8, **kwargs)
                if btn.Exists(0.2, 0.05):
                    return btn
            except Exception:
                continue
    except Exception:
        return None
    return None


def _gemini_window_size(hwnd: int) -> tuple[int, int, int, int]:
    from cli.win_gui_tasks import get_window_rect

    try:
        left, top, right, bottom = get_window_rect(hwnd)
        if right > left and bottom > top:
            return left, top, right - left, bottom - top
    except Exception:
        pass
    import pyautogui

    sw, sh = pyautogui.size()
    return 0, 0, sw, sh


def _click_json_copy_icon(hwnd: int | None = None, *, idx: int = 0) -> None:
    """Step 3: click JSON block copy icon (expanded-sidebar layout)."""
    if hwnd is None:
        hwnd = _find_gemini_chrome_hwnd()
    if not hwnd:
        return
    points = _json_copy_icon_points(hwnd)
    x, y = points[idx % len(points)]
    log(f"gem step3: copy JSON ({x},{y})")
    _instant_click(x, y)


def wait_and_copy_gemini_json(
    prompt_text: str = "",
    min_wait_s: float = 8.0,
    *,
    layout_ready: bool = False,
) -> str:
    """Wait for JSON, click copy icon. Does not re-open sidebar when layout_ready."""
    from cli.win_gui_tasks import set_foreground

    hwnd = _find_gemini_chrome_hwnd()
    if hwnd:
        if layout_ready:
            _foreground_gemini(hwnd)
        else:
            _prepare_gemini_window(hwnd)
    log("waiting for Gemini to finish generating JSON…")
    deadline = time.monotonic() + GENERATION_TIMEOUT_MS / 1000
    started = time.monotonic()
    last_geo = 0.0
    geo_every_s = 3.0
    copy_idx = 0

    while time.monotonic() < started + min_wait_s and time.monotonic() < deadline:
        remaining = started + min_wait_s - time.monotonic()
        log(f"generation still running, wait {remaining:.0f}s before first copy")
        time.sleep(min(4.0, max(1.0, remaining)))

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - started
        if hwnd is None:
            hwnd = _find_gemini_chrome_hwnd()
            if hwnd:
                set_foreground(hwnd)
        def _read_scenes() -> Optional[list[Any]]:
            try:
                text = read_windows_clipboard()
            except Exception as exc:
                log(f"clipboard read failed: {exc}")
                return None
            exp = _expected_scene_count(prompt_text)
            parsed = parse_ready_scene_json(text, prompt_text, expected=exp or None)
            if parsed is None:
                log(f"JSON not ready yet ({elapsed:.0f}s), clipboard={len(text)} chars")
            return parsed

        btn = _find_copy_button_fast(hwnd) if hwnd else None
        if btn:
            try:
                rect = btn.BoundingRectangle
                if rect and rect.width() > 0:
                    _instant_click(
                        rect.left + rect.width() // 2,
                        rect.top + rect.height() // 2,
                    )
                    log("clicked Gemini Copy button")
                    time.sleep(0.6)
                    parsed = _read_scenes()
                    if parsed is not None:
                        log(f"copied {len(parsed)} scenes after {elapsed:.0f}s")
                        return json.dumps(parsed, ensure_ascii=False, indent=2)
            except Exception as exc:
                log(f"Copy button click failed: {exc}")
        if (time.monotonic() - last_geo) >= geo_every_s:
            if hwnd:
                _scroll_gemini_to_response(hwnd)
            _click_json_copy_icon(hwnd, idx=copy_idx)
            copy_idx += 1
            last_geo = time.monotonic()
            time.sleep(0.6)
            parsed = _read_scenes()
            if parsed is not None:
                log(f"copied {len(parsed)} scenes after {elapsed:.0f}s")
                return json.dumps(parsed, ensure_ascii=False, indent=2)
        time.sleep(2.0)

    exp = _expected_scene_count(prompt_text)
    raise RuntimeError(
        f"等了 3 分钟仍没拿到完整 {exp or '?'} 场 JSON。"
        "请点代码块右上角复制，再发：content <json>"
    )


def _open_gemini_new_chat(page: Page) -> None:
    """Always start a fresh chat so the previous answer cannot be re-read."""
    try:
        if "gemini.google.com" not in (page.url or ""):
            page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
            time.sleep(1.5)
            return
    except Exception:
        pass
    for selector in (
        'button[aria-label*="New chat" i]',
        'button[aria-label*="新对话"]',
        'a[aria-label*="New chat" i]',
    ):
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=3000)
                log("gem: opened New chat")
                time.sleep(1.2)
                return
        except Exception:
            continue
    try:
        page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
        time.sleep(1.5)
    except Exception as exc:
        log(f"could not reset Gemini chat: {exc}")


def _handle_gemini_cdp(prompt_text: str) -> str:
    """CDP/DOM path: exact element targeting, zero screen coordinates."""
    profile_label = _ensure_gemini_chrome_profile()
    port = ensure_gemini_cdp()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            contexts = browser.contexts
            if not contexts:
                raise RuntimeError("CDP Chrome has no browser context")
            context = contexts[0]

            page = None
            for candidate in context.pages:
                try:
                    if "gemini.google.com" in (candidate.url or ""):
                        page = candidate
                        break
                except Exception:
                    continue
            if page is None:
                page = context.new_page()
                page.goto(
                    GEMINI_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS
                )

            page.set_default_timeout(DEFAULT_TIMEOUT_MS)
            page.bring_to_front()
            page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)

            if is_login_page(page):
                raise RuntimeError(_gemini_login_help(profile_label))

            _open_gemini_new_chat(page)
            submit_gemini_prompt(page, prompt_text)
            exp = _expected_scene_count(prompt_text)
            scenes = wait_for_gemini_json(page, expected=exp or None)
            return json.dumps(scenes, ensure_ascii=False, indent=2)
        finally:
            try:
                browser.close()
            except Exception:
                pass


GEMINI_PASTED_MARK = "__GEMINI_PASTED__"


def handle_gemini(prompt_text: str) -> str:
    """gem: CDP 直连 DOM —— 精确定位输入框、回车生成、直接读回 JSON。"""
    write_windows_clipboard(prompt_text)
    try:
        scene_json = _handle_gemini_cdp(prompt_text)
    except Exception as exc:
        msg = str(exc)
        if "还没登录 Google" in msg or "HermesChromeCDP" in msg:
            raise
        log(f"CDP path failed: {exc}")
        return _handle_gemini_mouse(prompt_text)
    try:
        write_windows_clipboard(scene_json)
    except Exception as exc:
        log(f"clipboard write failed: {exc}")
    return scene_json


def copy_existing_gemini_json() -> str:
    """gem_copy: read the JSON already on screen out of the DOM. No re-send."""
    try:
        _ensure_gemini_chrome_profile()
        port = ensure_gemini_cdp()
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            try:
                page = None
                for context in browser.contexts:
                    for candidate in context.pages:
                        try:
                            if "gemini.google.com" in (candidate.url or ""):
                                page = candidate
                                break
                        except Exception:
                            continue
                    if page is not None:
                        break
                if page is None:
                    raise RuntimeError("CDP Chrome 里没有 Gemini 标签页")
                page.bring_to_front()
                exp = _expected_scene_count()
                scenes = wait_for_gemini_json(page, expected=exp or None)
                out = json.dumps(scenes, ensure_ascii=False, indent=2)
                write_windows_clipboard(out)
                return out
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as exc:
        log(f"CDP copy failed: {exc}")
        return wait_and_copy_gemini_json(min_wait_s=1.0, layout_ready=False)


def _handle_gemini_mouse(prompt_text: str) -> str:
    """Fallback only: screen-coordinate path for when CDP cannot be started."""
    log("falling back to screen-coordinate path (HermesChromeCDP)")
    _reset_gemini_layout_session()
    _ensure_gemini_chrome_profile()
    write_windows_clipboard(prompt_text)
    if not _find_gemini_chrome_hwnd():
        try:
            ensure_hermes_cdp_chrome(GEMINI_URL)
            log("launched HermesChromeCDP → Gemini")
        except Exception as exc:
            log(f"HermesChromeCDP launch failed: {exc}")
        if not _wait_for_gemini_hwnd(20.0):
            raise RuntimeError(
                "找不到 Gemini 窗口。请在 HermesChromeCDP 打开 gemini.google.com 并登录，再发 gem。\n"
                + _gemini_login_help()
            )
    paste_prompt_into_gemini_window(prompt_text)
    return wait_and_copy_gemini_json(prompt_text, layout_ready=True)


def read_prompt_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def launch_chrome_profile_window(*urls: str, debug_port: int | None = None) -> str:
    """Open URL(s) in HermesChromeCDP (never daily Chrome User Data).

    Multiple URLs become multiple tabs in that window (Grok Imagine × N).
  When *debug_port* is set, Chrome exposes CDP on that port.
    """
    pages = [u.strip() for u in urls if (u or "").strip()]
    if not pages:
        raise RuntimeError("no URL to open in Chrome")
    exe = (getattr(config, "CHROME_EXE", "") or "").strip()
    if not exe or not Path(exe).is_file():
        raise RuntimeError(f"Chrome executable not found: {exe}")
    profile_dir = resolve_chrome_profile_directory(
        getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    user_data = _chrome_cdp_user_data_dir()
    Path(user_data).mkdir(parents=True, exist_ok=True)
    preferred = int(debug_port or _grok_cdp_port())
    args = [
        exe,
        f"--user-data-dir={user_data}",
        f"--profile-directory={profile_dir}",
        f"--remote-debugging-port={preferred}",
        "--remote-allow-origins=*",
        "--remote-debugging-address=127.0.0.1",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        *pages,
    ]
    log("launching HermesChromeCDP: " + " ".join(args))
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return profile_dir


def _notebooklm_title_match(title: str) -> bool:
    low = (title or "").lower()
    return any(
        token in low
        for token in (
            "notebooklm",
            "notebook.google",
            "story builder",
            "gemini notebook",
        )
    )


def _enum_titled_windows() -> list[tuple[int, str]]:
    from cli.win_gui_tasks import enum_windows_safe

    return enum_windows_safe()


def _find_notebooklm_hwnd(exclude: set[int] | None = None) -> Optional[int]:
    skip = exclude or set()
    for hwnd, title in _enum_titled_windows():
        if hwnd in skip:
            continue
        if _notebooklm_title_match(title):
            return hwnd
    return None


def _wait_notebooklm_hwnd(
    *,
    exclude: set[int] | None = None,
    timeout_s: float = 22.0,
) -> int:
    skip = exclude or set()
    deadline = time.monotonic() + timeout_s
    last_new: Optional[int] = None
    while time.monotonic() < deadline:
        hwnd = _find_notebooklm_hwnd(skip)
        if hwnd:
            return hwnd
        for hwnd, title in _enum_titled_windows():
            if hwnd in skip:
                continue
            low = (title or "").lower()
            if "chrome" in low or "google" in low:
                last_new = hwnd
        time.sleep(0.5)
    if last_new:
        log(f"NotebookLM title not seen; using newest Chrome hwnd={last_new}")
        return last_new
    raise RuntimeError(
        "NotebookLM Chrome window not found. "
        "Check the selected profile is signed in to Google."
    )


def _chrome_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    return _gemini_window_size(hwnd)


def _click_xy(x: int, y: int, *, pause: float = 0.35) -> None:
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.moveTo(x, y, duration=0.08)
    pyautogui.click(x, y)
    time.sleep(pause)


def _right_click_xy(x: int, y: int, *, pause: float = 0.45) -> None:
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.moveTo(x, y, duration=0.08)
    pyautogui.rightClick(x, y)
    time.sleep(pause)


def _click_ratio(hwnd: int, x_r: float, y_r: float, *, pause: float = 0.4) -> None:
    left, top, width, height = _chrome_window_rect(hwnd)
    x = left + int(width * x_r)
    y = top + int(height * y_r)
    log(f"click ratio ({x_r:.2f},{y_r:.2f}) → ({x},{y}) window={width}x{height}")
    _click_xy(x, y, pause=pause)


def _click_rect_center(rect, *, extra_x: int = 0) -> bool:
    try:
        w = rect.width() if callable(getattr(rect, "width", None)) else (rect.right - rect.left)
        h = rect.height() if callable(getattr(rect, "height", None)) else (rect.bottom - rect.top)
        if w <= 0 or h <= 0:
            return False
        x = rect.left + w // 2 + extra_x
        y = rect.top + h // 2
        _click_xy(x, y)
        return True
    except Exception:
        return False


def _uia_root(hwnd: int):
    try:
        from cli.win_gui_tasks import ensure_uia_com

        ensure_uia_com()
    except Exception:
        pass
    try:
        import uiautomation as auto
    except Exception:
        return None
    try:
        return auto.ControlFromHandle(hwnd)
    except Exception:
        return None


def _uia_named(
    hwnd: int,
    name: str,
    control_types: list[str],
    *,
    search_depth: int = 12,
    timeout_s: float = 0.3,
    found_index: int | None = None,
):
    """Name / SubName lookup. No WalkControl (deep scans freeze Chrome)."""
    root = _uia_root(hwnd)
    if root is None:
        return None
    extra = {}
    if found_index:
        extra["foundIndex"] = int(found_index)
    for ctype in control_types:
        ctor = getattr(root, ctype, None)
        if not callable(ctor):
            continue
        for kwargs in ({"Name": name}, {"SubName": name}):
            try:
                ctrl = ctor(searchDepth=search_depth, **kwargs, **extra)
                if ctrl.Exists(timeout_s, 0.05):
                    return ctrl
            except Exception:
                continue
    return None


def _click_named(
    hwnd: int,
    name: str,
    control_types: list[str],
    *,
    extra_x: int = 0,
    search_depth: int = 12,
) -> bool:
    ctrl = _uia_named(hwnd, name, control_types, search_depth=search_depth)
    if not ctrl:
        return False
    try:
        rect = ctrl.BoundingRectangle
    except Exception:
        return False
    log(f"UIA click {name!r}")
    return _click_rect_center(rect, extra_x=extra_x)


def _uia_named_all(
    hwnd: int,
    name: str,
    control_types: list[str],
    *,
    search_depth: int = 14,
    limit: int = 6,
    timeout_s: float = 0.12,
) -> list:
    """Every match for ``name``, via foundIndex (no WalkControl — it freezes Chrome).

    foundIndex counts per control type, so each type is enumerated separately —
    sharing one counter across types silently skips matches.
    """
    found = []
    for ctype in control_types:
        for index in range(1, max(1, limit) + 1):
            ctrl = _uia_named(
                hwnd,
                name,
                [ctype],
                search_depth=search_depth,
                timeout_s=timeout_s,
                found_index=index,
            )
            if ctrl is None:
                break
            found.append(ctrl)
    return found


def _ctrl_box(ctrl) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) for a UIA control, or None when unusable."""
    try:
        rect = ctrl.BoundingRectangle
        left, top, right, bottom = (
            int(rect.left),
            int(rect.top),
            int(rect.right),
            int(rect.bottom),
        )
    except Exception:
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _uia_value(ctrl) -> str:
    """Read text from a UIA edit via ValuePattern (fallback: Name)."""
    if ctrl is None:
        return ""
    try:
        return (ctrl.GetValuePattern().Value or "").strip()
    except Exception:
        pass
    try:
        return (ctrl.Name or "").strip()
    except Exception:
        return ""


def _paste_text_verified(expected: str, actual: str, *, field_label: str = "field") -> None:
    """Raise if pasted text does not look like *expected* (gem-style read-back)."""
    exp = (expected or "").strip()
    got = (actual or "").strip()
    if not exp:
        raise RuntimeError(f"{field_label}: empty prompt")
    if not got:
        raise RuntimeError(
            f"{field_label}: paste failed — editor empty after Ctrl+V"
        )
    min_len = max(32, int(len(exp) * 0.72))
    head = exp[: min(64, len(exp))]
    if len(got) >= min_len:
        log(f"{field_label}: read-back {len(got)} chars (verify ok)")
        return
    if head and (head in got or got[:48] in exp):
        log(f"{field_label}: read-back prefix match ({len(got)} chars)")
        return
    raise RuntimeError(
        f"{field_label}: paste verify failed — "
        f"expected ~{len(exp)} chars, read back {len(got)}"
    )


def _find_grok_composer_edit(hwnd: int):
    for name in ("Ask Grok", "What do you want", "Message"):
        edit = _uia_named(
            hwnd,
            name,
            ["EditControl", "ComboBoxControl"],
            search_depth=14,
            timeout_s=0.25,
        )
        if edit:
            return edit
    return None


def _paste_grok_composer_text(hwnd: int, text: str, *, replace: bool = True) -> None:
    """Paste into Grok composer and verify via UIA read-back."""
    import pyautogui

    pyautogui.FAILSAFE = False
    _click_grok_composer(hwnd)
    time.sleep(0.15)
    edit = _find_grok_composer_edit(hwnd)
    write_windows_clipboard(text)
    _force_english_ime()
    if replace:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.08)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.55)
    actual = _uia_value(edit) if edit else ""
    if edit and len(actual) < 20:
        time.sleep(0.45)
        actual = _uia_value(edit)
    if edit:
        _paste_text_verified(text, actual, field_label="Grok composer")
    else:
        log("Grok composer edit not found by UIA; pasted without read-back")


def _named_exists(
    hwnd: int,
    name: str,
    control_types: list[str],
    *,
    search_depth: int = 12,
    timeout_s: float = 0.25,
) -> bool:
    return _uia_named(
        hwnd, name, control_types, search_depth=search_depth, timeout_s=timeout_s
    ) is not None


def _wait_named(
    hwnd: int,
    name: str,
    control_types: list[str],
    *,
    timeout_s: float = 12.0,
    search_depth: int = 12,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _named_exists(hwnd, name, control_types, search_depth=search_depth):
            return True
        time.sleep(0.4)
    return False


def _notebooklm_quota_hit(hwnd: int) -> bool:
    for name in (
        "daily limit",
        "Daily limit",
        "limit reached",
        "reached your limit",
        "usage limit",
    ):
        if _named_exists(
            hwnd,
            name,
            ["TextControl", "ButtonControl", "HyperlinkControl"],
            timeout_s=0.15,
        ):
            return True
    return False


_NOTEBOOK_CARD_TYPES = [
    "ButtonControl",
    "HyperlinkControl",
    "ListItemControl",
    "GroupControl",
    "CustomControl",
]


def _notebooklm_window_title(hwnd: int) -> str:
    from cli.win_gui_tasks import win32gui

    if not hwnd or win32gui is None:
        return ""
    try:
        return (win32gui.GetWindowText(int(hwnd)) or "").strip()
    except Exception:
        return ""


def _title_looks_like_open_notebook(title: str) -> bool:
    low = (title or "").lower()
    if "story builder" in low:
        return True
    # Home tab is typically just "Gemini Notebook" / "NotebookLM".
    if low in ("gemini notebook", "notebooklm", "notebooklm - google chrome"):
        return False
    if "notebook" in low and any(
        token in low for token in ("story", "builder", "sources")
    ):
        return True
    return False


def _inside_notebook(hwnd: int, *, timeout_s: float = 0.35) -> bool:
    if _named_exists(
        hwnd,
        "Infographic",
        ["ButtonControl", "HyperlinkControl"],
        search_depth=16,
        timeout_s=timeout_s,
    ):
        return True
    return _title_looks_like_open_notebook(_notebooklm_window_title(hwnd))


def _notebooklm_cdp_port() -> int:
    """HermesChromeCDP port — same as ``grv`` (9222)."""
    return _grok_cdp_port()


def _resolve_notebooklm_cdp_port(*, attach_only: bool = False) -> int | None:
    if attach_only:
        try:
            return _resolve_hermes_cdp_attach_port(attach_only=True)
        except RuntimeError:
            return None
    return _hermes_cdp_port_live()


def ensure_notebooklm_cdp(
    *urls: str,
    timeout_s: float = 45.0,
    attach_only: bool = False,
) -> int:
    """HermesChromeCDP for NotebookLM — reuse live 9222 when possible (no kill)."""
    open_urls = [u.strip() for u in urls if (u or "").strip()] or [NOTEBOOKLM_URL]
    if attach_only:
        port = _resolve_hermes_cdp_attach_port(attach_only=True)
        log(f"NotebookLM CDP attach-only port={port}")
        if open_urls:
            _hermes_cdp_open_urls(port, open_urls)
        return port
    live = _hermes_cdp_port_live()
    if live:
        port = live
        if cdp_ready(port):
            log(f"NotebookLM CDP reuse port={port}")
            if open_urls:
                _hermes_cdp_open_urls(port, open_urls)
            return port
    return ensure_hermes_cdp_chrome(*open_urls, timeout_s=timeout_s)


def _create_new_box(hwnd: int) -> tuple[int, int, int, int] | None:
    """Rect of the Recent-row ``Create new notebook`` tile — not the header button."""
    card_types = [
        "ButtonControl",
        "HyperlinkControl",
        "GroupControl",
        "ListItemControl",
        "TextControl",
    ]
    candidates: list[tuple[int, int, int, int]] = []
    for name in ("Create new notebook", "Create new"):
        for ctrl in _uia_named_all(hwnd, name, card_types, search_depth=22, limit=6):
            box = _ctrl_box(ctrl)
            if box and box not in candidates:
                candidates.append(box)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Header "+ Create new" sits high; Recent-row card is lower and usually taller.
    picked = max(candidates, key=lambda b: (b[1], b[3] - b[1]))
    log(f"Create-new anchor picked from {len(candidates)} candidates: {picked}")
    return picked


def _pick_first_recent_card(
    anchor: tuple[int, int, int, int],
    boxes: list[tuple[int, int, int, int]],
) -> tuple[int, int, int, int] | None:
    """Leftmost box sharing the 'Create new' row and sitting to its right.

    Featured notebooks carry the same captions but live in a higher row, so the
    vertical filter is what keeps them out.
    """
    _, a_top, a_right, a_bottom = anchor
    a_mid_y = (a_top + a_bottom) // 2
    a_height = max(1, a_bottom - a_top)

    same_row = [
        box
        for box in dict.fromkeys(boxes)
        if abs((box[1] + box[3]) // 2 - a_mid_y) <= a_height and box[0] >= a_right - 8
    ]
    if not same_row:
        return None
    return min(same_row, key=lambda b: b[0])


def _first_recent_notebook_box(hwnd: int) -> tuple[int, int, int, int] | None:
    """Rect of the first EXISTING notebook card on the NotebookLM home page.

    Every notebook tile carries an 'N sources' caption, so those captions locate
    the cards without a deep tree walk.
    """
    anchor = _create_new_box(hwnd)
    if not anchor:
        return None

    boxes = []
    for ctrl in _uia_named_all(
        hwnd,
        "sources",
        ["TextControl", "ListItemControl", "ButtonControl"],
        search_depth=20,
        limit=6,
    ):
        box = _ctrl_box(ctrl)
        if box:
            boxes.append(box)

    picked = _pick_first_recent_card(anchor, boxes)
    if picked is None:
        log(f"no 'N sources' caption in the Recent row (saw {len(boxes)} captions)")
    else:
        log(f"first Recent notebook card box={picked}")
    return picked


def _return_to_notebooklm_home(hwnd: int) -> bool:
    """Undo a click that navigated somewhere other than a notebook."""
    if _create_new_box(hwnd):
        return True
    import pyautogui

    from cli.win_gui_tasks import set_foreground

    pyautogui.FAILSAFE = False
    set_foreground(hwnd)
    log("click went off-target; going back to the NotebookLM home page")
    pyautogui.hotkey("alt", "left")
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        if _create_new_box(hwnd):
            return True
        time.sleep(0.4)
    return False


def _find_notebooklm_cdp_page(browser):
    hits: list = []
    for ctx in browser.contexts:
        for page in ctx.pages:
            url = (page.url or "").lower()
            if "notebook.google.com" in url or "notebooklm" in url:
                hits.append(page)
    if not hits:
        return None
    for page in hits:
        if "/notebook/" in (page.url or "").lower():
            return page
    return hits[0]


def _run_with_notebooklm_page(fn, port: int | None = None, *, attach_only: bool = False):
    """Call ``fn(page)`` on the live NotebookLM tab via HermesChromeCDP."""
    if port is None:
        if attach_only:
            port = _resolve_hermes_cdp_attach_port(attach_only=True)
        else:
            port = _hermes_cdp_port_live()
    if port is None:
        log(
            f"HermesChromeCDP not on {_grok_cdp_port()}; "
            "itc/nbi will launch it on first use"
        )
        return fn(None)
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            page = _find_notebooklm_cdp_page(browser)
            if page is None:
                log(f"HermesChromeCDP on {port} connected but no notebook tab")
                return fn(None)
            try:
                page.bring_to_front()
            except Exception:
                pass
            return fn(page)
    except Exception as exc:
        log(f"NotebookLM CDP session failed on {port}: {exc}")
        return fn(None)


def _open_notebook_home_card_via_dom(page) -> bool:
    """Click the first existing Recent notebook on the NotebookLM home page."""
    import re

    from playwright.sync_api import TimeoutError as PWTimeout

    try:
        if page.get_by_text("Infographic", exact=False).count() > 0:
            log("CDP/DOM: already inside notebook (Infographic visible)")
            return True
    except Exception:
        pass

    for pattern in (
        re.compile(r"Story Builder", re.I),
        re.compile(r"Young Chinese", re.I),
    ):
        try:
            loc = page.get_by_role("link", name=pattern)
            if loc.count() == 0:
                loc = page.locator("a, [role='button'], [role='link']").filter(
                    has_text=pattern
                )
            if loc.count() > 0:
                loc.first.click(timeout=8000)
                log(f"CDP/DOM: clicked notebook card matching /{pattern.pattern}/")
                page.get_by_text("Infographic", exact=False).first.wait_for(
                    state="visible", timeout=20000
                )
                return True
        except PWTimeout:
            log(f"CDP/DOM: Infographic did not appear after clicking /{pattern.pattern}/")
        except Exception as exc:
            log(f"CDP/DOM: card click failed for /{pattern.pattern}/: {exc}")

    try:
        create = page.get_by_text("Create new notebook", exact=False)
        if create.count() > 0:
            box = create.first.bounding_box()
            if box:
                cy = box["y"] + box["height"] / 2
                sources = page.get_by_text(re.compile(r"\d+\s+sources?", re.I))
                best_el = None
                best_x = None
                for i in range(min(sources.count(), 14)):
                    el = sources.nth(i)
                    b = el.bounding_box()
                    if not b:
                        continue
                    if abs((b["y"] + b["height"] / 2) - cy) > box["height"] * 1.2:
                        continue
                    if b["x"] <= box["x"] + box["width"] - 5:
                        continue
                    if best_x is None or b["x"] < best_x:
                        best_x = b["x"]
                        best_el = el
                if best_el is not None:
                    best_el.click(timeout=8000)
                    log("CDP/DOM: clicked first Recent-row card (right of Create new notebook)")
                    page.get_by_text("Infographic", exact=False).first.wait_for(
                        state="visible", timeout=20000
                    )
                    return True
    except PWTimeout:
        log("CDP/DOM: Infographic did not appear after Recent-row geometry click")
    except Exception as exc:
        log(f"CDP/DOM: Recent-row geometry click failed: {exc}")

    return False


def _open_first_existing_notebook_cdp(port: int, *, timeout_s: float = 22.0) -> bool:
    """Open the first existing Recent notebook via Playwright CDP (no screen coords)."""
    if not cdp_ready(port):
        log(f"NotebookLM CDP not ready on port {port}")
        return False
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        log(f"playwright unavailable for NotebookLM CDP: {exc}")
        return False

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                page = _find_notebooklm_cdp_page(browser)
                if page is None:
                    time.sleep(0.4)
                    continue
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=6000)
                except Exception:
                    pass
                if _open_notebook_home_card_via_dom(page):
                    return True
        except Exception as exc:
            log(f"NotebookLM CDP attempt failed: {exc}")
        time.sleep(0.45)
    return False


def _open_first_existing_notebook(hwnd: int) -> None:
    """Home: first EXISTING Recent notebook (right of Create new). Never create one."""
    if _inside_notebook(hwnd):
        log("already inside a notebook (Infographic visible)")
        return

    def _opened() -> bool:
        if _inside_notebook(hwnd, timeout_s=0.4):
            return True
        return _wait_named(
            hwnd,
            "Infographic",
            ["ButtonControl", "HyperlinkControl"],
            timeout_s=5.0,
            search_depth=16,
        )

    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline and not (
        _create_new_box(hwnd)
        or _named_exists(
            hwnd,
            "Recent notebooks",
            ["TextControl", "GroupControl"],
            search_depth=16,
            timeout_s=0.2,
        )
    ):
        time.sleep(0.4)

    # 1) Story Builder card — try every UIA match (not just the first false positive).
    for ctrl in _uia_named_all(
        hwnd, "Story Builder", _NOTEBOOK_CARD_TYPES + ["TextControl"], search_depth=22, limit=8
    ):
        box = _ctrl_box(ctrl)
        if not box:
            continue
        left, top, right, bottom = box
        x, y = (left + right) // 2, (top + bottom) // 2
        log(f"click Story Builder card at ({x},{y}) box={box}")
        _click_xy(x, y, pause=2.0)
        if _opened():
            return
        _return_to_notebooklm_home(hwnd)

    if _click_named(hwnd, "Story Builder", _NOTEBOOK_CARD_TYPES, search_depth=20):
        log("clicked existing notebook by name: Story Builder")
        if _opened():
            return
        _return_to_notebooklm_home(hwnd)

    # 2) Geometry anchored on the real 'Create new notebook' rect — no hardcoded ratios.
    box = _first_recent_notebook_box(hwnd)
    if box:
        left, top, right, bottom = box
        x, y = (left + right) // 2, (top + bottom) // 2
        log(f"click first Recent notebook card at ({x},{y}) box={box}")
        _click_xy(x, y, pause=2.0)
        if _opened():
            return
        _return_to_notebooklm_home(hwnd)

    # 3) Step right from 'Create new notebook' in increasing strides.
    for factor in (0.75, 1.15, 1.55, 1.95):
        anchor = _create_new_box(hwnd)
        if not anchor:
            break
        _, a_top, a_right, a_bottom = anchor
        x = a_right + int(max(120, a_right - anchor[0]) * factor)
        y = (a_top + a_bottom) // 2
        log(f"probe right of Create new at ({x},{y}) factor={factor}")
        _click_xy(x, y, pause=1.6)
        if _opened():
            return
        _return_to_notebooklm_home(hwnd)

    # 4) UIA-free: Recent row, first card to the right of Create new.
    #    Create new sits ~x 0.08-0.20; Story Builder ~x 0.22-0.38; row ~y 0.56-0.70.
    log("UIA missed the card; ratio-click first Recent notebook (not Create new)")
    for x_r, y_r in (
        (0.28, 0.62),
        (0.30, 0.58),
        (0.26, 0.66),
        (0.32, 0.64),
        (0.28, 0.70),
    ):
        _click_ratio(hwnd, x_r, y_r, pause=1.8)
        if _opened():
            return
        if _title_looks_like_open_notebook(_notebooklm_window_title(hwnd)):
            return
        _return_to_notebooklm_home(hwnd)
    log("all probes right of Create new failed")


def _infographic_customize_open(hwnd: int) -> bool:
    """True when the Customize Infographic modal appears open."""
    if _named_exists(
        hwnd,
        "Customize Infographic",
        ["TextControl", "PaneControl", "WindowControl", "GroupControl"],
        search_depth=22,
        timeout_s=0.25,
    ):
        return True
    for marker in (
        "Describe the infographic you want to create",
        "Describe the infographic",
        "Choose orientation",
        "Choose visual style",
        "Level of detail",
        "Choose language",
    ):
        if _named_exists(
            hwnd,
            marker,
            ["TextControl", "EditControl", "DocumentControl", "ButtonControl"],
            search_depth=22,
            timeout_s=0.2,
        ):
            return True
    return False


def _wait_infographic_customize_open(
    hwnd: int, *, timeout_s: float = 12.0
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _infographic_customize_open(hwnd):
            return True
        time.sleep(0.35)
    return False


def _find_infographic_describe_edit(hwnd: int):
    for name in (
        "Describe the infographic you want to create",
        "Describe the infographic",
        "infographic you want to create",
    ):
        for ctype in ("EditControl", "DocumentControl", "TextControl"):
            edit = _uia_named(
                hwnd,
                name,
                [ctype],
                search_depth=22,
                timeout_s=0.45,
            )
            if edit:
                return edit
    return _uia_named(
        hwnd,
        "infographic",
        ["EditControl", "DocumentControl"],
        search_depth=22,
        timeout_s=0.35,
    )


def _click_infographic_option(
    hwnd: int,
    *names: str,
    ratio: tuple[float, float] | None = None,
) -> bool:
    types = ["RadioButtonControl", "ButtonControl", "TabItemControl", "HyperlinkControl"]
    for name in names:
        if _click_named(hwnd, name, types, search_depth=22):
            return True
    if ratio:
        log(f"ratio-click infographic option {names[0]!r} at {ratio}")
        _click_ratio(hwnd, ratio[0], ratio[1], pause=0.35)
        return True
    return False


def _open_customize_infographic(hwnd: int) -> None:
    if _infographic_customize_open(hwnd):
        log("Customize Infographic already open")
        return
    if not _click_named(
        hwnd,
        "Infographic",
        ["ButtonControl", "HyperlinkControl"],
        search_depth=18,
    ):
        log("Infographic button not found by name; ratio-click Studio tile")
        _click_ratio(hwnd, 0.78, 0.48, pause=0.6)
        _click_ratio(hwnd, 0.84, 0.50, pause=0.6)
    time.sleep(1.8)
    if _wait_infographic_customize_open(hwnd, timeout_s=5.0):
        return
    ctrl = _uia_named(
        hwnd,
        "Infographic",
        ["ButtonControl", "HyperlinkControl"],
        search_depth=18,
        timeout_s=0.35,
    )
    if ctrl:
        try:
            rect = ctrl.BoundingRectangle
            extra = max(18, int(rect.width() * 0.42))
            log("retry Infographic chevron (right edge)")
            _click_rect_center(rect, extra_x=extra)
            time.sleep(1.8)
        except Exception:
            pass
    if _wait_infographic_customize_open(hwnd, timeout_s=8.0):
        return
    raise RuntimeError(
        "Customize Infographic dialog did not open. "
        "Is Studio visible in the Story Builder notebook?"
    )


def _set_infographic_options(hwnd: int) -> None:
    """Portrait + Concise (UIA first, ratio fallback for Chrome modal)."""
    _click_infographic_option(
        hwnd,
        "Portrait",
        "直向",
        "纵向",
        ratio=(0.47, 0.535),
    )
    time.sleep(0.35)
    _click_infographic_option(
        hwnd,
        "Concise",
        "簡潔",
        "简洁",
        ratio=(0.38, 0.615),
    )
    time.sleep(0.35)


def _paste_infographic_prompt(hwnd: int, prompt: str) -> None:
    import pyautogui

    pyautogui.FAILSAFE = False
    edit = _find_infographic_describe_edit(hwnd)
    if edit:
        try:
            edit.SetFocus()
            time.sleep(0.25)
        except Exception:
            _click_rect_center(edit.BoundingRectangle)
    else:
        log("Describe field not found by UIA; ratio-click modal text area")
        _click_ratio(hwnd, 0.50, 0.73, pause=0.45)
        edit = _find_infographic_describe_edit(hwnd)
        if not edit:
            _click_ratio(hwnd, 0.50, 0.70, pause=0.35)
    write_windows_clipboard(prompt)
    _force_english_ime()
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.12)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.75)
    actual = _uia_value(edit) if edit else ""
    if edit and len(actual) < 20:
        time.sleep(0.5)
        actual = _uia_value(edit)
        if len(actual) < 20:
            log("read-back short; retry paste into describe field")
            _click_ratio(hwnd, 0.50, 0.73, pause=0.35)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.6)
            actual = _uia_value(edit)
    if edit and actual:
        _paste_text_verified(
            prompt, actual, field_label="Describe the infographic"
        )
    else:
        log(
            f"pasted {len(prompt)} chars into Describe the infographic "
            "(no UIA read-back — using clipboard paste)"
        )


def _click_generate(hwnd: int) -> None:
    if not _click_named(
        hwnd, "Generate", ["ButtonControl"], search_depth=22
    ):
        log("Generate button not found by name; ratio-click modal bottom-right")
        _click_ratio(hwnd, 0.58, 0.825, pause=0.55)
    time.sleep(1.2)


def _wait_customize_closed(hwnd: int, timeout_s: float = 18.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _infographic_customize_open(hwnd):
            return True
        time.sleep(0.5)
    return False


def windows_downloads_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or str(Path.home())) / "Downloads"
    return home


def copy_image_file_to_clipboard(image_path: str) -> None:
    """Put an image file on the Windows clipboard as CF_DIB (pasteable bitmap)."""
    from io import BytesIO

    import win32clipboard
    from PIL import Image

    path = Path(image_path)
    if not path.is_file():
        raise RuntimeError(f"image not found: {image_path}")
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, "BMP")
    data = buf.getvalue()[14:]
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()


_GENERATING_INFOGRAPHIC_RE = re.compile(
    r"generating\s+info?r?graphics?",
    re.IGNORECASE,
)
_GENERATING_BASED_ON_RE = re.compile(
    r"based on\s+\d+\s+sources?",
    re.IGNORECASE,
)


def _count_generating_markers_in_text(blob: str) -> int:
    text = blob or ""
    n = len(_GENERATING_INFOGRAPHIC_RE.findall(text))
    if n:
        return n
    n = len(_GENERATING_BASED_ON_RE.findall(text))
    if n:
        return n
    if "正在生成" in text and ("信息图" in text or "infographic" in text.lower()):
        return max(1, text.count("正在生成"))
    return 0


def _looks_like_generating_studio_text(name: str) -> bool:
    """Studio spinner row: 'Generating infographic...' / 'based on 1 source'."""
    return _count_generating_markers_in_text(name or "") > 0


# Hermes D:\Hermes\check_notebooklm_generating.py — inspect Studio right-hand list.
_NOTEBOOKLM_STUDIO_INSPECT_JS = r"""() => {
  const studio = document.querySelector('studio-panel') || document.querySelector('.studio-panel');
  if (!studio) return { error: 'studio_panel_not_found' };

  function hasRotatingSyncIcon(scope) {
    return Array.from(scope.querySelectorAll('*')).some(el => {
      const cls = (el.className && el.className.toString()) || '';
      const t = (el.textContent || '').trim();
      const anim = (getComputedStyle(el).animationName || '').toLowerCase();
      return /artifact-icon/.test(cls) && t === 'sync' && /rotate|spin/.test(anim);
    });
  }

  function hasGenericSpinner(scope) {
    return !!scope.querySelector('mat-progress-spinner, g-progress-spinner, [class*="progress-spinner"], [class*="spinner"]')
        || Array.from(scope.querySelectorAll('svg, circle')).some(el => {
             const anim = (getComputedStyle(el).animationName || '').toLowerCase();
             return /rotate|spin|loop/.test(anim) || (el.tagName === 'CIRCLE' && el.getAttribute('stroke-dasharray'));
           });
  }

  let items = Array.from(studio.querySelectorAll('.artifact-item-button, [class*="artifact-item"], [class*="artifact-card"]'));
  if (items.length === 0) {
    items = Array.from(studio.querySelectorAll('*')).filter(el => {
      const t = (el.textContent || '').trim();
      return el.children.length > 0 && /(source|ago|Generating|正在生成)/i.test(t) && t.length < 300;
    });
  }

  const seen = [];
  const uniq = [];
  for (const it of items) {
    if (seen.indexOf(it) === -1) { seen.push(it); uniq.push(it); }
  }
  items = uniq;

  const generating = [];
  let total = 0;
  for (const it of items) {
    if (it.closest('.create-artifact-buttons-container')) continue;
    const txt = (it.textContent || '').replace(/\s+/g, ' ').trim();
    if (!txt) continue;
    total += 1;

    const titleEl = it.querySelector('.artifact-title')
                || it.querySelector('[class*="artifact-title"]')
                || it.querySelector('.artifact-primary-content')
                || it;
    const title = (titleEl ? titleEl.textContent : txt).replace(/\s+/g, ' ').trim();

    const cls = (it.className && it.className.toString()) || '';
    const shimmer = /shimmer-/.test(cls);
    const rotating = hasRotatingSyncIcon(it);
    const generic = hasGenericSpinner(it);

    let host = it, statusAttrs = {};
    for (let i = 0; i < 4 && host; i++, host = host.parentElement) {
      for (const a of ['aria-busy', 'data-state', 'data-status', 'aria-disabled']) {
        const v = host.getAttribute(a);
        if (v) statusAttrs[a] = v;
      }
    }
    const attrGen = statusAttrs['aria-busy'] === 'true'
                 || /generating|loading/i.test(statusAttrs['data-state'] || '')
                 || /loading/i.test(statusAttrs['data-status'] || '')
                 || statusAttrs['aria-disabled'] === 'true';

    const signals = [];
    if (/^(Generating|正在生成)/i.test(title)) signals.push('title_prefix');
    if (rotating) signals.push('rotating_sync_icon');
    if (shimmer) signals.push('shimmer_class');
    if (generic) signals.push('generic_spinner');
    if (attrGen) signals.push('attr:' + JSON.stringify(statusAttrs));

    if (signals.length > 0) {
      generating.push({ title: title.slice(0, 80), signals: signals });
    }
  }

  return {
    error: null,
    total_items: total,
    is_generating: generating.length > 0,
    generating_items: generating,
    studio_present: true
  };
}"""


def _notebooklm_studio_status_via_cdp(
    *, ensure_cdp: bool = True, attach_only: bool = False
) -> dict:
    """Inspect Studio panel via HermesChromeCDP (D:\\Hermes\\check_notebooklm_generating.py)."""
    port = _hermes_cdp_port_live()
    if port is None and attach_only:
        try:
            port = _resolve_hermes_cdp_attach_port(attach_only=True)
        except RuntimeError as exc:
            return {
                "ok": False,
                "count": 0,
                "generating": False,
                "ready": False,
                "via": "cdp",
                "error": str(exc),
            }
    if port is None:
        if not ensure_cdp:
            p = _grok_cdp_port()
            return {
                "ok": False,
                "count": 0,
                "generating": False,
                "ready": False,
                "via": "cdp",
                "error": f"HermesChromeCDP not listening on {p}",
            }
        try:
            port = ensure_notebooklm_cdp(
                NOTEBOOKLM_URL, timeout_s=25.0, attach_only=attach_only
            )
        except Exception as exc:
            return {
                "ok": False,
                "count": 0,
                "generating": False,
                "ready": False,
                "via": "cdp",
                "error": str(exc),
            }

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            page = _find_notebooklm_cdp_page(browser)
            if page is None:
                return {
                    "ok": False,
                    "count": 0,
                    "generating": False,
                    "ready": False,
                    "via": "cdp",
                    "error": f"no NotebookLM tab on CDP port {port}",
                }
            try:
                page.bring_to_front()
            except Exception:
                pass
            time.sleep(1.2)

            def _inspect() -> dict:
                try:
                    return page.evaluate(_NOTEBOOKLM_STUDIO_INSPECT_JS) or {}
                except Exception as exc:
                    log(f"nbif studio inspect failed: {exc}")
                    return {"error": str(exc)}

            res = _inspect()
            if res.get("error") == "studio_panel_not_found":
                log("nbif: studio panel not found; opening first Recent notebook via CDP")
                if _open_first_existing_notebook_cdp(port):
                    time.sleep(2.0)
                    page = _find_notebooklm_cdp_page(browser) or page
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass
                    time.sleep(1.2)
                    res = _inspect()

            err = str(res.get("error") or "").strip()
            if err:
                return {
                    "ok": False,
                    "count": 0,
                    "generating": False,
                    "ready": False,
                    "via": "cdp",
                    "error": err,
                }

            gen_items = list(res.get("generating_items") or [])
            is_gen = bool(res.get("is_generating"))
            total = int(res.get("total_items") or 0)
            log(
                f"nbif studio via CDP port={port} total={total} "
                f"generating={len(gen_items)} is_generating={is_gen}"
            )
            if gen_items:
                for g in gen_items[:5]:
                    log(f"  generating: {g.get('title')!r} signals={g.get('signals')}")
            return {
                "ok": True,
                "count": len(gen_items),
                "generating": is_gen,
                "ready": not is_gen and bool(res.get("studio_present")),
                "total_items": total,
                "generating_items": gen_items,
                "via": "cdp",
                "error": "",
            }
    except Exception as exc:
        log(f"nbif CDP connect failed: {exc}")
        return {
            "ok": False,
            "count": 0,
            "generating": False,
            "ready": False,
            "via": "cdp",
            "error": str(exc),
        }


def _notebooklm_generating_via_cdp() -> dict:
    """Backward-compatible alias for Studio status probe."""
    return _notebooklm_studio_status_via_cdp(ensure_cdp=True)


def _infographic_still_generating(hwnd: int) -> bool:
    return _count_generating_infographics(hwnd) > 0


def _count_generating_infographics(hwnd: int) -> int:
    """UIA fallback: spinner row names (Chrome often does not expose these)."""
    types = ["TextControl", "CustomControl", "GroupControl", "ListItemControl", "ButtonControl"]
    best = 0
    for name in (
        "Generating infographic",
        "Generating Infographic",
        "based on 1 source",
    ):
        found = _uia_named_all(
            hwnd,
            name,
            types,
            search_depth=22,
            limit=4,
            timeout_s=0.25,
        )
        best = max(best, len(found))
        if best:
            return best
    ctrl = _uia_named(
        hwnd,
        "Generating",
        types,
        search_depth=22,
        timeout_s=0.4,
    )
    if ctrl is not None:
        try:
            label = ctrl.Name or ""
        except Exception:
            label = ""
        if _looks_like_generating_studio_text(label) or "generating" in label.lower():
            return 1
    return best


def _is_studio_artifact_stamp(name: str) -> bool:
    """Finished Studio list row: '1 source · 30m ago' / '2h ago' / '刚刚'."""
    text = (name or "").strip()
    low = text.lower()
    if not text or _looks_like_generating_studio_text(text):
        return False
    if "based on" in low:
        return False
    if re.search(r"\d+\s*sources?", low):
        return True
    if re.search(r"\d+\s*[mh]\s*ago", low):
        return True
    if re.search(r"\d+\s*(min(?:ute)?s?|hours?|hrs?|days?)\s*ago", low):
        return True
    if any(tok in text for tok in ("just now", "Just now", "刚刚", "剛剛", "秒前", "分钟前", "分鐘前")):
        return True
    return False


def _is_recent_studio_stamp(name: str) -> bool:
    """Alias: any finished Studio artifact row (top-N is chosen by y-order)."""
    return _is_studio_artifact_stamp(name)


def _dedupe_row_boxes(
    boxes: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    ordered = sorted(dict.fromkeys(boxes), key=lambda b: (b[1], b[0]))
    out: list[tuple[int, int, int, int]] = []
    for box in ordered:
        mid = (box[1] + box[3]) // 2
        if out and abs(((out[-1][1] + out[-1][3]) // 2) - mid) < 28:
            continue
        out.append(box)
    return out


def _studio_recent_row_boxes(hwnd: int) -> list[tuple[int, int, int, int]]:
    """Top-to-bottom rects of Studio history *buttons* (title + 1 source · …)."""
    win_left, _win_top, width, _height = _chrome_window_rect(hwnd)
    min_x = win_left + int(width * 0.52)
    boxes: list[tuple[int, int, int, int]] = []
    needles = (
        "source ·",
        "source •",
        "sources ·",
        "sources •",
        "1 source",
    )
    for needle in needles:
        for ctrl in _uia_named_all(
            hwnd,
            needle,
            ["ButtonControl", "ListItemControl", "HyperlinkControl"],
            search_depth=22,
            limit=8,
        ):
            try:
                name = ctrl.Name or ""
            except Exception:
                name = ""
            if _looks_like_generating_studio_text(name):
                continue
            if "source" not in name.lower():
                continue
            box = _ctrl_box(ctrl)
            if not box:
                continue
            left, top, right, bottom = box
            if left < min_x:
                continue
            if (bottom - top) > 240 or (right - left) > int(width * 0.48):
                continue
            if (bottom - top) < 24:
                continue
            boxes.append(box)
    return _dedupe_row_boxes(boxes)


def _studio_infographic_rows_ready(hwnd: int, expected: int) -> int:
    """Count recently finished Studio infographic rows."""
    return len(_studio_recent_row_boxes(hwnd))


def _wait_infographics_ready(
    hwnd: int,
    expected: int = NOTEBOOKLM_COVER_TIMES,
    timeout_s: float = NOTEBOOKLM_READY_TIMEOUT_S,
) -> None:
    want = max(1, int(expected or NOTEBOOKLM_COVER_TIMES))
    started = time.monotonic()
    idle_s = 0.0
    log(f"waiting for {want} infographics in Studio (up to {int(timeout_s)}s)…")
    while time.monotonic() - started < timeout_s:
        elapsed = time.monotonic() - started
        generating = _infographic_still_generating(hwnd)
        rows = _studio_infographic_rows_ready(hwnd, want)
        if generating:
            idle_s = 0.0
        else:
            idle_s += 8.0
        log(
            f"infographic wait {elapsed:.0f}s generating={generating} "
            f"studio_rows={rows}/{want} idle={idle_s:.0f}s"
        )
        counted = (
            elapsed >= NOTEBOOKLM_READY_MIN_S
            and not generating
            and rows >= want
        )
        # Spinners gone for a while: generation finished even if UIA count is off.
        settled = (
            not generating
            and idle_s >= 90.0
            and elapsed >= max(120.0, want * 35.0)
        )
        if counted or settled:
            time.sleep(3.0)
            if _infographic_still_generating(hwnd):
                idle_s = 0.0
                continue
            log(
                "infographics look ready in Studio "
                f"(rows={_studio_infographic_rows_ready(hwnd, want)}, settled={settled})"
            )
            return
        time.sleep(8.0)
    raise RuntimeError(
        f"等了 {int(timeout_s // 60)} 分钟，Studio 里仍不足 {want} 张 infographic。"
        "请在页面上看是否卡住，或换 profile 再试。"
    )


def _infographic_preview_open(hwnd: int) -> bool:
    for marker in (
        "View prompt",
        "Good content",
        "Bad content",
        "Zoom in",
        "Zoom out",
        "Download",
        "下载",
        "下載",
    ):
        if _named_exists(
            hwnd,
            marker,
            ["ButtonControl", "TextControl", "HyperlinkControl", "MenuItemControl"],
            search_depth=22,
            timeout_s=0.2,
        ):
            return True
    return False


def _click_infographic_preview_more_menu(hwnd: int) -> bool:
    for name in (
        "More",
        "More options",
        "More actions",
        "More menu",
        "更多",
        "更多选项",
        "更多選項",
    ):
        if _click_named(
            hwnd, name, ["ButtonControl", "MenuItemControl"], search_depth=22
        ):
            time.sleep(0.45)
            return True
    log("ratio-click infographic preview ⋮ menu (top-right of modal)")
    for x_r, y_r in ((0.80, 0.10), (0.77, 0.11), (0.83, 0.09), (0.80, 0.12)):
        _click_ratio(hwnd, x_r, y_r, pause=0.4)
        if _named_exists(
            hwnd,
            "Download",
            ["MenuItemControl", "ButtonControl", "TextControl"],
            search_depth=12,
            timeout_s=0.2,
        ):
            return True
    return True


def _click_infographic_download_menu_item(hwnd: int) -> bool:
    for name in ("Download", "下载", "下載", "Save image", "保存图片"):
        if _click_named(
            hwnd,
            name,
            ["MenuItemControl", "ButtonControl", "TextControl", "HyperlinkControl"],
            search_depth=12,
        ):
            time.sleep(0.8)
            return True
    log("ratio-click Download in ⋮ menu")
    for x_r, y_r in ((0.80, 0.14), (0.80, 0.16), (0.77, 0.15), (0.718, 0.205)):
        _click_ratio(hwnd, x_r, y_r, pause=0.85)
        if _named_exists(
            hwnd,
            "Export Image",
            ["ButtonControl", "MenuItemControl", "TextControl"],
            search_depth=14,
            timeout_s=0.25,
        ) or _named_exists(
            hwnd,
            "JPG",
            ["ButtonControl", "MenuItemControl", "TextControl"],
            search_depth=14,
            timeout_s=0.25,
        ):
            return True
    return True


def _close_infographic_preview(hwnd: int) -> None:
    """Dismiss the infographic overlay with Escape. Never click Close (that can quit Chrome)."""
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.press("escape")
    time.sleep(0.4)


def _wait_new_browser_download(
    since_ts: float,
    *,
    timeout_s: float = 35.0,
) -> Path | None:
    downloads = windows_downloads_dir()
    exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        candidates: list[Path] = []
        try:
            for path in downloads.iterdir():
                if not path.is_file():
                    continue
                if path.suffix.lower() not in exts:
                    continue
                if path.name.endswith(".crdownload") or path.name.endswith(".tmp"):
                    continue
                try:
                    if path.stat().st_mtime >= since_ts - 2.0 and path.stat().st_size > 2000:
                        candidates.append(path)
                except OSError:
                    continue
        except OSError:
            pass
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)
        time.sleep(0.6)
    return None


def _save_download_as_jpg(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if src.suffix.lower() in (".jpg", ".jpeg"):
            shutil.copy2(src, dest)
        else:
            from PIL import Image

            img = Image.open(src)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(dest, "JPEG", quality=93)
        return dest.is_file() and dest.stat().st_size > 2000
    except Exception as exc:
        log(f"save download as jpg failed: {exc}")
        return False


def _save_download_as_png(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if src.suffix.lower() == ".png":
            shutil.copy2(src, dest)
        else:
            from PIL import Image

            img = Image.open(src)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.save(dest, "PNG")
        return dest.is_file() and dest.stat().st_size > 2000
    except Exception as exc:
        log(f"save download as png failed: {exc}")
        return False


def _physical_click_viewport(page, hwnd: int, vx: float, vy: float, *, pause: float = 0.45) -> None:
    """Move the real mouse and click a page viewport point (visible to the user)."""
    from cli.win_gui_tasks import set_foreground

    set_foreground(hwnd)
    time.sleep(0.12)
    sx, sy = _viewport_point_to_screen(hwnd, page, vx, vy)
    log(f"physical click viewport=({vx:.0f},{vy:.0f}) screen=({sx},{sy})")
    _click_xy(sx, sy, pause=pause)


def _physical_click_export_dialog_button(page, hwnd: int, names: tuple[str, ...]) -> bool:
    if page is None:
        return False
    try:
        info = page.evaluate(_EXPORT_DIALOG_BUTTON_JS, list(names))
    except Exception as exc:
        log(f"export dialog button lookup failed: {exc}")
        return False
    if not isinstance(info, dict) or not info.get("x"):
        return False
    _physical_click_viewport(
        page, hwnd, float(info["x"]), float(info["y"]), pause=0.55
    )
    log(f"physical export dialog click {info.get('text')!r}")
    return True


def _confirm_infographic_export_dialog(page, hwnd: int) -> bool:
    """If NotebookLM opens JPG/Export Image after Download, confirm it."""
    jpg_done = False
    exported = False
    deadline = time.monotonic() + 28.0
    while time.monotonic() < deadline:
        if page is not None and not jpg_done:
            for name in ("JPG", "PNG"):
                try:
                    btn = page.get_by_role("button", name=name)
                    if int(btn.count() or 0) > 0 and btn.first.is_visible():
                        btn.first.click(timeout=2500)
                        log(f"CDP export dialog: chose {name}")
                        jpg_done = True
                        time.sleep(0.45)
                        break
                except Exception:
                    pass
        if page is not None:
            for name in ("Export Image", "Export", "Download"):
                try:
                    btn = page.get_by_role("button", name=name)
                    if int(btn.count() or 0) > 0 and btn.first.is_visible():
                        btn.first.click(timeout=4000)
                        log(f"CDP export dialog: clicked {name!r}")
                        exported = True
                        time.sleep(0.5)
                        break
                except Exception:
                    pass
        if exported:
            return True
        if not jpg_done:
            for name in ("JPG", "PNG"):
                if _physical_click_export_dialog_button(page, hwnd, (name,)):
                    jpg_done = True
                    time.sleep(0.45)
                    break
                if _click_named(
                    hwnd,
                    name,
                    ["ButtonControl", "MenuItemControl", "HyperlinkControl"],
                    search_depth=16,
                ):
                    log(f"UIA export dialog: chose {name!r}")
                    jpg_done = True
                    time.sleep(0.45)
                    break
        for name in ("Export Image", "Export", "Download"):
            if _physical_click_export_dialog_button(page, hwnd, (name,)):
                exported = True
                time.sleep(0.55)
                return True
            if _click_named(
                hwnd,
                name,
                ["ButtonControl", "MenuItemControl", "HyperlinkControl"],
                search_depth=16,
            ):
                log(f"UIA export dialog: clicked {name!r}")
                exported = True
                time.sleep(0.55)
                return True
        time.sleep(0.45)
    return exported


def _physical_download_via_preview_menu(page, hwnd: int, dest: Path) -> bool:
    """Visible mouse: preview ⋮ → Download → Export Image → save PNG."""
    from cli.win_gui_tasks import set_foreground

    if page is None:
        return False
    set_foreground(hwnd)
    time.sleep(0.25)
    since = time.time()
    try:
        info = page.evaluate(_PREVIEW_MORE_BUTTON_JS)
    except Exception as exc:
        log(f"physical ⋮ lookup failed: {exc}")
        return False
    if not isinstance(info, dict) or not info.get("x"):
        log("physical ⋮ button not found")
        return False
    _physical_click_viewport(
        page, hwnd, float(info["x"]), float(info["y"]), pause=0.6
    )
    dl_info = None
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        try:
            items = page.evaluate(_PREVIEW_MENU_ITEMS_JS) or []
        except Exception:
            items = []
        if items:
            texts = [str(i.get("text") or "") for i in items]
            log(f"preview ⋮ menu items: {texts}")
            for item in items:
                text = str(item.get("text") or "").strip()
                if re.match(r"^(download|下载|下載|export|save image|导出)", text, re.I):
                    dl_info = item
                    break
            if dl_info:
                break
        try:
            dl_info = page.evaluate(_PREVIEW_DOWNLOAD_MENU_JS)
        except Exception:
            dl_info = None
        if isinstance(dl_info, dict) and dl_info.get("x"):
            break
        time.sleep(0.35)
    if not isinstance(dl_info, dict) or not dl_info.get("x"):
        log("physical Download menu item not found after ⋮ click")
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            pyautogui.press("escape")
        except Exception:
            pass
        return False
    _physical_click_viewport(
        page,
        hwnd,
        float(dl_info["x"]),
        float(dl_info["y"]),
        pause=0.85,
    )
    log(f"physical clicked menu item {dl_info.get('text')!r}")
    time.sleep(0.5)
    _confirm_infographic_export_dialog(page, hwnd)
    downloaded = _wait_new_browser_download(since, timeout_s=50.0)
    if downloaded and _save_download_as_png(downloaded, dest):
        log(f"physical ⋮ Download saved → {dest}")
        return True
    log("physical ⋮ Download clicked but no file in Downloads")
    return False


def working_media_dir() -> Path:
    """Folder for itc PNG captures. Always prefer ``D:\\AI_MEDIA\\working``."""
    preferred = Path(r"D:\AI_MEDIA\working")
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        if preferred.is_dir():
            return preferred
    except OSError as exc:
        log(f"D:\\AI_MEDIA\\working not usable: {exc}")
    raw = str(getattr(config, "WORKING_MEDIA_PATH", "") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    candidates.append(Path(str(getattr(config, "BASE_MEDIA_PATH", "") or "")) / "working")
    for p in candidates:
        try:
            if not str(p).strip() or str(p) in ("working", "\\working"):
                continue
            p.mkdir(parents=True, exist_ok=True)
            if p.is_dir():
                return p
        except OSError:
            continue
    preferred.mkdir(parents=True, exist_ok=True)
    return preferred


def _next_working_png() -> Path:
    folder = working_media_dir()
    for _ in range(8):
        stamp = time.strftime("%Y%m%d%H%M%S")
        dest = folder / f"{stamp}.png"
        if not dest.exists():
            return dest
        time.sleep(1.05)
    return folder / f"{time.strftime('%Y%m%d%H%M%S')}_{os.getpid()}.png"


def _save_clipboard_image_png(dest: Path) -> bool:
    try:
        from PIL import Image, ImageGrab
    except Exception as exc:
        log(f"Pillow ImageGrab missing: {exc}")
        return False
    clip = ImageGrab.grabclipboard()
    if clip is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if isinstance(clip, list):
            src = next((str(p) for p in clip if p and Path(p).is_file()), "")
            if not src:
                return False
            img = Image.open(src)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.save(dest, "PNG")
        else:
            mode = getattr(clip, "mode", "") or ""
            if mode not in ("RGB", "RGBA"):
                clip = clip.convert("RGBA")
            clip.save(dest, "PNG")
    except Exception as exc:
        log(f"save clipboard png failed: {exc}")
        return False
    return dest.is_file() and dest.stat().st_size > 2000


def _save_clipboard_image(dest: Path) -> bool:
    try:
        from PIL import ImageGrab
    except Exception as exc:
        log(f"Pillow ImageGrab missing: {exc}")
        return False
    clip = ImageGrab.grabclipboard()
    if clip is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(clip, list):
        src = next((str(p) for p in clip if p and Path(p).is_file()), "")
        if not src:
            return False
        from shutil import copy2

        copy2(src, dest)
        return dest.is_file()
    try:
        clip.convert("RGB").save(dest, "JPEG", quality=93)
    except Exception as exc:
        log(f"save clipboard image failed: {exc}")
        return False
    return dest.is_file() and dest.stat().st_size > 2000


# CDK aria-describedby tooltips on Studio artifact cards. Skip chrome UI.
_STUDIO_TOOLTIP_SKIP_RE = re.compile(
    r"^(share|analytics|export|new note|jump to bottom|close|more|download|"
    r"view prompt|zoom in|zoom out|good content|bad content)$"
    r"|^(generate |drive files|chat history|make a copy|based on your)",
    re.I,
)

_STUDIO_ARTIFACT_TITLES_JS = """() => {
    const skipExact = new Set([
        'share','analytics','export','new note','close','more','download',
        'jump to bottom','view prompt','zoom in','zoom out',
        'good content','bad content','copy','edit'
    ]);
    const skipRe = /^(generate |drive files|chat history|make a copy|based on your)/i;
    const titles = [];
    const seen = new Set();
    for (const tip of document.querySelectorAll('[role="tooltip"]')) {
        const t = (tip.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!t || t.length < 2 || t.length > 90) continue;
        if (skipExact.has(t.toLowerCase()) || skipRe.test(t)) continue;
        if (seen.has(t)) continue;
        seen.add(t);
        titles.push({id: tip.id || '', title: t});
    }
    return titles;
}"""

_STUDIO_CARD_FOR_TITLE_JS = """(title) => {
    const vw = window.innerWidth, vh = window.innerHeight;
    const want = (title || '').trim();
    if (!want) return null;
    const hits = [];
    const add = (el, how) => {
        if (!el) return;
        const r = el.getBoundingClientRect();
        if (r.width < 36 || r.height < 18) return;
        if (r.bottom < 70 || r.top > vh - 4) return;
        hits.push({
            how, text: want,
            x: r.left, y: r.top, w: r.width, h: r.height,
            cx: r.left + Math.min(90, Math.max(28, r.width * 0.30)),
            cy: r.top + r.height * 0.42,
        });
    };
    const collect = (root) => {
        if (!root || !root.querySelectorAll) return;
        for (const el of root.querySelectorAll('button, [role="button"]')) {
            const label = (
                el.getAttribute('aria-label') ||
                el.getAttribute('mattooltip') ||
                el.innerText ||
                el.textContent ||
                ''
            ).replace(/\\s+/g, ' ').trim();
            if (label.includes(want)) add(el, 'button');
        }
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) collect(el.shadowRoot);
        }
    };
    collect(document.documentElement);
    if (!hits.length) return null;
    hits.sort((a, b) => (b.x - a.x) || (a.y - b.y) || (a.w * a.h - b.w * b.h));
    const right = hits.filter(h => h.x >= vw * 0.48);
    const best = (right.length ? right : hits)[0];
    if (best.w > vw * 0.50) {
        best.cx = best.x + Math.min(80, best.w * 0.18);
        best.cy = best.y + Math.min(48, best.h * 0.35);
    }
    return best;
}"""


_PREVIEW_IMG_JS = """() => {
    const consider = (el, extra) => {
        const r = el.getBoundingClientRect();
        if (r.width < 180 || r.height < 180) return;
        const area = r.width * r.height;
        if (!best || area > best.area) {
            best = {
                src: extra.src || '',
                tag: extra.tag || (el.tagName || ''),
                x: r.x, y: r.y, w: r.width, h: r.height, area,
                nw: extra.nw || 0, nh: extra.nh || 0,
            };
        }
    };
    let best = null;
    const visit = (root) => {
        if (!root || !root.querySelectorAll) return;
        for (const img of root.querySelectorAll('img')) {
            const nw = img.naturalWidth || 0;
            if (nw > 0 && nw < 40) continue;
            consider(img, {
                tag: 'IMG',
                src: img.currentSrc || img.src || '',
                nw, nh: img.naturalHeight || 0,
            });
        }
        for (const canvas of root.querySelectorAll('canvas')) {
            consider(canvas, {
                tag: 'CANVAS', src: '',
                nw: canvas.width || 0, nh: canvas.height || 0,
            });
        }
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) visit(el.shadowRoot);
        }
    };
    visit(document.documentElement);
    return best;
}"""

_PREVIEW_IMAGE_LOADED_JS = """() => {
    const spinners = document.querySelectorAll(
        'mat-spinner, mat-progress-spinner, [role="progressbar"], .loading, .spinner'
    );
    for (const sp of spinners) {
        const r = sp.getBoundingClientRect();
        if (r.width >= 16 && r.height >= 16 && r.top > 70 && r.bottom < window.innerHeight - 8) {
            return { ready: false, reason: 'spinner' };
        }
    }
    let best = null;
    const consider = (el, tag, nw, nh, src) => {
        const r = el.getBoundingClientRect();
        if (r.width < 220 || r.height < 220) return;
        if (tag === 'IMG') {
            if (!el.complete) return;
            if (nw > 0 && nw < 120) return;
            if (nh > 0 && nh < 120) return;
        } else if (tag === 'CANVAS') {
            if (nw < 200 || nh < 200) return;
        }
        const area = r.width * r.height;
        if (!best || area > best.area) {
            best = {
                ready: true,
                reason: 'loaded',
                tag, nw, nh,
                x: r.x, y: r.y, w: r.width, h: r.height, area,
                src: src || '',
            };
        }
    };
    const visit = (root) => {
        if (!root || !root.querySelectorAll) return;
        for (const img of root.querySelectorAll('img')) {
            consider(img, 'IMG', img.naturalWidth || 0, img.naturalHeight || 0,
                     img.currentSrc || img.src || '');
        }
        for (const c of root.querySelectorAll('canvas')) {
            consider(c, 'CANVAS', c.width || 0, c.height || 0, '');
        }
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) visit(el.shadowRoot);
        }
    };
    visit(document.documentElement);
    return best || { ready: false, reason: 'no-image' };
}"""

_CANVAS_PNG_JS = """() => {
    const found = [];
    const visit = (root) => {
        if (!root || !root.querySelectorAll) return;
        for (const c of root.querySelectorAll('canvas')) {
            const r = c.getBoundingClientRect();
            if (r.width < 180 || r.height < 180) continue;
            found.push(c);
        }
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) visit(el.shadowRoot);
        }
    };
    visit(document.documentElement);
    if (!found.length) return '';
    found.sort((a, b) => (b.width * b.height) - (a.width * a.height));
    try { return found[0].toDataURL('image/png'); } catch (e) { return ''; }
}"""

_PREVIEW_MORE_BUTTON_JS = """() => {
    const bigEnough = (el) => {
        const r = el.getBoundingClientRect();
        return r.width > 480 && r.height > 360;
    };
    const hasMarker = (node) => {
        const t = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ');
        return /View prompt|Good content|Zoom in|Zoom out|Bad content/i.test(t);
    };
    const findRoot = () => {
        for (const pane of document.querySelectorAll('.cdk-overlay-pane')) {
            if (!bigEnough(pane)) continue;
            if (hasMarker(pane)) return pane;
        }
        for (const marker of ['View prompt', 'Good content', 'Zoom in', 'Bad content']) {
            for (const el of document.querySelectorAll('button, span, div, a, p, h1, h2')) {
                const t = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                if (!t.includes(marker)) continue;
                let p = el;
                for (let i = 0; i < 22 && p; i++) {
                    if (bigEnough(p) && hasMarker(p)) return p;
                    p = p.parentElement;
                }
            }
        }
        const panes = [...document.querySelectorAll('.cdk-overlay-pane')].filter(bigEnough);
        if (panes.length) {
            panes.sort((a, b) => {
                const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
                return (rb.width * rb.height) - (ra.width * ra.height);
            });
            return panes[0];
        }
        return null;
    };
    const root = findRoot();
    if (!root) return null;
    const vw = window.innerWidth;
    const btns = [];
    for (const b of root.querySelectorAll(
        'button.artifact-more-button, button[aria-label="More"], button.mat-mdc-menu-trigger'
    )) {
        const r = b.getBoundingClientRect();
        if (r.width < 16 || r.height < 16) continue;
        if (r.left < vw * 0.30) continue;
        btns.push({ x: r.left + r.width / 2, y: r.top + r.height / 2, right: r.right, top: r.top });
    }
    if (!btns.length) {
        for (const b of document.querySelectorAll('button.artifact-more-button, button[aria-label="More"]')) {
            const r = b.getBoundingClientRect();
            if (r.width < 16 || r.height < 16) continue;
            if (r.top > window.innerHeight * 0.30) continue;
            if (r.left < vw * 0.35) continue;
            let p = b.parentElement;
            let inPreview = false;
            for (let i = 0; i < 24 && p; i++) {
                if (bigEnough(p) && hasMarker(p)) { inPreview = true; break; }
                p = p.parentElement;
            }
            if (!inPreview) continue;
            btns.push({ x: r.left + r.width / 2, y: r.top + r.height / 2, right: r.right, top: r.top });
        }
    }
    if (!btns.length) return null;
    btns.sort((a, b) => (b.right - a.right) || (a.top - b.top));
    const best = btns[0];
    return { x: best.x, y: best.y, mode: document.querySelectorAll('.cdk-overlay-pane').length ? 'overlay' : 'inline' };
}"""

_PREVIEW_DOWNLOAD_MENU_JS = """() => {
    const panels = [...document.querySelectorAll(
        '.cdk-overlay-container .mat-mdc-menu-panel, .mat-mdc-menu-panel'
    )];
    const panel = panels.filter(p => {
        const r = p.getBoundingClientRect();
        return r.width > 40 && r.height > 20;
    }).pop();
    if (!panel) return null;
    for (const item of panel.querySelectorAll('.mat-mdc-menu-item, [role="menuitem"]')) {
        const t = (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!/^(download|下载|下載|save image|export)$/i.test(t)) continue;
        const r = item.getBoundingClientRect();
        if (r.width < 20 || r.height < 10) continue;
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, text: t };
    }
    return null;
}"""

_PREVIEW_MENU_ITEMS_JS = """() => {
    const panels = [...document.querySelectorAll(
        '.cdk-overlay-container .mat-mdc-menu-panel, .mat-mdc-menu-panel'
    )];
    const panel = panels.filter(p => {
        const r = p.getBoundingClientRect();
        return r.width > 40 && r.height > 20;
    }).pop();
    if (!panel) return [];
    return [...panel.querySelectorAll('.mat-mdc-menu-item, [role="menuitem"]')].map(item => {
        const t = (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').trim();
        const r = item.getBoundingClientRect();
        return {
            text: t,
            x: r.left + r.width / 2,
            y: r.top + r.height / 2,
            w: r.width,
            h: r.height,
        };
    }).filter(i => i.w > 10 && i.h > 8);
}"""

_EXPORT_DIALOG_BUTTON_JS = """(names) => {
    const want = (names || []).map(n => String(n).toLowerCase());
    for (const btn of document.querySelectorAll('button,[role="button"]')) {
        const t = (btn.innerText || btn.textContent || btn.getAttribute('aria-label') || '')
            .replace(/\\s+/g, ' ').trim();
        if (!t) continue;
        if (!want.includes(t.toLowerCase())) continue;
        const r = btn.getBoundingClientRect();
        if (r.width < 20 || r.height < 12) continue;
        return { text: t, x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }
    return null;
}"""


def _list_studio_history_rows(page) -> list[dict]:
    """Studio artifact cards by CDK tooltip title (e.g. 內心的破曉), not Chat timestamps."""
    titles: list[str] = []
    try:
        raw = page.evaluate(_STUDIO_ARTIFACT_TITLES_JS) or []
    except Exception as exc:
        log(f"CDP tooltip titles failed: {exc}")
        raw = []
    for item in raw:
        if isinstance(item, dict):
            t = str(item.get("title") or "").strip()
        else:
            t = str(item or "").strip()
        if not t or _STUDIO_TOOLTIP_SKIP_RE.search(t):
            continue
        if t not in titles:
            titles.append(t)
    rows: list[dict] = [{"text": t} for t in titles]
    if not rows:
        try:
            loc = page.get_by_role("button").filter(
                has_text=re.compile(r"\d+\s+sources?\s*[·•]", re.I)
            )
            n = min(int(loc.count() or 0), 12)
            vw = float(page.evaluate("() => window.innerWidth") or 1920)
            seen: list[str] = []
            for i in range(n):
                box = loc.nth(i).bounding_box()
                if not box or box["x"] < vw * 0.48:
                    continue
                name = (loc.nth(i).inner_text() or "").replace("\n", " ").strip()
                if name in seen:
                    continue
                seen.append(name)
                rows.append({"text": name, "x": box["x"], "y": box["y"]})
        except Exception as exc:
            log(f"CDP button fallback list failed: {exc}")
    preview = "; ".join(
        f"{i + 1}:{(r.get('text') or '')[:40]!r}" for i, r in enumerate(rows[:8])
    )
    log(f"Studio history rows={len(rows)} [{preview}]")
    return rows


def _pick_rightmost_locator(page, loc):
    """Studio is the right column; Chat in the middle also may contain the title."""
    try:
        n = int(loc.count() or 0)
    except Exception:
        return None
    if n <= 0:
        return None
    vw = 1920.0
    try:
        vw = float(page.evaluate("() => window.innerWidth") or vw)
    except Exception:
        pass
    best = None
    best_x = -1.0
    for i in range(min(n, 12)):
        try:
            box = loc.nth(i).bounding_box()
        except Exception:
            box = None
        if not box:
            continue
        if box["x"] < vw * 0.45:
            continue
        if box["x"] >= best_x:
            best_x = box["x"]
            best = loc.nth(i)
    return best


def _click_studio_title_via_playwright(page, title: str) -> bool:
    """Click the Studio history *button* whose accessible name includes *title*."""
    title = (title or "").strip()
    if not title:
        return False
    locators = []
    try:
        locators.append(page.get_by_role("button", name=title))
    except Exception:
        pass
    try:
        locators.append(
            page.get_by_role("button").filter(has_text=title)
        )
    except Exception:
        pass
    try:
        locators.append(page.get_by_text(title, exact=True))
    except Exception:
        pass
    for loc in locators:
        target = _pick_rightmost_locator(page, loc)
        if target is None:
            continue
        try:
            box = target.bounding_box()
            log(
                f"CDP click Studio button {title!r} "
                f"box=({box['x']:.0f},{box['y']:.0f},{box['width']:.0f}x{box['height']:.0f})"
                if box else f"CDP click Studio button {title!r}"
            )
            target.click(timeout=7000)
            return True
        except Exception as exc:
            log(f"CDP locator click failed for {title!r}: {exc}")
    try:
        geom = page.evaluate(_STUDIO_CARD_FOR_TITLE_JS, title)
    except Exception as exc:
        log(f"CDP card geom failed for {title!r}: {exc}")
        geom = None
    if isinstance(geom, dict) and geom.get("cx") is not None:
        cx = float(geom["cx"])
        cy = float(geom["cy"])
        log(
            f"CDP mouse click Studio card {title!r} at ({cx:.0f},{cy:.0f}) "
            f"box=({geom.get('x'):.0f},{geom.get('y'):.0f},"
            f"{geom.get('w'):.0f}x{geom.get('h'):.0f})"
        )
        try:
            page.mouse.click(cx, cy)
            return True
        except Exception as exc:
            log(f"CDP mouse click failed for {title!r}: {exc}")
    return False


def _infographic_image_loaded(page) -> dict:
    """True when the popup infographic pixels are ready (not just the shell)."""
    if page is None:
        return {"ready": False, "reason": "no-page"}
    try:
        info = page.evaluate(_PREVIEW_IMAGE_LOADED_JS)
    except Exception as exc:
        log(f"CDP/DOM image-loaded probe failed: {exc}")
        return {"ready": False, "reason": "probe-failed"}
    return info if isinstance(info, dict) else {"ready": False, "reason": "bad-probe"}


def _largest_preview_img_info(page) -> dict | None:
    try:
        info = page.evaluate(_PREVIEW_IMG_JS)
    except Exception as exc:
        log(f"CDP/DOM preview img probe failed: {exc}")
        return None
    return info if isinstance(info, dict) and info.get("w") else None


def _preview_markers_open(page) -> bool:
    if page is None:
        return False
    try:
        for marker in ("View prompt", "Zoom in", "Good content"):
            if page.get_by_text(marker, exact=False).count() > 0:
                return True
    except Exception:
        pass
    return _largest_preview_img_info(page) is not None


def _wait_infographic_preview_ready(
    hwnd: int,
    page=None,
    *,
    timeout_s: float = INFOGRAPHIC_PREVIEW_LOAD_TIMEOUT_S,
) -> bool:
    """Wait for popup, then wait until the infographic image has finished loading."""
    deadline = time.monotonic() + timeout_s
    popup_open_deadline = time.monotonic() + min(
        INFOGRAPHIC_POPUP_OPEN_TIMEOUT_S, timeout_s * 0.4
    )
    popup_seen = False
    last_reason = ""
    log(f"waiting for infographic image to load (up to {int(timeout_s)}s)…")
    while time.monotonic() < deadline:
        loaded = _infographic_image_loaded(page) if page is not None else {"ready": False}
        if loaded.get("ready"):
            log(
                f"infographic image ready {loaded.get('tag')!r} "
                f"natural={loaded.get('nw')}x{loaded.get('nh')} "
                f"box={loaded.get('w'):.0f}x{loaded.get('h'):.0f}"
            )
            time.sleep(0.6)
            return True
        last_reason = str(loaded.get("reason") or "")
        if page is not None and _preview_markers_open(page):
            popup_seen = True
        elif _infographic_preview_open(hwnd):
            popup_seen = True
        if not popup_seen and time.monotonic() > popup_open_deadline:
            log("infographic popup never opened")
            return False
        if popup_seen and last_reason in ("spinner", "no-image"):
            elapsed = timeout_s - (deadline - time.monotonic())
            if int(elapsed) % 4 == 0:
                log(f"popup open, image still loading ({last_reason})…")
        time.sleep(0.55)
    log(f"infographic image not loaded within {int(timeout_s)}s (last={last_reason})")
    return False


def _write_image_png(data: bytes, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.save(dest, "PNG")
    except Exception:
        try:
            dest.write_bytes(data)
        except Exception as exc:
            log(f"write png failed: {exc}")
            return False
    return dest.is_file() and dest.stat().st_size > 2000


def _save_png_from_src(page, src: str, dest: Path) -> bool:
    if not src:
        return False
    if src.startswith("data:"):
        try:
            _, b64 = src.split(",", 1)
            return _write_image_png(base64.b64decode(b64), dest)
        except Exception as exc:
            log(f"data-url png failed: {exc}")
            return False
    try:
        resp = page.request.get(src, timeout=20000)
        if resp.ok:
            data = resp.body()
            if data and len(data) > 2000:
                return _write_image_png(data, dest)
    except Exception as exc:
        log(f"page.request get image failed: {exc}")
    try:
        b64 = page.evaluate(
            """async (src) => {
                const r = await fetch(src, {credentials: 'include'});
                const buf = await r.arrayBuffer();
                const bytes = new Uint8Array(buf);
                let s = '';
                const chunk = 0x8000;
                for (let i = 0; i < bytes.length; i += chunk) {
                    s += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
                }
                return btoa(s);
            }""",
            src,
        )
        data = base64.b64decode(b64)
        if data and len(data) > 2000:
            return _write_image_png(data, dest)
    except Exception as exc:
        log(f"page.evaluate fetch image failed: {exc}")
    return False


def _open_studio_infographic_via_dom(page, index: int):
    """Click Studio history item *index* by title. Returns (preview_page, extra_tab, clicked, title)."""
    try:
        page.keyboard.press("Escape")
        time.sleep(0.25)
    except Exception:
        pass
    rows = _list_studio_history_rows(page)
    if not (1 <= index <= len(rows)):
        log(f"CDP/DOM: no Studio history row {index} (have {len(rows)})")
        return None, False, False, ""
    title = str(rows[index - 1].get("text") or "").strip()
    ctx = page.context
    before = list(ctx.pages)
    log(f"CDP open Studio history #{index} title={title!r}")
    if not _click_studio_title_via_playwright(page, title):
        log(f"CDP/DOM: could not click Studio title {title!r}")
        return None, False, False, title
    time.sleep(0.8)
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        after = list(ctx.pages)
        if len(after) > len(before):
            newp = [p for p in after if p not in before]
            if newp:
                p = newp[-1]
                try:
                    p.bring_to_front()
                except Exception:
                    pass
                log("CDP/DOM: infographic opened in a new tab")
                return p, True, True, title
        time.sleep(0.2)
    return page, False, True, title


def _dismiss_infographic_popup(
    hwnd: int,
    *,
    notebook_page=None,
    preview_page=None,
    extra_tab: bool = False,
) -> None:
    """Close the infographic overlay/tab only. Never quit Chrome or the notebook tab."""
    if (
        extra_tab
        and preview_page is not None
        and notebook_page is not None
        and preview_page is not notebook_page
    ):
        try:
            others = [p for p in preview_page.context.pages if p is not preview_page]
        except Exception:
            others = []
        notebook_alive = False
        for p in others:
            try:
                url = (p.url or "").lower()
            except Exception:
                url = ""
            if "notebook.google.com" in url or "notebooklm" in url:
                notebook_alive = True
                break
        if notebook_alive:
            log("closing infographic extra tab; notebook tab stays open")
            try:
                preview_page.close()
                time.sleep(0.45)
                return
            except Exception as exc:
                log(f"extra-tab close failed: {exc}")
        else:
            log("skip extra-tab close (would close the only NotebookLM tab)")
    target = preview_page if extra_tab else (notebook_page or preview_page)
    for _ in range(3):
        try:
            if target is not None:
                target.keyboard.press("Escape")
            else:
                import pyautogui

                pyautogui.FAILSAFE = False
                pyautogui.press("escape")
        except Exception:
            try:
                import pyautogui

                pyautogui.FAILSAFE = False
                pyautogui.press("escape")
            except Exception:
                pass
        time.sleep(0.5)
        still = False
        try:
            if _preview_markers_open(notebook_page or preview_page):
                still = True
            elif _infographic_preview_open(hwnd):
                still = True
        except Exception:
            still = False
        if not still:
            log("infographic popup dismissed (Escape)")
            return
    log("infographic popup still open after Escape; leaving Chrome open")


def _close_infographic_preview_smart(hwnd: int, page=None) -> None:
    _dismiss_infographic_popup(hwnd, notebook_page=page, preview_page=page, extra_tab=False)


def _wait_studio_history_visible(page, *, timeout_s: float = 6.0) -> bool:
    if page is None:
        time.sleep(0.5)
        return True
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if len(_list_studio_history_rows(page)) >= 1 and not _preview_markers_open(page):
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _viewport_point_to_screen(hwnd: int, page, vx: float, vy: float) -> tuple[int, int]:
    """Map a page viewport point to Windows screen pixels via ClientToScreen."""
    from cli.win_gui_tasks import set_foreground

    set_foreground(hwnd)
    time.sleep(0.15)
    chrome = page.evaluate(
        """() => {
            const side = (window.outerWidth - window.innerWidth) / 2;
            const top = window.outerHeight - window.innerHeight - side;
            return { side, top };
        }"""
    )
    cx = int(round(float(chrome.get("side") or 0) + float(vx)))
    cy = int(round(float(chrome.get("top") or 0) + float(vy)))
    return _gemini_client_to_screen(hwnd, cx, cy)


def _preview_image_click_points(page) -> list[tuple[float, float, str]]:
    """Viewport points to right-click the opened infographic image (center first)."""
    points: list[tuple[float, float, str]] = []
    info = _largest_preview_img_info(page)
    if info and float(info.get("w") or 0) >= 120:
        x = float(info["x"]) + float(info["w"]) * 0.50
        y = float(info["y"]) + float(info["h"]) * 0.50
        points.append((x, y, "dom-img-center"))
    try:
        vw, vh = page.evaluate("() => [window.innerWidth, window.innerHeight]")
        vw, vh = float(vw), float(vh)
        # Modal infographic sits in the page centre (see user screenshot).
        for x_r, y_r, label in (
            (0.40, 0.52, "modal-centre"),
            (0.38, 0.55, "modal-centre-low"),
            (0.42, 0.48, "modal-centre-high"),
        ):
            points.append((vw * x_r, vh * y_r, label))
    except Exception:
        pass
    seen: set[tuple[int, int]] = set()
    out: list[tuple[float, float, str]] = []
    for x, y, label in points:
        key = (int(x // 8), int(y // 8))
        if key in seen:
            continue
        seen.add(key)
        out.append((x, y, label))
    return out


def _click_copy_image_menu(hwnd: int) -> bool:
    """Click Copy image. Chrome's context menu is a desktop popup, not under hwnd."""
    from cli.win_gui_tasks import ensure_uia_com

    ensure_uia_com()
    names = ("Copy image", "复制图片", "複製圖片")
    for name in names:
        if _click_named(
            hwnd,
            name,
            ["MenuItemControl", "MenuControl", "ButtonControl", "TextControl"],
            search_depth=10,
        ):
            return True
    try:
        import uiautomation as auto

        desktop = auto.GetRootControl()
        for name in names:
            for kwargs in ({"Name": name}, {"SubName": name}):
                try:
                    item = desktop.MenuItemControl(searchDepth=12, **kwargs)
                    if item.Exists(0.55, 0.05):
                        rect = item.BoundingRectangle
                        log(f"desktop UIA click {name!r}")
                        return _click_rect_center(rect)
                except Exception:
                    continue
    except Exception as extra:
        log(f"desktop Copy image lookup failed: {extra}")
    return False


def _activate_copy_image_menu(hwnd: int, *, menu_x: int, menu_y: int) -> bool:
    """Pick Copy image from Chrome's image context menu."""
    if _click_copy_image_menu(hwnd):
        return True
    import pyautogui

    pyautogui.FAILSAFE = False
    # Chrome image menu order: Open in new tab, Save image as, Copy image (3rd).
    log("Copy image UIA miss; keyboard Down×2 Enter on context menu")
    time.sleep(0.2)
    pyautogui.press("down")
    time.sleep(0.06)
    pyautogui.press("down")
    time.sleep(0.06)
    pyautogui.press("enter")
    return True


def _right_click_copy_image_to_png(
    page,
    hwnd: int,
    dest: Path,
    x: float,
    y: float,
    *,
    label: str = "",
) -> bool:
    """Real OS right-click on the image → Copy image → write PNG to dest."""
    write_windows_clipboard("__expect_infographic_image__")
    time.sleep(0.12)
    try:
        sx, sy = _viewport_point_to_screen(hwnd, page, x, y)
    except Exception as extra:
        log(f"viewport-to-screen failed: {extra}")
        sx, sy = int(x), int(y)
    tag = f" ({label})" if label else ""
    log(f"right-click infographic{tag} viewport=({x:.0f},{y:.0f}) screen=({sx},{sy})")
    try:
        _right_click_xy(sx, sy, pause=1.0)
    except Exception as extra:
        log(f"pyautogui right-click failed: {extra}")
        return False
    if not _activate_copy_image_menu(hwnd, menu_x=sx, menu_y=sy):
        log("Copy image menu activation failed; dismissing menu")
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            pyautogui.press("escape")
        except Exception:
            pass
        return False
    time.sleep(0.85)
    if _save_clipboard_image_png(dest):
        log(f"saved preview via Copy image → {dest}")
        return True
    log("Copy image clicked but clipboard had no image")
    return False


def _screenshot_preview_to_png(page, dest: Path, info: dict | None) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if info and float(info.get("w") or 0) >= 180 and float(info.get("h") or 0) >= 180:
        try:
            clip = {
                "x": max(0.0, float(info["x"])),
                "y": max(0.0, float(info["y"])),
                "width": float(info["w"]),
                "height": float(info["h"]),
            }
            page.screenshot(path=str(dest), clip=clip)
            if dest.is_file() and dest.stat().st_size > 2000:
                log(f"saved preview via clip screenshot → {dest}")
                return True
        except Exception as extra:
            log(f"clip screenshot failed: {extra}")
    try:
        vw, vh = page.evaluate("() => [window.innerWidth, window.innerHeight]")
        clip = {
            "x": float(vw) * 0.12,
            "y": float(vh) * 0.12,
            "width": float(vw) * 0.56,
            "height": float(vh) * 0.76,
        }
        page.screenshot(path=str(dest), clip=clip)
        if dest.is_file() and dest.stat().st_size > 2000:
            log(f"saved preview via modal clip screenshot → {dest}")
            return True
    except Exception as extra:
        log(f"modal clip screenshot failed: {extra}")
    try:
        data_url = page.evaluate(_CANVAS_PNG_JS) or ""
        if data_url and _save_png_from_src(page, str(data_url), dest):
            log(f"saved preview via canvas → {dest}")
            return True
    except Exception as extra:
        log(f"canvas png failed: {extra}")
    return False


def _preview_root_locator(page):
    """Open infographic preview container (CDK overlay or inline in-page viewer)."""
    panes = page.locator(".cdk-overlay-pane")
    for marker in ("View prompt", "Good content", "Zoom in", "Bad content"):
        try:
            hit = panes.filter(has=page.get_by_text(marker, exact=False))
            if int(hit.count() or 0) > 0:
                return hit.last
        except Exception:
            continue
    for marker in ("View prompt", "Good content"):
        try:
            dlg = page.get_by_role("dialog").filter(has=page.get_by_text(marker, exact=False))
            if int(dlg.count() or 0) > 0:
                return dlg.last
        except Exception:
            pass
    try:
        inline = page.locator("*").filter(
            has=page.get_by_text("View prompt", exact=False)
        ).filter(has=page.get_by_text("Good content", exact=False))
        if int(inline.count() or 0) > 0:
            return inline.last
    except Exception:
        pass
    return page.locator("body")


def _preview_overlay_locator(page):
    """Backward-compatible alias."""
    return _preview_root_locator(page)


def _wait_mat_menu_visible(page, *, timeout_ms: int = 4000) -> bool:
    menu = page.locator(".cdk-overlay-container .mat-mdc-menu-panel").last
    try:
        menu.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        return False


def _click_preview_download_menu_playwright(page) -> bool:
    """Click Download in the preview popup's ⋮ menu (Angular mat-menu in overlay)."""
    if not _wait_mat_menu_visible(page, timeout_ms=5000):
        log("CDP mat-menu panel not visible after ⋮ click")
    menu = page.locator(".cdk-overlay-container .mat-mdc-menu-panel").last
    patterns = (
        re.compile(r"^Download$", re.I),
        re.compile(r"^Export$", re.I),
        re.compile(r"^下载$"),
        re.compile(r"^下載$"),
        re.compile(r"Save image", re.I),
    )
    for pat in patterns:
        try:
            item = menu.get_by_role("menuitem", name=pat)
            if int(item.count() or 0) > 0:
                item.first.click(timeout=5000)
                log(f"CDP clicked menuitem /{pat.pattern}/")
                return True
        except Exception as exc:
            log(f"CDP menuitem /{pat.pattern}/ failed: {exc}")
    try:
        item = menu.locator(".mat-mdc-menu-item").filter(
            has_text=re.compile(r"^Download$|^Export$|^下载$|^下載$", re.I)
        )
        if int(item.count() or 0) > 0:
            item.first.click(timeout=5000)
            log("CDP clicked Download via .mat-mdc-menu-item text")
            return True
    except Exception as exc:
        log(f"CDP Download text locator failed: {exc}")
    try:
        item = page.get_by_role("menuitem", name=re.compile(r"download|下载|下載", re.I))
        if int(item.count() or 0) > 0:
            item.last.click(timeout=5000)
            log("CDP clicked menuitem via download regex")
            return True
    except Exception as exc:
        log(f"CDP download regex menuitem failed: {exc}")
    try:
        info = page.evaluate(_PREVIEW_DOWNLOAD_MENU_JS)
    except Exception as exc:
        log(f"CDP Download menu lookup failed: {exc}")
        info = None
    if isinstance(info, dict) and info.get("x") and info.get("y"):
        x, y = float(info["x"]), float(info["y"])
        log(f"CDP click Download menu at viewport ({x:.0f},{y:.0f}) text={info.get('text')!r}")
        page.mouse.click(x, y)
        time.sleep(0.45)
        return True
    return False


def _click_preview_more_menu_playwright(page) -> bool:
    """Click the ⋮ button in the opened infographic preview (not Studio list rows)."""
    try:
        info = page.evaluate(_PREVIEW_MORE_BUTTON_JS)
    except Exception as exc:
        log(f"CDP preview ⋮ lookup failed: {exc}")
        info = None
    if isinstance(info, dict) and info.get("x") and info.get("y"):
        x, y = float(info["x"]), float(info["y"])
        mode = info.get("mode") or "unknown"
        log(f"CDP click preview ⋮ at viewport ({x:.0f},{y:.0f}) mode={mode}")
        page.mouse.click(x, y)
        time.sleep(0.55)
        if _wait_mat_menu_visible(page, timeout_ms=3500):
            return True
        log("CDP ⋮ clicked but mat-menu not visible yet; continuing")
        return True

    root = _preview_root_locator(page)
    for label, loc in (
        ("artifact-more-button", root.locator("button.artifact-more-button")),
        ("More role", root.get_by_role("button", name=re.compile(r"^More$", re.I))),
        (
            "artifact-more global",
            page.locator("button.artifact-more-button"),
        ),
    ):
        try:
            n = int(loc.count() or 0)
            if n <= 0:
                continue
            btn = loc.last
            box = btn.bounding_box()
            if box and box["x"] < float(page.evaluate("() => window.innerWidth") or 1920) * 0.30:
                continue
            btn.scroll_into_view_if_needed(timeout=2500)
            btn.click(timeout=5000)
            log(f"CDP click preview ⋮ via {label}")
            time.sleep(0.45)
            if _wait_mat_menu_visible(page, timeout_ms=3500):
                return True
        except Exception as exc:
            log(f"CDP preview ⋮ {label} failed: {exc}")
    return False


def _try_save_via_copy_image(page, hwnd: int, dest: Path) -> bool:
    """Visible right-click infographic → Copy image → save PNG."""
    if page is None:
        return False
    log("trying visible right-click Copy image…")
    write_windows_clipboard("__expect_infographic_image__")
    time.sleep(0.12)
    for vx, vy, label in _preview_image_click_points(page):
        if _right_click_copy_image_to_png(page, hwnd, dest, vx, vy, label=label):
            return True
    return False


def _download_infographic_via_preview_menu(page, hwnd: int, dest: Path) -> bool:
    """Save the open infographic via preview ⋮ → Download → D:\\AI_MEDIA\\working\\*.png."""
    from cli.win_gui_tasks import set_foreground

    dest = Path(dest)
    set_foreground(hwnd)
    time.sleep(0.25)

    def _persist_downloaded(src: Path | None) -> bool:
        if src and _save_download_as_png(src, dest):
            log(f"saved preview via ⋮ Download → {dest}")
            return True
        return False

    if page is not None:
        if _physical_download_via_preview_menu(page, hwnd, dest):
            return True

        try:
            with page.expect_download(timeout=60000) as dl_info:
                if not _click_preview_more_menu_playwright(page):
                    raise RuntimeError("preview ⋮ not found")
                if not _click_preview_download_menu_playwright(page):
                    raise RuntimeError("Download menuitem not found")
                _confirm_infographic_export_dialog(page, hwnd)
            download = dl_info.value
            suffix = Path(download.suggested_filename or "infographic.png").suffix or ".png"
            tmp = dest.parent / f"_itc_{int(time.time())}{suffix}"
            download.save_as(str(tmp))
            ok = _persist_downloaded(tmp)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if ok:
                return True
        except PlaywrightTimeoutError:
            log("CDP expect_download timed out; trying Downloads folder watch")
        except Exception as exc:
            log(f"CDP expect_download failed: {exc}")

        since = time.time()
        try:
            if _click_preview_more_menu_playwright(page):
                if _click_preview_download_menu_playwright(page):
                    time.sleep(0.7)
                    _confirm_infographic_export_dialog(page, hwnd)
                    if _persist_downloaded(_wait_new_browser_download(since, timeout_s=45.0)):
                        return True
                    log("CDP Download clicked but no new file in Downloads")
                else:
                    log("CDP Download menuitem not found after ⋮ click")
            else:
                log("CDP could not find preview ⋮ button")
        except Exception as exc:
            log(f"CDP preview download failed: {exc}")

    log("UIA fallback: preview ⋮ → Download")
    since = time.time()
    _click_infographic_preview_more_menu(hwnd)
    _click_infographic_download_menu_item(hwnd)
    time.sleep(0.8)
    _confirm_infographic_export_dialog(page, hwnd)
    return _persist_downloaded(_wait_new_browser_download(since, timeout_s=45.0))


def _save_open_infographic_png(page, hwnd: int, dest: Path) -> bool:
    """Save open infographic: preview ⋮ → Download, then screenshot fallback."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"itc save target {dest}")
    loaded = _infographic_image_loaded(page)
    if not loaded.get("ready"):
        log("image not marked loaded before save; waiting again…")
        if not _wait_infographic_preview_ready(
            hwnd, page, timeout_s=INFOGRAPHIC_PREVIEW_LOAD_TIMEOUT_S
        ):
            log("image still not loaded; trying ⋮ Download anyway")
    else:
        info = _largest_preview_img_info(page) or loaded
        if info:
            log(
                f"preview visual {info.get('tag')!r} "
                f"{info.get('w', 0):.0f}x{info.get('h', 0):.0f} "
                f"natural={info.get('nw', 0)}x{info.get('nh', 0)}"
            )

    if _download_infographic_via_preview_menu(page, hwnd, dest):
        return True

    if _try_save_via_copy_image(page, hwnd, dest):
        return True

    log("⋮ Download and Copy image failed; trying screenshot fallback")
    info = _largest_preview_img_info(page) or loaded
    if _screenshot_preview_to_png(page, dest, info):
        return True
    try:
        imgs = page.locator("img")
        best_i = None
        best_a = 0.0
        for i in range(min(int(imgs.count() or 0), 24)):
            box = imgs.nth(i).bounding_box()
            if not box or box["width"] < 180 or box["height"] < 180:
                continue
            area = box["width"] * box["height"]
            if area > best_a:
                best_a = area
                best_i = i
        if best_i is not None:
            imgs.nth(best_i).screenshot(path=str(dest))
            if dest.is_file() and dest.stat().st_size > 2000:
                log(f"saved preview via element screenshot → {dest}")
                return True
    except Exception as extra:
        log(f"img locator screenshot failed: {extra}")
    if info and info.get("src"):
        if _save_png_from_src(page, str(info["src"]), dest):
            log(f"saved preview via image src → {dest}")
            return True
    log(f"all save methods failed for {dest}")
    return False


def _copy_visible_infographic_image(hwnd: int, *, x: int | None = None, y: int | None = None) -> bool:
    """Right-click the opened infographic image. Never click Chat (window center)."""
    import pyautogui

    pyautogui.FAILSAFE = False
    if x is None or y is None:
        log("skip window-center right-click (that hits Chat, not the infographic)")
        return False
    log(f"right-click infographic image at ({x},{y})")
    _right_click_xy(int(x), int(y), pause=0.55)
    if _click_named(
        hwnd,
        "Copy image",
        ["MenuItemControl", "MenuControl", "ButtonControl", "TextControl"],
        search_depth=8,
    ):
        time.sleep(0.5)
        return True
    if _click_named(
        hwnd,
        "复制图片",
        ["MenuItemControl", "MenuControl", "ButtonControl", "TextControl"],
        search_depth=8,
    ):
        time.sleep(0.5)
        return True
    pyautogui.press("escape")
    return False


def _click_studio_infographic_row(
    hwnd: int, index: int, title: str = ""
) -> bool:
    """Click the Nth Studio history *button*. False if that row was not found."""
    title = (title or "").strip()
    if title:
        ctrl = _uia_named(
            hwnd,
            title,
            ["ButtonControl", "HyperlinkControl", "ListItemControl"],
            search_depth=22,
            timeout_s=0.4,
        )
        box = _ctrl_box(ctrl) if ctrl is not None else None
        if box:
            left, top, right, bottom = box
            x = left + min(80, max(24, (right - left) // 3))
            y = (top + bottom) // 2
            log(f"UIA click Studio title {title!r} at ({x},{y}) box={box}")
            _click_xy(x, y, pause=1.6)
            return True
        log(f"UIA did not find button named {title!r}")
    boxes = _studio_recent_row_boxes(hwnd)
    if not (1 <= index <= len(boxes)):
        log(f"UIA Studio history row {index} not found (have {len(boxes)}); not guessing")
        return False
    left, top, right, bottom = boxes[index - 1]
    x = left + min(80, max(24, (right - left) // 3))
    y = (top + bottom) // 2
    log(f"click Studio infographic row {index} at ({x},{y}) box={boxes[index - 1]}")
    _click_xy(x, y, pause=1.6)
    return True


def _download_one_infographic_via_menu(hwnd: int, index: int, dest: Path) -> bool:
    """Open Studio row → ⋮ → Download → save to *dest*."""
    _click_studio_infographic_row(hwnd, index)
    time.sleep(1.8)
    if not _infographic_preview_open(hwnd):
        log(f"preview may not be open for row {index}; skip download (no Chat right-click)")
        return False

    since = time.time()
    _click_infographic_preview_more_menu(hwnd)
    _click_infographic_download_menu_item(hwnd)
    time.sleep(0.8)
    _confirm_infographic_export_dialog(None, hwnd)
    downloaded = _wait_new_browser_download(since, timeout_s=35.0)
    if downloaded and _save_download_as_jpg(downloaded, dest):
        log(f"downloaded row {index} via menu → {dest}")
        _close_infographic_preview(hwnd)
        return True

    log(f"menu download failed for row {index}; fallback Copy image")
    write_windows_clipboard("__expect_infographic_image__")
    time.sleep(0.15)
    _copy_visible_infographic_image(hwnd)
    if _save_clipboard_image(dest):
        _close_infographic_preview(hwnd)
        return True
    _close_infographic_preview(hwnd)
    return False


def _download_whole_story_images(hwnd: int, times: int) -> list[str]:
    """Open each Studio infographic, ⋮ → Download, save into Windows Downloads."""
    from cli.win_gui_tasks import set_foreground

    downloads = windows_downloads_dir()
    downloads.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    saved: list[str] = []
    n = max(1, int(times or NOTEBOOKLM_COVER_TIMES))
    for i in range(1, n + 1):
        hwnd = _find_notebooklm_hwnd() or hwnd
        set_foreground(hwnd)
        time.sleep(0.5)
        dest = downloads / f"whole_story_image_{i}_{stamp}.jpg"
        if _download_one_infographic_via_menu(hwnd, i, dest):
            saved.append(str(dest))
            log(f"saved {dest} ({dest.stat().st_size} bytes)")
        else:
            log(f"failed to save whole_story_image_{i}")
        time.sleep(0.8)
    from utility.telegram_session import save_whole_story_images

    return save_whole_story_images(saved)


def check_notebooklm_infographic_status(
    expected: int = NOTEBOOKLM_COVER_TIMES,
    *,
    attach_only: bool = False,
) -> dict:
    """Look at Studio right-hand list: generating spinner vs finished rows (Hermes CDP)."""
    from cli.win_gui_tasks import ensure_uia_com, set_foreground

    want = max(1, int(expected or NOTEBOOKLM_COVER_TIMES))
    if attach_only is False and hermes_cdp_is_open():
        attach_only = True
    cdp = _notebooklm_studio_status_via_cdp(
        ensure_cdp=True, attach_only=attach_only
    )
    if cdp.get("ok"):
        generating_n = int(cdp.get("count") or 0)
        generating = bool(cdp.get("generating"))
        ready = bool(cdp.get("ready"))
        total = int(cdp.get("total_items") or 0)
        log(
            f"nbif via=cdp generating={generating} count={generating_n} "
            f"total={total} ready={ready}"
        )
        return {
            "ok": True,
            "ready": ready,
            "generating": generating,
            "generating_count": generating_n,
            "finished_count": max(0, total - generating_n),
            "expected": want,
            "uncertain": False,
            "via": "cdp",
            "error": "",
            "generating_items": list(cdp.get("generating_items") or []),
            "total_items": total,
        }

    hwnd = _find_notebooklm_hwnd()
    if not hwnd:
        return {
            "ok": False,
            "ready": False,
            "generating": False,
            "generating_count": 0,
            "finished_count": 0,
            "expected": want,
            "error": (
                f"CDP 查询失败（{cdp.get('error') or '未知'}），"
                "也找不到 NotebookLM 窗口。请先 nbi 打开 notebook。"
            ),
        }
    ensure_uia_com()
    set_foreground(hwnd)
    time.sleep(0.25)
    generating_n = _count_generating_infographics(hwnd)
    generating = generating_n > 0
    uncertain = not generating
    log(
        f"nbif CDP unavailable ({cdp.get('error')}); "
        f"UIA fallback count={generating_n} uncertain={uncertain}"
    )
    err = ""
    if uncertain:
        err = (
            f"CDP Studio 检测失败（{cdp.get('error') or 'CDP 失败'}），"
            "UIA 也没扫到 Generating。请确认 HermesChromeCDP 已打开 notebook。"
        )
    return {
        "ok": True,
        "ready": not generating and not uncertain,
        "generating": generating,
        "generating_count": generating_n,
        "finished_count": 0,
        "expected": want,
        "uncertain": uncertain,
        "via": "uia",
        "error": err,
    }


def _copy_one_infographic_to_png(hwnd: int, index: int, dest: Path, page=None) -> bool:
    """Open Studio history item *index*, wait for the image page, copy PNG, close it."""
    preview_page = page
    extra_tab = False
    clicked = False
    title = ""
    if page is not None:
        preview_page, extra_tab, clicked, title = _open_studio_infographic_via_dom(
            page, index
        )
    if not clicked:
        clicked = _click_studio_infographic_row(hwnd, index, title=title)
        preview_page = page
        extra_tab = False
    if not clicked:
        log(f"did not click Studio history #{index}; skip wait and skip Chat clicks")
        return False

    log(f"itc item {index} will save to {dest}")
    if not _wait_infographic_preview_ready(
        hwnd,
        preview_page,
        timeout_s=INFOGRAPHIC_PREVIEW_LOAD_TIMEOUT_S,
    ):
        log(f"Studio history #{index} click did not open infographic page")
        _dismiss_infographic_popup(
            hwnd, notebook_page=page, preview_page=preview_page, extra_tab=extra_tab
        )
        return False

    saved = False
    if preview_page is not None:
        saved = _save_open_infographic_png(preview_page, hwnd, dest)
    elif _infographic_preview_open(hwnd):
        log("CDP page unavailable; trying physical/UIA save on open preview")
        saved = _save_open_infographic_png(None, hwnd, dest)
    if not saved:
        log(f"Studio item {index}: preview open but ⋮ Download save failed")

    log(f"dismiss infographic popup #{index} (keep Chrome / notebook open)")
    _dismiss_infographic_popup(
        hwnd, notebook_page=page, preview_page=preview_page, extra_tab=extra_tab
    )
    _wait_studio_history_visible(page, timeout_s=6.0)

    ok = bool(saved and dest.is_file() and dest.stat().st_size > 2000)
    if ok:
        log(f"saved infographic {index} → {dest}")
    else:
        log(f"failed to save infographic {index} to {dest}")
    return ok


_NB_VISIBLE_CENTER_JS = """(sel) => {
    const els = (eval(sel))();
    for (const el of els){
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        const onscreen = r.width>0 && r.height>0 && r.bottom>0 && r.top < window.innerHeight && r.right>0 && r.left < window.innerWidth;
        const vis = cs.visibility!=='hidden' && cs.display!=='none' && parseFloat(cs.opacity||'1')>0.05;
        if (onscreen && vis){
            el.scrollIntoView({block:'center'});
            const rr = el.getBoundingClientRect();
            return {x: Math.round(rr.x+rr.width/2), y: Math.round(rr.y+rr.height/2)};
        }
    }
    return null;
}"""

_NB_ARTIFACT_TITLES_JS = """(limit) => {
    const titles = [];
    for (const el of document.querySelectorAll('.artifact-title')) {
        const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!t || titles.includes(t)) continue;
        titles.push(t);
        if (limit > 0 && titles.length >= limit) break;
    }
    return titles;
}"""

_NB_VIEWER_IMG_SRC_JS = """() => {
    const av = document.querySelector('artifact-viewer');
    if (!av) return null;
    const im = av.querySelector('img[src^="https://lh3.googleusercontent.com/notebooklm/"]');
    return im ? im.getAttribute('src') : null;
}"""

_NB_VIEWER_IMG_READY_JS = """() => {
    const av = document.querySelector('artifact-viewer');
    if (!av) return false;
    return !!av.querySelector('img[src^="https://lh3.googleusercontent.com/notebooklm/"]');
}"""


def _nb_itc_visible_center(page, selector_js: str) -> dict | None:
    try:
        pt = page.evaluate(_NB_VISIBLE_CENTER_JS, selector_js)
    except Exception as exc:
        log(f"visible_center failed: {exc}")
        return None
    return pt if isinstance(pt, dict) and pt.get("x") else None


def _nb_itc_close_viewer(page) -> None:
    """Close artifact-viewer overlay. Use Close button — Escape can dismiss the notebook."""
    for _ in range(2):
        try:
            page.locator('button[aria-label="Close"]').first.click(timeout=2500)
            page.wait_for_timeout(1300)
        except Exception:
            break


def _nb_itc_list_artifact_titles(page, limit: int = 3) -> list[str]:
    titles: list[str] = []
    try:
        raw = page.evaluate(_NB_ARTIFACT_TITLES_JS, max(1, int(limit))) or []
        titles = [str(t).strip() for t in raw if str(t).strip()]
    except Exception as exc:
        log(f"artifact-title list failed: {exc}")
    if titles:
        return titles[:limit]
    rows = _list_studio_history_rows(page)
    return [
        str(r.get("text") or "").strip()
        for r in rows[:limit]
        if str(r.get("text") or "").strip()
    ]


def _nb_itc_open_artifact(page, title: str) -> bool:
    """Open a Studio infographic by title (Hermes nb_cover_dl approach)."""
    title = (title or "").strip()
    if not title:
        return False
    _nb_itc_close_viewer(page)
    try:
        page.locator(".artifact-title", has_text=title).first.scroll_into_view_if_needed(
            timeout=5000
        )
        row = page.locator(
            ".artifact-button-content",
            has=page.locator(".artifact-title", has_text=title),
        ).first
        row.click(timeout=8000, force=True)
        page.wait_for_selector("artifact-viewer", timeout=10000)
    except Exception as exc:
        log(f"open artifact {title!r} via .artifact-title failed: {exc}")
        if not _click_studio_title_via_playwright(page, title):
            return False
        try:
            page.wait_for_selector("artifact-viewer", timeout=10000)
        except Exception:
            return False
    for _ in range(30):
        try:
            if page.evaluate(_NB_VIEWER_IMG_READY_JS):
                return True
        except Exception:
            pass
        time.sleep(1.5)
    return False


def _nb_itc_viewer_img_src(page) -> str:
    try:
        return str(page.evaluate(_NB_VIEWER_IMG_SRC_JS) or "").strip()
    except Exception as exc:
        log(f"viewer img src failed: {exc}")
        return ""


def _nb_itc_download_via_menu(page, dest: Path) -> bool:
    """More options → Download on the visible artifact-viewer (coordinate click)."""
    dest = Path(dest)
    page.bring_to_front()
    more_js = '() => [...document.querySelectorAll(\'button[aria-label="More options"]\')]'
    pt = None
    for _ in range(10):
        pt = _nb_itc_visible_center(page, more_js)
        if pt:
            break
        page.wait_for_timeout(700)
    if not pt:
        raise RuntimeError("More options button not visible")
    page.mouse.click(pt["x"], pt["y"])
    page.wait_for_timeout(900)

    dl_js = (
        '() => [...document.querySelectorAll(\'[role="menuitem"]\')]'
        ".filter(e => /Download/i.test(e.textContent))"
    )
    pt2 = None
    for _ in range(10):
        pt2 = _nb_itc_visible_center(page, dl_js)
        if pt2:
            break
        page.wait_for_timeout(500)
    if not pt2:
        raise RuntimeError("Download menuitem not visible")

    dest.parent.mkdir(parents=True, exist_ok=True)
    with page.expect_download(timeout=25000) as dl_info:
        page.mouse.click(pt2["x"], pt2["y"])
    dl = dl_info.value
    dl.save_as(str(dest))
    for _ in range(25):
        if dest.is_file() and dest.stat().st_size > 0:
            break
        time.sleep(0.3)
    return dest.is_file() and dest.stat().st_size > 2000


def _capture_infographics_via_artifact_viewer(page, n: int) -> list[str]:
    """Download top N NotebookLM infographics → Windows Downloads (Hermes-style)."""
    downloads = windows_downloads_dir()
    downloads.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    titles = _nb_itc_list_artifact_titles(page, n)
    log(f"itc artifact titles ({len(titles)}): {titles!r}")
    saved: list[str] = []
    for i in range(1, n + 1):
        title = titles[i - 1] if i <= len(titles) else ""
        dest = downloads / f"whole_story_image_{i}_{stamp}.png"
        log(f"itc item {i}/{n} title={title!r} → {dest}")

        opened = _nb_itc_open_artifact(page, title) if title else False
        if not opened:
            log(f"could not open artifact #{i} ({title!r})")
            continue

        src = _nb_itc_viewer_img_src(page)
        log(f"itc item {i} viewer img: {bool(src)}")
        if not src:
            _nb_itc_close_viewer(page)
            continue

        ok = False
        try:
            ok = _nb_itc_download_via_menu(page, dest)
            if ok:
                log(f"itc item {i} saved via menu → {dest} ({dest.stat().st_size} bytes)")
        except Exception as exc:
            log(f"itc item {i} menu download failed: {exc}")

        if not ok:
            try:
                ok = _save_png_from_src(page, src, dest)
                if ok:
                    log(f"itc item {i} saved via URL → {dest} ({dest.stat().st_size} bytes)")
            except Exception as exc2:
                log(f"itc item {i} URL fallback failed: {exc2}")

        _nb_itc_close_viewer(page)
        page.wait_for_timeout(800)
        if ok:
            saved.append(str(dest))
    return saved


def notebooklm_window_open() -> bool:
    return bool(_find_notebooklm_hwnd())


def close_notebooklm_chrome_window() -> bool:
    """Close the NotebookLM Chrome window after itc finishes copying."""
    hwnd = _find_notebooklm_hwnd()
    if not hwnd:
        return False
    log(f"closing NotebookLM Chrome hwnd={hwnd}")
    try:
        import win32con
        import win32gui

        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        time.sleep(0.7)
        return True
    except Exception as exc:
        log(f"PostMessage close failed: {exc}")
    try:
        import pyautogui
        from cli.win_gui_tasks import set_foreground

        set_foreground(hwnd)
        time.sleep(0.2)
        pyautogui.hotkey("alt", "f4")
        time.sleep(0.5)
        return True
    except Exception as exc:
        log(f"Alt+F4 close failed: {exc}")
        return False


def capture_notebooklm_infographics(
    times: int = NOTEBOOKLM_COVER_TIMES,
    *,
    require_ready: bool = True,
    attach_only: bool = False,
    close_chrome: bool = False,
) -> list[str]:
    """Open each Studio infographic via artifact-viewer, download PNGs to Downloads."""
    from cli.win_gui_tasks import ensure_uia_com
    from utility.telegram_session import save_whole_story_images

    n = max(1, int(times or NOTEBOOKLM_COVER_TIMES))
    hwnd = _find_notebooklm_hwnd()
    if not hwnd and not attach_only:
        raise RuntimeError(
            "找不到 NotebookLM 窗口。请发 itc N（N=Chrome 号）重新打开 notebook 再拷图。"
        )
    ensure_uia_com()
    port = ensure_notebooklm_cdp(NOTEBOOKLM_URL, attach_only=attach_only)
    hwnd = _find_notebooklm_hwnd() or hwnd
    if port and hwnd and not _inside_notebook(hwnd, timeout_s=0.5):
        if _open_first_existing_notebook_cdp(port):
            time.sleep(2.0)
            hwnd = _find_notebooklm_hwnd() or hwnd
    status = check_notebooklm_infographic_status(
        expected=n, attach_only=attach_only
    )
    if status.get("generating"):
        raise RuntimeError(
            "Studio 里还能看到 “Generating infographic...”，还没 ready。"
            "请先发 nbif，等 ready 后再 itc。"
        )
    if require_ready and not status.get("ready"):
        raise RuntimeError(
            status.get("error")
            or "还不能确认三张 infographic 已经 ready。请先发 nbif。"
        )

    def _copy_all(page) -> list[str]:
        if page is None:
            raise RuntimeError(
                "NotebookLM CDP 不可用，无法用 artifact-viewer 下载。"
                "请重发 itc；若仍失败，确认 HermesChromeCDP 已在 9222 启动。"
            )
        return _capture_infographics_via_artifact_viewer(page, n)

    saved = _run_with_notebooklm_page(
        _copy_all, port=port, attach_only=attach_only
    )
    if len(saved) < n:
        if saved:
            save_whole_story_images(saved)
        raise RuntimeError(
            f"只拷到 {len(saved)}/{n} 张 infographic。"
            "请确认已点开 Studio 右侧历史上边的 generate 项，再重发 itc。"
        )
    paths = save_whole_story_images(saved)
    if close_chrome:
        log("all infographics saved; closing NotebookLM Chrome now")
        close_notebooklm_chrome_window()
    else:
        log("all infographics saved; keeping NotebookLM Chrome open")
    return paths


def open_existing_notebooklm_window() -> tuple[int, str]:
    """Launch current Chrome profile → NotebookLM home → first existing notebook.

    Does not Generate. Returns ``(hwnd, profile_dir)``.
    """
    try:
        import pyautogui
    except Exception as exc:
        raise RuntimeError(f"pyautogui is required for NotebookLM: {exc}") from exc

    pyautogui.FAILSAFE = False
    from cli.win_gui_tasks import ensure_uia_com, set_foreground, win32con, win32gui

    ensure_uia_com()
    before = {hwnd for hwnd, _ in _enum_titled_windows()}
    nbl_port = ensure_notebooklm_cdp(NOTEBOOKLM_URL)
    try:
        hwnd = _wait_notebooklm_hwnd(exclude=before, timeout_s=10.0)
    except RuntimeError:
        log("no new NotebookLM window; trying existing")
        hwnd = _find_notebooklm_hwnd()
        if not hwnd:
            hwnd = _wait_notebooklm_hwnd(timeout_s=12.0)
    log(f"NotebookLM hwnd={hwnd} cdp_port={nbl_port} (HermesChromeCDP)")
    if win32gui is not None and win32con is not None:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        except Exception:
            pass
    set_foreground(hwnd)
    time.sleep(3.5)

    opened = False
    if cdp_ready(nbl_port):
        opened = _open_first_existing_notebook_cdp(nbl_port)
        if opened:
            log("opened first Recent notebook via CDP/DOM")
    if not opened:
        _open_first_existing_notebook(hwnd)
    time.sleep(2.5)
    hwnd = _find_notebooklm_hwnd() or hwnd
    set_foreground(hwnd)
    profile_dir = resolve_chrome_profile_directory(
        getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    if _named_exists(
        hwnd,
        "Add sources",
        ["ButtonControl", "TextControl", "HyperlinkControl"],
        search_depth=12,
        timeout_s=0.25,
    ) and not _inside_notebook(hwnd, timeout_s=0.35):
        raise RuntimeError(
            "看起来点到了 Create new（空 notebook）。"
            "请不要新建，只打开 Recent notebooks 里已有的第一张 Story Builder。"
        )
    if not _inside_notebook(hwnd, timeout_s=0.5):
        _wait_named(
            hwnd,
            "Infographic",
            ["ButtonControl", "HyperlinkControl"],
            timeout_s=10.0,
            search_depth=16,
        )
    if not _inside_notebook(hwnd, timeout_s=0.5):
        if _create_new_box(hwnd) or not _title_looks_like_open_notebook(
            _notebooklm_window_title(hwnd)
        ):
            raise RuntimeError(
                "还停在 NotebookLM 首页，没能点开 Recent notebooks 第一张卡片。"
                "请确认首页已完全加载（Create new 右边确实有一张 Story Builder 卡），"
                "然后再发 nbi N 或 itc N。"
            )
        raise RuntimeError(
            "打开已有 notebook 后看不到 Infographic。"
            "请确认 Recent notebooks 第一张（Create new 右侧）是 Story Builder，且没有点到 Create new。"
        )
    return int(hwnd), str(profile_dir)


def reopen_notebooklm_and_capture(
    times: int = NOTEBOOKLM_COVER_TIMES,
) -> list[str]:
    """Open current Chrome profile + existing notebook, then copy top N infographics."""
    open_existing_notebooklm_window()
    return capture_notebooklm_infographics(times=times, require_ready=False)


def handle_notebooklm_covers(times: int = NOTEBOOKLM_COVER_TIMES) -> str:
    """Open NotebookLM with the current Chrome profile and Generate infographic N times.

    Clipboard must already hold the NotebookLM cover prompt (``notebooklm 1``).
    Clicks: first Recent notebook → Infographic → Portrait + Concise → paste → Generate.
    Does not wait for generation to finish; use ``nbif`` then ``itc``.
    """
    try:
        import pyautogui
    except Exception as exc:
        raise RuntimeError(f"pyautogui is required for NotebookLM: {exc}") from exc

    pyautogui.FAILSAFE = False
    prompt = ""
    try:
        prompt = (read_windows_clipboard() or "").strip()
    except Exception:
        prompt = ""
    if len(prompt) < NOTEBOOKLM_PROMPT_MIN_CHARS:
        raise RuntimeError(
            "剪贴板里没有 NotebookLM 提示词（太短）。"
            "先在 SCENE 发 nbp，再 nbp 1（Image / 单图）。"
        )

    from cli.win_gui_tasks import set_foreground

    hwnd, profile_dir = open_existing_notebooklm_window()
    if _notebooklm_quota_hit(hwnd):
        raise RuntimeError(
            "NotebookLM daily limit reached on this profile. "
            "换一个账号再发 nbi N。"
        )

    started = 0
    n = max(1, int(times or NOTEBOOKLM_COVER_TIMES))
    for i in range(n):
        log(f"NotebookLM infographic {i + 1}/{n}")
        hwnd = _find_notebooklm_hwnd() or hwnd
        set_foreground(hwnd)
        time.sleep(0.6)
        _open_customize_infographic(hwnd)
        time.sleep(0.4)
        _set_infographic_options(hwnd)
        _paste_infographic_prompt(hwnd, prompt)
        _click_generate(hwnd)
        closed = _wait_customize_closed(hwnd, timeout_s=16.0)
        started += 1
        log(f"Generate {i + 1} clicked; dialog_closed={closed}")
        time.sleep(2.4)

    from utility.telegram_session import mark_notebooklm_generate_started

    mark_notebooklm_generate_started(started or n)
    return (
        f"launched {NOTEBOOKLM_URL} profile_dir={profile_dir}; "
        f"clicked Generate {started} time(s) (Portrait + Concise); "
        f"未等待生成结束。请稍后发 nbif 查询是否 ready，ready 后再发 itc 拷图。"
    )


def _clipboard_has_image() -> bool:
    """True when the Windows clipboard currently holds a pasteable bitmap."""
    try:
        from PIL import ImageGrab

        clip = ImageGrab.grabclipboard()
        if clip is None:
            return False
        if hasattr(clip, "size"):
            w, h = clip.size
            return w > 0 and h > 0
        if isinstance(clip, list) and clip:
            return True
    except Exception as exc:
        log(f"clipboard image probe failed: {exc}")
    return False


def _wait_grok_hwnd(timeout_s: float = 28.0) -> int:
    from cli.win_gui_tasks import set_foreground

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hwnd = _find_grok_chrome_hwnd()
        if hwnd:
            set_foreground(hwnd)
            time.sleep(0.35)
            return hwnd
        time.sleep(0.5)
    raise RuntimeError(
        "Grok Imagine 窗口未出现。请检查 Chrome 是否已打开 grok.com/imagine。"
    )


def _wait_grok_composer_ready(hwnd: int, timeout_s: float = 18.0) -> bool:
    per = max(2.0, timeout_s / 5.0)
    for name in (
        "输入或粘贴图像",
        "输入你的想象",
        "Ask Grok",
        "What do you want",
        "Imagine",
        "我们应该想象什么",
        "Message",
    ):
        if _wait_named(
            hwnd,
            name,
            ["TextControl", "EditControl", "ButtonControl"],
            timeout_s=per,
            search_depth=14,
        ):
            return True
    return False


def _grok_scene_image_prompts(n: int) -> list[tuple[str, str]]:
    """Scene image prompts 1…N from ``DIRECT_VIDEO_PROMPT_CHOICES`` (same as old ``gri``)."""
    import config_prompt

    rows = [
        (str(lbl).strip(), str(tpl or ""))
        for lbl, tpl in (config_prompt.DIRECT_VIDEO_PROMPT_CHOICES or [])
        if str(lbl or "").strip()
    ]
    image_rows = rows[:4]
    if len(image_rows) < n:
        raise RuntimeError(
            f"需要 {n} 个场景图提示词，DIRECT_VIDEO_PROMPT_CHOICES 只有 {len(image_rows)} 个。"
        )
    out: list[tuple[str, str]] = []
    for i in range(n):
        lbl, tpl = image_rows[i]
        text = (tpl or "").strip()
        if not text:
            raise RuntimeError(f"场景图提示词为空：{lbl}")
        out.append((lbl, text))
    return out


def _grok_scene_video_prompts(n: int, *, video_nb_index: int | None = None) -> list[tuple[str, str]]:
    """NotebookLM video 提示词 1…N — used internally by ``grv`` automation."""
    import config_prompt
    from cli.bridge import send_bridge_command
    from utility.telegram_session import load_grok_scene_video_nb_index

    idx = video_nb_index if video_nb_index is not None else load_grok_scene_video_nb_index()
    base, var, short = config_prompt.grok_scene_video_nb_export(idx)
    tag = f"[{idx}] {short}"
    out: list[tuple[str, str]] = []
    for i in range(1, n + 1):
        ok, msg = send_bridge_command(
            screen=config.SCREEN_STORY_SCENE,
            op="set",
            field="scene_choice",
            value=str(i),
            timeout_s=25.0,
        )
        if not ok:
            raise RuntimeError(
                f"场景 {i} {tag} 提示词失败（需要 SCENE 已打开且 scene_content 有效）：{msg}"
            )
        text = (read_windows_clipboard() or "").strip()
        if len(text) < 12:
            raise RuntimeError(
                f"场景 {i} video 提示词为空或太短（{base}/{var}）。"
                "请确认 scene_content 是有效 JSON 数组。"
            )
        out.append((f"场景{i} {tag}", text))
        log(f"Grok scene {i} video prompt ready ({base}/{var}, {len(text)} chars)")
    return out


def handle_grok_imagine_tabs(*, video_nb_index: int | None = None) -> str:
    """Open N ``grok.com/imagine`` tabs and prepare each for scene image generation."""
    import config_prompt
    from utility.telegram_session import (
        load_story_scene_prompt_choice,
        save_grok_scene_video_nb_index,
    )

    choice = load_story_scene_prompt_choice()
    label = (choice.get("label") or "").strip()
    n = int(choice.get("tabs") or 0)
    if not label or n < 1:
        raise RuntimeError(
            "还没有记录 story_scene_prompt_choice。"
            "先在 SCENE 选 LM：lm 4。"
        )
    if video_nb_index is not None:
        save_grok_scene_video_nb_index(video_nb_index)
    if video_nb_index is not None:
        v_idx = video_nb_index
    else:
        from utility.telegram_session import load_grok_scene_video_nb_index

        v_idx = load_grok_scene_video_nb_index()
    v_label = config_prompt.grok_scene_video_nb_choice_label(v_idx)
    grok_port = ensure_grok_cdp(GROK_IMAGINE_URL)
    profile_dir = resolve_chrome_profile_directory(
        getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    profile_label = (getattr(config, "GEMINI_CHROME_PROFILE", "") or profile_dir).strip()
    user_data = _chrome_cdp_user_data_dir()
    log(
        f"Grok Imagine × {n} ({label}) cdp_port={grok_port} "
        f"account={profile_label!r} profile={profile_dir} user-data={user_data}"
    )
    cover_png = _grok_resolve_cover_png()
    if not cover_png:
        raise RuntimeError(
            "没有封面图。请先 itc 选封面（或 Copy image 到剪贴板），再 grv 1。"
        )
    scene_prompts = _grok_scene_image_prompts(n)
    video_prompts = _grok_scene_video_prompts(n, video_nb_index=v_idx)
    pasted_n, prompt_n, downloads = _grok_prepare_all_tabs_cdp(
        n,
        cover_png=cover_png,
        port=grok_port,
        fresh_tabs=True,
        scene_prompts=scene_prompts,
        auto_generate=True,
        video_prompts=video_prompts,
        auto_generate_video=True,
        auto_download_video=True,
    )
    if pasted_n < n:
        raise RuntimeError(
            f"第一轮只成功粘贴 {pasted_n}/{n} 个标签的封面图。"
            "请确认封面图有效，并重发 grv 1。"
        )
    paste_note = f"; pasted cover image into {n} tab(s) (round 1 Ctrl+V)"
    if prompt_n < n:
        raise RuntimeError(
            f"只成功粘贴 {prompt_n}/{n} 个场景提示词。"
            "请重发 grv 1。"
        )
    prompt_labels = ", ".join(lbl for lbl, _ in scene_prompts)
    video_labels = ", ".join(lbl for lbl, _ in video_prompts)
    download_note = ""
    if downloads:
        from utility.telegram_session import save_grok_scene_videos

        save_grok_scene_videos(downloads)
        names = ", ".join(
            f"scene {d.get('scene')}: {Path(d.get('path') or '').name}"
            for d in downloads
        )
        download_note = f"; downloaded {len(downloads)} video clip(s) ({names})"
    return (
        f"opened {n} Grok Imagine tab(s) for {label!r} "
        f"({GROK_IMAGINE_URL}) account={profile_label} "
        f"profile_dir={profile_dir} cdp={grok_port}; "
        f"video_nb={v_idx} ({v_label}); "
        f"prepared image + 9:16 竖屏 + scene prompts + Submit generate image "
        f"+ Video mode + scene video prompts + Submit generate video "
        f"+ download each scene mp4 on each tab{paste_note}{download_note}; "
        f"image prompts: {prompt_labels}; video prompts: {video_labels}"
    )


def prepare_open_grok_imagine_tabs(*, paste_image: bool = True) -> str:
    """On already-open Grok Imagine tabs: paste clipboard image + 9:16 竖屏."""
    n = _grok_recorded_tab_count() or 1
    port = _grok_resolve_cdp_port()
    cover_png = _grok_resolve_cover_png() if paste_image else None
    pasted_n, _prompt_n, _downloads = _grok_prepare_all_tabs_cdp(
        n, cover_png=cover_png, port=port, fresh_tabs=False
    )
    if cover_png:
        if pasted_n < n:
            raise RuntimeError(
                f"只成功粘贴 {pasted_n}/{n} 个 Grok 标签。"
                "请确认剪贴板有图片；若 Grok 窗口已关，先关尽 Chrome 再重发 grv 1。"
            )
        note = f"pasted clipboard image + 9:16 竖屏 on {n} tab(s) (verified)"
    else:
        note = f"set 9:16 竖屏 on {n} tab(s); clipboard 无图片"
    return note


# Grok Imagine composer sits in the page center (not the bottom gallery).
GROK_PROMPT_X = 0.52
GROK_PROMPT_Y = 0.52
GROK_TOOLBAR_Y = 0.575
GROK_ASPECT_BTN_X = 0.595
GROK_ASPECT_MENU_Y = 0.468
GROK_IMAGE_ICON_X = 0.395
GROK_VIDEO_ICON_X = 0.418
GROK_GENERATE_X = 0.665

# Stable Grok Imagine DOM selectors (from page outerHTML analysis).
GROK_EDITOR_SEL = (
    'div[data-testid="chat-input"] div[contenteditable="true"][role="textbox"]'
)
GROK_EDITOR_ALT_SEL = '[contenteditable="true"][aria-label="Ask Grok anything"]'
GROK_FILE_INPUT_SEL = 'input[type="file"][name="files"]'
GROK_UPLOAD_BTN_SEL = 'button[aria-label="上传"]'
GROK_DROP_CONTAINER_SEL = '[data-testid="drop-container"]'
GROK_IMAGE_ATTACH_TIMEOUT_S = 20.0
GROK_IMAGE_READY_MIN_S = 6
GROK_IMAGE_READY_TIMEOUT_S = 6 * 60
GROK_VIDEO_READY_MIN_S = 8
GROK_VIDEO_READY_TIMEOUT_S = 8 * 60
GROK_DOWNLOAD_TIMEOUT_S = 120


_GROK_FOCUS_COMPOSER_JS = """() => {
  const chat = document.querySelector('[data-testid="chat-input"]');
  if (chat) {
    const el = chat.querySelector('.ProseMirror, [contenteditable="true"][role="textbox"], [contenteditable="true"]') || chat;
    el.focus();
    el.click();
    return 'chat-input';
  }
  const el = document.querySelector('[contenteditable="true"][role="textbox"]');
  if (el) { el.focus(); el.click(); return 'contenteditable'; }
  return false;
}"""


_GROK_FIND_BOTTOM_PROMPT_BAR_JS = """() => {
  const vh = window.innerHeight;
  const vw = window.innerWidth;
  const minTop = vh * 0.60;

  function meta(el, method) {
    const r = el.getBoundingClientRect();
    return {
      method,
      x: r.left + Math.min(Math.max(r.width * 0.18, 48), 140),
      y: r.top + r.height * 0.5,
      top: r.top,
      width: r.width,
      text: (el.innerText || el.textContent || '').slice(0, 120),
    };
  }

  function isOverlayOnImage(el) {
    const r = el.getBoundingClientRect();
    const text = (el.innerText || el.textContent || '');
    if (/描述你想修改|describe what you want to change/i.test(text) && r.width < 320) return true;
    if (r.top < minTop) return true;
    if (r.width < 120 || r.height < 14) return true;
    return false;
  }

  function score(el) {
    if (isOverlayOnImage(el)) return -1;
    const r = el.getBoundingClientRect();
    let s = r.top;
    const text = (el.innerText || el.textContent || '');
    if (/Visual_Style|Export_variant|video\\/motion/i.test(text)) s += 10000;
    if (el.closest('[data-testid="chat-input"]')) s += 20000;
    const cx = r.left + r.width / 2;
    s += Math.max(0, 600 - Math.abs(cx - vw / 2));
    s += Math.min(r.width, 900);
    if (r.width < 220) s -= 8000;
    return s;
  }

  const chat = document.querySelector('[data-testid="chat-input"]');
  if (chat) {
    const r = chat.getBoundingClientRect();
    if (r.top >= minTop) {
      const ed = chat.querySelector('.ProseMirror, [contenteditable="true"][role="textbox"], [contenteditable="true"]');
      return meta(ed || chat, 'chat-input-bottom');
    }
  }

  const pool = [
    ...document.querySelectorAll('[data-testid="chat-input"] .ProseMirror'),
    ...document.querySelectorAll('[data-testid="chat-input"] [contenteditable="true"]'),
    ...document.querySelectorAll('.ProseMirror[contenteditable="true"]'),
    ...document.querySelectorAll('[contenteditable="true"][role="textbox"]'),
  ];
  let best = null;
  let bestScore = -1;
  for (const el of pool) {
    const sc = score(el);
    if (sc > bestScore) { bestScore = sc; best = el; }
  }
  if (!best) return null;
  return meta(best, 'scored-bottom-bar');
}"""


_GROK_FIND_MAIN_COMPOSER_CLICK_JS = """() => {
  function isOverlay(el) {
    const r = el.getBoundingClientRect();
    const t = (el.innerText || el.textContent || '');
    return /描述你想修改|describe what you want to change/i.test(t) && r.width < 320;
  }
  const chat = document.querySelector('[data-testid="chat-input"]');
  if (!chat || isOverlay(chat)) return null;
  const ed = chat.querySelector('.ProseMirror, [contenteditable="true"][role="textbox"], [contenteditable="true"]') || chat;
  const r = ed.getBoundingClientRect();
  return {
    method: 'main-chat-input',
    x: r.left + Math.min(Math.max(r.width * 0.18, 48), 140),
    y: r.top + r.height * 0.5,
    top: r.top,
    width: r.width,
    text: (ed.innerText || ed.textContent || '').slice(0, 120),
  };
}"""


_GROK_OPEN_FILE_CHOOSER_JS = """() => {
  const btns=[...document.querySelectorAll('button')];
  const cand=btns.find(b=>{
    const t=(b.getAttribute('aria-label')||'')+(b.getAttribute('title')||'')+(b.innerText||'');
    if(/480p|720p|1080p|6s|10s|15s|resolution|duration/i.test(t)) return false;
    return /attach|upload|image|图片|图象|上传|add|plus|\\+|file|附件|添/i.test(t);
  });
  if(cand){cand.click(); return 'button';}
  const fi=document.querySelector('input[type=file]');
  if(fi){fi.click(); return 'input';}
  return 'none';
}"""


def _restore_windows_clipboard_image_from_png(path: Path) -> None:
    """Put a PNG back on the Windows clipboard as CF_DIB (for repeated Ctrl+V paste)."""
    import io

    from PIL import Image

    try:
        import win32clipboard
        import win32con
    except ImportError as exc:
        raise RuntimeError("pywin32 required for clipboard image restore") from exc
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, "BMP")
    dib = out.getvalue()[14:]
    out.close()
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
    finally:
        win32clipboard.CloseClipboard()
    log(f"restored clipboard image from {path.name}")


def _clipboard_dib_to_temp_png() -> Path | None:
    """Read CF_DIB / CF_DIBV5 from Windows clipboard (Hermes model)."""
    import io
    import struct
    import tempfile

    try:
        import win32clipboard
        from PIL import Image
    except ImportError:
        return None
    CF_DIB, CF_DIBV5 = 8, 17
    win32clipboard.OpenClipboard()
    try:
        fmts = set()
        f = 0
        while True:
            f = win32clipboard.EnumClipboardFormats(f)
            if f == 0:
                break
            fmts.add(f)
        src = CF_DIBV5 if CF_DIBV5 in fmts else (CF_DIB if CF_DIB in fmts else None)
        if src is None:
            return None
        data = win32clipboard.GetClipboardData(src)
    finally:
        win32clipboard.CloseClipboard()
    try:
        bi_size = struct.unpack("<I", data[0:4])[0]
        bi_comp = struct.unpack("<I", data[16:20])[0]
        if bi_comp == 4:
            bmp = data[bi_size:]
        else:
            bi_clr = struct.unpack("<I", data[32:36])[0]
            bi_bit = struct.unpack("<H", data[14:16])[0]
            if bi_clr == 0 and bi_bit <= 8:
                bi_clr = 1 << bi_bit
            off = 14 + bi_size + bi_clr * 4
            bmp = b"BM" + struct.pack("<I", off + len(data) - bi_size) + b"\0\0\0\0" + struct.pack("<I", off) + data
        img = Image.open(io.BytesIO(bmp))
        path = Path(tempfile.gettempdir()) / f"grok_clip_{int(time.time() * 1000)}.png"
        img.convert("RGB").save(path, "PNG")
        return path
    except Exception as exc:
        log(f"clipboard DIB → png failed: {exc}")
        return None


def _clipboard_image_to_temp_png() -> Path | None:
    """Write clipboard bitmap or image file path to a temp PNG."""
    png = _clipboard_dib_to_temp_png()
    if png and png.is_file():
        return png
    import tempfile

    from PIL import Image, ImageGrab

    clip = ImageGrab.grabclipboard()
    if clip is None:
        return None
    path = Path(tempfile.gettempdir()) / f"grok_clip_{int(time.time() * 1000)}.png"
    try:
        if hasattr(clip, "save"):
            clip.save(path, "PNG")
            return path
        if isinstance(clip, list) and clip:
            src = Path(str(clip[0]).strip())
            if src.is_file():
                Image.open(src).convert("RGB").save(path, "PNG")
                return path
    except Exception as exc:
        log(f"clipboard → temp png failed: {exc}")
    return None


def _grok_resolve_cover_png() -> Path | None:
    """Cover for grv round 1: clipboard first, else itc-selected whole_story image."""
    png = _clipboard_image_to_temp_png()
    if png and png.is_file():
        log(f"Grok cover image from clipboard → {png}")
        return png
    try:
        from utility.telegram_session import selected_whole_story_image_path

        picked = (selected_whole_story_image_path() or "").strip()
        if picked and Path(picked).is_file():
            import tempfile

            from PIL import Image

            path = Path(tempfile.gettempdir()) / f"grok_cover_{int(time.time() * 1000)}.png"
            Image.open(picked).convert("RGB").save(path, "PNG")
            copy_image_file_to_clipboard(picked)
            log(f"Grok cover image from itc record → {picked}")
            return path
    except Exception as exc:
        log(f"Grok cover from itc/session failed: {exc}")
    return None


_GROK_COMPOSER_HAS_IMAGE_JS = """
() => {
  if (document.querySelector('button[aria-label="Remove image"]')) return true;
  if (document.querySelector('button[aria-label*="Remove"]')) return true;
  if (document.querySelector('img[src^="blob:https://grok.com/"]')) return true;
  if (document.querySelector('img[src^="blob:"]')) return true;
  const root = document.querySelector('[data-testid="chat-input"]');
  if (root && root.querySelector('.group\\/current-files img')) return true;
  if (root && root.querySelector('img')) return true;
  const n = document.querySelectorAll(
    'img[src^="blob:"], [data-testid*="attach"], [class*="attachment"], [class*="thumb"], [class*="preview"]'
  ).length;
  return n > 0;
}
"""


_GROK_INJECT_FILE_INPUT_JS = """
({ b64, mime, name }) => {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  const file = new File([arr], name || 'reference.png', { type: mime });
  const input = document.querySelector('input[type="file"][name="files"]');
  if (!input) return 'no-file-input';
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return 'file-input-events';
}
"""


_GROK_DROP_FILE_JS = """
({ b64, mime, name }) => {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  const file = new File([arr], name || 'reference.png', { type: mime });
  const dt = new DataTransfer();
  dt.items.add(file);
  const drop = document.querySelector('[data-testid="drop-container"]')
    || document.querySelector('[data-testid="drop-ui"]');
  if (!drop) return 'no-drop-target';
  for (const type of ['dragenter', 'dragover', 'drop']) {
    drop.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt }));
  }
  return 'drop-events';
}
"""


_GROK_ASPECT_916_JS = """
() => {
  const norm = (s) => (s || '').trim();
  const txt = (el) => norm(el.innerText || el.textContent);
  const aria = (el) => norm(el.getAttribute('aria-label') || el.getAttribute('title') || '');

  const btns = [...document.querySelectorAll('button, [role="button"]')];
  const isRatioPill = (b) => /^\\d+:\\d+$/.test(txt(b));
  const isAspectBtn = (b) => {
    const blob = (txt(b) + ' ' + aria(b)).toLowerCase();
    return isRatioPill(b)
      || /纵横比|aspect\\s*ratio|方比例/.test(blob);
  };

  let pill = btns.find((b) => txt(b) === '9:16');
  if (!pill) pill = btns.find(isAspectBtn);
  if (!pill) pill = btns.find(isRatioPill);
  if (!pill) return null;
  pill.click();

  const items = [...document.querySelectorAll(
    '[role="menuitem"], [role="option"], [role="menuitemradio"], button, div, span, li'
  )];
  for (const el of items) {
    const t = txt(el);
    if (/^9:16/.test(t)) {
      el.click();
      return t;
    }
  }
  return null;
}
"""


_GROK_READ_COMPOSER_TEXT_JS = """() => {
  function isOverlay(el) {
    const r = el.getBoundingClientRect();
    const t = (el.innerText || el.textContent || '');
    return /描述你想修改|describe what you want to change/i.test(t) && r.width < 320;
  }
  const chat = document.querySelector('[data-testid="chat-input"]');
  if (chat) {
    const el = chat.querySelector('.ProseMirror, [contenteditable="true"][role="textbox"], [contenteditable="true"]');
    if (el && !isOverlay(el)) return (el.innerText || el.textContent || '');
  }
  let best = null;
  let bestW = 0;
  for (const el of document.querySelectorAll('.ProseMirror[contenteditable="true"], [contenteditable="true"][role="textbox"]')) {
    if (isOverlay(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width > bestW) { bestW = r.width; best = el; }
  }
  return best ? (best.innerText || best.textContent || '') : '';
}"""


_GROK_READ_BOTTOM_COMPOSER_TEXT_JS = """() => {
  const vh = window.innerHeight;
  const minTop = vh * 0.60;
  const chat = document.querySelector('[data-testid="chat-input"]');
  if (chat && chat.getBoundingClientRect().top >= minTop) {
    const el = chat.querySelector('.ProseMirror, [contenteditable="true"][role="textbox"], [contenteditable="true"]');
    if (el) return (el.innerText || el.textContent || '');
  }
  for (const el of document.querySelectorAll('.ProseMirror[contenteditable="true"], [contenteditable="true"][role="textbox"]')) {
    const r = el.getBoundingClientRect();
    const t = (el.innerText || '');
    if (r.top >= minTop && r.width >= 200 && !/描述你想修改/i.test(t)) {
      return (el.innerText || el.textContent || '');
    }
  }
  return '';
}"""


_GROK_CLICK_IMAGE_MODE_JS = """() => {
  const btns = [...document.querySelectorAll('button')];
  const cand = btns.find((b) => {
    const t = (b.getAttribute('aria-label') || '') + (b.getAttribute('title') || '')
      + (b.innerText || '');
    if (/video|视频|480p|720p|1080p|6s|10s|15s|resolution|duration/i.test(t)) return false;
    const lab = (b.getAttribute('aria-label') || b.innerText || '').trim();
    return lab === '图片' || lab === 'Image' || /^image$/i.test(lab);
  });
  if (cand) { cand.click(); return cand.getAttribute('aria-label') || '图片'; }
  return null;
}"""


_GROK_FIND_VIDEO_MODE_BUTTON_JS = """() => {
  function btnMeta(btn, method) {
    const br = btn.getBoundingClientRect();
    return {
      method,
      x: br.left + br.width / 2,
      y: br.top + br.height / 2,
      aria: (btn.getAttribute('aria-label') || '').trim(),
      w: br.width,
      h: br.height,
    };
  }
  function isPlusBtn(b) {
    const t = ((b.getAttribute('aria-label') || '') + (b.innerText || '')).toLowerCase();
    return (b.innerText || '').trim() === '+' || /add|attach|upload|上传/.test(t);
  }
  function isImageModeBtn(b) {
    const t = ((b.getAttribute('aria-label') || '') + (b.getAttribute('title') || '')).toLowerCase();
    if (/video|motion|视频|摄像/.test(t)) return false;
    return t === 'image' || t === '图片' || /\\bimage\\b|图片/.test(t);
  }
  function isAspectPill(b) {
    const t = ((b.innerText || '') + (b.getAttribute('aria-label') || '')).trim();
    return /\\d+:\\d+|方比例|aspect|比例|竖屏|横屏/i.test(t);
  }
  function isVideoModeBtn(b) {
    const aria = ((b.getAttribute('aria-label') || '') + (b.getAttribute('title') || '')).toLowerCase();
    const testid = (b.getAttribute('data-testid') || '').toLowerCase();
    if (/video|motion|视频|摄像|camera/.test(aria) && !/720|480|1080|6s|10s|15s/.test(aria)) return true;
    return /video/.test(testid);
  }

  const input = document.querySelector('[data-testid="chat-input"]');
  if (!input) return null;
  const ir = input.getBoundingClientRect();
  let card = input;
  for (let up = 0; up < 12; up++) {
    card = card.parentElement;
    if (!card) break;
    const cr = card.getBoundingClientRect();
    if (cr.width < 260) continue;
    const toolbar = [...card.querySelectorAll('button, [role="button"]')]
      .filter((b) => {
        if (b.disabled) return false;
        const br = b.getBoundingClientRect();
        if (br.width < 18 || br.height < 18) return false;
        if (br.width > 72) return false;
        const inFooter = br.top >= ir.top + ir.height * 0.2 && br.bottom <= cr.bottom + 4;
        const inCardX = br.left >= cr.left + 2 && br.right <= cr.right + 2;
        return inFooter && inCardX;
      })
      .sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);

    for (const b of toolbar) {
      if (isVideoModeBtn(b)) return btnMeta(b, 'aria-video');
    }
    const modeIcons = toolbar.filter((b) => !isPlusBtn(b) && !isImageModeBtn(b) && !isAspectPill(b));
    if (modeIcons.length) return btnMeta(modeIcons[0], 'camera-icon');
    if (toolbar.length >= 3) return btnMeta(toolbar[2], 'toolbar-index-2');
  }
  return null;
}"""


_GROK_FIND_SUBMIT_BUTTON_JS = """() => {
  function btnMeta(btn, method) {
    const br = btn.getBoundingClientRect();
    return {
      method,
      x: br.left + br.width / 2,
      y: br.top + br.height / 2,
      aria: (btn.getAttribute('aria-label') || '').trim(),
    };
  }
  function isSubmitBtn(b, ir, cr) {
    const aria = ((b.getAttribute('aria-label') || '') + (b.getAttribute('title') || '')).toLowerCase();
    if (/submit|send|generate|生成|发送|start/.test(aria)) return true;
    if ((b.getAttribute('type') || '').toLowerCase() === 'submit') return true;
    const br = b.getBoundingClientRect();
    const round = Math.abs(br.width - br.height) < 16;
    const hasSvg = !!b.querySelector('svg');
    const farRight = br.right >= cr.right - 40;
    const inFooter = br.top >= ir.top + ir.height * 0.2 && br.bottom <= cr.bottom + 4;
    return inFooter && farRight && round && br.width >= 28 && hasSvg;
  }

  const input = document.querySelector('[data-testid="chat-input"]');
  if (!input) return null;
  const ir = input.getBoundingClientRect();
  const form = input.closest('form');
  if (form) {
    const submit = form.querySelector('button[type="submit"], input[type="submit"]');
    if (submit && !submit.disabled) return btnMeta(submit, 'form-submit');
  }
  let card = input;
  for (let up = 0; up < 12; up++) {
    card = card.parentElement;
    if (!card) break;
    const cr = card.getBoundingClientRect();
    if (cr.width < 260) continue;
    const band = [...card.querySelectorAll('button, [role="button"]')].filter((b) => !b.disabled);
    let best = null;
    let bestScore = -1;
    for (const b of band) {
      const br = b.getBoundingClientRect();
      let score = 0;
      if (isSubmitBtn(b, ir, cr)) score += 200;
      if (b.querySelector('svg')) score += 30;
      if (Math.abs(br.width - br.height) < 16) score += 25;
      score += br.right / 10;
      if (score > bestScore) { best = b; bestScore = score; }
    }
    if (best && bestScore >= 120) return btnMeta(best, 'composer-submit');
  }
  return null;
}"""


_GROK_CLICK_SUBMIT_TOOLBAR_JS = """() => {
  function clickMeta(btn, method) {
    btn.click();
    const br = btn.getBoundingClientRect();
    return {
      method,
      x: br.left + br.width / 2,
      y: br.top + br.height / 2,
      aria: (btn.getAttribute('aria-label') || '').trim(),
      title: (btn.getAttribute('title') || '').trim(),
      type: (btn.getAttribute('type') || '').trim(),
    };
  }
  function isSubmitBtn(b, ir) {
    const aria = ((b.getAttribute('aria-label') || '') + (b.getAttribute('title') || '')).toLowerCase();
    if (/submit|send|generate|生成|发送|start/.test(aria)) return true;
    if ((b.getAttribute('type') || '').toLowerCase() === 'submit') return true;
    const br = b.getBoundingClientRect();
    const round = Math.abs(br.width - br.height) < 14;
    const hasSvg = !!b.querySelector('svg');
    const cls = (b.className || '').toString().toLowerCase();
    const looksPrimary = /primary|blue|submit|bg-/.test(cls);
    const farRight = br.right >= ir.right - 32;
    return (round && br.width >= 28 && farRight && hasSvg)
      || (looksPrimary && hasSvg && farRight && br.width >= 24);
  }

  const input = document.querySelector('[data-testid="chat-input"]');
  if (!input) return null;
  const ir = input.getBoundingClientRect();
  const form = input.closest('form');
  if (form) {
    const submit = form.querySelector('button[type="submit"], input[type="submit"]');
    if (submit && !submit.disabled) return clickMeta(submit, 'form-submit');
  }

  for (const sel of [
    'button[aria-label="Submit"]',
    'button[aria-label="Send"]',
    'button[aria-label="Generate"]',
    'button[aria-label="生成"]',
    'button[aria-label="发送"]',
  ]) {
    const el = document.querySelector(sel);
    if (el && !el.disabled) return clickMeta(el, 'aria-submit');
  }

  let card = input;
  for (let up = 0; up < 12; up++) {
    card = card.parentElement;
    if (!card) break;
    const r = card.getBoundingClientRect();
    if (r.width < 280) continue;
    const band = [...card.querySelectorAll('button, [role="button"]')].filter((b) => {
      if (b.disabled) return false;
      const br = b.getBoundingClientRect();
      if (br.width < 22 || br.height < 22) return false;
      const belowInput = br.top >= ir.bottom - 40;
      const nearBottom = br.bottom >= r.bottom - 12;
      return belowInput && nearBottom;
    });
    let best = null;
    let bestScore = -1;
    for (const b of band) {
      const br = b.getBoundingClientRect();
      let score = 0;
      if (isSubmitBtn(b, ir)) score += 100;
      if (b.querySelector('svg')) score += 30;
      if (Math.abs(br.width - br.height) < 14) score += 25;
      score += br.right / 10;
      if (score > bestScore) { best = b; bestScore = score; }
    }
    if (best && bestScore >= 80) return clickMeta(best, 'blue-round-arrow');
  }
  return null;
}"""


_GROK_IS_VIDEO_MODE_JS = """() => {
  for (const b of document.querySelectorAll('button, [role="button"]')) {
    const t = ((b.getAttribute('aria-label') || '') + (b.innerText || '')).trim();
    if (/^720p$|^480p$|^10s$|^6s$|^15s$|10秒|6秒|15秒/i.test(t)) return true;
    const aria = ((b.getAttribute('aria-label') || '') + (b.getAttribute('title') || '')).toLowerCase();
    if (/video|motion|视频|摄像/.test(aria) && b.getAttribute('aria-pressed') === 'true') return true;
  }
  return false;
}"""


_GROK_COMPOSER_TOOLBAR_COUNT_JS = """() => {
  const input = document.querySelector('[data-testid="chat-input"]');
  if (!input) return 0;
  const ir = input.getBoundingClientRect();
  let card = input;
  for (let up = 0; up < 12; up++) {
    card = card.parentElement;
    if (!card) break;
    const r = card.getBoundingClientRect();
    if (r.width < 280) continue;
    const leftGroup = [...card.querySelectorAll('button, [role="button"]')].filter((b) => {
      const br = b.getBoundingClientRect();
      if (br.width < 18 || br.height < 18) return false;
      const belowInput = br.top >= ir.bottom - 44;
      const nearInputX = br.left >= ir.left - 72 && br.left <= ir.left + 260;
      return belowInput && nearInputX;
    });
    return leftGroup.length;
  }
  return 0;
}"""


_GROK_CLICK_CONVERT_TO_VIDEO_SIDEBAR_JS = """() => {
  const labels = [
    '制作视频', '转换为视频', 'Convert to video', 'Convert to Video', '转为视频', '转视频',
  ];
  for (const b of document.querySelectorAll('button, [role="button"]')) {
    const t = (b.innerText || b.textContent || '').trim();
    const aria = (b.getAttribute('aria-label') || '').trim();
    if (labels.some((lab) => t.includes(lab) || aria.includes(lab))) {
      b.click();
      const br = b.getBoundingClientRect();
      return {
        method: 'sidebar-convert-video',
        x: br.left + br.width / 2,
        y: br.top + br.height / 2,
        aria,
      };
    }
  }
  return null;
}"""


_GROK_CLICK_VIDEO_SETTINGS_JS = """() => {
  const names720 = ['720p', '720P', '720'];
  const names10 = ['10s', '10 s', '10sec', '10 sec', '10 seconds', '10秒'];
  const clicked = [];
  for (const b of document.querySelectorAll('button')) {
    const t = (b.getAttribute('aria-label') || b.innerText || '').trim();
    if (!clicked.includes('720') && names720.some((n) => t === n || t.includes(n))) {
      b.click();
      clicked.push('720');
    }
    if (!clicked.includes('10') && names10.some((n) => t === n || t.includes(n))) {
      b.click();
      clicked.push('10');
    }
  }
  return clicked;
}"""


_GROK_CLICK_GENERATE_JS = """() => {
  const labels = ['Submit', 'Send', '生成', 'Generate', 'Start'];
  for (const b of document.querySelectorAll('button')) {
    const lab = (b.getAttribute('aria-label') || '').trim();
    if (labels.some((x) => lab.toLowerCase() === x.toLowerCase())) {
      b.click();
      return lab;
    }
  }
  const input = document.querySelector('[data-testid="chat-input"]');
  if (!input) return null;
  let container = input.closest('form') || input.parentElement;
  for (let up = 0; up < 8 && container; up++) {
    const btns = [...container.querySelectorAll('button')].filter((b) => !b.disabled);
    for (const b of [...btns].reverse()) {
      const aria = (b.getAttribute('aria-label') || '').trim();
      if (/submit|send|arrow|生成/i.test(aria)) {
        b.click();
        return aria || 'submit';
      }
      const r = b.getBoundingClientRect();
      if (r.width >= 28 && r.width <= 64 && Math.abs(r.width - r.height) < 10) {
        if (b.querySelector('svg')) {
          b.click();
          return 'round-submit-arrow';
        }
      }
    }
    container = container.parentElement;
  }
  const root = input.closest('form') || input.parentElement;
  if (root) {
    const btns = [...root.querySelectorAll('button')].filter((b) => !b.disabled);
    if (btns.length) {
      btns[btns.length - 1].click();
      return 'last-toolbar-btn';
    }
  }
  return null;
}"""


_GROK_REPLACE_PROMPT_JS = """(text) => {
  function isOverlay(el) {
    const r = el.getBoundingClientRect();
    const t = (el.innerText || el.textContent || '');
    return /描述你想修改|describe what you want to change/i.test(t) && r.width < 320;
  }
  const chat = document.querySelector('[data-testid="chat-input"]');
  let el = null;
  if (chat) {
    el = chat.querySelector('.ProseMirror, [contenteditable="true"][role="textbox"], [contenteditable="true"]');
    if (el && isOverlay(el)) el = null;
  }
  if (!el) {
    let best = null;
    let bestW = 0;
    for (const cand of document.querySelectorAll('.ProseMirror[contenteditable="true"], [contenteditable="true"][role="textbox"]')) {
      if (isOverlay(cand)) continue;
      const r = cand.getBoundingClientRect();
      if (r.width > bestW) { bestW = r.width; best = cand; }
    }
    el = best;
  }
  if (!el) return 'no-editor';
  el.focus();
  el.click();
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((n) => { n.textContent = ''; });
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand('insertText', false, text);
  return (el.innerText || el.textContent || '').slice(0, 120);
}"""


_GROK_REPLACE_BOTTOM_PROMPT_JS = """(text) => {
  const vh = window.innerHeight;
  const minTop = vh * 0.60;
  const chat = document.querySelector('[data-testid="chat-input"]');
  let el = null;
  if (chat && chat.getBoundingClientRect().top >= minTop) {
    el = chat.querySelector('.ProseMirror, [contenteditable="true"][role="textbox"], [contenteditable="true"]');
  }
  if (!el) {
    for (const cand of document.querySelectorAll('.ProseMirror[contenteditable="true"], [contenteditable="true"][role="textbox"]')) {
      const r = cand.getBoundingClientRect();
      const t = (cand.innerText || '');
      if (r.top >= minTop && r.width >= 200 && !/描述你想修改/i.test(t)) { el = cand; break; }
    }
  }
  if (!el) return 'no-editor';
  el.focus();
  el.click();
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((n) => { n.textContent = ''; });
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand('insertText', false, text);
  return (el.innerText || el.textContent || '').slice(0, 120);
}"""


_GROK_CLICK_SUBMIT_NEAR_INPUT_JS = """() => {
  const input = document.querySelector('[data-testid="chat-input"]');
  if (!input) return null;
  let node = input;
  for (let up = 0; up < 12; up++) {
    node = node.parentElement;
    if (!node) break;
    const rect = node.getBoundingClientRect();
    const btns = [...node.querySelectorAll('button')].filter((b) => !b.disabled);
    let best = null;
    let bestScore = -1;
    for (const b of btns) {
      const r = b.getBoundingClientRect();
      if (r.width < 24 || r.height < 24) continue;
      const svg = b.querySelector('svg');
      const aria = (b.getAttribute('aria-label') || '').toLowerCase();
      let score = 0;
      if (/submit|send|生成|generate/.test(aria)) score += 100;
      if (svg) score += 50;
      if (Math.abs(r.width - r.height) < 12) score += 30;
      const right = r.right >= rect.right - 80;
      const bottom = r.bottom >= rect.bottom - 80;
      if (right && bottom) score += 40;
      if (score > bestScore) { bestScore = score; best = b; }
    }
    if (best && bestScore >= 50) {
      best.click();
      return best.getAttribute('aria-label') || 'submit-near-input';
    }
  }
  return null;
}"""


_GROK_IS_GENERATING_JS = """() => {
  const t = document.body.innerText || '';
  return /generating|正在生成|生成中|creating image|creating video/i.test(t);
}"""


_GROK_HAS_OUTPUT_IMAGE_JS = """() => {
  const composer = document.querySelector('[data-testid="chat-input"]');
  const imgs = [...document.querySelectorAll('img')].filter((img) => {
    if (!img.src) return false;
    if (composer && composer.contains(img)) return false;
    const r = img.getBoundingClientRect();
    return r.width > 120 && r.height > 120;
  });
  return imgs.length > 0;
}"""


_GROK_HAS_OUTPUT_VIDEO_JS = """() => {
  const composer = document.querySelector('[data-testid="chat-input"]');
  const videos = [...document.querySelectorAll('video')].filter((v) => {
    if (composer && composer.contains(v)) return false;
    const r = v.getBoundingClientRect();
    return r.width > 120 && r.height > 120;
  });
  return videos.length > 0;
}"""

_GROK_OUTPUT_VIDEO_SRC_JS = """() => {
  const composer = document.querySelector('[data-testid="chat-input"]');
  const videos = [...document.querySelectorAll('video')].filter((v) => {
    if (composer && composer.contains(v)) return false;
    const r = v.getBoundingClientRect();
    return r.width > 120 && r.height > 120;
  });
  if (!videos.length) return {ok: false, reason: 'no output video'};
  const v = videos[0];
  const src = v.src || (v.querySelector('source') && v.querySelector('source').src);
  if (!src) return {ok: false, reason: 'no video src'};
  return {ok: true, src};
}"""


def _grok_paste_prompt_cdp(page: Page, prompt: str, *, bottom_bar: bool = False) -> None:
    """Replace composer text. ``bottom_bar=True`` prefers post-image bottom bar, else main."""
    text = (prompt or "").strip()
    if not text:
        raise RuntimeError("Grok composer: empty prompt")
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    read_js = _GROK_READ_COMPOSER_TEXT_JS
    snippet = None
    if bottom_bar:
        snippet = page.evaluate(_GROK_REPLACE_BOTTOM_PROMPT_JS, text)
        if snippet and snippet != "no-editor":
            read_js = _GROK_READ_BOTTOM_COMPOSER_TEXT_JS
        else:
            log("Grok CDP: bottom bar not found for video prompt; fallback main composer")
            snippet = page.evaluate(_GROK_REPLACE_PROMPT_JS, text)
    else:
        snippet = page.evaluate(_GROK_REPLACE_PROMPT_JS, text)
    if not snippet or snippet == "no-editor":
        where = "composer" if bottom_bar else "main composer"
        raise RuntimeError(f"Grok {where} editor not found for prompt replace")
    time.sleep(0.4)
    actual = str(page.evaluate(read_js) or "")
    _paste_text_verified(text, actual, field_label="Grok composer")
    log(
        f"Grok CDP: prompt set ({len(text)} chars)"
        f"{' [bottom bar]' if bottom_bar and read_js == _GROK_READ_BOTTOM_COMPOSER_TEXT_JS else ' [main composer]'}"
    )


def _grok_scroll_composer_into_view(page: Page) -> None:
    page.evaluate(
        """() => {
      const chat = document.querySelector('[data-testid="chat-input"]');
      if (chat) chat.scrollIntoView({ block: 'center', inline: 'nearest' });
    }"""
    )
    time.sleep(0.2)


def _grok_click_main_composer_cdp(page: Page) -> dict | None:
    """Click the main chat-input composer (top or bottom — not in-image overlay)."""
    pt = page.evaluate(_GROK_FIND_MAIN_COMPOSER_CLICK_JS)
    if isinstance(pt, dict) and pt.get("x") and pt.get("y"):
        _grok_mouse_click_point(
            page, float(pt["x"]), float(pt["y"]), label="main-composer"
        )
        page.evaluate(_GROK_FOCUS_COMPOSER_JS)
        log(
            f"Grok CDP: main composer {pt.get('method')!r} "
            f"top={float(pt.get('top') or 0):.0f} w={float(pt.get('width') or 0):.0f}"
        )
        return pt
    try:
        _grok_focus_editor(page)
        return {"method": "playwright-editor"}
    except Exception as exc:
        log(f"Grok CDP: main composer click failed: {exc}")
        return None


def _grok_click_bottom_prompt_bar_cdp(page: Page, *, required: bool = False) -> dict | None:
    """Click bottom Visual_Style bar after deep image. Returns None if not found."""
    pt = page.evaluate(_GROK_FIND_BOTTOM_PROMPT_BAR_JS)
    if not isinstance(pt, dict) or not pt.get("x") or not pt.get("y"):
        if required:
            raise RuntimeError(
                "找不到底部 Visual_Style 提示词栏。"
                "应点击主图正下方、蓝 Submit 左侧的输入框。"
            )
        return None
    _grok_mouse_click_point(
        page, float(pt["x"]), float(pt["y"]), label="bottom-prompt-bar"
    )
    page.evaluate(_GROK_FOCUS_COMPOSER_JS)
    log(
        f"Grok CDP: bottom prompt bar {pt.get('method')!r} "
        f"top={float(pt.get('top') or 0):.0f} w={float(pt.get('width') or 0):.0f} "
        f"text={str(pt.get('text') or '')[:60]!r}"
    )
    return pt


def _grok_focus_composer_toolbar_once_cdp(page: Page, *, deep_image: bool = False) -> None:
    """One click inside the prompt text area — keeps toolbar open, avoids image clicks."""
    _grok_scroll_composer_into_view(page)
    pt = None
    if deep_image:
        pt = page.evaluate(_GROK_FIND_BOTTOM_PROMPT_BAR_JS)
    if not isinstance(pt, dict) or not pt.get("x"):
        pt = page.evaluate(_GROK_FIND_MAIN_COMPOSER_CLICK_JS)
    if isinstance(pt, dict) and pt.get("x") and pt.get("y"):
        _grok_mouse_click_point(
            page, float(pt["x"]), float(pt["y"]), label="composer-focus-once"
        )
    time.sleep(0.25)


def _grok_awaken_composer_toolbar_cdp(page: Page, *, deep_image: bool = False) -> None:
    """Focus composer so +/image/video toolbar is active."""
    _grok_focus_composer_toolbar_once_cdp(page, deep_image=deep_image)
    count = int(page.evaluate(_GROK_COMPOSER_TOOLBAR_COUNT_JS) or 0)
    log(f"Grok CDP: composer toolbar icons={count}")


def _grok_mouse_click_point(page: Page, x: float, y: float, *, label: str) -> None:
    page.mouse.move(x, y)
    time.sleep(0.05)
    page.mouse.click(x, y)
    log(f"Grok CDP: mouse {label} at ({x:.0f},{y:.0f})")
    time.sleep(0.3)


def _grok_click_js_target(page: Page, pt: object, *, kind: str) -> bool:
    if not isinstance(pt, dict):
        return False
    x, y = pt.get("x"), pt.get("y")
    if not x or not y:
        return False
    _grok_mouse_click_point(page, float(x), float(y), label=kind)
    log(
        f"Grok CDP: {kind} via {pt.get('method')!r} "
        f"aria={pt.get('aria')!r} title={pt.get('title')!r} testid={pt.get('testid')!r}"
    )
    return True


def _grok_viewport_click(page: Page, rx: float, ry: float, *, label: str) -> None:
    pt = page.evaluate(
        "([rx, ry]) => ({ x: window.innerWidth * rx, y: window.innerHeight * ry })",
        [rx, ry],
    )
    _grok_mouse_click_point(page, float(pt["x"]), float(pt["y"]), label=label)


def _grok_click_image_mode_cdp(page: Page) -> bool:
    label = page.evaluate(_GROK_CLICK_IMAGE_MODE_JS)
    if not label:
        log("Grok CDP: 图片 mode button not found; continuing")
        return False
    log(f"Grok CDP: clicked image mode {label!r}")
    time.sleep(0.25)
    return True


def _grok_click_video_mode_cdp(page: Page) -> bool:
    _grok_focus_composer_toolbar_once_cdp(page, deep_image=True)
    vid = page.evaluate(_GROK_FIND_VIDEO_MODE_BUTTON_JS)
    if not (isinstance(vid, dict) and vid.get("x") and vid.get("y")):
        log(f"Grok CDP: video mode button not found in composer toolbar: {vid!r}")
        return False
    _grok_mouse_click_point(
        page, float(vid["x"]), float(vid["y"]), label="video-mode-icon"
    )
    log(
        f"Grok CDP: video mode icon via {vid.get('method')!r} "
        f"at ({vid['x']:.0f},{vid['y']:.0f}) aria={vid.get('aria')!r}"
    )
    time.sleep(0.4)
    if page.evaluate(_GROK_IS_VIDEO_MODE_JS):
        log("Grok CDP: video mode confirmed (720p/10s visible)")
    else:
        log("Grok CDP: video icon clicked; toolbar kept open")
    return True


def _grok_click_video_settings_cdp(page: Page) -> None:
    try:
        picked = page.evaluate(_GROK_CLICK_VIDEO_SETTINGS_JS)
        if picked:
            log(f"Grok CDP: video settings {picked!r}")
    except Exception as exc:
        log(f"Grok CDP: video settings skipped: {exc}")
    time.sleep(0.15)


def _grok_click_generate_cdp(page: Page, *, deep_image: bool = False) -> None:
    _grok_scroll_composer_into_view(page)
    if deep_image:
        _grok_focus_composer_toolbar_once_cdp(page, deep_image=True)
    else:
        _grok_awaken_composer_toolbar_cdp(page, deep_image=False)
    time.sleep(0.15)
    if deep_image:
        pt = page.evaluate(_GROK_FIND_SUBMIT_BUTTON_JS)
        if isinstance(pt, dict) and pt.get("x") and pt.get("y"):
            _grok_mouse_click_point(
                page, float(pt["x"]), float(pt["y"]), label="submit-icon"
            )
            log(
                f"Grok CDP: submit via {pt.get('method')!r} "
                f"at ({pt['x']:.0f},{pt['y']:.0f}) aria={pt.get('aria')!r}"
            )
            time.sleep(0.5)
            if page.evaluate(_GROK_IS_GENERATING_JS):
                return
    pt = page.evaluate(_GROK_CLICK_SUBMIT_TOOLBAR_JS)
    if _grok_click_js_target(page, pt, kind="submit"):
        time.sleep(0.5)
        if page.evaluate(_GROK_IS_GENERATING_JS):
            return
        log("Grok CDP: submit click sent but generating not detected; retry")
    if not deep_image:
        _grok_viewport_click(page, GROK_GENERATE_X, GROK_TOOLBAR_Y, label="submit-ratio")
        time.sleep(0.5)
        if page.evaluate(_GROK_IS_GENERATING_JS):
            return
    clicked = page.evaluate(_GROK_CLICK_SUBMIT_NEAR_INPUT_JS)
    if clicked:
        log(f"Grok CDP: clicked Submit near input ({clicked!r})")
        return
    for sel in (
        'button[aria-label="Submit"]',
        'button[aria-label="Send"]',
        'button[aria-label="生成"]',
    ):
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click(timeout=5000, force=True)
            log(f"Grok CDP: clicked generate via {sel}")
            return
    label = page.evaluate(_GROK_CLICK_GENERATE_JS)
    if label:
        log(f"Grok CDP: clicked generate {label!r}")
        return
    raise RuntimeError("Grok Submit 按钮未找到（右下角蓝色上箭头）")


def _grok_wait_image_ready_cdp(
    page: Page, timeout_s: float = GROK_IMAGE_READY_TIMEOUT_S
) -> None:
    started = time.monotonic()
    log(f"waiting for Grok image via CDP (up to {int(timeout_s)}s)…")
    while time.monotonic() - started < timeout_s:
        elapsed = time.monotonic() - started
        try:
            generating = bool(page.evaluate(_GROK_IS_GENERATING_JS))
            has_output = bool(page.evaluate(_GROK_HAS_OUTPUT_IMAGE_JS))
        except Exception as exc:
            log(f"Grok CDP image wait probe failed: {exc}")
            generating = False
            has_output = False
        log(
            f"grok image CDP wait {elapsed:.0f}s "
            f"generating={generating} output={has_output}"
        )
        if (
            elapsed >= GROK_IMAGE_READY_MIN_S
            and not generating
            and has_output
        ):
            time.sleep(2.0)
            try:
                still_gen = bool(page.evaluate(_GROK_IS_GENERATING_JS))
                still_out = bool(page.evaluate(_GROK_HAS_OUTPUT_IMAGE_JS))
            except Exception:
                still_gen = True
                still_out = False
            if not still_gen and still_out:
                log("Grok image looks ready (CDP)")
                return
        time.sleep(4.0)
    raise RuntimeError(
        f"等了 {int(timeout_s // 60)} 分钟 Grok image 仍在生成。请看该标签是否卡住。"
    )


def _grok_wait_video_ready_cdp(
    page: Page, timeout_s: float = GROK_VIDEO_READY_TIMEOUT_S
) -> None:
    started = time.monotonic()
    log(f"waiting for Grok video via CDP (up to {int(timeout_s)}s)…")
    while time.monotonic() - started < timeout_s:
        elapsed = time.monotonic() - started
        try:
            generating = bool(page.evaluate(_GROK_IS_GENERATING_JS))
            has_output = bool(page.evaluate(_GROK_HAS_OUTPUT_VIDEO_JS))
        except Exception as exc:
            log(f"Grok CDP video wait probe failed: {exc}")
            generating = False
            has_output = False
        log(
            f"grok video CDP wait {elapsed:.0f}s "
            f"generating={generating} output={has_output}"
        )
        if (
            elapsed >= GROK_VIDEO_READY_MIN_S
            and not generating
            and has_output
        ):
            time.sleep(2.0)
            try:
                still_gen = bool(page.evaluate(_GROK_IS_GENERATING_JS))
                still_out = bool(page.evaluate(_GROK_HAS_OUTPUT_VIDEO_JS))
            except Exception:
                still_gen = True
                still_out = False
            if not still_gen and still_out:
                log("Grok video looks ready (CDP)")
                return
        time.sleep(4.0)
    raise RuntimeError(
        f"等了 {int(timeout_s // 60)} 分钟 Grok video 仍在生成。请看该标签是否卡住。"
    )


def _grok_composer_has_image_page(page: Page) -> bool:
    try:
        return bool(page.evaluate(_GROK_COMPOSER_HAS_IMAGE_JS))
    except Exception as exc:
        log(f"Grok composer image probe failed: {exc}")
        return False


def _grok_wait_image_attached(page: Page, timeout_s: float = GROK_IMAGE_ATTACH_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _grok_composer_has_image_page(page):
            return True
        time.sleep(0.35)
    return False


def _grok_focus_editor(page: Page):
    for sel in (GROK_EDITOR_SEL, GROK_EDITOR_ALT_SEL):
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.wait_for(state="visible", timeout=12_000)
            loc.first.click(timeout=8000)
            return loc.first
    raise RuntimeError("Grok ProseMirror editor not found")


def _grok_paste_cover_image_cdp(page: Page, cover_png: Path) -> bool:
    """Paste cover via Ctrl+V (Hermes), file-input fallback if needed."""
    path_str = str(cover_png)
    page.bring_to_front()
    try:
        page.locator('[data-testid="chat-input"]').wait_for(
            state="visible", timeout=25_000
        )
    except Exception as exc:
        log(f"Grok CDP: chat-input wait failed: {exc}")
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(2.0)

    _restore_windows_clipboard_image_from_png(cover_png)
    for attempt in range(1, 4):
        try:
            editor = page.locator(GROK_EDITOR_SEL).first
            if editor.count() > 0:
                editor.click(timeout=8000)
            else:
                page.evaluate(_GROK_FOCUS_COMPOSER_JS)
            time.sleep(0.4)
            page.keyboard.press("Control+V")
            log(f"Grok CDP: Control+V cover attempt {attempt}")
            if _grok_wait_image_attached(page, 10.0):
                return True
            time.sleep(1.0)
        except Exception as exc:
            log(f"Grok CDP cover Ctrl+V attempt {attempt}: {exc}")

    try:
        file_input = page.locator(GROK_FILE_INPUT_SEL)
        if file_input.count() > 0:
            file_input.set_input_files(path_str)
            log("Grok CDP: cover via set_input_files fallback")
            if _grok_wait_image_attached(page, 15.0):
                return True
    except Exception as exc:
        log(f"Grok CDP cover file-input fallback: {exc}")

    try:
        with page.expect_file_chooser(timeout=10_000) as fc_info:
            page.evaluate(_GROK_OPEN_FILE_CHOOSER_JS)
        fc_info.value.set_files(path_str)
        log("Grok CDP: cover via file chooser fallback")
        if _grok_wait_image_attached(page, 15.0):
            return True
    except Exception as exc:
        log(f"Grok CDP cover file chooser fallback: {exc}")

    return False


def _grok_paste_image_clipboard_cdp(page: Page) -> bool:
    """Legacy wrapper — requires cover_png on caller."""
    return False


def _grok_paste_image_cdp(page: Page) -> bool:
    return _grok_paste_image_clipboard_cdp(page)


def _grok_set_aspect_916_cdp(page: Page) -> bool:
    for attempt in range(1, 4):
        try:
            label = page.evaluate(_GROK_ASPECT_916_JS)
            if label:
                log(f"Grok CDP aspect 9:16 selected: {label!r}")
                time.sleep(0.35)
                return True
            log(f"Grok CDP aspect 9:16 attempt {attempt}: menu item not found")
            time.sleep(0.45)
        except Exception as exc:
            log(f"Grok CDP aspect attempt {attempt}: {exc}")
            time.sleep(0.45)
    log("Grok CDP aspect: failed to select 9:16")
    return False


def _grok_ensure_image_mode_and_aspect_916_cdp(page: Page) -> bool:
    """图片模式 + 9:16（贴封面后、点生成前都要设）。"""
    _grok_click_image_mode_cdp(page)
    time.sleep(0.3)
    return _grok_set_aspect_916_cdp(page)


def _grok_prepare_tab_cdp(page: Page, *, paste_image: bool) -> bool:
    pasted = False
    if paste_image:
        cover = _grok_resolve_cover_png()
        if cover:
            pasted = _grok_paste_cover_image_cdp(page, cover)
            try:
                cover.unlink(missing_ok=True)
            except OSError:
                pass
    _grok_ensure_image_mode_and_aspect_916_cdp(page)
    return pasted or not paste_image


def _grok_generate_image_on_tab_cdp(page: Page) -> None:
    """Switch to 图片 mode, set 9:16, click Submit, wait until image ready."""
    _grok_ensure_image_mode_and_aspect_916_cdp(page)
    time.sleep(0.2)
    _grok_click_generate_cdp(page, deep_image=False)
    time.sleep(0.6)
    _grok_wait_image_ready_cdp(page)


def _grok_generate_video_on_tab_cdp(page: Page, prompt: str) -> None:
    """Paste video prompt, Video mode icon, Submit, wait."""
    _grok_paste_prompt_cdp(page, prompt, bottom_bar=True)
    if not _grok_click_video_mode_cdp(page):
        raise RuntimeError(
            "Grok 视频模式未切换成功。请先点击输入框展开工具栏，"
            "再点 + 旁摄像机 icon（或右侧「转换为视频」）。"
        )
    time.sleep(0.3)
    _grok_click_video_settings_cdp(page)
    time.sleep(0.2)
    _grok_click_generate_cdp(page, deep_image=True)
    time.sleep(0.6)
    _grok_wait_video_ready_cdp(page)


def _grok_prepare_all_tabs_cdp(
    n: int,
    *,
    cover_png: Path | None = None,
    port: int | None = None,
    fresh_tabs: bool = False,
    scene_prompts: list[tuple[str, str]] | None = None,
    auto_generate: bool = False,
    video_prompts: list[tuple[str, str]] | None = None,
    auto_generate_video: bool = False,
    auto_download_video: bool = False,
) -> tuple[int, int, list[dict]]:
    """Prepare N Grok Imagine tabs.

    Returns ``(image_paste_ok_count, prompt_paste_ok_count, downloaded_clips)``.
    When ``auto_download_video``, each tab is saved right after Round 3 video gen.
    """
    port = int(port or _grok_cdp_port())
    if not cdp_ready(port):
        raise RuntimeError(f"Grok CDP not listening on {port}")
    pasted = 0
    prompts_done = 0
    downloads: list[dict] = []
    download_stamp = ""
    download_cookies: dict[str, str] = {}
    if cover_png is None or not cover_png.is_file():
        cover_png = _grok_resolve_cover_png()
    paste_image = cover_png is not None and cover_png.is_file()
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            if not browser.contexts:
                raise RuntimeError("Grok CDP connected but no browser context")
            ctx = browser.contexts[0]
            pages: list[Page] = []
            if fresh_tabs:
                # Hermes model: open tab → wait → paste cover → 9:16 (one tab at a time)
                log(f"Grok round 1: open + paste cover on {n} tab(s)")
                for i in range(n):
                    tab_no = i + 1
                    pg = ctx.new_page()
                    pg.goto(GROK_IMAGINE_URL, wait_until="domcontentloaded", timeout=60_000)
                    pages.append(pg)
                    log(f"Grok round 1 tab {tab_no}/{n} opened {pg.url}")
                    if paste_image and cover_png:
                        if _grok_paste_cover_image_cdp(pg, cover_png):
                            pasted += 1
                            log(f"Grok tab {tab_no}: cover pasted")
                        else:
                            raise RuntimeError(
                                f"第一轮：标签 {tab_no} 封面图粘贴失败。"
                            )
                        _grok_ensure_image_mode_and_aspect_916_cdp(pg)
                        time.sleep(0.25)
                log(f"Grok round 1 done: {pasted}/{n} tabs have cover")
            else:
                pages = _grok_imagine_pages(ctx)
                need = max(0, n - len(pages))
                for _ in range(need):
                    pg = ctx.new_page()
                    pg.goto(GROK_IMAGINE_URL, wait_until="domcontentloaded", timeout=60_000)
                    time.sleep(0.6)
                pages = _grok_imagine_pages(ctx)
                if len(pages) < n:
                    raise RuntimeError(
                        f"Grok CDP found {len(pages)} imagine tab(s), need {n}. "
                        "请重发 grv 1。"
                    )
                if paste_image and cover_png:
                    log(f"Grok round 1: paste cover to {n} existing tab(s)")
                    for i in range(n):
                        tab_no = i + 1
                        page = pages[i]
                        log(f"Grok round 1 tab {tab_no}/{n}")
                        if _grok_paste_cover_image_cdp(page, cover_png):
                            pasted += 1
                        else:
                            raise RuntimeError(
                                f"第一轮：标签 {tab_no} 封面图粘贴失败。"
                            )
                        _grok_ensure_image_mode_and_aspect_916_cdp(page)
                        time.sleep(0.25)

            # ── Round 2: scene prompt + Submit per tab ──
            if scene_prompts:
                if auto_download_video:
                    download_stamp = _grok_scene_video_download_stamp()
                    download_cookies = _grok_cdp_cookies_for_download(ctx)
                    if not download_cookies:
                        log("grv download: warning — no grok.com cookies; download may 403")
                log(f"Grok round 2: scene prompts + Submit on {n} tab(s)")
                for i in range(n):
                    tab_no = i + 1
                    page = pages[i]
                    if i >= len(scene_prompts):
                        break
                    lbl, prompt = scene_prompts[i]
                    log(f"Grok round 2 tab {tab_no}/{n} ({lbl})")
                    page.bring_to_front()
                    page.wait_for_load_state("domcontentloaded", timeout=20_000)
                    time.sleep(0.8)
                    _grok_paste_prompt_cdp(page, prompt)
                    prompts_done += 1
                    log(f"Grok tab {tab_no}: scene prompt set")
                    if auto_generate:
                        log(f"Grok tab {tab_no}: clicking Submit…")
                        _grok_generate_image_on_tab_cdp(page)
                        log(f"Grok tab {tab_no}: image generation complete")
                        if auto_generate_video and video_prompts and i < len(video_prompts):
                            vlbl, vprompt = video_prompts[i]
                            log(
                                f"Grok round 3 tab {tab_no}/{n} ({vlbl}) "
                                "→ Video mode + Submit"
                            )
                            _grok_generate_video_on_tab_cdp(page, vprompt)
                            log(f"Grok tab {tab_no}: video generation complete")
                            if auto_download_video:
                                log(
                                    f"Grok round 4 tab {tab_no}/{n}: download video "
                                    f"({vlbl})"
                                )
                                item = _grok_download_tab_video_cdp(
                                    page,
                                    tab_no,
                                    download_cookies,
                                    stamp=download_stamp,
                                    wait_ready=False,
                                    log_prefix="grv",
                                )
                                downloads.append(item)
                                log(f"Grok tab {tab_no}: video downloaded")
    finally:
        if cover_png is not None:
            try:
                cover_png.unlink(missing_ok=True)
            except OSError:
                pass
    return pasted, prompts_done, downloads


def _grok_run_on_tab(tab_index: int, fn, *, port: int | None = None) -> Any:
    port = int(port or _grok_cdp_port())
    if not cdp_ready(port):
        raise RuntimeError(f"Grok CDP not listening on {port}")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        if not browser.contexts:
            raise RuntimeError("Grok CDP connected but no browser context")
        ctx = browser.contexts[0]
        pages = _grok_imagine_pages(ctx)
        if tab_index < 1 or tab_index > len(pages):
            raise RuntimeError(
                f"Grok CDP tab {tab_index} not found ({len(pages)} imagine page(s))"
            )
        page = pages[tab_index - 1]
        page.bring_to_front()
        time.sleep(0.35)
        return fn(page)


def _click_uia_ctrl(ctrl) -> bool:
    box = _ctrl_box(ctrl)
    if not box:
        return False
    left, top, right, bottom = box

    class _Rect:
        pass

    rect = _Rect()
    rect.left = left
    rect.top = top
    rect.right = right
    rect.bottom = bottom
    rect.width = lambda: right - left
    rect.height = lambda: bottom - top
    return _click_rect_center(rect)


def _find_grok_chrome_hwnd() -> Optional[int]:
    from cli.win_gui_tasks import enum_windows_safe

    for sub in ("Grok", "grok.com", "Imagine"):
        hits = enum_windows_safe(sub=sub)
        if hits:
            return hits[-1][0]
    return None


def _grok_recorded_tab_count() -> int:
    from utility.telegram_session import load_story_scene_prompt_choice

    n = int(load_story_scene_prompt_choice().get("tabs") or 0)
    return max(0, n)


def _focus_grok_window() -> int:
    from cli.win_gui_tasks import set_foreground, win32con, win32gui

    hwnd = _find_grok_chrome_hwnd()
    if not hwnd:
        raise RuntimeError(
            "找不到 Grok Imagine 窗口。请先发 grv 打开标签。"
        )
    if win32gui is not None and win32con is not None:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        except Exception:
            pass
    set_foreground(hwnd)
    time.sleep(0.25)
    return hwnd


def _focus_grok_tab(hwnd: int, index: int) -> None:
    import pyautogui
    from cli.win_gui_tasks import set_foreground

    pyautogui.FAILSAFE = False
    set_foreground(hwnd)
    time.sleep(0.15)
    _force_english_ime()
    pyautogui.hotkey("ctrl", str(max(1, min(index, 8))))
    time.sleep(0.65)


def _click_grok_composer(hwnd: int) -> None:
    _click_grok_prompt_input(hwnd)


def _click_grok_prompt_input(hwnd: int) -> None:
    """Focus the central prompt box (输入或粘贴图像 / 输入你的想象)."""
    for name in (
        "输入或粘贴图像",
        "输入你的想象",
        "Ask Grok",
        "What do you want",
        "Message",
    ):
        if _click_named(
            hwnd,
            name,
            ["EditControl", "TextControl", "ComboBoxControl"],
            search_depth=14,
        ):
            return
    log("ratio-click Grok prompt input")
    _click_ratio(hwnd, GROK_PROMPT_X, GROK_PROMPT_Y, pause=0.3)


def _grok_composer_has_image_hwnd(hwnd: int) -> bool:
    for name in ("Remove image", "Remove", "移除图片", "移除"):
        if _named_exists(
            hwnd, name, ["ButtonControl"], search_depth=16, timeout_s=0.15
        ):
            return True
    return False


def _paste_grok_via_upload_dialog(hwnd: int) -> bool:
    """Physical 上传 → file path, or prompt Ctrl+V (no CDP)."""
    import pyautogui
    from cli.win_gui_tasks import set_foreground

    temp = _clipboard_image_to_temp_png()
    if temp is None:
        return False
    pyautogui.FAILSAFE = False
    set_foreground(hwnd)
    time.sleep(0.35)
    _force_english_ime()
    path_str = str(temp)

    if _click_named(hwnd, "上传", ["ButtonControl"], search_depth=16):
        time.sleep(1.0)
        pyautogui.hotkey("alt", "d")
        time.sleep(0.25)
        pyautogui.write(path_str, interval=0.012)
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(1.2)
        if _grok_composer_has_image_hwnd(hwnd):
            log("hwnd paste ok via 上传 + file path")
            return True

    log("hwnd paste: click prompt + Ctrl+V")
    _click_grok_prompt_input(hwnd)
    time.sleep(0.35)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1.2)
    if _grok_composer_has_image_hwnd(hwnd):
        log("hwnd paste ok via Ctrl+V")
        return True
    return False


def _prepare_all_grok_via_hwnd(n: int, *, paste_image: bool) -> int:
    hwnd = _focus_grok_window()
    pasted = 0
    for i in range(1, n + 1):
        log(f"hwnd prepare Grok tab {i}/{n}")
        _focus_grok_tab(hwnd, i)
        _wait_grok_composer_ready(hwnd)
        if paste_image and _paste_grok_via_upload_dialog(hwnd):
            pasted += 1
        _click_grok_image_mode(hwnd)
        time.sleep(0.2)
        _click_grok_aspect_ratio_916(hwnd)
        time.sleep(0.25)
    return pasted


def _paste_image_into_grok_composer(hwnd: int, tab_index: int = 1) -> bool:
    """Paste clipboard bitmap into the Grok Imagine prompt area."""
    if not _clipboard_has_image():
        return False
    if cdp_ready(_grok_cdp_port()):
        try:
            return bool(
                _grok_run_on_tab(
                    tab_index,
                    lambda page: _grok_paste_image_cdp(page),
                )
            )
        except Exception as exc:
            log(f"Grok CDP paste error tab {tab_index}: {exc}")

    import pyautogui

    pyautogui.FAILSAFE = False
    _force_english_ime()
    log("UIA fallback: click prompt then Ctrl+V clipboard image")
    _click_grok_prompt_input(hwnd)
    time.sleep(0.35)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1.0)
    return False


def _click_grok_image_mode(hwnd: int) -> None:
    """Picture icon beside + on the composer toolbar."""
    if _click_named(
        hwnd, "图片", ["ButtonControl", "RadioButtonControl"], search_depth=14
    ):
        return
    if _click_named(
        hwnd, "Image", ["ButtonControl", "RadioButtonControl"], search_depth=14
    ):
        return
    _click_ratio(hwnd, GROK_IMAGE_ICON_X, GROK_TOOLBAR_Y, pause=0.25)


def _click_grok_aspect_ratio_916(hwnd: int) -> None:
    """Toolbar 纵横比 / 9:16 → dropdown → 9:16."""
    _left, top, _w, height = _chrome_window_rect(hwnd)
    toolbar_y = top + int(height * 0.50)

    toolbar_btn = None
    best_y = -1
    for label in ("纵横比", "Aspect ratio", "Aspect Ratio", "9:16"):
        for ctrl in _uia_named_all(
            hwnd,
            label,
            ["ButtonControl", "TextControl"],
            search_depth=16,
            limit=8,
        ):
            box = _ctrl_box(ctrl)
            if not box:
                continue
            cy = (box[1] + box[3]) // 2
            if cy >= toolbar_y and cy > best_y:
                best_y = cy
                toolbar_btn = ctrl
        if toolbar_btn is not None:
            break

    if toolbar_btn is not None:
        log("UIA click toolbar aspect-ratio pill")
        _click_uia_ctrl(toolbar_btn)
    else:
        log("ratio-click toolbar aspect-ratio pill")
        _click_ratio(hwnd, GROK_ASPECT_BTN_X, GROK_TOOLBAR_Y, pause=0.35)
    time.sleep(0.45)

    if _click_named(
        hwnd,
        "9:16",
        ["MenuItemControl", "ButtonControl", "TextControl", "ListItemControl"],
        search_depth=16,
    ):
        log("selected aspect ratio 9:16")
        time.sleep(0.2)
        return

    log("ratio-click dropdown item 9:16")
    _click_ratio(hwnd, GROK_ASPECT_BTN_X, GROK_ASPECT_MENU_Y, pause=0.25)


def _prepare_grok_imagine_tab(
    hwnd: int, tab_index: int = 1, *, paste_image: bool = False
) -> bool:
    """Current Grok tab: paste cover image, then 图片 mode + 9:16. Returns paste ok."""
    if not _wait_grok_composer_ready(hwnd):
        log("Grok composer not confirmed by UIA; continuing")
    if cdp_ready(_grok_cdp_port()):
        try:
            return bool(
                _grok_run_on_tab(
                    tab_index,
                    lambda page: _grok_prepare_tab_cdp(page, paste_image=paste_image),
                )
            )
        except Exception as exc:
            log(f"Grok CDP prepare tab {tab_index} failed: {exc}; UIA fallback")

    pasted = False
    if paste_image:
        pasted = _paste_image_into_grok_composer(hwnd, tab_index)
    _click_grok_aspect_ratio_916(hwnd)
    time.sleep(0.2)
    return pasted or not paste_image


def _click_grok_video_mode(hwnd: int) -> None:
    """Second icon beside + under the composer → 视频 / Video."""
    if _click_named(
        hwnd, "视频", ["ButtonControl", "RadioButtonControl"], search_depth=14
    ):
        return
    if _click_named(
        hwnd, "Video", ["ButtonControl", "RadioButtonControl"], search_depth=14
    ):
        return
    _click_ratio(hwnd, 0.430, GROK_TOOLBAR_Y, pause=0.25)
    _click_ratio(hwnd, 0.450, GROK_TOOLBAR_Y, pause=0.2)


def _click_grok_video_settings(hwnd: int) -> None:
    """Best-effort 720p / 10s after Video mode. Skip quietly if the UI has no names."""
    for name in ("720p", "720P", "720"):
        if _click_named(
            hwnd,
            name,
            ["ButtonControl", "RadioButtonControl", "ComboBoxControl", "TextControl"],
            search_depth=14,
        ):
            time.sleep(0.15)
            break
    for name in ("10s", "10 s", "10sec", "10 sec", "10 seconds", "10秒"):
        if _click_named(
            hwnd,
            name,
            ["ButtonControl", "RadioButtonControl", "ComboBoxControl", "TextControl"],
            search_depth=14,
        ):
            time.sleep(0.15)
            break


def _click_grok_generate(hwnd: int) -> None:
    """Last icon on the composer bar — up-arrow Generate."""
    for name in ("Submit", "Send", "生成", "Start"):
        if _click_named(
            hwnd, name, ["ButtonControl"], search_depth=14
        ):
            return
    _click_ratio(hwnd, GROK_GENERATE_X, GROK_TOOLBAR_Y, pause=0.3)


def paste_image_into_all_grok_tabs() -> str:
    """Paste clipboard image + 9:16 竖屏 on every open Grok Imagine tab."""
    n = _grok_recorded_tab_count() or 1
    port = _grok_resolve_cdp_port()
    cover_png = _grok_resolve_cover_png()
    pasted_n, _prompt_n, _downloads = _grok_prepare_all_tabs_cdp(
        n, cover_png=cover_png, port=port, fresh_tabs=False
    )
    if pasted_n < n:
        raise RuntimeError(
            f"只成功粘贴 {pasted_n}/{n} 个 Grok 标签。"
            "请确认剪贴板有图片，并确保 Grok 窗口在前台后重发 grv prep。"
        )
    return f"pasted image + 9:16 竖屏 on {n} Grok Imagine tab(s) (verified)"


def apply_grok_image_prompt_to_tab(tab_index: int, prompt: str) -> str:
    """Reuse grv's Grok Imagine tab N: paste prompt, 图片 mode, Generate, wait."""
    port = _grok_attach_cdp_port(allow_launch=False)
    recorded = _grok_recorded_tab_count()

    def _apply(page: Page) -> bool:
        page.bring_to_front()
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
        time.sleep(0.6)
        _grok_paste_prompt_cdp(page, prompt)
        _grok_click_image_mode_cdp(page)
        time.sleep(0.3)
        _grok_click_generate_cdp(page)
        time.sleep(0.6)
        _grok_wait_image_ready_cdp(page)
        return True

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        if not browser.contexts:
            raise RuntimeError("Grok CDP connected but no browser context")
        pages = _grok_imagine_pages(browser.contexts[0])
        n = len(pages)
        if n < 1:
            raise RuntimeError(
                "找不到 grok.com/imagine 标签。请先 grv 1 打开标签。"
            )
        if tab_index < 1 or tab_index > n:
            raise RuntimeError(
                f"没有第 {tab_index} 个 Grok Imagine 标签（当前 {n} 个）。"
                "请先 grv 开够标签。"
            )
        if recorded and tab_index > recorded:
            raise RuntimeError(
                f"第 {tab_index} 个标签超出 LM 记录的 {recorded} 个场景。"
                f"只发 gri 1…{recorded}。"
            )
        page = pages[tab_index - 1]
        log(f"gri: reuse tab {tab_index}/{n} url={page.url}")
        _apply(page)

    return (
        f"Grok tab {tab_index}/{n}: prompt pasted (reuse, CDP verified), "
        f"图片 mode, Generate done — image ready"
    )


def _grok_still_generating(hwnd: int) -> bool:
    for name in (
        "Generating",
        "Generating video",
        "Generating image",
        "Generating Image",
        "Creating image",
        "正在生成",
        "生成中",
        "Generating Video",
        "Loading",
    ):
        if _named_exists(
            hwnd,
            name,
            ["TextControl", "ButtonControl", "StatusBarControl"],
            search_depth=14,
            timeout_s=0.12,
        ):
            return True
    return False


def _wait_grok_media_ready(
    hwnd: int,
    *,
    label: str,
    min_s: float,
    timeout_s: float,
) -> None:
    started = time.monotonic()
    log(f"waiting for Grok {label} (up to {int(timeout_s)}s)…")
    while time.monotonic() - started < timeout_s:
        elapsed = time.monotonic() - started
        generating = _grok_still_generating(hwnd)
        log(f"grok {label} wait {elapsed:.0f}s generating={generating}")
        if elapsed >= min_s and not generating:
            time.sleep(2.0)
            if not _grok_still_generating(hwnd):
                log(f"Grok {label} looks ready")
                return
        time.sleep(4.0)
    raise RuntimeError(
        f"等了 {int(timeout_s // 60)} 分钟 Grok {label} 仍在生成。请看该标签是否卡住。"
    )


def _wait_grok_image_ready(
    hwnd: int, timeout_s: float = GROK_IMAGE_READY_TIMEOUT_S
) -> None:
    _wait_grok_media_ready(
        hwnd,
        label="image",
        min_s=GROK_IMAGE_READY_MIN_S,
        timeout_s=timeout_s,
    )


def _wait_grok_video_ready(hwnd: int, timeout_s: float = GROK_VIDEO_READY_TIMEOUT_S) -> None:
    _wait_grok_media_ready(
        hwnd,
        label="video",
        min_s=GROK_VIDEO_READY_MIN_S,
        timeout_s=timeout_s,
    )


def _click_grok_download(hwnd: int) -> None:
    """Footer download icon under Share（向下箭头进托盘）。"""
    for name in ("下载", "Download", "Save", "保存", "Save video"):
        if _click_named(
            hwnd,
            name,
            ["ButtonControl", "HyperlinkControl", "MenuItemControl"],
            search_depth=14,
        ):
            return
    # Right-rail action cluster: small icon row under 共享, last icon = download.
    _click_ratio(hwnd, 0.938, 0.448, pause=0.25)
    _click_ratio(hwnd, 0.955, 0.472, pause=0.2)


def _mp4_snapshot(folder: Path) -> set[str]:
    return {str(p.resolve()) for p in folder.glob("*.mp4") if p.is_file()}


def _wait_new_download_mp4(
    folder: Path,
    before: set[str],
    timeout_s: float = GROK_DOWNLOAD_TIMEOUT_S,
) -> Path:
    deadline = time.monotonic() + timeout_s
    last_size = -1
    candidate: Path | None = None
    while time.monotonic() < deadline:
        pending = list(folder.glob("*.crdownload")) + list(folder.glob("*.tmp"))
        fresh = [
            p
            for p in folder.glob("*.mp4")
            if p.is_file() and str(p.resolve()) not in before
        ]
        if fresh and not pending:
            newest = max(fresh, key=lambda p: p.stat().st_mtime)
            try:
                size = newest.stat().st_size
            except OSError:
                size = 0
            if size > 40_000 and size == last_size and candidate == newest:
                return newest
            last_size = size
            candidate = newest
        time.sleep(0.6)
    raise RuntimeError(
        "Downloads 里没有出现新的 mp4。请确认 Grok 已出完片，并点了右下下载图标。"
    )


def _grok_cdp_cookies_for_download(ctx: BrowserContext) -> dict[str, str]:
    """grok.com auth cookies for authenticated asset GET (same idea as Hermes cdp_download)."""
    out: dict[str, str] = {}
    for c in ctx.cookies():
        dom = (c.get("domain") or "").lstrip(".")
        if dom.endswith("grok.com"):
            out[c["name"]] = c["value"]
    return out


def _grok_download_video_asset(src: str, cookies: dict[str, str], dest: Path) -> int:
    import requests

    r = requests.get(
        src,
        cookies=cookies,
        stream=True,
        timeout=120,
        allow_redirects=True,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"HTTP {r.status_code} downloading video ({src[:80]}…)"
        )
    total = 0
    with open(dest, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            if chunk:
                f.write(chunk)
                total += len(chunk)
    if total < 1000:
        raise RuntimeError(f"downloaded file too small ({total} bytes)")
    return total


def _grok_scene_video_download_stamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _grok_download_tab_video_cdp(
    page: Page,
    scene: int,
    cookies: dict[str, str],
    *,
    stamp: str,
    folder: Path | None = None,
    wait_ready: bool = False,
    log_prefix: str = "gvd",
) -> dict:
    """CDP: read output ``<video>.src`` + cookie GET → ``grok_scene_{scene}_{stamp}.mp4``."""
    dest_dir = folder or windows_downloads_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    page.bring_to_front()
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(0.35)
    if wait_ready:
        _grok_wait_video_ready_cdp(page)
    info = page.evaluate(_GROK_OUTPUT_VIDEO_SRC_JS) or {}
    if not info.get("ok"):
        reason = info.get("reason") or "unknown"
        raise RuntimeError(
            f"场景 {scene} 没有可下载的 video src（{reason}）。"
            "请确认该标签已出片。"
        )
    src = str(info.get("src") or "").strip()
    if not src.startswith("http"):
        raise RuntimeError(
            f"场景 {scene} video src 不是 http URL：{src[:80]!r}。"
            "可能还在 blob/生成中，请稍后再试。"
        )
    log(f"{log_prefix} tab {scene}: src={src[:90]}…")
    dest = dest_dir / f"grok_scene_{scene}_{stamp}.mp4"
    total = _grok_download_video_asset(src, cookies, dest)
    log(f"{log_prefix} tab {scene}: saved {dest.name} ({total} bytes)")
    return {"scene": scene, "path": str(dest.resolve())}


def _grok_download_scene_videos_cdp(
    ctx: BrowserContext,
    pages: list[Page],
    n: int,
    *,
    stamp: str | None = None,
    wait_ready: bool = True,
    log_prefix: str = "gvd",
) -> list[dict]:
    """Download scene 1…N from open Imagine tabs (shared by ``grv`` and ``gvd``)."""
    if not pages:
        raise RuntimeError(
            "找不到 grok.com/imagine 标签。请先 grv 1 开标签并出片。"
        )
    if len(pages) < n:
        raise RuntimeError(
            f"Grok CDP found {len(pages)} imagine tab(s), need {n}。"
            "请重发 grv 开够标签。"
        )
    stamp = stamp or _grok_scene_video_download_stamp()
    cookies = _grok_cdp_cookies_for_download(ctx)
    log(
        f"{log_prefix} CDP: {len(pages)} tab(s), {len(cookies)} grok.com cookie(s), "
        f"scene_count={n}"
    )
    if not cookies:
        log(f"{log_prefix} CDP: warning — no grok.com cookies; download may 403")
    recorded: list[dict] = []
    for i in range(1, n + 1):
        page = pages[i - 1]
        log(f"{log_prefix} CDP tab {i}/{n} url={page.url}")
        recorded.append(
            _grok_download_tab_video_cdp(
                page,
                i,
                cookies,
                stamp=stamp,
                wait_ready=wait_ready,
                log_prefix=log_prefix,
            )
        )
    return recorded


def download_grok_scene_videos() -> list[dict]:
    """Download each Grok Imagine tab's video via CDP ``video.src`` + cookies.

    Matches the reliable path in ``D:\\Hermes\\cdp_download.py`` (no UI download click).
    Re-download /补下 when ``grv`` did not run or a clip was missed.
    """
    n = _grok_recorded_tab_count() or 1
    port = _grok_attach_cdp_port(allow_launch=False)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        if not browser.contexts:
            raise RuntimeError("Grok CDP connected but no browser context")
        ctx = browser.contexts[0]
        pages = _grok_imagine_pages(ctx)
        recorded = _grok_download_scene_videos_cdp(
            ctx, pages, n, wait_ready=True, log_prefix="gvd"
        )

    from utility.telegram_session import save_grok_scene_videos

    return save_grok_scene_videos(recorded)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    p_gemini = sub.add_parser("gemini")
    p_gemini.add_argument("prompt")

    p_file = sub.add_parser("gemini_file")
    p_file.add_argument("path")

    sub.add_parser("gemini_clipboard")
    sub.add_parser("notebooklm")
    sub.add_parser("grok_imagine")
    sub.add_parser("status")

    args = parser.parse_args()

    try:
        if args.action == "gemini":
            print(handle_gemini(args.prompt))
            return 0

        if args.action == "gemini_file":
            print(handle_gemini(read_prompt_file(args.path)))
            return 0

        if args.action == "gemini_clipboard":
            print(handle_gemini_clipboard())
            return 0

        if args.action == "notebooklm":
            print(handle_notebooklm_covers())
            return 0

        if args.action == "grok_imagine":
            print(handle_grok_imagine_tabs())
            return 0

        if args.action == "status":
            with sync_playwright() as p:
                controller = BrowserController(p)
                try:
                    controller.connect()
                    print("browser=ready")
                    return 0
                finally:
                    controller.close()

        return 2

    except Exception as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
