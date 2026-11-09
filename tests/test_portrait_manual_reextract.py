"""t343u offline tests: manual 图片修改 → 提取人物肖像 re-extracts every person (even with a portrait).

Review answers: OK → new replaces old (old kept as .bakN); IGNORED → new discarded, old untouched
(none → nothing saved); DELETED → neither kept (both in .bak); STOP → like ignore, then stop.
The automatic flow (existing="review") is unchanged and covered by test_actor_portrait_extract.
No Grok, GUI, providers or .env: generate/review are stubs, GUI wiring is checked from source.
"""
from __future__ import annotations

import ast
import glob
import os
import shutil
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utility.actor_portrait_extract import (  # noqa: E402
    REVIEW_DELETED,
    REVIEW_IGNORED,
    REVIEW_OK,
    REVIEW_STOP,
    STATUS_DELETED,
    STATUS_FAILED,
    STATUS_IGNORED,
    STATUS_OK,
    STATUS_REPLACED,
    STATUS_STOPPED,
    actor_identity,
    format_actor_result_line,
    review_portraits_for_scene,
)


def _img(path, color):
    from PIL import Image

    Image.new("RGB", (60, 60), color).save(path)
    return path


def _actor(body, label):
    return {"role": "person", "body": body, "label": label, "name": body.split("/")[-1]}


class ManualReextractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t343_")
        self.avatar = os.path.join(self.tmp, "avatar")
        os.makedirs(self.avatar)
        self.scene_img = _img(os.path.join(self.tmp, "scene.png"), (40, 40, 40))
        self.a = _actor("woman/mature/chinese/林氏", "人物1")
        self.b = _actor("man/youth/chinese/贾雨村", "人物2")
        self.gen_calls, self.reviews = [], []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _dest(self, role, name, avatar_dir="", style=None):
        return os.path.join(avatar_dir, actor_identity(name).replace("/", "_") + ".png")

    def _path(self, role, name, avatar_dir="", style=None):
        p = self._dest(role, name, avatar_dir)
        return p if os.path.isfile(p) else ""

    def _seed(self, actor, data=b"OLD-PORTRAIT"):
        p = self._dest("person", actor["body"], self.avatar)
        Path(p).write_bytes(data)
        return p

    def _run(self, actors, answers=None, fail_for=()):
        answers = answers or {}

        def generate(image, actor, prompt):
            self.gen_calls.append(actor["body"])
            if actor["body"] in fail_for:
                return ""
            return _img(os.path.join(self.tmp, f"actor_portrait_{len(self.gen_calls)}.png"), (200, 10, 10))

        def review(actor, path, kind):
            self.reviews.append((actor["body"], kind))
            self.assertEqual(os.path.abspath(path), os.path.abspath(self._dest("person", actor["body"], self.avatar)))
            self.assertNotEqual(Path(path).read_bytes(), b"OLD-PORTRAIT", "review must show the NEW extract")
            return answers.get(actor["body"], REVIEW_OK)

        self.confirmed = set()
        return review_portraits_for_scene(
            {"clip_image": self.scene_img, "actor_refs": [dict(x) for x in actors]}, self.avatar,
            generate=generate, review=review, confirmed=self.confirmed, existing="replace",
            stop_on_failure=False, portrait_path=self._path, portrait_dest=self._dest,
        )

    def _baks(self):
        return sorted(glob.glob(os.path.join(self.avatar, "*.bak*")))

    def test_existing_portrait_is_reextracted_and_ok_replaces_with_backup(self):
        old = self._seed(self.a)
        out = self._run([self.a])
        self.assertEqual(self.gen_calls, [self.a["body"]], "Grok is called even though a portrait exists")
        self.assertEqual(self.reviews, [(self.a["body"], "replace")])
        self.assertEqual(out["results"][0]["status"], STATUS_REPLACED)
        self.assertNotEqual(Path(old).read_bytes(), b"OLD-PORTRAIT")
        baks = self._baks()
        self.assertEqual(len(baks), 1)
        self.assertEqual(Path(baks[0]).read_bytes(), b"OLD-PORTRAIT")
        self.assertEqual(self.confirmed, {"person:" + self.a["body"]})
        self.assertIn("已换成新提取的肖像", format_actor_result_line(out["results"][0]))

    def test_ignore_keeps_existing_portrait_unchanged(self):
        old = self._seed(self.a)
        out = self._run([self.a], {self.a["body"]: REVIEW_IGNORED})
        self.assertEqual(out["results"][0]["status"], STATUS_IGNORED)
        self.assertEqual(Path(old).read_bytes(), b"OLD-PORTRAIT")
        self.assertEqual(self._baks(), [], "ignore leaves no extra files and does not rename the old one")
        self.assertEqual(self.confirmed, set())
        self.assertEqual(os.listdir(self.avatar), [os.path.basename(old)])

    def test_ignore_without_existing_saves_nothing(self):
        out = self._run([self.a], {self.a["body"]: REVIEW_IGNORED})
        self.assertEqual(out["results"][0]["status"], STATUS_IGNORED)
        self.assertEqual(os.listdir(self.avatar), [])

    def test_ok_without_existing_saves_new(self):
        out = self._run([self.a])
        self.assertEqual(out["results"][0]["status"], STATUS_OK)
        self.assertTrue(os.path.isfile(self._dest("person", self.a["body"], self.avatar)))
        self.assertEqual(self._baks(), [])

    def test_every_actor_processed_and_grok_failure_leaves_old(self):
        old = self._seed(self.a)
        self._seed(self.b, b"OLD-B")
        out = self._run([self.a, self.b], fail_for=(self.a["body"],))
        self.assertEqual(self.gen_calls, [self.a["body"], self.b["body"]])
        self.assertEqual([r["status"] for r in out["results"]], [STATUS_FAILED, STATUS_REPLACED])
        self.assertEqual(Path(old).read_bytes(), b"OLD-PORTRAIT")
        self.assertEqual(self.reviews, [(self.b["body"], "replace")])

    def test_delete_removes_both_into_backups(self):
        self._seed(self.a)
        out = self._run([self.a], {self.a["body"]: REVIEW_DELETED})
        self.assertEqual(out["results"][0]["status"], STATUS_DELETED)
        self.assertFalse(os.path.isfile(self._dest("person", self.a["body"], self.avatar)))
        self.assertEqual(len(self._baks()), 2)
        self.assertIn(b"OLD-PORTRAIT", [Path(p).read_bytes() for p in self._baks()])

    def test_stop_restores_old_and_stops(self):
        old = self._seed(self.a)
        out = self._run([self.a, self.b], {self.a["body"]: REVIEW_STOP})
        self.assertTrue(out["stopped"])
        self.assertEqual(out["results"][0]["status"], STATUS_STOPPED)
        self.assertEqual(Path(old).read_bytes(), b"OLD-PORTRAIT")
        self.assertEqual(self.gen_calls, [self.a["body"]])
        self.assertEqual(self._baks(), [])

    def test_narrators_excluded(self):
        host = {"role": "host", "body": "woman/mature/chinese/讲员甲", "label": "讲员"}
        self._run([host, self.a])
        self.assertEqual(self.gen_calls, [self.a["body"]])


class ManualReextractWiringTest(unittest.TestCase):
    def _src(self, rel):
        return Path(ROOT, rel).read_text(encoding="utf-8")

    def _seg(self, rel, name):
        src = self._src(rel)
        node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == name)
        return ast.get_source_segment(src, node)

    def test_manual_dialog_uses_replace_and_new_description(self):
        dlg = self._src("gui/picture_prompt_dialog.py")
        run = dlg[dlg.index("def _run_portrait_extract"):dlg.index("def on_submit")]
        self.assertIn('existing="replace"', run)
        self.assertNotIn('existing="skip"', run)
        self.assertIn("已有肖像也重新提取；满意就确定替换，不满意就忽略，保留原来的肖像。", dlg)
        self.assertNotIn("提取还没有肖像的人物头部。已经有肖像的不改", dlg)

    def test_auto_flow_unchanged(self):
        step = self._seg("gui/workflow/wf_prompt_flows.py", "_run_picture_batch")
        self.assertNotIn('existing="replace"', step)
        src = self._src("gui/workflow/wf_prompt_flows.py")
        self.assertNotIn('existing="replace"', src)

    def test_review_window_buttons_and_keys(self):
        body = self._seg("gui/workflow/wf_actors.py", "_open_portrait_dialog")
        self.assertNotIn("finish(False)", body)
        self.assertIn('dlg.bind("<Return>", lambda _e: confirm())', body)
        self.assertIn('dlg.bind("<Escape>", lambda _e: ignore_new() if ignore else cancel())', body)
        self.assertIn('text="忽略", command=ignore_new', body)
        ign = body[body.index("def ignore_new"):body.index("def close_window")]
        self.assertIn('holder["result"] = "ignored"', ign)
        for bad in ("_remove_portrait_files", "_backup_portrait", "os.remove", "os.replace"):
            self.assertNotIn(bad, ign)
        review = self._seg("gui/workflow/wf_actors.py", "_review_actor_portrait")
        self.assertIn('if kind == "replace":', review)
        self.assertIn("ignore=True", review)

    def test_ignored_answer_is_not_remembered_as_confirmed(self):
        src = self._seg("gui/workflow/wf_prompt_flows.py", "_portrait_review_on_ui")
        ns = {}
        exec(textwrap.dedent(src), ns)  # noqa: S102
        remembered = []
        for answer, expect_mark in (("ignored", False), ("ok", True), ("deleted", False), ("stop", False)):
            remembered.clear()
            gui = types.SimpleNamespace(
                _review_actor_portrait=lambda body, kind, parent=None, a=answer: a,
                _remember_portrait_confirmed=lambda key: remembered.append(key),
            )
            got = ns["_portrait_review_on_ui"](gui, {"role": "person", "body": "man/youth/chinese/甲"}, "replace")
            self.assertEqual(got, answer)
            self.assertEqual(bool(remembered), expect_mark, answer)


if __name__ == "__main__":
    unittest.main()
