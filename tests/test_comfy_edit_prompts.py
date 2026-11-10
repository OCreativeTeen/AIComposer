"""t356u: separate ComfyUI (MOSS / QN) image-edit prompts + negatives; Grok/Gemini prompts unchanged (offline)."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_video_speaker_semantics import _install_stubs  # noqa: E402

_install_stubs()


def _imp(name):
    """Import with throwaway stubs for heavy optional deps (rembg, dotenv, …)."""
    for _ in range(40):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as e:
            miss = e.name
            if not miss or miss in sys.modules or miss.split(".")[0] in ("utility", "config", "config_prompt", "gui"):
                raise
            m = types.ModuleType(miss)
            m.__path__ = []
            m.__getattr__ = (lambda attr: (_ for _ in ()).throw(AttributeError(attr)) if attr.startswith("__")
                             else (lambda *a, **k: None))
            sys.modules[miss] = m
    raise RuntimeError("too many stubs")


cp = _imp("config_prompt")


def _load_sd_image_processor():
    """Load utility/sd_image_processor.py under a private name with temporary stubs (llm_api, rembg, config
    attributes), then put sys.modules back so other test modules see exactly what they saw before."""
    import importlib.util

    import utility  # noqa: F401

    saved = dict(sys.modules)
    base_cfg = sys.modules.get("config")

    class _Cfg(types.ModuleType):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return getattr(base_cfg, name, "") if base_cfg is not None else ""

    try:
        sys.modules["config"] = _Cfg("config")
        for name in ("utility.llm_api", "rembg"):
            if name not in sys.modules:
                m = types.ModuleType(name)
                m.remove = lambda *a, **k: None
                sys.modules[name] = m
        spec = importlib.util.spec_from_file_location("utility._t356u_sd_image_processor",
                                                      str(ROOT / "utility" / "sd_image_processor.py"))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "utility"
        for _ in range(20):
            try:
                spec.loader.exec_module(mod)
                break
            except ModuleNotFoundError as e:
                if not e.name or e.name in sys.modules or e.name.split(".")[0] in ("utility", "config_prompt"):
                    raise
                sys.modules[e.name] = types.ModuleType(e.name)
        return mod
    finally:
        for k in list(sys.modules):
            if k not in saved:
                del sys.modules[k]
        sys.modules.update(saved)


sdp = _load_sd_image_processor()
from utility import cover_panels  # noqa: E402

COVER = str(ROOT / "covers" / "cover1.png")
COVER3 = str(ROOT / "covers" / "cover3.png")
ROWS = [
    {"label": "人物1", "role": "person", "name": "woman/mature/chinese/封氏", "image": "/p/a.png", "image_no": 2},
    {"label": "人物2", "role": "person", "name": "man/youth/chinese/贾雨村", "image": "/p/b.png", "image_no": 3},
    {"label": "人物3", "role": "person", "name": "man/elder/chinese/甄士隐", "image": "/p/c.png", "image_no": 4},
    {"label": "人物4", "role": "person", "name": "girl/child/chinese/英莲", "image": "", "image_no": 0},
]
SCENE = {"caption": "雨夜狂奔", "visual": "雨夜的街上，封氏撑伞追赶贾雨村，甄士隐站在门口。",
         "speaking": "<1> 等一等！ <2> 我不回头了。", "actor": "人物1:woman/mature/chinese/封氏"}


def grok_gemini_cases() -> list:
    """Every Grok / Gemini image-edit prompt builder touched by 图片修改, over a spread of options."""
    out = []
    for k in (1, 2, 4):
        for cap in ("keep", "erase", "keywords", "express"):
            for keep in (True, False):
                for ex in (True, False):
                    out.append(cp.build_step_image_clipbody(
                        k, visual_style="水彩", keep_style=keep, caption=cap, extract_only=ex,
                        fyi="多一点雨" if k == 2 else "", scene_caption="标题" if not ex else "",
                        scene_visual="画面" if not ex else "", main_character="封氏" if not ex else ""))
    for text in ("keep", "erase", "keywords", "express"):
        out.append(cp.build_cast_fix_prompt(SCENE, ROWS[:3], visual_style="水彩", fyi="主角换人", text=text))
    out.append(cp.build_cast_fix_prompt({}, ROWS[:1]))
    for task in ("keep", "restyle", "extract"):
        for text in ("keep", "erase", "keywords", "express"):
            for flags in ((False, False, False), (True, False, False), (True, True, True)):
                try:
                    out.append(cp.build_picture_flow_prompt(
                        task=task, text=text, visual_style="水彩", narrative="story",
                        use_visual=flags[0], use_speaking=flags[1], use_actor=flags[2], scene_content=[SCENE],
                        host_narrator="", main_character="", actor_override="",
                        edit_request="把天空改成黄昏" if not any(flags) else "",
                        actor_images=ROWS[:2] if flags[2] else [], base_image=True))
                except ValueError as exc:
                    out.append("ValueError:" + str(exc))
    out.append(cp.output_aspect_line("1920x1080") + "|" + cp.output_aspect_line("1080x1920"))
    out.append(cp.scene_cast_lock_line([SCENE], True, where="picture"))
    return out


# sha256 of "\n<<>>\n".join(grok_gemini_cases()).
# t373u: intentionally re-taken — every Grok / Gemini image-edit prompt now starts with the
# "ART STYLE LOCK (rule 1, most important):" line, and the people-extract wording keeps the picture's art style.
# (Before t373u: ba6d90e4d3be804a2cc4deae8aac0f0e307e8a8cdd81fca6ebf5517c64a68ec2, unchanged since pre-t356u.)
GROK_GEMINI_DIGEST = "24d15f7b4f36112f4f554b2189cbee219b678e0dcb62ae40301abbe876ed04b8"


def _body(prompt: str) -> str:
    """t373u: the prompt without its leading ART STYLE LOCK line (asserts the lock really is first)."""
    first, _, rest = prompt.partition("\n")
    assert first.startswith((cp.IMAGE_STYLE_LOCK_PREFIX, cp.UPSCALE_RESTORE_PREFIX)), first[:80]  # t377u: upscale
    return rest.lstrip("\n")


class GrokGeminiUnchangedTest(unittest.TestCase):
    def test_grok_gemini_prompts_byte_identical(self):
        got = hashlib.sha256("\n<<>>\n".join(grok_gemini_cases()).encode("utf-8")).hexdigest()
        self.assertEqual(got, GROK_GEMINI_DIGEST)

    def test_only_moss_qn_are_comfy(self):
        self.assertEqual(cp.comfy_backend("grok"), "")
        self.assertEqual(cp.comfy_backend("gemini"), "")
        self.assertEqual(cp.comfy_backend(""), "")
        self.assertEqual(cp.comfy_backend("MOSS"), "moss")
        self.assertEqual(cp.comfy_backend("qn"), "qn")

    def test_dialog_comfy_branches_are_gated(self):
        src = (ROOT / "gui" / "picture_prompt_dialog.py").read_text(encoding="utf-8")
        self.assertIn("comfy = config_prompt.comfy_backend(backend)", src)
        for call in ("build_comfy_cover_step_prompt", "build_comfy_cast_fix_prompt", "build_comfy_picture_edit_prompt"):
            self.assertEqual(src.count(call + "("), 1, call)
        # every use of the comfy helpers sits under an ``if comfy`` guard
        self.assertEqual(src.count("_comfy_step_job(step_no") + src.count("_comfy_step_job(k,"), 3)
        self.assertGreaterEqual(src.count("if comfy:"), 4)
        # portrait extraction stays Grok-only: no comfy code in _run_portrait_extract
        start = src.index("def _run_portrait_extract")
        end = src.index("def on_submit")
        self.assertNotIn("comfy", src[start:end])


class CoverPanelLayoutTest(unittest.TestCase):
    def test_cover1_is_four_columns(self):
        lay = cover_panels.detect_panel_layout(COVER)
        self.assertEqual((lay["layout"], lay["count"]), ("columns", 4))
        self.assertEqual(cover_panels.detect_panel_layout(COVER, 4)["layout"], "columns")

    def test_irregular_cover_is_unknown(self):
        self.assertEqual(cover_panels.detect_panel_layout(COVER3)["layout"], "")

    def test_crop_second_panel(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as d:
            prep = cover_panels.prepare_cover_step_input(COVER, 2, out_dir=d)
            self.assertTrue(prep["cropped"])
            with Image.open(prep["image"]) as im:
                w, h = im.size
            self.assertEqual(h, 2752)
            self.assertTrue(360 <= w <= 410, w)  # one quarter of 1536

    def test_rows_and_out_of_range(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "rows.png")
            im = Image.new("RGB", (900, 1200), (250, 250, 250))
            for i, c in enumerate(((200, 30, 30), (30, 200, 30), (30, 30, 200))):
                im.paste(c, (0, i * 400, 900, (i + 1) * 400))
            im.save(p)
            lay = cover_panels.detect_panel_layout(p)
            self.assertEqual((lay["layout"], lay["count"]), ("rows", 3))
            self.assertLessEqual(abs(cover_panels.panel_box(lay, 3)[1] - 800), 8)
            self.assertIsNone(cover_panels.panel_box(lay, 4))
            self.assertEqual(cover_panels.prepare_cover_step_input(p, 5, out_dir=d)["cropped"], False)


class ComfyPromptTest(unittest.TestCase):
    def test_cover_step_cropped_moss_vs_qn(self):
        m, mn = cp.build_comfy_cover_step_prompt(2, backend="moss", layout="columns", count=4, cropped=True,
                                                 caption="erase", size=(1360, 768), scene_caption="雨夜狂奔")
        q, qn = cp.build_comfy_cover_step_prompt(2, backend="qn", layout="columns", count=4, cropped=True,
                                                 caption="erase", size=(1360, 768), scene_caption="雨夜狂奔")
        self.assertTrue(_body(m).startswith("image 1 is one panel cut out"))
        self.assertTrue(_body(q).startswith("Picture 1 is one panel cut out"))
        self.assertIn("wide 16:9 landscape", m)
        self.assertIn('title "雨夜狂奔"', m)
        self.assertEqual(mn, qn)
        for neg in ("collage", "split screen", "text", "watermark", "deformed face"):
            self.assertIn(neg, mn)
        self.assertNotIn("Do not", m)

    def test_cover_step_position_words(self):
        cols, _ = cp.build_comfy_cover_step_prompt(2, layout="columns", count=4)
        rows, _ = cp.build_comfy_cover_step_prompt(3, layout="rows", count=5)
        unk, _ = cp.build_comfy_cover_step_prompt(2)
        self.assertIn("side by side, read from left to right", cols)
        self.assertIn("2nd panel from the left (panel 2 of 4)", cols)
        self.assertIn("stacked from top to bottom", rows)
        self.assertIn("3rd panel from the top", rows)
        self.assertIn("reading order (left to right, then top to bottom)", unk)
        self.assertNotIn("counting from the top", cols)

    def test_cover_caption_keep_allows_text(self):
        pos, neg = cp.build_comfy_cover_step_prompt(2, cropped=True, caption="keep")
        self.assertIn("short title once, as a single caption line", pos)
        self.assertIn("duplicate title", neg)
        self.assertNotIn("letters", neg)
        pos, neg = cp.build_comfy_cover_step_prompt(2, cropped=True, caption="keywords")
        self.assertIn("key words", pos)
        self.assertNotIn("letters", neg)
        self.assertIn("speech bubble", neg)

    def test_cast_rows_respect_slot_limits(self):
        m_rows, m_paths = cp.comfy_cast_rows(ROWS, "moss")
        q_rows, q_paths = cp.comfy_cast_rows(ROWS, "qn")
        self.assertEqual(m_paths, ["/p/a.png", "/p/b.png", "/p/c.png"])
        self.assertEqual(q_paths, ["/p/a.png", "/p/b.png"])
        self.assertEqual([r["image_no"] for r in q_rows], [2, 3, 0, 0])
        pos, neg = cp.build_comfy_cast_fix_prompt(SCENE, q_rows, backend="qn", text="erase")
        self.assertIn("exactly 4 people", pos)
        self.assertIn("Picture 2 shows 封氏 (woman, mature, chinese)", pos)
        self.assertIn("Picture 3 shows 贾雨村", pos)
        self.assertIn("甄士隐 (man, elder, chinese) has no reference picture", pos)
        self.assertNotIn("Picture 4", pos)
        self.assertIn("extra people", neg)
        m_pos, _ = cp.build_comfy_cast_fix_prompt(SCENE, m_rows, backend="moss")
        self.assertIn("image 4 shows 甄士隐", m_pos)

    def test_general_edit_variants(self):
        pos, neg = cp.build_comfy_picture_edit_prompt(backend="moss", task="keep", text="keep", edit_request="把天空改成黄昏")
        self.assertTrue(_body(pos).startswith("把天空改成黄昏\nChange only what is asked"))
        self.assertIn("extra people", neg)
        self.assertNotIn("caption", neg)  # keep text: nothing in the negative fights the picture's own words
        self.assertNotIn("background figures", neg)
        pos, _ = cp.build_comfy_picture_edit_prompt(backend="qn", task="restyle", text="erase", visual_style="水彩",
                                                    scene=SCENE, use_visual=True, region="中国", era="清朝")
        self.assertIn("Edit Picture 1 to show this scene: 雨夜的街上", pos)
        self.assertIn("Redraw the whole picture in this art style: 水彩", pos)
        self.assertNotIn("Story_Scene_Content", pos)
        self.assertNotIn("Picture_choices", pos)
        pos, neg = cp.build_comfy_picture_edit_prompt(backend="moss", task="extract", text="keep")
        self.assertIn("waist-up portrait of every person in image 1", pos)
        self.assertIn("scenery", neg)

    def test_canvas_size(self):
        self.assertEqual(cp.comfy_canvas_size("1920x1080"), (1360, 768))
        self.assertEqual(cp.comfy_canvas_size("1080x1920"), (768, 1360))
        self.assertEqual(cp.comfy_canvas_size(""), ())


class ComfyWorkflowTest(unittest.TestCase):
    def _qwf(self):
        with open(sdp.QN_EDIT_API_WORKFLOW, encoding="utf-8-sig") as f:
            return json.load(f)

    def test_qwen_canvas_override(self):
        wf = sdp.build_qwen_edit_prompt(self._qwf(), base_name="b.png", ref_names=[], prompt="p", seed=1,
                                        negative="n", width=1360, height=768, base_size=(1920, 1080))
        ks = sdp._one_node(wf, "KSampler")
        lat = wf[ks]["inputs"]["latent_image"][0]
        self.assertEqual(wf[lat]["class_type"], "EmptySD3LatentImage")
        self.assertEqual((wf[lat]["inputs"]["width"], wf[lat]["inputs"]["height"]), (1360, 768))
        self.assertFalse(sdp._find_nodes(wf, "VAEEncode"))
        self.assertEqual(wf["36"]["inputs"]["prompt"], "n")
        # the base still feeds the encoder as the reference picture, scaled to the canvas pixel count
        self.assertEqual(wf["39"]["inputs"]["image1"], ["117", 0])
        self.assertEqual(wf["117"]["class_type"], "ImageScaleToTotalPixels")
        self.assertEqual(wf["117"]["inputs"]["image"], ["8", 0])
        self.assertEqual(wf["117"]["inputs"]["resolution_steps"], 16)
        self.assertAlmostEqual(wf["117"]["inputs"]["megapixels"], 1360 * 768 / 1048576.0, places=3)

    def test_qwen_tall_crop_keeps_kontext_scale(self):
        wf = sdp.build_qwen_edit_prompt(self._qwf(), base_name="b.png", ref_names=[], prompt="p", seed=1,
                                        width=1360, height=768, base_size=(384, 2752))
        ks = sdp._one_node(wf, "KSampler")
        self.assertEqual(wf[wf[ks]["inputs"]["latent_image"][0]]["class_type"], "EmptySD3LatentImage")
        self.assertEqual(wf["117"]["class_type"], "FluxKontextImageScale")
        wf = sdp.build_qwen_edit_prompt(self._qwf(), base_name="b.png", ref_names=[], prompt="p", seed=1,
                                        width=1360, height=768)
        self.assertEqual(wf["117"]["class_type"], "FluxKontextImageScale")

    def test_qwen_default_follows_base(self):
        wf = sdp.build_qwen_edit_prompt(self._qwf(), base_name="b.png", ref_names=[], prompt="p", seed=1)
        ks = sdp._one_node(wf, "KSampler")
        self.assertEqual(wf[wf[ks]["inputs"]["latent_image"][0]]["class_type"], "VAEEncode")
        self.assertEqual(wf["117"]["class_type"], "FluxKontextImageScale")

    def test_fallback_adapt_uses_layout(self):
        grok = cp.output_aspect_line("1920x1080") + "\n\n" + cp.build_step_image_clipbody(
            2, extract_only=True, keep_style=True, caption="erase")
        pos, neg = sdp.adapt_prompt_for_moss_edit(grok, COVER)
        self.assertIn("2nd panel from the left (panel 2 of 4)", pos)
        self.assertNotIn("counting from the top", pos)
        self.assertIn("Remove all writing", pos)
        self.assertIn("collage", neg)
        q, _ = sdp.adapt_prompt_for_qwen_edit(grok, COVER)
        self.assertTrue(_body(q).startswith("Picture 1 is a story cover"))
        pos2, _ = sdp.adapt_prompt_for_moss_edit(grok)
        self.assertIn("reading order", pos2)
        self.assertEqual(sdp._parse_extract_step_prompt(grok)["size"], (1360, 768))

    def test_fallback_crop_and_passthrough(self):
        grok = cp.build_step_image_clipbody(2, extract_only=True)
        pos, neg, img = sdp._adapt_extract_step(grok, COVER, "moss", crop=True)
        self.assertTrue(_body(pos).startswith("image 1 is one panel cut out"))
        self.assertTrue(img.endswith("cover1_panel2of4.png"), img)
        other = "Make the sky orange."
        self.assertEqual(sdp.adapt_prompt_for_moss_edit(other), (other, None))

    def test_generators_accept_comfy_kwargs(self):
        import inspect

        for fn in (sdp.generate_image_moss_edit, sdp.generate_image_qwen_edit):
            params = inspect.signature(fn).parameters
            for name in ("negative", "adapt", "width", "height"):
                self.assertIn(name, params, (fn.__name__, name))


class ComfyDispatchSourceTest(unittest.TestCase):
    def test_batch_workers_and_manual_window_pass_comfy_meta(self):
        flows = (ROOT / "gui" / "workflow" / "wf_prompt_flows.py").read_text(encoding="utf-8")
        self.assertIn("generate_image_moss_edit(prompt, list(images), status=scene_status(head), **comfy_kwargs(job))", flows)
        self.assertIn("generate_image_qwen_edit(prompt, list(images), status=scene_status(head), **comfy_kwargs(job))", flows)
        self.assertIn('extra["comfy_negative"]', flows)
        api = (ROOT / "utility" / "llm_api.py").read_text(encoding="utf-8")
        self.assertIn("generate_image_moss_edit(prompt, list(image_paths), status=_cli_set_status, **_cf)", api)
        self.assertIn("generate_image_qwen_edit(prompt, list(image_paths), status=_cli_set_status, **_cf)", api)
        # Grok / Gemini calls in the manual window are untouched
        self.assertIn("img = grok_cdp.make_image(prompt, list(image_paths), status=_cli_set_status)", api)
        self.assertIn("img = gemini_cdp.make_image(prompt, list(image_paths), status=_cli_set_status)", api)


if __name__ == "__main__":
    unittest.main()
