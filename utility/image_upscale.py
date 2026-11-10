"""t366u: 图片修改 · 提高分辨率 —— 目标尺寸、ComfyUI 画布、结果对齐（纯函数，可离线测）。

尺寸规则（按原图的宽高比，不按项目比例）：
- 长边 = 1920；短边 = 1920 × 短/长，四舍五入到偶数。
- 和 16:9 / 9:16 差不到 1%（例如 MOSS/QN 出的 1360x768）就当 16:9 / 9:16：正好 1920x1080 / 1080x1920。
- 后端回来的图：比例和目标一样 → Lanczos 直接缩放到目标尺寸；比例变了 → 居中裁到原图比例再 Lanczos 缩放（不拉伸）。

t377u 忠实修复（提高分辨率 / 尾帧增强，所有后端）：
- MOSS / QN 不再从空画布整张重画：采样从「原图 Lanczos 缩到画布 → VAEEncode」开始，denoise 用 UPSCALE_INIT_DENOISE
  （只重画细节；构图、颜色、画风强度都跟着原图）。其他图片修改模式不受影响（仍是 denoise=1）。
- 结果回来后 match_color_stats：在 LAB 里把每个通道的均值 / 标准差对齐到原图（Lanczos 放大后的原图），
  亮度、对比度、颜色、饱和度回到原图的水平（全图统计量，不动局部细节；比例有夹限，很温和）。
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


# ---- t377u: 忠实修复 ----
UPSCALE_INIT_DENOISE = {"moss": 0.35, "qn": 0.4}  # 从原图开始采样的重画强度（越小越像原图）
UPSCALE_COLOR_MATCH = True
_STD_RATIO_CLAMP = (0.67, 1.5)


def upscale_init_denoise(backend: str):
    """MOSS / QN 提高分辨率用的 denoise；别的后端 None（不走 init latent）。"""
    return UPSCALE_INIT_DENOISE.get(str(backend or "").strip().lower())


def match_color_stats(img, ref, strength: float = 1.0):
    """把 img 的整体颜色统计对齐到 ref（同尺寸或会先缩到 img 的尺寸）：LAB 每个通道 均值 / 标准差 → ref 的。

    只改全图的亮度、对比度、色偏、饱和度水平，不动局部细节和构图；标准差比例夹在 0.67–1.5 之间。
    strength=0 原样返回，1 = 完全对齐。返回 RGB PIL 图。"""
    import numpy as np
    from PIL import Image

    if img.mode != "RGB":
        img = img.convert("RGB")
    if ref.mode != "RGB":
        ref = ref.convert("RGB")
    if ref.size != img.size:
        ref = ref.resize(img.size, Image.Resampling.LANCZOS)
    k = max(0.0, min(1.0, float(strength)))
    if k <= 0:
        return img.copy()
    a = np.asarray(img, dtype=np.float32) / 255.0
    b = np.asarray(ref, dtype=np.float32) / 255.0
    try:
        import cv2

        la, lb = cv2.cvtColor(a, cv2.COLOR_RGB2LAB), cv2.cvtColor(b, cv2.COLOR_RGB2LAB)
        back = lambda x: cv2.cvtColor(x, cv2.COLOR_LAB2RGB)  # noqa: E731
    except Exception:  # noqa: BLE001  没有 cv2：在 RGB 里做
        la, lb = a.copy(), b.copy()
        back = lambda x: x  # noqa: E731
    out = la.copy()
    for c in range(3):
        ma, sa = float(la[..., c].mean()), float(la[..., c].std())
        mb, sb = float(lb[..., c].mean()), float(lb[..., c].std())
        r = (sb / sa) if sa > 1e-6 else 1.0
        r = min(max(r, _STD_RATIO_CLAMP[0]), _STD_RATIO_CLAMP[1])
        matched = (la[..., c] - ma) * r + mb
        out[..., c] = la[..., c] + k * (matched - la[..., c])
    rgb = np.clip(back(out), 0.0, 1.0)
    return Image.fromarray((rgb * 255.0 + 0.5).astype(np.uint8), "RGB")


def finish_upscale(img, size, source=None, *, color_match=None):
    """后端结果 → 目标尺寸（fit_to_size），再按原图对齐颜色统计（source = 原图路径或 PIL；没有就只对齐尺寸）。"""
    from PIL import Image

    out = fit_to_size(img, size)
    if out.mode != "RGB":
        out = out.convert("RGB")
    use = UPSCALE_COLOR_MATCH if color_match is None else bool(color_match)
    if not use or source is None:
        return out
    try:
        if isinstance(source, str):
            with Image.open(source) as im:
                ref = fit_to_size(im.convert("RGB"), size)
        else:
            ref = fit_to_size(source, size)
        return match_color_stats(out, ref)
    except Exception as exc:  # noqa: BLE001
        print(f"提高分辨率：颜色对齐没做成，用后端原样的结果：{exc}")
        return out
