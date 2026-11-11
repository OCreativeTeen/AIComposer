"""t395u offline tests: 尾帧增强 defaults to Qwen; MiniMax workflows are only FastH3 8-step (default) and Pika 6-step,
old saved i2v / r2v map to 8-step; both use the t392u portraits-only-for-missing-speakers logic."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class LastFrameEnhanceDefaultTest(unittest.TestCase):
    def test_default_is_qwen_saved_choice_kept(self):
        from utility import video_segments as vs

        self.assertEqual(vs.LAST_FRAME_ENHANCE_DEFAULT, "qn")
        for raw, want in ((None, "qn"), ("", "qn"), ("bogus", "qn"), ("moss", "moss"), ("none", "none"), ("grok", "grok")):
            self.assertEqual(vs.normalize_last_frame_enhance(raw), want)

    def test_no_moss_default_text_left(self):
        for rel in ("gui/video_prompt_dialog.py", "utility/video_segments.py", "utility/last_frame_chain.py"):
            self.assertNotIn("默认 MOSS", _src(rel))
        self.assertIn('enhance="qn"', _src("gui/workflow/wf_prompt_flows.py"))


class MiniMaxWorkflowOptionsTest(unittest.TestCase):
    def setUp(self):
        # sd_image_processor needs the real config; like test_minimax_dynamic_length, run only the needed chunk
        import os
        import types

        src = _src("utility/sd_image_processor.py")
        a = src.index("MINIMAX_H3_FAST8_WORKFLOW = ")
        b = src.index("MINIMAX_MODEL_SOURCE_HINT")
        c = src.index("# t395u: 生场视频窗口里的 MiniMax 工作流")
        d = src.index("\n\n\n", src.index("def minimax_workflow_for"))
        ns = {"os": os, "__file__": str(ROOT / "utility" / "sd_image_processor.py")}
        exec(src[a:b] + "\n" + src[c:d], ns)
        self.sdp = types.SimpleNamespace(**{k: v for k, v in ns.items() if not k.startswith("__")})
        self.src = src

    def test_only_two_options_fast8_first(self):
        self.assertEqual([k for k, _ in self.sdp.MINIMAX_H3_WORKFLOW_OPTIONS], ["r2v_fast8", "r2v_pika6"])
        self.assertEqual(self.sdp.MINIMAX_H3_WORKFLOW_DEFAULT, "r2v_fast8")

    def test_old_values_map_to_fast8(self):
        n = self.sdp.normalize_h3_workflow
        for raw in (None, "", "i2v", "r2v", "original", "bogus", "r2v_fast8"):
            self.assertEqual(n(raw), "r2v_fast8")
        self.assertEqual(n("r2v_pika6"), "r2v_pika6")
        for raw in (None, "i2v", "r2v"):
            self.assertEqual(self.sdp.minimax_workflow_for(raw), self.sdp.MINIMAX_H3_FAST8_WORKFLOW)
        self.assertEqual(self.sdp.minimax_workflow_for("r2v_pika6"), self.sdp.MINIMAX_H3_PIKA6_WORKFLOW)
        self.assertNotIn("MINIMAX_H3_R2V_WORKFLOW", self.src)

    def test_both_workflow_files_are_reference_workflows(self):
        import json

        for path in (self.sdp.MINIMAX_H3_FAST8_WORKFLOW, self.sdp.MINIMAX_H3_PIKA6_WORKFLOW):
            wf = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertTrue(any(isinstance(v, dict) and v.get("class_type") == "MiniMaxH3ReferenceToVideo"
                                for v in wf.values()), path)

    def test_dialog_has_no_removed_options(self):
        dlg = _src("gui/video_prompt_dialog.py")
        for gone in ("原工作流（无参考图）", "参考图工作流（人物肖像）", '("i2v", "r2v"'):
            self.assertNotIn(gone, dlg)
        self.assertIn("for value, label in _sdp_wf.MINIMAX_H3_WORKFLOW_OPTIONS:", dlg)
        self.assertIn('_sdp_wf.normalize_h3_workflow(_sv.get("h3_workflow"))', dlg)
        # both kept workflows collect portraits, then the t392u presence check filters them
        self.assertIn('normalize_h3_workflow(h3_wf_var.get()) in ("r2v_fast8", "r2v_pika6")', dlg)
        self.assertIn("_spres.portraits_for_missing(", dlg)
        self.assertNotIn("原工作流（无参考图）", _src("utility/sd_image_processor.py"))


if __name__ == "__main__":
    unittest.main()
