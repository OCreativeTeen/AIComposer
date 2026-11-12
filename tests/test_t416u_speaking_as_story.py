"""t416u: 生场视频「讲话当故事内容」：讲话不说出来、用画面演；没人说话，只有音效、没有音乐。
所有后端的提示词（Grok / Gemini 一般格式、过渡、MiniMax H3）、Strata 精简（锁定句换回 + validate）、对话框接线。"""
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
from utility import prompt_polish as pp  # noqa: E402

SPEAK = "<1> 你今天怎麼來了？ <2> 想你了。"
STYLE = "三维卡通 (Pixar-Art-Cartoon)"
RULES = (cp.SPEAKING_STORY_SILENT_RULE, cp.SPEAKING_STORY_SHOW_RULE, cp.SPEAKING_STORY_SOUND_RULE)


def _flow(sc=None, **kw):
    args = dict(frames="one", background="none", evolve="keep", visual_style=STYLE,
                scene_content=[sc or _scene(SPEAK)], language="zh", narrative="story", text="keywords",
                use_visual=True, use_speaking=False, use_actor=True, story_style="story_speak",
                speaking_as_story=True)
    args.update(kw)
    return cp.build_video_flow_prompt(**args)


def _h3(sc=None, **kw):
    args = dict(language="zh", audio_mode="talk", text="keywords", style=STYLE, region="中国", era="现代",
                use_visual=True, use_speaking=False, speaking_as_story=True)
    args.update(kw)
    return cp.build_h3_prompt([sc or _scene(SPEAK)], **args)


class HelpersTest(unittest.TestCase):
    def test_story_text_strips_marks_and_scene_copy_is_silent(self):
        sc = _scene(SPEAK, extra={"voiceover": "那天下着雨。", "story_content": "x"})
        text = cp.speaking_story_text(sc)
        self.assertIn("你今天怎麼來了", text)
        self.assertIn("想你了", text)
        self.assertIn("那天下着雨", text)
        self.assertNotIn("<1>", text)
        self.assertNotIn("<2>", text)
        copy = cp.speaking_story_scenes([sc, "bad"])
        self.assertEqual(len(copy), 1)
        self.assertEqual((copy[0]["speaking"], copy[0]["voiceover"]), ("", ""))
        self.assertNotIn("story_content", copy[0])
        self.assertEqual(sc["speaking"], SPEAK)  # 原场景不动

    def test_story_content_fallback(self):
        self.assertEqual(cp.speaking_story_text({"speaking": "", "story_content": "他推门进来。"}), "他推门进来。")
        self.assertEqual(cp.speaking_story_text(None), "")


class FlowPromptTest(unittest.TestCase):
    def test_flow_prompt_has_rules_story_section_and_no_speech(self):
        p = _flow()
        for r in RULES:
            self.assertEqual(p.count(r), 1, r[:30])
        self.assertIn("Story_Content (Story content, shown in the picture, never spoken):", p)
        self.assertIn("你今天怎麼來了？ 想你了。", p)
        self.assertLess(p.index("Story_Content ("), p.index("Story_Scene_Content:"))
        self.assertNotIn("Sound: natural sound of the place only", p)
        self.assertNotIn("Spoken language:", p)
        self.assertNotIn("says aloud", p)
        self.assertNotIn("<1>", p)
        self.assertIn("nobody speaks", p)
        # existing locks still there
        self.assertIn(cp.VIDEO_ONE_SHOT_PREFIX, p)
        self.assertIn(cp.VIDEO_PROPS_LOCK_PREFIX, p)
        self.assertIn(cp.VIDEO_IMAGE_KEYWORDS_PREFIX, p)

    def test_story_only_and_empty(self):
        p = _flow(use_visual=False, use_actor=False)
        self.assertIn(cp.SPEAKING_STORY_SHOW_RULE, p)
        with self.assertRaises(ValueError):
            _flow(sc=_scene(""), use_visual=False, use_actor=False)
        q = _flow(sc=_scene(""))  # 没有讲话：只有「没人说话」+「只有音效」
        self.assertIn(cp.SPEAKING_STORY_SILENT_RULE, q)
        self.assertIn(cp.SPEAKING_STORY_SOUND_RULE, q)
        self.assertNotIn(cp.SPEAKING_STORY_SHOW_RULE, q)

    def test_off_is_unchanged(self):
        a = _flow(use_speaking=True, speaking_as_story=False)
        for r in RULES:
            self.assertNotIn(r, a)
        self.assertIn("Sound: natural sound of the place only", a)

    def test_transition(self):
        p = cp.build_transition_video_prompt(
            visual_style=STYLE, scene_content=[_scene(SPEAK)], transition={"时空": "黄昏", "对白": "对话"},
            language="zh", use_visual=True, use_speaking=False, use_actor=True, speaking_as_story=True)
        for r in RULES:
            self.assertEqual(p.count(r), 1)
        self.assertIn("想你了", p)
        self.assertNotIn("Spoken language:", p)


class H3PromptTest(unittest.TestCase):
    def test_h3_silent_story_sfx_only(self):
        p = _h3()
        self.assertIn(cp.SPEAKING_STORY_SILENT_RULE, p)
        self.assertIn(cp.SPEAKING_STORY_SHOW_RULE, p)
        self.assertIn("Story content: 你今天怎麼來了？ 想你了.", p)
        self.assertNotIn("<d>", p)  # audio_mode=talk 也不说话
        self.assertIn("overall_soundscape: " + cp.SPEAKING_STORY_SOUND_RULE, p)
        self.assertIn("non_diegetic_music: N/A", p)
        self.assertIn(cp.VIDEO_ONE_SHOT_PREFIX, p)
        self.assertIn(cp.VIDEO_PROPS_LOCK_PREFIX, p)

    def test_h3_off_still_talks(self):
        p = _h3(use_speaking=True, speaking_as_story=False, audio_mode="none")
        self.assertIn("<d>", p)
        self.assertNotIn(cp.SPEAKING_STORY_SILENT_RULE, p)


class StrataTest(unittest.TestCase):
    def test_restore_rules_and_soundscape(self):
        orig = _h3()
        bad = orig.replace(cp.SPEAKING_STORY_SILENT_RULE, "Two friends meet.") \
                  .replace("overall_soundscape: " + cp.SPEAKING_STORY_SOUND_RULE, "overall_soundscape: soft piano music")
        out = cp.restore_video_locked_rules(orig, bad)
        self.assertEqual(out.count(cp.SPEAKING_STORY_SILENT_RULE), 1)
        self.assertIn("overall_soundscape: " + cp.SPEAKING_STORY_SOUND_RULE, out)
        self.assertNotIn("piano music", out)
        flow = _flow()
        out2 = cp.restore_video_locked_rules(flow, flow.replace(cp.SPEAKING_STORY_SOUND_RULE, "Sound: gentle music."))
        self.assertEqual(out2.count(cp.SPEAKING_STORY_SOUND_RULE), 1)

    def test_non_story_prompt_untouched(self):
        orig = _flow(use_speaking=True, speaking_as_story=False)
        self.assertEqual(cp.restore_speaking_story_rules(orig, "abc"), "abc")
        self.assertEqual(cp.speaking_story_added_words(orig, orig + " She says hello with music."), "")

    def test_added_words(self):
        orig = _flow()
        self.assertEqual(cp.speaking_story_added_words(orig, orig), "")
        self.assertEqual(cp.speaking_story_added_words(orig, orig + "\nSoft background music plays."), "music")
        self.assertEqual(cp.speaking_story_added_words(orig, orig + "\nShe says hello."), "says")
        self.assertEqual(cp.speaking_story_added_words(orig, orig + "\nThere is no music and nobody talks."), "")

    def test_validate(self):
        orig = _flow()
        self.assertIn("No speech", pp.validate(orig, orig.replace(cp.SPEAKING_STORY_SILENT_RULE, ""), "grok"))
        self.assertIn("讲话 / 音乐", pp.validate(orig, orig[: len(orig) // 2] + "\n" + cp.SPEAKING_STORY_SILENT_RULE
                                           + "\n" + cp.SPEAKING_STORY_SOUND_RULE + "\nA song plays with music.", "grok"))

    def test_system_prompts_mention_rule(self):
        self.assertIn("No speech (t416u)", pp._SYS_GENERAL)
        self.assertIn("No speech (t416u)", pp._SYS_H3)


class DialogWiringTest(unittest.TestCase):
    def setUp(self):
        self.src = Path(ROOT, "gui/video_prompt_dialog.py").read_text(encoding="utf-8")

    def test_saved_and_exclusive(self):
        s = self.src
        self.assertIn("saved_story = bool(saved_choice.get(config_prompt.SPEAKING_STORY_KEY))", s)
        self.assertIn("if saved_story:\n        saved_speaking = False", s)
        self.assertIn('speaking_var.trace_add("write", _exclusive(speaking_var, story_var))', s)
        self.assertIn('story_var.trace_add("write", _exclusive(story_var, speaking_var))', s)
        self.assertIn("config_prompt.SPEAKING_STORY_KEY: bool(story_var.get()),", s)
        self.assertIn("story_var=story_var", s)
        self.assertEqual(cp.SPEAKING_STORY_KEY, "speaking_story")

    def test_exclusive_logic(self):
        ns = {"tk": type("tk", (), {"TclError": Exception})}
        body = self.src.split("    def _exclusive(on_var, off_var):", 1)[1].split("\n\n", 1)[0]
        exec("def _exclusive(on_var, off_var):" + body, ns)

        class V:
            def __init__(self, v):
                self.v = v

            def get(self):
                return self.v

            def set(self, v):
                self.v = v

        sp, st = V(True), V(True)
        ns["_exclusive"](st, sp)()
        self.assertEqual((sp.v, st.v), (False, True))

    def test_go_path(self):
        go = self.src.split("    def on_go(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("use_sp = bool(speaking_var.get()) and not story_on", go)
        self.assertIn("speaking_as_story=story_on,", go)
        self.assertEqual(go.count("speaking_as_story=story_on"), 2)  # flow/transition field_kw + H3
        self.assertIn('_amode = "none"', go)
        self.assertIn("_guard_scenes = config_prompt.speaking_story_scenes(scenes) if story_on else scenes", go)
        self.assertIn("video_closing_block(_guard_scenes", go)
        self.assertIn("_speech_speed = 1.0", go)
        self.assertNotIn("use_speaking=bool(speaking_var.get())", go)

    def test_audio_radios_disabled(self):
        sb = self.src.split("    def _sync_backend(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("mm and _has_audio and not _story", sb)
        self.assertIn('story_var.trace_add("write", _sync_backend)', self.src)

    def test_field_box_has_story_option(self):
        sp = Path(ROOT, "gui/slide_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn('ttk.Checkbutton(options, text="讲话当故事内容", variable=story_var)', sp)


if __name__ == "__main__":
    unittest.main()
