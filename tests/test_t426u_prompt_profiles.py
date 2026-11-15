"""t426u: MiniMax 无讲话档（M0 忠实动画 / M1 无讲话场景）的档位提示词、校验、Strata 翻译和发送前核对。"""
import json
import os
import re
import unittest

from tests.test_video_speaker_semantics import _install_stubs, _scene

_install_stubs()

import config_prompt as cp  # noqa: E402
from prompt_profiles import M0_FAITHFUL, M1_SILENT, select_h3_profile  # noqa: E402
from prompt_profiles import blocks  # noqa: E402
from prompt_profiles.context import make_h3_context  # noqa: E402
from prompt_profiles.h3 import build_h3  # noqa: E402
from prompt_profiles.strata import refine_h3, system_prompt  # noqa: E402
from prompt_profiles.validate import field, has_cjk, speech_word, validate_h3  # noqa: E402

STYLE = "三维卡通 (Pixar-Art-Cartoon)"
SPEAK = "<1> 你今天怎麼來了？ <2> 想你了。"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _m0(fyi="镜头慢慢推近，树叶随风摆动", text="keywords"):
    return make_h3_context(M0_FAITHFUL, [_scene(SPEAK)], style=STYLE, text=text, fyi=fyi,
                           use_visual=True, story_on=True, use_actor=True, region="中东", era="古巴比伦")


def _m1(actor=False, story=True, visual=True, fyi="", region="", era="", text="erase"):
    return make_h3_context(M1_SILENT, [_scene(SPEAK)], style=STYLE, text=text, fyi=fyi, use_visual=visual,
                           story_on=story, use_actor=actor, region=region, era=era)


def _fake(answer):
    calls = []

    def call(system, user, timeout_s):
        calls.append((system, user))
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)

    call.calls = calls
    return call


def _body(prompt):
    return prompt.replace(blocks.SOUNDSCAPE, " ")


class SelectTest(unittest.TestCase):
    def sel(self, **kw):
        base = dict(is_minimax=True, fyi_only=False, story_on=False, use_speaking=False, audio_mode="none",
                    frames="one", transition=False)
        base.update(kw)
        return select_h3_profile(**base)

    def test_m0_m1(self):
        self.assertEqual(self.sel(fyi_only=True), M0_FAITHFUL)
        self.assertEqual(self.sel(), M1_SILENT)
        self.assertEqual(self.sel(story_on=True, use_speaking=False), M1_SILENT)

    def test_other_combos_old_path(self):
        self.assertEqual(self.sel(use_speaking=True), "")
        self.assertEqual(self.sel(is_minimax=False, fyi_only=True), "")
        self.assertEqual(self.sel(fyi_only=True, transition=True), "")
        self.assertEqual(self.sel(frames="two"), "")
        self.assertEqual(self.sel(audio_mode="talk"), "")
        self.assertEqual(self.sel(audio_mode="sing", fyi_only=True), "")

    def test_switch(self):
        self.assertEqual(self.sel(fyi_only=True, enabled=False), "")
        import prompt_profiles

        self.assertTrue(prompt_profiles.PROMPT_PROFILES_ENABLED)


class M0PromptTest(unittest.TestCase):
    def test_shape_and_rules(self):
        ctx = _m0()
        en = {"fyi": "the camera slowly pushes in while the leaves sway in the wind"}
        b = build_h3(ctx, en)
        p = b.prompt
        self.assertTrue(p.startswith("subject_definitions:"))
        self.assertTrue(cp.is_profile_prompt(p))
        self.assertEqual(validate_h3(p, ctx, allow_raw=b.allow_raw, fyi_text=b.fyi_text), "")
        self.assertFalse(has_cjk(p))
        self.assertEqual(speech_word(_body(p)), "")
        self.assertEqual(field(p, "overall_soundscape:"), blocks.SOUNDSCAPE)
        self.assertIn("No speech, no singing, no music", field(p, "overall_soundscape:"))
        self.assertIn("quiet natural ambient sound of the place", field(p, "overall_soundscape:"))
        self.assertEqual(field(p, "non_diegetic_music:"), blocks.MUSIC)
        for pre in (cp.ART_STYLE_LOCK_PREFIX, cp.VIDEO_ONE_SHOT_PREFIX, cp.VIDEO_PROPS_LOCK_PREFIX,
                    cp.VIDEO_FAITHFUL_PREFIX, cp.VIDEO_NO_NEW_PEOPLE_PREFIX, cp.VIDEO_IMAGE_KEYWORDS_PREFIX):
            self.assertEqual(p.count(pre), 1, pre)
        self.assertIn("Throughout the clip, the camera slowly pushes in", field(p, "detailed_description:"))
        self.assertNotIn("Throughout the clip, the camera", field(p, "overall_soundscape:"))

    def test_m0_ignores_scene_people_and_place(self):
        ctx = _m0()
        p = build_h3(ctx).prompt
        for w in ("Babylon", "Middle East", "young woman", "young man", "沙发", "想你", "Direction:",
                  "Spoken words", "<Picture 2>", cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE):
            self.assertNotIn(w, p)
        self.assertEqual(ctx.visual, "")
        self.assertEqual(ctx.story, "")
        self.assertFalse(ctx.use_actor)

    def test_fallback_keeps_fyi_only_in_visual_description(self):
        ctx = _m0()
        b = build_h3(ctx)
        self.assertEqual(b.allow_raw, ["镜头慢慢推近，树叶随风摆动"])
        self.assertIn("镜头慢慢推近", field(b.prompt, "detailed_description:"))
        for f in ("subject_definitions:", "summary:", "retention_analysis:", "overall_soundscape:"):
            self.assertFalse(has_cjk(field(b.prompt, f)), f)
        self.assertEqual(validate_h3(b.prompt, ctx, allow_raw=b.allow_raw, fyi_text=b.fyi_text), "")
        self.assertNotEqual(validate_h3(b.prompt, ctx), "")  # 不说明允许就不通过（有中文）

    def test_fyi_caption_and_note_lines_dropped(self):
        ctx = _m0(fyi="注意：别加字\n树叶随风摆动")
        self.assertEqual(ctx.fyi, "树叶随风摆动")

    def test_no_fyi(self):
        ctx = _m0(fyi="")
        b = build_h3(ctx)
        self.assertEqual(b.allow_raw, [])
        self.assertFalse(has_cjk(b.prompt))
        self.assertEqual(validate_h3(b.prompt, ctx), "")


class M1PromptTest(unittest.TestCase):
    def test_no_actor_no_people_no_place(self):
        ctx = _m1(region="中东", era="古巴比伦")
        en = {"visual": "the two sit side by side on the living-room sofa",
              "story": "warm lamplight slowly fills the quiet room"}  # t429u: 没勾人物：故事只译成气氛
        b = build_h3(ctx, en)
        p = b.prompt
        self.assertEqual(validate_h3(p, ctx, allow_raw=b.allow_raw), "")
        self.assertIn(cp.VIDEO_NO_NEW_PEOPLE_PREFIX, p)
        self.assertNotIn(cp.VIDEO_FAITHFUL_PREFIX, p)
        self.assertNotIn("Babylon", p)
        self.assertNotIn("young woman", p)
        self.assertIn(blocks.STORY_THROUGH_SCENE, p)  # t429u
        self.assertIn("Throughout the clip, warm lamplight slowly fills the quiet room.", p)
        self.assertNotIn("acts out", p)
        self.assertFalse(has_cjk(p))
        self.assertEqual(speech_word(_body(p)), "")

    def test_actor_cast_and_place(self):
        ctx = _m1(actor=True, region="中东", era="古巴比伦")
        p = build_h3(ctx, {"visual": "they sit on the sofa", "story": "she greets him warmly"}).prompt
        self.assertIn("the two people already in <Picture 1> (a young woman and a young man)", p)
        self.assertIn("The setting is ancient Babylon", p)
        self.assertNotIn(cp.VIDEO_NO_NEW_PEOPLE_PREFIX, p)
        self.assertEqual(validate_h3(p, ctx), "")

    def test_story_is_text_of_speaking_not_spoken(self):
        ctx = _m1()
        self.assertIn("想你了", ctx.story)
        b = build_h3(ctx)  # t429u: 没勾人物又没翻译：讲话原文不放进去（里面的人会被画出来），只用场景讲
        self.assertNotIn("想你了", b.prompt)
        self.assertIn(blocks.STORY_THROUGH_SCENE, b.prompt)
        self.assertEqual(validate_h3(b.prompt, ctx, allow_raw=b.allow_raw), "")
        ctx = _m1(actor=True)  # 勾了人物：原文只在画面描述里
        b = build_h3(ctx)
        self.assertIn("想你了", field(b.prompt, "detailed_description:"))
        self.assertNotIn("想你了", field(b.prompt, "overall_soundscape:"))
        self.assertEqual(validate_h3(b.prompt, ctx, allow_raw=b.allow_raw), "")

    def test_nothing_ticked_still_moves(self):
        ctx = _m1(story=False, visual=False)
        p = build_h3(ctx).prompt
        self.assertIn("comes gently alive in place", p)  # t429u
        self.assertEqual(validate_h3(p, ctx), "")

    def test_caption_modes(self):
        for text in ("keep", "keywords", "erase", "express"):
            with self.subTest(text=text):
                ctx = _m1(text=text, story=False, visual=False)
                p = build_h3(ctx).prompt
                self.assertEqual(validate_h3(p, ctx), "")
                self.assertEqual(p.count(cp.VIDEO_IMAGE_KEYWORDS_PREFIX), 1 if text in ("keep", "keywords") else 0)
                self.assertFalse(has_cjk(p))


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.ctx = _m1(story=False)
        self.b = build_h3(self.ctx, {"visual": "they sit on the sofa"})

    def test_ok(self):
        self.assertEqual(validate_h3(self.b.prompt, self.ctx), "")

    def test_rejects_speech_words(self):
        for w in ("She speaks softly.", "a voice calls", "they talk", "narrator", "lip-sync", "He says hello.",
                  "subtitles appear", "she sings"):
            with self.subTest(w=w):
                bad = self.b.prompt.replace("they sit on the sofa", "they sit on the sofa; " + w)
                self.assertNotEqual(validate_h3(bad, self.ctx), "")

    def test_rejects_cjk(self):
        bad = self.b.prompt.replace("they sit on the sofa", "他们坐在沙发上")
        self.assertIn("中文", validate_h3(bad, self.ctx))

    def test_rejects_missing_locked_line(self):
        bad = self.b.prompt.replace(blocks.objects_lock(), "")
        self.assertIn(cp.VIDEO_PROPS_LOCK_PREFIX, validate_h3(bad, self.ctx))
        bad = self.b.prompt.replace(blocks.no_new_people(), "")
        self.assertIn(cp.VIDEO_NO_NEW_PEOPLE_PREFIX, validate_h3(bad, self.ctx))

    def test_rejects_changed_soundscape_and_fyi_in_sound(self):
        bad = self.b.prompt.replace(blocks.SOUNDSCAPE, "Birds sing.")
        self.assertNotEqual(validate_h3(bad, self.ctx), "")
        ctx = _m1(story=False, fyi="x")
        b = build_h3(ctx, {"visual": "they sit", "fyi": "leaves sway gently"})
        self.assertEqual(validate_h3(b.prompt, ctx, fyi_text=b.fyi_text), "")
        moved = b.prompt.replace("\n" + b.fyi_text, "").replace(blocks.MUSIC, blocks.MUSIC + " " + b.fyi_text)
        self.assertNotEqual(validate_h3(moved, ctx, fyi_text=b.fyi_text), "")


class StrataRefineTest(unittest.TestCase):
    def test_translates_slots(self):
        ctx = _m1(fyi="树叶随风摆动")
        call = _fake({"visual": "the two sit side by side on the sofa",
                      "story": "warm lamplight slowly fills the quiet room",
                      "fyi": "leaves sway gently in the breeze"})
        out, why = refine_h3(ctx, call=call)
        self.assertIn("Strata", why)
        self.assertFalse(has_cjk(out))
        self.assertIn("Throughout the clip, leaves sway gently in the breeze.", field(out, "detailed_description:"))
        self.assertEqual(validate_h3(out, ctx), "")
        system, user = call.calls[0]
        self.assertEqual(set(json.loads(user)), {"visual", "story", "fyi"})
        self.assertIn("Keep every subject to what the start picture already shows", system)
        # 发送前的核对（对话框 _poll）不改它
        self.assertEqual(cp.restore_video_locked_rules(build_h3(ctx).prompt, out), out)

    def test_fallbacks(self):
        ctx = _m1(fyi="树叶随风摆动")
        plain = build_h3(ctx).prompt
        for ans in (RuntimeError("down"), "not json", {"visual": "they sit"},
                    {"visual": "she says hi", "story": "x", "fyi": "y"},
                    {"visual": "他们坐着", "story": "x", "fyi": "y"},
                    {"visual": "a crowd of people walks in", "story": "she smiles", "fyi": "leaves sway"},
                    {"visual": "they sit", "story": "she smiles", "fyi": "in ancient Babylon leaves sway"}):
            with self.subTest(ans=str(ans)[:40]):
                out, why = refine_h3(ctx, call=_fake(ans))
                self.assertEqual(out, plain)
                self.assertIn("没精简的档位提示词", why)

    def test_generic_people_ok_without_actor(self):
        from prompt_profiles.strata import added_people_or_place

        self.assertEqual(added_people_or_place("两人坐在沙发上", "the two people sit on the sofa"), "")
        self.assertEqual(added_people_or_place("两人坐着", "a crowd gathers"), "crowd")
        self.assertEqual(added_people_or_place("两人坐着", "in medieval light"), "medieval")
        self.assertEqual(added_people_or_place("古代的客厅", "an ancient living room"), "")

    def test_actor_may_name_place(self):
        ctx = _m1(actor=True, story=False, visual=False, fyi="远处有人走过")
        out, _why = refine_h3(ctx, call=_fake({"fyi": "a figure crosses far behind them"}))
        self.assertIn("a figure crosses far behind them", out)
        self.assertNotIn("Keep every subject", system_prompt(ctx))

    def test_no_slots_no_call(self):
        ctx = _m0(fyi="")
        call = _fake(RuntimeError("must not be called"))
        out, _why = refine_h3(ctx, call=call)
        self.assertEqual(out, build_h3(ctx).prompt)
        self.assertEqual(call.calls, [])

    def test_m0_system_prompt(self):
        s = system_prompt(_m0())
        self.assertIn("faithful animation", s)
        self.assertIn("no region, country, era or period", s)


class SendHooksTest(unittest.TestCase):
    def test_send_time_hooks_keep_profile_prompt(self):
        p = build_h3(_m1(fyi="树叶随风摆动")).prompt
        q = cp.ensure_video_no_subtitle_first_line(p)
        q = cp.prepare_h3_spoken_text(q)
        q = cp.ensure_portrait_reference_rule(q)
        q = cp.ensure_h3_monologue_no_lipsync_rules(q, has_monologue=False)
        q = cp.strip_repeated_no_subtitle_rules(q)
        self.assertEqual(q, p)
        self.assertNotIn(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE, q)
        self.assertEqual(cp.restore_video_locked_rules(p, p), p)

    def test_other_prompts_still_get_first_line(self):
        self.assertTrue(cp.ensure_video_no_subtitle_first_line("x").startswith(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE))
        self.assertFalse(cp.is_profile_prompt("integrated_multimodal_description: x"))


class DialogWiringTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(_ROOT, "gui", "video_prompt_dialog.py"), encoding="utf-8") as f:
            self.src = f.read()

    def test_profile_selected_and_used(self):
        self.assertIn("_pp_select(is_minimax=_cfg_mm.is_minimax(backend), fyi_only=fyi_only, story_on=story_on", self.src)
        self.assertIn("and _use_actor and not _pp_profile:", self.src)
        self.assertIn("prompt = _pp_build(_pp_ctx)", self.src)
        self.assertIn('box["v"] = refine_h3(_pp_ctx)', self.src)
        self.assertLess(self.src.find("_pp_select("), self.src.find("portrait_refs = []"))
        self.assertLess(self.src.find("prompt = _pp_build(_pp_ctx)"), self.src.find("if missing and quiet:"))
        self.assertLess(self.src.find('box["v"] = (base, "没用 Strata 精简")'), self.src.find('box["v"] = refine_h3(_pp_ctx)'))

    def test_dialog_lf(self):
        with open(os.path.join(_ROOT, "gui", "video_prompt_dialog.py"), "rb") as f:
            self.assertNotIn(b"\r\n", f.read())


if __name__ == "__main__":
    unittest.main()
