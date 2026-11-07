"""Local still-image preview clips: no TTS, no network, no shared full-speech audio."""
from __future__ import annotations

import os
import re
import shutil
import subprocess

from utility.speaking_marks import PAUSE_MARK_RE, strip_speaker_marks

# Approximate spoken pace for a silent preview when clip_audio is not ready.
_CJK_CHARS_PER_SEC = 4.0
_LATIN_CHARS_PER_SEC = 12.0
_MIN_PREVIEW_SEC = 1.0
_MAX_PREVIEW_SEC = 120.0


def estimate_speaking_preview_seconds(speaking: str) -> float:
    raw = str(speaking or "")
    pauses = 0.0
    for match in PAUSE_MARK_RE.finditer(raw):
        num = re.search(r"\d+\.\d+", match.group(0) or "")
        if not num:
            continue
        try:
            value = float(num.group(0))
        except (TypeError, ValueError):
            continue
        if value > 0:
            pauses += value
    text = strip_speaker_marks(raw, pauses=True)
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf")
    other = sum(1 for ch in text if not ch.isspace()) - cjk
    speech = 0.0
    if cjk > 0:
        speech += cjk / _CJK_CHARS_PER_SEC
    if other > 0:
        speech += other / _LATIN_CHARS_PER_SEC
    duration = pauses + speech
    if duration <= 0:
        duration = 2.0
    return max(_MIN_PREVIEW_SEC, min(_MAX_PREVIEW_SEC, duration))


def write_still_preview_mp4(
    image_path: str,
    dest_path: str,
    *,
    duration: float,
    audio_path: str = "",
) -> str:
    """Write a readable still mp4 from ``image_path``.

    Uses ``audio_path`` only when that file exists (the caller's own half audio).
    Otherwise muxes generated silence of ``duration`` seconds. Never invents TTS.
    """
    if not (image_path and os.path.isfile(image_path)):
        raise FileNotFoundError("没有场景图，无法生成预览视频")
    dest_dir = os.path.dirname(dest_path) or "."
    os.makedirs(dest_dir, exist_ok=True)
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = _MIN_PREVIEW_SEC
    duration = max(_MIN_PREVIEW_SEC, min(_MAX_PREVIEW_SEC, duration))
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", image_path,
    ]
    own_audio = bool(audio_path and os.path.isfile(audio_path))
    if own_audio:
        cmd += ["-i", audio_path, "-shortest"]
    else:
        cmd += [
            "-f", "lavfi",
            "-t", f"{duration:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", f"{duration:.3f}",
            "-shortest",
        ]
    cmd += [
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", dest_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"生成静态预览视频失败: {err}") from exc
    if not os.path.isfile(dest_path) or os.path.getsize(dest_path) <= 0:
        raise RuntimeError("生成静态预览视频失败: 文件为空")
    return dest_path


def attach_still_preview_to_scene(scene: dict, dest_path: str, *, audio_path: str = "") -> str:
    """Estimate duration from this scene's speaking and write ``dest_path`` as ``clip``.

    Does not write silent audio onto ``clip_audio``. Returns the clip path.
    """
    if not isinstance(scene, dict):
        raise ValueError("scene 必须是字典")
    image = scene.get("clip_image") or ""
    own_audio = ""
    if audio_path and os.path.isfile(audio_path):
        own_audio = audio_path
    else:
        existing = scene.get("clip_audio") or ""
        if existing and os.path.isfile(existing):
            own_audio = existing
    duration = estimate_speaking_preview_seconds(scene.get("speaking") or "")
    write_still_preview_mp4(image, dest_path, duration=duration, audio_path=own_audio)
    scene["clip"] = dest_path
    return dest_path
