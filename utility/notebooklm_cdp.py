"""NotebookLM (Gemini Notebook) Studio over CDP: 演示文稿 / 信息图 / 音频概览 / 视频概览.

Used by the manual LLM window's CLI自动 for cli_kind in STUDIO_KINDS.

Flow (studied from cli/browser_tasks.py's 信息图 flow, rewritten for the
luminous UI with DOM selectors instead of UIA/ratio clicks):

1. Same HermesChromeCDP Chrome on 9222 as grok_cdp (``grok_cdp.ensure_chrome``)
   and the same cross-process ``grok_cdp.chrome_lock``.
2. Open/reuse the notebook tab (``NOTEBOOKLM_STUDIO_URL`` in config, or project
   config ``notebooklm_studio_url``, or ``extra["notebook_url"]``).
3. Click the Studio tile (``.create-artifact-button-container[aria-label=...]``).
   In this UI the click opens the 自定义 dialog (``mat-dialog-container``); it does
   NOT start generating by itself.
4. Fill the dialog ``textarea``; click 立即生成.
5. Wait for a new row in the Studio list (``.artifact-button-content``) that is no
   longer generating, then 更多 (``button[aria-label=更多]``) → 下载 menu item.
6. Save to ``dest_dir`` (default ~/Downloads) as ``nblm_<kind>_<YYYYmmdd_HHMMSS><ext>``.

Blocking; call from a worker thread. Never deletes Studio items.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

import config

Status = Optional[Callable[[str], None]]

STUDIO_KINDS = {
    "slides": {
        "labels": ("演示文稿", "Slide deck", "Slides", "Presentation"),
        "ext": ".pdf",
        "menu": (r"PDF", r"\.pdf"),
        "timeout_s": 25 * 60,
        "name": "演示文稿",
    },
    "infographic": {
        "labels": ("信息图", "Infographic"),
        "ext": ".png",
        "menu": (r"^\W*\w*\s*下载\s*$", r"下载", r"Download"),
        "timeout_s": 20 * 60,
        "name": "信息图",
    },
    "audio_overview": {
        "labels": ("音频概览", "Audio Overview", "Audio overview"),
        "ext": ".m4a",
        "menu": (r"下载", r"Download"),
        "timeout_s": 30 * 60,
        "name": "音频概览",
    },
    "video_overview": {
        "labels": ("视频概览", "Video Overview", "Video overview"),
        "ext": ".mp4",
        "menu": (r"下载", r"Download"),
        "timeout_s": 40 * 60,
        "name": "视频概览",
    },
}

TILE_SEL = ".create-artifact-button-container"
DIALOG_SEL = "mat-dialog-container"
DIALOG_CLOSE_SEL = 'mat-dialog-container button[aria-label="关闭对话框"], mat-dialog-container button[aria-label="Close dialog"]'
GENERATE_NOW_RE = re.compile(r"^\s*(立即生成|Generate now|Generate)\s*$", re.I)
ROW_SEL = ".artifact-button-content"
ROW_MORE_SEL = 'button[aria-label="更多"], button[aria-label="More"], button[aria-label="More options"]'
POLL_S = 5.0

# Every row in the Studio list, newest first: key, kind (aria-description), title, text, generating, failed.
ROWS_JS = r"""() => [...document.querySelectorAll('.artifact-button-content')].map((row, i) => {
  const btn = row.querySelector('.artifact-stretched-button');
  const t = row.querySelector('.artifact-title');
  const txt = (row.innerText || '').replace(/\s+/g, ' ').trim();
  const spin = !!row.querySelector('mat-spinner, mat-progress-spinner, mat-progress-bar, .rotate, [class*="loading"], [class*="generating"], [class*="spinner"]');
  const icons = [...row.querySelectorAll('mat-icon')].map(m => (m.textContent || '').trim());
  const gen = spin || icons.includes('sync') || icons.includes('progress_activity')
      || /正在生成|生成中|Generating|is being generated/i.test(txt);
  return {
    i,
    key: (btn && btn.getAttribute('aria-labelledby')) || ('t:' + (t ? t.textContent.trim() : txt)),
    kind: (btn && btn.getAttribute('aria-description')) || '',
    title: t ? t.textContent.trim() : '',
    text: txt.slice(0, 200),
    generating: gen,
    failed: /生成失败|无法生成|failed to generate|generation failed/i.test(txt),
    hasMore: !!row.querySelector('button[aria-label="更多"], button[aria-label="More"], button[aria-label="More options"]'),
  };
})"""


def _say(status: Status, msg: str) -> None:
    print(f"[notebooklm_cdp] {msg}")
    if status:
        try:
            status(msg)
        except Exception:
            pass


def notebook_url(override: str = "") -> str:
    url = (override or "").strip()
    if not url:
        try:
            import project_manager

            url = str((project_manager.PROJECT_CONFIG or {}).get("notebooklm_studio_url") or "").strip()
        except Exception:
            url = ""
    if not url:
        url = (getattr(config, "NOTEBOOKLM_STUDIO_URL", "") or "").strip()
    if not url:
        raise RuntimeError("没有设 NotebookLM 笔记本地址（config.NOTEBOOKLM_STUDIO_URL）")
    return url


def downloads_dir() -> str:
    return str(Path.home() / "Downloads")


def unique_path(kind: str, dest_dir: str, ext: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(dest_dir, f"nblm_{kind}_{stamp}{ext}")
    n = 2
    while os.path.exists(path):
        path = os.path.join(dest_dir, f"nblm_{kind}_{stamp}_{n}{ext}")
        n += 1
    return path


def _notebook_id(url: str) -> str:
    m = re.search(r"/notebook/([0-9a-f-]{8,})", url or "")
    return m.group(1) if m else ""


def _studio_page(ctx, url: str, status: Status):
    nid = _notebook_id(url)
    page = None
    for p in ctx.pages:
        u = p.url or ""
        if (nid and nid in u) or (not nid and u.rstrip("/") == url.rstrip("/")):
            page = p
            break
    if page is None:
        _say(status, "打开 NotebookLM 笔记本 …")
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.bring_to_front()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if "accounts.google.com" in (page.url or ""):
            raise RuntimeError("NotebookLM 没有登录，请在 9222 的 Chrome 里先登录 Google")
        try:
            if page.locator(TILE_SEL).count():
                return page
        except Exception:
            pass
        time.sleep(1.0)
    raise RuntimeError("NotebookLM 页面上找不到 Studio 面板（可能被收起了）")


def _rows(page) -> list:
    try:
        return list(page.evaluate(ROWS_JS) or [])
    except Exception as exc:
        print(f"[notebooklm_cdp] rows failed: {exc}")
        return []


def _close_dialog(page) -> None:
    for _ in range(2):
        loc = page.locator(DIALOG_CLOSE_SEL)
        if not loc.count():
            return
        try:
            loc.first.click(timeout=3000)
        except Exception:
            return
        page.wait_for_timeout(800)


def _tile(page, spec: dict):
    for lab in spec["labels"]:
        loc = page.locator(f'{TILE_SEL}[aria-label="{lab}"]')
        if loc.count():
            return loc.first
    raise RuntimeError(f"Studio 里找不到「{spec['name']}」按钮")


def _open_customize(page, spec: dict, status: Status):
    _close_dialog(page)
    _say(status, f"打开「{spec['name']}」自定义 …")
    _tile(page, spec).click()
    try:
        page.wait_for_selector(f"{DIALOG_SEL} textarea", timeout=15_000)
    except Exception:
        raise RuntimeError(f"「{spec['name']}」的自定义窗口没有打开")
    return page.locator(DIALOG_SEL).last


def _click_dialog_options(dlg, options) -> None:
    """``extra["nblm_options"]``: texts to click in the dialog (e.g. "演示用幻灯片", "纵向", "短")."""
    for text in options or []:
        text = str(text or "").strip()
        if not text:
            continue
        try:
            dlg.get_by_text(text, exact=True).first.click(timeout=4000)
        except Exception as exc:
            print(f"[notebooklm_cdp] option {text!r} not clicked: {exc}")


def _fill_prompt(page, dlg, prompt: str) -> None:
    box = dlg.locator("textarea").first
    box.click()
    box.fill(prompt)
    page.wait_for_timeout(400)
    got = box.input_value() or ""
    if len(got.strip()) < min(20, len(prompt.strip())):
        raise RuntimeError("提示词没有填进 NotebookLM 的描述框")


def _click_generate_now(page, dlg) -> None:
    btn = dlg.get_by_role("button", name=GENERATE_NOW_RE)
    if not btn.count():
        btn = dlg.locator("button", has_text=re.compile(r"立即生成|Generate now", re.I))
    btn.last.click(timeout=8000)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if not page.locator(DIALOG_SEL).count():
            return
        time.sleep(0.5)
    raise RuntimeError("按了「立即生成」但自定义窗口没有关闭（可能额度用完）")


def _menu_download(page, row_index: int, spec: dict, dest_dir: str, kind: str, *, probe_only=False):
    """Open the row's 更多 menu and click the download item. probe_only: just report whether it exists."""
    row = page.locator(ROW_SEL).nth(row_index)
    row.scroll_into_view_if_needed(timeout=5000)
    row.locator(ROW_MORE_SEL).first.click(timeout=5000)
    page.wait_for_timeout(900)
    items = page.locator('[role="menuitem"]')
    texts = [(items.nth(i).inner_text() or "").strip() for i in range(items.count())]
    pick = -1
    for pat in spec["menu"]:
        for i, t in enumerate(texts):
            label = re.sub(r"^[a-z_0-9]+\s+", "", t)  # drop the icon ligature ("save_alt 下载")
            if re.search(pat, label, re.I) and not re.search(r"pptx|PowerPoint", label, re.I):
                pick = i
                break
        if pick >= 0:
            break
    if probe_only or pick < 0:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        return pick >= 0, texts
    with page.expect_download(timeout=180_000) as info:
        items.nth(pick).click()
    dl = info.value
    ext = os.path.splitext(dl.suggested_filename or "")[1] or spec["ext"]
    path = unique_path(kind, dest_dir, ext)
    dl.save_as(path)
    for _ in range(40):
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            break
        time.sleep(0.3)
    if not (os.path.isfile(path) and os.path.getsize(path) > 1000):
        raise RuntimeError("下载的文件是空的")
    return path, texts


def _wait_new_row(page, before: set, spec: dict, status: Status, timeout_s: float) -> int:
    """Index of the new finished row (not in ``before``). Raises on timeout/failure."""
    t0 = time.monotonic()
    labels = set(spec["labels"])
    last_probe = 0.0
    seen_gen = False
    while time.monotonic() - t0 < timeout_s:
        rows = _rows(page)
        new = [r for r in rows if r.get("key") not in before]
        mine = [r for r in new if not r.get("kind") or r.get("kind") in labels]
        el = int(time.monotonic() - t0)
        if mine:
            r = mine[0]
            if r.get("failed"):
                raise RuntimeError(f"NotebookLM 生成失败：{r.get('text')}")
            if r.get("generating"):
                seen_gen = True
                _say(status, f"「{spec['name']}」生成中 … {el // 60}:{el % 60:02d}")
            elif r.get("hasMore") and time.monotonic() - last_probe > 8:
                last_probe = time.monotonic()
                try:
                    ok, _texts = _menu_download(page, r["i"], spec, "", "", probe_only=True)
                except Exception as exc:
                    print(f"[notebooklm_cdp] probe menu failed: {exc}")
                    ok = False
                if ok:
                    return r["i"]
                _say(status, f"「{spec['name']}」快好了 … {el // 60}:{el % 60:02d}")
        else:
            _say(status, f"等 NotebookLM 开始生成「{spec['name']}」… {el}s")
            if el > 120 and not seen_gen:
                raise RuntimeError("两分钟内 Studio 列表里没有出现新的项目")
        time.sleep(POLL_S)
    raise RuntimeError(f"等了 {int(timeout_s // 60)} 分钟，「{spec['name']}」还没生成完")


def make_studio(kind: str, prompt: str, dest_dir: str = "", notebook_url_: str = "",
                status: Status = None, *, extra: Optional[dict] = None,
                timeout_s: Optional[float] = None) -> str:
    """Generate one Studio item from ``prompt`` and download it. Returns the saved file path."""
    from . import grok_cdp

    spec = STUDIO_KINDS.get(kind)
    if spec is None:
        raise ValueError(f"不认识的 NotebookLM 类型：{kind}")
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("提示词是空的")
    extra = dict(extra or {})
    url = notebook_url(notebook_url_ or str(extra.get("notebook_url") or ""))
    dest_dir = dest_dir or downloads_dir()
    timeout_s = float(timeout_s or extra.get("timeout_s") or spec["timeout_s"])
    with grok_cdp.chrome_lock(status=status):
        port = grok_cdp.ensure_chrome(status)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _studio_page(ctx, url, status)
            before = {r.get("key") for r in _rows(page)}
            dlg = _open_customize(page, spec, status)
            _click_dialog_options(dlg, extra.get("nblm_options"))
            _say(status, "填提示词 …")
            _fill_prompt(page, dlg, prompt)
            _say(status, "立即生成 …")
            _click_generate_now(page, dlg)
            idx = _wait_new_row(page, before, spec, status, timeout_s)
            _say(status, "下载 …")
            path, _texts = _menu_download(page, idx, spec, dest_dir, kind)
            _say(status, f"已下载：{os.path.basename(path)}")
            return path


def probe(kinds=None, status: Status = None) -> dict:
    """Read-only check: tiles exist, each customize dialog has textarea + 立即生成 (closed again), row menus."""
    from . import grok_cdp

    out: dict = {}
    with grok_cdp.chrome_lock(status=status):
        port = grok_cdp.ensure_chrome(status)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0]
            page = _studio_page(ctx, notebook_url(), status)
            for kind in kinds or STUDIO_KINDS:
                spec = STUDIO_KINDS[kind]
                dlg = _open_customize(page, spec, status)
                gen = dlg.get_by_role("button", name=GENERATE_NOW_RE).count()
                ta = dlg.locator("textarea").first.get_attribute("aria-label")
                _close_dialog(page)
                out[kind] = {"textarea": ta, "generate_now": gen, "closed": not page.locator(DIALOG_SEL).count()}
            out["rows"] = _rows(page)[:5]
    return out
