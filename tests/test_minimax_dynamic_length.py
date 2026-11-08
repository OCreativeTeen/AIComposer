"""Offline tests for MiniMax dynamic frame length (t306u).

Frame helpers are loaded from the sd_image_processor source slice so this
file never imports rembg/openai/config.py (no .env).
"""
from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_sdp_timing():
    src = Path(ROOT, "utility/sd_image_processor.py").read_text(encoding="utf-8")
    a = src.index("def _align_h3_frames")
    b = src.index("\ndef _find_nodes")
    p0 = src.index("def _parse_size")
    d = src.index("\ndef crop_to_aspect")
    chunk = "import math\nMINIMAX_H3_FPS = 24\n" + src[a:b] + "\n" + src[p0:d]
    ns = {
        "math": math,
        "os": os,
        "config": SimpleNamespace(
            MINIMAX_SIZE_6S="1312x736",
            MINIMAX_SIZE_XLARGE="1280x704",
            MINIMAX_SIZE_LARGE="1120x640",
        ),
    }
    exec(compile(chunk, "sd_image_processor.py", "exec"), ns)
    return ns


SDP = _load_sdp_timing()


class MiniMaxFrameMathTest(unittest.TestCase):
    def test_source_backed_bounds_and_old_buckets(self):
        h3 = SDP["minimax_h3_frames"]
        exact = SDP["minimax_exact_seconds"]
        self.assertEqual(SDP["MINIMAX_H3_FPS"], 24)
        self.assertEqual(h3(5), 124)
        self.assertAlmostEqual(exact(5), 124 / 24)
        self.assertAlmostEqual(SDP["MINIMAX_MIN_SECONDS"], 5.1666666667, places=6)
        self.assertEqual(h3(6), 158)
        self.assertAlmostEqual(exact(6), 158 / 24)
        self.assertEqual(h3(9), 226)
        self.assertAlmostEqual(exact(9), 226 / 24)
        self.assertEqual(h3(12), 294)
        self.assertAlmostEqual(exact(12), 294 / 24)
        self.assertEqual(SDP["MINIMAX_MIN_FRAMES"], 124)
        self.assertEqual(SDP["MINIMAX_MAX_FRAMES"], 294)
        self.assertAlmostEqual(SDP["MINIMAX_MAX_SECONDS"], 12.25)

    def test_legal_frames_are_17n_plus_5_not_8n_plus_1(self):
        for frames in (124, 141, 158, 175, 192, 209, 226, 243, 260, 277, 294):
            self.assertEqual((frames - 5) % 17, 0)
        self.assertEqual((124 - 1) % 8, 3)

    def test_ceil_plus_one_then_align(self):
        speech = SDP["minimax_frames_for_speech"]
        sec = SDP["minimax_seconds_from_frames"]
        self.assertEqual(speech(7.0), 175)
        self.assertAlmostEqual(sec(175), 175 / 24)
        self.assertEqual(speech(8.0 + 1e-12), speech(8.0))
        self.assertEqual(speech(8.0), 209)
        self.assertNotIn(speech(8.0), (158, 226, 294))
        self.assertAlmostEqual(sec(speech(8.0)), 8.7083333333, places=6)

    def test_clamp_min_and_max(self):
        speech = SDP["minimax_frames_for_speech"]
        self.assertEqual(speech(0), 124)
        self.assertEqual(speech(1.0), 124)
        self.assertEqual(speech(4.9), 124)
        self.assertEqual(speech(20.0), 294)
        self.assertEqual(speech(12.25), 294)
        self.assertEqual(speech(13.0), 294)

    def test_submit_seconds_does_not_snap_middle_to_bucket(self):
        sec = SDP["minimax_seconds_from_frames"]
        submit = SDP["minimax_submit_seconds"]
        snap = SDP["minimax_snap_seconds"]
        h3 = SDP["minimax_h3_frames"]
        mid = sec(209)
        self.assertEqual(snap(mid), 9)
        self.assertAlmostEqual(submit(f"{mid:.10g}s"), mid)
        self.assertEqual(h3(submit(f"{mid:.10g}s")), 209)
        self.assertAlmostEqual(submit("12s"), 12.25)
        self.assertAlmostEqual(submit("6s"), 158 / 24)
        self.assertAlmostEqual(submit("9s"), 226 / 24)
        self.assertAlmostEqual(submit("10s"), 226 / 24)
        s = submit("7.2916666667s")
        self.assertEqual(h3(s), 175)
        self.assertAlmostEqual(submit(s), s)

    def test_audio_follows_same_alignment_keeps_4s_floor(self):
        audio = SDP["minimax_audio_video_seconds"]
        h3 = SDP["minimax_h3_frames"]
        self.assertAlmostEqual(audio(0), 12.25)
        self.assertAlmostEqual(audio(20), 12.25)
        self.assertEqual(h3(audio(4.0)), 107)
        self.assertGreaterEqual(audio(5.5) * 24, 107)
        self.assertEqual(h3(audio(5.5)), 141)
        self.assertEqual((h3(audio(7.01)) - 5) % 17, 0)

    def test_resolution_tiers_use_actual_duration(self):
        size_for = SDP["minimax_size_for"]
        w, h, why = size_for("landscape", 6.0, False)
        self.assertEqual((w, h), (1312, 736))
        self.assertIn("158", why)
        w, h, _ = size_for("landscape", 175 / 24, False)
        self.assertEqual((w, h), (1280, 704))
        w, h, _ = size_for("landscape", 8.708333, False)
        self.assertEqual((w, h), (1280, 704))
        w, h, _ = size_for("landscape", 12.25, False)
        self.assertEqual((w, h), (1120, 640))


class MiniMaxDynamicChoiceTest(unittest.TestCase):
    def test_empty_speech_uses_min(self):
        from config_prompt import auto_minimax_dynamic_choice

        length, speed, normal, why = auto_minimax_dynamic_choice("")
        self.assertAlmostEqual(float(length.rstrip("s")), SDP["MINIMAX_MIN_SECONDS"])
        self.assertEqual(speed, 1.0)
        self.assertEqual(normal, 0.0)
        self.assertIn(str(SDP["MINIMAX_MIN_FRAMES"]), why)

    def test_middle_speech_not_bucketed(self):
        from config_prompt import auto_minimax_dynamic_choice, minimax_speech_seconds

        text = "这是一句普通的中文台词，用来确认中间时长不会被套进六九十二十三档。"
        est = minimax_speech_seconds(text)
        self.assertGreater(est, 0)
        frames = SDP["minimax_frames_for_speech"](est)
        length, speed, normal, why = auto_minimax_dynamic_choice(text)
        self.assertEqual(length, f"{SDP['minimax_seconds_from_frames'](frames):.10g}s")
        self.assertNotIn(length, ("6s", "9s", "12s"))
        if est <= frames / 24 + 1e-9:
            self.assertEqual(speed, 1.0)
        self.assertAlmostEqual(normal, est)

    def test_over_max_speedup_and_slowback_use_actual_12_25(self):
        from config_prompt import AUTO_SPEED_FLOOR, auto_minimax_dynamic_choice, minimax_speech_seconds

        text = "测试超长台词。" * 80
        est = minimax_speech_seconds(text)
        self.assertGreater(est, SDP["MINIMAX_MAX_SECONDS"])
        length, speed, normal, why = auto_minimax_dynamic_choice(text)
        self.assertAlmostEqual(float(length.rstrip("s")), SDP["MINIMAX_MAX_SECONDS"])
        raw = SDP["MINIMAX_MAX_SECONDS"] / est
        self.assertAlmostEqual(speed, round(max(AUTO_SPEED_FLOOR, raw), 3))
        self.assertIn(str(SDP["MINIMAX_MAX_FRAMES"]), why)
        self.assertLess(speed, 1.0)
        self.assertAlmostEqual(
            SDP["MINIMAX_MAX_SECONDS"] / speed,
            est if raw >= AUTO_SPEED_FLOOR else SDP["MINIMAX_MAX_SECONDS"] / AUTO_SPEED_FLOOR,
        )

    def test_grok_gemini_tiers_unchanged(self):
        from config_prompt import AUTO_LEN_STD, auto_length_for_backend, auto_length_speed_choice

        text = "Hello there, this is a short line."
        length, speed, normal, why = auto_length_for_backend(text, False)
        self.assertIn(length, AUTO_LEN_STD)
        length2, *_ = auto_length_speed_choice(text, AUTO_LEN_STD)
        self.assertEqual(length, length2)
        self.assertIn(length2, ("6s", "10s", "15s"))

    def test_prompt_helpers_match_sdp_formula(self):
        from config_prompt import _minimax_frames_for_speech

        for s in (0, 1, 5, 5.17, 6, 7, 8, 8.0417, 10, 11.2, 12.25, 20):
            self.assertEqual(_minimax_frames_for_speech(s), SDP["minimax_frames_for_speech"](s))

    def test_auto_info_and_dialog_contracts(self):
        from config_prompt import auto_info_text

        info = auto_info_text("7.291666667s", 1.0)
        self.assertIn("7.29秒", info)
        self.assertIn("175帧", info)
        info2 = auto_info_text("10s", 0.8)
        self.assertIn("自动: 10秒", info2)
        self.assertIn("说快", info2)
        dlg = Path(ROOT, "gui/video_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn("自动（范围）", dlg)
        self.assertIn("auto_minimax_dynamic_choice", dlg)
        self.assertIn("minimax_submit_seconds", dlg)
        self.assertNotIn("minimax_snap_seconds(_dur)", dlg)
        self.assertIn("_speech_speed = 1.0", dlg)
        dual = Path(ROOT, "utility/minimax_dual.py").read_text(encoding="utf-8")
        self.assertIn("minimax_submit_seconds", dual)
        self.assertNotIn("minimax_snap_seconds(extra", dual)
        wf = Path(ROOT, "workflow/MiniMax_H3_api_5070.json").read_text(encoding="utf-8")
        self.assertIn("max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17", wf)
        self.assertIn('"value": 5.0', wf)


if __name__ == "__main__":
    unittest.main()
