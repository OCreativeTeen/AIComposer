"""Offline tests for t283u video speaker identity and inner-monologue prompt rules.

Stubs ``project_manager`` and ``config`` before importing ``config_prompt`` so
nothing reads ``.env`` or calls a live LLM.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _install_stubs() -> None:
    pm = sys.modules.get("project_manager")
    if pm is None:
        pm = types.ModuleType("project_manager")
        sys.modules["project_manager"] = pm
    if True:

        def actor_text_for_generation(text):
            return text or ""

        def active_actor_entries(text):
            rows = []
            for i, line in enumerate(str(text or "").splitlines()):
                line = line.strip()
                if not line:
                    continue
                if ":" in line:
                    label, body = line.split(":", 1)
                else:
                    label, body = f"人物{i + 1}", line
                rows.append({"label": label.strip(), "body": body.strip(), "role": "person"})
            return rows

        def split_actor_motion(body):
            return (body or "").strip(), ""

        def scene_is_story_act(scene):
            return (
                isinstance(scene, dict)
                and bool(str(scene.get("story_content") or "").strip())
                and not str(scene.get("speaking") or "").strip()
            )

        pm.actor_text_for_generation = actor_text_for_generation
        pm.active_actor_entries = active_actor_entries
        pm.split_actor_motion = split_actor_motion
        pm.scene_is_story_act = scene_is_story_act
        pm._person_body = lambda raw: (raw or "").strip()
        pm.normalize_scene_content_item_for_workflow = lambda out: out
        pm.actor_is_absent = lambda body: False
        pm._ACTOR_AGE = {
            "kids": "kids", "youth": "youth", "teenager": "teenager",
            "mature": "mature", "senior": "senior",
        }
        pm.PROJECT_CONFIG = {}
        sys.modules["project_manager"] = pm

    if "config" not in sys.modules:
        cfg = types.ModuleType("config")
        cfg.audio_language_label = lambda language: "Chinese" if language else ""
        sys.modules["config"] = cfg


_install_stubs()


def _scene(speaking, *, extra=None):
    sc = {
        "id": 1,
        "visual": "两人坐在客厅沙发上。",
        "speaking": speaking,
        "actor": "人物1: woman/youth/chinese/小美\n人物2: man/youth/chinese/阿明",
    }
    if extra:
        sc.update(extra)
    return sc


class VideoSpeakerSemanticsTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def _flow(self, speaking, story_style="story_speak", **extra):
        from config_prompt import build_video_flow_prompt

        return build_video_flow_prompt(
            frames="one",
            background="none",
            evolve="keep",
            visual_style="realistic",
            scene_content=[_scene(speaking, extra=extra)],
            language="zh",
            narrative="story",
            story_style=story_style,
            use_visual=True,
            use_speaking=True,
            use_actor=True,
        )

    def _h3(self, speaking, **extra):
        from config_prompt import build_h3_prompt

        return build_h3_prompt(
            [_scene(speaking, extra=extra)],
            language="zh",
            audio_mode="none",
            use_visual=True,
            use_speaking=True,
            seconds=6.0,
        )

    def _mm(self, speaking, **kw):
        from config_prompt import build_minimax_video_prompt

        return build_minimax_video_prompt(
            [_scene(speaking)],
            language="zh",
            with_audio=kw.get("with_audio", False),
        )

    def test_identity_same_actor_including_multidigit(self):
        from config_prompt import SPEAKER_MARK_IDENTITY_RULE

        raw = self._flow("<12s> 我想了很久。还是算了。")
        h3 = self._h3("<12s> 我想了很久。还是算了。")
        mm = self._mm("<12s> 我想了很久。还是算了。")
        for text in (raw, h3, mm):
            self.assertIn(SPEAKER_MARK_IDENTITY_RULE, text)
            self.assertIn("<12>=<12s>", text)
            self.assertIn("<1>=<1s>", text)
            self.assertIn("identical actor", text.lower())
            self.assertNotRegex(text.lower(), r"speaker s\b|character s\b|person s\b")

    def test_single_s_turn_multiple_sentences_is_inner_vo(self):
        from config_prompt import SINGLE_INNER_MONOLOGUE_RULE, H3_LIP_SYNC_LINE

        speaking = "<1s> 我想了很久。还是算了。\n也许明天会不一样。"
        raw = self._flow(speaking)
        h3 = self._h3(speaking)
        mm = self._mm(speaking)
        for text in (raw, h3, mm):
            self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, text)
            self.assertIn("mouth closed", text.lower())
            self.assertNotIn("lips moving in sync with the voice track,", text)
            self.assertNotIn(H3_LIP_SYNC_LINE, text)
            self.assertNotIn("not a voice-over or inner monologue", text)
            self.assertNotIn("mouth is already open and forming that syllable", text)
            self.assertNotIn("No narrator, no voice-over.", text)
        self.assertIn("no lip-sync", raw.lower())
        self.assertIn("voice-over", raw.lower())
        self.assertIn("Lip sync:", h3)
        self.assertIn("no lip sync", h3.lower())
        self.assertIn("On camera:", h3)
        self.assertIn("closed", h3.lower())
        self.assertIn("Speaker map:", h3)
        self.assertNotIn("only that person's mouth moves", h3)

    def test_legacy_chinese_parenthetical_is_single_inner(self):
        from utility.speaking_marks import speaking_is_single_inner_monologue
        from config_prompt import SINGLE_INNER_MONOLOGUE_RULE

        speaking = "<2>（自言自语）我怎么又这样。"
        self.assertTrue(speaking_is_single_inner_monologue(speaking))
        raw = self._flow(speaking)
        h3 = self._h3(speaking)
        self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, raw)
        self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, h3)

    def test_normal_story_speak_still_lip_syncs(self):
        from config_prompt import SINGLE_INNER_MONOLOGUE_RULE, H3_LIP_SYNC_LINE, SPEAKER_MARK_IDENTITY_RULE

        speaking = "<1> 你好。<2> 今天怎么样？"
        raw = self._flow(speaking)
        h3 = self._h3(speaking)
        self.assertIn(SPEAKER_MARK_IDENTITY_RULE, raw)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, raw)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, h3)
        self.assertIn("lip-synced to that person", raw)
        self.assertIn(H3_LIP_SYNC_LINE, h3)
        self.assertIn("not a voice-over or inner monologue", h3)
        self.assertIn("only that person's mouth moves", h3)

    def test_mixed_scene_keeps_per_turn_rules(self):
        from config_prompt import SINGLE_INNER_MONOLOGUE_RULE, H3_MONOLOGUE_NO_LIPSYNC_RULE, H3_MIXED_LIP_SYNC_LINE

        speaking = "<1s> 我有点累。<2> 那你先休息。"
        raw = self._flow(speaking)
        h3 = self._h3(speaking)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, raw)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, h3)
        self.assertIn(H3_MONOLOGUE_NO_LIPSYNC_RULE, raw)
        self.assertIn(H3_MONOLOGUE_NO_LIPSYNC_RULE, h3)
        self.assertIn("Interactive", raw)
        self.assertIn(H3_MIXED_LIP_SYNC_LINE, h3)
        self.assertNotIn("every mouth stays closed for the entire scene", h3)

    def test_two_monologue_turns_are_not_single_turn_policy(self):
        from config_prompt import SINGLE_INNER_MONOLOGUE_RULE
        from utility.speaking_marks import speaking_is_single_inner_monologue

        speaking = "<1s> 第一句。<1s> 第二句。"
        self.assertFalse(speaking_is_single_inner_monologue(speaking))
        raw = self._flow(speaking)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, raw)
        self.assertIn("no lip-sync", raw.lower())

    def test_story_act_does_not_ask_for_mouth_speaking(self):
        from config_prompt import SINGLE_INNER_MONOLOGUE_RULE

        silent = self._flow("", story_style="story_act", extra={"story_content": "她走到窗边，看着夜色。", "speaking": ""})
        self.assertIn("nobody speaks", silent.lower())
        self.assertIn("no lip-sync", silent.lower())
        self.assertNotIn("lip-synced to that person", silent)

        inner = self._flow(
            "<1s> 我不能再这样了。明天一定要开口。",
            story_style="story_act",
            extra={"story_content": "她走到窗边，看着夜色。"},
        )
        self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, inner)
        self.assertIn("do not speak on camera", inner.lower())
        self.assertIn("inner voice", inner.lower())
        self.assertNotIn("lip-synced to that person", inner)

    def test_final_guard_restores_identity_and_strips_conflicts(self):
        from config_prompt import (
            SPEAKER_MARK_IDENTITY_RULE,
            SINGLE_INNER_MONOLOGUE_RULE,
            H3_LIP_SYNC_LINE,
            H3_INNER_VO_NO_LIPSYNC_LINE,
            H3_MONOLOGUE_NO_LIPSYNC_RULE,
            ensure_speaker_semantics_rules,
        )
        from utility.prompt_polish import restore_h3_locked_lines

        polished = (
            "Some rewritten clip. " + H3_LIP_SYNC_LINE + " "
            "On camera: 小美 speaks on camera, visibly moving their lips with every word "
            "(spoken dialogue, not a voice-over or inner monologue). "
            "No narrator, no voice-over. their lips moving in sync with the voice track."
        )
        guarded = ensure_speaker_semantics_rules(
            polished, has_speaking=True, has_monologue=True, single_inner=True,
        )
        self.assertIn(SPEAKER_MARK_IDENTITY_RULE, guarded)
        self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, guarded)
        self.assertIn(H3_MONOLOGUE_NO_LIPSYNC_RULE, guarded)
        self.assertIn(H3_INNER_VO_NO_LIPSYNC_LINE, guarded)
        self.assertNotIn(H3_LIP_SYNC_LINE, guarded)
        self.assertNotIn("not a voice-over or inner monologue", guarded)
        self.assertNotIn("visibly moving their lips with every word", guarded)
        self.assertNotIn("No narrator, no voice-over.", guarded)

        original = "Speaker marks: KEEP-ME. Other text. Entire-scene inner monologue: KEEP-TOO."
        dropped = "Strata rewrote everything without the locked lines."
        restored = restore_h3_locked_lines(original, dropped)
        self.assertIn("Speaker marks: KEEP-ME.", restored)
        self.assertIn("Entire-scene inner monologue: KEEP-TOO.", restored)

    def test_parser_turn_count_not_sentences(self):
        from utility.speaking_marks import (
            speaking_is_single_inner_monologue,
            speaking_is_all_inner_monologue,
        )

        wrapped = "<1s> First sentence. Second sentence.\nThird wrapped line."
        self.assertTrue(speaking_is_single_inner_monologue(wrapped))
        self.assertTrue(speaking_is_all_inner_monologue(wrapped))
        self.assertFalse(speaking_is_single_inner_monologue("<1s> a. <2> b"))
        self.assertFalse(speaking_is_single_inner_monologue("<1s> a. <1s> b."))

    def test_user_facing_mode_hints(self):
        from config_prompt import story_style_mode_text

        speak = story_style_mode_text("story_speak", True)
        act = story_style_mode_text("story_act", True)
        self.assertIn("<N> 与 <Ns> 是同一个人", speak)
        self.assertIn("嘴巴闭合", speak)
        self.assertIn("画外心声", act)
        self.assertIn("不对口型", act)


if __name__ == "__main__":
    unittest.main()
