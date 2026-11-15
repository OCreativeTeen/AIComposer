"""t429u: MiniMax 无讲话档（M0 / M1）没勾人物时：不加人、不加动物 / 生物；讲话当故事内容只用图里已有的东西 + 镜头 + 光线 +
环境 + 关键词讲；Strata 译文写了新人物 / 动物就不通过。"""
import json
import unittest

from tests.test_video_speaker_semantics import _install_stubs, _scene

_install_stubs()

import config_prompt as cp  # noqa: E402
from prompt_profiles import M0_FAITHFUL, M1_SILENT, blocks, select_h3_profile  # noqa: E402
from prompt_profiles.context import make_h3_context  # noqa: E402
from prompt_profiles.h3 import build_h3  # noqa: E402
from prompt_profiles.strata import refine_h3, system_prompt  # noqa: E402
from prompt_profiles.validate import animal_word, being_word, field, validate_h3  # noqa: E402

STYLE = "三维卡通 (Pixar-Art-Cartoon)"
STORY = "我妻子每天晚上都在等我回家，弟弟却总说我变了。"


def _m1(**kw):
    return make_h3_context(M1_SILENT, [_scene(STORY)], style=STYLE, text="keywords", story_on=True, **kw)


def _call(answer):
    return lambda system, user, timeout_s: json.dumps(answer)


class SameProfileTest(unittest.TestCase):
    def test_tom_combo_routes(self):
        # 讲话当故事内容（人物没勾）→ M1；什么都不勾 → M0；都是 MiniMax 无讲话档，同一个工作流（窗口里选的那个）
        self.assertEqual(select_h3_profile(is_minimax=True, fyi_only=False, story_on=True, use_speaking=False), M1_SILENT)
        self.assertEqual(select_h3_profile(is_minimax=True, fyi_only=True, story_on=False, use_speaking=False),
                         M0_FAITHFUL)

    def test_background_ticked_without_actor_has_no_place(self):
        # 对话框只在勾了人物时才把地域 / 时代传进来（t424u）；就算传了，没勾人物也不写
        ctx = _m1(region="中东", era="古巴比伦")
        self.assertEqual(ctx.place, "")
        self.assertNotIn("Babylon", build_h3(ctx).prompt)


class PromptTest(unittest.TestCase):
    def test_no_creature_invites_in_template(self):
        for ctx in (_m1(), make_h3_context(M0_FAITHFUL, [], style=STYLE, text="keywords")):
            with self.subTest(profile=ctx.profile):
                p = build_h3(ctx).prompt
                self.assertNotIn("animals and objects", p)
                self.assertNotIn("acts out", p)
                self.assertNotIn("breathing", p)
                self.assertNotIn("birds", p)
                self.assertNotIn("妻子", p)
                self.assertIn(blocks.no_new_people(), p)
                self.assertIn("no animal, pet, cat, dog, bird, creature, mascot or cartoon character is added", p)
                self.assertEqual(validate_h3(p, ctx), "")

    def test_story_told_through_scene(self):
        p = build_h3(_m1()).prompt
        self.assertIn(blocks.STORY_THROUGH_SCENE, field(p, "detailed_description:"))
        self.assertIn("carried by the camera, the light", field(p, "summary:"))

    def test_actor_ticked_still_acts(self):
        ctx = _m1(use_actor=True)
        p = build_h3(ctx, {"story": "she waits by the door"}).prompt
        self.assertIn("acts out this moment", p)
        self.assertNotIn(cp.VIDEO_NO_NEW_PEOPLE_PREFIX, p)
        self.assertEqual(validate_h3(p, ctx), "")

    def test_soundscape_no_birds(self):
        self.assertNotIn("bird", blocks.SOUNDSCAPE)
        self.assertIn("No speech, no singing, no music.", blocks.SOUNDSCAPE)

    def test_locked_rule_survives_restore(self):
        ctx = _m1()
        out, _ = refine_h3(ctx, call=_call({"story": "warm lamplight slowly fills the quiet room"}))
        pre = build_h3(ctx).prompt
        self.assertEqual(cp.restore_video_locked_rules(pre, out), out)


class StrataTest(unittest.TestCase):
    def test_tom_case_translation_with_people_rejected(self):
        ctx = _m1()
        plain = build_h3(ctx).prompt
        for story in ("his wife waits for him every night by the door",
                      "a woman waits by the door while her younger brother shakes his head",
                      "a little dog sleeps by the door",
                      "a cartoon cat watches from the window"):
            with self.subTest(story=story):
                out, why = refine_h3(ctx, call=_call({"story": story}))
                self.assertEqual(out, plain)
                self.assertIn("人物 / 动物", why)

    def test_mood_translation_accepted(self):
        ctx = _m1()
        out, why = refine_h3(ctx, call=_call({"story": "warm lamplight slowly fills the quiet room while the "
                                                       "shadows by the door grow long"}))
        self.assertIn("Throughout the clip, warm lamplight slowly fills the quiet room", out)
        self.assertNotIn("没精简", why)

    def test_visual_may_describe_picture_people_but_not_new_animals(self):
        ctx = make_h3_context(M1_SILENT, [_scene("x")], style=STYLE, text="keywords", use_visual=True)
        out, why = refine_h3(ctx, call=_call({"visual": "the two sit side by side on the sofa, she smiles"}))
        self.assertIn("she smiles", out)
        out, why = refine_h3(ctx, call=_call({"visual": "the two sit on the sofa with a dog"}))
        self.assertIn("没精简", why)

    def test_system_prompt_rules(self):
        s = system_prompt(_m1())
        self.assertIn("Keep every subject to what the start picture already shows", s)
        self.assertIn('"story" is the moment whose mood the scene shows', s)
        self.assertNotIn("act out", s)
        self.assertNotIn("she smiles warmly", s)


class WordsTest(unittest.TestCase):
    def test_being_words(self):
        for w in ("wife", "brother", "a cat", "dogs", "she", "creature", "boy"):
            self.assertTrue(being_word(w), w)
        self.assertEqual(being_word("warm light on the wall"), "")
        self.assertEqual(being_word("a cat sleeps", "一只猫在睡觉"), "")
        self.assertEqual(animal_word("she smiles"), "")
        self.assertEqual(animal_word("a bird flies"), "bird")

    def test_validate_rejects_creature_in_content(self):
        ctx = _m1()
        b = build_h3(ctx, {"story": "warm lamplight fills the room"})
        bad = b.prompt.replace("warm lamplight fills the room", "a cat walks across the room")
        self.assertIn("人物 / 动物", validate_h3(bad, ctx))


if __name__ == "__main__":
    unittest.main()
