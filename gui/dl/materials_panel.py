"""STORY 窗口「材料」区：一个列表显示这一条的 PDF、全部图片、音频/视频、文字稿。

每一项有小预览（图片缩略图、视频一帧、音频波形、PDF 第一页），单击选中（作为生成场景的材料），
双击拷到剪贴板，右键有这一项的操作菜单；音频 / 视频有 ▶ 播放按钮。
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
    ) -> None:
        super().__init__(master)
        self._on_analyze = on_analyze
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

        ttk.Label(
            self,
            text="把 PDF、图片、音频或 mp4 拖到这里：PDF 换掉原来的，图片加进列表，音频/视频换掉原来的。"
            "单击选作生成材料，双击拷到剪贴板，右键更多操作。",
            font=("TkDefaultFont", 8),
            foreground="gray30",
        ).pack(anchor=tk.W, pady=(0, 2))
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
        self.bind("<Destroy>", lambda e: self.player.stop() if e.widget is self else None)

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
        if kind in ("audio", "video") and entry.get("path"):
            play_btn = ttk.Button(row, text="▶", width=3)
            play_btn.configure(command=lambda e=entry, b=play_btn: self._toggle_play(e, b))
            play_btn.pack(side=tk.RIGHT, padx=(4, 2))
            if self.player.playing(entry["path"]):
                play_btn.configure(text="■")
        for w in widgets:
            w.bind("<Button-1>", lambda _e, en=entry: self._click(en))
            w.bind("<Double-Button-1>", lambda _e, en=entry: self._double(en))
            w.bind("<Button-3>", lambda e, en=entry: self._popup(e, en))
            w.bind("<MouseWheel>", self._wheel)
        self._rows.append((entry, widgets))
        if entry.get("path") and kind in ("pdf", "image", "audio", "video"):
            self._load_thumb_async(kind, entry["path"], thumb)

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

    def _click(self, entry: dict):
        sel = entry.get("select") or ""
        if sel:
            self.selected = sel
            self._paint_selection()
            self._on_select(entry)
        return "break"

    def _double(self, entry: dict):
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
