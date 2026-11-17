"""t267: STORY 窗口材料列表里每份 PDF 的页范围（开始页 / 结束页）。

纯逻辑、截页、抽图、读文字用真的 PyMuPDF 在临时目录造 PDF；要真 config / scene_editor / magic_workflow 的检查在子进程里跑，只读，
不碰任何项目 / 列表数据；数字框的检查用一个临时的隐藏 Tk 窗口（没有显示器就跳过）。"""
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _real(code):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-W", "ignore", "-c", "import warnings\nwarnings.filterwarnings('ignore')\n" + code],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-2500:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _png(color) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (240, 320), color).save(buf, "PNG")
    return buf.getvalue()


def make_pdf(path: str, pages: int, *, images: bool = False) -> str:
    """第 k 页写着 'page k'；images=True 时每页铺满一张不同颜色的图。"""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        if images:
            page.insert_image(page.rect, stream=_png((i * 7 % 256, 100, 200 - i % 150)))
        page.insert_text((40, 60), f"page {i + 1}")
    doc.save(path)
    doc.close()
    return path


def page_texts(path: str) -> list:
    with fitz.open(path) as doc:
        return [p.get_text().strip() for p in doc]


class _TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t267_")
        self.derived = os.path.join(self.tmp, "derived")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pdf = make_pdf(os.path.join(self.tmp, "文档.pdf"), 32)
        # 派生 PDF 默认放系统临时目录；测试里记下来，结束时清掉
        self._made = []

        def cleanup():
            for p in self._made:
                shutil.rmtree(os.path.dirname(p), True)

        self.addCleanup(cleanup)

    def eff(self, item, path=None, *fb):
        out = pr.effective_pdf(item, path or self.pdf, *fb)
        if out != (path or self.pdf):
            self._made.append(out)
        return out


class DefaultsAndLegacy(_TmpCase):
    def test_new_pdf_is_page_one_to_last(self):
        self.assertEqual(pr.get_range({}, self.pdf), (1, 32, 32))
        self.assertEqual(pr.get_range(None, self.pdf), (1, 32, 32))
        self.assertEqual(pr.pages_arg({}, self.pdf), None)  # 整份：读文字 / 抽图都不带页范围
        self.assertEqual(pr.effective_page_count({}, self.pdf), 32)
        self.assertEqual(self.eff({}), self.pdf)  # 整份就是原文件，不截

    def test_every_route_that_adds_a_pdf_starts_full(self):
        # 选一份 / 拖进来 / 节目生成产出 / 图片合成 PDF 都走 append_program_media(…, "slides", path)
        item = {"slide": []}
        pr.set_range(item, self.pdf, 3, 4)  # 这个路径上残存的旧范围
        self.assertEqual(pr.get_range(item, self.pdf), (3, 4, 32))
        pm.append_program_media(item, "slides", self.pdf)
        self.assertEqual(pr.get_range(item, self.pdf), (1, 32, 32))
        self.assertNotIn(pr.RANGES_KEY, item)
        # 已经在列表里的（挪到最前）不重置
        pr.set_range(item, self.pdf, 5, 9)
        pm.append_program_media(item, "slides", self.pdf)
        self.assertEqual(pr.get_range(item, self.pdf), (5, 9, 32))
        # 第二份 PDF 从头到尾，不受第一份影响
        other = make_pdf(os.path.join(self.tmp, "b.pdf"), 8)
        pm.append_program_media(item, "slides", other)
        self.assertEqual(pr.get_range(item, other), (1, 8, 8))
        self.assertEqual(pr.get_range(item, self.pdf), (5, 9, 32))
        # PDF 删掉，范围一起删
        pm.remove_program_media(item, "slides", self.pdf)
        self.assertFalse(pr.has_entry(item, self.pdf))

    def test_legacy_entries_without_a_range_mean_the_whole_document(self):
        legacy = {"id": "s1", "slide": self.pdf, "scene_content": []}  # t266 以前的条目：没有 pdf_page_ranges
        self.assertEqual(pr.get_range(legacy, self.pdf), (1, 32, 32))
        self.assertIsNone(pr.pages_arg(legacy, self.pdf))
        for junk in (None, [], "", 0, {"x": 1}, {self.pdf: "bad"}, {self.pdf: {"start": "a", "end": None}},
                     {self.pdf: {"start": 3, "end": 5}}):  # 最后一个：没记总页数 = 不认
            item = {pr.RANGES_KEY: junk}
            s, e, n = pr.get_range(item, self.pdf)
            self.assertEqual(n, 32)
            self.assertTrue(1 <= s <= e <= 32)
        self.assertEqual(pr.get_range({pr.RANGES_KEY: {self.pdf: {"start": 3, "end": 5}}}, self.pdf), (1, 32, 32))

    def test_row_text_shows_the_range(self):
        self.assertEqual(pr.label(10, 32, 32), "共 32 页 · 第 10–32 页")
        self.assertEqual(pr.label(1, 8, 8), "共 8 页 · 第 1–8 页")
        self.assertEqual(pr.label(7, 7, 32), "共 32 页 · 第 7 页")
        self.assertEqual(pr.label(1, 0, 0), "")
        self.assertEqual(pr.range_text(10, 32), "第 10–32 页")
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("pdf_range.label(pstart, pend, pages)", se)  # 材料列表 PDF 行的说明文字
        self.assertIn('"page_start": pstart, "page_end": pend', se)

    def test_unreadable_pdf(self):
        bad = os.path.join(self.tmp, "bad.pdf")
        with open(bad, "wb") as f:
            f.write(b"not a pdf")
        self.assertEqual(pr.get_range({}, bad), (1, 0, 0))
        self.assertEqual(pr.page_count(os.path.join(self.tmp, "missing.pdf")), 0)
        with self.assertRaises(pr.PdfRangeError):
            pr.extract_pages(bad, 1, 2)
        with self.assertRaises(pr.PdfRangeError):
            pr.extract_pages(os.path.join(self.tmp, "missing.pdf"), 1, 2)


class ClampingAndOrder(_TmpCase):
    def test_clamp_table(self):
        c = pr.clamp_range
        self.assertEqual(c(1, 32, 32), (1, 32))
        self.assertEqual(c(10, 32, 32), (10, 32))
        self.assertEqual(c(0, 32, 32), (1, 32))      # 小于 1 → 1
        self.assertEqual(c(-5, 99, 32), (1, 32))     # 大于总页数 → 总页数
        self.assertEqual(c(40, 50, 32), (32, 32))    # 两个都超 → 都夹到最后一页（单页）
        self.assertEqual(c(7, 7, 32), (7, 7))        # 单页允许
        self.assertEqual(c("12", " 20 ", 32), (12, 20))
        self.assertEqual(c("", None, 32), (1, 32))   # 乱填 = 整份的那一端
        self.assertEqual(c("abc", "x", 32), (1, 32))
        self.assertEqual(c(3, 3, 1), (1, 1))         # 一页的文档
        self.assertEqual(c(1, 5, 0), (1, 0))         # 总页数未知

    def test_start_never_exceeds_end_whichever_box_was_edited(self):
        # 改开始页超过结束页：开始页算数，结束页跟上去
        self.assertEqual(pr.clamp_range(25, 20, 32, "start"), (25, 25))
        # 改结束页低于开始页：结束页算数，开始页跟下来
        self.assertEqual(pr.clamp_range(10, 5, 32, "end"), (5, 5))
        # 先改开始页再改结束页能到想要的 40–50
        item = {}
        pr.set_range(item, self.pdf, 10, 20)
        s, e, _n = pr.set_range(item, self.pdf, 30, 20, "start")
        self.assertEqual((s, e), (30, 30))
        s, e, _n = pr.set_range(item, self.pdf, s, 32, "end")
        self.assertEqual((s, e), (30, 32))
        # 随机组合：永远 1 ≤ 开始 ≤ 结束 ≤ 总页数
        import itertools

        vals = (-3, 0, 1, 2, 16, 31, 32, 33, 99)
        for a, b, edited in itertools.product(vals, vals, ("start", "end")):
            s, e = pr.clamp_range(a, b, 32, edited)
            self.assertTrue(1 <= s <= e <= 32, (a, b, edited, s, e))

    def test_set_range_clamps_and_full_leaves_no_record(self):
        item = {}
        self.assertEqual(pr.set_range(item, self.pdf, 10, 99, "end"), (10, 32, 32))
        self.assertEqual(item[pr.RANGES_KEY][os.path.abspath(self.pdf)], {
            "start": 10, "end": 32, "pages": 32, "size": os.path.getsize(self.pdf)})
        self.assertEqual(pr.set_range(item, self.pdf, 0, 0, "start"), (1, 1, 32))  # 开始页 0 → 1，结束页 0 → 1
        self.assertEqual(pr.set_range(item, self.pdf, 1, 32), (1, 32, 32))
        self.assertNotIn(pr.RANGES_KEY, item)  # 回到整份 = 不留记录
        self.assertEqual(pr.reset_range(item, self.pdf), (1, 32, 32))

    def test_replaced_pdf_invalidates_the_range(self):
        item = {}
        pr.set_range(item, self.pdf, 10, 20)
        make_pdf(self.pdf, 12)  # 同一个路径被换成 12 页的另一份
        self.assertEqual(pr.get_range(item, self.pdf), (1, 12, 12))
        pr.set_range(item, self.pdf, 3, 5)
        make_pdf(self.pdf, 12, images=True)  # 页数一样但是另一份文件（大小不同）
        self.assertEqual(pr.get_range(item, self.pdf), (1, 12, 12))

    def test_path_match_ignores_case_and_slashes(self):
        item = {}
        pr.set_range(item, self.pdf, 10, 20)
        self.assertEqual(pr.get_range(item, self.pdf.replace("\\", "/"))[:2], (10, 20))
        self.assertEqual(pr.get_range(item, self.pdf.upper() if os.name == "nt" else self.pdf)[:2], (10, 20))

    def test_ranges_are_per_pdf(self):
        other = make_pdf(os.path.join(self.tmp, "b.pdf"), 8)
        item = {}
        pr.set_range(item, self.pdf, 10, 20)
        pr.set_range(item, other, 2, 3)
        self.assertEqual(pr.get_range(item, self.pdf)[:2], (10, 20))
        self.assertEqual(pr.get_range(item, other)[:2], (2, 3))
        pr.forget(item, self.pdf)
        self.assertEqual(pr.get_range(item, other)[:2], (2, 3))
        self.assertEqual(pr.get_range(item, self.pdf)[:2], (1, 32))

    def test_owner_picks_the_item_that_has_the_range(self):
        row, cfg = {}, {}
        pr.set_range(row, self.pdf, 4, 6)
        self.assertEqual(pr.pages_arg(cfg, self.pdf, row), (4, 6))  # 项目配置没有、列表行有
        self.assertEqual(pr.pages_arg(row, self.pdf, cfg), (4, 6))
        self.assertIsNone(pr.pages_arg(cfg, self.pdf, {}))


class Persistence(_TmpCase):
    def test_json_round_trip_and_reopen(self):
        item = {"id": "s1", "slide": [self.pdf]}
        pr.set_range(item, self.pdf, 10, 32)
        path = os.path.join(self.tmp, "list.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([item], f, ensure_ascii=False, indent=2)
        with open(path, encoding="utf-8") as f:
            reopened = json.load(f)[0]
        self.assertEqual(pr.get_range(reopened, self.pdf), (10, 32, 32))
        self.assertEqual(pr.label(*pr.get_range(reopened, self.pdf)), "共 32 页 · 第 10–32 页")

    def test_real_list_storage_keeps_the_range(self):
        res = _real(r'''
import json, os, sys, tempfile
sys.path.insert(0, %r)
import config
from gui.dl import list_store
from utility import pdf_range as pr
tmp = tempfile.mkdtemp(prefix="t267_")
pdf = os.path.join(tmp, "m.pdf")
import fitz
doc = fitz.open()
for i in range(20): doc.new_page()
doc.save(pdf); doc.close()
row = {"id": "s20261115", "title": "t", "slide": [pdf]}
pr.set_range(row, pdf, 10, 20)
list_store._normalize_channel_list_item_for_storage(row, "")      # 保存时的规范化
lst = os.path.join(tmp, "list", "topic.json")
config.write_channel_list_json(lst, [row])                         # 真正的写列表函数
back = json.load(open(lst, encoding="utf-8"))[0]
copy = list_store._copy_story_list_row(back, "s_copy")             # 复制故事材料
print(json.dumps({"back": pr.get_range(back, pdf), "copy": pr.get_range(copy, pdf),
                  "keys": sorted(k for k in back if "range" in k), "tmp": tmp}))
''' % ROOT)
        self.addCleanup(shutil.rmtree, res["tmp"], True)
        self.assertEqual(res["back"], [10, 20, 20])
        self.assertEqual(res["copy"], [10, 20, 20])
        self.assertEqual(res["keys"], ["pdf_page_ranges"])

    def test_project_config_carries_the_range(self):
        res = _real(r'''
import json, os, sys, tempfile
sys.path.insert(0, %r)
import project_manager
from utility import pdf_range as pr
tmp = tempfile.mkdtemp(prefix="t267_")
pdf = os.path.join(tmp, "m.pdf")
import fitz
doc = fitz.open()
for i in range(20): doc.new_page()
doc.save(pdf); doc.close()
row = {"id": "s1", "slide": [pdf], "scene_source": "pdf", "scene_source_path": pdf}
pr.set_range(row, pdf, 5, 8)
cfg = project_manager.project_config_from_list_item(row)
print(json.dumps({"cfg": pr.get_range(cfg, pdf), "legacy": pr.get_range(project_manager.project_config_from_list_item(
    {"id": "s2", "slide": [pdf]}), pdf), "tmp": tmp}))
''' % ROOT)
        self.addCleanup(shutil.rmtree, res["tmp"], True)
        self.assertEqual(res["cfg"], [5, 8, 20])
        self.assertEqual(res["legacy"], [1, 20, 20])  # 旧条目 = 整份


class ConsumersGetOnlySelectedPages(_TmpCase):
    def test_effective_pdf_holds_exactly_the_selected_pages(self):
        item = {}
        pr.set_range(item, self.pdf, 10, 14)
        out = self.eff(item)
        self.assertNotEqual(out, self.pdf)
        self.assertEqual(page_texts(out), [f"page {n}" for n in range(10, 15)])
        self.assertEqual(pr.page_count(out), 5)
        self.assertEqual(os.path.basename(out), "文档_p10-14.pdf")  # 名字带页范围
        self.assertEqual(pr.effective_page_count(item, self.pdf), 5)
        self.assertTrue(os.path.isfile(self.pdf) and pr.page_count(self.pdf) == 32)  # 原文件不动
        self.assertEqual(self.eff(item), out)  # 同一范围再要一次 = 现成的
        pr.set_range(item, self.pdf, 32, 32)  # 单页
        one = self.eff(item)
        self.assertEqual(page_texts(one), ["page 32"])
        self.assertEqual(os.path.basename(one), "文档_p32.pdf")
        pr.set_range(item, self.pdf, 1, 32)  # 回到整份：又是原文件
        self.assertEqual(self.eff(item), self.pdf)

    def test_effective_pdf_never_falls_back_to_the_whole_file(self):
        item = {}
        pr.set_range(item, self.pdf, 3, 5)
        real_extract = pr.extract_pages

        def boom(*a, **k):
            raise pr.PdfRangeError("截页失败")

        pr.extract_pages = boom
        try:
            with self.assertRaises(pr.PdfRangeError):
                pr.effective_pdf(item, self.pdf)
        finally:
            pr.extract_pages = real_extract

    def test_analyze_reads_only_the_selected_pages(self):
        from utility.pdf_util import pdf_text_content

        whole = pdf_text_content(self.pdf)
        self.assertEqual(whole["pages"], 32)
        self.assertIn("page 1", whole["text"])
        part = pdf_text_content(self.pdf, pages=(10, 12))
        self.assertEqual(part["pages"], 3)
        for n in (10, 11, 12):
            self.assertIn(f"page {n}", part["text"])
        for n in (1, 9, 13, 32):
            self.assertNotIn(f"page {n}\n", part["text"] + "\n")
        one = pdf_text_content(self.pdf, pages=(7, 7))
        self.assertEqual((one["pages"], one["text"]), (1, "page 7"))
        out_of_range = pdf_text_content(self.pdf, pages=(30, 99))  # 越界也只读存在的页
        self.assertEqual(out_of_range["pages"], 3)
        # 材料列表「分析」按钮用的就是这个读法
        se = _read("gui", "dl", "scene_editor.py")
        body = se[se.index("def _material_analyze"):se.index("def _walk_materials_drop")]
        self.assertIn("pdf_range.pages_arg(video_detail, path)", body)
        self.assertIn("pdf_text_content(path, pages=pages_sel)", body)

    def test_image_extraction_only_selected_pages(self):
        from utility import material_image_matcher as mim

        pdf = make_pdf(os.path.join(self.tmp, "img.pdf"), 12, images=True)
        out_all = os.path.join(self.tmp, "all")
        every = mim.extract_pdf_images(pdf, out_all, log=lambda *_: None)
        self.assertEqual([i["page"] for i in every], list(range(1, 13)))
        out_sel = os.path.join(self.tmp, "sel")
        part = mim.extract_pdf_images(pdf, out_sel, log=lambda *_: None, pages=(4, 6))
        self.assertEqual([i["page"] for i in part], [4, 5, 6])  # 页码仍是原文档的页码
        self.assertEqual(sorted(os.listdir(out_sel)), ["p004.png", "p005.png", "p006.png"])
        one = mim.extract_pdf_images(pdf, os.path.join(self.tmp, "one"), log=lambda *_: None, pages=(12, 12))
        self.assertEqual([i["page"] for i in one], [12])

    def test_image_to_scene_matching_only_selected_pages(self):
        from utility import material_image_matcher as mim

        pdf = make_pdf(os.path.join(self.tmp, "img.pdf"), 12, images=True)
        scenes = [{"caption": f"s{i}", "visual": "v"} for i in range(3)]
        seen = []

        def ask(path):
            seen.append(os.path.basename(path))
            return json.dumps({"desc": "d " + os.path.basename(path), "text": ""})

        res = mim.run_match(pdf, "pdf", scenes, out_dir=os.path.join(self.tmp, "m"), log=lambda *_: None,
                            vision_ask=ask, judge=lambda info, cands: cands[0][0], pages=(3, 5))
        self.assertEqual([i["page"] for i in res["images"]], [3, 4, 5])
        self.assertEqual(sorted(seen), ["p003.png", "p004.png", "p005.png"])  # Strata 只看了选中的页
        # 没给页范围 = 老样子整份
        res_all = mim.run_match(pdf, "pdf", scenes, out_dir=os.path.join(self.tmp, "m2"), log=lambda *_: None,
                                vision_ask=ask, judge=lambda info, cands: cands[0][0])
        self.assertEqual(len(res_all["images"]), 12)

    def test_auto_attach_after_scene_generation_passes_the_pages(self):
        from utility import material_image_matcher as mim

        got = {}

        def pdf_run(path, source, scenes, **kw):
            got["kw"] = kw
            return {"images": [], "matches": {}}

        mim.auto_ref_matches("pdf", self.pdf, [{"caption": "a"}], log=lambda *_: None, pdf_run=pdf_run, pages=(2, 4))
        self.assertEqual(got["kw"].get("pages"), (2, 4))
        got.clear()
        mim.auto_ref_matches("pdf", self.pdf, [{"caption": "a"}], log=lambda *_: None, pdf_run=pdf_run)
        self.assertNotIn("pages", got["kw"])  # 整份：调用方式和以前一样

        calls = []

        def matcher(kind, path, scenes, **kw):
            calls.append(kw)
            return {}

        self.assertTrue(mim.start_auto_attach(lambda ms, fn: fn(), "pdf", self.pdf, [{"caption": "a"}],
                                              get_current=lambda: [], commit=lambda *_: None, log=lambda *_: None,
                                              matcher=matcher, thread=False, pages=(2, 4)))
        self.assertEqual(calls[0].get("pages"), (2, 4))
        mim.start_auto_attach(lambda ms, fn: fn(), "pdf", self.pdf, [{"caption": "a"}], get_current=lambda: [],
                              commit=lambda *_: None, log=lambda *_: None, matcher=matcher, thread=False)
        self.assertNotIn("pages", calls[1])
        dl = _read("gui", "downloader.py")
        body = dl[dl.index("def _start_scene_auto_ref_images"):dl.index("def _start_scene_auto_ref_images") + 6000]
        self.assertIn("pdf_range.source_pages_arg(video_detail, path)", body)  # t271: 场景生成时记下的范围（旧项目退回现在的范围）
        self.assertIn('extra["pages"] = pages', body)

    def test_scene_generation_materials_use_the_selected_pages(self):
        se = _read("gui", "dl", "scene_editor.py")
        # 场景生成：附件 = 只含选中页的 PDF；说明文字里的页数 = 选中的页数；场景来源仍记原文件
        self.assertIn("_eff_pdf = pdf_range.effective_pdf(video_detail, pdf_original)", se)  # t275: 一页一个场景时 attachment = _eff_pdf
        self.assertIn("attachment = _eff_pdf", se)
        self.assertIn('source_path = pdf_original or attachment or ""', se)
        rem = se[se.index("def _remember_pdf_source"):se.index("def _fill_material_preview")]
        self.assertIn("_pdf_pages_as_scene_source(pdf_range.effective_pdf(video_detail, slide))", rem)
        self.assertIn("This file holds only pages", rem)
        # 复制到剪贴板（预览里 / 材料列表右键）
        self.assertIn("slide = pdf_range.effective_pdf(video_detail, slide)", se[se.index("def _copy_slide_pdf"):se.index("def _remember_pdf_source")])
        mc = se[se.index("def _material_copy"):se.index("def _material_double")]
        self.assertIn("pdf_range.effective_pdf(video_detail, path)", mc)
        # 图片对场景（右键「抽图对场景…」）
        mm = se[se.index("def _material_image_match"):se.index("def _material_menu")]
        self.assertIn("pages_sel = pdf_range.pages_arg(video_detail, path)", mm)
        self.assertIn('**({"pages": pages_sel} if pages_sel else {})', mm)

    def test_scene_prompt_page_count_is_the_selected_count(self):
        res = _real(r'''
import json, os, sys, tempfile, fitz
sys.path.insert(0, %r)
from gui.dl.slides_pdf import _pdf_pages_as_scene_source
from utility import pdf_range as pr
tmp = tempfile.mkdtemp(prefix="t267_")
pdf = os.path.join(tmp, "m.pdf")
doc = fitz.open()
for i in range(32): doc.new_page()
doc.save(pdf); doc.close()
item = {}
pr.set_range(item, pdf, 10, 32)
eff = pr.effective_pdf(item, pdf)
text, pages, _ = _pdf_pages_as_scene_source(eff)
print(json.dumps({"pages": pages, "text": text, "eff": eff, "tmp": tmp}))
''' % ROOT)
        self.addCleanup(shutil.rmtree, res["tmp"], True)
        self.addCleanup(shutil.rmtree, os.path.dirname(res["eff"]), True)
        self.assertEqual(res["pages"], 23)  # 第 10–32 页 = 23 页，不是 32
        self.assertIn("Page count: 23", res["text"])

    def test_program_generation_uses_the_selected_pages(self):
        """节目生成（材料 PDF 上传 NotebookLM / 拷成 content.pdf）：真函数 + 假的下游。（建项目拆页 t271 已去掉）"""
        res = _real(r'''
import json, os, sys, tempfile, fitz
sys.path.insert(0, %r)
import config
import gui.dl.scene_editor as se
import gui.slide_prompt_dialog as spd
import magic_workflow, project_manager
from utility import pdf_range as pr
from tkinter import messagebox
tmp = tempfile.mkdtemp(prefix="t267_")
pdf = os.path.join(tmp, "m.pdf")
doc = fitz.open()
for i in range(10):
    doc.new_page().insert_text((40, 60), "page %%d" %% (i + 1))
doc.save(pdf); doc.close()
out = {"tmp": tmp}
warns = []
messagebox.showwarning = lambda *a, **k: warns.append(a)
config.load_yt_tools_prefs = lambda: {}
cap = {}
spd.open_slide_prompt_dialog = lambda *a, **k: cap.update(k)
class G:
    def _persist_video_detail_story(self, *a, **k): pass
vd = {"id": "x1", "slide": [pdf], "scene_prompt_label": "故事对话"}
pr.set_range(vd, pdf, 4, 6)
se._open_story_program_dialog(G(), object(), None, vd, {})
mp = cap.get("material_pdf") or ""
out["program"] = {"pages": pr.page_count(mp), "name": os.path.basename(mp),
                  "texts": [p.get_text().strip() for p in fitz.open(mp)]}
vd_full = {"id": "x2", "slide": [pdf]}
cap.clear()
se._open_story_program_dialog(G(), object(), None, vd_full, {})
out["program_full"] = cap.get("material_pdf") == pdf
# 页范围用不了 → 不带材料 PDF，不退回整份
real_extract = pr.extract_pages
pr.extract_pages = lambda *a, **k: (_ for _ in ()).throw(pr.PdfRangeError("坏了"))
cap.clear(); warns.clear()
se._open_story_program_dialog(G(), object(), None, vd, {})
out["program_failed"] = {"material": cap.get("material_pdf"), "warned": bool(warns)}
pr.extract_pages = real_extract

print(json.dumps(out, ensure_ascii=False))
''' % ROOT)
        self.addCleanup(shutil.rmtree, res["tmp"], True)
        self.assertEqual(res["program"]["pages"], 3)
        self.assertEqual(res["program"]["name"], "m_p4-6.pdf")
        self.assertEqual(res["program"]["texts"], ["page 4", "page 5", "page 6"])
        self.assertTrue(res["program_full"])
        self.assertEqual(res["program_failed"], {"material": "", "warned": True})
        # t271: 建项目不再把 PDF 拆成场景图（场景图由预览窗口「场景生成」自动配好），这里不再有“按选中页拆页”的路径


class RowControls(unittest.TestCase):
    """材料列表里的 PDF 行：开始页 / 结束页数字框（隐藏的 Tk 窗口；没有显示器就跳过）。"""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"没有 Tk 显示：{exc}")
        cls.root.attributes("-alpha", 0.0)  # 要真的映射出来才收得到焦点 / 键盘事件；全透明，用户看不到
        cls.root.geometry("+0+0")
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def setUp(self):
        from gui.dl.materials_panel import MaterialsPanel

        self.tmp = tempfile.mkdtemp(prefix="t267_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pdf = make_pdf(os.path.join(self.tmp, "a.pdf"), 32)
        self.item = {}
        self.opened, self.rebuilds = [], []
        self.panel = MaterialsPanel(
            self.root, get_entries=self.entries, on_select=lambda e: None,
            on_copy=lambda e: self.opened.append(e["path"]), build_menu=lambda m, e: None,
            on_rebuilt=lambda w: self.rebuilds.append(1), on_pdf_range=self.changed, on_analyze=lambda e: None)
        self.panel.pack()
        self.panel.refresh()
        self.root.update()

    def tearDown(self):
        self.panel.destroy()

    def entries(self):
        s, e, n = pr.get_range(self.item, self.pdf)
        return [{"kind": "pdf", "path": self.pdf, "select": "pdf", "analyze": True, "title": "PDF：a.pdf",
                 "detail": pr.label(s, e, n), "pages": n, "page_start": s, "page_end": e}]

    def changed(self, entry, which, start, end):
        # 和 scene_editor._pdf_range_changed 一样：夹范围、记进这一条、返回（开始, 结束, 说明文字）
        s, e, n = pr.set_range(self.item, entry["path"], start, end, edited=which)
        return s, e, pr.label(s, e, n)

    def spins(self):
        return self.panel.range_spins[os.path.normcase(os.path.abspath(self.pdf))]

    def values(self):
        sp = self.spins()
        return int(sp["start"].get()), int(sp["end"].get())

    def detail_text(self):
        import tkinter as tk

        found = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Label):
                    found.append(c.cget("text"))
                walk(c)

        walk(self.panel.inner)
        return [t for t in found if "共" in t and "页" in t]

    def type_into(self, which, text):
        """像用户一样：在数字框里改字再回车 / 离开输入框（两个事件都会走同一个提交）。"""
        sp = self.spins()[which]
        sp.focus_force()
        self.root.update()
        sp.delete(0, "end")
        sp.insert(0, text)
        sp.event_generate("<Return>")
        self.root.update()

    def test_row_starts_at_page_one_to_last_with_the_range_in_the_text(self):
        self.assertEqual(self.values(), (1, 32))
        self.assertEqual(int(float(self.spins()["start"].cget("from"))), 1)
        self.assertEqual(int(float(self.spins()["end"].cget("to"))), 32)
        self.assertEqual(self.detail_text(), ["共 32 页 · 第 1–32 页"])

    def test_changing_the_pickers_saves_and_updates_the_text_without_rebuilding(self):
        n_rebuilds = len(self.rebuilds)
        self.type_into("start", "10")
        self.assertEqual(self.values(), (10, 32))
        self.assertEqual(self.item[pr.RANGES_KEY][os.path.abspath(self.pdf)]["start"], 10)
        self.assertEqual(self.detail_text(), ["共 32 页 · 第 10–32 页"])
        self.type_into("end", "20")
        self.assertEqual(self.values(), (10, 20))
        self.assertEqual(self.detail_text(), ["共 32 页 · 第 10–20 页"])
        self.assertEqual(len(self.rebuilds), n_rebuilds)  # 数字框没被销毁重建（点着点着框没了就糟了）

    def test_arrow_buttons_commit_through_the_same_path(self):
        sp = self.spins()["start"]
        sp.event_generate("<<Increment>>")  # 点上箭头 = ttk 的 <<Increment>>，会调 command
        self.root.update()
        self.assertEqual(self.values()[0], 2)
        self.assertEqual(self.detail_text(), ["共 32 页 · 第 2–32 页"])

    def test_single_page_order_and_clamp(self):
        self.type_into("start", "7")
        self.type_into("end", "7")
        self.assertEqual(self.values(), (7, 7))  # 单页允许
        self.assertEqual(self.detail_text(), ["共 32 页 · 第 7 页"])
        self.type_into("start", "20")  # 开始页超过结束页：结束页跟上去
        self.assertEqual(self.values(), (20, 20))
        self.type_into("end", "5")  # 结束页低于开始页：开始页跟下来
        self.assertEqual(self.values(), (5, 5))
        self.type_into("end", "99")  # 超过总页数 → 夹到 32
        self.assertEqual(self.values(), (5, 32))
        self.type_into("start", "0")  # 小于 1 → 1
        self.assertEqual(self.values(), (1, 32))
        self.assertNotIn(pr.RANGES_KEY, self.item)  # 回到整份：不留记录

    def test_junk_text_goes_back_to_the_old_value(self):
        self.type_into("start", "10")
        self.type_into("start", "abc")
        self.assertEqual(self.values(), (10, 32))
        self.type_into("end", "")
        self.assertEqual(self.values(), (10, 32))

    def test_reopen_restores_the_pickers(self):
        self.type_into("start", "10")
        self.item = json.loads(json.dumps(self.item))  # 存盘再读回来
        self.panel.refresh()
        self.root.update_idletasks()
        self.assertEqual(self.values(), (10, 32))
        self.assertEqual(self.detail_text(), ["共 32 页 · 第 10–32 页"])

    def test_spinboxes_do_not_count_as_clicking_the_row_and_double_click_still_opens(self):
        sp = self.spins()
        for which in ("start", "end"):
            self.assertEqual(sp[which].bind("<Button-1>"), "")  # 数字框自己处理点击，不触发整行的单击 / 双击
            self.assertTrue(sp[which].bind("<Return>"))
            self.assertTrue(sp[which].bind("<FocusOut>"))
        entry = self.panel._rows[0][0]
        self.panel._click(entry)
        self.panel._click(entry)  # 500 毫秒内第二下 = 双击 → on_copy（调用方用默认程序打开 PDF）
        self.assertEqual(self.opened, [self.pdf])

    def test_row_without_page_count_or_callback_has_no_pickers(self):
        from gui.dl.materials_panel import MaterialsPanel

        plain = MaterialsPanel(self.root, get_entries=self.entries, on_select=lambda e: None, on_copy=lambda e: None,
                               build_menu=lambda m, e: None)
        self.addCleanup(plain.destroy)
        plain.refresh()
        self.assertEqual(plain.range_spins, {})


class SceneEditorWiring(unittest.TestCase):
    def test_double_click_opens_the_pdf_and_new_routes_start_full(self):
        se = _read("gui", "dl", "scene_editor.py")
        self.assertIn("on_copy=_material_double,", se)  # 双击 = 用默认程序打开（t206u），t267 保持
        body = se[se.index("def _material_double"):se.index("def _material_select")]
        self.assertIn("_open_path(path)", body)
        # 选一份 / 拖进来 都走 _import_slide_pdf：新文件名 + 页范围清零
        imp = se[se.index("def _import_slide_pdf"):se.index('scene_ui["import_slide_pdf"]')]
        self.assertIn("pdf_range.forget(video_detail, os.path.abspath(dest))", imp)
        drop = se[se.index("def _offer_pdf_scene_generate"):se.index("def _on_scene_pdf_drop")]
        self.assertIn('importer = scene_ui.get("import_slide_pdf")', drop)
        pick = se[se.index("def _material_pick"):se.index("def _material_copy")]
        self.assertIn("_import_slide_pdf(picked)", pick)
        # 范围的回调进了面板；删 PDF 时一起清
        self.assertIn("on_pdf_range=_pdf_range_changed", se)
        dele = se[se.index("def _material_delete"):se.index("_image_match_busy")]
        self.assertIn("pdf_range.forget(video_detail, path)", dele)

    def test_range_callback_clamps_and_saves_later(self):
        se = _read("gui", "dl", "scene_editor.py")
        cb = se[se.index("def _pdf_range_changed"):se.index('scene_ui["pdf_range_changed"]')]
        self.assertIn("pdf_range.set_range(video_detail, path, start, end, edited=which)", cb)
        self.assertIn("dlg.after(600, _persist_range_now)", cb)  # 连点箭头不会每下都写一次列表
        self.assertIn("persist(video_detail, parent=dlg)", se[se.index("def _persist_range_now"):se.index("def _pdf_range_changed")])

    def test_no_consumer_reads_the_whole_pdf_without_the_range(self):
        """列出所有读「这一条的 PDF」的地方，每一处都带页范围（新增读 PDF 的地方要来这里登记）。"""
        se = _read("gui", "dl", "scene_editor.py")
        for needle in ("pdf_range.effective_pdf(video_detail, material_pdf)",     # 节目生成：材料 PDF 上传 / 拷成 content.pdf
                       "pdf_range.effective_pdf(video_detail, pdf_original)",     # 场景生成：附件
                       "pdf_range.pages_arg(video_detail, path)"):                # 分析 / 抽图对场景
            self.assertIn(needle, se, needle)
        mw = _read("magic_workflow.py")
        self.assertNotIn("effective_pdf(pc, slide_pdf", mw)                       # t271: 建项目不再读 PDF 拆页
        # 材料 PDF 经 slide_prompt_dialog 上传 / 拷贝时，拿到的就是上面截好的文件
        spd = _read("gui", "slide_prompt_dialog.py")
        self.assertIn("extra_sources = [material_pdf] if material_pdf else []", spd)
        self.assertIn("shutil.copy2(material_pdf, pdf_path)", spd)


if __name__ == "__main__":
    unittest.main()
