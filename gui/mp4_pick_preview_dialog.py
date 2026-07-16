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
    __slots__ = ("path", "duration", "fps", "frame_count", "start", "end", "speed")

    def __init__(self, path: str):
        self.path = os.path.normpath(path)
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
) -> Union[Tuple[str, str, str], None]:
    """
  左侧文件列表 + 右侧裁剪/变速预览。
  ``build_adjusted_pair(full_path, volume, start=, end=, speed=) -> (tmp_mp4, tmp_wav)``
    """
    if parent is None:
        try:
            parent = tk._default_root
        except Exception:
            parent = None
    if not choices or build_adjusted_pair is None or cv2 is None:
        if cv2 is None and parent:
            messagebox.showwarning("预览", "需要安装 opencv-python 才能预览视频。", parent=parent)
        return None

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.geometry("980x640")
    dlg.minsize(900, 580)
    if parent:
        dlg.transient(parent)
    dlg.grab_set()

    result: list = [None]
    clip = [_ClipTrim(os.path.join(folder_path, choices[0]))]
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
    listbox = tk.Listbox(left, width=38, height=22, exportselection=False, font=("Consolas", 9))
    listbox.pack(fill=tk.BOTH, expand=True)
    for c in choices:
        listbox.insert(tk.END, c)

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

    foot = ttk.Frame(root)
    foot.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(foot, text="取消", command=lambda: _close()).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(foot, text="确定", command=lambda: _on_confirm()).pack(side=tk.RIGHT)

    def _c() -> _ClipTrim:
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
        if not _open_cap():
            return
        play_range_only[0] = range_only
        play_media_start[0] = start_t
        play_media_stop[0] = stop_t
        play_speed[0] = spd
        play_wall_start[0] = time.perf_counter()
        video_cap[0].set(cv2.CAP_PROP_POS_FRAMES, int(round(start_t * c.fps)))
        ret, frame = video_cap[0].read()
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

    def _load_file(fn: str) -> None:
        _stop_play()
        full = os.path.join(folder_path, fn)
        sel_fn[0] = fn
        clip[0] = _ClipTrim(full)
        c = clip[0]
        current_t[0] = c.start
        _apply_ui()
        _show_frame(c.start)

    def _on_list_select(_e=None) -> None:
        sel = listbox.curselection()
        if not sel:
            return
        fn = choices[sel[0]]
        if fn != sel_fn[0]:
            _load_file(fn)

    listbox.bind("<<ListboxSelect>>", _on_list_select)

    def _on_confirm() -> None:
        _save_trim()
        c = _c()
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
            result[0] = (sel_fn[0], mp4_adj, wav_adj)
        except TypeError:
            mp4_adj, wav_adj = build_adjusted_pair(c.path, vol)
            result[0] = (sel_fn[0], mp4_adj, wav_adj)
        except Exception as ex:
            messagebox.showerror("错误", str(ex), parent=dlg)
            return
        _close()

    def _close() -> None:
        _stop_play()
        try:
            dlg.destroy()
        except tk.TclError:
            pass

    dlg.protocol("WM_DELETE_WINDOW", _close)
    listbox.selection_set(0)
    _load_file(choices[0])

    sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
    dlg.update_idletasks()
    dlg.geometry(f"980x640+{(sw - 980) // 2}+{(sh - 640) // 2}")
    dlg.wait_window()
    return result[0]
