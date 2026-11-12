# -*- coding: utf-8 -*-
"""t409u: 生成场景后按来源自动配图（PDF 抽图对场景 / 视频每场取中段一帧），建项目时用 ref_images 第一张。"""
import ast
import json
import os
import pathlib
import tempfile
import unittest

from utility import material_image_matcher as mim

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class TimeAndSpansTest(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(mim.parse_time(12), 12.0)
        self.assertEqual(mim.parse_time("83.5"), 83.5)
        self.assertEqual(mim.parse_time("01:23.5"), 83.5)
        self.assertEqual(mim.parse_time("[00:01:23.5]"), 83.5)
        self.assertIsNone(mim.parse_time(""))
        self.assertIsNone(mim.parse_time(None))
        self.assertIsNone(mim.parse_time(True))
        self.assertIsNone(mim.parse_time("abc"))

    def test_spans_fill_missing_end(self):
        scenes = [{"start": 0, "end": 10}, {"caption": "无时间"}, {"start": 10}, {"start": "00:00:30"}]
        self.assertEqual(mim.scene_spans(scenes, 50.0), [(0, 0.0, 10.0), (2, 10.0, 30.0), (3, 30.0, 50.0)])
        self.assertEqual(mim.scene_spans([{"start": 5, "end": 99}], 20.0), [(0, 5.0, 20.0)])
        self.assertEqual(mim.scene_spans([{"caption": "x"}]), [])


class FramePickTest(unittest.TestCase):
    def test_skips_dark_prefers_sharp_and_still(self):
        cands = [
            (0.35, 5.0, 900.0, 0.0),    # 黑场
            (0.45, 120.0, 300.0, 0.5),  # 清楚、静止
            (0.50, 120.0, 400.0, 20.0), # 更清楚但在转场
            (0.60, 120.0, 80.0, 0.0),   # 糊
        ]
        self.assertEqual(mim.choose_frame(cands), 1)
        self.assertIsNone(mim.choose_frame([(0.5, 3.0, 999.0, 0.0)]))
        # 一样清楚时越靠中间越好
        self.assertEqual(mim.choose_frame([(0.35, 100, 100, 0), (0.5, 100, 100, 0), (0.65, 100, 100, 0)]), 1)

    def test_extract_scene_frames_on_synthetic_video(self):
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as d:
            vid = os.path.join(d, "v.avi")
            w = cv2.VideoWriter(vid, cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 90))
            for i in range(60):  # 6 秒：前 3 秒一张图，后 3 秒另一张
                f = np.full((90, 160, 3), 40 if i < 30 else 200, np.uint8)
                cv2.putText(f, "A" if i < 30 else "B", (60, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5,
                            (255, 255, 255) if i < 30 else (0, 0, 0), 3)
                w.write(f)
            w.release()
            scenes = [{"start": 0, "end": 3}, {"caption": "没时间"}, {"start": 3}]
            out = mim.extract_scene_frames(vid, scenes, os.path.join(d, "out"), log=lambda *_: None)
            self.assertEqual(sorted(out), [0, 2])
            self.assertEqual(os.path.basename(out[0][0]["path"]), "scene_001.png")
            self.assertEqual(os.path.basename(out[2][0]["path"]), "scene_003.png")
            self.assertTrue(1.0 <= out[0][0]["time"] <= 2.0)
            self.assertTrue(4.0 <= out[2][0]["time"] <= 5.0)
            self.assertEqual(out[2][0]["source"], "video")
            img = cv2.imdecode(np.fromfile(out[2][0]["path"], np.uint8), cv2.IMREAD_GRAYSCALE)
            self.assertGreater(float(img.mean()), 120)  # 取到的是后一张（亮的）
            scene = {}
            mim.add_ref_images(scene, out[2])
            self.assertEqual(scene["ref_images"][0]["source"], "video")
            self.assertIn("time", scene["ref_images"][0])


class AutoAttachTest(unittest.TestCase):
    def _file(self, d, name):
        p = os.path.join(d, name)
        pathlib.Path(p).write_bytes(b"x")
        return p

    def test_route_by_source(self):
        with tempfile.TemporaryDirectory() as d:
            pdf, mp4 = self._file(d, "a.pdf"), self._file(d, "b.mp4")
            seen = []
            pdf_run = lambda path, src, scenes, **k: (seen.append(("pdf", src)) or {"images": [1], "matches": {0: ["i"]}})
            video_run = lambda path, scenes, **k: (seen.append(("video", path)) or {1: ["f"]})
            kw = dict(log=lambda *_: None, pdf_run=pdf_run, video_run=video_run)
            sc = [{"a": 1}, {"b": 2}]
            self.assertEqual(mim.auto_ref_matches("pdf", pdf, sc, **kw), {0: ["i"]})
            self.assertEqual(mim.auto_ref_matches("video", mp4, sc, **kw), {1: ["f"]})
            for kind in ("text", "audio", "infographic", ""):
                self.assertEqual(mim.auto_ref_matches(kind, mp4, sc, **kw), {})
            self.assertEqual(seen, [("pdf", "pdf"), ("video", mp4)])
            logs = []
            empty = lambda path, src, scenes, **k: {"images": [], "matches": {}}
            self.assertEqual(mim.auto_ref_matches("pdf", pdf, sc, log=logs.append, pdf_run=empty), {})
            self.assertTrue(any("没有图片" in x for x in logs))

    def test_start_auto_attach_commits_in_tk_thread(self):
        with tempfile.TemporaryDirectory() as d:
            mp4 = self._file(d, "b.mp4")
            scenes = [{"caption": "一", "start": 0}, {"caption": "二", "start": 5}]
            pending = []
            after = lambda ms, fn: pending.append(fn)
            editor = json.loads(json.dumps(scenes))
            commits = []
            frame = {"path": os.path.join(d, "scene_002.png"), "source": "video", "time": 7.5}
            ok = mim.start_auto_attach(after, "video", mp4, scenes, get_current=lambda: editor,
                                       commit=lambda cur, added: commits.append((cur, added)),
                                       log=lambda *_: None, matcher=lambda *a, **k: {1: [frame]}, thread=False)
            self.assertTrue(ok)
            self.assertEqual(commits, [])  # 只在 after 回调（Tk 线程）里写回
            while pending:
                pending.pop(0)()
            self.assertEqual(len(commits), 1)
            cur, added = commits[0]
            self.assertEqual(added, 1)
            self.assertIs(cur, editor)
            self.assertEqual(editor[1]["ref_images"][0]["time"], 7.5)
            self.assertNotIn("ref_images", scenes[1])  # 原来的列表不动
            for kind in ("text", "audio", "infographic"):
                self.assertFalse(mim.start_auto_attach(after, kind, mp4, scenes, get_current=list, commit=None))


class FirstRefImageTest(unittest.TestCase):
    def test_first_existing(self):
        with tempfile.TemporaryDirectory() as d:
            p2 = os.path.join(d, "p2.png")
            pathlib.Path(p2).write_bytes(b"x")
            scene = {"ref_images": [{"path": os.path.join(d, "gone.png")}, {"path": p2}, {"path": "z.png"}]}
            self.assertEqual(mim.first_ref_image(scene), os.path.abspath(p2))
            self.assertEqual(mim.first_ref_image({}), "")
            self.assertEqual(mim.first_ref_image({"ref_images": "bad"}), "")


def _method(src_rel, cls, name):
    tree = ast.parse(_src(src_rel))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return ast.get_source_segment(_src(src_rel), item)
    raise AssertionError(f"{cls}.{name} not found")


class ProjectCreationTest(unittest.TestCase):
    def _load(self, refresh):
        import textwrap
        import types

        ns = {"os": os, "refresh_scene_media": refresh,
              "project_manager": types.SimpleNamespace(SCENE_SOURCE_INFOGRAPHIC="infographic")}
        exec(textwrap.dedent(_method("magic_workflow.py", "MagicWorkflow", "_apply_ref_images_to_scenes")), ns)
        return ns["_apply_ref_images_to_scenes"]

    def test_first_ref_goes_to_clip_image_except_infographic(self):
        import types

        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "p003.png")
            pathlib.Path(img).write_bytes(b"x")
            calls = []
            fn = self._load(lambda scene, slot, ext, src, copy: calls.append((scene.get("id"), slot, ext, src, copy)))
            fake = types.SimpleNamespace(
                scenes=[{"id": 1, "ref_images": [{"path": img}]}, {"id": 2}, {"id": 3, "ref_images": [{"path": "gone"}]}],
                ffmpeg_processor=types.SimpleNamespace(resize_image_smart=lambda p: p + ".webp"),
                sync_project_ref_images=lambda **kw: 0,  # t410u: 复制进项目另有单测
            )
            for kind in ("pdf", "audio", "video", "text"):
                calls.clear()
                self.assertEqual(fn(fake, kind), 1)
                self.assertEqual(calls, [(1, "clip_image", ".webp", os.path.abspath(img) + ".webp", True)])
            calls.clear()
            self.assertEqual(fn(fake, "infographic"), 0)
            self.assertEqual(calls, [])

    def test_order_and_no_dialogs(self):
        mw = _src("magic_workflow.py")
        a = mw.index("self._apply_cover_media_to_scenes(scene_list)")
        b = mw.index("self._apply_ref_images_to_scenes(kind)")
        c = mw.index("self._apply_item_media_as_scene_clips()", b)
        self.assertTrue(a < b < c)  # 先定图，音频再用这张图合成 clip
        warn = _method("magic_workflow.py", "MagicWorkflow", "_source_warning")
        self.assertNotIn("messagebox", warn)
        for name in ("_apply_cover_media_to_scenes", "_apply_ref_images_to_scenes", "_apply_item_media_as_scene_clips",
                     "_apply_item_media_as_shared_zero"):
            body = _method("magic_workflow.py", "MagicWorkflow", name)
            self.assertNotIn("messagebox", body, name)
            self.assertNotIn("askchoice", body, name)
        clips = _method("magic_workflow.py", "MagicWorkflow", "_apply_item_media_as_scene_clips")
        self.assertIn('get_file_path(scene, "clip_image")', clips)  # 音频：clip = clip_image + 这一场的声音

    def test_generation_hook_wired(self):
        dl = _src("gui/downloader.py")
        self.assertIn("def _start_scene_auto_ref_images(", dl)
        i = dl.index("if not persist(video_detail, parent=parent):")
        self.assertIn("_start_scene_auto_ref_images(", dl[i:i + 600])
        self.assertIn("start_auto_attach(root.after", dl)
        se = _src("gui/dl/scene_editor.py")
        self.assertIn('get_scene_json=lambda: tx.get("1.0", tk.END)', se)


if __name__ == "__main__":
    unittest.main()
