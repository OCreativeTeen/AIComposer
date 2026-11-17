# -*- coding: utf-8 -*-
"""t276: 勾了「动态生成人物」时，场景生成完全不用原来的人物栏（所有人物 + 讲员）：
不发给模型（Grok / Gemini / 手动复制 / 文字模式 / Strata 一页一页），人物全部从内容里找、用故事里的真名；
生成完人物栏整个换成找出来的人，场景 actor 跟着改。没勾 = 照旧（固定名单、「人物设置」门槛）。

假 Grok / Gemini / Strata，子进程里跑真 downloader，只读，不碰项目 / 列表数据。"""
import json
import os
import subprocess
import sys
import unittest

from tests.test_t272_pdf_scenes_cast import _FAKE_SELF
from utility import cast_preset as cp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _real(code, timeout=180):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-W", "ignore", "-c", "import warnings\nwarnings.filterwarnings('ignore')\n" + code],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-3000:])
    return json.loads(proc.stdout.strip().splitlines()[-1]), proc.stdout


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


OLD = "讲员：woman/mature/chinese/小美 | 人物1：woman/senior/chinese/林冲 | 人物2：man/mature/chinese/朱富"
OLD_NAMES = ("林冲", "朱富", "小美")

_SETUP = _FAKE_SELF + r'''
OLD = %r
seen = []
REPLY = [
    {"visual": "公堂", "actor": "人物1：man/mature/chinese/贾雨村（升堂） | 人物2：man/youth/chinese/门子（使眼色）", "speaking": "<1>带人犯。"},
    {"visual": "后堂", "actor": "人物2：man/youth/chinese/门子（低声） | 人物1：man/mature/chinese/贾雨村", "speaking": "<1>老爷可记得我？"},
    {"visual": "街上", "actor": "人物3：man/youth/chinese/冯渊（倒地）", "speaking": ""},
]
def gen(prompt, sys_, expect_list=True, attachment=None, extra=None):
    seen.append({"prompt": prompt, "attachment": attachment})
    return json.loads(json.dumps(REPLY))
f.llm_api_manual = type("M", (), {"generate_json": staticmethod(gen)})()
def row(dynamic=True, cast=OLD):
    return {"analyzed_content": "葫芦案的故事", "dynamic_cast": dynamic, "story_actors": cast, "narrator": "小美",
            "project_profile": {"story_actors": cast, "narrator": "小美"}}
''' % OLD


class FreshCastHelpers(unittest.TestCase):
    def test_fresh_view_drops_every_old_person_without_touching_the_row(self):
        vd = {"story_actors": OLD, "narrator": "小美", "project_profile": {"story_actors": OLD, "narrator": "小美"}}
        v = cp.fresh_cast_view(vd)
        self.assertEqual(v["story_actors"], "")
        self.assertEqual(v["project_profile"]["story_actors"], "")
        self.assertNotIn("narrator", v)
        self.assertNotIn("narrator", v["project_profile"])
        self.assertTrue(cp.is_fresh_view(v))
        self.assertEqual(vd["story_actors"], OLD)  # 原来那一条不动
        self.assertEqual(vd["project_profile"]["story_actors"], OLD)
        self.assertFalse(cp.is_fresh_view(vd))

    def test_dynamic_block_fresh_wording(self):
        b = cp.dynamic_cast_block("", "story_speak", fresh=True)
        self.assertIn("IGNORE ANY EARLIER CAST", b)
        self.assertIn("Name each person by their real name in this story", b)
        self.assertIn("never reuse a name from an earlier cast list", b)
        self.assertIn("Never use a placeholder", b)
        # t278: 四段都要写全（项目词表），每场自己找人，不再有「前面页找到的人照抄」
        self.assertIn("All four parts are required for every person in every scene", b)
        self.assertIn("FIND THE PEOPLE OF EACH SCENE ON ITS OWN", b)
        self.assertNotIn("IGNORE ANY EARLIER CAST", cp.dynamic_cast_block("", "story_speak"))  # 不是 fresh：t272 原样
        b2 = cp.dynamic_cast_block("人物1：man/mature/chinese/贾雨村", "story_speak", fresh=True)
        self.assertNotIn("found by you on the earlier pages of this same material", b2)


class WholeBatchBackends(unittest.TestCase):
    def test_grok_gemini_pdf_and_text_mode_get_no_old_cast_and_cast_is_replaced(self):
        res, out = _real(_SETUP + r'''
pdf = mk(3)
res = {}
for name, kw in (("grok_text", dict(text_backend="grok")),
                 ("gemini_pdf_page", dict(text_backend="gemini", attachment=pdf)),
                 ("grok_pdf_textmode", dict(text_backend="grok", content_override="第一页的字。\n\n第二页的字。"))):
    vd = row()
    sc = G(f, vd, "故事对话", prompt_params={"steps": 0, "episodes": 1}, **kw)
    res[name] = {"prompt": seen[-1]["prompt"], "cast": vd["story_actors"], "prof": vd["project_profile"]["story_actors"],
                 "actors": [s.get("actor", "") for s in sc]}
shutil.rmtree(tmp, True)
print(json.dumps(res, ensure_ascii=False))
''')
        want = "man/mature/chinese/贾雨村 | man/youth/chinese/门子 | man/youth/chinese/冯渊"  # t280: 新写法（讲员 H …，人物不带 人物N：）
        for name, r in res.items():
            for old in OLD_NAMES:
                self.assertNotIn(old, r["prompt"], name)  # 原来的人物（含讲员）一个字都不发
            self.assertIn("IGNORE ANY EARLIER CAST", r["prompt"], name)
            self.assertIn("Cast list: none fixed in advance", r["prompt"], name)
            self.assertEqual(r["cast"], want, name)  # 人物栏整个换掉（讲员也没了）
            self.assertEqual(r["prof"], want, name)
            self.assertEqual(r["actors"][0], "man/mature/chinese/贾雨村（升堂） | man/youth/chinese/门子（使眼色）")  # t280: 新写法
            self.assertEqual(r["actors"][1], "man/youth/chinese/门子（低声） | man/mature/chinese/贾雨村")
        self.assertIn("人物栏已整个换成内容里的人物", out)
        self.assertIn("原来的人物栏不要了", out)
        self.assertIn("肖像 / 声音文件还在", out)

    def test_cap_four_people_and_podcast_may_get_a_new_host(self):
        res, _ = _real(_SETUP + r'''
REPLY[:] = [{"visual": "v", "actor": "讲员：woman/mature/chinese/主持阿兰 | " + " | ".join(
    "人物%d：man/youth/chinese/甲%d" % (i, i) for i in range(1, 13)), "speaking": "<1>大家好"}]
vd = row()
G(f, vd, "播客", prompt_params={"steps": 0, "episodes": 1}, text_backend="grok")
pod = vd["story_actors"]
vd2 = row()
G(f, vd2, "故事对话", prompt_params={"steps": 0, "episodes": 1}, text_backend="grok")
print(json.dumps({"pod": pod, "speak": vd2["story_actors"], "pod_prompt_old": any(o in seen[0]["prompt"] for o in ("林冲", "朱富", "小美"))}, ensure_ascii=False))
''')
        self.assertTrue(res["pod"].startswith("H woman/mature/chinese/主持阿兰 | "))  # 播客：模式需要讲员，可以由内容里来
        self.assertEqual(len([s for s in res["pod"].split(" | ") if s and not s.startswith("H ")]), 10)  # t279: 最多 10 个人物
        self.assertFalse(res["speak"].startswith(("讲员", "H ")))  # 故事对话不加讲员
        self.assertEqual(len([s for s in res["speak"].split(" | ") if s and not s.startswith("H ")]), 10)
        self.assertFalse(res["pod_prompt_old"])

    def test_dynamic_off_keeps_the_fixed_cast(self):
        res, _ = _real(_SETUP + r'''
vd = row(dynamic=False)
G(f, vd, "故事对话", prompt_params={"steps": 0, "episodes": 1}, text_backend="grok")
blocked = ""
try:
    G(f, row(dynamic=False, cast="人物1：man/youth/chinese/阿明"), "故事对话", text_backend="grok")
except ValueError as e:
    blocked = str(e)
print(json.dumps({"has_old": "林冲" in seen[0]["prompt"], "cast": vd["story_actors"], "fresh": "IGNORE ANY EARLIER CAST" in seen[0]["prompt"],
                  "blocked": blocked}, ensure_ascii=False))
''')
        self.assertTrue(res["has_old"])
        self.assertFalse(res["fresh"])
        self.assertEqual(res["cast"], OLD)  # 没勾：人物栏不动
        self.assertIn("人物设置", res["blocked"])  # 人物不够照旧拦


class StrataPerPage(unittest.TestCase):
    def test_cumulative_cast_starts_empty_and_replaces_the_old_one(self):
        res, out = _real(_SETUP + r'''
pdf = mk(3)
calls = []
pages = {1: "人物1:man/mature/chinese/贾雨村(升堂)", 2: "人物1:man/mature/chinese/贾雨村 | 人物2:man/youth/chinese/门子(低声)", 3: ""}
def ask(img, system, user):
    k = len(calls) + 1
    calls.append(system + "\n" + user)
    return json.dumps([{"visual": "p%d" % k, "actor": pages[k], "speaking": ""}], ensure_ascii=False)
vd = row()
sc = G(f, vd, "故事对话", attachment=pdf, text_backend="strata", strata_ask=ask)
shutil.rmtree(tmp, True)
print(json.dumps({"old_in": [any(o in c for o in ("林冲", "朱富", "小美")) for c in calls], "fresh": ["IGNORE ANY EARLIER CAST" in c for c in calls],
                  "jia_on_p2": "升堂" in calls[1] or "People so far" in calls[1], "cast": vd["story_actors"], "n": len(sc)}, ensure_ascii=False))
''')
        self.assertEqual(res["old_in"], [False, False, False])
        self.assertEqual(res["fresh"], [True, True, True])
        self.assertFalse(res["jia_on_p2"])  # t278: 每页自己找人，第 2 页拿不到第 1 页的人（全部页跑完才归拢）
        self.assertEqual(res["cast"], "man/mature/chinese/贾雨村 | man/youth/chinese/门子")  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertEqual(res["n"], 3)
        self.assertIn("人物栏已整个换成内容里的人物", out)


class ManualCopyAndWiring(unittest.TestCase):
    def test_manual_copy_prompt_has_no_old_cast(self):
        res, _ = _real(_SETUP + r'''
vd = row()
_, p = f._combined_prompt_text_for_label(vd, "故事对话", prompt_params={"steps": 0, "episodes": 1})
_, p_off = f._combined_prompt_text_for_label(row(dynamic=False), "故事对话", prompt_params={"steps": 0, "episodes": 1})
print(json.dumps({"old": any(o in p for o in ("林冲", "朱富", "小美")), "fresh": "IGNORE ANY EARLIER CAST" in p,
                  "off_old": "林冲" in p_off, "row_untouched": vd["story_actors"] == OLD}, ensure_ascii=False))
''')
        self.assertEqual(res, {"old": False, "fresh": True, "off_old": True, "row_untouched": True})

    def test_editor_shows_the_replaced_cast_after_generation(self):
        se = _read("gui", "dl", "scene_editor.py")
        body = se[se.index("def _on_smart_saved"):se.index("def _ask_scene_text_backend")]
        self.assertIn("_panel_now.set_text(_new_cast, notify=False)", body)
        self.assertLess(body.index("_panel_now.set_text(_new_cast"), body.index('sync_cast = scene_ui.get("sync_cast_from_scenes")'))


if __name__ == "__main__":
    unittest.main()