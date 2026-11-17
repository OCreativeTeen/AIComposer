# -*- coding: utf-8 -*-
"""t272: 连环画没有 Comic to Scenes（叙事方式 = 共用三种）；PDF 来源一页一场；Strata 一页一页看图；Gemini 带 PDF 自动提交；
「动态生成人物」。

纯逻辑在临时目录里用假 Strata / 假 Gemini 测；要真 config / downloader / project_manager 的检查在子进程里跑
（不装桩，只读，不写任何项目 / 列表数据）。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import fitz

from utility import cast_preset as cpr
from utility import pdf_scene_pages as psp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THREE = ["播客", "故事对话", "故事表演"]
HOST = "讲员：woman/mature/chinese/秦"


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _real(code):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-W", "ignore", "-c", "import warnings\nwarnings.filterwarnings('ignore')\n" + code],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-3000:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def make_pdf(path, pages):
    from io import BytesIO

    from PIL import Image

    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        buf = BytesIO()
        Image.new("RGB", (240, 320), (i * 9 % 256, 100, 200 - i)).save(buf, "PNG")
        page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(path)
    doc.close()
    return path


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t272_")
        self.addCleanup(shutil.rmtree, self.tmp, True)


# ------------------------------------------------------------------ 1. 叙事方式
class NoComicToScenes(unittest.TestCase):
    def test_every_channel_with_narration_modes_has_the_same_three(self):
        res = _real(
            'import json, config, config_channel as cc\n'
            'ch = {k: [l for l, _t in (c.get("scenes_prompt_choices") or [])] for k, c in config.CHANNEL_CONFIG.items()}\n'
            'tpl = {k: {l: t for l, t in (c.get("scenes_prompt_choices") or [])} for k, c in config.CHANNEL_CONFIG.items()}\n'
            'legacy = {l: [cc.canonical_prompt_label(l), cc.series_style_key(l), cc.fixed_story_steps(l, {"steps": 3})]\n'
            '          for l in ("Comic to Scenes", "Reshape Episode", "Expand Episode", "Condense · 2 Acts",\n'
            '                    "Condense · 3 Acts", "Condense · 4 Acts", "播客", "故事表演")}\n'
            'print(json.dumps({"ch": ch, "same": tpl["comic"] == tpl["counseling"], "legacy": legacy,\n'
            '                  "default": cc.default_scene_prompt_label(ch["comic"])}, ensure_ascii=False))')
        self.assertEqual(res["ch"]["comic"], THREE)
        self.assertEqual(res["ch"]["counseling"], THREE)
        self.assertTrue(res["same"], "连环画的三种方式用的模板和 counseling 是同一份")
        self.assertEqual(res["default"], "故事对话")
        for labels in res["ch"].values():
            for lab in labels:
                self.assertNotIn("Comic to Scenes", lab)
        for old in ("Comic to Scenes", "Reshape Episode", "Expand Episode", "Condense · 2 Acts", "Condense · 3 Acts",
                    "Condense · 4 Acts"):
            self.assertEqual(res["legacy"][old][:2], ["故事对话", "story_speak"], old)
        self.assertEqual(res["legacy"]["播客"][0], "播客")
        self.assertEqual(res["legacy"]["故事表演"][0], "故事表演")

    def test_comic_channel_builds_the_shared_prompts_and_old_label_still_works(self):
        res = _real(
            'import json, gui.downloader as d\n'
            'f = d.MediaGUIManager.__new__(d.MediaGUIManager)\n'
            'f._channel_config_key = lambda: "comic"\n'
            'f.language = "Chinese"\n'
            'cast = "人物1：man/youth/chinese/阿明 | 人物2：woman/youth/chinese/小美"\n'
            'out = {}\n'
            'for lab in ("播客", "故事对话", "故事表演", "Comic to Scenes"):\n'
            '    out[lab] = d.MediaGUIManager._combined_prompt_text_for_label(\n'
            '        f, {"analyzed_content": "x", "story_actors": "讲员：woman/mature/chinese/秦 | " + cast}, lab)[1]\n'
            'print(json.dumps(out, ensure_ascii=False))')
        for lab in THREE:
            self.assertTrue(res[lab].strip(), lab)
        self.assertEqual(res["Comic to Scenes"], res["故事对话"])  # 旧存值读作故事对话，提示词一模一样
        self.assertNotIn("Picture-story editor", res["故事对话"])

    def test_source_has_no_comic_label_in_config(self):
        self.assertNotIn('("Comic to Scenes"', _read("config.py"))
        self.assertIn('"Comic to Scenes": SERIES_STYLE_LABELS["story_speak"]', _read("config_channel.py"))


# ------------------------------------------------------------------ 2/3. 一页一场 + Strata 一页一页
class PagesToScenes(Tmp):
    def test_render_gives_one_image_per_page(self):
        pdf = make_pdf(os.path.join(self.tmp, "c_p1-15.pdf"), 15)
        paths = psp.render_pages(pdf, os.path.join(self.tmp, "img"))
        self.assertEqual(len(paths), 15)
        self.assertEqual([os.path.basename(p) for p in paths][:3], ["page_001.jpg", "page_002.jpg", "page_003.jpg"])
        self.assertTrue(all(os.path.getsize(p) > 200 for p in paths))
        self.assertEqual(len(psp.page_texts(pdf)), 15)

    def test_parse_one_scene_variants(self):
        sc = {"actor": "", "visual": "雪地", "speaking": ""}
        for raw in (json.dumps([sc]), json.dumps(sc), "```json\n" + json.dumps([sc]) + "\n```",
                    "好的：\n" + json.dumps({"scenes": [sc]}, ensure_ascii=False) + "\n完", "<think>x</think>" + json.dumps([sc])):
            self.assertEqual(psp.parse_one_scene(raw), sc, raw)
        for bad in ("", "没有 JSON", "[]", "[1, 2]"):
            self.assertIsNone(psp.parse_one_scene(bad), bad)

    def _run(self, n, replies, *, cast="", dynamic=False, mode="story_speak", allow_host=False, retries=1):
        images = [f"/fake/page_{i:03d}.jpg" for i in range(1, n + 1)]
        calls = []

        def ask(img, system, user):
            calls.append((img, system, user))
            return replies(len(calls), img)

        def build(k, total, cast_text, scenes):
            return f"SYSTEM[cast={cast_text}]", psp.page_user_text(
                k, total, original_page=10 + k, page_text="", cast_text=cast_text, scenes=scenes)

        res = psp.run_pages(images, ask, build, first_page=11, cast_text=cast, mode=mode, dynamic=dynamic, cap=4,
                            allow_host=allow_host, retries=retries)
        return res, calls

    def test_fifteen_pages_make_fifteen_scenes_in_order(self):
        res, calls = self._run(15, lambda i, img: json.dumps([{"visual": f"画面{i}", "actor": "", "speaking": ""}]))
        self.assertEqual([s["visual"] for s in res["scenes"]], [f"画面{i}" for i in range(1, 16)])
        self.assertEqual([c[0] for c in calls], [f"/fake/page_{i:03d}.jpg" for i in range(1, 16)])  # 一页一次，按页序
        self.assertIn("page 1 of 15 of the selected PDF pages (page 11 of the original file)", calls[0][2])
        self.assertIn("page 15 of 15", calls[14][2])
        self.assertIn("This is the first scene", calls[0][2])
        self.assertIn("This is the last scene", calls[14][2])
        self.assertIn("exactly ONE scene", calls[3][2])
        self.assertIn("scene 3: ", calls[3][2])  # 前面场景的摘要
        self.assertIn("A page with nobody in it is allowed", calls[0][2])

    def test_scene_without_people_is_allowed(self):
        res, _ = self._run(2, lambda i, img: json.dumps([{"visual": "空镜", "actor": "", "speaking": ""}]), dynamic=True)
        self.assertEqual(len(res["scenes"]), 2)
        self.assertEqual(res["cast"], "")
        self.assertEqual(res["scenes"][0]["actor"], "")

    def test_fixed_cast_is_not_touched(self):
        cast = "人物1：woman/mature/chinese/王夫人 | 人物2：man/mature/chinese/贾政"
        replies = lambda i, img: json.dumps([{"visual": "堂屋", "actor": "人物1:woman/youth/chinese/王夫人(哭) | 人物2:man/mature/chinese/贾政", "speaking": "<1>x"}], ensure_ascii=False)
        res, calls = self._run(2, replies, cast=cast, dynamic=False)
        self.assertEqual(res["cast"], cast)
        self.assertIn("woman/youth/chinese/王夫人", res["scenes"][0]["actor"])  # 不动人的写法
        self.assertTrue(all(f"cast={cast}" in c[1] for c in calls))

    def test_dynamic_cast_grows_page_by_page_and_later_pages_get_it(self):
        def replies(i, img):
            people = {1: "人物1:woman/mature/chinese/王夫人(哭)", 2: "人物1:woman/youth/chinese/王夫人 | 人物2:man/mature/chinese/贾政(叹气)",
                      3: "人物1:man/mature/chinese/贾政 | 人物2:girl/kids/chinese/黛玉"}[i]
            return json.dumps([{"visual": f"p{i}", "actor": people, "speaking": ""}], ensure_ascii=False)

        res, calls = self._run(3, replies, dynamic=True)
        self.assertEqual(calls[0][1], "SYSTEM[cast=]")
        self.assertEqual(calls[1][1], "SYSTEM[cast=woman/mature/chinese/王夫人]")  # 第 2 页拿到第 1 页加的人
        self.assertIn(" | man/mature/chinese/贾政]", calls[2][1])  # t280: 新写法
        self.assertEqual(res["cast"], "woman/mature/chinese/王夫人 | man/mature/chinese/贾政 | girl/kids/chinese/黛玉")
        # 名单里已有的人，actor 里写成名单里的 id（名字不变，样子一致）
        self.assertIn("woman/mature/chinese/王夫人", res["scenes"][1]["actor"])
        self.assertNotIn("woman/youth/chinese/王夫人", res["scenes"][1]["actor"])
        self.assertIn("新人物：man/mature/chinese/贾政", " ".join(res["notes"]))

    def test_dynamic_cast_is_capped_at_four_people_without_host(self):
        def replies(i, img):
            actor = f"人物1:man/mature/chinese/甲{i}"
            return json.dumps([{"visual": f"p{i}", "actor": actor, "speaking": ""}], ensure_ascii=False)

        res, _ = self._run(6, replies, dynamic=True, cast="讲员：woman/mature/chinese/秦")
        host, people = cpr.split_cast(res["cast"])
        self.assertEqual(host, "woman/mature/chinese/秦")  # 讲员不算人物
        self.assertEqual(len(people), 4)
        self.assertTrue(any("人物已满 4 个" in n for n in res["notes"]))

    def test_podcast_may_add_a_host_other_modes_may_not(self):
        reply = lambda i, img: json.dumps([{"visual": "x", "actor": "讲员:woman/mature/chinese/李老师 | 人物1:man/youth/chinese/小周", "speaking": ""}], ensure_ascii=False)
        res, _ = self._run(1, reply, dynamic=True, mode="podcast", allow_host=True)
        self.assertEqual(cpr.split_cast(res["cast"]), ("woman/mature/chinese/李老师", ["man/youth/chinese/小周"]))
        res, _ = self._run(1, reply, dynamic=True, mode="story_speak", allow_host=False)
        self.assertEqual(cpr.split_cast(res["cast"]), ("", ["man/youth/chinese/小周"]))

    def test_unparseable_page_is_retried_once_then_names_the_page(self):
        seen = []

        def replies(i, img):
            seen.append(img)
            return "不是 JSON" if img.endswith("page_002.jpg") else json.dumps([{"visual": "ok"}])

        with self.assertRaises(psp.PageSceneError) as cm:
            self._run(3, replies)
        self.assertEqual((cm.exception.page, cm.exception.total), (2, 3))
        self.assertIn("第 2/3 页", str(cm.exception))
        self.assertEqual(seen.count("/fake/page_002.jpg"), 2)  # 重试 1 次
        self.assertNotIn("/fake/page_003.jpg", seen)  # 失败就停，不往下跑

    def test_ask_failure_names_the_page(self):
        def replies(i, img):
            raise ConnectionError("Strata 连不上")

        with self.assertRaises(psp.PageSceneError) as cm:
            self._run(2, replies)
        self.assertIn("第 1/2 页", str(cm.exception))
        self.assertIn("Strata 连不上", str(cm.exception))

    def test_strata_vision_function_reuses_the_existing_strata_vision_calls(self):
        src = _read("utility", "material_image_matcher.py")
        body = src[src.index("def strata_scene_vision"):src.index("def _strata_text")]
        for needle in ("llm_api.LLMApi(llm_api.STRATA)", "api._strata_request(", "_strata_client(", "_image_data_url(", "_clean("):
            self.assertIn(needle, body)
        self.assertNotIn('req["max_tokens"] =', body)  # 一个场景的 JSON 比看图描述长：用 Strata 默认上限


# ------------------------------------------------------------------ 动态人物（纯逻辑）
class DynamicCastLogic(unittest.TestCase):
    def test_flag_is_read_from_row_or_profile(self):
        self.assertFalse(cpr.dynamic_cast_enabled({}))
        self.assertFalse(cpr.dynamic_cast_enabled(None))
        self.assertTrue(cpr.dynamic_cast_enabled({"dynamic_cast": True}))
        self.assertTrue(cpr.dynamic_cast_enabled({"project_profile": {"dynamic_cast": True}}))
        self.assertFalse(cpr.dynamic_cast_enabled({"dynamic_cast": False, "project_profile": {"dynamic_cast": True}}))
        self.assertTrue(cpr.dynamic_cast_enabled({"dynamic_cast": "true"}))
        self.assertFalse(cpr.dynamic_cast_enabled({"dynamic_cast": "0"}))

    def test_merge_keeps_ids_consistent_and_keeps_scene_motion(self):
        cast = "人物1：woman/mature/chinese/王夫人（母亲）"
        new_cast, actor, notes = cpr.merge_scene_people(
            cast, "人物1:woman/youth/chinese/王夫人(哭泣) | 人物2:man/mature/chinese/贾政(叹气)")
        self.assertEqual(new_cast, "woman/mature/chinese/王夫人 | man/mature/chinese/贾政")
        self.assertEqual(actor, "woman/mature/chinese/王夫人(哭泣) | man/mature/chinese/贾政(叹气)")  # t280: 新写法
        self.assertEqual(notes, ["新人物：man/mature/chinese/贾政"])

    def test_nameless_person_is_not_added(self):
        new_cast, _actor, notes = cpr.merge_scene_people("", "人物1:woman/mature/chinese")
        self.assertEqual(new_cast, "")
        self.assertTrue(notes and "没有名字" in notes[0])

    def test_prompt_block_says_cap_consistency_and_empty_scenes(self):
        empty = cpr.dynamic_cast_block("", "story_speak")
        self.assertIn("At most 10 people (人物)", empty)  # t279: 人物栏最多 10 个人物
        self.assertIn("the 讲员 is not counted", empty)
        self.assertIn("same id", empty)
        self.assertIn("A scene may have nobody in it", empty)
        full = cpr.dynamic_cast_block(" | ".join(f"人物{i}：man/youth/chinese/甲{i}" for i in range(1, 11)), "story_act")
        self.assertIn("The list is full: add nobody", full)
        self.assertIn("Do not invent a 讲员", full)
        self.assertIn("introduce one", cpr.dynamic_cast_block("", "podcast"))

    def test_row_with_dynamic_cast_is_not_blocked_and_prompt_has_the_block(self):
        res = _real(
            'import json, gui.dl.prompts_notebooklm as p\n'
            'on = {"dynamic_cast": True, "story_actors": ""}\n'
            'off = {"story_actors": ""}\n'
            'ctx = p._notebooklm_prompt_context_from_video_detail(type("M", (), {"language": "Chinese"})(), on)\n'
            'ctx_off = p._notebooklm_prompt_context_from_video_detail(type("M", (), {"language": "Chinese"})(), off)\n'
            'five = "讲员：woman/mature/chinese/秦 | " + " | ".join("人物%d：man/youth/chinese/n%d" % (i, i) for i in range(1, 5))\n'
            'print(json.dumps({"on": [p.scene_cast_check(on, l)[0] for l in ("播客", "故事对话", "故事表演")],\n'
            '                  "off": [p.scene_cast_check(off, l)[0] for l in ("播客", "故事对话", "故事表演")],\n'
            '                  "program_check_ignores_flag": p.scene_cast_check(on, "故事对话", honor_dynamic=False)[0],\n'
            '                  "ctx_on": ctx["cast"], "ctx_off": ctx_off["cast"],\n'
            '                  "block5": p.build_cast_block(five, 5), "block4": p.build_cast_block(five, 4)}, ensure_ascii=False))')
        self.assertEqual(res["on"], [True, True, True])
        self.assertEqual(res["off"], [False, False, False])
        self.assertFalse(res["program_check_ignores_flag"])
        self.assertIn("DYNAMIC CAST", res["ctx_on"])
        self.assertIn("Cast list: EMPTY", res["ctx_on"])
        self.assertNotIn("DYNAMIC CAST", res["ctx_off"])
        self.assertIn("  - man/youth/chinese/n4", res["block5"])  # 讲员 + 4 个人物都在
        self.assertNotIn("  - man/youth/chinese/n4", res["block4"])  # 只给一场的上限（含讲员 4 个）时

    def test_cast_list_cap_is_four_people_plus_host_only_when_asked(self):
        res = _real(
            'import json, project_manager as pm\n'
            'text = "讲员：woman/mature/chinese/秦 | " + " | ".join("人物%d：man/youth/chinese/n%d" % (i, i) for i in range(1, 13))\n'
            'print(json.dumps({"d_norm": pm.normalize_actor_text(text), "d_ent": len(pm.actor_entries(text)),\n'
            '                  "dyn_norm": pm.normalize_actor_text(text, pm.CAST_MAX_PRESENT_DYNAMIC),\n'
            '                  "dyn_ent": len(pm.actor_entries(text, pm.CAST_MAX_PRESENT_DYNAMIC)),\n'
            '                  "const": [pm.ACTOR_MAX_PRESENT, pm.CAST_MAX_PRESENT_DYNAMIC]}, ensure_ascii=False))')
        self.assertEqual(res["const"], [4, 11])  # t279: 一场 4 个；人物栏 10 个人物 + 1 个讲员
        self.assertEqual(res["d_ent"], 4)  # 一场 / 旧人物栏：含讲员最多 4
        self.assertEqual(res["dyn_ent"], 11)  # 人物栏：讲员 + 10 个人物
        self.assertEqual(len([s for s in res["dyn_norm"].split(" | ") if s and not s.startswith("H ")]), 10)  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertTrue(res["dyn_norm"].startswith("H "))


# ------------------------------------------------------------------ 3/5. 真的走一遍 downloader（假 Strata / 假 Gemini）
_FAKE_SELF = (
    'import json, os, sys, tempfile, shutil, fitz\n'
    'from io import BytesIO\n'
    'from PIL import Image\n'
    'import gui.downloader as d\n'
    'os.environ.setdefault("AICOMPOSER_CAST_CONSOLIDATE", "local")\n'  # t278: 归拢人物不调真 Strata（本地合并）
    'tmp = tempfile.mkdtemp(prefix="t272_dl_")\n'
    'def mk(n):\n'
    '    doc = fitz.open()\n'
    '    for i in range(n):\n'
    '        p = doc.new_page(width=300, height=400)\n'
    '        b = BytesIO(); Image.new("RGB", (240, 320), (i * 20, 90, 180)).save(b, "PNG")\n'
    '        p.insert_image(p.rect, stream=b.getvalue())\n'
    '    path = os.path.join(tmp, "红楼梦_p5-%d.pdf" % (4 + n)); doc.save(path); doc.close(); return path\n'
    'f = d.MediaGUIManager.__new__(d.MediaGUIManager)\n'
    'f._channel_config_key = lambda: "comic"\n'
    'f.language = "Chinese"\n'
    'G = d.MediaGUIManager._generate_scene_content_from_notebooklm_prompt\n'
)


class DownloaderFlows(unittest.TestCase):
    def test_strata_pdf_goes_page_by_page_with_cumulative_cast(self):
        res = _real(_FAKE_SELF + r'''
pdf = mk(3)
calls = []
people = {1: "人物1:woman/mature/chinese/王夫人(哭)", 2: "人物1:woman/youth/chinese/王夫人 | 人物2:man/mature/chinese/贾政(叹气)", 3: ""}
def ask(img, system, user):
    k = len(calls) + 1
    calls.append({"img": os.path.basename(img), "system": system, "user": user, "exists": os.path.isfile(img)})
    sp = "<1>你好。" if k == 1 else ""
    return json.dumps([{"visual": "第%d页画面" % k, "actor": people[k], "speaking": sp}], ensure_ascii=False)
vd = {"analyzed_content": "x", "dynamic_cast": True, "story_actors": "", "project_profile": {"story_actors": ""}}
scenes = G(f, vd, "故事对话", instruction="我的说明", attachment=pdf, text_backend="strata", prompt_params={"steps": 4, "episodes": 3},
           pdf_user_instruction="我的说明", pdf_first_page=5, strata_ask=ask)
left = [x for x in os.listdir(tempfile.gettempdir()) if x.startswith("t272_pages_")]
print(json.dumps({"n": len(scenes), "visual": [s["visual"] for s in scenes], "actor": [s.get("actor", "") for s in scenes],
                  "imgs": [c["img"] for c in calls], "exists": [c["exists"] for c in calls],
                  "sys2": calls[1]["system"], "sys1": calls[0]["system"], "user2": calls[1]["user"], "user1": calls[0]["user"],
                  "cast": vd["story_actors"], "prof": vd["project_profile"]["story_actors"], "left": left}, ensure_ascii=False))
shutil.rmtree(tmp, True)
''')
        self.assertEqual(res["n"], 3)
        self.assertEqual(res["visual"], ["第1页画面", "第2页画面", "第3页画面"])  # 3 页 = 3 场，按页序
        self.assertEqual(res["imgs"], ["page_001.jpg", "page_002.jpg", "page_003.jpg"])
        self.assertTrue(all(res["exists"]))
        self.assertEqual(res["left"], [], "渲染出来的页图用完就删")
        self.assertIn("page 2 of 3", res["user2"])
        self.assertIn("page 6 of the original file", res["user2"])  # 范围从原文件第 5 页开始
        self.assertIn("我的说明", res["sys2"])  # 用户自己写的说明在
        self.assertNotIn("The PDF has", res["sys2"])  # 整份 PDF 的「共 n 页 n 场」那句不进每一页
        self.assertIn("Cast list: none fixed in advance", res["sys1"])  # 第 1 页：名单还是空的（t276: 原来的人物栏不发）
        # t278: 每页自己找人：第 2 页拿不到第 1 页的人（没有累计名单），全部页跑完才归拢
        self.assertNotIn("王夫人", res["sys2"])
        self.assertNotIn("王夫人", res["user2"])
        self.assertIn("PEOPLE ON THIS PAGE ONLY", res["user2"])
        self.assertIn("DYNAMIC CAST", res["sys2"])
        self.assertEqual(res["actor"][2], "")  # 没有人的一页也是一场
        self.assertEqual(res["cast"], "woman/mature/chinese/王夫人 | man/mature/chinese/贾政")
        self.assertEqual(res["prof"], res["cast"])  # project_profile 里的那份一起更新

    def test_strata_pdf_with_fixed_cast_blocks_when_cast_is_short_and_runs_when_enough(self):
        res = _real(_FAKE_SELF + r'''
pdf = mk(2)
def ask(img, system, user):
    return json.dumps([{"visual": "v", "actor": "人物1:man/youth/chinese/阿明 | 人物2:woman/youth/chinese/小美", "speaking": "<1>好"}], ensure_ascii=False)
out = {}
try:
    G(f, {"analyzed_content": "x", "story_actors": "人物1：man/youth/chinese/阿明"}, "故事对话", attachment=pdf, text_backend="strata", strata_ask=ask)
    out["short"] = "NOT BLOCKED"
except ValueError as e:
    out["short"] = str(e)
cast = "人物1：man/youth/chinese/阿明 | 人物2：woman/youth/chinese/小美"
vd = {"analyzed_content": "x", "story_actors": cast}
sc = G(f, vd, "故事表演", attachment=pdf, text_backend="strata", strata_ask=ask)
out["n"] = len(sc); out["cast"] = vd["story_actors"]
shutil.rmtree(tmp, True)
print(json.dumps(out, ensure_ascii=False))
''')
        self.assertIn("「人物设置」", res["short"])  # 没勾动态：人物不够照旧拦
        self.assertEqual(res["n"], 2)
        self.assertEqual(res["cast"], "人物1：man/youth/chinese/阿明 | 人物2：woman/youth/chinese/小美")  # 固定名单不动

    def test_strata_page_failure_stops_and_names_the_page_audio_and_deepseek_still_blocked(self):
        res = _real(_FAKE_SELF + r'''
pdf = mk(3)
def ask(img, system, user):
    if img.endswith("page_002.jpg"):
        return "胡说"
    return json.dumps([{"visual": "v"}])
vd = {"analyzed_content": "x", "dynamic_cast": True}
out = {}
try:
    G(f, vd, "故事对话", attachment=pdf, text_backend="strata", strata_ask=ask)
except RuntimeError as e:
    out["fail"] = str(e)
out["cast_untouched"] = "story_actors" not in vd
for backend, att in (("deepseek", pdf), ("strata", os.path.join(tmp, "a.mp3"))):
    open(os.path.join(tmp, "a.mp3"), "wb").write(b"ID3")
    try:
        G(f, {"analyzed_content": "x", "dynamic_cast": True}, "故事对话", attachment=att, text_backend=backend)
        out[backend] = "NOT BLOCKED"
    except RuntimeError as e:
        out[backend] = str(e)
shutil.rmtree(tmp, True)
print(json.dumps(out, ensure_ascii=False))
''')
        self.assertIn("第 2/3 页", res["fail"])
        self.assertTrue(res["cast_untouched"])
        self.assertIn("DeepSeek 不支持", res["deepseek"])
        self.assertIn("Strata 不支持", res["strata"])

    def test_gemini_gets_the_ranged_pdf_and_dynamic_cast_is_merged_after(self):
        res = _real(_FAKE_SELF + r'''
pdf = mk(3)
seen = {}
def gen(prompt, sys_, expect_list=True, attachment=None, extra=None):
    seen.update({"attachment": attachment, "extra": extra, "prompt": prompt})
    return [{"visual": "a", "actor": "人物1:woman/mature/chinese/王夫人(哭)", "speaking": ""},
            {"visual": "b", "actor": "人物1:woman/youth/chinese/王夫人 | 人物2:man/mature/chinese/贾政", "speaking": ""},
            {"visual": "c", "actor": "", "speaking": ""}]
f.llm_api_manual = type("M", (), {"generate_json": staticmethod(gen)})()
vd = {"analyzed_content": "x", "dynamic_cast": True, "story_actors": ""}
sc = G(f, vd, "故事对话", instruction="共 3 页", attachment=pdf, text_backend="gemini")
shutil.rmtree(tmp, True)
print(json.dumps({"n": len(sc), "att": os.path.basename(seen["attachment"]), "extra": seen["extra"], "cast": vd["story_actors"],
                  "a2": sc[1]["actor"], "prompt_dyn": "DYNAMIC CAST" in seen["prompt"]}, ensure_ascii=False))
''')
        self.assertEqual(res["n"], 3)
        self.assertEqual(res["att"], "红楼梦_p5-7.pdf")  # 整份选中页的 PDF 发给 Gemini
        self.assertEqual(res["extra"], {"text_backend": "gemini"})
        self.assertTrue(res["prompt_dyn"])
        self.assertEqual(res["cast"], "woman/mature/chinese/王夫人 | man/mature/chinese/贾政")
        self.assertIn("woman/mature/chinese/王夫人", res["a2"])

    def test_pdf_instruction_says_one_scene_per_page_in_order(self):
        res = _real(
            'import json, gui.dl.prompts_notebooklm as p\n'
            'print(json.dumps({l: p._pdf_scene_generation_instruction(l, 15, "ai") for l in ("播客", "故事对话", "故事表演")}))')
        for lab, text in res.items():
            self.assertIn("exactly 15 scenes", text, lab)
            self.assertIn("One scene per page, in page order", text, lab)
            self.assertIn("an empty actor is allowed", text, lab)
            self.assertIn("narration mode rules", text, lab)


# ------------------------------------------------------------------ 4. Gemini 为什么不提交 / 现在怎么提交
class GeminiPdfSubmit(unittest.TestCase):
    def test_which_file_attachments_may_run_automatically(self):
        res = _real(
            'import json\n'
            'from utility import llm_api as L\n'
            'f = L.cli_auto_allows_file\n'
            'print(json.dumps({"none": f("", "grok", "text"), "pdf_gemini": f("pdf", "gemini", "file"), "pdf_grok": f("pdf", "grok", "file"),\n'
            '                  "pdf_none": f("pdf", "", "file"), "audio_gemini": f("audio", "gemini", "file"),\n'
            '                  "video_gemini": f("video", "gemini", "file")}))')
        self.assertTrue(res["none"])
        self.assertTrue(res["pdf_gemini"])  # 选了 Gemini + PDF：自动提交
        self.assertFalse(res["pdf_grok"])  # Grok 网页没有文件上传：仍手动
        self.assertFalse(res["pdf_none"])
        self.assertFalse(res["audio_gemini"])
        self.assertFalse(res["video_gemini"])

    def test_dialog_uses_it_for_button_auto_start_and_text_branch(self):
        src = _read("utility", "llm_api.py")
        self.assertIn("return cli_auto_allows_file(file_kind,", src)
        self.assertIn("if not _auto_files_ok(text_backend_override):", src)
        self.assertIn("or not _auto_files_ok():", src)
        self.assertIn("if auto_var.get() and _auto_files_ok():", src)
        self.assertIn("gemini_cdp.ask_text_with_file(prompt, attachment, status=_cli_set_status)", src)
        self.assertNotIn("or cli_busy[0] or file_kind:", src)  # 旧的「有文件一律不自动」
        self.assertNotIn("if auto_var.get() and not file_kind:", src)

    def test_gemini_cdp_sends_the_file_with_the_prompt(self):
        res = _real(
            'import json, os, tempfile\n'
            'from utility import gemini_cdp as g\n'
            'sent = {}\n'
            'class S:\n'
            '    def __init__(self, status=None, model=None): pass\n'
            '    def __enter__(self): return self\n'
            '    def __exit__(self, *a): return False\n'
            '    def send_text(self, prompt, images=None, timeout_s=0):\n'
            '        sent.update({"prompt": prompt, "images": images, "timeout": timeout_s}); return "[{}]"\n'
            'g.GeminiSession = S\n'
            'g.gemini_model = lambda: "x"\n'
            'p = os.path.join(tempfile.gettempdir(), "t272_x.pdf"); open(p, "wb").write(b"%PDF-1.4")\n'
            'out = {"reply": g.ask_text_with_file("  提示词  ", p, timeout_s=5)}\n'
            'os.remove(p)\n'
            'out.update(sent=sent["prompt"], images=[os.path.basename(x) for x in sent["images"]], timeout=sent["timeout"])\n'
            'errs = []\n'
            'for args in (("", p), ("x", p + ".missing")):\n'
            '    try:\n'
            '        g.ask_text_with_file(*args); errs.append("NO ERROR")\n'
            '    except RuntimeError as e:\n'
            '        errs.append(str(e))\n'
            'out["errs"] = errs\n'
            'print(json.dumps(out, ensure_ascii=False))')
        self.assertEqual(res["reply"], "[{}]")
        self.assertEqual(res["sent"], "提示词")
        self.assertEqual(res["images"], ["t272_x.pdf"])
        self.assertEqual(res["timeout"], 5)
        self.assertEqual(res["errs"][0], "提示词是空的")
        self.assertIn("文件不存在", res["errs"][1])

    def test_upload_status_names_pdf_files(self):
        self.assertIn("上传 PDF（", _read("utility", "gemini_cdp.py"))


# ------------------------------------------------------------------ 界面（源码 + 登记顺序）
class SceneWindowWiring(unittest.TestCase):
    def setUp(self):
        self.se = _read("gui", "dl", "scene_editor.py")

    def test_checkbox_label_persistence_and_order(self):
        self.assertEqual(cpr.DYNAMIC_CAST_LABEL, "动态生成人物")
        self.assertIn("text=_cast_dynmod.DYNAMIC_CAST_LABEL", self.se)
        self.assertIn("video_detail[_cast_dynmod.DYNAMIC_CAST_KEY] = on", self.se)
        self.assertIn("pp[_cast_dynmod.DYNAMIC_CAST_KEY] = on", self.se)  # 和 project_profile 一起存（每一条各存各的）
        self.assertIn("persist(video_detail, parent=dlg)", self.se[self.se.index("def _on_dynamic_cast_toggle"):])
        # t274: 勾选框在第 3 行（人物栏右边），不在生成按钮这一行了；显示规则不变（只在三种叙事方式下）
        self.assertIn('(cast_btn, "cast"), (smart_btn, "smart")', self.se)
        self.assertNotIn('(dynamic_cast_chk, "dynamic")', self.se)
        sync = self.se[self.se.index("def _sync_dynamic_prompt_widgets"):self.se.index("prompt_combo_var.trace_add")]
        self.assertIn('_dyn_sync(bool(_cast_dyn.mode_for_label(sel)))', sync)

    def test_cast_check_skipped_when_dynamic(self):
        self.assertIn("if _cast_mode and not _cast_preset.dynamic_cast_enabled(video_detail):", self.se)
        self.assertIn("max_present=project_manager.CAST_MAX_PRESENT", self.se)  # t279: 勾不勾都是 10 个人物 + 1 个讲员

    def test_backend_dialog_unlocks_strata_for_pdf_only(self):
        self.assertIn('text_only = ("deepseek",) if pdf_source else ("deepseek", "strata")', self.se)
        self.assertIn("素材是 PDF：DeepSeek 不支持；Strata 一页一页看图，一页一个场景", self.se)
        self.assertIn("素材是音频 / 视频，DeepSeek / Strata 不支持", self.se)
        self.assertNotIn("素材是 PDF/音视频，DeepSeek / Strata 不支持", self.se)
        self.assertIn('pdf_source=self.llm_api.__class__._attachment_kind(attachment or "") == "pdf"', self.se)
        self.assertIn("pdf_user_instruction=_pdf_raw_instr", self.se)

    def test_downloader_routes_strata_pdf_to_the_page_loop(self):
        dl = _read("gui", "downloader.py")
        self.assertIn("scene_cast_check(video_detail, prompt_label)", dl)  # t263 的入口检查还在
        self.assertIn("return self._generate_pdf_scenes_per_page_strata(", dl)
        self.assertIn("ask = _mim.strata_scene_vision", dl)

    def test_legacy_deepseek_text_path_unchanged(self):
        dl = _read("gui", "downloader.py")
        self.assertIn('raise RuntimeError(f"素材是 PDF/音视频，{who} 不支持（只收文字），请选 Grok 或 Gemini。")', dl)


if __name__ == "__main__":
    unittest.main()
