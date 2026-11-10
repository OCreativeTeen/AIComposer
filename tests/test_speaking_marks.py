"""Offline tests for <N>/<Ns> parsing, cover steps and the Ctrl+S <s> segment mark (t373u)."""
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
        self.assertFalse(parse_speaking_turns(simp)[0].monologue)
        self.assertEqual(parse_speaking_turns(simp)[0].speaker, 1)
        self.assertEqual(parse_speaking_turns(simp)[0].text, "（自言自语）跟朋友吃了顿饭。")
        self.assertFalse(parse_speaking_turns(simp)[1].monologue)
        self.assertFalse(parse_speaking_turns(trad)[0].monologue)
        self.assertEqual(parse_speaking_turns(trad)[0].text, "（自言自語）原来我不是坏掉了。")
        self.assertFalse(speaking_has_monologue(simp))
        self.assertFalse(speaking_has_monologue(trad))
        self.assertEqual(strip_speaker_marks(simp), "（自言自语）跟朋友吃了顿饭。 你今天怎么这么累？")

    def test_tts_and_speaker_helpers_recognize_tags(self):
        from utility.speaking_marks import split_speaking_turns, strip_speaker_marks, speaker_ids_in_text

        turns = split_speaking_turns("<1s> 心里话 <2> 对你说 <0.5> 再等一下")
        self.assertEqual(turns[0], (1, "心里话"))
        self.assertEqual(turns[1][0], 2)
        self.assertIn("<0.5>", turns[1][1])
        spoken = " ".join(t[1] for t in turns)
        self.assertNotIn("自言自语", spoken)
        self.assertFalse(spoken.strip().startswith("s"))
        self.assertEqual(strip_speaker_marks("<1s>（自言自语）心里话"), "（自言自语）心里话")
        from utility.speaking_marks import strip_monologue_tag
        self.assertEqual(strip_monologue_tag("（自言自语）心里话"), (False, "（自言自语）心里话"))
        self.assertEqual(speaker_ids_in_text("<1s> a <2> b"), [1, 2])


class CoverStepTest(unittest.TestCase):
    """t373u: scenes are never split by <Ns>, so every scene is its own cover step."""

    def test_steps_stamped_in_order_and_kept(self):
        from utility.speaking_marks import (
            COVER_STEP_KEY,
            cover_step_sequence,
            ensure_cover_steps,
            iter_cover_extract_targets,
            unique_cover_step_count,
        )

        scenes = [
            {"caption": "A", "visual": "V", "actor": "X", "speaking": "<1s> 心里先转了一圈。<2> 你今天怎么这么累？"},
            {"caption": "B", "visual": "V", "actor": "X", "speaking": "<1> 第二场对白。"},
            {"caption": "C", "visual": "V", "actor": "X", "speaking": "<1> 先坐下再说。<1s> 原来如此。"},
        ]
        self.assertTrue(ensure_cover_steps(scenes))
        self.assertEqual(cover_step_sequence(scenes), [1, 2, 3])
        self.assertEqual(unique_cover_step_count(scenes), 3)
        self.assertFalse(ensure_cover_steps(scenes))
        self.assertEqual(len(scenes), 3)  # nothing split
        self.assertEqual([s for _sc, s in iter_cover_extract_targets(scenes)], [1, 2, 3])
        scenes.insert(1, {"caption": "N", "speaking": "<1> 新加的一场。"})
        scenes[0][COVER_STEP_KEY] = 1
        self.assertTrue(ensure_cover_steps(scenes))
        self.assertEqual(cover_step_sequence(scenes), [1, 4, 2, 3])

    def test_segment_clone_shares_cover_step(self):
        import copy as _copy

        from utility.speaking_marks import ensure_cover_steps, iter_cover_extract_targets

        base = {"caption": "A", "visual": "V", "actor": "X", "speaking": "<1> a <s><2> b"}
        ensure_cover_steps([base])
        clone = _copy.deepcopy(base)  # t370u video segment clone: same authored fields, same step
        clone["speaking"] = "<1> a"
        scenes = [clone, base]
        self.assertEqual([sc for sc, _s in iter_cover_extract_targets(scenes)], [clone])


class SegmentMarkInsertTest(unittest.TestCase):
    """t373u: speaking box Ctrl+S inserts <s> at the cursor (only right before a <n> mark)."""

    def _ins(self, text, marker="|"):
        from utility.speaking_marks import segment_mark_insert

        pos = text.index(marker)
        return segment_mark_insert(text.replace(marker, "", 1), pos)

    def test_inserts_before_speaker_mark(self):
        new, pos, why = self._ins("<1> 你好。|<2> 今天怎么样？<1> 还行。")
        self.assertEqual(why, "")
        self.assertEqual(new, "<1> 你好。<s> <2> 今天怎么样？<1> 还行。")
        self.assertEqual(new[:pos], "<1> 你好。<s> ")
        new, _pos, _ = self._ins("<1> 你好。 |<12> 嗯。")
        self.assertEqual(new, "<1> 你好。 <s> <12> 嗯。")
        new, _pos, _ = self._ins("<1> 你好。|<1s> 我想想。")
        self.assertEqual(new, "<1> 你好。<s> <1s> 我想想。")
        new, _pos, _ = self._ins("<1> 你好。＜2＞ 嗯。".replace("＜2＞", "|＜2＞"))
        self.assertIn("<s> ＜2＞", new)

    def test_whitespace_between_cursor_and_mark_is_allowed(self):
        new, pos, why = self._ins("<1> 你好。|\n<2> 今天怎么样？")
        self.assertEqual(why, "")
        self.assertEqual(new, "<1> 你好。<s>\n<2> 今天怎么样？")
        self.assertEqual(pos, len("<1> 你好。<s>"))
        new, _pos, _ = self._ins("<1> 你好。|   <2> 嗯。")
        self.assertEqual(new, "<1> 你好。<s>   <2> 嗯。")

    def test_segments_follow_the_new_mark(self):
        from utility.speaking_marks import speaking_segments

        new, _pos, _ = self._ins("<1> 一。<2> 二。|<1> 三。<2> 四。")
        self.assertEqual(len(speaking_segments(new)), 2)

    def test_refused_positions(self):
        for text, bit in (
            ("<1> 你好。<|2> 嗯。", "标记里面"),          # inside the mark
            ("<1|> 你好。<2> 嗯。", "标记里面"),
            ("|<1> 你好。<2> 嗯。", "最开头"),            # very start
            ("  \n|<1> 你好。", "最开头"),
            ("<1> 你好。|<2>", "最末尾"),                 # mark with nothing after it
            ("<1> 你好。|<2>  ", "最末尾"),
            ("<1> 你好。<2> 嗯。|", "最末尾"),            # very end
            ("<1> 你好。<2> 嗯。  |", "最末尾"),
            ("<1> 你好。<2> |嗯。", "前半句是空的"),     # right after a mark
            ("<1> 你好。<2>\n|嗯。", "前半句是空的"),
            ("你|好。", "说话人标记"),                    # no owner mark
            ("<1> 你好。<s>|<2> 嗯。", "已经有"),          # duplicate (before)
            ("<1> 你好。<s> |<2> 嗯。", "已经有"),
            ("<1> 你好。|<s> <2> 嗯。", "已经有"),         # duplicate (after)
            ("<1> 你好 <s>|吗。<2> 嗯。", "已经有"),
        ):
            new, pos, why = self._ins(text)
            self.assertIsNone(new, text)
            self.assertIsNone(pos, text)
            self.assertIn(bit, why, text)

    def test_mid_sentence_splits_with_same_speaker(self):
        """t380u: cursor inside a line → <s> plus the same speaker mark."""
        new, pos, why = self._ins("<1> 你好|吗。<2> 嗯。")
        self.assertEqual(why, "")
        self.assertEqual(new, "<1> 你好 <s> <1> 吗。<2> 嗯。")
        self.assertEqual(new[pos:], "吗。<2> 嗯。")
        new, pos, why = self._ins("<1>\n好，我試試……|寫完了，居然沒那麼可怕。\n<2>\n看，你不是做不到。")
        self.assertEqual(why, "")
        self.assertEqual(new, "<1>\n好，我試試……\n<s> <1>\n寫完了，居然沒那麼可怕。\n<2>\n看，你不是做不到。")
        self.assertEqual(new[pos:pos + 3], "寫完了")
        new, _pos, why = self._ins("<2s> 我想|想看。<1> 好。")
        self.assertEqual(new, "<2s> 我想 <s> <2s> 想看。<1> 好。")
        new, _pos, why = self._ins("<1> 甲。<12> 乙乙|丙丙")
        self.assertEqual(new, "<1> 甲。<12> 乙乙 <s> <12> 丙丙")

    def test_mid_sentence_segments(self):
        from utility.speaking_marks import parse_speaking_turns, speaking_segments

        new, _pos, _ = self._ins("<1>\n好，我試試……|寫完了。\n<2>\n看，你不是做不到。")
        segs = speaking_segments(new)
        self.assertEqual(len(segs), 2)
        first = parse_speaking_turns(segs[0])
        rest = parse_speaking_turns(segs[1])
        self.assertEqual([(t.speaker, t.text) for t in first], [(1, "好，我試試……")])
        self.assertEqual([(t.speaker, t.text) for t in rest], [(1, "寫完了。"), (2, "看，你不是做不到。")])
        self.assertTrue(all(not t.cut_before for t in rest))

    def test_mid_sentence_keeps_timing(self):
        """t380u: speaking_timing stays usable after the extra <s> <n> (cut lands inside speaker 1's line)."""
        from utility.video_segments import plan_first_segment, segment_cut_seconds

        old = "<1>\n好，我試試寫完了。\n<2>\n看，你不是做不到。"
        new, _pos, _ = self._ins("<1>\n好，我試試|寫完了。\n<2>\n看，你不是做不到。")
        scene = {"speaking": new, "speaking_timing": {"text": old, "sections": [
            {"speaker": 1, "start": 0.0, "end": 4.0, "text": "好，我試試寫完了。"},
            {"speaker": 2, "start": 4.2, "end": 8.0, "text": "看，你不是做不到。"}]}}
        plan = plan_first_segment(scene)
        cut, source, _spans = segment_cut_seconds(scene, plan, 8.7)
        self.assertEqual(source, "timing")
        self.assertTrue(0.5 < cut < 4.0, cut)

    def test_hotkey_wiring(self):
        cfg = Path(ROOT, "gui/workflow/wf_config.py").read_text(encoding="utf-8")
        spk = Path(ROOT, "gui/workflow/wf_speaking.py").read_text(encoding="utf-8")
        self.assertIn('self.scene_speaking.bind("<Control-s>", self._on_speaking_ctrl_s_insert_segment_mark)', cfg)
        self.assertIn('self.scene_speaking.bind("<Control-S>", self._on_speaking_ctrl_s_insert_segment_mark)', cfg)
        self.assertNotIn("_on_speaking_ctrl_s_split_clone", cfg + spk)
        body = spk.split("def _on_speaking_ctrl_s_insert_segment_mark", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("segment_mark_insert(", body)
        self.assertIn("messagebox.showwarning", body)
        self.assertIn("self.update_current_scene()", body)
        self.assertIn('mark_set("insert"', body)
        for gone in ("deepcopy", "scenes.insert", "max_id"):
            self.assertNotIn(gone, body)


if __name__ == "__main__":
    unittest.main()
