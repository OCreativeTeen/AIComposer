"""t366u: 图片修改 · 提高分辨率 —— target size, result fit, prompts, dialog / write-back wiring (offline)."""
from __future__ import annotations

import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_comfy_edit_prompts import GROK_GEMINI_DIGEST, _body, cp, grok_gemini_cases, sdp  # noqa: E402
from utility.image_upscale import (  # noqa: E402
    comfy_upscale_canvas,
    fit_to_size,
    upscale_target_for_image,
    upscale_target_size,
)


_CASES_DIGEST_AT_IMPORT = hashlib.sha256("\n<<>>\n".join(grok_gemini_cases()).encode("utf-8")).hexdigest()


class TargetSizeTest(unittest.TestCase):
    def test_16_9_and_9_16(self):
        self.assertEqual(upscale_target_size(1920, 1080), (1920, 1080))
        self.assertEqual(upscale_target_size(1280, 720), (1920, 1080))
        self.assertEqual(upscale_target_size(1080, 1920), (1080, 1920))
        self.assertEqual(upscale_target_size(720, 1280), (1080, 1920))
        self.assertEqual(upscale_target_size(3840, 2160), (1920, 1080))  # already bigger → still the 1920 class

    def test_near_16_9_snaps(self):
        # MOSS / QN canvases (1360x768, 768x1360) and 1920x1088 are within 1% of 16:9 / 9:16
        self.assertEqual(upscale_target_size(1360, 768), (1920, 1080))
        self.assertEqual(upscale_target_size(768, 1360), (1080, 1920))
        self.assertEqual(upscale_target_size(1920, 1088), (1920, 1080))

    def test_other_ratios_long_side_1920_even(self):
        self.assertEqual(upscale_target_size(1024, 768), (1920, 1440))   # 4:3
        self.assertEqual(upscale_target_size(768, 1024), (1440, 1920))   # 3:4
        self.assertEqual(upscale_target_size(1000, 1000), (1920, 1920))  # square
        self.assertEqual(upscale_target_size(2752, 384), (1920, 268))    # tall cover strip turned sideways
        self.assertEqual(upscale_target_size(1000, 1234), (1556, 1920))  # 1555.9 → 1556 (even)
        self.assertEqual(upscale_target_size(1234, 1000), (1920, 1556))
        self.assertEqual(upscale_target_size(1000, 1237), (1552, 1920))  # 1552.1 → 1552
        for w, h in ((1000, 1234), (777, 555), (333, 1001), (1501, 999)):
            tw, th = upscale_target_size(w, h)
            self.assertEqual(max(tw, th), 1920)
            self.assertEqual(tw % 2 + th % 2, 0)
            self.assertLess(abs((tw / th) / (w / h) - 1), 0.002)

    def test_bad_input(self):
        self.assertEqual(upscale_target_size(0, 100), ())
        self.assertEqual(upscale_target_size(None, 100), ())

    def test_for_image_and_comfy_canvas(self):
        import tempfile

        from PIL import Image

        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "a.png")
            Image.new("RGB", (640, 480)).save(p)
            self.assertEqual(upscale_target_for_image(p), (1920, 1440))
        self.assertEqual(comfy_upscale_canvas((1920, 1080)), (1920, 1088))
        self.assertEqual(comfy_upscale_canvas((1080, 1920)), (1088, 1920))
        self.assertEqual(comfy_upscale_canvas((1556, 1920)), (1552, 1920))
        for size in ((1920, 1080), (1556, 1920), (1920, 268)):
            cw, ch = comfy_upscale_canvas(size)
            self.assertEqual((cw % 16, ch % 16), (0, 0))


class FitTest(unittest.TestCase):
    def _img(self, w, h):
        from PIL import Image

        im = Image.new("RGB", (w, h), (0, 0, 255))
        # red band in the middle third so we can see what a crop keeps
        im.paste((255, 0, 0), (w // 3, 0, 2 * w // 3, h))
        return im

    def test_same_aspect_is_plain_lanczos(self):
        out = fit_to_size(self._img(1360, 765), (1920, 1080))
        self.assertEqual(out.size, (1920, 1080))
        self.assertEqual(out.getpixel((960, 540)), (255, 0, 0))

    def test_canvas_1088_is_center_cropped_not_stretched(self):
        from PIL import Image

        im = Image.new("RGB", (1920, 1088), (0, 255, 0))
        im.paste((255, 0, 0), (0, 0, 1920, 4))       # top 4 rows
        im.paste((255, 0, 0), (0, 1084, 1920, 1088))  # bottom 4 rows
        out = fit_to_size(im, (1920, 1080))
        self.assertEqual(out.size, (1920, 1080))
        self.assertEqual(out.getpixel((960, 0)), (0, 255, 0))
        self.assertEqual(out.getpixel((960, 1079)), (0, 255, 0))

    def test_changed_aspect_center_fit(self):
        # backend returned a square for a 16:9 target → keep the center, crop top/bottom, no stretch
        out = fit_to_size(self._img(1024, 1024), (1920, 1080))
        self.assertEqual(out.size, (1920, 1080))
        self.assertEqual(out.getpixel((960, 540)), (255, 0, 0))
        self.assertEqual(out.getpixel((100, 540)), (0, 0, 255))
        # too wide for a portrait target → crop the sides
        out = fit_to_size(self._img(1920, 1080), (1080, 1920))
        self.assertEqual(out.size, (1080, 1920))
        self.assertEqual(out.getpixel((540, 960)), (255, 0, 0))

    def test_mode_and_exact_size(self):
        from PIL import Image

        out = fit_to_size(Image.new("L", (100, 100), 128), (1920, 1920))
        self.assertEqual((out.mode, out.size), ("RGB", (1920, 1920)))
        same = Image.new("RGB", (1920, 1080))
        self.assertEqual(fit_to_size(same, (1920, 1080)).size, (1920, 1080))


class UpscalePromptTest(unittest.TestCase):
    def test_grok_prompt_is_strict(self):
        p = cp.build_upscale_prompt((1920, 1080))
        for must in ("FAITHFUL RESTORE", "FAITHFUL UPSCALE / RESTORE ONLY", "exactly 1920x1080", "16:9 landscape",
                     "same aspect ratio", "look exactly the same", "same art style at the same strength",
                     "contrast, brightness, saturation", "No color grading", "Keep the picture identical",
                     "composition", "faces", "poses", "clothing", "objects", "text", "colors", "lighting",
                     "camera framing", "Only restore image quality", "remove noise", "recover fine detail",
                     "看上去一模一样", "不调色", "不改画风", "输出尺寸 1920x1080"):
            self.assertIn(must, p, must)
        self.assertNotIn("OUTPUT FORMAT", p)  # no project aspect line
        self.assertIn("9:16 portrait", cp.build_upscale_prompt((1080, 1920)))
        self.assertIn("exactly 1556x1920", cp.build_upscale_prompt((1556, 1920)))
        self.assertIn("4:3 landscape", cp.build_upscale_prompt((1920, 1440)))
        self.assertIn("1556:1920 portrait", cp.build_upscale_prompt((1556, 1920)))

    def test_comfy_prompt_and_negative(self):
        pos, neg = cp.build_comfy_upscale_prompt((1920, 1080), backend="moss")
        self.assertTrue(_body(pos).startswith("Restore image 1 as a clean, sharp, high-resolution 1920x1080"))
        self.assertIn("same art style at the same strength", pos)
        self.assertNotIn("16:9", pos)
        self.assertNotIn("OUTPUT FORMAT", pos)
        qpos, qneg = cp.build_comfy_upscale_prompt((1920, 1080), backend="qn")
        self.assertIn("Restore Picture 1", qpos)
        self.assertEqual(neg, qneg)
        for must in ("changed composition", "new objects", "style change", "extra people", "altered face",
                     "text changes", "blurry", "noise", "sharpening halos", "artifacts", "more cartoonish",
                     "more realistic", "color shift", "higher contrast", "brighter", "oversaturated"):
            self.assertIn(must, neg, must)
        fpos, _ = cp.build_comfy_upscale_prompt((1920, 1080), backend="qn", fyi="  让脸更清楚  ")
        self.assertTrue(_body(fpos).startswith("让脸更清楚\nRestore Picture 1"))

    def test_existing_grok_gemini_prompts_unchanged(self):
        # digest taken at import (other test modules later swap in a project_manager stub)
        self.assertEqual(_CASES_DIGEST_AT_IMPORT, GROK_GEMINI_DIGEST)


class ComfyCanvasTest(unittest.TestCase):
    def test_moss_and_qn_accept_upscale_canvas(self):
        with open(sdp.MOSS_EDIT_API_WORKFLOW, encoding="utf-8-sig") as f:
            mwf = json.load(f)
        wf = sdp.build_moss_edit_prompt(mwf, base_name="b.png", ref_names=[], prompt="p", seed=1,
                                        negative=cp.COMFY_UPSCALE_NEGATIVE, width=1920, height=1088)
        lat = sdp._one_node(wf, "EmptyFlux2LatentImage")
        self.assertEqual((wf[lat]["inputs"]["width"], wf[lat]["inputs"]["height"]), (1920, 1088))
        with open(sdp.QN_EDIT_API_WORKFLOW, encoding="utf-8-sig") as f:
            qwf = json.load(f)
        wf = sdp.build_qwen_edit_prompt(qwf, base_name="b.png", ref_names=[], prompt="p", seed=1,
                                        negative="n", width=1920, height=1088, base_size=(1920, 1080))
        ks = sdp._one_node(wf, "KSampler")
        lat = wf[ks]["inputs"]["latent_image"][0]
        self.assertEqual((wf[lat]["inputs"]["width"], wf[lat]["inputs"]["height"]), (1920, 1088))
        self.assertEqual(wf["117"]["class_type"], "ImageScaleToTotalPixels")  # same aspect → aligned base


class DialogWiringTest(unittest.TestCase):
    src = (ROOT / "gui" / "picture_prompt_dialog.py").read_text(encoding="utf-8")
    flows = (ROOT / "gui" / "workflow" / "wf_prompt_flows.py").read_text(encoding="utf-8")
    images = (ROOT / "gui" / "workflow" / "wf_images.py").read_text(encoding="utf-8")

    def test_mode_listed_with_description(self):
        tree = ast.parse(self.src)
        modes = next(ast.literal_eval(n.value) for n in tree.body
                     if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PICTURE_EDIT_MODES")
        keys = [m[0] for m in modes]
        self.assertEqual(keys, ["modify", "cover", "cast", "portrait", "upscale"])
        title, desc = modes[-1][1], modes[-1][2]
        self.assertEqual(title, "提高分辨率")
        self.assertIn("1920", desc)
        self.assertNotIn("\n", desc)

    def test_upscale_branch_uses_both_prompt_sets_and_batch(self):
        body = self.src.split("def _go_upscale", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("config_prompt.build_upscale_prompt(target, style_up)", body)  # t373u: 项目画风
        self.assertIn("config_prompt.build_comfy_upscale_prompt(target, backend=comfy", body)
        self.assertIn("style=style_up", body)
        self.assertIn("comfy_upscale_canvas(target)", body)
        self.assertIn('"upscale_size": target', body)
        self.assertIn("run_batch(jobs, backend, skipped, account)", body)
        self.assertIn("upscale=m_[\"upscale_size\"]", body)
        self.assertNotIn("output_aspect_line", body)  # no project aspect line in upscale prompts
        go = self.src.split("def on_go", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('if mode == "upscale":\n            _go_upscale(backend, account, comfy)', go)
        # 提交 offers all four backends for upscale (only portrait is Grok-only)
        sub = self.src.split("def on_submit", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('extra_backends=(("moss", "MOSS"), ("qn", "QN"))', sub)

    def test_result_is_fitted_and_written_at_target_size(self):
        om = self.flows.split("def open_manual", 1)[1].split("\n        def batch_scenes", 1)[0]
        self.assertIn("upscale=None", om)
        self.assertIn("finish_upscale(pil_img, upscale, images[0] if images else None)", om)  # t377u
        self.assertIn('extra["comfy_init_denoise"] = comfy["init_denoise"]', om)
        self.assertIn("exact_size=tuple(upscale)", om)
        batch = self.flows.split("def _run_picture_batch", 1)[1]
        apply = batch.split("def apply(scene, img, label)", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("finish_upscale(img, up, upscale_base.get(id(scene)))", apply)  # t377u
        self.assertIn("exact_size=up", apply)
        rep = self.images.split("def _replace_current_clip_image_from_pil", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("exact_size=None", rep)
        self.assertIn("resize_image_smart(tmp_path, int(exact_size[0]), int(exact_size[1]))", rep)
        self.assertIn("resize_image_smart(tmp_path)", rep)  # other modes unchanged


if __name__ == "__main__":
    unittest.main()
