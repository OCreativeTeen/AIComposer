"""
本地 MP4/MP3：预览播放 → Whisper 转写，结果展示、剪贴板与同目录 TXT 保存。
"""
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pygame
except ImportError:
    pygame = None

from PIL import Image, ImageTk

from utility.audio_transcriber import AudioTranscriber, remove_transcribe_cache_for_audio_path
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor

_DEFAULT_SCENE_MIN = 9


def open_transcribe_media_dialog(parent, media_gui, media_path: str) -> None:
    TranscribeMediaDialog(parent, media_gui, media_path)


class TranscribeMediaDialog:
    def __init__(self, parent, media_gui, media_path: str):
        self.media_path = os.path.abspath(media_path)
        self.media_gui = media_gui
        self._is_mp3 = os.path.splitext(self.media_path)[1].lower() == ".mp3"

        self._transcriber = AudioTranscriber(media_gui.pid, "small", "cuda")

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("媒体转写 — 预览与文稿")
        self.dlg.transient(parent)
        self.dlg.geometry("900x720")
        self.dlg.minsize(640, 520)

        self.video_cap = None
        self.video_playing = False
        self.video_after_id = None
        self._temp_audio_path = None
        self.current_photo = None
        self._mp3_playing = False
        self._mp3_paused = False

        top = ttk.Frame(self.dlg, padding=8)
        top.pack(fill=tk.BOTH, expand=True)

        ttk.Label(top, text=self.media_path, wraplength=860, font=("Arial", 9)).pack(anchor="w", pady=(0, 6))

        self.preview_canvas = tk.Canvas(top, bg="black", height=320, highlightthickness=1, highlightbackground="#444")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=4)

        self.time_lbl = ttk.Label(top, text="")
        self.time_lbl.pack(anchor="w")

        ctrl = ttk.Frame(top)
        ctrl.pack(fill=tk.X, pady=4)
        self.play_btn = ttk.Button(ctrl, text="▶ 播放", command=self._toggle_play)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(ctrl, text="停止", command=self._stop_play).pack(side=tk.LEFT)

        ttk.Label(top, text="转写结果（可编辑）", font=("Arial", 9, "bold")).pack(anchor="w", pady=(8, 2))
        self.text_w = scrolledtext.ScrolledText(top, height=12, wrap=tk.WORD, font=("Arial", 10))
        self.text_w.pack(fill=tk.BOTH, expand=True, pady=4)

        btn_row = ttk.Frame(top)
        btn_row.pack(fill=tk.X, pady=8)

        ttk.Button(btn_row, text="转写", command=self._on_transcribe).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="复制到剪贴板", command=self._copy_clipboard).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="保存为 TXT", command=self._save_txt_manual).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="关闭", command=self._on_close).pack(side=tk.RIGHT)

        self.dlg.protocol("WM_DELETE_WINDOW", self._on_close)

        self.dlg.after(200, self._try_auto_preview)

    def _ffmpeg_audio(self):
        return FfmpegAudioProcessor(self.media_gui.pid)

    def _try_auto_preview(self):
        if not os.path.isfile(self.media_path):
            self.preview_canvas.create_text(
                320, 160, text="文件不存在", fill="white", font=("Arial", 14)
            )
            return
        if self._is_mp3:
            self._init_mp3_preview()
            return
        if cv2 is None:
            self.preview_canvas.create_text(
                320, 160, text="未安装 OpenCV，无法内嵌预览", fill="white", font=("Arial", 12)
            )
            return
        self._stop_play()
        self.video_cap = cv2.VideoCapture(self.media_path)
        if not self.video_cap.isOpened():
            self.preview_canvas.create_text(
                320, 160, text="无法打开视频", fill="white", font=("Arial", 12)
            )
            return
        self._fps = float(self.video_cap.get(cv2.CAP_PROP_FPS) or 30)
        if self._fps < 1 or self._fps > 120:
            self._fps = 30
        fa = self._ffmpeg_audio()
        self._temp_audio_path = fa.extract_audio_from_video(self.media_path, "wav")
        if pygame:
            try:
                pygame.mixer.init(frequency=44100)
            except pygame.error:
                pass
        self._start_play_video()

    def _init_mp3_preview(self):
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(
            320, 160, text="MP3 音频（点击下方播放试听）", fill="white", font=("Arial", 12)
        )
        self.time_lbl.config(text="")
        if pygame:
            try:
                pygame.mixer.init(frequency=44100)
            except pygame.error:
                pass
        else:
            self.preview_canvas.create_text(
                320, 200, text="未安装 pygame，无法播放", fill="#888", font=("Arial", 10)
            )

    def _toggle_play(self):
        if self._is_mp3:
            self._toggle_play_mp3()
            return
        if self.video_cap is None or not self.video_cap.isOpened():
            self._try_auto_preview()
            return
        if self.video_playing:
            self.video_playing = False
            self.play_btn.config(text="▶ 播放")
            if self.video_after_id and self.dlg.winfo_exists():
                try:
                    self.dlg.after_cancel(self.video_after_id)
                except tk.TclError:
                    pass
                self.video_after_id = None
            if pygame:
                try:
                    pygame.mixer.music.pause()
                except Exception:
                    pass
        else:
            if pygame and self._temp_audio_path and os.path.isfile(self._temp_audio_path):
                try:
                    pygame.mixer.music.unpause()
                except Exception:
                    try:
                        pygame.mixer.music.load(self._temp_audio_path)
                        pygame.mixer.music.play()
                    except Exception:
                        pass
            self.video_playing = True
            self.play_btn.config(text="⏸ 暂停")
            self._play_next_frame()

    def _toggle_play_mp3(self):
        if not pygame:
            messagebox.showwarning("提示", "未安装 pygame，无法播放 MP3。", parent=self.dlg)
            return
        if self._mp3_paused:
            try:
                pygame.mixer.music.unpause()
            except Exception:
                pass
            self._mp3_paused = False
            self._mp3_playing = True
            self.play_btn.config(text="⏸ 暂停")
            return
        if self._mp3_playing:
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass
            self._mp3_paused = True
            self._mp3_playing = False
            self.play_btn.config(text="▶ 播放")
            return
        try:
            pygame.mixer.music.load(self.media_path)
            pygame.mixer.music.play()
        except Exception as e:
            messagebox.showerror("播放失败", str(e), parent=self.dlg)
            return
        self._mp3_paused = False
        self._mp3_playing = True
        self.play_btn.config(text="⏸ 暂停")

    def _start_play_video(self):
        self.video_playing = True
        self.play_btn.config(text="⏸ 暂停")
        if self.video_cap:
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        if pygame and self._temp_audio_path and os.path.isfile(self._temp_audio_path):
            try:
                pygame.mixer.music.load(self._temp_audio_path)
                pygame.mixer.music.play()
            except Exception:
                pass
        self._play_next_frame()

    def _play_next_frame(self):
        if not self.video_playing or not self.dlg.winfo_exists():
            return
        if not self.video_cap or not self.video_cap.isOpened():
            return

        ret, frame = self.video_cap.read()
        if not ret:
            self._stop_play()
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        cw = max(self.preview_canvas.winfo_width(), 400)
        ch = max(self.preview_canvas.winfo_height(), 240)
        pil_image.thumbnail((cw - 8, ch - 8), Image.Resampling.LANCZOS)
        self.current_photo = ImageTk.PhotoImage(pil_image)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=self.current_photo)

        try:
            pos = self.video_cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            fc = self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_t = fc / self._fps if self._fps else 0
            self.time_lbl.config(text=f"{pos:.1f}s / {total_t:.1f}s")
        except Exception:
            pass

        delay = max(1, int(1000 / self._fps))
        self.video_after_id = self.dlg.after(delay, self._play_next_frame)

    def _stop_play(self):
        self.video_playing = False
        self._mp3_playing = False
        self._mp3_paused = False
        self.play_btn.config(text="▶ 播放")
        if self.video_after_id and self.dlg.winfo_exists():
            try:
                self.dlg.after_cancel(self.video_after_id)
            except tk.TclError:
                pass
            self.video_after_id = None
        if pygame:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        if self.video_cap:
            try:
                self.video_cap.release()
            except Exception:
                pass
            self.video_cap = None

    def _txt_path_default(self) -> str:
        d = os.path.dirname(self.media_path)
        stem = os.path.splitext(os.path.basename(self.media_path))[0]
        return os.path.join(d, f"{stem}.txt")

    def _copy_clipboard(self):
        text = self.text_w.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "文稿为空", parent=self.dlg)
            return
        self.dlg.clipboard_clear()
        self.dlg.clipboard_append(text)
        self.dlg.update()

    def _save_txt_manual(self):
        text = self.text_w.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "文稿为空", parent=self.dlg)
            return
        path = self._txt_path_default()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            messagebox.showerror("保存失败", str(e), parent=self.dlg)
            return
        messagebox.showinfo("已保存", path, parent=self.dlg)

    def _on_transcribe(self):
        root = self.media_gui.root
        dlg = self.dlg
        tw = self.text_w
        tr = self._transcriber
        fa = self._ffmpeg_audio()
        lang = self.media_gui.language or "zh"
        smin = _DEFAULT_SCENE_MIN
        smax = max(smin, int(smin * 1.5))
        src = self.media_path
        is_mp3 = self._is_mp3

        def work():
            if is_mp3:
                audio = src
            else:
                audio = fa.extract_audio_from_video(src)
                if not audio:
                    root.after(0, lambda: messagebox.showwarning("提示", "视频无音频或无法提取", parent=dlg))
                    return
            try:
                remove_transcribe_cache_for_audio_path(audio)
                segs = tr.transcribe_with_whisper(audio, lang, smin, smax)
                text = ". ".join(
                    (json_item.get("caption") or "").strip()
                    for json_item in segs
                    if (json_item.get("caption") or "").strip()
                ).strip()
                if not text:
                    root.after(0, lambda: messagebox.showwarning("提示", "转写无结果", parent=dlg))
                    return
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("转写失败", str(e), parent=dlg))
                return

            out_txt = os.path.join(
                os.path.dirname(src),
                f"{os.path.splitext(os.path.basename(src))[0]}.txt",
            )
            try:
                with open(out_txt, "w", encoding="utf-8") as f:
                    f.write(text)
            except OSError as save_err:
                root.after(
                    0,
                    lambda: messagebox.showerror("保存 TXT 失败", str(save_err), parent=dlg),
                )
                return

            def apply_text():
                tw.delete("1.0", tk.END)
                tw.insert("1.0", text)
                dlg.clipboard_clear()
                dlg.clipboard_append(text)
                dlg.update()

            root.after(0, apply_text)
            root.after(
                0,
                lambda: messagebox.showinfo(
                    "转写完成",
                    f"已写入剪贴板，并保存：\n{out_txt}",
                    parent=dlg,
                ),
            )

        threading.Thread(target=work, daemon=True).start()

    def _on_close(self):
        self._stop_play()
        if self._temp_audio_path and os.path.isfile(self._temp_audio_path):
            try:
                os.remove(self._temp_audio_path)
            except OSError:
                pass
            self._temp_audio_path = None
        try:
            self.dlg.destroy()
        except tk.TclError:
            pass
