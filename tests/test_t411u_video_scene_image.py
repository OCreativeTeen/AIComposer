# -*- coding: utf-8 -*-
"""t411u: 视频来源的场景用选的图（ref_images 第一张）当场景图；选图预览里去掉「写到本集结束」。"""
import ast
import os
import pathlib
import tempfile
import textwrap
import types
import unittest

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


class VideoCutKeepsRefImageTest(unittest.TestCase):
    def test_cut_does_not_overwrite_ref_image(self):
        with tempfile.TemporaryDirectory() as d:
            media = _touch(os.path.join(d, "src.mp4"))
            ref = _touch(os.path.join(d, "media", "1", "1_1.png"))
            ref3 = _touch(os.path.join(d, "media", "1", "3_1.png"))
            n = [0]

            def tmpfile(tag):
                n[0] += 1
                return _touch(os.path.join(d, f"{tag}_{n[0]}"))

            fp = types.SimpleNamespace(
                get_duration=lambda m: 10.0,
                trim_video=lambda m, s, e: tmpfile("clip.mp4"),
                extract_frame=lambda v, first: tmpfile("first.webp" if first else "last.webp"),
            )
            fa = types.SimpleNamespace(get_duration=lambda m: 10.0,
                                       extract_audio_from_video=lambda v, f: tmpfile("a.wav"))
            scenes = [
                {"id": 1, "start": 0, "end": 5, "clip_image": "REF1", "ref_images": [{"path": ref}]},
                {"id": 2, "start": 0, "end": 5, "clip_image": "DEFAULT"},          # 同一段（复用）、没有参考图
                {"id": 3, "start": 5, "clip_image": "REF3", "ref_images": [ref3]},
            ]
            writes = []

            def refresh(scene, slot, ext, src, copy=False):
                writes.append((scene["id"], slot))
                scene[slot] = src

            wf = types.SimpleNamespace(
                scenes=scenes, ffmpeg_processor=fp, ffmpeg_audio_processor=fa,
                _original_media_path=lambda: media,
                _scene_time_seconds=lambda v: None if v is None else float(v),
            )
            fn = _method("magic_workflow.py", "_apply_item_media_as_scene_clips",
                         {"os": os, "refresh_scene_media": refresh, "get_file_path": lambda s, k: s.get(k) or ""})
            fn(wf)
            self.assertEqual(scenes[0]["clip_image"], "REF1")
            self.assertEqual(scenes[2]["clip_image"], "REF3")
            self.assertIn("first.webp", os.path.basename(scenes[1]["clip_image"]))   # 没参考图的照旧用首帧
            for sid in (1, 2, 3):
                self.assertIn((sid, "clip"), writes)
                self.assertIn((sid, "clip_image_last"), writes)
            self.assertNotIn((1, "clip_image"), writes)
            self.assertNotIn((3, "clip_image"), writes)


class SourceKindTest(unittest.TestCase):
    def test_scene_source_is_video(self):
        pm = types.SimpleNamespace(SCENE_SOURCE_VIDEO="video")
        fn = _method("magic_workflow.py", "scene_source_is_video", {"project_manager": pm})
        self.assertTrue(fn(types.SimpleNamespace(_story_scene_source=lambda: ("video", ""))))
        self.assertFalse(fn(types.SimpleNamespace(_story_scene_source=lambda: ("pdf", "x.pdf"))))

        def boom():
            raise RuntimeError

        self.assertTrue(fn(types.SimpleNamespace(_story_scene_source=boom, _scene_source_kind="video")))


class PickerTest(unittest.TestCase):
    def test_no_write_to_end_button(self):
        src = _src("gui/workflow/wf_pdf_episode.py")
        body = src[src.index("def _open_pdf_page_review"):]
        body = body[body.index("dlg = tk.Toplevel"):]  # 跳过说明文字
        for gone in ("写到本集结束", "写到结束（跨集）", "_assign_forward", "_forward_hint", "forward_btn"):
            self.assertNotIn(gone, body, gone)
        self.assertIn("当前页 → 当前场景", body)

    def test_video_source_pick_keeps_video_clip(self):
        src = _src("gui/workflow/wf_pdf_episode.py")
        node = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "_assign_current")
        body = ast.get_source_segment(src, node)
        a = body.index("self.workflow.scene_source_is_video()")
        b = body.index("self._offer_still_videos_after_pdf(")
        self.assertLess(a, b)
        self.assertIn("return", body[a:b])


if __name__ == "__main__":
    unittest.main()
