"""t419u / t420u: 生场视频「没有讲话」（讲话当故事内容，或讲话没勾且场景音频不加）生成的视频，
导入（包括全集 / 双机自动导入）时声音一律换成本场原来的音频（配声），视频自带的音效不用；
固定 6 / 9 / 12 秒的视频按「配声」变速对齐到本场音频长度，本场音频和时间轴不变。
没有讲话是提交时记在 scene["video_speech_speed"]["no_speech"]，导入时按文件认，不看对话框现在的勾选。"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _src(rel: str) -> str:
    return Path(ROOT, rel).read_text(encoding="utf-8")


CP = _src("config_prompt.py")
DLG = _src("gui/video_prompt_dialog.py")
FLOWS = _src("gui/workflow/wf_prompt_flows.py")
IMPORT = _src("gui/workflow/wf_media_import.py")
SCANNER = _src("utility/media_scanner.py")


def _module_parts(src: str, names: set) -> dict:
    tree = ast.parse(src)
    parts = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in names for t in node.targets):
            parts.append(ast.get_source_segment(src, node))
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            parts.append(ast.get_source_segment(src, node))
    ns: dict = {}
    exec("\n\n".join(parts), ns)
    return ns


def _method(src: str, name: str) -> str:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            import textwrap

            return textwrap.dedent(ast.get_source_segment(src, node))
    raise AssertionError(name)


CPNS = _module_parts(CP, {"NO_SPEECH_RECORD_KEY", "video_no_speech_mode", "recorded_no_speech",
                          "recorded_speech_speed"})


class NoSpeechModeTest(unittest.TestCase):
    def test_mode_table(self):
        f = CPNS["video_no_speech_mode"]
        self.assertTrue(f(True, False, "none"))      # 讲话当故事内容
        self.assertTrue(f(True, True, "talk"))       # 故事内容优先
        self.assertTrue(f(False, False, "none"))     # 两个都没勾
        self.assertFalse(f(False, True, "none"))     # 讲话
        self.assertFalse(f(False, False, "talk"))    # 场景音频作为说话
        self.assertFalse(f(False, False, "sing"))
        self.assertEqual(CPNS["NO_SPEECH_RECORD_KEY"], "no_speech")

    def test_recorded_matches_file(self):
        f = CPNS["recorded_no_speech"]
        sc = {"video_speech_speed": {"speed": 1.0, "at": time.time(), "file": "a.mp4", "no_speech": True}}
        self.assertTrue(f(sc, r"D:\x\A.MP4".replace("\\", os.sep)))
        self.assertFalse(f(sc, "b.mp4"))
        sc["video_speech_speed"]["no_speech"] = False
        self.assertFalse(f(sc, "a.mp4"))
        self.assertFalse(f({}, "a.mp4"))
        self.assertFalse(f(None, "a.mp4"))

    def test_recorded_by_mtime_without_file(self):
        f = CPNS["recorded_no_speech"]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "v.mp4")
            Path(p).write_bytes(b"x")
            sc = {"video_speech_speed": {"speed": 1.0, "at": time.time(), "no_speech": True}}
            self.assertTrue(f(sc, p))
            sc["video_speech_speed"]["at"] = time.time() + 100  # 提交之前就有的文件不认
            self.assertFalse(f(sc, p))
            self.assertFalse(f(sc, os.path.join(d, "missing.mp4")))


class SubmitRecordTest(unittest.TestCase):
    def test_on_go_records_flag(self):
        i = DLG.index('scenes[0]["video_speech_speed"] = {')
        block = DLG[i:i + 500]
        self.assertIn("config_prompt.NO_SPEECH_RECORD_KEY: config_prompt.video_no_speech_mode(story_on, use_sp, _amode)",
                      block)
        # 记录在 _amode 被讲话当故事内容压成 none 之后
        self.assertLess(DLG.index('_amode = "none"', DLG.index("def on_go(")), i)


class _Root:
    def after(self, _ms, fn=None):
        if fn:
            fn()


class AutoImportTest(unittest.TestCase):
    def _run(self, rec):
        cp = types.SimpleNamespace(
            recorded_no_speech=CPNS["recorded_no_speech"],
            recorded_speech_speed=lambda sc, p: (rec or {}).get("speed"),
            attach_video_prompt_file=lambda sc, p: None,
        )
        fake_dlg = types.ModuleType("gui.mp4_pick_preview_dialog")
        fake_dlg.default_video_range = lambda p: (0.0, 6.5)
        ns = {"os": os, "config_prompt": cp}
        exec(_method(FLOWS, "_auto_import_scene_video"), ns)
        picks, pairs = [], []
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "gen.mp4")
            Path(path).write_bytes(b"x")
            scene = {"clip_audio": "voice.wav"}
            if rec is not None:
                scene["video_speech_speed"] = dict(rec, file="gen.mp4")
            done = threading.Event()
            this = types.SimpleNamespace(
                root=_Root(),
                workflow=types.SimpleNamespace(scenes=[scene]),
                current_scene_index=0,
                _project_input_dir=lambda k: d + "_other",
                _build_volume_adjusted_mp4_wav_pair=lambda p, v, start, end, speed: (
                    pairs.append(speed) or ("t.mp4", "t.wav")),
                _apply_editor_pick=lambda pick, stage_download, on_done: (picks.append(pick), done.set()),
            )
            with mock.patch.dict(sys.modules, {"gui.mp4_pick_preview_dialog": fake_dlg}):
                ns["_auto_import_scene_video"](this, scene, path, lambda ok, why: done.set())
                self.assertTrue(done.wait(5))
        return picks[0], pairs[0]

    def test_no_speech_uses_scene_audio(self):
        pick, spd = self._run({"speed": 1.0, "at": time.time(), "no_speech": True})
        self.assertEqual(pick["radio"], "replace_speed")  # 配声：本场音频，视频变速对齐
        self.assertTrue(pick.get("no_speech"))
        self.assertEqual(spd, 1.0)

    def test_no_speech_ignores_speed_record(self):
        pick, spd = self._run({"speed": 0.8, "at": time.time(), "no_speech": True})
        self.assertEqual(spd, 1.0)
        self.assertEqual(pick["radio"], "replace_speed")

    def test_speaking_keeps_existing_behaviour(self):
        pick, spd = self._run({"speed": 0.8, "at": time.time(), "no_speech": False})
        self.assertEqual(pick["radio"], "keep")
        self.assertNotIn("no_speech", pick)
        self.assertEqual(spd, 0.8)

    def test_old_record_without_flag(self):
        pick, _spd = self._run({"speed": 1.0, "at": time.time()})
        self.assertEqual(pick["radio"], "keep")


class ReplaceSpeedKeepsSceneAudioTest(unittest.TestCase):
    """配声：clip_audio 不动（本场时间轴不变），视频按本场音频长度变速，mp4 里的声音换成本场音频。"""

    def test_replace_speed(self):
        calls = []
        refreshed = []

        def refresh(scene, key, ext, src):
            refreshed.append(key)
            scene[key] = "new_" + key + ext
            return None, scene[key]

        fp = types.SimpleNamespace(
            height=720,
            resize_video=lambda v, width=None, height=None: v,
            get_video_fps=lambda v: 24,
            add_audio_to_video=lambda v, a, m, mode: (calls.append((v, a, m, mode)), "fitted.mp4")[1],
        )
        ap = types.SimpleNamespace(extract_audio_from_video=lambda v: "gen.wav")
        ns = {"os": os, "refresh_scene_media": refresh,
              "get_file_path": lambda sc, k: sc.get(k)}
        exec(_method(SCANNER, "video_simple_replacement"), ns)
        this = types.SimpleNamespace(
            workflow=types.SimpleNamespace(ffmpeg_processor=fp, ffmpeg_audio_processor=ap),
            last_image_replacement=lambda *a: None,
        )
        scene = {"clip": "old.mp4", "clip_audio": "voice.wav"}
        ns["video_simple_replacement"](this, scene, "gen.mp4", "gen.wav", "replace_speed", "clip")
        self.assertEqual(calls, [("gen.mp4", "voice.wav", True, "speed")])
        self.assertEqual(refreshed, ["clip"])          # clip_audio 不换
        self.assertEqual(scene["clip_audio"], "voice.wav")


class ManualImportDefaultTest(unittest.TestCase):
    def test_manual_default_is_scene_audio(self):
        i = IMPORT.index("sound_radios = (")
        self.assertIn('"replace_speed",\n        )', IMPORT[i:i + 300].replace("\r\n", "\n"))


if __name__ == "__main__":
    unittest.main()
