"""t340u: the video is the scene image; portraits only identify people (offline)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_video_speaker_semantics import _install_stubs, _scene  # noqa: E402

_install_stubs()

import config_prompt as cp  # noqa: E402
from utility import prompt_polish as pp  # noqa: E402

TWO = "<1> 你今天怎么来了？ <2> 想你了。"
REFS = [(1, "小美", "/x/a.png"), (2, "阿明", "/x/b.png")]
RULE = cp.PORTRAIT_REFERENCE_ONLY_RULE
GEN = cp.PORTRAIT_REFERENCE_ONLY_RULE_GENERIC


def _h3_r2v():
    """What the video dialog builds for the MiniMax reference-picture workflow, as sent (first line enforced)."""
    body = cp.build_h3_prompt([_scene(TWO)], language="zh", seconds=8, portrait_pictures={1: 2, 2: 3})
    return cp.ensure_video_no_subtitle_first_line(cp.h3_portrait_reference_block(REFS) + "\n\n" + body)


class PortraitReferenceRuleTest(unittest.TestCase):
    def test_rule_wording(self):
        self.assertTrue(RULE.startswith("Single scene shot:"))
        for must in ("the whole video is one continuous shot of the scene in <Picture 1>", "opening frame",
                     "only setting and composition", "never cuts, switches or transitions to a portrait picture",
                     "never shows a portrait as a shot", "identity references only",
                     "find that person in <Picture 1>", "the right person lip-syncs each line",
                     "walks naturally into this same scene, looking like their portrait"):
            self.assertIn(must, RULE)
        self.assertIn("reference image 1", GEN)
        self.assertNotIn("<Picture", GEN)

    def test_h3_labels_and_rule_once_near_top(self):
        p = _h3_r2v()
        lines = p.splitlines()
        self.assertEqual(lines[0], cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE)
        self.assertEqual(p.count(RULE), 1)
        self.assertIn("- <Picture 1> is the scene: the video itself (opening frame, setting and composition).", p)
        self.assertIn("- <Picture 2> is the portrait of 小美 (S1): identity reference only", p)
        self.assertIn("- <Picture 3> is the portrait of 阿明 (S2): identity reference only", p)
        self.assertEqual(p.count("never shown as a shot"), 2)
        # the rule follows the picture list and comes before the H3 body and the exact-speech rule
        self.assertLess(p.index("- <Picture 3>"), p.index(RULE))
        self.assertLess(p.index(RULE), p.index(cp.H3_I2V_LINE))
        self.assertLess(p.index(RULE), p.index(cp.SPOKEN_EXACT_TEXT_RULE))
        # inline mentions say the portrait only identifies a person in <Picture 1>
        self.assertNotIn("whose portrait is", p)
        self.assertIn("(S2) is 阿明", p)
        self.assertIn("identified in <Picture 1> by the portrait <Picture 3>", p)
        # the old wording that tied an entrance to the dialogue is gone
        self.assertNotIn("only when the dialogue brings them in", p)

    def test_no_portraits_no_rule(self):
        p = cp.build_h3_prompt([_scene(TWO)], language="zh", seconds=8)
        self.assertNotIn(RULE, p)
        self.assertNotIn("<Picture 2>", p)
        self.assertEqual(cp.ensure_portrait_reference_rule(p), p)
        self.assertEqual(cp.h3_portrait_reference_block([]), "")

    def test_generic_block_for_grok(self):
        b = cp.portrait_reference_block(REFS)
        self.assertEqual(b.count(GEN), 1)
        self.assertIn("- Reference image 1 is the scene: the video itself", b)
        self.assertIn("- Reference image 3 is the portrait of Speaker 2 阿明: identity reference only", b)
        self.assertLess(b.index("- Reference image 3"), b.index(GEN))
        self.assertNotIn(RULE, b)

    def test_send_time_ensure_is_idempotent_and_dedupes(self):
        p = _h3_r2v()
        self.assertEqual(cp.ensure_portrait_reference_rule(p), p)
        dropped = p.replace("\n" + RULE, "")
        doubled = p.replace(cp.H3_I2V_LINE, RULE + " " + cp.H3_I2V_LINE)
        for bad in (dropped, doubled):
            fixed = cp.ensure_portrait_reference_rule(bad)
            self.assertEqual(fixed.count(RULE), 1)
            self.assertLess(fixed.index("- <Picture 3>"), fixed.index(RULE))
            self.assertLess(fixed.index(RULE), fixed.index(cp.H3_I2V_LINE))
        g = "OUTPUT\n\n" + cp.portrait_reference_block(REFS).replace("\n" + GEN, "") + "\n\nbody"
        self.assertEqual(cp.ensure_portrait_reference_rule(g).count(GEN), 1)
        for name in ("utility/minimax_dual.py", "utility/sd_image_processor.py"):
            src = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("ensure_portrait_reference_rule(prompt)", src)
        self.assertEqual((ROOT / "utility/sd_image_processor.py").read_text(encoding="utf-8")
                         .count("ensure_portrait_reference_rule(prompt)"), 2)

    def test_post_strata_restore(self):
        orig = _h3_r2v()
        dropped = orig.replace("\n" + RULE, "")
        added_twice = orig.replace("[Shot 1]", "[Shot 1] " + RULE, 1)
        for polished in (dropped, added_twice, orig):
            out = cp.restore_portrait_reference_rule(orig, polished)
            self.assertEqual(out.count(RULE), 1)
            self.assertLess(out.index("- <Picture 3>"), out.index(RULE))
        # original without portraits: Strata may not add the rule
        plain = cp.build_h3_prompt([_scene(TWO)], language="zh", seconds=8)
        self.assertNotIn(RULE, cp.restore_portrait_reference_rule(plain, plain + " " + RULE))
        # Grok / generic prompt goes to Strata whole: rule comes back after the list
        g = cp.portrait_reference_block(REFS) + "\n\nClip body."
        out = cp.restore_portrait_reference_rule(g, g.replace("\n" + GEN, ""))
        self.assertEqual(out.count(GEN), 1)
        self.assertLess(out.index("- Reference image 3"), out.index(GEN))

    def test_reference_block_is_kept_out_of_strata(self):
        head, body = pp.split_reference_block(_h3_r2v())
        self.assertIn(RULE, head)
        self.assertNotIn(RULE, body)
        self.assertTrue(body.startswith(cp.H3_I2V_LINE))
        src = (ROOT / "utility/prompt_polish.py").read_text(encoding="utf-8")
        self.assertIn("return restore_portrait_reference_rule(prompt, ref_head + out), why", src)
        self.assertIn("out = restore_portrait_reference_rule(prompt, out)", src)

    def test_strata_instructions(self):
        for sys_txt in (pp._SYS_GENERAL, pp._SYS_H3):
            self.assertEqual(sys_txt.count('starting "Single scene shot:"'), 1)
            self.assertIn("never write that it cuts, switches or transitions to a portrait", sys_txt)
            self.assertIn("only identifies a person in picture 1", sys_txt)

    def test_image_order_matches_labels(self):
        """Dialog sends [scene] + portraits in portrait_refs order; the R2V workflow wires ref_image_0 = scene."""
        dlg = (ROOT / "gui/video_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn("images = images[:1] + [p for _n, _name, p in portrait_refs]", dlg)
        self.assertIn("_pics = {n: k for k, (n, _nm, _p) in enumerate(portrait_refs, 2)}", dlg)
        mm = (ROOT / "utility/minimax_dual.py").read_text(encoding="utf-8")
        self.assertIn("_refs = list(_imgs[1:1 + _n])", mm)
        sd = (ROOT / "utility/sd_image_processor.py").read_text(encoding="utf-8")
        self.assertIn('"scene (first frame)" if i == 0 else f"portrait <Picture {i + 1}>"', sd)
        self.assertIn("names = [image_name] + list(ref_image_names or [])", sd)


if __name__ == "__main__":
    unittest.main()
