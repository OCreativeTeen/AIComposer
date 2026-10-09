"""从文件夹挑选 MP4：预览、裁剪起止、变速、音量；确认后产出临时 mp4/wav。"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional, Tuple, Union

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pygame
except ImportError:
    pygame = None

try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    _RECORDING_OK = True
except ImportError:
    sd = None
    sf = None
    np = None
    _RECORDING_OK = False

from PIL import Image, ImageTk

from utility.ffmpeg_audio_processor import ffmpeg_path, ffprobe_path

_PREVIEW_SPEED_MIN = 0.7
_PREVIEW_SPEED_MAX = 1.2
_PREVIEW_SPEED_STEP = 0.1
_PREVIEW_MIN_CLIP_SEC = 0.1
_PREVIEW_HANDLE_PX = 10


def _fmt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:d}:{s:05.2f}"


def _snap_mp4_preview_volume(raw: float) -> float:
    v = round(float(raw) * 2.0) / 2.0
    return max(0.5, min(2.0, v))


def _is_audio_path(path: str) -> bool:
    return os.path.splitext(path or "")[1].lower() in (".mp3", ".wav", ".m4a", ".aac")


def _probe_audio_duration(path: str) -> float:
    try:
        r = subprocess.run(
            [
                ffprobe_path, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            check=False, capture_output=True, text=True, encoding="utf-8", errors="ignore",
        )
        return max(0.01, float((r.stdout or "").strip() or 0.01))
    except Exception:
        return 0.01


def _probe_mp4_meta(path: str) -> tuple[float, float, int]:
    abs_path = os.path.abspath(path)
    dur = 0.01
    fps = 30.0
    fc = 1
    if cv2 is not None:
        cap = cv2.VideoCapture(abs_path)
        if cap.isOpened():
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            if fps < 1 or fps > 240:
                fps = 30.0
            fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            dur = fc / fps if fc > 0 and fps > 0 else 0.01
            cap.release()
    return max(0.01, dur), max(1.0, fps), max(1, fc)


def _ffprobe_video_has_audio(file_path: str) -> bool:
    try:
        r = subprocess.run(
            [
                ffprobe_path, "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=codec_type", "-of", "csv=p=0", file_path,
            ],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="ignore",
        )
        return bool(r.stdout.strip())
    except Exception:
        return False


def _ffmpeg_atempo_filter(speed: float) -> str:
    """``atempo`` 单次仅支持 0.5–2.0，必要时链式拼接。"""
    s = float(speed or 1.0)
    if abs(s - 1.0) < 0.001:
        return ""
    parts: list[str] = []
    while s < 0.5 - 1e-9:
        parts.append("atempo=0.5")
        s /= 0.5
    while s > 2.0 + 1e-9:
        parts.append("atempo=2.0")
        s /= 2.0
    if abs(s - 1.0) > 0.001:
        parts.append(f"atempo={s:.6f}")
    return ",".join(parts)


def _ffmpeg_extract_segment_raw_wav(
    video_path: str, start: float, length: float, volume: float, out_wav: str,
) -> bool:
    if length <= 0:
        return False
    vol = float(volume or 1.0)
    af = f"volume={vol}" if abs(vol - 1.0) > 0.001 else "anull"
    try:
        r = subprocess.run(
            [
                ffmpeg_path, "-y",
                "-ss", f"{max(0.0, float(start)):.6f}",
                "-i", video_path,
                "-t", f"{length:.6f}",
                "-vn", "-af", af,
                "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le",
                out_wav,
            ],
            check=False, capture_output=True, text=True, encoding="utf-8", errors="ignore",
        )
        return r.returncode == 0 and os.path.isfile(out_wav)
    except Exception:
        return False


def _ffmpeg_apply_atempo_wav(in_wav: str, speed: float, out_wav: str) -> bool:
    chain = _ffmpeg_atempo_filter(speed)
    if not chain:
        try:
            import shutil
            shutil.copy2(in_wav, out_wav)
            return os.path.isfile(out_wav)
        except Exception:
            return False
    try:
        r = subprocess.run(
            [
                ffmpeg_path, "-y", "-i", in_wav,
                "-af", chain,
                "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le",
                out_wav,
            ],
            check=False, capture_output=True, text=True, encoding="utf-8", errors="ignore",
        )
        return r.returncode == 0 and os.path.isfile(out_wav)
    except Exception:
        return False


def _build_preview_segment_wav(
    video_path: str, start: float, stop: float, speed: float, volume: float,
) -> str:
    """裁剪区间 wav，再按 speed 做 atempo（慢放时输出时长 = 区间/speed）。"""
    length = max(0.05, float(stop) - float(start))
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    if not _ffmpeg_extract_segment_raw_wav(video_path, start, length, volume, tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return ""
    spd = float(speed or 1.0)
    if abs(spd - 1.0) < 0.001:
        return tmp
    fd2, tmp2 = tempfile.mkstemp(suffix=".wav")
    os.close(fd2)
    if _ffmpeg_apply_atempo_wav(tmp, spd, tmp2):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return tmp2
    return tmp


class _ClipTrim:
    __slots__ = ("path", "duration", "fps", "frame_count", "start", "end", "speed", "is_audio")

    def __init__(self, path: str):
        self.path = os.path.normpath(path)
        self.is_audio = _is_audio_path(path)
        if self.is_audio:
            dur = _probe_audio_duration(path)
            fps, fc = 100.0, max(1, int(round(dur * 100.0)))
        else:
            dur, fps, fc = _probe_mp4_meta(path)
        self.duration = dur
        self.fps = fps
        self.frame_count = fc
        self.start = 0.0
        self.end = dur
        self.speed = 1.0


def ask_mp4_pick_with_trim_preview(
    title: str,
    choices: list,
    folder_path: str,
    parent=None,
    *,
    build_adjusted_pair: Optional[
        Callable[..., Tuple[str, str]]
    ] = None,
    confirm_actions: Optional[list] = None,
    radios: Optional[tuple] = None,
    sources: Optional[list] = None,
    audio_sources: Optional[list] = None,
    dest_options: Optional[list] = None,
    lock_video_source: bool = False,
) -> Union[dict, Tuple[str, str, str], Tuple[str, str, str, str], None]:
    """
  左侧文件列表 + 右侧裁剪/变速预览。
  ``build_adjusted_pair(full_path, volume, start=, end=, speed=) -> (tmp_mp4, tmp_wav)``
    """
    if parent is None:
        try:
            parent = tk._default_root
        except Exception:
            parent = None
    if sources and not lock_video_source:
        usable = [item for item in sources if item.get("choices")]
        if not usable or build_adjusted_pair is None or cv2 is None:
            if cv2 is None and parent:
                messagebox.showwarning("预览", "需要安装 opencv-python 才能预览视频。", parent=parent)
            return None
        current = next((item for item in sources if item.get("key") == "download"), usable[0])
        folder_path = current["folder"]
        choices = list(current["choices"])
        radios = current.get("radios")
        confirm_actions = current.get("confirm_actions")
    elif sources and lock_video_source:
        if build_adjusted_pair is None or cv2 is None or not choices:
            if cv2 is None and parent:
                messagebox.showwarning("预览", "需要安装 opencv-python 才能预览视频。", parent=parent)
            return None
        current = sources[0]
        radios = None
        confirm_actions = current.get("confirm_actions")
    elif not choices or build_adjusted_pair is None or cv2 is None:
        if cv2 is None and parent:
            messagebox.showwarning("预览", "需要安装 opencv-python 才能预览视频。", parent=parent)
        return None

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.geometry("980x760" if audio_sources else "980x640")
    dlg.minsize(900, 680 if audio_sources else 580)
    if parent:
        dlg.transient(parent)
    dlg.grab_set()

    result: list = [None]
    folder_box = [folder_path]
    radio_holder = [radios]
    confirm_holder = [confirm_actions]
    clip = [_ClipTrim(os.path.join(folder_box[0], choices[0]))]
    sel_fn = [choices[0]]

    playing = [False]
    play_range_only = [False]
    play_wall_start = [0.0]
    play_media_start = [0.0]
    play_media_stop = [0.0]
    play_speed = [1.0]
    current_t = [0.0]
    after_id = [None]
    click_after_id = [None]
    video_cap = [None]
    preview_wav = [None]
    preview_audio_job = [0]
    photo = [None]
    tl_drag = [None]
    syncing_ui = [False]
    pygame_ok = [False]

    root = ttk.Frame(dlg, padding=10)
    root.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        root,
        text="拖动时间轴设定起止；单击预览播放/暂停；双击按选中区间播放（含速度）。",
        wraplength=920,
    ).pack(anchor=tk.W, pady=(0, 8))

    body = ttk.Frame(root)
    body.pack(fill=tk.BOTH, expand=True)

    left = ttk.LabelFrame(body, text="文件列表", padding=6)
    left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
    choice_style = ttk.Style(dlg)
    choice_style.configure("PickChoice.TLabel", font=("Microsoft YaHei UI", 14))
    choice_style.configure("PickChoice.TRadiobutton", font=("Microsoft YaHei UI", 14))
    choice_box = ttk.Frame(left)
    if sources or radios:
        choice_box.pack(fill=tk.X, anchor=tk.W, pady=(0, 8))
    video_box = ttk.LabelFrame(left, text="片段列表", padding=4)
    video_box.pack(fill=tk.BOTH, expand=True)
    listbox = tk.Listbox(
        video_box, width=42, height=8 if audio_sources else 22,
        exportselection=False, font=("Consolas", 9),
    )
    listbox.pack(fill=tk.BOTH, expand=True)
    for c in choices:
        listbox.insert(tk.END, c)
    audio_box = None
    audio_listbox = None
    audio_source_var = tk.StringVar(value="")
    audio_choices: list = []
    audio_folder_box = [""]
    audio_state = {"clip": None, "fn": "", "armed": False}
    rec = {
        "on": False,
        "chunks": [],
        "thread": None,
        "dialog": None,
        "folder": "",
        "started": 0.0,
        "rate": 44100,
        "channels": 1,
        "time_label": None,
    }
    focus = ["video"]
    if audio_sources:
        usable_audio = [item for item in audio_sources if item.get("folder")]
        if usable_audio:
            audio_source_var.set(usable_audio[0]["key"])
            audio_folder_box[0] = usable_audio[0]["folder"]
            audio_choices.extend(usable_audio[0].get("choices") or [])
        audio_box = ttk.LabelFrame(left, text="音频", padding=4)
        audio_box.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        if len(usable_audio) > 1:
            audio_src_row = ttk.Frame(audio_box)
            audio_src_row.pack(fill=tk.X, anchor=tk.W, pady=(0, 4))
            ttk.Label(audio_src_row, text="来源").pack(side=tk.LEFT, padx=(0, 6))
            for item in usable_audio:
                ttk.Radiobutton(
                    audio_src_row, text=item["label"], value=item["key"], variable=audio_source_var,
                ).pack(side=tk.LEFT, padx=(0, 8))
        audio_listbox = tk.Listbox(
            audio_box, width=42, height=8, exportselection=False, font=("Consolas", 9),
        )
        audio_listbox.pack(fill=tk.BOTH, expand=True)
        for name in audio_choices:
            audio_listbox.insert(tk.END, name)
        record_row = ttk.Frame(audio_box)
        record_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(record_row, text="录音", command=lambda: _start_record()).pack(side=tk.LEFT)

    right = ttk.Frame(body)
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    preview_canvas = tk.Canvas(right, bg="black", height=280, highlightthickness=1, highlightbackground="#444")
    preview_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

    time_lbl = ttk.Label(right, text="")
    time_lbl.pack(anchor=tk.W)

    trim_box = ttk.LabelFrame(right, text="选中区间", padding=8)
    trim_box.pack(fill=tk.X, pady=(4, 0))

    spin_row = ttk.Frame(trim_box)
    spin_row.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(spin_row, text="起点").pack(side=tk.LEFT, padx=(0, 4))
    start_spin = ttk.Spinbox(spin_row, from_=0.0, to=9999.0, increment=0.01, width=10)
    start_spin.pack(side=tk.LEFT, padx=(0, 12))
    ttk.Label(spin_row, text="终点").pack(side=tk.LEFT, padx=(0, 4))
    end_spin = ttk.Spinbox(spin_row, from_=0.0, to=9999.0, increment=0.01, width=10)
    end_spin.pack(side=tk.LEFT, padx=(0, 12))
    ttk.Button(spin_row, text="设为播放位置→起点", command=lambda: _set_start_playhead()).pack(
        side=tk.LEFT, padx=(0, 6)
    )
    ttk.Button(spin_row, text="设为播放位置→终点", command=lambda: _set_end_playhead()).pack(side=tk.LEFT)

    speed_row = ttk.Frame(trim_box)
    speed_row.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(speed_row, text="区间速度", width=8).pack(side=tk.LEFT)
    ttk.Button(speed_row, text="◀", width=3, command=lambda: _speed_down()).pack(side=tk.LEFT)
    speed_lbl = ttk.Label(speed_row, text="1.0×", width=8, anchor=tk.CENTER)
    speed_lbl.pack(side=tk.LEFT, padx=4)
    ttk.Button(speed_row, text="▶", width=3, command=lambda: _speed_up()).pack(side=tk.LEFT)
    ttk.Label(speed_row, text="（0.7–1.2）", foreground="#555").pack(side=tk.LEFT, padx=(8, 0))

    vol_row = ttk.Frame(trim_box)
    vol_row.pack(fill=tk.X, pady=(0, 6))
    volume_var = tk.DoubleVar(value=_snap_mp4_preview_volume(1.0))
    ttk.Label(vol_row, text="试听音量增益").pack(side=tk.LEFT, padx=(0, 8))
    vol_lbl = ttk.Label(vol_row, text=f"{volume_var.get():.1f}×", width=8)
    vol_lbl.pack(side=tk.LEFT)
    vol_slider = tk.Scale(
        vol_row, from_=0.5, to=2.0, resolution=0.5, orient=tk.HORIZONTAL,
        variable=volume_var, command=lambda _: _on_volume_change(), showvalue=0, length=220,
    )
    vol_slider.pack(side=tk.LEFT, padx=(8, 0))

    sel_dur_lbl = ttk.Label(trim_box, text="选中时长: —", foreground="#0a5a9e")
    sel_dur_lbl.pack(anchor=tk.W, pady=(0, 4))

    timeline = tk.Canvas(trim_box, height=52, bg="#e8e8e8", highlightthickness=0, cursor="hand2")
    timeline.pack(fill=tk.X, pady=(4, 0))

    radio_var = tk.StringVar(value="")
    dest_var = tk.StringVar(value=(dest_options[0][0] if dest_options else ""))
    source_var = tk.StringVar(value=(current["key"] if sources else ""))
    if sources:
        source_row = ttk.Frame(choice_box)
        source_row.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        ttk.Label(source_row, text="来源", style="PickChoice.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        source_radios = []
        for item in sources:
            rb = ttk.Radiobutton(
                source_row,
                text=item["label"],
                value=item["key"],
                variable=source_var,
                style="PickChoice.TRadiobutton",
            )
            rb.pack(side=tk.LEFT, padx=(0, 12))
            source_radios.append(rb)
        if lock_video_source:
            for rb in source_radios:
                rb.state(["disabled"])
    extra_host = ttk.Frame(choice_box)
    extra_host.pack(anchor=tk.W, fill=tk.X)
    if dest_options:
        dest_row = ttk.Frame(choice_box)
        dest_row.pack(anchor=tk.W, fill=tk.X, pady=(4, 0))
        ttk.Label(dest_row, text="放到", style="PickChoice.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        for value, label in dest_options:
            ttk.Radiobutton(
                dest_row, text=label, value=value, variable=dest_var, style="PickChoice.TRadiobutton",
            ).pack(side=tk.LEFT, padx=(0, 10))
    foot = ttk.Frame(root)
    foot.pack(fill=tk.X, pady=(10, 0))
    mix_btn = None
    if audio_sources:
        mix_btn = ttk.Button(foot, text="套用这段音频", state=tk.DISABLED)
        mix_btn.pack(side=tk.LEFT)
    btn_host = ttk.Frame(foot)
    btn_host.pack(side=tk.RIGHT)

    def _c() -> _ClipTrim:
        if focus[0] == "audio" and audio_state.get("clip") is not None:
            return audio_state["clip"]
        return clip[0]

    def _snap_time(t: float) -> float:
        c = _c()
        t = max(0.0, min(float(t), c.duration))
        frame = int(round(t * c.fps))
        frame = max(0, min(frame, c.frame_count - 1))
        return frame / c.fps

    def _save_trim() -> None:
        c = _c()
        try:
            s = float(start_spin.get())
            e = float(end_spin.get())
        except (tk.TclError, ValueError):
            s, e = c.start, c.end
        s = _snap_time(s)
        e = _snap_time(e)
        if e < s + _PREVIEW_MIN_CLIP_SEC:
            e = _snap_time(s + _PREVIEW_MIN_CLIP_SEC)
        c.start = max(0.0, min(s, c.duration - _PREVIEW_MIN_CLIP_SEC))
        c.end = max(c.start + _PREVIEW_MIN_CLIP_SEC, min(e, c.duration))

    def _apply_ui() -> None:
        syncing_ui[0] = True
        try:
            c = _c()
            start_spin.config(to=c.duration)
            end_spin.config(to=c.duration)
            start_spin.delete(0, tk.END)
            start_spin.insert(0, f"{c.start:.3f}")
            end_spin.delete(0, tk.END)
            end_spin.insert(0, f"{c.end:.3f}")
            speed_lbl.config(text=f"{c.speed:.1f}×")
            seg = max(0.0, c.end - c.start)
            out_dur = seg / max(0.01, c.speed)
            spd_note = f"  → 输出 {_fmt_time(out_dur)}（×{c.speed:.1f}）" if abs(c.speed - 1.0) > 0.001 else ""
            time_lbl.config(
                text=f"{os.path.basename(c.path)}  ·  {_fmt_time(current_t[0])} / {_fmt_time(c.duration)}  ({c.fps:.2f} fps)"
            )
            sel_dur_lbl.config(
                text=f"选中时长: {_fmt_time(seg)} / 全长 {_fmt_time(c.duration)}{spd_note}"
            )
            _draw_timeline()
        finally:
            syncing_ui[0] = False

    def _on_spin_commit(_e=None) -> None:
        if syncing_ui[0]:
            return
        _save_trim()
        _apply_ui()

    for sp in (start_spin, end_spin):
        sp.bind("<Return>", _on_spin_commit)
        sp.bind("<FocusOut>", _on_spin_commit)

    def _set_start_playhead() -> None:
        c = _c()
        c.start = _snap_time(current_t[0])
        if c.end <= c.start + _PREVIEW_MIN_CLIP_SEC:
            c.end = _snap_time(min(c.duration, c.start + _PREVIEW_MIN_CLIP_SEC))
        _apply_ui()

    def _set_end_playhead() -> None:
        c = _c()
        c.end = _snap_time(current_t[0])
        if c.end <= c.start + _PREVIEW_MIN_CLIP_SEC:
            c.start = _snap_time(max(0.0, c.end - _PREVIEW_MIN_CLIP_SEC))
        _apply_ui()

    def _speed_up() -> None:
        c = _c()
        c.speed = round(min(_PREVIEW_SPEED_MAX, c.speed + _PREVIEW_SPEED_STEP), 1)
        _apply_ui()

    def _speed_down() -> None:
        c = _c()
        c.speed = round(max(_PREVIEW_SPEED_MIN, c.speed - _PREVIEW_SPEED_STEP), 1)
        _apply_ui()

    def _time_to_x(t: float) -> float:
        c = _c()
        w = max(timeline.winfo_width(), 200)
        return 2 + (t / c.duration) * (w - 4) if c.duration > 0 else 2.0

    def _x_to_time(x: float) -> float:
        c = _c()
        w = max(timeline.winfo_width(), 200)
        frac = max(0.0, min(1.0, (x - 2) / max(1, w - 4)))
        return _snap_time(frac * c.duration)

    def _draw_timeline() -> None:
        c = _c()
        timeline.delete("all")
        w = max(timeline.winfo_width(), 200)
        timeline.create_rectangle(2, 18, w - 2, 34, fill="#c8c8c8", outline="#999")
        if c.duration <= 0:
            return
        x0, x1 = _time_to_x(c.start), _time_to_x(c.end)
        timeline.create_rectangle(x0, 14, x1, 38, fill="#4a9fd8", outline="#2a6fa0", width=2)
        for x, tag in ((x0, "起点"), (x1, "终点")):
            timeline.create_rectangle(
                x - _PREVIEW_HANDLE_PX, 10, x + _PREVIEW_HANDLE_PX, 42, fill="#2a6fa0", outline="#1a4f70",
            )
            timeline.create_text(x, 48, text=tag, fill="#333", font=("Arial", 8))
        if current_t[0] > 0 or playing[0]:
            xp = _time_to_x(current_t[0])
            timeline.create_line(xp, 8, xp, 44, fill="#e03030", width=2)

    def _show_frame(t: float) -> None:
        c = _c()
        t = _snap_time(t)
        current_t[0] = t
        if getattr(c, "is_audio", False):
            cw = max(preview_canvas.winfo_width(), 360)
            ch = max(preview_canvas.winfo_height(), 200)
            preview_canvas.delete("all")
            preview_canvas.create_text(
                cw // 2, ch // 2, text="音频\n" + os.path.basename(c.path),
                fill="white", font=("Microsoft YaHei UI", 16), justify=tk.CENTER,
            )
            _apply_ui()
            return
        cap = cv2.VideoCapture(c.path)
        if not cap.isOpened():
            return
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * c.fps)))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        cw = max(preview_canvas.winfo_width(), 360)
        ch = max(preview_canvas.winfo_height(), 200)
        pil.thumbnail((cw - 8, ch - 8), Image.Resampling.LANCZOS)
        photo[0] = ImageTk.PhotoImage(pil)
        preview_canvas.delete("all")
        preview_canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=photo[0])
        _apply_ui()

    def _init_pygame() -> None:
        if not pygame or pygame_ok[0]:
            return
        try:
            pygame.mixer.init(frequency=44100, buffer=512)
            pygame_ok[0] = True
        except Exception:
            pygame_ok[0] = False

    def _stop_preview_audio() -> None:
        preview_audio_job[0] += 1
        if pygame_ok[0] and pygame:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        wav = preview_wav[0]
        if wav and os.path.isfile(wav):
            try:
                os.remove(wav)
            except OSError:
                pass
        preview_wav[0] = None

    def _start_preview_audio(
        start_t: float, stop_t: float, speed: float, volume: float, *, on_ready=None,
    ) -> None:
        """后台生成试听 wav；完成后加载播放，并可选回调（用于同步启动视频时钟）。"""
        _stop_preview_audio()
        if not pygame or not _ffprobe_video_has_audio(_c().path):
            if callable(on_ready):
                try:
                    on_ready()
                except Exception:
                    pass
            return
        job = preview_audio_job[0]
        c = _c()
        spd = max(0.01, float(speed or 1.0))
        vol = float(volume or 1.0)

        def worker():
            wav = _build_preview_segment_wav(c.path, start_t, stop_t, spd, vol)

            def apply():
                if job != preview_audio_job[0] or not dlg.winfo_exists():
                    if wav and os.path.isfile(wav):
                        try:
                            os.remove(wav)
                        except OSError:
                            pass
                    return
                if not wav:
                    if callable(on_ready):
                        try:
                            on_ready()
                        except Exception:
                            pass
                    return
                preview_wav[0] = wav
                _init_pygame()
                if pygame_ok[0] and pygame:
                    try:
                        pygame.mixer.music.load(wav)
                        pygame.mixer.music.play()
                    except Exception:
                        pass
                if callable(on_ready):
                    try:
                        on_ready()
                    except Exception:
                        pass

            try:
                dlg.after(0, apply)
            except tk.TclError:
                if wav and os.path.isfile(wav):
                    try:
                        os.remove(wav)
                    except OSError:
                        pass

        threading.Thread(target=worker, daemon=True).start()

    def _stop_play(release_cap: bool = True) -> None:
        playing[0] = False
        play_range_only[0] = False
        if after_id[0]:
            try:
                dlg.after_cancel(after_id[0])
            except tk.TclError:
                pass
            after_id[0] = None
        _stop_preview_audio()
        if release_cap and video_cap[0]:
            try:
                video_cap[0].release()
            except Exception:
                pass
            video_cap[0] = None
        _draw_timeline()

    def _open_cap() -> bool:
        if video_cap[0]:
            try:
                video_cap[0].release()
            except Exception:
                pass
        video_cap[0] = cv2.VideoCapture(_c().path)
        return bool(video_cap[0] and video_cap[0].isOpened())

    def _start_play(*, range_only: bool) -> None:
        _save_trim()
        c = _c()
        if range_only:
            start_t, stop_t, spd = c.start, c.end, max(0.01, float(c.speed))
        else:
            start_t = max(c.start, min(current_t[0], c.end - (1.0 / c.fps)))
            stop_t, spd = c.end, 1.0
        start_t, stop_t = _snap_time(start_t), _snap_time(stop_t)
        if start_t >= stop_t - (1.0 / c.fps):
            messagebox.showwarning("预览", "选中区间过短。", parent=dlg)
            return
        _stop_play()
        if not getattr(c, "is_audio", False):
            if not _open_cap():
                return
        play_range_only[0] = range_only
        play_media_start[0] = start_t
        play_media_stop[0] = stop_t
        play_speed[0] = spd
        play_wall_start[0] = time.perf_counter()
        ret = False
        if video_cap[0]:
            video_cap[0].set(cv2.CAP_PROP_POS_FRAMES, int(round(start_t * c.fps)))
            ret, frame = video_cap[0].read()
        else:
            _show_frame(start_t)
        if ret:
            current_t[0] = start_t
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            cw = max(preview_canvas.winfo_width(), 360)
            ch = max(preview_canvas.winfo_height(), 200)
            pil.thumbnail((cw - 8, ch - 8), Image.Resampling.LANCZOS)
            photo[0] = ImageTk.PhotoImage(pil)
            preview_canvas.delete("all")
            preview_canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=photo[0])
        vol = _snap_mp4_preview_volume(volume_var.get())
        playing[0] = True

        def _begin_playback_clock():
            play_wall_start[0] = time.perf_counter()
            if video_cap[0] and video_cap[0].isOpened():
                video_cap[0].set(cv2.CAP_PROP_POS_FRAMES, int(round(start_t * c.fps)))
            _play_tick()

        _start_preview_audio(
            start_t, stop_t, spd if range_only else 1.0, vol, on_ready=_begin_playback_clock,
        )

    def _play_tick() -> None:
        if not playing[0] or not dlg.winfo_exists():
            return
        c = _c()
        spd = max(0.01, play_speed[0])
        elapsed = time.perf_counter() - play_wall_start[0]
        seg_wall = (play_media_stop[0] - play_media_start[0]) / spd
        target_t = play_media_start[0] + elapsed * spd
        stop_t = play_media_stop[0]

        if elapsed >= seg_wall - (0.5 / c.fps):
            current_t[0] = stop_t
            _draw_timeline()
            if play_range_only[0]:
                _stop_play()
                return
            play_wall_start[0] = time.perf_counter()
            play_media_start[0] = c.start
            target_t = c.start
            if video_cap[0]:
                video_cap[0].set(cv2.CAP_PROP_POS_FRAMES, int(round(c.start * c.fps)))
            vol = _snap_mp4_preview_volume(volume_var.get())
            _start_preview_audio(c.start, c.end, 1.0, vol)

        current_t[0] = min(target_t, stop_t) if play_range_only[0] else target_t
        _draw_timeline()

        if (
            play_range_only[0]
            and preview_wav[0]
            and pygame_ok[0]
            and pygame
            and _ffprobe_video_has_audio(c.path)
        ):
            try:
                if not pygame.mixer.music.get_busy() and elapsed > 0.15:
                    current_t[0] = stop_t
                    _draw_timeline()
                    _stop_play()
                    return
            except Exception:
                pass

        if video_cap[0] and video_cap[0].isOpened():
            target_frame = int(round(current_t[0] * c.fps))
            cur_frame = int(video_cap[0].get(cv2.CAP_PROP_POS_FRAMES))
            if target_frame > cur_frame:
                if target_frame - cur_frame > 2:
                    video_cap[0].set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = video_cap[0].read()
                if ret:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(rgb)
                    cw = max(preview_canvas.winfo_width(), 360)
                    ch = max(preview_canvas.winfo_height(), 200)
                    pil.thumbnail((cw - 8, ch - 8), Image.Resampling.LANCZOS)
                    photo[0] = ImageTk.PhotoImage(pil)
                    preview_canvas.delete("all")
                    preview_canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=photo[0])

        after_id[0] = dlg.after(15, _play_tick)

    def _on_volume_change() -> None:
        v = _snap_mp4_preview_volume(volume_var.get())
        volume_var.set(v)
        vol_lbl.config(text=f"{v:.1f}×")
        if playing[0]:
            c = _c()
            _start_preview_audio(play_media_start[0], play_media_stop[0], play_speed[0], v)

    def _on_tl_press(event) -> None:
        _save_trim()
        c = _c()
        x0, x1 = _time_to_x(c.start), _time_to_x(c.end)
        x = event.x
        if abs(x - x0) <= _PREVIEW_HANDLE_PX:
            tl_drag[0] = "start"
        elif abs(x - x1) <= _PREVIEW_HANDLE_PX:
            tl_drag[0] = "end"
        elif x0 < x < x1:
            tl_drag[0] = "scrub"
        else:
            tl_drag[0] = "scrub"
        _on_tl_drag(event)

    def _on_tl_drag(event) -> None:
        c = _c()
        t = _x_to_time(event.x)
        if tl_drag[0] == "start":
            c.start = _snap_time(min(t, c.end - _PREVIEW_MIN_CLIP_SEC))
        elif tl_drag[0] == "end":
            c.end = _snap_time(max(t, c.start + _PREVIEW_MIN_CLIP_SEC))
        elif tl_drag[0] == "scrub":
            current_t[0] = t
            _show_frame(t)
            return
        _apply_ui()

    def _on_tl_release(_e) -> None:
        tl_drag[0] = None

    timeline.bind("<Configure>", lambda _e: _draw_timeline())
    timeline.bind("<ButtonPress-1>", _on_tl_press)
    timeline.bind("<B1-Motion>", _on_tl_drag)
    timeline.bind("<ButtonRelease-1>", _on_tl_release)

    def _on_preview_click(_e) -> None:
        if click_after_id[0]:
            try:
                dlg.after_cancel(click_after_id[0])
            except tk.TclError:
                pass
        click_after_id[0] = dlg.after(280, _toggle_play)

    def _toggle_play() -> None:
        click_after_id[0] = None
        if playing[0]:
            _stop_play()
        else:
            _start_play(range_only=False)

    def _on_preview_double(_e) -> None:
        if click_after_id[0]:
            try:
                dlg.after_cancel(click_after_id[0])
            except tk.TclError:
                pass
            click_after_id[0] = None
        _stop_play()
        _start_play(range_only=True)

    preview_canvas.bind("<Button-1>", _on_preview_click)
    preview_canvas.bind("<Double-Button-1>", _on_preview_double)

    def _sync_mix_btn() -> None:
        if mix_btn is None:
            return
        if audio_state.get("clip") is None:
            mix_btn.config(state=tk.DISABLED, text="套用这段音频")
        elif audio_state.get("armed"):
            mix_btn.config(state=tk.NORMAL, text="已套用这段音频")
        else:
            mix_btn.config(state=tk.NORMAL, text="套用这段音频")

    def _arm_audio_mix() -> None:
        if audio_state.get("clip") is None:
            return
        _save_trim()
        audio_state["armed"] = True
        _sync_mix_btn()

    if mix_btn is not None:
        mix_btn.config(command=_arm_audio_mix)

    def _load_file(fn: str) -> None:
        _save_trim()
        _stop_play()
        focus[0] = "video"
        full = os.path.normpath(os.path.join(folder_box[0], fn))
        sel_fn[0] = fn
        if clip[0] is None or os.path.normpath(clip[0].path) != full:
            clip[0] = _ClipTrim(full)
        current_t[0] = clip[0].start
        _apply_ui()
        _show_frame(clip[0].start)

    def _load_audio(fn: str) -> None:
        _save_trim()
        _stop_play()
        focus[0] = "audio"
        full = os.path.normpath(os.path.join(audio_folder_box[0], fn))
        prev = audio_state.get("clip")
        if prev is None or os.path.normpath(prev.path) != full:
            audio_state["clip"] = _ClipTrim(full)
            audio_state["armed"] = False
        audio_state["fn"] = fn
        current_t[0] = audio_state["clip"].start
        _sync_mix_btn()
        _apply_ui()
        _show_frame(audio_state["clip"].start)

    def _on_list_select(_e=None) -> None:
        sel = listbox.curselection()
        if not sel:
            return
        fn = choices[sel[0]]
        if fn != sel_fn[0] or focus[0] != "video":
            _load_file(fn)

    listbox.bind("<<ListboxSelect>>", _on_list_select)

    def _apply_audio_source() -> None:
        if not audio_sources or audio_listbox is None:
            return
        spec = next(item for item in audio_sources if item["key"] == audio_source_var.get())
        _stop_play()
        audio_folder_box[0] = spec["folder"]
        audio_choices.clear()
        audio_choices.extend(spec.get("choices") or [])
        audio_listbox.delete(0, tk.END)
        for name in audio_choices:
            audio_listbox.insert(tk.END, name)
        audio_state["clip"] = None
        audio_state["fn"] = ""
        audio_state["armed"] = False
        _sync_mix_btn()
        if focus[0] == "audio":
            focus[0] = "video"
            if clip[0] is not None:
                _show_frame(clip[0].start)

    def _on_audio_select(_e=None) -> None:
        if audio_listbox is None:
            return
        sel = audio_listbox.curselection()
        if not sel:
            return
        fn = audio_choices[sel[0]]
        if fn != audio_state.get("fn") or focus[0] != "audio":
            _load_audio(fn)

    if audio_listbox is not None:
        audio_listbox.bind("<<ListboxSelect>>", _on_audio_select)
        if len([item for item in (audio_sources or []) if item.get("folder")]) > 1:
            audio_source_var.trace_add("write", lambda *_a: _apply_audio_source())

    def _on_confirm(action: str | None = None) -> None:
        if clip[0] is None:
            messagebox.showwarning("导入视频", "这里没有视频。", parent=dlg)
            return
        _save_trim()
        c = clip[0]
        if c.end <= c.start + (1.0 / c.fps):
            messagebox.showerror("区间无效", "结束时间必须大于开始时间。", parent=dlg)
            return
        vol = _snap_mp4_preview_volume(volume_var.get())
        try:
            mp4_adj, wav_adj = build_adjusted_pair(
                c.path, vol, start=c.start, end=c.end, speed=round(c.speed, 1),
            )
            if not mp4_adj:
                raise RuntimeError("生成本地临时音视频失败")
            picked = (sel_fn[0], mp4_adj, wav_adj)
        except TypeError:
            mp4_adj, wav_adj = build_adjusted_pair(c.path, vol)
            picked = (sel_fn[0], mp4_adj, wav_adj)
        except Exception as ex:
            messagebox.showerror("错误", str(ex), parent=dlg)
            return
        if action:
            picked = picked + (action,)
        if radio_holder[0]:
            picked = picked + (radio_var.get(),)
        if sources:
            picked = picked + (source_var.get(),)
        if audio_sources or dest_options:
            audio_payload = None
            if audio_state.get("armed") and audio_state.get("clip") is not None:
                ac = audio_state["clip"]
                audio_payload = {
                    "path": ac.path,
                    "start": ac.start,
                    "end": ac.end,
                    "speed": round(ac.speed, 1),
                }
            result[0] = {
                "filename": picked[0],
                "mp4": picked[1],
                "wav": picked[2],
                "action": action,
                "radio": radio_var.get() if radio_holder[0] else "",
                "source": source_var.get() if sources else "",
                "dest": dest_var.get() if dest_options else "",
                "audio": audio_payload,
            }
        else:
            result[0] = picked
        _close()

    def _save_recording(notify: bool) -> None:
        chunks = rec["chunks"]
        rec["chunks"] = []
        rec_dlg = rec.get("dialog")
        rec["dialog"] = None
        if rec_dlg is not None:
            try:
                if rec_dlg.winfo_exists():
                    rec_dlg.destroy()
            except tk.TclError:
                pass
        if not chunks or np is None or sf is None:
            if notify:
                messagebox.showwarning("录音", "没有录到声音。", parent=dlg)
            return
        folder = rec.get("folder") or ""
        if not folder:
            if notify:
                messagebox.showwarning("录音", "当前没有音频文件夹。", parent=dlg)
            return
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = f"rec_{stamp}.wav"
        path = os.path.join(folder, name)
        n = 2
        while os.path.exists(path):
            name = f"rec_{stamp}_{n}.wav"
            path = os.path.join(folder, name)
            n += 1
        try:
            audio_data = np.concatenate(chunks, axis=0)
            sf.write(path, audio_data, rec["rate"])
        except Exception as exc:
            if notify:
                messagebox.showerror("录音", f"保存失败: {exc}", parent=dlg)
            return
        norm_folder = os.path.normpath(folder)
        matched = None
        for item in audio_sources or []:
            if os.path.normpath(item.get("folder") or "") == norm_folder:
                names = item.setdefault("choices", [])
                if name not in names:
                    names.append(name)
                    names.sort()
                matched = item
        if (
            audio_listbox is not None
            and matched is not None
            and os.path.normpath(audio_folder_box[0] or "") == norm_folder
        ):
            audio_choices.clear()
            audio_choices.extend(matched.get("choices") or [])
            audio_listbox.delete(0, tk.END)
            for item_name in audio_choices:
                audio_listbox.insert(tk.END, item_name)
            if name in audio_choices:
                idx = audio_choices.index(name)
                audio_listbox.selection_clear(0, tk.END)
                audio_listbox.selection_set(idx)
                audio_listbox.see(idx)
                _load_audio(name)
        if notify:
            messagebox.showinfo("录音", f"已保存到当前文件夹:\n{name}", parent=dlg)

    def _recording_worker() -> None:
        def _on_audio(indata, _frames, _time_info, status):
            if status:
                print(f"录音状态: {status}")
            if rec["on"]:
                rec["chunks"].append(indata.copy())

        try:
            with sd.InputStream(
                samplerate=rec["rate"],
                channels=rec["channels"],
                callback=_on_audio,
                dtype="float32",
            ):
                while rec["on"]:
                    time.sleep(0.1)
        except Exception as exc:
            rec["on"] = False
            print(f"录音线程错误: {exc}")
            dlg.after(0, lambda: messagebox.showerror("录音", f"录音失败: {exc}", parent=dlg))

    def _tick_recording() -> None:
        rec_dlg = rec.get("dialog")
        label = rec.get("time_label")
        if not rec["on"] or rec_dlg is None or label is None:
            return
        try:
            if not rec_dlg.winfo_exists():
                return
        except tk.TclError:
            return
        elapsed = time.time() - rec["started"]
        label.config(text=f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}")
        rec_dlg.after(100, _tick_recording)

    def _stop_record(notify: bool = True) -> None:
        if not rec["on"]:
            return
        rec["on"] = False
        thread = rec.get("thread")
        if thread is not None:
            thread.join(timeout=1.5)
        rec["thread"] = None
        _save_recording(notify)

    def _start_record() -> None:
        if audio_listbox is None:
            return
        if not _RECORDING_OK:
            messagebox.showerror("录音", "录音不可用。请安装 sounddevice 和 soundfile。", parent=dlg)
            return
        folder = audio_folder_box[0] or ""
        if not folder:
            messagebox.showwarning("录音", "当前没有音频文件夹。", parent=dlg)
            return
        if rec["on"]:
            _stop_record(True)
            return
        _stop_play()
        rec["chunks"] = []
        rec["folder"] = folder
        rec["on"] = True
        rec["started"] = time.time()
        rec_dlg = tk.Toplevel(dlg)
        rec_dlg.title("录音中...")
        rec_dlg.geometry("360x180")
        rec_dlg.resizable(False, False)
        rec_dlg.transient(dlg)
        rec_dlg.grab_set()
        box = ttk.Frame(rec_dlg, padding=20)
        box.pack(fill=tk.BOTH, expand=True)
        ttk.Label(box, text="正在录音...", font=("Arial", 14), foreground="red").pack(pady=10)
        time_label = ttk.Label(box, text="00:00", font=("Arial", 12))
        time_label.pack(pady=5)
        rec["dialog"] = rec_dlg
        rec["time_label"] = time_label
        ttk.Button(box, text="停止录音", command=lambda: _stop_record(True)).pack(pady=16)
        rec_dlg.protocol("WM_DELETE_WINDOW", lambda: _stop_record(True))
        rec["thread"] = threading.Thread(target=_recording_worker, daemon=True)
        rec["thread"].start()
        _tick_recording()

    def _close() -> None:
        if rec["on"]:
            _stop_record(False)
        _stop_play()
        try:
            dlg.destroy()
        except tk.TclError:
            pass

    def _fill_actions() -> None:
        for widget in extra_host.winfo_children():
            widget.destroy()
        for widget in btn_host.winfo_children():
            widget.destroy()
        spec = radio_holder[0]
        if spec:
            radio_title, radio_options = spec
            radio_var.set(radio_options[0][0])
            ttk.Label(extra_host, text=radio_title, style="PickChoice.TLabel").pack(
                side=tk.LEFT, padx=(0, 8)
            )
            for value, label in radio_options:
                ttk.Radiobutton(
                    extra_host,
                    text=label,
                    value=value,
                    variable=radio_var,
                    style="PickChoice.TRadiobutton",
                ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(btn_host, text="取消", command=_close).pack(side=tk.RIGHT, padx=(6, 0))
        actions = confirm_holder[0]
        if actions:
            for value, label in reversed(actions):
                ttk.Button(
                    btn_host, text=label, command=lambda v=value: _on_confirm(v)
                ).pack(side=tk.RIGHT, padx=(0, 6))
        else:
            ttk.Button(btn_host, text="确定", command=lambda: _on_confirm()).pack(side=tk.RIGHT)

    def _apply_source() -> None:
        if not sources:
            return
        spec = next(item for item in sources if item["key"] == source_var.get())
        _stop_play()
        folder_box[0] = spec["folder"]
        choices.clear()
        choices.extend(spec["choices"])
        listbox.delete(0, tk.END)
        for name in choices:
            listbox.insert(tk.END, name)
        radio_holder[0] = spec.get("radios")
        confirm_holder[0] = spec.get("confirm_actions")
        _fill_actions()
        if choices:
            listbox.selection_set(0)
            _load_file(choices[0])
        else:
            clip[0] = None
            sel_fn[0] = ""
            preview_canvas.delete("all")

    dlg.protocol("WM_DELETE_WINDOW", _close)
    _fill_actions()
    if sources:
        source_var.trace_add("write", lambda *_args: _apply_source())
    listbox.selection_set(0)
    _load_file(choices[0])

    sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
    dlg.update_idletasks()
    _dw, _dh = (980, 760) if audio_sources else (980, 640)
    dlg.geometry(f"{_dw}x{_dh}+{(sw - _dw) // 2}+{(sh - _dh) // 2}")
    dlg.wait_window()
    return result[0]
