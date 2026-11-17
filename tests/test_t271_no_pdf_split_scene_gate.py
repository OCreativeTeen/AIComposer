# -*- coding: utf-8 -*-
"""t271: 视频生成不再从 PDF 拆页建场景图；没有有效的场景 JSON 不能创建 / 打开项目；PDF 页范围的 4 个缺口。

纯逻辑在临时目录里测；要真 config / project_manager / magic_workflow / GUI_wf 的检查在子进程里跑
（messagebox / 启动进程都换成假的），只读，不碰任何项目 / 列表数据。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import fitz

from utility import pdf_range as pr
from utility import program_media as pm
from utility import story_scenes as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def make_pdf(path, pages, *, images=False):
    from io import BytesIO

    from PIL import Image

    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        if images:
            buf = BytesIO()
            Image.new("RGB", (240, 320), (i * 9 % 256, 100, 200 - i)).save(buf, "PNG")
            page.insert_image(page.rect, stream=buf.getvalue())
        page.insert_text((40, 60), f"page {i + 1}")
    doc.save(path)
    doc.close()
    return path


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t271_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write_json(self, name, data, raw=None):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(raw if raw is not None else json.dumps(data, ensure_ascii=False))
        return p


GOOD = [{"caption": "开场", "visual": "a road", "speaking": "hello"}, {"caption": "第二场", "voiceover": "x"}]


class ValidScenes(Tmp):
    def test_scene_content_rules(self):
        self.assertEqual(ss.scene_content_problem(GOOD), "")
        self.assertEqual(ss.scene_content_problem(json.dumps(GOOD)), "")  # JSON 文本也算
        self.assertEqual(ss.scene_content_problem([{"actor": "A"}]), "")
        self.assertEqual(ss.scene_content_problem([{"title": "t"}]), "")
        for bad in (None, "", "  ", [], "[]"):
            self.assertIn("空的", ss.scene_content_problem(bad), repr(bad))
        self.assertIn("合法的 JSON", ss.scene_content_problem("not json"))
        self.assertIn("必须是数组", ss.scene_content_problem({"caption": "x"}))
        self.assertIn("必须是数组", ss.scene_content_problem(5))
        self.assertIn("第 2 个场景不是对象", ss.scene_content_problem([GOOD[0], "oops"]))
        self.assertIn("第 1 场没有任何内容", ss.scene_content_problem([{}]))
        self.assertIn("第 2 场没有任何内容", ss.scene_content_problem([GOOD[0], {"caption": " ", "visual": "", "speaking": None}]))
        # 以前只看“非空”：随便一段文字 / 一个空对象都算有场景
        self.assertNotEqual(ss.scene_content_problem("随便一段话"), "")
        self.assertNotEqual(ss.scene_content_problem([{}]), "")

    def test_existing_scenes_json_decides_when_present(self):
        ok = self.write_json("ok.json", GOOD)
        self.assertEqual(ss.scenes_file_problem(ok), "")
        self.assertEqual(ss.open_problem({"scene_content": []}, scenes_path=ok), "")  # scenes.json 有效 = 能开，不再看 scene_content
        broken = self.write_json("broken.json", None, raw="{oops")
        empty = self.write_json("empty.json", [])
        notlist = self.write_json("notlist.json", {"a": 1})
        for p, word in ((broken, "读不出来"), (empty, "一场都没有"), (notlist, "不是 JSON 数组")):
            self.assertIn(word, ss.open_problem({"scene_content": GOOD}, scenes_path=p))  # 有 scenes.json 就只看它
            self.assertIn(p, ss.scenes_file_problem(p))
        self.assertEqual(ss.scenes_file_problem(os.path.join(self.tmp, "nope.json")), "")  # 不存在：交给 scene_content

    def test_open_without_scenes_json_uses_scene_content(self):
        missing = os.path.join(self.tmp, "scenes.json")
        self.assertEqual(ss.open_problem({"scene_content": GOOD}, scenes_path=missing), "")
        self.assertEqual(ss.open_problem({}, {"scene_content": GOOD}, scenes_path=missing), "")  # 配置里没有，列表行里有
        self.assertIn("空的", ss.open_problem({"scene_content": []}, {}, scenes_path=missing))
        self.assertIn("空的", ss.open_problem(None, None, scenes_path=missing))
        self.assertIn("第 1 场没有任何内容", ss.open_problem({"scene_content": [{}]}, scenes_path=missing))

    def test_user_visible_messages(self):
        self.assertEqual(ss.BLOCK_CREATE_TITLE, "不能创建项目")
        self.assertEqual(ss.BLOCK_OPEN_TITLE, "不能打开项目")
        c = ss.create_message("场景 JSON 是空的（还没有生成场景）")
        self.assertEqual(c, "不能创建项目：这个故事还没有有效的场景 JSON。\n\n原因：场景 JSON 是空的（还没有生成场景）\n\n"
                            "请先回到预览窗口（STORY），按「场景生成」生成场景（或在「场景」里贴入有效的场景 JSON），保存后再创建项目。")
        o = ss.open_message("X")
        self.assertEqual(o, "不能打开项目：这个故事还没有有效的场景 JSON。\n\n原因：X\n\n"
                            "请先回到预览窗口（STORY），按「场景生成」生成场景，保存后再打开 视频生成。")


class PdfSplitRemoved(unittest.TestCase):
    def test_first_open_never_turns_pdf_pages_into_scene_images(self):
        res = _real(r'''
import json, os, sys, tempfile, fitz
sys.path.insert(0, %r)
import magic_workflow, project_manager
MW = magic_workflow.MagicWorkflow
tmp = tempfile.mkdtemp(prefix="t271_")
pdf = os.path.join(tmp, "m.pdf")
doc = fitz.open()
for i in range(3): doc.new_page().insert_text((40, 60), "p%%d" %% i)
doc.save(pdf); doc.close()
class F: pass
calls = []
def boom(name):
    def f(*a, **k): calls.append(name); raise AssertionError(name)
    return f
f = F(); f.scenes = [{"caption": "c%%d" %% i} for i in range(3)]; f._scene_source_kind = "pdf"; f._scene_source_path = pdf
f._seed_cover_override = ""
f._source_warning = boom("warning")
f.export_pdf_pages_to_group = boom("export_pdf_pages_to_group")
f._pdf_pages_to_images = boom("_pdf_pages_to_images")
f.ffmpeg_processor = None
before = json.dumps(f.scenes, ensure_ascii=False)
project_manager.PROJECT_CONFIG = {"slide": [pdf], "pdf_page_ranges": {}, "cover_image": []}
MW._apply_cover_media_to_scenes(f, [])
out = {"calls": calls, "unchanged": json.dumps(f.scenes, ensure_ascii=False) == before,
       "gone": [n for n in ("_copy_slide_pdf_into_episode", "_stamp_episode_folder_to_pdf") if hasattr(MW, n)],
       "kept": [n for n in ("export_pdf_pages_to_group", "_pdf_pages_to_images", "_source_warning", "_apply_cover_media_to_scenes") if hasattr(MW, n)]}
print(json.dumps(out))
''' % ROOT)
        self.assertEqual(res["calls"], [])
        self.assertTrue(res["unchanged"])
        self.assertEqual(res["gone"], [])
        self.assertEqual(len(res["kept"]), 4)

    def test_source_has_no_pdf_to_scene_path_left(self):
        mw = _read("magic_workflow.py")
        body = mw[mw.index("def _apply_cover_media_to_scenes"):mw.index("def _seed_cover_path")]
        for needle in ("export_pdf_pages_to_group", "_copy_slide_pdf_into_episode", "effective_pdf", "_pdf_page_count",
                       "_stamp_episode_folder_to_pdf", "get_primary_program_media"):
            self.assertNotIn(needle, body, needle)
        self.assertNotIn("def _copy_slide_pdf_into_episode", mw)
        self.assertNotIn("def _stamp_episode_folder_to_pdf", mw)
        self.assertIn("export_pdf_pages_to_group", mw)  # 手动「导入 PDF」还在用

    def test_load_scenes_refuses_to_create_a_project_without_scenes(self):
        res = _real(r'''
import json, os, sys, tempfile
sys.path.insert(0, %r)
import config, magic_workflow, project_manager
from utility import story_scenes
tmp = tempfile.mkdtemp(prefix="t271_")
config.get_scenes_path = lambda pid: os.path.join(tmp, "scenes.json")
class F: pass
f = F(); f.pid = "p_t271"; f.scenes = [{"caption": "old"}]
out = {}
for name, sc in (("empty", []), ("junk", "随便一段话"), ("hollow", [{}])):
    project_manager.PROJECT_CONFIG = {"scene_content": sc, "channel": "x"}
    try:
        magic_workflow.MagicWorkflow.load_scenes(f); out[name] = "no error"
    except story_scenes.NoValidScenesError as e:
        out[name] = str(e)[:30]
print(json.dumps(out, ensure_ascii=False))
''' % ROOT)
        for v in res.values():
            self.assertTrue(v.startswith("不能打开项目"), res)


class Gates(Tmp):
    def test_downloader_create_check_is_strict(self):
        res = _real(r'''
import json, sys
sys.path.insert(0, %r)
from gui.downloader import _video_detail_can_create_project as can
good = [{"caption": "a", "visual": "v"}]
print(json.dumps([can({"scene_content": good}), can({"scene_content": json.dumps(good)}), can({"scene_content": "随便一段话"}),
                  can({"scene_content": [{}]}), can({"scene_content": []}), can({}), can(None)]))
''' % ROOT)
        self.assertEqual(res, [True, True, False, False, False, False, False])

    def test_create_project_with_initial_raw_blocks_with_the_message(self):
        res = _real(r'''
import json, sys
sys.path.insert(0, %r)
import project_manager as pm
from tkinter import messagebox
from utility import story_scenes as ss
shown = []
messagebox.showerror = lambda t, m, **k: shown.append([t, m])
class Reached(Exception): pass
def dlg(*a, **k): raise Reached()
pm.ProjectSelectionDialog = dlg
def call(sc):
    try:
        return list(pm.create_project_with_initial_raw(None, "ch", "tw", "n", "v", "", sc, "c", "s", []))
    except Reached:
        return "reached dialog"
out = {"bad": [call([]), call("随便一段话"), call([{}])], "good": call([{"caption": "a", "visual": "v"}]), "shown": shown}
print(json.dumps(out, ensure_ascii=False))
''' % ROOT)
        self.assertEqual(res["bad"], [["cancel", None]] * 3)
        self.assertEqual(res["good"], "reached dialog")
        self.assertEqual(len(res["shown"]), 3)  # 以前这里是悄悄取消
        for title, msg in res["shown"]:
            self.assertEqual(title, "不能创建项目")
            self.assertTrue(msg.startswith("不能创建项目：这个故事还没有有效的场景 JSON。\n\n原因："))
            self.assertTrue(msg.endswith("保存后再创建项目。"))

    def test_project_selection_dialog_create_and_open(self):
        res = _real(r'''
import json, os, sys, tempfile
sys.path.insert(0, %r)
import config, project_manager as pm
from tkinter import messagebox
shown = []
messagebox.showerror = lambda t, m, **k: shown.append([t, m])
tmp = tempfile.mkdtemp(prefix="t271_")
config.get_scenes_path = lambda pid: os.path.join(tmp, pid, "scenes.json")
class Fake: pass
class Tree:
    def selection(self): return ["i"]
    def item(self, i): return {"tags": ["cfgfile"]}
class CM:
    def __init__(self, cfg): self.cfg = cfg
    def load_project_config(self, f): return self.cfg
def open_with(cfg):
    d = Fake(); d.project_tree = Tree(); d.config_manager = CM(cfg); d.story_result = {}; d.dialog = Fake(); d.dialog.destroyed = False
    d.dialog.destroy = lambda: setattr(d.dialog, "destroyed", True); d.selected_config = None
    pm.ProjectConfigManager.set_global_config = staticmethod(lambda c: None)
    pm.ProjectSelectionDialog.open_selected(d)
    return [d.dialog.destroyed, d.story_result.get("action"), d.selected_config is None]
out = {"open_bad": open_with({"pid": "pA", "scene_content": []}),
       "open_good": open_with({"pid": "pB", "scene_content": [{"caption": "a"}]})}
out["open_shown"] = list(shown); shown.clear()
d = Fake(); d.story_result = {"scene_content": [{}]}; d._form_parent = None; d.parent = None
pm.ProjectSelectionDialog.create_new_project(d)
out["create_shown"] = list(shown)
print(json.dumps(out, ensure_ascii=False))
''' % ROOT)
        self.assertEqual(res["open_bad"], [False, None, True])      # 留在列表里，没有关窗口
        self.assertEqual(res["open_good"], [True, "open", False])
        self.assertEqual(len(res["open_shown"]), 1)
        self.assertEqual(res["open_shown"][0][0], "不能打开项目")
        self.assertIn("原因：场景 JSON 是空的", res["open_shown"][0][1])
        self.assertEqual(len(res["create_shown"]), 1)
        self.assertEqual(res["create_shown"][0][0], "不能创建项目")
        self.assertIn("第 1 场没有任何内容", res["create_shown"][0][1])

    def test_launchers_gate_before_starting_the_workflow_process(self):
        res = _real(r'''
import json, os, sys, tempfile
sys.path.insert(0, %r)
import config, project_manager as pm
import gui.dl.workflow_launch as wl
from tkinter import messagebox
shown, started = [], []
messagebox.showerror = lambda t, m, **k: shown.append([t, m])
tmp = tempfile.mkdtemp(prefix="t271_")
config.get_scenes_path = lambda pid: os.path.join(tmp, pid, "scenes.json")
wl._focus_open_workflow = lambda pid="": False
wl._watch_workflow_launch = lambda *a, **k: None
class P:
    def poll(self): return None
wl.subprocess.Popen = lambda cmd, **k: (started.append(cmd[2:]), P())[1]
rows = [{"id": "r_bad", "project_profile": {"pid": "pBad"}, "scene_content": []},
        {"id": "r_good", "project_profile": {"pid": "pGood2"}, "scene_content": [{"caption": "a", "visual": "v"}]}]
lst = os.path.join(tmp, "list.json")
json.dump(rows, open(lst, "w", encoding="utf-8"), ensure_ascii=False)
pm.load_project_config_by_pid = lambda pid: {"pid": pid, "scene_content": rows[0]["scene_content"] if pid == "pBad" else rows[1]["scene_content"]}
out = {}
out["pid_bad"] = [wl._launch_gui_wf_open_pid("pBad"), len(started), len(shown)]
out["pid_good"] = [wl._launch_gui_wf_open_pid("pGood"), len(started), len(shown)]
shown.clear(); started.clear()
out["json_bad"] = [wl._launch_gui_wf_from_list_json(lst, 0), len(started), len(shown), shown[0][0] if shown else ""]
out["json_good"] = [wl._launch_gui_wf_from_list_json(lst, 1), len(started), len(shown)]
print(json.dumps(out, ensure_ascii=False))
''' % ROOT)
        self.assertEqual(res["pid_bad"], [True, 0, 1])    # 已经提示；返回 True，调用方不再试别的启动方式（不会弹两次）
        self.assertEqual(res["pid_good"], [True, 1, 1])
        self.assertEqual(res["json_bad"], [True, 0, 1, "不能打开项目"])
        self.assertEqual(res["json_good"], [True, 1, 1])

    def test_workflow_process_refuses_to_open_without_scenes(self):
        """GUI_wf 进程里的最后一道：--open-pid / --open-from-list-json / 选择项目 都走 WorkflowGUI.__init__。"""
        res = _real(r'''
import json, os, sys, tempfile
sys.path.insert(0, %r)
import config, project_manager
import GUI_wf
from tkinter import messagebox
shown = []
messagebox.showerror = lambda t, m, **k: shown.append([t, m])
tmp = tempfile.mkdtemp(prefix="t271_")
config.get_scenes_path = lambda pid: os.path.join(tmp, pid, "scenes.json")
GUI_wf.llm_api.LLMApi = lambda *a, **k: object()
GUI_wf.pygame.mixer.init = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no audio"))
cfg = {"pid": "pT271", "scene_content": []}
GUI_wf.ProjectConfigManager.load_config = lambda self, pid: cfg
GUI_wf.ProjectConfigManager.set_global_config = staticmethod(lambda c: setattr(project_manager, "PROJECT_CONFIG", c))
root = GUI_wf.TkinterDnD.Tk(); root.withdraw()
w = GUI_wf.WorkflowGUI.__new__(GUI_wf.WorkflowGUI)
GUI_wf.WorkflowGUI.__init__(w, root, initial_pid="pT271")
try: alive = bool(root.winfo_exists())
except Exception: alive = False
print(json.dumps({"shown": shown, "tasks_built": hasattr(w, "tasks"), "root_alive": alive}, ensure_ascii=False))
''' % ROOT)
        self.assertEqual(len(res["shown"]), 1)
        self.assertEqual(res["shown"][0][0], "不能打开项目")
        self.assertIn("原因：场景 JSON 是空的", res["shown"][0][1])
        self.assertFalse(res["tasks_built"])   # 窗口没往下建
        self.assertFalse(res["root_alive"])

    def test_every_gate_is_wired_in_source(self):
        dlg = _read("gui", "dl", "channel_videos_dialog.py")
        self.assertIn("story_scenes.create_problem(scene_content)", dlg)
        self.assertEqual(dlg.count("story_scenes.create_message("), 3)
        self.assertNotIn("scene_content 须为有效 JSON array", dlg)
        pmgr = _read("project_manager.py")
        self.assertIn("story_scenes.project_open_problem(self.selected_config)", pmgr)
        self.assertIn("story_scenes.create_problem(scene_content)", pmgr)
        self.assertIn("story_scenes.create_problem(sc)", pmgr)
        wf = _read("GUI_wf.py")
        self.assertIn("story_scenes.project_open_problem(project_manager.PROJECT_CONFIG", wf)
        lau = _read("gui", "dl", "workflow_launch.py")
        self.assertEqual(lau.count("_block_open_without_scenes("), 3)  # 定义 + 两个启动函数


class RangeGaps(Tmp):
    def setUp(self):
        super().setUp()
        self.pdf = make_pdf(os.path.join(self.tmp, "m.pdf"), 10)

    # ---- 缺口 1：场景生成用的范围
    def test_scene_source_range_record_and_use(self):
        vd = {}
        pr.set_range(vd, self.pdf, 3, 5)
        rec = pr.source_range_record(vd, self.pdf)
        self.assertEqual((rec["start"], rec["end"], rec["pages"]), (3, 5, 10))
        self.assertEqual(rec["size"], os.path.getsize(self.pdf))
        vd[pr.SOURCE_RANGE_KEY] = rec
        self.assertEqual(pr.source_pages_arg(vd, self.pdf), (3, 5))
        pr.set_range(vd, self.pdf, 1, 10)  # 之后在材料列表里把范围改回整份
        self.assertEqual(pr.pages_arg(vd, self.pdf), None)
        self.assertEqual(pr.source_pages_arg(vd, self.pdf), (3, 5))  # 配图仍按场景生成时的那几页
        vd2 = {pr.SOURCE_RANGE_KEY: pr.source_range_record({}, self.pdf)}  # 生成时是整份
        pr.set_range(vd2, self.pdf, 2, 4)
        self.assertIsNone(pr.source_pages_arg(vd2, self.pdf))
        legacy = {}
        pr.set_range(legacy, self.pdf, 6, 8)  # 旧项目：没记过 → 退回现在的范围（和以前一样）
        self.assertEqual(pr.source_pages_arg(legacy, self.pdf), (6, 8))
        other = make_pdf(os.path.join(self.tmp, "other.pdf"), 7)
        stale = {pr.SOURCE_RANGE_KEY: dict(rec)}
        self.assertEqual(pr.source_pages_arg(stale, other), None)  # PDF 换成别的文件：记录作废，退回现在的范围（没有 = 整份）
        self.assertIsNone(pr.source_range_record({}, os.path.join(self.tmp, "gone.pdf")))

    def test_auto_attach_after_generation_uses_the_recorded_range(self):
        res = _real(r'''
import json, os, sys
sys.path.insert(0, %r)
import gui.downloader as dl
import utility.material_image_matcher as mim
from utility import pdf_range as pr
pdf = %r
vd = {"scene_source_path": pdf, "scene_content": [{"caption": "a"}]}
pr.set_range(vd, pdf, 3, 5)
vd[pr.SOURCE_RANGE_KEY] = pr.source_range_record(vd, pdf)
pr.set_range(vd, pdf, 1, 10)           # 生成之后又把范围改了
seen = []
mim.start_auto_attach = lambda after, kind, path, scenes, **kw: seen.append([kind, kw.get("pages")])
class App: root = type("R", (), {"after": staticmethod(lambda *a: None)})()
dl._start_scene_auto_ref_images(App(), None, vd, vd["scene_content"], "pdf", lambda t: None, lambda: "", lambda *a, **k: True)
print(json.dumps(seen))
''' % (ROOT, self.pdf))
        self.assertEqual(res, [["pdf", [3, 5]]])

    def test_generation_stores_and_clears_the_range(self):
        dl = _read("gui", "downloader.py")
        self.assertIn("scene_source_range: dict | None = None,", dl)
        self.assertIn('video_detail["scene_source_range"] = dict(scene_source_range)', dl)
        self.assertIn('video_detail.pop("scene_source_range", None)', dl)
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("pdf_source_range = pdf_range.source_range_record(video_detail, pdf_original)", se)
        self.assertIn("scene_source_range=pdf_source_range if source_kind == project_manager.SCENE_SOURCE_PDF else None,", se)
        self.assertIn('video_detail.pop("scene_source_range", None)', se)  # 信息图来源：没有页范围
        res = _real(r'''
import json, sys
sys.path.insert(0, %r)
import project_manager as pm
rec = {"start": 3, "end": 5, "pages": 10}
cfg = pm.project_config_from_list_item({"id": "r1", "scene_content": [{"caption": "a"}], "scene_source": "pdf", "scene_source_range": rec})
print(json.dumps({"key": "scene_source_range" in pm.LIST_ITEM_TOP_PROJECT_KEYS, "carried": cfg.get("scene_source_range") == rec}))
''' % ROOT)
        self.assertEqual(res, {"key": True, "carried": True})  # 随项目一起存 / 带进项目配置

    # ---- 缺口 2
    def test_merge_missing_program_media_restores_the_ranges_with_the_slide(self):
        rng = {self.pdf: {"start": 3, "end": 5, "pages": 10}}
        existing = {"slide": [self.pdf], pr.RANGES_KEY: rng}
        inc = pm.merge_missing_program_media({"id": "x"}, existing)
        self.assertEqual(inc["slide"], [self.pdf])
        self.assertEqual(inc[pr.RANGES_KEY], rng)
        self.assertIsNot(inc[pr.RANGES_KEY], rng)  # 拷贝，不共用
        own = pm.merge_missing_program_media({"id": "x", pr.RANGES_KEY: {"k": 1}}, existing)  # incoming 自己的范围优先
        self.assertEqual(own[pr.RANGES_KEY], {"k": 1})
        removed = pm.merge_missing_program_media({"id": "x", "slide": []}, existing)  # 用户删了 PDF：slide 和范围都不补
        self.assertEqual(removed["slide"], [])
        self.assertNotIn(pr.RANGES_KEY, removed)
        noslide = pm.merge_missing_program_media({}, {pr.RANGES_KEY: rng})  # 旧行没有 slide：不凭空补范围
        self.assertNotIn(pr.RANGES_KEY, noslide)
        lst = pm.merge_program_media_into_list([{"id": "a", "title": "t"}], [{"id": "a", "slide": [self.pdf], pr.RANGES_KEY: rng}])
        self.assertEqual(lst[0][pr.RANGES_KEY], rng)

    # ---- 缺口 3
    def test_hydrate_clears_a_stale_range_when_the_row_has_none(self):
        res = _real(r'''
import json, sys
sys.path.insert(0, %r)
import project_manager as pm
stale = {"/x/a.pdf": {"start": 3, "end": 5, "pages": 10}}
out = {}
cfg = {"pid": "p1", "pdf_page_ranges": json.loads(json.dumps(stale))}
pm.hydrate_config_cover_media(cfg, {"id": "r1", "title": "t"})           # 行上没有范围 → 清掉
out["cleared"] = "pdf_page_ranges" in cfg
cfg = {"pid": "p1", "pdf_page_ranges": json.loads(json.dumps(stale))}
fresh = {"/x/b.pdf": {"start": 2, "end": 4, "pages": 9}}
pm.hydrate_config_cover_media(cfg, {"id": "r1", "pdf_page_ranges": fresh})  # 行上有 → 以行为准
out["replaced"] = cfg["pdf_page_ranges"] == fresh
pm.load_video_detail_row_for_config = lambda c: None                      # 找不到列表行 → 不动
cfg = {"pid": "p1", "pdf_page_ranges": json.loads(json.dumps(stale))}
pm.hydrate_config_cover_media(cfg)
out["kept_without_row"] = cfg.get("pdf_page_ranges") == stale
print(json.dumps(out))
''' % ROOT)
        self.assertEqual(res, {"cleared": False, "replaced": True, "kept_without_row": True})

    # ---- 缺口 4
    def test_scene_episode_pdf_never_falls_back_to_the_whole_original(self):
        res = _real(r'''
import json, os, sys, tempfile, fitz
sys.path.insert(0, %r)
import config, project_manager
from gui.workflow.wf_pdf_episode import PdfEpisodeMixin
from utility import pdf_range as pr
tmp = tempfile.mkdtemp(prefix="t271_")
orig = os.path.join(tmp, "orig"); media = os.path.join(tmp, "media"); gen = os.path.join(tmp, "gen")
for d in (orig, media, gen): os.makedirs(d)
pdf = os.path.join(orig, "1.pdf")
doc = fitz.open()
for i in range(10): doc.new_page().insert_text((40, 60), "page %%d" %% (i + 1))
doc.save(pdf); doc.close()
config.get_media_path = lambda pid: media
config.INPUT_MEDIA_GEN_VIDEO_PATH = gen
class W:
    pid = "pT271"
    def scene_group(self, scene): return "1"
class F: workflow = W()
scene = {"episode_pdf": "1.pdf"}
out = {}
project_manager.PROJECT_CONFIG = {"slide": [pdf]}
out["slide_only"] = PdfEpisodeMixin._resolve_scene_episode_pdf(F(), scene)             # 以前：返回整份原始 PDF
import shutil
shutil.copy2(pdf, os.path.join(gen, "1.pdf"))
out["gen_full"] = os.path.basename(PdfEpisodeMixin._resolve_scene_episode_pdf(F(), scene))
cfg = {"slide": [pdf]}; pr.set_range(cfg, os.path.join(gen, "1.pdf"), 4, 6)
project_manager.PROJECT_CONFIG = cfg
got = PdfEpisodeMixin._resolve_scene_episode_pdf(F(), scene)
out["gen_range"] = [os.path.basename(got), pr.page_count(got)]
real = pr.extract_pages
pr.extract_pages = lambda *a, **k: (_ for _ in ()).throw(pr.PdfRangeError("坏了"))
out["gen_range_fails"] = PdfEpisodeMixin._resolve_scene_episode_pdf(F(), scene)
pr.extract_pages = real
pm_ep = os.path.join(media, "1"); os.makedirs(pm_ep); shutil.copy2(pdf, os.path.join(pm_ep, "1.pdf"))
os.remove(os.path.join(gen, "1.pdf"))
out["media_copy"] = os.path.basename(PdfEpisodeMixin._resolve_scene_episode_pdf(F(), scene))
print(json.dumps(out, ensure_ascii=False))
''' % ROOT)
        self.assertEqual(res["slide_only"], "")
        self.assertEqual(res["gen_full"], "1.pdf")
        self.assertEqual(res["gen_range"], ["1_p4-6.pdf", 3])
        self.assertEqual(res["gen_range_fails"], "")
        self.assertEqual(res["media_copy"], "1.pdf")
        src = _read("gui", "workflow", "wf_pdf_episode.py")
        self.assertNotIn('get_primary_program_media(pc, "slides")', src[src.index("def _resolve_scene_episode_pdf"):src.index("def _scenes_as_prompt_content")])


class PreviewSceneGenerationFromPdf(Tmp):
    """任务 C：预览窗口「场景生成」(来源 PDF) → 后台自动配图，只用开始页–结束页的页。
    t275: 一页一个场景 → 第 k 页直接对第 k 场（不看图、不用 Strata，下面把 Strata / 看图换成「一调用就报错」）。"""

    def test_pdf_scene_generation_attaches_scene_images_from_the_selected_pages_only(self):
        pdf = make_pdf(os.path.join(self.tmp, "deck.pdf"), 10, images=True)
        res = _real(r'''
import json, os, sys, time
sys.path.insert(0, %r)
import gui.downloader as dl
import utility.material_image_matcher as mim
from utility import pdf_range as pr
pdf, out_dir = %r, %r
vd = {"scene_source": "pdf", "scene_source_path": pdf}
pr.set_range(vd, pdf, 4, 6)
vd[pr.SOURCE_RANGE_KEY] = pr.source_range_record(vd, pdf)      # 场景生成那一刻记下
scenes = [{"caption": "s%%d" %% i, "visual": "v"} for i in range(3)]
vd["scene_content"] = scenes
def boom(*a, **k): raise AssertionError("Strata / 看图 / 匹配不该被自动调用")
mim.run_match = mim.describe_image = mim.make_strata_judge = boom
mim.working_dir_for = lambda *a, **k: out_dir      # 图存到临时目录，不写真正的 working 目录
queue = []
class Root:
    def after(self, ms, fn): queue.append(fn)
class App: root = Root()
saved, shown = [], []
dl._start_scene_auto_ref_images(App(), None, vd, scenes, "pdf", lambda t: shown.append(t), lambda: json.dumps(scenes), lambda v, parent=None: saved.append(1) or True)
t0 = time.time()
while time.time() - t0 < 60 and not saved:
    if queue: queue.pop(0)()
    time.sleep(0.05)
refs = [[r.get("page") for r in (s.get("ref_images") or [])] for s in vd["scene_content"]]
print(json.dumps({"saved": len(saved), "refs": refs, "files": sorted(os.listdir(os.path.join(out_dir, "pages"))), "written": bool(shown)}))
''' % (ROOT, pdf, os.path.join(self.tmp, "imgs")))
        self.assertEqual(res["saved"], 1)               # 配完以后自动写回编辑框并保存
        self.assertTrue(res["written"])
        self.assertEqual(res["refs"], [[4], [5], [6]])   # 只有第 4–6 页（开始页–结束页），一页对一场（直接对应）
        self.assertEqual([f for f in res["files"] if f.endswith(".png")], ["p004.png", "p005.png", "p006.png"])


if __name__ == "__main__":
    unittest.main()
