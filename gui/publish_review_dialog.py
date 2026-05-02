"""
成品发布前审阅：预览 MP4、转写（AudioTranscriber.transcribe_with_whisper）、
重合成（VoiceboxService.synthesize_speaker_text_to_wav + FfmpegProcessor）。

旁白音色：本对话框可重新选择「重合成」说话人；未改时顺序为
主界面「旁白」scene_narrator → 欢迎屏 LAST_NARRATOR → 项目 narrator → 默认人物。
"""
import json
import os
import shutil
import threading
from datetime import datetime
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

import config
import project_manager
from utility.audio_transcriber import AudioTranscriber, remove_transcribe_cache_for_audio_path
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.ffmpeg_processor import FfmpegProcessor
from utility.file_util import safe_copy_overwrite, safe_remove
from utility.voicebox_speech_service import VoiceboxService

_DEFAULT_SCENE_MIN = 9


def _run_on_tk_main_and_wait(root, fn, timeout=120):
    """在 Tk 主线程执行 fn()，worker 线程阻塞等待（用于释放预览后再写文件）。"""
    ev = threading.Event()
    boxed = [None]
    err = [None]

    def _run():
        try:
            boxed[0] = fn()
        except Exception as e:
            err[0] = e
        finally:
            ev.set()

    root.after(0, _run)
    if not ev.wait(timeout=timeout):
        raise TimeoutError("主线程操作超时")
    if err[0]:
        raise err[0]
    return boxed[0]


class PublishReviewDialog:
    def __init__(
        self,
        parent,
        mp4_path: str,
        video_detail: dict,
        media_gui,
        workflow_gui,
        on_refresh_after_publish,
    ):
        self.mp4_path = os.path.abspath(mp4_path)
        self.video_detail = video_detail
        self.media_gui = media_gui
        self.workflow_gui = workflow_gui
        self.on_refresh_after_publish = on_refresh_after_publish

        self._transcriber = AudioTranscriber(media_gui.pid, "small", "cuda")
        self._voicebox = VoiceboxService(media_gui.pid)

        self.dlg = tk.Toplevel(parent)
        self.dlg._publish_review = self  # 供发布/归档前在主线程调用 _stop_play，释放 mp4 占用
        self.dlg.title("审阅成品视频 — 发布前")
        self.dlg.transient(parent)
        self.dlg.geometry("900x720")
        self.dlg.minsize(640, 520)

        self.video_cap = None
        self.video_playing = False
        self.video_after_id = None
        self._temp_audio_path = None
        self.current_photo = None

        top = ttk.Frame(self.dlg, padding=8)
        top.pack(fill=tk.BOTH, expand=True)

        ttk.Label(top, text=self.mp4_path, wraplength=860, font=("Arial", 9)).pack(anchor="w", pady=(0, 6))

        self.preview_canvas = tk.Canvas(top, bg="black", height=320, highlightthickness=1, highlightbackground="#444")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=4)

        self.time_lbl = ttk.Label(top, text="")
        self.time_lbl.pack(anchor="w")

        ctrl = ttk.Frame(top)
        ctrl.pack(fill=tk.X, pady=4)
        self.play_btn = ttk.Button(ctrl, text="▶ 播放", command=self._toggle_play)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(ctrl, text="停止", command=self._stop_play).pack(side=tk.LEFT)

        ttk.Label(
            top,
            text="文稿 / 转写结果（重合成时使用下方「说话人」）",
            font=("Arial", 9, "bold"),
        ).pack(anchor="w", pady=(8, 2))
        self.text_w = scrolledtext.ScrolledText(top, height=12, wrap=tk.WORD, font=("Arial", 10))
        self.text_w.pack(fill=tk.BOTH, expand=True, pady=4)

        scene_content = self.video_detail.get('scene_content', {}).get(config.LANGUAGES[self.media_gui.language], [{}])[0]
        if scene_content:
            summary = scene_content.get("message", "")
            summary = summary + "\n" + scene_content.get("concise_speaking", "")
            summary = summary + "\n" + scene_content.get("story_analysis", "")
        else:
            summary = self.video_detail.get("analyzed_content", {}).get(config.LANGUAGES[self.media_gui.language],"")
            if not summary:
                summary = self.video_detail.get("content")

        self.text_w.insert(tk.END, summary + "\n\n")

        btn_row = ttk.Frame(top)
        btn_row.pack(fill=tk.X, pady=8)

        self.btn_trans = ttk.Button(btn_row, text="Transcript（转写）", command=self._on_transcribe)
        self.btn_trans.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_regen = ttk.Button(btn_row, text="重合成音频", command=self._on_regenerate)
        self.btn_regen.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_pub = ttk.Button(btn_row, text="发布到 YouTube", command=self._on_publish)
        self.btn_pub.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="关闭", command=self._on_close).pack(side=tk.RIGHT)

        self._sync_publish_button_state()

        narrator_row = ttk.Frame(top)
        narrator_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(narrator_row, text="重合成旁白（说话人）", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 8))
        self.narrator_pick = ttk.Combobox(
            narrator_row,
            width=34,
            values=config.CHARACTER_PERSON_OPTIONS,
            state="normal",
        )
        self.narrator_pick.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.narrator_pick.set(self._default_narrator())

        self.dlg.protocol("WM_DELETE_WINDOW", self._on_close)

        self.dlg.after(200, self._try_auto_play)

    def _sync_publish_button_state(self):
        """已有 publish 或上传成功后禁用「发布到 YouTube」。"""
        if (self.video_detail.get("publish") or "").strip():
            try:
                self.btn_pub.config(state="disabled")
            except tk.TclError:
                pass
        else:
            try:
                self.btn_pub.config(state="normal")
            except tk.TclError:
                pass

    def _ffmpeg_audio(self):
        return FfmpegAudioProcessor(self.media_gui.pid)

    def _default_narrator(self) -> str:
        """与摘要窗口「旁白」一致：主界面旁白 → 欢迎屏 LAST_NARRATOR → 项目 narrator → 列表首项。"""
        wg = self.workflow_gui
        if wg and getattr(wg, "scene_narrator", None) is not None:
            raw = (wg.scene_narrator.get() or "").strip()
            if raw:
                return raw
        ln = (getattr(project_manager, "LAST_NARRATOR", None) or "").strip()
        if ln:
            return ln
        pc = getattr(project_manager, "PROJECT_CONFIG", None)
        if isinstance(pc, dict):
            pn = (pc.get("narrator") or "").strip()
            if pn:
                return pn
        opts = [x for x in config.CHARACTER_PERSON_OPTIONS if (x or "").strip()]
        if opts:
            return opts[0]
        return "woman/mature/chinese"

    def _narrator_speaker(self) -> str:
        """重合成使用的说话人：优先本对话框下拉框，空则回退 _default_narrator。"""
        if getattr(self, "narrator_pick", None) is not None:
            raw = (self.narrator_pick.get() or "").strip()
            if raw:
                return raw
        return self._default_narrator()

    def _try_auto_play(self):
        if not os.path.isfile(self.mp4_path):
            self.preview_canvas.create_text(
                320, 160, text="文件不存在", fill="white", font=("Arial", 14)
            )
            return
        if cv2 is None:
            self.preview_canvas.create_text(
                320, 160, text="未安装 OpenCV，无法内嵌预览", fill="white", font=("Arial", 12)
            )
            return
        self._stop_play()
        self.video_cap = cv2.VideoCapture(self.mp4_path)
        if not self.video_cap.isOpened():
            self.preview_canvas.create_text(
                320, 160, text="无法打开视频", fill="white", font=("Arial", 12)
            )
            return
        self._fps = float(self.video_cap.get(cv2.CAP_PROP_FPS) or 30)
        if self._fps < 1 or self._fps > 120:
            self._fps = 30
        fa = self._ffmpeg_audio()
        self._temp_audio_path = fa.extract_audio_from_video(self.mp4_path, "wav")
        if pygame:
            try:
                pygame.mixer.init(frequency=44100)
            except pygame.error:
                pass
        self._start_play()

    def _toggle_play(self):
        if self.video_cap is None or not self.video_cap.isOpened():
            self._try_auto_play()
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

    def _start_play(self):
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

    def _on_transcribe(self):
        root = self.media_gui.root
        mp4 = self.mp4_path
        tw = self.text_w
        dlg = self.dlg
        tr = self._transcriber
        fa = self._ffmpeg_audio()
        lang = self.media_gui.language or "zh"
        smin = _DEFAULT_SCENE_MIN
        smax = max(smin, int(smin * 1.5))

        self._stop_play()

        def work():
            orig_mp4 = os.path.abspath(mp4)
            temp_dir = config.get_temp_path(self.media_gui.pid)
            ts = datetime.now().strftime("%Y%m%d%H%M")
            stem = os.path.splitext(os.path.basename(orig_mp4))[0]
            work_mp4 = os.path.join(temp_dir, f"{stem}_{ts}_src.mp4")
            try:
                _run_on_tk_main_and_wait(root, lambda: self._stop_play(), timeout=30)
            except Exception:
                pass
            try:
                shutil.copy2(orig_mp4, work_mp4)
            except OSError as e:
                root.after(
                    0,
                    lambda err=str(e): messagebox.showerror(
                        "错误", f"无法复制视频到临时目录以提取音频：\n{err}", parent=dlg
                    ),
                )
                return
            audio = fa.extract_audio_from_video(work_mp4)
            safe_remove(work_mp4)
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

            def apply_text():
                #insert at end of the text
                tw.insert(tk.END, "\n"+text)

            root.after(0, apply_text)
            root.after(0, lambda: messagebox.showinfo("转写", "已完成", parent=dlg))

        threading.Thread(target=work, daemon=True).start()

    def _on_regenerate(self):
        content = self.text_w.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "文稿为空", parent=self.dlg)
            return
        speaker = self._narrator_speaker()
        if not (speaker or "").strip():
            messagebox.showwarning("提示", "无法解析旁白人物。", parent=self.dlg)
            return

        root = self.media_gui.root
        dlg = self.dlg
        mp4 = self.mp4_path
        vb = self._voicebox
        lk = self.media_gui.language or "zh"
        txt = content.replace("——", ", ").replace("—", ",")

        self._stop_play()

        def work():
            orig_mp4 = os.path.abspath(mp4)
            pid = self.media_gui.pid
            temp_dir = config.get_temp_path(pid)
            ts = datetime.now().strftime("%Y%m%d%H%M")
            stem = os.path.splitext(os.path.basename(orig_mp4))[0]
            work_mp4 = os.path.join(temp_dir, f"{stem}_{ts}.mp4")
            try:
                _run_on_tk_main_and_wait(root, lambda: self._stop_play(), timeout=30)
            except Exception:
                pass
            try:
                shutil.copy2(orig_mp4, work_mp4)
            except OSError as e:
                root.after(0, lambda: messagebox.showerror("错误", f"无法复制视频到临时目录处理：\n{e}", parent=dlg))
                return
            try:
                tts_wav = vb.synthesize_speaker_text_to_wav(speaker, txt, lk)
                if not tts_wav:
                    root.after(0, lambda: messagebox.showerror("错误", "TTS 生成失败", parent=dlg))
                    return
                fp = FfmpegProcessor(pid, lk)
                newv = fp.add_audio_to_video(work_mp4, tts_wav)
                if not newv or not os.path.isfile(newv):
                    root.after(0, lambda: messagebox.showerror("错误", "合成视频失败", parent=dlg))
                    return

                def _stop_and_copy_back():
                    self._stop_play()
                    return safe_copy_overwrite(newv, orig_mp4)

                try:
                    out = _run_on_tk_main_and_wait(root, _stop_and_copy_back, timeout=120)
                except Exception as e:
                    root.after(0, lambda err=str(e): messagebox.showerror("错误", f"写回失败：{err}", parent=dlg))
                    return
                if not out:
                    root.after(
                        0,
                        lambda: messagebox.showerror(
                            "错误",
                            "无法写回原路径（可能被占用或权限不足），成品仍在临时目录：\n"
                            + newv,
                            parent=dlg,
                        ),
                    )
                    return
                safe_remove(tts_wav)
                if newv != work_mp4:
                    safe_remove(newv)
                safe_remove(work_mp4)
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("重合成失败", str(e), parent=dlg))
                return
            root.after(0, lambda: messagebox.showinfo("完成", "已用新音频替换该视频音轨。", parent=dlg))

        threading.Thread(target=work, daemon=True).start()

    def _on_publish(self):
        def after():
            if self.on_refresh_after_publish:
                self.on_refresh_after_publish()
            self._sync_publish_button_state()

        self.media_gui._open_publish_video_dialog(self.dlg, "", self.mp4_path, self.video_detail, after)

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
