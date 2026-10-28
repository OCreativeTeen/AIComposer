"""Chrome 账户（HermesChromeCDP 里的 profile）切换：同一个 --user-data-dir、同一个 CDP 端口 9222。

做法：选了别的账户时，用同一个 --user-data-dir 再跑一次 chrome.exe --profile-directory=<目录> <网址>。
Chrome 已经开着，会把它交给正在跑的那个实例，在那个 profile 里开一个新窗口；CDP 里就多一个标签。
每个标签的 Target.getTargetInfo 里有 browserContextId（每个 profile 一个），记下「profile → browserContextId」，
之后挑标签、开新标签都按它来（Playwright connect_over_cdp 不一定把别的 profile 分成单独的 context）。

用法（工作线程里，chrome_lock 之内或之外都行）：
    with chrome_account.use("oct"):
        grok_cdp.make_image(...)
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import time
from pathlib import Path

import config

TOM = "tom"
OCT = "oct"
ACCOUNTS = (
    (TOM, "Tom（当前账户）"),
    (OCT, "ocreativeteen@gmail.com"),
)
ACCOUNT_EMAILS = {TOM: "bjtombj2023@gmail.com", OCT: "ocreativeteen@gmail.com"}
# t130u: 按邮箱找不到时，再按 Local State 的显示名 / gaia_name 找（小写包含）
ACCOUNT_NAMES = {TOM: ("tom bj", "your chrome"), OCT: ("org creative", "org")}
# profile 目录名：环境变量优先；然后按邮箱 / 显示名在 Local State 里找；都找不到用这里的默认值。
# （2026-10 HermesChromeCDP：Default = bjtombj2023 / tom bj，Profile 2 = ocreativeteen / Org Creative）
DEFAULT_PROFILE_DIRS = {TOM: "Default", OCT: "Profile 2"}
PROFILE_ENV = {TOM: "CHROME_PROFILE_TOM", OCT: "CHROME_PROFILE_OCT"}
OPEN_WAIT_S = 25.0

_state = {"active": ""}
_ctx_ids: dict = {}  # (browser key, profile dir) -> browserContextId


def user_data_dir() -> str:
    path = (getattr(config, "CHROME_CDP_USER_DATA_DIR", "") or "").strip()
    return os.path.expandvars(path) if path else str(Path.home() / "AppData" / "Local" / "HermesChromeCDP")


def chrome_exe() -> str:
    return (getattr(config, "CHROME_EXE", "") or "").strip() or r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def normalize(name: str) -> str:
    name = (name or "").strip().lower()
    return name if name in dict(ACCOUNTS) else TOM


def label(name: str) -> str:
    return dict(ACCOUNTS).get(normalize(name), name)


def profile_dir(name: str) -> str:
    """账户 → --profile-directory。找不到（还没建这个 profile）返回 ""。"""
    name = normalize(name)
    env = (os.environ.get(PROFILE_ENV[name]) or "").strip()
    if env:
        return env
    email = ACCOUNT_EMAILS.get(name, "").lower()
    try:
        data = json.loads((Path(user_data_dir()) / "Local State").read_text(encoding="utf-8"))
        cache = (data.get("profile") or {}).get("info_cache") or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[chrome_account] Local State 读不出来：{exc}")
        cache = None
    if isinstance(cache, dict):
        if email:
            for dirname, info in cache.items():
                if isinstance(info, dict) and str(info.get("user_name") or "").strip().lower() == email:
                    return str(dirname)
        for want in ACCOUNT_NAMES.get(name, ()):
            for dirname, info in cache.items():
                if not isinstance(info, dict) or str(info.get("user_name") or "").strip():
                    if not isinstance(info, dict):
                        continue
                names = {str(info.get("gaia_name") or "").strip().lower(), str(info.get("name") or "").strip().lower()}
                if want in names:
                    return str(dirname)
        # Local State 里有这个默认目录才用（没建过的 profile 不要假装有）
        d = DEFAULT_PROFILE_DIRS.get(name, "")
        return d if d and d in cache else ""
    return DEFAULT_PROFILE_DIRS.get(name, "")


def missing_profile_message(name: str) -> str:
    return (
        f"HermesChromeCDP 里还没有登录 {label(name)} 的 Chrome 用户。\n"
        "在 9222 那个 Chrome 窗口右上角头像 → 添加 → 用这个 Google 账户登录，建好后再试。"
    )


@contextlib.contextmanager
def use(name: str):
    """这段时间里 Grok / Gemini 的 CDP 操作用这个账户。"""
    old = _state["active"]
    _state["active"] = normalize(name) if name else ""
    try:
        yield
    finally:
        _state["active"] = old


def active() -> str:
    return _state["active"] or TOM


def _browser_key(browser) -> str:
    """同一次 Chrome 运行里不变的键：CDP /json/version 的 webSocketDebuggerUrl（Chrome 重开就变）。
    每次任务都会重新 connect_over_cdp，所以不能用 id(browser)。"""
    try:
        import urllib.request

        port = int(getattr(config, "GROK_CDP_PORT", 9222) or 9222)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as resp:
            ws = str((json.loads(resp.read().decode("utf-8")) or {}).get("webSocketDebuggerUrl") or "")
        if ws:
            return ws
    except Exception:  # noqa: BLE001
        pass
    return "chrome"


def _page_ctx_id(page) -> str:
    try:
        s = page.context.new_cdp_session(page)
        try:
            info = s.send("Target.getTargetInfo") or {}
        finally:
            try:
                s.detach()
            except Exception:  # noqa: BLE001
                pass
        return str((info.get("targetInfo") or {}).get("browserContextId") or "")
    except Exception:  # noqa: BLE001
        return ""


def _all_pages(browser) -> list:
    out = []
    for ctx in list(browser.contexts or []):
        for pg in list(ctx.pages):
            try:
                if not pg.is_closed():
                    out.append(pg)
            except Exception:  # noqa: BLE001
                continue
    return out


def _other_ids(browser) -> set:
    """非 Tom 账户已知的 browserContextId。"""
    key = _browser_key(browser)
    tom_dir = profile_dir(TOM)
    return {v for (k, d), v in _ctx_ids.items() if k == key and d != tom_dir and v}


def page_matches(page) -> bool:
    """这个标签属于当前账户吗？Tom：不属于任何已知的其他账户；其他账户：browserContextId 对得上。"""
    name = active()
    try:
        browser = page.context.browser
    except Exception:  # noqa: BLE001
        return name == TOM
    if browser is None:
        return name == TOM
    if name == TOM:
        others = _other_ids(browser)
        return not others or _page_ctx_id(page) not in others
    want = _ctx_ids.get((_browser_key(browser), profile_dir(name)))
    return bool(want) and _page_ctx_id(page) == want


def filter_pages(pages) -> list:
    return [p for p in pages if page_matches(p)]


def _wait_page(browser, pred, timeout_s: float):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for pg in _all_pages(browser):
            if pred(pg):
                return pg
        time.sleep(0.5)
    return None


def new_page(browser, url: str, status=None):
    """在当前账户里开一个新标签打开 url，返回 Playwright Page。Tom 账户返回 None（调用方照旧 ctx.new_page()）。"""
    name = active()
    if name == TOM:
        return None
    pdir = profile_dir(name)
    if not pdir:
        raise RuntimeError(missing_profile_message(name))
    key = (_browser_key(browser), pdir)
    ctx_id = _ctx_ids.get(key)
    if ctx_id:
        try:
            cdp = browser.new_browser_cdp_session()
            res = cdp.send("Target.createTarget", {"url": url or "about:blank", "browserContextId": ctx_id})
            tid = str(res.get("targetId") or "")
            page = _wait_page(browser, lambda p: _target_id(p) == tid, 15.0)
            if page is not None:
                return page
        except Exception as exc:  # noqa: BLE001
            print(f"[chrome_account] 在已知 profile 里开标签失败，改用 chrome.exe：{exc}")
    # 第一次（或 context 不在了）：chrome.exe --profile-directory 交给正在跑的 Chrome，开一个新窗口
    before = {id(p) for p in _all_pages(browser)}
    if callable(status):
        try:
            status(f"用 {label(name)} 打开 Chrome 窗口 …")
        except Exception:  # noqa: BLE001
            pass
    subprocess.Popen(
        [chrome_exe(), f"--user-data-dir={user_data_dir()}", f"--profile-directory={pdir}", url or "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    host = (url or "").split("//")[-1].split("/")[0]
    page = _wait_page(browser, lambda p: id(p) not in before and (not host or host in (p.url or "")), OPEN_WAIT_S)
    if page is None:
        raise RuntimeError(f"没等到 {label(name)} 的 Chrome 窗口（{OPEN_WAIT_S:.0f} 秒）")
    cid = _page_ctx_id(page)
    if not cid:
        raise RuntimeError("新窗口的 browserContextId 读不出来，没法区分账户")
    tom_any = [p for p in _all_pages(browser) if id(p) in before]
    if tom_any and all(_page_ctx_id(p) == cid for p in tom_any[:3]) and pdir != profile_dir(TOM):
        print("[chrome_account] 警告：新窗口和原来的标签 browserContextId 一样，可能没切到另一个 profile")
    _ctx_ids[key] = cid
    return page


def _target_id(page) -> str:
    try:
        s = page.context.new_cdp_session(page)
        try:
            return str(((s.send("Target.getTargetInfo") or {}).get("targetInfo") or {}).get("targetId") or "")
        finally:
            try:
                s.detach()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        return ""


def ensure_known(browser, url: str, status=None) -> None:
    """非 Tom 账户：还不知道它的 browserContextId 时先开一个窗口认出来。"""
    name = active()
    if name == TOM:
        return
    pdir = profile_dir(name)
    if not pdir:
        raise RuntimeError(missing_profile_message(name))
    if not _ctx_ids.get((_browser_key(browser), pdir)):
        new_page(browser, url, status)
