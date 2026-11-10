"""t316u / t319u / t329u: Grok portrait extraction reviewed by a human in the actor window (offline).

No Strata: every portrait is shown in the actor review window; ``review`` here is a stub that
answers what the human clicked (ok / deleted / stop)."""
from __future__ import annotations

import ast
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utility.actor_portrait_extract import (  # noqa: E402
    DEFAULT_IMAGE_SLOT,
    REVIEW_DELETED,
    REVIEW_OK,
    REVIEW_STOP,
    STATUS_CONFIRMED,
    STATUS_DELETED,
    STATUS_EXISTING,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_SKIPPED,
    STATUS_STOPPED,
    actor_identity,
    actors_from_scene,
    all_actors_confirmed,
    build_portrait_extract_prompt,
    clip_image_is_cover_copy,
    confirm_key,
    format_actor_result_line,
    review_portraits_for_scene,
    scan_scenes_for_portraits,
    scene_clip_image_source,
    status_label,
)


def _rgb_image(path: str, color=(220, 30, 30), size=(80, 80)):
    from PIL import Image

    Image.new("RGB", size, color).save(path)
    return path


def _actor(body, label="人物1", note=""):
    bits = [p for p in body.split("/") if p]
    return {
        "role": "person", "body": body, "label": label, "note": note,
        "gender": bits[0] if bits else "", "age": bits[1] if len(bits) > 1 else "",
        "nationality": bits[2] if len(bits) > 2 else "", "name": bits[-1] if bits else body,
        "key": f"person:{body}",
    }


def _talk(scene):
    """t357u: give every listed actor a spoken line (<1> … <N>) unless the test sets speaking itself."""
    if isinstance(scene, dict) and "speaking" not in scene:
        n = len(scene.get("actor_refs") or [])
        scene["speaking"] = " ".join(f"<{i}> 台词{i}。" for i in range(1, n + 1))
    return scene


class ActorPortraitReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="portrait_x_")
        self.avatar = os.path.join(self.tmp, "avatar")
        os.makedirs(self.avatar, exist_ok=True)
        self.scene_img = _rgb_image(os.path.join(self.tmp, "scene.png"), (40, 40, 40), (200, 120))
        self.woman = _actor("woman/mature/chinese/林氏", "人物1", note="青衫，低头，发髻")
        self.man = _actor("man/youth/chinese/贾雨村", "人物2", note="蓝衣，神情严肃")
        self.gen_calls = []
        self.reviews = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- stubs ---------------------------------------------------------------------------------
    @staticmethod
    def _dest(role, name, avatar_dir="", style=None):
        return os.path.join(avatar_dir, actor_identity(name).replace("/", "_") + ".png")

    def _path(self, role, name, avatar_dir="", style=None):
        p = self._dest(role, name, avatar_dir)
        return p if os.path.isfile(p) else ""

    def _gen(self, fail_for=()):
        def generate(image, actor, prompt):
            self.gen_calls.append((os.path.basename(image), actor["body"]))
            if (os.path.basename(image), actor["body"]) in fail_for or actor["body"] in fail_for:
                return ""
            path = os.path.join(self.tmp, f"actor_portrait_{len(self.gen_calls)}.png")
            _rgb_image(path, (10 * len(self.gen_calls), 90, 90))
            return path
        return generate

    def _review(self, answers):
        """answers: {(body, kind): [answer, ...]} — default ok."""
        def review(actor, path, kind):
            self.assertTrue(os.path.isfile(path), "review shows an associated file")
            self.assertEqual(os.path.abspath(path), os.path.abspath(self._dest("person", actor["body"], self.avatar)))
            self.reviews.append((actor["body"], kind))
            queue = answers.get((actor["body"], kind)) or []
            return queue.pop(0) if queue else REVIEW_OK
        return review

    def _run(self, scene, answers=None, confirmed=None, **kw):
        return review_portraits_for_scene(
            _talk(scene), self.avatar, generate=self._gen(kw.pop("fail_for", ())), review=self._review(answers or {}),
            confirmed=confirmed if confirmed is not None else set(),
            portrait_path=self._path, portrait_dest=self._dest, **kw,
        )

    def _seed_existing(self, actor, data=b"OLD-PORTRAIT"):
        path = self._dest("person", actor["body"], self.avatar)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def _scenes(self, n, actors):
        out = []
        for i in range(1, n + 1):
            img = _rgb_image(os.path.join(self.tmp, f"s{i}.png"), (20 * i, 20, 20), (160, 100))
            out.append(_talk({"clip_image": img, "actor_refs": [dict(a) for a in actors]}))
        return out

    # --- the six decisions -------------------------------------------------------------------
    def test_existing_ok_no_grok_and_confirmed(self):
        path = self._seed_existing(self.woman)
        confirmed = set()
        out = self._run({"clip_image": self.scene_img, "actor_refs": [self.woman]}, confirmed=confirmed)
        self.assertEqual(self.gen_calls, [])
        self.assertEqual(self.reviews, [(self.woman["body"], "existing")])
        self.assertEqual(out["results"][0]["status"], STATUS_CONFIRMED)
        self.assertIn(confirm_key(self.woman), confirmed)
        self.assertEqual(Path(path).read_bytes(), b"OLD-PORTRAIT")

    def test_existing_delete_regenerates_from_this_scene(self):
        old = self._seed_existing(self.woman)
        confirmed = set()
        out = self._run({"clip_image": self.scene_img, "actor_refs": [self.woman]},
                        answers={(self.woman["body"], "existing"): [REVIEW_DELETED]}, confirmed=confirmed)
        self.assertEqual(self.gen_calls, [("scene.png", self.woman["body"])])
        self.assertEqual(self.reviews, [(self.woman["body"], "existing"), (self.woman["body"], "new")])
        self.assertEqual(out["results"][0]["status"], STATUS_OK)
        self.assertIn(confirm_key(self.woman), confirmed)
        self.assertNotEqual(Path(old).read_bytes(), b"OLD-PORTRAIT")  # new portrait at the same paste path
        bak = os.path.join(self.avatar, "woman_mature_chinese_林氏.bak1.png")
        self.assertEqual(Path(bak).read_bytes(), b"OLD-PORTRAIT")  # deleted = renamed, recoverable

    def test_existing_delete_then_regenerated_delete_skips_scene(self):
        self._seed_existing(self.woman)
        confirmed = set()
        out = self._run({"clip_image": self.scene_img, "actor_refs": [self.woman]}, confirmed=confirmed,
                        answers={(self.woman["body"], "existing"): [REVIEW_DELETED],
                                 (self.woman["body"], "new"): [REVIEW_DELETED]})
        self.assertEqual(len(self.gen_calls), 1)  # one Grok call per attempt
        self.assertEqual(out["results"][0]["status"], STATUS_DELETED)
        self.assertEqual(self._path("person", self.woman["body"], self.avatar), "")
        self.assertNotIn(confirm_key(self.woman), confirmed)

    def test_missing_ok_associates_and_confirms(self):
        confirmed = set()
        out = self._run({"clip_image": self.scene_img, "actor_refs": [self.woman]}, confirmed=confirmed)
        self.assertEqual(self.gen_calls, [("scene.png", self.woman["body"])])
        self.assertEqual(self.reviews, [(self.woman["body"], "new")])
        row = out["results"][0]
        self.assertEqual(row["status"], STATUS_OK)
        self.assertEqual(os.path.abspath(row["dest"]), os.path.abspath(self._dest("person", self.woman["body"], self.avatar)))
        self.assertIn("成功", format_actor_result_line(row))
        self.assertIn(confirm_key(self.woman), confirmed)
        self.assertFalse([f for f in os.listdir(self.tmp) if f.startswith("actor_portrait_")], "temp file cleaned")

    def test_missing_delete_skips_scene_and_next_scene_tries_again(self):
        scenes = self._scenes(3, [self.woman])
        answers = {(self.woman["body"], "new"): [REVIEW_DELETED, REVIEW_OK]}
        report = scan_scenes_for_portraits(
            scenes, self.avatar, generate=self._gen(), review=self._review(answers),
            portrait_path=self._path, portrait_dest=self._dest,
        )
        self.assertEqual([c[0] for c in self.gen_calls], ["s1.png", "s2.png"])
        self.assertEqual([r["status"] for r in report["results"]], [STATUS_DELETED, STATUS_OK])
        self.assertEqual(status_label(STATUS_DELETED), "已删除，这一场跳过")
        self.assertIn(confirm_key(self.woman), report["confirmed"])
        self.assertTrue(os.path.isfile(self._dest("person", self.woman["body"], self.avatar)))

    def test_confirmed_skipped_later_and_scan_stops_when_all_confirmed(self):
        scenes = self._scenes(4, [self.woman, self.man])
        scenes[0]["actor_refs"] = [dict(self.woman)]  # scene 1: only the woman
        answers = {(self.man["body"], "new"): [REVIEW_DELETED, REVIEW_OK]}
        report = scan_scenes_for_portraits(
            scenes, self.avatar, generate=self._gen(), review=self._review(answers),
            portrait_path=self._path, portrait_dest=self._dest,
        )
        # s1 woman ok; s2 woman skipped (confirmed), man deleted; s3 man ok; s4 never touched
        self.assertEqual(self.gen_calls, [("s1.png", self.woman["body"]), ("s2.png", self.man["body"]),
                                          ("s3.png", self.man["body"])])
        self.assertEqual(self.reviews.count((self.woman["body"], "new")), 1)
        self.assertNotIn("s4.png", [c[0] for c in self.gen_calls])
        statuses = [(r["body"], r["status"]) for r in report["results"]]
        self.assertIn((self.woman["body"], STATUS_SKIPPED), statuses)
        self.assertTrue(all_actors_confirmed(scenes, report["confirmed"]))
        # 已确认的人（例如从项目配置读回来的）：已有肖像也不再给人看、不调 Grok
        self.gen_calls.clear()
        self.reviews.clear()
        out = self._run(scenes[3], confirmed=set(report["confirmed"]))
        self.assertEqual((self.gen_calls, self.reviews), ([], []))
        self.assertEqual(out["reason"], "all_confirmed")

    def test_grok_failure_no_window_skip_rest_of_scene(self):
        scenes = self._scenes(2, [self.woman, self.man])
        report = scan_scenes_for_portraits(
            scenes, self.avatar, generate=self._gen(fail_for={("s1.png", self.woman["body"])}),
            review=self._review({}), portrait_path=self._path, portrait_dest=self._dest,
        )
        # s1: woman fails → no review window, the man in s1 is not tried; s2 tries both
        self.assertEqual(self.gen_calls, [("s1.png", self.woman["body"]), ("s2.png", self.woman["body"]),
                                          ("s2.png", self.man["body"])])
        self.assertEqual(self.reviews, [(self.woman["body"], "new"), (self.man["body"], "new")])
        self.assertEqual(report["results"][0]["status"], STATUS_FAILED)
        self.assertEqual(status_label(STATUS_FAILED), "提取失败")
        self.assertEqual(sorted(os.listdir(self.avatar)), ["man_youth_chinese_贾雨村.png", "woman_mature_chinese_林氏.png"])

    # --- stop / manual mode / safety -------------------------------------------------------
    def test_stop_ends_the_whole_scan(self):
        scenes = self._scenes(3, [self.woman, self.man])
        report = scan_scenes_for_portraits(
            scenes, self.avatar, generate=self._gen(),
            review=self._review({(self.woman["body"], "new"): [REVIEW_STOP]}),
            portrait_path=self._path, portrait_dest=self._dest,
        )
        self.assertTrue(report["stopped"])
        self.assertEqual(self.gen_calls, [("s1.png", self.woman["body"])])
        self.assertEqual(report["results"][-1]["status"], STATUS_STOPPED)
        self.assertNotIn(confirm_key(self.woman), report["confirmed"])
        # stop never deletes: the portrait stays associated (only Delete removes)
        self.assertTrue(os.path.isfile(self._dest("person", self.woman["body"], self.avatar)))

    def test_manual_mode_only_missing_and_failure_continues(self):
        self._seed_existing(self.woman)
        third = _actor("woman/youth/chinese/香菱", "人物3")
        out = self._run({"clip_image": self.scene_img, "actor_refs": [self.woman, self.man, third]},
                        existing="skip", stop_on_failure=False, fail_for={self.man["body"]})
        self.assertEqual([r["status"] for r in out["results"]], [STATUS_EXISTING, STATUS_FAILED, STATUS_OK])
        self.assertEqual([c[1] for c in self.gen_calls], [self.man["body"], third["body"]])
        self.assertEqual(self.reviews, [(third["body"], "new")])  # existing not shown, failure no window
        self.assertEqual(Path(self._dest("person", self.woman["body"], self.avatar)).read_bytes(), b"OLD-PORTRAIT")

    def test_paste_during_grok_is_not_overwritten_and_recheck_before_call(self):
        pasted = self._dest("person", self.man["body"], self.avatar)

        def generate(image, actor, prompt):
            self.gen_calls.append(actor["body"])
            with open(pasted, "wb") as fh:  # user pastes the man while Grok works on the woman
                fh.write(b"USER-PASTE")
            if actor["body"] == self.woman["body"]:
                with open(self._dest("person", actor["body"], self.avatar), "wb") as fh:
                    fh.write(b"USER-PASTE-W")
            return _rgb_image(os.path.join(self.tmp, f"actor_portrait_g{len(self.gen_calls)}.png"))

        out = review_portraits_for_scene(
            _talk({"clip_image": self.scene_img, "actor_refs": [self.woman, self.man]}), self.avatar,
            generate=generate, review=self._review({}), portrait_path=self._path, portrait_dest=self._dest,
            existing="skip",
        )
        self.assertEqual(self.gen_calls, [self.woman["body"]])
        self.assertEqual([r["status"] for r in out["results"]], [STATUS_EXISTING, STATUS_EXISTING])
        self.assertEqual(Path(pasted).read_bytes(), b"USER-PASTE")
        self.assertEqual(Path(self._dest("person", self.woman["body"], self.avatar)).read_bytes(), b"USER-PASTE-W")

    def test_parenthesis_ignored_and_scene_image_untouched(self):
        self.assertEqual(actor_identity("woman/mature/chinese/林氏（低头，青衫）"), "woman/mature/chinese/林氏")
        self.assertEqual(actor_identity("man/youth/chinese/贾雨村(走向门口)"), "man/youth/chinese/贾雨村")
        before, mtime = Path(self.scene_img).read_bytes(), os.path.getmtime(self.scene_img)
        twins = [dict(self.man, body="man/youth/chinese/贾雨村（坐）"), dict(self.man, body="man/youth/chinese/贾雨村（站）")]
        out = self._run({"clip_image": self.scene_img, "actor_refs": twins})
        self.assertEqual(len(self.gen_calls), 1)
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(confirm_key(twins[0]), confirm_key(twins[1]))
        self.assertEqual(Path(self.scene_img).read_bytes(), before)
        self.assertEqual(os.path.getmtime(self.scene_img), mtime)
        preset = actors_from_scene({"actor_refs": [dict(self.woman, body="woman/mature/chinese/林氏（低头）")]})
        self.assertEqual(preset[0]["body"], "woman/mature/chinese/林氏")

    def test_host_is_not_reviewed_or_extracted(self):
        host = dict(_actor("man/elder/chinese/讲员甲", "讲员"), role="host", key="host:man/elder/chinese/讲员甲")
        out = self._run({"clip_image": self.scene_img, "actor_refs": [host]})
        self.assertEqual((self.gen_calls, self.reviews), ([], []))
        self.assertEqual(out["reason"], "no_actors")
        self.assertTrue(all_actors_confirmed([{"actor_refs": [host]}], set()))

    def test_no_cover_fallback_uses_only_scene_clip_image(self):
        cover = _rgb_image(os.path.join(self.tmp, "cover.png"), (1, 2, 3), (200, 120))
        seeded_clip = os.path.join(self.tmp, "clip_seed.png")
        frozen = os.path.join(self.tmp, "zero_last.png")
        shutil.copy2(cover, seeded_clip)
        shutil.copy2(cover, frozen)
        seeded = {"cover_origin": "cover", "clip_image": seeded_clip, "clip_image_last": self.scene_img,
                  "zero_image_last": frozen, "actor_refs": [self.woman]}
        self.assertTrue(clip_image_is_cover_copy(seeded))
        self.assertEqual(scene_clip_image_source(seeded), "")
        out = self._run(seeded, covers=[cover])
        self.assertEqual((self.gen_calls, self.reviews), ([], []))
        self.assertEqual(out["reason"], "no_scene_clip_image")
        self.assertEqual(scene_clip_image_source({"clip_image_last": self.scene_img}), "")
        self.assertEqual(scene_clip_image_source({"clip_image": seeded_clip}, covers=[cover]), "")
        out = self._run(dict(seeded, clip_image=self.scene_img), covers=[cover])
        self.assertEqual(out["source"], os.path.abspath(self.scene_img))
        self.assertEqual([c[0] for c in self.gen_calls], ["scene.png"])

    # --- wiring (source checks; the GUI can't be imported offline) ---------------------------
    def test_prompt_and_no_strata_anywhere(self):
        prompt = build_portrait_extract_prompt(self.woman)
        for bit in ("Gender: woman", "Age: mature", "Nationality/ethnicity: chinese", "林氏", "青衫，低头，发髻",
                    "clearly present", "Do not invent", "simple background in the same art style"):
            self.assertIn(bit, prompt)
        mod = Path(ROOT, "utility/actor_portrait_extract.py").read_text(encoding="utf-8")
        for gone in ("verify_portrait_with_strata", "VERIFY_SYSTEM", "MIN_VERIFY_CONFIDENCE", "parse_verify_json",
                     "verdict_accepts", "visual_remix", "STATUS_REJECTED", "def extract_actor_portraits"):
            self.assertNotIn(gone, mod)
        dlg = Path(ROOT, "gui/picture_prompt_dialog.py").read_text(encoding="utf-8")
        run = dlg[dlg.index("def _run_portrait_extract"):dlg.index("def on_submit")]
        self.assertNotIn("verify", run)
        self.assertIn("scene_clip_image_source(scene, covers)", run)
        self.assertNotIn("chosen_image()", run)
        self.assertIn('existing="replace"', run)  # t343u: 手动 = 每位都重新提取
        self.assertIn("stop_on_failure=False", run)
        self.assertIn("threading.Thread(target=work", run)
        self.assertIn('("portrait", "提取人物肖像"', dlg)
        self.assertIn('fixed_backend="grok"', dlg)
        self.assertEqual(DEFAULT_IMAGE_SLOT, "clip_image")

    def test_auto_flow_wiring(self):
        src = Path(ROOT, "gui/workflow/wf_prompt_flows.py").read_text(encoding="utf-8")
        step = src[src.index("def portrait_step(scene, label)"):src.index("def scene_status(head)")]
        self.assertIn("review_portraits_for_scene(", step)
        self.assertIn("self._portrait_review_from_worker(act, kind)", step)
        self.assertIn('confirmed=portrait_ctx["confirmed"]', step)
        self.assertIn('portrait_ctx["stopped"] = True', step)
        self.assertIn("all_actors_confirmed(", step)
        self.assertNotIn("extract_portraits_for_scene", src)
        self.assertIn("written_evt.wait(", src)
        self.assertIn("review_portrait=self._portrait_review_from_worker", src)
        self.assertIn('"actor_portrait_confirmed"', src)
        worker = src[src.index("def _portrait_review_from_worker"):]
        self.assertIn("self.root.after(0, run)", worker)
        self.assertIn("done.wait()", worker)

    def test_review_window_delete_button_key_and_outcome(self):
        src = Path(ROOT, "gui/workflow/wf_actors.py").read_text(encoding="utf-8")
        dlg = src[src.index("    def _open_portrait_dialog("):src.index("    def _scene_actor_rows(")]
        self.assertIn('text="删除肖像", command=delete_portrait', dlg)
        self.assertIn('dlg.bind("<Delete>", delete_portrait)', dlg)
        self.assertIn('return holder["result"]', dlg)
        self.assertIn('dlg.protocol("WM_DELETE_WINDOW", close_window)', dlg)
        self.assertIn('holder["result"] = "stop" if review', dlg)
        self.assertIn("isinstance(focus, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text))", dlg)
        rev = src[src.index("    def _review_actor_portrait("):src.index("    def _paste_portrait_file(")]
        self.assertIn("actor_entry=None", rev)  # auto review never edits the scene's actor list
        self.assertIn("review=True", rev)

    def test_dialog_remove_renames_every_lookup_level(self):
        """_remove_portrait_files (ast-extracted): backs up each file path_for finds until none is left."""
        src = Path(ROOT, "gui/workflow/wf_actors.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        segs = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in ("_remove_portrait_files", "_backup_portrait"):
                segs[node.name] = ast.get_source_segment(src, node)
        ns = {"os": os}
        exec("class M:\n" + "\n".join("    " + line for line in (
            "@staticmethod\n" + segs["_backup_portrait"] + "\n" + segs["_remove_portrait_files"]).splitlines()), ns)
        story = os.path.join(self.tmp, "story")
        os.makedirs(story)
        a = self._seed_existing(self.woman, b"A")
        b = os.path.join(story, os.path.basename(a))
        Path(b).write_bytes(b"B")

        def path_for(name):
            for p in (a, b):
                if os.path.isfile(p):
                    return p
            return ""

        removed = ns["M"]()._remove_portrait_files(self.woman["body"], path_for)
        self.assertEqual(removed, [a, b])
        self.assertEqual(path_for(self.woman["body"]), "")
        self.assertEqual(Path(os.path.splitext(a)[0] + ".bak1.png").read_bytes(), b"A")
        self.assertEqual(ns["M"]()._remove_portrait_files(self.woman["body"], path_for), [])


if __name__ == "__main__":
    unittest.main()
