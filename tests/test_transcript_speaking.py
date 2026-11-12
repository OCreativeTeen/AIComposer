import ast
import pathlib
import re
import unittest
from unittest import mock

from utility import media_transcript as _mt
from utility.media_transcript import (
    _punctuate_with_times,
    apply_verbatim_speaking,
    parse_timed_transcript,
)


TRANSCRIPT = """
[00:00:00.0] <1> 今天天气很好。
[00:00:02.5] 我们出去走走。
[00:00:20.0] <2> 好啊。
[00:00:22.0] <1> 那就现在走。
"""


def _real_languages() -> dict:
    """config.py 里的 LANGUAGES（只读源码里的字面量，不执行 config.py）。"""
    src = (pathlib.Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "LANGUAGES" for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


class VerbatimSpeakingTest(unittest.TestCase):
    def setUp(self):
        # 全套跑时 test_comfy_edit_prompts 先导入，用 test_video_speaker_semantics._install_stubs 把
        # sys.modules["config"] 换成没有 LANGUAGES 的假模块；media_transcript 随后导入就绑到了它。
        # 只在缺的时候补上真的 LANGUAGES，测完还原，不影响别的测试。
        if not hasattr(_mt.config, "LANGUAGES"):
            patcher = mock.patch.object(_mt.config, "LANGUAGES", _real_languages(), create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_parse_carries_speaker(self):
        rows = parse_timed_transcript(TRANSCRIPT)
        self.assertEqual(
            [(0.0, 1, "今天天气很好。"), (2.5, 1, "我们出去走走。"), (20.0, 2, "好啊。"), (22.0, 1, "那就现在走。")],
            [(r["start"], r["speaker"], r["text"]) for r in rows],
        )

    def test_copies_original_sentences(self):
        scenes = [
            {"start": 0, "end": 20, "speaking": "<1> 今天真不错，出去吧。"},
            {"start": 20.0, "end": 40, "speaking": "<2> 行，马上走。"},
        ]
        copied, missed = apply_verbatim_speaking(scenes, TRANSCRIPT)
        self.assertEqual(copied, 2)
        self.assertEqual(missed, 0)
        self.assertEqual(scenes[0]["speaking"], "<1> 今天天气很好。 我们出去走走。")
        self.assertEqual(scenes[1]["speaking"], "<2> 好啊。 <1> 那就现在走。")
        self.assertNotIn("speaking_timing", scenes[0])

    def test_scene_opening_keeps_carried_speaker(self):
        scenes = [
            {"start": 0, "end": 2.5, "speaking": "rewritten"},
            {"start": 2.5, "end": 20, "speaking": "rewritten"},
            {"start": 20, "end": 40, "speaking": "rewritten"},
        ]
        apply_verbatim_speaking(scenes, TRANSCRIPT)
        self.assertEqual(scenes[0]["speaking"], "<1> 今天天气很好。")
        self.assertEqual(scenes[1]["speaking"], "<1> 我们出去走走。")
        self.assertEqual(scenes[2]["speaking"], "<2> 好啊。 <1> 那就现在走。")

    def test_unpunctuated_lines_keep_a_sentence_break(self):
        raw = (
            "[00:00:00.0] <1> 你有沒有發現到了今天就是空氣里總是瀰漫著一種恐慌感對吧\n"
            "[00:00:10.8] <2> 大家聊著聊著話題總會拐到AI說實話\n"
            "[00:00:20.0] <1> 怎麼個對比法？\n"
        )
        scenes = [{"start": 0, "end": 30, "speaking": "模型改写过的一整段"}]
        apply_verbatim_speaking(scenes, raw)
        self.assertEqual(
            scenes[0]["speaking"],
            "<1> 你有沒有發現到了今天就是空氣里總是瀰漫著一種恐慌感對吧。"
            " <2> 大家聊著聊著話題總會拐到AI說實話。"
            " <1> 怎麼個對比法？",
        )

    def test_punctuation_is_sent_to_strata_in_short_slices(self):
        calls = []

        def ask(_system, user, _what):
            calls.append(user)
            lines = []
            for line in user.splitlines():
                stamp = re.match(r"\[(\d+(?:\.\d+)?)-", line).group(1)
                text = line.split("] ", 1)[1]
                lines.append(f"[{stamp}] {text}。")
            return "\n".join(lines)

        items = [
            {
                "start": i * 20.0,
                "end": i * 20.0 + 18.0,
                "text": "这是没有标点的一段识别文字我们继续往下说",
            }
            for i in range(8)
        ]
        out = _punctuate_with_times(items, "zh", ask, {})
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(len(out), 8)
        self.assertTrue(all(sentence.endswith("。") for _stamp, sentence in out))

    def test_preamble_and_clock_time_are_accepted(self):
        def ask(_system, _user, _what):
            return "补好了：\n[00:00:01.5] 你好吗？\n[00:00:04.0] 我很好。"

        items = [
            {"start": 1.5, "end": 4.0, "text": "你好吗"},
            {"start": 4.0, "end": 6.0, "text": "我很好"},
        ]
        out = _punctuate_with_times(items, "zh", ask, {})
        self.assertEqual([(1.5, "你好吗？"), (4.0, "我很好。")], out)

    def test_reply_without_punctuation_is_not_kept(self):
        def ask(_system, user, _what):
            lines = []
            for line in user.splitlines():
                stamp = re.match(r"\[(\d+(?:\.\d+)?)-", line).group(1)
                text = line.split("] ", 1)[1]
                lines.append(f"[{stamp}] {text}")
            return "\n".join(lines)

        sentence = "你有没有发现到了今天空气里总是弥漫着一种挥之不去的恐慌感绝对的到处都是这种感觉对吧"
        items = [
            {"start": 0.0, "end": 8.0, "text": sentence},
            {"start": 8.0, "end": 16.0, "text": sentence},
        ]
        stats = {}
        out = _punctuate_with_times(items, "zh", ask, stats)
        self.assertEqual([sentence, sentence], [text for _stamp, text in out])
        self.assertGreaterEqual(stats["punct_fallback"], 1)

    def test_leaves_speaking_when_times_missing(self):
        scenes = [{"speaking": "<1> 模型写的。", "caption": "x"}]
        copied, missed = apply_verbatim_speaking(scenes, TRANSCRIPT)
        self.assertEqual((copied, missed), (0, 0))
        self.assertEqual(scenes[0]["speaking"], "<1> 模型写的。")


if __name__ == "__main__":
    unittest.main()
