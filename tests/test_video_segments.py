"""t370u: offline tests for dynamic video segments (<Ns> / manual <s>) at 生场视频 time."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class SegmentParseTest(unittest.TestCase):
    def test_manual_s_before_n_splits(self):
        from utility.speaking_marks import speaking_segments

        text = "<1> 一。<2> 二。<s><1> 三。<2> 四。<1> 五。<s> <2> 六。<1> 七。"
        self.assertEqual(speaking_segments(text), [
            "<1> 一。 <2> 二。", "<1> 三。 <2> 四。 <1> 五。", "<2> 六。 <1> 七。"])

    def test_ns_at_start_and_end_are_own_segments(self):
        from utility.speaking_marks import speaking_segments

        self.assertEqual(speaking_segments("<1s> 我怎么又这样。<2> 你累了？<1> 还好。"),
                         ["<1s> 我怎么又这样。", "<2> 你累了？ <1> 还好。"])
        self.assertEqual(speaking_segments("<2> 先坐下。<1> 好。<1s> 原来如此。<1s> 再想想。"),
                         ["<2> 先坐下。 <1> 好。", "<1s> 原来如此。 <1s> 再想想。"])
        # both ends and with a manual cut in the middle
        self.assertEqual(len(__import__("utility.speaking_marks", fromlist=["x"]).speaking_segments(
            "<1s> a <2> b <s><1> c <1s> d")), 4)

    def test_no_marks_one_segment(self):
        from utility.speaking_marks import speaking_segment_count, speaking_segments

        self.assertEqual(speaking_segment_count("<1> 你好。<2> 好。"), 1)
        self.assertEqual(speaking_segment_count(""), 0)
        self.assertEqual(speaking_segments("没有标记的一句"), ["<1> 没有标记的一句"])
        # a leading <s> splits nothing
        self.assertEqual(speaking_segment_count("<s><1> a <2> b"), 1)
        self.assertEqual(speaking_segment_count("<1> a <s>"), 1)

    def test_mid_turn_s_keeps_speaker(self):
        from utility.speaking_marks import speaking_segments

        self.assertEqual(speaking_segments("<2> 前半句。<s> 后半句。<1> 好。"),
                         ["<2> 前半句。", "<2> 后半句。 <1> 好。"])

    def test_s_is_not_a_speaker_and_never_spoken(self):
        from utility.speaking_marks import (
            parse_speaking_turns,
            speaker_ids_in_text,
            split_speaking_turns,
            strip_speaker_marks,
        )

        text = "<1> 你好。<s><2> 你好呀。＜s＞<1> 再见。"
        self.assertEqual(speaker_ids_in_text(text), [1, 2])
        self.assertEqual(split_speaking_turns(text), [(1, "你好。"), (2, "你好呀。"), (1, "再见。")])
        self.assertTrue(all("<s>" not in t.text and "＜s＞" not in t.text for t in parse_speaking_turns(text)))
        self.assertNotIn("s>", strip_speaker_marks(text))
        # TTS (voicebox_speech_service.split_speaking_turns) delegates to parse_speaking_turns
        with open(os.path.join(ROOT, "utility", "voicebox_speech_service.py"), encoding="utf-8") as f:
            tts = f.read().split("def split_speaking_turns", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("parse_speaking_turns(text)", tts)

    def test_format_round_trip_keeps_s(self):
        from utility.speaking_marks import format_speaking_turns, parse_speaking_turns

        out = format_speaking_turns(parse_speaking_turns("<1> a <s><2> b <1s> c"))
        self.assertEqual(out, "<1> a <s> <2> b <1s> c")
        self.assertEqual(format_speaking_turns(parse_speaking_turns(out)), out)

    def test_portrait_filter_ignores_s(self):
        from utility.actor_portrait_extract import speaking_actor_slots

        self.assertEqual(set(speaking_actor_slots({"speaking": "<1> a <s><3> b"}, 3)), {1, 3})


class SplitBookkeepingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="seg_")
        self.audio = os.path.join(self.tmp, "scene.wav")
        with open(self.audio, "wb") as f:
            f.write(b"WAV-FULL")
        self.cuts = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _clone_images(self, src, dst):
        for slot in ("clip_image", "zero_image_last"):
            if src.get(slot):
                dst[slot] = src[slot] + f".copy{dst['id']}"

    def _cut(self, path, start, length):
        out = os.path.join(self.tmp, f"cut_{len(self.cuts)}.wav")
        with open(out, "wb") as f:
            f.write(f"{start:.3f}+{length:.3f}".encode())
        self.cuts.append((round(start, 3), round(length, 3)))
        return out

    @staticmethod
    def _store(sc, key, ext, path):
        sc[key] = path

    def _scene(self, speaking, sections=None):
        sc = {"id": 300, "caption": "c", "visual": "v", "actor": "a", "speaking": speaking,
              "clip": os.path.join(self.tmp, "old.mp4"), "clip_audio": self.audio,
              "clip_image": "/img/start.webp", "zero_image_last": "/img/zl.webp", "episode": "e1"}
        if sections is not None:
            sc["speaking_timing"] = {"text": speaking, "sections": sections}
        return sc

    def _split(self, scenes, scene, total=10.0, next_id=10500):
        from utility.video_segments import split_first_segment

        return split_first_segment(scenes, scene, next_id=next_id, clone_images=self._clone_images,
                                   cut_audio=self._cut, audio_seconds=lambda p: total, store_media=self._store)

    def test_clone_inserted_before_with_first_segment_and_timing_cut(self):
        sp = "<1s> 想一想。<2> 你好。<1> 好啊。"
        secs = [{"speaker": 1, "start": 0.2, "end": 2.0, "text": "想一想。"},
                {"speaker": 2, "start": 2.4, "end": 5.0, "text": "你好。"},
                {"speaker": 1, "start": 5.2, "end": 9.0, "text": "好啊。"}]
        scene = self._scene(sp, secs)
        other = {"id": 400, "speaking": "<1> 下一场"}
        scenes = [other, scene]
        tok = self._split(scenes, scene)
        self.assertIsNotNone(tok)
        clone = tok["clone"]
        self.assertEqual([s.get("id") for s in scenes], [400, 10500, 300])
        self.assertIs(scenes[2], scene)
        self.assertEqual(clone["speaking"], "<1s> 想一想。")
        self.assertEqual(scene["speaking"], "<2> 你好。 <1> 好啊。")
        self.assertEqual(tok["cut_source"], "timing")
        self.assertAlmostEqual(tok["cut"], 2.2)
        self.assertEqual(self.cuts, [(0.0, 2.2), (2.2, 7.8)])
        self.assertNotEqual(clone["clip_audio"], scene["clip_audio"])
        self.assertNotIn("clip", clone)
        self.assertNotIn("clip", scene)
        self.assertEqual(clone["clip_image"], "/img/start.webp.copy10500")
        # rebased timing
        self.assertEqual(scene["speaking_timing"]["text"], scene["speaking"])
        self.assertEqual([(x["start"], x["end"]) for x in scene["speaking_timing"]["sections"]], [(0.2, 2.8), (3.0, 6.8)])
        self.assertEqual(clone["speaking_timing"]["sections"][0]["end"], 2.0)
        self.assertEqual(clone["video_segment_of"], 300)

    def test_repeated_split_until_last_segment(self):
        scene = self._scene("<1> a <2> b <s><1> c <s><2> d")
        scenes = [scene]
        t1 = self._split(scenes, scene, next_id=None)
        self.assertEqual(t1["cut_source"], "estimate")
        t2 = self._split(scenes, scene, total=6.0, next_id=None)
        self.assertIsNone(self._split(scenes, scene, next_id=None))  # last segment: no clone
        self.assertEqual([s["speaking"] for s in scenes], ["<1> a <2> b", "<1> c", "<2> d"])
        self.assertIs(scenes[-1], scene)
        self.assertIs(scenes[0], t1["clone"])
        self.assertIs(scenes[1], t2["clone"])
        self.assertEqual(len({s["id"] for s in scenes}), 3)

    def test_undo_restores_scene_and_removes_clone(self):
        from utility.video_segments import undo_first_segment

        sp = "<1> a <s><2> b"
        scene = self._scene(sp, [{"speaker": 1, "start": 0, "end": 1, "text": "a"},
                                 {"speaker": 2, "start": 1, "end": 2, "text": "b"}])
        before = dict(scene)
        scenes = [scene]
        tok = self._split(scenes, scene, total=2.0)
        self.assertEqual(len(scenes), 2)
        self.assertTrue(undo_first_segment(scenes, tok))
        self.assertEqual(scenes, [scene])
        for key in ("speaking", "speaking_timing", "clip_audio", "clip"):
            self.assertEqual(scene.get(key), before.get(key))
        self.assertNotIn("monologue_split", scene)

    def test_collapsed_sections_are_split_by_weight(self):
        from utility.speaking_marks import parse_speaking_turns
        from utility.video_segments import turn_spans_from_timing

        sp = "<1> 一二三 <s><1> 四五六 <2> 七"
        sc = {"speaking": sp, "speaking_timing": {"text": sp, "sections": [
            {"speaker": 1, "start": 0.0, "end": 4.0, "text": "一二三四五六"},
            {"speaker": 2, "start": 4.0, "end": 5.0, "text": "七"}]}}
        spans = turn_spans_from_timing(sc, parse_speaking_turns(sp))
        self.assertEqual([round(a, 2) for a, _b in spans], [0.0, 2.0, 4.0])

    def test_no_audio_no_cut_calls(self):
        scene = self._scene("<1> a <s><2> b")
        scene.pop("clip_audio")
        scenes = [scene]
        tok = self._split(scenes, scene)
        self.assertIsNotNone(tok)
        self.assertEqual(self.cuts, [])
        self.assertNotIn("clip_audio", tok["clone"])

    def test_clone_image_failure_leaves_scene_untouched(self):
        from utility.video_segments import split_first_segment

        scene = self._scene("<1> a <s><2> b")
        snap = dict(scene)
        scenes = [scene]

        def boom(_s, _d):
            raise OSError("disk full")

        self.assertIsNone(split_first_segment(scenes, scene, clone_images=boom))
        self.assertEqual(scenes, [scene])
        self.assertEqual(scene, snap)


class LastFrameUpscaleTest(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        self.tmp = tempfile.mkdtemp(prefix="seg_up_")
        self.frame = os.path.join(self.tmp, "last.png")
        Image.new("RGB", (1312, 736), (10, 20, 30)).save(self.frame)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_upscale_success_fits_target_and_passes_style(self):
        from PIL import Image

        from utility.video_segments import enhance_last_frame

        seen = {}

        def up(path, target, style):
            seen.update(path=path, target=target, style=style)
            return Image.new("RGB", (1920, 1088), (1, 2, 3))

        out, ok, _note = enhance_last_frame(self.frame, style="三维卡通 (Pixar-Art-Cartoon)", upscale=up)
        self.assertTrue(ok)
        self.assertEqual(seen["target"], (1920, 1080))
        self.assertEqual(seen["style"], "三维卡通 (Pixar-Art-Cartoon)")
        with Image.open(out) as im:
            self.assertEqual(im.size, (1920, 1080))
        os.remove(out)

    def test_comfy_down_falls_back_to_raw_frame(self):
        from utility.video_segments import enhance_last_frame

        def down(*_a):
            raise ConnectionError("ComfyUI 192.168.1.227:8188 refused")

        out, ok, note = enhance_last_frame(self.frame, style="写实", upscale=down)
        self.assertFalse(ok)
        self.assertEqual(out, self.frame)
        self.assertIn("refused", note)

    def test_comfy_upscale_prompt_carries_style(self):
        import config_prompt as cp

        base_pos, base_neg = cp.build_comfy_upscale_prompt((1920, 1080), backend="moss")
        pos, neg = cp.build_comfy_upscale_prompt((1920, 1080), backend="moss", style="三维卡通 (Pixar-Art-Cartoon)")
        self.assertIn("Keep the original art style.", base_pos)
        self.assertIn("3D animation", pos)
        self.assertIn("never turns photorealistic", pos)
        self.assertIn("photorealistic", neg)
        self.assertTrue(neg.startswith(base_neg))
        rpos, rneg = cp.build_comfy_upscale_prompt((1920, 1080), backend="moss", style="写实 (Realistic)")
        self.assertNotIn("never turns photorealistic", rpos)
        self.assertEqual(rneg, base_neg)


class WiringTest(unittest.TestCase):
    def _src(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_creation_split_disabled_by_default(self):
        # other test modules swap a stub ``config`` into sys.modules, so read the source
        cfg = self._src("config.py")
        self.assertIn('SPLIT_S_SCENES_AT_CREATION = _env("SPLIT_S_SCENES_AT_CREATION", "0")', cfg)
        helper = self._src("gui/workflow/wf_images.py").split("def _finish_monologue_split_after_image", 1)[1]
        helper = helper.split("\n    def ", 1)[0]
        self.assertIn('if getattr(_cfg_split, "SPLIT_S_SCENES_AT_CREATION", False):', helper)

    def test_dialog_and_flow_hooks(self):
        dlg = self._src("gui/video_prompt_dialog.py")
        self.assertIn('on_episode_submit(single=True)', dlg)
        self.assertIn('episode["split"](target)', dlg)
        self.assertIn('_seg_start["path"]', dlg)
        self.assertIn("not single and not _seg_scenes", dlg)
        flows = self._src("gui/workflow/wf_prompt_flows.py")
        for key in ('"segments": self._video_segment_count', '"split": self._split_video_segment',
                    '"unsplit": self._undo_video_segment', '"chain": self._chain_video_segment',
                    "write_chained_next_zero_image_last(scene, path)", "vs.moss_upscale("):
            self.assertIn(key, flows)

    def test_segment_mark_never_in_video_prompt(self):
        import config_prompt as cp

        scene = {"id": 1, "caption": "c", "visual": "客厅", "actor": "人物1:woman/young/chinese/小美\n人物2:man/young/chinese/阿哲",
                 "speaking": "<1> 你好。<s><2> 你好呀。"}
        p = cp.build_video_flow_prompt(frames="one", background="keep", evolve="keep", visual_style="三维卡通",
                                       scene_content=[scene], language="zh", host_narrator="")
        self.assertNotIn("<s>", p)


if __name__ == "__main__":
    unittest.main()
