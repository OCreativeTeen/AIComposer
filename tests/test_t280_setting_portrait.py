# -*- coding: utf-8 -*-
"""t280: 地域 / 时代 / 舞台 进场景生成（Strata 每页 + 人物归拢）；生成肖像（utility/portrait_gen，假的 LLM / 图）；
LLM 手动窗口支持文生图（cli_kind="text_image"）。"""
import importlib
import os
import tempfile
import unittest

from tests.test_t272_pdf_scenes_cast import _read, _real
from tests.test_t280_actor_format import restore_modules, use_real_modules

pg = None


def setUpModule():
    global pg
    use_real_modules()
    pg = importlib.import_module("utility.portrait_gen")


def tearDownModule():
    restore_modules()

SCENES = [
    {"actor": "H woman/mature/chinese/秦 | man/youth/chinese/门子（低头）", "visual": "门子站在堂下。贾雨村坐着。"},
    {"actor": "man/mature/chinese/贾雨村 | man/youth/chinese/门子（笑，穿青衣）", "content": "门子笑道：老爷。"},
    {"actor": "man/mature/chinese/贾雨村", "content": "雨村独坐。"},
]
SETTING = "The story takes place in Suzhou, Ming dynasty. Stage: a county yamen hall."


class Setting(unittest.TestCase):
    def test_story_setting_context(self):
        from gui.dl import prompts_notebooklm as p

        txt = p.story_setting_context({"setting_region": "中国", "setting_era": "明朝"})
        self.assertTrue(txt.startswith("The story takes place in "), txt)
        self.assertEqual(p.story_setting_context({}), p.story_setting_context(None))

    def test_strata_page_user_text_carries_setting(self):
        from utility import pdf_scene_pages as psp

        txt = psp.page_user_text(1, 2, original_page=3, page_text="x", cast_text="", scenes=[], setting=SETTING)
        self.assertIn("SETTING", txt)
        self.assertIn(SETTING, txt)
        self.assertNotIn("SETTING", psp.page_user_text(1, 2, original_page=3, page_text="x", cast_text="", scenes=[]))

    def test_consolidation_prompt_carries_setting(self):
        from utility import cast_consolidate as cc

        scenes = [{"actor": "man/youth/chinese/甲", "speaking": "<1>a"}]
        people = []
        _sys, user = cc.build_prompt(scenes, people, setting=SETTING)
        self.assertIn(SETTING, user)
        _sys2, user2 = cc.build_prompt(scenes, people)
        self.assertNotIn("Story setting", user2)

    def test_downloader_passes_setting(self):
        src = _read("gui", "downloader.py")
        self.assertIn("story_setting_context(video_detail)", src)
        self.assertIn("setting=setting", src)


class FakeLLM:
    def __init__(self, reply="A young Chinese man in plain blue servant robes, Ming dynasty."):
        self.reply = reply
        self.calls = []

    def generate_text(self, system, user):
        self.calls.append((system, user))
        return self.reply


class FakeImageLLM:
    def __init__(self, img):
        self.img = img
        self.calls = []

    def show_manual_window(self, system, user="", **kw):
        self.calls.append((system, kw))
        return self.img


class Portrait(unittest.TestCase):
    def test_collect_descriptions_from_all_scenes(self):
        d = pg.collect_descriptions(SCENES, "man/youth/chinese/门子")
        self.assertEqual([x["scene"] for x in d], [1, 2])
        self.assertEqual(d[1]["note"], "笑，穿青衣")
        self.assertIn("门子笑道", d[1]["text"])

    def test_prompt_has_setting_style_rules(self):
        llm = FakeLLM()
        r = pg.write_portrait_prompt("man/youth/chinese/门子（低头）", SCENES, setting=SETTING, style="", llm=llm)
        self.assertEqual(r["source"], "strata")
        self.assertIn(SETTING, llm.calls[0][1])
        self.assertIn("scene 2", llm.calls[0][1])
        self.assertIn("region, era and story stage", llm.calls[0][0])
        p = r["prompt"]
        self.assertIn("Ming dynasty", p)
        self.assertIn("photorealistic", p)
        self.assertIn("no caption", p)
        self.assertIn("head-and-shoulders", p)

    def test_fallback_template_when_strata_empty(self):
        r = pg.write_portrait_prompt("man/youth/chinese/门子", SCENES, setting=SETTING, style="水墨画", llm=FakeLLM(""))
        self.assertEqual(r["source"], "template")
        self.assertIn("youth chinese man", r["prompt"])
        self.assertIn("Art style: 水墨画", r["prompt"])
        self.assertIn(SETTING, r["prompt"])

    def test_generate_saves_and_backs_up(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "man_youth_chinese_门子.png")
            Image.new("RGB", (8, 8), "red").save(dest)
            img_llm = FakeImageLLM(Image.new("RGB", (16, 16), "blue"))
            res = pg.generate_portrait("man/youth/chinese/门子", SCENES, dest, setting=SETTING,
                                       llm=FakeLLM(), image_llm=img_llm)
            self.assertTrue(res["ok"], res)
            self.assertEqual(os.path.normcase(res["path"]), os.path.normcase(dest))
            with Image.open(dest) as im:
                self.assertEqual(im.size, (16, 16))
            self.assertTrue(any(".bak" in n for n in os.listdir(tmp)))  # 原来的先备份
            self.assertEqual(img_llm.calls[0][1].get("cli_kind"), "text_image")
            self.assertEqual(img_llm.calls[0][1].get("extra", {}).get("image_backend"), "grok")
            self.assertEqual(img_llm.calls[0][0], res["prompt"])

    def test_cancel_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "x.png")
            res = pg.generate_portrait("man/youth/chinese/门子", SCENES, dest, llm=FakeLLM(), image_llm=FakeImageLLM(None))
            self.assertFalse(res["ok"])
            self.assertTrue(res["error"])
            self.assertEqual(os.listdir(tmp), [])

    def test_needs_full_id(self):
        res = pg.generate_portrait("", SCENES, "x.png", llm=FakeLLM(), image_llm=FakeImageLLM(None))
        self.assertFalse(res["ok"])


class TextToImageWindow(unittest.TestCase):
    def test_llm_api_text_image_mode(self):
        from utility import llm_api

        self.assertEqual(llm_api.TEXT_IMAGE_CLI_KIND, "text_image")
        src = _read("utility", "llm_api.py")
        self.assertIn('else "image" if (image_paths or cli_kind == TEXT_IMAGE_CLI_KIND)', src)
        self.assertIn("grok_cdp.make_image_from_text(prompt, status=_cli_set_status)", src)
        self.assertIn("img = gemini_cdp.make_image(prompt, [], status=_cli_set_status, allow_text=True)", src)

    def test_grok_and_gemini_text_to_image(self):
        import inspect

        from utility import gemini_cdp, grok_cdp

        self.assertTrue(hasattr(grok_cdp.make_image_from_text, "__wrapped__"))  # 和 make_image 一样加了 Chrome 锁
        self.assertIn("allow_text", inspect.signature(gemini_cdp.make_image).parameters)
        src = _read("utility", "grok_cdp.py")
        blk = src[src.index("def make_image_from_text"):src.index("# ---- cross-process lock")]
        self.assertIn("_ensure_image_mode(page, status)", blk)  # 绝不生成视频
        self.assertNotIn("prepare_imagine", blk)

    def test_buttons_in_both_previews(self):
        sap = _read("gui", "dl", "story_actor_panel.py")
        self.assertIn('text="生成肖像", command=self._gen_portrait', sap)
        wf = _read("gui", "workflow", "wf_actors.py")
        self.assertIn('gen_btn = ttk.Button(btns, text="生成肖像", command=gen_portrait)', wf)
        self.assertIn("portrait_gen.generate_portrait(", wf)
        self.assertIn("portrait_gen.generate_portrait(", sap)


DIALOG = r'''
import json, os, tempfile, tkinter as tk
from tkinter import messagebox
from gui.dl import story_actor_panel as sap
from utility import portrait_gen
from PIL import Image
root = tk.Tk()
root.withdraw()
tmp = tempfile.mkdtemp(prefix="_tmp_t280_")
seen = {}
def fake_generate(body, scenes, dest, *, setting="", style="", **kw):
    seen.update(body=body, n=len(scenes), setting=setting, style=style, dest=dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    Image.new("RGB", (10, 10), "green").save(dest)
    return {"ok": True, "path": dest, "prompt": "p", "source": "strata", "error": ""}
portrait_gen.generate_portrait = fake_generate
messagebox.showwarning = lambda *a, **k: None
p = sap.StoryActorPanel(root, text="H woman/mature/chinese/秦 | man/youth/chinese/门子",
                        person_dir=lambda: tmp, style=lambda: "写实 (Realistic)", channel_path=lambda: tmp,
                        portrait_context=lambda: {"scenes": [{"actor": "man/youth/chinese/门子"}], "setting": "SET"})
row = p._rows_from_chips()[1]
before = p.portrait_path(row)
d = sap.ActorEditDialog(p, row, allow_host=False, on_done=lambda r: None)
d._gen_portrait(runner=lambda w, job, done: done(job()))
after = seen["dest"]  # t281: 生成的存进频道肖像库 <频道>/avatar/<风格>/，不直接换这一位的肖像
out = {"before": before, "after": os.path.basename(after), "seen": {k: seen[k] for k in ("body", "n", "setting", "style")},
       "in_tmp": os.path.dirname(os.path.abspath(after)) == os.path.join(os.path.abspath(tmp), "avatar", "Realistic"),
       "hint": d.hint_var.get().startswith("已生成肖像") and p.portrait_path(row) == ""}
d.destroy()
root.destroy()
import shutil; shutil.rmtree(tmp, ignore_errors=True)
print(json.dumps(out, ensure_ascii=False))
'''


class DialogSmoke(unittest.TestCase):
    def test_actor_edit_dialog_generate_button(self):
        res = _real(DIALOG)
        self.assertEqual(res["before"], "")
        self.assertEqual(res["after"], "man_youth_chinese_门子.png")
        self.assertTrue(res["in_tmp"])
        self.assertTrue(res["hint"])
        self.assertEqual(res["seen"], {"body": "man/youth/chinese/门子", "n": 1, "setting": "SET", "style": "写实 (Realistic)"})


if __name__ == "__main__":
    unittest.main()
