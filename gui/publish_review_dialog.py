"""
成品发布前审阅：预览 MP4、转写（AudioTranscriber.transcribe_with_whisper → WhisperX / API 回退）、
重合成（VoiceboxService.synthesize_speaker_text_to_wav + FfmpegProcessor）。

旁白音色：本对话框可重新选择「重合成」说话人；未改时顺序为
主界面「旁白」scene_narrator → 欢迎屏 LAST_NARRATOR → 项目 narrator → 默认人物。
"""
import os
import shutil
import threading
import time
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


def _dialog_parent(preferred, fallback=None):
    """messagebox 父窗口：preferred 已关闭时回退 fallback。"""
    for w in (preferred, fallback):
        if w is None:
            continue
        try:
            if w.winfo_exists():
                return w
        except tk.TclError:
            continue
    return fallback


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
        self._publishing = False

        self._transcriber = AudioTranscriber(media_gui.pid, "small", "cuda")
        self._voicebox = VoiceboxService(media_gui.pid)

        self.dlg = tk.Toplevel(parent)
        self.dlg._publish_review = self  # 供发布/归档前在主线程调用 _stop_play，释放 mp4 占用
        self.dlg.transient(parent)
        self.dlg.geometry("900x720")
        self.dlg.minsize(640, 520)

        self.video_cap = None
        self.video_playing = False
        self.video_after_id = None
        self._temp_audio_path = None
        self.current_photo = None
        self._current_t = 0.0
        self._duration = 0.0
        self._fps = 30.0
        self._frame_count = 0
        self._pygame_ok = False
        self._play_wall_start = 0.0
        self._has_audio = False

        top = ttk.Frame(self.dlg, padding=8)
        top.pack(fill=tk.BOTH, expand=True)

        self._publish_banner = ttk.Label(top, text="", wraplength=860, foreground="#0a6b0a")
        self._publish_banner.pack(anchor="w", pady=(0, 6))

        ttk.Label(top, text=self.mp4_path, wraplength=860, font=("Arial", 9)).pack(anchor="w", pady=(0, 6))

        self.preview_canvas = tk.Canvas(top, bg="black", height=320, highlightthickness=1, highlightbackground="#444")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=4)
        self.preview_canvas.bind("<Double-Button-1>", self._on_preview_double_click)

        self.time_lbl = ttk.Label(top, text="")
        self.time_lbl.pack(anchor=tk.W)
        ttk.Label(
            top,
            text="双击视频播放（音画同步）；再双击停止并回到开头。",
            font=("Arial", 9),
            foreground="#555",
        ).pack(anchor=tk.W, pady=(0, 4))

        toolbar = ttk.Frame(top)
        toolbar.pack(fill=tk.X, pady=(4, 6))
        self.btn_trans = ttk.Button(toolbar, text="Transcript（转写）", command=self._on_transcribe)
        self.btn_trans.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_regen = ttk.Button(toolbar, text="重合成音频", command=self._on_regenerate)
        self.btn_regen.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_pub = ttk.Button(toolbar, text="发布到 YouTube", command=self._on_publish)
        self.btn_pub.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="关闭", command=self._on_close).pack(side=tk.RIGHT)

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

        ttk.Label(
            top,
            text="文稿 / 转写结果（重合成时使用上方「说话人」）",
            font=("Arial", 9, "bold"),
        ).pack(anchor="w", pady=(8, 2))
        self.text_w = scrolledtext.ScrolledText(top, height=12, wrap=tk.WORD, font=("Arial", 10))
        self.text_w.pack(fill=tk.BOTH, expand=True, pady=4)

        story_raw = self.video_detail.get("story")
        summary = project_manager.publish_story_source_text(story_raw)
        if not summary:
            summary = project_manager.story_first_entry_text(story_raw) or ""
        if not summary:
            summary = (self.video_detail.get("analyzed_content") or "") or ""

        self.text_w.insert(tk.END, summary + "\n\n")

        self._sync_window_title()
        self._sync_publish_banner()
        self._sync_publish_button_state()

        self.dlg.protocol("WM_DELETE_WINDOW", self._on_close)

        self.dlg.after(200, self._init_video_preview)

    def _fmt_time(self, sec: float) -> str:
        sec = max(0.0, float(sec))
        m = int(sec // 60)
        s = sec - m * 60
        return f"{m:d}:{s:05.2f}"

    def _probe_video_meta(self) -> None:
        ff = FfmpegProcessor(self.media_gui.pid, self.media_gui.language or "zh")
        self._duration = float(ff.get_duration(self.mp4_path) or 0.0)
        self._fps = 30.0
        self._frame_count = 0
        if cv2 is not None:
            cap = cv2.VideoCapture(self.mp4_path)
            if cap.isOpened():
                self._fps = float(cap.get(cv2.CAP_PROP_FPS) or 30)
                if self._fps < 1 or self._fps > 240:
                    self._fps = 30.0
                self._frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                cap.release()
        if self._frame_count <= 0 and self._duration > 0:
            self._frame_count = max(1, int(round(self._duration * self._fps)))
        if self._duration <= 0 and self._frame_count > 0:
            self._duration = self._frame_count / self._fps
        self._duration = max(0.01, self._duration)
        self._has_audio = ff.has_audio_stream(self.mp4_path)

    def _init_pygame(self) -> None:
        if not pygame or self._pygame_ok:
            return
        try:
            pygame.mixer.init(frequency=44100, buffer=512)
            self._pygame_ok = True
        except Exception:
            self._pygame_ok = False

    def _load_audio_bg(self) -> None:
        if not self._has_audio:
            return
        try:
            ap = self._ffmpeg_audio().extract_audio_from_video(self.mp4_path, "wav") or ""
        except Exception:
            ap = ""
        self._temp_audio_path = ap

    def _paint_frame(self, frame) -> None:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        cw = max(self.preview_canvas.winfo_width(), 400)
        ch = max(self.preview_canvas.winfo_height(), 240)
        pil_image.thumbnail((cw - 8, ch - 8), Image.Resampling.LANCZOS)
        self.current_photo = ImageTk.PhotoImage(pil_image)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            cw // 2, ch // 2, anchor=tk.CENTER, image=self.current_photo
        )

    def _update_time_label(self) -> None:
        self.time_lbl.config(
            text=f"{self._fmt_time(self._current_t)} / {self._fmt_time(self._duration)}"
        )

    def _show_frame_at(self, t: float) -> None:
        if cv2 is None:
            return
        t = max(0.0, min(t, self._duration))
        self._current_t = t
        cap = cv2.VideoCapture(self.mp4_path)
        if not cap.isOpened():
            return
        frame_idx = int(round(t * self._fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        if ret:
            self._paint_frame(frame)
        self._update_time_label()

    def _open_cap(self) -> bool:
        if cv2 is None:
            return False
        if self.video_cap:
            try:
                self.video_cap.release()
            except Exception:
                pass
        self.video_cap = cv2.VideoCapture(self.mp4_path)
        return bool(self.video_cap and self.video_cap.isOpened())

    def _init_video_preview(self):
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
        self._stop_play(reset_to_start=False)
        self._probe_video_meta()
        self._init_pygame()
        threading.Thread(target=self._load_audio_bg, daemon=True).start()
        self._show_frame_at(0.0)

    def _on_preview_double_click(self, _event) -> None:
        if self.video_playing:
            self._stop_play(reset_to_start=True)
        else:
            self._start_play()

    def _start_play(self) -> None:
        if cv2 is None or not os.path.isfile(self.mp4_path):
            return
        self._stop_play(reset_to_start=False, release_cap=True)
        if not self._open_cap():
            return
        self._current_t = 0.0
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = self.video_cap.read()
        if ret:
            self._paint_frame(frame)
        self._update_time_label()

        if self._has_audio and self._temp_audio_path and os.path.isfile(self._temp_audio_path):
            self._init_pygame()
            if self._pygame_ok and pygame:
                try:
                    pygame.mixer.music.stop()
                    pygame.mixer.music.load(self._temp_audio_path)
                except Exception:
                    pass

        self._play_wall_start = time.perf_counter()
        if self._has_audio and self._pygame_ok and pygame and self._temp_audio_path:
            try:
                pygame.mixer.music.play()
            except Exception:
                pass

        self.video_playing = True
        self._play_tick()

    def _play_tick(self) -> None:
        if not self.video_playing or not self.dlg.winfo_exists():
            return
        elapsed = time.perf_counter() - self._play_wall_start
        target_t = elapsed
        if target_t >= self._duration - (0.5 / self._fps):
            self._current_t = self._duration
            self._update_time_label()
            self._stop_play(reset_to_start=True)
            return

        self._current_t = min(target_t, self._duration)
        self._update_time_label()

        if self._has_audio and self._pygame_ok and pygame and self._temp_audio_path:
            try:
                if not pygame.mixer.music.get_busy():
                    self._stop_play(reset_to_start=True)
                    return
            except Exception:
                pass

        if self.video_cap and self.video_cap.isOpened():
            cur_frame = int(self.video_cap.get(cv2.CAP_PROP_POS_FRAMES))
            target_frame = int(round(target_t * self._fps))
            if target_frame > cur_frame:
                if target_frame - cur_frame > 2:
                    self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = self.video_cap.read()
                if ret:
                    self._paint_frame(frame)

        self.video_after_id = self.dlg.after(15, self._play_tick)

    def _stop_play(self, *, reset_to_start: bool = False, release_cap: bool = True):
        self.video_playing = False
        if self.video_after_id and self.dlg.winfo_exists():
            try:
                self.dlg.after_cancel(self.video_after_id)
            except tk.TclError:
                pass
            self.video_after_id = None
        if self._pygame_ok and pygame:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        if release_cap and self.video_cap:
            try:
                self.video_cap.release()
            except Exception:
                pass
            self.video_cap = None
        if reset_to_start:
            self._show_frame_at(0.0)

    def _sync_window_title(self):
        if (self.video_detail.get("publish") or "").strip():
            self.dlg.title("审阅成品 — 本条已有发布记录（可再次上传）")
        else:
            self.dlg.title("审阅成品视频 — 发布前")

    def _sync_publish_banner(self):
        if not getattr(self, "_publish_banner", None):
            return
        pb = (self.video_detail.get("publish") or "").strip()
        u = (self.video_detail.get("url") or "").strip()
        ud = (self.video_detail.get("upload_date") or "").strip()
        if pb or u or ud:
            bits = []
            if pb:
                bits.append(f"发布/定时记录（publish）：{pb}")
            if u:
                bits.append(f"成片链接（url）：{u}")
            if ud:
                bits.append(f"upload_date：{ud}（本条最新一次成功上传写入）")
            bits.append("可按「发布到 YouTube」再次上传。")
            try:
                self._publish_banner.config(text="  ".join(bits))
            except tk.TclError:
                pass
        else:
            try:
                self._publish_banner.config(text="")
            except tk.TclError:
                pass

    def _sync_publish_button_state(self):
        """发布按钮始终可用（支持重投）；本条无成品时请从列表侧检查 gen_video/mp4。"""
        try:
            self.btn_pub.config(state=tk.NORMAL)
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
                        "错误",
                        f"无法复制视频到临时目录以提取音频：\n{err}",
                        parent=_dialog_parent(dlg, root),
                    ),
                )
                return
            audio = fa.extract_audio_from_video(work_mp4)
            safe_remove(work_mp4)
            if not audio:
                root.after(
                    0,
                    lambda: messagebox.showwarning(
                        "提示", "视频无音频或无法提取", parent=_dialog_parent(dlg, root)
                    ),
                )
                return
            try:
                remove_transcribe_cache_for_audio_path(audio)
                segs = tr.transcribe_with_whisper(
                    audio, lang, False, False, False, smin, smax
                )
                text = ". ".join(
                    (json_item.get("caption") or "").strip()
                    for json_item in segs
                    if (json_item.get("caption") or "").strip()
                ).strip()
                if not text:
                    root.after(
                        0,
                        lambda: messagebox.showwarning(
                            "提示", "转写无结果", parent=_dialog_parent(dlg, root)
                        ),
                    )
                    return
            except Exception as e:
                err = str(e)
                root.after(
                    0,
                    lambda: messagebox.showerror(
                        "转写失败", err, parent=_dialog_parent(dlg, root)
                    ),
                )
                return

            def apply_text():
                #insert at end of the text
                tw.insert(tk.END, "\n"+text)

            root.after(0, apply_text)
            root.after(
                0,
                lambda: messagebox.showinfo(
                    "转写", "已完成", parent=_dialog_parent(dlg, root)
                ),
            )

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
                root.after(
                    0,
                    lambda err=str(e): messagebox.showerror(
                        "错误",
                        f"无法复制视频到临时目录处理：\n{err}",
                        parent=_dialog_parent(dlg, root),
                    ),
                )
                return
            try:
                tts_wav = vb.synthesize_speaker_text_to_wav(speaker, txt, lk)
                if not tts_wav:
                    root.after(
                        0,
                        lambda: messagebox.showerror(
                            "错误", "TTS 生成失败", parent=_dialog_parent(dlg, root)
                        ),
                    )
                    return
                fp = FfmpegProcessor(pid, lk)
                newv = fp.add_audio_to_video(work_mp4, tts_wav)
                if not newv or not os.path.isfile(newv):
                    root.after(
                        0,
                        lambda: messagebox.showerror(
                            "错误", "合成视频失败", parent=_dialog_parent(dlg, root)
                        ),
                    )
                    return

                def _stop_and_copy_back():
                    self._stop_play()
                    return safe_copy_overwrite(newv, orig_mp4)

                try:
                    out = _run_on_tk_main_and_wait(root, _stop_and_copy_back, timeout=120)
                except Exception as e:
                    root.after(
                        0,
                        lambda err=str(e): messagebox.showerror(
                            "错误", f"写回失败：{err}", parent=_dialog_parent(dlg, root)
                        ),
                    )
                    return
                if not out:
                    root.after(
                        0,
                        lambda: messagebox.showerror(
                            "错误",
                            "无法写回原路径（可能被占用或权限不足），成品仍在临时目录：\n"
                            + newv,
                            parent=_dialog_parent(dlg, root),
                        ),
                    )
                    return
                safe_remove(tts_wav)
                if newv != work_mp4:
                    safe_remove(newv)
                safe_remove(work_mp4)
            except Exception as e:
                root.after(
                    0,
                    lambda err=str(e): messagebox.showerror(
                        "重合成失败", err, parent=_dialog_parent(dlg, root)
                    ),
                )
                return
            root.after(
                0,
                lambda: messagebox.showinfo(
                    "完成",
                    "已用新音频替换该视频音轨。",
                    parent=_dialog_parent(dlg, root),
                ),
            )

        threading.Thread(target=work, daemon=True).start()

    def _on_publish(self):
        def after():
            if self.on_refresh_after_publish:
                self.on_refresh_after_publish()
            self._sync_window_title()
            self._sync_publish_banner()
            self._sync_publish_button_state()

        review_script = (self.text_w.get("1.0", tk.END) or "").strip()
        self.media_gui._open_publish_video_dialog(
            self.dlg,
            "",
            self.mp4_path,
            self.video_detail,
            after,
            review_script_text=review_script,
        )

    def _on_close(self):
        if getattr(self, "_publishing", False):
            par = _dialog_parent(self.dlg, getattr(self.media_gui, "root", None))
            if not messagebox.askyesno(
                "上传进行中",
                "正在上传 YouTube，关闭本窗口后成功/失败提示将改在主窗口显示。\n\n确定关闭？",
                parent=par,
            ):
                return
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
