"""t427u: 演示文稿（场景内容做来源）：正好 N 页、一场一页；画风 / 地域时代放在 NotebookLM 自定义框最前面。不连 NotebookLM。"""
import os
import sys
import types
import unittest
from unittest import mock

from tests.test_video_speaker_semantics import _install_stubs, _scene

_install_stubs()

import config_prompt as cp  # noqa: E402

STYLE = "三维卡通 (Pixar-Art-Cartoon)"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lock(n=21, **kw):
    return cp.notebooklm_deck_lock(n, STYLE, **kw)


class DeckLockTest(unittest.TestCase):
    def test_count_and_order_for_21(self):
        lock = _lock(21)
        self.assertTrue(lock.startswith(cp.NOTEBOOKLM_DECK_LOCK_TITLE))
        self.assertIn("正好 21 页", lock)
        self.assertIn("content.pdf 共 21 场", lock)
        self.assertIn("第 k 页 = 场景 k（k = 1–21）", lock)
        self.assertIn("exactly 21 slides", lock)
        self.assertIn("slide 21 is scene 21", lock)
        self.assertEqual(cp.notebooklm_deck_slide_count(lock), 21)

    def test_count_comes_before_style_and_place(self):
        lock = _lock(21, region="中东", era="古巴比伦")
        self.assertLess(lock.index("【页数】"), lock.index("【画风】"))
        self.assertLess(lock.index("【画风】"), lock.index("【地域 · 时代】"))

    def test_style_emphasis_positive(self):
        lock = _lock(21)
        self.assertIn("「三维卡通 (Pixar-Art-Cartoon)」", lock)
        self.assertIn("every picture on every slide is 3D animation (Pixar-style 3D animated cartoon, CGI)", lock)
        self.assertIn("like a still from a 3D animated movie", lock)
        for w in ("NOT ", "never", "not photo", "realistic"):
            self.assertNotIn(w, lock)
        real = cp.notebooklm_deck_lock(5, "写实 (Realistic)")
        self.assertIn("photorealistic", real)

    def test_place_only_when_given(self):
        self.assertNotIn("地域", _lock(21))
        lock = _lock(21, region="中东", era="古巴比伦")
        self.assertIn("中东 · 古巴比伦", lock)
        self.assertIn("the Middle East, ancient Babylon", lock)

    def test_with_and_strip(self):
        p = cp.with_notebooklm_deck_lock("FYI：x\n\n---\n\nArt_Style:\nabc", _lock(21))
        self.assertTrue(p.startswith(cp.NOTEBOOKLM_DECK_LOCK_HEAD + "\n"))
        self.assertEqual(cp.notebooklm_deck_lock_of(p), _lock(21))
        p2 = cp.with_notebooklm_deck_lock(p, _lock(9))  # 换掉，不叠两段
        self.assertEqual(p2.count(cp.NOTEBOOKLM_DECK_LOCK_HEAD), 1)
        self.assertEqual(cp.notebooklm_deck_slide_count(p2), 9)
        self.assertEqual(cp.strip_notebooklm_deck_lock(p), "FYI：x\n\n---\n\nArt_Style:\nabc")


class TopicBoxTest(unittest.TestCase):
    def test_slides_box_starts_with_lock(self):
        p = cp.with_notebooklm_deck_lock("long rules", _lock(21, region="中东", era="古巴比伦"))
        box = cp.notebooklm_topic_box_text("slides", "巴比伦", prompt=p)
        self.assertTrue(box.startswith(cp.NOTEBOOKLM_DECK_LOCK_TITLE))
        self.assertIn("exactly 21 slides", box)
        self.assertIn("FYI：\n" + cp.NOTEBOOKLM_STUDIO_FYI, box)
        self.assertTrue(box.rstrip().endswith("巴比伦"))
        self.assertNotIn("long rules", box)
        self.assertLessEqual(len(box), cp.NOTEBOOKLM_TOPIC_MAX_CHARS)

    def test_long_topic_truncated_lock_kept(self):
        p = cp.with_notebooklm_deck_lock("x", _lock(21, region="中东", era="古巴比伦"))
        box = cp.notebooklm_topic_box_text("slides", "主题" * 2000, prompt=p)
        self.assertLessEqual(len(box), cp.NOTEBOOKLM_TOPIC_MAX_CHARS)
        self.assertIn(_lock(21, region="中东", era="古巴比伦"), box)
        self.assertTrue(box.endswith("…"))

    def test_other_kinds_and_no_lock_unchanged(self):
        p = cp.with_notebooklm_deck_lock("x", _lock(21))
        for kind in ("audio_overview", "video_overview"):
            self.assertEqual(cp.notebooklm_topic_box_text(kind, "t", prompt=p),
                             cp.notebooklm_topic_box_text(kind, "t"))
        self.assertEqual(cp.notebooklm_topic_box_text("slides", "t", prompt="plain"),
                         cp.notebooklm_topic_box_text("slides", "t"))


class _Stop(Exception):
    pass


class ContentPdfTest(unittest.TestCase):
    def _html(self, **kw):
        seen = {}
        fake = types.ModuleType("fitz")
        fake.Archive = lambda *a, **k: types.SimpleNamespace(add=lambda *a2, **k2: None)

        def story(html="", **_k):
            seen["html"] = html
            raise _Stop()

        fake.Story = story
        from utility import content_pdf

        scenes = [_scene(f"<1> 第{i}句。") for i in range(1, 22)]
        with mock.patch.dict(sys.modules, {"fitz": fake}), mock.patch.object(content_pdf, "_font_file", lambda: ""):
            with self.assertRaises(_Stop):
                content_pdf.build_content_pdf(scenes, dest=os.path.join(_ROOT, "tests", "_t427u_unused.pdf"), **kw)
        return seen["html"]

    def test_slides_numbered(self):
        h = self._html(output="slides", style=STYLE, place="中东 · 古巴比伦")
        self.assertIn("共 21 场 = 演示文稿正好 21 页 / 21 scenes = exactly 21 slides", h)
        self.assertIn("场景 1 / Scene 1 · 第 1 页（共 21 页）/ Slide 1 of 21", h)
        self.assertIn("Slide 21 of 21", h)
        self.assertIn("End of scenes: 21 scenes = 21 slides", h)
        self.assertIn(STYLE, h)
        self.assertIn("中东 · 古巴比伦", h)
        self.assertLess(h.index("exactly 21 slides"), h.index("Slide 1 of 21"))

    def test_other_outputs_unchanged(self):
        h = self._html(output="infographic")
        self.assertIn("<h2>场景 1 / Scene 1</h2>", h)
        self.assertNotIn("Slide 1 of", h)
        self.assertNotIn("exactly", h)
        h = self._html()
        self.assertIn("<h2>场景 21 / Scene 21</h2>", h)


class WiringTest(unittest.TestCase):
    def _src(self, rel):
        with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_dialog_adds_lock_for_slides(self):
        s = self._src("gui/slide_prompt_dialog.py")
        self.assertIn("config_prompt.with_notebooklm_deck_lock(prompt, config_prompt.notebooklm_deck_lock(", s)
        self.assertIn("len(scenes), style, region=region if _bg_on else \"\"", s)
        self.assertIn('_deck = output_var.get() == "slides"', s)
        self.assertIn("output=output_var.get(),  # t427u", s)
        self.assertLess(s.index("with_notebooklm_deck_lock"), s.index("copy_text(prompt)\n        except (tk.TclError, OSError):\n            messagebox.showwarning(\"全集生成\""))

    def test_studio_picks_long_for_many_scenes(self):
        s = self._src("utility/notebooklm_cdp.py")
        self.assertIn("_select_slides_long(dlg)", s)
        self.assertIn("NOTEBOOKLM_DECK_LONG_FROM", s)
        self.assertLess(s.index("_select_slides_long(dlg)"), s.index('_step("填主题"'))
        from utility import notebooklm_cdp

        for t in ("长", "较长", "Long", " Long "):
            self.assertTrue(notebooklm_cdp.SLIDES_LENGTH_LONG_RE.match(t), t)
        for t in ("短", "默认", "Longer story"):
            self.assertFalse(notebooklm_cdp.SLIDES_LENGTH_LONG_RE.match(t), t)
        self.assertEqual(cp.NOTEBOOKLM_DECK_LONG_FROM, 11)


if __name__ == "__main__":
    unittest.main()
