"""Offline tests for <N>/<Ns> parsing and new-project monologue splits."""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class SpeakingMarksTest(unittest.TestCase):
    def test_normal_dialogue_unaffected(self):
        from utility.speaking_marks import (
            format_speaking_turns,
            parse_speaking_turns,
            speaker_ids_in_text,
            speaking_has_monologue,
            split_speaking_pair,
            strip_speaker_marks,
        )

        text = "<1> 你好。<2> 今天怎么样？<1> 还行。"
        turns = parse_speaking_turns(text)
        self.assertEqual([(t.speaker, t.text, t.monologue) for t in turns], [
            (1, "你好。", False),
            (2, "今天怎么样？", False),
            (1, "还行。", False),
        ])
        self.assertFalse(speaking_has_monologue(text))
        self.assertIsNone(split_speaking_pair(text))
        self.assertEqual(speaker_ids_in_text(text), [1, 2])
        self.assertEqual(strip_speaker_marks(text), "你好。 今天怎么样？ 还行。")
        self.assertEqual(strip_speaker_marks("温度不到 <0.5> 度"), "温度不到 度")
        self.assertEqual(speaker_ids_in_text("score 1s and < 3"), [])
        plain = "没有尖括号的对白"
        self.assertEqual([(t.speaker, t.text, t.monologue) for t in parse_speaking_turns(plain)], [
            (1, plain, False),
        ])

    def test_ns_and_legacy_both_scripts_and_multidigit(self):
        from utility.speaking_marks import parse_speaking_turns, speaker_ids_in_text, speaking_has_monologue, strip_speaker_marks

        modern = "<12s> 我想了很久。<3> 你说呢？"
        turns = parse_speaking_turns(modern)
        self.assertEqual(turns[0].speaker, 12)
        self.assertTrue(turns[0].monologue)
        self.assertEqual(turns[1].speaker, 3)
        self.assertFalse(turns[1].monologue)
        self.assertEqual(speaker_ids_in_text(modern), [12, 3])
        self.assertTrue(speaking_has_monologue(modern))
        self.assertEqual(strip_speaker_marks(modern), "我想了很久。 你说呢？")
        self.assertNotIn("s", strip_speaker_marks("<1s> 你好"))

        simp = "<1>（自言自语）跟朋友吃了顿饭。<2> 你今天怎么这么累？"
        trad = "<1>（自言自語）原来我不是坏掉了。"
        self.assertTrue(parse_speaking_turns(simp)[0].monologue)
        self.assertEqual(parse_speaking_turns(simp)[0].speaker, 1)
        self.assertFalse(parse_speaking_turns(simp)[1].monologue)
        self.assertTrue(parse_speaking_turns(trad)[0].monologue)
        self.assertTrue(speaking_has_monologue(simp))
        self.assertTrue(speaking_has_monologue(trad))
        self.assertEqual(strip_speaker_marks(simp), "跟朋友吃了顿饭。 你今天怎么这么累？")

    def test_leading_split_order_and_authored_copies(self):
        from utility.speaking_marks import expand_scenes_for_new_project

        extra = {"note": ["keep"], "n": 1}
        src = [{
            "caption": "四小时换一小时",
            "visual": "深夜书房",
            "actor": "人物1:man/mature/chinese/阿哲 | 人物2:woman/mature/chinese/小雨",
            "speaking": "<1s> 跟朋友吃了顿饭。<2> 你今天怎么这么累？<1> 我也不知道。",
            "extra": extra,
            "id": 99,
        }]
        frozen = copy.deepcopy(src)
        out = expand_scenes_for_new_project(src)
        self.assertEqual(src, frozen)  # source list untouched
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0]["speaking"].startswith("<1s>"))
        self.assertIn("<2>", out[1]["speaking"])
        self.assertNotIn("s>", out[1]["speaking"].replace("<1s>", ""))
        self.assertFalse(out[1]["speaking"].startswith("<1s>"))
        for key in ("caption", "visual", "actor"):
            self.assertEqual(out[0][key], src[0][key])
            self.assertEqual(out[1][key], src[0][key])
        self.assertEqual(out[0]["extra"], extra)
        self.assertEqual(out[1]["extra"], extra)
        self.assertIsNot(out[0]["extra"], extra)
        self.assertIsNot(out[0]["extra"], out[1]["extra"])
        self.assertNotIn("id", out[0])
        self.assertNotIn("id", out[1])

    def test_trailing_split_and_merged_block(self):
        from utility.speaking_marks import expand_scenes_for_new_project, parse_speaking_turns

        src = [{
            "caption": "C",
            "visual": "V",
            "actor": "A",
            "speaking": "<1> 每天都有截止日期。<2> 就像每天拆一面墙。<1s> 原来我不是坏掉了。<2s> 我只是燃尽了。",
        }]
        out = expand_scenes_for_new_project(src)
        self.assertEqual(len(out), 2)
        self.assertIn("截止日期", out[0]["speaking"])
        self.assertNotIn("<1s>", out[0]["speaking"])
        self.assertNotIn("<2s>", out[0]["speaking"])
        mono = parse_speaking_turns(out[1]["speaking"])
        self.assertTrue(all(t.monologue for t in mono))
        self.assertEqual([t.speaker for t in mono], [1, 2])
        self.assertIn("原来我不是坏掉了", out[1]["speaking"])
        self.assertIn("我只是燃尽了", out[1]["speaking"])

    def test_pure_monologue_and_no_blank(self):
        from utility.speaking_marks import expand_scenes_for_new_project, split_speaking_pair

        src = [{"caption": "C", "speaking": "<1s> 我一个人想了很久。<1s> 还是老样子。"}]
        out = expand_scenes_for_new_project(src)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["speaking"], src[0]["speaking"])
        self.assertIsNone(split_speaking_pair("<1s>   "))
        self.assertEqual(expand_scenes_for_new_project([]), [])

    def test_invalid_interior_and_both_ends_kept_unchanged(self):
        from utility.speaking_marks import expand_scenes_for_new_project, split_speaking_pair

        interior_speaking = "<1> 你好。<2s> 夹在中间。<1> 还在。"
        both_speaking = "<1s> 开头。<2> 中间。<1s> 结尾。"
        interior = [{"caption": "ok", "speaking": interior_speaking, "visual": "V1", "actor": "A1"}]
        both = [{"caption": "also", "speaking": both_speaking, "visual": "V2", "actor": "A2"}]
        frozen_i = copy.deepcopy(interior)
        frozen_b = copy.deepcopy(both)
        out_i = expand_scenes_for_new_project(interior)
        out_b = expand_scenes_for_new_project(both)
        self.assertEqual(interior, frozen_i)
        self.assertEqual(both, frozen_b)
        self.assertEqual(len(out_i), 1)
        self.assertEqual(len(out_b), 1)
        self.assertEqual(out_i[0]["speaking"], interior_speaking)
        self.assertEqual(out_b[0]["speaking"], both_speaking)
        self.assertEqual(out_i[0]["caption"], "ok")
        self.assertEqual(out_b[0]["visual"], "V2")
        self.assertIsNone(split_speaking_pair(interior_speaking))
        self.assertIsNone(split_speaking_pair(both_speaking))
        self.assertIsNone(split_speaking_pair("<1>（自言自语）头。<2> 中。<1s> 尾。"))

    def test_mixed_list_valid_split_and_invalid_unchanged(self):
        from utility.speaking_marks import expand_scenes_for_new_project

        leading = "<1s> 先想一下。<2> 你在吗？"
        interior = "<1> 你好。<2s> 夹在中间。<1> 还在。"
        trailing = "<2> 先坐下。<1s> 原来如此。"
        both = "<1s> 头。<2> 中。<1s> 尾。"
        src = [
            {"caption": "L", "visual": "VL", "actor": "AL", "speaking": leading},
            {"caption": "I", "visual": "VI", "actor": "AI", "speaking": interior},
            {"caption": "T", "visual": "VT", "actor": "AT", "speaking": trailing},
            {"caption": "B", "visual": "VB", "actor": "AB", "speaking": both},
        ]
        frozen = copy.deepcopy(src)
        out = expand_scenes_for_new_project(src)
        self.assertEqual(src, frozen)
        self.assertEqual(len(out), 6)
        self.assertTrue(out[0]["speaking"].startswith("<1s>"))
        self.assertIn("<2>", out[1]["speaking"])
        self.assertEqual(out[0]["caption"], "L")
        self.assertEqual(out[1]["caption"], "L")
        self.assertEqual(out[2]["speaking"], interior)
        self.assertEqual(out[2]["caption"], "I")
        self.assertIn("先坐下", out[3]["speaking"])
        self.assertTrue(out[4]["speaking"].startswith("<1s>"))
        self.assertEqual(out[3]["caption"], "T")
        self.assertEqual(out[4]["caption"], "T")
        self.assertEqual(out[5]["speaking"], both)
        self.assertEqual(out[5]["caption"], "B")

    def test_tts_and_speaker_helpers_recognize_tags(self):
        from utility.speaking_marks import split_speaking_turns, strip_speaker_marks, speaker_ids_in_text

        turns = split_speaking_turns("<1s> 心里话 <2> 对你说 <0.5> 再等一下")
        self.assertEqual(turns[0], (1, "心里话"))
        self.assertEqual(turns[1][0], 2)
        self.assertIn("<0.5>", turns[1][1])
        spoken = " ".join(t[1] for t in turns)
        self.assertNotIn("自言自语", spoken)
        self.assertFalse(spoken.strip().startswith("s"))
        self.assertEqual(strip_speaker_marks("<1s>（自言自语）心里话"), "心里话")
        self.assertEqual(speaker_ids_in_text("<1s> a <2> b"), [1, 2])


    def test_new_project_defers_split_until_image_save(self):
        pm = Path(ROOT, "project_manager.py").read_text(encoding="utf-8")
        wf = Path(ROOT, "magic_workflow.py").read_text(encoding="utf-8")
        images = Path(ROOT, "gui/workflow/wf_images.py").read_text(encoding="utf-8")
        flows = Path(ROOT, "gui/workflow/wf_prompt_flows.py").read_text(encoding="utf-8")
        create = pm.split("def create_new_project", 1)[1].split("\n    def ", 1)[0]
        self.assertNotIn("expand_scenes_for_new_project", create)
        self.assertNotIn("apply_monologue_split_after_image(", create)
        self.assertNotIn("expand_scenes_for_new_project", wf)
        helper = images.split("def _finish_monologue_split_after_image", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("apply_monologue_split_after_image", helper)
        replace = images.split("def _replace_current_clip_image_from_pil", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("defer_monologue_split", replace)
        self.assertIn("_finish_monologue_split_after_image", replace)
        self.assertIn("if not defer_monologue_split", replace)
        batch = flows.split("def _run_picture_batch", 1)[1]
        apply = batch.split("def apply(scene, img, label)", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("defer_monologue_split=bool(remix_visual)", apply)
        self.assertIn("pending_split", apply)
        qremix = batch.split("def queue_remix", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("_finish_monologue_split_after_image", qremix)
        avis = batch.split("def apply_visual", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("finally:", avis)
        self.assertIn("_finish_monologue_split_after_image", avis)
        rwork = batch.split("def remix_worker", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("_finish_monologue_split_after_image", rwork)


def _install_pm_stub(media_dir: str):
    import types
    existing = sys.modules.get("project_manager")
    if existing is not None and getattr(existing, "_slot_test_stub", False):
        existing._slot_media_dir = media_dir
        existing._slot_n = 0
        return existing
    pm = types.ModuleType("project_manager")
    pm._slot_test_stub = True
    pm._slot_media_dir = media_dir
    pm._slot_n = 0

    def allocate_scene_media_path(scene, media_type, media_postfix):
        pm._slot_n += 1
        name = f"{media_type}_{scene.get('id', 0)}_{pm._slot_n}{media_postfix}"
        return os.path.join(pm._slot_media_dir, name)

    pm.allocate_scene_media_path = allocate_scene_media_path
    sys.modules["project_manager"] = pm
    return pm


class MonologueSplitAfterImageTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="mono_split_")
        self.media = os.path.join(self.tmp, "media")
        os.makedirs(self.media)
        _install_pm_stub(self.media)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _scene_with_images(self, speaking, *, sid=10100, cover=True):
        from utility.scene_image_slots import COVER_SEED_SLOTS, mark_cover_origin

        scene = {
            "id": sid,
            "caption": "四小时换一小时",
            "visual": "深夜书房",
            "actor": "人物1:man/mature/chinese/阿哲",
            "speaking": speaking,
            "clip": os.path.join(self.tmp, "full_speech.mp4"),
            "clip_audio": os.path.join(self.tmp, "full_speech.wav"),
            "speaking_timing": {"text": speaking},
        }
        for slot in COVER_SEED_SLOTS:
            path = os.path.join(self.media, f"src_{sid}_{slot}.webp")
            with open(path, "wb") as f:
                f.write(("IMG-%s-%s" % (slot, sid)).encode())
            scene[slot] = path
        if cover:
            mark_cover_origin(scene)
        return scene

    def test_image_once_splits_two_independent_scenes(self):
        from utility.speaking_marks import (
            MONOLOGUE_SPLIT_DONE,
            MONOLOGUE_SPLIT_KEY,
            apply_monologue_split_after_image,
        )
        from utility.scene_image_slots import COVER_SEED_SLOTS, scene_has_frozen_zero_last

        speaking = "<1s> 跟朋友吃了顿饭。<2> 你今天怎么这么累？"
        scene = self._scene_with_images(speaking)
        sibling_jobs = self._scene_with_images("<1> 下一场。", sid=10200)
        scenes = [scene, sibling_jobs]
        out = apply_monologue_split_after_image(scenes, scene, next_id=10300)
        self.assertIsNotNone(out)
        self.assertEqual(len(scenes), 3)
        self.assertIs(scenes[0], scene)
        self.assertIs(scenes[2], sibling_jobs)
        self.assertTrue(scene["speaking"].startswith("<1s>"))
        self.assertIn("<2>", out["speaking"])
        self.assertEqual(scene["caption"], out["caption"])
        self.assertEqual(scene["visual"], out["visual"])
        self.assertEqual(scene["actor"], out["actor"])
        self.assertEqual(scene[MONOLOGUE_SPLIT_KEY], MONOLOGUE_SPLIT_DONE)
        self.assertEqual(out[MONOLOGUE_SPLIT_KEY], MONOLOGUE_SPLIT_DONE)
        self.assertEqual(out["id"], 10300)
        self.assertNotIn("clip", out)
        self.assertNotIn("clip_audio", out)
        self.assertNotIn("speaking_timing", out)
        self.assertNotIn("speaking_timing", scene)
        self.assertNotIn("clip", scene)
        self.assertNotIn("clip_audio", scene)
        self.assertTrue(scene_has_frozen_zero_last(scene))
        self.assertTrue(scene_has_frozen_zero_last(out))
        last_src = scene["zero_image_last"]
        last_new = out["zero_image_last"]
        self.assertNotEqual(os.path.abspath(last_src), os.path.abspath(last_new))
        self.assertEqual(Path(last_src).read_bytes(), Path(last_new).read_bytes())
        self.assertNotEqual(
            (os.stat(last_src).st_dev, os.stat(last_src).st_ino),
            (os.stat(last_new).st_dev, os.stat(last_new).st_ino),
        )
        for slot in COVER_SEED_SLOTS:
            a, b = scene[slot], out[slot]
            self.assertTrue(os.path.isfile(a) and os.path.isfile(b))
            self.assertNotEqual(os.path.abspath(a), os.path.abspath(b))
            self.assertEqual(Path(a).read_bytes(), Path(b).read_bytes())
        self.assertEqual(sibling_jobs["speaking"], "<1> 下一场。")
        self.assertNotIn(MONOLOGUE_SPLIT_KEY, sibling_jobs)

    def test_retries_do_not_duplicate_and_failure_leaves_untouched(self):
        from utility.speaking_marks import apply_monologue_split_after_image
        import utility.scene_image_slots as slots

        speaking = "<2> 先坐下。<1s> 原来如此。"
        scene = self._scene_with_images(speaking)
        scenes = [scene]
        first = apply_monologue_split_after_image(scenes, scene, next_id=20000)
        self.assertIsNotNone(first)
        self.assertEqual(len(scenes), 2)
        again = apply_monologue_split_after_image(scenes, scene, next_id=20100)
        self.assertIsNone(again)
        self.assertEqual(len(scenes), 2)

        doomed = self._scene_with_images("<1s> 想一下。<2> 你在吗？", sid=30000)
        doomed_list = [doomed]
        frozen_speaking = doomed["speaking"]
        real = slots.clone_image_slots

        def boom(*a, **k):
            raise RuntimeError("copy fail")

        slots.clone_image_slots = boom
        try:
            self.assertIsNone(apply_monologue_split_after_image(doomed_list, doomed, next_id=30100))
        finally:
            slots.clone_image_slots = real
        self.assertEqual(doomed_list, [doomed])
        self.assertEqual(doomed["speaking"], frozen_speaking)
        self.assertNotIn("monologue_split", doomed)

    def test_invalid_and_pure_remain_one(self):
        from utility.speaking_marks import apply_monologue_split_after_image

        interior = self._scene_with_images("<1> 你好。<2s> 夹在中间。<1> 还在。", sid=40100)
        both = self._scene_with_images("<1s> 头。<2> 中。<1s> 尾。", sid=40200)
        pure = self._scene_with_images("<1s> 我一个人想了很久。", sid=40300)
        scenes = [interior, both, pure]
        self.assertIsNone(apply_monologue_split_after_image(scenes, interior, next_id=50000))
        self.assertIsNone(apply_monologue_split_after_image(scenes, both, next_id=50100))
        self.assertIsNone(apply_monologue_split_after_image(scenes, pure, next_id=50200))
        self.assertEqual(len(scenes), 3)
        self.assertEqual(interior["speaking"], "<1> 你好。<2s> 夹在中间。<1> 还在。")
        self.assertEqual(both["speaking"], "<1s> 头。<2> 中。<1s> 尾。")
        self.assertEqual(pure["speaking"], "<1s> 我一个人想了很久。")

    def test_no_image_yet_does_not_split(self):
        from utility.speaking_marks import apply_monologue_split_after_image

        scene = {
            "id": 60100,
            "caption": "还没出图",
            "visual": "空",
            "actor": "人物1:man",
            "speaking": "<1s> 先想一下。<2> 你在吗？",
        }
        scenes = [scene]
        self.assertIsNone(apply_monologue_split_after_image(scenes, scene, next_id=60200))
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scene["speaking"], "<1s> 先想一下。<2> 你在吗？")
        self.assertNotIn("monologue_split", scene)

    def test_remix_then_split_mirrors_authored_fields_and_leaves_batch_neighbor(self):
        """Cover-extract order: image once, remix once, then split.

        Both children get the remixed visual/actor (and other authored
        metadata). The next original batch job stays the same object,
        unsplit, so it is still processed exactly once.
        """
        from utility.speaking_marks import (
            MONOLOGUE_SPLIT_DONE,
            MONOLOGUE_SPLIT_KEY,
            apply_monologue_split_after_image,
            scene_monologue_split_done,
            split_speaking_pair,
        )
        from utility.scene_image_slots import scene_has_frozen_zero_last

        speaking = "<1s> 跟朋友吃了顿饭。<2> 你今天怎么这么累？"
        scene = self._scene_with_images(speaking)
        neighbor = self._scene_with_images("<1> 下一场对白。", sid=10200)
        scenes = [scene, neighbor]
        # Image write happened on the still-unsplit original (no split yet).
        self.assertFalse(scene_monologue_split_done(scene))
        self.assertIsNotNone(split_speaking_pair(scene["speaking"]))
        authored = {
            "caption": scene["caption"],
            "visual": "remix后的深夜书房，台灯更暖",
            "actor": "人物1:man/mature/chinese/阿哲（衬衫微皱）",
            "visual_before_remix": scene["visual"],
            "actor_before_remix": scene["actor"],
        }
        scene.update(authored)
        out = apply_monologue_split_after_image(scenes, scene, next_id=10300)
        self.assertIsNotNone(out)
        self.assertEqual(len(scenes), 3)
        self.assertIs(scenes[0], scene)
        self.assertIs(scenes[2], neighbor)
        self.assertTrue(scene["speaking"].startswith("<1s>"))
        self.assertIn("<2>", out["speaking"])
        for key, value in authored.items():
            self.assertEqual(scene[key], value)
            self.assertEqual(out[key], value)
        self.assertEqual(scene[MONOLOGUE_SPLIT_KEY], MONOLOGUE_SPLIT_DONE)
        self.assertEqual(out[MONOLOGUE_SPLIT_KEY], MONOLOGUE_SPLIT_DONE)
        self.assertTrue(scene_has_frozen_zero_last(scene))
        self.assertTrue(scene_has_frozen_zero_last(out))
        self.assertNotEqual(
            os.path.abspath(scene["zero_image_last"]),
            os.path.abspath(out["zero_image_last"]),
        )
        self.assertEqual(neighbor["speaking"], "<1> 下一场对白。")
        self.assertEqual(neighbor["visual"], "深夜书房")
        self.assertNotIn(MONOLOGUE_SPLIT_KEY, neighbor)
        again = apply_monologue_split_after_image(scenes, neighbor, next_id=10400)
        self.assertIsNone(again)
        self.assertEqual(len(scenes), 3)
        self.assertIs(scenes[2], neighbor)



if __name__ == "__main__":
    unittest.main()
