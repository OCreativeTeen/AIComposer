"""t376u: 生场视频 · 分节「尾帧增强」选项（不增强 / MOSS / Qwen / Grok Image）+ 背景块窄版，离线测试。"""
from __future__ import annotations

import contextlib
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

STYLE = "三维卡通 (Pixar-Art-Cartoon)"


def _src(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class EnhanceOptionTest(unittest.TestCase):
    def test_options_and_default(self):
        from utility import video_segments as vs

        self.assertEqual([k for k, _ in vs.LAST_FRAME_ENHANCE_OPTIONS], ["none", "moss", "qn", "grok"])
        self.assertEqual([l for _, l in vs.LAST_FRAME_ENHANCE_OPTIONS], ["不增强", "MOSS", "Qwen", "Grok Image"])
        self.assertEqual(vs.LAST_FRAME_ENHANCE_DEFAULT, "qn")  # t395u
        for raw, want in ((None, "qn"), ("", "qn"), ("bogus", "qn"), ("MOSS", "moss"), ("none", "none"),
                          ("qwen", "qn"), ("QN", "qn"), ("Grok Image", "grok"), ("grok", "grok")):
            self.assertEqual(vs.normalize_last_frame_enhance(raw), want, raw)
        self.assertEqual(vs.last_frame_enhance_label("qn"), "Qwen")
        self.assertIsNone(vs.last_frame_upscaler("none"))


class EnhanceRoutingTest(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        self.tmp = tempfile.mkdtemp()
        self.frame = os.path.join(self.tmp, "last.png")
        Image.new("RGB", (1312, 736), (10, 20, 30)).save(self.frame)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_sd(self, calls):
        from PIL import Image

        def make(name):
            def gen(prompt, images, **kw):
                calls.append((name, prompt, list(images), kw))
                return Image.new("RGB", (kw["width"], kw["height"]), (1, 2, 3))
            return gen

        fake = types.ModuleType("utility.sd_image_processor")
        fake.generate_image_moss_edit = make("moss")
        fake.generate_image_qwen_edit = make("qn")
        return fake

    def _fake_grok(self, calls, fail=False):
        from PIL import Image

        grok = types.ModuleType("utility.grok_cdp")

        def make_image(prompt, image_path, status=None):
            calls.append(("grok", prompt, list(image_path), {}))
            if fail:
                raise RuntimeError("Grok tab not ready")
            return Image.new("RGB", (1920, 1080), (4, 5, 6))

        grok.make_image = make_image
        acct = types.ModuleType("utility.chrome_account")
        used = []

        @contextlib.contextmanager
        def use(name):
            used.append(name)
            yield

        acct.use = use
        return grok, acct, used

    def _patched(self, sd=None, grok=None, acct=None):
        import utility

        stack = contextlib.ExitStack()
        mods = {}
        if sd is not None:
            mods["utility.sd_image_processor"] = sd
            stack.enter_context(mock.patch.object(utility, "sd_image_processor", sd, create=True))
        if grok is not None:
            mods["utility.grok_cdp"] = grok
            mods["utility.chrome_account"] = acct
            stack.enter_context(mock.patch.object(utility, "grok_cdp", grok, create=True))
            stack.enter_context(mock.patch.object(utility, "chrome_account", acct, create=True))
        stack.enter_context(mock.patch.dict(sys.modules, mods))
        return stack

    def _check_out(self, out):
        from PIL import Image

        with Image.open(out) as im:
            self.assertEqual(im.size, (1920, 1080))
        os.remove(out)

    def test_none_returns_raw_frame_and_calls_nothing(self):
        from utility import video_segments as vs

        calls = []
        with self._patched(sd=self._fake_sd(calls)):
            out, ok, note = vs.enhance_segment_last_frame(self.frame, mode="none", style=STYLE)
        self.assertEqual((out, ok), (self.frame, False))
        self.assertIn("不增强", note)
        self.assertEqual(calls, [])

    def test_moss_route(self):
        from utility import video_segments as vs

        calls = []
        with self._patched(sd=self._fake_sd(calls)):
            out, ok, _n = vs.enhance_segment_last_frame(self.frame, mode="moss", style=STYLE)
        self.assertTrue(ok)
        self.assertEqual([c[0] for c in calls], ["moss"])
        name, prompt, images, kw = calls[0]
        self.assertEqual(images, [self.frame])
        self.assertFalse(kw["adapt"])
        self.assertEqual((kw["width"], kw["height"]), (1920, 1088))
        self.assertTrue(prompt.startswith("FAITHFUL RESTORE"))  # t377u
        self.assertIn("image 1", prompt)
        self.assertIn("more cartoonish", kw["negative"])
        self.assertIn("color shift", kw["negative"])
        self.assertEqual(kw["init_denoise"], 0.35)  # t377u: start from the frame, low denoise
        self._check_out(out)

    def test_qn_route_uses_qwen_edit_with_picture_wording(self):
        from utility import video_segments as vs

        calls = []
        with self._patched(sd=self._fake_sd(calls)):
            out, ok, _n = vs.enhance_segment_last_frame(self.frame, mode="qn", style=STYLE)
        self.assertTrue(ok)
        self.assertEqual([c[0] for c in calls], ["qn"])
        _name, prompt, images, kw = calls[0]
        self.assertEqual(images, [self.frame])
        self.assertTrue(prompt.startswith("FAITHFUL RESTORE"))  # t377u
        self.assertIn("Picture 1", prompt)
        self.assertEqual(kw["init_denoise"], 0.55)  # t397u: 0.4 -> 0.55
        self.assertIn("1920x1080", prompt)
        self.assertEqual((kw["width"], kw["height"]), (2880, 1616))  # t397u: 1.5x supersample canvas
        self.assertFalse(kw["adapt"])
        self._check_out(out)

    def test_grok_route_uses_upscale_prompt_and_account(self):
        from utility import video_segments as vs

        calls = []
        grok, acct, used = self._fake_grok(calls)
        with self._patched(grok=grok, acct=acct):
            out, ok, _n = vs.enhance_segment_last_frame(self.frame, mode="grok", style=STYLE, account="tom2")
        self.assertTrue(ok)
        self.assertEqual(used, ["tom2"])
        _name, prompt, images, _kw = calls[0]
        self.assertEqual(images, [self.frame])
        self.assertTrue(prompt.startswith("FAITHFUL RESTORE"))  # t377u
        self.assertIn("TASK: FAITHFUL UPSCALE / RESTORE ONLY", prompt)
        self.assertIn("1920x1080", prompt)
        self._check_out(out)

    def test_failures_fall_back_to_raw_frame(self):
        from utility import video_segments as vs

        calls = []
        grok, acct, _used = self._fake_grok(calls, fail=True)
        with self._patched(grok=grok, acct=acct):
            out, ok, note = vs.enhance_segment_last_frame(self.frame, mode="grok", style=STYLE)
        self.assertEqual((out, ok), (self.frame, False))
        self.assertIn("Grok tab not ready", note)

        bad = types.ModuleType("utility.sd_image_processor")

        def down(*_a, **_k):
            raise ConnectionError("ComfyUI 192.168.1.227:8188 refused")

        bad.generate_image_moss_edit = bad.generate_image_qwen_edit = down
        for mode in ("moss", "qn"):
            with self._patched(sd=bad):
                out, ok, note = vs.enhance_segment_last_frame(self.frame, mode=mode, style=STYLE)
            self.assertEqual((out, ok), (self.frame, False), mode)
            self.assertIn("refused", note)


class DialogWiringTest(unittest.TestCase):
    def test_dialog_group_persist_and_chain_kwargs(self):
        dlg = _src("gui/video_prompt_dialog.py")
        self.assertIn('text="尾帧增强"', dlg)
        self.assertIn('"last_frame_enhance": enhance_var.get()', dlg)  # 记在项目 video_prompt
        self.assertIn('normalize_last_frame_enhance(_sv.get("last_frame_enhance"))', dlg)
        self.assertIn("enhance=_enh, account=_enh_account", dlg)
        # 放在 MiniMax 工作流后面、场景音频前面
        i_h3 = dlg.index('text="MiniMax 工作流"')
        i_enh = dlg.index('text="尾帧增强"')
        i_audio = dlg.index('text="场景音频"')
        self.assertLess(i_h3, i_enh)
        self.assertLess(i_enh, i_audio)
        self.assertNotIn("末帧用 MOSS 提高分辨率", dlg)
        self.assertIn("compact=True", dlg)

    def test_flow_chain_takes_enhance(self):
        flows = _src("gui/workflow/wf_prompt_flows.py")
        self.assertIn('def _chain_video_segment(self, token, style, status, done, enhance="qn", account="")', flows)
        self.assertIn("vs.enhance_segment_last_frame(", flows)
        self.assertIn("mode=enhance", flows)

    def test_background_block_compact_lines(self):
        fyi = _src("gui/prompt_fyi.py")
        self.assertIn("compact: bool = False", fyi)
        self.assertIn('"\\n　（仅当人物中有讲员出镜时写入）"', fyi)
        self.assertIn('"始终写入：\\n　画面风格 "', fyi)
        self.assertIn('"\\n　场景风格 "', fyi)


if __name__ == "__main__":
    unittest.main()
