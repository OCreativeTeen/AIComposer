"""t277: STORY 窗——步数和「共 N 集」之间什么都不放；材料行下面那一行提示跟着选中的东西变，而且在 1000 像素宽时总是一行放得下。"""
import os
import unittest

from gui.dl import material_hint as mh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


PDF = {"kind": "pdf", "path": "a.pdf", "select": "pdf"}
IMG = {"kind": "image", "path": "a.png", "select": "image"}
AUD = {"kind": "audio", "path": "a.mp3", "select": "media"}
VID = {"kind": "video", "path": "a.mp4", "select": "media"}
TRS = {"kind": "transcript", "path": "a.txt", "select": "media"}
AOV = {"kind": "audio", "path": "o.m4a", "select": "media", "program_kind": "audio_overview"}
VOV = {"kind": "video", "path": "o.mp4", "select": "media", "program_kind": "video_overview"}
HOLE = {"kind": "pdf", "path": "", "select": "", "placeholder": True}

# (material_var, 点中的那一行, pdf 用法, 故事对话?) → 状态
CASES = [
    (("analyzed", None, "page", True), "analyzed"),
    (("analyzed", PDF, "page", True), "analyzed"),
    (("pdf", PDF, "page", True), "pdf_page_steps"),
    (("pdf", PDF, "page", False), "pdf_page"),
    (("pdf", PDF, "text", True), "pdf_text"),
    (("pdf", None, "page", True), "pdf_page_steps"),
    (("image", IMG, "page", True), "image"),
    (("media", AUD, "page", True), "audio"),
    (("media", VID, "page", True), "video"),
    (("media", TRS, "page", True), "transcript"),
    (("media", AOV, "page", True), "audio_overview"),
    (("media", VOV, "page", True), "video_overview"),
    (("media", None, "page", True), "none"),
    (("pdf", HOLE, "page", True), "pdf_page_steps"),
    (("media", HOLE, "page", True), "none"),
    (("", None, "page", True), "none"),
    (("pdf", IMG, "page", True), "pdf_page_steps"),  # 点中的那行和现在的材料对不上：按材料来
]


class HintRules(unittest.TestCase):
    def test_state_for_each_selection(self):
        for (mat, entry, mode, dia), want in CASES:
            self.assertEqual(mh.state_for(mat, entry, pdf_mode=mode, dialogue=dia), want, (mat, entry, mode, dia))

    def test_every_state_has_its_own_short_text(self):
        self.assertEqual(len(set(mh.HINTS.values())), len(mh.HINTS))
        for state, text in mh.HINTS.items():
            self.assertNotIn("\n", text, state)
            self.assertLessEqual(len(text), 64, state)
        self.assertIn("步数不用", mh.PDF_PAGE_STEPS)
        for s in ("开始/结束页", "双击查看", "抽图对场景"):
            for t in (mh.PDF_PAGE_STEPS, mh.PDF_PAGE, mh.PDF_TEXT):
                self.assertIn(s, t)
        for s in (mh.PDF_PAGE, mh.PDF_TEXT, mh.NONE, mh.ANALYZED, mh.IMAGE):
            self.assertNotIn("步数", s)
        self.assertIn("拖到这里", mh.NONE)
        self.assertTrue(mh.ANALYZED.startswith("分析报告"))
        self.assertEqual(mh.text_for("???"), mh.NONE)

    def test_fit_text_drops_tail_parts_then_ellipsis(self):
        m = len
        t = "aaaa · bbbb · cccc"
        self.assertEqual(mh.fit_text(t, m, 100), t)
        self.assertEqual(mh.fit_text(t, m, 11), "aaaa · bbbb")
        self.assertEqual(mh.fit_text(t, m, 6), "aaaa")
        self.assertEqual(mh.fit_text(t, m, 3), "aa…")
        self.assertEqual(mh.fit_text(t, m, 0), t)


class EditorSource(unittest.TestCase):
    def setUp(self):
        self.se = _read("gui", "dl", "scene_editor.py").replace("\r\n", "\n")

    def test_nothing_between_steps_and_series(self):
        se = self.se
        blk = se[se.index("step_frm = ttk.Frame(gen_host)"):se.index("series_frm = ttk.Frame(gen_host)")]
        made = [ln.strip() for ln in blk.splitlines() if "(step_frm" in ln or ln.strip() == "step_frm,"]
        self.assertEqual(len(made), 3, made)  # 只有「步数」标签、步数下拉（参数行），然后登记进生成区
        self.assertTrue(made[0].startswith('step_lbl = ttk.Label(step_frm, text="步数")'))
        self.assertEqual(made[1], "step_frm,")
        self.assertIn("step_count_combo = ttk.Combobox(\n                step_frm,", blk)
        self.assertTrue(made[2].startswith('gen_row.add(step_frm, "step"'))
        self.assertEqual(blk.count("ttk."), 3)  # Frame + Label(步数) + Combobox，没有别的控件
        self.assertEqual(blk.count("tk.Label("), 1)
        self.assertNotIn("step_note", se)
        self.assertNotIn("PDF 一页一个场景，步数不用", se)
        sync = se[se.index("def _sync_steps_for_pdf"):se.index("def _sync_episode_enable")]
        self.assertIn('step_count_combo.configure(state="disabled" if off else "readonly")', sync)  # 灰掉照旧
        self.assertNotIn(".pack(", sync)

    def test_hint_line_wiring(self):
        se = self.se
        self.assertIn("material_hint_lbl.pack(fill=tk.X, pady=(0, 2))", se)
        self.assertLess(se.index("material_row.pack(fill=tk.X, pady=(0, 6))"), se.index("material_hint_lbl.pack(fill=tk.X"))
        self.assertEqual(se.count("after=material_hint_lbl)"), 2)
        self.assertNotIn("after=material_row)", se)
        self.assertIn("hint=False,", se)
        self.assertIn("on_focus=lambda _e: _sync_material_hint(),", se)  # 点中一行
        self.assertIn("on_rebuilt=_on_materials_rebuilt,", se)  # 材料变了
        self.assertIn('_hint_sync = scene_ui.get("sync_material_hint")', se[se.index("def _sync_steps_for_pdf"):])  # 叙事方式 / PDF 用法 / 选的材料
        self.assertIn('frm.bind("<Configure>", _sync_material_hint, add="+")', se)  # 窗口宽度
        body = se[se.index("def _sync_material_hint"):se.index('scene_ui["sync_material_hint"] = _sync_material_hint')]
        self.assertIn("material_hint_mod.fit_text(full, fnt.measure, width - 16)", body)
        st = se[se.index("def _material_hint_state"):se.index("def _sync_material_hint")]
        for need in ("material_var.get()", "focused_entry", "pdf_mode=_pdf_mode_now()", '== "dialogue"'):
            self.assertIn(need, st)

    def test_old_long_hint_gone(self):
        mp = _read("gui", "dl", "materials_panel.py")
        self.assertNotIn("单击选作生成材料，双击用默认程序打开", mp)
        self.assertNotIn("PDF 换掉原来的，图片加进列表", mp)


class _Tk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"没有 Tk 显示：{exc}")
        cls.root.attributes("-alpha", 0.0)
        cls.root.geometry("1000x300+0+0")
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:  # noqa: BLE001
            pass


class TkSmoke(_Tk):
    def test_steps_then_series_with_nothing_between_at_1000px(self):
        """按 scene_editor 的做法：步数框里只有「步数」+ 下拉；后面紧接「共 N 集」（只隔 padx 8）。"""
        import tkinter as tk
        from tkinter import ttk

        row = ttk.Frame(self.root)
        row.pack(fill=tk.X)
        self.addCleanup(row.destroy)
        step_frm = ttk.Frame(row)
        ttk.Label(step_frm, text="步数").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Combobox(step_frm, values=["0", "1"], state="disabled", width=3).pack(side=tk.LEFT)
        step_frm.pack(side=tk.LEFT, padx=(0, 8))
        series = ttk.Frame(row)
        ttk.Label(series, text="共").pack(side=tk.LEFT)
        series.pack(side=tk.LEFT, padx=(0, 8))
        self.root.update()
        self.assertEqual(len(step_frm.winfo_children()), 2)
        gap = series.winfo_x() - (step_frm.winfo_x() + step_frm.winfo_width())
        self.assertLessEqual(gap, 8)

    def test_each_hint_fits_one_line_at_1000px(self):
        import tkinter as tk
        import tkinter.font as tkfont
        from tkinter import ttk

        frm = ttk.Frame(self.root, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)
        self.addCleanup(frm.destroy)
        var = tk.StringVar(value="A")
        lbl = ttk.Label(frm, textvariable=var, font=("TkDefaultFont", 8), foreground="gray30", anchor="w")
        lbl.pack(fill=tk.X, pady=(0, 2))
        self.root.update()
        one_line_h = lbl.winfo_reqheight()
        fnt = tkfont.Font(root=frm, font=lbl.cget("font"))
        width = frm.winfo_width() - 16  # 和 scene_editor._sync_material_hint 一样
        self.assertGreater(width, 900)
        for state, full in mh.HINTS.items():
            with self.subTest(state=state):
                var.set(mh.fit_text(full, fnt.measure, width))
                self.root.update()
                self.assertEqual(var.get(), full)  # 1000 像素宽时不用缩短
                self.assertLessEqual(fnt.measure(var.get()), lbl.winfo_width())
                self.assertEqual(lbl.winfo_reqheight(), one_line_h)  # 一行
        # 窄窗口：缩短后照样一行、放得下
        self.root.geometry("420x300+0+0")
        self.root.update()
        w2 = frm.winfo_width() - 16
        for state, full in mh.HINTS.items():
            with self.subTest(narrow=state):
                var.set(mh.fit_text(full, fnt.measure, w2))
                self.root.update()
                self.assertLessEqual(fnt.measure(var.get()), w2)
                self.assertEqual(lbl.winfo_reqheight(), one_line_h)
        self.root.geometry("1000x300+0+0")
        self.root.update()

    def test_materials_panel_short_hint_and_focus_callback(self):
        from gui.dl.materials_panel import MaterialsPanel

        focused, selected = [], []
        ents = [dict(TRS), dict(HOLE)]
        p = MaterialsPanel(self.root, get_entries=lambda: ents, on_select=selected.append, on_copy=lambda e: None,
                           build_menu=lambda m, e: None, hint=False, on_focus=focused.append)
        p.pack()
        self.addCleanup(p.destroy)
        p.refresh()
        self.root.update()
        self.assertIsNone(p.hint_label)
        p._click(ents[0])
        self.assertEqual(focused[-1]["kind"], "transcript")
        self.assertEqual(selected[-1]["kind"], "transcript")
        p._last_click = (None, 0.0)
        p._click(ents[1])  # 空位：不选，但提示要知道点了它
        self.assertTrue(focused[-1].get("placeholder"))
        self.assertEqual(len(selected), 1)
        plain = MaterialsPanel(self.root, get_entries=lambda: [], on_select=lambda e: None, on_copy=lambda e: None,
                               build_menu=lambda m, e: None)
        self.addCleanup(plain.destroy)
        self.assertEqual(plain.hint_label.cget("text"), mh.NONE)


if __name__ == "__main__":
    unittest.main()