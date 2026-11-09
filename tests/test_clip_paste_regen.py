"""t328u offline test: after a new clip_image (paste / drop / neighbor / frame), the scene's clip
video is rebuilt from it — with clip_audio via the still-video path, and without clip_audio as a
silent still preview (no longer left showing the old video). Method pulled from source with ast."""
from __future__ import annotations

import ast
import os
import tempfile
import textwrap
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "gui/workflow/wf_pdf_episode.py").read_text(encoding="utf-8")


def _method(name: str):
    tree = ast.parse(SRC)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {
        "os": os,
        "get_file_path": lambda scene, key: (scene or {}).get(key) or "",
        "show_auto_close_popup": lambda *a, **k: ns["popups"].append(a[2] if len(a) > 2 else ""),
        "popups": [],
    }
    exec(textwrap.dedent(ast.get_source_segment(SRC, node)), ns)  # noqa: S102
    return ns[name], ns


class _Root:
    def after(self, _ms, fn):
        fn()


class ClipPasteRegenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.img = os.path.join(self.tmp, "clip.webp")
        Path(self.img).write_bytes(b"img")
        self.aud = os.path.join(self.tmp, "clip.wav")
        Path(self.aud).write_bytes(b"wav")
        self.calls = []
        self.gui = types.SimpleNamespace(
            root=_Root(),
            _offer_still_videos_after_pdf=lambda scenes, summary: self.calls.append(("audio", scenes)),
            _rebuild_silent_still_clip=lambda scene: self.calls.append(("silent", scene)),
        )

    def test_without_clip_audio_rebuilds_silent_preview(self):
        fn, ns = _method("_after_clip_image_changed")
        scene = {"clip_image": self.img, "clip": "/old/preview.mp4"}
        fn(self.gui, scene, "已换上新的 clip 图片")
        self.assertEqual(self.calls, [("silent", scene)])

    def test_with_clip_audio_uses_still_video_path(self):
        fn, ns = _method("_after_clip_image_changed")
        scene = {"clip_image": self.img, "clip_audio": self.aud}
        fn(self.gui, scene, "x")
        self.assertEqual(self.calls, [("audio", [scene])])

    def test_no_image_only_popup(self):
        fn, ns = _method("_after_clip_image_changed")
        fn(self.gui, {"clip_image": os.path.join(self.tmp, "missing.webp")}, "x")
        self.assertEqual(self.calls, [])
        self.assertEqual(ns["popups"], ["x"])

    def test_silent_rebuild_uses_preview_writer_then_refreshes(self):
        fn, _ns = _method("_rebuild_silent_still_clip")
        done = []
        scene = {"id": 4, "clip_image": self.img}
        gui = types.SimpleNamespace(
            root=_Root(),
            _rebuild_monologue_preview_clips=lambda *s: done.append(("rebuild", s)),
            workflow=types.SimpleNamespace(save_scenes_to_json=lambda: done.append("save")),
            refresh_gui_scenes=lambda: done.append("refresh"),
        )
        fn(gui, scene)
        for _ in range(100):
            if "refresh" in done:
                break
            import time

            time.sleep(0.01)
        self.assertEqual(done, [("rebuild", (scene,)), "save", "refresh"])

    def test_paste_paths_call_hook(self):
        src = (ROOT / "gui/workflow/wf_images.py").read_text(encoding="utf-8")
        apply = src[src.index("def _apply_image_paths_to_preview_slot"):src.index("def display_image_on_canvas_for_track")]
        self.assertIn("self._after_clip_image_changed(", apply)


if __name__ == "__main__":
    unittest.main()
