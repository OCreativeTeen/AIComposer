"""t392u offline tests: MiniMax reference-picture workflow sends portraits only for speakers missing from the scene
picture (the model plays attached portraits as shots). Detector is mocked; no Strata / ComfyUI calls."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_video_speaker_semantics import _install_stubs, _scene  # noqa: E402

_install_stubs()

import config_prompt as cp  # noqa: E402
from utility import speaker_presence as sp  # noqa: E402

SPEAK = "<1> 你今天怎麼來了？ <2> 想你了。"
REFS = [(1, "吴兴", "man.png"), (2, "林芳", "woman.png")]
PEOPLE = [(1, "吴兴", "middle-aged man, left sofa", "man.png"), (2, "林芳", "middle-aged woman, by the window", "woman.png")]


def _det(present):
    return lambda image_path, people, scene=None: (set(present), "mock")


def _send(present, detect=None):
    """What the video dialog does after the check: images, extra, prompt."""
    images = ["scene.webp"] + [p for _n, _nm, p in REFS]
    logs = []
    kept = sp.portraits_for_missing({}, "scene.webp", REFS, PEOPLE, detect=detect or _det(present), log=logs.append)
    images[1:] = [p for _n, _nm, p in kept]
    pics = {n: k for k, (n, _nm, _p) in enumerate(kept, 2)} or None
    body = cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", portrait_pictures=pics)
    prompt = (cp.h3_portrait_reference_block(kept) + "\n\n" + body) if kept else body
    return images, kept, prompt, logs


class SpeakerPresenceTest(unittest.TestCase):
    def setUp(self):
        _install_stubs()
        sp._CACHE.clear()

    def test_all_present_sends_scene_only(self):
        images, kept, prompt, logs = _send({1, 2})
        self.assertEqual(images, ["scene.webp"])
        self.assertEqual(kept, [])
        self.assertNotIn("<Picture 2>", prompt)
        self.assertNotIn("REFERENCE PICTURES", prompt)
        self.assertNotIn("by the portrait", prompt)
        self.assertIn("不发肖像", logs[0])

    def test_one_missing_only_that_portrait_as_picture_2(self):
        images, kept, prompt, logs = _send({1})
        self.assertEqual(images, ["scene.webp", "woman.png"])
        self.assertEqual(kept, [(2, "林芳", "woman.png")])
        self.assertIn("- <Picture 2> is the portrait of 林芳 (S2)", prompt)
        self.assertNotIn("<Picture 3>", prompt)
        self.assertNotIn("portrait of 吴兴", prompt)
        self.assertIn("identified in <Picture 1> by the portrait <Picture 2>", prompt)
        self.assertIn("不在：林芳", logs[0])

    def test_detector_failure_sends_no_portraits(self):
        images, kept, prompt, logs = _send(None, detect=lambda *a, **k: (None, "timeout"))
        self.assertEqual(images, ["scene.webp"])
        self.assertEqual(kept, [])
        self.assertIn("不发肖像", logs[0])

    def test_detect_parses_caches_and_records_on_scene(self):
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "s.png")
            Path(img).write_bytes(b"x")
            calls = []

            def ask(content, timeout_s):
                calls.append(content)
                return '```json\n{"present": ["S1"], "missing": ["S2"]}\n```'

            orig = sp._content
            sp._content = lambda *a, **k: "C"
            try:
                scene = {}
                got, _why = sp.detect_present_speakers(img, PEOPLE, scene=scene, ask=ask)
                self.assertEqual(got, {1})
                self.assertEqual(scene[sp.SCENE_CACHE_FIELD]["present"], [1])
                got2, why2 = sp.detect_present_speakers(img, PEOPLE, scene=scene, ask=ask)
                self.assertEqual(got2, {1})
                self.assertIn("缓存", why2)
                self.assertEqual(len(calls), 1)
                sp._CACHE.clear()  # new run: the scene record is enough
                got3, why3 = sp.detect_present_speakers(img, PEOPLE, scene=scene, ask=ask)
                self.assertEqual((got3, len(calls)), ({1}, 1))
                # bad answer -> None (caller then sends no portraits)
                bad, why = sp.detect_present_speakers(img, [(3, "x", "", "")], ask=lambda c, t: "no idea")
                self.assertIsNone(bad)
            finally:
                sp._content = orig

    def test_missing_image_is_failure(self):
        self.assertEqual(sp.detect_present_speakers("nope.png", PEOPLE)[0], None)

    def test_vision_prompt_names_no_object(self):
        low = sp._SYS.lower()
        for w in ("phone", "tablet", "cup", "laptop"):
            self.assertNotIn(w, low)

    def test_dialog_wiring(self):
        dlg = (Path(ROOT) / "gui/video_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn("_spres.portraits_for_missing(", dlg)
        self.assertIn('images[1:] = [p for _n, _nm, p in kept]', dlg)
        self.assertIn('extra["portrait_refs"] = len(kept)', dlg)
        self.assertIn('portrait_pictures=_pres["pics"]', dlg)
        # the check runs inside the background _work thread, not on the Tk thread
        w = dlg.index("def _work() -> None:")
        self.assertIn("_presence() if _need_presence else prompt", dlg[w:w + 400])
        self.assertIn("threading.Thread(target=_work", dlg[w:])

    def test_generate_sends_no_refs_when_zero(self):
        src = (Path(ROOT) / "utility/minimax_dual.py").read_text(encoding="utf-8")
        self.assertIn('_n = int(extra.get("portrait_refs") or 0)', src)
        self.assertIn("_refs = list(_imgs[1:1 + _n])", src)


if __name__ == "__main__":
    unittest.main()
