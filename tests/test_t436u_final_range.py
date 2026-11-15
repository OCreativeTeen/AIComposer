"""t436u 阶段 5：最终视频可以选范围：标记范围 / 本集 / 全部。"""
import pathlib
import unittest

from utility.final_range import final_range_bounds, normalize_scope, scope_label

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RangeTest(unittest.TestCase):
    def test_scopes(self):
        self.assertEqual(final_range_bounds("marker", 10, (2, 5), (6, 9)), (2, 5))
        self.assertEqual(final_range_bounds("episode", 10, (2, 5), (6, 9)), (6, 9))
        self.assertEqual(final_range_bounds("all", 10, (2, 5), (6, 9)), (0, 9))

    def test_fallbacks(self):
        self.assertEqual(final_range_bounds("episode", 10, (2, 5), (-1, -1)), (0, 9))
        self.assertEqual(final_range_bounds("bogus", 10, (2, 5), (6, 9)), (2, 5))
        self.assertEqual(final_range_bounds("all", 0, (0, 0), (-1, -1)), (0, 0))
        self.assertEqual(normalize_scope(None), "marker")
        self.assertEqual(scope_label("episode"), "本集")

    def test_wiring(self):
        src = (ROOT / "gui" / "workflow" / "wf_finalize_publish.py").read_text(encoding="utf-8")
        self.assertIn('result["value"] = (mode, speed, normalize_scope(scope_var.get()))', src)
        self.assertIn('PROJECT_CONFIG["final_video_scope"]', src)
        run = src[src.index("    def run_finalize_video"):src.index("    def _run_finalize_after_logo")]
        self.assertLess(run.index("_ask_final_video_options()"), run.index("askyesnocancel("))
        self.assertIn("self._final_range_bounds(picked[2])", run)
        self.assertNotIn("_marker_scene_bounds()", run)
        after = src[src.index("    def _run_finalize_after_logo"):src.index("    def _open_finalize_menu")]
        self.assertIn("scene_start=start", after)
        self.assertIn("self._final_range_bounds(scope)", after)


if __name__ == "__main__":
    unittest.main()
