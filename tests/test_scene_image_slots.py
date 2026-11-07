"""Offline tests for independent cover/clip/zero image copies and freeze rules.

These tests stub project_manager.allocate_scene_media_path so they never import
config.py (which may load .env).
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _install_pm_stub(media_dir: str):
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


class SceneImageSlotsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="slot_test_")
        self.media = os.path.join(self.tmp, "media")
        os.makedirs(self.media)
        self.cover = os.path.join(self.tmp, "cover.webp")
        with open(self.cover, "wb") as f:
            f.write(b"COVER-BYTES-AAAA")
        self.pm = _install_pm_stub(self.media)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _inodes(self, paths):
        return {(os.stat(p).st_dev, os.stat(p).st_ino) for p in paths}

    def test_creation_writes_four_independent_copies(self):
        from utility.scene_image_slots import (
            COVER_ORIGIN_FROZEN,
            COVER_ORIGIN_KEY,
            COVER_SEED_SLOTS,
            seed_scene_images_from_cover,
        )

        scene = {"id": 101}
        written = seed_scene_images_from_cover(scene, self.cover)
        self.assertEqual(set(written), set(COVER_SEED_SLOTS))
        self.assertEqual(scene.get(COVER_ORIGIN_KEY), COVER_ORIGIN_FROZEN)
        paths = [scene[k] for k in COVER_SEED_SLOTS]
        self.assertEqual(len(set(os.path.abspath(p) for p in paths)), 4)
        self.assertEqual(len(self._inodes(paths)), 4)
        for p in paths:
            self.assertTrue(os.path.isfile(p))
            self.assertFalse(os.path.islink(p))
            self.assertEqual(Path(p).read_bytes(), b"COVER-BYTES-AAAA")
        with open(scene["clip_image"], "wb") as f:
            f.write(b"MUTATED-CLIP")
        self.assertEqual(Path(scene["clip_image_last"]).read_bytes(), b"COVER-BYTES-AAAA")
        self.assertEqual(Path(scene["zero_image"]).read_bytes(), b"COVER-BYTES-AAAA")
        self.assertEqual(Path(scene["zero_image_last"]).read_bytes(), b"COVER-BYTES-AAAA")

    def test_edit_writes_three_new_files_and_freezes_zero_last(self):
        from utility.scene_image_slots import seed_scene_images_from_cover, write_edited_scene_images

        scene = {"id": 202}
        seed_scene_images_from_cover(scene, self.cover)
        old = {k: scene[k] for k in ("clip_image", "clip_image_last", "zero_image", "zero_image_last")}
        old_last_bytes = Path(old["zero_image_last"]).read_bytes()
        edit = os.path.join(self.tmp, "edit.png")
        with open(edit, "wb") as f:
            f.write(b"EDIT-V2-XXXX")
        written = write_edited_scene_images(scene, edit)
        self.assertEqual(set(written), {"clip_image", "clip_image_last", "zero_image"})
        self.assertNotIn("zero_image_last", written)
        self.assertEqual(scene["zero_image_last"], old["zero_image_last"])
        self.assertEqual(Path(scene["zero_image_last"]).read_bytes(), old_last_bytes)
        for slot in ("clip_image", "clip_image_last", "zero_image"):
            self.assertNotEqual(os.path.abspath(scene[slot]), os.path.abspath(old[slot]))
            self.assertEqual(Path(scene[slot]).read_bytes(), b"EDIT-V2-XXXX")
        with open(scene["clip_image"], "wb") as f:
            f.write(b"ONLY-CLIP")
        self.assertEqual(Path(scene["clip_image_last"]).read_bytes(), b"EDIT-V2-XXXX")
        self.assertEqual(Path(scene["zero_image"]).read_bytes(), b"EDIT-V2-XXXX")
        self.assertEqual(Path(scene["zero_image_last"]).read_bytes(), old_last_bytes)

    def test_failed_multi_write_does_not_partially_update(self):
        import utility.scene_image_slots as slots
        from utility.scene_image_slots import seed_scene_images_from_cover, write_edited_scene_images

        scene = {"id": 303}
        seed_scene_images_from_cover(scene, self.cover)
        before = dict(scene)
        before_files = {p for p in os.listdir(self.media) if os.path.isfile(os.path.join(self.media, p))}
        edit = os.path.join(self.tmp, "edit2.png")
        with open(edit, "wb") as f:
            f.write(b"EDIT-FAIL")
        real = slots._copy_independent
        calls = {"n": 0}

        def boom(source, dest):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("simulated copy failure")
            return real(source, dest)

        slots._copy_independent = boom
        try:
            with self.assertRaises(RuntimeError):
                write_edited_scene_images(scene, edit)
        finally:
            slots._copy_independent = real
        for key in ("clip_image", "clip_image_last", "zero_image", "zero_image_last", "cover_origin"):
            self.assertEqual(scene.get(key), before.get(key))
        after_files = {p for p in os.listdir(self.media) if os.path.isfile(os.path.join(self.media, p))}
        self.assertEqual(after_files, before_files)

    def test_frozen_guards_and_legacy_unmarked(self):
        from utility.scene_image_slots import (
            is_frozen_zero_last_write,
            scene_has_frozen_zero_last,
            seed_scene_images_from_cover,
            should_skip_shared_zero_image,
            write_edited_scene_images,
        )

        scene = {"id": 404}
        seed_scene_images_from_cover(scene, self.cover)
        self.assertTrue(scene_has_frozen_zero_last(scene))
        self.assertTrue(is_frozen_zero_last_write(scene, "zero_image_last"))
        self.assertFalse(is_frozen_zero_last_write(scene, "zero_image"))
        self.assertTrue(should_skip_shared_zero_image(scene, "zero_image"))
        self.assertTrue(should_skip_shared_zero_image(scene, "zero_image_last"))

        legacy = {"id": 405, "clip_image": "", "zero_image_last": ""}
        self.assertFalse(scene_has_frozen_zero_last(legacy))
        self.assertFalse(is_frozen_zero_last_write(legacy, "zero_image_last"))
        self.assertFalse(should_skip_shared_zero_image(legacy, "zero_image"))
        written = write_edited_scene_images(legacy, self.cover)
        self.assertEqual(set(written), {"clip_image", "clip_image_last", "zero_image"})
        self.assertNotIn("zero_image_last", written)

        pm_src = Path(ROOT, "project_manager.py").read_text(encoding="utf-8")
        self.assertIn("is_frozen_zero_last_write", pm_src)
        self.assertIn("def allocate_scene_media_path", pm_src)
        mw_src = Path(ROOT, "magic_workflow.py").read_text(encoding="utf-8")
        self.assertIn("if scene_has_frozen_zero_last(scene):", mw_src)
        self.assertIn("should_skip_shared_zero_image", mw_src)

    def test_cover_extract_prefers_frozen_last(self):
        from utility.scene_image_slots import cover_extract_source, seed_scene_images_from_cover, write_edited_scene_images

        scene = {"id": 607}
        seed_scene_images_from_cover(scene, self.cover)
        edit = os.path.join(self.tmp, "altered.png")
        with open(edit, "wb") as f:
            f.write(b"ALTERED-CLIP")
        write_edited_scene_images(scene, edit)
        src = cover_extract_source(scene, self.cover)
        self.assertEqual(os.path.abspath(src), os.path.abspath(scene["zero_image_last"]))
        self.assertEqual(Path(src).read_bytes(), b"COVER-BYTES-AAAA")
        legacy = {"clip_image": edit}
        self.assertEqual(os.path.abspath(cover_extract_source(legacy, self.cover)), os.path.abspath(edit))

    def test_selector_prefs_and_dual_frame(self):
        from utility.scene_image_slots import IMAGE_CHOICE_KEYS, normalize_image_choice, resolve_video_prompt_images

        files = {k: f"/tmp/fake_{k}.webp" for k in IMAGE_CHOICE_KEYS}

        def get(key):
            return files[key]

        self.assertEqual(len(IMAGE_CHOICE_KEYS), 4)
        for key in IMAGE_CHOICE_KEYS:
            self.assertEqual(normalize_image_choice(key), key)
            start, end = resolve_video_prompt_images("one", key, get)
            self.assertEqual(start, files[key])
            self.assertIsNone(end)
        self.assertEqual(normalize_image_choice("nope"), "clip_image")
        start, end = resolve_video_prompt_images("two", "zero_image_last", get)
        self.assertEqual(start, files["clip_image"])
        self.assertEqual(end, files["clip_image_last"])

    def test_zero_video_import_does_not_update_zero_images(self):
        from utility.scene_image_slots import video_import_updates_image_slots

        self.assertFalse(video_import_updates_image_slots("zero"))
        self.assertTrue(video_import_updates_image_slots("clip"))
        self.assertTrue(video_import_updates_image_slots("narration"))
        src = Path(ROOT, "utility/media_scanner.py").read_text(encoding="utf-8")
        self.assertIn("video_import_updates_image_slots", src)


if __name__ == "__main__":
    unittest.main()
