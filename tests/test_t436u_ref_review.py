"""t436u 阶段 4：预览窗口 Ctrl+双击场景 JSON → 看这一场的参考图、选一张（移到第一张）。"""
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("_t436u_rir", ROOT / "gui" / "dl" / "ref_image_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # 不经过 gui/__init__（盒子上没有 tkinter）
    return mod


class SceneIndexTest(unittest.TestCase):
    def setUp(self):
        self.m = _mod()
        self.scenes = [{"caption": "A", "visual": "甲 [x]"}, {"caption": "B", "s": "}{,"}, {"caption": "C"}]
        self.text = json.dumps(self.scenes, ensure_ascii=False, indent=2)

    def test_each_scene(self):
        for i, s in enumerate(self.scenes):
            off = self.text.index(f'"{s["caption"]}"')
            self.assertEqual(self.m.scene_index_at(self.text, off), i)

    def test_outside(self):
        self.assertEqual(self.m.scene_index_at(self.text, 0), -1)
        self.assertEqual(self.m.scene_index_at(self.text, len(self.text) - 1), -1)

    def test_bad_json(self):
        self.assertEqual(self.m.scene_index_at('{"a": 1}', 2), -1)
        self.assertEqual(self.m.scene_index_at('[{"a": ', 3), -1)
        self.assertEqual(self.m.scene_index_at("", 0), -1)

    def test_compact(self):
        t = '[{"a":1},{"b":2}]'
        self.assertEqual(self.m.scene_index_at(t, t.index('"b"')), 1)
        self.assertEqual(self.m.scene_index_at(t, t.index(",{")), -1)


class PickTest(unittest.TestCase):
    def setUp(self):
        self.m = _mod()
        self.tmp = tempfile.mkdtemp()
        self.a = os.path.join(self.tmp, "a.png")
        self.b = os.path.join(self.tmp, "b.png")
        for p in (self.a, self.b):
            pathlib.Path(p).write_bytes(b"x")

    def test_paths_skip_missing(self):
        scene = {"ref_images": [{"path": self.a}, {"path": os.path.join(self.tmp, "gone.png")}, self.b]}
        self.assertEqual(self.m.review_paths(scene), [os.path.abspath(self.a), os.path.abspath(self.b)])
        self.assertEqual(self.m.review_paths({}), [])

    def test_pick_moves_first(self):
        scene = {"ref_images": [{"path": self.a, "source": "pdf"}, {"path": self.b, "source": "video", "time": 3}]}
        self.m.pick_ref_image(scene, self.b)
        self.assertEqual(scene["ref_images"][0]["path"], self.b)
        self.assertEqual(scene["ref_images"][0]["time"], 3)
        self.assertEqual(len(scene["ref_images"]), 2)


class WiringTest(unittest.TestCase):
    def test_editor_binding(self):
        ed = (ROOT / "gui" / "dl" / "scene_editor.py").read_text(encoding="utf-8")
        self.assertIn('tx.bind("<Control-Double-Button-1>", _on_tx_ctrl_double)', ed)
        self.assertNotIn("_bind_text_editor_replace_from_clipboard_on_double_click", ed)  # t439u: 普通双击 = 默认选词
        self.assertNotIn('tx.bind("<Double-Button-1>"', ed)
        body = ed[ed.index("def _on_tx_ctrl_double"):ed.index('tx.bind("<Control-Double-Button-1>"')]
        self.assertIn('return "break"', body)
        self.assertIn("on_persist_keep_open()", body)


if __name__ == "__main__":
    unittest.main()
