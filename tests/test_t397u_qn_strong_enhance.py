"""t397u: QN last-frame enhance = strong but faithful (denoise 0.55, 1.5x supersample canvas, light USM)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utility import image_upscale as iu  # noqa: E402


def _img(w=240, h=160):
    import numpy as np
    from PIL import Image

    from PIL import ImageFilter

    yy, xx = np.mgrid[0:h, 0:w]
    check = (((xx // 6) + (yy // 6)) % 2).astype(np.float32)[..., None]  # fine texture
    base = np.where(check > 0, (170, 120, 90), (110, 80, 60)).astype(np.float32)
    base[:, w // 2:] += (-40, 0, 50)
    return Image.fromarray(np.clip(base, 0, 255).astype("uint8"), "RGB").filter(ImageFilter.GaussianBlur(1.5))


def _lapvar(img):
    import numpy as np

    g = np.asarray(img.convert("L"), np.float32)
    lap = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]
    return float(lap.var())


class QnStrongEnhanceTest(unittest.TestCase):
    def test_settings(self):
        self.assertEqual(iu.upscale_init_denoise("qn"), 0.55)
        self.assertEqual(iu.upscale_init_denoise("moss"), 0.35)  # MOSS unchanged
        self.assertEqual(iu.upscale_supersample("QN"), 1.5)
        self.assertEqual(iu.upscale_supersample("moss"), 1.0)
        self.assertEqual(iu.upscale_supersample("grok"), 1.0)
        self.assertEqual(iu.upscale_sharpen("qn"), (1.2, 80, 2))
        self.assertIsNone(iu.upscale_sharpen("moss"))
        self.assertIsNone(iu.upscale_sharpen("none"))

    def test_supersample_canvas(self):
        self.assertEqual(iu.comfy_upscale_canvas((1080, 1920), 1.5), (1616, 2880))
        self.assertEqual(iu.comfy_upscale_canvas((1920, 1080), 1.5), (2880, 1616))
        self.assertEqual(iu.comfy_upscale_canvas((1080, 1920), 1.0), (1088, 1920))
        self.assertEqual(iu.comfy_upscale_canvas((1080, 1920)), (1088, 1920))
        for c in iu.comfy_upscale_canvas((1556, 1920), 1.5):
            self.assertEqual(c % 16, 0)

    def test_sharpen_adds_detail_keeps_colour(self):
        import numpy as np

        src = _img()
        out = iu.sharpen_detail(src, iu.upscale_sharpen("qn"))
        self.assertEqual(out.size, src.size)
        self.assertGreater(_lapvar(out), _lapvar(src) * 1.2)
        a, b = np.asarray(src, np.float32), np.asarray(out, np.float32)
        self.assertLess(abs(a.mean() - b.mean()), 1.0)  # overall colour / brightness kept
        for c in range(3):
            self.assertLess(abs(a[..., c].mean() - b[..., c].mean()), 1.5)
        self.assertIs(iu.sharpen_detail(src, None), src)

    def test_finish_upscale_sharpen_after_supersample(self):
        src = _img(108, 192)
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            src.save(path)
            back = src.resize((162, 288))  # 1.5x supersampled backend result
            plain = iu.finish_upscale(back, (108, 192), path)
            sharp = iu.finish_upscale(back, (108, 192), path, sharpen=iu.upscale_sharpen("qn"))
            self.assertEqual(sharp.size, (108, 192))
            self.assertGreater(_lapvar(sharp), _lapvar(plain))
            self.assertEqual(list(iu.finish_upscale(back, (108, 192), path, sharpen=None).getdata()),
                             list(plain.getdata()))
        finally:
            os.remove(path)

    def test_last_frame_enhance_passes_sharpen(self):
        from utility import video_segments as vs

        src = _img(108, 192)
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        outs = []
        try:
            src.save(path)
            big = _img(1620, 2880)  # 1.5x supersampled result for the 1080x1920 target
            up = lambda p, t, s: big  # noqa: E731
            for sh in (None, iu.upscale_sharpen("qn")):
                out, ok, _ = vs.enhance_last_frame(path, upscale=up, sharpen=sh)
                self.assertTrue(ok)
                outs.append(out)
            from PIL import Image

            with Image.open(outs[0]) as a, Image.open(outs[1]) as b:
                self.assertGreater(_lapvar(b), _lapvar(a))
        finally:
            for p in [path] + outs:
                if os.path.isfile(p):
                    os.remove(p)


if __name__ == "__main__":
    unittest.main()
