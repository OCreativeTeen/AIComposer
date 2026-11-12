# -*- coding: utf-8 -*-
"""t404u: 节目生成「音频格式」选项，以及按真实 NotebookLM 标签点选。不连 NotebookLM。"""
from __future__ import annotations

import unittest
from pathlib import Path

from utility import notebooklm_cdp


AUDIO_LABELS = dict(notebooklm_cdp.AUDIO_FORMAT_CHOICES)
ROOT = Path(__file__).resolve().parents[1]


class AudioFormatNormalizeTests(unittest.TestCase):
    def test_default_is_deep_dive(self):
        self.assertEqual(notebooklm_cdp.AUDIO_FORMAT_DEFAULT, "deep_dive")
        self.assertEqual(AUDIO_LABELS["deep_dive"], "深入探究")
        self.assertEqual(notebooklm_cdp.normalize_audio_format(""), "deep_dive")
        self.assertEqual(notebooklm_cdp.normalize_audio_format(None), "deep_dive")
        self.assertEqual(notebooklm_cdp.normalize_audio_format("nope"), "deep_dive")

    def test_accepts_keys_and_chinese_and_english(self):
        cases = {
            "deep_dive": "deep_dive",
            "深入探究": "deep_dive",
            "Deep Dive": "deep_dive",
            "brief": "brief",
            "摘要": "brief",
            "Brief": "brief",
            "critique": "critique",
            "评论": "critique",
            "Critique": "critique",
            "debate": "debate",
            "辩论": "debate",
            "Debate": "debate",
            "talk_show": "talk_show",
            "谈话节目": "talk_show",
            "Talk Show": "talk_show",
        }
        for raw, expect in cases.items():
            self.assertEqual(notebooklm_cdp.normalize_audio_format(raw), expect, raw)

    def test_choices_order_matches_the_dialog(self):
        self.assertEqual(
            [zh for _k, zh in notebooklm_cdp.AUDIO_FORMAT_CHOICES],
            ["深入探究", "摘要", "评论", "辩论", "谈话节目"],
        )

    def test_pick_label_from_visible_texts(self):
        texts = ["深入探究", "摘要", "评论", "辩论", "谈话节目", "立即生成"]
        self.assertEqual(notebooklm_cdp.pick_audio_format_label(texts, "deep_dive"), "深入探究")
        self.assertEqual(notebooklm_cdp.pick_audio_format_label(texts, "辩论"), "辩论")
        self.assertEqual(
            notebooklm_cdp.pick_audio_format_label(
                ["Deep Dive", "Brief", "Critique", "Debate", "Talk Show"], "critique"
            ),
            "Critique",
        )
        self.assertEqual(notebooklm_cdp.pick_audio_format_label(["立即生成"], "deep_dive"), "")


class RealUiSelectorTests(unittest.TestCase):
    def test_audio_focus_label_matches_screenshot(self):
        labels = notebooklm_cdp.TOPIC_BOX_LABELS["audio_overview"]
        self.assertEqual(labels[0], "AI 主持人在本集节目中应着重于哪些方面？")
        self.assertIn("What should the AI hosts focus on", labels)

    def test_video_still_targets_custom_topic_not_the_chip_field(self):
        labels = notebooklm_cdp.TOPIC_BOX_LABELS["video_overview"]
        self.assertEqual(labels[0], "自定义主题")
        self.assertIn("描述您自己的主题", labels)
        self.assertIn("Describe your own topic", labels)
        self.assertFalse(any("侧重于哪些方面" in x for x in labels))

    def test_video_format_still_prefers_explainer(self):
        self.assertEqual(notebooklm_cdp.VIDEO_FORMAT_PREFERRED, "explainer")
        self.assertTrue(notebooklm_cdp.VIDEO_FORMAT_LABELS["explainer"].search("说明视频"))
        self.assertTrue(notebooklm_cdp.VIDEO_FORMAT_LABELS["brief"].search("简洁版"))
        self.assertTrue(notebooklm_cdp.VIDEO_FORMAT_LABELS["brief"].search("简洁版 新功能!"))
        self.assertEqual(
            notebooklm_cdp.pick_video_format_label(["简洁版", "说明视频", "新功能!"]),
            "说明视频",
        )


class ProgramDialogAudioFormatTests(unittest.TestCase):
    def test_program_dialog_has_audio_format_radios_only_for_audio_overview(self):
        src = (ROOT / "gui" / "slide_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn('text="音频格式："', src)
        self.assertIn("AUDIO_FORMAT_CHOICES", src)
        self.assertIn('title == "节目生成" and output_var.get() == "audio_overview"', src)
        self.assertIn("audio_fmt_row.pack_forget()", src)
        self.assertIn('"audio_format": audio_format_var.get()', src)
        self.assertIn('"audio_format": "deep_dive"', src)
        self.assertIn("normalize_audio_format", src)

    def test_open_manual_forwards_audio_format(self):
        scene = (ROOT / "gui" / "dl" / "scene_editor.py").read_text(encoding="utf-8")
        self.assertIn('audio_format: str = ""', scene)
        self.assertIn('extra["audio_format"] = (audio_format or "").strip()', scene)
        wf = (ROOT / "gui" / "workflow" / "wf_prompt_flows.py").read_text(encoding="utf-8")
        self.assertIn('audio_format: str = ""', wf)
        self.assertIn('extra["audio_format"] = (audio_format or "").strip()', wf)

    def test_make_studio_selects_audio_format_before_fill(self):
        src = (ROOT / "utility" / "notebooklm_cdp.py").read_text(encoding="utf-8")
        audio_at = src.index('if kind == "audio_overview":')
        fill_at = src.index('_step("填主题"')
        self.assertLess(audio_at, fill_at)
        self.assertIn("_select_audio_format", src)
        self.assertNotIn("选择语言", src[audio_at:fill_at])
        self.assertNotIn("时长", src[audio_at:fill_at])


if __name__ == "__main__":
    unittest.main()
