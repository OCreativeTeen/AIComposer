"""Gemini 网页图生图：和 Grok Imagine 同一条 Chrome（CDP 9222）。

贴图顺序：第一张是基础图，后面是人物参考图。再贴提示词并发送。
生成结束后，点结果图下面的「⋯」→「复制图片」，从剪贴板取回 PIL 图。

在工作线程里调用，不要在 Tk 主线程里调用。
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from typing import Callable, Optional

from utility import grok_cdp

Status = Optional[Callable[[str], None]]
GEMINI_URL = "https://gemini.google.com/app"
MAX_IMAGES = 5
GEN_TIMEOUT_S = 240.0

_COPY_NAME = re.compile(r"复制图片|複製圖片|Copy image", re.I)
_MORE_LABEL = re.compile(
    r"更多选项|更多操作|显示更多|^更多$|More options|More actions|^More$",
    re.I,
)


def _say(status: Status, msg: str) -> None:
    print(f"[gemini_cdp] {msg}")
    if status:
        try:
            status(msg)
        except Exception:
            pass


def _fingerprint(img) -> tuple:
    from PIL import Image

    if not isinstance(img, Image.Image):
        return ((0, 0), "")
    rgb = img.convert("RGB")
    small = rgb.resize((32, 32))
    return (rgb.size, hashlib.md5(small.tobytes()).hexdigest())


def _file_fingerprint(path: str):
    from PIL import Image

    try:
        with Image.open(path) as im:
            im.load()
            return _fingerprint(im)
    except Exception:
        return None


def _clipboard_image():
    from PIL import Image, ImageGrab

    try:
        clip = ImageGrab.grabclipboard()
    except Exception:
        return None
    if clip is None:
        return None
    try:
        if isinstance(clip, list):
            src = next((p for p in clip if isinstance(p, str) and p and os.path.isfile(p)), "")
            if not src:
                return None
            with Image.open(src) as opened:
                opened.load()
                return opened.copy()
        if not hasattr(clip, "copy"):
            return None
        clip.load()
        return clip.copy()
    except Exception:
        return None


def _mark_clipboard() -> None:
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText("gemini-image-pending")
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass


def _context_with_grok(browser):
    """用正在看 Grok 的那个窗口，不要开到另一个 Chrome。"""
    contexts = list(browser.contexts or [])
    for ctx in contexts:
        for pg in list(ctx.pages):
            try:
                if "grok.com" in (pg.url or ""):
                    return ctx, pg
            except Exception:
                continue
    if not contexts:
        return browser.new_context(), None
    ctx = max(contexts, key=lambda c: len(list(c.pages)))
    return ctx, None


def _open_gemini(browser, status: Status):
    """在 Grok 那个 Chrome 里打开 Gemini。不抢前台、不按真实键盘，避免把魔法工作台的窗口挤乱。"""
    ctx, _grok_page = _context_with_grok(browser)
    page = None
    for pg in list(ctx.pages):
        try:
            if "gemini.google.com" in (pg.url or ""):
                page = pg
                break
        except Exception:
            continue
    if page is None:
        _say(status, "在 Grok 那个 Chrome 里新开 Gemini 标签 …")
        page = ctx.new_page()
        page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60_000)
    else:
        _say(status, "使用已经打开的 Gemini 标签 …")
    return page


def _prompt_landed(text: str, prompt: str) -> bool:
    """Quill 会把换行拆成多个 <p>，innerText 比原文多空行。比的时候去掉空白。"""
    body = re.sub(r"\s+", "", text or "")
    want = re.sub(r"\s+", "", (prompt or "").strip())
    if len(want) < 6:
        return bool(want) and want in body
    return want[:30] in body


def _composer_text(page) -> str:
    try:
        return page.evaluate(
            """() => {
                const el = document.querySelector('rich-textarea .ql-editor')
                    || document.querySelector('div.ql-editor[contenteditable="true"]');
                return el ? (el.innerText || '') : '';
            }"""
        ) or ""
    except Exception:
        return ""


def _insert_prompt(page, prompt: str) -> bool:
    """写进 Gemini 的 Quill 输入框。只走页面内部，不点击、不按 Ctrl，避免键盘事件打进魔法工作台。"""
    try:
        ok = page.evaluate(
            """(text) => {
                const el = document.querySelector('rich-textarea .ql-editor')
                    || document.querySelector('div.ql-editor[contenteditable="true"]');
                if (!el) return false;
                el.focus();
                const sel = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(el);
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('insertText', false, text);
                el.blur();
                const got = (el.innerText || '').replace(/\\s+/g, '');
                const want = String(text || '').trim().replace(/\\s+/g, '');
                return want.slice(0, 30).length > 0 && got.includes(want.slice(0, 30));
            }""",
            prompt,
        )
        return bool(ok)
    except Exception as exc:
        print(f"[gemini_cdp] insertText failed: {exc}")
        return False


def _send_prompt(page) -> None:
    clicked = page.evaluate(
        """() => {
            const labels = ['Send message', '发送消息', 'Send', '发送'];
            const buttons = [...document.querySelectorAll('button')];
            const btn = buttons.find((b) => {
                const label = b.getAttribute('aria-label') || '';
                return labels.some((name) => label === name || label.startsWith(name));
            });
            if (!btn || btn.disabled) return false;
            btn.click();
            return true;
        }"""
    )
    if not clicked:
        raise RuntimeError("Gemini 输入框里已经有提示词，但没有找到可点的发送按钮")


def _submit_prompt(page, prompt: str, status: Status) -> None:
    if not _insert_prompt(page, prompt):
        got = re.sub(r"\s+", " ", _composer_text(page)).strip()
        tail = f"（框里现在是：{got[:40]}）" if got else "（输入框是空的）"
        raise RuntimeError(f"提示词没能写进 Gemini 输入框{tail}")
    _say(status, "提示词已写入，发送 …")
    before = _composer_text(page)
    _send_prompt(page)
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        now = re.sub(r"\s+", "", _composer_text(page))
        if len(now) < 12 or not _prompt_landed(now, prompt):
            return
        time.sleep(0.3)
    if _prompt_landed(before, prompt) and _prompt_landed(_composer_text(page), prompt):
        raise RuntimeError("提示词已经在 Gemini 输入框里，但没有发出去。请在那个标签里按一次发送。")


def _new_chat(page) -> None:
    for sel in (
        'button[aria-label*="新对话"]',
        'a[aria-label*="新对话"]',
        'button[aria-label*="New chat" i]',
        'a[aria-label*="New chat" i]',
    ):
        loc = page.locator(sel)
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=3000)
                time.sleep(0.8)
                return
        except Exception:
            continue
    try:
        page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1.0)
    except Exception as exc:
        print(f"[gemini_cdp] new chat skipped: {exc}")


def _image_srcs(page) -> list:
    try:
        return page.evaluate(
            """() => [...document.querySelectorAll('img')].filter((img) => {
                const r = img.getBoundingClientRect();
                return r.width >= 64 && r.height >= 64;
            }).map((img) => (img.currentSrc || img.src || ''))"""
        ) or []
    except Exception:
        return []


_FILE_INPUT_SELECTORS = (
    'input[type="file"][accept*="image"]',
    'input[type="file"]',
)

_UPLOAD_MENU_BUTTONS = (
    'button[aria-label*="打开上传文件菜单"]',
    'button[aria-label*="Open upload file menu" i]',
    'button[aria-label*="上传文件菜单"]',
    'button[aria-label*="upload file menu" i]',
    'button[aria-label*="添加文件"]',
    'button[aria-label*="Add files" i]',
    'button[aria-label*="上传"]',
    'button[aria-label*="Upload" i]',
    'uploader button',
    'button:has(mat-icon[fonticon="add"])',
    'button:has(mat-icon[data-mat-icon-name="add"])',
    'button:has(mat-icon:text-is("add"))',
)

_UPLOAD_MENU_ITEMS = (
    '[role="menuitem"]:has-text("上传文件")',
    '[role="menuitem"]:has-text("Upload files")',
    '[role="menuitem"]:has-text("Upload file")',
    'button:has-text("上传文件")',
    'button:has-text("Upload files")',
    '[data-test-id*="local-image-file-uploader"]',
    '[data-test-id*="uploader"]',
)


def _image_input(page):
    """页面里任何 input[type=file]（隐藏的也算；Playwright 的 CSS 会穿进打开的 shadow root）。"""
    for sel in _FILE_INPUT_SELECTORS:
        loc = page.locator(sel)
        try:
            if loc.count() >= 1:
                return loc.first
        except Exception:
            continue
    return None


def _click_first_visible(page, selectors) -> str:
    for sel in selectors:
        loc = page.locator(sel)
        try:
            n = loc.count()
        except Exception:
            continue
        for i in range(min(n, 4)):
            item = loc.nth(i)
            try:
                if item.is_visible():
                    item.click(timeout=3000)
                    return sel
            except Exception:
                continue
    return ""


def _paste_files(page, paths: list) -> bool:
    """最后一招：在输入框上发一个带 File 的 paste 事件（DataTransfer）。"""
    import base64
    import mimetypes
    files = []
    for p in paths:
        with open(p, "rb") as fh:
            data = base64.b64encode(fh.read()).decode("ascii")
        files.append({"name": os.path.basename(p), "type": mimetypes.guess_type(str(p))[0] or "image/png", "b64": data})
    try:
        return bool(page.evaluate(
            """(files) => {
                const el = document.querySelector('rich-textarea .ql-editor')
                    || document.querySelector('div.ql-editor[contenteditable="true"]');
                if (!el) return false;
                const dt = new DataTransfer();
                for (const f of files) {
                    const bin = atob(f.b64);
                    const buf = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
                    dt.items.add(new File([buf], f.name, {type: f.type}));
                }
                el.focus();
                const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
                el.dispatchEvent(ev);
                el.blur();
                return true;
            }""",
            files,
        ))
    except Exception as exc:
        print(f"[gemini_cdp] synthetic paste failed: {exc}")
        return False


def _upload(page, paths: list, status: Status) -> None:
    files = [str(p) for p in paths]
    steps = []
    before_count = len(_image_srcs(page))
    _say(status, f"上传 {len(paths)} 张图（第 1 张是基础图，后面是人物参考）…")
    done = False
    # (a) 页面上已经有 file input：直接设文件（CDP DOM.setFileInputFiles）。
    target = _image_input(page)
    if target is not None:
        try:
            target.set_input_files(files, timeout=20_000)
            done = True
            steps.append("直接设置 file input：成功")
        except Exception as exc:
            steps.append(f"直接设置 file input 失败（{str(exc)[:60]}）")
    else:
        steps.append("页面上没有 file input")
    # (b) 点「+」打开上传菜单，再点「上传文件」，拦截文件对话框。
    if not done:
        btn = _click_first_visible(page, _UPLOAD_MENU_BUTTONS)
        if not btn:
            steps.append("找不到输入框左边的「+」上传菜单按钮")
        else:
            time.sleep(0.5)
            try:
                with page.expect_file_chooser(timeout=8_000) as fc:
                    item = _click_first_visible(page, _UPLOAD_MENU_ITEMS)
                    if not item:
                        raise RuntimeError("no menu item")
                fc.value.set_files(files)
                done = True
                steps.append("「+」→「上传文件」：成功")
            except Exception as exc:
                steps.append(f"「+」菜单里点「上传文件」没有弹出文件选择（{str(exc)[:60]}）")
                target = _image_input(page)
                if target is not None:
                    try:
                        target.set_input_files(files, timeout=20_000)
                        done = True
                        steps.append("菜单打开后出现的 file input：成功")
                    except Exception as exc2:
                        steps.append(f"菜单后的 file input 失败（{str(exc2)[:60]}）")
            if not done:
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
    # (c) 合成 paste 事件。
    if not done:
        if _paste_files(page, files):
            steps.append("已尝试合成粘贴")
            done = True
        else:
            steps.append("合成粘贴失败")
    print("[gemini_cdp] upload steps: " + " / ".join(steps))
    if not done:
        raise RuntimeError("Gemini 图片上传失败：" + "；".join(steps))
    before = before_count
    names = [os.path.basename(p) for p in paths]
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        now = _image_srcs(page)
        chips = 0
        try:
            chips = page.locator(
                'button[aria-label*="移除"], button[aria-label*="删除"], button[aria-label*="Remove" i], button[aria-label*="取消"]'
            ).count()
        except Exception:
            chips = 0
        named = 0
        try:
            blob = page.locator("body").inner_text(timeout=1000)
            named = sum(1 for name in names if name and name in blob)
        except Exception:
            named = 0
        if chips >= len(paths) or (len(now) - before) >= len(paths) or named >= len(paths):
            return
        time.sleep(0.4)
    raise RuntimeError("图片没有出现在 Gemini 输入框里，没有发送（上传步骤：" + "；".join(steps) + "）")


def _large_results(page) -> list:
    try:
        return page.evaluate(
            """() => [...document.querySelectorAll('img')].map((img) => {
                const r = img.getBoundingClientRect();
                return {
                    src: img.currentSrc || img.src || '',
                    nw: img.naturalWidth || 0,
                    nh: img.naturalHeight || 0,
                    w: r.width,
                    h: r.height,
                    top: r.top,
                    bottom: r.bottom,
                };
            }).filter((x) => x.nw >= 200 && x.nh >= 200 && x.w >= 120 && x.h >= 120)"""
        ) or []
    except Exception:
        return []


def _generating(page) -> bool:
    try:
        n = page.locator(
            'button[aria-label*="停止"], button[aria-label*="Stop" i]'
        ).count()
        if n:
            return True
    except Exception:
        pass
    return False


def _wait_result(page, before_srcs: set, status: Status) -> dict:
    _say(status, "等待 Gemini 生成图片 …")
    started = time.monotonic()
    last_say = 0.0
    stable = None
    stable_n = 0
    while time.monotonic() - started < GEN_TIMEOUT_S:
        fresh = [
            row for row in _large_results(page)
            if row.get("src") and row["src"] not in before_srcs
        ]
        if fresh and not _generating(page):
            pick = max(fresh, key=lambda row: (row.get("top") or 0, (row.get("nw") or 0) * (row.get("nh") or 0)))
            if stable and stable.get("src") == pick.get("src"):
                stable_n += 1
            else:
                stable = pick
                stable_n = 1
            if stable_n >= 2:
                return pick
        else:
            stable = None
            stable_n = 0
        elapsed = time.monotonic() - started
        if elapsed - last_say >= 20:
            _say(status, f"等待 Gemini 生成图片 … {int(elapsed)} 秒")
            last_say = elapsed
        time.sleep(1.5)
    raise RuntimeError(f"等了 {int(GEN_TIMEOUT_S)} 秒，Gemini 还没有新的结果图")


def _click_more(page, result: dict) -> None:
    top = float(result.get("top") or 0)
    bottom = float(result.get("bottom") or top)
    clicked = page.evaluate(
        """([top, bottom]) => {
            const buttons = [...document.querySelectorAll('button')];
            const hits = buttons.filter((b) => {
                const label = (b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '');
                const icon = [...b.querySelectorAll('mat-icon, .google-symbols, span')]
                    .map((el) => (el.textContent || '').trim()).join(' ');
                if (!/更多选项|更多操作|显示更多|更多|More options|More actions|\\bMore\\b|more_vert/.test(label + ' ' + icon)) {
                    return false;
                }
                const r = b.getBoundingClientRect();
                return r.width > 8 && r.height > 8 && r.top >= bottom - 8 && r.top <= bottom + 90 && r.top >= top;
            });
            const btn = hits.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
            if (!btn) return false;
            btn.click();
            return true;
        }""",
        [top, bottom],
    )
    if clicked:
        return
    loc = page.locator("button")
    try:
        n = loc.count()
    except Exception:
        n = 0
    for i in range(n):
        btn = loc.nth(i)
        try:
            label = (btn.get_attribute("aria-label") or "") + " " + (btn.inner_text(timeout=300) or "")
        except Exception:
            continue
        if not _MORE_LABEL.search(label):
            continue
        box = btn.bounding_box()
        if not box:
            continue
        if bottom - 8 <= box["y"] <= bottom + 90:
            btn.click(timeout=3000)
            return
    raise RuntimeError("结果图下面没有找到「⋯」菜单")


def _click_copy(page) -> None:
    time.sleep(0.35)
    try:
        item = page.get_by_role("menuitem", name=_COPY_NAME)
        if item.count():
            item.first.click(timeout=3000)
            return
    except Exception:
        pass
    clicked = page.evaluate(
        """() => {
            const nodes = [...document.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], button, a, span')];
            const hit = nodes.find((el) => /^\\s*(复制图片|複製圖片|Copy image)\\s*$/i.test((el.innerText || '').trim()));
            if (!hit) return false;
            (hit.closest('[role="menuitem"], button, a') || hit).click();
            return true;
        }"""
    )
    if not clicked:
        raise RuntimeError("菜单里没有「复制图片」")


def _copy_result(page, result: dict, reject: set, status: Status):
    from PIL import Image

    _mark_clipboard()
    _click_more(page, result)
    _click_copy(page)
    _say(status, "已点「复制图片」，读取剪贴板 …")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        img = _clipboard_image()
        if isinstance(img, Image.Image) and _fingerprint(img) not in reject:
            img.load()
            return img
        time.sleep(0.25)
    src = result.get("src") or ""
    if src.startswith("http"):
        _say(status, "剪贴板没有新图，改为下载结果地址 …")
        data = grok_cdp._fetch_image_bytes(page, page.context, src)
        img = Image.open(__import__("io").BytesIO(data))
        img.load()
        if _fingerprint(img) in reject:
            raise RuntimeError("拿到的仍是输入图，不是 Gemini 生成的结果")
        return img
    raise RuntimeError("「复制图片」之后剪贴板里没有新图片")


def make_image(prompt: str, image_path, status: Status = None):
    """贴基础图和人物参考图，再贴提示词。返回生成结果的 PIL Image。"""
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("提示词是空的")
    paths = [image_path] if isinstance(image_path, str) else [p for p in (image_path or []) if p]
    paths = [p for p in paths if isinstance(p, str) and os.path.isfile(p)]
    if not paths:
        raise RuntimeError("没有输入图片")
    if len(paths) > MAX_IMAGES:
        raise RuntimeError(f"Gemini 这次最多 {MAX_IMAGES} 张输入图，现在有 {len(paths)} 张")
    reject = {fp for fp in (_file_fingerprint(p) for p in paths) if fp}

    with grok_cdp.chrome_lock(status=status):
        _say(status, "连接和 Grok 同一个 Chrome …")
        port = grok_cdp.ensure_chrome(status)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            page = _open_gemini(browser, status)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30_000)
            except Exception:
                pass
            from cli.browser_tasks import is_login_page

            if is_login_page(page):
                raise RuntimeError("这个 Chrome 里的 Gemini 还没登录。请在刚打开的 Gemini 标签里登录后再试。")
            _say(status, "打开新的 Gemini 对话 …")
            _new_chat(page)
            known = set(_image_srcs(page))
            _upload(page, paths, status)
            known |= set(_image_srcs(page))
            _say(status, "把提示词写进 Gemini 输入框 …")
            _submit_prompt(page, prompt, status)
            result = _wait_result(page, known, status)
            return _copy_result(page, result, reject, status)
