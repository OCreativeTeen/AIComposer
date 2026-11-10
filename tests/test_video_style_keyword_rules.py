"""t369u offline tests: 「关键字作背景」= keep lettering already in the start picture (may come alive), never add
new text or pull keywords from visual / speaking; the video keeps the start picture's art style (3D animation never
turns realistic). Both rules survive Strata 精简 (restore + validate). Stubs project_manager / config (no .env, no LLM)."""
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
REAL = "写实 (Realistic)"


def _h3(text="keywords", style=PIXAR, **kw):
    return cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", text=text, style=style,
                              region="中国", era="现代", **kw)


def _flow(text="keywords", style=PIXAR, evolve="keep"):
    return cp.build_video_flow_prompt(
        frames="one", background="none", evolve=evolve, visual_style=style,
        scene_content=[_scene(SPEAK)], language="zh", narrative="story", text=text,
        use_visual=True, use_speaking=True, use_actor=True, story_style="story_speak",
    )


def _lock(prompt):
    sp = cp._rule_span(prompt, cp.ART_STYLE_LOCK_PREFIX)
    return prompt[sp[0]:sp[1]] if sp else ""


class KeywordRuleTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_rule_means_keep_existing_never_add(self):
        r = cp.VIDEO_IMAGE_KEYWORDS_RULE
        self.assertTrue(r.startswith(cp.VIDEO_IMAGE_KEYWORDS_PREFIX))
        for must in ("already drawn in the start picture", "never erased", "come alive", "No new text is ever added",
                     "visual description", "speaking lines", "has no lettering, the video has none",
                     "保留、不删除", "可以灵动起来", "绝不再加任何字"):
            self.assertIn(must, r)
        # 旧说法会让模型去找「这一场的关键字」往画面上加
        self.assertNotIn("scene's keywords", r)
        self.assertNotIn("the only words in the video are", r)

    def test_no_keyword_extraction_into_video_prompts(self):
        for p in (_h3("keywords"), _flow("keywords")):
            self.assertEqual(p.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
            self.assertNotIn("Keyword hint", p)
            self.assertNotIn("distil", p)
            self.assertNotIn(cp.KEYWORD_COUNT_EN, p)
            self.assertNotIn("Take it from", p)

    def test_restore_keyword_rule_on_one_line_h3_keeps_rest(self):
        original = _h3("keywords")
        rewritten = original.replace(cp.VIDEO_IMAGE_KEYWORDS_RULE, "Image keywords: show the scene keywords 想你 on the wall.")
        out = cp.restore_image_keywords_rule(original, rewritten)
        self.assertEqual(out.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
        self.assertNotIn("想你 on the wall", out)
        self.assertIn("<d>[Chinese] 想你了。</d>", out)  # 同一行后面的内容没被删掉
        self.assertIn("overall_soundscape:", out)
        dup = original.replace(cp.VIDEO_IMAGE_KEYWORDS_RULE, cp.VIDEO_IMAGE_KEYWORDS_RULE + " " + cp.VIDEO_IMAGE_KEYWORDS_RULE)
        self.assertEqual(cp.restore_image_keywords_rule(original, dup).count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)


class ArtStyleLockTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_style_names(self):
        self.assertEqual(cp.video_art_style_en(PIXAR), ("3D animation (Pixar-style 3D animated cartoon, CGI)", True))
        self.assertEqual(cp.video_art_style_en("三维卡通 (Pixar-Art Cartoon)")[1], True)
        self.assertEqual(cp.video_art_style_en(REAL)[1], False)
        self.assertEqual(cp.video_art_style_en("黏土动画 (Claymation)")[1], True)
        self.assertEqual(cp.video_art_style_en("复古胶片 (Vintage-Film)")[1], False)

    def test_h3_states_style_and_never_realistic(self):
        p = _h3()
        shot = p.split("[Shot 1] ", 1)[1]
        self.assertTrue(shot.startswith("3D animation (Pixar-style 3D animated cartoon, CGI), in the style of " + PIXAR))
        self.assertNotIn("Cinematic", shot.split(".", 1)[0])
        lock = _lock(p)
        self.assertTrue(lock)
        self.assertEqual(p.count(lock), 1)
        self.assertIn("exact art style of <Picture 1>", lock)
        self.assertIn(cp.ART_STYLE_NO_REAL_MARK, lock)
        self.assertIn("绝不变成写实", lock)
        self.assertLess(p.index(lock), p.index("<d>"))
        for w in ("photorealistic", "live-action", "realistic", "film"):
            self.assertNotIn(w, p.replace(lock, "").lower(), w)
        self.assertEqual(cp.added_realism_words(p, p), "")

    def test_realistic_style_unchanged_head_and_no_ban(self):
        p = _h3(style=REAL)
        self.assertIn("[Shot 1] Live-action, cinematic, realistic", p)
        self.assertNotIn(cp.ART_STYLE_NO_REAL_MARK, p)
        self.assertIn(cp.ART_STYLE_LOCK_PREFIX, p)

    def test_grok_gemini_flow_has_lock_when_style_kept(self):
        p = _flow()
        lock = _lock(p)
        self.assertIn("exact art style of picture 1", lock)
        self.assertEqual(p.count(lock), 1)
        self.assertNotIn(cp.ART_STYLE_LOCK_PREFIX, _flow(evolve="to_style"))  # 演进到目标风格：不锁
        fyi = cp.build_video_fyi_only_prompt(frames="one", evolve="keep", visual_style=PIXAR, fyi="走过来")
        self.assertIn(cp.ART_STYLE_NO_REAL_MARK, fyi)
        self.assertNotIn("film", cp.VIDEO_NO_CAPTION_RULE.lower())
        mm = cp.build_minimax_video_prompt([_scene(SPEAK)], style=PIXAR, language="zh")
        self.assertNotIn("cinematic film", mm.lower())
        self.assertIn(cp.ART_STYLE_NO_REAL_MARK, mm)


class StrataKeepsBothRulesTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_system_prompts_name_both_rules(self):
        from utility.prompt_polish import _SYS_GENERAL, _SYS_H3

        for s in (_SYS_GENERAL, _SYS_H3):
            self.assertIn('"Art style lock:"', s)
            self.assertIn('"Image keywords:"', s)
            self.assertIn("NO new text is ever added", s)
            self.assertIn("never rewrite the style as live-action, photorealistic", s)
            self.assertIn("Never take words from the visual description, the speaking lines", s)

    def test_restore_after_strata_drops_both(self):
        for original in (_h3(), cp.ensure_video_no_subtitle_first_line(_flow())):
            lock = _lock(original)
            dropped = original.replace(" " + lock, "").replace(lock, "")
            dropped = dropped.replace(" " + cp.VIDEO_IMAGE_KEYWORDS_RULE, "").replace(cp.VIDEO_IMAGE_KEYWORDS_RULE, "")
            self.assertNotIn(cp.ART_STYLE_LOCK_PREFIX, dropped)
            out = cp.restore_video_locked_rules(original, dropped)
            self.assertEqual(out.count(lock), 1)
            self.assertEqual(out.count(cp.VIDEO_IMAGE_KEYWORDS_RULE), 1)
            self.assertEqual(cp.restore_video_locked_rules(original, out), out)  # 幂等

    def test_restore_rewritten_lock_and_validate_rejects_realism(self):
        from utility.prompt_polish import validate

        original = _h3()
        lock = _lock(original)
        bad = original.replace(lock, "Art style lock: a photorealistic live-action film.")
        fixed = cp.restore_art_style_rule(original, bad)
        self.assertEqual(fixed.count(lock), 1)
        self.assertNotIn("photorealistic live-action film", fixed)
        self.assertEqual(validate(original, original, "minimax_5070ti"), "")
        real = original.replace("[Shot 1] 3D animation", "[Shot 1] Photorealistic live-action footage, 3D animation")
        self.assertIn("写实", validate(original, real, "minimax_5070ti"))
        self.assertEqual(cp.added_realism_words(original, real), "photorealistic")
        flow = cp.ensure_video_no_subtitle_first_line(_flow())
        self.assertIn("画风锁定", validate(flow, flow.replace(_lock(flow), ""), "grok"))

    def test_dialog_rechecks_before_send(self):
        src = (Path(ROOT) / "gui" / "video_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn("restore_video_locked_rules(box.get(\"pre\") or prompt, final)", src)
        pol = (Path(ROOT) / "utility" / "prompt_polish.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(pol.count("restore_video_locked_rules(prompt, out)"), 2)


if __name__ == "__main__":
    unittest.main()
