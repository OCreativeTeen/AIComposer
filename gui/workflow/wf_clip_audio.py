"""ClipAudioMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter.messagebox as messagebox
import os
import threading
import config
from project_manager import refresh_scene_media
import project_manager
from utility.file_util import get_file_path, show_auto_close_popup
from gui.choice_dialog import askchoice


class ClipAudioMixin:
    def apply_tts_audio_to_scene_track(
        self,
        scene,
        track,
        speaker,
        content,
        *,
        track_label="Clip",
        save_scenes=True,
        refresh_gui=True,
        show_success_message=True,
        show_error_messages=True,
        ready_wav=None,
    ):
        """
        对单个场景：TTS 生成音频并 mux 到指定轨道视频（clip / narration）。
        用于「生场音频」单镜流程，以及本故事批量生主轨音频。
        """
        text = (content or "").strip()
        if not text and not ready_wav:
            if show_error_messages:
                messagebox.showwarning("警告", "讲话内容为空", parent=self.root)
            return False
        if ready_wav:
            tts_wav = ready_wav
        else:
            tts_wav = self.speech_service.synthesize_speaker_text_to_wav(speaker, text, self.workflow.language)
        if not tts_wav:
            if show_error_messages:
                messagebox.showerror("错误", "TTS 生成失败", parent=self.root)
            return False
        _olda, newa = refresh_scene_media(scene, track + "_audio", ".wav", tts_wav)
        vtrack = get_file_path(scene, track)
        if not vtrack:
            vtrack = get_file_path(scene, "clip")
        if not vtrack or not os.path.exists(vtrack):
            if show_error_messages:
                messagebox.showwarning(
                    "警告",
                    f"场景 id={scene.get('id')} 无可用视频，无法合成。请先添加视频。",
                    parent=self.root,
                )
            return False
        newv = self.workflow.ffmpeg_processor.add_audio_to_video(vtrack, newa)
        refresh_scene_media(scene, track, ".mp4", newv)
        if refresh_gui:
            self.refresh_gui_scenes()
        if save_scenes:
            self.workflow.save_scenes_to_json()
        if show_success_message:
            messagebox.showinfo("成功", f"{track_label} 音频已生成并替换", parent=self.root)
        return True

    def _run_story_clip_audio_all(self, current_scene, source_mode: str = "speaker"):
        """为本故事从 current_scene 起批量 TTS 主轨 clip（不依赖 current_scene_index）。

        source_mode: ``speaker`` → actor + speaking；``narrator`` → narrator + voiceover。

        返回 (ok_count, skipped_lines, fatal_error)。fatal_error 非空时未执行或已中止。
        """
        if not self.workflow or not self.speech_service:
            return 0, [], "工作流未就绪，请先选择项目"
        if not current_scene:
            return 0, [], "没有当前场景"
        story_scenes = self.workflow.scenes_in_story(current_scene)
        if not story_scenes:
            return 0, [], "当前故事无场景"

        ok = 0
        skipped = []
        start = False
        for s in story_scenes:
            if not start:
                if s.get("id") == current_scene.get("id"):
                    start = True
                else:
                    continue

            sid = s.get("id", "?")
            out = self.regenerate_story_clip_for_scene(s, source_mode=source_mode)
            if out == "ok":
                ok += 1
            elif out == "no_content":
                if source_mode == "narrator":
                    skipped.append(f"id={sid}：无旁白内容")
                else:
                    skipped.append(f"id={sid}：无对白内容")
            elif out == "no_speaker":
                if source_mode == "narrator":
                    skipped.append(f"id={sid}：未设置讲员")
                else:
                    skipped.append(f"id={sid}：未设置人物")
            elif out == "fail":
                skipped.append(f"id={sid}：TTS 或合成失败")

        return ok, skipped, None

    def _run_every_scene_clip_audio(self, source_mode: str = "speaker"):
        """全部场景都重新生主轨音频，不限这一集。"""
        if not self.workflow or not self.speech_service:
            return 0, [], "工作流未就绪，请先选择项目"
        scenes = [s for s in (self.workflow.scenes or []) if isinstance(s, dict)]
        if not scenes:
            return 0, [], "没有场景"
        ok = 0
        skipped = []
        for s in scenes:
            sid = s.get("id", "?")
            out = self.regenerate_story_clip_for_scene(s, source_mode=source_mode)
            if out == "ok":
                ok += 1
            elif out == "no_content":
                skipped.append(f"id={sid}：无对白内容")
            elif out == "no_speaker":
                skipped.append(f"id={sid}：未设置人物")
            elif out == "fail":
                skipped.append(f"id={sid}：TTS 或合成失败")
        return ok, skipped, None

    def _make_still_clip_video(self, scene: dict) -> str:
        """用 clip_image 加 clip_audio 做一段静态画面的视频，写成这一场的 clip。

        返回 ``ok``、``no_image``、``no_audio`` 或 ``fail``。
        """
        image = get_file_path(scene, "clip_image")
        audio = get_file_path(scene, "clip_audio")
        if not image or not os.path.isfile(image):
            return "no_image"
        if not audio or not os.path.isfile(audio):
            return "no_audio"
        try:
            video = self.workflow.ffmpeg_processor.image_audio_to_video(image, audio, 1)
        except Exception as exc:  # noqa: BLE001
            print(f"静态视频生成出错 (id={scene.get('id')}): {exc}")
            return "fail"
        if not video or not os.path.isfile(video):
            return "fail"
        refresh_scene_media(scene, "clip", ".mp4", video)
        return "ok"

    def _run_clip_video(self, method: str, scope: str):
        """生场视频：用 clip_image 加 clip_audio 做静态画面视频（method=still）；WAN 生成留着以后用。"""
        if not self.workflow:
            return
        scene_anchor = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene_anchor:
            messagebox.showwarning("提示", "没有当前场景", parent=self.root)
            return
        if method == "wan":
            self.regenerate_video("clip", False)
            return

        self.update_current_scene()
        if scope == "all":
            targets = [s for s in (self.workflow.scenes or []) if isinstance(s, dict)]
        elif scope == "story":
            story = self.workflow.scenes_in_story(scene_anchor) or []
            ids = [id(s) for s in story]
            start = ids.index(id(scene_anchor)) if id(scene_anchor) in ids else 0
            targets = story[start:]
        else:
            targets = [scene_anchor]
        self._run_still_clip_videos(targets)

    def _run_still_clip_videos(self, targets: list, *, quiet: bool = False) -> None:
        """后台给这些场景用 clip_image 加 clip_audio 重做静态 clip 视频，做完弹出结果。"""
        if not targets:
            messagebox.showwarning("生场视频", "没有可用场景", parent=self.root)
            return
        if getattr(self, "_clip_video_worker_busy", False):
            messagebox.showinfo("提示", "已有生场视频任务进行中，请稍候。", parent=self.root)
            return
        self._clip_video_worker_busy = True
        root = self.root

        def work():
            ok = 0
            skipped: list[str] = []
            for s in targets:
                sid = s.get("id", "?")
                out = self._make_still_clip_video(s)
                if out == "ok":
                    ok += 1
                elif out == "no_image":
                    skipped.append(f"id={sid}：没有 clip image")
                elif out == "no_audio":
                    skipped.append(f"id={sid}：没有 clip 音频")
                else:
                    skipped.append(f"id={sid}：合成失败")

            def finish():
                self._clip_video_worker_busy = False
                self.workflow.save_scenes_to_json()
                self.refresh_gui_scenes()
                tail = "\n".join(skipped[:12])
                if len(skipped) > 12:
                    tail += f"\n…另有 {len(skipped) - 12} 条"
                msg = f"已生成 {ok} / {len(targets)} 个场景的静态视频。"
                if tail:
                    msg += "\n\n跳过：\n" + tail
                    if quiet:  # t176u: 自动流程不弹要确认的窗
                        print(msg)
                        show_auto_close_popup(root, "生场视频", msg, duration_ms=4000)
                    else:
                        messagebox.showwarning("生场视频", msg, parent=root)
                else:
                    show_auto_close_popup(root, "生场视频", msg, duration_ms=2000)

            root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def choose_clip_audio_scope(self):
        """生主轨 clip 音频：当前场景，或从这一场起的本集。后台线程执行。"""
        clip_choices = [
            (
                ("single", "speaker"),
                "仅当前场景",
            ),
            (
                ("story", "speaker"),
                "本故事从这一场起",
            ),
            (
                ("all", "speaker"),
                "全部场景",
            ),
        ]
        picked = askchoice(
            "Clip 主轨音频：请选择范围与音源\n（取消 = 放弃）",
            clip_choices,
            parent=self.root,
        )
        if picked is None:
            return
        _lbl, bundle = picked
        scope, source_mode = bundle
        if scope not in ("single", "story", "all") or source_mode not in ("speaker", "narrator"):
            return
        do_all_story = scope == "story"
        do_every_scene = scope == "all"

        if getattr(self, "_clip_audio_worker_busy", False):
            messagebox.showinfo("提示", "已有 Clip 音频生成任务进行中，请稍候。", parent=self.root)
            return
        scene_anchor = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene_anchor:
            messagebox.showwarning("提示", "没有当前场景", parent=self.root)
            return
        anchor_id = scene_anchor.get("id")
        self._clip_audio_worker_busy = True
        root = self.root

        def clear_busy():
            self._clip_audio_worker_busy = False

        def work():
            try:
                if scene_anchor not in self.workflow.scenes:
                    root.after(
                        0,
                        lambda: (
                            clear_busy(),
                            messagebox.showwarning(
                                "Clip 音频",
                                "发起时的场景已不在当前列表中，任务取消。",
                                parent=root,
                            ),
                        ),
                    )
                    return

                if not do_all_story and not do_every_scene:
                    try:
                        out = self.regenerate_story_clip_for_scene(
                            scene_anchor, source_mode=source_mode
                        )
                    except Exception as e:
                        root.after(
                            0,
                            lambda e=e: (
                                clear_busy(),
                                messagebox.showerror("Clip 音频", f"生成失败：{e}", parent=root),
                            ),
                        )
                        return

                    def finish_single():
                        clear_busy()
                        still = scene_anchor in self.workflow.scenes
                        self.workflow.save_scenes_to_json()
                        self.refresh_gui_scenes()
                        if not still:
                            messagebox.showwarning(
                                "Clip 音频",
                                f"任务完成时，发起时的场景 (id={anchor_id}) 已从列表中移除；"
                                "若磁盘上已生成媒体，请自行核对。",
                                parent=root,
                            )
                        if out == "ok":
                            messagebox.showinfo("Clip 音频", "当前场景主轨音频已生成。", parent=root)
                        elif out == "no_content":
                            if source_mode == "narrator":
                                messagebox.showwarning("Clip 音频", "当前场景无旁白内容，跳过。", parent=root)
                            else:
                                messagebox.showwarning("Clip 音频", "当前场景无对白内容，跳过。", parent=root)
                        elif out == "no_speaker":
                            if source_mode == "narrator":
                                messagebox.showwarning("Clip 音频", "未设置讲员，跳过。", parent=root)
                            else:
                                messagebox.showwarning("Clip 音频", "未设置人物，跳过。", parent=root)
                        elif out == "no_scene":
                            messagebox.showwarning("Clip 音频", "当前场景无效。", parent=root)
                        else:
                            messagebox.showwarning("Clip 音频", "TTS 或合成失败。", parent=root)

                    root.after(0, finish_single)
                    return

                if do_every_scene:
                    ok, skipped, err = self._run_every_scene_clip_audio(source_mode=source_mode)
                    title = "全部场景生音频"
                    total = len(self.workflow.scenes or [])
                else:
                    ok, skipped, err = self._run_story_clip_audio_all(scene_anchor, source_mode=source_mode)
                    title = "本故事生音频"
                    story_scenes = self.workflow.scenes_in_story(scene_anchor)
                    total = len(story_scenes) if story_scenes else 0

                def finish_batch(ok=ok, skipped=skipped, err=err, title=title, total=total):
                    clear_busy()
                    self.workflow.save_scenes_to_json()
                    self.refresh_gui_scenes()
                    if err:
                        messagebox.showerror(title, err, parent=root)
                        return
                    tail = "\n".join(skipped[:12])
                    if len(skipped) > 12:
                        tail += f"\n… 另有 {len(skipped) - 12} 条"
                    src_note = "人物+对白" if source_mode == "speaker" else "讲员+旁白"
                    msg = f"完成（{src_note}）：成功 {ok} / {total} 个场景。"
                    if skipped:
                        msg += f"\n\n跳过或失败 ({len(skipped)}):\n{tail}"
                    messagebox.showinfo(title, msg, parent=root)

                root.after(0, finish_batch)
            except Exception as e:
                root.after(
                    0,
                    lambda e=e: (
                        clear_busy(),
                        messagebox.showerror("Clip 音频", f"任务异常：{e}", parent=root),
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def _transcribe_engine(self) -> str | None:
        """用哪一种转录，由 config.TRANSCRIBE_ENGINE 决定（"whisper" 或 "voicebox"），不再问用户。"""
        engine = str(getattr(config, "TRANSCRIBE_ENGINE", "whisper") or "").strip().lower()
        if engine not in ("whisper", "voicebox"):
            messagebox.showerror(
                "音频转录",
                f"config.py 里的 TRANSCRIBE_ENGINE 写的是 {engine!r}，只能是 \"whisper\" 或 \"voicebox\"。",
                parent=self.root,
            )
            return None
        return engine

    def choose_clip_transcribe_scope(self):
        """把主轨声音转成讲稿。范围是本场、本集，或全部场。"""
        picked = askchoice(
            "音频转录：请选择范围\n（取消 = 放弃）",
            [
                ("scene", "本场"),
                ("episode", "本集内容"),
                ("all", "全部内容"),
            ],
            parent=self.root,
        )
        if picked is None:
            return
        _label, scope = picked
        if scope not in ("scene", "episode", "all"):
            return
        engine = self._transcribe_engine()
        if engine is None:
            return
        if getattr(self, "_clip_transcribe_busy", False):
            messagebox.showinfo("音频转录", "上一次转录还在进行。", parent=self.root)
            return
        scene_anchor = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
        if not scene_anchor:
            messagebox.showwarning("音频转录", "没有当前场景", parent=self.root)
            return
        if scope == "scene":
            targets = [scene_anchor]
        elif scope == "episode":
            targets = list(self.workflow.scenes_in_story(scene_anchor) or [scene_anchor])
        else:
            targets = [s for s in (self.workflow.scenes or []) if isinstance(s, dict)]
        if not targets:
            messagebox.showwarning("音频转录", "没有要转录的场。", parent=self.root)
            return
        self._clip_transcribe_busy = True
        root = self.root

        def work():
            ok = 0
            skipped = []
            try:
                for scene in targets:
                    if scene not in (self.workflow.scenes or []):
                        continue
                    sid = scene.get("id", "?")
                    out = self._transcribe_scene_clip(scene, engine)
                    if out == "ok":
                        ok += 1
                    elif out == "no_audio":
                        skipped.append(f"id={sid}：没有主轨声音")
                    elif out == "skip":
                        skipped.append(f"id={sid}：时间记录对不上，已跳过")
                    elif out == "no_text":
                        skipped.append(f"id={sid}：没有转出文字")
                    else:
                        skipped.append(f"id={sid}：转录失败")
                self.workflow.save_scenes_to_json()
            except Exception as exc:
                err = str(exc)

                def fail(msg=err):
                    self._clip_transcribe_busy = False
                    messagebox.showerror("音频转录", msg, parent=root)

                root.after(0, fail)
                return

            def finish(ok_n=ok, skipped_rows=list(skipped), total=len(targets)):
                self._clip_transcribe_busy = False
                self.refresh_gui_scenes()
                tail = "\n".join(skipped_rows[:12])
                if len(skipped_rows) > 12:
                    tail += f"\n… 另有 {len(skipped_rows) - 12} 条"
                msg = f"完成：成功 {ok_n} / {total} 个场景。"
                if skipped_rows:
                    msg += f"\n\n跳过或失败 ({len(skipped_rows)}):\n{tail}"
                messagebox.showinfo("音频转录", msg, parent=root)

            root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def _speaking_voice_turns(self, scene):
        """speaking 里的 ``<N>`` 换成对应 actor 的音色。没有标记就沿用上一个人。"""
        from utility.voicebox_speech_service import split_speaking_turns

        raw = (scene.get("speaking") or "").replace("——", ", ").replace("—", ", ")
        pieces = split_speaking_turns(raw)
        if not pieces:
            return []
        entries = project_manager.actor_entries(scene.get("actor") or "")
        bodies = [(row.get("body") or "").strip() for row in entries if (row.get("body") or "").strip()]
        if not bodies:
            return []
        turns = []
        last_voice = ""
        for n, text in pieces:
            if n < 1 or n > 3 or n > len(bodies):
                continue
            body = bodies[n - 1]
            voice = project_manager.resolve_actor_voice(body) or body or last_voice
            if not voice:
                return []
            last_voice = voice
            turns.append((voice, text))
        return turns

    def _clip_wav_from_speaking_timing(self, scene):
        """按每段的时间生成。两段之间一定补静音：记录里的空档，小于 0.3 秒按 0.3 秒。

        没有可用的时间记录时返回 None，调用方改走整段生成。
        记录在但某段生成失败时返回 False。
        成功时返回 (wav, 每段讲话的起止)。起点仍是原来的起点，结束点改成这段真实语音的长度。静音只留在两段中间，不写进下一段的起点。
        """
        stored = self._timing_sections(scene)
        if not stored:
            return None
        entries = project_manager.actor_entries(scene.get("actor") or "")
        bodies = [(row.get("body") or "").strip() for row in entries if (row.get("body") or "").strip()]
        if not bodies:
            return None
        rows = []
        for item in stored:
            if not isinstance(item, dict):
                continue
            body = (item.get("text") or "").strip()
            if not body:
                continue
            try:
                start = float(item.get("start"))
                end = float(item.get("end"))
                speaker = int(item.get("speaker") or 1)
            except (TypeError, ValueError):
                continue
            if end <= start or speaker < 1 or speaker > 3 or speaker > len(bodies):
                continue
            rows.append((start, end, speaker, body))
        if not rows:
            return None
        rows.sort(key=lambda row: (row[0], row[1]))
        chain = []
        timing = []
        ap = self.workflow.ffmpeg_audio_processor
        lang = self.workflow.language
        for index, (start, end, speaker, body) in enumerate(rows):
            voice_body = bodies[speaker - 1]
            voice = project_manager.resolve_actor_voice(voice_body) or voice_body
            if not voice:
                return False
            wav = self.speech_service.synthesize_speaker_text_to_wav(voice, body, lang)
            if not wav:
                return False
            dur = float(ap.get_duration(wav) or 0.0)
            if dur <= 0:
                return False
            timing.append({
                "speaker": speaker,
                "start": round(start, 2),
                "end": round(start + dur, 2),
                "text": body,
            })
            chain.append(wav)
            if index + 1 >= len(rows):
                continue
            # 两段之间的空档用记录里的间隔。小于 0.3 秒就按 0.3 秒，不能太短。
            gap = max(self._MIN_SECTION_GAP_SEC, rows[index + 1][0] - end)
            silence = ap.make_silence(gap)
            if not silence:
                return False
            chain.append(silence)
        if len(chain) == 1:
            return chain[0], timing
        joined = self.workflow.ffmpeg_audio_processor.concat_audios(chain)
        if not joined:
            return False
        return joined, timing

    def regenerate_story_clip_for_scene(self, scene, source_mode: str = "speaker"):
        """单场景：按 speaking 里的 ``<N>`` 换音色，拼成主轨 clip 音频。

        返回：'ok' 成功，'fail' TTS/合成失败，'no_content' / 'no_speaker' 跳过，'no_scene' 无场景。"""
        if not scene:
            return "no_scene"
        turns = self._speaking_voice_turns(scene)
        if not (scene.get("speaking") or "").strip():
            return "no_content"
        if not turns:
            return "no_speaker"
        timing = None
        built = self._clip_wav_from_speaking_timing(scene)
        if built is False:
            return "fail"
        if built:
            wav, timing = built
        else:
            wav = self.speech_service.synthesize_turns_to_wav(turns, self.workflow.language)
        if not wav:
            return "fail"
        ok = self.apply_tts_audio_to_scene_track(
            scene,
            "clip",
            turns[0][0],
            (scene.get("speaking") or "").strip(),
            track_label="Clip",
            save_scenes=False,
            refresh_gui=False,
            show_success_message=False,
            show_error_messages=False,
            ready_wav=wav,
        )
        if not ok:
            return "fail"
        if timing:
            self._store_timing(scene, timing)
        return "ok"
