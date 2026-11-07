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
        self.assertIn("off-mouth delivery", raw.lower())
        self.assertIn("Lip sync:", h3)
        self.assertIn("no lip sync", h3.lower())
        self.assertIn("On camera:", h3)
        self.assertIn("closed", h3.lower())
        self.assertIn("Speaker map:", h3)
        self.assertNotIn("only that person's mouth moves", h3)

    def test_legacy_chinese_parenthetical_is_not_selftalk(self):
        from utility.speaking_marks import speaking_is_single_inner_monologue, speaking_has_monologue, split_speaking_pair
        from config_prompt import SINGLE_INNER_MONOLOGUE_RULE

        speaking = "<2>（自言自语）我怎么又这样。"
        self.assertFalse(speaking_is_single_inner_monologue(speaking))
        self.assertFalse(speaking_has_monologue(speaking))
        self.assertIsNone(split_speaking_pair(speaking))
        raw = self._flow(speaking)
        h3 = self._h3(speaking)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, raw)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, h3)
        self.assertNotIn("legacy", raw.lower())
        self.assertNotIn("legacy", h3.lower())

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
        self.assertIn("off-mouth delivery", inner.lower())
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
        self.assertIn("绝不能念出来", speak)
        self.assertIn("讲话」原文", act)
        self.assertIn("不念视觉描述", act)
        self.assertIn("嘴巴不动", act)

    def test_spoken_words_only_from_speaking_not_visual(self):
        from config_prompt import (
            SPOKEN_SOURCE_RULE, SILENT_VISUAL_PREFIX, SPOKEN_TRANSCRIPT_BEGIN,
            restore_spoken_transcript, ensure_spoken_transcript_block,
            build_video_flow_prompt, SINGLE_INNER_MONOLOGUE_RULE, H3_LIP_SYNC_LINE,
        )
        from utility.speaking_marks import scene_speaking_source

        visual = '他低声说“窗外的夜色真安静”，然后坐回沙发。'
        male_actor = "人物1: man/youth/chinese/阿明\n人物2: woman/youth/chinese/小美"
        s1 = "<1s> 我想了很久。还是算了。\n也许明天会不一样。"
        raw1 = self._flow(s1, extra={"visual": visual, "actor": male_actor, "story_content": "这段不该被念。"})
        self.assertIn(SPOKEN_SOURCE_RULE, raw1)
        self.assertIn(SPOKEN_TRANSCRIPT_BEGIN, raw1)
        self.assertIn("我想了很久。还是算了。", raw1)
        self.assertIn("也许明天会不一样。", raw1)
        self.assertIn("silent picture direction", raw1.lower())
        self.assertIn("MALE", raw1.upper())
        self.assertIn("阿明", raw1)
        self.assertNotIn("这段不该被念。", raw1.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0])
        quoted = "窗外的夜色真安静"
        transcript = raw1.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0]
        self.assertNotIn(quoted, transcript)
        self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, raw1)
        self.assertNotIn("inner voice-over", raw1.lower())

        s2 = "<1> 你回来了。<2> 我只是出去走走。"
        raw2 = self._flow(s2, extra={"visual": visual, "actor": male_actor, "story_content": "邻场独白不该出现。"})
        self.assertIn(SPOKEN_SOURCE_RULE, raw2)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, raw2)
        self.assertIn("你回来了。", raw2)
        self.assertIn("我只是出去走走。", raw2)
        self.assertNotIn("我想了很久。还是算了。", raw2)
        self.assertIn("lip-synced to that person", raw2)
        t2 = raw2.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0]
        self.assertNotIn(quoted, t2)
        self.assertNotIn("邻场独白不该出现。", t2)

        h3_2 = self._h3(s2, extra={"visual": visual, "actor": male_actor})
        self.assertIn(H3_LIP_SYNC_LINE, h3_2)
        self.assertIn(SILENT_VISUAL_PREFIX, h3_2)
        self.assertNotIn(SINGLE_INNER_MONOLOGUE_RULE, h3_2)

        empty = self._flow("", extra={"visual": visual, "speaking": "", "story_content": "<1s> 不该当讲话。"})
        self.assertTrue("speak nothing" in empty.lower() or "nobody speaks" in empty.lower())
        et = empty.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0]
        self.assertNotIn(quoted, et)
        self.assertNotIn("<1s> 不该当讲话。", et)
        self.assertEqual(scene_speaking_source({"speaking": "", "story_content": "<1s> 不该当讲话。"}), "")
        self.assertIn(
            "<1s> 不该当讲话。",
            scene_speaking_source({"speaking": "", "story_content": "<1s> 不该当讲话。"}, allow_story_content=True),
        )

        original = ensure_spoken_transcript_block("raw visual: " + visual, [{"speaking": s2, "actor": male_actor, "visual": visual}])
        malicious = (
            "Narrator: " + visual + " The camera explains the living room. "
            "Then they talk about something else entirely."
        )
        restored = restore_spoken_transcript(original, malicious)
        self.assertIn(SPOKEN_TRANSCRIPT_BEGIN, restored)
        self.assertIn("你回来了。", restored)
        self.assertIn("我只是出去走走。", restored)
        block = restored.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0]
        self.assertNotIn("Then they talk about something else entirely.", block)

    def test_guard_swaps_do_not_invent_picture_narration(self):
        from config_prompt import (
            SPEAKER_MARK_IDENTITY_RULE, SINGLE_INNER_MONOLOGUE_RULE,
            H3_LIP_SYNC_LINE, H3_INNER_VO_NO_LIPSYNC_LINE,
            ensure_speaker_semantics_rules, SPOKEN_SOURCE_RULE,
        )
        polished = (
            "Some rewritten clip. " + H3_LIP_SYNC_LINE + " "
            "On camera: 阿明 speaks on camera, visibly moving their lips with every word "
            "(spoken dialogue, not a voice-over or inner monologue). "
            "No narrator, no voice-over. their lips moving in sync with the voice track."
        )
        guarded = ensure_speaker_semantics_rules(
            polished, has_speaking=True, has_monologue=True, single_inner=True,
        )
        self.assertIn(SPOKEN_SOURCE_RULE, guarded)
        self.assertIn(SPEAKER_MARK_IDENTITY_RULE, guarded)
        self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, guarded)
        self.assertIn(H3_INNER_VO_NO_LIPSYNC_LINE, guarded)
        self.assertNotIn(H3_LIP_SYNC_LINE, guarded)
        self.assertNotIn("not a voice-over or inner monologue", guarded)


    def test_generated_prompts_have_no_legacy_syntax(self):
        from config_prompt import (
            SPEAKER_MARK_IDENTITY_RULE, SINGLE_INNER_MONOLOGUE_RULE,
            H3_MONOLOGUE_NO_LIPSYNC_RULE, SPOKEN_TRANSCRIPT_BEGIN,
            ensure_speaker_semantics_rules, ensure_h3_monologue_no_lipsync_rules,
            restore_spoken_transcript, ensure_spoken_transcript_block,
        )
        from utility.prompt_polish import restore_h3_locked_lines, _SYS_GENERAL, _SYS_H3

        speaking = "<1s> 才寫了三行，怎麼就像跑完一場馬拉松。"
        raw = self._flow(speaking)
        h3 = self._h3(speaking)
        mm = self._mm(speaking)
        for text in (raw, h3, mm):
            self.assertNotIn("legacy", text.lower())
            self.assertNotIn("（自言自语）", text)
            self.assertNotIn("（自言自語）", text)
            self.assertNotIn("[自言自语]", text)
            self.assertNotIn("Self-talk (自言自语)", text)
            self.assertNotIn("count parser turns", text.lower())
        for rule in (SPEAKER_MARK_IDENTITY_RULE, SINGLE_INNER_MONOLOGUE_RULE, H3_MONOLOGUE_NO_LIPSYNC_RULE):
            self.assertNotIn("legacy", rule.lower())
            self.assertNotIn("（自言自语）", rule)
            self.assertNotIn("（自言自語）", rule)
        for sys_txt in (_SYS_GENERAL, _SYS_H3):
            self.assertNotIn("legacy", sys_txt.lower())
            self.assertNotIn("（自言自语）", sys_txt)
            self.assertNotIn("Self-talk (自言自语)", sys_txt)

        transcript = raw.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0]
        self.assertIn("才寫了三行，怎麼就像跑完一場馬拉松。", transcript)
        self.assertNotIn("[自言自语]", transcript)
        self.assertNotIn("（自言自语）", transcript)

        h3_t = h3.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0]
        self.assertIn("才寫了三行，怎麼就像跑完一場馬拉松。", h3_t)
        self.assertNotIn("[自言自语]", h3_t)

        guarded = ensure_speaker_semantics_rules(
            "Some rewritten clip.", has_speaking=True, has_monologue=True, single_inner=True,
        )
        guarded = ensure_h3_monologue_no_lipsync_rules(guarded, has_monologue=True)
        self.assertNotIn("legacy", guarded.lower())
        self.assertNotIn("（自言自语）", guarded)
        self.assertNotIn("（自言自語）", guarded)
        self.assertNotIn("[自言自语]", guarded)
        self.assertIn(H3_MONOLOGUE_NO_LIPSYNC_RULE, guarded)
        self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, guarded)

        original = ensure_spoken_transcript_block(h3, [_scene(speaking)])
        malicious = (
            "Strata rewrite without locked self-talk rules. "
            "Speaker marks: <N> and <Ns> (and legacy <N>（自言自语） / <N>（自言自語）) refer to people. "
            "BEGIN_SPOKEN_TRANSCRIPT\nsomeone says aloud: WRONG TEXT [自言自语]\nEND_SPOKEN_TRANSCRIPT"
        )
        restored = restore_h3_locked_lines(original, malicious)
        restored = restore_spoken_transcript(original, restored)
        self.assertNotIn("legacy", restored.lower())
        self.assertNotIn("[自言自语]", restored.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0])
        self.assertIn(SPEAKER_MARK_IDENTITY_RULE, restored)
        self.assertIn(H3_MONOLOGUE_NO_LIPSYNC_RULE, restored)
        self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, restored)
        block = restored.split(SPOKEN_TRANSCRIPT_BEGIN, 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0]
        self.assertIn("才寫了三行，怎麼就像跑完一場馬拉松。", block)
        self.assertNotIn("or legacy", restored.lower())

    def test_two_cast_single_inner_only_marked_actor_speaks(self):
        from config_prompt import (
            AUDIBLE_FROM_SPEAKING_RULE, SINGLE_INNER_ONE_VOICE_RULE, SPEAK_LINE_ONCE_RULE,
            SINGLE_INNER_MONOLOGUE_RULE, H3_ALTERNATING_SPEAKERS_CLAUSE,
            H3_SINGLE_INNER_SILENT_CAST_CLAUSE, H3_LIP_SYNC_LINE, H3_MIXED_LIP_SYNC_LINE,
            ensure_speaker_semantics_rules, SPEAKER_MARK_IDENTITY_RULE,
        )

        two = "人物1: man/mature/chinese/阿哲\n人物2: woman/mature/chinese/小雨"
        line = "才寫了三行，怎麼就像跑完一場馬拉松。"
        s1 = f"<1s> {line}"
        raw1 = self._flow(s1, actor=two)
        h31 = self._h3(s1, actor=two)
        mm1 = self._mm(s1)
        for text in (raw1, h31, mm1):
            self.assertIn(SINGLE_INNER_MONOLOGUE_RULE, text)
            self.assertIn(AUDIBLE_FROM_SPEAKING_RULE, text)
            self.assertIn(SINGLE_INNER_ONE_VOICE_RULE, text)
            self.assertIn(SPEAK_LINE_ONCE_RULE, text)
            self.assertIn(SPEAKER_MARK_IDENTITY_RULE, text)
            self.assertNotIn(H3_ALTERNATING_SPEAKERS_CLAUSE, text)
            self.assertNotIn("legacy", text.lower())
        self.assertIn(H3_SINGLE_INNER_SILENT_CAST_CLAUSE, h31)
        self.assertIn("exactly 1 audible voice (S1)", h31)
        self.assertIn("(S2) has no speaking turn", h31)
        self.assertIn("小雨", h31)
        self.assertIn("阿哲", h31)
        d_at = h31.find("<d>")
        self.assertGreater(d_at, 0)
        sent_start = max(h31.rfind(".", 0, d_at), h31.rfind("!", 0, d_at)) + 1
        pre_d = h31[sent_start:d_at]
        self.assertIn("阿哲", pre_d)
        self.assertNotIn("小雨", pre_d)
        after_d = h31[d_at:]
        self.assertIn("小雨", after_d.split("overall_soundscape", 1)[0])
        self.assertIn("never speaks, repeats, or echoes this line", after_d)
        self.assertIn("MALE", raw1.upper())
        self.assertIn(line, raw1)
        self.assertEqual(raw1.split("BEGIN_SPOKEN_TRANSCRIPT", 1)[1].split("END_SPOKEN_TRANSCRIPT", 1)[0].count(line), 1)

        s2 = f"<2s> {line}"
        raw2 = self._flow(s2, actor=two)
        h32 = self._h3(s2, actor=two)
        for text in (raw2, h32):
            self.assertIn(SINGLE_INNER_ONE_VOICE_RULE, text)
            self.assertIn(AUDIBLE_FROM_SPEAKING_RULE, text)
            self.assertNotIn(H3_ALTERNATING_SPEAKERS_CLAUSE, text)
        self.assertIn("exactly 1 audible voice (S2)", h32)
        self.assertIn("(S1) has no speaking turn", h32)
        d_at2 = h32.find("<d>")
        sent_start2 = max(h32.rfind(".", 0, d_at2), h32.rfind("!", 0, d_at2)) + 1
        pre2 = h32[sent_start2:d_at2]
        self.assertIn("小雨", pre2)
        self.assertNotIn("阿哲", pre2)
        self.assertIn("FEMALE", raw2.upper())

        twelve_actor = "\n".join(
            [f"人物1: man/mature/chinese/阿哲", "人物2: woman/mature/chinese/小雨"]
            + [f"人物{i}: woman/youth/chinese/配角{i}" for i in range(3, 13)]
        )
        s12 = "<12s> 我想了很久。还是算了。"
        h312 = self._h3(s12, actor=twelve_actor)
        raw12 = self._flow(s12, actor=twelve_actor)
        self.assertIn("<12>=<12s>", raw12)
        self.assertIn("exactly 1 audible voice (S12)", h312)
        self.assertIn(SINGLE_INNER_ONE_VOICE_RULE, h312)

        normal = "<1> 你好。<2> 今天怎么样？"
        raw_n = self._flow(normal, actor=two)
        h3_n = self._h3(normal, actor=two)
        self.assertNotIn(SINGLE_INNER_ONE_VOICE_RULE, raw_n)
        self.assertNotIn(SINGLE_INNER_ONE_VOICE_RULE, h3_n)
        self.assertIn(H3_ALTERNATING_SPEAKERS_CLAUSE, h3_n)
        self.assertIn(AUDIBLE_FROM_SPEAKING_RULE, raw_n)
        self.assertIn("lip-synced to that person", raw_n)
        self.assertNotIn("(S2) has no speaking turn", h3_n)

        mixed = "<1s> 我有点累。<2> 那你先休息。"
        raw_m = self._flow(mixed, actor=two)
        h3_m = self._h3(mixed, actor=two)
        self.assertNotIn(SINGLE_INNER_ONE_VOICE_RULE, raw_m)
        self.assertNotIn(SINGLE_INNER_ONE_VOICE_RULE, h3_m)
        self.assertIn(H3_MIXED_LIP_SYNC_LINE, h3_m)
        self.assertIn(H3_ALTERNATING_SPEAKERS_CLAUSE, h3_m)
        self.assertNotIn(H3_LIP_SYNC_LINE, h3_m)

        polished = (
            "Strata rewrite. " + H3_ALTERNATING_SPEAKERS_CLAUSE + " "
            "First the woman says the line, then the man repeats it as an echo. "
            + H3_LIP_SYNC_LINE
        )
        guarded = ensure_speaker_semantics_rules(
            polished, has_speaking=True, has_monologue=True, single_inner=True,
        )
        self.assertNotIn(H3_ALTERNATING_SPEAKERS_CLAUSE, guarded)
        self.assertIn(H3_SINGLE_INNER_SILENT_CAST_CLAUSE, guarded)
        self.assertIn(AUDIBLE_FROM_SPEAKING_RULE, guarded)
        self.assertIn(SINGLE_INNER_ONE_VOICE_RULE, guarded)
        self.assertIn(SPEAK_LINE_ONCE_RULE, guarded)
        self.assertNotIn(H3_LIP_SYNC_LINE, guarded)


if __name__ == "__main__":
    unittest.main()
