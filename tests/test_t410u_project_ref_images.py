# -*- coding: utf-8 -*-
"""t410u: 场景参考图（ref_images）进项目、选图、分集。

- 建项目：ref_images 复制进 media/<集>/，改名 <本集第几场>_<序号>，路径改写，第一张是这一场的图；旧 episode_page 并进来。
- 选图：按场景顺序翻（能翻到别的场景的图），选中的放到这一场最前面，不改名不复制。
- 分集：ref_images 的文件一律复制进新集文件夹，原文件不动。
"""
import ast
import json
import os
import pathlib
import tempfile
import textwrap
import types
import unittest

from utility import project_ref_images as pri

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _method(src_rel, cls, name):
    src = _src(src_rel)
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return textwrap.dedent(ast.get_source_segment(src, item))
    raise AssertionError(f"{cls}.{name} not found")


def _touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pathlib.Path(path).write_bytes(data)
    return os.path.abspath(path)


def _paths(scene):
    return [pri.entry_path(e) for e in scene.get("ref_images") or []]


class ImportCopyRenameTest(unittest.TestCase):
    def test_copy_rename_and_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "working", "deck")
            a = _touch(os.path.join(work, "p003.png"), b"A")
            b = _touch(os.path.join(work, "s007.jpg"), b"B")
            media = os.path.join(d, "proj", "media")
            folder = os.path.join(media, "1")
            scene = {"ref_images": [
                {"path": a, "source": "pdf", "page": 3, "desc": "图"},
                b,                                    # 手工加的字符串也认
                {"path": a},                          # 重复
                {"path": os.path.join(work, "gone.png")},  # 不在了：原样留着
            ]}
            n = pri.import_scene_ref_images(scene, folder, 2, media_root=media)
            self.assertEqual(n, 2)
            p = _paths(scene)
            self.assertEqual([os.path.basename(x) for x in p[:2]], ["2_1.png", "2_2.jpg"])
            self.assertTrue(all(os.path.dirname(x) == os.path.abspath(folder) for x in p[:2]))
            self.assertEqual(pathlib.Path(p[0]).read_bytes(), b"A")
            self.assertEqual(scene["ref_images"][0]["page"], 3)          # 元数据留着
            self.assertEqual(scene["ref_images"][0]["from"], a)          # 记下原来在哪
            self.assertEqual(len(p), 3)                                   # 重复的去掉
            self.assertTrue(os.path.isfile(a) and os.path.isfile(b))      # 原图不动
            # 再跑一次：已经在项目里的不再复制、不改名
            self.assertEqual(pri.import_scene_ref_images(scene, folder, 2, media_root=media), 0)
            self.assertEqual(_paths(scene)[:2], p[:2])

    def test_numbering_skips_taken_names(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "media", "1")
            _touch(os.path.join(folder, "1_1.webp"))
            src = _touch(os.path.join(d, "w", "x.png"))
            scene = {"ref_images": [src]}
            pri.import_scene_ref_images(scene, folder, 1, media_root=os.path.join(d, "media"))
            self.assertEqual(os.path.basename(_paths(scene)[0]), "1_2.png")

    def test_image_in_other_episode_not_copied(self):
        with tempfile.TemporaryDirectory() as d:
            media = os.path.join(d, "media")
            other = _touch(os.path.join(media, "2", "4_1.png"))
            scene = {"ref_images": [other]}
            self.assertEqual(pri.import_scene_ref_images(scene, os.path.join(media, "1"), 1, media_root=media), 0)
            self.assertEqual(_paths(scene), [other])


class LegacyMigrationTest(unittest.TestCase):
    def test_episode_page_goes_first_or_last(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "1")
            page = _touch(os.path.join(folder, "3.webp"))
            _touch(os.path.join(folder, "3.png"))
            own = _touch(os.path.join(folder, "1_1.png"))
            s1 = {"episode_page": 3}
            self.assertTrue(pri.merge_legacy_page(s1, folder, first=True))
            self.assertEqual(_paths(s1), [page])                  # webp 优先
            s2 = {"episode_page": 3, "ref_images": [own]}
            pri.merge_legacy_page(s2, folder, first=True)
            self.assertEqual(_paths(s2), [page, own])
            s3 = {"episode_page": 3, "ref_images": [own]}
            pri.merge_legacy_page(s3, folder, first=False)
            self.assertEqual(_paths(s3), [own, page])
            self.assertFalse(pri.merge_legacy_page(s3, folder, first=True))  # 已在列表里不动
            self.assertFalse(pri.merge_legacy_page({"episode_page": 9}, folder, first=True))
            self.assertFalse(pri.merge_legacy_page({}, folder, first=True))


class _FakeWorkflow:
    def __init__(self, media, scenes):
        self.media = media
        self.scenes = scenes
        self.pid = "p"

    def scene_group(self, scene):
        return str(scene.get("episode") or "1")

    def episode_media_dir(self, episode):
        return os.path.join(self.media, episode or "1")


class WorkflowSyncTest(unittest.TestCase):
    def _bind(self, name, wf, refresh=None):
        ns = {"os": os, "json": json,
              "config": types.SimpleNamespace(get_media_path=lambda pid: wf.media),
              "refresh_scene_media": refresh or (lambda *a, **k: None)}
        exec(_method("magic_workflow.py", "MagicWorkflow", name), ns)
        fn = ns[name]
        return lambda *a, **k: fn(wf, *a, **k)

    def test_sync_numbers_scenes_within_episode(self):
        with tempfile.TemporaryDirectory() as d:
            media = os.path.join(d, "media")
            w = os.path.join(d, "working")
            scenes = [
                {"id": 1, "ref_images": [_touch(os.path.join(w, "a.png")), _touch(os.path.join(w, "b.png"))]},
                {"id": 2},
                {"id": 3, "ref_images": [{"path": _touch(os.path.join(w, "c.jpg")), "source": "video"}]},
                {"id": 4, "episode": "2", "ref_images": [_touch(os.path.join(w, "d.png"))]},
                {"id": 5, "episode_page": 1},
            ]
            _touch(os.path.join(media, "1", "1.webp"))
            wf = _FakeWorkflow(media, scenes)
            changed = self._bind("sync_project_ref_images", wf)(legacy_first=False)
            self.assertEqual(changed, 4)
            names = lambda s: [os.path.relpath(p, media).replace(os.sep, "/") for p in _paths(s)]
            self.assertEqual(names(scenes[0]), ["1/1_1.png", "1/1_2.png"])
            self.assertNotIn("ref_images", scenes[1])
            self.assertEqual(names(scenes[2]), ["1/3_1.jpg"])        # 本集第 3 场
            self.assertEqual(names(scenes[3]), ["2/1_1.png"])        # 第 2 集第 1 场
            self.assertEqual(names(scenes[4]), ["1/1.webp"])         # 旧记录并进来
            self.assertEqual(self._bind("sync_project_ref_images", wf)(legacy_first=True), 0)

    def test_apply_at_creation_uses_first_copied_image(self):
        with tempfile.TemporaryDirectory() as d:
            media = os.path.join(d, "media")
            src = _touch(os.path.join(d, "working", "p001.png"))
            scenes = [{"id": 1, "ref_images": [{"path": src, "source": "pdf"}]}]
            wf = _FakeWorkflow(media, scenes)
            calls = []
            sync = self._bind("sync_project_ref_images", wf)
            wf.sync_project_ref_images = sync
            wf.ffmpeg_processor = types.SimpleNamespace(resize_image_smart=lambda p: p)
            ns = {"os": os, "refresh_scene_media": lambda sc, slot, ext, p, c: calls.append((slot, p)),
                  "project_manager": types.SimpleNamespace(SCENE_SOURCE_INFOGRAPHIC="infographic")}
            exec(_method("magic_workflow.py", "MagicWorkflow", "_apply_ref_images_to_scenes"), ns)
            self.assertEqual(ns["_apply_ref_images_to_scenes"](wf, "audio"), 1)
            dest = os.path.join(media, "1", "1_1.png")
            self.assertEqual(calls, [("clip_image", os.path.abspath(dest))])
            self.assertEqual(_paths(scenes[0]), [os.path.abspath(dest)])

    def test_select_moves_to_front_without_rename(self):
        with tempfile.TemporaryDirectory() as d:
            media = os.path.join(d, "media")
            a1 = _touch(os.path.join(media, "1", "1_1.png"))
            a2 = _touch(os.path.join(media, "1", "1_2.png"))
            b1 = _touch(os.path.join(media, "1", "2_1.png"))
            page = _touch(os.path.join(media, "1", "5.webp"))
            s1 = {"id": 1, "ref_images": [a1, a2], "episode_page": 3}
            s2 = {"id": 2, "ref_images": [b1]}
            wf = _FakeWorkflow(media, [s1, s2])
            calls = []
            select = self._bind("select_scene_ref_image", wf, lambda sc, slot, ext, p, c: calls.append((slot, ext, p)))
            # 选别的场景的图：只记路径，放最前面，不改名不复制
            before = sorted(os.listdir(os.path.join(media, "1")))
            self.assertEqual(select(s1, b1), 0)
            self.assertEqual(_paths(s1), [b1, a1, a2])
            self.assertEqual(_paths(s2), [b1])
            self.assertNotIn("episode_page", s1)
            self.assertEqual(sorted(os.listdir(os.path.join(media, "1"))), before)
            self.assertEqual(calls[-1], ("clip_image", ".png", b1))
            # 列表里已有的：挪到最前
            select(s1, a2)
            self.assertEqual(_paths(s1), [a2, b1, a1])
            # 编号页图：记 episode_page
            self.assertEqual(select(s1, page), 5)
            self.assertEqual(s1["episode_page"], 5)
            self.assertEqual(_paths(s1)[0], page)


class PickerPoolTest(unittest.TestCase):
    def test_pool_order_start_and_users(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "1")
            a1 = _touch(os.path.join(folder, "1_1.png"))
            a2 = _touch(os.path.join(folder, "1_2.png"))
            b1 = _touch(os.path.join(folder, "2_1.png"))
            c1 = _touch(os.path.join(folder, "3_1.png"))
            p1 = _touch(os.path.join(folder, "1.webp"))
            p2 = _touch(os.path.join(folder, "2.webp"))
            _touch(os.path.join(folder, "1.pdf"))
            _touch(os.path.join(folder, "cover.png"))
            scenes = [
                {"ref_images": [a1, a2]},
                {"ref_images": [b1, a1, os.path.join(folder, "gone.png")]},
                {},
                {"ref_images": [p2]},
            ]
            pool = pri.image_pool(scenes, [folder])
            # 按场景顺序，各场自己的图；再接文件夹里没出现过的编号页图、<场>_<序号>
            self.assertEqual(pool, [a1, a2, b1, p2, p1, c1])
            self.assertEqual(pri.start_index(pool, scenes[1]), 2)
            self.assertEqual(pri.start_index(pool, scenes[2]), 0)
            self.assertEqual(pri.image_users(scenes, a1), [(0, True), (1, False)])
            self.assertEqual(pri.image_users(scenes, c1), [])

    def test_select_ref_image_front(self):
        a, b, c = (os.path.abspath(os.path.join("x", n)) for n in ("a.png", "b.png", "c.png"))
        s = {"ref_images": [{"path": a, "source": "pdf"}, b]}
        pri.select_ref_image(s, b)
        self.assertEqual(_paths(s), [b, a])
        pri.select_ref_image(s, c)
        self.assertEqual(_paths(s)[0], c)
        self.assertEqual(s["ref_images"][0]["source"], "picked")
        self.assertEqual(len(s["ref_images"]), 3)


class EpisodeSplitCopyTest(unittest.TestCase):
    def _mixin(self, media, scenes):
        import importlib.util
        import sys

        # 别的测试会往 sys.modules 里放假的 config：这里用自己的一份载入，互不影响。
        spec = importlib.util.spec_from_file_location("_t410u_episodes", ROOT / "magic_workflow_episodes.py")
        mod = importlib.util.module_from_spec(spec)
        saved = sys.modules.get("config")
        sys.modules["config"] = types.SimpleNamespace(WORKING_DIR=tempfile.gettempdir(),
                                                      get_media_path=lambda pid: media)
        try:
            spec.loader.exec_module(mod)
        finally:
            if saved is None:
                sys.modules.pop("config", None)
            else:
                sys.modules["config"] = saved
        EpisodeOpsMixin = mod.EpisodeOpsMixin

        class WF(EpisodeOpsMixin):
            pid = "p"

            def __init__(self):
                self.scenes = scenes
                self.last_episode_op = {}

            def scene_group(self, s):
                return str(s.get("episode") or "1")

            def episode_media_dir(self, ep):
                return os.path.join(media, ep or "1")

            def episode_run_bounds(self, index):
                ep = self.scene_group(self.scenes[index])
                idx = [i for i, s in enumerate(self.scenes) if self.scene_group(s) == ep]
                return idx[0], idx[-1]

            def next_group_name(self):
                return "2"

            def backup_episode_files(self, episodes, tag):
                return []

            def pdf_import_history_path(self, ep):
                return os.path.join(self.episode_media_dir(ep), "pdf_imports.json")

            def touch_episode_media(self, ep):
                pass

        return WF()

    def test_split_copies_never_moves(self):
        with tempfile.TemporaryDirectory() as d:
            media = os.path.join(d, "media")
            e1 = os.path.join(media, "1")
            shared = _touch(os.path.join(e1, "1_1.png"), b"S")
            own = _touch(os.path.join(e1, "2_1.png"), b"O")
            page = _touch(os.path.join(e1, "2.webp"), b"P")
            outside = _touch(os.path.join(d, "working", "w.png"))
            scenes = [
                {"id": 1, "ref_images": [shared], "episode_page": 1},
                {"id": 2, "ref_images": [{"path": own, "source": "pdf"}, shared, page, outside], "episode_page": 2},
                {"id": 3, "ref_images": [shared]},
            ]
            wf = self._mixin(media, scenes)
            new_ep, reason = wf.split_episode_after(0)
            self.assertEqual((new_ep, reason), ("2", ""))
            e2 = os.path.join(media, "2")
            # 原文件都还在（一律复制）
            for p in (shared, own, page):
                self.assertTrue(os.path.isfile(p), p)
            self.assertEqual(_paths(scenes[0]), [shared])
            moved = _paths(scenes[1])
            for p in moved[:3]:
                self.assertTrue(p.startswith(os.path.abspath(e2) + os.sep), p)
                self.assertTrue(os.path.isfile(p), p)
            self.assertEqual(os.path.basename(moved[0]), "2_1.png")     # 不改名
            self.assertEqual(os.path.basename(moved[1]), "1_1.png")
            self.assertEqual(moved[3], outside)                          # 项目外的不动
            self.assertEqual(scenes[1]["episode_page"], 1)               # 页图照旧接新集页号
            self.assertEqual(moved[2], os.path.abspath(os.path.join(e2, "1.webp")))
            self.assertEqual(pathlib.Path(moved[2]).read_bytes(), b"P")
            self.assertEqual(_paths(scenes[2]), [moved[1]])              # 同一张图只复制一次
            self.assertEqual(scenes[1]["ref_images"][0]["source"], "pdf")
            self.assertEqual(wf.last_episode_op.get("pages_moved"), [])

    def test_move_keeps_file_used_by_staying_ref_images(self):
        with tempfile.TemporaryDirectory() as d:
            media = os.path.join(d, "media")
            page = _touch(os.path.join(media, "1", "4.webp"))
            scenes = [
                {"id": 1, "ref_images": [page]},
                {"id": 2, "episode_page": 4, "ref_images": [page]},
            ]
            wf = self._mixin(media, scenes)
            wf._transfer_scenes([scenes[1]], "1", "2")
            self.assertTrue(os.path.isfile(page))        # 留下的场景还在用：只复制
            self.assertTrue(os.path.isfile(_paths(scenes[1])[0]))
            self.assertNotEqual(_paths(scenes[1])[0], page)

    def test_rename_folder_updates_ref_images(self):
        with tempfile.TemporaryDirectory() as d:
            media = os.path.join(d, "media")
            old = os.path.join(media, "3")
            scenes = [{"ref_images": [{"path": os.path.join(old, "1_1.png")}, os.path.join(d, "x.png")]}]
            wf = self._mixin(media, scenes)
            aside = os.path.join(media, "_merged_ep3")
            self.assertEqual(wf._rename_folder_refs(old, aside), 1)
            self.assertEqual(_paths(scenes[0])[0], os.path.join(aside, "1_1.png"))


class GuiWiringTest(unittest.TestCase):
    def test_picker_no_longer_requires_pdf(self):
        src = _src("gui/workflow/wf_images.py")
        body = src[src.index("def _open_clip_image_pdf_review"):src.index("def _is_approx_16_9_landscape")]
        a = body.index("self.workflow.ref_image_pool(group_name)")
        b = body.index("if not pdf_path and not pages")
        self.assertLess(a, b)
        self.assertIn("sync_project_ref_images(legacy_first=True)", body)
        self.assertIn("start_index(pages, scene)", body)

    def test_review_media_source_uses_pool_and_select(self):
        src = _src("gui/workflow/wf_pdf_episode.py")
        self.assertIn("return self.workflow.ref_image_pool(group_name)", src)
        self.assertIn("self.workflow.select_scene_ref_image(scene, src)", src)
        assign = src[src.index("def _assign_scene_clip_image_from_file"):src.index("def _tag_scene_pdf_page")]
        self.assertIn("select_ref_image(scene, image_path", assign)

    def test_regen_after_pick_handles_silent_scenes(self):
        src = _src("gui/workflow/wf_pdf_episode.py")
        node = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "_offer_still_videos_after_pdf")
        ns = {"os": os, "get_file_path": lambda s, k: s.get(k) or "",
              "show_auto_close_popup": lambda *a, **k: None, "messagebox": None}
        exec(textwrap.dedent(ast.get_source_segment(src, node)), ns)
        with tempfile.TemporaryDirectory() as d:
            aud = _touch(os.path.join(d, "a.wav"))
            voiced, silent = {"clip_audio": aud}, {"clip_audio": os.path.join(d, "none.wav")}
            calls = []
            gui = types.SimpleNamespace(
                root=None,
                _run_still_clip_videos=lambda sc: calls.append(("voiced", sc)),
                _rebuild_silent_still_clip=lambda *sc: calls.append(("silent", list(sc))),
            )
            ns["_offer_still_videos_after_pdf"](gui, [voiced, silent], "x")
            self.assertEqual(calls, [("silent", [silent]), ("voiced", [voiced])])


if __name__ == "__main__":
    unittest.main()
