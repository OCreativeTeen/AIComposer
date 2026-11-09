"""Scene still-image slots: independent files and frozen cover original.

Lifecycle (scenes created WITH a project cover):
  1. Creation copies the cover into FOUR distinct real files on every scene:
     clip_image, clip_image_last, zero_image, zero_image_last.
  2. The scene is marked cover_origin="cover". After that, zero_image_last is
     the immutable original cover — later edits, imports, preview auto-fill,
     drag/drop, swap, track-frame grabs, template reapply, and shared-zero
     must not replace it. Old scenes without the marker keep legacy behavior;
     we never invent an original cover for them.
  3. Manual image editing and cover-scene extraction write THREE new distinct
     files: clip_image, clip_image_last, and zero_image. Cover extraction
     reads the frozen zero_image_last (not the already-changed clip).
  4. Video generation/import updates only clip image fields (typically
     clip_image_last from the last frame). It must not rewrite zero images,
     except the sanctioned clip-tail chain: after a clip scene video is saved,
     last_image_replacement independently copies that last frame into the
     next scene's zero_image_last (even if that slot was the frozen cover).
     Other writers still obey the freeze. zero_image is never part of this chain.

Copies are always separate files (never a shared path, symlink, or hardlink).
A failed multi-slot write leaves scene keys unchanged (no partial update).
"""
from __future__ import annotations

import os
from typing import Iterable

from utility.file_util import safe_copy_overwrite, safe_remove

# Persisted on the scene dict in scenes.json when creation seeded from a cover.
COVER_ORIGIN_KEY = "cover_origin"
COVER_ORIGIN_FROZEN = "cover"

COVER_SEED_SLOTS = ("clip_image", "clip_image_last", "zero_image", "zero_image_last")
EDIT_OUTPUT_SLOTS = ("clip_image", "clip_image_last", "zero_image")
FROZEN_SLOT = "zero_image_last"
# Persisted when the sanctioned clip-tail chain overwrites next.zero_image_last.
# Does not disable freeze for edits / shared-zero / other imports.
ZERO_LAST_CHAIN_KEY = "zero_image_last_chain"
ZERO_LAST_CHAIN_CLIP = "clip"

# Shared picker / persisted "image" preference (图片修改 + 生场视频).
IMAGE_CHOICE_KEYS = ("clip_image", "clip_image_last", "zero_image", "zero_image_last")
IMAGE_CHOICE_LABELS = (
    ("clip_image", "起始图"),
    ("clip_image_last", "结束图"),
    ("zero_image", "Zero 起始"),
    ("zero_image_last", "Zero 结束"),
)


def scene_has_frozen_zero_last(scene) -> bool:
    """True when this scene's zero_image_last was seeded from the project cover."""
    return isinstance(scene, dict) and scene.get(COVER_ORIGIN_KEY) == COVER_ORIGIN_FROZEN


def mark_cover_origin(scene: dict) -> None:
    if isinstance(scene, dict):
        scene[COVER_ORIGIN_KEY] = COVER_ORIGIN_FROZEN


def is_frozen_zero_last_write(scene, slot: str) -> bool:
    """Whether writing ``slot`` would violate the frozen original-cover rule."""
    return str(slot or "") == FROZEN_SLOT and scene_has_frozen_zero_last(scene)


def should_skip_shared_zero_image(scene, slot: str) -> bool:
    """Shared-zero must not overwrite cover-seeded zero stills (first or last)."""
    return str(slot or "") in ("zero_image", "zero_image_last") and scene_has_frozen_zero_last(scene)


def video_import_updates_image_slots(media_type: str) -> bool:
    """Video generation/import may refresh clip stills, never zero stills."""
    return str(media_type or "") != "zero"


def normalize_image_choice(raw, default: str = "clip_image") -> str:
    key = str(raw or "").strip()
    return key if key in IMAGE_CHOICE_KEYS else default


def resolve_video_prompt_images(frames: str, chosen: str, get_image) -> tuple:
    """Images sent with a video prompt.

    Dual-frame mode stays compatible: always clip_image + clip_image_last
    (the picker is only for single-frame mode).
    """
    if str(frames or "") == "two":
        start = (get_image("clip_image") if callable(get_image) else "") or ""
        end = (get_image("clip_image_last") if callable(get_image) else "") or ""
        return start, end
    key = normalize_image_choice(chosen)
    start = (get_image(key) if callable(get_image) else "") or ""
    return start, None


def cover_extract_source(scene, fallback: str = "") -> str:
    """Input image for cover-scene extraction: frozen original, else legacy clip."""
    if scene_has_frozen_zero_last(scene):
        path = str((scene or {}).get(FROZEN_SLOT) or "").strip()
        if path and os.path.isfile(path):
            return path
    path = str((scene or {}).get("clip_image") or "").strip()
    if path and os.path.isfile(path):
        return path
    fb = str(fallback or "").strip()
    return fb if fb and os.path.isfile(fb) else ""


def _existing_file(path: str) -> str:
    p = str(path or "").strip()
    return os.path.abspath(p) if p and os.path.isfile(p) else ""


def _primary_cover_from_mapping(src) -> str:
    """First existing project/item cover file. Never reads scene image slots."""
    if not isinstance(src, dict):
        return ""
    try:
        import project_manager as _pm
        getter = getattr(_pm, "get_primary_cover_image", None)
        if callable(getter):
            found = _existing_file(getter(src) or "")
            if found:
                return found
    except Exception:
        pass
    raw = src.get("cover_image")
    if isinstance(raw, str):
        entries = [raw]
    elif isinstance(raw, (list, tuple)):
        entries = list(raw)
    else:
        entries = []
    for entry in entries:
        found = _existing_file(entry)
        if found:
            return found
    return ""


def resolve_project_cover_image(
    *,
    cover_seeded_path: str = "",
    cover_override: str = "",
    project_config=None,
    item=None,
) -> str:
    """Authoritative original project cover (not a scene still).

    Precedence: ``cover_seeded_path``, then ``cover_override`` (workflow
    ``_seed_cover_override``), then the persistent item/project ``cover_image``
    list (same first-existing file as ``get_primary_cover_image`` / newest-first
    covers[0]). Missing cover returns "".

    Never reads clip_image / clip_image_last / zero_image / zero_image_last.
    After t297u, zero_image_last may be a chained previous-scene tail, so
    ``cover_extract_source`` is not safe for the manual 从封面提取 dialog.
    Automatic ``_maybe_auto_extract_steps_from_cover`` still uses
    ``cover_extract_source`` and is intentionally unchanged.
    """
    for candidate in (cover_seeded_path, cover_override):
        found = _existing_file(candidate)
        if found:
            return found
    for src in (project_config, item):
        found = _primary_cover_from_mapping(src)
        if found:
            return found
    return ""


def list_project_cover_images(
    *,
    cover_seeded_path: str = "",
    cover_override: str = "",
    project_config=None,
    item=None,
) -> list:
    """All existing project/item cover files, deduped, missing skipped.

    Order: ``project_config`` covers (stored newest-first), then any extra
    from ``item``, then seeded/override paths not already listed.
    Does not change project state.
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        found = _existing_file(path)
        if not found:
            return
        key = os.path.normcase(found)
        if key in seen:
            return
        seen.add(key)
        out.append(found)

    def _add_from(src) -> None:
        if not isinstance(src, dict):
            return
        try:
            import project_manager as _pm

            getter = getattr(_pm, "get_cover_images", None)
            if callable(getter):
                for entry in getter(src) or []:
                    _add(entry)
                return
        except Exception:
            pass
        raw = src.get("cover_image")
        if isinstance(raw, str):
            entries = [raw]
        elif isinstance(raw, (list, tuple)):
            entries = list(raw)
        else:
            entries = []
        for entry in entries:
            _add(entry)

    _add_from(project_config)
    _add_from(item)
    for extra in (cover_seeded_path, cover_override):
        _add(extra)
    return out


def normalize_cover_preview_choices(paths, selected: str = "") -> tuple[list, str]:
    """Dedupe existing cover files; pick ``selected`` if present else the first."""
    items: list[str] = []
    seen: set[str] = set()
    for path in paths or []:
        found = _existing_file(path)
        if not found:
            continue
        key = os.path.normcase(found)
        if key in seen:
            continue
        seen.add(key)
        items.append(found)
    pick = _existing_file(selected)
    if pick:
        pkey = os.path.normcase(pick)
        for item in items:
            if os.path.normcase(item) == pkey:
                return items, item
    return items, (items[0] if items else "")


def needs_cover_vs_pdf_prompt(covers, pdf_path: str = "") -> bool:
    """新项目只在「至少一张封面 + 一份分页 PDF」时询问用封面还是 PDF。

    多张封面本身不弹窗挑图：建项目播种用当前封面（列表第一张）。
    """
    has_cover = any(isinstance(c, str) and str(c).strip() for c in (covers or []))
    return bool(has_cover) and bool(str(pdf_path or "").strip())


def covers_for_pdf_prompt(covers) -> list:
    """封面-对-PDF 询问只出示当前封面（covers[0]），不把每张封面都当成选项。"""
    items = [c for c in (covers or []) if isinstance(c, str) and str(c).strip()]
    return items[:1]


def primary_cover_for_seeding(covers, override: str = "") -> str:
    """建项目播种用的封面：有覆盖路径就用覆盖，否则用 covers[0]（当前/最新）。"""
    ov = str(override or "").strip()
    if ov:
        return ov
    items = [c for c in (covers or []) if isinstance(c, str) and str(c).strip()]
    return items[0] if items else ""


def cover_preview_max_size(path: str) -> tuple[int, int]:
    """Preview box larger than the 96x60 four-slot tiles; follow 16:9 vs 9:16."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            width, height = im.size
        if height > width:
            return (180, 320)
    except Exception:
        pass
    return (320, 180)


def manual_cover_extract_images(project_cover: str) -> list:
    """Images submitted for manual cover extract: the true cover, or empty.

    Empty means the caller must disable/error; never fall back to a chosen
    scene slot or chained last frame.
    """
    found = _existing_file(project_cover)
    return [found] if found else []


def _same_file(a: str, b: str) -> bool:
    try:
        return bool(a and b and os.path.isfile(a) and os.path.isfile(b) and os.path.samefile(a, b))
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _copy_independent(source: str, dest: str) -> None:
    """Copy bytes to ``dest`` so dest is a distinct regular file, not a link to source."""
    if not source or not os.path.isfile(source):
        raise FileNotFoundError(f"没有可拷贝的源图：{source}")
    dest_dir = os.path.dirname(dest)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    if os.path.abspath(source) == os.path.abspath(dest):
        raise ValueError(f"源和目标是同一路径，无法做独立拷贝：{dest}")
    safe_copy_overwrite(source, dest)
    if not dest or not os.path.isfile(dest):
        raise RuntimeError(f"独立拷贝失败：{dest}")
    if _same_file(source, dest):
        data = open(source, "rb").read()
        if os.path.exists(dest):
            os.remove(dest)
        with open(dest, "wb") as f:
            f.write(data)
    if _same_file(source, dest):
        raise RuntimeError(f"拷贝后仍与源是同一文件：{dest}")
    try:
        if os.path.islink(dest):
            raise RuntimeError(f"目标是符号链接，不是独立文件：{dest}")
    except OSError:
        pass


def write_independent_slots(scene: dict, slots: Iterable[str], source: str, *,
                            mark_frozen: bool = False) -> dict:
    """Write ``source`` into each slot as its own new file, then update the scene.

    Frozen ``zero_image_last`` is never included. If any copy fails, scene keys
    are left as they were and newly written files are removed.
    Returns {slot: new_path}.
    """
    if not isinstance(scene, dict):
        raise ValueError("scene 必须是字典")
    if not source or not os.path.isfile(source):
        raise FileNotFoundError(f"没有可写入的源图：{source}")
    wanted = []
    for slot in slots:
        slot = str(slot or "").strip()
        if not slot:
            continue
        if is_frozen_zero_last_write(scene, slot):
            continue
        wanted.append(slot)
    if not wanted:
        return {}

    from project_manager import allocate_scene_media_path

    ext = os.path.splitext(source)[1].lower() or ".webp"
    if ext not in (".webp", ".png", ".jpg", ".jpeg"):
        ext = ".webp"

    planned: list[tuple[str, str]] = []
    written: list[str] = []
    try:
        for slot in wanted:
            planned.append((slot, allocate_scene_media_path(scene, slot, ext)))
        seen = set()
        for slot, dest in planned:
            key = os.path.normcase(os.path.abspath(dest))
            if key in seen:
                raise RuntimeError(f"分配了重复路径给 {slot}：{dest}")
            seen.add(key)
        for _slot, dest in planned:
            _copy_independent(source, dest)
            written.append(dest)
        by_inode = []
        for _slot, dest in planned:
            st = os.stat(dest)
            by_inode.append((st.st_dev, st.st_ino))
        if len(set(by_inode)) != len(by_inode):
            raise RuntimeError("多槽写入产生了硬链接或同一 inode，不是独立文件")
        for slot, dest in planned:
            scene[slot] = dest
        if mark_frozen:
            mark_cover_origin(scene)
        return {slot: dest for slot, dest in planned}
    except Exception:
        for dest in written:
            safe_remove(dest)
        raise


def seed_scene_images_from_cover(scene: dict, cover: str) -> dict:
    """Creation: four distinct cover copies + freeze marker. Atomic per scene."""
    return write_independent_slots(scene, COVER_SEED_SLOTS, cover, mark_frozen=True)


def write_edited_scene_images(scene: dict, source: str) -> dict:
    """Edit / cover extraction: three new files; frozen zero_image_last skipped."""
    return write_independent_slots(scene, EDIT_OUTPUT_SLOTS, source, mark_frozen=False)


def write_chained_next_zero_image_last(next_scene: dict, source: str) -> str:
    """Copy a clip last-frame into the next scene's ``zero_image_last``.

    This is the only writer allowed to replace a cover-frozen ``zero_image_last``.
    It does not call ``refresh_scene_media`` and does not change
    ``is_frozen_zero_last_write`` / ``should_skip_shared_zero_image``, so edits,
    shared-zero, drag/drop, and other imports still skip this slot.
    ``zero_image`` is not touched. On failure the next scene's keys and existing
    file stay as they were; a partial dest file is removed.
    """
    if not isinstance(next_scene, dict):
        return ""
    if not source or not os.path.isfile(source):
        raise FileNotFoundError(f"没有可衔接的末帧：{source}")
    from project_manager import allocate_scene_media_path

    ext = os.path.splitext(source)[1].lower() or ".webp"
    if ext not in (".webp", ".png", ".jpg", ".jpeg"):
        ext = ".webp"
    dest = allocate_scene_media_path(next_scene, FROZEN_SLOT, ext)
    try:
        _copy_independent(source, dest)
        if _same_file(source, dest):
            raise RuntimeError(f"衔接拷贝后仍与源是同一文件：{dest}")
        next_scene[FROZEN_SLOT] = dest
        next_scene[ZERO_LAST_CHAIN_KEY] = ZERO_LAST_CHAIN_CLIP
        return dest
    except Exception:
        safe_remove(dest)
        raise


def clone_image_slots(source: dict, dest: dict) -> dict:
    """Copy each still-image slot from ``source`` into a new independent file on ``dest``.

    Includes frozen ``zero_image_last`` (the sibling gets its own copy of the
    original cover, then the cover_origin marker is restored). Dest must not
    keep source paths. On failure dest keys are left as they were and new
    files are removed.
    """
    if not isinstance(source, dict) or not isinstance(dest, dict):
        raise ValueError("source/dest 必须是字典")
    from project_manager import allocate_scene_media_path

    restore = scene_has_frozen_zero_last(source)
    planned: list[tuple[str, str, str]] = []
    for slot in COVER_SEED_SLOTS:
        src = source.get(slot) or ""
        if not (isinstance(src, str) and src and os.path.isfile(src)):
            continue
        ext = os.path.splitext(src)[1].lower() or ".webp"
        if ext not in (".webp", ".png", ".jpg", ".jpeg"):
            ext = ".webp"
        planned.append((slot, src, allocate_scene_media_path(dest, slot, ext)))
    if not planned:
        if restore:
            mark_cover_origin(dest)
        return {}

    written: list[str] = []
    old_values = {slot: dest.get(slot) for slot, _src, _dst in planned}
    old_marker = dest.get(COVER_ORIGIN_KEY)
    try:
        dest.pop(COVER_ORIGIN_KEY, None)
        for slot, src, dst in planned:
            _copy_independent(src, dst)
            written.append(dst)
        by_inode = [(os.stat(dst).st_dev, os.stat(dst).st_ino) for _s, _src, dst in planned]
        if len(set(by_inode)) != len(by_inode):
            raise RuntimeError("克隆场景图产生了硬链接或同一 inode")
        for slot, src, dst in planned:
            if _same_file(src, dst):
                raise RuntimeError(f"克隆后仍与源是同一文件：{dst}")
            dest[slot] = dst
        if restore:
            mark_cover_origin(dest)
        return {slot: dst for slot, _src, dst in planned}
    except Exception:
        for dst in written:
            safe_remove(dst)
        for slot, old in old_values.items():
            if old is None:
                dest.pop(slot, None)
            else:
                dest[slot] = old
        if old_marker is None:
            dest.pop(COVER_ORIGIN_KEY, None)
        else:
            dest[COVER_ORIGIN_KEY] = old_marker
        raise
