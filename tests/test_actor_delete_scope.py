"""t327u offline test: actor-row delete dialog — 是 = only this scene, 否 = same name in every
scene of this episode, 取消 = nothing. The method is pulled out of gui/workflow/wf_actors.py with
ast and run against stubs (no tkinter / pygame / config import, no .env)."""
from __future__ import annotations

import ast
import textwrap
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "gui/workflow/wf_actors.py").read_text(encoding="utf-8")


def _method_source(name: str) -> str:
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return textwrap.dedent(ast.get_source_segment(SRC, node))
    raise AssertionError(name)


class _PM:
    @staticmethod
    def split_actor_motion(body):
        return body, ""

    @staticmethod
    def actor_is_absent(name):
        return False

    @staticmethod
    def actor_index_by_name(text, name):
        lines = [ln for ln in (text or "").splitlines() if ln.strip()]
        return next((i for i, ln in enumerate(lines, 1) if ln.strip() == name), 0)

    @staticmethod
    def apply_actor_delete(scene, text, index):
        lines = [ln for ln in (text or "").splitlines() if ln.strip()]
        if len(lines) <= 1:
            return False
        del lines[index - 1]
        scene["actor"] = "\n".join(lines)
        return True


class _Messagebox:
    def __init__(self):
        self.calls = []

    def askyesnocancel(self, title, message, parent=None):
        self.calls.append(message)
        return None

    def showinfo(self, *a, **k):
        pass


class _Workflow:
    def __init__(self, scenes):
        self.scenes = scenes
        self.saved = 0

    def get_scene_by_index(self, i):
        return self.scenes[i]

    def scenes_in_story(self, cur):
        return list(self.scenes)

    def save_scenes_to_json(self):
        self.saved += 1


def _make(mb):
    ns = {"project_manager": _PM, "messagebox": mb, "show_auto_close_popup": lambda *a, **k: None}
    exec(_method_source("_delete_actor_from_chip"), ns)  # noqa: S102
    fn = ns["_delete_actor_from_chip"]
    a = "woman/mature/chinese/母親"
    b = "man/youth/chinese/阿明"
    scenes = [{"actor": f"{a}\n{b}"}, {"actor": f"{a}\n{b}"}, {"actor": f"{b}\n{a}"}]
    self_ = types.SimpleNamespace(
        root=None, workflow=_Workflow(scenes), current_scene_index=0, _actor_text=scenes[0]["actor"],
        log=[],
    )
    self_._scene_actor_rows = lambda: [ln for ln in self_._actor_text.splitlines() if ln.strip()]

    def _drop(entry):
        rows = self_._scene_actor_rows()
        kept = [r for r in rows if r != entry["body"]]
        return kept, len(kept) != len(rows)

    def _apply(entry):
        self_.log.append("scene")
        scenes[0]["actor"] = "\n".join(_drop(entry)[0])
        return True

    self_._drop_scene_actor = _drop
    self_._apply_current_scene_actor_delete = _apply
    self_._after_actor_delete = lambda: None
    self_._sync_speaking_widget_to_scene = lambda cur: None
    self_._show_scene_speaking = lambda cur: None
    self_._render_actor_buttons = lambda: None
    return fn, self_, scenes, a, b


class ActorDeleteScopeTest(unittest.TestCase):
    def test_yes_deletes_only_this_scene(self):
        fn, s, scenes, a, b = _make(_Messagebox())
        self.assertEqual(fn(s, {"body": a}, ask=lambda name: True), "scene")
        self.assertEqual(scenes[0]["actor"], b)
        self.assertIn(a, scenes[1]["actor"])
        self.assertIn(a, scenes[2]["actor"])

    def test_no_deletes_same_name_in_every_scene_of_episode(self):
        fn, s, scenes, a, b = _make(_Messagebox())
        self.assertEqual(fn(s, {"body": a}, ask=lambda name: False), "episode")
        for sc in scenes:
            self.assertEqual(sc["actor"], b)
        self.assertEqual(s.workflow.saved, 1)

    def test_cancel_deletes_nothing(self):
        mb = _Messagebox()
        fn, s, scenes, a, b = _make(mb)
        self.assertEqual(fn(s, {"body": a}), "cancel")
        self.assertEqual([sc["actor"] for sc in scenes], [f"{a}\n{b}", f"{a}\n{b}", f"{b}\n{a}"])
        self.assertEqual(mb.calls, [f"删除「{a}」：\n是 = 只删这一场\n否 = 本集所有场景里同名的都删\n取消 = 不删"])


if __name__ == "__main__":
    unittest.main()
