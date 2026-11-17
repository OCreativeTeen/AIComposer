# -*- coding: utf-8 -*-
"""t275: PDF 生成场景——(1) 一页一个场景时第 k 页直接对第 k 场的配图（不用 Strata 判断），「当文字内容」不自动配图；
(2) 自动配图只剩这一条直接对应 + 视频取帧，PDF 的 Strata「图片对场景」只在手动（PDF 资源右键）时跑；
(3) 生成前问用户：一页一个场景 / 把 PDF 当文字内容（文字走和分析内容同一条场景提示词路，步数照用）。

纯逻辑在临时目录里测；要真 downloader / Tk 的检查在子进程里跑（假 Strata / 假 Gemini / 假弹窗），只读。"""
import json
import os
import shutil
import tempfile
import unittest

import fitz

from tests.test_t271_no_pdf_split_scene_gate import _read, make_pdf
import subprocess
import sys


def _real(code, timeout=120):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-W", "ignore", "-c", "import warnings\nwarnings.filterwarnings('ignore')\n" + code],
                          cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=timeout)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-3000:])
    return json.loads(proc.stdout.strip().splitlines()[-1])
from tests.test_t272_pdf_scenes_cast import _FAKE_SELF
from utility import material_image_matcher as mim

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t275_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pdf = make_pdf(os.path.join(self.tmp, "book.pdf"), 6, images=True)


class DirectPageMapping(Tmp):
    def test_page_k_goes_to_scene_k_without_strata(self):
        def boom(*a, **k):
            raise AssertionError("Strata / 看图不该被调用")

        saved = (mim.describe_image, mim.make_strata_judge, mim.run_match)
        mim.describe_image, mim.make_strata_judge, mim.run_match = boom, boom, boom
        self.addCleanup(lambda: setattr(mim, "describe_image", saved[0]))
        self.addCleanup(lambda: setattr(mim, "make_strata_judge", saved[1]))
        self.addCleanup(lambda: setattr(mim, "run_match", saved[2]))
        logs = []
        scenes = [{"caption": str(i)} for i in range(3)]
        out_dir = os.path.join(self.tmp, "pages")
        m = mim.direct_page_matches(self.pdf, scenes, pages=(2, 4), out_dir=out_dir, log=logs.append)
        self.assertEqual(sorted(m), [0, 1, 2])
        self.assertEqual([m[k][0]["page"] for k in range(3)], [2, 3, 4])  # 页码是原文档的页码
        for k in range(3):
            p = m[k][0]["path"]
            self.assertTrue(os.path.isfile(p), p)
            self.assertEqual(os.path.basename(p), "p%03d.png" % (k + 2))
            self.assertEqual(m[k][0]["source"], "pdf")
        # 写回场景：和手动「图片对场景」同一个 ref_images 字段
        cur = [dict(s) for s in scenes]
        added, lost = mim.apply_matches(cur, scenes, m)
        self.assertEqual((added, lost), (3, 0))
        self.assertEqual(cur[2]["ref_images"][0]["page"], 4)
        self.assertTrue(any("直接对应" in x for x in logs))

    def test_whole_pdf_when_no_range_and_count_mismatch_is_skipped(self):
        logs = []
        out_dir = os.path.join(self.tmp, "pages")
        full = mim.direct_page_matches(self.pdf, [{} for _ in range(6)], out_dir=out_dir, log=logs.append)
        self.assertEqual(sorted(full), [0, 1, 2, 3, 4, 5])
        off = mim.direct_page_matches(self.pdf, [{} for _ in range(5)], pages=(1, 6), out_dir=out_dir, log=logs.append)
        self.assertEqual(off, {})  # 6 页 5 场：页和场景对不上，不乱配
        self.assertTrue(any("对不上" in x and "图片对场景" in x for x in logs))

    def test_auto_ref_matches_direct_never_runs_the_matcher(self):
        seen = []
        direct = lambda path, scenes, **kw: seen.append(("direct", kw.get("pages"))) or {0: ["d"]}
        pdf_run = lambda *a, **k: seen.append(("strata",)) or {"images": ["x"], "matches": {0: ["s"]}}
        r = mim.auto_ref_matches("pdf", self.pdf, [{}], pdf_run=pdf_run, pdf_direct=direct, pages=(2, 3), direct=True)
        self.assertEqual(r, {0: ["d"]})
        self.assertEqual(seen, [("direct", (2, 3))])
        seen.clear()  # 不带 direct = 手动那条（抽图 + Strata）原样
        r = mim.auto_ref_matches("pdf", self.pdf, [{}], pdf_run=pdf_run, pdf_direct=direct)
        self.assertEqual((r, seen), ({0: ["s"]}, [("strata",)]))

    def test_start_auto_attach_direct_commits_refs(self):
        pages = mim.render_page_images(self.pdf, (1, 2), os.path.join(self.tmp, "pg"), log=lambda *_: None)
        orig = mim.render_page_images
        mim.render_page_images = lambda *a, **k: pages
        self.addCleanup(lambda: setattr(mim, "render_page_images", orig))
        editor = [{"caption": "a"}, {"caption": "b"}]
        done = []
        ok = mim.start_auto_attach(lambda ms, fn: fn(), "pdf", self.pdf, editor, get_current=lambda: editor,
                                   commit=lambda cur, added: done.append(added), log=lambda *_: None,
                                   thread=False, pages=(1, 2), direct=True)
        self.assertTrue(ok)
        self.assertEqual(done, [2])
        self.assertEqual([s["ref_images"][0]["page"] for s in editor], [1, 2])


class AutoTriggers(Tmp):
    def test_text_mode_pdf_never_starts_auto_attach_and_per_page_goes_direct(self):
        res = _real(r'''
import json, sys
sys.path.insert(0, %r)
import gui.downloader as dl
import utility.material_image_matcher as mim
from utility import pdf_range as pr
pdf = %r
seen = []
mim.start_auto_attach = lambda after, kind, path, scenes, **kw: seen.append([kind, kw.get("pages"), kw.get("direct")])
class App: root = type("R", (), {"after": staticmethod(lambda *a: None)})()
def run(kind, per_page):
    vd = {"scene_source_path": pdf, "scene_content": [{"caption": "a"}]}
    pr.set_range(vd, pdf, 2, 4); vd[pr.SOURCE_RANGE_KEY] = pr.source_range_record(vd, pdf)
    dl._start_scene_auto_ref_images(App(), None, vd, vd["scene_content"], kind, lambda t: None, lambda: "", lambda *a, **k: True, pdf_per_page=per_page)
run("pdf", True); run("pdf", False); run("video", False); run("audio", False); run("", False)
print(json.dumps(seen))
''' % (ROOT, self.pdf))
        # PDF：一页一个场景 → 启动一次（带记下的页范围 + 直接对应）；当文字内容 → 不启动。
        # 视频 / 其他来源照旧交给 start_auto_attach（这里是假的，真的那个只收 pdf / video）
        self.assertEqual([e for e in res if e[0] == "pdf"], [["pdf", [2, 4], True]])
        self.assertEqual([e for e in res if e[0] == "video"], [["video", None, None]])  # 视频取帧不受影响，不带 direct

    def test_only_one_auto_trigger_remains_and_it_is_not_strata(self):
        dl = _read("gui", "downloader.py")
        self.assertEqual(dl.count("_start_scene_auto_ref_images("), 2)  # 定义 + 唯一的调用（生成场景保存之后）
        self.assertIn('pdf_per_page=llm_api.LLMApi._attachment_kind((attachment or "").strip()) == "pdf"', dl)
        self.assertIn('extra["direct"] = True', dl)
        body = dl[dl.index("def _start_scene_auto_ref_images"):dl.index("def apply_scene_content_from_editor_text")]
        self.assertIn("if str(src_kind or \"\").strip().lower() == \"pdf\" and not pdf_per_page:", body)
        mm = _read("utility", "material_image_matcher.py")
        auto = mm[mm.index("def auto_ref_matches"):mm.index("def start_auto_attach")]
        self.assertIn("if kind == \"pdf\" and direct:", auto)
        # 手动「图片对场景」（PDF 资源右键）还在，而且还是抽图 + Strata
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("def _material_image_match(entry: dict, source: str)", se)
        self.assertIn("run_match", se[se.index("def _material_image_match"):se.index("def _material_image_match") + 6000])


class AskDialog(unittest.TestCase):
    def test_dialog_text_buttons_defaults_and_no_text_guard(self):
        res = _real(r'''
import json, sys
sys.path.insert(0, %r)
import tkinter as tk, tkinter.ttk as ttk, tkinter.messagebox as mb
from gui.dl import pdf_scene_mode as m
root = tk.Tk(); root.withdraw()
warns = []
mb.showwarning = lambda *a, **k: warns.append(a[1])
def walk(w):
    yield w
    for c in w.winfo_children(): yield from walk(c)
def key(t, name):
    t.focus_force(); t.update(); t.event_generate(name)
def drive(actions, **kw):
    box = {}
    def go():
        tops = [w for w in walk(root) if isinstance(w, tk.Toplevel)]
        box["t"] = tops[0]
        box["texts"] = [str(w.cget("text")) for w in walk(tops[0]) if w.winfo_class() in ("TButton", "TLabel")]
        box["title"] = tops[0].title()
        actions(tops[0])
    def bail():  # 保险：任何情况下 3 秒后关掉弹窗，不让测试挂住
        for w in list(walk(root)):
            if isinstance(w, tk.Toplevel):
                w.destroy()
    root.after(150, go)
    root.after(3000, bail)
    v = m.ask_pdf_scene_mode(root, pdf_name="book.pdf", range_text="第 3–17 页", pages=15, **kw)
    return v, box
def btn(top, text):
    return [w for w in walk(top) if w.winfo_class() == "TButton" and str(w.cget("text")) == text][0]
out = {}
v, box = drive(lambda t: btn(t, "一页一个场景").invoke(), text_chars=1200, last="text"); out["page"] = v; out["texts"] = box["texts"]; out["title"] = box["title"]
v, _ = drive(lambda t: btn(t, "把 PDF 当文字内容").invoke(), text_chars=1200); out["text"] = v
v, _ = drive(lambda t: btn(t, "取消").invoke(), text_chars=1200); out["cancel"] = v
out["defaults"] = [m.default_mode("text", True), m.default_mode("page", True), m.default_mode("text", False), m.default_mode("", True)]
def no_text(t):
    btn(t, "把 PDF 当文字内容").invoke()   # 没文字：弹提示、窗口还在
    root.after(50, lambda: btn(t, "一页一个场景").invoke())
v, box = drive(no_text, text_chars=0, last="text"); out["no_text"] = v; out["no_text_texts"] = box["texts"]; out["warns"] = warns
print(json.dumps(out, ensure_ascii=False))
root.destroy()
''' % ROOT)
        self.assertEqual(res["title"], "场景生成 · PDF")
        for want in ("这份 PDF 要怎么生成场景？", "一页一个场景", "把 PDF 当文字内容", "取消"):
            self.assertIn(want, res["texts"])
        self.assertTrue(any("15 页 = 15 场" in t and "步数不用" in t for t in res["texts"]))
        self.assertTrue(any("提取第 3–17 页的文字" in t and "步数照用" in t for t in res["texts"]))
        self.assertEqual((res["page"], res["text"], res["cancel"]), ("page", "text", ""))
        self.assertEqual(res["defaults"], ["text", "page", "page", "page"])  # 默认选中上一次的；没文字时是一页一个场景
        self.assertIn('box.bind("<Return>", lambda _e: pick(default))', _read("gui", "dl", "pdf_scene_mode.py"))
        self.assertIn('box.bind("<Escape>", lambda _e: box.destroy())', _read("gui", "dl", "pdf_scene_mode.py"))
        self.assertEqual(res["no_text"], "page")
        self.assertEqual(len(res["warns"]), 1)
        self.assertIn("提取不到文字", res["warns"][0])
        self.assertIn("请改选「一页一个场景」", res["warns"][0])
        self.assertTrue(any("建议选「一页一个场景」" in t for t in res["no_text_texts"]))

    def test_remembered_mode_defaults_to_page(self):
        res = _real(
            'import json\nfrom gui.dl import pdf_scene_mode as m\n'
            'vd = {}\na = m.remembered_mode(vd)\nm.remember_mode(vd, "text")\nb = m.remembered_mode(vd)\n'
            'm.remember_mode(vd, "bogus")\nprint(json.dumps([a, b, m.remembered_mode(vd), vd[m.MODE_KEY]]))')
        self.assertEqual(res, ["page", "text", "page", "page"])


class TextModeUsesAnalyzePromptPath(unittest.TestCase):
    def test_same_prompt_as_analyzed_content_and_steps_apply(self):
        res = _real(_FAKE_SELF + r'''
cast = "人物1：man/youth/chinese/阿明 | 人物2：woman/youth/chinese/小美"
TXT = "第一页的字。\n\n第二页的字。"
seen = []
def gen(prompt, sys_, expect_list=True, attachment=None, extra=None):
    seen.append((prompt, attachment))
    return [{"visual": "v", "actor": "", "speaking": ""}]
f.llm_api_manual = type("M", (), {"generate_json": staticmethod(gen)})()
def run(steps, **kw):
    vd = dict({"story_actors": cast}, **kw.pop("vd", {}))
    G(f, vd, "故事对话", prompt_params={"steps": steps, "episodes": 1}, text_backend="grok", **kw)
    return seen[-1]
via_override = run(4, content_override=TXT, vd={"analyzed_content": "别的"})          # 当文字内容：{content} = 选中页文字
via_analyzed = run(4, vd={"analyzed_content": TXT})                                    # 分析内容本身
steps0 = run(0, content_override=TXT, vd={"analyzed_content": "别的"})
print(json.dumps({"same": via_override[0] == via_analyzed[0], "att": via_override[1], "has_txt": "第二页的字" in via_override[0],
                  "steps_apply": via_override[0] != steps0[0]}, ensure_ascii=False))
shutil.rmtree(tmp, True)
''')
        self.assertTrue(res["same"])        # 同一个提示词构建器、同一条路
        self.assertTrue(res["has_txt"])
        self.assertIsNone(res["att"])       # 文字模式不带 PDF 附件
        self.assertTrue(res["steps_apply"])  # 步数照用（不是一页一场）

    def test_extract_text_of_the_ranged_pdf(self):
        tmp = tempfile.mkdtemp(prefix="t275_txt_")
        self.addCleanup(shutil.rmtree, tmp, True)
        from utility import pdf_scene_pages as psp

        path = os.path.join(tmp, "t.pdf")
        doc = fitz.open()
        for s in ("alpha page one", "", "gamma page three"):
            pg = doc.new_page()
            if s:
                pg.insert_text((72, 100), s)
        doc.save(path)
        doc.close()
        text, n, with_text = psp.pdf_text_content(path)
        self.assertEqual((n, with_text), (3, 2))
        self.assertEqual(text, "alpha page one\n\ngamma page three")
        blank = os.path.join(tmp, "b.pdf")
        d2 = fitz.open(); d2.new_page(); d2.save(blank); d2.close()
        self.assertEqual(psp.pdf_text_content(blank), ("", 1, 0))


class SceneEditorWiring(unittest.TestCase):
    def setUp(self):
        self.se = _read("gui", "dl", "scene_editor.py")

    def test_generate_asks_first_and_text_mode_is_the_analyze_path(self):
        se = self.se
        body = se[se.index("def on_smart_generate"):se.index("def on_persist_keep_open")]
        self.assertIn("pdf_mode_mod.ask_pdf_scene_mode(", body)
        self.assertLess(body.index("pdf_mode_mod.ask_pdf_scene_mode("), body.index("_ask_scene_text_backend("))
        self.assertIn("if not _mode:\n                                return  # 取消 / Esc", body.replace("\r\n", "\n"))
        self.assertIn("pdf_mode_mod.remember_mode(video_detail, _mode)", body)
        self.assertIn("_ptext, _pn, _pnt, _perr = _pdf_text_content_now()", body)
        # 文字模式：{content} = 选中页的文字，当 analyzed 材料，不带附件；来源仍记 PDF + 页范围
        self.assertIn("override = _ptext", body)
        self.assertIn('kind = "analyzed"', body)
        self.assertIn("if not pdf_text_mode:\n                                    attachment = _eff_pdf", body.replace("\r\n", "\n"))
        self.assertIn("if kind == \"pdf\" or pdf_text_mode:\n                            source_kind = project_manager.SCENE_SOURCE_PDF", body.replace("\r\n", "\n"))
        # 后端窗：文字模式没有附件 → DeepSeek / Strata 文字都可选；一页一个场景 → t272 那样
        self.assertIn("text_only_blocked=self.llm_api.__class__._attachment_kind(attachment or \"\")", body)

    def test_steps_note_only_in_per_page_mode(self):
        se = self.se
        ign = se[se.index("def _steps_ignored_now"):se.index("def _sync_steps_for_pdf")]
        self.assertIn("_pdf_mode_now() == pdf_mode_mod.MODE_PAGE", ign)
        self.assertIn("_sync_pdf_steps()", se[se.index("pdf_mode_mod.remember_mode(video_detail, _mode)"):][:900])
        # t277: 不再是步数旁边的小字，改成材料行下面的提示行（只在故事对话 + 一页一个场景时说「步数不用」）
        from gui.dl import material_hint as mh
        self.assertEqual(mh.state_for("pdf", {"kind": "pdf", "select": "pdf"}, pdf_mode="page", dialogue=True), "pdf_page_steps")
        self.assertEqual(mh.state_for("pdf", {"kind": "pdf", "select": "pdf"}, pdf_mode="text", dialogue=True), "pdf_text")
        self.assertNotIn("步数不用", mh.PDF_TEXT)
        self.assertNotIn("step_note", se)
        # 手动复制提示词：文字模式 = 分析内容那条路
        cp = se[se.index("def _scene_prompt_text_now"):se.index("def _copy_selected_scene_prompt")]
        self.assertIn("elif kind == \"pdf\" and _pdf_mode_now() == pdf_mode_mod.MODE_TEXT:", cp)

    def test_dialog_module_texts(self):
        mod = _read("gui", "dl", "pdf_scene_mode.py")
        for s in ('TITLE = "场景生成 · PDF"', 'QUESTION = "这份 PDF 要怎么生成场景？"', 'BTN_PAGE = "一页一个场景"',
                  'BTN_TEXT = "把 PDF 当文字内容"', 'BTN_CANCEL = "取消"', 'MODE_KEY = "scene_pdf_mode"'):
            self.assertIn(s, mod)


if __name__ == "__main__":
    unittest.main()