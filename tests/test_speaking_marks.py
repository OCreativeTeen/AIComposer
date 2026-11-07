"""Offline tests for <N>/<Ns> parsing and new-project monologue splits."""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class SpeakingMarksTest(unittest.TestCase):
    def test_normal_dialogue_unaffected(self):
        from utility.speaking_marks import (
            format_speaking_turns,
            parse_speaking_turns,
            speaker_ids_in_text,
            speaking_has_monologue,
            split_speaking_pair,
            strip_speaker_marks,
        )

        text = "<1> 你好。<2> 今天怎么样？<1> 还行。"
        turns = parse_speaking_turns(text)
        self.assertEqual([(t.speaker, t.text, t.monologue) for t in turns], [
            (1, "你好。", False),
            (2, "今天怎么样？", False),
            (1, "还行。", False),
        ])
        self.assertFalse(speaking_has_monologue(text))
        self.assertIsNone(split_speaking_pair(text))
        self.assertEqual(speaker_ids_in_text(text), [1, 2])
        self.assertEqual(strip_speaker_marks(text), "你好。 今天怎么样？ 还行。")
        self.assertEqual(strip_speaker_marks("温度不到 <0.5> 度"), "温度不到 度")
        self.assertEqual(speaker_ids_in_text("score 1s and < 3"), [])
        plain = "没有尖括号的对白"
        self.assertEqual([(t.speaker, t.text, t.monologue) for t in parse_speaking_turns(plain)], [
            (1, plain, False),
        ])

    def test_ns_and_legacy_both_scripts_and_multidigit(self):
        from utility.speaking_marks import parse_speaking_turns, speaker_ids_in_text, speaking_has_monologue, strip_speaker_marks

        modern = "<12s> 我想了很久。<3> 你说呢？"
        turns = parse_speaking_turns(modern)
        self.assertEqual(turns[0].speaker, 12)
        self.assertTrue(turns[0].monologue)
        self.assertEqual(turns[1].speaker, 3)
        self.assertFalse(turns[1].monologue)
        self.assertEqual(speaker_ids_in_text(modern), [12, 3])
        self.assertTrue(speaking_has_monologue(modern))
        self.assertEqual(strip_speaker_marks(modern), "我想了很久。 你说呢？")
        self.assertNotIn("s", strip_speaker_marks("<1s> 你好"))

        simp = "<1>（自言自语）跟朋友吃了顿饭。<2> 你今天怎么这么累？"
        trad = "<1>（自言自語）原来我不是坏掉了。"
        self.assertTrue(parse_speaking_turns(simp)[0].monologue)
        self.assertEqual(parse_speaking_turns(simp)[0].speaker, 1)
        self.assertFalse(parse_speaking_turns(simp)[1].monologue)
        self.assertTrue(parse_speaking_turns(trad)[0].monologue)
        self.assertTrue(speaking_has_monologue(simp))
        self.assertTrue(speaking_has_monologue(trad))
        self.assertEqual(strip_speaker_marks(simp), "跟朋友吃了顿饭。 你今天怎么这么累？")

    def test_leading_split_order_and_authored_copies(self):
        from utility.speaking_marks import expand_scenes_for_new_project

        extra = {"note": ["keep"], "n": 1}
        src = [{
            "caption": "四小时换一小时",
            "visual": "深夜书房",
            "actor": "人物1:man/mature/chinese/阿哲 | 人物2:woman/mature/chinese/小雨",
            "speaking": "<1s> 跟朋友吃了顿饭。<2> 你今天怎么这么累？<1> 我也不知道。",
            "extra": extra,
            "id": 99,
        }]
        frozen = copy.deepcopy(src)
        out = expand_scenes_for_new_project(src)
        self.assertEqual(src, frozen)  # source list untouched
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0]["speaking"].startswith("<1s>"))
        self.assertIn("<2>", out[1]["speaking"])
        self.assertNotIn("s>", out[1]["speaking"].replace("<1s>", ""))
        self.assertFalse(out[1]["speaking"].startswith("<1s>"))
        for key in ("caption", "visual", "actor"):
            self.assertEqual(out[0][key], src[0][key])
            self.assertEqual(out[1][key], src[0][key])
        self.assertEqual(out[0]["extra"], extra)
        self.assertEqual(out[1]["extra"], extra)
        self.assertIsNot(out[0]["extra"], extra)
        self.assertIsNot(out[0]["extra"], out[1]["extra"])
        self.assertNotIn("id", out[0])
        self.assertNotIn("id", out[1])

    def test_trailing_split_and_merged_block(self):
        from utility.speaking_marks import expand_scenes_for_new_project, parse_speaking_turns

        src = [{
            "caption": "C",
            "visual": "V",
            "actor": "A",
            "speaking": "<1> 每天都有截止日期。<2> 就像每天拆一面墙。<1s> 原来我不是坏掉了。<2s> 我只是燃尽了。",
        }]
        out = expand_scenes_for_new_project(src)
        self.assertEqual(len(out), 2)
        self.assertIn("截止日期", out[0]["speaking"])
        self.assertNotIn("<1s>", out[0]["speaking"])
        self.assertNotIn("<2s>", out[0]["speaking"])
        mono = parse_speaking_turns(out[1]["speaking"])
        self.assertTrue(all(t.monologue for t in mono))
        self.assertEqual([t.speaker for t in mono], [1, 2])
        self.assertIn("原来我不是坏掉了", out[1]["speaking"])
        self.assertIn("我只是燃尽了", out[1]["speaking"])

    def test_pure_monologue_and_no_blank(self):
        from utility.speaking_marks import expand_scenes_for_new_project, split_speaking_pair

        src = [{"caption": "C", "speaking": "<1s> 我一个人想了很久。<1s> 还是老样子。"}]
        out = expand_scenes_for_new_project(src)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["speaking"], src[0]["speaking"])
        self.assertIsNone(split_speaking_pair("<1s>   "))
        self.assertEqual(expand_scenes_for_new_project([]), [])

    def test_invalid_interior_and_both_ends_kept_unchanged(self):
        from utility.speaking_marks import expand_scenes_for_new_project, split_speaking_pair

        interior_speaking = "<1> 你好。<2s> 夹在中间。<1> 还在。"
        both_speaking = "<1s> 开头。<2> 中间。<1s> 结尾。"
        interior = [{"caption": "ok", "speaking": interior_speaking, "visual": "V1", "actor": "A1"}]
        both = [{"caption": "also", "speaking": both_speaking, "visual": "V2", "actor": "A2"}]
        frozen_i = copy.deepcopy(interior)
        frozen_b = copy.deepcopy(both)
        out_i = expand_scenes_for_new_project(interior)
        out_b = expand_scenes_for_new_project(both)
        self.assertEqual(interior, frozen_i)
        self.assertEqual(both, frozen_b)
        self.assertEqual(len(out_i), 1)
        self.assertEqual(len(out_b), 1)
        self.assertEqual(out_i[0]["speaking"], interior_speaking)
        self.assertEqual(out_b[0]["speaking"], both_speaking)
        self.assertEqual(out_i[0]["caption"], "ok")
        self.assertEqual(out_b[0]["visual"], "V2")
        self.assertIsNone(split_speaking_pair(interior_speaking))
        self.assertIsNone(split_speaking_pair(both_speaking))
        self.assertIsNone(split_speaking_pair("<1>（自言自语）头。<2> 中。<1s> 尾。"))

    def test_mixed_list_valid_split_and_invalid_unchanged(self):
        from utility.speaking_marks import expand_scenes_for_new_project

        leading = "<1s> 先想一下。<2> 你在吗？"
        interior = "<1> 你好。<2s> 夹在中间。<1> 还在。"
        trailing = "<2> 先坐下。<1s> 原来如此。"
        both = "<1s> 头。<2> 中。<1s> 尾。"
        src = [
            {"caption": "L", "visual": "VL", "actor": "AL", "speaking": leading},
            {"caption": "I", "visual": "VI", "actor": "AI", "speaking": interior},
            {"caption": "T", "visual": "VT", "actor": "AT", "speaking": trailing},
            {"caption": "B", "visual": "VB", "actor": "AB", "speaking": both},
        ]
        frozen = copy.deepcopy(src)
        out = expand_scenes_for_new_project(src)
        self.assertEqual(src, frozen)
        self.assertEqual(len(out), 6)
        self.assertTrue(out[0]["speaking"].startswith("<1s>"))
        self.assertIn("<2>", out[1]["speaking"])
        self.assertEqual(out[0]["caption"], "L")
        self.assertEqual(out[1]["caption"], "L")
        self.assertEqual(out[2]["speaking"], interior)
        self.assertEqual(out[2]["caption"], "I")
        self.assertIn("先坐下", out[3]["speaking"])
        self.assertTrue(out[4]["speaking"].startswith("<1s>"))
        self.assertEqual(out[3]["caption"], "T")
        self.assertEqual(out[4]["caption"], "T")
        self.assertEqual(out[5]["speaking"], both)
        self.assertEqual(out[5]["caption"], "B")

    def test_tts_and_speaker_helpers_recognize_tags(self):
        from utility.speaking_marks import split_speaking_turns, strip_speaker_marks, speaker_ids_in_text

        turns = split_speaking_turns("<1s> 心里话 <2> 对你说 <0.5> 再等一下")
        self.assertEqual(turns[0], (1, "心里话"))
        self.assertEqual(turns[1][0], 2)
        self.assertIn("<0.5>", turns[1][1])
        spoken = " ".join(t[1] for t in turns)
        self.assertNotIn("自言自语", spoken)
        self.assertFalse(spoken.strip().startswith("s"))
        self.assertEqual(strip_speaker_marks("<1s>（自言自语）心里话"), "心里话")
        self.assertEqual(speaker_ids_in_text("<1s> a <2> b"), [1, 2])

    def test_new_project_hook_only(self):
        pm = Path(ROOT, "project_manager.py").read_text(encoding="utf-8")
        wf = Path(ROOT, "magic_workflow.py").read_text(encoding="utf-8")
        self.assertIn("expand_scenes_for_new_project", pm)
        self.assertIn("def create_new_project", pm)
        create = pm.split("def create_new_project", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("expand_scenes_for_new_project", create)
        self.assertNotIn("MonologueSplitError", create)
        self.assertNotIn("expand_scenes_for_new_project", wf)


if __name__ == "__main__":
    unittest.main()
