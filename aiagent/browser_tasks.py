"""
Browser automation controller for Hermes Story Video Generation (v2).

Supported actions:
    python -m aiagent.browser_tasks gemini "<prompt>"
    python -m aiagent.browser_tasks gemini_file "<prompt-file>"
    python -m aiagent.browser_tasks gemini_clipboard
    python -m aiagent.browser_tasks notebooklm
    python -m aiagent.browser_tasks grok_imagine
    python -m aiagent.browser_tasks status
"""

from __future__ import annotations

import argparse
import ctypes
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

# Per ``handle_gemini`` run: sidebar star only once at open.
_GEMINI_SIDEBAR_DONE = False


def log(message: str) -> None:
    print(f"[browser_tasks] {message}", file=sys.stderr, flush=True)


def resolve_chrome_profile_directory(profile_email: str = "") -> str:
    """Map ``GEMINI_CHROME_PROFILE`` (email) to Chrome ``--profile-directory``."""
    want = (profile_email or getattr(config, "GEMINI_CHROME_PROFILE", "") or "").strip()
    for item in getattr(config, "list_gemini_chrome_profiles", lambda: [])():
        if item.get("label", "").strip().lower() == want.lower():
            directory = (item.get("directory") or "").strip() or "Default"
            log(f"profile list: {want} → --profile-directory={directory}")
            return directory

    explicit = (getattr(config, "GEMINI_CHROME_PROFILE_DIRECTORY", "") or "").strip()
    if explicit:
        return explicit

    want = (profile_email or getattr(config, "GEMINI_CHROME_PROFILE", "") or "").strip().lower()
    user_data = (getattr(config, "CHROME_USER_DATA_DIR", "") or "").strip()
    local_state = Path(user_data) / "Local State" if user_data else None
    if want and local_state and local_state.is_file():
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
                        info.get("user_name"),
                    ]
                    blob = " ".join(str(x) for x in fields if x).lower()
                    if want and want in blob:
                        log(f"resolved {profile_email or want} → --profile-directory={dirname}")
                        return str(dirname)
        except Exception as exc:
            log(f"could not read Chrome Local State: {exc}")

    return "Profile 2"


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


def ensure_chrome_cdp() -> None:
    """Attach to Chrome on the debug port, or launch it with GEMINI_CHROME_PROFILE."""
    port = int(getattr(config, "CHROME_REMOTE_DEBUGGING_PORT", 9222) or 9222)
    if cdp_ready(port):
        log(f"Chrome CDP already listening on {port}")
        return

    exe = (getattr(config, "CHROME_EXE", "") or "").strip()
    if not exe or not Path(exe).is_file():
        raise RuntimeError(f"Chrome executable not found: {exe}")

    profile_dir = resolve_chrome_profile_directory(getattr(config, "GEMINI_CHROME_PROFILE", ""))
    args = [
        exe,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--profile-directory={profile_dir}",
        "--new-window",
        GEMINI_URL,
    ]
    log("launching Chrome: " + " ".join(args))
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        if cdp_ready(port):
            log(f"Chrome CDP ready on {port} (profile={profile_dir})")
            return
        time.sleep(0.4)

    raise RuntimeError(
        f"Chrome did not open CDP on port {port}. "
        "A normal Chrome was probably already running and swallowed this launch. "
        f"Profile: {getattr(config, 'GEMINI_CHROME_PROFILE', '')} ({profile_dir})."
    )


def _chrome_cdp_user_data_dir() -> str:
    path = (getattr(config, "CHROME_CDP_USER_DATA_DIR", "") or "").strip()
    if path:
        return path
    return str(Path.home() / "AppData" / "Local" / "HermesChromeCDP")


def ensure_gemini_cdp(timeout_s: float = 30.0) -> int:
    """Guarantee a Chrome speaking CDP on the debug port; return the port.

    Uses a dedicated ``--user-data-dir`` so this works even while the normal
    Chrome is running (Chrome only opens the debug port on a fresh instance).
    """
    port = int(getattr(config, "CHROME_REMOTE_DEBUGGING_PORT", 9222) or 9222)
    if cdp_ready(port):
        log(f"CDP already up on {port}")
        return port

    exe = (getattr(config, "CHROME_EXE", "") or "").strip()
    if not exe or not Path(exe).is_file():
        raise RuntimeError(f"Chrome executable not found: {exe}")

    user_data = _chrome_cdp_user_data_dir()
    Path(user_data).mkdir(parents=True, exist_ok=True)
    profile_dir = resolve_chrome_profile_directory(
        getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    args = [
        exe,
        f"--user-data-dir={user_data}",
        f"--profile-directory={profile_dir}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        GEMINI_URL,
    ]
    log(f"launching CDP Chrome: user-data-dir={user_data} profile={profile_dir}")
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if cdp_ready(port):
            log(f"CDP ready on {port}")
            time.sleep(1.5)
            return port
        time.sleep(0.5)

    raise RuntimeError(
        f"Chrome 没能在 {port} 端口打开调试接口。\n"
        f"user-data-dir={user_data}\n"
        "请检查 CHROME_EXE 路径，或手工跑 cli/launch_chrome_gemini.py 看报错。"
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

        user_data_dir = os.environ.get("HERMES_CHROME_USER_DATA_DIR", "").strip()
        profile = os.environ.get("HERMES_CHROME_PROFILE", "").strip()
        channel = os.environ.get("HERMES_BROWSER_CHANNEL", "").strip() or None

        if not user_data_dir:
            user_data_dir = str(
                Path.home() / "AppData" / "Local" / "HermesChromeProfile"
            )
            log(
                "HERMES_CHROME_USER_DATA_DIR not set; using dedicated persistent "
                f"profile: {user_data_dir}"
            )

        launch_args = {}
        if profile:
            launch_args["args"] = [f"--profile-directory={profile}"]

        log(f"launching persistent browser profile: {user_data_dir}")

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
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        return False

    login_markers = [
        "sign in",
        "log in",
        "choose an account",
        "use another account",
        "登录",
        "选择账号",
    ]
    return any(marker in text for marker in login_markers)


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
    from aiagent.win_gui_tasks import enum_windows_safe

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
        from aiagent.win_gui_tasks import win32gui

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
        from aiagent.win_gui_tasks import win32gui

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
    from aiagent.win_gui_tasks import set_foreground, win32con, win32gui

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
    from aiagent.win_gui_tasks import set_foreground

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
    from aiagent.win_gui_tasks import set_foreground

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
    from aiagent.win_gui_tasks import get_window_rect

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
    from aiagent.win_gui_tasks import set_foreground

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
                raise RuntimeError(
                    "这个 Chrome 还没登录 Google。请在刚弹出的窗口里登录一次"
                    f"（{getattr(config, 'GEMINI_CHROME_PROFILE', '')}），"
                    "之后 gem 就一直能用。"
                )

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
    log("falling back to screen-coordinate path")
    _reset_gemini_layout_session()
    write_windows_clipboard(prompt_text)
    if not _find_gemini_chrome_hwnd():
        try:
            launch_chrome_profile_window(GEMINI_URL)
            log("launched Chrome → Gemini")
        except Exception as exc:
            log(f"Chrome launch failed: {exc}")
        if not _wait_for_gemini_hwnd(20.0):
            raise RuntimeError(
                "找不到 Gemini 窗口，CDP 也起不来。请先打开 gemini.google.com，再发 gem。"
            )
    paste_prompt_into_gemini_window(prompt_text)
    return wait_and_copy_gemini_json(prompt_text, layout_ready=True)


def read_prompt_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def launch_chrome_profile_window(*urls: str) -> str:
    """Open URL(s) in a new Chrome window using the currently selected profile.

    Multiple URLs become multiple tabs in that window (Grok Imagine × N).
    Does not attach CDP. Empty directory maps to Default.
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
    args = [
        exe,
        f"--profile-directory={profile_dir}",
        "--new-window",
        *pages,
    ]
    log("launching Chrome: " + " ".join(args))
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
    from aiagent.win_gui_tasks import enum_windows_safe

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


def _open_first_existing_notebook(hwnd: int) -> None:
    """Home: first EXISTING Recent notebook (right of Create new). Never create one."""
    if _named_exists(
        hwnd,
        "Infographic",
        ["ButtonControl", "HyperlinkControl"],
        search_depth=14,
        timeout_s=0.35,
    ):
        log("already inside a notebook (Infographic visible)")
        return

    if _click_named(
        hwnd,
        "Story Builder",
        [
            "ButtonControl",
            "HyperlinkControl",
            "ListItemControl",
            "GroupControl",
            "TextControl",
            "CustomControl",
        ],
        search_depth=14,
    ):
        log("clicked existing notebook: Story Builder")
        time.sleep(2.2)
        return

    create = _uia_named(
        hwnd,
        "Create new",
        ["ButtonControl", "HyperlinkControl", "GroupControl", "ListItemControl"],
        search_depth=14,
        timeout_s=0.4,
    )
    if create:
        try:
            rect = create.BoundingRectangle
            w = rect.width() if callable(getattr(rect, "width", None)) else (rect.right - rect.left)
            # Next card to the RIGHT of Create new — never the plus card itself.
            x = rect.right + max(28, int((w or 160) * 0.55))
            y = (rect.top + rect.bottom) // 2
            log(f"click first EXISTING notebook (right of Create new) at ({x},{y})")
            _click_xy(x, y, pause=2.2)
            return
        except Exception:
            pass

    log("UIA missed Story Builder; ratio-click first existing Recent card (not Create new)")
    for x_r, y_r in ((0.34, 0.70), (0.38, 0.66), (0.32, 0.72), (0.40, 0.68)):
        _click_ratio(hwnd, x_r, y_r, pause=1.2)
        if _wait_named(
            hwnd,
            "Infographic",
            ["ButtonControl", "HyperlinkControl"],
            timeout_s=2.5,
            search_depth=14,
        ):
            return
    time.sleep(1.5)


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


def _infographic_still_generating(hwnd: int) -> bool:
    for name in (
        "Generating Infographic",
        "Generating infographic",
        "正在生成信息图",
        "正在生成",
    ):
        if _named_exists(
            hwnd,
            name,
            ["TextControl", "ButtonControl", "StatusBarControl"],
            search_depth=14,
            timeout_s=0.15,
        ):
            return True
    return False


def _studio_infographic_rows_ready(hwnd: int, expected: int) -> int:
    """Count Studio infographic rows that look finished (``Nm ago`` / ``just now``)."""
    found = 0
    for i in range(1, max(1, expected) + 1):
        labels = (
            f"{i}m ago",
            f"{i} min ago",
            f"{i} minute ago",
            f"{i} 分鐘前",
            f"{i}分钟前",
        )
        if i == 1:
            labels = ("just now", "Just now", "剛剛", "刚刚", *labels)
        if any(
            _named_exists(
                hwnd,
                label,
                ["TextControl", "HyperlinkControl", "ButtonControl", "ListItemControl"],
                search_depth=22,
                timeout_s=0.12,
            )
            for label in labels
        ):
            found = max(found, i)
    return found


def _wait_infographics_ready(
    hwnd: int,
    expected: int = NOTEBOOKLM_COVER_TIMES,
    timeout_s: float = NOTEBOOKLM_READY_TIMEOUT_S,
) -> None:
    want = max(1, int(expected or NOTEBOOKLM_COVER_TIMES))
    started = time.monotonic()
    log(f"waiting for {want} infographics in Studio (up to {int(timeout_s)}s)…")
    while time.monotonic() - started < timeout_s:
        elapsed = time.monotonic() - started
        generating = _infographic_still_generating(hwnd)
        rows = _studio_infographic_rows_ready(hwnd, want)
        log(f"infographic wait {elapsed:.0f}s generating={generating} studio_rows={rows}/{want}")
        if (
            elapsed >= NOTEBOOKLM_READY_MIN_S
            and not generating
            and rows >= want
        ):
            time.sleep(3.0)
            if _studio_infographic_rows_ready(hwnd, want) >= want:
                log("infographics look ready in Studio")
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
    ):
        if _named_exists(
            hwnd,
            marker,
            ["ButtonControl", "TextControl", "HyperlinkControl"],
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
        "更多",
        "更多选项",
    ):
        if _click_named(
            hwnd, name, ["ButtonControl", "MenuItemControl"], search_depth=22
        ):
            time.sleep(0.45)
            return True
    log("ratio-click infographic preview ⋮ menu (top-right of modal)")
    _click_ratio(hwnd, 0.718, 0.152, pause=0.55)
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
    _click_ratio(hwnd, 0.718, 0.205, pause=0.85)
    return True


def _close_infographic_preview(hwnd: int) -> None:
    import pyautogui

    pyautogui.FAILSAFE = False
    for name in ("Close", "关闭", "關閉"):
        if _click_named(
            hwnd, name, ["ButtonControl"], search_depth=22
        ):
            time.sleep(0.45)
            return
    log("ratio-click preview Close (X)")
    _click_ratio(hwnd, 0.688, 0.152, pause=0.35)
    pyautogui.press("escape")
    time.sleep(0.35)


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


def _copy_visible_infographic_image(hwnd: int) -> bool:
    """Right-click the open infographic → Copy image (as in the Chrome context menu)."""
    import pyautogui

    pyautogui.FAILSAFE = False
    left, top, width, height = _chrome_window_rect(hwnd)
    # Portrait infographic sits in the main/center column.
    x = left + int(width * 0.42)
    y = top + int(height * 0.48)
    log(f"right-click infographic at ({x},{y})")
    _right_click_xy(x, y, pause=0.55)
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
    # Context menu: Open / Save as / Copy image (3rd item) — screenshot layout.
    log("Copy image menu item not named; click 3rd context-menu row")
    _click_xy(x + 90, y + 78, pause=0.5)
    return True


def _click_studio_infographic_row(hwnd: int, index: int) -> None:
    """Open the Nth generated infographic in Studio (1-based, newest-first)."""
    ago_labels = [
        f"{index}m ago",
        f"{index} min ago",
        f"{index} minute ago",
        f"{index} 分鐘前",
        f"{index}分钟前",
    ]
    if index == 1:
        ago_labels = ["just now", "Just now", "剛剛", "刚刚", *ago_labels]
    for label in ago_labels:
        if _click_named(
            hwnd,
            label,
            ["TextControl", "HyperlinkControl", "ButtonControl", "ListItemControl"],
            search_depth=22,
        ):
            log(f"click Studio infographic row {index} via {label!r}")
            time.sleep(2.0)
            return

    left, top, width, height = _chrome_window_rect(hwnd)
    cutoff = top + int(height * 0.52)
    for name in ("is ready", "Infographic"):
        ctrl = _uia_named(
            hwnd,
            name,
            ["ButtonControl", "HyperlinkControl", "TextControl", "ListItemControl"],
            search_depth=18,
            timeout_s=0.25,
            found_index=index,
        )
        if not ctrl:
            continue
        try:
            rect = ctrl.BoundingRectangle
            if rect.top >= cutoff or name == "is ready":
                log(f"click Studio infographic row {index} via {name!r}")
                _click_rect_center(rect)
                time.sleep(2.0)
                return
        except Exception:
            continue
    y_r = 0.565 + (index - 1) * 0.085
    log(f"ratio-click Studio note row {index} at (0.82, {y_r:.2f})")
    _click_ratio(hwnd, 0.82, y_r, pause=2.0)


def _download_one_infographic_via_menu(hwnd: int, index: int, dest: Path) -> bool:
    """Open Studio row → ⋮ → Download → save to *dest*."""
    _click_studio_infographic_row(hwnd, index)
    time.sleep(1.8)
    if not _infographic_preview_open(hwnd):
        log(f"preview may not be open for row {index}; trying download anyway")

    since = time.time()
    _click_infographic_preview_more_menu(hwnd)
    _click_infographic_download_menu_item(hwnd)

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
    from aiagent.win_gui_tasks import set_foreground

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


def handle_notebooklm_covers(times: int = NOTEBOOKLM_COVER_TIMES) -> str:
    """Open NotebookLM with the current Chrome profile and Generate infographic N times.

    Clipboard must already hold the NotebookLM cover prompt (``notebooklm 1``).
    Clicks: first Recent notebook → Infographic → Portrait + Concise → paste → Generate.
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

    from aiagent.win_gui_tasks import set_foreground, win32con, win32gui

    before = {hwnd for hwnd, _ in _enum_titled_windows()}
    profile_dir = launch_chrome_profile_window(NOTEBOOKLM_URL)
    try:
        hwnd = _wait_notebooklm_hwnd(exclude=before, timeout_s=10.0)
    except RuntimeError:
        log("no new NotebookLM window; trying existing")
        hwnd = _find_notebooklm_hwnd()
        if not hwnd:
            hwnd = _wait_notebooklm_hwnd(timeout_s=12.0)
    log(f"NotebookLM hwnd={hwnd} profile_dir={profile_dir}")
    if win32gui is not None and win32con is not None:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        except Exception:
            pass
    set_foreground(hwnd)
    time.sleep(3.5)

    _open_first_existing_notebook(hwnd)
    time.sleep(2.5)
    hwnd = _find_notebooklm_hwnd() or hwnd
    set_foreground(hwnd)
    if _named_exists(
        hwnd,
        "Add sources",
        ["ButtonControl", "TextControl", "HyperlinkControl"],
        search_depth=12,
        timeout_s=0.25,
    ) and not _named_exists(
        hwnd,
        "Infographic",
        ["ButtonControl", "HyperlinkControl"],
        search_depth=14,
        timeout_s=0.25,
    ):
        raise RuntimeError(
            "看起来点到了 Create new（空 notebook）。"
            "请不要新建，只打开 Recent notebooks 里已有的第一张 Story Builder。"
        )
    if not _wait_named(
        hwnd,
        "Infographic",
        ["ButtonControl", "HyperlinkControl"],
        timeout_s=14.0,
        search_depth=14,
    ):
        raise RuntimeError(
            "打开已有 notebook 后看不到 Infographic。"
            "请确认 Recent notebooks 第一张（Create new 右侧）是 Story Builder，且没有点到 Create new。"
        )

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

    hwnd = _find_notebooklm_hwnd() or hwnd
    set_foreground(hwnd)
    _wait_infographics_ready(hwnd, expected=n)
    files = _download_whole_story_images(hwnd, n)
    names = ", ".join(Path(p).name for p in files) or "(none)"
    return (
        f"launched {NOTEBOOKLM_URL} profile_dir={profile_dir}; "
        f"clicked Generate {started} time(s) (Portrait + Concise); "
        f"downloaded {len(files)} whole story image(s) to Downloads: {names}"
    )


def handle_grok_imagine_tabs() -> str:
    """Open N ``grok.com/imagine`` tabs from recorded ``story_scene_prompt_choice``."""
    from utility.telegram_session import load_story_scene_prompt_choice

    choice = load_story_scene_prompt_choice()
    label = (choice.get("label") or "").strip()
    n = int(choice.get("tabs") or 0)
    if not label or n < 1:
        raise RuntimeError(
            "还没有记录 story_scene_prompt_choice。"
            "先在 SCENE 选 LM：lm 4。"
        )
    urls = [GROK_IMAGINE_URL] * n
    profile_dir = launch_chrome_profile_window(*urls)
    log(f"Grok Imagine × {n} ({label}) profile_dir={profile_dir}")
    return (
        f"opened {n} Grok Imagine tab(s) for {label!r} "
        f"({GROK_IMAGINE_URL}) profile_dir={profile_dir}"
    )


def _find_grok_chrome_hwnd() -> Optional[int]:
    from aiagent.win_gui_tasks import enum_windows_safe

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
    from aiagent.win_gui_tasks import set_foreground, win32con, win32gui

    hwnd = _find_grok_chrome_hwnd()
    if not hwnd:
        raise RuntimeError(
            "找不到 Grok Imagine 窗口。请先发 gr 打开标签。"
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
    from aiagent.win_gui_tasks import set_foreground

    pyautogui.FAILSAFE = False
    set_foreground(hwnd)
    time.sleep(0.15)
    _force_english_ime()
    pyautogui.hotkey("ctrl", str(max(1, min(index, 8))))
    time.sleep(0.65)


def _click_grok_composer(hwnd: int) -> None:
    if _click_named(
        hwnd,
        "Ask Grok",
        ["EditControl", "ComboBoxControl"],
        search_depth=14,
    ):
        return
    if _click_named(
        hwnd,
        "What do you want",
        ["EditControl"],
        search_depth=14,
    ):
        return
    if _click_named(
        hwnd,
        "Message",
        ["EditControl"],
        search_depth=14,
    ):
        return
    _click_ratio(hwnd, 0.50, 0.90, pause=0.25)


def _click_grok_image_mode(hwnd: int) -> None:
    """First icon beside + under the composer → 图片 / Image."""
    if _click_named(
        hwnd, "图片", ["ButtonControl", "RadioButtonControl"], search_depth=14
    ):
        return
    if _click_named(
        hwnd, "Image", ["ButtonControl", "RadioButtonControl"], search_depth=14
    ):
        return
    # + is left of the composer pill; first icon sits just to its right.
    _click_ratio(hwnd, 0.305, 0.905, pause=0.25)
    _click_ratio(hwnd, 0.328, 0.905, pause=0.2)


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
    # First icon ~0.305–0.328; second is one slot to the right.
    _click_ratio(hwnd, 0.350, 0.905, pause=0.25)
    _click_ratio(hwnd, 0.372, 0.905, pause=0.2)


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
    _click_ratio(hwnd, 0.74, 0.905, pause=0.3)
    _click_ratio(hwnd, 0.78, 0.905, pause=0.2)


def paste_image_into_all_grok_tabs() -> str:
    """Paste the clipboard image into every open Grok Imagine tab composer."""
    import pyautogui

    pyautogui.FAILSAFE = False
    n = _grok_recorded_tab_count() or 1
    hwnd = _focus_grok_window()
    for i in range(1, n + 1):
        log(f"paste whole-story image into Grok tab {i}/{n}")
        _focus_grok_tab(hwnd, i)
        _click_grok_composer(hwnd)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.85)
    return f"pasted image into {n} Grok Imagine tab(s)"


def apply_grok_image_prompt_to_tab(tab_index: int, prompt: str) -> str:
    """Paste prompt into Grok tab N, switch to 图片, Generate, wait until ready."""
    hwnd = _focus_grok_window()
    n = _grok_recorded_tab_count() or 1
    if tab_index < 1 or tab_index > n:
        raise RuntimeError(
            f"没有第 {tab_index} 个 Grok 标签（当前记录 {n} 个）。"
        )
    _focus_grok_tab(hwnd, tab_index)
    _paste_grok_composer_text(hwnd, prompt, replace=True)
    _click_grok_image_mode(hwnd)
    time.sleep(0.25)
    _click_grok_generate(hwnd)
    time.sleep(0.6)
    _wait_grok_image_ready(hwnd)
    return (
        f"Grok tab {tab_index}: prompt verified, 图片 mode, "
        f"Generate done — image ready"
    )


def apply_grok_video_prompt_to_tab(tab_index: int, prompt: str = "") -> str:
    """Paste video prompt into Grok tab N, Video mode, Generate, wait until ready.

    Prompt defaults to the Windows clipboard (``nbv`` just copied it).
    Replaces composer text; leaves any already-attached scene image in place.
    """
    text = (prompt or "").strip()
    if not text:
        text = read_windows_clipboard()
    if len(text) < 12:
        raise RuntimeError(
            "剪贴板没有 video 提示词。请先 sc i（或 sc i 后再 nbv）。"
        )
    hwnd = _focus_grok_window()
    n = _grok_recorded_tab_count() or 1
    if tab_index < 1 or tab_index > n:
        raise RuntimeError(
            f"没有第 {tab_index} 个 Grok 标签（当前记录 {n} 个）。"
        )
    _focus_grok_tab(hwnd, tab_index)
    _paste_grok_composer_text(hwnd, text, replace=True)
    _click_grok_video_mode(hwnd)
    time.sleep(0.3)
    _click_grok_video_settings(hwnd)
    time.sleep(0.2)
    _click_grok_generate(hwnd)
    time.sleep(0.6)
    _wait_grok_video_ready(hwnd)
    return (
        f"Grok tab {tab_index}: video prompt verified, Video mode, "
        f"Generate done — video ready"
    )


GROK_IMAGE_READY_MIN_S = 6
GROK_IMAGE_READY_TIMEOUT_S = 6 * 60
GROK_VIDEO_READY_MIN_S = 8
GROK_VIDEO_READY_TIMEOUT_S = 8 * 60
GROK_DOWNLOAD_TIMEOUT_S = 120


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


def download_grok_scene_videos() -> list[dict]:
    """Download each Grok Imagine tab's video clip into Windows Downloads, scene order."""
    import shutil
    from datetime import datetime

    n = _grok_recorded_tab_count() or 1
    hwnd = _focus_grok_window()
    folder = windows_downloads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    recorded: list[dict] = []
    for i in range(1, n + 1):
        log(f"download Grok video tab {i}/{n}")
        _focus_grok_tab(hwnd, i)
        time.sleep(0.4)
        _wait_grok_video_ready(hwnd)
        before = _mp4_snapshot(folder)
        _click_grok_download(hwnd)
        raw = _wait_new_download_mp4(folder, before)
        dest = folder / f"grok_scene_{i}_{stamp}.mp4"
        if raw.resolve() != dest.resolve():
            shutil.copy2(raw, dest)
            path = dest
        else:
            path = raw
        recorded.append({"scene": i, "path": str(path.resolve())})
        log(f"scene {i} -> {path.name}")
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
