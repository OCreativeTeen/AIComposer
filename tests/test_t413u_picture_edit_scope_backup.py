"""t413u: 图片修改两种提交（提交 / 全集提交）+ 修改前把原 clip_image 备份到 clip_image_last。"""
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _src(rel):
    return Path(ROOT, rel).read_text(encoding="utf-8")


def _method(rel, cls, name):
    tree = ast.parse(_src(rel))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return textwrap.dedent(ast.get_source_segment(_src(rel), item))
    raise AssertionError(f"{cls}.{name} not found")


class _PM:
    """project_manager stub: allocate_scene_media_path → unique files in a temp dir."""

    def __init__(self, media):
        self.media, self.n = media, 0
        self.prev = sys.modules.get("project_manager")
        mod = types.ModuleType("project_manager")
        mod._slot_test_stub = True
        mod._slot_media_dir = media
        mod._slot_n = 0

        def allocate_scene_media_path(scene, media_type, media_postfix):
            mod._slot_n += 1
            return os.path.join(mod._slot_media_dir, f"{media_type}_{scene.get('id', 0)}_{mod._slot_n}{media_postfix}")

        mod.allocate_scene_media_path = allocate_scene_media_path
        self.mod = mod

    def __enter__(self):
        existing = sys.modules.get("project_manager")
        if existing is not None and getattr(existing, "_slot_test_stub", False):
            existing._slot_media_dir = self.media
            self.mod = existing
        else:
            sys.modules["project_manager"] = self.mod
        return self.mod

    def __exit__(self, *a):
        if self.prev is not None and not getattr(self.prev, "_slot_test_stub", False):
            sys.modules["project_manager"] = self.prev
        return False


class BackupWriterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t413u_")
        self.media = os.path.join(self.tmp, "media")
        os.makedirs(self.media)
        self.old = os.path.join(self.tmp, "old_clip.webp")
        Path(self.old).write_bytes(b"OLD-CLIP")
        self.edit = os.path.join(self.tmp, "edit.png")
        Path(self.edit).write_bytes(b"EDITED")
        self.cover_last = os.path.join(self.tmp, "cover.webp")
        Path(self.cover_last).write_bytes(b"COVER")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_old_clip_backed_up_to_last_and_edit_becomes_clip(self):
        from utility.scene_image_slots import write_edited_scene_images_with_backup

        with _PM(self.media):
            scene = {"id": 7, "clip_image": self.old, "clip_image_last": "x_last.webp",
                     "zero_image": "z.webp", "zero_image_last": self.cover_last, "cover_origin": "cover"}
            written, backed_up = write_edited_scene_images_with_backup(scene, self.edit)
        self.assertTrue(backed_up)
        self.assertEqual(set(written), {"clip_image", "clip_image_last", "zero_image"})
        self.assertEqual(Path(scene["clip_image"]).read_bytes(), b"EDITED")
        self.assertEqual(Path(scene["zero_image"]).read_bytes(), b"EDITED")
        self.assertEqual(Path(scene["clip_image_last"]).read_bytes(), b"OLD-CLIP")
        # backup is an independent new file; old file untouched; frozen cover untouched
        self.assertNotEqual(os.path.abspath(scene["clip_image_last"]), os.path.abspath(self.old))
        self.assertTrue(os.path.isfile(self.old))
        self.assertEqual(scene["zero_image_last"], self.cover_last)
        self.assertEqual(len({os.path.abspath(scene[k]) for k in ("clip_image", "clip_image_last", "zero_image")}), 3)

    def test_no_old_clip_falls_back_to_three_edited_copies(self):
        from utility.scene_image_slots import write_edited_scene_images_with_backup

        with _PM(self.media):
            scene = {"id": 8, "clip_image": os.path.join(self.tmp, "missing.webp")}
            written, backed_up = write_edited_scene_images_with_backup(scene, self.edit)
        self.assertFalse(backed_up)
        for slot in ("clip_image", "clip_image_last", "zero_image"):
            self.assertEqual(Path(scene[slot]).read_bytes(), b"EDITED")

    def test_failure_restores_scene_and_removes_backup(self):
        import utility.scene_image_slots as slots

        with _PM(self.media):
            scene = {"id": 9, "clip_image": self.old, "clip_image_last": "prev_last.webp", "zero_image": "z.webp"}
            before = dict(scene)
            real = slots._copy_independent
            calls = {"n": 0}

            def boom(source, dest):
                calls["n"] += 1
                if calls["n"] >= 2:
                    raise RuntimeError("simulated")
                return real(source, dest)

            slots._copy_independent = boom
            try:
                with self.assertRaises(RuntimeError):
                    slots.write_edited_scene_images_with_backup(scene, self.edit)
            finally:
                slots._copy_independent = real
        self.assertEqual(scene, before)
        self.assertEqual(os.listdir(self.media), [])


class ReplaceClipImageWiringTest(unittest.TestCase):
    def test_replace_uses_backup_writer_and_skips_pooling_backup(self):
        body = _method("gui/workflow/wf_images.py", "ImagesMixin", "_replace_current_clip_image_from_pil")
        self.assertIn("write_edited_scene_images_with_backup(scene, file_path)", body)
        self.assertNotIn("write_edited_scene_images(scene, file_path)", body)
        self.assertIn('not (slot == "clip_image_last" and backed_up)', body)
        self.assertIn("self._pool_clip_slot_image(scene, slot, written[slot])", body)


class VideoSourceGuardTest(unittest.TestCase):
    def _flows(self, video):
        ns = {"os": os}
        for name in ("_video_source_project", "_stale_still_clip_scenes", "_rebuild_still_clips_after_batch"):
            exec(_method("gui/workflow/wf_prompt_flows.py", self._cls(), name), ns)

        class Fake:
            pass

        f = Fake()
        f.workflow = types.SimpleNamespace(scene_source_is_video=lambda: video)
        f.ran = []
        f._run_still_clip_videos = lambda targets, quiet=False: f.ran.append(list(targets))
        for name in ("_video_source_project", "_stale_still_clip_scenes", "_rebuild_still_clips_after_batch"):
            setattr(f, name, types.MethodType(ns[name], f))
        return f

    @staticmethod
    def _cls():
        tree = ast.parse(_src("gui/workflow/wf_prompt_flows.py"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(i, ast.FunctionDef) and i.name == "_stale_still_clip_scenes" for i in node.body
            ):
                return node.name
        raise AssertionError("class not found")

    def test_video_source_never_rebuilds_still_clips(self):
        tmp = tempfile.mkdtemp(prefix="t413v_")
        try:
            img = os.path.join(tmp, "a.webp"); Path(img).write_bytes(b"i")
            aud = os.path.join(tmp, "a.wav"); Path(aud).write_bytes(b"a")
            scene = {"clip_image": img, "clip_audio": aud}
            fu = types.ModuleType("utility.file_util")
            fu.get_file_path = lambda s, k: s.get(k) or ""
            prev = sys.modules.get("utility.file_util")
            sys.modules["utility.file_util"] = fu
            try:
                still = self._flows(False)
                self.assertEqual(still._stale_still_clip_scenes([scene]), [scene])
                still._rebuild_still_clips_after_batch([scene], [(scene,)])
                self.assertEqual(still.ran, [[scene]])
                vid = self._flows(True)
                self.assertEqual(vid._stale_still_clip_scenes([scene]), [])
                vid._rebuild_still_clips_after_batch([scene], [(scene,)])
                self.assertEqual(vid.ran, [])
            finally:
                if prev is not None:
                    sys.modules["utility.file_util"] = prev
                else:
                    sys.modules.pop("utility.file_util", None)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class DialogScopeTest(unittest.TestCase):
    def setUp(self):
        self.src = _src("gui/picture_prompt_dialog.py").replace("\r\n", "\n")

    def test_no_more_yes_no_cancel_scope_prompt(self):
        self.assertNotIn("askyesnocancel", self.src)
        self.assertNotIn('mode != "modify" and callable(batch_scenes)', self.src)
        self.assertEqual(self.src.count("got_scope = _resolve_scope("), 3)  # cover / general (含修改图片) / upscale

    def test_two_buttons_and_portrait_current_only(self):
        self.assertIn('big_submit_button(dlg, bottom, lambda: on_submit("scene"), text="提交")', self.src)
        self.assertIn('big_submit_button(dlg, bottom, lambda: on_submit("episode"), text="全集提交")', self.src)
        btn = self.src.split('text="全集提交"', 1)[0][-400:]
        self.assertIn('if mode != "portrait" and callable(batch_scenes) and callable(run_batch):', btn)
        sub = self.src.split("def on_submit", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('_submit_scope["v"] = "episode" if scope == "episode" and mode != "portrait" else "scene"', sub)

    def test_resolve_scope_behaviour(self):
        body = self.src.split("    def _resolve_scope(note: str):", 1)[1].split("\n    def ", 1)[0]
        fn_src = "def _resolve_scope(note):" + body
        calls = []
        mb = types.SimpleNamespace(
            showwarning=lambda *a, **k: calls.append("warn"),
            showinfo=lambda *a, **k: calls.append("info"),
            askokcancel=lambda *a, **k: calls.append(("ask", a[1])) or self.ok,
        )
        scenes = [{"id": 3}, {"id": 4}]

        def make(scope_v, batch=True):
            ns = {"messagebox": mb, "_submit_scope": {"v": scope_v}, "dlg": None,
                  "batch_scenes": (lambda: (scenes, 3, 4)) if batch else None,
                  "run_batch": (lambda *a: None) if batch else None}
            exec(textwrap.dedent(fn_src), ns)
            return ns["_resolve_scope"]

        self.ok = True
        self.assertEqual(make("scene")("x"), ("scene", [], 0, 0))
        self.assertEqual(calls, [])
        self.assertEqual(make("episode")("x"), ("episode", scenes, 3, 4))
        self.assertIn("备份", calls[-1][1])
        self.ok = False
        self.assertIsNone(make("episode")("x"))
        self.assertIsNone(make("episode", batch=False)("x"))
        self.assertEqual(calls[-1], "warn")

    def test_batch_writes_through_replace_with_backup(self):
        flows = _src("gui/workflow/wf_prompt_flows.py")
        batch = flows.split("def _run_picture_batch", 1)[1]
        apply = batch.split("def apply(scene, img, label)", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("self._replace_current_clip_image_from_pil(", apply)
        self.assertIn("if self._stale_still_clip_scenes([scene]):", apply)  # 视频来源时为空 → 不重做


if __name__ == "__main__":
    unittest.main()
