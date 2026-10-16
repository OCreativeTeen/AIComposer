"""MediaImportMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter.messagebox as messagebox
import os
from datetime import datetime
import config
from project_manager import refresh_scene_media
import project_manager
from utility.file_util import get_file_path, show_auto_close_popup
import shutil
from gui.choice_dialog import askchoice, askchoice_media_preview
from gui.workflow.wf_common import _download_folder_list_matching_suffixes, _external_media_pick_folders


class MediaImportMixin:
    def choose_from_channel_media(self, track, audio_action, radios=None):
        try:
            channel = project_manager.PROJECT_CONFIG.get('channel')
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            source_folder = config.channel_track_media_dir(channel, track)
            if not os.path.isdir(source_folder):
                messagebox.showwarning("警告", f"未找到频道素材目录：\n{source_folder}")
                return

            # 1. 文件名含场景名（同档内优先匹配位置前缀）
            # 2. 不含场景名但文件名以 starting / ending / running 开头（依当前是否首/末场景）
            # 3. 其余符合 ratio 的 mp4
            # 1. 文件名以 starting / ending / running 开头（依当前是否首/末场景）优先
            # 2. 横屏项目：169_* 或无宽高前缀（视为 169）；竖屏：仅 916_*
            vw, vh = project_manager.video_size_pair(
                (project_manager.PROJECT_CONFIG or {}).get("video_width"),
                (project_manager.PROJECT_CONFIG or {}).get("video_height"),
            )
            landscape = vw > vh
            if track == "clip" or track == "narration" or track == "zero":
                candidates = [
                    f for f in os.listdir(source_folder)
                    if f.lower().endswith(".mp4")
                    and os.path.isfile(os.path.join(source_folder, f))
                    and config.channel_media_matches_project_layout(f, landscape=landscape)
                ]
                if not candidates:
                    messagebox.showwarning("警告", "未找到 .mp4 文件")
                    return
            else:
                _img_ext = (".png", ".jpg", ".jpeg", ".webp")
                candidates = [
                    f for f in os.listdir(source_folder)
                    if f.lower().endswith(_img_ext)
                    and os.path.isfile(os.path.join(source_folder, f))
                    and config.channel_media_matches_project_layout(f, landscape=landscape)
                ]
                if not candidates:
                    messagebox.showwarning("警告", "未找到图片文件（png / jpg / webp）")
                    return

            n_scenes = len(self.workflow.scenes)
            idx = self.current_scene_index
            if idx == 0:
                position_prefix = "starting"
            elif n_scenes > 0 and idx == n_scenes - 1:
                position_prefix = "ending"
            else:
                position_prefix = "running"
            pp = position_prefix.lower()

            def _channel_media_sort_key(f: str):
                fl = f.lower()
                has_pos = fl.startswith(pp)
                if has_pos:
                    return (1, 0, f)
                return (2, 0, f)

            matching = sorted(candidates, key=_channel_media_sort_key)
            mp4_track = track in ("clip", "narration", "zero")
            pv_kw = {}
            if mp4_track:
                pv_kw = {
                    "use_mp4_video_preview": True,
                    "build_volume_adjusted_pair": self._build_volume_adjusted_mp4_wav_pair,
                }
                if radios:
                    pv_kw["radios"] = radios
            pick = askchoice_media_preview(
                "从频道媒体选择文件",
                matching, source_folder, self.root,
                **pv_kw,
            )
            if not pick:
                return

            if mp4_track:
                if radios:
                    _fn, tmp_mp4, tmp_wav, audio_action = pick[0], pick[1], pick[2], pick[-1]
                else:
                    _fn, tmp_mp4, tmp_wav = pick
                self._video_simple_replacement_async(
                    current_scene,
                    tmp_mp4,
                    tmp_wav,
                    audio_action,
                    track,
                    track_status="ENH2",
                )
                return
            else:
                media_path = os.path.join(source_folder, pick)
                webp_path = self.workflow.ffmpeg_processor.to_webp(media_path)
                refresh_scene_media(current_scene, track, ".webp", webp_path, True)

            self.refresh_gui_scenes()
                
        except Exception as e:
            messagebox.showerror("错误", f"选择文件时出错: {str(e)}")

    def _import_dest_track(self, dest: str) -> tuple[str, bool]:
        """返回写入的轨道，以及要不要铺到这一集的每一场。"""
        if dest in ("zero", "zero_episode"):
            return "zero", True
        if dest == "zero_scene":
            return "zero", False
        return dest or "clip", False

    def _project_input_dir(self, kind: str) -> str:
        path = os.path.join(config.get_media_path(self.workflow.pid), kind)
        os.makedirs(path, exist_ok=True)
        return path

    def _names_in(self, folder: str, suffixes: tuple[str, ...]) -> list:
        if not folder or not os.path.isdir(folder):
            return []
        names = [
            name
            for name in os.listdir(folder)
            if name.lower().endswith(suffixes) and os.path.isfile(os.path.join(folder, name))
        ]
        return sorted(names)

    def _project_video_source(self) -> tuple[str, list]:
        folder = self._project_input_dir("input_video")
        return folder, self._names_in(folder, (".mp4",))

    def _project_audio_source(self) -> tuple[str, list]:
        folder = self._project_input_dir("input_audio")
        return folder, self._audio_names_in(folder)

    def _intake_import_file(self, src: str, *, kind: str, move: bool) -> str:
        """把选中的文件放进项目 media/input_video 或 input_audio。下载来的移走，其余复制。"""
        if not src or not os.path.isfile(src):
            return src
        dest_dir = self._project_input_dir(kind)
        if os.path.normcase(os.path.abspath(os.path.dirname(src))) == os.path.normcase(os.path.abspath(dest_dir)):
            return src
        name = os.path.basename(src)
        dest = os.path.join(dest_dir, name)
        if os.path.exists(dest):
            stem, ext = os.path.splitext(name)
            dest = os.path.join(dest_dir, f"{stem}_{datetime.now().strftime('%H%M%S')}{ext}")
        if move:
            shutil.move(src, dest)
        else:
            shutil.copy2(src, dest)
        return dest

    def _next_audio_segment_path(self, src: str, ext: str) -> str:
        """同一段音频多次导入时，按 原名-1、原名-2 往后排。"""
        dest_dir = self._project_input_dir("input_audio")
        stem = os.path.splitext(os.path.basename(src))[0] or "audio"
        if not ext.startswith("."):
            ext = f".{ext}"
        used = []
        prefix = f"{stem}-"
        if os.path.isdir(dest_dir):
            for name in os.listdir(dest_dir):
                file_stem = os.path.splitext(name)[0]
                if not file_stem.startswith(prefix):
                    continue
                tail = file_stem[len(prefix):]
                if tail.isdigit():
                    used.append(int(tail))
        number = (max(used) + 1) if used else 1
        return os.path.join(dest_dir, f"{stem}-{number}{ext}")

    def _audio_names_in(self, folder: str) -> list:
        if not folder or not os.path.isdir(folder):
            return []
        names = [
            name
            for name in os.listdir(folder)
            if name.lower().endswith((".mp3", ".wav"))
            and os.path.isfile(os.path.join(folder, name))
        ]
        return sorted(names)

    def _download_audio_source(self) -> tuple[str, list]:
        folder, _videos = self._download_mp4_source()
        return folder, self._audio_names_in(folder)

    def _channel_audio_source(self) -> tuple[str, list]:
        folder, _videos = self._channel_mp4_source()
        return folder, self._audio_names_in(folder)

    def _audio_source_specs(self) -> list:
        project_folder, project_files = self._project_audio_source()
        download_folder, download_files = self._download_audio_source()
        channel_folder, channel_files = self._channel_audio_source()
        return [
            {"key": "project", "label": "项目", "folder": project_folder, "choices": project_files},
            {"key": "download", "label": "下载", "folder": download_folder, "choices": download_files},
            {"key": "channel", "label": "频道", "folder": channel_folder, "choices": channel_files},
        ]

    def _mix_audio_onto_video(self, video_path: str, audio: dict) -> tuple[str, str]:
        from gui.mp4_pick_preview_dialog import _build_preview_segment_wav

        src = audio.get("path") or ""
        start = float(audio.get("start") or 0.0)
        end = float(audio.get("end") or 0.0)
        speed = float(audio.get("speed") or 1.0)
        volume = float(audio.get("volume") or 1.0)
        duration = float(audio.get("duration") or 0.0)
        untouched = (
            abs(volume - 1.0) < 0.001
            and abs(speed - 1.0) < 0.05
            and start <= 0.05
            and (duration <= 0 or end >= duration - 0.05)
        )
        wav = src if untouched and src and os.path.isfile(src) else _build_preview_segment_wav(
            src, start, end, speed, volume,
        )
        if not wav:
            return video_path, ""
        mixed = self.workflow.ffmpeg_processor.add_audio_to_video(video_path, wav, True, "speed")
        if mixed and os.path.isfile(mixed):
            return mixed, wav
        return video_path, wav

    def _blend_audio_into_video(self, video_path: str, audio: dict) -> tuple[str, str]:
        from gui.mp4_pick_preview_dialog import _build_preview_segment_wav

        src = audio.get("path") or ""
        wav = _build_preview_segment_wav(
            src,
            float(audio.get("start") or 0.0),
            float(audio.get("end") or 0.0),
            float(audio.get("speed") or 1.0),
            1.0,
        )
        if not wav:
            return video_path, ""
        fp = self.workflow.ffmpeg_processor
        fade_in = float(audio.get("fade_in") or 0.0)
        fade_out = float(audio.get("fade_out") or 0.0)
        audio_dur = float(fp.get_duration(wav) or 0.0)
        video_dur = float(fp.get_duration(video_path) or 0.0)
        mix_len = audio_dur
        if video_dur > 0.05 and audio_dur > video_dur + 0.05:
            mix_len = video_dur
        if mix_len > 0.05 and (fade_in > 0.01 or fade_out > 0.01 or mix_len < audio_dur - 0.05):
            piece = fp.extract_audio_segment(wav, 0, mix_len, fade_in, fade_out)
            if piece:
                wav = piece
        ratio = float(audio.get("mix_ratio") if audio.get("mix_ratio") is not None else 0.5)
        mixed = fp.video_audio_mix(video_path, wav, volume=ratio, audio_mix_position=0.0, match_audio_length=False)
        if not mixed or not os.path.isfile(mixed):
            return video_path, wav
        raw = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(mixed)
        return mixed, raw or wav

    def _later_story_scenes(self, scene) -> list:
        story = self.workflow.scenes_in_story(scene) if scene else []
        try:
            index = story.index(scene)
        except ValueError:
            return []
        later = []
        for item in story[index + 1:]:
            path = item.get("clip") if isinstance(item.get("clip"), str) else ""
            path = (path or "").strip()
            if not path or not os.path.isfile(path):
                break
            later.append(item)
        return later

    def _current_clip_length(self) -> float:
        """这一场现有 clip 的时长（主窗口“共 …”），没有视频就返回 0。"""
        try:
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            path = get_file_path(scene, "clip") if scene else ""
            if not path or not os.path.isfile(path):
                return 0.0
            return float(self.workflow.ffmpeg_processor.get_duration(path) or 0.0)
        except Exception:
            return 0.0

    def _later_scene_lengths(self) -> list[float]:
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        fp = self.workflow.ffmpeg_processor
        lengths = []
        for item in self._later_story_scenes(scene):
            path = (item.get("clip") or "").strip()
            dur = float(fp.get_duration(path) or 0.0)
            if dur <= 0.05:
                break
            lengths.append(dur)
        return lengths

    def _blend_audio_across_scenes(self, scene, first_video: str, audio: dict) -> None:
        from gui.mp4_pick_preview_dialog import _build_preview_segment_wav

        wav = _build_preview_segment_wav(
            audio.get("path") or "",
            float(audio.get("start") or 0.0),
            float(audio.get("end") or 0.0),
            float(audio.get("speed") or 1.0),
            1.0,
        )
        if not wav:
            messagebox.showerror("混音", "这段音频处理失败。", parent=self.root)
            return
        fp = self.workflow.ffmpeg_processor
        audio_dur = float(fp.get_duration(wav) or 0.0)
        if audio_dur <= 0.05:
            messagebox.showerror("混音", "这段音频没有长度。", parent=self.root)
            return
        count = max(1, int(audio.get("mix_scenes") or 1))
        mix_at = max(0.0, float(audio.get("mix_at") or 0.0))
        targets = [scene] + self._later_story_scenes(scene)
        targets = targets[:count]
        fade_in = float(audio.get("fade_in") or 0.0)
        fade_out = float(audio.get("fade_out") or 0.0)
        ratio = float(audio.get("mix_ratio") if audio.get("mix_ratio") is not None else 0.5)
        # 混音+声音淡变：先把导入片的画面/原声淡好，再逐场混旁白。
        fi = float(audio.get("video_fade_in") or 0.0)
        fo = float(audio.get("video_fade_out") or 0.0)
        af = bool(audio.get("audio_fade", True))
        if af and (fi >= 0.05 or fo >= 0.05):
            first_video = self._fade_finished_clip(first_video, fi, fo, audio_fade=True)
            fi, fo, af = 0.0, 0.0, False
        offset = 0.0
        written = 0
        for index, target in enumerate(targets):
            video = first_video if index == 0 else (target.get("clip") or "").strip()
            if not video or not os.path.isfile(video):
                break
            video_dur = float(fp.get_duration(video) or 0.0)
            remaining = audio_dur - offset
            if video_dur <= 0.05 or remaining <= 0.05:
                break
            room = max(0.0, video_dur - mix_at) if index == 0 else video_dur
            if room <= 0.05:
                continue
            mix_len = min(room, remaining)
            last = index == len(targets) - 1 or offset + mix_len >= audio_dur - 0.05
            piece = fp.extract_audio_segment(
                wav,
                offset,
                mix_len,
                fade_in if offset <= 0.05 else 0.0,
                fade_out if last else 0.0,
            )
            if not piece:
                break
            mixed = fp.video_audio_mix(
                video,
                piece,
                volume=ratio,
                audio_mix_position=mix_at if index == 0 else 0.0,
                match_audio_length=False,
            )
            if not mixed or not os.path.isfile(mixed):
                break
            raw = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(mixed)
            if index == 0 and (fi >= 0.05 or fo >= 0.05):
                # 仅剩画面淡变（声音已在混音前处理，或未勾选同时淡变声音）
                mixed = self._fade_finished_clip(mixed, fi, fo, audio_fade=False)
                raw = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(mixed) or raw
            self._backup_clip_to_scene_back(target)
            refresh_scene_media(target, "clip", ".mp4", mixed)
            if raw and os.path.isfile(raw):
                refresh_scene_media(target, "clip_audio", ".wav", raw, True)
            offset += mix_len
            written += 1
        if not written:
            messagebox.showerror("混音", "没有混进任何一场。", parent=self.root)
            return
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, "混音", f"已混进 {written} 场。每一场可以用时钟退回。")

    def _apply_editor_pick(self, pick: dict, *, stage_download: bool) -> None:
        if isinstance(pick, dict) and pick.get("audio_only"):
            audio = pick.get("audio") or {}
            src = audio.get("path") or ""
            if not src or not os.path.isfile(src):
                messagebox.showerror("音频", "这段音频不在了。", parent=self.root)
                return
            if audio.get("as_is"):
                dest = self._next_audio_segment_path(src, os.path.splitext(src)[1] or ".mp3")
                shutil.copy2(src, dest)
            else:
                from gui.mp4_pick_preview_dialog import _build_preview_segment_wav

                wav = _build_preview_segment_wav(
                    src,
                    float(audio.get("start") or 0.0),
                    float(audio.get("end") or 0.0),
                    float(audio.get("speed") or 1.0),
                    float(audio.get("volume") or 1.0),
                )
                if not wav:
                    messagebox.showerror("音频", "这段音频处理失败。", parent=self.root)
                    return
                dest = self._next_audio_segment_path(src, ".wav")
                if os.path.exists(dest):
                    os.remove(dest)
                shutil.move(wav, dest)
            show_auto_close_popup(self.root, "音频", f"已拷进项目：{os.path.basename(dest)}")
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene or not isinstance(pick, dict):
            return
        mp4 = pick.get("mp4") or ""
        wav = pick.get("wav") or ""
        audio = pick.get("audio")
        if audio and stage_download:
            audio["path"] = self._intake_import_file(
                audio.get("path") or "",
                kind="input_audio",
                move=(audio.get("source") == "download"),
            )
        if audio and audio.get("use") == "mix" and not stage_download:
            audio["video_fade_in"] = pick.get("video_fade_in") or 0.0
            audio["video_fade_out"] = pick.get("video_fade_out") or 0.0
            audio["audio_fade"] = bool(pick.get("audio_fade"))
            self._blend_audio_across_scenes(scene, mp4, audio)
            return
        fi = float(pick.get("video_fade_in") or 0.0)
        fo = float(pick.get("video_fade_out") or 0.0)
        af = bool(pick.get("audio_fade"))
        if audio:
            if audio.get("use") == "mix":
                # 混音：先淡导入片原声(+画面)，再混入所选旁白；之后不再对混音结果 afade。
                if af and (fi >= 0.05 or fo >= 0.05):
                    pre = self._fade_finished_clip(mp4, fi, fo, audio_fade=True)
                    if pre and os.path.isfile(pre):
                        mp4 = pre
                    fi, fo, af = 0.0, 0.0, False
                mp4, mixed_wav = self._blend_audio_into_video(mp4, audio)
            else:
                # 配声替换：只允许画面淡变
                af = False
                mp4, mixed_wav = self._mix_audio_onto_video(mp4, audio)
            if mixed_wav:
                wav = mixed_wav
        # 导入视频原声/混音(radio)：此处先淡，再交给 simple_replacement 混合场景声。
        # 配声：audio_fade=False，只淡画面。
        faded = self._fade_finished_clip(mp4, fi, fo, audio_fade=af)
        if faded and faded != mp4 and os.path.isfile(faded):
            mp4 = faded
            extracted = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(mp4)
            if extracted and os.path.isfile(extracted):
                wav = extracted
        dest = (pick.get("dest") or "clip").strip() or "clip"
        track, share_episode = self._import_dest_track(dest)
        if track == "clip":
            self._backup_clip_to_scene_back(scene)
        source = pick.get("source") or ""
        if source == "channel":
            filename = pick.get("filename") or ""
            channel_folder = self._channel_mp4_source()[0]
            if filename:
                self._intake_import_file(
                    os.path.join(channel_folder, filename),
                    kind="input_video",
                    move=False,
                )
            self._video_simple_replacement_async(
                scene, mp4, wav, pick.get("radio") or "keep", track,
                track_status="ENH2", share_episode=share_episode,
                mix_volume=float(pick.get("mix_volume") or 0.5),
            )
            return
        if stage_download and source in ("download", "project"):
            folder = (
                self._project_input_dir("input_video")
                if source == "project"
                else self._download_mp4_source()[0]
            )
            res = self._stage_downloaded_video(
                folder,
                pick.get("filename") or "",
                mp4,
                wav,
                pick.get("action") or "replace",
                track,
                track,
            )
            if res:
                if audio:
                    # 另选了音频：视频已经带着这条音频，原样写入。
                    res["audio_choice"] = "keep"
                else:
                    res["audio_choice"] = (pick.get("radio") or "").strip()
                res["mix_volume"] = float(pick.get("mix_volume") or 0.5)
                print(f"🎚️ 导入视频：对话框传回的声音方式 radio={pick.get('radio')!r}, 采用={res['audio_choice']!r}")
                self._apply_download_video_result(res, track, share_episode=share_episode)
            return
        refresh_scene_media(scene, track, ".mp4", mp4)
        if wav and os.path.isfile(wav):
            refresh_scene_media(scene, track + "_audio", ".wav", wav, True)
        if track == "zero" and share_episode:
            self._share_zero_across_episode(scene)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        if track == "zero" and share_episode:
            n = len(self.workflow.scenes_in_story(scene) or [])
            show_auto_close_popup(self.root, "Zero", f"已写入这一集的 {n} 个场景。")
        elif track == "zero":
            show_auto_close_popup(self.root, "Zero", "已写入这一场的 Zero。")
        else:
            show_auto_close_popup(self.root, "片段", "已写回这一场。")

    def _fade_finished_clip(
        self,
        video_path: str,
        fade_in: float,
        fade_out: float,
        audio_fade: bool = True,
    ) -> str:
        """成片写回之前：画面淡入/淡出；audio_fade 时同一时长也对音轨 afade。

        导入视频混音顺序：先对本段（导入原声）做淡变，再与旁白/场景声混合。
        配声模式应传 audio_fade=False，只淡画面。
        """
        fade_in = max(0.0, min(3.0, float(fade_in or 0.0)))
        fade_out = max(0.0, min(3.0, float(fade_out or 0.0)))
        if fade_in < 0.05 and fade_out < 0.05:
            return video_path
        if not video_path or not os.path.isfile(video_path) or not self.workflow:
            return video_path
        fp = self.workflow.ffmpeg_processor
        duration = float(fp.get_duration(video_path) or 0.0)
        if duration > 0.05:
            half = duration / 2.0
            fade_in = min(fade_in, half)
            fade_out = min(fade_out, half)
            if fade_in + fade_out > duration:
                scale = duration / (fade_in + fade_out)
                fade_in *= scale
                fade_out *= scale
        faded = fp.fade_video(video_path, fade_in, fade_out, audio_fade=bool(audio_fade))
        if faded and os.path.isfile(faded) and os.path.getsize(faded) > 0:
            return faded
        return video_path

    def _share_zero_across_episode(self, scene) -> None:
        """导入到 ZERO 时，同一集里的每一场都换成这一份。"""
        if not scene or not self.workflow:
            return
        zero = get_file_path(scene, "zero")
        zero_audio = get_file_path(scene, "zero_audio")
        for other in self.workflow.scenes_in_story(scene) or []:
            if other is scene:
                continue
            # 同一集共用一份，其它场景直接指向同一个文件，不再拷贝。
            if zero and os.path.isfile(zero) and scene.get("zero"):
                other["zero"] = scene["zero"]
            if zero_audio and os.path.isfile(zero_audio) and scene.get("zero_audio"):
                other["zero_audio"] = scene["zero_audio"]

    def _download_mp4_source(self) -> tuple[str, list]:
        suffixes = (".mp4",)
        for folder in _external_media_pick_folders():
            matching = _download_folder_list_matching_suffixes(folder, suffixes)
            if matching:
                return folder, matching
        download_path = config.get_project_path(self.workflow.pid) + "/download"
        os.makedirs(download_path, exist_ok=True)
        return download_path, _download_folder_list_matching_suffixes(download_path, suffixes)

    def _channel_mp4_source(self) -> tuple[str, list]:
        channel = (project_manager.PROJECT_CONFIG or {}).get("channel")
        source_folder = config.channel_track_media_dir(channel, "clip")
        if not os.path.isdir(source_folder):
            return source_folder, []
        vw, vh = project_manager.video_size_pair(
            (project_manager.PROJECT_CONFIG or {}).get("video_width"),
            (project_manager.PROJECT_CONFIG or {}).get("video_height"),
        )
        landscape = vw > vh
        candidates = [
            name
            for name in os.listdir(source_folder)
            if name.lower().endswith(".mp4")
            and os.path.isfile(os.path.join(source_folder, name))
            and config.channel_media_matches_project_layout(name, landscape=landscape)
        ]
        n_scenes = len(self.workflow.scenes or [])
        idx = self.current_scene_index
        if idx == 0:
            position_prefix = "starting"
        elif n_scenes > 0 and idx == n_scenes - 1:
            position_prefix = "ending"
        else:
            position_prefix = "running"
        prefix = position_prefix.lower()

        def _sort_key(name: str):
            if name.lower().startswith(prefix):
                return (1, 0, name)
            return (2, 0, name)

        return source_folder, sorted(candidates, key=_sort_key)

    def _stage_downloaded_video(
        self, folder: str, filename: str, temp_adj_mp4, temp_adj_wav, place, picked_radio, track_rename_key: str
    ) -> dict | None:
        """外部下载的视频移进项目 media/input_video。已经在这个目录里的文件留在原地。"""
        input_dir = self._project_input_dir("input_video")
        media_path = os.path.join(folder, filename)
        in_project = os.path.normcase(os.path.abspath(folder)) == os.path.normcase(
            os.path.abspath(input_dir)
        )
        if in_project:
            media_final = media_path
        elif os.path.isfile(media_path):
            media_final = self._intake_import_file(media_path, kind="input_video", move=True)
        else:
            media_final = os.path.join(input_dir, os.path.basename(filename))
        if temp_adj_mp4 is None or temp_adj_wav is None:
            messagebox.showerror("错误", "内部错误：未取得音量处理后的临时视频/音频。", parent=self.root)
            return None
        return {
            "final_path": media_final,
            "temp_adj_mp4": temp_adj_mp4,
            "temp_adj_wav": temp_adj_wav,
            "place": place,
            "track": picked_radio,
        }

    def _apply_download_video_result(self, res: dict, track: str, *, share_episode: bool | None = None) -> None:
        if share_episode is None:
            share_episode = track == "zero"
        if res.get("track"):
            track = res["track"]
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        rename = res["final_path"]
        temp_adj_mp4 = res.get("temp_adj_mp4")
        temp_adj_wav = res.get("temp_adj_wav")

        if rename.lower().endswith(".mp4"):
            place_mode = res.get("place") or "replace"
            if place_mode in ("prepend", "append"):
                self._concat_downloaded_track_async(
                    scene, temp_adj_mp4, temp_adj_wav, track, place_mode
                )
                return
            preset = (res.get("audio_choice") or "").strip()
            if preset in ("keep", "replace_speed", "replace_trim", "overlay"):
                audio_choice = preset
            else:
                picked = askchoice(
                    "下载视频替换：音频如何处理？",
                    [
                        ("keep", "保留输入自带音频"),
                        ("replace_speed", "场景音轨替换/SPEED"),
                        ("replace_trim", "场景音轨替换/TRIM"),
                        ("keep_trim", "保留输入自带音频/TRIM"),
                        ("mix", "ZERO混音伸缩"),
                        ("mix_flat", "ZERO混音平铺"),
                    ],
                    self.root,
                )
                if picked is None:
                    return
                _, audio_choice = picked
            self._video_simple_replacement_async(
                scene,
                temp_adj_mp4,
                temp_adj_wav,
                audio_choice,
                track,
                track_status="ORIG",
                share_episode=share_episode,
                mix_volume=float(res.get("mix_volume") or 0.5),
            )
            return

        olda, newa = refresh_scene_media(
            scene,
            track + "_audio",
            ".wav",
            self.workflow.ffmpeg_audio_processor.to_wav(rename),
        )
        vtrack = get_file_path(scene, track)
        if not vtrack:
            vtrack = get_file_path(scene, "clip")
        newv = self.workflow.ffmpeg_processor.add_audio_to_video(vtrack, newa)
        refresh_scene_media(scene, track, ".mp4", newv)
        self.workflow.get_scene_by_index(self.current_scene_index)[track + "_status"] = "ORIG"
        self.refresh_gui_scenes()

    def choose_import_video(self, initial_source: str | None = None, preselect_file: str | None = None) -> None:
        """导入视频。默认先看项目 media/input_video，也可以改到下载、频道或剪贴板。

        ``initial_source`` 预选来源（"project" / "download" / "channel" / "clipboard"）；
        ``preselect_file`` 按文件名预选片段列表里的那一个（如 CLI自动 刚下载的 mp4）。
        """
        project_folder, project_files = self._project_video_source()
        download_folder, download_files = self._download_mp4_source()
        channel_folder, channel_files = self._channel_mp4_source()
        clipboard_folder, clipboard_files = self._clipboard_mp4_source()
        video_actions = [
            ("replace", "替换"),
        ]
        # 声音：原声 = 用导入视频自带的声音；配声 = 用本场现有音频，视频伸缩去配它；
        # 混音 = 本场音频 100% 加上导入视频的声音 66%，视频原速，长裁短定格。
        # 项目、下载、频道三个来源都一样。
        sound_radios = (
            "声音",
            [("keep", "原声"), ("replace_speed", "配声"), ("overlay", "混音")],
            "replace_speed",
        )
        sources = [
            {
                "key": "project",
                "label": "项目",
                "folder": project_folder,
                "choices": project_files,
                "radios": sound_radios,
                "confirm_actions": video_actions,
            },
            {
                "key": "download",
                "label": "下载",
                "folder": download_folder,
                "choices": download_files,
                "radios": sound_radios,
                "confirm_actions": video_actions,
            },
            {
                "key": "channel",
                "label": "频道",
                "folder": channel_folder,
                "choices": channel_files,
                "radios": sound_radios,
                "confirm_actions": [("replace", "替换")],
            },
            {
                "key": "clipboard",
                "label": "剪贴板",
                "folder": clipboard_folder,
                "choices": clipboard_files,
                "radios": sound_radios,
                "confirm_actions": video_actions,
            },
        ]
        pick = askchoice_media_preview(
            "导入视频",
            project_files,
            project_folder,
            self.root,
            use_mp4_video_preview=True,
            build_volume_adjusted_pair=self._build_volume_adjusted_mp4_wav_pair,
            sources=sources,
            audio_sources=self._audio_source_specs(),
            dest_options=list(self._CLIP_DEST_OPTIONS),
            initial_source=initial_source,
            target_clip_length=self._current_clip_length(),
            preselect_file=preselect_file,
        )
        if not pick:
            return
        if isinstance(pick, dict):
            self._apply_editor_pick(pick, stage_download=True)
            return

    def _edit_current_scene_clip(self) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        clip = get_file_path(scene, "clip") if scene else ""
        if not clip or not os.path.isfile(clip):
            messagebox.showinfo("编辑当前片段", "这一场还没有视频。先导入一段。", parent=self.root)
            return
        folder = os.path.dirname(clip)
        name = os.path.basename(clip)
        project_audio_folder, project_audio_files = self._project_audio_source()
        pick = askchoice_media_preview(
            "编辑这一场片段",
            [name],
            folder,
            self.root,
            use_mp4_video_preview=True,
            build_volume_adjusted_pair=self._build_volume_adjusted_mp4_wav_pair,
            audio_sources=[{
                "key": "project",
                "label": "项目",
                "folder": project_audio_folder,
                "choices": project_audio_files,
            }],
            audio_edit=True,
            later_scene_lengths=self._later_scene_lengths(),
        )
        if not isinstance(pick, dict):
            return
        self._apply_editor_pick(pick, stage_download=False)

    def apply_zero_background_media_from_path(
        self,
        source_path: str,
        *,
        mp4_adjusted_path: str | None = None,
        mp4_adjusted_wav_path: str | None = None,
    ) -> bool:
        """与本故事拖放「ZERO 背景」一致：将同一音频或 MP4 写入各场景 ``zero`` / ``zero_audio``。"""
        if not source_path or not os.path.isfile(source_path):
            messagebox.showwarning("提示", "媒体文件不存在", parent=self.root)
            return False
        scene_anchor = self.workflow.get_scene_by_index(self.current_scene_index)
        story_scenes = self.workflow.scenes_in_story(scene_anchor) if scene_anchor else []
        if not story_scenes:
            messagebox.showwarning("提示", "没有当前故事场景", parent=self.root)
            return False

        low = source_path.lower()

        if low.endswith(".mp4"):
            video_src = mp4_adjusted_path or source_path
            wav_src = mp4_adjusted_wav_path
            if not wav_src:
                wav_src = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(video_src, "wav")
            try:
                for scene in story_scenes:
                    refresh_scene_media(scene, "zero_audio", ".wav", wav_src, True)
                    refresh_scene_media(scene, "zero", ".mp4", video_src, True)
                self.workflow.save_scenes_to_json()
                self.refresh_gui_scenes()
                print(f"✅ 已用 MP4 写入本故事各场景 zero/zero_audio（共 {len(story_scenes)} 个场景）")
                return True
            except Exception as e:
                messagebox.showerror("错误", f"写入 ZERO 失败：{e}", parent=self.root)
                return False

        if low.endswith(".mp3"):
            wav_path = self.workflow.ffmpeg_audio_processor.to_wav(source_path)
        elif low.endswith(".wav"):
            wav_path = source_path
        else:
            messagebox.showerror("错误", "仅支持从零导入 MP3 / WAV / MP4", parent=self.root)
            return False

        clip_image_path = get_file_path(scene_anchor, "clip_image")
        if not clip_image_path or not os.path.isfile(clip_image_path):
            clip_image_path = None
            for scene in story_scenes:
                candidate = get_file_path(scene, "clip_image")
                if candidate and os.path.isfile(candidate):
                    clip_image_path = candidate
                    break

        if not clip_image_path:
            messagebox.showwarning(
                "提示",
                "本故事无可用 clip_image，无法由图片+音频生成 ZERO。\n"
                "请先设置 clip_image，或拖入 MP4 作为 ZERO 背景。",
                parent=self.root,
            )
            return False

        try:
            fp = self.workflow.ffmpeg_processor
            new_zero = fp.image_audio_to_video(clip_image_path, wav_path)
            if not new_zero or not os.path.isfile(new_zero):
                raise RuntimeError("由 clip_image + 音频生成 ZERO 视频失败")
            for scene in story_scenes:
                refresh_scene_media(scene, "zero_audio", ".wav", wav_path, True)
                refresh_scene_media(scene, "zero", ".mp4", new_zero, True)
            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()
            print(
                f"✅ 已用 clip_image + 音频生成本故事 zero/zero_audio"
                f"（共 {len(story_scenes)} 个场景）"
            )
            return True
        except Exception as e:
            messagebox.showerror("错误", f"写入 ZERO 失败：{e}", parent=self.root)
            return False
