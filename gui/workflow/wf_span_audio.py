"""SpanAudioMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
from utility import audio_transcriber
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import subprocess
import json
import threading
import config
import config_prompt
from project_manager import refresh_scene_media
import project_manager
from utility.file_util import get_file_path, show_auto_close_popup
from utility.voicebox_speech_service import VoiceboxService
from gui.choice_dialog import askchoice


class SpanAudioMixin:
    def _span_voice_names(self) -> list[str]:
        try:
            config.reload_character_person_options()
        except Exception:
            pass
        names = []
        for name in config.narrator_person_options():
            name = (name or "").strip()
            if name and name not in names:
                names.append(name)
        return names or ["woman/mature/chinese"]

    def _ask_span_action(self, title: str, who: str, voice: str, start: float, end: float, has_text: bool, span_index: int | None = None) -> dict | None:
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.withdraw()
        holder = {"choice": None}
        voices = self._span_voice_names()
        if voice not in voices:
            voices.insert(0, voice)
        voice_var = tk.StringVar(value=voice)
        speed_var = tk.DoubleVar(value=1.0)
        speed_text = tk.StringVar(value="1.00 倍")

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text=f"{title}  {start:.2f}–{end:.2f} 秒\n这一段现在对的是 {who}",
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))
        ttk.Label(frame, text="声音").grid(row=1, column=0, sticky=tk.W, padx=(0, 6))
        combo = ttk.Combobox(frame, textvariable=voice_var, values=voices, state="readonly", width=28)
        combo.grid(row=1, column=1, columnspan=2, sticky=tk.EW)
        ttk.Button(
            frame,
            text="按这个声音重做",
            command=lambda: self._close_span_action(dlg, holder, "regen", voice_var, speed_var, has_text, title),
        ).grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(8, 10))
        ttk.Label(frame, text="速度").grid(row=3, column=0, sticky=tk.W)
        tk.Scale(
            frame,
            from_=0.7,
            to=1.5,
            resolution=0.01,
            orient=tk.HORIZONTAL,
            length=260,
            variable=speed_var,
            showvalue=False,
            command=lambda val: speed_text.set(f"{float(val):.2f} 倍"),
        ).grid(row=3, column=1, sticky=tk.EW)
        ttk.Label(frame, textvariable=speed_text, width=8).grid(row=3, column=2, sticky=tk.W, padx=(6, 0))
        ttk.Label(frame, text="0.7 倍更慢更长，1.5 倍更快更短。画面跟着这段声音对齐。").grid(
            row=4, column=0, columnspan=3, sticky=tk.W, pady=(2, 4)
        )
        ttk.Button(
            frame,
            text="套用这个速度",
            command=lambda: self._close_span_action(dlg, holder, "speed", voice_var, speed_var, True, title),
        ).grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(0, 10))
        ttk.Button(
            frame,
            text="拷贝这一段声音",
            command=lambda: self._close_span_action(dlg, holder, "copy", voice_var, speed_var, True, title),
        ).grid(row=6, column=0, columnspan=3, sticky=tk.EW)
        ttk.Button(
            frame,
            text="把这一段转成文字",
            command=lambda: self._close_span_action(dlg, holder, "transcribe", voice_var, speed_var, True, title),
        ).grid(row=7, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        ttk.Button(
            frame,
            text="把这一段静音",
            command=lambda: self._close_span_action(dlg, holder, "mute", voice_var, speed_var, True, title),
        ).grid(row=8, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        prev_btn = ttk.Button(
            frame,
            text="和前一段合成一段",
            command=lambda: self._close_span_action(dlg, holder, "merge_prev", voice_var, speed_var, True, title),
        )
        prev_btn.grid(row=9, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        next_btn = ttk.Button(
            frame,
            text="和后一段合成一段",
            command=lambda: self._close_span_action(dlg, holder, "merge_next", voice_var, speed_var, True, title),
        )
        next_btn.grid(row=10, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        sections = getattr(self, "_speech_sections", None) or []
        if span_index is None or span_index <= 0:
            prev_btn.state(["disabled"])
        if span_index is None or span_index >= len(sections) - 1:
            next_btn.state(["disabled"])
        ttk.Button(frame, text="关闭", command=dlg.destroy).grid(row=11, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        self._place_popup_near(dlg, self.speech_span_canvas, below=False)
        dlg.grab_set()
        dlg.wait_window()
        return holder["choice"]

    def _close_span_action(self, dlg, holder, action: str, voice_var, speed_var, has_text: bool, title: str) -> None:
        speed = float(speed_var.get() or 1.0)
        if action == "regen" and not has_text:
            messagebox.showinfo(title, f"这一场的{title}是空的，不能重做。", parent=dlg)
            return
        if action == "speed" and abs(speed - 1.0) < 0.005:
            messagebox.showinfo(title, "速度还是 1 倍，这一段不用变。", parent=dlg)
            return
        holder["choice"] = {"action": action, "voice": (voice_var.get() or "").strip(), "speed": speed}
        dlg.destroy()

    def _merge_speaking_section(self, index: int, with_prev: bool) -> None:
        """把这一段和前一段或后一段合成一段。记号用双击的这一段是谁。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        sections = [dict(section) for section in (getattr(self, "_speech_sections", None) or [])]
        other = index - 1 if with_prev else index + 1
        if not scene or index < 0 or index >= len(sections) or other < 0 or other >= len(sections):
            return
        current = sections[index]
        neighbor = sections[other]
        try:
            speaker = min(3, max(1, int(current.get("speaker") or 1)))
            start = min(float(current.get("start")), float(neighbor.get("start")))
            end = max(float(current.get("end")), float(neighbor.get("end")))
        except (TypeError, ValueError):
            return
        first, second = (neighbor, current) if with_prev else (current, neighbor)
        text = ((first.get("text") or "").strip() + (second.get("text") or "").strip()).strip()
        merged = {"speaker": speaker, "start": round(start, 2), "end": round(end, 2), "text": text}
        lo, hi = sorted((index, other))
        sections[lo:hi + 1] = [merged]
        sections = self._collapse_same_speaker_sections(sections)
        self._speech_sections = sections
        self._write_speaking_sections(scene, sections)
        self._put_speaking_text(project_manager.speaking_box_text(scene))
        self.workflow.save_scenes_to_json()
        self._draw_speech_span_bar()
        show_auto_close_popup(self.root, "合成", f"已合成第 {speaker} 个人的一段。")

    def _ask_regenerate_span(self, index: int) -> None:
        scene = None
        if getattr(self, "workflow", None):
            try:
                scene = self.update_current_scene()
            except Exception:
                scene = None
            if not scene:
                scene = self.workflow.get_scene_by_index(self.current_scene_index)
        sections = getattr(self, "_speech_sections", None) or []
        if not scene or index < 0 or index >= len(sections):
            return
        section = sections[index]
        try:
            start = float(section.get("start"))
            end = float(section.get("end"))
            speaker = int(section.get("speaker") or 1)
        except (TypeError, ValueError):
            return
        title = f"第{speaker}人"
        if end <= start:
            messagebox.showinfo(title, "先标出这一段的开始和结束。", parent=self.root)
            return
        actor_text = (getattr(self, "_actor_text", "") or "").strip() or (scene.get("actor") or "")
        active = project_manager.active_actor_entries(actor_text)
        voice = "woman/mature/chinese"
        who = "这一段"
        if 1 <= speaker <= len(active):
            row = active[speaker - 1]
            body = (row.get("body") or "").strip()
            voice = project_manager.resolve_actor_voice(body) or voice
            who = "讲员" if row.get("role") == "host" else (row.get("label") or "人物")
        text = (section.get("text") or "").strip()
        key = f"sec{index}"
        choice = self._ask_span_action(title, who, voice, float(start), float(end), bool(text), index)
        if not choice:
            return
        if choice["action"] in ("merge_prev", "merge_next"):
            self._merge_speaking_section(index, choice["action"] == "merge_prev")
            return
        if choice["action"] == "copy":
            self._copy_span_audio(key, float(start), float(end))
            return
        if choice["action"] == "transcribe":
            engine = self._transcribe_engine()
            if engine is None:
                return
            if getattr(self, "_span_regen_busy", False):
                messagebox.showinfo(title, "上一段还在处理。", parent=self.root)
                return
            self._span_regen_busy = True
            try:
                self.root.config(cursor="watch")
            except tk.TclError:
                pass
            threading.Thread(
                target=self._transcribe_span_audio,
                args=(key, float(start), float(end), engine),
                daemon=True,
            ).start()
            return
        if choice["action"] == "mute":
            if getattr(self, "_span_regen_busy", False):
                messagebox.showinfo(title, "上一段还在处理。", parent=self.root)
                return
            self._span_regen_busy = True
            try:
                self.root.config(cursor="watch")
            except tk.TclError:
                pass
            threading.Thread(
                target=self._mute_span_audio,
                args=(key, float(start), float(end)),
                daemon=True,
            ).start()
            return
        if getattr(self, "_span_regen_busy", False):
            messagebox.showinfo(title, "上一段还在处理。", parent=self.root)
            return
        self._span_regen_busy = True
        try:
            self.root.config(cursor="watch")
        except tk.TclError:
            pass
        if choice["action"] == "speed":
            threading.Thread(
                target=self._speed_span_audio,
                args=(key, float(choice["speed"]), float(start), float(end)),
                daemon=True,
            ).start()
            return
        threading.Thread(
            target=self._regenerate_span_audio,
            args=(key, choice["voice"], text, float(start), float(end)),
            daemon=True,
        ).start()

    def _span_source_audio(self, scene: dict) -> str:
        audio = get_file_path(scene, "clip_audio")
        if audio and os.path.isfile(audio):
            return audio
        video = get_file_path(scene, "clip")
        if video and os.path.isfile(video):
            return video
        return ""

    def _cut_span_wav(self, source: str, start: float, end: float, dest: str) -> bool:
        from utility.ffmpeg_processor import ffmpeg_path

        try:
            subprocess.run(
                [
                    ffmpeg_path, "-y",
                    "-ss", f"{start:.3f}",
                    "-to", f"{end:.3f}",
                    "-i", source,
                    "-vn",
                    "-c:a", "pcm_s16le",
                    "-ar", "44100",
                    "-ac", "2",
                    dest,
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return False
        return os.path.isfile(dest) and os.path.getsize(dest) > 100

    def _atempo_wav(self, source: str, speed: float, dest: str) -> bool:
        from utility.ffmpeg_processor import ffmpeg_path

        speed = max(0.7, min(1.5, float(speed)))
        try:
            subprocess.run(
                [
                    ffmpeg_path, "-y",
                    "-i", source,
                    "-filter:a", f"atempo={speed:.4f}",
                    "-c:a", "pcm_s16le",
                    "-ar", "44100",
                    "-ac", "2",
                    dest,
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return False
        return os.path.isfile(dest) and os.path.getsize(dest) > 100

    def _copy_span_audio(self, key: str, start: float, end: float) -> None:
        title = "这一段"
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        source = self._span_source_audio(scene) if scene else ""
        if not source:
            messagebox.showinfo(title, "这一场没有声音。", parent=self.root)
            return
        pid = getattr(self.workflow, "pid", None) or "span"
        folder = os.path.join(config.get_project_path(str(pid)), "temp")
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, f"{key}_{start:.2f}_{end:.2f}.wav")
        if not self._cut_span_wav(source, start, end, dest):
            messagebox.showerror(title, "这一段声音没有切出来。", parent=self.root)
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(dest)
            self.root.update()
        except tk.TclError:
            messagebox.showwarning(title, f"文件已经写好，但没能放进剪贴板：\n{dest}", parent=self.root)
            return
        show_auto_close_popup(self.root, title, "这一段 wav 的路径已经拷贝")

    def _mute_span_audio(self, key: str, start: float, end: float) -> None:
        """把主轨上这一段换成等长静音，画面长短不动。"""
        root = self.root
        title = "这一段"

        def finish(ok: bool, message: str) -> None:
            self._span_regen_busy = False
            try:
                root.config(cursor="")
            except tk.TclError:
                pass
            if ok:
                self.refresh_gui_scenes()
                show_auto_close_popup(root, title, message)
            else:
                messagebox.showerror(title, message, parent=root)

        try:
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            audio = get_file_path(scene, "clip_audio") if scene else ""
            if not audio or not os.path.isfile(audio):
                root.after(0, lambda: finish(False, "这一场没有主轨声音。"))
                return
            ap = self.workflow.ffmpeg_audio_processor
            duration = float(ap.get_duration(audio) or 0.0)
            if duration <= 0.2:
                root.after(0, lambda: finish(False, "读不出这段声音有多长。"))
                return
            cut_start = max(0.0, min(duration, float(start)))
            cut_end = max(0.0, min(duration, float(end)))
            if cut_end - cut_start < 0.15:
                root.after(0, lambda: finish(False, "这一段太短。"))
                return
            parts = []
            if cut_start > 0.08:
                head = ap.audio_cut_fade(audio, 0.0, cut_start, 0, 0)
                if not head or not os.path.isfile(head):
                    root.after(0, lambda: finish(False, "前面一段没有切开。"))
                    return
                parts.append(head)
            silence = ap.make_silence(cut_end - cut_start)
            if not silence or not os.path.isfile(silence):
                root.after(0, lambda: finish(False, "静音没有做好。"))
                return
            parts.append(silence)
            if duration - cut_end > 0.08:
                tail = ap.audio_cut_fade(audio, cut_end, duration - cut_end, 0, 0)
                if not tail or not os.path.isfile(tail):
                    root.after(0, lambda: finish(False, "后面一段没有切开。"))
                    return
                parts.append(tail)
            merged = ap.concat_audios(parts) if len(parts) > 1 else parts[0]
            if not merged or not os.path.isfile(merged):
                root.after(0, lambda: finish(False, "静音没有接回去。"))
                return
            self._backup_clip_to_scene_back(scene)
            refresh_scene_media(scene, "clip_audio", ".wav", merged, True)
            new_audio = get_file_path(scene, "clip_audio")
            clip_video = get_file_path(scene, "clip")
            if clip_video and os.path.isfile(clip_video) and new_audio:
                output_video = self.workflow.ffmpeg_processor.add_audio_to_video(clip_video, new_audio)
                if output_video and os.path.isfile(output_video):
                    refresh_scene_media(scene, "clip", ".mp4", output_video, True)
            self.workflow.save_scenes_to_json()
            root.after(0, lambda: finish(True, "这一段已经静音。"))
        except Exception as exc:
            err = str(exc)
            root.after(0, lambda msg=err: finish(False, msg))

    def _ask_near_choices(self, anchor, title: str, choices: list[tuple[str, str]], hint: str = "") -> str | None:
        """在按钮上方弹出几个选项。点一项就返回，取消返回空。"""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.withdraw()
        holder = {"value": None}
        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=title).pack(anchor=tk.W, pady=(0, 6))
        if hint:
            ttk.Label(frame, text=hint, wraplength=360, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

        def pick(value: str) -> None:
            holder["value"] = value
            dlg.destroy()

        def text_width(text: str) -> int:
            return sum(2 if ord(ch) > 127 else 1 for ch in text) + 2

        width = max(text_width(label) for _value, label in choices)
        width = max(width, text_width("取消"), 12)
        for value, label in choices:
            ttk.Button(frame, text=label, width=width, command=lambda v=value: pick(v)).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="取消", width=width, command=dlg.destroy).pack(fill=tk.X, pady=(8, 0))
        self._place_popup_near(dlg, anchor, below=False)
        dlg.grab_set()
        dlg.wait_window()
        return holder["value"]

    def _ask_video_treatment(self) -> None:
        picked = self._ask_near_choices(
            self.btn_video_treat,
            "视频效果",
            [("reverse", "反转"), ("mirror", "镜像")],
        )
        if picked == "reverse":
            self.reverse_video()
        elif picked == "mirror":
            self.mirror_video()

    def _ask_clip_overlay(self) -> None:
        picked = self._ask_near_choices(
            self.btn_overlay,
            "图文叠加",
            [
                ("logo", "右下角 Logo"),
                ("head", "顶部角标"),
                ("title", "烧上标题"),
            ],
        )
        if picked == "logo":
            self.add_watermark()
        elif picked == "head":
            self.add_headmark()
        elif picked == "title":
            self.print_title()

    def _span_transcriber(self):
        transcriber = getattr(self.workflow, "transcriber", None)
        if transcriber is None:
            transcriber = audio_transcriber.AudioTranscriber(self.workflow.pid, model_size="small", device="cuda")
            self.workflow.transcriber = transcriber
        return transcriber

    def _punctuate_span_text(self, text: str) -> str:
        """Whisper 原文没有标点。用原来的提示词交给 Gemini，补上逗号句号。"""
        text = (text or "").strip()
        if not text:
            return ""
        lang = getattr(self.workflow, "language", None) or "zh"
        if lang in ("zh-CN", "tw", "zh-TW", "zh-tw"):
            lang = "zh"
        lang_label = config.LANGUAGES.get(lang, lang)
        system = config_prompt.SRT_REORGANIZATION_SYSTEM_PROMPT.format(language=lang_label)
        try:
            from utility import llm_api
            raw = llm_api.LLMApi(llm_api.TEXT_MODEL).generate_text(system, text)
        except Exception as exc:
            print(f"span punctuate failed: {type(exc).__name__}: {exc}")
            return text
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        return cleaned or text

    def _transcribe_wav_to_text(self, wav: str, engine: str, span: float) -> tuple[str, str]:
        """把一段 wav 转成带标点的文字。返回 (文字, 错误说明)。"""
        if engine == "voicebox":
            service = getattr(self, "speech_service", None)
            if service is None:
                service = VoiceboxService(self.workflow.pid)
                self.speech_service = service
            raw = service.transcribe(wav)
            text = ""
            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
                if isinstance(data, dict):
                    text = str(data.get("text") or "").strip()
                else:
                    text = str(raw).strip()
            if text:
                text = self._punctuate_span_text(text)
            if text:
                return text, ""
            detail = str(getattr(service, "_last_transcribe_error", "") or "").strip()
            message = "Voicebox 没有转出文字。"
            if detail:
                message = message + " " + detail[:240]
            return "", message
        segments = self._span_transcriber().transcribe_with_whisper(
            wav,
            getattr(self.workflow, "language", None) or "zh",
            False,
            False,
            False,
            0.2,
            max(1.0, float(span)),
        )
        pieces = []
        for seg in segments or []:
            if isinstance(seg, dict):
                piece = str(seg.get("caption") or seg.get("text") or "").strip()
            else:
                piece = str(seg or "").strip()
            if piece:
                pieces.append(piece)
        text = self._punctuate_span_text("".join(pieces))
        if text:
            return text, ""
        return "", "这一段没有转出文字。"

    def _merged_timing_rows(self, scene: dict) -> list[tuple]:
        """按已有时间记录取出每一段。连着的同一人先合成一段，起点取更早的，终点取更晚的。"""
        speaking = (scene.get("speaking") or "").strip()
        stored = self._timing_sections(scene)
        rows = []
        if stored:
            for item in stored:
                if not isinstance(item, dict):
                    continue
                try:
                    start = float(item.get("start"))
                    end = float(item.get("end"))
                    speaker = min(3, max(1, int(item.get("speaker") or 1)))
                except (TypeError, ValueError):
                    continue
                if end <= start:
                    continue
                rows.append((start, end, speaker, (item.get("text") or "").strip()))
        if not rows and speaking:
            self._apply_collapsed_speaking(scene, speaking)
            fresh = self._retimed_speaking_sections(scene) or []
            for item in fresh:
                if not isinstance(item, dict):
                    continue
                try:
                    start = float(item.get("start"))
                    end = float(item.get("end"))
                    speaker = min(3, max(1, int(item.get("speaker") or 1)))
                except (TypeError, ValueError):
                    continue
                if end <= start:
                    continue
                rows.append((start, end, speaker, (item.get("text") or "").strip()))
        merged = []
        for start, end, speaker, body in rows:
            if merged and merged[-1][2] == speaker:
                prev = merged[-1]
                merged[-1] = (
                    min(prev[0], start),
                    max(prev[1], end),
                    speaker,
                    ((prev[3] or "") + (body or "")).strip(),
                )
            else:
                merged.append((start, end, speaker, body))
        return merged

    def _fit_timing_rows(self, rows, audio_start: float, audio_end: float):
        """把每段收进真实声音的起止里。后面的段不能早于前面的段。对不上就返回空。"""
        if audio_end - audio_start < 0.2:
            return None
        fitted = []
        prev_end = audio_start
        for start, end, speaker, body in rows:
            start = max(float(start), audio_start)
            end = min(float(end), audio_end)
            if end - start < 0.05 or start + 0.01 < prev_end:
                return None
            fitted.append((round(start, 2), round(end, 2), speaker, body))
            prev_end = end
        return fitted or None

    def _ask_bad_timing_choice(self, scene) -> str:
        """时间记录对不上时，请用户选整段归第一个人，或跳过这一场。"""
        holder = {"choice": "skip"}
        done = threading.Event()

        def ask():
            sid = scene.get("id", "?")
            picked = askchoice(
                f"场景 {sid} 的时间记录对不上。\n"
                "后面的段跑到了前面，或起止超出了真实声音。\n"
                "这些分段不再当作参考。",
                [
                    ("whole", "整段归第一个人"),
                    ("skip", "跳过这一场"),
                ],
                parent=self.root,
            )
            holder["choice"] = "skip" if not picked else picked[1]
            done.set()

        self.root.after(0, ask)
        done.wait()
        return holder["choice"]

    def _transcribe_whole_as_first(self, scene, source: str, duration: float, engine: str) -> str:
        self._ensure_default_actor(scene)
        wav = config.get_temp_file(self.workflow.pid, "wav")
        if not self._cut_span_wav(source, 0, duration, wav):
            return "fail"
        spoken, _err = self._transcribe_wav_to_text(wav, engine, duration)
        if not spoken:
            return "no_text"
        scene["speaking"] = f"<1> {spoken}"
        self._store_timing(scene, [{
            "speaker": 1,
            "start": 0.0,
            "end": round(duration, 2),
            "text": spoken,
        }])
        return "ok"

    def _transcribe_scene_clip(self, scene: dict, engine: str) -> str:
        """按每一段的时间转录，文字写回这个人。讲稿是空的，或人物没定，整段归第一个人。"""
        source = self._span_source_audio(scene)
        if not source:
            return "no_audio"
        duration = float(self._clip_duration(scene) or 0.0)
        if duration <= 0.2:
            duration = float(self.workflow.ffmpeg_audio_processor.get_duration(source) or 0.0)
        if duration <= 0.2:
            return "no_audio"
        speaking = (scene.get("speaking") or "").strip()
        if not speaking:
            return self._transcribe_whole_as_first(scene, source, duration, engine)
        if not self._scene_actor_defined(scene):
            self._ensure_default_actor(scene)
        rows = self._merged_timing_rows(scene)
        if not rows:
            return "no_text"
        path = self._speech_media_path(scene) or source
        bounds = self._audio_activity_bounds(path, duration)
        if not bounds or bounds[1] - bounds[0] < 0.2:
            audio_start, audio_end = 0.0, duration
        else:
            audio_start, audio_end = bounds
        fitted = self._fit_timing_rows(rows, audio_start, audio_end)
        if not fitted:
            if self._ask_bad_timing_choice(scene) != "whole":
                return "skip"
            return self._transcribe_whole_as_first(scene, source, duration, engine)
        parts_out = []
        for start, end, speaker, body in fitted:
            cut_end = min(end, duration)
            if cut_end - start < 0.2:
                if body:
                    parts_out.append((start, cut_end, speaker, body))
                continue
            wav = config.get_temp_file(self.workflow.pid, "wav")
            if not self._cut_span_wav(source, start, cut_end, wav):
                return "fail"
            spoken, _err = self._transcribe_wav_to_text(wav, engine, cut_end - start)
            parts_out.append((start, cut_end, speaker, spoken or body))
        parts_out = [row for row in parts_out if row[3]]
        if not parts_out:
            return "no_text"
        scene["speaking"] = "".join(f"<{speaker}> {text}" for _start, _end, speaker, text in parts_out)
        self._store_timing(scene, [
            {
                "speaker": speaker,
                "start": round(start, 2),
                "end": round(end, 2),
                "text": text,
            }
            for start, end, speaker, text in parts_out
        ])
        return "ok"

    def _transcribe_span_audio(self, key: str, start: float, end: float, engine: str = "whisper") -> None:
        """把这一段声音转成文字，写回这一段讲稿。engine 为 whisper 或 voicebox。"""
        root = self.root
        title = "这一段"

        def finish(ok: bool, message: str) -> None:
            self._span_regen_busy = False
            try:
                root.config(cursor="")
            except tk.TclError:
                pass
            if ok:
                self.refresh_gui_scenes()
                show_auto_close_popup(root, title, message)
            else:
                messagebox.showerror(title, message, parent=root)

        try:
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            source = self._span_source_audio(scene) if scene else ""
            if not source:
                root.after(0, lambda: finish(False, "这一场没有主轨声音。"))
                return
            wav = config.get_temp_file(self.workflow.pid, "wav")
            if not self._cut_span_wav(source, start, end, wav):
                root.after(0, lambda: finish(False, "这一段声音没有切出来。"))
                return
            text, err = self._transcribe_wav_to_text(wav, engine, max(1.0, float(end) - float(start)))
            if not text:
                root.after(0, lambda msg=err or "这一段没有转出文字。": finish(False, msg))
                return
            if key.startswith("sec") and key[3:].isdigit():
                index = int(key[3:])
                parts = self._speaking_turn_parts(scene.get("speaking") or "")
                if index >= len(parts):
                    root.after(0, lambda: finish(False, "这一段对不上讲稿。"))
                    return
                parts[index] = (parts[index][0], text)
                scene["speaking"] = "".join(f"<{speaker}>{body}" for speaker, body in parts)
            else:
                scene[key] = text
            self._retime_scene_after_structure(scene)
            self.workflow.save_scenes_to_json()
            root.after(0, lambda: finish(True, f"已写进{title}。"))
        except Exception as exc:
            err = str(exc)
            root.after(0, lambda msg=err: finish(False, msg))

    def _install_span_wav(self, key: str, wav: str, start: float, end: float, scene: dict, clip: str, finish, success: str) -> None:
        root = self.root
        new_len = float(self.workflow.ffmpeg_processor.get_duration(wav) or 0.0)
        if new_len <= 0.2:
            root.after(0, lambda: finish(False, "这一段声音太短。"))
            return
        duration = float(self.workflow.ffmpeg_processor.get_duration(clip) or 0.0)
        if duration <= 0:
            root.after(0, lambda: finish(False, "读不出视频有多长。"))
            return
        end = min(end, duration)
        if end - start < 0.15:
            root.after(0, lambda: finish(False, "这一段太短。"))
            return
        ff = self.workflow.ffmpeg_processor
        pieces = []
        if start > 0.08:
            head = ff.trim_video(clip, 0, start)
            if not head:
                root.after(0, lambda: finish(False, "切开前面一段失败。"))
                return
            pieces.append(head)
        middle = ff.trim_video(clip, start, end)
        if not middle:
            root.after(0, lambda: finish(False, "切开这一段失败。"))
            return
        sped = ff.adjust_video_to_duration(middle, new_len, when_longer="speed")
        muxed = ff.add_audio_to_video(sped, wav, match_audio_length=True, when_longer="speed")
        if not muxed or not os.path.isfile(muxed):
            root.after(0, lambda: finish(False, "新的声音没有接到画面上。"))
            return
        pieces.append(muxed)
        if duration - end > 0.08:
            tail = ff.trim_video(clip, end, duration)
            if not tail:
                root.after(0, lambda: finish(False, "切开后面一段失败。"))
                return
            pieces.append(tail)
        merged = ff.concat_videos(pieces, True)
        if not merged or not os.path.isfile(merged):
            root.after(0, lambda: finish(False, "接回整段视频失败。"))
            return
        self._backup_clip_to_scene_back(scene)
        refresh_scene_media(scene, "clip", ".mp4", merged)
        new_clip = get_file_path(scene, "clip")
        extracted = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(new_clip, "wav")
        if extracted and os.path.isfile(extracted):
            refresh_scene_media(scene, "clip_audio", ".wav", extracted)
        old_len = end - start
        delta = new_len - old_len
        scene[f"{key}_start"] = round(start, 2)
        scene[f"{key}_end"] = round(start + new_len, 2)
        other = "voiceover" if key == "speaking" else "speaking"
        other_start = scene.get(f"{other}_start")
        other_end = scene.get(f"{other}_end")
        try:
            other_start_f = float(other_start)
            other_end_f = float(other_end)
        except (TypeError, ValueError):
            other_start_f = None
            other_end_f = None
        if other_start_f is not None and other_end_f is not None and other_start_f >= end - 0.08:
            scene[f"{other}_start"] = round(other_start_f + delta, 2)
            scene[f"{other}_end"] = round(other_end_f + delta, 2)
        self.workflow.save_scenes_to_json()
        root.after(0, lambda: finish(True, success))

    def _speed_span_audio(self, key: str, speed: float, start: float, end: float) -> None:
        root = self.root

        def finish(ok: bool, message: str) -> None:
            self._span_regen_busy = False
            try:
                root.config(cursor="")
            except tk.TclError:
                pass
            if ok:
                self.refresh_gui_scenes()
                show_auto_close_popup(root, "声音", message)
            else:
                messagebox.showerror("声音", message, parent=root)

        try:
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            clip = get_file_path(scene, "clip") if scene else ""
            source = self._span_source_audio(scene) if scene else ""
            if not clip or not os.path.isfile(clip) or not source:
                root.after(0, lambda: finish(False, "这一场没有主轨声音。"))
                return
            raw = config.get_temp_file(self.workflow.pid, "wav")
            sped = config.get_temp_file(self.workflow.pid, "wav")
            if not self._cut_span_wav(source, start, end, raw):
                root.after(0, lambda: finish(False, "这一段声音没有切出来。"))
                return
            if not self._atempo_wav(raw, speed, sped):
                root.after(0, lambda: finish(False, "速度没有套上。"))
                return
            self._install_span_wav(
                key, sped, start, end, scene, clip, finish,
                f"这一段已经按 {speed:.2f} 倍放好，画面也跟着对齐了。",
            )
        except Exception as exc:
            err = str(exc)
            root.after(0, lambda msg=err: finish(False, msg))

    def _regenerate_span_audio(self, key: str, voice: str, text: str, start: float, end: float) -> None:
        root = self.root

        def finish(ok: bool, message: str) -> None:
            self._span_regen_busy = False
            try:
                root.config(cursor="")
            except tk.TclError:
                pass
            if ok:
                self.refresh_gui_scenes()
                show_auto_close_popup(root, "声音", message)
            else:
                messagebox.showerror("声音", message, parent=root)

        try:
            if not getattr(self, "speech_service", None):
                root.after(0, lambda: finish(False, "语音服务还没准备好。"))
                return
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            clip = get_file_path(scene, "clip") if scene else ""
            if not clip or not os.path.isfile(clip):
                root.after(0, lambda: finish(False, "这一场没有主轨视频。"))
                return
            wav = self.speech_service.synthesize_speaker_text_to_wav(voice, text, self.workflow.language)
            if not wav or not os.path.isfile(wav):
                root.after(0, lambda: finish(False, "语音没有生成出来。"))
                return
            self._install_span_wav(
                key, wav, start, end, scene, clip, finish,
                "这一段声音已经换上，画面也跟着对齐了。",
            )
        except Exception as exc:
            err = str(exc)
            root.after(0, lambda msg=err: finish(False, msg))
