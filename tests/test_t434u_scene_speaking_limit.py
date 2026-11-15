"""t434u: 从文字稿生成场景：一场讲话最多 115 个字（汉字 1、英文词 / 数字 2、标点不算），约 25 秒；
超了按句拆成连续的几场（在人物对位以前），起止时间取自文字稿的句子时间。"""
import pathlib
import unittest

from tests.test_video_speaker_semantics import _install_stubs

_install_stubs()

from utility.media_transcript import (
    SCENE_SPEAKING_MAX_SECONDS,
    SCENE_SPEAKING_MAX_UNITS,
    apply_verbatim_speaking,
    split_long_transcript_scenes,
    speaking_units,
)  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
S20 = "这是一句二十个字左右的测试句子用来看看分场效果"  # 23 字


def _transcript(n, step=4.0, change_at=None):
    lines = []
    for i in range(n):
        t = i * step
        mark = "<1> " if i == 0 else ("<2> " if i == change_at else "")
        lines.append(f"[00:{int(t // 60):02d}:{t % 60:04.1f}] {mark}{S20}{i}。")
    return "\n".join(lines)


def _run(scenes, text):
    apply_verbatim_speaking(scenes, text)
    return split_long_transcript_scenes(scenes, text)


class UnitsTest(unittest.TestCase):
    def test_counting(self):
        self.assertEqual(SCENE_SPEAKING_MAX_UNITS, 115)
        self.assertEqual(SCENE_SPEAKING_MAX_SECONDS, 25.0)
        self.assertEqual(speaking_units("<1> 你好，世界！"), 4)  # 标点、标记不算
        self.assertEqual(speaking_units("Hello world."), 4)  # 一个英文词算 2
        self.assertEqual(speaking_units("<2> 我们 2026 年 don't stop"), 3 + 2 + 4)


class SplitTest(unittest.TestCase):
    def test_short_scene_untouched(self):
        text = _transcript(4)
        scenes = [{"caption": "A", "start": 0, "end": 16.0}]
        out, added = _run(scenes, text)
        self.assertEqual(added, 0)
        self.assertIs(out[0], scenes[0])

    def test_long_scene_split_balanced_with_times(self):
        text = _transcript(12, step=2.0, change_at=3)  # 12 句 × 25 = 300，24 秒
        scene = {"caption": "A", "visual": "客厅里两个人", "actor": "1 主持人; 2 嘉宾", "episode": "1",
                 "start": 0, "end": 24.0}
        out, added = _run([scene, {"caption": "B", "start": 24.0, "end": 30.0}], text)
        self.assertEqual(added, 2)
        parts = out[:3]
        units = [speaking_units(p["speaking"]) for p in parts]
        self.assertTrue(all(u <= 115 for u in units), units)
        self.assertEqual(sum(units), 12 * 25)  # 23 字 + 序号（数字算 2）
        self.assertEqual(units, [100, 100, 100])
        self.assertEqual([(p["start"], p["end"]) for p in parts], [(0, 8.0), (8.0, 16.0), (16.0, 24.0)])
        for p in parts:  # 同一个故事场景：画面、人物、集号都沿用
            self.assertEqual((p["caption"], p["visual"], p["actor"], p["episode"]),
                             ("A", "客厅里两个人", "1 主持人; 2 嘉宾", "1"))
            self.assertRegex(p["speaking"], r"^<\d> ")
        self.assertTrue(parts[0]["speaking"].startswith("<1> "))
        self.assertIn("<2> ", parts[0]["speaking"])  # 第 4 句换人
        self.assertTrue(parts[1]["speaking"].startswith("<2> "))
        self.assertEqual(out[3]["caption"], "B")

    def test_single_long_sentence_cut_at_commas(self):
        clause = "我们今天来聊一聊这个非常重要的问题"  # 17 字
        text = "[00:00:00.0] <1> " + "，".join([clause] * 10) + "。\n[00:00:20.0] 好。"
        out, added = _run([{"caption": "L", "start": 0, "end": 22.0}], text)
        self.assertEqual(added, 1)
        for p in out:
            self.assertLessEqual(speaking_units(p["speaking"]), 115)
        self.assertTrue(out[0]["speaking"].endswith("，"))  # 在逗号后面切
        self.assertEqual(sum(speaking_units(p["speaking"]) for p in out), 171)
        self.assertEqual(out[0]["start"], 0)
        self.assertEqual(out[-1]["end"], 22.0)
        self.assertEqual(out[0]["end"], out[1]["start"])

    def test_sentence_without_punctuation_hard_split(self):
        text = "[00:00:00.0] <1> " + "字" * 200 + "\n"
        out, added = _run([{"start": 0, "end": 30.0}], text)
        self.assertEqual(added, 1)
        self.assertEqual([speaking_units(p["speaking"]) for p in out], [100, 100])

    def test_english_words_count_double(self):
        sentence = " ".join(["word"] * 20) + "."  # 40 units
        text = "\n".join(f"[00:00:{i * 3:04.1f}] {'<1> ' if i == 0 else ''}{sentence}" for i in range(4))
        out, added = _run([{"start": 0, "end": 12.0}], text)
        self.assertEqual(added, 1)  # 160 → 2 场 80 + 80
        self.assertEqual([speaking_units(p["speaking"]) for p in out], [80, 80])

    def test_seconds_second_check(self):
        text = "\n".join(f"[00:00:{i * 10:04.1f}] {'<1> ' if i == 0 else ''}好的。" for i in range(5))
        out, added = _run([{"start": 0, "end": 50.0}], text)  # 只有 10 个字，但 50 秒
        self.assertGreaterEqual(added, 1)
        for p in out:
            self.assertLessEqual(p["end"] - p["start"], 25.0)

    def test_no_timeline_no_change(self):
        scenes = [{"caption": "A", "speaking": "x" * 10}]
        out, added = split_long_transcript_scenes(scenes, _transcript(40))
        self.assertEqual((out, added), (scenes, 0))


class WiringTest(unittest.TestCase):
    def test_not_split_at_scene_generation(self):
        # t436u: 生成场景时不再按 115 字拆（建项目时由 utility/scene_prep 整理、拆分）
        src = (ROOT / "gui" / "downloader.py").read_text(encoding="utf-8")
        self.assertIn("apply_verbatim_speaking(scenes, transcript_text)", src)
        self.assertNotIn("split_long_transcript_scenes(", src)

    def test_llm_not_limited(self):
        # t436u: 提示词只按完整的故事片段分场，不限时长 / 字数
        for rel in ("gui/dl/prompts_notebooklm.py", "config_channel.py"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                self.assertNotIn("115 units", src)
                self.assertIn("complete story fragment", src)
                self.assertIn("no length limit", src)
                self.assertNotIn("15 to 50", src)


if __name__ == "__main__":
    unittest.main()
