"""t386u: 每次导入 clip 视频（全集 / 本集 / 生场视频 / 手动导入），末帧接到下一场 zero_image_last 之前
都按「尾帧增强」增强（后台），离线测试：增强器、写入都是假的，不碰 ComfyUI / tkinter / .env。"""
from __future__ import annotations

import ast
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utility import last_frame_chain as lfc  # noqa: E402


def _segment(rel: str, name: str) -> str:
    src = (ROOT / rel).read_text(encoding="utf-8")
    node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(src, node)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t386_")
        self.frame = os.path.join(self.tmp, "frame.webp")
        Path(self.frame).write_bytes(b"RAWFRAME")
        self.raw_dest = os.path.join(self.tmp, "next_zero_last_raw.webp")
        Path(self.raw_dest).write_bytes(b"RAWFRAME")
        self.next_scene = {"id": 7, "zero_image_last": self.raw_dest}
        self.writes = []
        self.saved = []
        self.seen = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def writer(self, scene, src):
        dest = os.path.join(self.tmp, f"next_zero_last_{len(self.writes)}.png")
        shutil.copyfile(src, dest)
        scene["zero_image_last"] = dest
        self.writes.append(dest)
        return dest

    def enhancer_ok(self, p):
        self.seen.append(p)
        self.assertTrue(os.path.isfile(p))
        out = os.path.join(self.tmp, "enhanced_tmp.png")
        Path(out).write_bytes(b"ENHANCED")
        return out, True, "1080x1920"

    def start(self, **kw):
        args = dict(mode="qn", enhancer=self.enhancer_ok, writer=self.writer,
                    on_written=self.saved.append, run_async=False)
        args.update(kw)
        return lfc.start_enhanced_chain(self.next_scene, self.raw_dest, self.frame, **args)


class EnhanceChainTest(_Base):
    def test_enhanced_replaces_raw_and_saves(self):
        self.assertTrue(self.start())
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(Path(self.next_scene["zero_image_last"]).read_bytes(), b"ENHANCED")
        self.assertEqual(self.saved, [self.writes[0]])
        # 增强器拿的是自己的一份拷贝，不是原末帧；拷贝和增强临时图都清掉
        self.assertNotEqual(self.seen[0], self.frame)
        self.assertFalse(os.path.exists(self.seen[0]))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "enhanced_tmp.png")))
        self.assertTrue(os.path.isfile(self.frame))

    def test_none_mode_keeps_raw(self):
        self.assertFalse(self.start(mode="none"))
        self.assertEqual(self.seen, [])
        self.assertEqual(self.next_scene["zero_image_last"], self.raw_dest)

    def test_failed_enhance_keeps_raw(self):
        self.assertTrue(self.start(enhancer=lambda p: (p, False, "ComfyUI 连不上")))
        self.assertEqual(self.writes, [])
        self.assertEqual(self.saved, [])
        self.assertEqual(self.next_scene["zero_image_last"], self.raw_dest)

    def test_enhancer_exception_keeps_raw(self):
        def boom(p):
            raise RuntimeError("timeout")

        self.assertTrue(self.start(enhancer=boom))
        self.assertEqual(self.writes, [])
        self.assertEqual(self.next_scene["zero_image_last"], self.raw_dest)

    def test_newer_import_wins_over_stale_result(self):
        newer = os.path.join(self.tmp, "newer_raw.webp")
        Path(newer).write_bytes(b"NEWER")

        def slow(p):
            self.next_scene["zero_image_last"] = newer  # 增强期间又导入了一次
            return self.enhancer_ok(p)

        self.assertTrue(self.start(enhancer=slow))
        self.assertEqual(self.writes, [])
        self.assertEqual(self.next_scene["zero_image_last"], newer)

    def test_scene_gone_or_project_switched(self):
        self.assertTrue(self.start(still_valid=lambda: False))
        self.assertEqual(self.writes, [])
        self.assertEqual(self.next_scene["zero_image_last"], self.raw_dest)

    def test_writer_failure_keeps_raw(self):
        def bad_writer(scene, src):
            raise OSError("disk full")

        self.assertTrue(self.start(writer=bad_writer))
        self.assertEqual(self.next_scene["zero_image_last"], self.raw_dest)
        self.assertEqual(self.saved, [])

    def test_dispatch_runs_write_on_main_thread_queue(self):
        queue = []
        self.assertTrue(self.start(dispatch=queue.append))
        self.assertEqual(self.writes, [], "nothing written until the main thread runs the callback")
        self.assertEqual(len(queue), 1)
        queue[0]()
        self.assertEqual(Path(self.next_scene["zero_image_last"]).read_bytes(), b"ENHANCED")

    def test_runs_in_background_thread(self):
        gate, done = threading.Event(), threading.Event()
        main = threading.get_ident()
        where = []

        def slow(p):
            where.append(threading.get_ident())
            gate.wait(5)
            return self.enhancer_ok(p)

        self.assertTrue(self.start(enhancer=slow, run_async=True, on_written=lambda p: done.set()))
        self.assertEqual(self.writes, [], "start returns before enhancement finishes (GUI not blocked)")
        gate.set()
        self.assertTrue(done.wait(5))
        self.assertNotEqual(where[0], main)
        self.assertEqual(len(self.writes), 1)

    def test_missing_frame_or_raw_dest(self):
        self.assertFalse(lfc.start_enhanced_chain(self.next_scene, "", self.frame, mode="qn",
                                                  enhancer=self.enhancer_ok, run_async=False))
        self.assertFalse(lfc.start_enhanced_chain(self.next_scene, self.raw_dest, "/nope.webp", mode="qn",
                                                  enhancer=self.enhancer_ok, run_async=False))
        self.assertEqual(self.seen, [])


class SettingsTest(unittest.TestCase):
    def test_saved_enhance_mode(self):
        self.assertEqual(lfc.saved_enhance_mode({"video_prompt": {"last_frame_enhance": "qn"}}), "qn")
        self.assertEqual(lfc.saved_enhance_mode({"video_prompt": {"last_frame_enhance": "Qwen"}}), "qn")
        self.assertEqual(lfc.saved_enhance_mode({"video_prompt": {"last_frame_enhance": "none"}}), "none")
        self.assertEqual(lfc.saved_enhance_mode({"video_prompt": {}}), "qn")
        self.assertEqual(lfc.saved_enhance_mode({}), "qn")  # t395u

    def test_saved_visual_style(self):
        self.assertEqual(lfc.saved_visual_style({"visual_style": " 梦幻 "}), "梦幻")
        self.assertEqual(lfc.saved_visual_style({}), "")

    def test_segment_pending_registry(self):
        clone = {"id": 991}
        self.assertFalse(lfc.is_segment_chain_pending(clone))
        lfc.mark_segment_chain_pending(clone)
        self.assertTrue(lfc.is_segment_chain_pending({"id": "991"}))
        lfc.clear_segment_chain_pending(clone)
        self.assertFalse(lfc.is_segment_chain_pending(clone))
        self.assertFalse(lfc.is_segment_chain_pending(None))


class SourceContractTest(unittest.TestCase):
    def test_every_clip_import_goes_through_enhanced_chain(self):
        seg = _segment("utility/media_scanner.py", "last_image_replacement")
        self.assertIn("raw_dest = write_chained_next_zero_image_last(next_scene, last_image)", seg)
        self.assertIn("self._enhance_chained_last_frame(current_scene, next_scene, raw_dest, frame)", seg)
        enh = _segment("utility/media_scanner.py", "_enhance_chained_last_frame")
        self.assertIn("is_segment_chain_pending(current_scene)", enh)
        self.assertIn("saved_enhance_mode(pc)", enh)
        self.assertIn("still_valid", enh)
        # 所有导入入口都调 last_image_replacement
        for name in ("video_simple_replacement", "take_gen_video"):
            self.assertIn("self.last_image_replacement(", _segment("utility/media_scanner.py", name), name)

    def test_segment_flow_not_enhanced_twice(self):
        flows = "gui/workflow/wf_prompt_flows.py"
        self.assertIn('mark_segment_chain_pending(tok["clone"])', _segment(flows, "_split_video_segment"))
        self.assertIn("clear_segment_chain_pending(", _segment(flows, "_undo_video_segment"))
        self.assertIn("clear_segment_chain_pending(clone)", _segment(flows, "_chain_video_segment"))

    def test_gui_marshals_write_to_main_thread(self):
        src = (ROOT / "GUI_wf.py").read_text(encoding="utf-8")
        self.assertIn("self.media_scanner.ui_call = lambda fn: self.root.after(0, fn)", src)
        self.assertIn("self.media_scanner.on_chain_written = _chain_written", src)


if __name__ == "__main__":
    unittest.main()
