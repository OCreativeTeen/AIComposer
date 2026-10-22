"""Grok in Chrome over CDP, for the manual LLM window's "CLI自动" button.

Text:  grok.com chat -> paste prompt -> submit -> wait -> copy last response.
Image: grok.com/imagine -> attach image + prompt -> submit -> wait -> fetch output image.

Chrome connection reuses ``cli.browser_tasks`` (same approach as the CLI):
connect over CDP on port 9222. When nothing answers on 9222 we launch Chrome
the way the user does by hand:

    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        --remote-debugging-port=9222
        --user-data-dir="%LOCALAPPDATA%\\HermesChromeCDP"

That user-data-dir already holds the logged-in Grok profile (see CHROME_PROFILES_JSON in .env);
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
# The logged-in Grok profile lives in this user-data-dir (HermesChromeCDP).
CHROME_USER_DATA_DIR = (getattr(config, "CHROME_CDP_USER_DATA_DIR", "") or "").strip() or os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local"), "HermesChromeCDP"
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
IMAGINE_DONE_TIMEOUT_S = 180
IMAGINE_SUBMIT_CONFIRM_S = 15

# Real DOM (grok.com/imagine, Oct 2026; dump in %TEMP%\\mpp\\grok_imagine_dom.json):
# - editor: [data-testid="chat-input"] div.ProseMirror[contenteditable], placeholder
#   "描述你的编辑内容，输入 @ 引用图片"
# - submit: the round arrow button right of the editor; on a post page aria-label="编辑"
#   (disabled while the editor is empty). Other builds: Submit / 提交 / Send / 发送.
# - finished post: URL /imagine/post/<id>; canvas <img> inside [data-testid="drop-ui"]
# - left filmstrip: button[aria-label="Thumbnail N"] (N=1 is the input; the highest N is
#   the newest generation). Focus stays on Thumbnail 1 after generate until clicked.
# - focused NEW result src: .../generated/<uuid>/image.jpg (not .../<postId>/content)
# - action row: 赞 / 踩 / 点赞 / 在 X 上发布 / 复制图像 / 下载 / 更多选项
IMAGINE_SUBMIT_LABELS = ("编辑", "Edit", "Submit", "提交", "Send", "发送", "生成", "Generate", "生成视频", "Generate video")

# Video mode (read-only DOM check, Oct 2026), all next to the composer:
# - mode: button[role="radio"][aria-label="视频"] (image: aria-label="图片")
# - resolution: button[aria-label="视频分辨率"][aria-haspopup="menu"] -> [role="menuitemradio"] "480p|720p|1080p"
# - duration:   button[aria-label="视频时长"][aria-haspopup="menu"]   -> [role="menuitemradio"] "6s|10s|15s"
# - (also 视频音频 toggle, 宽高比 menu)
IMAGINE_VIDEO_MODE_LABELS = ("视频", "Video")
IMAGINE_VIDEO_RES_LABELS = ("视频分辨率", "Video resolution", "Resolution")
IMAGINE_VIDEO_DUR_LABELS = ("视频时长", "Video duration", "Duration")
IMAGINE_VIDEO_TIMEOUT_S = 15 * 60

IMAGINE_VIDEO_STATE_JS = """() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const drop = document.querySelector('[data-testid="drop-ui"]') || document.body;
  const vids = [...drop.querySelectorAll('video')].filter(vis).sort((a, b) => {
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    return rb.width * rb.height - ra.width * ra.height;
  });
  const v = vids[0] || null;
  let src = v ? (v.currentSrc || v.src || '') : '';
  if (v && !src) { const s = v.querySelector('source'); src = s ? (s.src || '') : ''; }
  const m = location.pathname.match(/\\/imagine\\/post\\/([^/?#]+)/);
  const progress = [...drop.querySelectorAll('[role="progressbar"], [aria-busy="true"], [class*="shimmer"], [class*="animate-pulse"], [class*="animate-spin"]')].some(vis)
    || /正在生成|生成中|Generating|\\b\\d{1,2}%/i.test(drop.innerText || '');
  const thumbs = [...document.querySelectorAll('button[aria-label^="Thumbnail"]')].filter(vis).length;
  const dl = [...document.querySelectorAll('button')].some((b) => vis(b) && ['下载', 'Download'].includes((b.getAttribute('aria-label') || '').trim()));
  return {url: location.href, postId: m ? m[1] : '', src, ready: !!(v && (v.readyState >= 2 || v.duration > 0) && !v.error),
          duration: v ? (v.duration || 0) : 0, vw: v ? v.videoWidth : 0, vh: v ? v.videoHeight : 0,
          progress, thumbCount: thumbs, download: dl};
}"""
IMAGINE_COPY_LABELS = ("复制图像", "Copy image")
IMAGINE_DOWNLOAD_LABELS = ("下载", "Download")

IMAGINE_FIND_SUBMIT_JS = """(labels) => {
  const input = document.querySelector('[data-testid="chat-input"]');
  if (!input) return null;
  const ed = input.querySelector('[contenteditable="true"]') || input;
  const er = ed.getBoundingClientRect();
  const vis = (b) => { const r = b.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  let scope = input;
  for (let i = 0; i < 4 && scope.parentElement; i++) scope = scope.parentElement;
  const cands = [...scope.querySelectorAll('button')].filter(vis).filter((b) => {
    const a = (b.getAttribute('aria-label') || '').trim();
    return labels.includes(a) || b.type === 'submit';
  }).map((b) => ({b, r: b.getBoundingClientRect()}))
    .filter(({r}) => r.left >= er.left + er.width * 0.5 && Math.abs((r.top + r.height / 2) - (er.top + er.height / 2)) < 80)
    .sort((x, y) => y.r.left - x.r.left);
  if (!cands.length) return null;
  const {b, r} = cands[0];
  b.setAttribute('data-grok-cdp-submit', '1');
  return {aria: b.getAttribute('aria-label') || '', disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true',
          x: r.left + r.width / 2, y: r.top + r.height / 2};
}"""

IMAGINE_STATE_JS = """(args) => {
  const [copyLabels, downloadLabels] = args;
  const input = document.querySelector('[data-testid="chat-input"]');
  const ed = input && (input.querySelector('[contenteditable="true"]') || input);
  const editorText = ed ? (ed.innerText || '').trim() : '';
  const m = location.pathname.match(/\\/imagine\\/post\\/([^/?#]+)/);
  const postId = m ? m[1] : '';
  const drop = document.querySelector('[data-testid="drop-ui"]');
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  let img = null;
  if (drop) {
    img = [...drop.querySelectorAll('img')].filter(vis).sort((a, b) => {
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      return rb.width * rb.height - ra.width * ra.height;
    })[0] || null;
  }
  const src = img ? (img.currentSrc || img.src || '') : '';
  const area = drop || document.body;
  const progress = [...area.querySelectorAll('[role="progressbar"], [aria-busy="true"], [class*="shimmer"], [class*="animate-pulse"], [class*="animate-spin"]')].some(vis)
    || /正在生成|生成中|Generating|\\b\\d{1,2}%/i.test((drop && drop.innerText) || '');
  const btn = (labels) => [...document.querySelectorAll('button')].find((b) => vis(b) && labels.includes((b.getAttribute('aria-label') || '').trim()));
  const copyBtn = btn(copyLabels), dlBtn = btn(downloadLabels);
  const rowOk = !!(copyBtn && dlBtn && copyBtn.parentElement === dlBtn.parentElement);
  const thumbs = [...document.querySelectorAll('button[aria-label^="Thumbnail"]')].filter(vis).map((b) => {
    const a = (b.getAttribute('aria-label') || '').trim();
    const n = parseInt(a.replace(/\\D/g, ''), 10) || 0;
    return {n, aria: a, ring: /(?:^|\\s)ring-2(?:\\s|$)/.test(String(b.className))};
  }).sort((a, b) => a.n - b.n);
  const generated = /\\/generated\\//.test(src);
  return {url: location.href, postId, editorText, src, nw: img ? img.naturalWidth : 0, nh: img ? img.naturalHeight : 0,
          complete: img ? img.complete : false, progress, actionRow: rowOk, copyEnabled: !!(copyBtn && !copyBtn.disabled),
          thumbCount: thumbs.length, newestThumb: thumbs.length ? thumbs[thumbs.length - 1].n : 0,
          focusedGenerated: generated};
}"""

IMAGINE_FOCUS_NEWEST_THUMB_JS = """() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const thumbs = [...document.querySelectorAll('button[aria-label^="Thumbnail"]')].filter(vis)
    .map((b) => ({b, n: parseInt((b.getAttribute('aria-label') || '').replace(/\\D/g, ''), 10) || 0}))
    .filter((t) => t.n > 0).sort((a, b) => a.n - b.n);
  if (!thumbs.length) return {ok: false, reason: 'no-thumbs'};
  const newest = thumbs[thumbs.length - 1];
  newest.b.click();
  return {ok: true, n: newest.n, count: thumbs.length};
}"""

IMAGINE_CLICK_COPY_JS = """(args) => {
  const [copyLabels, downloadLabels] = args;
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const dl = [...document.querySelectorAll('button')].find((b) => vis(b) && downloadLabels.includes((b.getAttribute('aria-label') || '').trim()));
  const row = dl ? dl.parentElement : document;
  const c = [...row.querySelectorAll('button')].find((b) => vis(b) && copyLabels.includes((b.getAttribute('aria-label') || '').trim()));
  if (!c || c.disabled) return false;
  c.click();
  return true;
}"""

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


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return (urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def site_page(ctx, host: str, url: str = "", *, close_duplicates: bool = True, front: bool = True):
    """每个站点只用一个常驻标签页：找到 host 相同的第一个标签复用，没有才新建（并打开 ``url``）。

    ``close_duplicates``：同一 host 的多余标签关掉（只关这个 host，绝不碰别的网站）。
    复用的标签从不关闭。
    """
    host = (host or "").lower()
    same = [p for p in ctx.pages if _host_of(p.url) == host]
    page = same[0] if same else None
    if close_duplicates:
        for extra in same[1:]:
            try:
                extra.close()
                print(f"[grok_cdp] closed duplicate {host} tab")
            except Exception:
                pass
    if page is None:
        page = ctx.new_page()
        if url:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    if front:
        try:
            page.bring_to_front()
        except Exception:
            pass
    return page


def _page_for(ctx, url_part: str, exclude: str = ""):
    for p in ctx.pages:
        u = p.url or ""
        if url_part in u and not (exclude and exclude in u):
            return p
    if "grok.com" in url_part:
        return site_page(ctx, "grok.com")  # 复用唯一的 Grok 标签（调用方再 goto）
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


IMAGINE_MAX_INPUT_IMAGES = 5  # xAI docs: image edit takes up to 5 source images

# Count the attachment thumbnails in the Imagine composer (one per attached input image).
IMAGINE_COMPOSER_IMAGE_COUNT_JS = """() => {
  const chat = document.querySelector('[data-testid="chat-input"]');
  let root = chat;
  for (let up = 0; up < 8 && root && root.parentElement; up++) {
    if (root.querySelector('button[aria-label="Remove image"], button[aria-label*="Remove"]')) break;
    root = root.parentElement;
  }
  root = root || document;
  const removes = root.querySelectorAll('button[aria-label="Remove image"]');
  if (removes.length) return removes.length;
  let n = 0;
  for (const img of root.querySelectorAll('img')) {
    const src = img.currentSrc || img.src || '';
    if (!/^(blob:|data:image)/i.test(src)) continue;
    const r = img.getBoundingClientRect();
    if (r.width >= 20 && r.height >= 20) n++;
  }
  return n;
}"""


def _composer_image_count(page) -> int:
    try:
        return int(page.evaluate(IMAGINE_COMPOSER_IMAGE_COUNT_JS) or 0)
    except Exception as exc:
        print(f"[grok_cdp] composer image count probe failed: {exc}")
        return -1


def _attach_more_images(page, pngs: list, status: Status) -> None:
    """Attach extra input images one at a time (keeps their order), waiting for each thumbnail to appear."""
    bt = _bt()
    for n, png in enumerate(pngs, start=2):
        before = _composer_image_count(page)
        _say(status, f"上传第 {n} 张图 …")
        done = False
        for sel in (bt.GROK_FILE_INPUT_SEL, 'input[type="file"]'):
            loc = page.locator(sel)
            if loc.count() < 1:
                continue
            loc.first.set_input_files(str(png), timeout=20_000)
            done = True
            break
        if not done:
            raise RuntimeError(f"第 {n} 张图没有地方上传（找不到文件输入框）")
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            now = _composer_image_count(page)
            if before < 0 or now < 0 or now > before:
                break
            time.sleep(0.4)
        else:
            raise RuntimeError(f"第 {n} 张图没有出现在 Grok Imagine 输入框里（仍是 {before} 张），没有提交")
    total = _composer_image_count(page)
    if total >= 0 and total != len(pngs) + 1:
        print(f"[grok_cdp] composer shows {total} images, expected {len(pngs) + 1}")
        if total < len(pngs) + 1:
            raise RuntimeError(f"Grok Imagine 输入框里只有 {total} 张图，应有 {len(pngs) + 1} 张，没有提交")


def prepare_imagine(image_path, status: Status = None) -> None:
    """Open/reuse a Grok Imagine tab and attach the input image(s) to its composer, in order. Does NOT submit.

    ``image_path`` is one path or a list of paths (base picture first, then reference portraits; at most 5).
    """
    from PIL import Image

    bt = _bt()
    paths = [image_path] if isinstance(image_path, str) else [p for p in (image_path or []) if p]
    if not paths:
        raise RuntimeError("没有输入图片")
    if len(paths) > IMAGINE_MAX_INPUT_IMAGES:
        raise RuntimeError(f"Grok Imagine 最多 {IMAGINE_MAX_INPUT_IMAGES} 张输入图，这次有 {len(paths)} 张")
    for one in paths:
        if not os.path.isfile(one):
            raise RuntimeError(f"找不到输入图片: {one}")
    image_path = paths[0]
    port = ensure_chrome(status)
    from playwright.sync_api import sync_playwright

    stamp = int(time.time())
    tmp_pngs = []
    for k, one in enumerate(paths, start=1):
        tmp = Path(os.environ.get("TEMP", ".")) / f"grok_cdp_in_{stamp}_{k}.png"
        with Image.open(one) as im:
            im.convert("RGB").save(tmp, "PNG")
        tmp_pngs.append(tmp)
    tmp_png = tmp_pngs[0]
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _imagine_page(ctx, want_image=False) or site_page(ctx, "grok.com")
            page.bring_to_front()
            _say(status, "打开 Grok Imagine …")
            page.goto(GROK_IMAGINE_URL, wait_until="domcontentloaded", timeout=45_000)
            if _logged_out(page):
                raise RuntimeError("Chrome 里的 grok.com 没有登录，请先在这个 Chrome (端口 9222) 里登录 Grok")
            _say(status, "上传图片 …" if len(tmp_pngs) == 1 else f"上传第 1 / {len(tmp_pngs)} 张图 …")
            if not bt._grok_paste_cover_image_cdp(page, tmp_png):
                raise RuntimeError("图片没有贴进 Grok Imagine 输入框")
            if len(tmp_pngs) > 1:
                _attach_more_images(page, tmp_pngs[1:], status)
    finally:
        for tmp in tmp_pngs:
            try:
                tmp.unlink()
            except OSError:
                pass


def _imagine_state(page) -> dict:
    try:
        return page.evaluate(IMAGINE_STATE_JS, [list(IMAGINE_COPY_LABELS), list(IMAGINE_DOWNLOAD_LABELS)]) or {}
    except Exception as exc:
        print(f"[grok_cdp] imagine state probe failed: {exc}")
        return {}


def _imagine_submitted(st: dict, before: dict) -> bool:
    """Submit counts as done once the prompt left the editor, the URL moved to a new post, or a progress
    indicator shows. The arrow button may vanish while generating, so it is not required."""
    if not st:
        return False
    if st.get("postId") and st.get("postId") != before.get("postId"):
        return True
    if st.get("progress"):
        return True
    return bool(before.get("editorText")) and not st.get("editorText")


def _imagine_submit(page, status: Status) -> None:
    before = _imagine_state(page)
    pt = None
    try:
        pt = page.evaluate(IMAGINE_FIND_SUBMIT_JS, list(IMAGINE_SUBMIT_LABELS))
    except Exception as exc:
        print(f"[grok_cdp] submit probe failed: {exc}")
    if pt and not pt.get("disabled"):
        _say(status, f"提交生成（{pt.get('aria') or 'submit'}）…")
        try:
            page.locator('button[data-grok-cdp-submit="1"]').first.click(timeout=5000)
        except Exception:
            page.mouse.click(pt["x"], pt["y"])
    else:
        # Fallback: the old multi-strategy helper. It raises when it cannot *see* generation start,
        # which is not proof that nothing was submitted, so check the page before giving up.
        try:
            _bt()._grok_click_generate_cdp(page, deep_image=False)
            return
        except Exception as exc:
            if _imagine_submitted(_imagine_state(page), before):
                print(f"[grok_cdp] submit helper said {exc!r}, but the page shows it was submitted")
                return
            raise
    deadline = time.monotonic() + IMAGINE_SUBMIT_CONFIRM_S
    while time.monotonic() < deadline:
        if _imagine_submitted(_imagine_state(page), before):
            return
        time.sleep(0.5)
    # Never click a second time: a double submit would make two generations.
    raise RuntimeError("点了提交，但 15 秒内没看到开始生成（提示词还在输入框里）")


def _imagine_wait_done(page, old_srcs: set, status: Status, timeout_s: float = IMAGINE_DONE_TIMEOUT_S, *, min_thumbs: int = 0) -> dict:
    """Done when generation finished: no progress, action row present, and either a new filmstrip
    thumbnail appeared or the canvas shows a /generated/ image that was not there before submit.

    Note: after generate, focus often stays on Thumbnail 1 (the input). Its canvas src is
    ``.../<postId>/content``, which is NOT the new result — do not treat that as ready.
    """
    _say(status, "等待生成图片 …")
    started = time.monotonic()
    stable = 0
    last = {}
    while time.monotonic() - started < timeout_s:
        st = _imagine_state(page)
        last = st
        src = st.get("src") or ""
        thumbs_ready = (st.get("thumbCount") or 0) > max(min_thumbs, 1)
        gen_ready = bool(src) and "/generated/" in src and src not in old_srcs and (st.get("nw") or 0) > 0
        ready = (
            st.get("actionRow")
            and not st.get("progress")
            and st.get("complete")
            and (thumbs_ready or gen_ready)
        )
        stable = stable + 1 if ready else 0
        if stable >= 2:
            return st
        time.sleep(1.5)
    raise RuntimeError(
        f"等了 {int(timeout_s)} 秒 Grok 图片还没好（progress={last.get('progress')}, "
        f"thumbs={last.get('thumbCount')}, generated={last.get('focusedGenerated')}）"
    )


def _clipboard_seq() -> int:
    try:
        import ctypes

        return int(ctypes.windll.user32.GetClipboardSequenceNumber())
    except Exception:
        return -1


def _img_fingerprint(img) -> tuple:
    """(size, md5 of a 32x32 RGB thumbnail) — enough to tell input from a new generation."""
    import hashlib
    from PIL import Image as _Image

    if not isinstance(img, _Image.Image):
        return ((0, 0), "")
    rgb = img.convert("RGB")
    small = rgb.resize((32, 32))
    return (rgb.size, hashlib.md5(small.tobytes()).hexdigest())


def _focus_newest_thumbnail(page, status: Status = None, *, reject_fp=None) -> dict:
    """Click the highest Thumbnail N so the canvas and 复制图像 row belong to the NEW result.

    After generate, Grok leaves Thumbnail 1 (input) focused; Thumbnail N (highest) is the new one.
    Retries once if the canvas still looks like the input (``reject_fp``).
    """
    before = _imagine_state(page)
    try:
        info = page.evaluate(IMAGINE_FOCUS_NEWEST_THUMB_JS) or {}
    except Exception as exc:
        print(f"[grok_cdp] focus newest thumb failed: {exc}")
        info = {}
    if not info.get("ok"):
        _say(status, "没有找到左侧缩略图，按当前画面取图")
        return before
    _say(status, f"切到最新缩略图 Thumbnail {info.get('n')} …")
    deadline = time.monotonic() + 8
    st = before
    while time.monotonic() < deadline:
        time.sleep(0.4)
        st = _imagine_state(page)
        src = st.get("src") or ""
        if src and src != (before.get("src") or "") and (st.get("nw") or 0) > 0 and st.get("complete"):
            break
        if st.get("focusedGenerated") and (st.get("nw") or 0) > 0:
            break
    # If still looking like the input, click newest again (sometimes the first click is a no-op).
    if reject_fp is not None and not st.get("focusedGenerated"):
        try:
            page.evaluate(IMAGINE_FOCUS_NEWEST_THUMB_JS)
            time.sleep(0.8)
            st = _imagine_state(page)
        except Exception:
            pass
    return st


def _grab_focused_image(page, st: dict, status: Status = None):
    """复制图像 on the focused canvas, else fetch its src. Returns a PIL Image."""
    from PIL import Image, ImageGrab

    want = (int(st.get("nw") or 0), int(st.get("nh") or 0))
    seq = _clipboard_seq()
    try:
        clicked = page.evaluate(IMAGINE_CLICK_COPY_JS, [list(IMAGINE_COPY_LABELS), list(IMAGINE_DOWNLOAD_LABELS)])
    except Exception as exc:
        clicked = False
        print(f"[grok_cdp] copy-image click failed: {exc}")
    if clicked and seq >= 0:
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if _clipboard_seq() != seq:
                time.sleep(0.3)
                try:
                    clip = ImageGrab.grabclipboard()
                except Exception as exc:
                    print(f"[grok_cdp] clipboard read failed: {exc}")
                    clip = None
                if isinstance(clip, Image.Image) and (not want[0] or clip.size == want or "/generated/" in (st.get("src") or "")):
                    _say(status, "已从「复制图像」拿到结果")
                    clip.load()
                    return clip
                if clip is not None:
                    print(f"[grok_cdp] clipboard image {getattr(clip, 'size', type(clip))} != {want}; fetching src")
                break
            time.sleep(0.2)
    src = st.get("src") or ""
    if not src:
        raise RuntimeError("当前画面没有可下载的图片地址")
    _say(status, "下载生成的图片 …")
    data = _fetch_image_bytes(page, page.context, src)
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def extract_imagine_result(page, st: dict, status: Status = None, *, reject_image=None):
    """Focus the newest filmstrip thumbnail, then copy/download that result.

    ``reject_image`` is the input (or any image that must NOT be returned). If the first grab
    matches it, focus the newest thumbnail again and retry once.
    """
    reject_fp = _img_fingerprint(reject_image) if reject_image is not None else None
    st = _focus_newest_thumbnail(page, status, reject_fp=reject_fp)
    img = _grab_focused_image(page, st, status)
    if reject_fp is not None and _img_fingerprint(img) == reject_fp:
        _say(status, "拿到的是输入图，再切到最新缩略图重试 …")
        st = _focus_newest_thumbnail(page, status, reject_fp=reject_fp)
        img = _grab_focused_image(page, st, status)
        if _img_fingerprint(img) == reject_fp:
            raise RuntimeError("复制/下载到的仍是输入图，不是新生成的结果")
    return img


def fetch_current_imagine_result(status: Status = None):
    """Read-only helper: take the result of the Imagine post page that is open now (no submit)."""
    port = ensure_chrome(status)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = next((pg for pg in ctx.pages if "grok.com/imagine/post/" in (pg.url or "")), None)
        if page is None:
            raise RuntimeError("没有打开的 grok.com/imagine/post/ 页面")
        st = _imagine_wait_done(page, set(), status, timeout_s=20)
        # Prefer the /generated/ result; no input image to reject in this read-only helper.
        return extract_imagine_result(page, st, status)


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
        # Everything visible now (the input image, older results) is "old".
        before_st = _imagine_state(page)
        old = set(page.evaluate(IMAGINE_OUTPUT_IMAGES_JS) or [])
        old.add(before_st.get("src") or "")
        min_thumbs = int(before_st.get("thumbCount") or 0)
        reject = None
        try:
            if before_st.get("src"):
                reject = Image.open(io.BytesIO(_fetch_image_bytes(page, ctx, before_st["src"])))
                reject.load()
        except Exception as exc:
            print(f"[grok_cdp] could not snapshot input image for reject check: {exc}")
        _imagine_submit(page, status)
        st = _imagine_wait_done(page, old, status, min_thumbs=min_thumbs)
        return extract_imagine_result(page, st, status, reject_image=reject)


def _menu_pick(page, trigger_labels, item_text: str, status: Status = None) -> bool:
    """Open a composer popover menu (by aria-label) and pick the menuitemradio whose text starts with ``item_text``."""
    btn = None
    for lab in trigger_labels:
        loc = page.locator(f'button[aria-label="{lab}"]')
        try:
            if loc.count() and loc.first.is_visible():
                btn = loc.first
                break
        except Exception:
            continue
    if btn is None:
        _say(status, f"没找到 {trigger_labels[0]} 按钮")
        return False
    try:
        if (btn.inner_text() or "").strip() == item_text:
            return True
        btn.click(timeout=5000)
        item = page.locator('[role="menuitemradio"]').filter(has_text=item_text).first
        item.click(timeout=5000)
        time.sleep(0.4)
        ok = (btn.inner_text() or "").strip() == item_text
        if not ok:
            page.keyboard.press("Escape")
        return ok
    except Exception as exc:
        print(f"[grok_cdp] menu pick {trigger_labels[0]}={item_text} failed: {exc}")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False


def _set_video_mode(page, resolution: str, duration: str, status: Status = None) -> None:
    clicked = False
    for lab in IMAGINE_VIDEO_MODE_LABELS:
        loc = page.locator(f'button[role="radio"][aria-label="{lab}"]')
        try:
            if loc.count():
                loc.first.click(timeout=5000)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        raise RuntimeError("没找到 Grok Imagine 的「视频」模式按钮")
    time.sleep(0.8)
    if not _menu_pick(page, IMAGINE_VIDEO_RES_LABELS, resolution, status):
        raise RuntimeError(f"没能把视频分辨率设成 {resolution}")
    if not _menu_pick(page, IMAGINE_VIDEO_DUR_LABELS, duration, status):
        raise RuntimeError(f"没能把视频时长设成 {duration}")
    _say(status, f"视频模式：{resolution} · {duration}")


def _video_state(page) -> dict:
    try:
        return page.evaluate(IMAGINE_VIDEO_STATE_JS) or {}
    except Exception as exc:
        print(f"[grok_cdp] video state probe failed: {exc}")
        return {}


def _wait_video_done(page, before: dict, status: Status, timeout_s: float = IMAGINE_VIDEO_TIMEOUT_S) -> dict:
    """Done = new post / new thumbnail, newest thumbnail focused, a playable <video> with a new src, no progress."""
    _say(status, "等待生成视频（可能要几分钟）…")
    started = time.monotonic()
    stable = 0
    last_say = 0.0
    last = {}
    old_src = before.get("src") or ""
    while time.monotonic() - started < timeout_s:
        st = _video_state(page)
        last = st
        moved = (st.get("postId") and st.get("postId") != before.get("postId")) or (
            (st.get("thumbCount") or 0) > (before.get("thumbCount") or 0)
        )
        if moved and not st.get("progress") and not (st.get("src") and st.get("src") != old_src and st.get("ready")):
            # Generation may be finished but focus still on the input thumbnail.
            try:
                page.evaluate(IMAGINE_FOCUS_NEWEST_THUMB_JS)
            except Exception:
                pass
            time.sleep(1.0)
            st = _video_state(page)
            last = st
        ready = bool(st.get("src")) and st.get("src") != old_src and st.get("ready") and not st.get("progress")
        stable = stable + 1 if ready else 0
        if stable >= 2:
            return st
        el = time.monotonic() - started
        if el - last_say >= 30:
            _say(status, f"等待生成视频 … {int(el)} 秒")
            last_say = el
        time.sleep(3.0)
    raise RuntimeError(
        f"等了 {int(timeout_s // 60)} 分钟 Grok 视频还没好（progress={last.get('progress')}, video={bool(last.get('src'))}）"
    )


def _unique_video_path(dest_dir: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(dest_dir, f"grok_video_{stamp}.mp4")
    n = 2
    while os.path.exists(path):
        path = os.path.join(dest_dir, f"grok_video_{stamp}_{n}.mp4")
        n += 1
    return path


def _save_video(page, st: dict, dest_dir: str, status: Status = None) -> str:
    """Fetch the focused <video> src (blob: or https). Fallback: the 下载 button in the action row."""
    path = _unique_video_path(dest_dir)
    src = st.get("src") or ""
    data = b""
    if src:
        try:
            _say(status, "下载生成的视频 …")
            data = base64.b64decode(page.evaluate(FETCH_AS_B64_JS, src))
        except Exception as exc:
            print(f"[grok_cdp] in-page video fetch failed ({exc})")
            if src.startswith("http"):
                try:
                    import requests

                    r = requests.get(src, cookies=_bt()._grok_cdp_cookies_for_download(page.context), timeout=300)
                    r.raise_for_status()
                    data = r.content
                except Exception as exc2:
                    print(f"[grok_cdp] requests video fetch failed ({exc2})")
    if len(data) > 10_000:
        with open(path, "wb") as f:
            f.write(data)
        return path
    _say(status, "用「下载」按钮保存视频 …")
    with page.expect_download(timeout=120_000) as dl_info:
        clicked = page.evaluate(IMAGINE_CLICK_COPY_JS.replace("copyLabels.includes", "downloadLabels.includes"),
                                [list(IMAGINE_DOWNLOAD_LABELS), list(IMAGINE_DOWNLOAD_LABELS)])
        if not clicked:
            raise RuntimeError("没找到视频的「下载」按钮")
    dl_info.value.save_as(path)
    return path


def run_imagine_video(prompt: str, dest_dir: str, status: Status = None, *,
                      resolution: str = "720p", duration: str = "15s") -> str:
    """Prepared Imagine tab (image attached): prompt, 视频 mode 720p/15s, submit, wait, save mp4 → path."""
    bt = _bt()
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("提示词是空的")
    if not dest_dir:
        raise RuntimeError("没有给视频的保存目录")
    port = ensure_chrome(status)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = _imagine_page(ctx, want_image=True)
        if page is None:
            raise RuntimeError("没找到已贴好图片的 Grok Imagine 标签")
        page.bring_to_front()
        _set_video_mode(page, resolution, duration, status)
        _say(status, "粘贴提示词 …")
        bt._grok_paste_prompt_cdp(page, prompt, append=True)
        before = _video_state(page)
        _imagine_submit(page, status)
        st = _wait_video_done(page, before, status)
        path = _save_video(page, st, dest_dir, status)
        _say(status, f"视频已保存：{os.path.basename(path)}")
        return path


def make_video(prompt: str, image_path: str, dest_dir: str, status: Status = None, *,
               resolution: str = "720p", duration: str = "15s") -> str:
    """Grok Imagine image→video: attach ``image_path`` + ``prompt``; returns the saved mp4 path."""
    prepare_imagine(image_path, status)
    return run_imagine_video(prompt, dest_dir, status, resolution=resolution, duration=duration)


def make_image(prompt: str, image_path, status: Status = None):
    """Grok Imagine: attach ``image_path`` (one path, or a list: base picture + reference portraits, in order)
    + ``prompt``, generate, return a PIL Image."""
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
fetch_current_imagine_result = _locked(fetch_current_imagine_result)
run_imagine = _locked(run_imagine)
make_image = _locked(make_image)
run_imagine_video = _locked(run_imagine_video)
make_video = _locked(make_video)
