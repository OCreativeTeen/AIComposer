"""t418u: 生场视频 MiniMax 没有讲话（讲话当故事内容 / 讲话没勾）时长度要从 6 / 9 / 12 秒里选，不自动；
讲话勾着照旧自动。帧数沿用 minimax_submit_seconds（24fps，17n+5）：158 / 226 / 294 帧。"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_minimax_dynamic_length import SDP  # noqa: E402

DLG = Path(ROOT, "gui/video_prompt_dialog.py").read_text(encoding="utf-8")


def _module_fns():
    tree = ast.parse(DLG)
    want = {"MINIMAX_FIXED_LENGTHS", "DEFAULT_MINIMAX_FIXED_LENGTH", "MINIMAX_FIXED_LENGTH_KEY",
            "minimax_fixed_length", "minimax_fixed_length_mode"}
    parts = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in want for t in node.targets):
            parts.append(ast.get_source_segment(DLG, node))
        elif isinstance(node, ast.FunctionDef) and node.name in want:
            parts.append(ast.get_source_segment(DLG, node))
    ns = {}
    exec("\n\n".join(parts), ns)
    return ns


NS = _module_fns()


class FixedLengthLogicTest(unittest.TestCase):
    def test_choices_default_key(self):
        self.assertEqual([v for v, _l in NS["MINIMAX_FIXED_LENGTHS"]], ["6s", "9s", "12s"])
        self.assertEqual([l for _v, l in NS["MINIMAX_FIXED_LENGTHS"]], ["6秒", "9秒", "12秒"])
        self.assertEqual(NS["DEFAULT_MINIMAX_FIXED_LENGTH"], "6s")
        self.assertEqual(NS["MINIMAX_FIXED_LENGTH_KEY"], "minimax_fixed_duration")
        f = NS["minimax_fixed_length"]
        self.assertEqual(f(None), "6s")
        self.assertEqual(f("auto"), "6s")
        self.assertEqual(f("10s"), "6s")
        self.assertEqual(f("9s"), "9s")
        self.assertEqual(f(" 12S "), "12s")

    def test_mode(self):
        m = NS["minimax_fixed_length_mode"]
        self.assertFalse(m(False, False, True))  # Grok / Gemini 不管
        self.assertFalse(m(True, True, False))  # 讲话 → 自动
        self.assertTrue(m(True, False, True))  # 讲话当故事内容
        self.assertTrue(m(True, True, True))  # 两个都记着 → 故事内容优先
        self.assertTrue(m(True, False, False))  # 都没勾 = 没有讲话
        self.assertFalse(m(True, False, False, "sing", True))  # 讲话没勾但用场景音频 → 跟音频
        self.assertTrue(m(True, False, False, "sing", False))  # 这一场没音频
        self.assertTrue(m(True, False, True, "talk", True))  # 故事内容：场景音频不加

    def test_frames_for_choices(self):
        submit, h3 = SDP["minimax_submit_seconds"], SDP["minimax_h3_frames"]
        got = {v: h3(submit(v)) for v, _l in NS["MINIMAX_FIXED_LENGTHS"]}
        self.assertEqual(got, {"6s": 158, "9s": 226, "12s": 294})
        for frames in got.values():
            self.assertEqual(frames % 17, 5)


class DialogWiringTest(unittest.TestCase):
    def test_saved_and_remembered(self):
        self.assertIn("mm_fixed_var = tk.StringVar(value=minimax_fixed_length(_sv_len.get(MINIMAX_FIXED_LENGTH_KEY)))", DLG)
        cur = DLG.split("def current_choice()", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("MINIMAX_FIXED_LENGTH_KEY: minimax_fixed_length(mm_fixed_var.get())", cur)
        self.assertIn("for _v in (duration_var, mm_fixed_var,", DLG)

    def test_on_go_uses_fixed_length(self):
        go = DLG.split("    def on_go(", 1)[1].split("\n    def ", 1)[0]
        i = go.index("_dur = duration_var.get()")
        j = go.index('if _dur == "auto":')
        head = go[i:j]
        self.assertIn("minimax_fixed_length_mode(", head)
        self.assertIn("_dur = minimax_fixed_length(mm_fixed_var.get())", head)
        self.assertIn("_secs = float(_sdp.minimax_submit_seconds(_dur))", go)

    def test_no_segments_without_speech(self):
        seg = DLG.split("    def _seg_count(sc) -> int:", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("_cfg_mm.is_minimax(backend_var.get()) and (story_var.get() or not speaking_var.get())", seg)
        self.assertLess(seg.index("return 1"), seg.index('episode.get("segments")'))

    def test_length_box_switches(self):
        self.assertIn("mm_fixed_radios = [ttk.Radiobutton(length_box, text=label, value=value, variable=mm_fixed_var)", DLG)
        sb = DLG.split("    def _sync_backend(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("fixed = minimax_fixed_length_mode(mm, bool(speaking_var.get()), bool(story_var.get()),", sb)
        self.assertIn("rb.pack(anchor=tk.W, before=auto_info_lbl)", sb)
        self.assertIn("没有讲话：MiniMax 长度要选（不自动）", sb)
        self.assertIn('speaking_var.trace_add("write", _sync_backend)', DLG)
        self.assertIn('story_var.trace_add("write", _sync_backend)', DLG)

    def test_file_stays_lf(self):
        self.assertNotIn(b"\r\n", Path(ROOT, "gui/video_prompt_dialog.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
