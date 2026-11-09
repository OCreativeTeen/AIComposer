"""t316u: Grok extract + Strata verify for actor portraits (offline, no live providers)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utility.actor_portrait_extract import (
    DEFAULT_IMAGE_SLOT,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_REJECTED,
    STATUS_SKIPPED,
    actors_from_scene,
    build_portrait_extract_prompt,
    extract_actor_portraits,
    format_actor_result_line,
    parse_verify_json,
    scan_scenes_for_portraits,
    actor_identity,
    clip_image_is_cover_copy,
    extract_portraits_for_scene,
    scene_clip_image_source,
    status_label,
    verdict_accepts,
)


def _rgb_image(path: str, color=(220, 30, 30), size=(80, 80)):
    from PIL import Image

    Image.new("RGB", size, color).save(path)
    return path


def _actor(body, label="人物1", note=""):
    bits = [p for p in body.split("/") if p]
    return {
        "role": "person",
        "body": body,
        "label": label,
        "note": note,
        "gender": bits[0] if bits else "",
        "age": bits[1] if len(bits) > 1 else "",
        "nationality": bits[2] if len(bits) > 2 else "",
        "name": bits[-1] if bits else body,
        "key": f"person:{body}",
    }


class ActorPortraitExtractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="portrait_x_")
        self.avatar = os.path.join(self.tmp, "avatar")
        os.makedirs(self.avatar, exist_ok=True)
        self.scene_img = os.path.join(self.tmp, "scene.png")
        _rgb_image(self.scene_img, (40, 40, 40), (200, 120))
        self.woman = _actor("woman/mature/chinese/林氏", "人物1", note="青衫，低头，发髻")
        self.man = _actor("man/youth/chinese/贾雨村", "人物2", note="蓝衣，神情严肃")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _dest(role, name, avatar_dir="", style=None):
        return os.path.join(avatar_dir, name.replace("/", "_") + ".png")

    def _path_lookup(self, existing):
        def portrait_path(role, name, avatar_dir="", style=None):
            return existing.get(name, "")

        return portrait_path

    def _gen(self, color, calls=None):
        def generate(image, actor, prompt):
            if calls is not None:
                calls.append((os.path.basename(image), actor["body"], prompt))
            path = os.path.join(self.tmp, f"got_{len(calls or [])}_{actor['name']}.png")
            _rgb_image(path, color)
            return path

        return generate

    def test_mode_list_contains_extract_portrait(self):
        src = Path(ROOT, "gui/picture_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn('("modify", "修改图片"', src)
        self.assertIn('("cover", "从封面提取"', src)
        self.assertIn('("cast", "补全/修正人物"', src)
        self.assertIn('("portrait", "提取人物肖像"', src)
        self.assertIn('title="提取人物肖像（Grok）"', src)
        self.assertIn('fixed_backend="grok"', src)
        self.assertEqual(DEFAULT_IMAGE_SLOT, "clip_image")

    def test_prompt_includes_description_attributes(self):
        prompt = build_portrait_extract_prompt(self.woman)
        self.assertIn("Gender: woman", prompt)
        self.assertIn("Age: mature", prompt)
        self.assertIn("Nationality/ethnicity: chinese", prompt)
        self.assertIn("林氏", prompt)
        self.assertIn("青衫，低头，发髻", prompt)
        self.assertIn("clearly present", prompt)
        self.assertIn("Do not invent", prompt)
        self.assertIn("neutral background", prompt)
        src = Path(ROOT, "utility/actor_portrait_extract.py").read_text(encoding="utf-8")
        self.assertNotIn("def crop_portrait", src)
        self.assertNotIn("def locate_actors_in_image", src)
        self.assertIn("generate_portrait_with_grok", src)
        self.assertIn("verify_portrait_with_strata", src)
        self.assertIn("MIN_VERIFY_CONFIDENCE = 0.7", src)

    def test_skip_existing_portrait_does_not_overwrite(self):
        existing_file = os.path.join(self.avatar, "woman_mature_chinese_林氏.png")
        with open(existing_file, "wb") as fh:
            fh.write(b"OLD-PORTRAIT")
        existing = {self.woman["body"]: existing_file}
        calls = []
        rows = extract_actor_portraits(
            self.scene_img, [self.woman], self.avatar,
            generate=self._gen((9, 9, 9), calls),
            verify=lambda *a: {"match": True, "confidence": 0.99, "reason": "ok"},
            portrait_path=self._path_lookup(existing),
            portrait_dest=self._dest,
        )
        self.assertEqual(calls, [])
        self.assertEqual(rows[0]["status"], STATUS_SKIPPED)
        self.assertEqual(status_label(rows[0]["status"]), "已有肖像跳过")
        with open(existing_file, "rb") as fh:
            self.assertEqual(fh.read(), b"OLD-PORTRAIT")

    def test_strata_reject_does_not_associate(self):
        calls = []
        rows = extract_actor_portraits(
            self.scene_img, [self.woman], self.avatar,
            generate=self._gen((200, 20, 20), calls),
            verify=lambda *a: {"match": False, "confidence": 0.95, "reason": "not her"},
            portrait_path=self._path_lookup({}),
            portrait_dest=self._dest,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(rows[0]["status"], STATUS_REJECTED)
        self.assertEqual(status_label(rows[0]["status"]), "未通过审核")
        dest = self._dest("person", self.woman["body"], self.avatar)
        self.assertFalse(os.path.isfile(dest))
        self.assertEqual(os.listdir(self.avatar), [])

    def test_unparseable_verdict_is_failure(self):
        rows = extract_actor_portraits(
            self.scene_img, [self.woman], self.avatar,
            generate=self._gen((10, 200, 10), []),
            verify=lambda *a: "not-json at all",
            portrait_path=self._path_lookup({}),
            portrait_dest=self._dest,
        )
        self.assertEqual(rows[0]["status"], STATUS_FAILED)
        self.assertEqual(status_label(rows[0]["status"]), "提取失败")
        self.assertEqual(os.listdir(self.avatar), [])
        self.assertIsNone(parse_verify_json("hello"))
        self.assertFalse(verdict_accepts({"match": True, "confidence": 0.5}))
        self.assertTrue(verdict_accepts({"match": True, "confidence": 0.7}))

    def test_strata_pass_associates_independent_file(self):
        rows = extract_actor_portraits(
            self.scene_img, [self.woman], self.avatar,
            generate=self._gen((20, 20, 200), []),
            verify=lambda *a: {"match": True, "confidence": 0.88, "reason": "matches"},
            portrait_path=self._path_lookup({}),
            portrait_dest=self._dest,
        )
        self.assertEqual(rows[0]["status"], STATUS_OK)
        self.assertEqual(status_label(rows[0]["status"]), "成功")
        dest = self._dest("person", self.woman["body"], self.avatar)
        self.assertEqual(os.path.abspath(rows[0]["dest"]), os.path.abspath(dest))
        self.assertTrue(os.path.isfile(dest))
        self.assertIn("成功", format_actor_result_line(rows[0]))
        src = Path(ROOT, "utility/content_pdf.py").read_text(encoding="utf-8")
        self.assertIn("def actor_portrait_dest(", src)

    def test_scan_reject_then_continue_next_scene_and_early_stop(self):
        gen_calls = []
        ver_calls = []

        def generate(image, actor, prompt):
            gen_calls.append((os.path.basename(image), actor["body"]))
            path = os.path.join(self.tmp, f"{os.path.basename(image)}_{actor['name']}.png")
            _rgb_image(path, (180, 80, 80) if actor is self.woman or actor["body"] == self.woman["body"] else (80, 80, 180))
            return path

        def verify(portrait, actor, scene_image):
            ver_calls.append((os.path.basename(scene_image), actor["body"]))
            name = os.path.basename(scene_image)
            if name == "s1.png" and actor["body"] == self.woman["body"]:
                return {"match": False, "confidence": 0.9, "reason": "not in scene 1"}
            return {"match": True, "confidence": 0.91, "reason": "ok"}

        s1 = os.path.join(self.tmp, "s1.png")
        s2 = os.path.join(self.tmp, "s2.png")
        s3 = os.path.join(self.tmp, "s3.png")
        _rgb_image(s1, (30, 30, 30), (160, 100))
        _rgb_image(s2, (50, 50, 50), (160, 100))
        _rgb_image(s3, (70, 70, 70), (160, 100))
        scenes = [
            {"clip_image": s1, "actor_refs": [self.woman, self.man]},
            {"clip_image": s2, "actor_refs": [self.woman, self.man]},
            {"clip_image": s3, "actor_refs": [self.woman, self.man]},
        ]
        report = scan_scenes_for_portraits(
            scenes, self.avatar, generate=generate, verify=verify,
            portrait_path=self._path_lookup({}),
            portrait_dest=self._dest,
        )
        self.assertEqual(report["grok_calls"], 3)
        self.assertEqual(report["strata_calls"], 3)
        self.assertEqual([c[0] for c in gen_calls], ["s1.png", "s1.png", "s2.png"])
        self.assertEqual(gen_calls[0][1], self.woman["body"])
        self.assertEqual(gen_calls[1][1], self.man["body"])
        self.assertEqual(gen_calls[2], ("s2.png", self.woman["body"]))
        self.assertNotIn("s3.png", [c[0] for c in gen_calls])
        have = set(os.listdir(self.avatar))
        self.assertIn("woman_mature_chinese_林氏.png", have)
        self.assertIn("man_youth_chinese_贾雨村.png", have)
        statuses = {(r["body"], r["status"]) for r in report["results"]}
        self.assertIn((self.woman["body"], STATUS_REJECTED), statuses)
        self.assertIn((self.woman["body"], STATUS_OK), statuses)
        self.assertIn((self.man["body"], STATUS_OK), statuses)

    def test_scene_image_untouched(self):
        before = Path(self.scene_img).read_bytes()
        mtime = os.path.getmtime(self.scene_img)
        extract_actor_portraits(
            self.scene_img, [self.woman], self.avatar,
            generate=self._gen((90, 90, 200), []),
            verify=lambda *a: {"match": True, "confidence": 0.8, "reason": "ok"},
            portrait_path=self._path_lookup({}),
            portrait_dest=self._dest,
        )
        self.assertEqual(Path(self.scene_img).read_bytes(), before)
        self.assertEqual(os.path.getmtime(self.scene_img), mtime)

    def test_default_slot_and_auto_hooks(self):
        scene = {"clip_image": self.scene_img}
        self.assertEqual(scene_clip_image_source(scene), os.path.abspath(self.scene_img))
        src = Path(ROOT, "gui/workflow/wf_prompt_flows.py").read_text(encoding="utf-8")
        self.assertNotIn("_maybe_auto_extract_actor_portraits", src)
        self.assertIn("portraits=True", src)
        self.assertIn("def portrait_step(scene, label)", src)
        self.assertIn("written_evt.wait(", src)
        self.assertIn("extract_portraits_for_scene(", src)
        self.assertIn("self._portrait_style()", src)
        dlg = Path(ROOT, "gui/picture_prompt_dialog.py").read_text(encoding="utf-8")
        run = dlg[dlg.index("def _run_portrait_extract"):dlg.index("def on_submit")]
        self.assertIn("scene_clip_image_source(scene, covers)", run)
        self.assertNotIn("chosen_image()", run)

    def test_no_cover_fallback_uses_only_scene_clip_image(self):
        cover = os.path.join(self.tmp, "cover.png")
        _rgb_image(cover, (1, 2, 3), (200, 120))
        seeded_clip = os.path.join(self.tmp, "clip_seed.png")
        frozen = os.path.join(self.tmp, "zero_last.png")
        import shutil

        shutil.copy2(cover, seeded_clip)
        shutil.copy2(cover, frozen)
        # 播种后还没提取：clip_image 是封面拷贝 → 不用，也不退到 clip_image_last / zero / 封面
        seeded = {"cover_origin": "cover", "clip_image": seeded_clip, "clip_image_last": self.scene_img,
                  "zero_image_last": frozen, "actor_refs": [self.woman]}
        self.assertTrue(clip_image_is_cover_copy(seeded))
        self.assertEqual(scene_clip_image_source(seeded), "")
        calls = []
        out = extract_portraits_for_scene(
            seeded, self.avatar, covers=[cover], generate=self._gen((5, 5, 5), calls),
            verify=lambda *a: {"match": True, "confidence": 0.99},
            portrait_path=self._path_lookup({}), portrait_dest=self._dest,
        )
        self.assertEqual(calls, [])
        self.assertEqual(out["reason"], "no_scene_clip_image")
        # 没有 clip_image：也不用 clip_image_last
        self.assertEqual(scene_clip_image_source({"clip_image_last": self.scene_img}), "")
        # 和项目封面同内容（无 cover_origin 标记）也算封面拷贝
        self.assertEqual(scene_clip_image_source({"clip_image": seeded_clip}, covers=[cover]), "")
        # 提取后：clip_image 是这一场自己的图 → 用它
        extracted = dict(seeded, clip_image=self.scene_img)
        out = extract_portraits_for_scene(
            extracted, self.avatar, covers=[cover], generate=self._gen((7, 7, 7), calls),
            verify=lambda *a: {"match": True, "confidence": 0.9},
            portrait_path=self._path_lookup({}), portrait_dest=self._dest,
        )
        self.assertEqual(out["source"], os.path.abspath(self.scene_img))
        self.assertEqual([c[0] for c in calls], ["scene.png"])

    def test_existing_portrait_skipped_when_only_parenthesis_differs(self):
        self.assertEqual(actor_identity("woman/mature/chinese/林氏（低头，青衫）"), "woman/mature/chinese/林氏")
        self.assertEqual(actor_identity("man/youth/chinese/贾雨村(走向门口)"), "man/youth/chinese/贾雨村")
        existing_file = self._dest("person", "woman/mature/chinese/林氏", self.avatar)
        with open(existing_file, "wb") as fh:
            fh.write(b"PASTED")
        calls = []

        def portrait_path(role, name, avatar_dir="", style=None):
            p = self._dest(role, name, avatar_dir)
            return p if os.path.isfile(p) else ""

        variant = dict(self.woman, body="woman/mature/chinese/林氏（另一场：站在门口，红衣）")
        rows = extract_actor_portraits(
            self.scene_img, [variant], self.avatar, generate=self._gen((3, 3, 3), calls),
            verify=lambda *a: {"match": True, "confidence": 0.99},
            portrait_path=portrait_path, portrait_dest=self._dest,
        )
        self.assertEqual(calls, [])
        self.assertEqual(rows[0]["status"], STATUS_SKIPPED)
        self.assertEqual(Path(existing_file).read_bytes(), b"PASTED")
        # 同一场里两个只差括号的同一人：只提取一次
        rows = extract_actor_portraits(
            self.scene_img,
            [dict(self.man, body="man/youth/chinese/贾雨村（坐）"), dict(self.man, body="man/youth/chinese/贾雨村（站）")],
            self.avatar, generate=self._gen((4, 4, 4), calls),
            verify=lambda *a: {"match": True, "confidence": 0.9},
            portrait_path=portrait_path, portrait_dest=self._dest,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(rows), 1)
        preset = actors_from_scene({"actor_refs": [dict(self.woman, body="woman/mature/chinese/林氏（低头）")]})
        self.assertEqual(preset[0]["body"], "woman/mature/chinese/林氏")

    def test_recheck_right_before_each_grok_call(self):
        """前一个人物/场景或用户刚粘贴的肖像：下一次调用前要重新查，不再提取。"""
        calls = []
        state = {}

        def portrait_path(role, name, avatar_dir="", style=None):
            return state.get(name, "")

        def generate(image, actor, prompt):
            calls.append(actor["body"])
            # Grok 处理第一个人时，用户在人物窗粘贴了第二个人的肖像
            pasted = self._dest("person", self.man["body"], self.avatar)
            _rgb_image(pasted, (9, 9, 9))
            state[self.man["body"]] = pasted
            path = os.path.join(self.tmp, f"g_{len(calls)}.png")
            _rgb_image(path, (100, 100, 100))
            return path

        rows = extract_actor_portraits(
            self.scene_img, [self.woman, self.man], self.avatar, generate=generate,
            verify=lambda *a: {"match": True, "confidence": 0.9},
            portrait_path=portrait_path, portrait_dest=self._dest,
        )
        self.assertEqual(calls, [self.woman["body"]])
        self.assertEqual([r["status"] for r in rows], [STATUS_OK, STATUS_SKIPPED])

    def test_paste_during_review_is_not_overwritten(self):
        state = {}
        pasted = self._dest("person", self.woman["body"], self.avatar)

        def portrait_path(role, name, avatar_dir="", style=None):
            return state.get(name, "")

        def verify(portrait, actor, scene_image):
            with open(pasted, "wb") as fh:
                fh.write(b"USER-PASTE")
            state[self.woman["body"]] = pasted
            return {"match": True, "confidence": 0.95}

        rows = extract_actor_portraits(
            self.scene_img, [self.woman], self.avatar, generate=self._gen((6, 6, 6), []),
            verify=verify, portrait_path=portrait_path, portrait_dest=self._dest,
        )
        self.assertEqual(rows[0]["status"], STATUS_SKIPPED)
        self.assertEqual(Path(pasted).read_bytes(), b"USER-PASTE")

    def test_preset_actor_refs_used_without_project_manager(self):
        scene = {"actor_refs": [self.woman]}
        found = actors_from_scene(scene)
        self.assertEqual(found[0]["body"], self.woman["body"])


if __name__ == "__main__":
    unittest.main()
