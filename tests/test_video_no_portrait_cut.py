"""t391u offline tests: MiniMax kept cutting to a speaker's portrait. The sent prompts (working/*.h3.json) all had the
One base shot rule, so Strata did not drop it; the pull came from the reference-picture workflow (portraits attached)
plus wording that pushed toward a frontal face ("faces the camera", "looks exactly like their portrait even if the
face is hidden"). The rule now allows slow camera moves and soft light but forbids zooming in to one face; the
portrait block keeps each person at their size and place in <Picture 1>."""
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
REFS = [(1, "吴兴", "a.png"), (2, "林芳", "b.png")]


def _h3_r2v():
    body = cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", style=PIXAR,
                              portrait_pictures={1: 2, 2: 3})
    return cp.ensure_video_no_subtitle_first_line(cp.h3_portrait_reference_block(REFS) + "\n\n" + body)


class NoPortraitCutTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()

    def test_rule_allows_camera_forbids_zoom(self):
        r = cp.video_one_shot_rule("<Picture 1>")
        for must in ("The camera may move slowly (pan, turn, drift or reposition", "the light may shift softly",
                     "never zooms in to one face", "never cuts to a portrait", "same place, background and people stay in view",
                     "at about the size and place they have in <Picture 1>", "摄像机可以慢慢移动", "绝不推到一个人的脸"):
            self.assertIn(must, r)
        self.assertNotIn("framing", r)
        self.assertEqual(r.count("）"), 1)
        self.assertTrue(r.endswith("）"))
        p = _h3_r2v()
        sp = cp._rule_span(p, cp.VIDEO_ONE_SHOT_PREFIX)
        self.assertEqual(p[sp[0]:sp[1]], r)

    def test_no_object_named(self):
        r = cp.video_one_shot_rule("<Picture 1>").lower()
        for w in ("phone", "tablet", "cup", "laptop", "手机", "平板", "杯"):
            self.assertNotIn(w, r)

    def test_speakers_do_not_face_the_camera(self):
        p = _h3_r2v()
        self.assertNotIn("faces the camera", p)
        self.assertIn("turns the face toward the person they talk to", p)

    def test_portrait_block_keeps_size_and_place(self):
        b = cp.h3_portrait_reference_block(REFS)
        self.assertNotIn("even if their face is hidden", b)
        self.assertIn("stays at the size, place, pose and distance from the camera they have in <Picture 1>", b)
        self.assertIn("never fills the frame", b)
        self.assertIn("never shown as a shot", b)
        self.assertEqual(b.count(cp.PORTRAIT_REFERENCE_ONLY_RULE), 1)

    def test_rule_once_and_restored_after_strata_drop(self):
        p = _h3_r2v()
        rule = cp.video_one_shot_rule("<Picture 1>")
        self.assertEqual(p.count(rule), 1)
        dropped = p.replace(rule, "")
        out = cp.restore_video_locked_rules(p, dropped)
        self.assertEqual(out.count(rule), 1)
        self.assertEqual(cp.restore_video_locked_rules(p, out), out)

    def test_validate_rejects_zoom_or_cut_added(self):
        from utility.prompt_polish import validate

        p = _h3_r2v()
        self.assertIn("切镜头", validate(p, p.replace("[Shot 1]", "[Shot 1] Cut to a close-up of 吴兴.", 1),
                                        "minimax_5070ti"))

    def test_strata_system_prompts_allow_camera(self):
        from utility import prompt_polish as pp

        for sysp in (pp._SYS_GENERAL, pp._SYS_H3):
            self.assertIn("never write a zoom in to one face", sysp)
            for w in ("phone", "tablet"):
                self.assertNotIn(w, sysp.lower())


if __name__ == "__main__":
    unittest.main()
