"""TracksMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.messagebox as messagebox
import os
import threading
import time
import pygame
import config
from project_manager import refresh_scene_media
from gui.picture_in_picture_dialog import PictureInPictureDialog
import cv2
from utility.file_util import get_file_path, show_auto_close_popup
from gui.choice_dialog import askchoice
from gui.workflow.wf_common import STANDARD_FPS


class TracksMixin:
    def _backup_clip_to_scene_back(self, scene):
        """改写主轨前，只记住当前这一条 clip 和 clip_audio。恢復Back 只能退这一步。"""
        clip_path = get_file_path(scene, "clip")
        if not clip_path or not os.path.isfile(clip_path):
            return False
        scene["back"] = clip_path
        # 合并过的这一场又被改了，⏱ 应该先退这一步，之前合并前的备份作废。
        try:
            info = self.workflow.merge_backup_info()
            if info and info.get("kept_id") == scene.get("id"):
                self.workflow.clear_merge_backup()
        except Exception as exc:  # noqa: BLE001
            print(f"清理合并备份失败: {exc}")
        # 新的备份先当成只改这一场；如果是一次动作改了几场，动作结束后由 _link_back_group 重新连起来。
        scene.pop("back_with", None)
        raw_audio = scene.get("clip_audio")
        audio_path = raw_audio.strip() if isinstance(raw_audio, str) else ""
        if not audio_path or not os.path.isfile(audio_path):
            audio_path = get_file_path(scene, "clip_audio") or ""
        if audio_path and os.path.isfile(audio_path):
            scene["back_audio"] = audio_path
        else:
            scene.pop("back_audio", None)
        # 导入视频会连带换掉结束图，一起记下来，恢复时一并退回。
        raw_last = scene.get("clip_image_last")
        last_path = raw_last.strip() if isinstance(raw_last, str) else ""
        if not last_path or not os.path.isfile(last_path):
            last_path = get_file_path(scene, "clip_image_last") or ""
        if last_path and os.path.isfile(last_path):
            scene["back_image_last"] = last_path
        else:
            scene.pop("back_image_last", None)
        return True

    def track_recover(self):
        """把主轨退回上一次改写之前。只退一步，退完就没有更早的版本。"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            messagebox.showwarning("警告", "没有当前场景")
            return
        # 一次动作改了几场（比如把一段挪到旁边那场），这几场要一起恢复。
        linked = []
        own_id = self._scene_id_of(current_scene)
        for other_id in current_scene.get("back_with") or []:
            for other in self.workflow.scenes or []:
                if (
                    isinstance(other, dict)
                    and other is not current_scene
                    and self._scene_id_of(other) == other_id
                    and own_id in (other.get("back_with") or [])
                ):
                    linked.append(other)
                    break
        if not self._restore_scene_back(current_scene):
            if self._restore_merge(current_scene):
                return
            messagebox.showwarning("警告", "没有可恢复的上一步视频")
            return
        restored = 1
        for other in linked:
            if self._restore_scene_back(other):
                restored += 1
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        if restored > 1:
            show_auto_close_popup(self.root, "恢复", f"已把这次动作改过的 {restored} 场一起恢复到之前的视频和声音。")
        else:
            show_auto_close_popup(self.root, "恢复", "已恢复到导入之前的视频和声音。")

    def _restore_merge(self, scene) -> bool:
        """这一场是最近一次合并留下的，就把它换回合并前的两场。"""
        info = self.workflow.merge_backup_info()
        if not info or info.get("kept_id") != scene.get("id"):
            return False
        if not messagebox.askyesno(
            "恢复合并", "把这一场拆回合并之前的两场？", parent=self.root
        ):
            return True
        index = self.workflow.restore_merge_backup(scene)
        if index is None:
            messagebox.showwarning("恢复合并", "合并前的备份已经对不上了，没法恢复。", parent=self.root)
            return True
        self._cancel_scene_debounce_timer()
        self.current_scene_index = index
        self.workflow.save_scenes_to_json()
        self._refresh_gui_scenes_impl()
        show_auto_close_popup(self.root, "恢复合并", "已恢复成合并之前的两场。")
        return True

    def _restore_scene_back(self, scene) -> bool:
        """把一场的主轨退回备份：画面、声音和结束图。没有可恢复的备份返回 False。"""
        back = scene.get("back") or ""
        if not isinstance(back, str):
            back = ""
        back_path = ""
        for part in back.split(","):
            part = part.strip()
            if part and os.path.isfile(part):
                back_path = part
                break
        if not back_path:
            return False

        audio_path = scene.get("back_audio") or ""
        if not isinstance(audio_path, str):
            audio_path = ""
        audio_path = audio_path.strip()
        if audio_path and not os.path.isfile(audio_path):
            audio_path = ""

        refresh_scene_media(scene, "clip", ".mp4", back_path)
        if audio_path:
            refresh_scene_media(scene, "clip_audio", ".wav", audio_path, True)
        last_path = scene.get("back_image_last") or ""
        if isinstance(last_path, str) and last_path.strip() and os.path.isfile(last_path.strip()):
            last_path = last_path.strip()
            refresh_scene_media(
                scene, "clip_image_last", os.path.splitext(last_path)[1] or ".webp", last_path, True
            )
        scene.pop("back", None)
        scene.pop("back_audio", None)
        scene.pop("back_image_last", None)
        scene.pop("back_with", None)
        return True

    def reset_track_offset(self):
        """重置轨道偏移量到当前场景的起始位置"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            self.secondary_track_offset = 0.0
            self.secondary_track_paused_time = None
            if hasattr(self, 'secondary_track_scale_var'):
                self.secondary_track_scale_var.set(0.0)
            self.update_secondary_track_time()
            return
        
        if self.selected_secondary_track == "narration":
            self.secondary_track_offset = 0.0
        else:
            self.secondary_track_offset, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scene_detail(current_scene)
            track_path = get_file_path(current_scene, self.selected_secondary_track)
            if track_path:
                track_duration = self.workflow.ffmpeg_processor.get_duration(track_path)
                if self.secondary_track_offset > track_duration:
                    self.secondary_track_offset = 0.0
            else:
                self.secondary_track_offset = 0.0

        self.secondary_track_paused_time = None
        # 更新滑块值
        if hasattr(self, 'secondary_track_scale_var'):
            self.secondary_track_scale_var.set(self.secondary_track_offset)
        
        # 更新canvas显示（显示新场景对应位置的帧）
        if hasattr(self, 'display_secondary_track_frame_at_time'):
            self.display_secondary_track_frame_at_time(self.secondary_track_offset)
        
        self.update_secondary_track_time()

    def choose_secondary_track(self, track_id):
        """选择旁白轨道并重置播放状态"""
        self.video_frame.config(text=f"预览 - secondary ({track_id})")
        self.selected_secondary_track = track_id
        # 重置播放偏移量到当前场景的起始位置
        self.reset_track_offset()
        # 切换 tab 并加载第一帧
        self.on_secondary_track_tab_changed()

    def _build_volume_adjusted_mp4_wav_pair(
        self,
        src_mp4: str,
        volume: float,
        *,
        start: float = 0.0,
        end: float | None = None,
        speed: float = 1.0,
    ):
        """按区间裁剪、变速。音量增益不是 1 时才改音量。"""
        wf = self.workflow
        if not wf:
            raise RuntimeError("工作流未就绪")
        ap = wf.ffmpeg_audio_processor
        fp = wf.ffmpeg_processor
        dur = float(fp.get_duration(src_mp4) or 0.0)
        st = max(0.0, float(start or 0.0))
        en = float(end if end is not None else dur)
        if en <= 0 or en > dur:
            en = dur
        spd = round(float(speed or 1.0), 3)
        vol = float(volume or 1.0)

        mp4_out = fp.trim_video(src_mp4, st, en, volume=1.0, speed=spd)
        if not mp4_out or not os.path.isfile(mp4_out):
            raise RuntimeError("裁剪/变速失败")

        raw = ap.extract_audio_from_video(mp4_out)
        if abs(vol - 1.0) < 0.001:
            if raw:
                return mp4_out, raw
            seg_len = fp.get_duration(mp4_out) or 0.0
            wav_out = ap.make_silence(seg_len) if seg_len > 0 else None
            if not wav_out:
                raise RuntimeError("无法生成临时 wav")
            return mp4_out, wav_out

        if raw:
            raw_len = ap.get_duration(raw)
            if raw_len is None:
                raw_len = fp.get_duration(mp4_out) or 0.0
            wav_out = ap.audio_cut_fade(raw, 0, raw_len, 0, 0, volume=vol)
        else:
            seg_len = fp.get_duration(mp4_out) or 0.0
            wav_out = ap.make_silence(seg_len) if seg_len > 0 else None
        if not wav_out:
            raise RuntimeError("无法生成增益后的临时 wav")
        muxed = fp.add_audio_to_video(mp4_out, wav_out)
        if not muxed or not os.path.isfile(muxed):
            raise RuntimeError("无法生成增益后的临时 mp4")
        return muxed, wav_out

    def _video_simple_replacement_async(
        self,
        scene,
        tmp_mp4,
        tmp_wav,
        audio_choice,
        track,
        *,
        track_status: str,
        share_episode: bool | None = None,
        mix_volume: float = 0.5,
        on_done=None,
    ):
        """在后台线程执行 ``video_simple_replacement``（内含 resize、混音等密集 FFmpeg），避免主界面假死。"""
        if share_episode is None:
            share_episode = track == "zero"

        def work():
            err = None
            try:
                self.media_scanner.video_simple_replacement(
                    scene, tmp_mp4, tmp_wav, audio_choice, track, mix_volume=mix_volume
                )
            except Exception as e:
                err = str(e)

            def done():
                try:
                    self.root.config(cursor="")
                except tk.TclError:
                    pass
                if err:
                    if on_done:  # t179u: 全集提交自动导入：不弹窗，交回调
                        on_done(False, f"替换失败：{err}")
                        return
                    messagebox.showerror("错误", f"视频处理失败：{err}", parent=self.root)
                else:
                    scene[track + "_status"] = track_status
                    if track == "zero" and share_episode:
                        self._share_zero_across_episode(scene)
                    self.workflow.save_scenes_to_json()
                    self.refresh_gui_scenes()
                    if track == "zero" and share_episode:
                        n = len(self.workflow.scenes_in_story(scene) or [])
                        show_auto_close_popup(self.root, "Zero", f"已写入这一集的 {n} 个场景。")
                    elif track == "zero":
                        show_auto_close_popup(self.root, "Zero", "已写入这一场的 Zero。")
                    if on_done:
                        on_done(True, "")

            try:
                self.root.after(0, done)
            except tk.TclError:
                pass

        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
        except tk.TclError:
            pass
        threading.Thread(target=work, daemon=True).start()

    def _concat_downloaded_track_async(self, scene, tmp_mp4, tmp_wav, track, where: str):
        """把下载的视频和声音接到当前音轨前面或后面。"""

        def work():
            err = None
            try:
                self._concat_downloaded_track(scene, tmp_mp4, tmp_wav, track, where)
            except Exception as e:
                err = str(e)

            def done():
                try:
                    self.root.config(cursor="")
                except tk.TclError:
                    pass
                if err:
                    messagebox.showerror("错误", f"接上失败：{err}", parent=self.root)
                else:
                    scene[track + "_status"] = "ORIG"
                    self.workflow.save_scenes_to_json()
                    self.refresh_gui_scenes()
                    show_auto_close_popup(
                        self.root,
                        "放入",
                        "已接到前面。" if where == "prepend" else "已接到后面。",
                    )

            try:
                self.root.after(0, done)
            except tk.TclError:
                pass

        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
        except tk.TclError:
            pass
        threading.Thread(target=work, daemon=True).start()

    def _concat_downloaded_track(self, scene, tmp_mp4, tmp_wav, track, where: str) -> None:
        fp = self.workflow.ffmpeg_processor
        ap = self.workflow.ffmpeg_audio_processor
        new_video = fp.resize_video(tmp_mp4, width=None, height=fp.height)
        if not new_video or not os.path.isfile(new_video):
            raise RuntimeError("新视频没有准备好")
        new_audio = tmp_wav if tmp_wav and os.path.isfile(tmp_wav) else ap.extract_audio_from_video(new_video)
        if not new_audio or not os.path.isfile(new_audio):
            raise RuntimeError("新视频里没有声音")
        old_video = get_file_path(scene, track)
        old_audio = get_file_path(scene, track + "_audio")
        if not old_video or not os.path.isfile(old_video):
            refresh_scene_media(scene, track + "_audio", ".wav", new_audio, True)
            refresh_scene_media(scene, track, ".mp4", new_video, True)
            return
        if not old_audio or not os.path.isfile(old_audio):
            old_audio = ap.extract_audio_from_video(old_video)
        if not old_audio or not os.path.isfile(old_audio):
            raise RuntimeError("当前这一段没有声音可以接")
        ow, oh = fp.get_resolution(old_video)
        if ow and oh and (ow != fp.width or oh != fp.height):
            fitted = fp.resize_video(old_video, width=fp.width, height=fp.height)
            if fitted and os.path.isfile(fitted):
                old_video = fitted
        if where == "prepend":
            videos = [new_video, old_video]
            audios = [new_audio, old_audio]
        else:
            videos = [old_video, new_video]
            audios = [old_audio, new_audio]
        merged_audio = ap.concat_audios(audios)
        merged_video = fp.concat_videos(videos, False)
        if not merged_audio or not merged_video:
            raise RuntimeError("没有接成一条")
        muxed = fp.add_audio_to_video(merged_video, merged_audio)
        if not muxed or not os.path.isfile(muxed):
            raise RuntimeError("声音没有回到画面上")
        if track == "clip":
            self._backup_clip_to_scene_back(scene)
        refresh_scene_media(scene, track + "_audio", ".wav", merged_audio, True)
        refresh_scene_media(scene, track, ".mp4", muxed, True)
        if track == "clip" and where == "prepend":
            added = float(fp.get_duration(new_video) or 0.0)
            if added > 0.05:
                record = self._timing_record(scene)
                if record is not None:
                    shifted = []
                    for item in record["sections"]:
                        if not isinstance(item, dict):
                            continue
                        row = dict(item)
                        for edge in ("start", "end"):
                            raw = row.get(edge)
                            if raw is None or raw == "":
                                continue
                            try:
                                row[edge] = round(float(raw) + added, 2)
                            except (TypeError, ValueError):
                                pass
                        shifted.append(row)
                    self._store_timing(scene, shifted, record.get("text") or "")

    def _clip_overlay_ffmpeg_batch_async(
        self,
        target_scenes,
        overlay_path,
        opts,
        dialog_title,
        failure_verb,
        apply_overlay,
        on_scene_ok=None,
        on_done=None,
    ):
        """对多个场景的 clip 依次调用 FFmpeg 叠加顶标/水印；在后台线程执行，避免界面假死。"""

        def work():
            fp = self.workflow.ffmpeg_processor
            failed = []
            for scene in target_scenes:
                oldv = get_file_path(scene, "clip")
                if not oldv or not os.path.isfile(oldv):
                    failed.append(f"场景 id={scene.get('id', '?')}: 无有效 clip 视频")
                    continue
                prior_back = scene.get("back")
                prior_back = prior_back.strip() if isinstance(prior_back, str) else ""
                prior_audio = scene.get("back_audio")
                prior_audio = prior_audio.strip() if isinstance(prior_audio, str) else ""
                self._backup_clip_to_scene_back(scene)
                oldv_ref, newv = refresh_scene_media(scene, "clip", ".mp4")
                temp_out = config.get_temp_file(self.workflow.pid, "mp4")
                moved = False
                try:
                    ok = apply_overlay(fp, oldv_ref, temp_out, overlay_path, opts)
                    if not ok or not os.path.isfile(temp_out) or os.path.getsize(temp_out) < 1000:
                        scene["clip"] = oldv_ref
                        if prior_back:
                            scene["back"] = prior_back
                        else:
                            scene.pop("back", None)
                        if prior_audio:
                            scene["back_audio"] = prior_audio
                        else:
                            scene.pop("back_audio", None)
                        failed.append(f"场景 id={scene.get('id', '?')}: {failure_verb}")
                        continue
                    os.replace(temp_out, newv)
                    moved = True
                    if on_scene_ok is not None:
                        on_scene_ok(scene, oldv_ref, newv)
                except Exception as e:
                    scene["clip"] = oldv_ref
                    if prior_back:
                        scene["back"] = prior_back
                    else:
                        scene.pop("back", None)
                    if prior_audio:
                        scene["back_audio"] = prior_audio
                    else:
                        scene.pop("back_audio", None)
                    failed.append(f"场景 id={scene.get('id', '?')}: {e}")
                finally:
                    if not moved and os.path.isfile(temp_out):
                        try:
                            os.remove(temp_out)
                        except OSError:
                            pass

            def done():
                try:
                    self.root.config(cursor="")
                except tk.TclError:
                    pass
                self.workflow.save_scenes_to_json()
                self.refresh_gui_scenes()
                if failed:
                    messagebox.showwarning(
                        dialog_title,
                        "部分场景未处理：\n" + "\n".join(failed[:12]),
                        parent=self.root,
                    )
                if on_done is not None:
                    on_done(failed)

            try:
                self.root.after(0, done)
            except tk.TclError:
                pass

        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
        except tk.TclError:
            pass
        threading.Thread(target=work, daemon=True).start()

    def remove_secondary_track(self):
        """删除当前选中的旁白轨道（视频+音频）"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            return
        track = self.selected_secondary_track
        track_path = get_file_path(current_scene, track)
        if not track_path:
            messagebox.showinfo("提示", f"当前场景的 {track} 轨道没有内容，无需删除")
            return
        track_label = {"narration": "旁白(NN)", "zero": "ZZ"}.get(track, track)
        if not messagebox.askyesno("确认删除", f"确定要删除当前 {track_label} 轨道的视频和音频吗？"):
            return
        for key in [track, track + '_audio', track + '_left', track + '_right', track + '_image', track + '_fps']:
            current_scene.pop(key, None)
        if hasattr(self, 'workflow') and self.workflow:
            self.workflow.save_scenes_to_json()
        self.secondary_track_offset = 0.0
        self.secondary_track_paused_time = None
        if hasattr(self, 'secondary_track_scale_var'):
            self.secondary_track_scale_var.set(0.0)
        self.secondary_track_canvas.delete("all")
        self.secondary_track_canvas.create_text(160, 90, text="旁白轨道视频预览\n选择视频后播放显示",
                                               fill='white', font=('Arial', 12), justify=tk.CENTER, tags="hint")
        if hasattr(self, 'secondary_track_scale'):
            self.secondary_track_scale.config(state=tk.DISABLED)
        self.update_secondary_track_time()
        self._update_remove_track_btn_state()

    def _update_remove_track_btn_state(self):
        """根据当前场景是否有轨道内容，启用/禁用删除按钮"""
        try:
            if not hasattr(self, 'remove_track_btn'):
                return
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            track_path = get_file_path(current_scene, self.selected_secondary_track) if current_scene else None
            self.remove_track_btn.config(state=tk.NORMAL if track_path else tk.DISABLED)
        except Exception:
            pass

    def pip_secondary_track(self):
        """将旁白轨道作为画中画叠加到主轨道视频上"""
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            secondary_path = get_file_path(current_scene, self.selected_secondary_track)
            secondary_audio = get_file_path(current_scene, self.selected_secondary_track+'_audio')
            secondary_left = get_file_path(current_scene, self.selected_secondary_track+'_left')
            secondary_right = get_file_path(current_scene, self.selected_secondary_track+'_right')
            if not secondary_path or not secondary_audio:
                messagebox.showwarning("警告", "第二轨道视频文件不存在")
                return

            #start_time, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scene_detail(current_scene)
            if self.secondary_track_paused_time:
                start_time = self.secondary_track_paused_time
            else:
                start_time = self.secondary_track_offset

            # popup to ask user to select background source ? 
            # if is clip_image or clip_image_last, then generate background video from clip_image or clip_image_last + narration_audio
            # if is clip, then use clip_audio
            _bg = askchoice("选择背景来源", ["clip", "clip_image", "clip_image_last"], self.root)
            if _bg is None:
                return
            _, background_source = _bg
            if background_source == "clip":
                target_video_track = "clip"  
                background_audio = get_file_path(current_scene, "clip_audio")
                background_video = get_file_path(current_scene, "clip")
            elif background_source == "clip_image":
                target_video_track = "narration"
            elif background_source == "clip_image_last":
                target_video_track = "narration"
                image = get_file_path(current_scene, 'clip_image_last')
                background_audio = get_file_path(current_scene, "narration_audio")
                if not background_audio or not os.path.exists(background_audio):
                    messagebox.showwarning("警告", "场景中没有 narration_audio")
                    return
                background_video = self.workflow.ffmpeg_processor.image_audio_to_video(image, background_audio, 1)
            else:
                return

            audio_duration = self.workflow.ffmpeg_processor.get_duration(background_audio)

            secondary_track_copy = self.workflow.ffmpeg_processor.trim_video(secondary_path, start_time, start_time+audio_duration)
            secondary_audio_copy = self.workflow.ffmpeg_audio_processor.audio_cut_fade(secondary_audio, start_time, audio_duration, 0, 0, 1.0)
            print(f"📺 打开画中画设置对话框...")
            
            # 创建画中画设置对话框
            pip_dialog = PictureInPictureDialog(self.root, background_video, secondary_track_copy, secondary_left, secondary_right)
            
            # 等待对话框关闭
            self.root.wait_window(pip_dialog.dialog)

            # 检查用户的选择
            if pip_dialog.result:
                settings = pip_dialog.result
                print(f"📺 用户选择的画中画设置: {settings}")

                if target_video_track == "clip":
                    self._backup_clip_to_scene_back(current_scene)

                if settings['position'] == "full":
                    v = self.workflow.ffmpeg_processor.add_audio_to_video(secondary_track_copy, background_audio)
                    refresh_scene_media(current_scene, target_video_track, '.mp4', v)
                elif settings['position'] == "av":
                    refresh_scene_media(current_scene, target_video_track, '.mp4', secondary_track_copy)
                    refresh_scene_media(current_scene, target_video_track+'_audio', '.wav', secondary_audio_copy)
                else:
                    # 处理画中画
                    self.process_picture_in_picture(
                        background_audio=background_audio,
                        background_video=background_video,
                        overlay_video=secondary_track_copy,
                        overlay_audio=secondary_audio_copy,
                        overlay_left=secondary_left,
                        overlay_right=secondary_right,
                        settings=settings,
                        output_track=target_video_track
                    )

                # 更新显示
                self.workflow.save_scenes_to_json()
                self.refresh_gui_scenes()
                messagebox.showinfo("成功", f"画中画处理完成")

            else:
                print("🚫 用户取消了画中画设置")
                
        except Exception as e:
            error_msg = f"画中画处理失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)

    def process_picture_in_picture(self, background_video, background_audio, overlay_video, overlay_audio, overlay_left, overlay_right, settings, output_track="clip"):
        """处理画中画视频生成。output_track: 输出到 clip 或 narration"""
        try:
            print(f"🎬 开始处理画中画...")
            if not self.video_cap:
                current_time = 0
            else:
                current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
                current_time = current_frame / STANDARD_FPS

            left_video = None
            right_video = None
            if settings['position'] == "left" and overlay_left:
                left_video = overlay_left
            elif settings['position'] == "right" and overlay_right:
                right_video = overlay_right
            elif settings['position'] == "center" and overlay_left and overlay_right:
                left_video = overlay_left
                right_video = overlay_right

            if left_video or right_video:
                #    background_audio=background_audio,
                output_video = self.workflow.ffmpeg_processor.add_left_right_picture_in_picture(
                                    background_video=background_video,
                                    overlay_video_left=left_video,
                                    overlay_video_right=right_video,
                                    ratio=settings['ratio'],
                                    delay_time=settings.get('delay_time', 0),
                                    edge_blur=0
                                )
            else:
                output_video = self.workflow.ffmpeg_processor.add_picture_in_picture(
                    background_video=background_video,
                    slide_in_video=overlay_video,
                    start_time=current_time,
                    ratio=settings['ratio'],
                    transition_duration=settings['transition_duration'],
                    position=settings['position'],
                    mask=settings['shape']
                )

            print(f"✅ 画中画处理完成: {output_video}")

            audio_field = output_track + "_audio"
            olda, output_audio = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), audio_field, ".wav", background_audio, True)
            output_video = self.workflow.ffmpeg_processor.add_audio_to_video(output_video, background_audio)
            olda, output_video = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), output_track, ".mp4", output_video, True)
            return output_video, output_audio

        except Exception as e:
            error_msg = f"画中画处理失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)
            return None, None

    def load_secondary_track_first_frame(self):
        """加载旁白轨道视频的第一帧到画布（从当前偏移位置）"""
        if not self.workflow:
            return
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            return
            
        track_path = get_file_path(current_scene, self.selected_secondary_track)

        try:
            self.secondary_track_canvas.delete("all")

            if not track_path:
                # 清除画布显示提示信息
                self.secondary_track_canvas.create_text(160, 90, text="旁白轨道视频预览\n选择视频后播放显示",
                                                   fill='white', font=('Arial', 12), 
                                                   justify=tk.CENTER, tags="hint")
                self.track_time_label.config(text="00:00/00:00")
                # 禁用滑块
                if hasattr(self, 'secondary_track_scale'):
                    self.secondary_track_scale.config(state=tk.DISABLED)
                self._update_remove_track_btn_state()
                return
            
            # 打开视频文件
            temp_cap = cv2.VideoCapture(track_path)
            if not temp_cap.isOpened():
                print(f"❌ 无法打开旁白轨道视频文件: {track_path}")
                return
            
            # 计算应该显示的帧位置（基于 offset + delta）
            temp_cap.set(cv2.CAP_PROP_POS_FRAMES, int(self.secondary_track_offset * STANDARD_FPS))
            
            ret, frame = temp_cap.read()
            if ret:
                # 显示第一帧到Canvas
                from PIL import Image, ImageTk
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                
                # 调整图像大小适应Canvas
                canvas_width = self.secondary_track_canvas.winfo_width()
                canvas_height = self.secondary_track_canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:
                    pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
                else:
                    pil_image.thumbnail((310, 170), Image.Resampling.LANCZOS)
                
                # 更新画布显示第一帧
                self.current_secondary_track_frame = ImageTk.PhotoImage(pil_image)
                
                canvas_width = canvas_width or 320
                canvas_height = canvas_height or 180
                x = canvas_width // 2
                y = canvas_height // 2
                self.secondary_track_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_secondary_track_frame)
                
            # 更新时间显示
            total_frames = temp_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_duration = total_frames / STANDARD_FPS
            total_str = f"{int(total_duration // 60):02d}:{int(total_duration % 60):02d}"
            
            # 显示当前偏移位置和总时长
            current_str = f"{int(self.secondary_track_offset // 60):02d}:{int(self.secondary_track_offset % 60):02d}"
            self.track_time_label.config(text=f"{current_str}/{total_str}")
            
            # 更新滑块的最大值和当前值
            if hasattr(self, 'secondary_track_scale'):
                self.secondary_track_scale.config(to=total_duration, state=tk.NORMAL)
                if self.secondary_track_paused_time is not None:
                    self.secondary_track_scale_var.set(self.secondary_track_paused_time)
                else:
                    self.secondary_track_scale_var.set(self.secondary_track_offset)
            
            temp_cap.release()
            self._update_remove_track_btn_state()

        except Exception as e:
            print(f"❌ 加载旁白轨道视频第一帧失败: {e}")
            self.secondary_track_canvas.delete("all")
            self.secondary_track_canvas.create_text(160, 90, text="旁白轨道视频预览\n选择视频后播放显示",
                                               fill='white', font=('Arial', 12), 
                                               justify=tk.CENTER, tags="hint")
            self._update_remove_track_btn_state()

    def toggle_track_playback(self):
        # 检查当前选中的tab
        current_tab_index = self.narration_notebook.index(self.narration_notebook.select())

        if current_tab_index == 1:
            if self.pip_lr_playing:
                self.pause_pip_lr() 
            else:
                self.play_pip_lr()
        else:
            if self.secondary_track_playing:
                self.pause_secondary_track()
            else:
                self.play_secondary_track()

    def play_secondary_track(self):
        """播放旁白轨道视频的当前场景时间段（支持从暂停状态和偏移位置恢复）"""
        narration_video_path = get_file_path(self.workflow.get_scene_by_index(self.current_scene_index), self.selected_secondary_track)
        narration_audio_path = get_file_path(self.workflow.get_scene_by_index(self.current_scene_index), self.selected_secondary_track+'_audio')
        try:
            if self.secondary_track_cap and self.secondary_track_paused_time:  #is_resuming
                play_start_time = self.secondary_track_paused_time
                # === 从暂停状态恢复（但没有设置偏移） ===
                # 计算播放起始时间
                if self.selected_secondary_track == "narration":
                    self.secondary_track_start_time = time.time() - play_start_time
                else:
                    self.secondary_track_start_time = time.time() - (play_start_time - self.secondary_track_offset)
                self.secondary_track_playing = True
                self.track_play_button.config(text="⏸")
                self.secondary_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(self.secondary_track_paused_time * STANDARD_FPS))
                
                # 从暂停位置重新加载并播放音频（确保音视频同步）
                self.play_secondary_track_audio(narration_audio_path, play_start_time)
                print(f"▶ 从暂停位置恢复播放: {play_start_time:.2f}秒")
                
            else:
                if self.secondary_track_cap:
                    self.secondary_track_cap.release()
                self.secondary_track_cap = cv2.VideoCapture(narration_video_path)
                if not self.secondary_track_cap.isOpened():
                    return

                # 优先使用滑块设置的暂停时间，否则使用offset
                if self.secondary_track_paused_time is not None:
                    start_position = self.secondary_track_paused_time
                    # 保存暂停时间用于音频播放，然后清除（因为现在开始播放了）
                    saved_paused_time = self.secondary_track_paused_time
                    self.secondary_track_paused_time = None
                else:
                    start_position = self.secondary_track_offset
                    saved_paused_time = None
                
                self.secondary_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_position * STANDARD_FPS))
                
                self.secondary_track_playing = True
                self.track_play_button.config(text="⏸")
                
                # 计算播放起始时间
                if self.selected_secondary_track == "narration":
                    self.secondary_track_start_time = time.time() - start_position
                else:
                    self.secondary_track_start_time = time.time() - (start_position - self.secondary_track_offset)
                
                # 传递正确的起始位置给音频播放
                self.play_secondary_track_audio(narration_audio_path, saved_paused_time if saved_paused_time is not None else start_position)
            
            # === 通用处理 - 开始播放循环
            self.play_secondary_track_frame()
            
            # 更新时间显示
            self.update_secondary_track_time()
            
        except Exception as e:
            print(f"❌ 播放旁白轨道视频失败: {e}")

    def play_secondary_track_audio(self, audio_path, audio_start_offset=None):
        """播放旁白轨道音频（支持从偏移位置开始）"""
        try:
            # 初始化pygame mixer（如果还没有初始化）
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # 停止任何正在播放的音频
            pygame.mixer.music.stop()
            
            # 加载音频文件
            pygame.mixer.music.load(audio_path)
            
            # 确定音频开始播放的偏移时间
            if audio_start_offset is None:
                if self.secondary_track_paused_time:
                    audio_start_offset = self.secondary_track_paused_time
                else:
                    if self.selected_secondary_track == "narration":
                        audio_start_offset = 0.0
                    else:    
                        audio_start_offset = self.secondary_track_offset
                    if audio_start_offset < 0:
                        audio_start_offset = 0
            
            try:
                if audio_start_offset > 0:
                    pygame.mixer.music.play(start=audio_start_offset)
                else:
                    pygame.mixer.music.play()
            except TypeError:
                print("⚠️ 当前pygame版本不支持从指定位置播放音频，将从头播放")
                pygame.mixer.music.play()
            
            # 设置音频播放状态
            self.secondary_track_audio_playing = True
            
        except Exception as e:
            print(f"❌ 播放旁白轨道音频失败: {e}")

    def stop_secondary_track_audio(self):
        """停止旁白轨道音频播放"""
        try:
            if self.secondary_track_audio_playing:
                pygame.mixer.music.stop()
                self.secondary_track_audio_playing = False
                self.secondary_track_audio_start_time = None
                print(f"⏹ 旁白轨道音频播放停止")
        except Exception as e:
            print(f"❌ 停止旁白轨道音频失败: {e}")

    def play_secondary_track_frame(self):
        """播放旁白轨道视频的下一帧（带同步机制）"""
        if not self.secondary_track_playing or not self.secondary_track_cap:
            return
            
        try:
            # 检查音频是否还在播放
            audio_is_playing = pygame.mixer.music.get_busy()
            if not audio_is_playing:
                # 音频播放完毕，停止视频
                self.stop_secondary_track()
                print("✅ 旁白轨道音频播放完毕，视频同步停止")
                return
            
            if self.secondary_track_start_time:
                # 计算实际经过的时间
                if self.selected_secondary_track == "narration":
                    current_time = (time.time() - self.secondary_track_start_time)
                else:    
                    current_time = (time.time() - self.secondary_track_start_time) + self.secondary_track_offset
                
                # 计算应该在第几帧
                target_frame = int(current_time * STANDARD_FPS)
                current_frame = int(self.secondary_track_cap.get(cv2.CAP_PROP_POS_FRAMES))
                
                # 如果视频帧落后于音频进度，跳帧追赶
                if target_frame > current_frame + 2:  # 允许2帧的容错
                    self.secondary_track_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                
                # 检查是否超过了视频结束时间
                duration = self.workflow.ffmpeg_audio_processor.get_duration( self.workflow.get_scene_by_index(self.current_scene_index)[self.selected_secondary_track] )
                if current_time >= duration:
                    self.stop_secondary_track()
                    return
            
            ret, frame = self.secondary_track_cap.read()
            if not ret:
                # 视频结束，停止播放
                self.stop_secondary_track()
                return
            
            # 显示视频帧到Canvas
            from PIL import Image, ImageTk
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # 调整图像大小适应Canvas
            canvas_width = self.secondary_track_canvas.winfo_width()
            canvas_height = self.secondary_track_canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
            else:
                pil_image.thumbnail((310, 170), Image.Resampling.LANCZOS)
            
            # 更新画布
            self.current_secondary_track_frame = ImageTk.PhotoImage(pil_image)
            self.secondary_track_canvas.delete("all")
            
            canvas_width = canvas_width or 320
            canvas_height = canvas_height or 180
            x = canvas_width // 2
            y = canvas_height // 2
            self.secondary_track_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_secondary_track_frame)
            
            # 更新时间显示
            self.update_secondary_track_time()
            
            # 安排下一帧播放
            delay = max(1, int(1000 / STANDARD_FPS))  # 毫秒
            self.secondary_track_after_id = self.root.after(delay, self.play_secondary_track_frame)
            
        except Exception as e:
            print(f"❌ 播放旁白轨道视频帧失败: {e}")
            self.stop_secondary_track()

    def pause_secondary_track(self):
        if not self.secondary_track_playing:
            return

        """暂停旁白轨道视频播放"""
        self.secondary_track_playing = False
        self.track_play_button.config(text="▶")
        
        # 计算并保存当前播放偏移时间（关键！与新的同步机制兼容）
        if self.secondary_track_start_time:
            if self.selected_secondary_track == "narration":
                self.secondary_track_paused_time = (time.time() - self.secondary_track_start_time)
            else:    
                self.secondary_track_paused_time = (time.time() - self.secondary_track_start_time) + self.secondary_track_offset
        
        # 暂停音频播放
        try:
            pygame.mixer.music.pause()
            print("⏸ 旁白轨道音频已暂停")
        except Exception as e:
            print(f"❌ 暂停旁白轨道音频失败: {e}")
        
        if self.secondary_track_after_id:
            self.root.after_cancel(self.secondary_track_after_id)
            self.secondary_track_after_id = None
            
        # 更新时间显示
        self.update_secondary_track_time()

    def stop_secondary_track(self):
        """停止旁白轨道视频播放"""
        self.secondary_track_playing = False
        self.track_play_button.config(text="▶")
        
        # 停止音频播放
        self.stop_secondary_track_audio()
        
        if self.secondary_track_after_id:
            self.root.after_cancel(self.secondary_track_after_id)
            self.secondary_track_after_id = None
            
        if self.secondary_track_cap:
            self.secondary_track_cap.release()
            self.secondary_track_cap = None
            
        # 清除所有状态变量
        self.secondary_track_paused_time = None
        self.secondary_track_start_time = None
        self.reset_track_offset()
        
        print("⏹ 清除旁白轨道所有状态")
            
        self.secondary_track_canvas.delete("all")
        self.secondary_track_canvas.create_text(160, 90, text="旁白轨道视频预览\n选择视频后播放显示", 
                                            fill="gray", font=("Arial", 10), justify=tk.CENTER, tags="hint")
        
        # 更新时间显示
        self.update_secondary_track_time()

    def play_pip_lr(self):
        """同步播放 narration_left 和 narration_right 视频（支持从暂停恢复）"""
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not current_scene:
                return
            
            # 获取视频路径
            left_path = current_scene.get('narration_left')
            right_path = current_scene.get('narration_right')
            audio_path = current_scene.get('clip_audio')
            
            if not left_path or not right_path:
                messagebox.showwarning("提示", "当前场景没有 narration_left 或 narration_right 视频")
                return
            
            if not os.path.exists(left_path) or not os.path.exists(right_path):
                messagebox.showerror("错误", "视频文件不存在")
                return
            
            # 检查是否是从暂停状态恢复
            is_resuming = (self.pip_left_cap and hasattr(self, 'pip_lr_paused_time') and self.pip_lr_paused_time is not None)
            
            if is_resuming:
                # 从暂停恢复
                self.pip_lr_playing = True
                self.pip_lr_start_time = time.time() - self.pip_lr_paused_time
                self.track_play_button.config(text="⏸")
                
                # 恢复音频播放
                if audio_path and os.path.exists(audio_path):
                    try:
                        pygame.mixer.music.unpause()
                        print(f"▶️ 从暂停位置 {self.pip_lr_paused_time:.1f}s 恢复播放 PIP L/R")
                    except:
                        pass
                
                # 清除暂停标记
                self.pip_lr_paused_time = None
                
                # 继续播放
                self.play_pip_lr_frame()
                
            else:
                # 全新开始播放
                # 打开视频文件
                self.pip_left_cap = cv2.VideoCapture(left_path)
                self.pip_right_cap = cv2.VideoCapture(right_path)
                
                if not self.pip_left_cap.isOpened() or not self.pip_right_cap.isOpened():
                    messagebox.showerror("错误", "无法打开视频文件")
                    return
                
                # 播放音频
                if audio_path and os.path.exists(audio_path):
                    try:
                        pygame.mixer.music.load(audio_path)
                        pygame.mixer.music.set_volume(1.0)
                        pygame.mixer.music.play()
                        print(f"🔊 播放音频: {audio_path}")
                    except Exception as e:
                        print(f"❌ 播放音频失败: {e}")
                
                # 设置播放状态
                self.pip_lr_playing = True
                self.pip_lr_start_time = time.time()
                self.pip_lr_paused_time = None
                self.track_play_button.config(text="⏸")
                
                # 开始播放帧
                self.play_pip_lr_frame()
                
                print("▶️ 开始播放 PIP L/R 视频")
            
        except Exception as e:
            print(f"❌ 播放 PIP L/R 失败: {e}")
            self.stop_pip_lr()

    def play_pip_lr_frame(self):
        """播放 PIP L/R 的下一帧（带音视频同步机制）"""
        try:
            if not self.pip_lr_playing:
                return
            
            if not self.pip_left_cap or not self.pip_right_cap:
                self.stop_pip_lr()
                return
            
            # 检查音频是否还在播放
            try:
                audio_is_playing = pygame.mixer.music.get_busy()
                if not audio_is_playing:
                    # 音频播放完毕，停止视频
                    self.stop_pip_lr()
                    print("✅ PIP L/R 音频播放完毕，视频同步停止")
                    return
            except:
                pass
            
            # 计算应该播放的帧位置以保持与音频同步
            if hasattr(self, 'pip_lr_start_time') and self.pip_lr_start_time:
                # 计算实际经过的时间
                elapsed_time = time.time() - self.pip_lr_start_time
                
                # 计算应该在第几帧
                target_frame = int(elapsed_time * STANDARD_FPS)
                current_frame_left = int(self.pip_left_cap.get(cv2.CAP_PROP_POS_FRAMES))
                current_frame_right = int(self.pip_right_cap.get(cv2.CAP_PROP_POS_FRAMES))
                
                # 如果视频帧落后于音频进度，跳帧追赶（允许2帧的容错）
                if target_frame > current_frame_left + 2:
                    self.pip_left_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                
                if target_frame > current_frame_right + 2:
                    self.pip_right_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            
            # 读取左右视频帧
            ret_left, frame_left = self.pip_left_cap.read()
            ret_right, frame_right = self.pip_right_cap.read()
            
            if not ret_left or not ret_right:
                # 视频结束
                self.stop_pip_lr()
                return
            
            # 显示左侧视频
            self.display_pip_frame(frame_left, self.pip_left_canvas)
            
            # 显示右侧视频
            self.display_pip_frame(frame_right, self.pip_right_canvas)
            
            # 更新时间显示
            elapsed = time.time() - self.pip_lr_start_time
            total_frames_left = self.pip_left_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_duration = total_frames_left / STANDARD_FPS
            
            current_str = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
            total_str = f"{int(total_duration // 60):02d}:{int(total_duration % 60):02d}"
            self.track_time_label.config(text=f"{current_str}/{total_str}")
            
            # 安排下一帧
            delay = max(1, int(1000 / STANDARD_FPS))
            self.pip_lr_after_id = self.root.after(delay, self.play_pip_lr_frame)
            
        except Exception as e:
            print(f"❌ 播放 PIP L/R 帧失败: {e}")
            self.stop_pip_lr()

    def display_pip_frame(self, frame, canvas):
        """在canvas上显示一帧"""
        try:
            from PIL import Image, ImageTk
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # 调整图像大小
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                pil_image.thumbnail((canvas_width - 4, canvas_height - 4), Image.Resampling.LANCZOS)
            else:
                pil_image.thumbnail((150, 150), Image.Resampling.LANCZOS)
            
            # 更新画布
            photo = ImageTk.PhotoImage(pil_image)
            canvas.delete("all")
            
            canvas_width = canvas_width or 155
            canvas_height = canvas_height or 160
            x = canvas_width // 2
            y = canvas_height // 2
            canvas.create_image(x, y, anchor=tk.CENTER, image=photo)
            
            # 保存引用防止被垃圾回收
            if canvas == self.pip_left_canvas:
                self.current_pip_left_frame = photo
            else:
                self.current_pip_right_frame = photo
                
        except Exception as e:
            print(f"❌ 显示 PIP 帧失败: {e}")

    def pause_pip_lr(self):
        if not self.pip_lr_playing:
            return

        """暂停 PIP L/R 播放"""
        self.pip_lr_playing = False
        self.track_play_button.config(text="▶")
        
        # 保存暂停时间点
        if hasattr(self, 'pip_lr_start_time') and self.pip_lr_start_time:
            self.pip_lr_paused_time = time.time() - self.pip_lr_start_time
            print(f"⏸ 暂停 PIP L/R 播放，位置: {self.pip_lr_paused_time:.1f}s")
        
        # 暂停音频
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
        except:
            pass
        
        # 取消下一帧调度
        if self.pip_lr_after_id:
            self.root.after_cancel(self.pip_lr_after_id)
            self.pip_lr_after_id = None

    def stop_pip_lr(self):
        """停止 PIP L/R 播放"""
        self.pip_lr_playing = False
        self.track_play_button.config(text="▶")
        
        # 停止音频
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except:
            pass
        
        # 取消调度
        if self.pip_lr_after_id:
            self.root.after_cancel(self.pip_lr_after_id)
            self.pip_lr_after_id = None
        
        # 释放视频
        if self.pip_left_cap:
            self.pip_left_cap.release()
            self.pip_left_cap = None
        
        if self.pip_right_cap:
            self.pip_right_cap.release()
            self.pip_right_cap = None
        
        # 清除播放状态
        self.pip_lr_start_time = None
        self.pip_lr_paused_time = None
        
        # 清空画布
        self.pip_left_canvas.delete("all")
        self.pip_left_canvas.create_text(77, 80, text="Left\n画中画左侧", 
                                         fill="gray", font=("Arial", 9), justify=tk.CENTER, tags="hint")
        
        self.pip_right_canvas.delete("all")
        self.pip_right_canvas.create_text(77, 80, text="Right\n画中画右侧", 
                                          fill="gray", font=("Arial", 9), justify=tk.CENTER, tags="hint")
        
        # 重置时间显示
        self.track_time_label.config(text="00:00/00:00")
        
        print("⏹ 停止 PIP L/R 播放")

    def on_secondary_track_tab_changed(self, event=None):
        """tab切换时停止正在播放的视频并加载预览帧"""
        if not self.workflow:
            return
        # 先停止所有播放
        self.pause_secondary_track()
        self.pause_pip_lr()
        
        # 根据当前 tab 加载相应的预览帧
        current_tab_index = self.narration_notebook.index(self.narration_notebook.select())
        if current_tab_index == 0:
            # 旁白轨道 tab：从当前偏移位置加载第一帧
            self.load_secondary_track_first_frame()
        elif current_tab_index == 1:
            # PIP L/R tab：从起始位置加载第一帧
            self.load_pip_lr_first_frame()
        self._update_remove_track_btn_state()

    def load_pip_lr_first_frame(self):
        """加载 PIP L/R 视频的第一帧"""
        if not self.workflow:
            return
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not current_scene:
                return
            
            left_path = current_scene.get(self.selected_secondary_track+'_left')
            right_path = current_scene.get(self.selected_secondary_track+'_right')
            
            if not left_path or not right_path:
                # 清空画布显示提示
                self.pip_left_canvas.delete("all")
                self.pip_left_canvas.create_text(77, 80, text="Left\n画中画左侧\n未生成", 
                                                 fill='gray', font=('Arial', 9), justify=tk.CENTER, tags="hint")
                self.pip_right_canvas.delete("all")
                self.pip_right_canvas.create_text(77, 80, text="Right\n画中画右侧\n未生成", 
                                                  fill='gray', font=('Arial', 9), justify=tk.CENTER, tags="hint")
                self.track_time_label.config(text="00:00/00:00")
                return
            
            if not os.path.exists(left_path) or not os.path.exists(right_path):
                print(f"❌ PIP L/R 视频文件不存在")
                return
            
            # 打开左侧视频获取第一帧
            temp_cap_left = cv2.VideoCapture(left_path)
            if temp_cap_left.isOpened():
                ret, frame = temp_cap_left.read()
                if ret:
                    self.display_pip_frame(frame, self.pip_left_canvas)
                
                # 获取总时长
                total_frames = temp_cap_left.get(cv2.CAP_PROP_FRAME_COUNT)
                total_duration = total_frames / STANDARD_FPS
                total_str = f"{int(total_duration // 60):02d}:{int(total_duration % 60):02d}"
                self.track_time_label.config(text=f"00:00/{total_str}")
                
                temp_cap_left.release()
            
            # 打开右侧视频获取第一帧
            temp_cap_right = cv2.VideoCapture(right_path)
            if temp_cap_right.isOpened():
                ret, frame = temp_cap_right.read()
                if ret:
                    self.display_pip_frame(frame, self.pip_right_canvas)
                temp_cap_right.release()
            
            print(f"✅ 已加载 PIP L/R 第一帧")
            
        except Exception as e:
            print(f"❌ 加载 PIP L/R 第一帧失败: {e}")

    def update_secondary_track_time(self):
        """更新旁白轨道播放时间显示"""
        try:
            if not hasattr(self, 'secondary_track_cap') or not self.secondary_track_cap:
                self.track_time_label.config(text="00:00/00:00")
                # 禁用滑块
                if hasattr(self, 'secondary_track_scale'):
                    self.secondary_track_scale.config(state=tk.DISABLED)
                return
            
            # 获取视频总时长
            total_frames = self.secondary_track_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_duration = total_frames / STANDARD_FPS
            
            # 更新滑块的最大值
            if hasattr(self, 'secondary_track_scale'):
                self.secondary_track_scale.config(to=total_duration, state=tk.NORMAL)
            
            # 确定当前播放时间
            current_time = 0.0
            if self.secondary_track_playing and self.secondary_track_start_time:
                if self.selected_secondary_track == "narration":
                    current_time = (time.time() - self.secondary_track_start_time)
                else:
                    current_time = (time.time() - self.secondary_track_start_time) + self.secondary_track_offset
            elif self.secondary_track_paused_time:
                current_time = self.secondary_track_paused_time
            else:
                # 默认：从视频帧位置计算
                current_pos = self.secondary_track_cap.get(cv2.CAP_PROP_POS_FRAMES)
                current_time = current_pos / STANDARD_FPS
            
            # 确保时间在合理范围内
            current_time = max(0, min(current_time, total_duration))
            
            # 更新滑块值（不触发回调）
            if hasattr(self, 'secondary_track_scale_var'):
                self.secondary_track_scale_var.set(current_time)
            
            # 格式化时间显示 (MM:SS 格式)
            current_str = f"{int(current_time // 60):02d}:{int(current_time % 60):02d}"
            total_str = f"{int(total_duration // 60):02d}:{int(total_duration % 60):02d}"
            
            self.track_time_label.config(text=f"{current_str}/{total_str}")
            
        except Exception as e:
            print(f"❌ 更新旁白轨道时间显示失败: {e}")
            self.track_time_label.config(text="00:00/00:00")
            if hasattr(self, 'secondary_track_scale'):
                self.secondary_track_scale.config(state=tk.DISABLED)

    def display_secondary_track_frame_at_time(self, time_position):
        """在canvas上显示指定时间的视频帧"""
        try:
            if not hasattr(self, 'secondary_track_cap') or not self.secondary_track_cap:
                # 如果没有cap，尝试打开视频
                current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
                if not current_scene:
                    return
                track_path = get_file_path(current_scene, self.selected_secondary_track)
                if not track_path:
                    return
                temp_cap = cv2.VideoCapture(track_path)
                if not temp_cap.isOpened():
                    return
            else:
                temp_cap = self.secondary_track_cap
            
            # 跳转到指定时间
            temp_cap.set(cv2.CAP_PROP_POS_FRAMES, int(time_position * STANDARD_FPS))
            ret, frame = temp_cap.read()
            
            if ret:
                from PIL import Image, ImageTk
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                
                # 调整图像大小适应Canvas
                canvas_width = self.secondary_track_canvas.winfo_width()
                canvas_height = self.secondary_track_canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:
                    pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
                else:
                    pil_image.thumbnail((310, 170), Image.Resampling.LANCZOS)
                
                # 更新画布显示
                self.current_secondary_track_frame = ImageTk.PhotoImage(pil_image)
                self.secondary_track_canvas.delete("all")
                
                canvas_width = canvas_width or 320
                canvas_height = canvas_height or 180
                x = canvas_width // 2
                y = canvas_height // 2
                self.secondary_track_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_secondary_track_frame)
            
            # 如果使用的是临时cap，释放它
            if temp_cap != self.secondary_track_cap:
                temp_cap.release()
                
        except Exception as e:
            print(f"❌ 显示视频帧失败: {e}")

    def on_secondary_track_scale_changed(self, value):
        """滑块拖拽回调：更新 secondary_track_paused_time"""
        try:
            if not hasattr(self, 'secondary_track_cap') or not self.secondary_track_cap:
                # 即使没有cap，也尝试显示帧
                current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
                if current_scene:
                    self.display_secondary_track_frame_at_time(float(value))
                return
            
            # 获取滑块值
            new_time = float(value)
            
            # 更新暂停时间（即使正在播放，也更新暂停时间以便下次暂停时使用）
            self.secondary_track_paused_time = new_time
            
            # 显示当前帧到canvas
            self.display_secondary_track_frame_at_time(new_time)
            
            # 如果当前正在播放，跳转到新位置
            if self.secondary_track_playing and self.secondary_track_cap:
                # 计算新的播放起始时间
                if self.selected_secondary_track == "narration":
                    self.secondary_track_start_time = time.time() - new_time
                else:
                    self.secondary_track_start_time = time.time() - (new_time - self.secondary_track_offset)
                
                # 跳转到新位置
                self.secondary_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(new_time * STANDARD_FPS))
                
                # 如果音频正在播放，也需要跳转
                try:
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.stop()
                        narration_audio_path = get_file_path(self.workflow.get_scene_by_index(self.current_scene_index), self.selected_secondary_track+'_audio')
                        if narration_audio_path:
                            pygame.mixer.music.load(narration_audio_path)
                            pygame.mixer.music.play(start=new_time)
                except Exception as e:
                    print(f"❌ 跳转音频位置失败: {e}")
            
            # 更新时间显示
            self.update_secondary_track_time()
            
        except Exception as e:
            print(f"❌ 滑块拖拽处理失败: {e}")

    def move_secondary_track_forward(self):
        """旁白轨道前进1秒"""
        try:
            if not hasattr(self, 'secondary_track_cap') or not self.secondary_track_cap:
                return
                
            # 获取当前播放位置
            current_pos = self.secondary_track_cap.get(cv2.CAP_PROP_POS_FRAMES)
            current_time = current_pos / STANDARD_FPS
            
            # 前进1秒
            new_time = current_time + 1.0
            
            # 获取视频总时长
            total_frames = self.secondary_track_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_duration = total_frames / STANDARD_FPS
            
            # 确保不超过视频总时长
            if new_time >= total_duration:
                new_time = total_duration - 0.1
                
            # 跳转到新位置
            self.secondary_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(new_time * STANDARD_FPS))
            
            # 更新时间显示
            self.update_secondary_track_time()
            
            print(f"⏩ 旁白轨道前进1秒: {current_time:.1f}s -> {new_time:.1f}s")
            
        except Exception as e:
            print(f"❌ 旁白轨道前进失败: {e}")

    def move_secondary_track_backward(self):
        """旁白轨道后退1秒"""
        try:
            if not hasattr(self, 'secondary_track_cap') or not self.secondary_track_cap:
                return
            # 获取当前播放位置
            current_pos = self.secondary_track_cap.get(cv2.CAP_PROP_POS_FRAMES)
            # 后退1秒
            new_time = current_pos / STANDARD_FPS - 1.0
            if new_time < 0:
                new_time = 0
                
            # 跳转到新位置
            self.secondary_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(new_time * STANDARD_FPS))
            
            # 更新时间显示
            self.update_secondary_track_time()
            
            print(f"⏪ 旁白轨道后退1秒")
            
        except Exception as e:
            print(f"❌ 旁白轨道后退失败: {e}")
