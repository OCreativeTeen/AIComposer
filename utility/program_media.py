"""节目生成产物：幻灯片 / 语音概览 / 视频概览 的列表存储（与 cover_image 一样，最新在前）。

旧数据里这些字段可能是单个路径字符串；读写一律走这里的辅助函数，不要直接
``.strip()`` 一个可能是 list 的值。``cover_video`` 是成片，不属于这里。
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import datetime

_SETTLED_STEM = re.compile(r"_\d{14}(?:_\d+)?$")

KIND_SLIDES = "slides"
KIND_AUDIO_OVERVIEW = "audio_overview"
KIND_VIDEO_OVERVIEW = "video_overview"
KIND_INFOGRAPHIC = "infographic"

# 故事 / 项目字段名。视频概览不写 cover_video（那是成片）。
FIELD_BY_KIND = {
    KIND_SLIDES: "slide",
    KIND_AUDIO_OVERVIEW: "audio_overview",
    KIND_VIDEO_OVERVIEW: "video_overview",
}

LISTISH_FIELDS = ("cover_image", "slide", "audio_overview", "video_overview")


def field_for_kind(kind: str) -> str:
    return FIELD_BY_KIND.get(str(kind or "").strip(), "")


def coerce_program_media_list(value) -> list[str]:
    """标量路径或路径列表 → 去空后的 list（保持原顺序，不做存在性检查）。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            path = str(item or "").strip()
            if path:
                out.append(path)
        return out
    path = str(value).strip()
    return [path] if path else []


def get_program_media_list(item: dict | None, kind: str) -> list[str]:
    if not isinstance(item, dict):
        return []
    field = field_for_kind(kind)
    if not field:
        return []
    return coerce_program_media_list(item.get(field))


def list_existing_program_media(item: dict | None, kind: str) -> list[str]:
    """列表里仍然存在于磁盘上的路径（相对顺序不变；最新在前）。"""
    out = []
    seen = set()
    for path in get_program_media_list(item, kind):
        if not os.path.isfile(path):
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        out.append(os.path.abspath(path))
    return out


def get_primary_program_media(item: dict | None, kind: str) -> str:
    """当前结果：列表第一项里仍然存在的文件；兼容旧的标量字段。"""
    for path in get_program_media_list(item, kind):
        if os.path.isfile(path):
            return os.path.abspath(path)
    return ""


def same_media_path(a: str, b: str) -> bool:
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except (OSError, ValueError, TypeError):
        return str(a) == str(b)


def append_program_media(item: dict, kind: str, path: str) -> list[str]:
    """把一条路径插到最前（最新）。已在列表里则先去掉再插到最前。返回新列表。"""
    if not isinstance(item, dict):
        return []
    field = field_for_kind(kind)
    if not field:
        return []
    path = str(path or "").strip()
    if not path:
        return get_program_media_list(item, kind)
    try:
        path = os.path.abspath(path)
    except (OSError, ValueError):
        pass
    current = [p for p in get_program_media_list(item, kind) if not same_media_path(p, path)]
    current.insert(0, path)
    item[field] = current
    return current


def remove_program_media(item: dict, kind: str, path: str) -> list[str]:
    if not isinstance(item, dict):
        return []
    field = field_for_kind(kind)
    if not field:
        return []
    current = [p for p in get_program_media_list(item, kind) if not same_media_path(p, path)]
    # 空列表表示「用户删光了」，和「字段根本没写」（旧数据被别的保存冲掉）要分开：
    # 写入列表时，缺了的字段会从磁盘补回，空列表则按删除处理。
    item[field] = current
    return current


def order_after_selection(candidates: list[str], selected: str | None) -> list[str]:
    """选中的作为当前（第一项），其余保持原相对顺序跟在后面。"""
    items = [str(p).strip() for p in (candidates or []) if str(p or "").strip()]
    if not items:
        return []
    sel = str(selected or "").strip()
    if not sel:
        return items
    rest = [p for p in items if not same_media_path(p, sel)]
    matched = next((p for p in items if same_media_path(p, sel)), sel)
    return [matched] + rest


def infographic_candidates_side_by_side(video_size: str) -> bool:
    """9:16 / 1080x1920 左右并排；16:9 / 1920x1080 上下排列。"""
    key = str(video_size or "").strip().lower().replace(" ", "")
    if key in ("1080x1920", "9:16", "9x16", "portrait"):
        return True
    if "1080x1920" in key or key.startswith("9:16") or key.startswith("9x16"):
        return True
    return False


STUDIO_TIMES_MAX = 3


def clamp_studio_times(times) -> int:
    """节目生成次数：1、2 或 3。非法或过小当作 1，超过 3 封顶。"""
    try:
        n = int(times or 1)
    except (TypeError, ValueError):
        return 1
    if n < 1:
        return 1
    if n > STUDIO_TIMES_MAX:
        return STUDIO_TIMES_MAX
    return n


def infographic_pick_thumb_size(video_size: str, count: int) -> tuple[int, int]:
    """信息图候选缩略图最大边框，使 2–3 张能放进普通屏幕。

    16:9 上下排：按高度均分；9:16 左右排：按宽度均分。
    """
    try:
        n = int(count or 1)
    except (TypeError, ValueError):
        n = 1
    n = 1 if n < 1 else n
    side = infographic_candidates_side_by_side(video_size)
    if side:
        max_w = max(160, min(400, 1100 // n))
        max_h = max(220, min(560, int(max_w * 16 / 9)))
        return (max_w, max_h)
    max_h = max(140, min(300, 720 // n))
    max_w = max(240, min(560, int(max_h * 16 / 9)))
    return (max_w, max_h)


def file_result_paths(response) -> list[str]:
    """FileResult.paths 或单个路径字符串 → 路径列表。"""
    if response is None:
        return []
    paths = getattr(response, "paths", None)
    if paths:
        return [str(p) for p in paths if str(p or "").strip()]
    text = str(response).strip()
    return [text] if text else []


def unique_dest_path(directory: str, filename: str) -> str:
    """在 directory 里给 filename 一个带时间戳、不碰撞的新名字（保持扩展名）。"""
    directory = directory or "."
    os.makedirs(directory, exist_ok=True)
    raw = os.path.basename(filename or "result") or "result"
    stem, ext = os.path.splitext(raw)
    if not stem:
        stem = "result"
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    for extra in ("", *(f"_{n}" for n in range(1, 100)), f"_{uuid.uuid4().hex[:6]}"):
        dest = os.path.join(directory, f"{stem}_{stamp}{extra}{ext}")
        if not os.path.exists(dest):
            return dest
    return os.path.join(directory, f"{stem}_{stamp}_{uuid.uuid4().hex}{ext}")


def settle_generated_file(path: str, dest_dir: str = "") -> str:
    """把刚下载的文件移到 dest_dir 并改成不碰撞的名字。

    已经位于目标目录时原样返回，避免二次提交之间、回调里再次加戳。
    """
    path = os.path.abspath(str(path or "").strip())
    if not path or not os.path.isfile(path):
        raise RuntimeError(f"生成结果不存在：{path}")
    directory = os.path.abspath(dest_dir or os.path.dirname(path))
    os.makedirs(directory, exist_ok=True)
    stem, _ext = os.path.splitext(os.path.basename(path))
    already_here = os.path.normcase(os.path.dirname(path)) == os.path.normcase(directory)
    if already_here and _SETTLED_STEM.search(stem):
        return path
    dest = unique_dest_path(directory, os.path.basename(path))
    if os.path.normcase(path) != os.path.normcase(dest):
        shutil.move(path, dest)
    return os.path.abspath(dest)


def run_sequential_generations(
    generate,
    times: int,
    *,
    should_cancel=None,
    on_status=None,
    existing=None,
):
    """依次调用 ``generate(index) -> path``，绝不并行。

    返回 ``(paths, error_or_None, cancelled)``。
    某次失败时保留已经完成的结果；取消则不再启动下一次。
    拒绝与已有结果（existing 或本轮已收集）同一路径的产物。
    """
    n = clamp_studio_times(times)
    paths: list[str] = []
    seen = set()
    for raw in existing or ():
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            seen.add(os.path.normcase(os.path.abspath(text)))
        except (OSError, ValueError):
            seen.add(text)
    for i in range(n):
        if should_cancel and should_cancel():
            return paths, None, True
        if on_status:
            on_status(i + 1, n, "start")
        try:
            path = generate(i)
        except Exception as exc:  # noqa: BLE001 — 调用方决定如何展示
            return paths, exc, False
        path = str(path or "").strip()
        if not path:
            return paths, RuntimeError("生成结果是空的"), False
        try:
            key = os.path.normcase(os.path.abspath(path))
        except (OSError, ValueError):
            key = path
        if key in seen:
            return paths, RuntimeError("后来的生成得到了与已有结果相同的文件，已忽略"), False
        seen.add(key)
        paths.append(path)
        if on_status:
            on_status(i + 1, n, "done")
    return paths, None, False


def studio_times_from_extra(extra) -> int:
    if not isinstance(extra, dict):
        return 1
    return clamp_studio_times(extra.get("studio_times"))

def merge_missing_program_media(incoming: dict, existing: dict) -> dict:
    """incoming 里没有的节目产物字段（幻灯片 / 语音概览 / 视频概览）从 existing 补回。

    字段在 incoming 里出现过（包括空列表）就以 incoming 为准，这样用户手动删掉才能保住。
    """
    if not isinstance(incoming, dict) or not isinstance(existing, dict):
        return incoming if isinstance(incoming, dict) else {}
    for kind in (KIND_SLIDES, KIND_AUDIO_OVERVIEW, KIND_VIDEO_OVERVIEW):
        field = field_for_kind(kind)
        if not field or field in incoming:
            continue
        if field in existing:
            incoming[field] = existing[field]
    return incoming


def _program_media_item_key(item: dict) -> tuple[str, str] | None:
    if not isinstance(item, dict):
        return None
    return (str(item.get("id") or "").strip(), str(item.get("url") or "").strip())


def merge_program_media_into_list(new_data, old_data):
    """把旧列表里还在的节目产物字段补进即将写入的新列表（只补完全缺失的键）。"""
    old_items = old_data if isinstance(old_data, list) else None
    new_items = new_data if isinstance(new_data, list) else None
    if not old_items or not new_items:
        return new_data
    by_pair: dict[tuple[str, str], dict] = {}
    by_id: dict[str, dict] = {}
    for item in old_items:
        key = _program_media_item_key(item)
        if not key or not (key[0] or key[1]):
            continue
        by_pair[key] = item
        if key[0]:
            by_id[key[0]] = item
    for item in new_items:
        key = _program_media_item_key(item)
        if not key:
            continue
        existing = by_pair.get(key) or (by_id.get(key[0]) if key[0] else None)
        if existing is not None and existing is not item:
            merge_missing_program_media(item, existing)
    return new_data
