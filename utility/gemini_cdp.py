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
TEXT_TIMEOUT_S = 180.0
# 对话里用的模型（模型选择按钮里的名字，按文字匹配）。.env GEMINI_MODEL 可改。
GEMINI_MODEL_DEFAULT = "3.8 Flash"


def gemini_model() -> str:
    return (os.environ.get("GEMINI_MODEL") or GEMINI_MODEL_DEFAULT).strip()

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
            """() => [...document.querySelectorAll('img')]
              // 只要模型回复里的图；自己发出去的图（user-query 里）不算结果
              .filter((img) => !img.closest('user-query') && (img.closest('model-response') || !document.querySelector('model-response')))
              .map((img) => {
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
            }).filter((x) => ((x.nw >= 200 && x.nh >= 200) || x.w >= 200) && x.w >= 120 && x.h >= 120)"""
        ) or []
    except Exception:
        return []


def _generating(page) -> bool:
    """还在生成：有「停止」按钮，或最后一条回复只有「Gemini 说」这样的抬头（思考中）。"""
    try:
        n = page.locator(
            'button[aria-label*="停止"], button[aria-label*="Stop" i], '
            'button.stop, [data-test-id*="stop"]'
        ).count()
        if n:
            return True
    except Exception:
        pass
    rows = _responses(page)
    return bool(rows) and not rows[-1]


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


def _click_direct_copy(page, src: str) -> bool:
    try:
        return bool(page.evaluate(
            """(src) => {
                const imgs = [...document.querySelectorAll('model-response img')];
                const img = imgs.find((i) => (i.currentSrc || i.src) === src) || imgs[imgs.length - 1];
                const resp = img ? img.closest('model-response') : null;
                if (!resp) return false;
                const btn = [...resp.querySelectorAll('button')].find((b) =>
                    /^(复制图片|複製圖片|Copy image)$/i.test((b.getAttribute('aria-label') || '').trim()));
                if (!btn) return false;
                btn.click();
                return true;
            }""",
            src,
        ))
    except Exception as exc:
        print(f"[gemini_cdp] direct copy failed: {exc}")
        return False


def _copy_result(page, result: dict, reject: set, status: Status):
    from PIL import Image

    _mark_clipboard()
    # 实测：结果图所在回复里直接有「复制图片」按钮（不在「⋯」菜单里）。先点它，没有再走菜单。
    if not _click_direct_copy(page, result.get("src") or ""):
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


# ---------------------------------------------------------------------------
# 模型选择：输入框下面的模型按钮（显示当前模型，如「Flash」「3.8 Flash」），点开后按文字选。
# 找不到就只记一条警告，不让任务失败。
# ---------------------------------------------------------------------------
_MODEL_WORDS = r"Flash|Pro|Argon|Thinking|Ultra|Lite|快速|思考"

_MODEL_BUTTON_SELECTORS = (
    'button[data-test-id="bard-mode-menu-button"]',
    '[data-test-id="bard-mode-menu-button"] button',
    'button[aria-label*="模式选择"]',
    'button[aria-label*="选择模型"]',
    'button[aria-label*="mode picker" i]',
    'button[aria-label*="model" i]',
    'button[aria-haspopup="menu"]',
    'button[aria-haspopup="true"]',
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _find_model_button(page):
    """返回 (locator, 当前显示的文字)。只认文字里有模型名字的按钮，优先输入框附近的。"""
    word = re.compile(_MODEL_WORDS, re.I)
    for sel in _MODEL_BUTTON_SELECTORS:
        try:
            loc = page.locator(sel)
            n = min(loc.count(), 20)
        except Exception:
            continue
        for i in range(n):
            btn = loc.nth(i)
            try:
                if not btn.is_visible():
                    continue
                label = (btn.inner_text(timeout=500) or "") + " " + (btn.get_attribute("aria-label") or "")
            except Exception:
                continue
            if word.search(label) and not re.search(r"升级|Upgrade|试用|Try |订阅|Subscribe|Google AI", label, re.I):
                return btn, label
    return None, ""


def _model_shown(label: str, btn, model: str) -> bool:
    """按钮显示的是不是这个模型。按钮只写短名（实测：文字「Flash」，aria-label「打开模式选择器，当前模式为“Flash”」）：
    3.8 Flash → Flash，3.1 Pro → Pro。短名 = 去掉版本号；「Flash」不等于「Flash-Lite」。"""
    want = _norm(model)
    if want in _norm(label):
        return True
    short = re.sub(r"^[\d.]+\s*", "", want).strip()
    try:
        shown = _norm(btn.inner_text(timeout=500)) if btn is not None else ""
    except Exception:
        shown = ""
    return bool(short) and shown == short


def _click_model_item(page, model: str) -> bool:
    """菜单打开后点名字以 model 开头（或包含 model）的那一项。"""
    want = _norm(model)
    try:
        return bool(page.evaluate(
            """(want) => {
                const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const nodes = [...document.querySelectorAll(
                    '[role="menuitem"], [role="menuitemradio"], [role="option"], mat-option, .mat-mdc-menu-item, button')];
                const vis = nodes.filter((el) => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; });
                const first = (el) => norm((el.innerText || '').split('\\n')[0]);
                let hit = vis.find((el) => first(el) === want)
                    || vis.find((el) => first(el).startsWith(want))
                    || vis.find((el) => norm(el.innerText).includes(want));
                if (!hit) return false;
                hit.click();
                return true;
            }""",
            want,
        ))
    except Exception as exc:
        print(f"[gemini_cdp] model item click failed: {exc}")
        return False


def _select_model(page, status: Status, model: str = "") -> bool:
    """把对话切到 model（默认 GEMINI_MODEL / 3.8 Flash）。已经是就跳过。失败只警告，返回 False。"""
    model = (model or gemini_model()).strip()
    if not model:
        return True
    try:
        btn, label = _find_model_button(page)
        if btn is None:
            _say(status, f"⚠ 没找到 Gemini 模型选择按钮，按当前模型继续（想要 {model}）")
            return False
        if _model_shown(label, btn, model):
            print(f"[gemini_cdp] model already {model}")
            return True
        btn.click(timeout=3000)
        time.sleep(0.6)
        if _click_model_item(page, model):
            time.sleep(0.8)
            _btn2, label2 = _find_model_button(page)
            if not label2 or _model_shown(label2, _btn2, model):
                _say(status, f"已选 Gemini 模型 {model}")
                return True
            _say(status, f"⚠ 点了 {model}，但按钮显示「{label2.strip()[:30]}」，继续")
            return False
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        _say(status, f"⚠ 模型菜单里没有「{model}」，按当前模型（{label.strip()[:30]}）继续")
        return False
    except Exception as exc:  # noqa: BLE001
        _say(status, f"⚠ 选 Gemini 模型时出错，按当前模型继续：{exc}")
        return False


# ---------------------------------------------------------------------------
# 文字回复
# ---------------------------------------------------------------------------
_RESPONSES_JS = """() => {
    const nodes = [...document.querySelectorAll('model-response')];
    const list = nodes.length ? nodes : [...document.querySelectorAll('message-content')];
    // 只有图、没有字的回复（出图结果）也算有内容
    return list.map((el) => {
        // 正文在 model-response-content 里；thinking-overlay（「正在创建您的图片」）不算回复
        const body = el.querySelector('model-response-content') || el;
        const busy = el.querySelector('thinking-dots-animation, .image-gen-shimmer-placeholder, .gem-shimmer-active');
        if (busy) return '';
        const txt = (body.innerText || '').trim();
        const img = [...body.querySelectorAll('img')].some((i) => (i.naturalWidth || 0) >= 200 && (i.naturalHeight || 0) >= 200);
        return img ? (txt + ' [image]').trim() : txt;
    });
}"""


_REPLY_HEADER = re.compile(r"^\s*(Gemini\s*(说|說|said|says)[:：]?)\s*", re.I)


def _responses(page) -> list:
    """每条模型回复的正文（去掉「Gemini 说」抬头）。思考中的那条是空字符串。"""
    try:
        rows = page.evaluate(_RESPONSES_JS) or []
    except Exception:
        return []
    return [_REPLY_HEADER.sub("", r or "").strip() for r in rows]


def _wait_idle(page, status: Status, timeout_s: float = TEXT_TIMEOUT_S) -> bool:
    """等上一条回复（文字或图）生成完，再发下一条。超时返回 False。"""
    started = time.monotonic()
    said = False
    while time.monotonic() - started < timeout_s:
        if not _generating(page):
            return True
        if not said:
            _say(status, "Gemini 还在回复上一条，等它结束 …")
            said = True
        time.sleep(1.0)
    return False


def _wait_text_reply(page, before_n: int, status: Status, timeout_s: float = TEXT_TIMEOUT_S) -> str:
    """等对话里多出一条模型回复，并且停止生成、文字稳定。返回这条回复的文字。"""
    started = time.monotonic()
    last, same, last_say = None, 0, 0.0
    while time.monotonic() - started < timeout_s:
        rows = _responses(page)
        txt = rows[-1] if len(rows) > before_n else ""
        if txt and not _generating(page):
            if txt == last:
                same += 1
                if same >= 2:
                    return txt
            else:
                last, same = txt, 0
        elapsed = time.monotonic() - started
        if elapsed - last_say >= 20:
            _say(status, f"等待 Gemini 回复 … {int(elapsed)} 秒")
            last_say = elapsed
        time.sleep(1.0)
    if last:
        return last
    raise RuntimeError(f"等了 {int(timeout_s)} 秒，Gemini 没有文字回复（回复数 {len(_responses(page))}，之前 {before_n}）")


# ---------------------------------------------------------------------------
# 同一个对话里连续发多条：批量图片修改用
# ---------------------------------------------------------------------------
class GeminiSession:
    """在一个 worker 线程里用：

        with GeminiSession(status) as gs:
            gs.send_text("…", images=[portraits])   # 文字回复
            img = gs.make_image(prompt, [base])      # 同一对话里出图，取最新一张

    整段时间占着 chrome_lock，连接一直开着，不会每次新开对话（除非 new_chat / restart）。
    """

    def __init__(self, status: Status = None, model: str = ""):
        self.status = status
        self.model = model
        self._lock = None
        self._pw = None
        self.browser = None
        self.page = None

    def __enter__(self):
        self._lock = grok_cdp.chrome_lock(status=self.status)
        self._lock.__enter__()
        try:
            self._connect()
            self.new_chat()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def set_status(self, status: Status) -> None:
        self.status = status

    def _connect(self) -> None:
        from playwright.sync_api import sync_playwright

        _say(self.status, "连接和 Grok 同一个 Chrome …")
        port = grok_cdp.ensure_chrome(self.status)
        if self._pw is None:
            self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        self.page = _open_gemini(self.browser, self.status)
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception:
            pass
        from cli.browser_tasks import is_login_page

        if is_login_page(self.page):
            raise RuntimeError("这个 Chrome 里的 Gemini 还没登录。请在刚打开的 Gemini 标签里登录后再试。")

    def _alive(self) -> bool:
        try:
            return bool(self.page) and not self.page.is_closed() and self.browser.is_connected()
        except Exception:
            return False

    def new_chat(self) -> None:
        if not self._alive():
            self._connect()
        _say(self.status, "打开新的 Gemini 对话 …")
        _new_chat(self.page)
        _select_model(self.page, self.status, self.model)

    def restart(self) -> None:
        """对话坏了：重新连接（必要时）并开新对话。调用方要重新发开场（人物形象图）。"""
        if not self._alive():
            try:
                if self.browser:
                    self.browser.close()
            except Exception:
                pass
            self.browser = self.page = None
        self.new_chat()

    def _attach(self, images) -> list:
        paths = [p for p in (images or []) if isinstance(p, str) and os.path.isfile(p)]
        if len(paths) > MAX_IMAGES:
            raise RuntimeError(f"Gemini 一条消息最多 {MAX_IMAGES} 张图，现在有 {len(paths)} 张")
        if paths:
            _upload(self.page, paths, self.status)
        return paths

    def send_text(self, prompt: str, images=None, timeout_s: float = TEXT_TIMEOUT_S) -> str:
        """发一条文字（可带图），等文字回复，返回回复文字。"""
        prompt = (prompt or "").strip()
        if not prompt:
            raise RuntimeError("提示词是空的")
        if not _wait_idle(self.page, self.status):
            raise RuntimeError("发送前：Gemini 上一条回复一直没结束")
        before_n = len(_responses(self.page))
        self._attach(images)
        _submit_prompt(self.page, prompt, self.status)
        _say(self.status, "等待 Gemini 回复 …")
        return _wait_text_reply(self.page, before_n, self.status, timeout_s)

    def make_image(self, prompt: str, images=None, reject_paths=None):
        """在当前对话里发 图 + 提示词，等新的结果图（取最新一张），返回 PIL Image。"""
        prompt = (prompt or "").strip()
        if not prompt:
            raise RuntimeError("提示词是空的")
        if not _wait_idle(self.page, self.status):
            raise RuntimeError("发送前：Gemini 上一条回复一直没结束")
        known = set(_image_srcs(self.page)) | {r.get("src") for r in _large_results(self.page)}
        try:
            paths = self._attach(images)
        except Exception as exc:
            raise RuntimeError(f"上传基础图：{exc}") from exc
        known |= set(_image_srcs(self.page))
        reject = {fp for fp in (_file_fingerprint(p) for p in list(paths) + list(reject_paths or [])) if fp}
        try:
            _submit_prompt(self.page, prompt, self.status)
        except Exception as exc:
            raise RuntimeError(f"发送提示词：{exc}") from exc
        try:
            result = _wait_result(self.page, known, self.status)
        except Exception as exc:
            raise RuntimeError(f"等结果图：{exc}") from exc
        try:
            return _copy_result(self.page, result, reject, self.status)
        except Exception as exc:
            raise RuntimeError(f"取回结果图：{exc}") from exc

    def close(self) -> None:
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None
        self.browser = self.page = None
        if self._lock is not None:
            try:
                self._lock.__exit__(None, None, None)
            except Exception:
                pass
            self._lock = None


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
            _select_model(page, status)
            known = set(_image_srcs(page))
            _upload(page, paths, status)
            known |= set(_image_srcs(page))
            _say(status, "把提示词写进 Gemini 输入框 …")
            _submit_prompt(page, prompt, status)
            result = _wait_result(page, known, status)
            return _copy_result(page, result, reject, status)


# ---------------------------------------------------------------------------
# Gemini 视频（https://gemini.google.com/videos）：起始图 + 提示词 → mp4
# 实测选择器（2026-10-21，只读查看）：
#   视频 chip：toolbox-drawer 里 gem-button[data-test-id="deselect-drawer-item-gem-button"]，
#             button aria-label="取消选择“视频”"（在 /videos 页面默认已选）
#   画面方向：input-companion-chip 里 gem-button.input-companion-chip-button > button，
#             aria-label="宽高比，横向 (16:9)"，文字「横向」；点开是菜单（另一项「纵向」）
#   上传：「+」按钮 aria-label="上传和工具"（同图片修改的上传）
#   输入框占位「描述视频」；模型按钮同对话页 data-test-id="bard-mode-menu-button"
# 结果视频和下载按钮当时页面上还没有，按 <video>（模型回复里）和「下载」类按钮查。
# ---------------------------------------------------------------------------
GEMINI_VIDEOS_URL = "https://gemini.google.com/videos"
VIDEO_TIMEOUT_S = 600.0
_ORIENT_WORDS = {"landscape": ("横向", "16:9", "Landscape"), "portrait": ("纵向", "9:16", "Portrait")}


def orientation_for_size(video_size: str = "", width=None, height=None) -> str:
    """1920x1080 → landscape（横向），1080x1920 → portrait（纵向）。"""
    try:
        if video_size and "x" in str(video_size):
            width, height = (int(v) for v in str(video_size).lower().split("x", 1))
        w, h = int(width), int(height)
        return "portrait" if h > w else "landscape"
    except (TypeError, ValueError):
        return "landscape"


def _url_path(page) -> str:
    try:
        from urllib.parse import urlparse

        return (urlparse(page.url or "").path or "").rstrip("/") or "/"
    except Exception:
        return ""


def _video_input_ready(page) -> bool:
    try:
        return page.locator('input-area-v2 [contenteditable="true"]').count() > 0
    except Exception:
        return False


def _video_input_disabled(page) -> bool:
    """Gemini 自己把视频输入框禁用了：fieldset[disabled] / 输入框 contenteditable=false。
    实测（2026-10-22）：/videos 加载 1~2 秒后整块输入区被禁用，「文件上传」点了没反应、也不能输入，页面上没有提示文字。
    多半是这个账号今天的视频额度用完了，或者还有一个视频在生成。"""
    try:
        return bool(page.evaluate(
            """() => {
                const fs = document.querySelector('input-area-v2 fieldset');
                const ed = document.querySelector('input-area-v2 [contenteditable]');
                return !!((fs && fs.disabled) || (ed && ed.getAttribute('contenteditable') === 'false'));
            }"""
        ))
    except Exception:
        return False


def _upload_copy(path: str) -> str:
    """webp 之类先转成 PNG 再上传（视频页对 webp 不一定认）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg"):
        return path
    try:
        from PIL import Image
        import tempfile

        out = os.path.join(tempfile.gettempdir(), "gemini_video_start_" + os.path.splitext(os.path.basename(path))[0] + ".png")
        Image.open(path).convert("RGB").save(out, "PNG")
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini_cdp] 转 PNG 失败，用原图：{exc}")
        return path


def _open_videos_page(browser, status: Status):
    """用 Tom 看得见的那个（Grok 所在的、已登录的）Chrome 窗口里的 Gemini 标签；没有才新开一个。
    切到前台（bring_to_front），任务完不关，方便看结果。
    以前每次 ctx.new_page() 开后台新标签、失败后又在 finally 里关掉，所以 Tom 看不到 /videos 页。"""
    ctx, _grok = _context_with_grok(browser)
    page = None
    gem = []
    for pg in list(ctx.pages):
        try:
            if "gemini.google.com" in (pg.url or ""):
                gem.append(pg)
        except Exception:
            continue
    gem.sort(key=lambda pg: 0 if "/videos" in (pg.url or "") else 1)  # 已经在 /videos 的优先
    if gem:
        page = gem[0]
        _say(status, f"打开视频页：用已开的 Gemini 标签（{page.url}）")
    else:
        page = ctx.new_page()
        _say(status, "打开视频页：新开 Gemini 标签 …")
    try:
        page.bring_to_front()
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini_cdp] bring_to_front failed: {exc}")
    return page


def _video_chip_on(page) -> bool:
    try:
        return page.locator(
            'gem-button[data-test-id="deselect-drawer-item-gem-button"] button[aria-label*="视频"], '
            'gem-button[data-test-id="deselect-drawer-item-gem-button"] button[aria-label*="Video" i]'
        ).count() > 0
    except Exception:
        return False


def _select_video_chip(page) -> bool:
    """「视频」没选上时试着点它（输入框里文字是「视频」的按钮，或「+」菜单里的「视频」）。"""
    if _video_chip_on(page):
        return True
    try:
        clicked = page.evaluate(
            """() => {
                const btn = [...document.querySelectorAll('input-area-v2 button, toolbox-drawer button')]
                    .find((b) => (b.innerText || '').trim() === '视频' && !/取消选择/.test(b.getAttribute('aria-label') || ''));
                if (!btn) return false;
                btn.click();
                return true;
            }"""
        )
        if clicked:
            time.sleep(1.0)
    except Exception:
        pass
    return _video_chip_on(page)


def _orientation_button(page):
    for sel in (
        'input-companion-chip button[aria-label*="宽高比"]',
        'input-companion-chip button[aria-label*="aspect" i]',
        'gem-button.input-companion-chip-button button',
        'input-companion-chip button',
    ):
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def _set_orientation(page, orientation: str, status: Status) -> bool:
    """把方向 chip 设成 横向 / 纵向。找不到只警告。"""
    want = _ORIENT_WORDS.get(orientation, _ORIENT_WORDS["landscape"])
    try:
        btn = _orientation_button(page)
        if btn is None:
            _say(status, "⚠ 没找到 横向/纵向 选择，按页面当前方向继续")
            return False
        label = (btn.get_attribute("aria-label") or "") + " " + (btn.inner_text(timeout=500) or "")
        if any(w.lower() in label.lower() for w in want):
            return True
        btn.click(timeout=3000)
        time.sleep(0.6)
        clicked = page.evaluate(
            """(words) => {
                const nodes = [...document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"], .mat-mdc-menu-item')];
                const vis = nodes.filter((el) => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; });
                const hit = vis.find((el) => words.some((w) => (el.innerText || '').includes(w)));
                if (!hit) return false;
                hit.click();
                return true;
            }""",
            list(want),
        )
        if not clicked:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            _say(status, f"⚠ 方向菜单里没有「{want[0]}」，按页面当前方向继续")
            return False
        time.sleep(0.6)
        btn2 = _orientation_button(page)
        label2 = (btn2.get_attribute("aria-label") or "") if btn2 is not None else ""
        ok = any(w.lower() in label2.lower() for w in want) or not label2
        _say(status, f"画面方向：{want[0]}" if ok else f"⚠ 点了「{want[0]}」，按钮显示「{label2[:30]}」")
        return ok
    except Exception as exc:  # noqa: BLE001
        _say(status, f"⚠ 设画面方向时出错，按页面当前方向继续：{exc}")
        return False


_VIDEO_STATE_JS = """() => {
    const resp = [...document.querySelectorAll('model-response')];
    const last = resp[resp.length - 1] || null;
    const vids = [...document.querySelectorAll('model-response video')].map((v) => ({
        src: v.currentSrc || v.src || (v.querySelector('source') || {}).src || '',
        w: v.videoWidth || 0, h: v.videoHeight || 0,
    })).filter((v) => v.src);
    const busy = !!(last && last.querySelector('thinking-dots-animation, .image-gen-shimmer-placeholder, .gem-shimmer-active'));
    const body = last ? (last.querySelector('model-response-content') || last) : null;
    return { n: resp.length, vids, busy, text: body ? (body.innerText || '').trim().slice(0, 300) : '' };
}"""


def _video_state(page) -> dict:
    try:
        return page.evaluate(_VIDEO_STATE_JS) or {}
    except Exception:
        return {}


def _wait_video(page, before: dict, status: Status, timeout_s: float = VIDEO_TIMEOUT_S) -> str:
    """等新的 <video>（src 不在 before 里），返回 src。回复结束却只有文字（额度、拒绝等）时报出那段文字。"""
    old = {v.get("src") for v in before.get("vids") or []}
    started = time.monotonic()
    last_say, text_since = 0.0, None
    while time.monotonic() - started < timeout_s:
        st = _video_state(page)
        fresh = [v for v in st.get("vids") or [] if v.get("src") and v["src"] not in old]
        if fresh and not st.get("busy") and not _generating(page):
            return fresh[-1]["src"]
        done_text = (st.get("n", 0) > before.get("n", 0) and not st.get("busy") and not _generating(page)
                     and st.get("text") and not fresh)
        if done_text:
            text_since = text_since or time.monotonic()
            if time.monotonic() - text_since > 20:
                raise RuntimeError(f"Gemini 没有出视频，回复：{st.get('text')[:200]}")
        else:
            text_since = None
        elapsed = time.monotonic() - started
        if elapsed - last_say >= 30:
            _say(status, f"等待 Gemini 生成视频 … {int(elapsed)} 秒（最多 {int(timeout_s)} 秒）")
            last_say = elapsed
        time.sleep(2.0)
    raise RuntimeError(f"等了 {int(timeout_s)} 秒，Gemini 还没有生成视频")


def _unique_gemini_video_path(dest_dir: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(dest_dir, f"gemini_video_{stamp}.mp4")
    n = 2
    while os.path.exists(path):
        path = os.path.join(dest_dir, f"gemini_video_{stamp}_{n}.mp4")
        n += 1
    return path


def _save_gemini_video(page, src: str, dest_dir: str, status: Status) -> str:
    import base64

    path = _unique_gemini_video_path(dest_dir)
    data = b""
    try:
        _say(status, "下载生成的视频 …")
        data = base64.b64decode(page.evaluate(grok_cdp.FETCH_AS_B64_JS, src))
    except Exception as exc:
        print(f"[gemini_cdp] in-page video fetch failed ({exc})")
    if len(data) > 10_000:
        with open(path, "wb") as f:
            f.write(data)
        return path
    _say(status, "用「下载」按钮保存视频 …")
    with page.expect_download(timeout=180_000) as dl_info:
        clicked = page.evaluate(
            """() => {
                const resp = [...document.querySelectorAll('model-response')].pop();
                if (!resp) return false;
                const btn = [...resp.querySelectorAll('button')].find((b) =>
                    /下载|Download/i.test((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')));
                if (!btn) return false;
                btn.click();
                return true;
            }"""
        )
        if not clicked:
            raise RuntimeError("没找到视频的「下载」按钮，视频地址也取不到")
    dl_info.value.save_as(path)
    return path


def _on_videos(page) -> bool:
    try:
        return "/videos" in (page.url or "") and _video_chip_on(page)
    except Exception:
        return False


def _ensure_videos_page(page, status: Status, step: str) -> None:
    """确认在 /videos 且输入框里有「视频」chip；不在就 goto，再不行点侧栏「视频」。都不行立即报错。"""
    for how in ("check", "goto", "sidebar"):
        if how == "goto":
            _say(status, f"{step}：不在视频页（{page.url}），重新打开 /videos …")
            try:
                page.goto(GEMINI_VIDEOS_URL, wait_until="domcontentloaded", timeout=60_000)
            except Exception as exc:
                print(f"[gemini_cdp] goto /videos failed: {exc}")
        elif how == "sidebar":
            _say(status, f"{step}：点侧栏「视频」…")
            try:
                link = page.locator('a[href="/videos"], a[href$="/videos"]')
                if link.count():
                    link.first.click(timeout=5000)
            except Exception as exc:
                print(f"[gemini_cdp] sidebar 视频 click failed: {exc}")
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if _on_videos(page):
                return
            if "/videos" in (page.url or "") and _select_video_chip(page):
                return
            time.sleep(0.5)
    raise RuntimeError(f"{step}：打不开 Gemini 视频页（现在是 {page.url}，没有选上「视频」）")


def _user_query_count(page) -> int:
    try:
        return page.locator("user-query").count()
    except Exception:
        return 0


_VIDEO_SEND_SELECTORS = (
    # 实测（/videos，写了字以后才出现）：input-area-v2 里 gem-button.send-button > button[aria-label="发送"]
    'input-area-v2 gem-button.send-button button',
    'input-area-v2 .send-button button',
    'input-area-v2 button[aria-label="发送"]',
    'input-area-v2 button[aria-label="Send" i]',
    'input-area-v2 button[aria-label="Send message" i]',
)


def _click_video_send(page) -> str:
    """只点视频输入框里的发送按钮（不用全页匹配，免得点到侧栏 / 新对话）。都没有就在输入框里按 Enter。"""
    for sel in _VIDEO_SEND_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible() and loc.first.is_enabled():
                loc.first.click(timeout=3000)
                return sel
        except Exception:
            continue
    try:
        page.locator("input-area-v2 rich-textarea .ql-editor").first.press("Enter", timeout=3000)
        return "Enter"
    except Exception as exc:
        raise RuntimeError(f"发送：输入框里没有发送按钮，按 Enter 也失败（{exc}）") from exc


def _video_job_started(page, before_uq: int, before_resp: int, start_url: str) -> bool:
    """发出去了：多了一条用户消息 / 模型回复，或地址变成某个对话 / 视频（/app/xxx、/videos/xxx）。"""
    # 只有对话里出现了这条消息 / 回复才算；单看 /app/<id> 地址不算（可能是普通对话）。
    if _user_query_count(page) > before_uq:
        return True
    try:
        return page.locator("model-response").count() > before_resp
    except Exception:
        return False


def _send_video_prompt(page, prompt: str, status: Status, already_typed: bool = False) -> None:
    """写提示词、点视频输入框里的发送，并确认任务真的发出去；否则立即报错。"""
    if not already_typed and not _insert_prompt(page, prompt):
        got = re.sub(r"\s+", " ", _composer_text(page)).strip()
        raise RuntimeError(f"写提示词：没能写进输入框（框里：{got[:40] or '空'}）")
    if "/videos" not in (page.url or ""):
        raise RuntimeError(f"写提示词：页面离开了视频页（{page.url}）")
    time.sleep(0.8)  # 发送按钮写了字以后才出现
    # 上传 / 写字可能把「视频」取消掉：发送前再确认一次，没选上就点回来，还不行就不发。
    if not _select_video_chip(page):
        raise RuntimeError("发送前：「视频」没有选上（上传或写提示词后被取消了），没有发送")
    before_uq = _user_query_count(page)
    try:
        before_resp = page.locator("model-response").count()
    except Exception:
        before_resp = 0
    start_url = page.url or ""
    how = _click_video_send(page)
    _say(status, f"已发送（{how}），确认任务开始 …")
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if _video_job_started(page, before_uq, before_resp, start_url):
            print(f"[gemini_cdp] video job started via {how}; url={page.url}")
            return
        url = page.url or ""
        if re.search(r"/app/?$", url) and _user_query_count(page) == 0 and time.monotonic() > deadline - 25.0:
            raise RuntimeError(f"发送：点了「{how}」后页面跳回了新对话 {url}，视频没有提交")
        time.sleep(0.5)
    raise RuntimeError(f"发送：点了「{how}」，30 秒内没看到任务开始（页面 {page.url}）")


def _fresh_videos_page(page, status: Status, step: str) -> None:
    """切到前台 → goto /videos → reload（最多 3 次），确认路径就是 /videos、视频输入框在、「视频」chip 选上。
    每一步把当前网址写进状态行。不就绪就报「打开视频页：…（实际网址）」。"""
    last = ""
    for attempt in range(1, 4):
        try:
            page.bring_to_front()
        except Exception:
            pass
        try:
            page.goto(GEMINI_VIDEOS_URL, wait_until="domcontentloaded", timeout=60_000)
            _say(status, f"{step}：已打开 {page.url}，刷新 …")
            page.reload(wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            last = f"第{attempt}次加载失败（网址 {page.url}）：{exc}"
            _say(status, f"{step}：{last}")
            continue
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if (_url_path(page) == "/videos" and _video_input_ready(page)
                    and (_video_chip_on(page) or _select_video_chip(page))):
                time.sleep(3.0)  # Gemini 加载后 1~2 秒才决定禁不禁用输入框
                if _video_input_disabled(page):
                    raise RuntimeError(
                        f"打开视频页：Gemini 把视频输入框禁用了（{page.url}，不能输入也不能上传，页面没给原因）。"
                        "多半是今天的视频额度用完了，或者还有一个视频在生成；请在这个标签里手动试试能不能输入。"
                    )
                _say(status, f"{step}：视频页就绪（{page.url}）")
                return
            time.sleep(0.7)
        last = (f"第{attempt}次：实际网址 {page.url}，路径 {_url_path(page)}，"
                f"视频输入框{'在' if _video_input_ready(page) else '不在'}，「视频」{'已选' if _video_chip_on(page) else '没选上'}")
        _say(status, f"{step}：视频页没就绪（{last}），刷新重试 …")
    raise RuntimeError(f"打开视频页：{step}，刷新 3 次仍不是可用的 Gemini 视频页（{last}）")


def _video_upload(page, path: str, status: Status) -> None:
    """视频页上传起始图：先用合成粘贴（实测保持视频模式），再试输入框里的「文件上传」按钮。
    不走「+ / 上传和工具」菜单——那是对话页的菜单，可能把视频模式切掉。"""
    def attached() -> bool:
        try:
            return page.locator('input-area-v2 button[aria-label*="关闭附件"], input-area-v2 button[aria-label*="Remove" i]').count() > 0
        except Exception:
            return False

    if _url_path(page) != "/videos" or not _video_input_ready(page):
        raise RuntimeError(f"打开视频页：上传前不在视频页（实际网址 {page.url}）")
    if _video_input_disabled(page):
        raise RuntimeError(f"上传起始图：Gemini 视频输入框是禁用的（{page.url}），多半是视频额度用完或另一个视频在生成")
    path = _upload_copy(path)
    _say(status, f"上传起始图 …（{page.url}）")
    try:
        page.bring_to_front()
        page.locator('input-area-v2 [contenteditable="true"]').first.click(timeout=3000)  # 让粘贴落在视频输入框
    except Exception:
        pass
    if _paste_files(page, [path]):
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if attached():
                return
            time.sleep(0.5)
    try:
        btn = page.locator('input-area-v2 button[aria-label="文件上传"], input-area-v2 button[aria-label*="Upload file" i]')
        if btn.count():
            with page.expect_file_chooser(timeout=10_000) as fc:
                btn.first.click(timeout=3000)
            fc.value.set_files([path])
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                if attached():
                    return
                time.sleep(0.5)
    except Exception as exc:
        print(f"[gemini_cdp] 文件上传 button failed: {exc}")
    raise RuntimeError(f"上传起始图：粘贴和「文件上传」按钮都没能把图放进视频输入框（网址 {page.url}）")


def make_video(prompt: str, image_path: str, dest_dir: str, status: Status = None, *,
               orientation: str = "landscape", model: str = "") -> str:
    """Gemini 视频：/videos 页，选模型、设 横向/纵向、贴起始图、贴提示词、发送，等 mp4 下载到 dest_dir。返回路径。"""
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("提示词是空的")
    if not (image_path and os.path.isfile(image_path)):
        raise RuntimeError("生成视频需要一张起始图")
    if not dest_dir:
        raise RuntimeError("没有给视频的保存目录")
    with grok_cdp.chrome_lock(status=status):
        _say(status, "连接和 Grok 同一个 Chrome …")
        port = grok_cdp.ensure_chrome(status)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            page = _open_videos_page(browser, status)
            try:
                from cli.browser_tasks import is_login_page

                if is_login_page(page):
                    raise RuntimeError("这个 Chrome 里的 Gemini 还没登录。请在 Gemini 标签里登录后再试。")
                _fresh_videos_page(page, status, "打开视频页")
                _select_model(page, status, model)
                _set_orientation(page, orientation, status)
                last_err = None
                for attempt in range(1, 4):  # 发送前页面离开视频页 → 整页刷新重来（最多再试 2 次）
                    if attempt > 1:
                        _say(status, f"发送前页面不在视频模式（{last_err}），刷新视频页重来（第{attempt}次）…")
                        _fresh_videos_page(page, status, "重新打开视频页")
                        _set_orientation(page, orientation, status)
                    else:
                        _fresh_videos_page(page, status, "上传前刷新视频页")
                        _set_orientation(page, orientation, status)
                    _video_upload(page, image_path, status)
                    if not _insert_prompt(page, prompt):
                        got = re.sub(r"\s+", " ", _composer_text(page)).strip()
                        raise RuntimeError(f"写提示词：没能写进输入框（框里：{got[:40] or '空'}）")
                    time.sleep(0.8)
                    if "/videos" not in (page.url or ""):
                        last_err = f"页面到了 {page.url}"
                        continue
                    if not (_video_chip_on(page) or _select_video_chip(page)):
                        last_err = "「视频」被取消"
                        continue
                    break
                else:
                    raise RuntimeError(f"发送前：刷新 3 次后仍不在视频模式（{last_err}），没有发送")
                before = _video_state(page)
                _send_video_prompt(page, prompt, status, already_typed=True)
                src = _wait_video(page, before, status)
                path = _save_gemini_video(page, src, dest_dir, status)
                _say(status, f"视频已保存：{os.path.basename(path)}")
                return path
            finally:
                # 不关标签：留在前台让 Tom 看到结果 / 出错时的页面（下次任务会复用并刷新它）
                try:
                    print(f"[gemini_cdp] 视频标签停在 {page.url}")
                except Exception:
                    pass
