"""Copy story media into ``publish/gen_video`` and return the stored path."""

from __future__ import annotations

import hashlib
import os

import config
from utility.file_util import safe_copy_overwrite


def gen_video_dir() -> str:
    folder = (getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or "").strip()
    if folder:
        os.makedirs(folder, exist_ok=True)
    return folder


def is_under_gen_video(path: str) -> bool:
    p = os.path.normpath(os.path.abspath((path or "").strip()))
    folder = os.path.normpath(os.path.abspath(gen_video_dir() or ""))
    if not p or not folder:
        return False
    try:
        return os.path.commonpath([p, folder]) == folder
    except ValueError:
        return False


def unique_media_stem(src: str) -> str:
    h = hashlib.sha1()
    h.update(os.path.abspath(src or "").encode("utf-8", "replace"))
    try:
        st = os.stat(src)
        h.update(str(int(st.st_size)).encode())
        h.update(str(int(st.st_mtime)).encode())
    except OSError:
        pass
    return h.hexdigest()[:12]


def copy_into_gen_video(
    src: str,
    *,
    dest_stem: str | None = None,
    dest_ext: str | None = None,
) -> str:
    """Copy *src* into ``gen_video``; if it is already there, return it unchanged."""
    path = os.path.normpath(os.path.abspath((src or "").strip()))
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(src or path or "empty path")
    folder = gen_video_dir()
    if not folder:
        raise RuntimeError("未配置 INPUT_MEDIA_GEN_VIDEO_PATH（publish/gen_video）")
    if is_under_gen_video(path):
        return path
    ext = (dest_ext or os.path.splitext(path)[1] or ".mp4").lower()
    if not ext.startswith("."):
        ext = "." + ext
    stem = (dest_stem or "").strip() or unique_media_stem(path)
    dest = os.path.abspath(os.path.join(folder, stem + ext))
    if os.path.isfile(dest):
        try:
            if os.path.getsize(dest) == os.path.getsize(path):
                return dest
        except OSError:
            pass
        dest = os.path.abspath(
            os.path.join(folder, unique_media_stem(path + "|" + dest) + ext)
        )
    copied = safe_copy_overwrite(path, dest)
    if not copied or not os.path.isfile(copied):
        raise OSError(f"复制到 gen_video 失败: {path} → {dest}")
    return os.path.abspath(copied)


def copy_clip_records(clips: list[dict] | list[str] | None) -> list[dict]:
    """Copy each clip file into gen_video; keep ``scene`` / ``path`` records."""
    out: list[dict] = []
    for i, item in enumerate(clips or [], 1):
        scene = i
        raw = ""
        extra: dict = {}
        if isinstance(item, str):
            raw = item
        elif isinstance(item, dict):
            raw = str(item.get("path") or "")
            extra = dict(item)
            try:
                scene = int(item.get("scene") or i)
            except (TypeError, ValueError):
                scene = i
        else:
            continue
        src = os.path.normpath(os.path.abspath(raw.strip()))
        if not src or not os.path.isfile(src):
            continue
        try:
            dest = copy_into_gen_video(src)
        except Exception as exc:
            print(f"copy clip to gen_video failed: {exc}")
            dest = src
        rec = dict(extra)
        rec["scene"] = scene
        rec["path"] = dest
        out.append(rec)
    return out
