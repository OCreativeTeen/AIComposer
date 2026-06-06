"""
选择对话框模块

提供通用的选择对话框功能
"""

import os
import subprocess
import tempfile
import threading
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.scrolledtext as scrolledtext
import tkinter.messagebox as messagebox
from typing import Callable, Optional, Tuple, Union

try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    pygame = None
    PYGAME_AVAILABLE = False

from utility.ffmpeg_audio_processor import ffmpeg_path, ffprobe_path


def _askchoice_normalize_pairs(choices):
    """将 choices 规范为 [(return_value, button_label), ...]。
    支持 str（返回值与按钮文案相同）或 (value, label) 二元组。
    """
    pairs = []
    for c in choices:
        if isinstance(c, (tuple, list)) and len(c) >= 2:
            pairs.append((c[0], str(c[1])))
        else:
            s = str(c)
            pairs.append((s, s))
    return pairs


def askchoice(title, choices, parent=None):
    """每个选项一个按钮，点击即选并关闭；点「取消」返回 None。

    choices:
      - list[str]：按钮文案与返回值均为该字符串
      - list[tuple]：每项 (return_value, button_label)，按钮显示 label，返回时 value 为 return_value

    返回:
      - None：用户取消
      - (label, value)：label 为按钮上显示的文案；value 为对应返回值（纯 str 选项时二者相同）
    """
    if not choices:
        return None

    if parent is None:
        try:
            parent = tk._default_root
        except Exception:
            parent = None

    pairs = _askchoice_normalize_pairs(choices)
    num_choices = len(pairs)
    max_label_len = max(len(lbl) for _, lbl in pairs)

    dialog = tk.Toplevel(parent)
    dialog.title(title[:80] + ("…" if len(title) > 80 else ""))

    button_height = 36
    title_height = 72
    cancel_height = 52
    padding = 24
    calculated_height = title_height + (num_choices * button_height) + cancel_height + padding
    min_height = 220

    dialog.update_idletasks()
    if parent:
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()
    else:
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()

    max_height = int(screen_height * 0.85)
    dialog_height = max(min_height, min(calculated_height, max_height))
    # 长英文标签时加宽窗口；按钮 width 为字符数
    dialog_width = min(920, max(360, 48 + int(min(max_label_len, 100) * 7.0)))

    dialog.resizable(False, False)

    if parent:
        dialog.transient(parent)
    dialog.grab_set()

    x = (screen_width // 2) - (dialog_width // 2)
    y = (screen_height // 2) - (dialog_height // 2)
    dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

    result = None

    def on_choice(val, lbl: str):
        nonlocal result
        result = (lbl, val)
        dialog.destroy()

    main = ttk.Frame(dialog, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    label = ttk.Label(
        main,
        text=title,
        font=("Arial", 12, "bold"),
        wraplength=dialog_width - 40,
        justify=tk.CENTER,
    )
    label.pack(pady=(8, 12))

    btn_char_w = min(100, max(25, min(max_label_len + 2, 95)))

    for val, lbl in pairs:
        ttk.Button(
            main,
            text=lbl,
            width=btn_char_w,
            command=lambda v=val, lb=lbl: on_choice(v, lb),
        ).pack(pady=4, fill=tk.X)

    ttk.Button(main, text="取消", width=min(btn_char_w, 28), command=dialog.destroy).pack(pady=(14, 6))

    dialog.wait_window()
    return result


def pack_text_buttons(parent, rows, cancel=None, width=48):
    """自上而下排列 ttk 按钮；用于「一点即执行」的自定义对话框（如讲话拷贝）。

    rows: [(label, command), ...]
    cancel: None 或 (label, command)，置于最下方并加大上边距。
    返回所有按钮控件列表（含取消），便于统一 disable 等。
    """
    buttons = []
    for label, cmd in rows:
        b = ttk.Button(parent, text=label, width=width, command=cmd)
        b.pack(fill=tk.X, pady=2)
        buttons.append(b)
    if cancel is not None:
        cl, cc = cancel
        b = ttk.Button(parent, text=cl, width=width, command=cc)
        b.pack(fill=tk.X, pady=(8, 0))
        buttons.append(b)
    return buttons


def ask_speaking_concise_review_dialog(
    parent,
    original_content: str,
    remix_fn: Callable[[str], str],
    *,
    title: str = "审阅文案",
    initial_edit: Optional[str] = None,
) -> Optional[str]:
    """弹窗：只读「原文」+ 可编辑定稿区；「Remix」对原文调用 ``remix_fn``；「确定」返回定稿。

    ``initial_edit`` 非空时定稿区初始值与之相同（原文仍为 ``original_content``，如字幕审阅用 speaking 作原文）。
    """
    result: list[Optional[str]] = [None]

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(True, True)

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    ttk.Label(
        main,
        text="原文（只读参考）",
        font=("Arial", 10, "bold"),
    ).pack(anchor=tk.W)
    orig_w = scrolledtext.ScrolledText(
        main,
        wrap=tk.WORD,
        height=7,
        width=72,
        font=("Arial", 10),
        state=tk.DISABLED,
        background="#f5f5f5",
    )
    orig_w.pack(fill=tk.BOTH, expand=False, pady=(2, 8))
    orig_w.config(state=tk.NORMAL)
    orig_w.insert("1.0", original_content or "")
    orig_w.config(state=tk.DISABLED)

    ttk.Label(
        main,
        text="定稿（可手工修改；Remix 基于当前编辑区全文重新摘要）",
        font=("Arial", 10, "bold"),
    ).pack(anchor=tk.W)
    edit_w = scrolledtext.ScrolledText(
        main,
        wrap=tk.WORD,
        height=10,
        width=72,
        font=("Arial", 10),
    )
    edit_w.pack(fill=tk.BOTH, expand=True, pady=(2, 8))
    edit_seed = initial_edit if initial_edit is not None else (original_content or "")
    edit_w.insert("1.0", edit_seed)

    btn_bar = ttk.Frame(main)
    btn_bar.pack(fill=tk.X, pady=(4, 0))

    def reset_from_original() -> None:
        edit_w.delete("1.0", tk.END)
        edit_w.insert("1.0", edit_seed)

    def do_remix() -> None:
        raw = original_content #edit_w.get("1.0", tk.END)
        try:
            out = remix_fn(raw)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Remix 失败", str(e), parent=dlg)
            return
        edit_w.delete("1.0", tk.END)
        edit_w.insert("1.0", (out or "").strip())

    def on_ok() -> None:
        text = edit_w.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("审阅", "定稿正文不能为空。", parent=dlg)
            return
        result[0] = text
        dlg.destroy()

    def on_cancel() -> None:
        dlg.destroy()

    ttk.Button(btn_bar, text="还原原文", command=reset_from_original).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_bar, text="Remix(LLM)", command=do_remix).pack(side=tk.LEFT, padx=(0, 6))

    btn_row2 = ttk.Frame(main)
    btn_row2.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(btn_row2, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(btn_row2, text="确定", command=on_ok).pack(side=tk.RIGHT)

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.update_idletasks()
    w_m, h_m = 720, min(640, dlg.winfo_reqheight() + 20)
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"{w_m}x{h_m}+{(sw - w_m) // 2}+{(sh - h_m) // 2}")
    dlg.wait_window()
    return result[0]


def post_nested_clipboard_menu(
    root,
    choices_dict,
    speaker,
    content,
    event,
    max_label_len=72,
    *,
    menu_x=None,
    menu_y=None,
):
    if not choices_dict:
        return "break"

    def _menu_label(s: str) -> str:
        t = (s or "").strip()
        if len(t) <= max_label_len:
            return t
        return t[: max_label_len - 1] + "…"

    def _copy(text: str) -> None:
        try:
            root.clipboard_clear()
            if content:
                if "$$$" in text:
                    text = text.replace("$$$", content)

                if speaker:
                    text = text.replace("###", speaker)
                else:
                    text = text.replace("###", "")
            root.clipboard_append(text)
            root.update_idletasks()
        except tk.TclError:
            pass

    m = tk.Menu(root, tearoff=0)
    for cn_key, items in choices_dict.items():
        sub = tk.Menu(m, tearoff=0)
        for text in items:
            sub.add_command(
                label=_menu_label(text),
                command=lambda t=text: _copy(t),
            )
        m.add_cascade(label=cn_key, menu=sub)

    if menu_x is None or menu_y is None:
        if event is not None:
            try:
                menu_x = int(event.x_root)
                menu_y = int(event.y_root)
            except (AttributeError, tk.TclError, TypeError, ValueError):
                menu_x = menu_y = None
    if menu_x is None or menu_y is None:
        root.update_idletasks()
        menu_x = root.winfo_rootx() + 40
        menu_y = root.winfo_rooty() + 40

    def _show_menu() -> None:
        try:
            root.update_idletasks()
            m.tk_popup(menu_x, menu_y)
        except tk.TclError:
            try:
                m.post(menu_x, menu_y)
            except tk.TclError:
                pass
        finally:
            try:
                m.grab_release()
            except tk.TclError:
                pass

    # 审阅对话框关闭后 grab 可能尚未完全释放；延后到 idle 再弹出菜单
    root.after_idle(_show_menu)
    return "break"


def _get_media_duration_sec(file_path):
    """返回视频时长（秒），无法读取或非视频则返回 None。"""
    try:
        import cv2
        lower = file_path.lower()
        if not lower.endswith((".mp4", ".avi", ".mov", ".webm", ".mkv")):
            return None
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        cap.release()
        if fps and fps > 0 and n and n > 0:
            return float(n / fps)
    except Exception:
        pass
    return None


def _format_duration(sec):
    if sec is None:
        return "—"
    if sec < 0:
        return "—"
    if sec < 60:
        return f"{sec:.1f}s"
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m}:{s:04.1f}"


def _load_preview_image(file_path, max_w=320, max_h=240):
    """从视频或图片文件加载预览图，返回可显示的 PhotoImage 或 None"""
    try:
        import cv2
        from PIL import Image, ImageTk
        lower = file_path.lower()
        frame = None
        if lower.endswith(('.mp4', '.avi', '.mov', '.webm', '.mkv')):
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
            if frame is None:
                return None
        elif lower.endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
            frame = cv2.imread(file_path)
            if frame is None:
                return None
        else:
            return None
        h, w = frame.shape[:2]
        if w > max_w or h > max_h:
            scale = min(max_w / w, max_h / h)
            nw, nh = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        return ImageTk.PhotoImage(pil_img)
    except Exception:
        return None


def _snap_mp4_preview_volume(raw: float) -> float:
    v = round(float(raw) * 2.0) / 2.0
    return max(0.5, min(2.0, v))


def _ffprobe_video_has_audio(file_path: str) -> bool:
    try:
        r = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                file_path,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        return bool(r.stdout.strip())
    except Exception:
        return False


def _ffmpeg_extract_volume_wav_to(video_path: str, volume: float, out_wav: str) -> bool:
    try:
        r = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                video_path,
                "-vn",
                "-af",
                f"volume={volume}",
                "-ac",
                "2",
                "-ar",
                "44100",
                "-c:a",
                "pcm_s16le",
                out_wav,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        return r.returncode == 0 and os.path.isfile(out_wav)
    except Exception:
        try:
            if os.path.isfile(out_wav):
                os.remove(out_wav)
        except Exception:
            pass
        return False


def _askchoice_media_preview_mp4_video(
    title: str,
    choices: list,
    folder_path: str,
    parent=None,
    build_volume_adjusted_pair: Optional[Callable[[str, float], Tuple[str, str]]] = None,
) -> Union[Tuple[str, str, str], None]:
    """MP4 专用：左侧列表右侧视频自动播放预览 + 音量滑块（0.5～2，步进 0.5）；确定时调用 build_volume_adjusted_pair(full_path, volume) 产出 (tmp_mp4, tmp_wav)。"""
    if parent is None:
        try:
            parent = tk._default_root
        except Exception:
            parent = None

    if not choices or build_volume_adjusted_pair is None:
        return None

    try:
        import cv2

        CV2_AVAILABLE = True
    except ImportError:
        CV2_AVAILABLE = False

    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dw, dh = 720, 520
    dialog.geometry(f"{dw}x{dh}")
    dialog.resizable(True, True)

    if parent:
        dialog.transient(parent)
    dialog.grab_set()

    dialog.update_idletasks()
    if parent:
        x = (parent.winfo_screenwidth() - dw) // 2
        y = (parent.winfo_screenheight() - dh) // 2
    else:
        x = (dialog.winfo_screenwidth() - dw) // 2
        y = (dialog.winfo_screenheight() - dh) // 2
    dialog.geometry(f"+{x}+{y}")

    result: list = [None]
    preview_wav_path = [None]
    # 试听 wav 在后台线程用 ffmpeg 生成；递增以丢弃过期的 after 回调，避免叠音与泄漏临时文件
    preview_audio_job_gen = [0]

    if PYGAME_AVAILABLE:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        except Exception:
            pass

    main = ttk.Frame(dialog, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    ttk.Label(main, text=title, font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 8))

    content = ttk.Frame(main)
    content.pack(fill=tk.BOTH, expand=True)

    left = ttk.Frame(content)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    list_frame = ttk.LabelFrame(left, text="文件列表", padding=5)
    list_frame.pack(fill=tk.BOTH, expand=True)
    scroll = ttk.Scrollbar(list_frame)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    listbox = tk.Listbox(list_frame, height=12, yscrollcommand=scroll.set, font=("Consolas", 9))
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.config(command=listbox.yview)
    for c in choices:
        listbox.insert(tk.END, c)

    right = ttk.Frame(content)
    right.pack(side=tk.RIGHT, padx=(10, 0), fill=tk.BOTH)

    preview_frame = ttk.LabelFrame(right, text="视频预览（自动循环播放）", padding=5)
    preview_frame.pack(fill=tk.BOTH, expand=True)

    canvas_w, canvas_h = 360, 240
    preview_canvas = tk.Canvas(preview_frame, width=canvas_w, height=canvas_h, bg="black", highlightthickness=0)
    preview_canvas.pack(pady=(0, 8))

    volume_var = tk.DoubleVar(value=_snap_mp4_preview_volume(1.0))
    vol_row = ttk.Frame(preview_frame)
    vol_row.pack(fill=tk.X, pady=4)

    ttk.Label(vol_row, text="试听音量增益:").pack(side=tk.LEFT)
    vol_value_lbl = ttk.Label(vol_row, text=f"{volume_var.get():.1f}x", foreground="blue", width=8)
    vol_value_lbl.pack(side=tk.RIGHT)

    slider = tk.Scale(
        preview_frame,
        from_=0.5,
        to=2.0,
        resolution=0.5,
        orient=tk.HORIZONTAL,
        variable=volume_var,
        command=lambda _: _debounced_volume_reload(),
        showvalue=0,
    )
    slider.pack(fill=tk.X)

    hint = (
        "0.5x～2.0x，步进 0.5。确定后生成本地临时：已增益的 mp4 + wav。\n"
        + ("（当前环境未检测到 pygame，仅视频预览无声音）" if not PYGAME_AVAILABLE else "")
        + ("\n（未检测到 opencv-python，视频预览不可用）" if not CV2_AVAILABLE else "")
    )
    ttk.Label(preview_frame, text=hint, foreground="gray25", wraplength=360, justify=tk.LEFT).pack(
        anchor="w", pady=(6, 0)
    )

    duration_label = ttk.Label(
        preview_frame,
        text="时长 —",
        font=("Consolas", 9),
        foreground="gray25",
    )
    duration_label.pack(pady=(4, 0))

    video_cap = [None]
    video_after_id = [None]
    video_playing = [False]
    current_full_path = [None]

    preview_photo_img = [None]

    debounce_audio_id = [None]

    def cleanup_resources():
        if video_after_id[0] is not None:
            try:
                dialog.after_cancel(video_after_id[0])
            except tk.TclError:
                pass
            video_after_id[0] = None
        if debounce_audio_id[0] is not None:
            try:
                dialog.after_cancel(debounce_audio_id[0])
            except tk.TclError:
                pass
            debounce_audio_id[0] = None
        if video_cap[0] is not None:
            try:
                video_cap[0].release()
            except Exception:
                pass
            video_cap[0] = None
        if PYGAME_AVAILABLE:
            try:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
            except Exception:
                pass
        wav = preview_wav_path[0]
        if wav and os.path.isfile(wav):
            try:
                os.remove(wav)
            except Exception:
                pass
            preview_wav_path[0] = None
        preview_audio_job_gen[0] += 1

    def _restart_preview_audio(vol: float, full_video: str):
        if not PYGAME_AVAILABLE:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        preview_audio_job_gen[0] += 1
        job = preview_audio_job_gen[0]

        def worker():
            if not _ffprobe_video_has_audio(full_video):
                return
            fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                ok = _ffmpeg_extract_volume_wav_to(full_video, vol, tmp_wav)
            except Exception:
                ok = False
            if not ok:
                try:
                    if os.path.isfile(tmp_wav):
                        os.remove(tmp_wav)
                except OSError:
                    pass
                return

            def apply():
                try:
                    if job != preview_audio_job_gen[0]:
                        try:
                            if os.path.isfile(tmp_wav):
                                os.remove(tmp_wav)
                        except OSError:
                            pass
                        return
                    try:
                        if not dialog.winfo_exists():
                            raise tk.TclError("destroyed")
                    except tk.TclError:
                        try:
                            if os.path.isfile(tmp_wav):
                                os.remove(tmp_wav)
                        except OSError:
                            pass
                        return
                    old = preview_wav_path[0]
                    if old and os.path.isfile(old):
                        try:
                            os.remove(old)
                        except OSError:
                            pass
                    preview_wav_path[0] = tmp_wav
                    try:
                        pygame.mixer.music.load(tmp_wav)
                        pygame.mixer.music.play()
                    except Exception:
                        pass
                except tk.TclError:
                    try:
                        if os.path.isfile(tmp_wav):
                            os.remove(tmp_wav)
                    except OSError:
                        pass

            try:
                dialog.after(0, apply)
            except tk.TclError:
                try:
                    if os.path.isfile(tmp_wav):
                        os.remove(tmp_wav)
                except OSError:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _debounced_volume_reload():
        sn = _snap_mp4_preview_volume(volume_var.get())
        if abs(sn - volume_var.get()) > 1e-6:
            volume_var.set(sn)
        vol_value_lbl.config(text=f"{sn:.1f}x")

        if debounce_audio_id[0] is not None:
            try:
                dialog.after_cancel(debounce_audio_id[0])
            except tk.TclError:
                pass

        def _reload():
            full = current_full_path[0]
            if full and CV2_AVAILABLE and video_playing[0]:
                restart_playback_keep_file(full)

        debounce_audio_id[0] = dialog.after(120, _reload)

    def restart_playback_keep_file(full: str):
        """同一文件音量变更：从头回放。"""
        if not CV2_AVAILABLE:
            return
        cleanup_resources()
        current_full_path[0] = full
        if PYGAME_AVAILABLE and pygame.mixer.music.get_busy():
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        vol = float(volume_var.get())
        cap = cv2.VideoCapture(full)
        video_cap[0] = cap
        video_playing[0] = True
        _restart_preview_audio(vol, full)
        update_video_frame()

    def stop_video_tick():
        if video_after_id[0] is not None:
            try:
                dialog.after_cancel(video_after_id[0])
            except tk.TclError:
                pass
            video_after_id[0] = None

    def load_selection(fn: str):
        full = os.path.join(folder_path, fn)
        current_full_path[0] = full
        sec = _get_media_duration_sec(full)
        if sec is not None:
            duration_label.config(text=f"时长 {_format_duration(sec)}")
        else:
            duration_label.config(text="时长 —")
        cleanup_resources()

        vol = float(volume_var.get())

        if not CV2_AVAILABLE:
            preview_canvas.delete("all")
            preview_canvas.create_text(
                canvas_w // 2,
                canvas_h // 2,
                text="需要 opencv-python",
                fill="white",
                font=("Arial", 11),
            )
            _restart_preview_audio(vol, full)
            return

        cap = cv2.VideoCapture(full)
        video_cap[0] = cap
        video_playing[0] = True

        preview_canvas.delete("all")
        preview_canvas.update_idletasks()

        vol = float(volume_var.get())
        _restart_preview_audio(vol, full)
        update_video_frame()

    def update_video_frame():
        if not video_playing[0] or video_cap[0] is None:
            return
        cap = video_cap[0]
        ok, frame = cap.read()

        interval_ms = 33
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        try:
            if fps > 0:
                interval_ms = max(16, int(1000.0 / fps))
        except Exception:
            pass

        try:
            if ok and frame is not None:
                h, w = frame.shape[:2]
                sx = canvas_w / w
                sy = canvas_h / h
                scale = min(sx, sy)
                nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
                from PIL import Image, ImageTk
                import cv2 as cv2_resize

                small = cv2_resize.resize(frame, (nw, nh), interpolation=cv2_resize.INTER_AREA)
                rgb = cv2_resize.cvtColor(small, cv2_resize.COLOR_BGR2RGB)
                pi = Image.fromarray(rgb)
                photo = ImageTk.PhotoImage(pi)
                preview_photo_img[0] = photo
                preview_canvas.delete("all")
                preview_canvas.create_image(canvas_w // 2, canvas_h // 2, image=photo)
            else:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                if PYGAME_AVAILABLE and _ffprobe_video_has_audio(current_full_path[0] or ""):
                    try:
                        if preview_wav_path[0]:
                            pygame.mixer.music.stop()
                            pygame.mixer.music.load(preview_wav_path[0])
                            pygame.mixer.music.play()
                    except Exception:
                        pass
        except Exception:
            pass

        video_after_id[0] = dialog.after(interval_ms, update_video_frame)

    def on_list_select(ev=None):
        sel = listbox.curselection()
        if not sel:
            return
        fn = choices[sel[0]]
        load_selection(fn)

    def on_confirm():
        sel = listbox.curselection()
        if not sel:
            dialog.destroy()
            return
        fn = choices[sel[0]]
        full = os.path.join(folder_path, fn)
        vol = _snap_mp4_preview_volume(volume_var.get())
        try:
            mp4_adj, wav_adj = build_volume_adjusted_pair(full, vol)
            if not mp4_adj:
                raise RuntimeError("生成本地临时音视频失败（请查看控制台）")
            result[0] = (fn, mp4_adj, wav_adj)
        except Exception as e:
            messagebox.showerror("错误", f"{e}", parent=dialog)
            return
        stop_video_tick()
        cleanup_resources()
        dialog.destroy()

    listbox.bind("<<ListboxSelect>>", on_list_select)
    listbox.bind("<Double-1>", lambda e: on_confirm())

    def on_dialog_close():
        stop_video_tick()
        cleanup_resources()
        try:
            dialog.destroy()
        except tk.TclError:
            pass

    btn_frame = ttk.Frame(main)
    btn_frame.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(btn_frame, text="确定", command=on_confirm).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="取消", command=on_dialog_close).pack(side=tk.LEFT)

    if choices:
        listbox.selection_set(0)
        listbox.see(0)
        load_selection(choices[0])

    dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

    dialog.wait_window()

    if PYGAME_AVAILABLE:
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

    return result[0]


def askchoice_media_preview(
    title,
    choices,
    folder_path,
    parent=None,
    *,
    use_mp4_video_preview=False,
    build_volume_adjusted_pair=None,
) -> Union[str, Tuple[str, str, str], None]:
    """
    带预览的媒体选择对话框（支持 mp4 与图片）。
    左侧为文件列表，右侧为选中文件的预览图；若 use_mp4_video_preview=True 则右侧改为视频播放 + 音量 + 产出临时 mp4/wav。

    choices: 文件名列表；folder_path: 文件所在目录。
    use_mp4_video_preview: 必须为 True 时提供 build_volume_adjusted_pair(src_full_path, volume) -> (tmp_mp4, tmp_wav)。

    返回:
      - 普通模式：选中的文件名字符串，取消为 None。
      - MP4 视频模式：(文件名, tmp_mp4, tmp_wav)，取消为 None。
    """
    if use_mp4_video_preview:
        return _askchoice_media_preview_mp4_video(
            title,
            choices,
            folder_path,
            parent,
            build_volume_adjusted_pair=build_volume_adjusted_pair,
        )

    if parent is None:
        try:
            parent = tk._default_root
        except Exception:
            parent = None

    if not choices:
        return None

    dialog = tk.Toplevel(parent)
    dialog.title(title)

    # 窗口尺寸：左侧列表 + 右侧预览
    dialog_width = 560
    dialog_height = 450
    dialog.geometry(f"{dialog_width}x{dialog_height}")
    dialog.resizable(True, True)

    if parent:
        dialog.transient(parent)
    dialog.grab_set()

    # 居中
    dialog.update_idletasks()
    if parent:
        x = (parent.winfo_screenwidth() - dialog_width) // 2
        y = (parent.winfo_screenheight() - dialog_height) // 2
    else:
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
    dialog.geometry(f"+{x}+{y}")

    result = [None]  # 用 list 以便在闭包中修改

    main = ttk.Frame(dialog, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    ttk.Label(main, text=title, font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 8))

    content = ttk.Frame(main)
    content.pack(fill=tk.BOTH, expand=True)

    # 左侧：文件列表
    left = ttk.Frame(content)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    list_frame = ttk.LabelFrame(left, text="文件列表", padding=5)
    list_frame.pack(fill=tk.BOTH, expand=True)
    scroll = ttk.Scrollbar(list_frame)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    listbox = tk.Listbox(list_frame, height=12, yscrollcommand=scroll.set, font=("Consolas", 9))
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.config(command=listbox.yview)
    for c in choices:
        listbox.insert(tk.END, c)

    # 右侧：预览
    right = ttk.Frame(content)
    right.pack(side=tk.RIGHT, padx=(10, 0), fill=tk.Y)
    preview_frame = ttk.LabelFrame(right, text="预览", padding=5)
    preview_frame.pack()
    preview_label = tk.Label(preview_frame, text="选择文件以查看预览", bg="gray90")
    preview_label.pack()
    duration_label = ttk.Label(
        preview_frame,
        text="时长 —",
        font=("Consolas", 9),
        foreground="gray25",
    )
    duration_label.pack(pady=(4, 0))
    preview_photo = [None]  # 保持引用避免被 GC

    def _update_duration_for_path(full):
        sec = _get_media_duration_sec(full)
        if sec is not None:
            duration_label.config(text=f"时长 {_format_duration(sec)}")
        else:
            lower = full.lower()
            if lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")):
                duration_label.config(text="时长 —（图片）")
            else:
                duration_label.config(text="时长 —")

    def on_select(e):
        sel = listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        fn = choices[idx]
        full = os.path.join(folder_path, fn)
        img = _load_preview_image(full)
        if img:
            preview_photo[0] = img
            preview_label.config(image=img, text="")
        else:
            preview_photo[0] = None
            preview_label.config(image="", text="(无预览)")
        _update_duration_for_path(full)

    def on_confirm():
        sel = listbox.curselection()
        if sel:
            result[0] = choices[sel[0]]
        dialog.destroy()

    listbox.bind("<<ListboxSelect>>", on_select)
    listbox.bind("<Double-1>", lambda e: on_confirm())

    # 默认选中第一项并显示预览
    if choices:
        listbox.selection_set(0)
        listbox.see(0)
        full = os.path.join(folder_path, choices[0])
        img = _load_preview_image(full)
        if img:
            preview_photo[0] = img
            preview_label.config(image=img, text="")
        else:
            preview_label.config(image="", text="(无预览)")
        _update_duration_for_path(full)

    btn_frame = ttk.Frame(main)
    btn_frame.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(btn_frame, text="确定", command=on_confirm).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT)

    dialog.wait_window()
    return result[0]
