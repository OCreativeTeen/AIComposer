"""t342u offline tests: importing / generating a scene video never touches clip_image.

Rules:
1. clip_image keeps its original (high-res) image; the video's first frame is not used.
2. The video's last frame goes to clip_image_last (and, for clip, a copy to the next
   scene's zero_image_last -- unchanged behaviour, covered in test_scene_image_slots).
3. zero_image is written only by 图片修改; video import / display never invents it.

GUI methods are pulled from source with ast; no tkinter, ffmpeg, providers or .env.
"""
from __future__ import annotations

import ast
import os
import shutil
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _method(rel: str, name: str, extra: dict):
    src = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {"os": os}
    ns.update(extra)
    exec(textwrap.dedent(ast.get_source_segment(src, node)), ns)  # noqa: S102
    return ns[name]


class _FP:
    def __init__(self, tmp):
        self.tmp = tmp
        self.calls = []

    def extract_frame(self, video, first):
        self.calls.append(bool(first))
        out = os.path.join(self.tmp, "first.webp" if first else "last.webp")
        Path(out).write_bytes(b"FIRST" if first else b"LAST")
        return out


class InstallClipFilesTest(unittest.TestCase):
    """wf_scene_structure._install_clip_files (挪动到前/后一场 installs re-cut clip videos)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t342_")
        self.writes = []

        def refresh(scene, key, ext, src=None, copy=False):
            self.writes.append(key)
            scene[key] = src
            return None, src

        self.fn = _method(
            "gui/workflow/wf_scene_structure.py",
            "_install_clip_files",
            {"refresh_scene_media": refresh, "get_file_path": lambda s, k: (s or {}).get(k) or ""},
        )
        self.fp = _FP(self.tmp)
        self.gui = types.SimpleNamespace(
            workflow=types.SimpleNamespace(ffmpeg_processor=self.fp),
            _backup_clip_to_scene_back=lambda scene: None,
        )
        self.video = os.path.join(self.tmp, "v.mp4")
        self.audio = os.path.join(self.tmp, "a.wav")
        Path(self.video).write_bytes(b"mp4")
        Path(self.audio).write_bytes(b"wav")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_keeps_clip_image_and_writes_only_last_frame(self):
        scene = {"clip_image": "/orig/highres.png", "zero_image": "/orig/zero.png"}
        self.fn(self.gui, scene, self.video, self.audio)
        self.assertEqual(scene["clip_image"], "/orig/highres.png")
        self.assertEqual(scene["zero_image"], "/orig/zero.png")
        self.assertNotIn("clip_image", self.writes)
        self.assertNotIn("zero_image", self.writes)
        self.assertIn("clip_image_last", self.writes)
        self.assertEqual(Path(scene["clip_image_last"]).read_bytes(), b"LAST")
        self.assertEqual(self.fp.calls, [False], "first frame must not even be extracted")

    def test_keep_images_skips_frames(self):
        scene = {"clip_image": "/orig/highres.png", "clip_image_last": "/orig/last.png"}
        self.fn(self.gui, scene, self.video, self.audio, keep_images=True)
        self.assertEqual(self.fp.calls, [])
        self.assertEqual(scene["clip_image_last"], "/orig/last.png")
        self.assertEqual(self.writes, ["clip", "clip_audio"])


class DisplayLazyFillTest(unittest.TestCase):
    """wf_images.display_image_on_canvas_for_track must not fill clip_image / zero_image from a video."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t342d_")
        self.writes = []

        def refresh(scene, key, ext, src=None, copy=False):
            self.writes.append(key)
            scene[key] = src
            return None, src

        self.fn = _method(
            "gui/workflow/wf_images.py",
            "display_image_on_canvas_for_track",
            {"refresh_scene_media": refresh, "print": lambda *a, **k: None},
        )
        self.fp = _FP(self.tmp)
        self.video = os.path.join(self.tmp, "v.mp4")
        Path(self.video).write_bytes(b"mp4")
        self.scene = {"clip": self.video, "zero": self.video, "clip_image": "/gone/missing.png"}
        canvas = types.SimpleNamespace(delete=lambda *a: None)
        self.gui = types.SimpleNamespace(
            current_scene_index=0,
            workflow=types.SimpleNamespace(ffmpeg_processor=self.fp, get_scene_by_index=lambda i: self.scene),
            clip_image_canvas=canvas, clip_image_last_canvas=canvas, narration_image_canvas=canvas,
            narration_image_last_canvas=canvas, zero_image_canvas=canvas, zero_image_last_canvas=canvas,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_clip_image_is_not_filled_from_first_frame(self):
        self.fn(self.gui, "clip_image")
        self.assertEqual(self.fp.calls, [])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.scene["clip_image"], "/gone/missing.png")

    def test_missing_zero_image_is_not_filled_from_zero_video(self):
        self.fn(self.gui, "zero_image")
        self.assertEqual(self.fp.calls, [])
        self.assertNotIn("zero_image", self.scene)

    def test_missing_clip_image_last_still_uses_last_frame(self):
        self.fn(self.gui, "clip_image_last")  # display itself fails on the fake file; error is caught
        self.assertEqual(self.fp.calls, [False])
        self.assertEqual(self.writes, ["clip_image_last"])


class ImportSourceContractTest(unittest.TestCase):
    """Import / generation code paths contain no clip_image or zero_image writes."""

    def _segment(self, rel, name):
        src = (ROOT / rel).read_text(encoding="utf-8")
        node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == name)
        return ast.get_source_segment(src, node)

    def test_scanner_import_never_writes_clip_or_zero_image(self):
        for name in ("last_image_replacement", "video_simple_replacement", "take_gen_video"):
            seg = self._segment("utility/media_scanner.py", name)
            self.assertNotIn('"_image", ".webp"', seg, name)
            self.assertNotIn('"clip_image"', seg, name)
            self.assertNotIn('"zero_image"', seg, name)
            self.assertNotIn("extract_frame(video_path, True)", seg, name)
        seg = self._segment("utility/media_scanner.py", "last_image_replacement")
        self.assertNotIn("refresh_scene_media(next_scene", seg)
        self.assertIn("write_chained_next_zero_image_last(next_scene, last_image)", seg)

    def test_gui_import_paths_never_write_clip_or_zero_image(self):
        for rel, name in (
            ("gui/workflow/wf_media_import.py", "_apply_editor_pick"),
            ("gui/workflow/wf_media_import.py", "_apply_download_video_result"),
            ("gui/workflow/wf_tracks.py", "_video_simple_replacement_async"),
            ("gui/workflow/wf_media_import.py", "_share_zero_across_episode"),
            ("gui/workflow/wf_prompt_flows.py", "_auto_import_scene_video"),
            ("gui/workflow/wf_tracks.py", "_concat_downloaded_track_async"),
            ("gui/workflow/wf_scene_structure.py", "_install_clip_files"),
        ):
            seg = self._segment(rel, name)
            self.assertNotIn('"clip_image",', seg, name)
            self.assertNotIn('"zero_image",', seg, name)
            self.assertNotIn("extract_frame(saved, True)", seg, name)

    def test_picture_edit_is_the_zero_image_writer(self):
        from utility import scene_image_slots as slots

        self.assertEqual(set(slots.EDIT_OUTPUT_SLOTS), {"clip_image", "clip_image_last", "zero_image"})
        self.assertFalse(slots.video_import_updates_image_slots("zero"))


if __name__ == "__main__":
    unittest.main()
