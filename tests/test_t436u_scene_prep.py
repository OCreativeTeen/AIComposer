"""t436u 阶段 3：建项目时整理场景（utility/scene_prep）：Strata 改写视觉 → 讲话超过 115 字按句拆 →
拆开的几段一起改写（连贯）→ 视频来源每段取自己的中间帧 → 写分镜 shot。Strata 用假的。"""
import os
import pathlib
import tempfile
import unittest

from tests.test_video_speaker_semantics import _install_stubs

_install_stubs()

from utility import scene_prep as sp  # noqa: E402
from utility.visual_remix import parse_split_group_visuals  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
LONG = "<1> " + "我们今天来聊一聊这个问题。" * 6 + "<2> " + "好的，没问题，我听着呢。" * 5  # 60 + 57 = 117


class FakeStrata:
    def __init__(self, fail=False, group=None):
        self.calls = []
        self.fail = fail
        self.group = group

    def remix_full(self, visual, image, *, actor_text, language_label, speaking):
        self.calls.append(("full", image))
        if self.fail:
            raise RuntimeError("Strata 连不上")
        return {"visual": "看图改写：" + visual, "actor": actor_text + "（穿红衣）"}

    def remix_text(self, visual, *, names, language_label, speaking):
        self.calls.append(("text", tuple(names)))
        if self.fail:
            raise RuntimeError("Strata 连不上")
        return "按讲话改写：" + visual

    def remix_group(self, visual, parts, *, names, language_label, image_path):
        self.calls.append(("group", len(parts)))
        if self.group is not None:
            return self.group
        return [f"第{i}段动作，接着上一段：{visual}" for i in range(1, len(parts) + 1)]


class UnitsTest(unittest.TestCase):
    def test_units(self):
        self.assertEqual(sp.speaking_units("<1> 你好，世界！ <0.5> Hello world."), 4 + 4)
        self.assertEqual(sp.speaking_units(LONG), 117)

    def test_shot(self):
        self.assertEqual(sp.shot_label(2, 3), "2-3")
        self.assertEqual(sp.parse_shot("2-3"), (2, 3))
        self.assertIsNone(sp.parse_shot("4-3"))
        self.assertIsNone(sp.parse_shot(""))


class SplitTextTest(unittest.TestCase):
    def test_split_balanced_with_marks(self):
        parts = sp.split_speaking_text(LONG)
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(sp.speaking_units(p) <= 115 for p in parts))
        self.assertEqual(sum(sp.speaking_units(p) for p in parts), 117)
        self.assertTrue(parts[0].startswith("<1> "))
        self.assertRegex(parts[1], r"^<\d> ")

    def test_short_unchanged(self):
        self.assertEqual(sp.split_speaking_text("<1> 你好。"), ["<1> 你好。"])

    def test_scene_times_interpolated(self):
        scene = {"caption": "A", "speaking": LONG, "start": 10.0, "end": 40.0, "actor": "人物1：x"}
        parts = sp.split_scene_by_text(scene)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["start"], 10.0)
        self.assertEqual(parts[-1]["end"], 40.0)
        self.assertEqual(parts[0]["end"], parts[1]["start"])
        self.assertEqual({p["caption"] for p in parts}, {"A"})

    def test_scene_without_end(self):
        parts = sp.split_scene_by_text({"speaking": LONG, "start": 5})
        self.assertEqual(parts[0]["start"], 5)
        self.assertNotIn("start", parts[1])

    def test_split_scenes_with_transcript(self):
        line = "这是一句二十个字左右的测试句子用来看看分场效果"
        tr = "\n".join(f"[00:00:{i * 2:04.1f}] {'<1> ' if i == 0 else ''}{line}。" for i in range(12))
        scenes = [{"caption": "A", "start": 0, "end": 24.0, "speaking": "x"}]
        from utility.media_transcript import apply_verbatim_speaking

        apply_verbatim_speaking(scenes, tr)
        final, groups = sp.split_scenes(scenes, tr)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], 0)
        self.assertEqual(len(final), 3)
        self.assertEqual(final[0]["start"], 0)
        self.assertEqual(final[-1]["end"], 24.0)


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.img = os.path.join(self.tmp, "a.png")
        pathlib.Path(self.img).write_bytes(b"x")

    def _scenes(self):
        return [
            {"caption": "A", "visual": "两人坐在客厅里说话，窗外下着雨。", "speaking": "<1> 你好。", "actor": "人物1：甲",
             "ref_images": [{"path": self.img, "source": "pdf"}]},
            {"caption": "B", "visual": "他慢慢走到窗边看着外面的街道。", "speaking": LONG, "actor": "人物1：甲 | 人物2：乙"},
        ]

    def test_full_run(self):
        src = self._scenes()
        fake = FakeStrata()
        out, rep = sp.prepare_scenes(src, strata=fake, log=lambda *_: None)
        self.assertEqual(len(src), 2)  # 输入不改
        self.assertNotIn("shot", src[0])
        self.assertEqual(len(out), 3)
        self.assertEqual([s["shot"] for s in out], ["1-1", "1-2", "2-2"])
        self.assertEqual(out[0]["visual"], "看图改写：两人坐在客厅里说话，窗外下着雨。")
        self.assertEqual(out[0]["visual_before_remix"], "两人坐在客厅里说话，窗外下着雨。")
        self.assertEqual(out[0]["actor"], "人物1：甲（穿红衣）")
        self.assertEqual(out[0]["actor_before_remix"], "人物1：甲")
        self.assertTrue(out[1]["visual"].startswith("第1段动作"))
        self.assertTrue(out[2]["visual"].startswith("第2段动作"))
        self.assertEqual(out[1]["visual_before_remix"], "他慢慢走到窗边看着外面的街道。")
        self.assertEqual(out[1]["caption"], out[2]["caption"])
        self.assertEqual(out[1]["actor"], out[2]["actor"])
        self.assertTrue(all(sp.speaking_units(s["speaking"]) <= 115 for s in out))
        self.assertEqual([c[0] for c in fake.calls], ["full", "text", "group"])
        self.assertEqual((rep["remixed"], rep["split"], rep["added"], rep["group_remixed"]), (2, 1, 1, 1))

    def test_bad_group_keeps_parent_visual(self):
        out, rep = sp.prepare_scenes(self._scenes(), strata=FakeStrata(group=["只有一段"]), log=lambda *_: None)
        self.assertEqual(out[1]["visual"], out[2]["visual"])
        self.assertTrue(out[1]["visual"].startswith("按讲话改写"))
        self.assertEqual(rep["group_remixed"], 0)

    def test_strata_failure(self):
        with self.assertRaises(sp.PrepFailed):
            sp.prepare_scenes(self._scenes(), strata=FakeStrata(fail=True), log=lambda *_: None)

    def test_cancel(self):
        with self.assertRaises(sp.PrepCancelled):
            sp.prepare_scenes(self._scenes(), strata=FakeStrata(), cancel=lambda: True, log=lambda *_: None)

    def test_rerun_keeps_shots(self):
        out, _ = sp.prepare_scenes(self._scenes(), strata=FakeStrata(), log=lambda *_: None)
        again, rep = sp.prepare_scenes(out, strata=FakeStrata(), log=lambda *_: None)
        self.assertEqual([s["shot"] for s in again], ["1-1", "1-2", "2-2"])
        self.assertEqual(rep["split"], 0)
        self.assertEqual(again[0]["visual_before_remix"], "两人坐在客厅里说话，窗外下着雨。")  # 最早的原文

    def test_video_parts_get_own_frames(self):
        video = os.path.join(self.tmp, "v.mp4")
        pathlib.Path(video).write_bytes(b"x")
        old = os.path.join(self.tmp, "old.png")
        scenes = self._scenes()
        scenes[1].update({"start": 0.0, "end": 30.0, "ref_images": [{"path": old, "source": "video"}]})

        def picker(path, parts, out_dir, log=print):
            return {i: [{"path": os.path.join(self.tmp, f"f{i}.png"), "source": "video", "time": 1.0 + i}]
                    for i in range(len(parts))}

        out, rep = sp.prepare_scenes(scenes, strata=FakeStrata(), source_kind="video", source_path=video,
                                     frame_picker=picker, log=lambda *_: None)
        self.assertEqual(rep["frames"], 2)
        self.assertEqual(out[1]["ref_images"][0]["path"], os.path.join(self.tmp, "f0.png"))
        self.assertEqual(out[2]["ref_images"][0]["path"], os.path.join(self.tmp, "f1.png"))
        self.assertEqual(out[2]["ref_images"][1]["path"], old)


class GroupParseTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_split_group_visuals('{"visuals": ["a", "b"]}', 2), ["a", "b"])
        self.assertEqual(parse_split_group_visuals('好的：{"visuals": ["a"]}', 1), ["a"])
        with self.assertRaises(Exception):
            parse_split_group_visuals('{"visuals": ["a"]}', 2)
        with self.assertRaises(Exception):
            parse_split_group_visuals('{"visuals": ["a", ""]}', 2)


class WiringTest(unittest.TestCase):
    def test_runner_and_buttons(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("_t436u_runner", ROOT / "gui" / "dl" / "scene_prep_runner.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # 不经过 gui/__init__（盒子上没有 tkinter）
        scene_list_of = mod.scene_list_of

        self.assertEqual(scene_list_of('[{"a": 1}, 2]'), [{"a": 1}])
        self.assertEqual(scene_list_of("bad"), [])
        dlg = (ROOT / "gui" / "dl" / "channel_videos_dialog.py").read_text(encoding="utf-8")
        self.assertLess(dlg.index("run_scene_prep_modal(parent, _sc_list"), dlg.index("create_project_with_initial_raw("))
        ed = (ROOT / "gui" / "dl" / "scene_editor.py").read_text(encoding="utf-8")
        self.assertIn('text="整理场景"', ed)
        prep = (ROOT / "utility" / "scene_prep.py").read_text(encoding="utf-8")
        self.assertIn("split_long_transcript_scenes(", prep)


if __name__ == "__main__":
    unittest.main()
