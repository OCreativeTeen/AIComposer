"""Grok in Chrome over CDP, for the manual LLM window's "CLI自动" button.

Text:  grok.com chat -> paste prompt -> submit -> wait -> copy last response.
Image: grok.com/imagine -> attach image + prompt -> submit -> wait -> fetch output image.

Chrome connection reuses ``cli.browser_tasks`` (same approach as the CLI):
connect over CDP on port 9222. When nothing answers on 9222 we launch Chrome
the way the user does by hand:

    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        --remote-debugging-port=9222
        --user-data-dir="C:\\Users\\wenju\\AppData\\Local\\HermesChromeCDP"

That user-data-dir already holds the profile logged in as bjtombj2023@gmail.com;
we reuse it as is and never create or switch profiles here.

Everything here is blocking; call it from a worker thread, never the Tk thread.
Grok's DOM changes often: all selectors live in the constants below.
"""
from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import config

CDP_PORT = int(getattr(config, "GROK_CDP_PORT", 9222) or 9222)
CHROME_EXE = (getattr(config, "CHROME_EXE", "") or "").strip() or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# Profile logged in as bjtombj2023@gmail.com lives in this user-data-dir (HermesChromeCDP).
CHROME_USER_DATA_DIR = (getattr(config, "CHROME_CDP_USER_DATA_DIR", "") or "").strip() or os.path.join(
    os.environ.get("LOCALAPPDATA") or r"C:\Users\wenju\AppData\Local", "HermesChromeCDP"
)
CHROME_LAUNCH_WAIT_S = 30.0

GROK_CHAT_URL = "https://grok.com/"
GROK_IMAGINE_URL = "https://grok.com/imagine"

# ---- grok.com chat selectors (tried in order) ----
# Chat input: ProseMirror contenteditable inside the chat-input box; older builds used a textarea.
CHAT_INPUT_SELECTORS = (
    'div[data-testid="chat-input"] div[contenteditable="true"]',
    'form div.ProseMirror[contenteditable="true"]',
    '[contenteditable="true"][aria-label]',
    'form textarea',
    'textarea',
)
# Send button (blue up arrow). Enter key is the fallback.
CHAT_SUBMIT_SELECTORS = (
    'button[data-testid="chat-submit"]',
    'button[type="submit"]',
    'button[aria-label="Submit"]',
    'button[aria-label="提交"]',
    'button[aria-label="Send"]',
    'button[aria-label="发送"]',
)
# Visible while Grok is still streaming the answer.
CHAT_STOP_SELECTORS = (
    'button[aria-label="Stop model response"]',
    'button[aria-label*="Stop"]',
    'button[aria-label*="停止"]',
)
# Every chat turn is a div[id^="response-"]. The user's turn has class items-end and an
# "Edit" button; Grok's turn has items-start. Grok's answer text lives in
# .response-content-markdown (the "worked for 8s" thinking header sits outside it).
CHAT_TURN_SEL = 'div[id^="response-"]'
CHAT_REPLY_TEXT_SEL = '.response-content-markdown'
# Copy button in the action row under Grok's reply (copy / link / like / dislike /
# regenerate / more). The user's own message has a plain "复制"/"Copy" button, so the
# reply's labels are matched first and the search is scoped to the reply's own turn.
CHAT_REPLY_COPY_LABELS = ("复制响应", "Copy response", "Copy", "复制")
CHAT_REPLY_JS = """() => {
  const turns = [...document.querySelectorAll('div[id^="response-"]')].filter((r) =>
    !/(^|\\s)items-end(\\s|$)/.test(String(r.className)) && !r.querySelector('button[aria-label="Edit"]'));
  const last = turns[turns.length - 1];
  if (!last) return {count: 0, id: '', text: ''};
  const md = last.querySelectorAll('.response-content-markdown');
  let text = '';
  if (md.length) {
    text = [...md].map((e) => e.innerText || e.textContent || '').join('\\n');
  } else {
    const bub = last.querySelector('.message-bubble') || last;
    const clone = bub.cloneNode(true);
    clone.querySelectorAll('.thinking-container, button').forEach((e) => e.remove());
    text = clone.innerText || clone.textContent || '';
  }
  return {count: turns.length, id: last.id, text: text.trim()};
}"""
# Logged-out grok.com: shows 登录/注册 and a "sign up to continue" card instead of answering.
LOGGED_OUT_JS = """() => {
  const t = (document.body && document.body.innerText) || '';
  if (/注册以无缝继续|Sign up to continue|Sign in to continue/i.test(t)) return true;
  return [...document.querySelectorAll('a[href*="sign-in"], a[href*="/login"], a[href*="accounts.x.ai"]')]
    .some((a) => a.getBoundingClientRect().width > 0);
}"""
CHAT_TIMEOUT_S = 10 * 60
CHAT_STABLE_POLLS = 3          # text unchanged this many polls in a row (and no stop button) = done
CHAT_POLL_S = 1.5

# ---- grok.com/imagine ----
# Composer, file input and submit come from cli.browser_tasks (GROK_EDITOR_SEL, GROK_FILE_INPUT_SEL,
# _GROK_FIND_SUBMIT_BUTTON_JS ...). Output image = biggest <img> outside the composer that was not
# there before submit.
IMAGINE_OUTPUT_IMAGES_JS = """() => {
  const composer = document.querySelector('[data-testid="chat-input"]');
  return [...document.querySelectorAll('img')].filter((img) => {
    if (!img.src || (composer && composer.contains(img))) return false;
    const r = img.getBoundingClientRect();
    return r.width > 120 && r.height > 120 && img.complete && img.naturalWidth > 0;
  }).sort((a, b) => {
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    return rb.width * rb.height - ra.width * ra.height;
  }).map((img) => img.currentSrc || img.src);
}"""
FETCH_AS_B64_JS = """async (src) => {
  const r = await fetch(src, {credentials: 'include'});
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const buf = new Uint8Array(await r.arrayBuffer());
  let s = '';
  for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return btoa(s);
}"""
IMAGINE_TIMEOUT_S = 6 * 60

Status = Optional[Callable[[str], None]]


def _bt():
    from cli import browser_tasks
    return browser_tasks


def _say(status: Status, msg: str) -> None:
    print(f"[grok_cdp] {msg}")
    if status:
        try:
            status(msg)
        except Exception:
            pass


def ensure_chrome(status: Status = None) -> int:
    """Return the CDP port, launching Chrome with the HermesChromeCDP profile when 9222 is closed."""
    bt = _bt()
    if bt.cdp_ready(CDP_PORT):
        return CDP_PORT
    if not os.path.isfile(CHROME_EXE):
        raise RuntimeError(f"找不到 Chrome: {CHROME_EXE}")
    _say(status, f"启动 Chrome (端口 {CDP_PORT}) …")
    subprocess.Popen(
        [CHROME_EXE, f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={CHROME_USER_DATA_DIR}", GROK_CHAT_URL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + CHROME_LAUNCH_WAIT_S
    while time.monotonic() < deadline:
        if bt.cdp_ready(CDP_PORT):
            return CDP_PORT
        time.sleep(1.0)
    raise RuntimeError(
        f"Chrome 端口 {CDP_PORT} 没有打开。如果 HermesChromeCDP 的 Chrome 已经开着但没带 "
        "--remote-debugging-port=9222，请先关掉它再试。"
    )


def _first(page, selectors, *, visible=True):
    for sel in selectors:
        loc = page.locator(sel)
        try:
            n = loc.count()
        except Exception:
            continue
        for i in range(n):
            item = loc.nth(i)
            try:
                if not visible or item.is_visible():
                    return item
            except Exception:
                continue
    return None


def _page_for(ctx, url_part: str, exclude: str = ""):
    for p in ctx.pages:
        u = p.url or ""
        if url_part in u and not (exclude and exclude in u):
            return p
    return ctx.new_page()


def _reply_state(page) -> dict:
    """{count, id, text} for Grok's newest reply (assistant turns only)."""
    try:
        return page.evaluate(CHAT_REPLY_JS) or {"count": 0, "id": "", "text": ""}
    except Exception:
        return {"count": 0, "id": "", "text": ""}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _copy_matches(copied: str, dom_text: str) -> bool:
    """Copy-button text (markdown) vs DOM innerText: same start/end and similar length."""
    a, b = _norm(copied), _norm(dom_text)
    if not a or not b:
        return False
    if not (0.8 <= len(a) / len(b) <= 1.3):
        return False
    strip = lambda t: re.sub(r"[`*_#>\-]", "", t)
    a, b = strip(a), strip(b)
    return a[:15] == b[:15] and a[-15:] == b[-15:]


def _logged_out(page) -> bool:
    try:
        return bool(page.evaluate(LOGGED_OUT_JS))
    except Exception:
        return False


def _stop_visible(page) -> bool:
    return _first(page, CHAT_STOP_SELECTORS) is not None


def _copy_last_response(page, reply: dict) -> str:
    """Scroll Grok's last reply into view, click the copy button in ITS action row,
    wait for the clipboard to leave a sentinel, and accept it only if it matches the
    reply's DOM text. Returns '' when the copy can't be trusted (caller uses DOM text)."""
    bt = _bt()
    turn_id = (reply or {}).get("id") or ""
    dom_text = (reply or {}).get("text") or ""
    if not turn_id:
        return ""
    turn = page.locator(f'[id="{turn_id}"]')
    try:
        turn.evaluate("(e) => e.scrollIntoView({block: 'end'})")
        time.sleep(0.4)
        turn.hover(timeout=3000)
    except Exception as exc:
        print(f"[grok_cdp] scroll/hover reply failed: {exc}")
    btn = None
    for label in CHAT_REPLY_COPY_LABELS:
        loc = turn.locator(f'button[aria-label="{label}"]')
        try:
            if loc.count():
                btn = loc.last
                break
        except Exception:
            continue
    if btn is None:
        print("[grok_cdp] copy button not found in reply action row")
        return ""
    sentinel = f"__grok_cdp_{time.time()}__"
    try:
        bt.write_windows_clipboard(sentinel)
    except Exception as exc:
        print(f"[grok_cdp] clipboard unavailable ({exc}); using DOM text")
        return ""
    try:
        btn.scroll_into_view_if_needed(timeout=3000)
        btn.click(timeout=5000)
    except Exception as exc:
        print(f"[grok_cdp] copy click failed: {exc}")
        return ""
    for _ in range(20):
        time.sleep(0.25)
        try:
            text = bt.read_windows_clipboard() or ""
        except Exception:
            text = ""
        if text and text != sentinel:
            text = text.strip()
            if _copy_matches(text, dom_text):
                return text
            print(f"[grok_cdp] copied text does not match reply ({len(text)} vs {len(dom_text)} chars); using DOM text")
            return ""
    print("[grok_cdp] clipboard never changed after copy click; using DOM text")
    return ""


def extract_last_reply(status: Status = None) -> str:
    """Re-read Grok's last reply on the open grok.com/c/ tab (no new prompt)."""
    port = ensure_chrome(status)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = _page_for(ctx, "grok.com/c/")
        reply = _reply_state(page)
        return _copy_last_response(page, reply) or reply.get("text") or ""


def ask_text(prompt: str, status: Status = None) -> str:
    """Send ``prompt`` to a new grok.com chat and return the reply text."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("提示词是空的")
    port = ensure_chrome(status)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = _page_for(ctx, "grok.com", exclude="/imagine")
        page.bring_to_front()
        _say(status, "打开 grok.com 新对话 …")
        page.goto(GROK_CHAT_URL, wait_until="domcontentloaded", timeout=45_000)
        editor = None
        deadline = time.monotonic() + 25
        while editor is None and time.monotonic() < deadline:
            editor = _first(page, CHAT_INPUT_SELECTORS)
            if editor is None:
                time.sleep(0.5)
        if _logged_out(page):
            raise RuntimeError("Chrome 里的 grok.com 没有登录，请先在这个 Chrome (端口 9222) 里登录 Grok")
        if editor is None:
            raise RuntimeError("找不到 Grok 输入框")
        _say(status, f"粘贴提示词 ({len(prompt)} 字) …")
        time.sleep(1.5)  # editor shows up before the page is hydrated; typing too early is lost
        probe = prompt[:20].strip()
        for _attempt in range(3):
            editor = _first(page, CHAT_INPUT_SELECTORS) or editor
            editor.click(timeout=8000)
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.keyboard.insert_text(prompt)
            time.sleep(0.8)
            try:
                got = editor.inner_text(timeout=3000) or editor.input_value(timeout=1000)
            except Exception:
                got = ""
            if probe in (got or "").replace("\n", " ") or probe.split()[0] in (got or ""):
                break
            time.sleep(1.5)
        else:
            raise RuntimeError("提示词没有贴进 Grok 输入框")
        before = int(_reply_state(page).get("count") or 0)
        btn = _first(page, CHAT_SUBMIT_SELECTORS)
        clicked = False
        if btn is not None:
            for _ in range(20):  # aria-disabled="true" until the editor content registers
                try:
                    if btn.get_attribute("aria-disabled") != "true" and btn.is_enabled():
                        btn.click(timeout=8000)
                        clicked = True
                        break
                except Exception:
                    pass
                time.sleep(0.5)
        if not clicked:
            editor.click(timeout=5000)
            page.keyboard.press("Enter")
        _say(status, "等待 Grok 回答 …")
        started = time.monotonic()
        last, same, reply = "", 0, {}
        while time.monotonic() - started < CHAT_TIMEOUT_S:
            time.sleep(CHAT_POLL_S)
            if _logged_out(page):
                raise RuntimeError("Chrome 里的 grok.com 没有登录，请先在这个 Chrome (端口 9222) 里登录 Grok")
            reply = _reply_state(page)
            text = reply.get("text") or ""
            if int(reply.get("count") or 0) <= before or not text:
                continue
            if text == last and not _stop_visible(page):
                same += 1
                if same >= CHAT_STABLE_POLLS:
                    break
            else:
                same = 0
                last = text
            _say(status, f"等待 Grok 回答 … {int(time.monotonic() - started)}s, {len(text)} 字")
        else:
            raise RuntimeError("Grok 回答超时")
        _say(status, "拷贝回答 …")
        copied = _copy_last_response(page, reply)
        return copied or last


def _fetch_image_bytes(page, ctx, src: str) -> bytes:
    if src.startswith("data:"):
        return base64.b64decode(src.split(",", 1)[1])
    try:
        return base64.b64decode(page.evaluate(FETCH_AS_B64_JS, src))
    except Exception as exc:
        print(f"[grok_cdp] in-page fetch failed ({exc}); trying requests")
    import requests
    r = requests.get(src, cookies=_bt()._grok_cdp_cookies_for_download(ctx), timeout=120)
    r.raise_for_status()
    return r.content


def _imagine_page(ctx, *, want_image: bool):
    """Imagine tab: the one whose composer already holds an image when ``want_image``."""
    bt = _bt()
    pages = [p for p in ctx.pages if "grok.com/imagine" in (p.url or "")]
    if want_image:
        for p in pages:
            if bt._grok_composer_has_image_page(p):
                return p
        return None
    return pages[0] if pages else None


def prepare_imagine(image_path: str, status: Status = None) -> None:
    """Open/reuse a Grok Imagine tab and attach ``image_path`` to its composer. Does NOT submit."""
    from PIL import Image

    bt = _bt()
    if not image_path or not os.path.isfile(image_path):
        raise RuntimeError(f"找不到输入图片: {image_path}")
    port = ensure_chrome(status)
    from playwright.sync_api import sync_playwright

    tmp_png = Path(os.environ.get("TEMP", ".")) / f"grok_cdp_in_{int(time.time())}.png"
    with Image.open(image_path) as im:
        im.convert("RGB").save(tmp_png, "PNG")
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _imagine_page(ctx, want_image=False) or ctx.new_page()
            page.bring_to_front()
            _say(status, "打开 Grok Imagine …")
            page.goto(GROK_IMAGINE_URL, wait_until="domcontentloaded", timeout=45_000)
            if _logged_out(page):
                raise RuntimeError("Chrome 里的 grok.com 没有登录，请先在这个 Chrome (端口 9222) 里登录 Grok")
            _say(status, "上传图片 …")
            if not bt._grok_paste_cover_image_cdp(page, tmp_png):
                raise RuntimeError("图片没有贴进 Grok Imagine 输入框")
    finally:
        try:
            tmp_png.unlink()
        except OSError:
            pass


def run_imagine(prompt: str, status: Status = None):
    """Use the already-prepared Imagine tab: add prompt, submit, wait, return the new image (PIL)."""
    from PIL import Image

    bt = _bt()
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("提示词是空的")
    port = ensure_chrome(status)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = _imagine_page(ctx, want_image=True)
        if page is None:
            raise RuntimeError("没找到已贴好图片的 Grok Imagine 标签，请先发图片（grokprep）")
        page.bring_to_front()
        _say(status, "粘贴提示词 …")
        bt._grok_paste_prompt_cdp(page, prompt, append=True)
        try:
            bt._grok_click_image_mode_cdp(page)
        except Exception as exc:
            print(f"[grok_cdp] image mode click skipped: {exc}")
        old = set(page.evaluate(IMAGINE_OUTPUT_IMAGES_JS) or [])
        _say(status, "提交生成 …")
        bt._grok_click_generate_cdp(page, deep_image=False)
        _say(status, "等待生成图片 …")
        bt._grok_wait_image_ready_cdp(page, timeout_s=IMAGINE_TIMEOUT_S)
        srcs = [s for s in (page.evaluate(IMAGINE_OUTPUT_IMAGES_JS) or []) if s not in old]
        if not srcs:
            raise RuntimeError("没找到生成的图片")
        _say(status, "下载生成的图片 …")
        data = _fetch_image_bytes(page, ctx, srcs[0])
        img = Image.open(io.BytesIO(data))
        img.load()
        return img


def make_image(prompt: str, image_path: str, status: Status = None):
    """Grok Imagine: attach ``image_path`` + ``prompt``, generate, return a PIL Image."""
    prepare_imagine(image_path, status)
    return run_imagine(prompt, status)


# ---- cross-process lock: the Telegram bot and the app share one Chrome ----
# %LOCALAPPDATA%\AIComposer\grok_cdp.lock is held while one grok_cdp operation runs.
# Waits up to LOCK_WAIT_S, then raises so the caller falls back to manual.
import threading as _threading

LOCK_WAIT_S = float(getattr(config, "GROK_CDP_LOCK_WAIT_S", 120) or 120)
LOCK_PATH = os.path.join(os.environ.get("LOCALAPPDATA") or str(Path.home()), "AIComposer", "grok_cdp.lock")
_local_lock = _threading.RLock()
_held = {"depth": 0, "fh": None}


def _try_file_lock(fh) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock_file(fh) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        fh.close()
    except OSError:
        pass


class chrome_lock:
    """Re-entrant within this process (make_image -> prepare_imagine), exclusive across processes."""

    def __init__(self, wait_s: float | None = None, status: Status = None):
        self.wait_s = LOCK_WAIT_S if wait_s is None else float(wait_s)
        self.status = status

    def __enter__(self):
        deadline = time.monotonic() + self.wait_s
        if not _local_lock.acquire(timeout=max(0.0, self.wait_s)):
            raise RuntimeError(f"Chrome 正被本程序的另一个 Grok 任务占用，等了 {self.wait_s:.0f} 秒")
        if _held["depth"] > 0:
            _held["depth"] += 1
            return self
        try:
            os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
            told = False
            while True:
                fh = open(LOCK_PATH, "a+b")
                if _try_file_lock(fh):
                    _held["fh"] = fh
                    _held["depth"] = 1
                    return self
                fh.close()
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"Chrome 正被另一个程序（如 Telegram 机器人）占用，等了 {self.wait_s:.0f} 秒"
                    )
                if not told:
                    _say(self.status, "Chrome 正忙（另一个 Grok 任务），排队等待 …")
                    told = True
                time.sleep(0.5)
        except BaseException:
            _local_lock.release()
            raise

    def __exit__(self, *_exc):
        _held["depth"] -= 1
        if _held["depth"] == 0 and _held["fh"] is not None:
            _unlock_file(_held["fh"])
            _held["fh"] = None
        _local_lock.release()
        return False


def _locked(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with chrome_lock(status=kwargs.get("status")):
            return fn(*args, **kwargs)

    return wrapper


ask_text = _locked(ask_text)
extract_last_reply = _locked(extract_last_reply)
prepare_imagine = _locked(prepare_imagine)
run_imagine = _locked(run_imagine)
make_image = _locked(make_image)
