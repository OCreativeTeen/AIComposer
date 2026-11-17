# -*- coding: utf-8 -*-
"""t278: 「动态生成人物」——每一场（每一页）自己找人；全部场景生成完一次 Strata 归拢（同一个人并成一个、
改正性别 / 年龄段 / 民族、最多 4 个人物 + 只有播客才有讲员、每场「原来那一项 → 最终的谁」）；
每场 actor 换成最终人物（可带这一场的括号），<N> / <Ns> 跟着改号；人物栏 = 最终名单，不带括号；
Strata 不行重试 1 次，再不行本地按名字合并。没勾 = 照旧。全部用假的 Strata，不碰项目 / 列表数据。"""
import json
import unittest

from tests.test_t272_pdf_scenes_cast import _FAKE_SELF, _read, _real
from utility import cast_consolidate as cc
from utility import cast_preset as cp
from utility import pdf_scene_pages as psp

SCENES = [
    {"caption": "公堂", "visual": "贾雨村升堂，门子在旁", "actor": "人物1：man/mature/chinese/贾雨村（升堂） | 人物2：man/youth/chinese/门子（使眼色）",
     "speaking": "<1>带人犯。<2>老爷且慢。"},
    {"caption": "后堂", "visual": "门子低声，甄家女儿的画像", "actor":
        "人物1：頁面內容：门子在后堂，说起英莲。 | 人物2：man/mature/chinese/应天府门子（低声） | 人物3：woman/mature/chinese/甄士隐之女",
     "speaking": "<2>老爷可记得我？"},
    {"caption": "回忆", "visual": "贾雨村和门子，门子又自称应天府门子", "actor":
        "人物1：man/mature/chinese/贾雨村 | 人物2：man/youth/chinese/门子 | 人物3：man/youth/chinese/应天府门子（扶着）",
     "speaking": "<3s>这事难办。<1>你说。<2>是。"},
    {"caption": "街上", "visual": "小女孩", "actor": "人物1：英莲", "speaking": ""},
]

REPLY = {
    "cast": [
        {"key": "P1", "gender": "man", "age": "mature", "ethnicity": "chinese", "name": "贾雨村"},
        {"key": "P2", "gender": "man", "age": "youth", "ethnicity": "chinese", "name": "门子"},
        {"key": "P3", "gender": "woman", "age": "kids", "ethnicity": "chinese", "name": "英莲（甄士隐之女）"},
    ],
    "host": None,
    "scenes": [
        {"scene": 1, "map": {"s1p1": "P1", "s1p2": "P2"}},
        {"scene": 2, "map": {"s2p1": "", "s2p2": "P2", "s2p3": "P3"}},
        {"scene": 3, "map": {"s3p1": "P1", "s3p2": "P2", "s3p3": "P2"}},
        {"scene": 4, "map": {"s4p1": "P3"}},
    ],
}


def _copy():
    return json.loads(json.dumps(SCENES, ensure_ascii=False))


class Vocab(unittest.TestCase):
    def test_project_vocab_is_used(self):
        self.assertEqual(cc.GENDERS, ("man", "woman"))
        self.assertEqual(cc.AGES, ("kids", "teenager", "youth", "mature", "senior"))
        self.assertEqual(cc.ETHNICITIES, ("chinese", "english"))

    def test_parse_person_normalizes_aliases_but_never_guesses(self):
        p = cc.parse_person("girl/kids/chinese/英莲（抱着）（哭）")
        self.assertEqual((p["gender"], p["age"], p["eth"], p["name"], p["note"]), ("woman", "kids", "chinese", "英莲", "抱着，哭"))
        self.assertEqual(p["missing"], [])
        q = cc.parse_person("门子")
        self.assertEqual((q["gender"], q["age"], q["eth"], q["name"]), ("", "", "", "门子"))  # 不自己补
        self.assertEqual(q["missing"], ["gender", "age", "eth"])
        self.assertTrue(cc.parse_person("頁面內容：甄士隱逗女兒，見賈雨村來。")["garbage"])
        u = cc.parse_person("man/youth/chinese/門子（旁白視角，此處由畫面")  # 没收尾的长括号：不是名字
        self.assertEqual((u["name"], u["note"]), ("門子", "旁白視角，此處由畫面"))

    def test_clean_body_and_cast_text_drop_every_bracket(self):
        self.assertEqual(cc.clean_body("woman/kids/chinese/英莲（抱着）（哭）"), "woman/kids/chinese/英莲")
        self.assertEqual(cc.clean_cast_text("讲员：woman/mature/chinese/秦（微笑） | 人物1：man/mature/chinese/贾雨村（升堂）"),
                         "H woman/mature/chinese/秦 | man/mature/chinese/贾雨村")  # t280: 新写法（讲员 H …，人物不带 人物N：）


class Consolidate(unittest.TestCase):
    def test_strata_merges_aliases_fixes_tags_rewrites_scenes_and_speakers(self):
        sc, logs, calls = _copy(), [], []

        def ask(system, user):
            calls.append((system, user))
            return "```json\n" + json.dumps(REPLY, ensure_ascii=False) + "\n```"

        res = cc.consolidate(sc, mode="story_speak", ask=ask, log=logs.append)
        self.assertEqual(res["source"], "strata")
        self.assertEqual(len(calls), 1)
        self.assertEqual(res["cast"], "man/mature/chinese/贾雨村 | man/youth/chinese/门子 | woman/kids/chinese/英莲")  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertNotIn("（", res["cast"])  # 人物栏不带括号
        self.assertEqual(sc[0]["actor"], "man/mature/chinese/贾雨村（升堂） | man/youth/chinese/门子（使眼色）")  # t280: 新写法
        # 第 2 场：不是人物的那一项拿掉 → <2> 变 <1>；应天府门子 = 门子；女儿改成 woman/kids
        self.assertEqual(sc[1]["actor"], "man/youth/chinese/门子（低声） | woman/kids/chinese/英莲")
        self.assertEqual(sc[1]["speaking"], "<1>老爷可记得我？")
        # 第 3 场：门子写了两遍 → 并成一个，<3s> → <2s>（自言自语标记、句子先后不动）
        self.assertEqual(sc[2]["actor"], "man/mature/chinese/贾雨村 | man/youth/chinese/门子（扶着）")
        self.assertEqual(sc[2]["speaking"], "<2s>这事难办。<1>你说。<2>是。")
        self.assertEqual(sc[3]["actor"], "woman/kids/chinese/英莲")
        # 缺字段只记日志，不自己补
        self.assertTrue(any("第 4 场：英莲 缺性别、年龄段、民族" in x for x in logs), logs)
        self.assertTrue(any("第 2 场：actor 里这一项不是人物" in x for x in logs))
        self.assertTrue(any("最终人物（Strata 归拢）" in x for x in logs))

    def test_prompt_has_index_caption_visual_lines_people_and_rules(self):
        people = [cc.scene_entries(k, s) for k, s in enumerate(_copy(), 1)]
        system, user = cc.build_prompt(_copy(), people, mode="story_speak", cap=4)
        for need in ("Merge entries that are the same person", "gender = man or woman", "kids, teenager, youth, mature or senior",
                     "chinese or english", "at most 4 people", "This mode has no 讲员", "map EVERY entry ref", "Output ONLY this JSON",
                     "No parentheses and no notes in the final cast", "甘氏之女"):
            self.assertIn(need, system)
        for need in ("scene 2: caption=后堂 | visual=门子低声", "lines=<2>老爷可记得我？", "s2p2 = man/mature/chinese/应天府门子",
                     "(in this scene: 低声)", "[speaks]", "s4p1 = 英莲  [missing: gender, age, ethnicity]", "NOT A PERSON?"):
            self.assertIn(need, user)
        self.assertNotIn("image_url", system + user)  # 只发文字

    def test_retry_once_then_succeed(self):
        n = []

        def ask(system, user):
            n.append(1)
            if len(n) == 1:
                raise ConnectionError("Strata 连不上")
            return json.dumps(REPLY, ensure_ascii=False)

        res = cc.consolidate(_copy(), mode="story_speak", ask=ask, log=lambda *_: None)
        self.assertEqual((res["source"], len(n)), ("strata", 2))

    def test_failure_falls_back_to_local_exact_name_merge_and_says_so(self):
        sc, logs, n = _copy(), [], []

        def ask(system, user):
            n.append(1)
            return json.dumps({"cast": [{"gender": "man", "age": "30", "ethnicity": "chinese", "name": "x"}]})  # 年龄不在词表

        res = cc.consolidate(sc, mode="story_speak", ask=ask, log=logs.append)
        self.assertEqual((res["source"], len(n)), ("local", 2))
        self.assertTrue(any("改用本地合并" in x for x in logs))
        # 本地：只合并名字完全一样的；门子 / 应天府门子 不并；英莲 什么都缺 → 不进人物栏（日志）
        self.assertEqual(res["cast"], "man/mature/chinese/贾雨村 | man/youth/chinese/门子 | "
                                      "man/mature/chinese/应天府门子 | woman/mature/chinese/甄士隐之女")  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertTrue(any("英莲 每一场都缺" in x for x in logs))
        self.assertEqual(sc[3]["actor"], "")  # 不说话、不在最终人物里：拿掉

    def test_cap_four_and_dropped_speaker_kept_in_scene_with_log(self):
        sc = [{"actor": " | ".join(f"人物{i}：man/youth/chinese/甲{i}" for i in range(1, 5)), "speaking": "<4>我是甲4"},
              {"actor": "人物1：man/youth/chinese/甲5", "speaking": ""}]
        reply = {"cast": [{"key": f"P{j}", "gender": "man", "age": "youth", "ethnicity": "chinese", "name": f"甲{i}"} for j, i in enumerate((5, 1, 2, 3, 4), 1)],
                 "scenes": [{"scene": 1, "map": {"s1p1": "P2", "s1p2": "P3", "s1p3": "P4", "s1p4": "P5"}}, {"scene": 2, "map": {"s2p1": "P1"}}]}
        logs = []
        res = cc.consolidate(sc, mode="story_act", ask=lambda s, u: json.dumps(reply, ensure_ascii=False), log=logs.append,
                             cap=4)  # t279: 默认上限是 10；这里用 4 测截断
        self.assertEqual(len([s for s in res["cast"].split(" | ") if s and not s.startswith("H ")]), 4)
        self.assertNotIn("甲4", res["cast"])  # 第 5 个人不进人物栏
        self.assertIn("man/youth/chinese/甲4", sc[0]["actor"])
        self.assertNotIn("人物", sc[0]["actor"])  # t280: 新写法（讲员 H …，人物不带 人物N：）  # 有台词：留在这一场
        self.assertEqual(sc[0]["speaking"], "<4>我是甲4")
        self.assertTrue(any("有台词但不在最终人物里" in x for x in logs))

    def test_podcast_host_maps_to_H_other_modes_have_no_host(self):
        sc = [{"actor": "讲员：woman/mature/chinese/阿兰（微笑） | 人物1：man/senior/chinese/老周", "speaking": "<1>欢迎。<2>谢谢。"}]
        reply = {"cast": [{"key": "P1", "gender": "man", "age": "senior", "ethnicity": "chinese", "name": "老周"}],
                 "host": {"gender": "woman", "age": "mature", "ethnicity": "chinese", "name": "阿兰"},
                 "scenes": [{"scene": 1, "map": {"s1p1": "H", "s1p2": "P1"}}]}
        res = cc.consolidate(sc, mode="podcast", ask=lambda s, u: json.dumps(reply, ensure_ascii=False), log=lambda *_: None)
        self.assertEqual(res["cast"], "H woman/mature/chinese/阿兰 | man/senior/chinese/老周")  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertEqual(sc[0]["actor"], "H woman/mature/chinese/阿兰（微笑） | man/senior/chinese/老周")
        sc2 = [{"actor": "讲员：woman/mature/chinese/阿兰 | 人物1：man/senior/chinese/老周", "speaking": "<1>欢迎。<2>谢谢。"}]
        res2 = cc.consolidate(sc2, mode="story_speak", ask=lambda s, u: json.dumps(reply, ensure_ascii=False), log=lambda *_: None)
        self.assertFalse(res2["cast"].startswith(("讲员", "H ")))

    def test_no_people_means_empty_cast_without_calling_strata(self):
        res = cc.consolidate([{"actor": "", "speaking": ""}], mode="story_speak",
                             ask=lambda s, u: (_ for _ in ()).throw(AssertionError("不该调")), log=lambda *_: None)
        self.assertEqual((res["cast"], res["source"]), ("", "none"))

    def test_env_local_never_calls_strata(self):
        import os

        old = os.environ.get(cc.ENV_MODE)
        os.environ[cc.ENV_MODE] = "local"
        try:
            with self.assertRaises(RuntimeError):
                cc.strata_ask("s", "u")
        finally:
            if old is None:
                os.environ.pop(cc.ENV_MODE, None)
            else:
                os.environ[cc.ENV_MODE] = old


class PerPageIndependent(unittest.TestCase):
    def test_every_page_gets_no_earlier_people(self):
        calls = []
        people = {1: "人物1:woman/mature/chinese/王夫人(哭)", 2: "人物1:man/mature/chinese/贾政", 3: ""}

        def ask(img, system, user):
            calls.append((system, user))
            k = len(calls)
            return json.dumps([{"visual": f"p{k}", "actor": people[k], "speaking": ""}], ensure_ascii=False)

        def build(k, n, cast_text, scenes):
            return f"SYSTEM[cast={cast_text}]", psp.page_user_text(k, n, original_page=k, page_text="", cast_text=cast_text,
                                                                  scenes=scenes, independent=True)

        res = psp.run_pages(["a", "b", "c"], ask, build, dynamic=True, mode="story_speak", independent=True)
        self.assertEqual([c[0] for c in calls], ["SYSTEM[cast=]"] * 3)  # 没有累计名单
        self.assertNotIn("王夫人", calls[1][1])  # 前面场景的摘要里也没有 actor
        self.assertNotIn("actor=", calls[1][1])
        self.assertIn("scene 1: visual=p1", calls[1][1])  # 故事接得上
        self.assertIn("PEOPLE ON THIS PAGE ONLY", calls[1][1])
        self.assertEqual(res["scenes"][0]["actor"], "人物1:woman/mature/chinese/王夫人(哭)")  # 原样，之后统一归拢
        self.assertEqual(res["cast"], "")


class DownloaderFlows(unittest.TestCase):
    def test_strata_pages_are_independent_then_one_consolidation(self):
        res = _real(_FAKE_SELF + r'''
pdf = mk(3)
calls, cons = [], []
pages = {1: "人物1:man/mature/chinese/贾雨村(升堂)", 2: "人物1:man/mature/chinese/应天府门子(低声)", 3: "人物1:门子 | 人物2:man/mature/chinese/贾雨村"}
def ask(img, system, user):
    k = len(calls) + 1
    calls.append(system + "\n" + user)
    sp = "<1>甲<2>乙" if k == 3 else "<1>好"
    return json.dumps([{"visual": "p%d" % k, "actor": pages[k], "speaking": sp}], ensure_ascii=False)
def cask(system, user):
    cons.append(user)
    return json.dumps({"cast": [{"key": "P1", "gender": "man", "age": "mature", "ethnicity": "chinese", "name": "贾雨村"},
                                {"key": "P2", "gender": "man", "age": "youth", "ethnicity": "chinese", "name": "门子"}],
                       "scenes": [{"scene": 1, "map": {"s1p1": "P1"}}, {"scene": 2, "map": {"s2p1": "P2"}},
                                  {"scene": 3, "map": {"s3p1": "P2", "s3p2": "P1"}}]}, ensure_ascii=False)
f._cast_consolidate_ask = cask
vd = {"analyzed_content": "x", "dynamic_cast": True, "story_actors": "人物1：man/senior/chinese/林冲", "project_profile": {"story_actors": "人物1：man/senior/chinese/林冲"}}
sc = G(f, vd, "故事对话", attachment=pdf, text_backend="strata", strata_ask=ask)
shutil.rmtree(tmp, True)
print(json.dumps({"p2_has_p1": "升堂" in calls[1] or "People so far" in calls[1], "p3_has_p2": "应天府门子" in calls[2],
                  "cons": len(cons), "cons_has_all": all(("scene %d:" % k) in cons[0] for k in (1, 2, 3)),
                  "cast": vd["story_actors"], "prof": vd["project_profile"]["story_actors"],
                  "actors": [s.get("actor") for s in sc], "sp3": sc[2]["speaking"], "old": "林冲" in "".join(calls)}, ensure_ascii=False))
''')
        self.assertFalse(res["p2_has_p1"])
        self.assertFalse(res["p3_has_p2"])
        self.assertFalse(res["old"])
        self.assertEqual(res["cons"], 1)  # 全部页跑完只归拢一次
        self.assertTrue(res["cons_has_all"])
        self.assertEqual(res["cast"], "man/mature/chinese/贾雨村 | man/youth/chinese/门子")  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertEqual(res["prof"], res["cast"])
        self.assertEqual(res["actors"], ["man/mature/chinese/贾雨村（升堂）", "man/youth/chinese/门子（低声）",
                                         "man/youth/chinese/门子 | man/mature/chinese/贾雨村"])  # t280: 新写法
        self.assertEqual(res["sp3"], "<1>甲<2>乙")  # 顺序没变：号不动

    def test_grok_batch_consolidates_once_and_off_never_consolidates(self):
        res = _real(_FAKE_SELF + r'''
cons = []
def cask(system, user):
    cons.append(user)
    return json.dumps({"cast": [{"key": "P1", "gender": "woman", "age": "kids", "ethnicity": "chinese", "name": "甘氏之女"}],
                       "scenes": [{"scene": 1, "map": {"s1p1": "P1"}}, {"scene": 2, "map": {"s2p1": "P1"}}]}, ensure_ascii=False)
f._cast_consolidate_ask = cask
REPLY = [{"visual": "a", "actor": "人物1：woman/mature/chinese/甘氏的女儿（读书）", "speaking": "<1>爹。"},
         {"visual": "b", "actor": "人物1：甘氏之女", "speaking": ""}]
def gen(prompt, sys_, expect_list=True, attachment=None, extra=None):
    return json.loads(json.dumps(REPLY))
f.llm_api_manual = type("M", (), {"generate_json": staticmethod(gen)})()
vd = {"analyzed_content": "x", "dynamic_cast": True, "story_actors": ""}
sc = G(f, vd, "故事对话", text_backend="grok", prompt_params={"steps": 0, "episodes": 1})
n_on = len(cons)
off = {"analyzed_content": "x", "story_actors": "人物1：man/youth/chinese/阿明 | 人物2：woman/youth/chinese/小美"}
G(f, off, "故事对话", text_backend="grok", prompt_params={"steps": 0, "episodes": 1})
print(json.dumps({"n_on": n_on, "n_total": len(cons), "cast": vd["story_actors"], "a": [s["actor"] for s in sc], "off": off["story_actors"]}, ensure_ascii=False))
''')
        self.assertEqual(res["n_on"], 1)
        self.assertEqual(res["n_total"], 1)  # 没勾：不归拢
        self.assertEqual(res["cast"], "woman/kids/chinese/甘氏之女")  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertEqual(res["a"], ["woman/kids/chinese/甘氏之女（读书）", "woman/kids/chinese/甘氏之女"])  # t280: 新写法
        self.assertEqual(res["off"], "人物1：man/youth/chinese/阿明 | 人物2：woman/youth/chinese/小美")  # 没勾：原来的旧写法名单一个字不动


class Wiring(unittest.TestCase):
    def test_top_cast_strips_brackets_from_scenes_when_dynamic(self):
        se = _read("gui", "dl", "scene_editor.py")
        fn = se[se.index("def _cast_base"):se.index("def _cast_from_scenes")]
        self.assertIn("_clean_cast_body(base)", fn)
        self.assertIn("dynamic_cast_enabled(video_detail)", fn)
        body = se[se.index("def _cast_from_scenes"):se.index("def _prune_silent_cast")]
        self.assertIn("base = _cast_base(row.get(\"body\"))", body)
        saved = se[se.index("def _on_smart_saved"):se.index("def _ask_scene_text_backend")]
        self.assertIn("_clean_cast_text(str(video_detail.get(\"story_actors\") or \"\"))", saved)

    def test_downloader_uses_consolidation_for_fresh_and_per_page(self):
        dl = _read("gui", "downloader.py")
        merge = dl[dl.index("def _merge_dynamic_cast"):dl.index("def _consolidate_dynamic_cast")]
        self.assertIn("self._consolidate_dynamic_cast(video_detail, scenes, prompt_label)", merge)
        per = dl[dl.index("def _generate_pdf_scenes_per_page_strata"):dl.index("def _run_scene_smart_generate_async")]
        self.assertIn("independent=fresh", per)
        self.assertIn("self._consolidate_dynamic_cast(video_detail, out, prompt_label)", per)

    def test_prompt_block_wording(self):
        b = cp.dynamic_cast_block("", "story_speak", fresh=True)
        for need in ("FIND THE PEOPLE OF EACH SCENE ON ITS OWN", "Do not carry people over from other scenes or pages",
                     "gender is man or woman; age band is kids, teenager, youth, mature or senior; ethnicity is chinese or english",
                     "All four parts are required for every person in every scene", "某某的女儿, 甘氏之女, 门子",
                     "a little daughter is woman/kids", "No reasoning, no explanations and no sentences in ``actor``",
                     "merged into one cast of at most 10 people"):
            self.assertIn(need, b)
        self.assertIn("plus one 讲员", cp.dynamic_cast_block("", "podcast", fresh=True))


if __name__ == "__main__":
    unittest.main()