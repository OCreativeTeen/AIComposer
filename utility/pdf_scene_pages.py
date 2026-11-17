"""t272: PDF 来源的场景生成，一页一页发给 Strata（Strata 读图片，不读 PDF）。

选中的页范围（开始页–结束页，PDF 已按范围截好）→ 每页渲染成一张图 → 按页序一页一页问 Strata，
一页一场，n 页 = n 场（这一页没有人也可以，actor 留空）。每页用「叙事方式」的场景提示词（播客 / 故事对话 / 故事表演
共用规则），再加这一页的说明：第几页 / 共几页、前面场景的摘要、到目前为止的人物名单（累计）。

勾了「动态生成人物」：每页的新人物并进名单（utility.cast_preset.merge_scene_people），后面的页拿到累计名单，
名字和样子前后一致，人物栏最多 10 个人物（t279，讲员不算；每一页的 actor 还是最多 4 个人）。

t278: 勾了「动态生成人物」且是播客 / 故事对话 / 故事表演（``independent=True``）：每一页自己找人，
前面页的人物一个也不带过来（没有累计名单，前面场景的摘要里也不放 actor），也不在这里并名单；
全部页跑完由调用方用 utility.cast_consolidate 归拢成最终人物。

本模块不碰界面和项目数据；调用方给 ``ask(image_path, system, user) -> str`` 和 ``build_prompt``。
"""

from __future__ import annotations

import json
import os
import re

PAGE_MAX_SIDE = 1280  # 每页渲染成图的最长边（像素）；漫画页上的字要看得清
PREV_SCENES_SHOWN = 3


class PageSceneError(RuntimeError):
    """某一页没有得到一个有效的场景。"""

    def __init__(self, page: int, total: int, why: str):
        super().__init__(f"第 {page}/{total} 页：{why}")
        self.page = page
        self.total = total


def render_pages(pdf_path: str, out_dir: str, max_side: int = PAGE_MAX_SIDE) -> list:
    """PDF 的每一页渲染成 JPEG，按页序返回路径列表（和 PDF 页数一样多）。"""
    import fitz  # PyMuPDF

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    doc = fitz.open(pdf_path)
    try:
        for i in range(len(doc)):
            page = doc[i]
            rect = page.rect
            scale = max_side / max(1.0, float(max(rect.width, rect.height)))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            dest = os.path.join(out_dir, f"page_{i + 1:03d}.jpg")
            pix.save(dest, jpg_quality=88)
            paths.append(dest)
    finally:
        doc.close()
    return paths


def page_texts(pdf_path: str) -> list:
    """每页的文字（没有文字的页是空串）。"""
    import fitz

    out = []
    doc = fitz.open(pdf_path)
    try:
        for i in range(len(doc)):
            try:
                out.append((doc[i].get_text("text") or "").strip())
            except Exception:  # noqa: BLE001
                out.append("")
    finally:
        doc.close()
    return out


def pdf_text_content(pdf_path: str) -> tuple:
    """t275: 「把 PDF 当文字内容」：PDF（已按选中的页范围截好）里每页的文字按页序连起来，页与页之间空一行。
    返回 (全文, 页数, 有文字的页数)；一页文字都没有（扫描图 / 漫画）→ 全文是空串。"""
    texts = page_texts(pdf_path)
    body = [t for t in texts if (t or "").strip()]
    return "\n\n".join(body).strip(), len(texts), len(body)


def parse_one_scene(raw: str):
    """模型回的文字 → 一个场景 dict；认不出返回 None。收一个元素的 JSON array、单个对象，或 {"scenes": [...]}。"""
    text = str(raw or "").strip()
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    candidates = [fence.group(1).strip()] if fence else []
    candidates.append(text)
    for cand in candidates:
        for opener, closer in (("[", "]"), ("{", "}")):
            a, b = cand.find(opener), cand.rfind(closer)
            if a < 0 or b <= a:
                continue
            try:
                data = json.loads(cand[a:b + 1])
            except ValueError:
                continue
            if isinstance(data, dict) and isinstance(data.get("scenes"), list):
                data = data["scenes"]
            if isinstance(data, list):
                data = next((x for x in data if isinstance(x, dict)), None)
            if isinstance(data, dict) and data:
                return data
    return None


def _short(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def prev_scenes_summary(scenes: list, shown: int = PREV_SCENES_SHOWN, with_actor: bool = True) -> str:
    """前面几场的摘要。t278: ``with_actor=False`` = 不放 actor（每页自己找人，前面的人物不带过来）。"""
    start = max(0, len(scenes) - shown)
    rows = []
    for i in range(start, len(scenes)):
        sc = scenes[i]
        who = f"actor={_short(sc.get('actor'), 120)} | " if with_actor else ""
        rows.append(f"    scene {i + 1}: {who}visual={_short(sc.get('visual'), 140)} "
                    f"| speaking={_short(sc.get('speaking'), 120)}")
    return "\n".join(rows)


def page_user_text(k: int, n: int, *, original_page: int, page_text: str, cast_text: str, scenes: list,
                   dynamic_block: str = "", independent: bool = False, setting: str = "") -> str:
    """第 k 页（共 n 页）的用户文字：只要这一页的一个场景。t280: ``setting`` = 地域 / 时代 / 舞台（每页都提醒一次）。"""
    parts = [
        f"THIS CALL: page {k} of {n} of the selected PDF pages (page {original_page} of the original file). "
        "The attached picture is exactly that page.",
        "Return exactly ONE scene for this page: a JSON array that holds one object with the scene fields of the "
        f"prompt above (this is scene {k} of {n}). Not zero scenes, not two, no text outside the JSON.",
        "A page with nobody in it is allowed: write an empty actor and no <N> lines for it. Everything else (speaking, "
        "visual, actor, how people speak and act) follows the narration mode rules above.",
    ]
    if (setting or "").strip():
        parts.append("SETTING (chosen by the user, the same for every page): " + setting.strip()
                     + " Clothing, places, objects, manners and the people's looks in ``visual`` and ``actor`` fit it.")
    if k == 1:
        parts.append("This is the first scene: open the story.")
    if k == n:
        parts.append("This is the last scene: close the story.")
    if independent:
        parts.append("PEOPLE ON THIS PAGE ONLY: find the people of this scene only from this page's picture and text. "
                     "Write each one in full (gender/age band/ethnicity/name). The earlier scenes below are given only "
                     "so the story continues; they do not tell you who is on this page.")
    elif (cast_text or "").strip():
        parts.append("People so far, in order (keep each id exactly as written): " + cast_text.strip())
    prev = prev_scenes_summary(scenes, with_actor=not independent)
    if prev:
        parts.append("Scenes already written for the earlier pages (continue from them, do not repeat them):\n" + prev)
    if (page_text or "").strip():
        parts.append("Readable text found on this page (may be incomplete; the picture is the truth):\n" + page_text.strip()[:1500])
    if dynamic_block:
        parts.append(dynamic_block)
    return "\n\n".join(parts)


def run_pages(images: list, ask, build_prompt, *, texts=None, first_page: int = 1, cast_text: str = "",
              mode: str = "", dynamic: bool = False, cap: int = 10, allow_host: bool = False,
              on_progress=None, should_cancel=None, retries: int = 1, independent: bool = False) -> dict:
    """一页一页问，按页序。返回 {"scenes": [...], "cast": 累计名单, "notes": [...]}。

    ``ask(image_path, system, user) -> str``；``build_prompt(k, n, cast_text, scenes) -> (system, user)``
    （调用方按累计名单现拼，所以后面的页拿到前面页加的人物）。某页拿不到有效场景（重试 retries 次后）→ PageSceneError。
    t278: ``independent=True`` = 每页自己找人：每页都给空名单，不并名单，scene 的 actor 原样留着（之后统一归拢）。"""
    from utility import cast_preset

    n = len(images)
    scenes, notes = [], []
    cast = cast_text or ""
    for k, path in enumerate(images, 1):
        if callable(should_cancel) and should_cancel():
            raise PageSceneError(k, n, "已取消")
        if callable(on_progress):
            on_progress(k, n)
        system, user = build_prompt(k, n, "" if independent else cast, scenes)
        scene, last = None, ""
        for _try in range(1 + max(0, int(retries))):
            try:
                last = ask(path, system, user) or ""
            except Exception as exc:  # noqa: BLE001
                raise PageSceneError(k, n, f"Strata 调用失败：{exc}") from exc
            scene = parse_one_scene(last)
            if scene:
                break
        if not scene:
            raise PageSceneError(k, n, "Strata 没有回一个有效的场景（要 1 个 JSON 对象）：" + (_short(last, 120) or "（空）"))
        if dynamic and not independent:
            cast, actor, got = cast_preset.merge_scene_people(
                cast, str(scene.get("actor") or ""), mode=mode, cap=cap, allow_host=allow_host)
            if "actor" in scene or actor:
                scene["actor"] = actor
            notes.extend(f"第 {k} 页：{x}" for x in got)
        scenes.append(scene)
    return {"scenes": scenes, "cast": cast, "notes": notes}
