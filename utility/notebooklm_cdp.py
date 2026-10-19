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
    from .grok_cdp import site_page

    nid = _notebook_id(url)
    page = site_page(ctx, NOTEBOOK_HOST)  # 唯一的 NotebookLM 标签
    u = page.url or ""
    if not ((nid and nid in u) or (not nid and u.rstrip("/") == url.rstrip("/"))):
        _say(status, "open notebook .")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
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



# ---- 来源（左侧「来源」面板）：上传 content.pdf ----
# 行: .single-source-container；标题 .source-title；更多: button.source-item-more-button[aria-description=<title>]
# 更多菜单: [role=menuitem] 「移除来源」/「重命名来源」；勾选: mat-checkbox.select-checkbox(.mat-mdc-checkbox-checked)
# 「添加来源」: button[aria-label="添加来源"] → mat-dialog-container 里「上传文件」按钮（点了才出 input[type=file]，
# 所以用 Playwright 的 file chooser 拦截 = CDP Page.setInterceptFileChooserDialog + DOM.setFileInputFiles，不弹系统对话框）。
SOURCE_ROW_SEL = ".single-source-container"
ADD_SOURCE_SEL = 'button[aria-label="添加来源"], button[aria-label="Add source"], button[aria-label="Add sources"]'
UPLOAD_BTN_RE = re.compile(r"上传文件|Upload files?|Upload", re.I)
REMOVE_ITEM_RE = re.compile(r"移除来源|删除来源|Remove source|Delete source", re.I)
CONFIRM_RE = re.compile(r"^\s*(删除|移除|Delete|Remove)\s*$", re.I)

SOURCES_JS = r"""() => [...document.querySelectorAll('.single-source-container')].map((row, i) => {
  const t = row.querySelector('.source-title');
  const cb = row.querySelector('mat-checkbox.select-checkbox');
  const input = cb && cb.querySelector('input[type=checkbox]');
  const spin = !!row.querySelector('mat-spinner, mat-progress-spinner, mat-progress-bar, [class*="loading"], [class*="spinner"]');
  return {
    i,
    title: t ? t.textContent.trim() : '',
    checked: !!(input && input.checked) || !!(cb && cb.classList.contains('mat-mdc-checkbox-checked')),
    hasCheckbox: !!cb,
    loading: spin || !cb,
  };
})"""


def _sources(page) -> list:
    try:
        return list(page.evaluate(SOURCES_JS) or [])
    except Exception as exc:
        print(f"[notebooklm_cdp] sources failed: {exc}")
        return []


def _remove_sources_named(page, name: str, status: Status) -> int:
    """删除标题为 ``name`` 的旧来源（更多 → 移除来源 → 确认）。返回删除个数。"""
    removed = 0
    for _ in range(10):
        rows = [r for r in _sources(page) if r.get("title") == name]
        if not rows:
            break
        _say(status, f"移除旧来源 {name} .")
        row = page.locator(SOURCE_ROW_SEL).nth(rows[0]["i"])
        row.scroll_into_view_if_needed(timeout=5000)
        row.locator("button.source-item-more-button").first.click(timeout=5000)
        page.wait_for_timeout(700)
        page.locator('[role="menuitem"]').filter(has_text=REMOVE_ITEM_RE).first.click(timeout=5000)
        page.wait_for_timeout(900)
        dlg = page.locator(DIALOG_SEL)
        if dlg.count():
            btn = dlg.last.get_by_role("button", name=CONFIRM_RE)
            if not btn.count():
                btn = dlg.last.locator("button", has_text=re.compile(r"删除|移除|Delete|Remove", re.I))
            btn.last.click(timeout=5000)
        before = len(_sources(page))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if len([r for r in _sources(page) if r.get("title") == name]) < len(rows):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"移除旧来源 {name} 没有生效")
        removed += 1
    return removed


def upload_source(page, path: str, status: Status = None, *, timeout_s: float = 300) -> dict:
    """把 ``path`` 上传为笔记本来源（先移除同名旧来源），等处理完成且已勾选。返回该来源行信息。"""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise RuntimeError(f"找不到来源文件：{path}")
    name = os.path.basename(path)
    _close_dialog(page)
    _remove_sources_named(page, name, status)
    _say(status, f"添加来源 {name} .")
    page.locator(ADD_SOURCE_SEL).first.click(timeout=8000)
    page.wait_for_selector(DIALOG_SEL, timeout=15_000)
    dlg = page.locator(DIALOG_SEL).last
    with page.expect_file_chooser(timeout=15_000) as fc:
        dlg.locator("button", has_text=UPLOAD_BTN_RE).first.click(timeout=8000)
    fc.value.set_files(path)
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        rows = [r for r in _sources(page) if r.get("title") == name]
        el = int(time.monotonic() - t0)
        if rows and not rows[0].get("loading"):
            row = rows[0]
            if not row.get("checked"):
                page.locator(SOURCE_ROW_SEL).nth(row["i"]).locator("mat-checkbox.select-checkbox").first.click()
                page.wait_for_timeout(600)
                row = next((r for r in _sources(page) if r.get("title") == name), row)
            _close_dialog(page)
            _say(status, f"来源 {name} 已就绪（{el}s）")
            return row
        _say(status, f"等待来源 {name} 处理 . {el}s")
        time.sleep(2.0)
    raise RuntimeError(f"来源 {name} {int(timeout_s)}s 内未处理完")


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
            source_pdf = str(extra.get("source_pdf") or "").strip()
            if source_pdf:
                # 其他来源保持原勾选；提示词里写明以 content.pdf 为主。
                upload_source(page, source_pdf, status)
            # 额外来源（节目生成：原始材料 PDF，只作背景）。全集生成不传，行为不变。上传失败只提示，不中断。
            for extra_src in extra.get("extra_sources") or ():
                extra_src = str(extra_src or "").strip()
                if not extra_src:
                    continue
                try:
                    upload_source(page, extra_src, status)
                except Exception as exc:  # noqa: BLE001
                    msg = f"⚠️ 来源 {os.path.basename(extra_src)} 上传失败：{exc}。继续生成。"
                    print(f"NotebookLM：{msg}")
                    _say(status, msg)
                    try:
                        _close_dialog(page)
                    except Exception:  # noqa: BLE001
                        pass
            actor_pdf = str(extra.get("actor_pdf") or "").strip()
            actor_ready = False
            if actor_pdf:
                # 本集人物（全名 + 形象图）：先删旧的 actor.pdf 来源，上传，等就绪后再生成。
                try:
                    upload_source(page, actor_pdf, status)
                    actor_ready = True
                    print(f"全集生成：actor.pdf 已上传并就绪：{actor_pdf}")
                except Exception as exc:  # noqa: BLE001 上传失败：大声说，并从提示词去掉 Actor_Reference
                    msg = f"⚠️ actor.pdf 上传失败：{exc}。这次不用 actor.pdf，已从提示词去掉 Actor_Reference。"
                    print(f"全集生成：{msg}")
                    _say(status, msg)
                    try:
                        _close_dialog(page)
                    except Exception:  # noqa: BLE001
                        pass
            elif source_pdf:
                # 这一集没有人物：去掉上一次留下的 actor.pdf，免得按旧人物画。
                _close_dialog(page)
                _remove_sources_named(page, "actor.pdf", status)
            if not actor_ready and "Actor_Reference:" in prompt:
                # 保证：只有 actor.pdf 真的上传就绪，提示词里才有 Actor_Reference。
                import config_prompt

                prompt = config_prompt.strip_actor_reference(prompt)
                print("全集生成：actor.pdf 没有就绪，提交前已去掉 Actor_Reference。")
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

# ---- notebook list (https://notebook.google.com/ 我的笔记本) ----
NOTEBOOK_HOME_URL = "https://notebook.google.com/"
NOTEBOOK_HOST = "notebook.google.com"
NOTEBOOK_PREF_KEY = "nblm_notebook"  # config.load/save_yt_tools_prefs: {"url": ..., "title": ...}
NOTEBOOK_CACHE_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA") or str(Path.home()), "AIComposer", "nblm_notebooks.json"
)
# Each card: <project-button> with <a class="primary-action-button" href="/notebook/<id>"
# aria-labelledby="project-<id>-title ...">; title text in #project-<id>-title.
NOTEBOOK_CARDS_JS = r"""() => {
  const scope = document.querySelector('.my-projects-container') || document;
  const out = [], seen = new Set();
  scope.querySelectorAll('project-button a.primary-action-button[href*="/notebook/"], project-button a[href*="/notebook/"]').forEach(a => {
    const href = a.getAttribute('href') || '';
    const m = href.match(/\/notebook\/([0-9a-f-]{8,})/i);
    if (!m || seen.has(m[1])) return;
    seen.add(m[1]);
    const card = a.closest('project-button');
    const tEl = document.getElementById('project-' + m[1] + '-title')
      || (card && card.querySelector('.project-button-title, [id$="-title"]'));
    out.push({id: m[1], title: tEl ? tEl.textContent.trim() : '', href});
  });
  return out;
}"""
_list_lock = __import__("threading").Lock()
_waiters_lock = __import__("threading").Lock()


def list_notebooks(status: Status = None, *, timeout_s: float = 40.0) -> list:
    """Read the notebook cards on notebook.google.com in the single reused NotebookLM tab
    (same 9222 Chrome, chrome_lock); go back to the notebook it was on. Returns [(title, url)] in page order and updates the cache."""
    from . import grok_cdp

    with grok_cdp.chrome_lock(status=status):
        port = grok_cdp.ensure_chrome(status)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            from .grok_cdp import site_page

            page = site_page(ctx, NOTEBOOK_HOST, front=False)  # 复用唯一的 NotebookLM 标签
            back_to = page.url if _notebook_id(page.url or "") else ""
            try:
                page.goto(NOTEBOOK_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
                cards: list = []
                deadline = time.monotonic() + timeout_s
                while time.monotonic() < deadline:
                    if "accounts.google.com" in (page.url or ""):
                        print(f"[notebooklm_cdp] not signed in to Google in Chrome {port}")
                        raise RuntimeError(f"not signed in to Google in Chrome {port}（NotebookLM 没有登录）")
                    try:  # a fresh Chrome may still redirect/reload the page
                        cards = page.evaluate(NOTEBOOK_CARDS_JS) or []
                        if cards:
                            page.wait_for_timeout(1500)  # let the grid finish rendering
                            cards = page.evaluate(NOTEBOOK_CARDS_JS) or cards
                            break
                    except Exception as exc:
                        print(f"[notebooklm_cdp] home page not ready yet: {exc}")
                        cards = []
                    time.sleep(1.0)
            finally:
                if back_to:  # 读完首页再回到原来的笔记本，标签停在选定的笔记本上
                    try:
                        page.goto(back_to, wait_until="domcontentloaded", timeout=60_000)
                    except Exception as exc:
                        print(f"[notebooklm_cdp] back to notebook failed: {exc}")
    result = [
        (c.get("title") or c["id"], f"https://notebook.google.com/notebook/{c['id']}") for c in cards
    ]
    if result:
        save_cached_notebooks(result)
    return result


def load_cached_notebooks() -> list:
    import json

    try:
        with open(NOTEBOOK_CACHE_PATH, encoding="utf-8") as f:
            return [(str(t), str(u)) for t, u in json.load(f)]
    except Exception:
        return []


def save_cached_notebooks(items: list) -> None:
    import json

    try:
        os.makedirs(os.path.dirname(NOTEBOOK_CACHE_PATH), exist_ok=True)
        with open(NOTEBOOK_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump([list(x) for x in items], f, ensure_ascii=False, indent=1)
    except Exception as exc:
        print(f"[notebooklm_cdp] notebook cache not saved: {exc}")


_refresh_waiters: list = []


def refresh_notebooks_in_background(on_done: Optional[Callable[[list], None]] = None, *,
                                    only_if_running: bool = False) -> None:
    """Non-blocking refresh of the notebook list; failures are only logged.

    Launches the HermesChromeCDP Chrome on 9222 when it is not running (``list_notebooks`` calls
    ``grok_cdp.ensure_chrome`` under ``chrome_lock``, so two callers never launch two Chromes).
    If a refresh is already running, ``on_done`` is queued and called with that run's result.
    ``only_if_running`` is accepted for old callers and ignored."""
    import threading

    with _waiters_lock:
        if on_done:
            _refresh_waiters.append(on_done)
        if not _list_lock.acquire(blocking=False):
            return  # a refresh is in flight; it will call our on_done

    def _run():
        items: list = []
        try:
            from . import grok_cdp

            was_up = grok_cdp._bt().cdp_ready(grok_cdp.CDP_PORT)
            items = list_notebooks()
            if was_up:
                print(f"[notebooklm_cdp] notebooks refreshed: {len(items)}")
            else:
                print(f"[notebooklm_cdp] launched Chrome {grok_cdp.CDP_PORT}, {len(items)} notebooks")
        except Exception as exc:
            print(f"[notebooklm_cdp] notebook list refresh failed (ignored): {exc}")
        finally:
            with _waiters_lock:
                waiters = list(_refresh_waiters)
                _refresh_waiters.clear()
                _list_lock.release()
            for fn in waiters:
                try:
                    fn(items)
                except Exception as exc:
                    print(f"[notebooklm_cdp] refresh callback failed: {exc}")

    threading.Thread(target=_run, name="nblm-list", daemon=True).start()


def saved_notebook_pref() -> dict:
    try:
        v = config.load_yt_tools_prefs().get(NOTEBOOK_PREF_KEY) or {}
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def save_notebook_pref(title: str, url: str) -> None:
    try:
        config.save_yt_tools_prefs({NOTEBOOK_PREF_KEY: {"title": title, "url": url}})
    except Exception as exc:
        print(f"[notebooklm_cdp] notebook pref not saved: {exc}")


def pick_saved_index(items: list, pref: Optional[dict] = None) -> int:
    """Index of the saved notebook in ``items`` (by URL, then title); 0 when not found."""
    pref = saved_notebook_pref() if pref is None else pref
    url, title = pref.get("url") or "", pref.get("title") or ""
    for i, (_t, u) in enumerate(items):
        if url and u == url:
            return i
    for i, (t, _u) in enumerate(items):
        if title and t == title:
            return i
    return 0
