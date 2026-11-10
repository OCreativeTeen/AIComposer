"""t373u: every image-processing prompt leads with the project's art-style lock (portrait extraction included)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_comfy_edit_prompts import ROWS, SCENE, cp  # noqa: E402
from utility.actor_portrait_extract import build_portrait_extract_prompt  # noqa: E402

CARTOON = "三维卡通 (Pixar-Art-Cartoon)"
REAL = "写实 (Realistic)"
ACTOR = {"body": "man/mature/chinese/陈默", "gender": "man", "age": "mature", "nationality": "chinese",
         "name": "陈默", "note": "灰色外套"}


def _first(p: str) -> str:
    return p.split("\n", 1)[0]


class LockTextTest(unittest.TestCase):
    def test_stylized_lock(self):
        lock = cp.image_art_style_lock_rule(CARTOON, "Image 1")
        self.assertTrue(lock.startswith(cp.IMAGE_STYLE_LOCK_PREFIX))
        for bit in ("3D animation (Pixar-style 3D animated cartoon, CGI)", CARTOON, "never photorealistic",
                    "not a photo", "not live-action", "画风锁定", "绝不变成写实照片 / 真人"):
            self.assertIn(bit, lock)
        self.assertNotIn("画风锁定", cp.image_art_style_lock_rule(CARTOON, zh=False))
        self.assertIn("redraw everything", cp.image_art_style_lock_rule(CARTOON, restyle=True))

    def test_realistic_and_empty_lock(self):
        real = cp.image_art_style_lock_rule(REAL)
        self.assertNotIn("never photorealistic", real)
        self.assertIn("photorealistic", real)
        self.assertIn("not cartoon", real)
        empty = cp.image_art_style_lock_rule("")
        self.assertTrue(empty.startswith(cp.IMAGE_STYLE_LOCK_PREFIX))
        self.assertIn("never turned into a photo or a real person", empty)

    def test_negatives(self):
        self.assertIn("photorealistic", cp.comfy_style_negative(CARTOON))
        self.assertIn("live-action", cp.comfy_style_negative(CARTOON))
        self.assertNotIn("photorealistic", cp.comfy_style_negative(REAL))
        self.assertIn("cartoon", cp.comfy_style_negative(REAL))
        self.assertEqual(cp.comfy_style_negative(""), "different art style, restyled")

    def test_style_lock_first(self):
        body = cp.build_picture_flow_prompt(task="keep", text="keep", visual_style=CARTOON, use_visual=False,
                                            use_speaking=False, use_actor=False, edit_request="天空变黄昏")
        wrapped = cp.output_aspect_line("1920x1080") + "\n\nNote: FYI\n\n" + body
        self.assertFalse(wrapped.startswith(cp.IMAGE_STYLE_LOCK_PREFIX))
        moved = cp.style_lock_first(wrapped)
        self.assertTrue(moved.startswith(cp.IMAGE_STYLE_LOCK_PREFIX))
        self.assertEqual(moved.count(cp.IMAGE_STYLE_LOCK_PREFIX), 1)
        self.assertIn("OUTPUT FORMAT", moved)
        self.assertNotIn("\n\n\n", moved)
        self.assertEqual(cp.style_lock_first(moved), moved)
        self.assertEqual(cp.style_lock_first("no lock here"), "no lock here")


class PortraitExtractTest(unittest.TestCase):
    def test_portrait_prompt_leads_with_project_style(self):
        p = build_portrait_extract_prompt(ACTOR, CARTOON)
        self.assertTrue(p.startswith(cp.IMAGE_STYLE_LOCK_PREFIX))
        self.assertIn("3D animation", _first(p))
        self.assertIn("never photorealistic", _first(p))
        self.assertIn("same art style as Image 1", p)
        for gone in ("real face", "neutral background"):
            self.assertNotIn(gone, p)
        self.assertTrue(build_portrait_extract_prompt(ACTOR).startswith(cp.IMAGE_STYLE_LOCK_PREFIX))

    def test_review_passes_project_style(self):
        src = Path(ROOT, "utility/actor_portrait_extract.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("build_portrait_extract_prompt(row, style)"), 2)
        self.assertNotIn("build_portrait_extract_prompt(row))", src)


class GrokGeminiPromptsTest(unittest.TestCase):
    def test_every_builder_starts_with_lock(self):
        prompts = []
        for task in ("keep", "restyle", "extract"):
            for flags in ((False, False, False), (True, True, True)):
                prompts.append(cp.build_picture_flow_prompt(
                    task=task, text="keep", visual_style=CARTOON, use_visual=flags[0], use_speaking=flags[1],
                    use_actor=flags[2], scene_content=[SCENE], edit_request="" if any(flags) else "把天空改成黄昏",
                    actor_images=ROWS[:2] if flags[2] else []))
        for ex in (True, False):
            for keep in (True, False):
                prompts.append(cp.build_step_image_clipbody(2, visual_style=CARTOON, keep_style=keep, extract_only=ex,
                                                            fyi="多一点雨"))
        prompts.append(cp.build_cast_fix_prompt(SCENE, ROWS[:2], visual_style=CARTOON, fyi="主角换人"))
        for p in prompts:
            self.assertTrue(p.startswith(cp.IMAGE_STYLE_LOCK_PREFIX), p[:120])
            self.assertIn("never photorealistic", _first(p))
            self.assertIn(CARTOON, _first(p))

    def test_upscale_leads_with_faithful_restore_not_style_lock(self):
        # t377u: upscale / last-frame enhance = faithful restore; the style is only a description
        p = cp.build_upscale_prompt((1920, 1080), CARTOON)
        self.assertTrue(p.startswith(cp.UPSCALE_RESTORE_PREFIX), p[:120])
        self.assertNotIn(cp.IMAGE_STYLE_LOCK_PREFIX, p)
        self.assertNotIn("never photorealistic", p)
        self.assertIn(CARTOON, _first(p))
        self.assertIn("only a description", _first(p))
        pos, neg = cp.build_comfy_upscale_prompt((1920, 1080), backend="moss", style=CARTOON)
        self.assertTrue(pos.startswith(cp.UPSCALE_RESTORE_PREFIX))
        self.assertNotIn("忠实修复", pos)  # ComfyUI: English only
        self.assertNotIn("photorealistic,", neg + ",")  # no one-sided realism push
        for both in ("more cartoonish", "more realistic", "exaggerated 3D"):
            self.assertIn(both, neg)

    def test_extract_has_no_photo_wording(self):
        p = cp.build_picture_flow_prompt(task="extract", text="keep", visual_style=CARTOON, scene_content=[SCENE])
        self.assertIn("same art style", p)
        self.assertNotIn("Plain empty background. ", p)


class ComfyPromptsTest(unittest.TestCase):
    def test_every_comfy_builder_starts_with_lock_and_bans_photo(self):
        rows, _paths = cp.comfy_cast_rows(ROWS, "qn")
        pairs = [
            cp.build_comfy_cover_step_prompt(2, backend="moss", cropped=True, visual_style=CARTOON),
            cp.build_comfy_cover_step_prompt(2, backend="qn", keep_style=False, visual_style=CARTOON),
            cp.build_comfy_cast_fix_prompt(SCENE, rows, backend="qn", visual_style=CARTOON),
            cp.build_comfy_picture_edit_prompt(backend="moss", task="extract", visual_style=CARTOON),
            cp.build_comfy_picture_edit_prompt(backend="qn", task="keep", visual_style=CARTOON, edit_request="x"),
            cp.build_comfy_picture_edit_prompt(backend="qn", task="restyle", visual_style=CARTOON, scene=SCENE,
                                               use_visual=True),
        ]
        for pos, neg in pairs:
            self.assertTrue(pos.startswith(cp.IMAGE_STYLE_LOCK_PREFIX), pos[:120])
            self.assertNotIn("画风锁定", pos)  # ComfyUI: English only
            self.assertIn("photorealistic", neg)
            self.assertIn("live-action", neg)

    def test_people_extract_no_grey_photo_backdrop(self):
        pos, _neg = cp.build_comfy_picture_edit_prompt(backend="qn", task="extract", visual_style=CARTOON)
        self.assertNotIn("Plain light grey background", pos)
        self.assertIn("same art style as Picture 1", pos)


class SinkWiringTest(unittest.TestCase):
    def test_lock_moved_first_before_sending(self):
        flows = Path(ROOT, "gui/workflow/wf_prompt_flows.py").read_text(encoding="utf-8")
        manual = flows.split("def open_manual(", 1)[1].split("def batch_scenes", 1)[0]
        self.assertIn("config_prompt.style_lock_first(prompt)", manual)
        batch = flows.split("def _run_picture_batch", 1)[1]
        self.assertIn("config_prompt.style_lock_first(j[1])", batch.split("def in_episode_label", 1)[0])
        self.assertIn('return config_prompt.style_lock_first("\\n".join(parts)), base + attach', batch)
        dlg = Path(ROOT, "gui/picture_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn("build_upscale_prompt(target, style_up)", dlg)


if __name__ == "__main__":
    unittest.main()
