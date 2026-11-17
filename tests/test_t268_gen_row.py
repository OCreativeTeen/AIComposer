"""t268: STORY 预览窗材料行：「共 N 集」的位置（任何时候都在叙事方式 / 步数后面）和五个动作按钮的大小（标签不被截）。

排版 / 大小用 gui/dl/gen_row.py（scene_editor 用的就是它），Tk 控件用隐藏（全透明）的窗口；没有显示器就跳过 Tk 的部分。"""
import itertools
import os
import re
import unittest

import config_channel as cc
from gui.dl import gen_row as gr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUTTONS = ("生成节目", "人物设置", "场景生成", "生成查看", "整理场景")

# 每一种叙事方式：(标签, 要不要步数, 要不要共 N 集)
MODES = [
    (cc.SERIES_STYLE_LABELS["podcast"], False, True),            # 播客：只有共 N 集（截图里的情况）
    (cc.SERIES_STYLE_LABELS["story_speak"], True, True),         # 故事对话：步数 + 共 N 集
    (cc.SERIES_STYLE_LABELS["story_act"], False, True),          # 故事表演
    (cc.STEP_STORY_LABEL, True, True),                           # FlyLink 固定步数故事
    (cc.STEP_IMAGE_LABEL, True, False),                          # 图片分解：第几步，没有共 N 集
    (cc.SCENE_SUMMARY_IMAGE_LABEL, False, False),                # 摘要图：都没有
    ("Some Other Channel Prompt", False, True),                  # 别的频道的提示词
    ("", False, True),
]


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class ModeRules(unittest.TestCase):
    def test_which_parts_each_mode_shows(self):
        for label, step, series in MODES:
            self.assertEqual(gr.visible_parts(label), {"step": step, "series": series}, label)

    def test_step_kind(self):
        self.assertEqual(gr.step_kind(cc.SERIES_STYLE_LABELS["story_speak"]), "dialogue")
        self.assertEqual(gr.step_kind(cc.STEP_STORY_LABEL), "fixed")
        self.assertEqual(gr.step_kind(cc.STEP_IMAGE_LABEL), "image")
        self.assertIsNone(gr.step_kind(cc.SERIES_STYLE_LABELS["podcast"]))

    def test_old_button_size_constants_are_the_ones_that_clipped(self):
        # 记录原来的值：width=6 个字符、padding (3, 6)、字号 9；现在不定死 width
        self.assertEqual((gr.OLD_BUTTON_WIDTH, gr.OLD_BUTTON_PADDING, gr.OLD_BUTTON_FONT[1]), (6, (3, 6), 9))
        self.assertEqual((gr.BUTTON_PADDING, gr.BUTTON_FONT[1]), ((10, 8), 10))


class _TkCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"没有 Tk 显示：{exc}")
        cls.root.attributes("-alpha", 0.0)
        cls.root.geometry("1000x160+0+0")
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def make_host(self, parent=None):
        """按 scene_editor 的做法造生成区：下拉先 pack，步数 / 共 N 集 / 分隔线 / 按钮是后来登记的。"""
        import tkinter as tk
        from tkinter import ttk

        host = ttk.Frame(parent or self.root)
        host.pack(side=tk.LEFT)
        self.addCleanup(host.destroy)
        combo = ttk.Combobox(host, values=[m[0] for m in MODES if m[0]], state="readonly", width=14)
        combo.pack(side=tk.LEFT, padx=(0, 8))
        row = gr.GenRow(host)
        row.add(combo, "combo", padx=(0, 8))
        step = ttk.Frame(host)
        ttk.Label(step, text="步数").pack(side=tk.LEFT)
        ttk.Combobox(step, values=["0", "1"], state="readonly", width=3).pack(side=tk.LEFT)
        row.add(step, "step", padx=(0, 8))
        series = ttk.Frame(host)
        ttk.Label(series, text="共").pack(side=tk.LEFT)
        ttk.Combobox(series, values=["1", "2"], state="readonly", width=3).pack(side=tk.LEFT)
        ttk.Label(series, text="集").pack(side=tk.LEFT)
        row.add(series, "series", padx=(0, 8))
        return host, row, combo, step, series

    def add_buttons(self, host, row):
        from tkinter import ttk
        import tkinter as tk

        style = gr.configure_button_style()
        sep = ttk.Separator(host, orient="vertical")
        row.add(sep, "sep", fill=tk.Y, padx=gr.SEPARATOR_PADX)
        btns = []
        for i, text in enumerate(BUTTONS):
            b = ttk.Button(host, text=text, style=style)
            row.add(b, f"b{i}", padx=gr.BUTTON_PADX)
            btns.append(b)
        return sep, btns

    def apply(self, row, label):
        for key, on in gr.visible_parts(label).items():
            row.show(key, on)
        row.relayout()
        self.root.update_idletasks()

    def order(self, host, widgets):
        names = {str(w): n for n, w in widgets.items()}
        return [names[str(w)] for w in host.pack_slaves() if str(w) in names]


class RowOrder(_TkCase):
    def expected(self, step, series, with_buttons=True):
        out = ["combo"] + (["step"] if step else []) + (["series"] if series else [])
        return out + (["sep", *[f"b{i}" for i in range(5)]] if with_buttons else [])

    def names(self, combo, step, series, sep=None, btns=()):
        d = {"combo": combo, "step": step, "series": series}
        if sep is not None:
            d["sep"] = sep
            d.update({f"b{i}": b for i, b in enumerate(btns)})
        return d

    def test_initial_layout_puts_the_episode_count_right_after_the_dropdown(self):
        """t268 的 bug：先排下拉 + 共 N 集，再挂分隔线和按钮（这些原来都 after=下拉），共 N 集就落到整行最后。"""
        for label, step, series in MODES:
            with self.subTest(initial_mode=label):
                host, row, combo, stp, ser = self.make_host()
                self.apply(row, label)  # 窗口刚打开：先按存下来的叙事方式排一次
                self.assertEqual(self.order(host, self.names(combo, stp, ser)), self.expected(step, series, False))
                sep, btns = self.add_buttons(host, row)  # 然后按钮才建好
                row.relayout()
                self.root.update_idletasks()
                got = self.order(host, self.names(combo, stp, ser, sep, btns))
                self.assertEqual(got, self.expected(step, series), label)
                if series:
                    self.assertLess(got.index("series"), got.index("sep"))  # 共 N 集在分隔线和按钮前面
                host.destroy()

    def test_every_mode_switch_keeps_the_order(self):
        host, row, combo, stp, ser = self.make_host()
        self.apply(row, MODES[0][0])
        sep, btns = self.add_buttons(host, row)
        row.relayout()
        names = self.names(combo, stp, ser, sep, btns)
        for (a, *_), (b, step, series) in itertools.product(MODES, MODES):  # 任何一种切到任何一种
            self.apply(row, a)
            self.apply(row, b)
            self.assertEqual(self.order(host, names), self.expected(step, series), f"{a!r} → {b!r}")
        # 反复来回切也不乱
        for label, step, series in MODES * 3:
            self.apply(row, label)
            self.assertEqual(self.order(host, names), self.expected(step, series), label)
        # 共 N 集永远紧跟下拉（有步数就跟在步数后面）
        self.apply(row, cc.SERIES_STYLE_LABELS["story_speak"])
        self.assertEqual(self.order(host, names)[:3], ["combo", "step", "series"])
        self.apply(row, cc.SERIES_STYLE_LABELS["podcast"])
        self.assertEqual(self.order(host, names)[:2], ["combo", "series"])

    def test_relayout_is_a_no_op_when_the_order_is_already_right(self):
        host, row, combo, stp, ser = self.make_host()
        self.apply(row, MODES[0][0])
        sep, btns = self.add_buttons(host, row)
        row.relayout()
        before = [str(w) for w in host.pack_slaves()]
        calls = []
        orig = btns[0].pack_forget
        btns[0].pack_forget = lambda *a, **k: (calls.append(1), orig())
        row.relayout()
        self.assertEqual(calls, [])  # 没有多余的 forget / 重排（不闪）
        self.assertEqual([str(w) for w in host.pack_slaves()], before)

    def test_scene_editor_registers_the_row_in_order_and_has_no_pack_after(self):
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("from gui.dl import gen_row as gen_row_mod", se)
        self.assertIn("_step_kind_of = gen_row_mod.step_kind", se)
        adds = [m.group(1) for m in re.finditer(r'gen_row(?:"\])?\.add\(\s*[\w_]+,\s*"(\w+)"', se)]
        self.assertEqual(adds, ["combo", "step", "series", "sep", "review", "prep"])  # program / cast / smart 在 for 循环里登记
        self.assertIn(  # t274: 「动态生成人物」勾选框搬去第 3 行，这一行只剩三个按钮
            'for _b, _k in ((program_btn, "program"), (cast_btn, "cast"), (smart_btn, "smart")):', se)
        self.assertNotIn('"dynamic"), (smart_btn', se)
        self.assertLess(se.index('"review", padx='), se.index('"prep", padx='))
        # 切叙事方式只开关再统一排版，不再各自 pack_forget / pack(after=…)
        sync = se[se.index("def _sync_dynamic_prompt_widgets"):se.index("prompt_combo_var.trace_add")]
        self.assertIn("gen_row.relayout()", sync)
        self.assertIn("gen_row_mod.visible_parts(sel).items()", sync)
        self.assertNotIn(".pack(", sync)
        self.assertNotIn("pack_forget", sync)
        self.assertNotIn("after=", sync)
        self.assertNotIn("after=_smart", se)
        self.assertNotIn("after=prompt_combo", se)


class ButtonSize(_TkCase):
    def test_every_button_is_wide_enough_for_its_label(self):
        from tkinter import ttk

        style = gr.configure_button_style()
        padx = gr.BUTTON_PADDING[0]
        for text in BUTTONS + ("生成节目（NotebookLM）",):
            b = ttk.Button(self.root, text=text, style=style)
            b.pack()
            self.root.update_idletasks()
            need = gr.text_width(b, text) + 2 * padx
            self.assertGreaterEqual(b.winfo_reqwidth(), need, text)  # 字 + 左右 padding 都放得下
            self.assertGreaterEqual(b.winfo_reqwidth(), gr.text_width(b, text), text)
            b.destroy()

    def test_buttons_are_at_least_30_percent_bigger_than_before(self):
        from tkinter import ttk

        old_style = "T268Old.TButton"
        ttk.Style().configure(old_style, font=gr.OLD_BUTTON_FONT, padding=gr.OLD_BUTTON_PADDING)
        new_style = gr.configure_button_style()
        for text in BUTTONS:
            old = ttk.Button(self.root, text=text, style=old_style, width=gr.OLD_BUTTON_WIDTH)
            new = ttk.Button(self.root, text=text, style=new_style)
            old.pack()
            new.pack()
            self.root.update_idletasks()
            self.assertGreaterEqual(new.winfo_reqwidth(), old.winfo_reqwidth() * 1.3, text)
            self.assertGreaterEqual(new.winfo_reqheight(), old.winfo_reqheight() * 1.1, text)
            # 原来的按钮：标签比按钮内部宽（被截）；现在不会
            self.assertLess(old.winfo_reqwidth(), gr.text_width(old, text, gr.OLD_BUTTON_FONT) + 2 * gr.OLD_BUTTON_PADDING[0] + 1 + 40)
            old.destroy()
            new.destroy()

    def test_buttons_are_not_clipped_in_the_real_row_at_1000px(self):
        """材料行（分析报告 · 材料 · 状态文字 · 分隔线 · 生成区）在 1000 像素宽的窗口里：按钮都在窗口内，状态文字换行变窄。"""
        import tkinter as tk
        from tkinter import ttk

        for label in (cc.SERIES_STYLE_LABELS["podcast"], cc.SERIES_STYLE_LABELS["story_speak"]):  # 后者多一个步数
            with self.subTest(mode=label):
                self.root.geometry("1000x160+0+0")
                row = ttk.Frame(self.root)
                row.pack(fill=tk.X)
                tk.Button(row, text="分析报告", width=8, relief=tk.SUNKEN, bd=1).pack(side=tk.LEFT, padx=(0, 4))
                tk.Button(row, text="材料", relief=tk.RAISED, bd=1).pack(side=tk.LEFT, padx=(0, 8))
                status = ttk.Label(row, text="PDF · 图片 0 · 无媒体 　场景 1 条")
                status.pack(side=tk.LEFT, padx=(4, 4))
                ttk.Separator(row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=8)
                host, grow, combo, stp, ser = self.make_host(row)
                host.pack_forget()
                host.pack(side=tk.LEFT, padx=(4, 0))
                self.apply(grow, label)
                sep, btns = self.add_buttons(host, grow)
                grow.relayout()
                self.root.update()
                gr.fit_status_label(row, status)
                self.root.update()
                right = max(b.winfo_rootx() + b.winfo_width() for b in btns) - self.root.winfo_rootx()
                self.assertLessEqual(right, 1000, f"最右的按钮伸到 {right}px")
                for b, text in zip(btns, BUTTONS):
                    self.assertGreaterEqual(b.winfo_width(), gr.text_width(b, text), text)  # 实际宽度（不只是请求宽度）够显示整个标签
                row.destroy()

    def test_status_label_wraps_only_when_the_row_is_too_narrow(self):
        import tkinter as tk
        from tkinter import ttk

        self.root.geometry("1000x160+0+0")
        row = ttk.Frame(self.root)
        row.pack(fill=tk.X)
        self.addCleanup(row.destroy)
        status = ttk.Label(row, text="PDF · 图片 0 · 无媒体 场景 1 条")
        status.pack(side=tk.LEFT)
        host, grow, *_ = self.make_host(row)
        self.apply(grow, MODES[1][0])
        self.add_buttons(host, grow)
        grow.relayout()
        self.root.update()
        self.assertEqual(gr.fit_status_label(row, status), 0)  # 放得下：不限宽
        self.root.geometry("560x160+0+0")
        self.root.update()
        wrap = gr.fit_status_label(row, status)
        self.assertGreaterEqual(wrap, 80)  # 太窄：状态文字换行，有最小宽度
        self.assertEqual(int(float(status.cget("wraplength"))), wrap)
        self.root.geometry("1000x160+0+0")
        self.root.update()
        self.assertEqual(gr.fit_status_label(row, status), 0)  # 再变宽：恢复

    def test_scene_editor_uses_the_shared_button_style_and_no_fixed_width(self):
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("smart_style = gen_row_mod.configure_button_style()", se)
        self.assertNotIn('"StorySmartGenerate.TButton"', se)
        for text in BUTTONS:
            block = se[se.index(f'text="{text}",\r\n') if f'text="{text}",\r\n' in se else se.index(f'text="{text}",\n'):][:260]
            self.assertIn("style=smart_style,", block, text)
            self.assertNotIn("width=", block.split(")")[0], text)  # 不再定死字符宽
        self.assertIn("material_row.bind(\"<Configure>\", _fit_status", se)
        self.assertIn("gen_row_mod.fit_status_label(material_row, scene_count_lbl)", se)


if __name__ == "__main__":
    unittest.main()