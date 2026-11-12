# -*- coding: utf-8 -*-
"""t402u / t403u: NotebookLM 内容主题传递、说明视频格式、固定 FYI、音频入库不被冲掉。不连 NotebookLM。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import config_prompt
from utility import notebooklm_cdp
from utility import program_media


FYI = config_prompt.NOTEBOOKLM_STUDIO_FYI


class TopicBoxTextTests(unittest.TestCase):
    def test_fyi_constant_is_the_agreed_chinese_text(self):
        self.assertEqual(
            FYI,
            "用第一人称、以自己的观点来讲，不要提到「文献」「资料」「这篇文章」「来源」「作者说」之类，"
            "直接说自己的事和想法。像聊天一样娓娓道来、一气呵成，不要分点罗列，"
            "不说「第一、第二」「我们分三点」「首先其次最后」，不要八股文式的清单。",
        )
        self.assertIn("文献", FYI)
        self.assertIn("娓娓道来", FYI)
        self.assertIn("八股文", FYI)

    def test_audio_video_slides_get_fyi_even_when_topic_is_empty(self):
        for kind in ("audio_overview", "video_overview", "slides"):
            text = config_prompt.notebooklm_topic_box_text(kind, "")
            self.assertTrue(text.startswith("FYI："), kind)
            self.assertIn(FYI, text)
            self.assertNotIn("内容主题：", text)
            self.assertEqual(text, "FYI：\n" + FYI)

    def test_topic_is_labeled_after_fyi(self):
        text = config_prompt.notebooklm_topic_box_text("video_overview", "边界与自我")
        self.assertTrue(text.startswith("FYI：\n" + FYI))
        self.assertIn("\n\n内容主题：\n边界与自我", text)
        # 主题在 FYI 后面
        self.assertLess(text.index("FYI："), text.index("内容主题："))
        self.assertLess(text.index(FYI), text.index("边界与自我"))

    def test_empty_topic_does_not_use_long_prompt_for_fyi_kinds(self):
        text = config_prompt.notebooklm_topic_box_text(
            "audio_overview", "", prompt="很长的规则提示词不应该出现在主题框里"
        )
        self.assertNotIn("很长的规则", text)
        self.assertEqual(text, "FYI：\n" + FYI)

    def test_infographic_has_no_fixed_fyi_and_falls_back_to_prompt(self):
        self.assertEqual(
            config_prompt.notebooklm_topic_box_text("infographic", "一张对照图"),
            "一张对照图",
        )
        self.assertEqual(
            config_prompt.notebooklm_topic_box_text("infographic", "", prompt="原来的提示词"),
            "原来的提示词",
        )
        self.assertNotIn("FYI：", config_prompt.notebooklm_topic_box_text("infographic", "x"))

    def test_long_topic_is_truncated_fyi_is_not(self):
        topic = "主题" * 2000
        text = config_prompt.notebooklm_topic_box_text(
            "slides", topic, max_chars=config_prompt.NOTEBOOKLM_TOPIC_MAX_CHARS
        )
        self.assertLessEqual(len(text), config_prompt.NOTEBOOKLM_TOPIC_MAX_CHARS)
        self.assertTrue(text.startswith("FYI：\n" + FYI))
        self.assertIn("内容主题：", text)
        self.assertTrue(text.endswith("…"))
        self.assertNotIn("…", FYI)

    def test_fyi_kinds_constant(self):
        self.assertEqual(
            config_prompt.NOTEBOOKLM_STUDIO_FYI_KINDS,
            frozenset({"slides", "audio_overview", "video_overview"}),
        )


class VideoFormatAndSelectorsTests(unittest.TestCase):
    def test_preferred_format_is_explainer_not_brief(self):
        self.assertEqual(notebooklm_cdp.VIDEO_FORMAT_PREFERRED, "explainer")
        self.assertTrue(notebooklm_cdp.VIDEO_FORMAT_LABELS["explainer"].search("说明视频"))
        self.assertTrue(notebooklm_cdp.VIDEO_FORMAT_LABELS["explainer"].search("Explainer"))
        self.assertTrue(notebooklm_cdp.VIDEO_FORMAT_LABELS["brief"].search("简洁版"))
        self.assertTrue(notebooklm_cdp.VIDEO_FORMAT_LABELS["brief"].search("Brief"))
        self.assertFalse(notebooklm_cdp.VIDEO_FORMAT_LABELS["explainer"].search("简洁版"))

    def test_pick_explainer_from_mixed_chinese_or_english_labels(self):
        self.assertEqual(
            notebooklm_cdp.pick_video_format_label(["简洁版", "说明视频", "立即生成"]),
            "说明视频",
        )
        self.assertEqual(
            notebooklm_cdp.pick_video_format_label(["Brief", "Explainer", "Generate now"]),
            "Explainer",
        )
        self.assertEqual(notebooklm_cdp.pick_video_format_label(["立即生成"]), "")

    def test_video_orientation_no_longer_maps_to_format_icons(self):
        self.assertFalse(hasattr(notebooklm_cdp, "VIDEO_FORMAT_ICON"))

    def test_topic_box_labels_cover_chinese_and_english(self):
        labels = notebooklm_cdp.TOPIC_BOX_LABELS
        self.assertIn("自定义主题", labels["video_overview"])
        self.assertEqual(labels["video_overview"][0], "描述您自己的主题")
        self.assertIn("描述您自己的主题", labels["video_overview"])
        self.assertIn("Describe your own topic", labels["video_overview"])
        self.assertEqual(
            labels["audio_overview"][0],
            "AI 主持人在本集节目中应着重于哪些方面？",
        )
        self.assertIn("视频/音频应侧重于哪些方面", labels["audio_overview"])
        self.assertIn("What should the AI hosts focus on", labels["audio_overview"])
        self.assertIn("描述你要创作的演示文稿", labels["slides"])
        self.assertTrue(any("presentation" in x.lower() or "slide" in x.lower() for x in labels["slides"]))
        self.assertIn("描述你要创建的信息图", labels["infographic"])
        self.assertIn("Describe the infographic", labels["infographic"])


class TopicPassingTests(unittest.TestCase):
    def test_dialog_passes_content_topic_kwarg(self):
        src = Path(__file__).resolve().parents[1].joinpath("gui", "slide_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn('_fyi_title = "内容主题" if title == "节目生成"', src)
        self.assertIn('title=_fyi_title', src)
        self.assertIn("content_topic = get_fyi_text()", src)
        self.assertIn('"content_topic": content_topic', src)
        self.assertIn('pack_fyi_note(', src)

    def test_program_dialog_only_renames_fyi_label(self):
        fyi = Path(__file__).resolve().parents[1].joinpath("gui", "prompt_fyi.py").read_text(encoding="utf-8")
        self.assertIn('title: str = "注意 / FYI"', fyi)
        pic = Path(__file__).resolve().parents[1].joinpath("gui", "picture_prompt_dialog.py").read_text(encoding="utf-8")
        vid = Path(__file__).resolve().parents[1].joinpath("gui", "video_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertNotIn('title="内容主题"', pic)
        self.assertNotIn('title="内容主题"', vid)

    def test_open_manual_puts_topic_in_extra(self):
        src = Path(__file__).resolve().parents[1].joinpath("gui", "dl", "scene_editor.py").read_text(encoding="utf-8")
        self.assertIn("content_topic: str = \"\"", src)
        self.assertIn('extra["content_topic"] = (content_topic or "").strip()', src)


class AudioAssociationTests(unittest.TestCase):
    def test_remove_leaves_empty_list_so_write_can_tell_delete_from_missing(self):
        item = {}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.m4a")
            Path(path).write_bytes(b"x")
            program_media.append_program_media(item, "audio_overview", path)
            self.assertTrue(item["audio_overview"])
            program_media.remove_program_media(item, "audio_overview", path)
            self.assertEqual(item["audio_overview"], [])
            self.assertIn("audio_overview", item)

    def test_missing_audio_overview_is_preserved_from_existing(self):
        existing = {"id": "s1", "audio_overview": [r"D:\AI_MEDIA\working\nblm_audio_overview.m4a"]}
        incoming = {"id": "s1", "title": "stale"}
        program_media.merge_missing_program_media(incoming, existing)
        self.assertEqual(incoming["audio_overview"], existing["audio_overview"])

    def test_explicit_empty_list_is_kept(self):
        existing = {"id": "s1", "audio_overview": [r"D:\a.m4a"], "video_overview": [r"D:\v.mp4"]}
        incoming = {"id": "s1", "audio_overview": []}
        program_media.merge_missing_program_media(incoming, existing)
        self.assertEqual(incoming["audio_overview"], [])
        self.assertEqual(incoming["video_overview"], [r"D:\v.mp4"])

    def test_list_write_preserves_audio_when_later_save_drops_the_key(self):
        old = [
            {
                "id": "s202611112047490b78",
                "title": "theology-paper-ai-and-wisdom",
                "audio_overview": [r"D:\AI_MEDIA\working\nblm_audio_overview_20261111_220320.m4a"],
                "video_overview": [r"D:\AI_MEDIA\working\nblm_video_overview.mp4"],
            }
        ]
        new = [
            {
                "id": "s202611112047490b78",
                "title": "theology-paper-ai-and-wisdom",
                "slide": [r"D:\AI_MEDIA\publish\gen_video\s.pdf"],
            }
        ]
        merged = program_media.merge_program_media_into_list(new, old)
        self.assertEqual(
            merged[0]["audio_overview"],
            [r"D:\AI_MEDIA\working\nblm_audio_overview_20261111_220320.m4a"],
        )
        self.assertEqual(
            merged[0]["video_overview"],
            [r"D:\AI_MEDIA\working\nblm_video_overview.mp4"],
        )
        self.assertEqual(merged[0]["slide"], [r"D:\AI_MEDIA\publish\gen_video\s.pdf"])

    def test_list_write_does_not_restore_after_explicit_delete(self):
        old = [{"id": "s1", "audio_overview": [r"D:\a.m4a"]}]
        new = [{"id": "s1", "audio_overview": []}]
        merged = program_media.merge_program_media_into_list(new, old)
        self.assertEqual(merged[0]["audio_overview"], [])


if __name__ == "__main__":
    unittest.main()
