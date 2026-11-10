"""t366u: 图片修改 · 提高分辨率 —— 目标尺寸、ComfyUI 画布、结果对齐（纯函数，可离线测）。

尺寸规则（按原图的宽高比，不按项目比例）：
- 长边 = 1920；短边 = 1920 × 短/长，四舍五入到偶数。
- 和 16:9 / 9:16 差不到 1%（例如 MOSS/QN 出的 1360x768）就当 16:9 / 9:16：正好 1920x1080 / 1080x1920。
- 后端回来的图：比例和目标一样 → Lanczos 直接缩放到目标尺寸；比例变了 → 居中裁到原图比例再 Lanczos 缩放（不拉伸）。
"""
from __future__ import annotations

UPSCALE_LONG_SIDE = 1920
_SNAP_TOLERANCE = 0.01  # 同 ffmpeg_processor.resize_image_smart 的「比例基本相同」


def _even(x: float) -> int:
    return max(2, int(round(x / 2.0)) * 2)


def upscale_target_size(width, height, long_side: int = UPSCALE_LONG_SIDE) -> tuple:
    """原图宽高 → 提高分辨率的目标尺寸 (w, h)。读不到返回 ()。"""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        return ()
    if w <= 0 or h <= 0:
        return ()
    long_side = int(long_side)
    ratio = w / float(h)
    for rw, rh in ((16, 9), (9, 16)):
        if abs(ratio / (rw / rh) - 1.0) < _SNAP_TOLERANCE:
            return (long_side, _even(long_side * 9 / 16)) if rw > rh else (_even(long_side * 9 / 16), long_side)
    if w >= h:
        return long_side, _even(long_side * h / float(w))
    return _even(long_side * w / float(h)), long_side


def upscale_target_for_image(path: str, long_side: int = UPSCALE_LONG_SIDE) -> tuple:
    from PIL import Image

    with Image.open(path) as im:
        return upscale_target_size(im.width, im.height, long_side)


def comfy_upscale_canvas(size) -> tuple:
    """目标尺寸 → MOSS / QN 的固定画布：每边就近取 16 的倍数（1920x1080 → 1920x1088），结果再对齐回目标尺寸。"""
    try:
        w, h = (int(v) for v in size)
    except (TypeError, ValueError):
        return ()
    if w <= 0 or h <= 0:
        return ()
    return max(16, int(round(w / 16.0)) * 16), max(16, int(round(h / 16.0)) * 16)


def fit_to_size(img, size):
    """后端回来的图 → 正好 size（宽, 高）的 RGB 图：比例相同直接 Lanczos；不同就居中裁到目标比例再 Lanczos（不拉伸）。"""
    from PIL import Image

    tw, th = (int(v) for v in size)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    sw, sh = img.size
    if (sw, sh) == (tw, th):
        return img.copy()
    want, have = tw / float(th), sw / float(sh)
    if abs(have / want - 1.0) > 1e-3:
        if have > want:  # 太宽：左右各裁一点
            nw = max(1, int(round(sh * want)))
            left = (sw - nw) // 2
            img = img.crop((left, 0, left + nw, sh))
        else:  # 太高：上下各裁一点
            nh = max(1, int(round(sw / want)))
            top = (sh - nh) // 2
            img = img.crop((0, top, sw, top + nh))
        if abs(have / want - 1.0) > 0.02:
            print(f"提高分辨率：后端回来的图 {sw}x{sh} 比例和原图不一样，已居中裁到原图比例（不拉伸）再缩到 {tw}x{th}")
    return img.resize((tw, th), Image.Resampling.LANCZOS)
