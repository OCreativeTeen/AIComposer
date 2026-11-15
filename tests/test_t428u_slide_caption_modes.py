"""t428u: 节目生成 · 说明文字：去掉「去掉文字」；关键字作背景 = 信息图的关键词做法（每页一套）；保留 = 每页有说明文字区；
用画面讲 = 整页只有画面。三种都写进硬性要求（紧跟画风，在 NotebookLM 自定义框最前面，不截）。"""
import ast
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


def _scenes(n=3):
    return [_scene(f"<1> 第{i}场的讲述，很长很长的一段话。", extra={"caption": f"怕改变的第{i}个人"}) for i in range(1, n + 1)]


def _slides(text, output="slides", narrative="narration", n=3):
    return cp.build_slide_flow_prompt(target="slideshow", text=text, visual_style=STYLE, scene_content=_scenes(n),
                                      narrative=narrative, output=output, content_source="content.pdf")


def _dialog_ns():
    """只取 slide_prompt_dialog 的 _DEFAULT_CHOICE / _clean_choice（不导入 tkinter）。"""
    path = os.path.join(_ROOT, "gui", "slide_prompt_dialog.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    keep = [n for n in tree.body if (isinstance(n, ast.Assign) and any(
        getattr(t, "id", "") in ("_DEFAULT_CHOICE", "OUTPUT_CHOICES", "RANGE_CHOICES") for t in n.targets))
        or (isinstance(n, ast.FunctionDef) and n.name == "_clean_choice")]
    mod = ast.Module(body=keep, type_ignores=[])
    fake_cdp = types.SimpleNamespace(normalize_audio_format=lambda v: v or "deep_dive")
    ns = {"config_prompt": cp}
    with mock.patch.dict(sys.modules, {"utility.notebooklm_cdp": fake_cdp}):
        import utility

        with mock.patch.object(utility, "notebooklm_cdp", fake_cdp, create=True):
            exec(compile(mod, path, "exec"), ns)
            ns["_clean"] = lambda saved: ns["_clean_choice"](saved)
            ns["_cleaned"] = {k: ns["_clean_choice"]({"text": k}) for k in ("erase", "none", "keep", "keywords",
                                                                             "express", "bogus")}
    return ns


class ChoicesTest(unittest.TestCase):
    def test_no_erase_in_slide_dialog(self):
        self.assertEqual([k for k, _ in cp.SLIDE_FLOW_TEXT_CHOICES], ["keep", "keywords", "express"])
        self.assertNotIn("去掉文字", dict(cp.SLIDE_FLOW_TEXT_CHOICES).values())
        # 图片 / 视频共用的四种不变
        self.assertIn(("erase", "去掉文字"), cp.FLOW_CAPTION_CHOICES)

    def test_saved_erase_migrates_to_express(self):
        ns = _dialog_ns()
        self.assertEqual(ns["_DEFAULT_CHOICE"]["text"], "express")
        got = ns["_cleaned"]
        self.assertEqual(got["erase"]["text"], "express")
        self.assertEqual(got["none"]["text"], "express")
        self.assertEqual(got["bogus"]["text"], "express")
        for k in ("keep", "keywords", "express"):
            self.assertEqual(got[k]["text"], k)
        self.assertEqual(cp.slide_text_choice("erase"), "express")
        self.assertEqual(cp.slide_text_choice("keywords"), "keywords")


class LockTest(unittest.TestCase):
    def test_mode_line_after_style_before_place(self):
        for text, mark in (("keywords", "【说明文字 · 关键字作背景】"), ("keep", "【说明文字 · 保留】"),
                           ("express", "【说明文字 · 用画面讲】"), ("erase", "【说明文字 · 用画面讲】")):
            with self.subTest(text=text):
                lock = cp.notebooklm_deck_lock(21, STYLE, region="中东", era="古巴比伦", text=text)
                self.assertEqual(lock.count("【说明文字"), 1)
                self.assertLess(lock.index("【画风】"), lock.index(mark))
                self.assertLess(lock.index(mark), lock.index("【地域 · 时代】"))
                self.assertLess(lock.index("【页数】"), lock.index("【画风】"))

    def test_mode_texts_positive(self):
        kw = "\n".join(cp.NOTEBOOKLM_DECK_TEXT_LINES["keywords"])
        self.assertIn("1 到 2 个关键词", kw)
        self.assertIn("融进背景", kw)
        self.assertIn("woven into the background", kw)
        keep = "\n".join(cp.NOTEBOOKLM_DECK_TEXT_LINES["keep"])
        self.assertIn("说明文字区", keep)
        self.assertIn("caption area", keep)
        exp = "\n".join(cp.NOTEBOOKLM_DECK_TEXT_LINES["express"])
        self.assertIn("整页只有画面", exp)
        self.assertIn("picture only", exp)
        for v in cp.NOTEBOOKLM_DECK_TEXT_LINES.values():
            for line in v:
                for w in ("NOT ", "never", "Never", "不要", "绝不"):
                    self.assertNotIn(w, line)

    def test_box_keeps_lock_whole_and_first(self):
        for text in ("keywords", "keep", "express"):
            with self.subTest(text=text):
                lock = cp.notebooklm_deck_lock(21, STYLE, region="中东", era="古巴比伦", text=text)
                box = cp.notebooklm_topic_box_text("slides", "主题" * 500, prompt=cp.with_notebooklm_deck_lock("x", lock))
                self.assertTrue(box.startswith(lock))
                self.assertLessEqual(len(box), cp.NOTEBOOKLM_TOPIC_MAX_CHARS)
                self.assertIn("FYI：", box)

    def test_no_count_lock_for_analysis(self):
        lock = cp.notebooklm_deck_lock(0, STYLE, text="keywords")
        self.assertNotIn("【页数】", lock)
        self.assertIn("【说明文字 · 关键字作背景】", lock)
        self.assertEqual(cp.notebooklm_deck_slide_count(lock), 0)


class SlidePromptTest(unittest.TestCase):
    def test_keywords_uses_infographic_approach(self):
        p = _slides("keywords")
        self.assertIn("幻灯片关键词（必须遵守，和信息图的关键词同一种做法）", p)
        self.assertIn(cp.KEYWORD_PLACE_ZH, p)
        self.assertIn(cp.KEYWORD_PLACE_EN, p)
        self.assertIn("没有标题、正文、小结或要点列表", p)
        self.assertIn("follow the slide key phrase rule in Output_rules", p)
        self.assertNotIn("Slide caption", p)

    def test_keep_has_caption_area(self):
        p = _slides("keep")
        self.assertIn("说明文字（保留）", p)
        self.assertIn(cp.SLIDE_KEEP_CAPTION_RULE, p)
        self.assertIn(cp.SLIDE_CAPTION_INPUT_NOTE, p)
        self.assertNotIn("Do not add a new caption", p)

    def test_express_picture_only(self):
        p = _slides("express")
        self.assertIn("全部用画面来讲", p)
        self.assertIn("No letters anywhere", p)

    def test_other_outputs_unchanged_by_mode_changes(self):
        for out in ("infographic", "video_overview", "audio_overview"):
            for text in ("keep", "keywords", "express", "erase"):
                with self.subTest(out=out, text=text):
                    p = _slides(text, output=out)
                    self.assertNotIn("Slide caption", p)
                    self.assertNotIn("幻灯片关键词", p)
        self.assertIn("信息图关键词（必须遵守）", _slides("keywords", output="infographic"))
        # 去掉文字在信息图里照旧（= 用画面讲）
        self.assertEqual(cp._notebooklm_text_rule("erase", "infographic", False),
                         cp._notebooklm_text_rule("express", "infographic", False))

    def test_payload_caption_only_in_keep(self):
        sc = _scenes(1)
        keep = cp.slide_flow_scene_payload(sc, use_visual=True, use_speaking=True, use_actor=False, keywords=False,
                                           caption_text=True)
        self.assertIn("Slide caption: 怕改变的第1个人", keep[0]["show_this_content"])
        kw = cp.slide_flow_scene_payload(sc, use_visual=True, use_speaking=True, use_actor=False, keywords=True)
        self.assertIn("Keyword hint: 怕改变的", kw[0]["show_this_content"])
        self.assertNotIn("Slide caption", kw[0]["show_this_content"])


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

        with mock.patch.dict(sys.modules, {"fitz": fake}), mock.patch.object(content_pdf, "_font_file", lambda: ""):
            with self.assertRaises(_Stop):
                content_pdf.build_content_pdf(_scenes(3), narrative="narration",
                                              dest=os.path.join(_ROOT, "tests", "_t428u_unused.pdf"), **kw)
        return seen["html"]

    def test_keywords_note_per_scene(self):
        h = self._html(output="slides", text="keywords", keywords=True)
        self.assertEqual(h.count("这一页的文字 / On-slide text"), 3)
        self.assertIn("只有 1 到 2 个关键词，融进背景画面", h)
        self.assertIn("关键词 / Keyword hint", h)
        self.assertNotIn("Slide caption", h)

    def test_keep_caption_field(self):
        h = self._html(output="slides", text="keep")
        self.assertIn("说明文字（写在这一页上）/ Slide caption", h)
        self.assertIn("怕改变的第2个人", h)

    def test_express_and_other_outputs(self):
        h = self._html(output="slides", text="express")
        self.assertIn("没有文字，全部用画面讲", h)
        h = self._html(output="infographic", text="keep")
        self.assertNotIn("On-slide text", h)
        self.assertNotIn("Slide caption", h)


class WiringTest(unittest.TestCase):
    def test_dialog(self):
        with open(os.path.join(_ROOT, "gui", "slide_prompt_dialog.py"), encoding="utf-8") as f:
            s = f.read()
        self.assertIn("content_source=CONTENT_PDF_NAME, text=text_var.get()))", s)
        self.assertIn('text=text_var.get() if _deck else "",', s)
        self.assertEqual(s.count("prompt = _with_text_lock(prompt, output_var.get(), style, text_var.get()"), 2)
        self.assertIn("def _with_text_lock(", s)

    def test_fill_reports_truncation(self):
        with open(os.path.join(_ROOT, "utility", "notebooklm_cdp.py"), encoding="utf-8") as f:
            s = f.read()
        self.assertIn('get_attribute("maxlength")', s)


if __name__ == "__main__":
    unittest.main()
