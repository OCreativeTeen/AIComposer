# -*- coding: utf-8 -*-
"""t281: 参考图称呼用新写法（H 讲员 / 人物不带 人物N + actor 位置）；人物合并时肖像 / 声音也并；
「生成肖像」：STORY 存进频道肖像库（当前画面风格），提示词带画面比例；魔法工作流用当前场景的比例 / 地域 / 时代 / 舞台。"""
import importlib
import os
import re
import tempfile
import unittest

from tests.test_t272_pdf_scenes_cast import ROOT, _read, _real
from tests.test_t280_actor_format import restore_modules, use_real_modules

af = cm = pg = cp = None


def setUpModule():
    global af, cm, pg, cp
    use_real_modules()
    af = importlib.import_module("utility.actor_format")
    cm = importlib.import_module("utility.cast_merge")
    pg = importlib.import_module("utility.portrait_gen")
    cp = importlib.import_module("config_prompt")


def tearDownModule():
    restore_modules()


HOST = {"label": "讲员", "role": "host", "name": "man/mature/chinese", "pos": 1, "image_no": 2}
FENG = {"label": "人物1", "role": "person", "name": "woman/mature/chinese/封氏", "pos": 2, "image_no": 3}
MENZI = {"label": "人物2", "role": "person", "name": "man/youth/chinese/门子", "pos": 3, "image_no": 0}


class Labels(unittest.TestCase):
    def test_ref_who(self):
        self.assertEqual(af.ref_who({"role": "host", "name": "man/mature/chinese"}), "H man/mature/chinese")
        self.assertEqual(af.ref_who(FENG), "woman/mature/chinese/封氏 (actor position 2)")
        self.assertEqual(af.ref_who(FENG, zh=True), "woman/mature/chinese/封氏（actor 第2位）")
        self.assertEqual(af.ref_who({"role": "person", "name": "man/youth/chinese/门子"}, pos=4),
                         "man/youth/chinese/门子 (actor position 4)")

    def test_reference_images_note(self):
        t = cp.picture_reference_images_note([HOST, FENG, MENZI], task="edit", narrative="x")
        self.assertIn("Image 2 = H man/mature/chinese (actor position 1)", t)
        self.assertIn("Image 3 = woman/mature/chinese/封氏 (actor position 2)", t)
        self.assertIn("第3张图是woman/mature/chinese/封氏（actor 第2位）的形象图", t)
        self.assertIn("man/youth/chinese/门子 (actor position 3)", t)
        self.assertNotIn("人物1", t)
        self.assertNotIn("「man", t)
        self.assertNotIn("「woman", t)

    def test_cast_fix_prompt(self):
        t = cp.build_cast_fix_prompt({"visual": "v", "actor": "H man/mature/chinese | woman/mature/chinese/封氏"},
                                     [dict(HOST, pos=None), dict(FENG, pos=None)])
        self.assertIn("- H man/mature/chinese (actor position 1): reference portrait is Image 2", t)
        self.assertIn("- woman/mature/chinese/封氏 (actor position 2): reference portrait is Image 3", t)
        self.assertNotIn("人物1 =", t)
        self.assertNotIn("人物1 (", t)

    def test_who_helper(self):
        self.assertEqual(cp._who({"role": "host", "body": "man/mature/chinese"}), "H man/mature/chinese")
        self.assertEqual(cp._who({"role": "person", "label": "人物1", "body": "woman/mature/chinese/封氏"}),
                         "woman/mature/chinese/封氏")

    def test_other_sites_use_ref_who(self):
        self.assertIn('"pos": pos', _read("utility", "content_pdf.py"))
        self.assertIn("ref_who(r)", _read("gui", "workflow", "wf_prompt_flows.py"))
        ppd = _read("gui", "picture_prompt_dialog.py")
        self.assertNotIn("{r['label']} {r['name']}", ppd)
        cps = _read("config_prompt.py")
        self.assertNotIn('label = "讲员" if row.get("role") == "host" else (row.get("label") or "人物")', cps)
        self.assertNotIn('role = "讲员" if row.get("role") == "host" else (row.get("label") or "人物")', cps)
        self.assertNotIn("{r.get('label') or '人物'}", cps)
        self.assertNotIn("{r.get('label')} = {r.get('name')}", cps)


class MergeAssets(unittest.TestCase):
    def _img(self, path, color):
        from PIL import Image

        Image.new("RGB", (4, 4), color).save(path)

    def _color(self, path):
        from PIL import Image

        with Image.open(path) as im:
            return im.convert("RGB").getpixel((0, 0))

    def test_keep_first_backup_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "man_youth_chinese_门子.png"), os.path.join(tmp, "man_youth_chinese_门子乙.png")
            self._img(a, "red")
            self._img(b, "blue")
            dest = os.path.join(tmp, "man_youth_chinese_门子甲.png")
            r = cm.merge_portrait_files([a, b], dest)
            self.assertEqual(r["kept"], a)
            self.assertEqual(self._color(dest), (255, 0, 0))
            self.assertFalse(os.path.exists(a))
            self.assertFalse(os.path.exists(b))
            self.assertEqual(len(r["backups"]), 2)
            self.assertTrue(all(os.path.isfile(p) and ".bak" in p for p in r["backups"]))

    def test_first_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = os.path.join(tmp, "man_youth_chinese_门子乙.png")
            self._img(b, "blue")
            dest = os.path.join(tmp, "man_youth_chinese_门子甲.png")
            r = cm.merge_portrait_files(["", os.path.join(tmp, "missing.png"), b], dest)
            self.assertEqual(r["kept"], b)
            self.assertEqual(self._color(dest), (0, 0, 255))
            self.assertEqual(len(r["backups"]), 1)

    def test_dest_is_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "man_youth_chinese_门子.png"), os.path.join(tmp, "man_youth_chinese_门子乙.png")
            self._img(a, "red")
            self._img(b, "blue")
            r = cm.merge_portrait_files([a, b], a)
            self.assertEqual(self._color(a), (255, 0, 0))
            self.assertEqual(len(r["backups"]), 1)
            self.assertFalse(os.path.exists(b))

    def test_nothing(self):
        self.assertEqual(cm.merge_portrait_files(["", None], "x.png")["kept"], "")

    def test_voices(self):
        pc = {"actor_voices": {"man/youth/chinese/门子乙": "v2", "man/youth/chinese/门子丙": "v3"}}
        r = cm.merge_voice_settings(pc, ["man/youth/chinese/门子", "man/youth/chinese/门子乙", "man/youth/chinese/门子丙"],
                                    "man/youth/chinese/门子甲")
        self.assertEqual(r, {"voice": "v2", "changed": True})
        self.assertEqual(pc["actor_voices"]["man/youth/chinese/门子甲"], "v2")
        self.assertEqual(pc["actor_voices"]["man/youth/chinese/门子乙"], "v2")  # 旧记录留着
        pc["actor_voices"]["man/youth/chinese/门子"] = "v1"
        r = cm.merge_voice_settings(pc, ["man/youth/chinese/门子", "man/youth/chinese/门子乙"], "man/youth/chinese/门子甲")
        self.assertEqual(r["voice"], "v1")
        self.assertFalse(cm.merge_voice_settings({}, ["a/b/c/d"], "a/b/c/e")["changed"])
        self.assertFalse(cm.merge_voice_settings(None, ["a/b/c/d"], "a/b/c/e")["changed"])


PANEL = r'''
import json, os, tempfile, tkinter as tk
from tkinter import messagebox
import project_manager
from gui.dl import story_actor_panel as sap
from PIL import Image
root = tk.Tk()
root.withdraw()
tmp = tempfile.mkdtemp(prefix="_tmp_t281_")
Image.new("RGB", (4, 4), "red").save(os.path.join(tmp, "man_youth_chinese_门子.png"))
Image.new("RGB", (4, 4), "blue").save(os.path.join(tmp, "man_mature_chinese_贾雨村.png"))
project_manager.PROJECT_CONFIG = {"actor_voices": {"man/mature/chinese/贾雨村": "v-jia"}}
saved = []
project_manager.save_project_config = lambda *a, **k: saved.append(1) or True
p = sap.StoryActorPanel(root, text="H woman/mature/chinese/秦 | man/youth/chinese/门子 | man/mature/chinese/贾雨村",
                        person_dir=lambda: tmp)
p._apply_merge([1, 2], "man/youth/chinese/门子甲")
files = sorted(os.listdir(tmp))
with Image.open(os.path.join(tmp, "man_youth_chinese_门子甲.png")) as im:
    color = list(im.convert("RGB").getpixel((0, 0)))
out = {"text": p.get_text(), "files": files, "color": color, "voices": project_manager.PROJECT_CONFIG["actor_voices"],
       "saved": len(saved)}
root.destroy()
import shutil; shutil.rmtree(tmp, ignore_errors=True)
print(json.dumps(out, ensure_ascii=False))
'''

GEN = r'''
import json, os, tempfile, tkinter as tk
from tkinter import messagebox
import config, project_manager
project_manager.PROJECT_CONFIG = None
from gui.dl import story_actor_panel as sap
from utility import portrait_gen
from PIL import Image
root = tk.Tk()
root.withdraw()
ch = tempfile.mkdtemp(prefix="_tmp_t281_")
os.makedirs(os.path.join(ch, "avatar", "realistic"))
Image.new("RGB", (4, 4), "gray").save(os.path.join(ch, "avatar", "realistic", "woman_mature_chinese_甲.png"))
people = tempfile.mkdtemp(prefix="_tmp_t281_")
seen = {}
def fake_generate(body, scenes, dest, *, setting="", style="", ratio="", **kw):
    seen.update(dest=dest, ratio=ratio, style=style, setting=setting)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    Image.new("RGB", (10, 10), "green").save(dest)
    return {"ok": True, "path": dest, "prompt": "p", "source": "strata", "error": ""}
portrait_gen.generate_portrait = fake_generate
messagebox.showwarning = lambda *a, **k: None
ctx = lambda: {"scenes": [{"actor": "man/youth/chinese/门子"}], "setting": "SET", "style": "写实 (Realistic)", "ratio": "1080x1920"}
p = sap.StoryActorPanel(root, text="man/youth/chinese/门子", person_dir=lambda: people, style=lambda: "写实 (Realistic)",
                        channel_path=lambda: ch, portrait_context=ctx)
row = p._rows_from_chips()[0]
lib = p.library_dest(row)
d = sap.ActorEditDialog(p, row, allow_host=False, on_done=lambda r: None)
d._gen_portrait(runner=lambda w, job, done: done(job()))
b = d.browser
shown = b.items[b.pos] if b.items else ""
p2 = sap.StoryActorPanel(root, text="man/youth/chinese/门子", person_dir=lambda: people, style=lambda: "写实 (Realistic)")
out = {"lib": os.path.relpath(lib, ch), "dest": os.path.relpath(seen["dest"], ch), "ratio": seen["ratio"],
       "exists": os.path.isfile(lib), "shown": os.path.normcase(shown) == os.path.normcase(lib),
       "person_unchanged": p.portrait_path(row) == "", "hint": d.hint_var.get(),
       "no_channel": os.path.normcase(p2.library_dest(row)) == os.path.normcase(os.path.join(config.AVATAR_PATH, "Realistic", "man_youth_chinese_门子.png"))}
d.destroy()
root.destroy()
import shutil; shutil.rmtree(ch, ignore_errors=True); shutil.rmtree(people, ignore_errors=True)
print(json.dumps(out, ensure_ascii=False))
'''

WF = r'''
import json
import project_manager
from gui.workflow import wf_actors
class WF:
    scenes = [{"actor": "man/youth/chinese/门子", "video_width": 1080, "video_height": 1920,
               "setting_region": "日本", "setting_era": "江户时代"},
              {"actor": "man/mature/chinese/贾雨村", "visual": "雨村独坐", "setting_era": "唐朝"},
              {"actor": "man/mature/chinese/贾雨村", "setting_region": "日本"}]
    def get_scene_by_index(self, i):
        return self.scenes[i] if 0 <= i < len(self.scenes) else None
o = wf_actors.ActorsMixin.__new__(wf_actors.ActorsMixin)
o.workflow = WF()
o._portrait_style = lambda: "写实 (Realistic)"
project_manager.PROJECT_CONFIG = {"setting_region": "中国", "setting_era": "明朝", "video_width": 1920, "video_height": 1080}
o.current_scene_index = 0
a = o._portrait_gen_context()
o.current_scene_index = 1
b = o._portrait_gen_context()
o.current_scene_index = 2
b2 = o._portrait_gen_context()
project_manager.PROJECT_CONFIG = {}
o.current_scene_index = 5
c = o._portrait_gen_context()
print(json.dumps({"a": [a["setting"], a["ratio"], len(a["scenes"]), a["style"]], "b": [b["setting"], b["ratio"]],
                  "b2": b2["setting"],
                  "c_ratio": c["ratio"]}, ensure_ascii=False))
'''


class PanelAssets(unittest.TestCase):
    def test_merge_moves_portrait_and_voice(self):
        res = _real(PANEL)
        self.assertEqual(res["text"], "H woman/mature/chinese/秦 | man/youth/chinese/门子甲")
        self.assertIn("man_youth_chinese_门子甲.png", res["files"])
        self.assertEqual(res["color"], [255, 0, 0])  # 第一个选中的（门子）的肖像
        self.assertEqual(sum(".bak" in f for f in res["files"]), 2)  # 原来两张都备份，不删
        self.assertEqual(res["voices"]["man/youth/chinese/门子甲"], "v-jia")  # 门子没选过声音 → 用贾雨村的
        self.assertEqual(res["voices"]["man/mature/chinese/贾雨村"], "v-jia")
        self.assertEqual(res["saved"], 1)

    def test_story_generate_saves_to_channel_library(self):
        res = _real(GEN)
        self.assertEqual(res["lib"], os.path.join("avatar", "realistic", "man_youth_chinese_门子.png"))
        self.assertEqual(res["dest"], res["lib"])
        self.assertTrue(res["exists"])
        self.assertTrue(res["shown"])
        self.assertTrue(res["person_unchanged"])
        self.assertEqual(res["ratio"], "1080x1920")
        self.assertIn("频道肖像库", res["hint"])
        self.assertTrue(res["no_channel"])


class Ratio(unittest.TestCase):
    def test_ratio_line(self):
        self.assertIn("9:16 portrait (1080x1920)", pg.ratio_line("1080x1920"))
        self.assertIn("16:9 landscape (1920x1080)", pg.ratio_line((1920, 1080)))
        self.assertIn("9:16 portrait.", pg.ratio_line("9:16"))
        self.assertEqual(pg.ratio_line(""), "")
        self.assertEqual(pg.ratio_line("abc"), "")

    def test_prompt_carries_ratio_and_infers_setting(self):
        from tests.test_t280_setting_portrait import SCENES, FakeLLM

        llm = FakeLLM()
        r = pg.write_portrait_prompt("man/youth/chinese/门子", SCENES, setting="", style="", ratio="1080x1920", llm=llm)
        self.assertIn("9:16 portrait (1080x1920)", llm.calls[0][1])
        self.assertIn("infer a plausible region and era", llm.calls[0][1])
        self.assertIn("9:16 portrait (1080x1920)", r["prompt"])
        r = pg.write_portrait_prompt("man/youth/chinese/门子", SCENES, ratio="1920x1080", llm=FakeLLM(""))
        self.assertEqual(r["source"], "template")
        self.assertIn("16:9 landscape", r["prompt"])

    def test_story_context_has_ratio(self):
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn('"ratio": ratio or video_detail.get("story_video_size") or project_manager.video_size_key()', se)
        self.assertIn('ratio=ctx.get("ratio") or ""', _read("gui", "dl", "story_actor_panel.py"))
        self.assertIn('ratio=ctx.get("ratio") or ""', _read("gui", "workflow", "wf_actors.py"))

    def test_workflow_context_scene_then_project(self):
        res = _real(WF)
        sa, ra, n, st = res["a"]
        self.assertIn("Japan", sa)   # 当前场景的地域 / 时代
        self.assertEqual(ra, "1080x1920")  # 场景的比例
        self.assertEqual(n, 3)
        self.assertEqual(st, "写实 (Realistic)")
        sb, rb = res["b"]
        self.assertIn("China", sb)   # 场景只写了时代（唐朝）→ 地域用项目的
        self.assertIn("Tang", sb)
        self.assertEqual(rb, "1920x1080")  # 场景没写 → 项目的
        self.assertIn("Ming", res["b2"])  # 场景 日本 + 项目 明朝 对不上 → 整对用项目的
        self.assertIn(res["c_ratio"], ("1920x1080", "1080x1920"))  # 都没有 → 上次选的


class SoulSamples(unittest.TestCase):
    def test_samples_new_format(self):
        d = os.path.join(ROOT, "_soul_samples")
        if not os.path.isdir(d):
            self.skipTest("_soul_samples 不在这里（gitignore 的开发样本）")
        old = re.compile(r"(人物\d+|讲员)[：:]\s*(woman|man|girl|boy)/")
        for name in os.listdir(d):
            if name.endswith(".txt"):
                with open(os.path.join(d, name), encoding="utf-8-sig") as f:
                    self.assertIsNone(old.search(f.read()), name)


if __name__ == "__main__":
    unittest.main()
