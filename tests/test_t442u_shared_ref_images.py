"""t442u: 参考图复制进项目：同一个原文件只复制一次（拆开的几段共用）、拆段中间帧编号排在原图后面、
选图翻页时当前场景的图连成一块。"""
import os
import pathlib
import tempfile
import unittest

from tests.test_video_speaker_semantics import _install_stubs

_install_stubs()

from utility import project_ref_images as pri  # noqa: E402
from utility import scene_prep as sp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pathlib.Path(path).write_bytes(b"x")
    return os.path.abspath(path)


def _paths(scene):
    return [pri.entry_path(e) for e in scene["ref_images"]]


class SharedCopyTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.media = os.path.join(self.d, "media")
        self.folder = os.path.join(self.media, "1")
        self.orig = [_touch(os.path.join(self.d, "src", f"o{i}.png")) for i in (1, 2, 3)]

    def test_split_parts_share_files(self):
        done = {}
        p3 = {"ref_images": [{"path": p, "source": "pdf"} for p in self.orig]}
        p4 = {"ref_images": [{"path": p, "source": "pdf"} for p in self.orig]}
        self.assertEqual(pri.import_scene_ref_images(p3, self.folder, 3, media_root=self.media, done=done), 3)
        self.assertEqual(pri.import_scene_ref_images(p4, self.folder, 4, media_root=self.media, done=done), 0)
        want = [os.path.join(self.folder, f"3_{k}.png") for k in (1, 2, 3)]
        self.assertEqual(_paths(p3), want)
        self.assertEqual(_paths(p4), want)
        self.assertEqual(p4["ref_images"][0]["from"], self.orig[0])
        self.assertEqual(sorted(os.listdir(self.folder)), ["3_1.png", "3_2.png", "3_3.png"])

    def test_other_episode_gets_own_copy(self):
        done = {}
        a = {"ref_images": [self.orig[0]]}
        b = {"ref_images": [self.orig[0]]}
        pri.import_scene_ref_images(a, self.folder, 3, media_root=self.media, done=done)
        f2 = os.path.join(self.media, "2")
        self.assertEqual(pri.import_scene_ref_images(b, f2, 1, media_root=self.media, done=done), 1)
        self.assertEqual(_paths(b), [os.path.join(f2, "1_1.png")])

    def test_without_done_unchanged(self):
        a = {"ref_images": [self.orig[0]]}
        b = {"ref_images": [self.orig[0]]}
        pri.import_scene_ref_images(a, self.folder, 3, media_root=self.media)
        pri.import_scene_ref_images(b, self.folder, 4, media_root=self.media)
        self.assertEqual(_paths(b), [os.path.join(self.folder, "4_1.png")])

    def test_shot_frames_numbered_after_originals(self):
        done = {}
        f3 = _touch(os.path.join(self.d, "shots", "scene_001.png"))
        f4 = _touch(os.path.join(self.d, "shots", "scene_002.png"))
        p3 = {"ref_images": [{"path": f3, "source": "shot_frame", "time": 5.0}] + [{"path": p} for p in self.orig]}
        p4 = {"ref_images": [{"path": f4, "source": "shot_frame"}] + [{"path": p} for p in self.orig]}
        pri.import_scene_ref_images(p3, self.folder, 3, media_root=self.media, done=done)
        pri.import_scene_ref_images(p4, self.folder, 4, media_root=self.media, done=done)
        j = lambda n: os.path.join(self.folder, n)  # noqa: E731
        self.assertEqual(_paths(p3), [j("3_4.png"), j("3_1.png"), j("3_2.png"), j("3_3.png")])
        self.assertEqual(_paths(p4), [j("4_1.png"), j("3_1.png"), j("3_2.png"), j("3_3.png")])
        self.assertEqual(p3["ref_images"][0]["source"], "shot_frame")
        self.assertEqual(p3["ref_images"][0]["time"], 5.0)

    def test_attach_part_frames_tags(self):
        video = _touch(os.path.join(self.d, "v.mp4"))
        parts = [{"ref_images": [{"path": self.orig[0], "source": "video"}]}]

        def picker(path, ps, out_dir, log=print):
            return {0: [{"path": os.path.join(self.d, "f.png"), "source": "video", "time": 2.5}]}

        self.assertEqual(sp.attach_part_frames(parts, video, picker=picker, log=lambda *_: None), 1)
        first = parts[0]["ref_images"][0]
        self.assertEqual((first["source"], first["time"]), ("shot_frame", 2.5))
        self.assertEqual(parts[0]["ref_images"][1]["path"], self.orig[0])


class PoolBlockTest(unittest.TestCase):
    def test_current_block(self):
        d = tempfile.mkdtemp()
        a1, f1, f2, o1, o2, b1 = (_touch(os.path.join(d, n + ".png")) for n in ("a1", "f1", "f2", "o1", "o2", "b1"))
        scenes = [{"ref_images": [a1]}, {"ref_images": [f1, o1, o2]}, {"ref_images": [f2, o1, o2]},
                  {"ref_images": [b1]}]
        self.assertEqual(pri.image_pool(scenes), [a1, f1, o1, o2, f2, b1])
        pool = pri.image_pool(scenes, current=scenes[2])
        self.assertEqual(pool, [a1, f1, f2, o1, o2, b1])
        self.assertEqual(pri.start_index(pool, scenes[2]), 2)
        pool = pri.image_pool(scenes, current=scenes[1])
        self.assertEqual(pool, [a1, f1, o1, o2, f2, b1])
        self.assertEqual(pri.start_index(pool, scenes[1]), 1)
        # 第一张是共用图的场（没有自己的中间帧）也停在自己那一块的开头
        scenes[2]["ref_images"] = [o2, o1]
        pool = pri.image_pool(scenes, current=scenes[2])
        self.assertEqual(pool, [a1, f1, o2, o1, b1])
        self.assertEqual(pri.start_index(pool, scenes[2]), 2)


class WiringTest(unittest.TestCase):
    def test_wiring(self):
        mw = (ROOT / "magic_workflow.py").read_text(encoding="utf-8")
        body = mw[mw.index("    def sync_project_ref_images"):mw.index("    def ref_image_pool")]
        self.assertIn("done=done", body)
        self.assertIn("current=current", mw[mw.index("    def ref_image_pool"):])
        wi = (ROOT / "gui" / "workflow" / "wf_images.py").read_text(encoding="utf-8")
        self.assertIn("ref_image_pool(group_name, current=scene)", wi)
        self.assertIn("focus_scene=scene", wi)
        pe = (ROOT / "gui" / "workflow" / "wf_pdf_episode.py").read_text(encoding="utf-8")
        self.assertIn("focus_scene: dict | None = None", pe)


if __name__ == "__main__":
    unittest.main()
