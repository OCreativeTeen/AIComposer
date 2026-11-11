"""t398u offline tests: 「关键字作背景」只保住起始图里已经有的关键字；图里没有的一律不加；
模型 / Strata 不得添加关键字。规则写进视频提示词，并作为锁定句经 restore + validate 从 Strata 打磨后活下来。
不点名具体物品。Stubs project_manager / config（不读 .env，不调 LLM）。"""
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
FORBIDDEN_OBJECT_NAMES = (
    "tablet", "phone", "pad", "cup", "book", "bowl", "plate",
    "平板", "手机", "手機", "杯子", "碗",
)


def _h3(text="keywords", style=PIXAR, **kw):
    return cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", text=text, style=style,
                              region="中国", era="现代", **kw)


def _flow(text="keywords", style=PIXAR, evolve="keep"):
    return cp.build_video_flow_prompt(
        frames="one", background="none", evolve=evolve, visual_style=style,
        scene_content=[_scene(SPEAK)], language="zh", narrative="story", text=text,
        use_visual=True, use_speaking=True, use_actor=True, story_style="story_speak",
    )


class T398uKeywordsBackgroundTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_rule_only_keeps_what_is_already_in_the_picture(self):
        r = cp.VIDEO_IMAGE_KEYWORDS_RULE
        self.assertTrue(r.startswith(cp.VIDEO_IMAGE_KEYWORDS_PREFIX))
        for must in (
            "the keywords only describe lettering already drawn in the start picture",
            "keep those as they are",
            "Anything in the keywords that is not already visible in the start picture must not be added",
            "Nothing new appears",
            "No new text is ever added",
            "has no lettering, the video has none",
            "只描述起始图里已经看得见",
            "保留、不删除",
            "关键字里有但图里没有的，一律不加",
            "绝不再加任何字",
            "图里本来没有字，视频里就没有字",
        ):
            self.assertIn(must, r)
        self.assertNotIn("scene's keywords", r)
        self.assertNotIn("the only words in the video are", r)
        self.assertNotIn("distil", r)
        low = r.lower()
        for name in FORBIDDEN_OBJECT_NAMES:
            self.assertNotIn(name.lower() if name.isascii() else name, low if name.isascii() else r, name)

    def test_caption_rule_and_prompts_use_the_locked_sentence(self):
        self.assertEqual(cp.video_caption_rule("keywords"), cp.VIDEO_IMAGE_KEYWORDS_RULE)
        self.assertEqual(cp.video_caption_rule("keep"), cp.VIDEO_IMAGE_KEYWORDS_RULE)
        for p in (_h3("keywords"), _h3("keep"), _flow("keywords"), _flow("keep")):
            self.assertEqual(p.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
            self.assertLess(p.index(cp.VIDEO_IMAGE_KEYWORDS_RULE), p.index("<d>") if "<d>" in p else p.index("says aloud:") if "says aloud:" in p else len(p))
        for text in ("", "erase", "express"):
            self.assertNotIn(cp.VIDEO_IMAGE_KEYWORDS_PREFIX, _h3(text))

    def test_restore_replaces_invented_keyword_rewrite(self):
        original = _h3("keywords")
        rewritten = original.replace(
            cp.VIDEO_IMAGE_KEYWORDS_RULE,
            "Image keywords: add the scene keywords onto the background even if they are not in the start picture.",
        )
        out = cp.restore_image_keywords_rule(original, rewritten)
        self.assertEqual(out.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
        self.assertNotIn("even if they are not in the start picture", out)
        dropped = original.replace(" " + cp.VIDEO_IMAGE_KEYWORDS_RULE, "").replace(cp.VIDEO_IMAGE_KEYWORDS_RULE, "")
        self.assertNotIn(cp.VIDEO_IMAGE_KEYWORDS_PREFIX, dropped)
        restored = cp.restore_video_locked_rules(original, dropped)
        self.assertEqual(restored.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
        self.assertEqual(cp.restore_video_locked_rules(original, restored), restored)

    def test_strata_instructions_and_validate_lock_the_rule(self):
        from utility.prompt_polish import _SYS_GENERAL, _SYS_H3, validate

        for s in (_SYS_GENERAL, _SYS_H3):
            self.assertIn("t398u", s)
            self.assertIn('"Image keywords:"', s)
            self.assertIn("the keywords only describe lettering already drawn in the start picture", s)
            self.assertIn("Anything in the keywords that is not already visible in the start picture must not be added", s)
            self.assertIn("Nothing new appears", s)
            self.assertIn("NO new text is ever added", s)
            self.assertIn("Do not invent or add keywords that are not already visible in the start picture", s)
            self.assertIn("Never take words from the visual description, the speaking lines", s)
            for name in FORBIDDEN_OBJECT_NAMES:
                self.assertNotIn(name, s)

        original = _h3("keywords")
        self.assertEqual(validate(original, original, "minimax_5070ti"), "")
        dropped = original.replace(" " + cp.VIDEO_IMAGE_KEYWORDS_RULE, "").replace(cp.VIDEO_IMAGE_KEYWORDS_RULE, "")
        why = validate(original, dropped, "minimax_5070ti")
        self.assertIn("关键字作背景", why)
        flow = cp.ensure_video_no_subtitle_first_line(_flow("keywords"))
        dropped_flow = flow.replace(" " + cp.VIDEO_IMAGE_KEYWORDS_RULE, "").replace(cp.VIDEO_IMAGE_KEYWORDS_RULE, "")
        self.assertIn("关键字作背景", validate(flow, dropped_flow, "grok"))
        fixed = cp.restore_video_locked_rules(original, dropped)
        self.assertEqual(validate(original, fixed, "minimax_5070ti"), "")


if __name__ == "__main__":
    unittest.main()
