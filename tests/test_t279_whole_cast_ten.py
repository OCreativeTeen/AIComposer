# -*- coding: utf-8 -*-
"""t279: 人物栏（整个故事的名单）最多 10 个人物 + 1 个讲员；每一场的 actor 还是最多 4 个人。
人物栏两行、每行 5 个人物（讲员 H 在最左边一格占两行）；卡片编号只显示短的：人物N → N，讲员 → H，
放不下截成 ``..``，鼠标放上去看完整文字。存的文字 / 提示词 / <N> 还是 人物N / 讲员。魔法工作流里的人物也这样显示。"""
import json
import unittest

from tests.test_t272_pdf_scenes_cast import _read, _real
from utility import cast_consolidate as cc
from utility import cast_preset as cp

TWELVE = "讲员：woman/mature/chinese/秦 | " + " | ".join(f"人物{i}：man/youth/chinese/甲{i}" for i in range(1, 13))


class Caps(unittest.TestCase):
    def test_constants(self):
        res = _real('import json, project_manager as pm\n'
                    'print(json.dumps([pm.ACTOR_MAX_PRESENT, pm.CAST_MAX_PEOPLE, pm.CAST_MAX_PRESENT, pm.CAST_MAX_PRESENT_DYNAMIC]))')
        self.assertEqual(res, [4, 10, 11, 11])
        self.assertEqual(cp.DYNAMIC_CAST_MAX_PEOPLE, 10)
        self.assertEqual(cc.MAX_PEOPLE, 10)

    def test_whole_cast_is_ten_people_plus_host_scene_stays_four(self):
        res = _real('import json, project_manager as pm\n'
                    f'text = {TWELVE!r}\n'
                    'cast = pm.normalize_cast_text(text)\n'
                    'nohost = pm.normalize_cast_text(text.split(" | ", 1)[1])\n'
                    'print(json.dumps({"cast": cast, "n": len(pm.cast_entries(text)), "nohost": len([s for s in nohost.split(" | ") if s]),\n'
                    '                  "scene": pm.normalize_actor_text(text), "scene_n": len(pm.actor_entries(text))}, ensure_ascii=False))')
        self.assertTrue(res["cast"].startswith("H woman/mature/chinese/秦 | man/youth/chinese/甲1"))  # t280: 新写法（讲员 H …，人物不带 人物N：）
        self.assertIn(" | man/youth/chinese/甲10", res["cast"])
        self.assertNotIn("甲11", res["cast"])
        self.assertEqual(res["n"], 11)
        self.assertEqual(res["nohost"], 10)  # 没有讲员也只有 10 个人物（讲员不占人物的名额）
        self.assertEqual(res["scene_n"], 4)  # 一场：含讲员最多 4 个
        self.assertNotIn("甲4", res["scene"])

    def test_prompts_and_program_cast_keep_ten(self):
        res = _real('import json, gui.dl.prompts_notebooklm as p\n'
                    f'text = {TWELVE!r}\n'
                    'vd = {"story_actors": text}\n'
                    'print(json.dumps({"max": [p.cast_max_present(vd), p.cast_max_present(dict(vd, dynamic_cast=True))],\n'
                    '                  "block": p.build_cast_block(text), "small": p.build_cast_block("人物1：man/youth/chinese/甲1"),\n'
                    '                  "nohost": p._without_host_cast(vd)["story_actors"],\n'
                    '                  "program": p.build_program_cast_block(vd, "故事对话")}, ensure_ascii=False))')
        self.assertEqual(res["max"], [11, 11])
        self.assertIn("Number of characters (人物): 10", res["block"])
        self.assertIn("  - man/youth/chinese/甲10", res["block"])
        self.assertNotIn("甲11", res["block"])
        self.assertIn("One scene's ``actor`` still holds at most four people", res["block"])
        self.assertNotIn("still holds at most four", res["small"])
        self.assertEqual(len([s for s in res["nohost"].split(" | ") if s and not s.startswith("H ")]), 10)  # t280: 新写法
        self.assertIn("  - man/youth/chinese/甲10", res["program"])  # 节目生成不再截成 4 个

    def test_portrait_names_cover_the_whole_cast(self):
        res = _real('import json\nfrom utility import story_portraits as sp\n'
                    f'print(json.dumps(sp.person_names({TWELVE!r}), ensure_ascii=False))')
        self.assertEqual(len(res), 10)
        self.assertEqual(res[-1], "man/youth/chinese/甲10")

    def test_dynamic_merge_and_consolidation_take_ten(self):
        cast = ""
        for i in range(1, 13):
            cast, _a, _n = cp.merge_scene_people(cast, f"人物1：man/youth/chinese/甲{i}")
        self.assertEqual(len([s for s in cast.split(" | ") if s and not s.startswith("H ")]), 10)
        scenes = [{"actor": " | ".join(f"人物{j}：man/youth/chinese/乙{k * 3 + j}" for j in range(1, 4)), "speaking": "<1>说"}
                  for k in range(4)]  # 4 场 × 3 人 = 12 个不同的人，每一场都不超过 4 个
        res = cc.consolidate(scenes, mode="story_speak", ask=lambda s, u: (_ for _ in ()).throw(RuntimeError("离线")),
                             log=lambda *_: None)
        self.assertEqual(res["source"], "local")
        self.assertEqual(len([s for s in res["cast"].split(" | ") if s and not s.startswith("H ")]), 10)  # t280: 新写法
        self.assertTrue(all(len(s["actor"].split(" | ")) <= 4 for s in scenes))
        system, _u = cc.build_prompt(scenes, [cc.scene_entries(k, s) for k, s in enumerate(scenes, 1)], mode="story_speak")
        self.assertIn("at most 10 people", system)

    def test_per_scene_prompt_still_says_four(self):
        b = cp.dynamic_cast_block("", "story_speak", fresh=True)
        self.assertIn("At most four people in one scene's ``actor``", b)
        self.assertIn("one cast of at most 10 people", b)
        self.assertIn("At most 10 people (人物) in the whole program", cp.dynamic_cast_block("", "story_speak"))


class Labels(unittest.TestCase):
    def test_short_display_ids(self):
        res = _real('import json, project_manager as pm\nfrom gui.dl import story_actor_panel as sap\n'
                    'rows = pm.cast_entries("讲员：woman/mature/chinese/秦（微笑） | 人物1：man/mature/chinese/贾雨村（升堂） | 人物2：woman/kids/chinese")\n'
                    'print(json.dumps({"ids": [pm.actor_display_id(r) for r in rows], "chips": [sap.chip_text(r) for r in rows],\n'
                    '                  "labels": [r["label"] for r in rows]}, ensure_ascii=False))')
        self.assertEqual(res["ids"], ["H", "1", "2"])
        self.assertEqual(res["chips"], ["H woman/mature/chinese/秦", "1 贾雨村（man/mature/chinese）", "2（woman/kids/chinese）"])
        self.assertEqual(res["labels"], ["讲员", "人物1", "人物2"])  # 存的 / 提示词里的不变

    def test_fit_text_truncates_with_two_dots(self):
        res = _real(r'''
import json
from gui.dl.story_actor_panel import fit_text, person_text_px
class F:
    @staticmethod
    def measure(s):
        return 10 * len(s)
print(json.dumps([fit_text("1 贾雨村（man）", F, 500), fit_text("abcdefghij", F, 60), person_text_px(1000),
                  person_text_px(1000, 150)], ensure_ascii=False))
''')
        self.assertEqual(res[:2], ["1 贾雨村（man）", "abcd.."])
        self.assertEqual(res[2:], [170, 140])  # (1000 - 8) / 5 - 28；左边有讲员那一格时更窄

    def test_workflow_displays_use_short_ids(self):
        wa = _read("gui", "workflow", "wf_actors.py")
        self.assertIn('sid = project_manager.actor_display_id(entry)', wa)
        self.assertIn('text = f"H：{body}" if base else "H"', wa)
        self.assertIn('text = f"{sid}：{body}" if sid else body', wa)
        self.assertNotIn('text = f"讲员：{body}" if base else "讲员"', wa)
        self.assertIn("project_manager.actor_display_id(row)", _read("gui", "workflow", "wf_span_audio.py"))
        self.assertIn("project_manager.actor_display_id(r) or r['label']", _read("gui", "picture_prompt_dialog.py"))
        # t281: 参考图名单里改成新写法（H 讲员 / 人物不带 人物N + actor 位置），见 actor_format.ref_who
        self.assertIn("return ref_who(r).strip()", _read("gui", "workflow", "wf_prompt_flows.py"))

    def test_scene_editor_uses_whole_cast_cap(self):
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("max_present=project_manager.CAST_MAX_PRESENT,", se)
        self.assertIn("cap = project_manager.CAST_MAX_PEOPLE", se)
        self.assertNotIn("人物栏回到最多 4 个人", se)
        self.assertNotIn("format_actor_entries(rows[:4])", se)


class PanelLayout(unittest.TestCase):
    def test_two_rows_five_each_at_1000px(self):
        res = _real(r'''
import json, tkinter as tk
from gui.dl import story_actor_panel as sap
root = tk.Tk()
root.withdraw()
long = " | ".join("人物%d：man/youth/chinese/%s" % (i, "欧阳长名字的人物" * 2 + str(i)) for i in range(1, 13))
p = sap.StoryActorPanel(root, text="讲员：woman/mature/chinese/秦 | " + long)
p.pack(fill="x")
root.update_idletasks()
chips = p._chips
info = [(c._actor_entry["role"], int(c.grid_info()["row"]), int(c.grid_info()["column"]), int(c.grid_info().get("rowspan", 1))) for c in chips]
host = [c for c in chips if c._actor_entry["role"] == "host"][0]
persons = [c for c in chips if c._actor_entry["role"] != "host"]
rows_w = {}
for c in persons:
    r = int(c.grid_info()["row"])
    rows_w[r] = rows_w.get(r, 0) + c.winfo_reqwidth() + 4
texts = [c._actor_text_label.cget("text") for c in chips]
text = p.get_text()
host_w = host.winfo_reqwidth() + 4
root.destroy()
print(json.dumps({"n": len(chips), "info": info, "rows_w": rows_w, "host_w": host_w,
                  "texts": texts, "full": [c._actor_full for c in persons][:1], "text": text}, ensure_ascii=False))
''')
        self.assertEqual(res["n"], 11)  # 讲员 + 10 个人物（第 11、12 个没进来）
        self.assertEqual(res["info"][0], ["host", 0, 0, 2])  # 讲员在最左边，占两行
        persons = res["info"][1:]
        self.assertEqual([(r, c) for _role, r, c, _s in persons], [(i // 5, 1 + i % 5) for i in range(10)])
        for r, w in res["rows_w"].items():
            self.assertLessEqual(w + res["host_w"], 1000, r)  # 一行 5 个放得下 1000px
        self.assertTrue(res["texts"][0].startswith("H "))
        self.assertTrue(res["texts"][1].startswith("1 欧阳") and res["texts"][1].endswith(".."))
        self.assertTrue(res["texts"][10].startswith("10 "))
        self.assertTrue(res["full"][0].endswith("（man/youth/chinese）"))  # 提示框里的完整文字
        self.assertTrue(res["text"].startswith("H woman/mature/chinese/秦 | "))  # t280: 存的是新写法（讲员 H，人物不带标签）
        self.assertEqual(len(res["text"].split(" | ")), 11)
        self.assertNotRegex(res["text"], r"(人物\d*|讲员)[：:]")

    def test_frame_is_two_rows_tall_even_with_few_people(self):
        res = _real(r'''
import json, tkinter as tk
from gui.dl import story_actor_panel as sap
root = tk.Tk()
root.withdraw()
p = sap.StoryActorPanel(root, text="人物1：man/youth/chinese/甲")
p.pack(fill="x")
root.update_idletasks()
out = {"h": p.row.winfo_reqheight(), "line": p._chip_height(), "rows": [int(p.row.grid_rowconfigure(r)["minsize"]) for r in (0, 1)],
       "text": p._chips[0]._actor_text_label.cget("text")}
root.destroy()
print(json.dumps(out, ensure_ascii=False))
''')
        self.assertEqual(res["rows"], [res["line"], res["line"]])
        self.assertGreaterEqual(res["h"], 2 * res["line"])
        self.assertEqual(res["text"], "1 甲（man/youth/chinese）")

    def test_manual_add_caps_at_ten_people(self):
        src = _read("gui", "dl", "story_actor_panel.py")
        fn = src[src.index("def _apply_edit"):src.index("class ActorEditDialog")]
        self.assertIn("cap = project_manager.CAST_MAX_PEOPLE", fn)
        self.assertIn("人物栏最多 {cap} 个人物（讲员另算）", fn)
        self.assertNotIn("一场最多四个人（含讲员）", fn)


if __name__ == "__main__":
    unittest.main()