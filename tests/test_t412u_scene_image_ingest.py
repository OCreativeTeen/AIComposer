# -*- coding: utf-8 -*-
"""t412u: 拖进 / 粘贴 / 换上的 clip 图另存到 media/<集>/<本集第几场>_<序号>，序号接在这一场最大的后面，放到 ref_images 最前面。"""
import ast
import os
import pathlib
import shutil
import tempfile
import textwrap
import types
import unittest

from utility import project_ref_images as pri

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _method(rel, name, ns):
    src = _src(rel)
    node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(textwrap.dedent(ast.get_source_segment(src, node)), ns)
    return ns[name]


def _touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pathlib.Path(path).write_bytes(data)
    return os.path.abspath(path)


class NextIndexTest(unittest.TestCase):
    def test_max_plus_one(self):
        with tempfile.TemporaryDirectory() as d:
            for k in (1, 2, 3, 5):
                _touch(os.path.join(d, f"2_{k}.png"))
            _touch(os.path.join(d, "12_9.png"))       # 别的场景
            _touch(os.path.join(d, "2.webp"))         # 编号页图
            path, k = pri.next_scene_image_path(d, 2, ".WEBP")
            self.assertEqual((os.path.basename(path), k), ("2_6.webp", 6))
            self.assertEqual(os.path.basename(pri.next_scene_image_path(d, 7, ".png")[0]), "7_1.png")
            self.assertEqual(os.path.basename(pri.next_scene_image_path(os.path.join(d, "none"), 1, ".png")[0]), "1_1.png")


class _WF:
    def __init__(self, media, scenes):
        self.media, self.scenes = media, scenes

    def scene_group(self, s):
        return str(s.get("episode") or "1")

    def episode_media_dir(self, ep):
        return os.path.join(self.media, ep)


class AddToLibraryTest(unittest.TestCase):
    def _bind(self, wf):
        ns = {"os": os, "shutil": shutil}
        add = _method("magic_workflow.py", "add_scene_image_to_library", ns)
        num = _method("magic_workflow.py", "scene_number_in_episode", {})
        wf.scene_number_in_episode = lambda s: num(wf, s)
        return lambda *a, **k: add(wf, *a, **k)

    def test_copies_appends_index_and_goes_first(self):
        with tempfile.TemporaryDirectory() as d:
            media = os.path.join(d, "media")
            old1 = _touch(os.path.join(media, "1", "2_1.png"))
            _touch(os.path.join(media, "1", "2_5.png"))
            s1, s2, s3 = {"id": 1}, {"id": 2, "ref_images": [{"path": old1}], "episode_page": 4}, {"id": 3, "episode": "2"}
            wf = _WF(media, [s1, s2, s3])
            add = self._bind(wf)
            drop = _touch(os.path.join(d, "tmp", "drop.webp"), b"NEW")
            dest = add(s2, drop)
            self.assertEqual(dest, os.path.abspath(os.path.join(media, "1", "2_6.webp")))
            self.assertEqual(pathlib.Path(dest).read_bytes(), b"NEW")
            self.assertTrue(os.path.isfile(drop))                      # 原图不动
            self.assertEqual([pri.entry_path(e) for e in s2["ref_images"]], [dest, old1])
            self.assertEqual(s2["ref_images"][0]["source"], "drop")
            self.assertNotIn("episode_page", s2)
            # 再来一张：_7，仍放最前
            dest2 = add(s2, drop)
            self.assertEqual(os.path.basename(dest2), "2_7.webp")
            self.assertEqual(pri.entry_path(s2["ref_images"][0]), dest2)
            # 第 2 集第 1 场
            self.assertEqual(os.path.relpath(add(s3, drop), media).replace(os.sep, "/"), "2/1_1.webp")
            self.assertEqual(add(s1, os.path.join(d, "missing.png")), "")


class WiringTest(unittest.TestCase):
    def test_pool_clip_slot_image_routes_start_image(self):
        calls = []
        wf = types.SimpleNamespace(
            add_scene_image_to_library=lambda s, p: calls.append(("add", p)),
            write_scene_page_png=lambda s, p, tag_scene=True: calls.append(("page", p, tag_scene)),
        )
        fn = _method("gui/workflow/wf_pdf_episode.py", "_pool_clip_slot_image", {"os": os})
        with tempfile.TemporaryDirectory() as d:
            img = _touch(os.path.join(d, "a.webp"))
            gui = types.SimpleNamespace(workflow=wf)
            fn(gui, {}, "clip_image", img)
            fn(gui, {}, "clip_image_last", img)
            fn(gui, {}, "zero_image", img)
        self.assertEqual(calls, [("add", img), ("page", img, False)])

    def test_drop_paths_use_library(self):
        drop = _src("gui/workflow/wf_media_drop.py")
        self.assertNotIn("write_scene_page_png", drop)
        self.assertEqual(drop.count("self.workflow.add_scene_image_to_library("), 4)
        mw = _src("magic_workflow.py")
        rep = mw[mw.index("def replace_scene_image"):mw.index("def replace_scene_image") + 600]
        self.assertIn("self.add_scene_image_to_library(current_scene, image_path)", rep)
        # 拖放 / 粘贴 / 图片修改都走 _apply_image_paths_to_preview_slot 或 _pool_clip_slot_image
        imgs = _src("gui/workflow/wf_images.py")
        apply = imgs[imgs.index("def _apply_image_paths_to_preview_slot"):imgs.index("def display_image_on_canvas_for_track")]
        self.assertIn("self._pool_clip_slot_image(scene, image_type, file_path)", apply)

    def test_video_source_keeps_clip_after_drop(self):
        popups, calls = [], []
        fn = _method("gui/workflow/wf_pdf_episode.py", "_after_clip_image_changed", {
            "os": os, "get_file_path": lambda s, k: s.get(k) or "",
            "show_auto_close_popup": lambda *a, **k: popups.append(a[1]),
        })

        class Root:
            def after(self, _ms, f):
                f()

        with tempfile.TemporaryDirectory() as d:
            scene = {"clip_image": _touch(os.path.join(d, "c.webp")), "clip_audio": _touch(os.path.join(d, "a.wav"))}
            gui = types.SimpleNamespace(
                root=Root(),
                workflow=types.SimpleNamespace(scene_source_is_video=lambda: True),
                _offer_still_videos_after_pdf=lambda *a: calls.append("still"),
                _rebuild_silent_still_clip=lambda *a: calls.append("silent"),
            )
            fn(gui, scene, "x")
            self.assertEqual(calls, [])
            gui.workflow.scene_source_is_video = lambda: False
            fn(gui, scene, "x")
            self.assertEqual(calls, ["still"])


if __name__ == "__main__":
    unittest.main()
