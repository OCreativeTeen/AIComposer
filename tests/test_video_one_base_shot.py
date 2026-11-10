"""t382u offline tests: the video stays in the base picture (picture 1 / start frame) the whole time. It never cuts to
a portrait or a close-up of whoever speaks; the speaker lip-syncs where they are, the others keep their mouths closed
(small movements are fine), and change is slow and local. The rule is in every video prompt (H3, MiniMax, Grok /
Gemini flow, FYI-only) and survives Strata 精简 (system prompts, restore, validate)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_video_speaker_semantics import _install_stubs, _scene  # noqa: E402

_install_stubs()

import config_prompt as cp  # noqa: E402

SPEAK = "<1> 你今天怎麼來了？ <2> 想你了。"
PIXAR = "三维卡通 (Pixar-Art-Cartoon)"


def _h3(**kw):
    return cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", text="keywords", style=PIXAR,
                              region="中国", era="现代", **kw)


def _flow(evolve="keep"):
    return cp.build_video_flow_prompt(
        frames="one", background="none", evolve=evolve, visual_style=PIXAR,
        scene_content=[_scene(SPEAK)], language="zh", narrative="story", text="keywords",
        use_visual=True, use_speaking=True, use_actor=True, story_style="story_speak",
    )


def _mm():
    return cp.build_minimax_video_prompt([_scene(SPEAK)], style=PIXAR, language="zh")


def _fyi():
    return cp.build_video_fyi_only_prompt(frames="one", evolve="keep", visual_style=PIXAR, fyi="走过来")


def _rule(prompt):
    sp = cp._rule_span(prompt, cp.VIDEO_ONE_SHOT_PREFIX)
    return prompt[sp[0]:sp[1]] if sp else ""


class OneBaseShotRuleTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_rule_text(self):
        r = cp.video_one_shot_rule("picture 1")
        self.assertTrue(r.startswith(cp.VIDEO_ONE_SHOT_PREFIX))
        for must in ("stays inside the base scene of picture 1", "never cuts", "never cuts to a portrait",
                     "single-person shot of whoever is speaking", "lips move in sync", "keeps the mouth closed",
                     "small natural movements", "talk with each other inside this same frame", "slow, small and local",
                     "never the whole scene", "绝不切到任何人的肖像", "不说话的人闭嘴", "可以做小动作", "只有缓慢的局部变化"):
            self.assertIn(must, r)
        self.assertEqual(_rule(r), r)  # 整句（到中文括号结束）就是一条锁定句

    def test_every_video_prompt_has_it_once(self):
        for name, p, pic in (("h3", _h3(), "<Picture 1>"), ("flow", _flow(), "picture 1"),
                             ("flow_evolve", _flow("to_style"), "picture 1"), ("minimax", _mm(), "the first frame"),
                             ("fyi", _fyi(), "picture 1")):
            rule = cp.video_one_shot_rule(pic)
            self.assertEqual(p.count(rule), 1, name)
            self.assertEqual(p.count(cp.VIDEO_ONE_SHOT_PREFIX), 1, name)

    def test_h3_rule_before_dialogue_and_spans_dont_merge(self):
        p = _h3()
        rule = _rule(p)
        self.assertLess(p.index(rule), p.index("<d>"))
        art = cp._rule_span(p, cp.ART_STYLE_LOCK_PREFIX)
        self.assertNotIn(cp.VIDEO_ONE_SHOT_PREFIX, p[art[0]:art[1]])
        self.assertNotIn(cp.ART_STYLE_LOCK_PREFIX, rule)

    def test_prompts_do_not_ask_for_cuts_elsewhere(self):
        for p in (_h3(), _flow(), _mm(), _fyi()):
            body = p.replace(_rule(p), " ").lower()
            for w in ("cut to", "cuts to", "cutaway", "jump cut", "[shot 2]", "close-up of", "portrait shot"):
                self.assertNotIn(w, body)

    def test_transition_prompt_not_forced(self):
        src = (Path(ROOT) / "config_prompt.py").read_text(encoding="utf-8")
        body = src.split("def build_transition_video_prompt", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("video_one_shot_rule", body)


class StrataKeepsOneShotTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_system_prompts_name_rule(self):
        from utility.prompt_polish import _SYS_GENERAL, _SYS_H3

        for s in (_SYS_GENERAL, _SYS_H3):
            self.assertIn('"One base shot:"', s)
            self.assertIn("copy it verbatim, once", s)
            self.assertIn("never write a cut", s)
            self.assertIn("portrait, a close-up or a single-person shot", s)
            self.assertIn("mouths closed", s)

    def test_restore_after_drop_or_rewrite(self):
        for original in (_h3(), cp.ensure_video_no_subtitle_first_line(_flow()), _mm()):
            rule = _rule(original)
            dropped = original.replace(" " + rule, "").replace(rule, "")
            self.assertNotIn(cp.VIDEO_ONE_SHOT_PREFIX, dropped)
            out = cp.restore_video_locked_rules(original, dropped)
            self.assertEqual(out.count(rule), 1)
            self.assertEqual(cp.restore_video_locked_rules(original, out), out)  # 幂等
            bad = original.replace(rule, "One base shot: cut to a close-up portrait of each speaker.")
            fixed = cp.restore_video_locked_rules(original, bad)
            self.assertEqual(fixed.count(rule), 1)
            self.assertNotIn("close-up portrait of each speaker", fixed)

    def test_validate_rejects_added_cuts(self):
        from utility.prompt_polish import validate

        original = _h3()
        self.assertEqual(validate(original, original, "minimax_5070ti"), "")
        self.assertEqual(cp.added_cut_words(original, original), "")
        cut = original.replace("<d>", "Then cut to a close-up of <1>. <d>", 1)
        self.assertEqual(cp.added_cut_words(original, cut), "cut to")
        self.assertIn("切镜头", validate(original, cut, "minimax_5070ti"))
        flow = cp.ensure_video_no_subtitle_first_line(_flow())
        self.assertIn("不切镜头", validate(flow, flow.replace(_rule(flow), ""), "grok"))
        self.assertEqual(cp.added_cut_words("no rule here", "cut to"), "")


if __name__ == "__main__":
    unittest.main()
