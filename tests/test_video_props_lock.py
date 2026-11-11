"""t388u/t390u offline tests: every object in the base picture stays the same for the whole video (empty hands stay
empty, held things stay held; nothing appears, changes or disappears). t390u: the rule and the Strata bullets never
name a concrete object (naming one made the model draw it). The rule is in every video prompt (H3, MiniMax, Grok / Gemini flow, FYI-only) and survives Strata 精简
(system prompts, restore, validate)."""
from __future__ import annotations

import re
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


def _fyi(evolve="keep"):
    return cp.build_video_fyi_only_prompt(frames="one", evolve=evolve, visual_style=PIXAR, fyi="走过来")


# t390u: 规则 / Strata 说明里不许出现的具体物品词（点名会让模型画出来）
FORBIDDEN_EN = ("tablet", "phone", "pad", "ipad", "cup", "mug", "table", "desk", "book", "laptop", "computer",
                "screen", "device", "glass", "bottle", "notebook", "pen", "paper", "bag")
FORBIDDEN_ZH = ("平板", "手机", "手機", "杯", "桌", "书", "書", "电脑", "電腦", "屏", "笔记本", "筆記本", "瓶", "包", "纸")
PRIMING = ("tablet", "phone", "ipad", "cup", "laptop", "手机", "手機", "平板", "杯")  # 整段视频提示词里都不该有


def _object_nouns(text):
    low = text.lower()
    hits = [w for w in FORBIDDEN_EN if re.search(rf"\b{w}(?:e?s)?\b", low)]
    return hits + [w for w in FORBIDDEN_ZH if w in text]


def _rule(prompt):
    sp = cp._rule_span(prompt, cp.VIDEO_PROPS_LOCK_PREFIX)
    return prompt[sp[0]:sp[1]] if sp else ""


class PropsLockRuleTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_rule_text(self):
        r = cp.video_props_lock_rule("picture 1")
        self.assertTrue(r.startswith(cp.VIDEO_PROPS_LOCK_PREFIX))
        for must in ("keep every object exactly as in picture 1", "Empty hands stay empty",
                     "keep holding the same thing", "No new object appears", "disappears",
                     "物品锁定", "空手一直空手", "拿着东西的一直拿着同一件", "不凭空多出东西"):
            self.assertIn(must, r)
        self.assertEqual(_object_nouns(r), [])  # t390u: 一个具体物品都不点名
        self.assertEqual(_rule(r), r)  # 整句（到中文括号结束）就是一条锁定句
        low = r.lower()
        for w in cp._CUT_WORDS + cp._REALISM_WORDS:  # 不会让切镜头 / 写实检查误报
            self.assertNotIn(w, low, w)
        self.assertEqual(cp.added_cut_words(_h3(), _h3() + " " + r), "")

    def test_every_video_prompt_has_it_once(self):
        for name, p, pic in (("h3", _h3(), "<Picture 1>"), ("flow", _flow(), "picture 1"),
                             ("flow_evolve", _flow("to_style"), "picture 1"),
                             ("flow_page", _flow("to_style_page"), "picture 1"),
                             ("flow_dissolve", _flow("to_style_dissolve"), "picture 1"),
                             ("minimax", _mm(), "the first frame"), ("fyi", _fyi(), "picture 1"),
                             ("fyi_evolve", _fyi("to_style"), "picture 1")):
            rule = cp.video_props_lock_rule(pic)
            self.assertEqual(p.count(rule), 1, name)
            self.assertEqual(p.count(cp.VIDEO_PROPS_LOCK_PREFIX), 1, name)

    def test_spans_dont_merge(self):
        for p in (_h3(), _flow(), _mm(), _fyi()):
            rule = _rule(p)
            for other in (cp.ART_STYLE_LOCK_PREFIX, cp.VIDEO_ONE_SHOT_PREFIX, cp.VIDEO_IMAGE_KEYWORDS_PREFIX):
                self.assertNotIn(other, rule)
                sp = cp._rule_span(p, other)
                if sp:
                    self.assertNotIn(cp.VIDEO_PROPS_LOCK_PREFIX, p[sp[0]:sp[1]])

    def test_h3_rule_before_dialogue(self):
        p = _h3()
        self.assertLess(p.index(_rule(p)), p.index("<d>"))

    def test_no_handing_or_changing_objects_elsewhere(self):
        for p in (_h3(), _flow(), _mm(), _fyi()):
            body = p.replace(_rule(p), " ").lower()
            for w in ("handed to", "picks up", "puts down", "moves or changes"):
                self.assertNotIn(w, body)
        line = cp.in_scene_direction_lines("林小雨把平板遞給王明", ["林小雨", "王明"])[0]
        self.assertIn("stays in the same hands", line)
        self.assertNotIn("screen", line)  # t390u
        self.assertIn(cp.IN_SCENE_FACING_MARK, line)
        self.assertNotIn("handed", line)

    def test_no_hardcoded_objects_in_video_prompts(self):
        """t390u: 视频提示词（含说话镜头那句、Strata 说明）里不写死手机 / 平板 / 杯子之类。"""
        for name, p in (("h3", _h3()), ("flow", _flow()), ("minimax", _mm()), ("fyi", _fyi()),
                        ("on_camera", cp.h3_on_camera_line(["林小雨", "王明"])),
                        ("no_music", cp.NOTEBOOKLM_VIDEO_NO_MUSIC)):
            low = p.lower()
            for w in PRIMING:
                hit = re.search(rf"\b{w}s?\b", low) if w.isascii() else (w in p)
                self.assertFalse(hit, (name, w))
        from utility import visual_remix
        src = (Path(ROOT) / "utility" / "visual_remix.py").read_text(encoding="utf-8")
        self.assertNotIn("手机", src)
        self.assertTrue(visual_remix)

    def test_transition_prompt_not_forced(self):
        src = (Path(ROOT) / "config_prompt.py").read_text(encoding="utf-8")
        body = src.split("def build_transition_video_prompt", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("video_props_lock_rule", body)


class StrataKeepsPropsLockTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_system_prompts_name_rule(self):
        from utility.prompt_polish import _SYS_GENERAL, _SYS_H3

        for s in (_SYS_GENERAL, _SYS_H3):
            self.assertIn('"Objects lock:"', s)
            self.assertEqual(s.count("Objects lock (t388u)"), 1)
            self.assertIn("copy it verbatim, once", s)
            self.assertIn("Never write that an object changes into another", s)
            self.assertIn("disappears", s)
            self.assertIn("Never name any object that the original prompt does not already name", s)
            bullet = s.split("Objects lock (t388u)", 1)[1].split("\n", 1)[0]
            self.assertEqual(_object_nouns(bullet), [])  # t390u

    def test_restore_after_drop_or_rewrite(self):
        for original in (_h3(), cp.ensure_video_no_subtitle_first_line(_flow()), _mm(),
                         cp.ensure_video_no_subtitle_first_line(_fyi())):
            rule = _rule(original)
            dropped = original.replace(" " + rule, "").replace(rule, "")
            self.assertNotIn(cp.VIDEO_PROPS_LOCK_PREFIX, dropped)
            out = cp.restore_video_locked_rules(original, dropped)
            self.assertEqual(out.count(rule), 1)
            self.assertEqual(cp.restore_video_locked_rules(original, out), out)  # 幂等
            bad = original.replace(rule, "Objects lock: the tablet slowly becomes a phone.")
            fixed = cp.restore_video_locked_rules(original, bad)
            self.assertEqual(fixed.count(rule), 1)
            self.assertNotIn("becomes a phone", fixed)
            for prefix in (cp.VIDEO_ONE_SHOT_PREFIX, cp.ART_STYLE_LOCK_PREFIX):  # 别的锁定句不受影响
                self.assertEqual(fixed.count(prefix), original.count(prefix))

    def test_validate_rejects_dropped_rule(self):
        from utility.prompt_polish import validate

        original = _h3()
        self.assertEqual(validate(original, original, "minimax_5070ti"), "")
        self.assertIn("物品锁定", validate(original, original.replace(_rule(original), ""), "minimax_5070ti"))
        flow = cp.ensure_video_no_subtitle_first_line(_flow())
        self.assertEqual(validate(flow, flow, "grok"), "")
        self.assertIn("物品锁定", validate(flow, flow.replace(_rule(flow), ""), "grok"))

    def test_added_object_words(self):
        """t390u: Strata 写出原文没有的物品名就不通过；原文本来就有的不算。"""
        from utility.prompt_polish import validate

        original = _h3()
        self.assertEqual(cp.added_object_words(original, original), "")
        self.assertEqual(cp.added_object_words(original, original + " 林小雨手里拿着手机。"), "手机")
        self.assertEqual(cp.added_object_words(original, original + " She holds a tablet."), "tablet")
        self.assertEqual(cp.added_object_words(original, original + " She looks at her iPad."), "ipad")
        self.assertEqual(cp.added_object_words("no lock here", "a phone"), "")  # 没有物品锁定句就不查
        with_phone = original + " 林小雨手里拿着手机。"
        self.assertEqual(cp.added_object_words(with_phone, with_phone), "")  # 原文有的不算
        self.assertIn("物品", validate(original, original + " Two phones lie nearby.", "minimax_5070ti"))
        flow = cp.ensure_video_no_subtitle_first_line(_flow())
        self.assertIn("phone", validate(flow, flow + " He picks up his phone.", "grok"))
        self.assertEqual(validate(flow, flow, "grok"), "")


if __name__ == "__main__":
    unittest.main()
