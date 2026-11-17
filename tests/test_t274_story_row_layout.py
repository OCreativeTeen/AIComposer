# -*- coding: utf-8 -*-
"""t274: STORY 窗布局——第 2 行最右 [名称栏][保存][打开项目]；「动态生成人物」勾选框在第 3 行（人物栏右边）；
生成按钮这一行不再放勾选框（「整理场景」不被挤掉）。源码级检查（真实几何由无头 Tk 冒烟看过）。"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _se() -> str:
    with open(os.path.join(ROOT, "gui", "dl", "scene_editor.py"), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


class StoryRowLayout(unittest.TestCase):
    def setUp(self):
        self.se = _se()

    def test_open_project_is_on_row2_after_save_at_far_right(self):
        se = self.se
        blk = se[se.index("# t274: 第 2 行最右边"):se.index("def _offer_pdf_scene_generate")]
        self.assertIn('_row2 = scene_ui.get("size_frm")', blk)
        # 先 pack 的在最右：打开项目 → 保存 → 名称栏
        self.assertLess(blk.index('text="打开项目"'), blk.index('text="保存"'))
        self.assertLess(blk.index('text="保存"'), blk.index("_te.pack(side=tk.RIGHT"))
        self.assertIn('scene_ui["open_project_btn"].pack(side=tk.RIGHT', blk)
        self.assertIn("command=on_open_project", blk)
        # 第 3 行（人物栏那一行）不再有打开项目 / 分隔线
        self.assertEqual(se.count('text="打开项目"'), 1)
        self.assertNotIn('open_host = scene_ui["prompt_row"]', se)

    def test_title_entry_is_narrower(self):
        self.assertRegex(self.se, r"title_entry = ttk\.Entry\([^\n]*textvariable=title_var, width=14\)")

    def test_dynamic_checkbox_lives_in_row3_with_unchanged_rules(self):
        se = self.se
        # t280: 新写法：勾选框在 prompt_row 里的 cast_side 小框（靠右），下面紧挨着「人物合并」按钮
        self.assertIn('cast_side = ttk.Frame(scene_ui["prompt_row"])', se)
        self.assertIn("cast_side.pack(side=tk.RIGHT", se)
        m = re.search(r"dynamic_cast_chk = ttk\.Checkbutton\(\s*cast_side,", se)
        self.assertIsNotNone(m)  # 第 3 行 = 人物栏所在的 prompt_row
        self.assertIn("dynamic_cast_chk.pack(side=tk.TOP, anchor=\"w\", before=cast_merge_btn)", se)
        self.assertIn("command=_on_dynamic_cast_toggle", se)
        self.assertIn("variable=dynamic_cast_var", se)
        sync = se[se.index("def _sync_dynamic_prompt_widgets"):se.index("prompt_combo_var.trace_add")]
        self.assertIn("mode_for_label(sel)", sync)  # 只在播客 / 故事对话 / 故事表演显示
        self.assertNotIn('gen_row.show("dynamic"', se)
        self.assertNotIn('gen_row"].add(dynamic_cast_chk', se)

    def test_toolbar_row_keeps_only_buttons(self):
        adds = re.findall(r'for _b, _k in \(([^\n]*)\):', self.se)
        self.assertTrue(any("dynamic" not in a and "smart_btn" in a for a in adds))


if __name__ == "__main__":
    unittest.main()