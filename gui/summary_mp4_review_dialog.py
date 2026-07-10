"""摘要窗拖入 MP4：审阅、裁剪片段、调整顺序，确认后末帧延长、拼接并加水印保存。"""
from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pygame
except ImportError:
    pygame = None

try:
    from tkinterdnd2 import DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    DND_FILES = None

from PIL import Image, ImageTk

import config
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.ffmpeg_processor import FfmpegProcessor, ffmpeg_path
from utility.file_util import safe_copy_overwrite, safe_remove


def _parse_dnd_mp4_paths(widget, raw) -> list[str]:
    if raw is None or str(raw).strip() == "":
        return []
    try:
        paths = list(widget.tk.splitlist(str(raw)))
    except tk.TclError:
        paths = [str(raw)]
    out: list[str] = []
    for raw_path in paths:
        p = (raw_path or "").strip()
        if p.startswith("{") and p.endswith("}"):
            p = p[1:-1]
        p = os.path.normpath(p)
        if p.lower().endswith(".mp4") and os.path.isfile(p):
            out.append(p)
    return out


class _ClipState:
    __slots__ = ("path", "duration", "fps", "frame_count", "start", "end", "speed")

    def __init__(self, path: str, duration: float, fps: float, frame_count: int):
        self.path = os.path.normpath(path)
        self.fps = max(1.0, float(fps))
        self.frame_count = max(1, int(frame_count))
        dur_frames = self.frame_count / self.fps
        self.duration = max(0.01, float(duration), dur_frames)
        self.start = 0.0
        self.end = self.duration
        self.speed = 1.0


SPEED_MIN = 0.7
SPEED_MAX = 1.2
SPEED_STEP = 0.1
CLIP_END_FREEZE_SEC = 0.66


def _fmt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:d}:{s:05.2f}"


def _probe_video_meta(path: str, ff: FfmpegProcessor) -> tuple[float, float, int]:
    """返回 (duration_sec, fps, frame_count)。"""
    abs_path = os.path.abspath(path)
    dur = float(ff.get_playback_duration(abs_path, fresh=True) or 0.0)
    fps = 30.0
    fc = 0
    if cv2 is not None:
        cap = cv2.VideoCapture(abs_path)
        if cap.isOpened():
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            if fps < 1 or fps > 240:
                fps = 30.0
            fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
    if fc <= 0 and dur > 0:
        fc = max(1, int(round(dur * fps)))
    if dur > 0 and fc > 0 and fps > 0:
        dur = max(dur, fc / fps)
    elif dur <= 0 and fc > 0:
        dur = fc / fps
    return max(0.01, dur), fps, max(1, fc)


class SummaryMp4ReviewDialog:
    """多段 MP4 审阅：列表排序、预览播放、起止裁剪。"""

    _HANDLE_PX = 10
    _MIN_CLIP_SEC = 0.1

    def __init__(
        self,
        parent,
        mp4_paths: list[str] | None = None,
        *,
        initial_segments: list[dict] | None = None,
        pid: str,
        lang: str,
    ):
        self.pid = pid or "yt_wm"
        self.lang = lang or "zh"
        self.ff = FfmpegProcessor(self.pid, self.lang)
        self.ff_audio = FfmpegAudioProcessor(self.pid)
        self.confirmed: list[dict] | None = None

        self.clips: list[_ClipState] = []
        if initial_segments:
            for seg in initial_segments:
                if not isinstance(seg, dict):
                    continue
                p = os.path.normpath((seg.get("path") or "").strip())
                if not p or not os.path.isfile(p) or not p.lower().endswith(".mp4"):
                    print(f"⚠️ 审阅窗跳过无效片段: {p or seg}")
                    continue
                dur, fps, fc = _probe_video_meta(p, self.ff)
                c = _ClipState(p, dur, fps, fc)
                try:
                    c.start = float(seg.get("start", 0.0))
                    c.end = float(seg.get("end", c.duration))
                    c.speed = round(float(seg.get("speed") or 1.0), 1)
                except (TypeError, ValueError):
                    c.start = 0.0
                    c.end = c.duration
                    c.speed = 1.0
                c.start = self._snap_time(c, c.start)
                c.end = self._snap_time(c, c.end)
                if c.end <= c.start + self._MIN_CLIP_SEC:
                    c.end = self._snap_time(c, min(c.duration, c.start + self._MIN_CLIP_SEC))
                c.speed = max(SPEED_MIN, min(SPEED_MAX, c.speed))
                self.clips.append(c)
            print(f"📎 审阅窗从配置载入 {len(self.clips)} 个片段")
        else:
            paths = [
                os.path.normpath(p)
                for p in (mp4_paths or [])
                if (p or "").strip() and os.path.isfile(p) and p.lower().endswith(".mp4")
            ]
            if not paths:
                raise ValueError("无有效 MP4")
            for p in paths:
                dur, fps, fc = _probe_video_meta(p, self.ff)
                self.clips.append(_ClipState(p, dur, fps, fc))
            print(f"📎 审阅窗载入 {len(self.clips)} 个 MP4（输入 {len(mp4_paths or [])} 项）")

        if not self.clips:
            raise ValueError("无有效 MP4 片段")
        for i, c in enumerate(self.clips, 1):
            print(f"  {i}. {os.path.basename(c.path)}")

        self._sel = 0
        self._drag_from: int | None = None
        self._drag_press_y: int | None = None
        self._drag_moved = False
        self._video_cap = None
        self._playing = False
        self._after_id = None
        self._click_after_id = None
        self._current_t = 0.0
        self._full_audio = ""
        self._play_audio_path = ""
        self._play_audio_key: tuple | None = None
        self._photo = None
        self._pygame_ok = False
        self._play_wall_start = 0.0
        self._play_media_start = 0.0
        self._play_media_stop = 0.0
        self._play_speed = 1.0
        self._tl_drag: str | None = None
        self._has_audio = False
        self._syncing_ui = False

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("审阅成片片段 — 裁剪与排序")
        self.dlg.geometry("1060x720")
        self.dlg.minsize(900, 600)
        self.dlg.transient(parent)
        self.dlg.grab_set()
        self.dlg.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._build_ui()
        self._select_clip(0)
        self.dlg.update_idletasks()
        sw = self.dlg.winfo_screenwidth()
        sh = self.dlg.winfo_screenheight()
        self.dlg.geometry(f"1060x720+{(sw - 1060) // 2}+{(sh - 720) // 2}")

    def _snap_time(self, c: _ClipState, t: float) -> float:
        t = max(0.0, min(float(t), c.duration))
        frame = int(round(t * c.fps))
        frame = max(0, min(frame, c.frame_count - 1))
        return frame / c.fps

    def _build_ui(self) -> None:
        root = ttk.Frame(self.dlg, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            root,
            text="片段自上而下为拼接顺序；拖动左侧列表项可调整顺序；"
            "拖放 .mp4 到列表可追加片段（同一文件可出现多次，各段独立裁剪）；"
            "选中后按 Delete 可删除。"
            "单击预览区播放/暂停；双击预览区按选中区间播放（含速度）。"
            "拖动时间轴两端把手设定起止；◀/▶ 调整区间速度（0.7–1.2）。",
            wraplength=1000,
        ).pack(anchor=tk.W, pady=(0, 8))

        body = ttk.Frame(root)
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(body, text="片段列表（拖动排序 / 拖放追加）", padding=6)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        self.listbox = tk.Listbox(left, width=42, height=22, exportselection=False)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)

        self.listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self.listbox.bind("<ButtonPress-1>", self._on_list_press, add="+")
        self.listbox.bind("<B1-Motion>", self._on_list_motion, add="+")
        self.listbox.bind("<ButtonRelease-1>", self._on_list_release, add="+")
        self.listbox.bind("<Delete>", self._on_delete_key)
        self.listbox.bind("<KP_Delete>", self._on_delete_key)
        self.dlg.bind("<Delete>", self._on_delete_key)
        self.dlg.bind("<KP_Delete>", self._on_delete_key)
        if DND_AVAILABLE:
            self._setup_clip_drop_targets(left, self.listbox)

        btn_col = ttk.Frame(left)
        btn_col.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_col, text="▲", width=4, command=self._move_up).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(btn_col, text="▼", width=4, command=self._move_down).pack(side=tk.LEFT)

        right = ttk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.preview_canvas = tk.Canvas(
            right, bg="black", height=360, highlightthickness=1, highlightbackground="#444"
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.preview_canvas.bind("<Button-1>", self._on_preview_click)
        self.preview_canvas.bind("<Double-Button-1>", self._on_preview_double_click)

        self.time_lbl = ttk.Label(right, text="")
        self.time_lbl.pack(anchor=tk.W)

        trim_box = ttk.LabelFrame(right, text="选中区间（拖动时间轴把手；数值按帧对齐）", padding=8)
        trim_box.pack(fill=tk.X, pady=(6, 0))

        spin_row = ttk.Frame(trim_box)
        spin_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(spin_row, text="起点").pack(side=tk.LEFT, padx=(0, 4))
        self.start_spin = ttk.Spinbox(
            spin_row, from_=0.0, to=9999.0, increment=0.01, width=10,
            command=self._on_spin_commit,
        )
        self.start_spin.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(spin_row, text="终点").pack(side=tk.LEFT, padx=(0, 4))
        self.end_spin = ttk.Spinbox(
            spin_row, from_=0.0, to=9999.0, increment=0.01, width=10,
            command=self._on_spin_commit,
        )
        self.end_spin.pack(side=tk.LEFT, padx=(0, 12))
        for sp in (self.start_spin, self.end_spin):
            sp.bind("<Return>", lambda _e: self._on_spin_commit())
            sp.bind("<FocusOut>", lambda _e: self._on_spin_commit())
        ttk.Button(spin_row, text="设为播放位置→起点", command=self._set_start_to_playhead).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(spin_row, text="设为播放位置→终点", command=self._set_end_to_playhead).pack(
            side=tk.LEFT
        )

        speed_row = ttk.Frame(trim_box)
        speed_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(speed_row, text="区间速度", width=8).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(speed_row, text="◀", width=3, command=self._speed_down).pack(side=tk.LEFT)
        self.speed_lbl = ttk.Label(speed_row, text="1.0×", width=8, anchor=tk.CENTER)
        self.speed_lbl.pack(side=tk.LEFT, padx=4)
        ttk.Button(speed_row, text="▶", width=3, command=self._speed_up).pack(side=tk.LEFT)
        ttk.Label(
            speed_row,
            text="（0.7–1.2，步进 0.1；仅作用于选中区间，导出时音画同步变速）",
            foreground="#555",
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.sel_dur_lbl = ttk.Label(trim_box, text="选中时长: —", foreground="#0a5a9e")
        self.sel_dur_lbl.pack(anchor=tk.W, pady=(0, 4))

        self.timeline = tk.Canvas(trim_box, height=52, bg="#e8e8e8", highlightthickness=0, cursor="hand2")
        self.timeline.pack(fill=tk.X, pady=(4, 0))
        self.timeline.bind("<Configure>", lambda _e: self._draw_timeline())
        self.timeline.bind("<ButtonPress-1>", self._on_tl_press)
        self.timeline.bind("<B1-Motion>", self._on_tl_drag)
        self.timeline.bind("<ButtonRelease-1>", self._on_tl_release)

        foot = ttk.Frame(root)
        foot.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(foot, text="取消", command=self._on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(
            foot,
            text="确认并保存（裁剪→末帧延长→拼接→水印）",
            command=self._on_confirm,
        ).pack(side=tk.RIGHT)

        self._refresh_listbox()

    def _clip_label(self, idx: int, c: _ClipState) -> str:
        name = os.path.basename(c.path)
        spd = f" @{c.speed:.1f}×" if abs(c.speed - 1.0) > 0.001 else ""
        return f"{idx + 1}. {name}  [{_fmt_time(c.start)} – {_fmt_time(c.end)}{spd}]"

    def _refresh_listbox(self) -> None:
        sel = self._sel
        self.listbox.delete(0, tk.END)
        for i, c in enumerate(self.clips):
            self.listbox.insert(tk.END, self._clip_label(i, c))
        if 0 <= sel < len(self.clips):
            self.listbox.selection_set(sel)
            self.listbox.see(sel)

    def _save_trim_to_clip(self) -> None:
        if not (0 <= self._sel < len(self.clips)):
            return
        c = self.clips[self._sel]
        try:
            s = float(self.start_spin.get())
            e = float(self.end_spin.get())
        except (tk.TclError, ValueError):
            s, e = c.start, c.end
        s = self._snap_time(c, s)
        e = self._snap_time(c, e)
        if e < s + self._MIN_CLIP_SEC:
            e = self._snap_time(c, s + self._MIN_CLIP_SEC)
        c.start = max(0.0, min(s, c.duration - self._MIN_CLIP_SEC))
        c.end = max(c.start + self._MIN_CLIP_SEC, min(e, c.duration))
        c.start = self._snap_time(c, c.start)
        c.end = self._snap_time(c, c.end)
        self._play_audio_key = None

    def _apply_clip_to_ui(self, c: _ClipState) -> None:
        self._syncing_ui = True
        try:
            self.start_spin.config(to=c.duration)
            self.end_spin.config(to=c.duration)
            self.start_spin.delete(0, tk.END)
            self.start_spin.insert(0, f"{c.start:.3f}")
            self.end_spin.delete(0, tk.END)
            self.end_spin.insert(0, f"{c.end:.3f}")
            self.speed_lbl.config(text=f"{c.speed:.1f}×")
            self._update_trim_labels()
            self._draw_timeline()
        finally:
            self._syncing_ui = False

    def _speed_up(self) -> None:
        c = self.clips[self._sel]
        c.speed = round(min(SPEED_MAX, c.speed + SPEED_STEP), 1)
        self._play_audio_key = None
        self._apply_clip_to_ui(c)
        self._refresh_listbox()

    def _speed_down(self) -> None:
        c = self.clips[self._sel]
        c.speed = round(max(SPEED_MIN, c.speed - SPEED_STEP), 1)
        self._play_audio_key = None
        self._apply_clip_to_ui(c)
        self._refresh_listbox()

    def _select_clip(self, idx: int) -> None:
        if not (0 <= idx < len(self.clips)):
            return
        if self._sel != idx and 0 <= self._sel < len(self.clips):
            self._save_trim_to_clip()
        self._sel = idx
        self._stop_play()
        c = self.clips[idx]
        self._apply_clip_to_ui(c)
        self._has_audio = self.ff.has_audio_stream(c.path)
        self._full_audio = ""
        self._play_audio_key = None
        threading.Thread(target=self._load_audio_bg, args=(c.path,), daemon=True).start()
        self._show_frame_at(c, c.start)
        self._refresh_listbox()

    def _load_audio_bg(self, path: str) -> None:
        if not self._has_audio:
            return
        try:
            ap = self.ff_audio.extract_audio_from_video(path, "wav") or ""
        except Exception:
            ap = ""
        if 0 <= self._sel < len(self.clips) and self.clips[self._sel].path == path:
            self._full_audio = ap

    def _on_list_select(self, _event=None) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx != self._sel:
            self._select_clip(idx)

    def _on_list_press(self, event) -> None:
        self._drag_from = self.listbox.nearest(event.y)
        self._drag_press_y = event.y
        self._drag_moved = False

    def _on_list_motion(self, event) -> None:
        if self._drag_press_y is not None and abs(event.y - self._drag_press_y) > 6:
            self._drag_moved = True

    def _on_list_release(self, event) -> None:
        if self._drag_from is None:
            return
        if not self._drag_moved:
            self._drag_from = None
            self._drag_press_y = None
            return
        self._save_trim_to_clip()
        to_idx = self.listbox.nearest(event.y)
        fr = self._drag_from
        self._drag_from = None
        self._drag_press_y = None
        self._drag_moved = False
        if to_idx < 0 or fr < 0 or to_idx == fr:
            return
        if not (0 <= fr < len(self.clips) and 0 <= to_idx < len(self.clips)):
            return
        item = self.clips.pop(fr)
        self.clips.insert(to_idx, item)
        self._select_clip(to_idx)

    def _move_up(self) -> None:
        i = self._sel
        if i <= 0:
            return
        self._save_trim_to_clip()
        self.clips[i - 1], self.clips[i] = self.clips[i], self.clips[i - 1]
        self._select_clip(i - 1)

    def _move_down(self) -> None:
        i = self._sel
        if i >= len(self.clips) - 1:
            return
        self._save_trim_to_clip()
        self.clips[i + 1], self.clips[i] = self.clips[i], self.clips[i + 1]
        self._select_clip(i + 1)

    def _on_delete_key(self, _event=None) -> None:
        focus = self.dlg.focus_get()
        if focus in (self.start_spin, self.end_spin):
            return
        self._delete_selected_clip()
        return "break"

    def _delete_selected_clip(self) -> None:
        if len(self.clips) <= 1:
            messagebox.showinfo("删除片段", "至少保留一个片段。", parent=self.dlg)
            return
        if not (0 <= self._sel < len(self.clips)):
            return
        self._save_trim_to_clip()
        idx = self._sel
        self.clips.pop(idx)
        self._select_clip(min(idx, len(self.clips) - 1))

    def _setup_clip_drop_targets(self, *widgets) -> None:
        for w in widgets:
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_clip_dnd_drop)
            except (tk.TclError, AttributeError, Exception):
                pass

    def _on_clip_dnd_drop(self, event) -> None:
        paths = _parse_dnd_mp4_paths(self.dlg, getattr(event, "data", None))
        if paths:
            self._add_clips_from_paths(paths)

    def _add_clips_from_paths(self, paths: list[str]) -> None:
        self._save_trim_to_clip()
        added = 0
        for p in paths:
            dur, fps, fc = _probe_video_meta(p, self.ff)
            self.clips.append(_ClipState(p, dur, fps, fc))
            added += 1
        if not added:
            return
        print(f"📎 审阅窗追加 {added} 个 MP4")
        self._select_clip(len(self.clips) - 1)

    def _on_spin_commit(self) -> None:
        if self._syncing_ui:
            return
        self._save_trim_to_clip()
        c = self.clips[self._sel]
        self._apply_clip_to_ui(c)
        self._refresh_listbox()

    def _set_start_to_playhead(self) -> None:
        c = self.clips[self._sel]
        c.start = self._snap_time(c, self._current_t)
        if c.end <= c.start + self._MIN_CLIP_SEC:
            c.end = self._snap_time(c, min(c.duration, c.start + self._MIN_CLIP_SEC))
        self._apply_clip_to_ui(c)
        self._refresh_listbox()

    def _set_end_to_playhead(self) -> None:
        c = self.clips[self._sel]
        c.end = self._snap_time(c, self._current_t)
        if c.end <= c.start + self._MIN_CLIP_SEC:
            c.start = self._snap_time(c, max(0.0, c.end - self._MIN_CLIP_SEC))
        self._apply_clip_to_ui(c)
        self._refresh_listbox()

    def _update_trim_labels(self) -> None:
        if not (0 <= self._sel < len(self.clips)):
            return
        c = self.clips[self._sel]
        seg = max(0.0, c.end - c.start)
        out_dur = seg / max(0.01, c.speed)
        spd_note = ""
        if abs(c.speed - 1.0) > 0.001:
            spd_note = f"  → 输出 {_fmt_time(out_dur)}（×{c.speed:.1f}）"
        self.time_lbl.config(
            text=(
                f"{os.path.basename(c.path)}  ·  "
                f"{_fmt_time(self._current_t)} / {_fmt_time(c.duration)}  "
                f"({c.fps:.2f} fps)"
            )
        )
        self.sel_dur_lbl.config(
            text=(
                f"选中时长: {_fmt_time(seg)} / 全长 {_fmt_time(c.duration)}  "
                f"[帧 {int(round(c.start * c.fps))} – {int(round(c.end * c.fps))}]"
                f"{spd_note}"
            )
        )

    def _tl_x_to_time(self, x: float) -> float:
        c = self.clips[self._sel]
        w = max(self.timeline.winfo_width(), 200)
        frac = max(0.0, min(1.0, (x - 2) / max(1, w - 4)))
        return self._snap_time(c, frac * c.duration)

    def _time_to_tl_x(self, t: float) -> float:
        c = self.clips[self._sel]
        w = max(self.timeline.winfo_width(), 200)
        if c.duration <= 0:
            return 2.0
        return 2 + (t / c.duration) * (w - 4)

    def _tl_hit(self, x: float) -> str:
        c = self.clips[self._sel]
        x0 = self._time_to_tl_x(c.start)
        x1 = self._time_to_tl_x(c.end)
        if abs(x - x0) <= self._HANDLE_PX:
            return "start"
        if abs(x - x1) <= self._HANDLE_PX:
            return "end"
        if x0 < x < x1:
            return "scrub"
        return "seek"

    def _on_tl_press(self, event) -> None:
        self._save_trim_to_clip()
        self._tl_drag = self._tl_hit(event.x)
        if self._tl_drag == "seek":
            self._tl_drag = "scrub"
        self._on_tl_drag(event)

    def _on_tl_drag(self, event) -> None:
        c = self.clips[self._sel]
        t = self._tl_x_to_time(event.x)
        if self._tl_drag == "start":
            c.start = min(t, c.end - self._MIN_CLIP_SEC)
            c.start = self._snap_time(c, c.start)
        elif self._tl_drag == "end":
            c.end = max(t, c.start + self._MIN_CLIP_SEC)
            c.end = self._snap_time(c, c.end)
        elif self._tl_drag == "scrub":
            self._current_t = t
            self._show_frame_at(c, t)
        self._apply_clip_to_ui(c)
        self._refresh_listbox()

    def _on_tl_release(self, _event) -> None:
        self._tl_drag = None

    def _draw_timeline(self) -> None:
        if not (0 <= self._sel < len(self.clips)):
            return
        c = self.clips[self._sel]
        cv = self.timeline
        cv.delete("all")
        w = max(cv.winfo_width(), 200)
        cv.create_rectangle(2, 18, w - 2, 34, fill="#c8c8c8", outline="#999")
        if c.duration <= 0:
            return
        x0 = self._time_to_tl_x(c.start)
        x1 = self._time_to_tl_x(c.end)
        cv.create_rectangle(x0, 14, x1, 38, fill="#4a9fd8", outline="#2a6fa0", width=2)
        for x, tag in ((x0, "起点"), (x1, "终点")):
            cv.create_rectangle(
                x - self._HANDLE_PX, 10, x + self._HANDLE_PX, 42,
                fill="#2a6fa0", outline="#1a4f70",
            )
            cv.create_text(x, 48, text=tag, fill="#333", font=("Arial", 8))
        if self._playing or self._current_t > 0:
            xp = self._time_to_tl_x(self._current_t)
            cv.create_line(xp, 8, xp, 44, fill="#e03030", width=2)
        cv.create_text(4, 4, anchor=tk.NW, text="0:00", fill="#555", font=("Arial", 8))
        cv.create_text(
            w - 4, 4, anchor=tk.NE, text=_fmt_time(c.duration), fill="#555", font=("Arial", 8)
        )

    def _init_pygame(self) -> None:
        if not pygame or self._pygame_ok:
            return
        try:
            pygame.mixer.init(frequency=44100, buffer=512)
            self._pygame_ok = True
        except Exception:
            self._pygame_ok = False

    def _atempo_wav(self, wav_path: str, speed: float) -> str:
        if abs(speed - 1.0) < 0.001 or not wav_path or not os.path.isfile(wav_path):
            return wav_path
        out = config.get_temp_file(self.pid, "wav")
        try:
            self.ff.run_ffmpeg_command([
                ffmpeg_path, "-y", "-i", wav_path,
                "-af", f"atempo={speed:.6f}",
                out,
            ])
            return out if os.path.isfile(out) else wav_path
        except Exception:
            return wav_path

    def _prepare_play_audio(self, start_t: float, stop_t: float, speed: float) -> str:
        c = self.clips[self._sel]
        spd = round(float(speed or 1.0), 1)
        key = (c.path, round(start_t, 4), round(stop_t, 4), spd)
        if key == self._play_audio_key and self._play_audio_path:
            return self._play_audio_path
        self._play_audio_path = ""
        if not self._has_audio or not self._full_audio or not os.path.isfile(self._full_audio):
            self._play_audio_key = key
            return ""
        length = max(0.05, stop_t - start_t)
        try:
            ap = self.ff_audio.audio_cut_fade(self._full_audio, start_t, length) or ""
        except Exception:
            ap = ""
        if ap and abs(spd - 1.0) > 0.001:
            ap = self._atempo_wav(ap, spd)
        self._play_audio_path = ap
        self._play_audio_key = key
        return ap

    def _show_frame_at(self, c: _ClipState, t: float) -> None:
        if cv2 is None:
            return
        t = self._snap_time(c, t)
        self._current_t = t
        cap = cv2.VideoCapture(c.path)
        if not cap.isOpened():
            return
        frame_idx = int(round(t * c.fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        if ret:
            self._paint_frame(frame)
        self._update_trim_labels()
        self._draw_timeline()

    def _paint_frame(self, frame) -> None:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(frame_rgb)
        cw = max(self.preview_canvas.winfo_width(), 400)
        ch = max(self.preview_canvas.winfo_height(), 240)
        pil.thumbnail((cw - 8, ch - 8), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(pil)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=self._photo)

    def _open_cap(self) -> bool:
        if cv2 is None:
            return False
        c = self.clips[self._sel]
        if self._video_cap:
            try:
                self._video_cap.release()
            except Exception:
                pass
        self._video_cap = cv2.VideoCapture(c.path)
        return bool(self._video_cap and self._video_cap.isOpened())

    def _seek_cap_frame(self, frame_idx: int) -> None:
        if not self._video_cap:
            return
        c = self.clips[self._sel]
        frame_idx = max(0, min(frame_idx, c.frame_count - 1))
        self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        self._current_t = frame_idx / c.fps

    def _start_play(self, *, range_only: bool) -> None:
        if cv2 is None:
            messagebox.showwarning("预览", "未安装 OpenCV，无法播放。", parent=self.dlg)
            return
        self._save_trim_to_clip()
        c = self.clips[self._sel]
        if range_only:
            start_t = c.start
            stop_t = c.end
            self._play_speed = max(0.01, float(c.speed))
        else:
            start_t = self._current_t
            stop_t = c.duration
            self._play_speed = 1.0
        start_t = self._snap_time(c, start_t)
        stop_t = self._snap_time(c, stop_t)
        if start_t >= stop_t - (1.0 / c.fps):
            messagebox.showwarning("预览", "选中区间过短。", parent=self.dlg)
            return

        self._stop_play(release_cap=True)
        if not self._open_cap():
            messagebox.showerror("预览", "无法打开视频。", parent=self.dlg)
            return

        self._play_media_start = start_t
        self._play_media_stop = stop_t
        self._seek_cap_frame(int(round(start_t * c.fps)))
        ret, frame = self._video_cap.read()
        if ret:
            self._current_t = int(round(start_t * c.fps)) / c.fps
            self._paint_frame(frame)
            self._update_trim_labels()
            self._draw_timeline()

        ap = self._prepare_play_audio(start_t, stop_t, self._play_speed)
        self._init_pygame()

        if ap and self._pygame_ok and pygame:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.load(ap)
            except Exception:
                ap = ""

        self._play_wall_start = time.perf_counter()
        if ap and self._pygame_ok and pygame:
            try:
                pygame.mixer.music.play()
            except Exception:
                pass

        self._playing = True
        self._play_tick()

    def _play_tick(self) -> None:
        if not self._playing or not self.dlg.winfo_exists():
            return
        c = self.clips[self._sel]
        speed = max(0.01, self._play_speed)
        elapsed = time.perf_counter() - self._play_wall_start
        seg_wall = (self._play_media_stop - self._play_media_start) / speed
        target_t = self._play_media_start + elapsed * speed
        stop_t = self._play_media_stop

        if elapsed >= seg_wall - (0.5 / c.fps):
            self._current_t = stop_t
            self._update_trim_labels()
            self._draw_timeline()
            self._stop_play()
            return

        self._current_t = min(target_t, stop_t)
        self._update_trim_labels()
        self._draw_timeline()

        if self._has_audio and self._pygame_ok and pygame and self._play_audio_path:
            try:
                if not pygame.mixer.music.get_busy():
                    self._stop_play()
                    return
            except Exception:
                pass

        if self._video_cap and self._video_cap.isOpened():
            cur_frame = int(self._video_cap.get(cv2.CAP_PROP_POS_FRAMES))
            target_frame = int(round(target_t * c.fps))
            if target_frame > cur_frame:
                if target_frame - cur_frame > 2:
                    self._seek_cap_frame(target_frame)
                ret, frame = self._video_cap.read()
                if ret:
                    self._paint_frame(frame)

        self._after_id = self.dlg.after(15, self._play_tick)

    def _stop_play(self, *, release_cap: bool = True) -> None:
        self._playing = False
        if self._after_id and self.dlg.winfo_exists():
            try:
                self.dlg.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._pygame_ok and pygame:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        if release_cap and self._video_cap:
            try:
                self._video_cap.release()
            except Exception:
                pass
            self._video_cap = None
        self._draw_timeline()

    def _on_preview_click(self, _event) -> None:
        if self._click_after_id and self.dlg.winfo_exists():
            try:
                self.dlg.after_cancel(self._click_after_id)
            except tk.TclError:
                pass
        self._click_after_id = self.dlg.after(280, self._toggle_play_single)

    def _toggle_play_single(self) -> None:
        self._click_after_id = None
        if self._playing:
            self._stop_play()
        else:
            self._start_play(range_only=False)

    def _on_preview_double_click(self, _event) -> None:
        if self._click_after_id and self.dlg.winfo_exists():
            try:
                self.dlg.after_cancel(self._click_after_id)
            except tk.TclError:
                pass
            self._click_after_id = None
        self._stop_play()
        self._start_play(range_only=True)

    def _on_confirm(self) -> None:
        self._save_trim_to_clip()
        for i, c in enumerate(self.clips):
            if c.end <= c.start + (1.0 / c.fps):
                messagebox.showerror(
                    "区间无效",
                    f"第 {i + 1} 段结束时间必须大于开始时间。",
                    parent=self.dlg,
                )
                return
        self.confirmed = [
            {
                "path": c.path,
                "start": c.start,
                "end": c.end,
                "speed": round(float(c.speed), 1),
            }
            for c in self.clips
        ]
        self._stop_play()
        self.dlg.destroy()

    def _on_cancel(self) -> None:
        self.confirmed = None
        self._stop_play()
        self.dlg.destroy()


def ask_summary_mp4_review_segments(
    parent,
    mp4_paths: list[str] | None = None,
    *,
    initial_segments: list[dict] | None = None,
    pid: str,
    lang: str,
) -> list[dict] | None:
    """审阅并返回 ``[{path, start, end, speed}, ...]``；取消返回 ``None``。"""
    dlg = SummaryMp4ReviewDialog(
        parent,
        mp4_paths,
        initial_segments=initial_segments,
        pid=pid,
        lang=lang,
    )
    parent.wait_window(dlg.dlg)
    return dlg.confirmed


def run_trim_concat_watermark_worker(
    *,
    segments: list[dict],
    pid: str,
    lang: str,
    wm_path: str,
    wm_opts: dict,
    gen_dir: str,
    dest_name: str,
    on_done,
) -> None:
    """后台：逐段 trim → 末帧延长 → concat → watermark → 写入 gen_video。"""

    def _worker():
        out_ok = ""
        err_msg = ""
        stage_tmps: list[str] = []
        concat_tmp = ""
        wm_tmp = ""
        try:
            os.makedirs(gen_dir, exist_ok=True)
            ff = FfmpegProcessor(pid, lang)
            processed: list[str] = []
            for seg in segments:
                p = seg["path"]
                st = float(seg["start"])
                en = float(seg["end"])
                spd = float(seg.get("speed") or 1.0)
                tp = ff.trim_video(p, st, en, volume=1.0, speed=spd)
                if not tp:
                    err_msg = f"裁剪失败：{os.path.basename(p)}"
                    return
                stage_tmps.append(tp)
                frozen = ff.extend_clip_end_with_last_frame(tp, CLIP_END_FREEZE_SEC)
                if not frozen:
                    err_msg = f"末帧延长 {CLIP_END_FREEZE_SEC:.2f}s 失败：{os.path.basename(p)}"
                    return
                if frozen != tp:
                    stage_tmps.append(frozen)
                processed.append(frozen)
            if len(processed) == 1:
                source = processed[0]
            else:
                source = ff.concat_videos(processed, True)
                concat_tmp = source or ""
                if not source:
                    err_msg = f"拼接 {len(processed)} 段失败。"
                    return
            wm_tmp = config.get_temp_file(pid, "mp4")
            ok = ff.apply_watermark_to_video(
                source, wm_tmp, wm_path, wm_opts or {}
            )
            if not ok:
                err_msg = "叠加水印失败。"
                return
            dest_abs = os.path.join(gen_dir, dest_name)
            safe_copy_overwrite(wm_tmp, dest_abs)
            FfmpegProcessor.invalidate_duration_cache(dest_abs)
            safe_remove(wm_tmp)
            wm_tmp = ""
            out_ok = dest_abs
        except Exception as ex:
            err_msg = str(ex)
        finally:
            for t in stage_tmps:
                if t and t != out_ok and t != concat_tmp:
                    try:
                        safe_remove(t)
                    except Exception:
                        pass
            if concat_tmp and concat_tmp not in stage_tmps and concat_tmp != out_ok:
                try:
                    safe_remove(concat_tmp)
                except Exception:
                    pass
            if wm_tmp:
                try:
                    safe_remove(wm_tmp)
                except Exception:
                    pass
        on_done(out_ok, err_msg, len(segments))

    threading.Thread(target=_worker, daemon=True).start()
