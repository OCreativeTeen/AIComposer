"""t422u / t424u: 生场视频没勾「人物」时不加图里没有的人，也不写地域 / 时代 / 舞台 / 默认讲员；
场景描述、讲话、讲话当故事内容、人物都没勾（只按 FYI）时只让图本身忠实地动起来。
Grok / Gemini / 过渡 / MiniMax H3 都有锁定句，Strata 精简后原样补回，丢了或多写了人 / 地域时代的词不通过。"""
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
STYLE = "三维卡通 (Pixar-Art-Cartoon)"
FYI = "保持画面的基本构成 尽量不要做场景转换 镜头可以移动"
PLACE_WORDS = ("Babylon", "Middle East", "Setting region", "Historical era", "If people appear", ", set in")


def _h3_faithful():
    return cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", text="keywords", style=STYLE,
                              region="中东", era="古巴比伦", use_visual=False, use_speaking=False, fyi=FYI,
                              seconds=12.0, use_actor=False, faithful=True)


def _h3_no_actor(**kw):
    return cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", text="keywords", style=STYLE,
                              region="中东", era="古巴比伦", use_actor=False, **kw)


def _fyi():
    return cp.build_video_fyi_only_prompt(frames="one", evolve="keep", visual_style=STYLE, text="keywords",
                                          duration="12s", fyi=FYI)


def _flow(use_actor=False, frames="one"):
    return cp.build_video_flow_prompt(
        frames=frames, background="none", evolve="keep", visual_style=STYLE, scene_content=[_scene(SPEAK)],
        language="zh", narrative="story", text="keywords", use_visual=True, use_speaking=True,
        use_actor=use_actor, story_style="story_speak")


def _span(prompt, prefix):
    sp = cp._rule_span(prompt, prefix)
    return prompt[sp[0]:sp[1]] if sp else ""


class RuleTextTest(unittest.TestCase):
    def test_rules_are_single_locked_sentences(self):
        for rule, prefix in ((cp.video_faithful_rule("<Picture 1>"), cp.VIDEO_FAITHFUL_PREFIX),
                             (cp.video_no_new_people_rule("<Picture 1>"), cp.VIDEO_NO_NEW_PEOPLE_PREFIX)):
            self.assertTrue(rule.startswith(prefix))
            self.assertTrue(rule.endswith("）"))
            self.assertEqual(_span(rule, prefix), rule)
        r = cp.video_no_new_people_rule("picture 1")
        for must in ("only the people already shown in picture 1", "none if it shows nobody", "no protagonist",
                     "crowd", "不加人"):
            self.assertIn(must, r)
        f = cp.video_faithful_rule("picture 1")
        for must in ("bring picture 1 itself to life", "keyword lettering", "add no place, country, period or culture",
                     "忠实动画"):
            self.assertIn(must, f)

    def test_silent_one_shot_has_no_speaking_clause(self):
        silent = cp.video_one_shot_rule("<Picture 1>", speaking=False)
        self.assertTrue(silent.startswith(cp.VIDEO_ONE_SHOT_PREFIX))
        self.assertIn("Nobody speaks", silent)
        for w in ("speaks right where", "lips move in sync", "whoever is speaking", "talk with each other", "谁说话"):
            self.assertNotIn(w, silent)
        self.assertEqual(_span(silent, cp.VIDEO_ONE_SHOT_PREFIX), silent)
        self.assertIn("speaks right where", cp.video_one_shot_rule("<Picture 1>"))


class FaithfulModeTest(unittest.TestCase):
    def test_h3_faithful_only_animates_picture(self):
        p = _h3_faithful()
        self.assertEqual(p.count(cp.video_faithful_rule("<Picture 1>")), 1)
        self.assertEqual(p.count(cp.video_no_new_people_rule("<Picture 1>")), 1)
        self.assertEqual(p.count(cp.video_one_shot_rule("<Picture 1>", speaking=False)), 1)
        self.assertIn(cp.VIDEO_IMAGE_KEYWORDS_RULE, p)  # 关键字作背景照旧
        self.assertIn("Direction:", p)  # FYI
        for w in PLACE_WORDS + ("小美", "阿明", "Speaker map", "Exactly", "<d>", "Lip sync", "两人坐在", "lips closed"):
            self.assertNotIn(w, p, w)

    def test_fyi_prompt_rules(self):
        p = _fyi()
        self.assertEqual(p.count(cp.video_faithful_rule("picture 1")), 1)
        self.assertEqual(p.count(cp.video_no_new_people_rule("picture 1")), 1)
        self.assertEqual(p.count(cp.video_one_shot_rule("picture 1", speaking=False)), 1)
        for w in PLACE_WORDS:
            self.assertNotIn(w, p)

    def test_guard_without_spoken_rule(self):
        g = cp.video_guard_block([], None, "", spoken=False)
        self.assertNotIn(cp.SPOKEN_SOURCE_RULE, g)
        self.assertIn(cp.VIDEO_NO_CAPTION_RULE, g)
        self.assertIn(cp.SPOKEN_SOURCE_RULE, cp.video_guard_block([_scene(SPEAK)]))


class NoActorTest(unittest.TestCase):
    def test_h3_no_actor_drops_region_era_stage_and_locks_people(self):
        p = _h3_no_actor()
        self.assertEqual(p.count(cp.video_no_new_people_rule("<Picture 1>")), 1)
        self.assertNotIn(cp.VIDEO_FAITHFUL_PREFIX, p)
        for w in ("Babylon", "Middle East", ", set in"):
            self.assertNotIn(w, p)
        self.assertIn("<d>", p)  # 讲话照旧
        self.assertIn("speaks right where", p)

    def test_h3_with_actor_unchanged(self):
        p = cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", style=STYLE,
                               region="中东", era="古巴比伦")
        self.assertIn(", set in", p)
        self.assertNotIn(cp.VIDEO_NO_NEW_PEOPLE_PREFIX, p)

    def test_story_mode_one_shot_is_silent(self):
        p = _h3_no_actor(speaking_as_story=True)
        self.assertIn(cp.video_one_shot_rule("<Picture 1>", speaking=False), p)

    def test_flow_and_transition_people_lines(self):
        p = _flow(use_actor=False)
        self.assertEqual(p.count(cp.video_no_new_people_rule("picture 1")), 1)
        self.assertNotIn(cp.PEOPLE_NO_CAST_LINE, p)
        self.assertNotIn(cp.VIDEO_NO_NEW_PEOPLE_PREFIX, _flow(use_actor=True))
        lines = cp._video_people_lines([], "two", "", "", "story")
        self.assertEqual(lines, [cp.video_no_new_people_rule("picture 1 and picture 2")])


class StrataTest(unittest.TestCase):
    def test_restore_after_drop_or_rewrite(self):
        for original in (_h3_faithful(), cp.ensure_video_no_subtitle_first_line(_fyi()),
                         cp.ensure_video_no_subtitle_first_line(_flow())):
            for prefix in (cp.VIDEO_FAITHFUL_PREFIX, cp.VIDEO_NO_NEW_PEOPLE_PREFIX):
                rule = _span(original, prefix)
                if not rule:
                    continue
                dropped = original.replace(" " + rule, "").replace(rule, "")
                out = cp.restore_video_locked_rules(original, dropped)
                self.assertEqual(out.count(rule), 1, prefix)
                bad = original.replace(rule, prefix + " a crowd of Babylonian merchants walks in.")
                fixed = cp.restore_video_locked_rules(original, bad)
                self.assertEqual(fixed.count(rule), 1)
                self.assertNotIn("Babylonian merchants", fixed)

    def test_added_people_and_place_words(self):
        o = _h3_faithful()
        self.assertEqual(cp.added_people_words(o, o), "")
        self.assertEqual(cp.added_place_era_words(o, o), "")
        self.assertEqual(cp.added_people_words(o, o.replace("[Shot 1]", "[Shot 1] A crowd gathers.", 1)), "crowd")
        self.assertEqual(cp.added_place_era_words(o, o.replace("[Shot 1]", "[Shot 1] In ancient Babylon.", 1)),
                         "ancient")
        self.assertEqual(cp.added_people_words("no rule", "crowd"), "")
        self.assertEqual(cp.added_place_era_words("no rule", "Babylon"), "")

    def test_validate(self):
        from utility.prompt_polish import validate, _SYS_GENERAL, _SYS_H3

        for s in (_SYS_GENERAL, _SYS_H3):
            self.assertIn('"Faithful animation:"', s)
            self.assertIn('"No new people:"', s)
        o = _h3_faithful()
        self.assertEqual(validate(o, o, "minimax_5070ti"), "")
        self.assertIn("忠实动画", validate(o, o.replace(_span(o, cp.VIDEO_FAITHFUL_PREFIX), ""), "minimax_5070ti"))
        self.assertIn("不加人", validate(o, o.replace(_span(o, cp.VIDEO_NO_NEW_PEOPLE_PREFIX), ""), "minimax_5070ti"))
        self.assertIn("加了人", validate(o, o.replace("[Shot 1]", "[Shot 1] Middle people walk.", 1), "minimax_5070ti"))
        self.assertIn("地域", validate(o, o.replace("[Shot 1]", "[Shot 1] In Mesopotamia.", 1), "minimax_5070ti"))


class DialogSourceTest(unittest.TestCase):
    SRC = (Path(ROOT) / "gui" / "video_prompt_dialog.py").read_text(encoding="utf-8")

    def test_background_only_with_actor(self):
        s = self.SRC
        self.assertIn("_bg_on = bool(bg_include_var.get()) and _use_actor", s)
        self.assertIn("include=_bg_on", s)
        self.assertIn('region=bg_region if _bg_on else "", era=bg_era if _bg_on else ""', s)
        self.assertIn("stage=bg_stage if _bg_on else None", s)
        self.assertIn("use_actor=_use_actor, faithful=fyi_only", s)
        self.assertNotIn("background_condition_block(", s)  # 只按 FYI 不再接背景条件

    def test_no_portraits_or_strata_people_without_actor(self):
        s = self.SRC
        i = s.index("portrait_refs = []\n        # t216u")
        self.assertIn("and _use_actor", s[i:i + 700])
        self.assertIn("if polish_var.get() and scenes and not fyi_only:", s)
        self.assertIn("spoken=not fyi_only", s)


if __name__ == "__main__":
    unittest.main()
