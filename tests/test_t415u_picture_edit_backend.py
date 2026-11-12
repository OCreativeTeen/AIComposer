"""t415u: 图片修改窗口里直接选生图后端（默认 QN = Qwen 图片编辑，ComfyUI），提交 / 全集提交都用它。"""
from __future__ import annotations

import ast
import os
import sys
import textwrap
import types
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLG = Path(ROOT, "gui/picture_prompt_dialog.py").read_text(encoding="utf-8").replace("\r\n", "\n")


def _module_ns():
    """只取模块级的后端常量和 picture_edit_backend / _clean_choice，不导入 tkinter / config。"""
    tree = ast.parse(DLG)
    want = {"_DEFAULT_CHOICE", "PICTURE_EDIT_BACKENDS", "DEFAULT_PICTURE_EDIT_BACKEND", "COMFY_PICTURE_BACKENDS",
            "picture_edit_backend", "_clean_choice"}
    parts = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in want for t in node.targets):
            parts.append(ast.get_source_segment(DLG, node))
        elif isinstance(node, ast.FunctionDef) and node.name in want:
            parts.append(ast.get_source_segment(DLG, node))
    cp = types.SimpleNamespace(
        SLIDE_FLOW_ACTOR_OVERRIDES=(("不换", ""),), PICTURE_FLOW_TASK_CHOICES=(("keep", ""),),
        PICTURE_FLOW_TEXT_CHOICES=(("keep", ""),), SLIDE_FLOW_NARRATIVE_CHOICES=(("narration", ""),),
    )
    slots = types.ModuleType("utility.scene_image_slots")
    slots.IMAGE_CHOICE_KEYS = ("clip_image",)
    prev = sys.modules.get("utility.scene_image_slots")
    sys.modules["utility.scene_image_slots"] = slots
    ns = {"config_prompt": cp, "clean_fyi_history": lambda saved: []}
    exec("\n\n".join(parts), ns)
    ns["_restore"] = lambda: (sys.modules.__setitem__("utility.scene_image_slots", prev) if prev is not None
                              else sys.modules.pop("utility.scene_image_slots", None))
    return ns


class BackendChoiceTest(unittest.TestCase):
    def setUp(self):
        self.ns = _module_ns()
        self.addCleanup(self.ns["_restore"])

    def test_options_and_default_qn(self):
        keys = [k for k, _t in self.ns["PICTURE_EDIT_BACKENDS"]]
        self.assertEqual(keys, ["qn", "moss", "grok", "gemini"])
        self.assertEqual(self.ns["DEFAULT_PICTURE_EDIT_BACKEND"], "qn")
        self.assertEqual(self.ns["_DEFAULT_CHOICE"]["backend"], "qn")
        self.assertEqual(set(self.ns["COMFY_PICTURE_BACKENDS"]), {"qn", "moss"})

    def test_normalise(self):
        f = self.ns["picture_edit_backend"]
        self.assertEqual(f(None), "qn")
        self.assertEqual(f("bogus"), "qn")
        self.assertEqual(f(" MOSS "), "moss")
        self.assertEqual(f("grok"), "grok")
        self.assertEqual(f("gemini"), "gemini")

    def test_clean_choice_persists_backend(self):
        cc = self.ns["_clean_choice"]
        self.assertEqual(cc(None)["backend"], "qn")
        self.assertEqual(cc({})["backend"], "qn")
        self.assertEqual(cc({"backend": "grok"})["backend"], "grok")
        self.assertEqual(cc({"backend": "minimax"})["backend"], "qn")


class DialogWiringTest(unittest.TestCase):
    def test_backend_var_saved_and_row_hidden_for_portrait(self):
        self.assertIn('backend_var = tk.StringVar(value=picture_edit_backend(last.get("backend")))', DLG)
        cur = DLG.split("def current_choice()", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('"backend": picture_edit_backend(backend_var.get())', cur)
        row = DLG.split('text="生图后端"', 1)[0][-300:]
        self.assertIn('if mode != "portrait":', row)
        self.assertIn("for _v, _t in PICTURE_EDIT_BACKENDS:", DLG)

    def _on_submit(self, backend, mode="modify", picked=("grok", "Profile 1")):
        body = DLG.split("    def on_submit(scope: str = \"scene\") -> None:", 1)[1].split("\n    def ", 1)[0]
        ns = _module_ns()
        self.addCleanup(ns["_restore"])
        calls = []
        ns.update({
            "_submit_scope": {"v": "scene"}, "mode": mode, "dlg": None,
            "backend_var": types.SimpleNamespace(get=lambda: backend),
            "on_go": lambda b, a: calls.append(("go", b, a)),
            "_run_portrait_extract": lambda a: calls.append(("portrait", a)),
            "ask_llm_and_account": lambda *a, **k: calls.append(("ask", k.get("fixed_backend"))) or picked,
        })
        exec("def on_submit(scope='scene'):" + body, ns)
        return ns, calls

    def test_comfy_backends_go_direct_both_scopes(self):
        for b in ("qn", "moss"):
            for scope in ("scene", "episode"):
                ns, calls = self._on_submit(b)
                ns["on_submit"](scope)
                self.assertEqual(calls, [("go", b, "")])
                self.assertEqual(ns["_submit_scope"]["v"], scope)

    def test_web_backends_ask_account_only(self):
        for b in ("grok", "gemini"):
            ns, calls = self._on_submit(b, picked=(b, "Profile 2"))
            ns["on_submit"]("episode")
            self.assertEqual(calls, [("ask", b), ("go", b, "Profile 2")])
        ns, calls = self._on_submit("grok", picked=None)
        ns["on_submit"]("scene")
        self.assertEqual(calls, [("ask", "grok")])

    def test_portrait_stays_grok(self):
        ns, calls = self._on_submit("qn", mode="portrait", picked=("grok", "P"))
        ns["on_submit"]("episode")
        self.assertEqual(calls, [("ask", "grok"), ("portrait", "P")])
        self.assertEqual(ns["_submit_scope"]["v"], "scene")


class ComfyPathTest(unittest.TestCase):
    def test_comfy_paths_exist_for_every_edit_type(self):
        go = DLG.split("    def on_go(", 1)[1].split("\n    def on_submit", 1)[0]
        self.assertIn("comfy = config_prompt.comfy_backend(backend)", go)
        for call in ("build_comfy_cover_step_prompt", "build_comfy_cast_fix_prompt",
                     "build_comfy_picture_edit_prompt", "build_comfy_upscale_prompt"):
            self.assertIn(call + "(", go)
        flows = Path(ROOT, "gui/workflow/wf_prompt_flows.py").read_text(encoding="utf-8")
        self.assertIn("generate_image_qwen_edit(", flows)
        self.assertIn("generate_image_moss_edit(", flows)
        self.assertIn('extra["image_backend"] = "qn"', flows)


if __name__ == "__main__":
    unittest.main()
