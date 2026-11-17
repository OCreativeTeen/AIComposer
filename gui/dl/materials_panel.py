"""STORY 窗口「材料」区：一个列表显示这一条的 PDF、全部图片、音频/视频、文字稿。

每一项有小预览（图片缩略图、视频一帧、音频波形、PDF 第一页），单击选中（作为生成场景的材料），
双击用 Windows 默认程序打开（没有文件的行 = 选文件），右键有这一项的操作菜单（含拷到剪贴板）；音频 / 视频有 ▶ 播放按钮。
条目由调用方给（``get_entries``），动作由调用方的回调完成，这里只管画和交互。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import queue
import threading
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable

from PIL import Image, ImageTk

THUMB_W, THUMB_H = 96, 60
ROW_PAD = 3
ROW_H = THUMB_H + 2 * ROW_PAD
_SELECTED_BG = "#d7e6f8"
_NORMAL_BG = "#ffffff"
_KIND_ICON = {"pdf": "PDF", "image": "图片", "audio": "音频", "video": "视频", "transcript": "文字稿"}
_thumb_cache: dict[tuple, Image.Image | None] = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------- rename offer
# 拖进 / 选进材料时，文件名像自动生成的就不问「要不要改项目名」。
_GENERIC_STEM_PATTERNS = [re.compile(p, re.I) for p in (
    r"^nblm[\s_-]",                                     # NotebookLM 下载
    r"^aicomposer_",                                    # 本程序的临时文件
    r"^(content|untitled|document|download|file|new|output|export|slides?|presentation|"
    r"image|video|audio|scan|recording|voice|movie|clip|track)([\s_-]*(\(\d+\)|\d+))?$",
    r"^(img|dsc|dscn|dcim|pxl|vid|mov|mvimg|wp|photo|pic|rec|audio|voice|screenshot|screen[\s_]?shot|"
    r"wechat|weixin|whatsapp[\s_](image|video|audio))[\s_-]*\d",  # IMG_1234, Screenshot 2026-…, WhatsApp Image 2026…
    r"^(chunk|part|page|scene|slide|frame|clip_image|clip|seg|segment)[\s_-]*\d+",  # chunk_*, scene_3
    r"^\d+$",                                            # 纯数字（时间戳等）
    r"^\d{4}[-_.]?\d{2}[-_.]?\d{2}([\sT_-]?\d{2}[-_.:]?\d{2}([-_.:]?\d{2})?)?([\s_-]*\(?\d+\)?)?$",  # 2026-10-17 10.15.00
    r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$",  # uuid
    r"^[0-9a-f]{16,}$",                                 # 长 hex
)]


def is_generic_file_stem(stem: str) -> bool:
    """文件名（不带扩展名）是不是自动起的名字（nblm_*、content、时间戳、IMG_1234、chunk_* …）。"""
    s = (stem or "").strip()
    if len(s) < 2:
        return True
    return any(p.search(s) for p in _GENERIC_STEM_PATTERNS)


def rename_offer_stem(path: str, current_name: str) -> str:
    """该问「改项目名」时返回文件名 stem；同名或是自动名字就返回空。"""
    stem = os.path.splitext(os.path.basename(path or ""))[0].strip()
    if not stem or is_generic_file_stem(stem):
        return ""
    if stem.casefold() == (current_name or "").strip().casefold():
        return ""
    return stem


# ---------------------------------------------------------------- previews
def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or ""


def _run_ffmpeg_to_png(args: list[str]) -> Image.Image | None:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return None
    fd, out = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run([ffmpeg, "-y", *args, out], capture_output=True, timeout=40, creationflags=flags)
        if not os.path.isfile(out) or os.path.getsize(out) <= 0:
            return None
        with Image.open(out) as img:
            img.load()
            return img.copy()
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def pdf_first_page(path: str) -> Image.Image | None:
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    try:
        if len(doc) <= 0:
            return None
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(0.3, 0.3), alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception:
        return None
    finally:
        try:
            doc.close()
        except Exception:
            pass


def video_frame(path: str) -> Image.Image | None:
    return _run_ffmpeg_to_png(["-ss", "0.5", "-i", path, "-frames:v", "1", "-vf", "scale=240:-2"])


def audio_waveform(path: str) -> Image.Image | None:
    return _run_ffmpeg_to_png(
        ["-i", path, "-filter_complex", f"showwavespic=s={THUMB_W * 2}x{THUMB_H * 2}:colors=#3a7bd5", "-frames:v", "1"]
    )


def image_thumb(path: str) -> Image.Image | None:
    try:
        with Image.open(path) as img:
            img.load()
            return img.copy()
    except Exception:
        return None


def make_preview(kind: str, path: str) -> Image.Image | None:
    """Thumbnail-sized PIL image for one material (cached by path + mtime)."""
    if not path or not os.path.isfile(path):
        return None
    try:
        key = (kind, os.path.abspath(path), os.path.getmtime(path))
    except OSError:
        return None
    with _cache_lock:
        if key in _thumb_cache:
            return _thumb_cache[key]
    img = {"pdf": pdf_first_page, "video": video_frame, "audio": audio_waveform, "image": image_thumb}.get(
        kind, lambda _p: None
    )(path)
    if img is not None:
        img = img.convert("RGB")
        img.thumbnail((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
    with _cache_lock:
        _thumb_cache[key] = img
    return img


# ---------------------------------------------------------------- open
def open_with_default_app(path: str, *, startfile=None, popen=None, platform=None) -> str:
    """t206u: 用系统默认程序打开 path（Windows os.startfile；macOS open；其它 xdg-open）。
    成功返回 ""，否则返回一句给用户看的原因。startfile / popen / platform 给测试替换用。"""
    import sys

    p = os.path.abspath(path) if path else ""
    if not p or not os.path.isfile(p):
        return f"文件不在磁盘上了：\n{path or '（没有路径）'}"
    plat = platform or sys.platform
    try:
        if plat.startswith("win"):
            (startfile or os.startfile)(p)  # type: ignore[attr-defined]
        else:
            (popen or subprocess.Popen)(["open" if plat == "darwin" else "xdg-open", p])
        return ""
    except (OSError, AttributeError) as exc:
        return f"打不开：\n{p}\n{exc}"


# ---------------------------------------------------------------- playback
class Player:
    """One playback at a time: ffplay (``-nodisp`` for audio) if present, else ``os.startfile``."""

    def __init__(self) -> None:
        self.proc = None
        self.path = ""

    def playing(self, path: str = "") -> bool:
        alive = self.proc is not None and self.proc.poll() is None
        return alive and (not path or os.path.normcase(path) == os.path.normcase(self.path))

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.kill()
            except OSError:
                pass
        self.proc = None
        self.path = ""

    def toggle(self, path: str, kind: str) -> bool:
        """Start or stop ``path``. Returns True when it is now playing in-process."""
        if self.playing(path):
            self.stop()
            return False
        self.stop()
        ffplay = shutil.which("ffplay")
        if ffplay:
            cmd = [ffplay, "-autoexit", "-loglevel", "quiet"]
            if kind == "audio":
                cmd.append("-nodisp")
            cmd.append(path)
            try:
                self.proc = subprocess.Popen(cmd)
                self.path = path
                return True
            except OSError:
                pass
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            pass
        return False


# ---------------------------------------------------------------- panel
class MaterialsPanel(ttk.Frame):
    """List of material entries. An entry is a dict:

    ``{"kind": pdf|image|audio|video|transcript, "path": str, "title": str, "detail": str,
       "select": material_var value or "", "placeholder": bool}``

    t267: PDF 行（``pages`` > 0 且给了 ``on_pdf_range``）右边有「开始页」「结束页」两个数字框（``page_start`` / ``page_end``）。
    数字框一改就调 ``on_pdf_range(entry, which, start, end) -> (start, end, detail_text)``：调用方夹范围（开始 ≤ 结束、1..总页数）、
    记下、保存，这里把两个框和说明文字换成它返回的值。不重建列表（重建会把正在点的数字框销毁）。
    """

    def __init__(
        self,
        master,
        *,
        get_entries: Callable[[], list[dict]],
        on_select: Callable[[dict], None],
        on_copy: Callable[[dict], None],
        build_menu: Callable[[tk.Menu, dict], None],
        on_rebuilt: Callable[[tk.Widget], None] | None = None,
        height: int = 190,
        on_analyze: Callable[[dict], None] | None = None,
        on_delete: Callable[[dict], None] | None = None,
        on_reorder_images: Callable[[list[str]], None] | None = None,
        on_pdf_range: Callable[[dict, str, int, int], tuple] | None = None,
        hint: bool = True,
        on_focus: Callable[[dict], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_focus = on_focus  # t277: 点中一行（含空位）后通知调用方（STORY 窗的提示行跟着变）
        self._on_pdf_range = on_pdf_range
        self.range_spins: dict[str, dict] = {}  # PDF 路径 → {"start": Spinbox, "end": Spinbox}
        self._on_reorder_images = on_reorder_images
        self._drag: dict | None = None  # t214u: 图片行拖动排序
        self._drop_line: tk.Frame | None = None
        self._on_analyze = on_analyze
        self._on_delete = on_delete
        self.focused_entry: dict | None = None  # 最后单击的那一行（Delete 键删它）
        self._get_entries = get_entries
        self._on_select = on_select
        self._on_copy = on_copy
        self._build_menu = build_menu
        self._on_rebuilt = on_rebuilt
        self._photos: list = []
        self._thumb_q: queue.Queue = queue.Queue()
        self._thumb_poll_id = None
        self._rows: list[tuple[dict, list[tk.Widget]]] = []
        self.selected = ""
        self.player = Player()
        self._last_click = (None, 0.0)  # t207u: (行的 key, 时间) —— 单击会重建列表，双击靠时间判断

        # t277: 原来那一长行说明（放不下被截掉）缩成一行；STORY 窗传 hint=False，自己在材料行下面放跟着选中变的提示。
        self.hint_label = None
        if hint:
            from gui.dl.material_hint import NONE as _HINT_NONE

            self.hint_label = ttk.Label(self, text=_HINT_NONE, font=("TkDefaultFont", 8), foreground="gray30")
            self.hint_label.pack(anchor=tk.W, pady=(0, 2))
        box = tk.Frame(self, bd=1, relief=tk.SUNKEN, bg=_NORMAL_BG)
        box.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(box, height=height, bg=_NORMAL_BG, highlightthickness=0)
        sb = ttk.Scrollbar(box, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.canvas, bg=_NORMAL_BG)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<MouseWheel>", self._wheel)
            w.bind("<Button-3>", lambda e: self._popup(e, {"kind": "", "path": "", "placeholder": True}))
            w.bind("<Delete>", self._delete_key)
        self.bind("<Destroy>", lambda e: self.player.stop() if e.widget is self else None)
        # t214u: 单击会重建列表（按下的控件被销毁），拖动/松开改挂在顶层窗口上（add，不顶掉别的绑定）
        top = self.winfo_toplevel()
        top.bind("<B1-Motion>", self._drag_motion, add="+")
        top.bind("<ButtonRelease-1>", self._drag_release, add="+")

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def refresh(self, selected: str | None = None) -> None:
        if selected is not None:
            self.selected = selected
        for child in self.inner.winfo_children():
            child.destroy()
        self._photos.clear()
        self._rows.clear()
        self.range_spins.clear()
        try:
            entries = list(self._get_entries() or [])
        except Exception as exc:
            entries = [{"kind": "", "path": "", "title": f"读取材料失败：{exc}", "detail": "", "placeholder": True}]
        for entry in entries:
            self._add_row(entry)
        self._paint_selection()
        if self._on_rebuilt:
            try:
                self._on_rebuilt(self.inner)
            except Exception:
                pass

    def _add_row(self, entry: dict) -> None:
        kind = entry.get("kind") or ""
        # Every row has the same fixed pixel height (the video tile size); a text-only
        # Label would size itself in characters, so the tile is a fixed-size Frame.
        row = tk.Frame(self.inner, bg=_NORMAL_BG, bd=0, height=ROW_H)
        row.pack(fill=tk.X)
        row.pack_propagate(False)
        tile = tk.Frame(row, bg="#eeeeee", width=THUMB_W, height=THUMB_H)
        tile.pack(side=tk.LEFT, padx=4, pady=ROW_PAD)
        tile.pack_propagate(False)
        thumb = tk.Label(tile, bg="#eeeeee", text=entry.get("tile") or _KIND_ICON.get(kind, ""),
                         font=("TkDefaultFont", 8), fg="gray40", bd=0)
        thumb.pack(fill=tk.BOTH, expand=True)
        text = tk.Frame(row, bg=_NORMAL_BG)
        text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 4))
        title = tk.Label(text, text=entry.get("title") or "", bg=_NORMAL_BG, anchor="w",
                         font=("TkDefaultFont", 9, "italic" if entry.get("placeholder") else "bold"),
                         fg="gray45" if entry.get("placeholder") else "black")
        title.pack(fill=tk.X)
        detail = tk.Label(text, text=entry.get("detail") or "", bg=_NORMAL_BG, anchor="w", justify=tk.LEFT,
                          font=("TkDefaultFont", 8), fg="gray30")
        detail.pack(fill=tk.X)
        widgets: list[tk.Widget] = [row, tile, thumb, text, title, detail]
        if self._on_analyze and entry.get("analyze") and entry.get("path") and not entry.get("placeholder"):
            # 「分析」：只用这一项的文字（PDF 文字 / 文字稿）作原始材料生成分析报告。
            analyze_btn = ttk.Button(row, text="分析", width=5,
                                     command=lambda en=entry: self._on_analyze(en))
            analyze_btn.pack(side=tk.RIGHT, padx=(4, 2))
        if (
            self._on_pdf_range
            and kind == "pdf"
            and entry.get("path")
            and not entry.get("placeholder")
            and int(entry.get("pages") or 0) > 0
        ):
            widgets.extend(self._add_range_controls(row, entry, detail))
        if kind in ("audio", "video") and entry.get("path"):
            play_btn = ttk.Button(row, text="▶", width=3)
            play_btn.configure(command=lambda e=entry, b=play_btn: self._toggle_play(e, b))
            play_btn.pack(side=tk.RIGHT, padx=(4, 2))
            if self.player.playing(entry["path"]):
                play_btn.configure(text="■")
        # t207u: 单击选材料会让调用方 refresh() 整个列表（控件全重建），Tk 的 <Double-Button-1> 永远到不了
        # 新控件；所以双击在 _click 里按时间 + 同一行判断。所有子控件都绑上（缩略图、标题、说明、行本身）。
        def _bind_all(w):
            if isinstance(w, (ttk.Button, ttk.Spinbox)) or getattr(w, "_aic_skip_bind", False):
                return  # 按钮 / 页范围数字框自己处理点击，不当成「点了这一行」
            w.bind("<Button-1>", lambda e, en=entry: self._click(en, e))
            # 控件没被重建时，第二下会匹配 <Double-Button-1>（不再触发 <Button-1>），同样交给 _click 计时判断
            w.bind("<Double-Button-1>", lambda e, en=entry: self._click(en, e))
            w.bind("<Button-3>", lambda e, en=entry: self._popup(e, en))
            w.bind("<MouseWheel>", self._wheel)
            for c in w.winfo_children():
                _bind_all(c)

        _bind_all(row)
        self._rows.append((entry, widgets))
        if entry.get("path") and kind in ("pdf", "image", "audio", "video"):
            self._load_thumb_async(kind, entry["path"], thumb)

    def _add_range_controls(self, row: tk.Frame, entry: dict, detail_label: tk.Label) -> list:
        """PDF 行右边的「开始页 [n]  结束页 [m]」。返回要跟着行一起涂选中底色的控件。"""
        total = int(entry.get("pages") or 0)
        start = int(entry.get("page_start") or 1)
        end = int(entry.get("page_end") or total)
        box = tk.Frame(row, bg=_NORMAL_BG)
        box._aic_skip_bind = True  # type: ignore[attr-defined]
        box.pack(side=tk.RIGHT, padx=(4, 6))
        vars_ = {"start": tk.StringVar(value=str(start)), "end": tk.StringVar(value=str(end))}
        painted: list = [box]
        spins = {}
        for col, (which, caption) in enumerate((("start", "开始页"), ("end", "结束页"))):
            lab = tk.Label(box, text=caption, bg=_NORMAL_BG, font=("TkDefaultFont", 8), fg="gray30")
            lab.grid(row=0, column=col * 2, padx=(6 if col else 0, 2))
            painted.append(lab)
            spin = ttk.Spinbox(
                box, from_=1, to=total, width=4, wrap=False, textvariable=vars_[which],
                command=lambda w=which: self._commit_range(entry, w, vars_, detail_label),
            )
            spin.grid(row=0, column=col * 2 + 1)
            spin.bind("<Return>", lambda _e, w=which: self._commit_range(entry, w, vars_, detail_label))
            spin.bind("<FocusOut>", lambda _e, w=which: self._commit_range(entry, w, vars_, detail_label))
            spins[which] = spin
        self.range_spins[os.path.normcase(os.path.abspath(entry.get("path") or ""))] = spins  # 给测试看
        return painted

    def _commit_range(self, entry: dict, which: str, vars_: dict, detail_label: tk.Label) -> None:
        """数字框改了（点箭头 / 回车 / 离开输入框）：交给调用方夹范围并保存，再把结果写回两个框。"""
        if not self._on_pdf_range:
            return
        total = int(entry.get("pages") or 0)
        cur_s = int(entry.get("page_start") or 1)
        cur_e = int(entry.get("page_end") or total)
        try:
            typed = int(str(vars_[which].get()).strip())
        except (ValueError, tk.TclError):
            typed = cur_s if which == "start" else cur_e  # 乱填：退回原来的
        start = typed if which == "start" else cur_s
        end = typed if which == "end" else cur_e
        try:
            s, e, text = self._on_pdf_range(entry, which, start, end)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ PDF 页范围没有保存：{exc}")
            s, e, text = cur_s, cur_e, None
        entry["page_start"], entry["page_end"] = s, e
        try:
            vars_["start"].set(str(s))
            vars_["end"].set(str(e))
            if text is not None:
                entry["detail"] = text
                detail_label.configure(text=text)
        except tk.TclError:
            pass  # 这一行已经被重建销毁了

    def _load_thumb_async(self, kind: str, path: str, label: tk.Label) -> None:
        def work():
            img = make_preview(kind, path)
            if img is None:
                return
            self._thumb_q.put((label, img))

        threading.Thread(target=work, daemon=True, name="material-thumb").start()
        self._ensure_thumb_poll()

    def _ensure_thumb_poll(self) -> None:
        # Tk is not thread-safe: workers only enqueue, the Tk thread applies.
        if self._thumb_poll_id is None:
            self._thumb_poll_id = self.after(50, self._drain_thumbs)

    def _drain_thumbs(self) -> None:
        self._thumb_poll_id = None
        while True:
            try:
                label, img = self._thumb_q.get_nowait()
            except queue.Empty:
                break
            self._set_thumb(label, img)
        if any(t.is_alive() for t in threading.enumerate() if t.name == "material-thumb"):
            self._ensure_thumb_poll()

    def _set_thumb(self, label: tk.Label, img: Image.Image) -> None:
        try:
            if not label.winfo_exists():
                return
            photo = ImageTk.PhotoImage(img)
            self._photos.append(photo)
            label.configure(image=photo, text="")
        except tk.TclError:
            pass

    def _toggle_play(self, entry: dict, button) -> None:
        now = self.player.toggle(entry["path"], entry.get("kind") or "")
        for e, ws in self._rows:
            for w in ws:
                if isinstance(w, ttk.Button):
                    w.configure(text="▶")
        try:
            button.configure(text="■" if now else "▶")
        except tk.TclError:
            pass

    def _delete_key(self, _event=None):
        entry = self.focused_entry
        if self._on_delete and entry and entry.get("path") and not entry.get("placeholder"):
            self._on_delete(entry)
        return "break"

    DOUBLE_MS = 500

    @staticmethod
    def _entry_key(entry: dict) -> tuple:
        return (entry.get("kind") or "", os.path.normcase(entry.get("path") or ""), entry.get("title") or "")

    def _click(self, entry: dict, event=None):
        import time

        now = time.monotonic()
        key = self._entry_key(entry)
        last_key, last_t = self._last_click
        if last_key == key and (now - last_t) * 1000 <= self.DOUBLE_MS:
            self._last_click = (None, 0.0)
            return self._double(entry)
        self._last_click = (key, now)
        self.focused_entry = entry
        if (
            self._on_reorder_images
            and entry.get("kind") == "image"
            and entry.get("path")
            and not entry.get("placeholder")
            and event is not None
        ):
            self._drag = {"path": entry["path"], "x": event.x_root, "y": event.y_root, "active": False}
        else:
            self._drag = None
        try:
            self.canvas.focus_set()  # 让 Delete 键落到这个面板
        except tk.TclError:
            pass
        sel = entry.get("select") or ""
        if sel:
            self.selected = sel
            self._paint_selection()
            self._on_select(entry)
        self._notify_focus(entry)
        return "break"

    def _notify_focus(self, entry: dict) -> None:
        if self._on_focus:
            try:
                self._on_focus(entry)
            except Exception:  # noqa: BLE001
                pass

    def select_entry(self, entry: dict) -> None:
        """t406u: 右键「选作生成材料」= 单击选中：记成点中的那一行（语音 / 视频概览就用这一个文件），涂色，再通知调用方。"""
        if not (entry.get("select") or "") or entry.get("placeholder"):
            return
        self.focused_entry = entry
        self._last_click = (None, 0.0)
        self.selected = entry.get("select") or ""
        self._paint_selection()
        self._on_select(entry)
        self._notify_focus(entry)

    def _double(self, entry: dict):
        print(f"📂 材料双击：{entry.get('kind') or '?'} · {entry.get('path') or '（没有文件）'}")
        self._on_copy(entry)
        return "break"

    def _popup(self, event, entry: dict):
        menu = tk.Menu(self, tearoff=0)
        try:
            self._build_menu(menu, entry)
        except Exception as exc:
            menu.add_command(label=f"菜单出错：{exc}", state=tk.DISABLED)
        if menu.index("end") is None:
            return "break"
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _paint_selection(self) -> None:
        for entry, widgets in self._rows:
            on = bool(self.selected) and (entry.get("select") or "") == self.selected and not entry.get("placeholder")
            bg = _SELECTED_BG if on else _NORMAL_BG
            for w in widgets:
                if isinstance(w, (tk.Frame, tk.Label)) and not (isinstance(w, tk.Label) and w is widgets[1]):
                    try:
                        w.configure(bg=bg)
                    except tk.TclError:
                        pass


    # ------------------------------------------------------------ t214u drag reorder
    DRAG_PX = 6

    def _image_paths_and_rows(self) -> tuple[list[str], list[tk.Widget]]:
        paths, rows = [], []
        for entry, widgets in self._rows:
            if entry.get("kind") == "image" and entry.get("path") and not entry.get("placeholder"):
                paths.append(entry["path"])
                rows.append(widgets[0])
        return paths, rows

    def _insert_index(self, y_root: int, rows: list) -> int:
        idx = 0
        for r in rows:
            try:
                mid = r.winfo_rooty() + r.winfo_height() / 2
            except tk.TclError:
                continue
            if y_root > mid:
                idx += 1
        return idx

    def _drag_motion(self, event):
        d = self._drag
        if not d:
            return None
        if not d["active"]:
            if abs(event.x_root - d["x"]) < self.DRAG_PX and abs(event.y_root - d["y"]) < self.DRAG_PX:
                return None
            d["active"] = True
            self._last_click = (None, 0.0)  # 拖动不算双击
            try:
                self.winfo_toplevel().configure(cursor="sb_v_double_arrow")
            except tk.TclError:
                pass
        paths, rows = self._image_paths_and_rows()
        if not rows:
            return None
        idx = self._insert_index(event.y_root, rows)
        try:
            if self._drop_line is None or not self._drop_line.winfo_exists():
                self._drop_line = tk.Frame(self.inner, bg="#1e6fd9", height=3)
            if idx < len(rows):
                y = rows[idx].winfo_y()
            else:
                y = rows[-1].winfo_y() + rows[-1].winfo_height() - 2
            self._drop_line.place(x=0, y=max(0, y - 1), relwidth=1.0, height=3)
            self._drop_line.lift()
        except tk.TclError:
            pass
        return None

    def _hide_drop_line(self) -> None:
        try:
            if self._drop_line is not None and self._drop_line.winfo_exists():
                self._drop_line.place_forget()
        except tk.TclError:
            pass
        try:
            self.winfo_toplevel().configure(cursor="")
        except tk.TclError:
            pass

    def _drag_release(self, event):
        d, self._drag = self._drag, None
        if not d or not d.get("active"):
            return None
        self._hide_drop_line()
        paths, rows = self._image_paths_and_rows()
        new = reorder_paths(paths, d["path"], self._insert_index(event.y_root, rows))
        if new != paths and self._on_reorder_images:
            print(f"🖼 图片排序：{os.path.basename(d['path'])} → 第 {new.index(d['path']) + 1} 张")
            self._on_reorder_images(new)
        return "break"


def reorder_paths(paths: list[str], moving: str, insert_idx: int) -> list[str]:
    """t214u: 把 ``moving`` 挪到插入位置 ``insert_idx``（按原列表的行间位置算，0 = 最前）。"""
    key = os.path.normcase(os.path.abspath(moving))
    keys = [os.path.normcase(os.path.abspath(p)) for p in paths]
    if key not in keys:
        return list(paths)
    src = keys.index(key)
    rest = [p for i, p in enumerate(paths) if i != src]
    dst = insert_idx - (1 if insert_idx > src else 0)
    dst = max(0, min(dst, len(rest)))
    rest.insert(dst, paths[src])
    return rest
