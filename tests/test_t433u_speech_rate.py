"""t433u: 生成视频的讲话语速估算调快：中文 4.6 字/秒，英文 2.5 词/秒（原 4.4 / 2.3）。"""
import unittest

from tests.test_video_speaker_semantics import _install_stubs

_install_stubs()

import config_prompt as cp  # noqa: E402


class SpeechRateTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(cp.MINIMAX_CJK_PER_SEC, 4.6)
        self.assertEqual(cp.MINIMAX_WORDS_PER_SEC, 2.5)

    def test_seconds(self):
        self.assertEqual(cp.minimax_speech_seconds("天" * 46), 10.0)
        self.assertEqual(cp.minimax_speech_seconds("天" * 50), 10.9)
        self.assertEqual(cp.minimax_speech_seconds(" ".join(["word"] * 25)), 10.0)
        self.assertEqual(cp.minimax_speech_seconds(" ".join(["word"] * 30)), 12.0)
        self.assertEqual(cp.minimax_speech_seconds("<1> " + "天" * 46 + "……"), 10.4)

    def test_minimax_frames(self):
        L, s, secs, _ = cp.auto_length_for_backend("天" * 50, True)
        self.assertEqual((L, s, secs), ("11.54166667s", 1.0, 10.9))  # 277 帧
        L, s, secs, _ = cp.auto_length_for_backend(" ".join(["word"] * 30), True)
        self.assertEqual((L, s, secs), ("12.25s", 1.0, 12.0))  # 294 帧，不再需要说快

    def test_grok_gemini_choice(self):
        L, s, _, _ = cp.auto_length_for_backend("天" * 50, False)
        self.assertEqual((L, s), ("10s", 0.917))
        L, s, _, _ = cp.auto_length_for_backend(" ".join(["word"] * 30), False)
        self.assertEqual((L, s), ("15s", 1.0))


if __name__ == "__main__":
    unittest.main()
