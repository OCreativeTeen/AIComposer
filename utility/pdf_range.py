# -*- coding: utf-8 -*-
"""t267: 每份 PDF 的页范围（开始页 / 结束页）。

STORY 窗口材料列表的 PDF 行有「开始页」「结束页」两个数字框：
- 任何方式进来的 PDF（拖进来、选一份 PDF、节目生成 / NotebookLM 产出、图片合成 PDF、旧项目里已有的）都从第 1 页到最后一页；
- 用户可以手动改；开始页永远 ≤ 结束页（单页 = 开始页等于结束页），都夹在 1..总页数里；
- 范围记在这一条（列表行 / video_detail）的 ``pdf_page_ranges`` 里（按 PDF 路径），重开项目恢复；
  没有这个字段的旧条目 = 整份文档。记的时候同时记下总页数和文件大小，PDF 被换成别的文件后范围自动作废（回到整份）。

所有读这份 PDF 的地方（分析、场景生成、抽图对场景、节目生成上传、拷到剪贴板、建项目拆页）只拿选中的页：
能按页读的（读文字、抽图）直接带 ``pages=(开始, 结束)``；只能整份文件上传 / 附件的，用 ``effective_pdf`` 截出一份只含这几页的新 PDF
（放在系统临时目录 ``aicomposer_pdf_range/``，原文件不动）。截不出来就抛 ``PdfRangeError``，绝不悄悄退回整份。

这个模块不碰 Tk，只在需要页数 / 截页时才 import fitz（PyMuPDF）。页码一律是 1 起、含两端。
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile

RANGES_KEY = "pdf_page_ranges"
SOURCE_RANGE_KEY = "scene_source_range"  # t271: 场景生成那一刻用的页范围（和 scene_source_path 放一起）
DERIVED_DIRNAME = "aicomposer_pdf_range"


class PdfRangeError(Exception):
    """页范围没法用（找不到文件、PDF 有密码、截页失败）。消息是给用户看的一句话。"""


# ---------------------------------------------------------------- 基本
def path_key(path: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(str(path or "").strip()))
    except (OSError, ValueError, TypeError):
        return str(path or "").strip()


def _to_int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


_count_cache: dict = {}


def _file_sig(path: str) -> tuple:
    st = os.stat(path)
    return (path_key(path), st.st_size, st.st_mtime_ns)


def page_count(path: str) -> int:
    """PDF 总页数；打不开 / 不存在返回 0。按（路径、大小、修改时间）缓存。"""
    path = str(path or "").strip()
    if not path or not os.path.isfile(path):
        return 0
    try:
        sig = _file_sig(path)
    except OSError:
        return 0
    if sig in _count_cache:
        return _count_cache[sig]
    try:
        import fitz

        with fitz.open(path) as doc:
            n = int(doc.page_count)
    except Exception:  # noqa: BLE001  坏文件 / 有密码都当 0 页
        return 0
    _count_cache[sig] = n
    return n


def clamp_range(start, end, pages: int, edited: str = "start") -> tuple[int, int]:
    """把（开始, 结束）夹进 1..pages，并保证开始 ≤ 结束。

    ``edited`` = 用户刚改的是哪一格（"start" / "end"）：刚改的那格算数，另一格跟着挪，
    例如 10–20 里把开始页改成 25 → 25–25，再把结束页改成 30 → 25–30（不会因为顺序问题改不动）。
    乱填（空、字母）按整份的那一端算。总页数 0 = 没法算，返回 (1, 0)。
    """
    n = max(0, _to_int(pages, 0))
    if n <= 0:
        return 1, 0
    s = min(max(_to_int(start, 1), 1), n)
    e = min(max(_to_int(end, n), 1), n)
    if s > e:
        if edited == "end":
            s = e
        else:
            e = s
    return s, e


def is_partial(start: int, end: int, total: int) -> bool:
    return total > 0 and not (int(start) == 1 and int(end) == int(total))


def label(start: int, end: int, total: int) -> str:
    """行里显示的文字：'共 32 页 · 第 10–32 页'；单页 '共 32 页 · 第 10 页'。"""
    if total <= 0:
        return ""
    if int(start) == int(end):
        return f"共 {total} 页 · 第 {int(start)} 页"
    return f"共 {total} 页 · 第 {int(start)}–{int(end)} 页"


def range_text(start: int, end: int) -> str:
    """只写页（给提示 / 日志用）：'第 10–32 页' / '第 10 页'。"""
    return f"第 {int(start)} 页" if int(start) == int(end) else f"第 {int(start)}–{int(end)} 页"


# ---------------------------------------------------------------- 记在条目里
def _find_entry(item, path: str):
    """(键, 记录) 或 (None, None)。路径按 normcase + abspath 比，不看大小写 / 斜线方向。"""
    if not isinstance(item, dict):
        return None, None
    ranges = item.get(RANGES_KEY)
    if not isinstance(ranges, dict) or not ranges:
        return None, None
    want = path_key(path)
    for key, rec in ranges.items():
        if path_key(key) == want:
            return key, rec
    return None, None


def has_entry(item, path: str) -> bool:
    return _find_entry(item, path)[0] is not None


def get_range(item, path: str, pages: int | None = None) -> tuple[int, int, int]:
    """(开始页, 结束页, 总页数)。没记过 / 记的已经不适用（PDF 被换了）= 整份。总页数 0（打不开）= (1, 0, 0)。"""
    total = int(pages) if pages else page_count(path)
    if total <= 0:
        return 1, 0, 0
    _key, rec = _find_entry(item, path)
    if not isinstance(rec, dict):
        return 1, total, total
    size = rec.get("size")
    try:
        actual_size = os.path.getsize(path)
    except OSError:
        actual_size = None
    if _to_int(rec.get("pages"), -1) != total or (
        size is not None and actual_size is not None and _to_int(size, -1) != actual_size
    ):
        return 1, total, total  # 这个路径上的 PDF 已经不是当时记范围的那一份
    s, e = clamp_range(rec.get("start"), rec.get("end"), total, "start")
    return s, e, total


def set_range(item, path: str, start, end, edited: str = "start", pages: int | None = None) -> tuple[int, int, int]:
    """记下范围（夹到 1..总页数、开始 ≤ 结束）。整份就不留记录。返回实际生效的（开始, 结束, 总页数）。"""
    total = int(pages) if pages else page_count(path)
    if total <= 0:
        return 1, 0, 0
    s, e = clamp_range(start, end, total, edited)
    if not isinstance(item, dict):
        return s, e, total
    forget(item, path)
    if is_partial(s, e, total):
        ranges = item.get(RANGES_KEY)
        if not isinstance(ranges, dict):
            ranges = {}
        try:
            size = os.path.getsize(path)
        except OSError:
            size = None
        rec = {"start": s, "end": e, "pages": total}
        if size is not None:
            rec["size"] = size
        ranges[os.path.abspath(str(path).strip())] = rec
        item[RANGES_KEY] = ranges
    return s, e, total


def forget(item, path: str) -> None:
    """去掉这份 PDF 的范围记录（= 回到整份）。新 PDF 进来 / PDF 被删时用。"""
    key, _rec = _find_entry(item, path)
    if key is None:
        return
    ranges = item.get(RANGES_KEY)
    ranges.pop(key, None)
    if not ranges:
        item.pop(RANGES_KEY, None)


def reset_range(item, path: str) -> tuple[int, int, int]:
    forget(item, path)
    return get_range(item, path)


def owner_of(path: str, *items):
    """第一个记了这份 PDF 范围的条目（列表行 / 项目配置）；都没记就返回第一个条目。"""
    for it in items:
        if has_entry(it, path):
            return it
    return items[0] if items else None


def pages_arg(item, path: str, *fallbacks):
    """读文字 / 抽图用：None = 整份；否则 (开始, 结束)。"""
    s, e, total = get_range(owner_of(path, item, *fallbacks), path)
    return (s, e) if is_partial(s, e, total) else None


# ---------------------------------------------------------------- 场景生成时用的范围（t271）
def source_range_record(item, path: str, *fallbacks):
    """场景生成这一刻这份 PDF 实际用的页：{"start", "end", "pages"[, "size"]}；整份也记（= 1..总页数）。打不开返回 None。"""
    path = str(path or "").strip()
    if not path:
        return None
    s, e, total = get_range(owner_of(path, item, *fallbacks), path)
    if total <= 0:
        return None
    rec = {"start": int(s), "end": int(e), "pages": int(total)}
    try:
        rec["size"] = os.path.getsize(path)
    except OSError:
        pass
    return rec


def source_pages_arg(item, path: str, *fallbacks):
    """场景页和 PDF 页对得上的地方用：None = 整份；否则 (开始, 结束)。

    优先用场景生成时记下的 ``scene_source_range``（场景是按那几页生成的，之后在材料列表里再改页范围也不影响）；
    没记过（旧项目）/ 那份 PDF 已经被换掉 → 退回现在的页范围（``pages_arg``，和以前一样）。"""
    rec = item.get(SOURCE_RANGE_KEY) if isinstance(item, dict) else None
    if isinstance(rec, dict):
        total = page_count(path)
        size = rec.get("size")
        try:
            actual_size = os.path.getsize(path)
        except OSError:
            actual_size = None
        same_file = total > 0 and _to_int(rec.get("pages"), -1) == total and not (
            size is not None and actual_size is not None and _to_int(size, -1) != actual_size
        )
        if same_file:
            s, e = clamp_range(rec.get("start"), rec.get("end"), total, "start")
            return (s, e) if is_partial(s, e, total) else None
    return pages_arg(item, path, *fallbacks)


# ---------------------------------------------------------------- 截页
def _derived_dir(dest_dir: str = "") -> str:
    return dest_dir or os.path.join(tempfile.gettempdir(), DERIVED_DIRNAME)


def extract_pages(path: str, start: int, end: int, dest_dir: str = "") -> str:
    """把 path 的第 start–end 页存成一份新 PDF，返回新文件路径（原文件不动）。

    名字是 ``<原名>_p10-32.pdf``，放在 ``<临时目录>/aicomposer_pdf_range/<按文件大小和时间算的短码>/``；
    同一份文件同一范围再要一次直接用现成的。新文件的修改时间 = 原文件的修改时间。
    """
    src = os.path.abspath(str(path or "").strip())
    if not os.path.isfile(src):
        raise PdfRangeError(f"找不到这份 PDF：{src}")
    total = page_count(src)
    if total <= 0:
        raise PdfRangeError(f"打不开这份 PDF（没有页面、损坏或有密码）：{os.path.basename(src)}")
    s, e = clamp_range(start, end, total)
    stat = os.stat(src)
    tag = hashlib.sha1(f"{path_key(src)}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8", "replace")).hexdigest()[:12]
    stem = re.sub(r'[<>:"/\\|?*]+', "_", os.path.splitext(os.path.basename(src))[0]).strip(" .") or "pdf"
    name = f"{stem}_p{s}.pdf" if s == e else f"{stem}_p{s}-{e}.pdf"
    folder = os.path.join(_derived_dir(dest_dir), tag)
    dest = os.path.join(folder, name)
    want = e - s + 1
    if os.path.isfile(dest) and page_count(dest) == want:
        return dest
    try:
        import fitz

        os.makedirs(folder, exist_ok=True)
        tmp = dest + ".part"
        with fitz.open(src) as doc:
            if doc.needs_pass:
                raise PdfRangeError(f"这份 PDF 有密码，没法截出第 {s}–{e} 页：{os.path.basename(src)}")
            out = fitz.open()
            try:
                out.insert_pdf(doc, from_page=s - 1, to_page=e - 1)
                out.save(tmp, deflate=True)
            finally:
                out.close()
        os.replace(tmp, dest)
        try:
            os.utime(dest, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        except OSError:
            pass
    except PdfRangeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PdfRangeError(f"截出第 {s}–{e} 页失败（{type(exc).__name__}: {exc}）：{os.path.basename(src)}") from exc
    if page_count(dest) != want:
        raise PdfRangeError(f"截出来的 PDF 页数不对（要 {want} 页）：{os.path.basename(src)}")
    return dest


def effective_pdf(item, path: str, *fallbacks) -> str:
    """要把整份文件交给别的程序（上传 / 附件 / 拷到剪贴板 / 拆页）时用的那个文件：
    整份 → 原路径；选了一部分 → 只含这几页的新 PDF。截不出来抛 PdfRangeError。"""
    path = str(path or "").strip()
    if not path:
        return ""
    s, e, total = get_range(owner_of(path, item, *fallbacks), path)
    if not is_partial(s, e, total):
        return path
    return extract_pages(path, s, e)


def effective_page_count(item, path: str, *fallbacks) -> int:
    """这份 PDF 里被选中的页数（整份 = 总页数）。"""
    s, e, total = get_range(owner_of(path, item, *fallbacks), path)
    return (e - s + 1) if total > 0 else 0
