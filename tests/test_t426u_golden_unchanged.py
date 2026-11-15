"""t426u: 不走档位的组合（有讲话、作为说话、Grok/Gemini 只按图、讲话当故事内容的 Grok 版……）输出和 t426u 前一字不差。
金样本 tests/golden_t426u/*.txt 是改代码前在 t422u–t424u 版本上生成的。"""
import os
import unittest

from tests.golden_t426u_cases import cases

_DIR = os.path.join(os.path.dirname(__file__), "golden_t426u")


class GoldenUnchangedTest(unittest.TestCase):
    def test_old_paths_unchanged(self):
        for name, fn in cases().items():
            with self.subTest(name=name):
                with open(os.path.join(_DIR, name + ".txt"), encoding="utf-8", newline="") as f:
                    want = f.read().replace("\r\n", "\n")
                self.assertEqual(fn().replace("\r\n", "\n"), want)

    def test_old_paths_not_profile_prompts(self):
        import config_prompt as cp

        for name, fn in cases().items():
            with self.subTest(name=name):
                out = fn()
                self.assertFalse(cp.is_profile_prompt(out))
                if name.startswith(("h3_", "fyi_only")):
                    self.assertTrue(out.startswith(cp.VIDEO_NO_SUBTITLE_CRITICAL_LINE))


if __name__ == "__main__":
    unittest.main()
