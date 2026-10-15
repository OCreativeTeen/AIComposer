"""SceneStructureMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
from utility import audio_transcriber
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import threading
import config_prompt
from project_manager import refresh_scene_media
import project_manager
from utility.file_util import get_file_path, show_auto_close_popup
import utility.llm_api as llm_api
import copy


class SceneStructureMixin:
    def _adjacent_story_scenes(self, scene):
        story = self.workflow.scenes_in_story(scene) or []
        if scene in story:
            index = story.index(scene)
            prev_scene = story[index - 1] if index > 0 else None
            next_scene = story[index + 1] if index + 1 < len(story) else None
            return prev_scene, next_scene
        prev_scene = self.workflow.get_previous_scene(self.current_scene_index)
        next_scene = self.workflow.get_next_scene(self.current_scene_index)
        return prev_scene, next_scene

    def _scene_clip_files(self, scene) -> tuple[str, str]:
        video = get_file_path(scene, "clip") if scene else ""
        if not video or not os.path.isfile(video):
            video = ""
        audio = get_file_path(scene, "clip_audio") if scene else ""
        if (not audio or not os.path.isfile(audio)) and video:
            audio = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(video) or ""
        if not video:
            return "", (audio if audio and os.path.isfile(audio) else "")
        if not audio or not os.path.isfile(audio):
            return video, ""
        return video, audio

    def _fit_clip_video(self, path: str) -> str:
        fp = self.workflow.ffmpeg_processor
        try:
            width, height = fp.get_resolution(path)
        except Exception:
            return path
        if width and height and (width != fp.width or height != fp.height):
            fitted = fp.resize_video(path, width=fp.width, height=fp.height)
            if fitted and os.path.isfile(fitted):
                return fitted
        return path

    def _join_clip_files(self, video_a: str, audio_a: str, video_b: str, audio_b: str):
        fp = self.workflow.ffmpeg_processor
        ap = self.workflow.ffmpeg_audio_processor
        video_a = self._fit_clip_video(video_a)
        video_b = self._fit_clip_video(video_b)
        merged_audio = ap.concat_audios([audio_a, audio_b])
        merged_video = fp.concat_videos([video_a, video_b], False)
        if not merged_audio or not merged_video:
            return "", ""
        muxed = fp.add_audio_to_video(merged_video, merged_audio)
        if not muxed or not os.path.isfile(muxed):
            return "", ""
        return muxed, merged_audio

    def _join_neighbor_media(
        self, still_image: str, video_n: str, audio_n: str, video_m: str, audio_m: str, *, front: bool
    ):
        """把挪过来的这一段接到旁边那场。front=True 时挪来的段放在旁边那场前面，否则放后面。

        有 ``still_image`` 时：只把两段声音接长，用旁边那场自己的 clip 图加上接长后的声音重新生成视频，
        不拼接画面（画面拼起来没有意义，原来的画面反正要作废）。没有图时才退回拼接画面。
        返回 ``(视频, 声音)``，失败返回 ``("", "")``。
        """
        if still_image and os.path.isfile(still_image):
            ap = self.workflow.ffmpeg_audio_processor
            pair = [audio_m, audio_n] if front else [audio_n, audio_m]
            joined_a = ap.concat_audios(pair)
            if not joined_a or not os.path.isfile(joined_a):
                return "", ""
            video = self.workflow.ffmpeg_processor.image_audio_to_video(still_image, joined_a, 1)
            if not video or not os.path.isfile(video):
                return "", ""
            return video, joined_a
        if front:
            return self._join_clip_files(video_m, audio_m, video_n, audio_n)
        return self._join_clip_files(video_n, audio_n, video_m, audio_m)

    def _scene_id_of(self, scene) -> int | None:
        try:
            return int(scene.get("id"))
        except (AttributeError, TypeError, ValueError):
            return None

    def _link_back_group(self, *scenes) -> None:
        """一次动作改了几场，就让这几场的备份互相记住，按 ⏱ 时一起恢复。"""
        ids = [self._scene_id_of(s) for s in scenes]
        for scene, own in zip(scenes, ids):
            if not isinstance(scene, dict):
                continue
            others = [i for i in ids if i is not None and i != own]
            if others:
                scene["back_with"] = others
            else:
                scene.pop("back_with", None)

    def _install_clip_files(self, scene, video: str, audio: str, *, keep_images: bool = False) -> None:
        self._backup_clip_to_scene_back(scene)
        refresh_scene_media(scene, "clip", ".mp4", video, True)
        if audio and os.path.isfile(audio):
            refresh_scene_media(scene, "clip_audio", ".wav", audio, True)
        if keep_images:
            # 视频是用这一场自己的 clip 图重新生成的，起始图和结束图都不用换。
            return
        fp = self.workflow.ffmpeg_processor
        saved = get_file_path(scene, "clip")
        first = fp.extract_frame(saved, True) if saved else None
        last = fp.extract_frame(saved, False) if saved else None
        if first and os.path.isfile(first):
            refresh_scene_media(scene, "clip_image", ".webp", first, True)
        if last and os.path.isfile(last):
            refresh_scene_media(scene, "clip_image_last", ".webp", last, True)

    def _shift_clip_to_neighbor(self, where: str, *, media_only: bool = False) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        plan = self._progress_action_plan()
        if not scene or not plan:
            return
        prev_scene, next_scene = self._adjacent_story_scenes(scene)
        if media_only:
            # 只搬画面和声音，不动讲稿：旁边那场是下一集或上一集的也可以。
            prev_scene = self.workflow.get_previous_scene(self.current_scene_index)
            next_scene = self.workflow.get_next_scene(self.current_scene_index)
        neighbor = prev_scene if where == "head" else next_scene
        if media_only:
            allowed = plan.get("media_prev") if where == "head" else plan.get("media_next")
            cut = float(plan["play"])
        else:
            move = plan["head"] if where == "head" else plan["tail"]
            allowed = bool(move)
            cut = float(move["cut"]) if move else 0.0
        if not allowed or neighbor is None:
            return
        video, audio = self._scene_clip_files(scene)
        other_video, other_audio = self._scene_clip_files(neighbor)
        if not video or not audio:
            messagebox.showinfo("挪动", "这一场没有画面或声音。", parent=self.root)
            return
        # 旁边那场的画面不拼接，只把声音接长，再用它自己的 clip 图加上新声音重新生成视频。
        # 所以旁边那场只要有声音和一张 clip 图就够；没有 clip 图时才退回拼接画面。
        neighbor_image = get_file_path(neighbor, "clip_image")
        use_still = bool(neighbor_image and os.path.isfile(neighbor_image))
        if not other_audio:
            messagebox.showinfo("挪动", "旁边那场没有声音。", parent=self.root)
            return
        if not use_still and not other_video:
            messagebox.showinfo("挪动", "旁边那场没有 clip 图，也没有画面。", parent=self.root)
            return
        sections = plan["sections"]
        self._release_preview_lock()
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
        except tk.TclError:
            pass

        def work() -> None:
            error = ""
            payload = None
            try:
                head_v = self.workflow.ffmpeg_processor.trim_video(video, start_time=0, end_time=cut)
                tail_v = self.workflow.ffmpeg_processor.trim_video(video, start_time=cut)
                head_a, tail_a = self.workflow.ffmpeg_audio_processor.split_audio(audio, cut)
                if not all([head_v, tail_v, head_a, tail_a]) or not all(
                    os.path.isfile(path) for path in (head_v, tail_v, head_a, tail_a)
                ):
                    error = "画面或声音没有切开。"
                elif where == "head":
                    joined_v, joined_a = self._join_neighbor_media(
                        neighbor_image if use_still else "", other_video, other_audio, head_v, head_a, front=False
                    )
                    if not joined_v:
                        error = "没有接到前一场。"
                    else:
                        payload = {"neighbor_v": joined_v, "neighbor_a": joined_a, "keep_v": tail_v, "keep_a": tail_a,
                                   "still": use_still}
                else:
                    joined_v, joined_a = self._join_neighbor_media(
                        neighbor_image if use_still else "", other_video, other_audio, tail_v, tail_a, front=True
                    )
                    if not joined_v:
                        error = "没有接到后一场。"
                    else:
                        payload = {"neighbor_v": joined_v, "neighbor_a": joined_a, "keep_v": head_v, "keep_a": head_a,
                                   "still": use_still}
            except Exception as exc:
                error = str(exc)

            def done() -> None:
                try:
                    self.root.config(cursor="")
                except tk.TclError:
                    pass
                if error or not payload:
                    messagebox.showerror("挪动", error or "没有挪过去。", parent=self.root)
                    return
                self._apply_shifted_media(scene, neighbor, where, cut, sections, payload) if media_only else self._apply_shifted_clip(scene, neighbor, where, cut, sections, payload)

            try:
                self.root.after(0, done)
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _apply_shifted_clip(self, scene, neighbor, where: str, cut: float, sections, payload) -> None:
        old_neighbor_len = float(self._clip_duration(neighbor) or 0.0)
        try:
            self._install_clip_files(
                neighbor, payload["neighbor_v"], payload["neighbor_a"], keep_images=bool(payload.get("still"))
            )
            self._install_clip_files(scene, payload["keep_v"], payload["keep_a"])
            self._link_back_group(scene, neighbor)
        except Exception as exc:
            messagebox.showerror("挪动", str(exc), parent=self.root)
            return
        source_len = float(self._speech_span_duration or 0.0)
        moved_len = cut if where == "head" else max(0.0, source_len - cut)
        moved = []
        kept = []
        for section in sections:
            try:
                start = float(section.get("start"))
                end = float(section.get("end"))
            except (TypeError, ValueError):
                continue
            row = dict(section)
            if where == "head":
                if end <= cut + 0.02:
                    moved.append(row)
                else:
                    row["start"] = round(max(0.0, start - cut), 2)
                    row["end"] = round(end - cut, 2)
                    kept.append(row)
            elif start >= cut - 0.02:
                row["start"] = round(max(0.0, start - cut), 2)
                row["end"] = round(max(0.0, end - cut), 2)
                moved.append(row)
            else:
                row["end"] = round(min(end, cut), 2)
                kept.append(row)
        self._write_speaking_sections(scene, kept)
        self._attach_sections_to_neighbor(neighbor, moved, where, old_neighbor_len, moved_len)
        self._preview_playhead = 0.0
        self.video_pause_time = 0.0
        self._speech_sections = kept
        self._speech_span_duration = max(0.0, float(self._speech_span_duration or 0.0) - cut) if where == "head" else cut
        self.workflow.save_scenes_to_json()
        self._put_speaking_text(scene.get("speaking") or "")
        self.refresh_gui_scenes()
        show_auto_close_popup(
            self.root,
            "挪动",
            "已移到前一场。" if where == "head" else "已移到后一场。",
        )

    def _apply_shifted_media(self, scene, neighbor, where: str, cut: float, sections, payload) -> None:
        """只搬画面和声音。讲稿不动。长短变了以后，这一场和接到的那场都按字数重新标时间。"""
        try:
            self._install_clip_files(
                neighbor, payload["neighbor_v"], payload["neighbor_a"], keep_images=bool(payload.get("still"))
            )
            self._install_clip_files(scene, payload["keep_v"], payload["keep_a"])
            self._link_back_group(scene, neighbor)
        except Exception as exc:
            messagebox.showerror("挪动", str(exc), parent=self.root)
            return
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
        except tk.TclError:
            pass
        self._retimed_speaking_sections(neighbor)
        fresh = self._retimed_speaking_sections(scene)
        try:
            self.root.config(cursor="")
        except tk.TclError:
            pass
        self._preview_playhead = 0.0
        self.video_pause_time = 0.0
        if fresh is not None:
            self._speech_sections = fresh
        self._speech_span_duration = float(self._clip_duration(scene) or 0.0)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(
            self.root,
            "挪动",
            "前面的画面和声音已接到上一场，时间已重新标好。" if where == "head" else "后面的画面和声音已接到下一场，时间已重新标好。",
        )

    def first_scene(self):
        """第一个场景"""
        if hasattr(self, '_save_timer') and self._save_timer:
            self.root.after_cancel(self._save_timer)
            self._save_timer = None
        self.update_current_scene()
        self.current_scene_index = 0
        self.refresh_gui_scenes()

    def last_scene(self):
        """最后一个场景"""
        if hasattr(self, '_save_timer') and self._save_timer:
            self.root.after_cancel(self._save_timer)
            self._save_timer = None
        self.update_current_scene()
        self.current_scene_index = len(self.workflow.scenes) - 1
        self.refresh_gui_scenes()

    def _episode_spans(self) -> list[tuple[str, int, int]]:
        """按场景顺序排出每一集的起止下标。"""
        spans: list[tuple[str, int, int]] = []
        for i, scene in enumerate(self.workflow.scenes or []):
            if not isinstance(scene, dict):
                continue
            name = self.workflow.scene_group(scene)
            if not spans or spans[-1][0] != name:
                spans.append((name, i, i))
            else:
                start = spans[-1][1]
                spans[-1] = (name, start, i)
        return spans

    def _jump_episode(self, delta: int) -> None:
        spans = self._episode_spans()
        if not spans:
            return
        if hasattr(self, "_save_timer") and self._save_timer:
            self.root.after_cancel(self._save_timer)
            self._save_timer = None
        self.update_current_scene()
        here = 0
        for k, (_name, start, end) in enumerate(spans):
            if start <= self.current_scene_index <= end:
                here = k
                break
        target = here + delta
        if target < 0 or target >= len(spans):
            return
        self.current_scene_index = spans[target][1]
        self.refresh_gui_scenes()

    def prev_episode(self):
        """跳到上一集的第一场。"""
        self._jump_episode(-1)

    def next_episode(self):
        """跳到下一集的第一场。"""
        self._jump_episode(1)

    def prev_scene(self):
        """上一个场景"""
        if hasattr(self, '_save_timer') and self._save_timer:
            self.root.after_cancel(self._save_timer)
            self._save_timer = None
        self.update_current_scene()
        self.current_scene_index -= 1
        if self.current_scene_index < 0:
            self.current_scene_index = len(self.workflow.scenes) - 1
        self.refresh_gui_scenes()

    def next_scene(self):
        """下一个场景"""
        if hasattr(self, '_save_timer') and self._save_timer:
            self.root.after_cancel(self._save_timer)
            self._save_timer = None
        self.update_current_scene()
        self.current_scene_index += 1
        if self.current_scene_index >= len(self.workflow.scenes):
            self.current_scene_index = 0
        self.refresh_gui_scenes()

    def _story_neighbor_index(self, delta: int) -> int | None:
        """同一故事里紧挨着的上一场或下一场。跨到别的故事就没有。"""
        scenes = self.workflow.scenes if self.workflow else None
        if not scenes:
            return None
        idx = self.current_scene_index
        other = idx + delta
        if other < 0 or other >= len(scenes):
            return None
        story = self.workflow.scenes_in_story(scenes[idx]) or []
        if scenes[other] not in story:
            return None
        return other

    def _ask_scene_structure(self) -> None:
        picked = self._ask_near_choices(
            self.btn_scene_edit,
            "场景分合",
            [
                ("delete", "删除本场"),
                ("merge_next", "与下一场合并"),
                ("merge_prev", "与上一场合并"),
                ("swap_next", "与下一场交换"),
                ("swap_prev", "与上一场交换"),
            ],
        )
        confirm = {
            "delete": "删除这一场？删掉以后回不来。",
            "merge_next": "把这一场和下一场合成一场？\n合并之后可以按 ⏱ 恢复成两场（只记最近一次合并）。",
            "merge_prev": "把上一场和这一场合成一场？\n合并之后可以按 ⏱ 恢复成两场（只记最近一次合并）。",
            "swap_next": "把这一场和下一场对调？",
            "swap_prev": "把这一场和上一场对调？",
        }.get(picked or "")
        if not confirm:
            return
        if not messagebox.askyesno("场景分合", confirm, parent=self.root):
            return
        if picked == "delete":
            self._delete_current_scene()
        elif picked == "merge_next":
            self._merge_with_neighbor(1)
        elif picked == "merge_prev":
            self._merge_with_neighbor(-1)
        elif picked == "swap_next":
            self._swap_with_neighbor(1)
        elif picked == "swap_prev":
            self._swap_with_neighbor(-1)

    def _delete_current_scene(self) -> None:
        if not self.workflow or not self.workflow.scenes:
            messagebox.showinfo("场景", "没有场景。", parent=self.root)
            return
        self.update_current_scene()
        self._cancel_scene_debounce_timer()
        self.workflow.replace_scene(self.current_scene_index)
        if self.current_scene_index >= len(self.workflow.scenes):
            self.current_scene_index = max(0, len(self.workflow.scenes) - 1)
        self.workflow.save_scenes_to_json()
        self._cancel_scene_debounce_timer()
        self._refresh_gui_scenes_impl()
        show_auto_close_popup(self.root, "场景", "本场已删除。")

    def _merge_with_neighbor(self, delta: int) -> None:
        if not self.workflow or not self.workflow.scenes:
            messagebox.showinfo("场景", "没有场景。", parent=self.root)
            return
        self.update_current_scene()
        other = self._story_neighbor_index(delta)
        if other is None:
            messagebox.showinfo(
                "场景",
                "没有上一场。" if delta < 0 else "没有下一场。",
                parent=self.root,
            )
            return
        self._cancel_scene_debounce_timer()
        current = self.current_scene_index
        if delta < 0:
            merged = self.workflow.merge_scene(other, current)
            if merged:
                self.current_scene_index = other
        else:
            merged = self.workflow.merge_scene(current, other)
        if not merged:
            messagebox.showinfo("场景", "这两场没有合并。", parent=self.root)
            return
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            self._retime_scene_after_structure(self.workflow.get_scene_by_index(self.current_scene_index))
        finally:
            try:
                self.root.config(cursor="")
            except tk.TclError:
                pass
        self.workflow.save_scenes_to_json()
        self._cancel_scene_debounce_timer()
        self._refresh_gui_scenes_impl()
        show_auto_close_popup(
            self.root,
            "场景",
            "已与上一场合并。" if delta < 0 else "已与下一场合并。",
        )

    def split_scene(self):
        """按预览播放线把当前场景切成前后两场。"""
        self.update_current_scene()
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
        if not scene:
            messagebox.showinfo("场景", "没有当前场景。", parent=self.root)
            return
        position = float(getattr(self, "_preview_playhead", 0) or 0)
        if not self.workflow.split_scene_at_position(self.current_scene_index, position):
            messagebox.showinfo("场景", "播放线还在开头或结尾，这一场分不开。", parent=self.root)
            return
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            for offset in (0, 1):
                self._retime_scene_after_structure(
                    self.workflow.get_scene_by_index(self.current_scene_index + offset)
                )
        finally:
            try:
                self.root.config(cursor="")
            except tk.TclError:
                pass
        self._preview_playhead = 0.0
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()

    def update_add_scene_insert_buttons_state(self):
        """当前有场景时可以打开插入过渡。"""
        if not getattr(self, "btn_add_scene", None):
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
        self.btn_add_scene.config(state=tk.NORMAL if scene else tk.DISABLED)

    def _insert_image_sides(self, before: bool) -> tuple:
        """前插时前一场是上一场、后一场是当前这场。后插相反。缺一边就不做首尾衔接。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        other_index = self.current_scene_index - 1 if before else self.current_scene_index + 1
        other = None
        if scene and 0 <= other_index < len(self.workflow.scenes or []):
            other = self.workflow.scenes[other_index]
        if before:
            return other, scene, other is not None
        return scene, other, other is not None

    def _insert_scene_copy(self, before: bool) -> None:
        """把当前场景复制一份，插在它前面或后面，仍在这一集。"""
        self.update_current_scene()
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return
        dup = copy.deepcopy(scene)
        dup["id"] = self.workflow.max_id(scene) + 1
        index = self.current_scene_index if before else self.current_scene_index + 1
        earlier, later, bridge = self._insert_image_sides(before)
        self.workflow.scenes.insert(index, dup)
        self.workflow.copy_inserted_scene_media(dup, scene, earlier=earlier, later=later, bridge=bridge)
        self.workflow.save_scenes_to_json()
        if before:
            self.current_scene_index += 1
        self.refresh_gui_scenes()

    def add_scene_insert(self):
        """在当前这场和上一场、或和下一场之间插入。"""
        self._open_ai_insert_dialog()

    def _open_ai_insert_dialog(self) -> None:
        """一个窗口里选择插在上一场和本场之间，还是本场和下一场之间。"""
        self.update_current_scene()
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
        if not scene:
            return
        total = len(self.workflow.scenes or [])
        has_prev = self.current_scene_index > 0
        has_next = self.current_scene_index + 1 < total
        place_var = tk.StringVar(value="before" if has_prev else "after")

        dlg = tk.Toplevel(self.root)
        dlg.title("插入过渡")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.withdraw()
        dlg.grab_set()

        main = ttk.Frame(dlg, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main, text="插入过渡", font=("Arial", 13, "bold")).pack(anchor=tk.W)
        ttk.Label(
            main,
            text="插在当前这场和相邻一场之间，仍在这一集。过渡接的就是选中的这两场。",
            wraplength=460,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 8))

        ttk.Label(main, text="插在").pack(anchor=tk.W)
        rb_before = ttk.Radiobutton(
            main,
            text="本场和上一场之间" if has_prev else "本场和上一场之间（这是第一场，没有上一场）",
            value="before",
            variable=place_var,
        )
        rb_before.pack(anchor=tk.W)
        rb_after = ttk.Radiobutton(
            main,
            text="本场和下一场之间" if has_next else "本场和下一场之间（这是最后一场，没有下一场）",
            value="after",
            variable=place_var,
        )
        rb_after.pack(anchor=tk.W, pady=(0, 8))
        if not has_prev:
            rb_before.state(["disabled"])
        if not has_next:
            rb_after.state(["disabled"])

        def _before() -> bool:
            return place_var.get() == "before"

        ttk.Button(
            main,
            text="简单拷贝",
            command=lambda: self._close_and_insert_copy(dlg, _before()),
        ).pack(fill=tk.X)
        copy_hint = ttk.Label(main, wraplength=460, foreground="#555555", justify=tk.LEFT)
        copy_hint.pack(anchor=tk.W, pady=(2, 10))

        box = ttk.LabelFrame(main, text="过渡场景", padding=8)
        box.pack(fill=tk.X)
        ttk.Label(
            box,
            text="上一场的尾图是这场的起始图，下一场的起始图是这场的终止图。视频要从这两张图之间转过去。下面几组可以一起选。",
            wraplength=440,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 6))
        missing_lbl = ttk.Label(
            box,
            text="旁边没有场景，不能做过渡。简单拷贝仍可用。",
            foreground="#8a3b12",
        )
        mode_caption = ttk.Label(box, text="时空")
        space_var = tk.StringVar(value=self._TRANSITION_SPACE[0][0])
        people_var = tk.StringVar(value=self._TRANSITION_PEOPLE[0][0])
        speech_var = tk.StringVar(value=self._TRANSITION_SPEECH[0][0])
        effect_var = tk.StringVar(value=self._TRANSITION_EFFECTS[0][0])

        def _pack_choice_group(title_widget, choices, variable) -> None:
            title_widget.pack(anchor=tk.W, pady=(8, 0))
            for key, hint in choices:
                ttk.Radiobutton(
                    box, text=f"{key}　{hint}", value=key, variable=variable
                ).pack(anchor=tk.W)

        _pack_choice_group(mode_caption, self._TRANSITION_SPACE, space_var)
        _pack_choice_group(ttk.Label(box, text="人物"), self._TRANSITION_PEOPLE, people_var)
        _pack_choice_group(ttk.Label(box, text="对白"), self._TRANSITION_SPEECH, speech_var)
        _pack_choice_group(ttk.Label(box, text="特效"), self._TRANSITION_EFFECTS, effect_var)

        actions = ttk.Frame(main)
        actions.pack(fill=tk.X, pady=(12, 0))
        insert_btn = ttk.Button(
            actions,
            text="插入过渡",
            command=lambda: self._close_and_insert_transition(
                dlg,
                _before(),
                space_var.get(),
                people_var.get(),
                speech_var.get(),
                effect_var.get(),
            ),
        )
        insert_btn.pack(side=tk.LEFT)
        ttk.Button(actions, text="取消", command=dlg.destroy).pack(side=tk.RIGHT)

        def _sync_place(*_args) -> None:
            before = _before()
            side_ok = has_prev if before else has_next
            copy_hint.config(
                text=(
                    "文字、声音和视频按当前这场拷贝。有上一场时，起始图用上一场的尾图，尾图用当前这场的起始图。"
                    if before
                    else "文字、声音和视频按当前这场拷贝。有下一场时，起始图用当前这场的尾图，尾图用下一场的起始图。"
                )
            )
            if side_ok:
                missing_lbl.pack_forget()
                insert_btn.state(["!disabled"])
            else:
                if not missing_lbl.winfo_ismapped():
                    missing_lbl.pack(anchor=tk.W, pady=(0, 6), before=mode_caption)
                insert_btn.state(["disabled"])

        place_var.trace_add("write", _sync_place)
        _sync_place()

        self._place_popup_near(dlg, self.btn_add_scene, below=False)
        dlg.wait_window()

    def _close_and_insert_copy(self, dlg: tk.Toplevel, before: bool) -> None:
        dlg.destroy()
        self._insert_scene_copy(before)

    def _close_and_insert_transition(
        self, dlg: tk.Toplevel, before: bool, space: str, people: str, speech: str, effect: str
    ) -> None:
        dlg.destroy()
        self._insert_transition_scene(before, space, people, speech, effect)

    def _scene_prompt_block(self, scene: dict, title: str) -> str:
        lines = [title]
        for key, label in (
            ("caption", "标题"),
            ("visual", "画面"),
            ("speaking", "讲话"),
            ("voiceover", "旁白"),
            ("actor", "人物"),
        ):
            value = (scene.get(key) or "").strip() if isinstance(scene, dict) else ""
            if value:
                lines.append(f"{label}：{value}")
        if len(lines) == 1:
            lines.append("（这场没有文字）")
        return "\n".join(lines)

    def _transition_prompt(
        self, earlier: dict, later: dict, space: str, people: str, speech: str, effect: str
    ) -> tuple[str, str]:
        """时空、人物、对白、特效四组选择拼成一场过渡。内容从这两场里看。"""
        space_text = {
            "不变": "地方和时间都不要改。人还在原来的地方，也不要换成另一个时段。",
            "换地方": (
                "地方要从起始图走到终止图。\n"
                "前一场在室外、后一场在室内：写出怎么走到门口、怎么进去。\n"
                "两个地方不一样：写出这一段路。不要顺便改时间。"
            ),
            "换时间": (
                "时间要过去。白天到黑夜，或黑夜到白天，都写在 visual 里。\n"
                "这种过渡很快。人可以留在场上。不要用对话解释过了多久，也不要顺便换地方。"
            ),
            "一起变": (
                "地方和时间一起变。这是一次大的场面转换，带一点奇幻的跳跃，但这场本身很短。\n"
                "例如从白天的街上，一下子到夜里的室内。不要把路途慢慢走完。"
            ),
        }.get(space) or "按这两场里真正的地方和时间来写。"
        people_text = {
            "没有变化": "在场的人保持不变。不要加人，也不要让人离开。不要新造两场里都没有的人。",
            "自然增减": (
                "比较两场的人物。变化要平淡。\n"
                "多出来的人平静地走进来，或被带着进来。例如前一场没有小孩，后一场有，就写这个小孩怎么走进画面。\n"
                "少掉的人平静地走开、转身、退出画面。\n"
                "不要用车、碰撞、惊吓这类意外来解释。"
            ),
            "意外增减": (
                "比较两场的人物。人的增减由一个意外带出来。\n"
                "例如车忽然停下，有人从车上下来；或一声动静把人引进来；少掉的人被意外带走、匆匆离开。\n"
                "意外要能从这两场里看出来。不要另编一场和这两场无关的事故，也不要新造两场里都没有的人。"
            ),
        }.get(people) or "人物按这两场里已经有的人来写。"
        speech_text = {
            "不说话": (
                "speaking 和 voiceover 都留空。不要寒暄，不要嬉笑、叹息，也不要借动作把话说出来。\n"
                "可以用一段很短的音乐把两场带过去，写在 visual 里。不要写歌词。不用音乐也可以，那就只留画面。"
            ),
            "简单寒暄": (
                "只写一两句没有实际内容的招呼，例如好久不见、进来坐。按这两场来写，不要照抄例子。\n"
                "不要接上两边正在谈的话题，也不要把后面那场的对话提前说完。\n"
                "一个人开口：话写在 speaking，voiceover 留空。actor 只放这个人，放在第一位。\n"
                "两个人都开口：每人只一句。第一人写 speaking，第二人写 voiceover。actor 按这个顺序写这两位。"
            ),
            "人声": (
                "用很短的人声，把人的出现或离开托出来。配合上面选的人物增减。\n"
                "人走进来、多了一个人，或忽然出现：一声嬉笑、一声招呼、一声轻呼。\n"
                "人离开或少了一个人：一声叹息、一声短别。声音要跟这个地方相称。\n"
                "不要写成一段有内容的对话，也不要把后面那场的话提前说完。\n"
                "一个人出声：写在 speaking，voiceover 留空。actor 只放这个人，放在第一位。\n"
                "两个人都出声：第一人写 speaking，第二人写 voiceover。actor 按这个顺序写这两位。\n"
                "人没有增减时，不要硬加一声。speaking 和 voiceover 留空。actor 只保留本来在场的人。"
            ),
            "小动作": (
                "speaking 和 voiceover 都留空。\n"
                "做一个把两场接上的小动作，声音跟着动作，写在 visual 里。\n"
                "饭馆里是吃饭、倒酒、碰杯；路上是走几步、停一下。按这两场真正的地方来，不要把话题讲下去。"
            ),
            "场景烘托": (
                "speaking 和 voiceover 都留空。对话在这里暂停。\n"
                "看两场正在谈的事，把那种气氛在环境里展现一下，并带上相应的声音，写在 visual 里。\n"
                "谈得沉重或可怕，就阴一点；谈得顺，就有光、鲜花。也可以是风、树叶，或他们看见的风景。\n"
                "只烘托他们的话题，不要替他们把话说完，也不要另起一个故事。"
            ),
        }.get(speech) or "话要少。"
        effect_text = {
            "自然转换": (
                "不加特效。画面从起始图自然走到终止图。\n"
                "不要写翻书、嗖的一声、擦除、闪白或叠化。"
            ),
            "叠化": (
                "这场很短。起始图慢慢变淡，终止图从里面显出来，两张图有一小段叠在一起。\n"
                "这个叠化写在 visual 里。"
            ),
            "嗖一下": (
                "这场很短。画面被很快地甩过去，带一声「嗖」的掠过。\n"
                "这一声写在 visual 里。不要写成慢慢走路。"
            ),
            "翻书": (
                "这场很短。起始图像书页被翻过去，终止图在新的一页上。可以有纸页翻动的声音。\n"
                "翻页写在 visual 里。"
            ),
            "擦除": (
                "这场很短。终止图从一侧把起始图推开，像一道擦除扫过画面。\n"
                "擦除写在 visual 里。"
            ),
            "闪白": (
                "这场很短。画面先闪成一片白，再落到终止图。\n"
                "闪白写在 visual 里。"
            ),
        }.get(effect) or (
            "画面从起始图走到终止图。这场保持短。"
        )
        system_prompt = (
            "写一场过渡，插在用户给出的两场之间。这里只写要写回这一场的文字。\n"
            "转场一定用两张已经备好的图：上一场的尾图是这场的起始图，下一场的起始图是这场的终止图。\n"
            "后面生成视频时，画面要从起始图转到终止图。visual 就是给这段视频用的，必须写成这个转场过程，不能写成两张各不相干的静图说明。\n"
            "时空、人物、对白、特效是四组分开的选择，每一组都要照着做。\n"
            "某一组选了不变、没有变化或不说话，就不要在那一组里自行加戏。\n"
            "内容必须来自这两场。不要另起一个故事，不要把两边已经说过的话再讲一遍。\n"
            "对白选了「不说话」时，可以在 visual 里写一段短音乐把这场带过去。其他对白不要写背景音乐。\n"
            "动作、表情、音效和转场特效都写在 visual，不要写进 actor。\n"
            "只要 speaking 或 voiceover 里有字，actor 就必须写上出声的人，并且和这两处对上。\n"
            "actor 用两场里已有的写法。第一位说 speaking，第二位说 voiceover。只有一个人出声时，actor 只写这一位，voiceover 留空。\n"
            "speaking 和 voiceover 都空时，不要为了填 actor 而加一个开口的人。\n\n"
            f"时空：{space}\n{space_text}\n\n"
            f"人物：{people}\n{people_text}\n\n"
            f"对白：{speech}\n{speech_text}\n\n"
            f"特效：{effect}\n{effect_text}\n"
            "除了自然转换，特效都是很短的一闪，不要写成一场完整的戏。\n\n"
            "只输出一个 JSON 对象，不要解释。字段是 caption、visual、speaking、voiceover、actor。\n"
            "用这两场原来的语言。\n"
            "actor 沿用两场里已有的人。有人出声时，actor 的顺序必须和 speaking、voiceover 一致，不能空着。"
        )
        user_prompt = (
            f"{self._scene_prompt_block(earlier, '前面那场')}\n\n"
            f"{self._scene_prompt_block(later, '后面那场')}"
        )
        return system_prompt, user_prompt

    def _insert_transition_scene(
        self, before: bool, space: str, people: str, speech: str, effect: str
    ) -> None:
        """插入一场图片已拷好的过渡场景，并把提示词拷到剪贴板。"""
        self.update_current_scene()
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return
        other_index = self.current_scene_index - 1 if before else self.current_scene_index + 1
        if other_index < 0 or other_index >= len(self.workflow.scenes):
            messagebox.showinfo("过渡", "旁边没有场景，不能做过渡。", parent=self.root)
            return
        other = self.workflow.scenes[other_index]
        earlier, later = (other, scene) if before else (scene, other)
        dup = copy.deepcopy(scene)
        dup["id"] = self.workflow.max_id(scene) + 1
        bits = [
            name
            for name, plain in (
                (space, "不变"),
                (people, "没有变化"),
                (speech, "不说话"),
                (effect, "自然转换"),
            )
            if name and name != plain
        ]
        dup["caption"] = "过渡" if not bits else "过渡·" + "·".join(bits)
        dup["transition"] = {
            "插在": "上一场" if before else "下一场",
            "时空": space,
            "人物": people,
            "对白": speech,
            "特效": effect,
        }
        dup["speaking"] = ""
        dup["voiceover"] = ""
        index = self.current_scene_index if before else self.current_scene_index + 1
        self.workflow.scenes.insert(index, dup)
        self.workflow.copy_inserted_scene_media(dup, scene, earlier=earlier, later=later, bridge=True)
        self.workflow.save_scenes_to_json()
        self.current_scene_index = index
        self.refresh_gui_scenes()
        system_prompt, user_prompt = self._transition_prompt(
            earlier, later, space, people, speech, effect
        )
        try:
            parsed = self.llm_api_manual.generate_json(system_prompt, user_prompt, expect_list=False)
        except Exception as exc:
            messagebox.showerror("过渡", f"没有拿到结果：{exc}", parent=self.root)
            return
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed and isinstance(parsed[0], dict) else {}
        if not isinstance(parsed, dict):
            parsed = {}
        fields = {
            key: parsed[key]
            for key in ("caption", "visual", "speaking", "voiceover", "actor")
            if key in parsed and parsed[key] is not None
        }
        if not fields:
            show_auto_close_popup(self.root, "过渡", "已插入过渡场景。这次没有写回文字。")
            return
        self._apply_scene_import_item(dup, fields)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, "过渡", "过渡文字已写回这一场。")

    def _on_scene_insert_silence_marker(self, event=None):
        """讲话/旁白框按 Insert：弹出静音时长菜单，在光标处插入 <0.5> 等标记。"""
        w = getattr(event, "widget", None)
        if w is None:
            return "break"

        silence_choices = (
            ("<0.5>", "0.5 秒"),
            ("<0.75>", "0.75 秒"),
            ("<1.0>", "1.0 秒"),
            ("<1.25>", "1.25 秒"),
            ("<1.5>", "1.5 秒"),
        )

        def _insert(marker: str):
            w.insert(tk.INSERT, marker)
            w.focus_set()

        menu = tk.Menu(w, tearoff=0)
        for marker, label in silence_choices:
            menu.add_command(label=label, command=lambda m=marker: _insert(m))

        try:
            bbox = w.bbox(tk.INSERT)
            if bbox:
                x, y, _, h = bbox
                menu.tk_popup(int(w.winfo_rootx() + x), int(w.winfo_rooty() + y + h))
            else:
                menu.tk_popup(int(w.winfo_rootx() + 8), int(w.winfo_rooty() + 8))
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
        return "break"

    def _swap_with_neighbor(self, delta: int) -> None:
        """和上一场或下一场对调位置。两边的内容整场换过去。"""
        if not self.workflow or not self.workflow.scenes:
            messagebox.showinfo("场景分合", "没有场景。", parent=self.root)
            return
        self.update_current_scene()
        other = self.current_scene_index + delta
        if other < 0 or other >= len(self.workflow.scenes):
            messagebox.showinfo(
                "场景分合",
                "没有上一场。" if delta < 0 else "没有下一场。",
                parent=self.root,
            )
            return
        if not self.workflow.swap_scene(self.current_scene_index, other):
            messagebox.showinfo("场景分合", "这两场没有交换。", parent=self.root)
            return
        self.refresh_gui_scenes()
        show_auto_close_popup(
            self.root,
            "场景分合",
            "已与上一场交换。" if delta < 0 else "已与下一场交换。",
        )

    def _apply_scene_import_item(self, scene: dict, raw_item: dict) -> int:
        """将单个 import 元素合并到场景：同名字段覆盖；``speaker`` 映射为 ``actor``。"""
        if not isinstance(scene, dict) or not isinstance(raw_item, dict):
            return 0
        item = copy.deepcopy(raw_item)
        project_manager.normalize_scene_content_item_for_workflow(item)

        applied = 0
        if "speaker" in item:
            sp = item.pop("speaker")
            if sp is not None and (sp != "" or "actor" in scene):
                scene["actor"] = sp
                applied += 1

        for key, val in item.items():
            if key in self._SCENE_IMPORT_SKIP_KEYS:
                continue
            if key in scene or key in self._SCENE_IMPORT_ALWAYS_KEYS:
                scene[key] = val
                applied += 1
        return applied

    def _ask_scene_transform_or_split(self) -> None:
        """一个窗口两部分：上面是场景变换，空一行，下面是场景拆分。点一项就执行。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("变换 / 拆分")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.withdraw()
        holder = {"value": None}
        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        def pick(value: str) -> None:
            holder["value"] = value
            dlg.destroy()

        def text_width(text: str) -> int:
            return sum(2 if ord(ch) > 127 else 1 for ch in text) + 2

        sections = [
            (
                "场景变换",
                "按现在的人物重写说法。结果直接写回这一场的讲话和旁白。",
                [
                    ("t1", "只改这一场的讲话和旁白"),
                    ("t2", "这一场和下一场合成一段"),
                    ("t3", "这一场连后面两场合成一段"),
                ],
            ),
            (
                "场景拆分",
                "文字拆分只改说法，每场复制原来的整段。音频转录按每句的起止，把画面和声音切开。",
                [
                    ("s_content", "按文字内容拆分，媒体照原样复制"),
                    ("s_audio", "音频转录拆分，按语句切开画面和声音"),
                ],
            ),
        ]
        width = max(
            [text_width(label) for _t, _h, items in sections for _v, label in items]
            + [text_width("取消"), 12]
        )
        for i, (head, hint, items) in enumerate(sections):
            if i:
                ttk.Frame(frame, height=14).pack(fill=tk.X)
            ttk.Label(frame, text=head).pack(anchor=tk.W, pady=(0, 4))
            ttk.Label(frame, text=hint, wraplength=360, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 6))
            for value, label in items:
                ttk.Button(frame, text=label, width=width, command=lambda v=value: pick(v)).pack(
                    fill=tk.X, pady=2
                )
        ttk.Button(frame, text="取消", width=width, command=dlg.destroy).pack(fill=tk.X, pady=(12, 0))
        self._place_popup_near(dlg, self._scene_speech_btn, below=False)
        dlg.grab_set()
        dlg.wait_window()
        picked = holder["value"]
        if picked in ("t1", "t2", "t3"):
            self.apply_scene_speech_transform(int(picked[1]))
        elif picked == "s_content":
            self.split_scene_content_by_llm()
        elif picked == "s_audio":
            self.split_scene_by_transcription()

    def apply_scene_speech_transform(self, span: int = 1) -> None:
        """按当前 actor 重写说法。span 为 2 或 3 时把后面连续几场并进这一场的讲话和旁白。"""
        title = "场景变换" if span <= 1 else f"场景变换{span}"
        if not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning(title, "没有当前场景", parent=self.root)
            return
        scene = self.update_current_scene()
        index = self.current_scene_index
        fetch = 1 if span <= 1 else span
        later = [self.workflow.get_scene_by_index(index + step) for step in range(1, fetch + 1)]
        if span >= 2 and not later[0]:
            messagebox.showwarning(title, "后面没有下一场。", parent=self.root)
            return
        if span >= 3 and not later[1]:
            messagebox.showwarning(title, "后面不够两场。", parent=self.root)
            return
        built = config_prompt.build_scene_speech_transform_prompt(
            scene,
            self.workflow.get_previous_scene(index),
            later[0] if later else None,
            span=1 if span <= 1 else span,
            later=later,
        )
        if not built:
            messagebox.showwarning(
                title,
                "这一场没有可说话的人。不出现的人不算。",
                parent=self.root,
            )
            return
        _label, text = built
        try:
            parsed = self.llm_api_manual.generate_json(text, "按要求重写，只返回 JSON 对象。", expect_list=False)
        except Exception as exc:
            messagebox.showerror(title, f"变换失败: {exc}", parent=self.root)
            return
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed and isinstance(parsed[0], dict) else None
        if not isinstance(parsed, dict):
            messagebox.showinfo(title, "没有拿到可写回的内容，这一场保持原样。", parent=self.root)
            return
        fields = {
            key: parsed[key]
            for key in ("speaking", "voiceover")
            if key in parsed and parsed[key] is not None
        }
        scene = self.workflow.get_scene_by_index(index)
        if not scene or not fields:
            messagebox.showinfo(title, "没有拿到可写回的内容，这一场保持原样。", parent=self.root)
            return
        n = self._apply_scene_import_item(scene, fields)
        if not n:
            messagebox.showinfo(title, "没有拿到可写回的内容，这一场保持原样。", parent=self.root)
            return
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, title, "已写回这一场的讲话和旁白")

    def split_scene_content_by_llm(self) -> None:
        title = "场景拆分"
        if not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning(title, "没有当前场景", parent=self.root)
            return
        scene = self.update_current_scene()
        index = self.current_scene_index
        cfg = project_manager.PROJECT_CONFIG or {}
        override = cfg.get("channel_prompt") if isinstance(cfg.get("channel_prompt"), dict) else None
        _label, text = config_prompt.build_split_scene_prompt(
            scene,
            self.workflow.channel,
            override,
            self.workflow.get_previous_scene(index),
            self.workflow.get_next_scene(index),
        )
        try:
            raw = llm_api.LLMApi(llm_api.MODEL_MANUAL).generate_json(text, "按要求拆开，只返回 JSON 数组。", expect_list=True)
        except Exception as exc:
            messagebox.showerror(title, f"拆分失败: {exc}", parent=self.root)
            return
        items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        if len(items) < 2:
            messagebox.showinfo(title, "没有拆成多场，这一场保持原样。", parent=self.root)
            return
        self._replace_scene_with_cloned_splits(items)

    def _replace_scene_with_cloned_splits(self, items: list) -> None:
        """用多场文字替换当前这一场。每场复制原来的整段画面和声音，不按时间切开。"""
        title = "场景拆分"
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene or len(items) < 2:
            return
        index = self.current_scene_index
        sources = {
            "clip": get_file_path(scene, "clip"),
            "clip_audio": get_file_path(scene, "clip_audio"),
            "clip_image": get_file_path(scene, "clip_image"),
            "clip_image_last": get_file_path(scene, "clip_image_last"),
        }
        used_ids = {int(s.get("id") or 0) for s in (self.workflow.scenes or []) if isinstance(s, dict)}
        next_id = max(used_ids or {0})
        base_id = int(scene.get("id") or 0)
        new_scenes = []
        for i, item in enumerate(items):
            project_manager.normalize_scene_content_item_for_workflow(item)
            piece = copy.deepcopy(scene)
            if i == 0:
                piece["id"] = base_id
            else:
                next_id += 1
                while next_id in used_ids:
                    next_id += 1
                used_ids.add(next_id)
                piece["id"] = next_id
                for field, src in sources.items():
                    if not src:
                        continue
                    postfix = os.path.splitext(src)[1] or ".mp4"
                    refresh_scene_media(piece, field, postfix, src, True)
            for key in ("speaking", "voiceover", "visual", "actor", "caption"):
                if key in item and item.get(key) is not None:
                    piece[key] = item.get(key)
            for key in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end", "speaking_timing"):
                piece.pop(key, None)
            piece["clip_status"] = "ORIG"
            new_scenes.append(piece)
        self.workflow.replace_scene_with_others(index, new_scenes)
        self.current_scene_index = index
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, title, f"已拆成 {len(new_scenes)} 场")

    def split_scene_by_transcription(self) -> None:
        """按音频转录的语句起止，把当前这场切开。画面和声音按每句的时间裁开。"""
        title = "音频转录拆分"
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning(title, "没有当前场景", parent=self.root)
            return
        self.update_current_scene()
        index = self.current_scene_index
        video = get_file_path(scene, "clip")
        audio = get_file_path(scene, "clip_audio")
        if not video:
            messagebox.showwarning(title, "这一场没有画面，无法按声音切开。", parent=self.root)
            return
        if not audio:
            audio = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(video)
        if not audio or not os.path.isfile(audio):
            messagebox.showwarning(title, "这一场没有声音，无法转录。", parent=self.root)
            return
        scene_min = project_manager.PROJECT_CONFIG.get("scene_min_length", 9) if project_manager.PROJECT_CONFIG else 9
        try:
            scene_min = float(scene_min)
        except (TypeError, ValueError):
            scene_min = 9
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            transcriber = audio_transcriber.AudioTranscriber(self.workflow.pid, model_size="small", device="cuda")
            segments = transcriber.transcribe_with_whisper(
                audio,
                self.workflow.language,
                False,
                True,
                False,
                scene_min,
                int(scene_min * 1.5),
            )
        except Exception as exc:
            messagebox.showerror(title, f"转录失败: {exc}", parent=self.root)
            return
        finally:
            try:
                self.root.config(cursor="")
            except tk.TclError:
                pass
        if not segments:
            messagebox.showinfo(title, "没有转录出语句，这一场保持原样。", parent=self.root)
            return
        full = float(self.workflow.ffmpeg_audio_processor.get_duration(audio) or 0.0)
        if full > 0:
            segments[-1]["end"] = full
        if len(segments) < 2:
            messagebox.showinfo(title, "没有拆成多场，这一场保持原样。", parent=self.root)
            return
        pieces = self._scenes_from_transcript(scene, segments)
        if len(pieces) < 2:
            messagebox.showinfo(title, "没有拆成多场，这一场保持原样。", parent=self.root)
            return
        # 转录的起止是相对这一场声音的。场景上的 start/end 只记原始媒体的位置：
        # 这一场本来有，就加上它的起点；本来没有（不是从原始媒体来的），就不写。
        base_start = self.workflow._scene_time_seconds(scene.get("start"))
        try:
            self._cut_transcript_scenes(pieces, video, audio)
        except Exception as exc:
            messagebox.showerror(title, f"切开失败: {exc}", parent=self.root)
            return
        for piece in pieces:
            local_start = self.workflow._scene_time_seconds(piece.get("start"))
            local_end = self.workflow._scene_time_seconds(piece.get("end"))
            if base_start is None or local_start is None or local_end is None:
                piece.pop("start", None)
                piece.pop("end", None)
            else:
                piece["start"] = round(base_start + local_start, 2)
                piece["end"] = round(base_start + local_end, 2)
            piece.pop("duration", None)
        self.workflow.replace_scene_with_others(index, pieces)
        for piece in pieces:
            piece["clip_status"] = "ORIG"
        self.workflow.save_scenes_to_json()
        self.current_scene_index = index
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, title, f"已按语句拆成 {len(pieces)} 场")

    def _scenes_from_transcript(self, scene: dict, segments: list) -> list:
        """按转录段生成场景。有起止的段不继承原来的画面和声音，留给后面按时间切开。"""
        raw_id = int((int(scene.get("id") or 0) / 100) * 100)
        pieces = []
        for item in segments:
            if not isinstance(item, dict):
                continue
            raw_id += 100
            piece = copy.deepcopy(scene)
            piece["name"] = scene.get("name", "story")
            piece["id"] = raw_id
            caption = item.get("caption", "")
            piece["caption"] = caption
            piece["speaking"] = caption
            piece["voiceover"] = ""
            if "visual" in item and item.get("visual") is not None:
                piece["visual"] = item.get("visual")
            if item.get("speaker") is not None:
                piece["narrator"] = item.get("speaker")
            for key in ("start", "end"):
                if key in item and item.get(key) is not None:
                    piece[key] = item.get(key)
            piece.pop("duration", None)
            if "start" in item and "end" in item:
                piece.pop("narrator_audio", None)
                piece.pop("clip_audio", None)
                piece.pop("clip", None)
            for key in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end", "speaking_timing"):
                piece.pop(key, None)
            pieces.append(piece)
        return pieces

    def _cut_transcript_scenes(self, pieces: list, video: str, audio: str) -> None:
        """按每场的 start、end 切开源画面和声音，并抽出这一段的首尾图。"""
        fp = self.workflow.ffmpeg_processor
        fa = self.workflow.ffmpeg_audio_processor
        for i, item in enumerate(pieces):
            try:
                start = float(item.get("start") or 0.0)
                end = float(item.get("end") or 0.0)
                duration = end - start
            except (TypeError, ValueError):
                duration = 0.0
                start = 0.0
                end = 0.0
            if duration <= 0:
                print(f"skip scene {i + 1}: duration={duration}")
                continue
            clip_wav = fa.audio_cut_fade(audio, start, duration)
            if clip_wav:
                _old, new_audio = refresh_scene_media(item, "clip_audio", ".wav", clip_wav)
                item["speaker_audio"] = new_audio
            trimmed = fp.trim_video(video, start, end)
            if not trimmed:
                continue
            refresh_scene_media(item, "clip", ".mp4", trimmed)
            first_image = item.get("clip_image")
            if not first_image or not os.path.exists(first_image):
                first_image = self._frame_or_fallback(trimmed, True)
                if first_image:
                    refresh_scene_media(item, "clip_image", ".webp", first_image)
            last_image = self._frame_or_fallback(trimmed, False)
            if last_image:
                refresh_scene_media(item, "clip_image_last", ".webp", last_image, True)
