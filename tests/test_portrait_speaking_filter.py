"""t357u: portrait extraction only for actors who are listed in the scene AND have a spoken line there (offline).

Rule: an actor at slot N of the scene's actor field (人物1 = slot 1, …) is extracted from this scene's image only
when the speaking text has a line for N: <N> or <Ns> (self-talk is the same person N). Unmarked speech (or text
before the first mark) is 人物1, the app's existing convention (speaking_marks.parse_speaking_turns /
config_prompt._speaker_slots). Empty speaking → nobody. Narrators (讲员) stay excluded. Skipped actors get
STATUS_NOT_SPEAKING ("这一场没有讲话，跳过…"). No Grok, GUI or .env: generate/review are stubs.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_video_speaker_semantics import _install_stubs  # noqa: E402

_install_stubs()

from utility.actor_portrait_extract import (  # noqa: E402
    REVIEW_OK,
    STATUS_NOT_SPEAKING,
    STATUS_OK,
    STATUS_REPLACED,
    actor_identity,
    actors_from_scene,
    all_actors_confirmed,
    confirm_key,
    format_actor_result_line,
    review_portraits_for_scene,
    scan_scenes_for_portraits,
    speaking_actor_slots,
    split_actors_by_speaking,
)

CHEN = "man/mature/chinese/陳默"
LIN = "woman/mature/chinese/林芳"
ACTOR_TEXT = f"人物1:{CHEN}\n人物2:{LIN}"


def _img(path, color):
    from PIL import Image

    Image.new("RGB", (60, 60), color).save(path)
    return path


class SpeakingSlotsTest(unittest.TestCase):
    def test_marks(self):
        self.assertEqual(speaking_actor_slots({"speaking": "<1s> 又一個字都沒寫……已經第三個晚上了。"}, 2), {1})
        self.assertEqual(speaking_actor_slots({"speaking": "<2s> 我在想什麼。"}, 2), {2})
        self.assertEqual(speaking_actor_slots({"speaking": "<1> 你來了。<2> 嗯。<1s> 她還是來了。"}, 2), {1, 2})
        self.assertEqual(speaking_actor_slots({"speaking": "＜2＞ 全形標記也算。"}, 2), {2})

    def test_unmarked_is_actor1_and_empty_is_nobody(self):
        self.assertEqual(speaking_actor_slots({"speaking": "沒有標記的一句話。"}, 2), {1})
        self.assertEqual(speaking_actor_slots({"speaking": "開頭沒標記 <2> 後面是二號。"}, 2), {1, 2})
        self.assertEqual(speaking_actor_slots({"speaking": ""}, 2), set())
        self.assertEqual(speaking_actor_slots({"speaking": "<1>   <2>  "}, 2), set())
        self.assertEqual(speaking_actor_slots({}, 2), set())

    def test_pause_marks_are_not_speakers(self):
        self.assertEqual(speaking_actor_slots({"speaking": "<2> 等等 <0.5> 再說。"}, 2), {2})

    def test_out_of_range_remapped_in_order_like_h3(self):
        # only one person listed, line written as <2>: maps to the first person (same as h3_speaker_map)
        self.assertEqual(speaking_actor_slots({"speaking": "<2> 只有一個人。"}, 1), {1})
        # three numbers for two people: no remap, keep as written
        self.assertEqual(speaking_actor_slots({"speaking": "<1> a <2> b <3> c"}, 2), {1, 2, 3})

    def test_story_content_used_only_when_speaking_empty_and_marked(self):
        self.assertEqual(speaking_actor_slots({"speaking": "", "story_content": "<2> 故事裡的話。"}, 2), {2})
        self.assertEqual(speaking_actor_slots({"speaking": "", "story_content": "沒有標記的故事。"}, 2), set())

    def test_actor_slots_from_actor_text(self):
        rows = actors_from_scene({"actor": ACTOR_TEXT})
        self.assertEqual([(r["label"], r["slot"]) for r in rows], [("人物1", 1), ("人物2", 2)])
        rows = actors_from_scene({"actor_refs": [{"body": CHEN}, {"body": LIN}]})
        self.assertEqual([r["slot"] for r in rows], [1, 2])


class ReviewFilterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t357_")
        self.avatar = os.path.join(self.tmp, "avatar")
        os.makedirs(self.avatar)
        self.gen_calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _dest(self, role, name, avatar_dir="", style=None):
        return os.path.join(avatar_dir, actor_identity(name).replace("/", "_") + ".png")

    def _path(self, role, name, avatar_dir="", style=None):
        p = self._dest(role, name, avatar_dir)
        return p if os.path.isfile(p) else ""

    def _gen(self, image, actor, prompt):
        self.gen_calls.append((os.path.basename(image), actor["body"]))
        return _img(os.path.join(self.tmp, f"g{len(self.gen_calls)}.png"), (200, 10 * len(self.gen_calls), 10))

    def _scene(self, speaking, name="s.png", **extra):
        sc = {"clip_image": _img(os.path.join(self.tmp, name), (30, 30, 30)), "actor": ACTOR_TEXT, "speaking": speaking}
        sc.update(extra)
        return sc

    def _run(self, scene, **kw):
        kw.setdefault("confirmed", set())
        return review_portraits_for_scene(
            scene, self.avatar, generate=self._gen, review=lambda a, p, k: REVIEW_OK,
            portrait_path=self._path, portrait_dest=self._dest, **kw)

    def test_self_talk_split_scene_extracts_only_speaker(self):
        """Tom's example: split-out self-talk scene with 人物1 陳默 + 人物2 林芳 → only 人物1."""
        out = self._run(self._scene("<1s> 又一個字都沒寫……已經第三個晚上了。"))
        self.assertEqual(self.gen_calls, [("s.png", CHEN)])
        self.assertEqual([(r["body"], r["status"]) for r in out["results"]],
                         [(CHEN, STATUS_OK), (LIN, STATUS_NOT_SPEAKING)])
        line = format_actor_result_line(out["results"][1])
        self.assertTrue(line.startswith("人物2 林芳："), line)
        self.assertIn("这一场没有讲话，跳过", line)
        self.assertFalse(os.path.exists(self._dest("person", LIN, self.avatar)))

    def test_second_speaker_only(self):
        self._run(self._scene("<2> 先喝口水吧。"))
        self.assertEqual(self.gen_calls, [("s.png", LIN)])

    def test_unmarked_speech_is_actor1(self):
        out = self._run(self._scene("沒有標記的一句話。"))
        self.assertEqual(self.gen_calls, [("s.png", CHEN)])
        self.assertEqual(out["results"][-1]["status"], STATUS_NOT_SPEAKING)

    def test_no_speech_extracts_nobody(self):
        out = self._run(self._scene(""))
        self.assertEqual(self.gen_calls, [])
        self.assertEqual(out["reason"], "no_speaking_actors")
        self.assertEqual([r["status"] for r in out["results"]], [STATUS_NOT_SPEAKING, STATUS_NOT_SPEAKING])

    def test_narrator_excluded_and_counts_as_slot(self):
        scene = {"clip_image": _img(os.path.join(self.tmp, "n.png"), (5, 5, 5)), "speaking": "<1> 各位好。<2> 我先說。",
                 "actor_refs": [{"role": "host", "body": "man/mature/chinese/讲员甲", "label": "讲员"},
                                {"role": "person", "body": CHEN, "label": "人物1"}]}
        out = self._run(scene)
        self.assertEqual(self.gen_calls, [("n.png", CHEN)])
        self.assertEqual([r["body"] for r in out["results"]], [CHEN])  # host never listed

    def test_manual_replace_mode_also_narrows(self):
        with open(self._dest("person", LIN, self.avatar), "wb") as fh:
            fh.write(b"OLD-LIN")
        out = self._run(self._scene("<1s> 又一個字都沒寫。"), existing="replace", stop_on_failure=False)
        self.assertEqual(self.gen_calls, [("s.png", CHEN)])
        self.assertEqual(out["results"][0]["status"], STATUS_OK)
        self.assertEqual(out["results"][1]["status"], STATUS_NOT_SPEAKING)
        with open(self._dest("person", LIN, self.avatar), "rb") as fh:
            self.assertEqual(fh.read(), b"OLD-LIN")  # existing portrait of the silent actor untouched

    def test_manual_replace_with_old_portrait_replaced_for_speaker(self):
        with open(self._dest("person", CHEN, self.avatar), "wb") as fh:
            fh.write(b"OLD-CHEN")
        out = self._run(self._scene("<1s> 又一個字都沒寫。"), existing="replace", stop_on_failure=False)
        self.assertEqual(out["results"][0]["status"], STATUS_REPLACED)

    def test_scan_takes_each_person_from_scene_where_they_speak(self):
        alone = self._scene("<1s> 又一個字都沒寫……", name="a.png")
        talk = self._scene("<2> 先喝口水吧。<1> 謝謝。", name="b.png")
        confirmed = set()
        report = scan_scenes_for_portraits(
            [alone, talk], self.avatar, generate=self._gen, review=lambda a, p, k: REVIEW_OK,
            confirmed=confirmed, portrait_path=self._path, portrait_dest=self._dest)
        # 陳默 from his self-talk scene, 林芳 only from the dialogue scene; 陳默 is not asked again
        self.assertEqual(self.gen_calls, [("a.png", CHEN), ("b.png", LIN)])
        self.assertEqual({confirm_key({"role": "person", "body": b}) for b in (CHEN, LIN)}, confirmed)

    def test_all_confirmed_ignores_silent_actors(self):
        alone = self._scene("<1s> 又一個字都沒寫。")
        key = confirm_key({"role": "person", "body": CHEN})
        self.assertTrue(all_actors_confirmed([alone], {key}))
        self.assertFalse(all_actors_confirmed([alone], set()))
        self.assertTrue(all_actors_confirmed([self._scene("")], set()))

    def test_duplicate_listing_any_slot_speaking_counts(self):
        sc = {"speaking": "<2> 是我。", "actor_refs": [{"body": CHEN}, {"body": CHEN + "（低头）"}]}
        speak, silent = split_actors_by_speaking(sc)
        self.assertEqual(([a["body"] for a in speak], silent), ([CHEN], []))


if __name__ == "__main__":
    unittest.main()
