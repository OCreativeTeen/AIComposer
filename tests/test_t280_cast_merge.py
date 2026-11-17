# -*- coding: utf-8 -*-
"""t280: 人物栏「人物合并」/ 多选删除：纯函数 + 无界面冒烟测试（单击 / Ctrl+单击选中、合并窗、Delete）。"""
import importlib
import unittest

from tests.test_t272_pdf_scenes_cast import _read, _real
from tests.test_t280_actor_format import restore_modules, use_real_modules

cm = None


def setUpModule():
    global cm
    use_real_modules()
    cm = importlib.import_module("utility.cast_merge")


def tearDownModule():
    restore_modules()

A = "man/youth/chinese/门子"
B = "man/youth/chinese/应天府门子"


def _keys(*bodies):
    return {cm.default_key({"role": "person", "body": b}) for b in bodies}


class MergeScene(unittest.TestCase):
    def test_two_in_one_scene_collapse_and_renumber(self):
        sc = {"actor": f"H woman/mature/chinese/秦 | {A}（低头） | man/mature/chinese/贾雨村 | {B}（笑）",
              "speaking": "<1>开场<2>老爷<3>嗯<4>是我", "speaking_timing": [1]}
        self.assertTrue(cm.merge_scene(sc, _keys(A, B), A))
        self.assertEqual(sc["actor"], f"H woman/mature/chinese/秦 | {A}（低头） | man/mature/chinese/贾雨村")
        self.assertEqual(sc["speaking"].replace(" ", ""), "<1>开场<2>老爷<3>嗯<2>是我")
        self.assertNotIn("speaking_timing", sc)

    def test_note_kept_and_position_kept(self):
        sc = {"actor": f"man/mature/chinese/贾雨村 | {B}（笑）", "speaking": "<1>甲<2>乙"}
        cm.merge_scene(sc, _keys(A, B), "man/youth/chinese/门子")
        self.assertEqual(sc["actor"], "man/mature/chinese/贾雨村 | man/youth/chinese/门子（笑）")
        self.assertEqual(sc["speaking"], "<1>甲<2>乙")  # 位置没变，讲话一个字不动

    def test_first_note_missing_uses_later_one(self):
        sc = {"actor": f"{A} | {B}（笑）", "speaking": "<1>甲<2>乙"}
        cm.merge_scene(sc, _keys(A, B), A)
        self.assertEqual(sc["actor"], f"{A}（笑）")
        self.assertEqual(sc["speaking"].replace(" ", ""), "<1>甲乙")  # 连着的同一个人合成一段

    def test_untouched_scene_and_host_never_merged(self):
        sc = {"actor": "H woman/mature/chinese/秦 | man/mature/chinese/贾雨村", "speaking": "<1>x"}
        self.assertFalse(cm.merge_scene(sc, _keys(A, B) | {("host", "")}, A))
        self.assertEqual(sc["actor"], "H woman/mature/chinese/秦 | man/mature/chinese/贾雨村")
        scenes = [dict(sc), {"actor": f"{B}", "speaking": "<1>y"}]
        self.assertEqual(cm.merge_people_in_scenes(scenes, _keys(A, B), A), 1)
        self.assertEqual(scenes[1]["actor"], A)

    def test_old_format_scene_is_written_new(self):
        sc = {"actor": f"讲员：woman/mature/chinese/秦 | 人物1：{B}", "speaking": "<1>a<2>b"}
        cm.merge_scene(sc, _keys(B), A)
        self.assertEqual(sc["actor"], f"H woman/mature/chinese/秦 | {A}")


class Rows(unittest.TestCase):
    ROWS = [{"role": "host", "body": "h"}, {"role": "person", "body": "x"}, {"role": "person", "body": "y"},
            {"role": "person", "body": "z"}]

    def test_merge_rows_at_first_selected(self):
        out = cm.merge_cast_rows(self.ROWS, [3, 1], "m/m/m/q")
        self.assertEqual([r["body"] for r in out], ["h", "y", "m/m/m/q"])

    def test_host_skipped_in_merge(self):
        out = cm.merge_cast_rows(self.ROWS, [0, 1, 2], "m/m/m/q")
        self.assertEqual([r["body"] for r in out], ["h", "m/m/m/q", "z"])

    def test_remove_rows_host_allowed(self):
        self.assertEqual([r["body"] for r in cm.remove_cast_rows(self.ROWS, [0, 2])], ["x", "z"])

    def test_split_id(self):
        self.assertEqual(cm.split_id("man/youth/chinese/门子（低头）"),
                         {"gender": "man", "age": "youth", "eth": "chinese", "name": "门子"})


PANEL = r'''
import json, tkinter as tk
from tkinter import messagebox
from gui.dl import story_actor_panel as sap
import tempfile, project_manager
_tmp = tempfile.mkdtemp(prefix="_tmp_t281_")  # t281: 合并会并肖像，人物肖像放临时目录，不碰真的
import atexit, shutil; atexit.register(shutil.rmtree, _tmp, True)
project_manager.PROJECT_CONFIG = None
root = tk.Tk()
root.withdraw()
merged, deleted, asked = [], [], []
messagebox.askyesno = lambda *a, **k: asked.append(a[1] if len(a) > 1 else "") or True
messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None
p = sap.StoryActorPanel(root, text="H woman/mature/chinese/秦 | girl/kids/chinese/英莲（哭） | man/youth/chinese/门子 | man/mature/chinese/贾雨村",
                        on_merge=lambda rows, body: merged.append(([r["body"] for r in rows], body)),
                        on_row_delete=lambda row: deleted.append(row["body"]), person_dir=lambda: _tmp)
p.pack(fill="x")
from tkinter import ttk
btn = ttk.Button(root, text="人物合并")
p.attach_merge_button(btn)
root.update_idletasks()
class E:
    def __init__(self, w): self.widget = w; self.x_root = 0; self.y_root = 0
ch = p._chips
out = {}
p._press(E(ch[1]))
out["single"] = p.selected_indexes()
out["btn1"] = btn.instate(["disabled"])
p._press(E(ch[2]._actor_text_label))
out["single2"] = p.selected_indexes()
p._ctrl_press(E(ch[1]))
p._ctrl_press(E(ch[0]))
out["multi"] = p.selected_indexes()
out["bg"] = [c.cget("bg") for c in ch]
out["btn2"] = btn.instate(["disabled"])
p._ctrl_press(E(ch[0]))
out["after_untoggle"] = p.selected_indexes()
dlg = p.merge_selected()
out["prefill"] = [dlg.gender_var.get(), dlg.age_var.get(), dlg.eth_var.get(), dlg.name_var.get()]
dlg.destroy()  # 取消：什么都不做
out["after_cancel"] = p.get_text()
out["merged_after_cancel"] = len(merged)
dlg = p.merge_selected()
dlg.name_var.set("门子甲")
dlg._ok()
out["merged"] = merged
out["text"] = p.get_text()
out["sel_after"] = p.selected_indexes()
# 讲员 + 一个人物：不能合并；Delete 删掉选中的（讲员也可以删），先问一次
p._press(E(p._chips[0]))
p._ctrl_press(E(p._chips[2]))
out["can_merge_host"] = p.can_merge()
out["merge_none"] = p.merge_selected() is None
p._delete_selected(p._chips[0])
out["asked"] = len(asked)
out["deleted"] = deleted
out["final"] = p.get_text()
root.destroy()
print(json.dumps(out, ensure_ascii=False))
'''


class PanelSmoke(unittest.TestCase):
    def test_select_merge_delete(self):
        res = _real(PANEL)
        self.assertEqual(res["single"], [1])
        self.assertTrue(res["btn1"])
        self.assertEqual(res["single2"], [2])  # 单击 = 只选这一枚
        self.assertEqual(res["multi"], [2, 1, 0])  # Ctrl+单击 加选（按选的先后）
        self.assertEqual(res["bg"], ["#9fc5ff"] * 3 + ["white"])
        self.assertFalse(res["btn2"])  # 2 个人物 → 能按
        self.assertEqual(res["after_untoggle"], [2, 1])
        self.assertEqual(res["prefill"], ["man", "youth", "chinese", "门子"])  # 第一个选中的人
        self.assertEqual(res["merged_after_cancel"], 0)
        self.assertIn("门子", res["after_cancel"])
        self.assertEqual(res["merged"], [[["man/youth/chinese/门子", "woman/kids/chinese/英莲（哭）"], "man/youth/chinese/门子甲"]])
        self.assertEqual(res["text"], "H woman/mature/chinese/秦 | man/youth/chinese/门子甲 | man/mature/chinese/贾雨村")
        self.assertEqual(res["sel_after"], [])
        self.assertFalse(res["can_merge_host"])
        self.assertTrue(res["merge_none"])
        self.assertEqual(res["asked"], 1)
        self.assertEqual(res["deleted"], ["woman/mature/chinese/秦", "man/mature/chinese/贾雨村"])
        self.assertEqual(res["final"], "man/youth/chinese/门子甲")


class Wiring(unittest.TestCase):
    def test_scene_editor_button_under_checkbox_and_callbacks(self):
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn('cast_merge_btn = ttk.Button(cast_side, text="人物合并"', se)
        self.assertIn("cast_merge_btn.pack(side=tk.BOTTOM", se)
        self.assertIn("on_merge=_cast_merge_scenes", se)
        self.assertIn('actor_panel.attach_merge_button(scene_ui["cast_merge_btn"])', se)
        self.assertIn("_cast_merge.merge_people_in_scenes(scenes, keys, body, key=_cast_key)", se)
        blk = se[se.index("def _cast_merge_scenes"):se.index("def _cast_portrait_context")]
        self.assertIn("self._persist_video_detail_story(video_detail, parent=dlg)", blk)


if __name__ == "__main__":
    unittest.main()
