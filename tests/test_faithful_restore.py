"""t377u: upscale / last-frame enhance = faithful restore (low-denoise init latent + colour-stat match)."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_comfy_edit_prompts import cp, sdp  # noqa: E402
from utility import image_upscale as iu  # noqa: E402

CARTOON = "三维卡通 (Pixar-Art-Cartoon)"


def _wf(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _refs(wf, nid):
    return [k for k, n in wf.items() for v in n.get("inputs", {}).values()
            if isinstance(v, list) and v and str(v[0]) == str(nid)]


class RestorePromptTest(unittest.TestCase):
    def test_rule_text(self):
        r = cp.upscale_restore_rule(CARTOON, "Image 1")
        self.assertTrue(r.startswith(cp.UPSCALE_RESTORE_PREFIX))
        for bit in ("look exactly the same as Image 1", "same art style at the same strength",
                    "colors, contrast, brightness, saturation, tone", "currently in 3D animation style",
                    "only a description", "not a request to change, strengthen or improve the style",
                    "more cartoonish, more 3D, more realistic", "看上去一模一样", "只是说明这张图现在是什么样子"):
            self.assertIn(bit, r)
        self.assertNotIn("忠实修复", cp.upscale_restore_rule(CARTOON, zh=False))
        self.assertNotIn("currently in", cp.upscale_restore_rule(""))

    def test_style_lock_first_moves_restore_rule(self):
        p = "FYI 脸清楚一点\n\n" + cp.build_upscale_prompt((1920, 1080), CARTOON)
        out = cp.style_lock_first(p)
        self.assertTrue(out.startswith(cp.UPSCALE_RESTORE_PREFIX))
        self.assertNotIn(cp.IMAGE_STYLE_LOCK_PREFIX, out)
        self.assertIn("FYI 脸清楚一点", out)
        self.assertEqual(cp.style_lock_first(out), out)

    def test_other_modes_keep_style_lock(self):
        pos, _ = cp.build_comfy_picture_edit_prompt(backend="qn", task="keep", visual_style=CARTOON, edit_request="x")
        self.assertTrue(pos.startswith(cp.IMAGE_STYLE_LOCK_PREFIX))


class InitLatentWorkflowTest(unittest.TestCase):
    def test_moss_init_latent(self):
        wf = sdp.build_moss_edit_prompt(_wf(sdp.MOSS_EDIT_API_WORKFLOW), base_name="b.png", ref_names=[], prompt="p",
                                        seed=1, width=1088, height=1920, init_denoise=0.35)
        ks = wf[sdp._one_node(wf, "KSampler")]["inputs"]
        self.assertEqual(ks["denoise"], 0.35)
        enc = wf[str(ks["latent_image"][0])]
        self.assertEqual(enc["class_type"], "VAEEncode")
        sc = wf[str(enc["inputs"]["pixels"][0])]
        self.assertEqual(sc["class_type"], "ImageScale")
        self.assertEqual((sc["inputs"]["width"], sc["inputs"]["height"]), (1088, 1920))
        self.assertEqual(wf[str(sc["inputs"]["image"][0])]["inputs"]["image"], "b.png")
        self.assertEqual(sdp._find_nodes(wf, "EmptyFlux2LatentImage"), [])
        self.assertEqual(sdp._find_nodes(wf, "GetImageSize"), [])
        for nid, node in wf.items():  # nothing dangling
            for v in node.get("inputs", {}).values():
                if isinstance(v, list) and v and isinstance(v[0], str):
                    self.assertIn(v[0], wf, (nid, v))

    def test_moss_default_unchanged(self):
        wf = sdp.build_moss_edit_prompt(_wf(sdp.MOSS_EDIT_API_WORKFLOW), base_name="b.png", ref_names=[], prompt="p",
                                        seed=1, width=1088, height=1920)
        ks = wf[sdp._one_node(wf, "KSampler")]["inputs"]
        self.assertEqual(ks["denoise"], 1.0)
        self.assertEqual(wf[str(ks["latent_image"][0])]["class_type"], "EmptyFlux2LatentImage")

    def test_qn_init_latent(self):
        wf = sdp.build_qwen_edit_prompt(_wf(sdp.QN_EDIT_API_WORKFLOW), base_name="b.png", ref_names=[], prompt="p",
                                        seed=1, width=1920, height=1088, base_size=(1312, 736), init_denoise=0.4)
        ks = wf[sdp._one_node(wf, "KSampler")]["inputs"]
        self.assertEqual(ks["denoise"], 0.4)
        enc = wf[str(ks["latent_image"][0])]
        self.assertEqual(enc["class_type"], "VAEEncode")
        self.assertNotIn("qn_canvas", wf)
        sc = wf[str(enc["inputs"]["pixels"][0])]
        self.assertEqual((sc["inputs"]["width"], sc["inputs"]["height"]), (1920, 1088))
        self.assertEqual(sdp._find_nodes(wf, "EmptySD3LatentImage"), [])
        wf0 = sdp.build_qwen_edit_prompt(_wf(sdp.QN_EDIT_API_WORKFLOW), base_name="b.png", ref_names=[], prompt="p",
                                         seed=1, width=1920, height=1088, base_size=(1312, 736))
        ks0 = wf0[sdp._one_node(wf0, "KSampler")]["inputs"]
        self.assertEqual((ks0["denoise"], ks0["latent_image"][0]), (1.0, "qn_canvas"))

    def test_init_needs_canvas_and_valid_denoise(self):
        with self.assertRaises(ValueError):
            sdp.build_moss_edit_prompt(_wf(sdp.MOSS_EDIT_API_WORKFLOW), base_name="b", ref_names=[], prompt="p",
                                       seed=1, init_denoise=0.3)
        with self.assertRaises(ValueError):
            sdp.build_qwen_edit_prompt(_wf(sdp.QN_EDIT_API_WORKFLOW), base_name="b", ref_names=[], prompt="p",
                                       seed=1, width=1920, height=1088, init_denoise=0)

    def test_denoise_table(self):
        self.assertEqual(iu.upscale_init_denoise("MOSS"), iu.UPSCALE_INIT_DENOISE["moss"])
        self.assertEqual(iu.upscale_init_denoise("qn"), iu.UPSCALE_INIT_DENOISE["qn"])
        self.assertIsNone(iu.upscale_init_denoise("grok"))
        for v in iu.UPSCALE_INIT_DENOISE.values():
            self.assertTrue(0.2 <= v <= 0.6)


class ColorMatchTest(unittest.TestCase):
    def _grad(self, w, h, gain=1.0, off=0):
        import numpy as np
        from PIL import Image

        x = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
        y = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        base = np.concatenate([np.broadcast_to(c, (h, w, 1)) for c in (x * 200 + 20, y * 150 + 40, (x + y) * 60 + 50)],
                              axis=2)
        arr = np.clip((base - 128) * gain + 128 + off, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, "RGB")

    def test_brightness_contrast_shift_is_undone(self):
        import numpy as np

        ref = self._grad(320, 180)
        bad = self._grad(320, 180, gain=1.3, off=25)  # brighter + more contrast
        out = iu.match_color_stats(bad, ref)
        d_bad = np.abs(np.asarray(bad, np.float32) - np.asarray(ref, np.float32)).mean()
        d_out = np.abs(np.asarray(out, np.float32) - np.asarray(ref, np.float32)).mean()
        self.assertLess(d_out, d_bad * 0.3)
        self.assertEqual(out.size, ref.size)

    def test_strength_zero_and_identity(self):
        import numpy as np

        ref = self._grad(64, 36)
        same = iu.match_color_stats(ref, ref)
        self.assertLess(np.abs(np.asarray(same, np.float32) - np.asarray(ref, np.float32)).max(), 2.5)
        bad = self._grad(64, 36, off=30)
        self.assertEqual(list(iu.match_color_stats(bad, ref, strength=0).getdata()), list(bad.getdata()))

    def test_finish_upscale_fits_and_matches(self):
        import tempfile

        import numpy as np

        src = self._grad(1312, 736)
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            src.save(path)
            back = self._grad(1920, 1088, gain=1.2, off=20)
            out = iu.finish_upscale(back, (1920, 1080), path)
            self.assertEqual(out.size, (1920, 1080))
            ref = iu.fit_to_size(src, (1920, 1080))
            l_out = np.asarray(out, np.float32).mean()
            self.assertAlmostEqual(l_out, np.asarray(ref, np.float32).mean(), delta=2.0)
            raw = iu.finish_upscale(back, (1920, 1080), path, color_match=False)
            self.assertGreater(np.asarray(raw, np.float32).mean() - l_out, 10)
            self.assertEqual(iu.finish_upscale(back, (1920, 1080), None).size, (1920, 1080))
        finally:
            os.remove(path)


class WiringTest(unittest.TestCase):
    def _src(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_picture_dialog_and_llm_api_carry_init_denoise(self):
        dlg = self._src("gui/picture_prompt_dialog.py")
        self.assertIn('"init_denoise": upscale_init_denoise(comfy)', dlg)
        api = self._src("utility/llm_api.py")
        self.assertIn('_cf["init_denoise"] = extra_params.get("comfy_init_denoise")', api)
        flows = self._src("gui/workflow/wf_prompt_flows.py")
        self.assertIn('kw["init_denoise"] = meta["init_denoise"]', flows)

    def test_last_frame_uses_finish_upscale(self):
        vs = self._src("utility/video_segments.py")
        self.assertIn("img = finish_upscale(img, target, frame_path, sharpen=sharpen)", vs)
        self.assertIn("sharpen=upscale_sharpen(m)", vs)
        self.assertIn('comfy_upscale_canvas(target, upscale_supersample("qn"))', vs)
        self.assertIn('init_denoise=upscale_init_denoise("moss")', vs)
        self.assertIn('init_denoise=upscale_init_denoise("qn")', vs)


if __name__ == "__main__":
    unittest.main()
