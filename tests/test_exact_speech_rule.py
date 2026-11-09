"""t336u: MiniMax speaks exactly the speaking text — once, nothing added (offline)."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_video_speaker_semantics import _install_stubs, _scene  # noqa: E402

_install_stubs()

import config_prompt as cp  # noqa: E402
from utility import prompt_polish as pp  # noqa: E402

TWO = "<1> 你今天怎么来了？ <2> 想你了。"
SELF = "<1s> 我一个人走在路上，想起从前。"


def _h3(speaking, **kw):
    kw.setdefault("audio_mode", "none")
    return cp.build_h3_prompt([_scene(speaking)], language="zh", seconds=8, **kw)


def _lines(speaking):
    return [t.strip() for t in re.split(r"<\d+s?>", speaking) if t.strip()]


class ExactSpeechRuleTest(unittest.TestCase):
    def test_rule_wording(self):
        r = cp.SPOKEN_EXACT_TEXT_RULE
        self.assertTrue(r.startswith("Exact speech:"))
        for must in ("exactly the speaking text", "word for word", "not one word more or less",
                     "never repeated", "nothing is added", "nobody speaks after the last line"):
            self.assertIn(must, r)
        self.assertEqual(cp.H3_SPOKEN_LEAD, cp.SPOKEN_AUDIO_ONLY_LABEL + " " + r)

    def test_h3_speaks_each_line_once_with_one_rule_before_dialogue(self):
        for speaking in (TWO, SELF):
            for mode in ("none", "talk"):
                p = _h3(speaking, audio_mode=mode)
                self.assertNotIn(cp.SPOKEN_TRANSCRIPT_BEGIN, p, (speaking, mode))
                self.assertEqual(p.count(cp.SPOKEN_EXACT_TEXT_RULE), 1)
                self.assertEqual(p.count(cp.SPOKEN_AUDIO_ONLY_LABEL), 1)
                for line in _lines(speaking):
                    self.assertEqual(p.count(line), 1, (line, mode))
                # the lead sits immediately before the first dialogue sentence
                at = cp._h3_dialogue_start(p)
                self.assertTrue(p[:at].rstrip().endswith(cp.SPOKEN_EXACT_TEXT_RULE))
                self.assertEqual(cp.count_h3_no_subtitle_rules(p), 1)
                self.assertTrue(p.startswith(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE))

    def test_no_wording_invites_more_speech(self):
        p = _h3(TWO)
        self.assertNotIn("keep talking", p)
        self.assertIn("while they say their lines", p)
        self.assertNotIn("while they talk and add no silence", pp._SYS_H3)
        self.assertIn("this never means more speech", pp._SYS_H3)

    def test_silent_scene_has_no_rule(self):
        p = _h3("")
        self.assertNotIn(cp.SPOKEN_EXACT_TEXT_RULE, p)
        self.assertNotIn(cp.SPOKEN_TRANSCRIPT_BEGIN, p)

    def test_segment_keeps_only_its_own_lines(self):
        """The old trailing transcript listed every line in every segment → segment 2 re-spoke segment 1."""
        from utility.minimax_segments import segment_prompt

        timeline = [(0.0, 3.0, 1), (3.0, 6.0, 2)]
        p = _h3(TWO, audio_mode="talk")
        legacy = cp.ensure_spoken_transcript_block(p, [_scene(TWO)])  # a prompt saved before t336u
        self.assertEqual(legacy.count("你今天怎么来了？"), 2)
        for prompt in (p, cp.prepare_h3_spoken_text(legacy)):
            seg2 = segment_prompt(prompt, 2, 2, 3.0, 6.0, True, timeline=timeline)
            self.assertIn("想你了。", seg2)
            self.assertNotIn("你今天怎么来了？", seg2)
            self.assertEqual(seg2.count(cp.SPOKEN_EXACT_TEXT_RULE), 1)

    def test_send_time_prepare_strips_duplicate_transcript_idempotent(self):
        legacy = cp.ensure_spoken_transcript_block(cp.strip_exact_speech_rule(_h3(TWO), with_label=True),
                                                   [_scene(TWO)])
        fixed = cp.prepare_h3_spoken_text(legacy)
        self.assertNotIn(cp.SPOKEN_TRANSCRIPT_BEGIN, fixed)
        self.assertEqual(fixed.count(cp.SPOKEN_EXACT_TEXT_RULE), 1)
        self.assertEqual(fixed.count("你今天怎么来了？"), 1)
        self.assertEqual(cp.prepare_h3_spoken_text(fixed), fixed)
        # a prompt whose speech lives only in the transcript (no <d>) is left alone
        flow = cp.format_spoken_transcript_block([_scene(TWO)])
        self.assertEqual(cp.prepare_h3_spoken_text(flow), flow)
        for name in ("utility/minimax_dual.py", "utility/sd_image_processor.py"):
            src = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("prepare_h3_spoken_text(prompt)", src)

    def test_transcript_block_has_rule_once(self):
        block = cp.format_spoken_transcript_block([_scene(TWO)])
        self.assertEqual(block.splitlines()[1], cp.SPOKEN_AUDIO_ONLY_LABEL)
        self.assertEqual(block.splitlines()[2], cp.SPOKEN_EXACT_TEXT_RULE)
        self.assertEqual(block.count(cp.SPOKEN_EXACT_TEXT_RULE), 1)
        empty = cp.format_spoken_transcript_block([{"speaking": ""}])
        self.assertIn("speak nothing", empty)

    def test_minimax_short_prompt_lines_once(self):
        p = cp.build_minimax_video_prompt([_scene(TWO)], language="zh", with_audio=False)
        self.assertNotIn(cp.SPOKEN_TRANSCRIPT_BEGIN, p)
        self.assertEqual(p.count("你今天怎么来了？"), 1)
        self.assertEqual(p.count(cp.SPOKEN_EXACT_TEXT_RULE), 1)
        a = cp.build_minimax_video_prompt([_scene(TWO)], language="zh", with_audio=True)
        self.assertIn(cp.SPOKEN_TRANSCRIPT_BEGIN, a)  # with audio the transcript is the only text source
        self.assertEqual(a.count("你今天怎么来了？"), 1)
        self.assertEqual(a.count(cp.SPOKEN_EXACT_TEXT_RULE), 1)

    def test_post_strata_restore(self):
        orig = _h3(TWO)
        dropped = cp.strip_exact_speech_rule(orig, with_label=True)
        doubled = orig.replace("[Shot 1]", "[Shot 1] " + cp.SPOKEN_EXACT_TEXT_RULE, 1)
        for polished in (dropped, doubled, orig):
            out = cp.restore_exact_speech_rule(orig, polished)
            self.assertEqual(out.count(cp.SPOKEN_EXACT_TEXT_RULE), 1)
            self.assertLess(out.index(cp.SPOKEN_EXACT_TEXT_RULE), out.index("<d>"))
        # original without the rule: Strata may not add one
        plain = cp.strip_exact_speech_rule(orig, with_label=True)
        self.assertNotIn(cp.SPOKEN_EXACT_TEXT_RULE, cp.restore_exact_speech_rule(plain, doubled))
        # transcript prompts: the copy inside the restored block stays, copies outside go
        flow = "Clip.\n\n" + cp.format_spoken_transcript_block([_scene(TWO)])
        strata = cp.SPOKEN_EXACT_TEXT_RULE + " Clip.\n\n" + cp.format_spoken_transcript_block([_scene(TWO)])
        out = cp.restore_exact_speech_rule(flow, cp.restore_spoken_transcript(flow, strata))
        self.assertEqual(out.count(cp.SPOKEN_EXACT_TEXT_RULE), 1)
        self.assertGreater(out.index(cp.SPOKEN_EXACT_TEXT_RULE), out.index(cp.SPOKEN_TRANSCRIPT_BEGIN))

    def test_strata_repeat_check_and_instructions(self):
        orig = _h3(TWO)
        self.assertEqual(pp._repeated_spoken_line(orig, orig), "")
        repeated = orig.replace("One person speaks at a time", "她又说：你今天怎么来了？ One person speaks at a time")
        self.assertEqual(pp._repeated_spoken_line(orig, repeated), "你今天怎么来了？")
        for sys_txt in (pp._SYS_GENERAL, pp._SYS_H3):
            self.assertEqual(sys_txt.count('starting "Exact speech:"'), 1)
            self.assertIn("never write a spoken line a second time", sys_txt)
            self.assertIn("do not repeat, split, merge, reword", sys_txt)
        src = (ROOT / "utility/prompt_polish.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("restore_exact_speech_rule(prompt, out)"), 2)
        self.assertIn("_repeated_spoken_line(prompt, out)", src)


if __name__ == "__main__":
    unittest.main()
