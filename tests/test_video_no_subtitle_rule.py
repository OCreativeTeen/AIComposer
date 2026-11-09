"""t321u offline tests: the no-subtitle rule is stated ONCE at the very top (video prompt and
Strata instructions), defined as the speaking content (not text already in the image); the
keep-image-text option adds a second, separate "Image keywords:" statement; speaking content is
labelled audio-only. Stubs project_manager / config (no .env, no live LLM)."""
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
LEGACY_CRITICAL = cp._LEGACY_VIDEO_NO_SUBTITLE_LINES[0]
LEGACY_H3 = cp._LEGACY_VIDEO_NO_SUBTITLE_LINES[1]


def _h3(text="", speaking=SPEAK, **kw):
    return cp.build_h3_prompt([_scene(speaking)], language="zh", audio_mode="none", text=text, **kw)


def _flow(text="erase", background="none", speaking=SPEAK):
    return cp.build_video_flow_prompt(
        frames="one", background=background, evolve="keep", visual_style="realistic",
        scene_content=[_scene(speaking)], language="zh", narrative="story", text=text,
        use_visual=True, use_speaking=True, use_actor=True, story_style="story_speak",
    )


def _below_first_line(prompt: str) -> str:
    return prompt.split("\n", 1)[1] if "\n" in prompt else ""


class NoSubtitleRuleTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_rule_wording_defines_subtitles_as_speaking_not_image_text(self):
        rule = cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE
        self.assertTrue(rule.startswith("NO SUBTITLES:"))
        self.assertIn("speaking content", rule)
        self.assertIn("never written on screen", rule)
        self.assertIn("not about text already in the image", rule)
        self.assertNotIn("说明文字", rule)  # 这是窗口里「保留 / 关键字作背景」选项的名字
        self.assertEqual(rule.count("字幕"), 1)
        self.assertNotIn("\n", rule)

    def test_h3_states_rule_once_at_top_and_nowhere_else(self):
        for text in ("", "erase", "express", "keywords", "keep"):
            p = _h3(text)
            self.assertEqual(p.split("\n", 1)[0], cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE, text)
            self.assertEqual(cp.count_h3_no_subtitle_rules(p), 1, text)
            self.assertNotIn(LEGACY_H3, p)
            self.assertNotIn("永远不许", p)
            body = _below_first_line(p).lower()
            for word in ("subtitle", "caption", "字幕", "on-screen text"):
                if text in cp.IMAGE_TEXT_KEEP_CHOICES:
                    body_wo = body.replace(cp.VIDEO_IMAGE_KEYWORDS_RULE.lower(), "")
                    self.assertNotIn(word, body_wo, (text, word))
                else:
                    self.assertNotIn(word, body, (text, word))

    def test_keep_text_option_adds_second_statement_only_when_on(self):
        for text in ("keywords", "keep"):
            p = _h3(text)
            self.assertEqual(p.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
            self.assertLess(p.index(cp.VIDEO_IMAGE_KEYWORDS_RULE), p.index("<d>"))
        rule = cp.VIDEO_IMAGE_KEYWORDS_RULE
        for must in ("already drawn in the start picture", "scene's keywords", "in the background exactly as they are",
                     "not the speaking content", "not subtitles", "not captions"):
            self.assertIn(must, rule)
        for text in ("", "erase", "express"):
            p = _h3(text)
            self.assertNotIn("Image keywords", p)
            self.assertNotIn("keyword", p.lower())

    def test_spoken_content_labelled_audio_only(self):
        p = _h3("keywords")
        # t336u: H3 不再附转写块；「Audio only」紧挨在台词前，后面就是「Exact speech」，各一次
        self.assertNotIn(cp.SPOKEN_TRANSCRIPT_BEGIN, p)
        self.assertEqual(p.count(cp.SPOKEN_AUDIO_ONLY_LABEL), 1)
        self.assertLess(p.index(cp.H3_SPOKEN_LEAD), p.index("<d>"))
        block = cp.format_spoken_transcript_block([{"speaking": "<1> 你好。", "actor": "woman/young/chinese/小美"}])
        self.assertEqual(block.splitlines()[1], cp.SPOKEN_AUDIO_ONLY_LABEL)
        self.assertIn("voice track", cp.SPOKEN_AUDIO_ONLY_LABEL)
        flow = _flow("keywords")
        content = flow.split("Story_Scene_Content:\n", 1)[1]
        self.assertTrue(content.startswith("Audio only:"))
        self.assertIn("SINGLE_INNER", "SINGLE_INNER")
        self.assertNotIn("subtitle", cp.SINGLE_INNER_MONOLOGUE_RULE.lower())

    def test_shared_flow_text_lines(self):
        guarded = cp.ensure_video_no_subtitle_first_line(_flow("keywords"))
        self.assertEqual(cp.count_h3_no_subtitle_rules(guarded), 1)
        self.assertEqual(guarded.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
        # 「保留 + 背景文字」不再从讲话里取字
        art = _flow("keep", background="art_text")
        self.assertIn(cp.VIDEO_IMAGE_KEYWORDS_RULE, art)
        self.assertNotIn("taken from the spoken content", art)
        for text in ("erase", "express"):
            p = _flow(text)
            self.assertNotIn("Image keywords", p)
            low = _below_first_line(cp.ensure_video_no_subtitle_first_line(p)).lower()
            self.assertNotIn("subtitle", low)
            self.assertNotIn("caption area", low)
        self.assertEqual(cp.VIDEO_NO_CAPTION_RULE, "Clean film image: only the scene fills the frame.")
        guard = cp.video_guard_block([_scene(SPEAK)])
        self.assertEqual(guard.count("Clean film image"), 1)
        self.assertNotIn("Clean film image", cp.video_closing_block([_scene(SPEAK)]))

    def test_legacy_repeats_are_cleaned_and_idempotent(self):
        old = (LEGACY_CRITICAL + "\n\nFor the target video ...\n\nintegrated_multimodal_description: [Shot 1] A. "
               + LEGACY_H3 + " B <d>[Chinese] 你好</d> " + LEGACY_H3 + " C. " + LEGACY_H3
               + "\n\noverall_soundscape: x\n\nnon_diegetic_music: N/A")
        fixed = cp.ensure_video_no_subtitle_first_line(old)
        self.assertEqual(cp.count_h3_no_subtitle_rules(fixed), 1)
        self.assertEqual(fixed.split("\n", 1)[0], cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE)
        self.assertIn("integrated_multimodal_description: [Shot 1] A. B <d>[Chinese] 你好</d> C.", fixed)
        self.assertEqual(cp.ensure_video_no_subtitle_first_line(fixed), fixed)
        # 副本在中间也只留第一行那一句；REFERENCE PICTURES 在它后面
        mid = "REFERENCE PICTURES: p\n\n" + cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE + "\n\nbody"
        out = cp.ensure_video_no_subtitle_first_line(mid)
        self.assertEqual(out, cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE + "\n\nREFERENCE PICTURES: p\n\nbody")
        # 旧名字（minimax_dual / ComfyUI 用过）不再凑三遍
        self.assertEqual(cp.count_h3_no_subtitle_rules(cp.ensure_h3_no_subtitle_rules(fixed)), 1)
        self.assertEqual(cp.count_h3_no_subtitle_rules(cp.ensure_h3_no_subtitle_rules("body only")), 0)


class StrataInstructionTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_system_prompts_keep_rule_once_at_front(self):
        from utility.prompt_polish import _SYS_GENERAL, _SYS_H3

        for sys_txt in (_SYS_GENERAL, _SYS_H3):
            self.assertIn('starting "NO SUBTITLES:"', sys_txt)
            self.assertIn("very first line of your output, once", sys_txt)
            self.assertIn("not about text already in the image", sys_txt)
            self.assertIn("Do not repeat it anywhere else", sys_txt)
            self.assertIn('"Image keywords:"', sys_txt)
            self.assertNotIn("there are three", sys_txt)
            self.assertNotIn("永远不许加任何字幕", sys_txt)
            self.assertNotIn(LEGACY_H3, sys_txt)
        self.assertNotIn("AND again as the last line", _SYS_GENERAL)

    def test_restore_after_polish(self):
        from utility.prompt_polish import _added_text_words, _fix_no_subtitle_line

        original = _h3("keywords")
        # Strata 把禁字幕句挪到后面并重复、丢了关键字句
        body = _below_first_line(original).replace(cp.VIDEO_IMAGE_KEYWORDS_RULE + " ", "")
        polished = body + " " + cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE
        out = _fix_no_subtitle_line(original, polished)
        out = cp.restore_image_keywords_rule(original, out)
        self.assertEqual(out.split("\n", 1)[0], cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE)
        self.assertEqual(cp.count_h3_no_subtitle_rules(out), 1)
        self.assertEqual(out.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
        self.assertEqual(_added_text_words(original, out), "")
        # Strata 自己加「no subtitles」之类的重复 → 不通过（退回原提示词）
        self.assertEqual(_added_text_words(original, out + " No subtitles."), "subtitle")
        # 参考图正文（原文没有禁字幕句）：Strata 加的那句清掉，外层前缀才有那一句
        ref_body = _below_first_line(original).strip()
        self.assertEqual(cp.count_h3_no_subtitle_rules(
            _fix_no_subtitle_line(ref_body, cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE + "\n\n" + ref_body)), 0)

    def test_dialog_passes_text_option_to_h3(self):
        src = Path(ROOT, "gui/video_prompt_dialog.py").read_text(encoding="utf-8")
        h3_args = src[src.index("_h3_args = dict("):src.index("_h3_refs = ")]
        self.assertIn("text=text_var.get()", h3_args)
        for mod in ("utility/minimax_dual.py", "utility/sd_image_processor.py", "utility/prompt_polish.py"):
            code = Path(ROOT, mod).read_text(encoding="utf-8")
            self.assertNotIn("ensure_h3_no_subtitle_rules(", code, mod)


if __name__ == "__main__":
    unittest.main()
