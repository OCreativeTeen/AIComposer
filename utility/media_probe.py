"""ffprobe helpers (moved verbatim from gui/downloader.py)."""
import os
import subprocess


def _ffprobe_video_height(path: str) -> int | None:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=height",
                "-of",
                "csv=p=0:s=x",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        h = int((r.stdout or "").strip())
        return h if h > 0 else None
    except Exception:
        return None


def _media_duration_seconds(path: str) -> float:
    """这条音频或视频的真实长度，秒，保留两位。量不到就返回 0。"""
    import shutil
    import subprocess

    path = (path or "").strip()
    if not path or not os.path.isfile(path):
        return 0.0
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        out = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", path,
            ],
            capture_output=True, text=True, timeout=20,
        )
        return max(0.0, round(float((out.stdout or "").strip() or 0), 2))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0
