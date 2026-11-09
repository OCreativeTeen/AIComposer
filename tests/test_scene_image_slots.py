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


def _ensure_scanner_imports(media_dir: str):
    """Stub config / refresh_scene_media so MediaScanner can load without .env."""
    pm = _install_pm_stub(media_dir)

    def refresh_scene_media(scene, media_type, media_postfix, replacement=None, make_replacement_copy=False):
        from utility.scene_image_slots import is_frozen_zero_last_write

        if not isinstance(scene, dict):
            raise TypeError("scene 必须是字典")
        if is_frozen_zero_last_write(scene, media_type):
            old = scene.get(media_type)
            return old, old
        old = scene.get(media_type)
        dest = pm.allocate_scene_media_path(scene, media_type, media_postfix)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        if replacement and os.path.isfile(replacement):
            shutil.copy2(replacement, dest)
            if not make_replacement_copy and os.path.abspath(replacement) != os.path.abspath(dest):
                try:
                    os.remove(replacement)
                except OSError:
                    pass
        scene[media_type] = dest
        return old, dest

    pm.refresh_scene_media = refresh_scene_media
    if "config" not in sys.modules:
        cfg = types.ModuleType("config")
        cfg.audio_language_label = lambda language: "Chinese" if language else ""
        sys.modules["config"] = cfg
    elif not hasattr(sys.modules["config"], "audio_language_label"):
        sys.modules["config"].audio_language_label = lambda language: "Chinese" if language else ""
    try:
        import tkinter.messagebox  # noqa: F401
    except Exception:
        tk = types.ModuleType("tkinter")
        mb = types.ModuleType("tkinter.messagebox")
        sys.modules["tkinter"] = tk
        sys.modules["tkinter.messagebox"] = mb


class _FakeFFmpeg:
    def __init__(self, tail_path, *, fail=False, fail_resize=False):
        self.tail_path = tail_path
        self.fail = fail
        self.fail_resize = fail_resize

    def extract_frame(self, video_path, first):
        if self.fail:
            return None
        tmp = self.tail_path + ".extract.webp"
        shutil.copy2(self.tail_path, tmp)
        return tmp

    def resize_image_smart(self, path):
        if self.fail_resize:
            return None
        return path


class _FakeWorkflow:
    def __init__(self, nxt):
        self._next = nxt
        self.ffmpeg_processor = None

    def next_scene_of_story(self, scene):
        return self._next


class ClipTailChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="slot_chain_")
        self.media = os.path.join(self.tmp, "media")
        os.makedirs(self.media)
        self.cover = os.path.join(self.tmp, "cover.webp")
        with open(self.cover, "wb") as f:
            f.write(b"COVER-BYTES-AAAA")
        self.tail = os.path.join(self.tmp, "tail.webp")
        with open(self.tail, "wb") as f:
            f.write(b"CLIP-TAIL-FRAME")
        self.pm = _ensure_scanner_imports(self.media)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _scanner(self, nxt, *, fail=False):
        from utility.media_scanner import MediaScanner

        wf = _FakeWorkflow(nxt)
        wf.ffmpeg_processor = _FakeFFmpeg(self.tail, fail=fail)
        return MediaScanner(wf, 0)

    def _seed(self, sid):
        from utility.scene_image_slots import seed_scene_images_from_cover

        scene = {"id": sid}
        seed_scene_images_from_cover(scene, self.cover)
        return scene

    def test_clip_gen_chains_independent_next_zero_last(self):
        from utility.scene_image_slots import (
            ZERO_LAST_CHAIN_CLIP,
            ZERO_LAST_CHAIN_KEY,
            is_frozen_zero_last_write,
            write_edited_scene_images,
        )

        current = self._seed(501)
        nxt = self._seed(502)
        old_next_zero = nxt["zero_image"]
        old_next_zero_bytes = Path(nxt["zero_image"]).read_bytes()
        old_next_last = nxt["zero_image_last"]
        scanner = self._scanner(nxt)
        scanner.last_image_replacement(current, os.path.join(self.tmp, "clip.mp4"), "clip")

        self.assertTrue(os.path.isfile(current["clip_image_last"]))
        self.assertEqual(Path(current["clip_image_last"]).read_bytes(), b"CLIP-TAIL-FRAME")
        self.assertEqual(Path(nxt["zero_image_last"]).read_bytes(), b"CLIP-TAIL-FRAME")
        self.assertNotEqual(os.path.abspath(nxt["zero_image_last"]), os.path.abspath(current["clip_image_last"]))
        self.assertNotEqual(
            (os.stat(nxt["zero_image_last"]).st_dev, os.stat(nxt["zero_image_last"]).st_ino),
            (os.stat(current["clip_image_last"]).st_dev, os.stat(current["clip_image_last"]).st_ino),
        )
        self.assertNotEqual(os.path.abspath(nxt["zero_image_last"]), os.path.abspath(old_next_last))
        self.assertEqual(os.path.abspath(nxt["zero_image"]), os.path.abspath(old_next_zero))
        self.assertEqual(Path(nxt["zero_image"]).read_bytes(), old_next_zero_bytes)
        self.assertEqual(nxt.get(ZERO_LAST_CHAIN_KEY), ZERO_LAST_CHAIN_CLIP)
        self.assertTrue(is_frozen_zero_last_write(nxt, "zero_image_last"))

        chained = nxt["zero_image_last"]
        chained_bytes = Path(chained).read_bytes()
        edit = os.path.join(self.tmp, "edit-after-chain.png")
        with open(edit, "wb") as f:
            f.write(b"EDIT-AFTER-CHAIN")
        written = write_edited_scene_images(nxt, edit)
        self.assertEqual(set(written), {"clip_image", "clip_image_last", "zero_image"})
        self.assertEqual(nxt["zero_image_last"], chained)
        self.assertEqual(Path(nxt["zero_image_last"]).read_bytes(), chained_bytes)

    def test_final_scene_and_failed_extract_do_not_write_next(self):
        current = self._seed(511)
        leftover = self._seed(599)
        old_last = leftover["zero_image_last"]
        scanner = self._scanner(None)
        scanner.last_image_replacement(current, os.path.join(self.tmp, "clip.mp4"), "clip")
        self.assertEqual(leftover["zero_image_last"], old_last)
        self.assertEqual(Path(leftover["zero_image_last"]).read_bytes(), b"COVER-BYTES-AAAA")
        self.assertTrue(os.path.isfile(current["clip_image_last"]))

        current2 = self._seed(512)
        nxt = self._seed(513)
        before = dict(nxt)
        fail_scanner = self._scanner(nxt, fail=True)
        fail_scanner.last_image_replacement(current2, os.path.join(self.tmp, "clip.mp4"), "clip")
        self.assertEqual(nxt.get("zero_image_last"), before.get("zero_image_last"))
        self.assertEqual(Path(nxt["zero_image_last"]).read_bytes(), b"COVER-BYTES-AAAA")
        self.assertEqual(Path(current2["clip_image_last"]).read_bytes(), b"COVER-BYTES-AAAA")

    def test_narration_and_zero_do_not_chain_next_zero_last(self):
        current = self._seed(521)
        nxt = self._seed(522)
        old_last = nxt["zero_image_last"]
        scanner = self._scanner(nxt)
        scanner.last_image_replacement(current, os.path.join(self.tmp, "n.mp4"), "narration")
        self.assertEqual(nxt["zero_image_last"], old_last)
        self.assertEqual(Path(current["narration_image_last"]).read_bytes(), b"CLIP-TAIL-FRAME")

        current_z = self._seed(523)
        nxt_z = self._seed(524)
        old_z_last = nxt_z["zero_image_last"]
        old_z_clip_last = current_z["clip_image_last"]
        scanner.last_image_replacement(current_z, os.path.join(self.tmp, "z.mp4"), "zero")
        self.assertEqual(nxt_z["zero_image_last"], old_z_last)
        self.assertEqual(current_z["clip_image_last"], old_z_clip_last)
        self.assertEqual(Path(nxt_z["zero_image_last"]).read_bytes(), b"COVER-BYTES-AAAA")

    def test_enh2_still_writes_next_clip_image_and_chains_zero_last(self):
        current = self._seed(531)
        current["clip_status"] = "ENH2"
        nxt = self._seed(532)
        old_zero = nxt["zero_image"]
        old_clip = nxt["clip_image"]
        scanner = self._scanner(nxt)
        scanner.last_image_replacement(current, os.path.join(self.tmp, "clip.mp4"), "clip")
        self.assertEqual(Path(nxt["clip_image"]).read_bytes(), b"CLIP-TAIL-FRAME")
        self.assertNotEqual(os.path.abspath(nxt["clip_image"]), os.path.abspath(old_clip))
        self.assertEqual(Path(nxt["zero_image_last"]).read_bytes(), b"CLIP-TAIL-FRAME")
        self.assertEqual(os.path.abspath(nxt["zero_image"]), os.path.abspath(old_zero))
        self.assertEqual(Path(nxt["zero_image"]).read_bytes(), b"COVER-BYTES-AAAA")

    def test_chain_copy_failure_leaves_next_unchanged(self):
        import utility.scene_image_slots as slots
        from utility.scene_image_slots import write_chained_next_zero_image_last

        nxt = self._seed(541)
        before = dict(nxt)
        before_last = nxt["zero_image_last"]
        real = slots._copy_independent

        def boom(source, dest):
            raise RuntimeError("simulated chain copy failure")

        slots._copy_independent = boom
        try:
            with self.assertRaises(RuntimeError):
                write_chained_next_zero_image_last(nxt, self.tail)
        finally:
            slots._copy_independent = real
        self.assertEqual(nxt.get("zero_image_last"), before_last)
        self.assertEqual(nxt.get("cover_origin"), before.get("cover_origin"))
        self.assertNotIn("zero_image_last_chain", nxt)
        self.assertEqual(Path(nxt["zero_image_last"]).read_bytes(), b"COVER-BYTES-AAAA")



class ProjectCoverResolveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cover_resolve_")
        self.seeded = os.path.join(self.tmp, "seeded_cover.webp")
        self.override = os.path.join(self.tmp, "override_cover.webp")
        self.primary = os.path.join(self.tmp, "primary_cover.webp")
        self.secondary = os.path.join(self.tmp, "older_cover.webp")
        self.item_cover = os.path.join(self.tmp, "item_cover.webp")
        self.missing = os.path.join(self.tmp, "gone.webp")
        self.clip = os.path.join(self.tmp, "scene_clip.webp")
        self.chained = os.path.join(self.tmp, "chained_last.webp")
        for path, payload in (
            (self.seeded, b"SEEDED"),
            (self.override, b"OVERRIDE"),
            (self.primary, b"PRIMARY"),
            (self.secondary, b"SECONDARY"),
            (self.item_cover, b"ITEM"),
            (self.clip, b"CLIP"),
            (self.chained, b"CHAIN"),
        ):
            with open(path, "wb") as f:
                f.write(payload)
        self.pm = _install_pm_stub(os.path.join(self.tmp, "media"))
        os.makedirs(os.path.join(self.tmp, "media"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seeded_path_wins_over_override_and_persistent(self):
        from utility.scene_image_slots import resolve_project_cover_image

        found = resolve_project_cover_image(
            cover_seeded_path=self.seeded,
            cover_override=self.override,
            project_config={"cover_image": [self.primary, self.secondary]},
            item={"cover_image": self.item_cover},
        )
        self.assertEqual(os.path.abspath(found), os.path.abspath(self.seeded))

    def test_override_wins_when_seeded_missing(self):
        from utility.scene_image_slots import resolve_project_cover_image

        found = resolve_project_cover_image(
            cover_seeded_path=self.missing,
            cover_override=self.override,
            project_config={"cover_image": [self.primary]},
        )
        self.assertEqual(os.path.abspath(found), os.path.abspath(self.override))

    def test_project_primary_is_first_existing_cover(self):
        from utility.scene_image_slots import resolve_project_cover_image

        found = resolve_project_cover_image(
            project_config={"cover_image": [self.missing, self.primary, self.secondary]},
        )
        self.assertEqual(os.path.abspath(found), os.path.abspath(self.primary))

    def test_item_cover_used_when_project_has_none(self):
        from utility.scene_image_slots import resolve_project_cover_image

        found = resolve_project_cover_image(
            project_config={"cover_image": [self.missing]},
            item={"cover_image": self.item_cover},
        )
        self.assertEqual(os.path.abspath(found), os.path.abspath(self.item_cover))

    def test_missing_cover_returns_empty(self):
        from utility.scene_image_slots import (
            manual_cover_extract_images,
            resolve_project_cover_image,
        )

        found = resolve_project_cover_image(
            cover_seeded_path=self.missing,
            project_config={"title": "no cover"},
        )
        self.assertEqual(found, "")
        self.assertEqual(manual_cover_extract_images(found), [])
        self.assertEqual(manual_cover_extract_images(self.missing), [])

    def test_scene_slots_cannot_override_true_cover(self):
        from utility.scene_image_slots import (
            manual_cover_extract_images,
            resolve_project_cover_image,
        )

        scene = {
            "clip_image": self.clip,
            "clip_image_last": self.clip,
            "zero_image": self.clip,
            "zero_image_last": self.chained,
            "cover_origin": "cover",
            "image": "clip_image",
        }
        found = resolve_project_cover_image(
            project_config=scene,
            item=scene,
        )
        self.assertEqual(found, "")
        found = resolve_project_cover_image(
            project_config={"cover_image": [self.primary], **scene},
        )
        self.assertEqual(os.path.abspath(found), os.path.abspath(self.primary))
        images = manual_cover_extract_images(found)
        self.assertEqual(images, [os.path.abspath(self.primary)])
        self.assertNotEqual(images[0], os.path.abspath(self.clip))
        self.assertNotEqual(images[0], os.path.abspath(self.chained))

    def test_batch_jobs_share_same_true_cover(self):
        from utility.scene_image_slots import (
            manual_cover_extract_images,
            resolve_project_cover_image,
        )

        cover = resolve_project_cover_image(
            project_config={"cover_image": [self.primary]},
        )
        scenes = [
            {"id": 1, "clip_image": self.clip, "zero_image_last": self.chained, "cover_step": 1},
            {"id": 2, "clip_image": self.clip, "zero_image_last": self.chained, "cover_step": 2},
        ]
        refs = [manual_cover_extract_images(cover) for _sc in scenes]
        self.assertEqual(refs[0], refs[1])
        self.assertEqual(refs[0], [os.path.abspath(self.primary)])
        self.assertTrue(all(img != os.path.abspath(self.clip) for job in refs for img in job))

    def test_auto_cover_extract_source_still_prefers_chained_zero_last(self):
        """Document unchanged auto path: cover_extract_source may pick t297u chain."""
        from utility.scene_image_slots import cover_extract_source

        scene = {
            "cover_origin": "cover",
            "zero_image_last": self.chained,
            "clip_image": self.clip,
        }
        self.assertEqual(cover_extract_source(scene, self.primary), self.chained)


class ManualCoverDialogContractTest(unittest.TestCase):
    def test_cover_mode_instantiates_preview_not_four_slot_picker(self):
        src = Path(ROOT, "gui/picture_prompt_dialog.py").read_text(encoding="utf-8")
        start = src.index('if mode == "cover":')
        else_idx = src.index("else:\n        from gui.clip_image_choice import pack_clip_image_choice", start)
        cover_block = src[start:else_idx]
        rest_after = src[else_idx:else_idx + 500]
        self.assertIn("pack_project_cover_preview", cover_block)
        self.assertNotIn("pack_clip_image_choice", cover_block)
        self.assertIn("pack_clip_image_choice", rest_after)
        self.assertIn("get_project_cover", src)
        self.assertIn("manual_cover_extract_images", src)
        self.assertIn("没有可用的项目封面，无法从封面提取。", src)

    def test_ask_picture_edit_mode_still_present_unchanged_shape(self):
        src = Path(ROOT, "gui/picture_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn("def ask_picture_edit_mode(", src)
        self.assertIn("PICTURE_EDIT_MODES", src)

    def test_auto_extract_flow_still_uses_cover_extract_source(self):
        src = Path(ROOT, "gui/workflow/wf_prompt_flows.py").read_text(encoding="utf-8")
        fn = src.index("def _maybe_auto_extract_steps_from_cover")
        nxt = src.find("\n    def ", fn + 10)
        body = src[fn:nxt if nxt != -1 else None]
        self.assertIn("cover_extract_source(", body)
        self.assertNotIn("resolve_project_cover_image", body)
        self.assertNotIn("manual_cover_extract_images", body)

    def test_cover_mode_lists_all_covers_for_picker(self):
        src = Path(ROOT, "gui/picture_prompt_dialog.py").read_text(encoding="utf-8")
        start = src.index('if mode == "cover":')
        else_idx = src.index("else:\n        from gui.clip_image_choice import pack_clip_image_choice", start)
        cover_block = src[start:else_idx]
        self.assertIn("list_project_cover_images", cover_block)
        self.assertIn("paths=", cover_block)
        self.assertIn("_selected_cover", src)
        wf = Path(ROOT, "gui/workflow/wf_prompt_flows.py").read_text(encoding="utf-8")
        self.assertIn("def get_project_covers", wf)
        self.assertIn("get_project_covers=get_project_covers", wf)


class CoverListAndPickerHelperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cover_list_")
        self.primary = os.path.join(self.tmp, "a_primary.webp")
        self.secondary = os.path.join(self.tmp, "b_older.webp")
        self.missing = os.path.join(self.tmp, "gone.webp")
        self.dup = os.path.join(self.tmp, "a_primary.webp")
        for path, payload in ((self.primary, b"A"), (self.secondary, b"B")):
            with open(path, "wb") as f:
                f.write(payload)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_covers_newest_first_skip_missing_dedupe(self):
        from utility.scene_image_slots import list_project_cover_images

        listed = list_project_cover_images(
            project_config={"cover_image": [self.primary, self.missing, self.secondary, self.primary]},
            item={"cover_image": [self.secondary]},
        )
        self.assertEqual(
            [os.path.abspath(self.primary), os.path.abspath(self.secondary)],
            listed,
        )

    def test_list_covers_includes_item_extras_and_skips_absent_seeded(self):
        from utility.scene_image_slots import list_project_cover_images

        extra = os.path.join(self.tmp, "seeded.webp")
        with open(extra, "wb") as f:
            f.write(b"S")
        listed = list_project_cover_images(
            cover_seeded_path=extra,
            cover_override=self.missing,
            project_config={"cover_image": [self.primary]},
            item={"cover_image": [self.secondary]},
        )
        self.assertEqual(os.path.abspath(listed[0]), os.path.abspath(self.primary))
        self.assertEqual(os.path.abspath(listed[1]), os.path.abspath(self.secondary))
        self.assertEqual(os.path.abspath(listed[2]), os.path.abspath(extra))

    def test_normalize_choices_defaults_to_primary_and_skips_missing(self):
        from utility.scene_image_slots import normalize_cover_preview_choices

        items, picked = normalize_cover_preview_choices(
            [self.primary, self.missing, self.secondary, self.primary],
            self.primary,
        )
        self.assertEqual(items, [os.path.abspath(self.primary), os.path.abspath(self.secondary)])
        self.assertEqual(picked, os.path.abspath(self.primary))
        items, picked = normalize_cover_preview_choices(
            [self.primary, self.secondary],
            self.secondary,
        )
        self.assertEqual(picked, os.path.abspath(self.secondary))
        items, picked = normalize_cover_preview_choices([], self.missing)
        self.assertEqual(items, [])
        self.assertEqual(picked, "")

    def test_preview_box_larger_than_old_tiles_and_follows_aspect(self):
        from utility.scene_image_slots import cover_preview_max_size

        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not available")
        land = os.path.join(self.tmp, "land.png")
        port = os.path.join(self.tmp, "port.png")
        Image.new("RGB", (1600, 900), (10, 20, 30)).save(land)
        Image.new("RGB", (900, 1600), (30, 20, 10)).save(port)
        lw, lh = cover_preview_max_size(land)
        pw, ph = cover_preview_max_size(port)
        self.assertEqual((lw, lh), (320, 180))
        self.assertEqual((pw, ph), (180, 320))
        self.assertGreater(lw * lh, 96 * 60)
        self.assertGreater(pw * ph, 96 * 60)

    def test_hydrate_copies_full_cover_list_not_just_primary(self):
        src = Path(ROOT, "project_manager.py").read_text(encoding="utf-8")
        start = src.index("def hydrate_config_cover_media")
        nxt = src.find("\\ndef ", start + 10)
        body = src[start:] if nxt < 0 else src[start:nxt]
        # cut at next top-level def if the escaped search is literal
        if "list_project_cover_images" not in body[:2500]:
            body = src[start:start + 2500]
        self.assertIn("list_project_cover_images", body)
        self.assertIn("set_cover_images(cfg, covers)", body)
        self.assertIn('if k == "cover_image":', body)
        from utility.scene_image_slots import list_project_cover_images

        row = {"cover_image": [self.primary, self.secondary]}
        cfg = {}
        covers = list_project_cover_images(project_config=cfg, item=row)
        self.assertEqual(
            [os.path.abspath(self.primary), os.path.abspath(self.secondary)],
            covers,
        )
        crushed = {"cover_image": self.primary}
        covers = list_project_cover_images(project_config=crushed, item=row)
        self.assertEqual(
            [os.path.abspath(self.primary), os.path.abspath(self.secondary)],
            covers,
        )

    def test_seeding_uses_covers_zero_without_multi_cover_prompt(self):
        from utility.scene_image_slots import (
            covers_for_pdf_prompt,
            needs_cover_vs_pdf_prompt,
            primary_cover_for_seeding,
        )

        third = os.path.join(self.tmp, "c_oldest.webp")
        with open(third, "wb") as f:
            f.write(b"C")
        covers = [self.primary, self.secondary, third]
        self.assertFalse(needs_cover_vs_pdf_prompt(covers, ""))
        self.assertFalse(needs_cover_vs_pdf_prompt(covers, None))
        self.assertTrue(needs_cover_vs_pdf_prompt(covers, "/tmp/slides.pdf"))
        self.assertTrue(needs_cover_vs_pdf_prompt([self.primary], "/tmp/slides.pdf"))
        self.assertFalse(needs_cover_vs_pdf_prompt([], "/tmp/slides.pdf"))
        self.assertEqual(covers_for_pdf_prompt(covers), [self.primary])
        self.assertEqual(primary_cover_for_seeding(covers), self.primary)
        self.assertNotEqual(primary_cover_for_seeding(covers), third)
        self.assertEqual(primary_cover_for_seeding(covers, override=self.secondary), self.secondary)
        mw = Path(ROOT, "magic_workflow.py").read_text(encoding="utf-8")
        seed_i = mw.index("def _seed_cover_path")
        nxt = mw.find("\n    def ", seed_i + 10)
        seed_fn = mw[seed_i: nxt if nxt != -1 else seed_i + 800]
        if "primary_cover_for_seeding" not in seed_fn:
            seed_fn = mw[seed_i:seed_i + 800]
        self.assertIn("primary_cover_for_seeding", seed_fn)
        self.assertNotIn("covers[-1]", seed_fn)
        apply_i = mw.index("def _apply_cover_media_to_scenes")
        ask_i = mw.index("def _ask_cover_or_pdf")
        apply_fn = mw[apply_i:ask_i]
        self.assertIn("needs_cover_vs_pdf_prompt", apply_fn)
        self.assertIn("covers_for_pdf_prompt", apply_fn)
        self.assertNotIn("len(covers) + (1 if pdf_opt else 0) >= 2", apply_fn)
        # 自动从封面提取仍走 cover_seeded_path；不改提取循环
        wf = Path(ROOT, "gui/workflow/wf_prompt_flows.py").read_text(encoding="utf-8")
        fn = wf.index("def _maybe_auto_extract_steps_from_cover")
        nxt = wf.find("\n    def ", fn + 10)
        body = wf[fn:nxt if nxt != -1 else fn + 2500]
        self.assertIn("cover_seeded_path", body)
        self.assertIn("cover_extract_source(", body)


if __name__ == "__main__":
    unittest.main()
