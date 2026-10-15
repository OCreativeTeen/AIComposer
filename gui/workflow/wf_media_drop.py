"""MediaDropMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.messagebox as messagebox
import os
from project_manager import refresh_scene_media
from utility.file_util import get_file_path, is_image_file, is_audio_file
from tkinterdnd2 import DND_FILES
from gui.choice_dialog import askchoice


class MediaDropMixin:
    def on_image_drop(self, event, image_type):
        """处理图片拖放事件
        
        Args:
            event: 拖放事件
            image_type: 'clip_image', "narration_image", 或 'zero_image'
        
        竖屏项目 **1080×1920**：一次拖入 **三张** 横向 ≈16∶9 图 → 1152×648、每图裁底 20px，
        自上而下顶对齐铺满宽度，底部留白叠水印（``compose_triple_landscape_vertical_mosaic_webp``）。
        **三图 / 双图拼图前** 会对每张图依次弹出裁切审阅（←/→ 平移水平视窗，复原恢复居中）。

        **两张** → 仍为双图居中拼接（1440×810、裁底 25px）；同样先逐张审阅。
        否则单图 ``resize_image_smart``；多张非拼图时仅用首张并提示。
        """
        IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        try:
            raw_paths = self.root.tk.splitlist(event.data)
        except tk.TclError:
            raw_paths = [event.data]

        paths = []
        seen = set()
        for rp in raw_paths:
            ps = os.path.expanduser(str(rp).strip().strip('{}"'))
            ps = ps.strip('"')
            if ps and ps not in seen:
                seen.add(ps)
                paths.append(ps)

        img_paths = [
            p for p in paths
            if os.path.isfile(p) and p.lower().endswith(IMAGE_EXT)
        ]
        if not img_paths:
            messagebox.showerror("错误", "请拖放图片文件 (PNG, JPG, WEBP等)", parent=self.root)
            return

        try:
            self._apply_image_paths_to_preview_slot(image_type, img_paths)
        except Exception as e:
            error_msg = f"更新图片失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg, parent=self.root)

    def setup_drag_and_drop(self):
        self.video_canvas.drop_target_register(DND_FILES)
        self.video_canvas.dnd_bind('<<Drop>>', self.on_media_drop)
        self.video_canvas.dnd_bind('<<DragEnter>>', self.on_video_drag_enter)
        self.video_canvas.dnd_bind('<<DragLeave>>', self.on_video_drag_leave)

    def on_video_drag_enter(self, event):
        """视频拖拽进入时的视觉反馈"""
        self.video_canvas.create_rectangle(0, 0, self.video_canvas.winfo_width(), 
                                         self.video_canvas.winfo_height(), 
                                         outline="blue", width=3, tags="drag_border")

    def on_video_drag_leave(self, event):
        """视频拖拽离开时恢复视觉状态"""
        self.video_canvas.delete("drag_border")

    def on_media_drop(self, event):
        self.video_canvas.delete("drag_border")

        try:
            raw_paths = self.root.tk.splitlist(event.data)
        except tk.TclError:
            raw_paths = [event.data]

        paths = []
        seen = set()
        for rp in raw_paths:
            ps = os.path.expanduser(str(rp).strip().strip('{}"'))
            ps = ps.strip('"')
            if ps and ps not in seen:
                seen.add(ps)
                paths.append(ps)

        if not paths:
            return

        if len(paths) > 1:
            for p in paths:
                if not os.path.isfile(p):
                    messagebox.showwarning("拖放", f"无效路径：\n{p}", parent=self.root)
                    return
                if not is_image_file(p):
                    messagebox.showwarning(
                        "拖放",
                        "多文件拖放时仅支持全部为图片（PNG、JPG、WEBP 等），\n请勿混入视频或其他类型。",
                        parent=self.root,
                    )
                    return
            picked = askchoice(
                "拖入多张图片",
                [
                    (
                        "story",
                        "本故事：第一张更新当前场景，其余按顺序插入克隆场景",
                    ),
                    (
                        "current_scene",
                        "当前场景：将当前场景克隆为多镜，每镜对应一张图",
                    ),
                ],
                self.root,
            )
            if picked is None:
                return
            _, mode = picked
            if mode == "story":
                self._on_media_drop_multi_clip_images(paths)
            elif mode == "current_scene":
                self._on_media_drop_multi_clip_images_current_scene(paths)
            return

        dropped_file = paths[0]
        if not os.path.exists(dropped_file):
            return

        if is_image_file(dropped_file):
            self._on_media_drop_single_clip_image(dropped_file)
            return

        if dropped_file.lower().endswith(".pdf"):
            self._on_media_drop_pdf(dropped_file)
            return

        can_equal_split = (
            (is_audio_file(dropped_file) and dropped_file.lower().endswith(".wav"))
            or (is_audio_file(dropped_file) and dropped_file.lower().endswith(".mp3"))
        )

        if can_equal_split:
            lower = dropped_file.lower()
            if lower.endswith(".mp3"):
                wav_path = self.workflow.ffmpeg_audio_processor.to_wav(dropped_file)
            else:
                wav_path = dropped_file

            picked = askchoice(
                "拖入音频：分配到本故事 CLIP 或 ZERO",
                [
                    (
                        "equal_clip", 
                        "均分：按时长均分音频，依次写入各场景"
                    ),
                    (
                        "ratio_clip",
                        "按比例：按各场景现有时长比例切分新音频",
                    ),
                    (
                        "zero_bg",
                        "ZERO 背景：同一音/视频写入各场景 zero/zero_audio",
                    ),
                ],
                self.root,
            )
            if picked is None:
                return
            _, mode = picked

            if mode == "equal_clip":
                self._media_drop_apply_equal_clip_audio_split(wav_path)
            elif mode == "ratio_clip":
                self._media_drop_apply_ratio_clip_audio_split(wav_path)
            elif mode == "zero_bg":
                self.apply_zero_background_media_from_path(wav_path)

            return

    def _on_media_drop_single_clip_image(self, image_path: str) -> None:
        """视频画布拖入单张图：仅更新当前场景 clip_image。"""
        try:
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not scene:
                return
            fp = self.workflow.ffmpeg_processor
            file_path = fp.resize_image_smart(image_path)
            refresh_scene_media(scene, "clip_image", ".webp", file_path, True)
            self.workflow.write_scene_page_png(scene, file_path)
            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()
            self.display_image_on_canvas_for_track("clip_image")
            print(f"✅ 已更新 clip_image（拖放）: {os.path.basename(file_path)}")
            self._after_clip_image_changed(scene, "已换上拖入的图片，并加进了本集图片库。")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", f"更新 clip_image 失败: {e}", parent=self.root)

    def _on_media_drop_multi_clip_images(self, image_paths: list[str]) -> None:
        """视频画布拖入多张图：第一张更新当前场景，其余按顺序插入克隆场景并各设 clip_image。"""
        try:
            scene0 = self.workflow.get_scene_by_index(self.current_scene_index)
            if not scene0:
                return
            k = self.current_scene_index
            template = scene0.copy()
            fp = self.workflow.ffmpeg_processor

            file_path0 = fp.resize_image_smart(image_paths[0])
            refresh_scene_media(scene0, "clip_image", ".webp", file_path0, True)
            self.workflow.write_scene_page_png(scene0, file_path0)

            for i in range(1, len(image_paths)):
                dup = template.copy()
                dup["id"] = self.workflow.max_id(dup) + 1
                self.workflow.scenes.insert(k + i, dup)
                file_i = fp.resize_image_smart(image_paths[i])
                refresh_scene_media(dup, "clip_image", ".webp", file_i, True)
                self.workflow.write_scene_page_png(dup, file_i, force_new_page=True)

            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()
            self.display_image_on_canvas_for_track("clip_image")
            print(
                f"✅ 拖入 {len(image_paths)} 张图：当前场景 + "
                f"{len(image_paths) - 1} 个克隆场景已写入 clip_image"
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", f"多图拖放失败: {e}", parent=self.root)

    def _on_media_drop_multi_clip_images_current_scene(self, image_paths: list[str]) -> None:
        """视频画布拖入多张图（当前场景）：将当前场景克隆 N 份，依次写入各镜 clip_image。"""
        try:
            scene0 = self.workflow.get_scene_by_index(self.current_scene_index)
            if not scene0:
                return
            k = self.current_scene_index
            template = scene0.copy()
            fp = self.workflow.ffmpeg_processor

            self.workflow.scenes.pop(k)
            for i, img_path in enumerate(image_paths):
                dup = template.copy()
                dup["id"] = self.workflow.max_id(dup) + 1
                file_i = fp.resize_image_smart(img_path)
                refresh_scene_media(dup, "clip_image", ".webp", file_i, True)
                self.workflow.scenes.insert(k + i, dup)
                self.workflow.write_scene_page_png(dup, file_i, force_new_page=(i > 0))

            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()
            self.display_image_on_canvas_for_track("clip_image")
            print(
                f"✅ 拖入 {len(image_paths)} 张图：当前场景已拆成 "
                f"{len(image_paths)} 个克隆场景并写入 clip_image"
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", f"多图拖放（当前场景）失败: {e}", parent=self.root)

    def _media_drop_write_clip_audio_slices(
        self, wav_path: str, story_scenes: list, slice_lengths: list[float], *, log_hint: str = ""
    ) -> bool:
        """按 slice_lengths 从 wav_path 顺序切分并写入各场景 clip_audio，并 mux 回 clip 视频。"""
        fa = self.workflow.ffmpeg_audio_processor
        n = len(story_scenes)
        if n == 0 or len(slice_lengths) != n:
            messagebox.showerror("错误", "分片数量与场景不一致", parent=self.root)
            return False
        try:
            duration = float(fa.get_duration(wav_path) or 0.0)
            if duration <= 0.1:
                messagebox.showerror("错误", f"音频时长无效（{duration}s）", parent=self.root)
                return False

            s = float(sum(slice_lengths))
            if s <= 0:
                messagebox.showerror("错误", "分片时长无效", parent=self.root)
                return False
            if abs(s - duration) > 0.02:
                slice_lengths = [float(L) * duration / s for L in slice_lengths]

            offset = 0.0
            for i, scene in enumerate(story_scenes):
                out_len = float(slice_lengths[i])
                if out_len <= 0:
                    messagebox.showerror("错误", f"第 {i + 1}/{n} 段时长无效", parent=self.root)
                    return False
                clip_wav = fa.audio_cut_fade(wav_path, offset, out_len, fade_in=0, fade_out=0)
                if not clip_wav or not os.path.isfile(clip_wav):
                    messagebox.showerror("错误", f"切分第 {i + 1}/{n} 段失败", parent=self.root)
                    return False
                refresh_scene_media(scene, "clip_audio", ".wav", clip_wav, True)
                clip_video = get_file_path(scene, "clip")
                if clip_video:
                    clip_video = self.workflow.ffmpeg_processor.add_audio_to_video(clip_video, clip_wav)
                    refresh_scene_media(scene, "clip", ".mp4", clip_video, True)
                offset += out_len

            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()
            extra = f" {log_hint}" if log_hint else ""
            print(f"✅ 已写入本故事 {n} 个场景 clip_audio（总长 {duration:.2f}s）{extra}".strip())
            return True
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", f"切分 clip_audio 失败: {e}", parent=self.root)
            return False

    def _media_drop_apply_equal_clip_audio_split(self, wav_path: str) -> bool:
        scene_anchor = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene_anchor:
            messagebox.showwarning("提示", "无当前场景", parent=self.root)
            return False
        story_scenes = self.workflow.scenes_in_story(scene_anchor)
        n = len(story_scenes)
        if n == 0:
            messagebox.showwarning("提示", "本故事无场景", parent=self.root)
            return False

        fa = self.workflow.ffmpeg_audio_processor
        duration = float(fa.get_duration(wav_path) or 0.0)
        if duration <= 0.1:
            messagebox.showerror("错误", f"音频时长无效（{duration}s）", parent=self.root)
            return False

        seg = duration / float(n)
        lengths = [seg] * (n - 1)
        lengths.append(max(0.01, duration - seg * (n - 1)))
        return self._media_drop_write_clip_audio_slices(
            wav_path, story_scenes, lengths, log_hint=f"均分，每段约 {seg:.2f}s"
        )

    def _media_drop_apply_ratio_clip_audio_split(self, wav_path: str) -> bool:
        """按各场景现有 clip 音/视频时长比例，将拖入音频切成多段写入 clip_audio。"""
        scene_anchor = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene_anchor:
            messagebox.showwarning("提示", "无当前场景", parent=self.root)
            return False
        story_scenes = self.workflow.scenes_in_story(scene_anchor)
        n = len(story_scenes)
        if n == 0:
            messagebox.showwarning("提示", "本故事无场景", parent=self.root)
            return False

        raw0 = [float(self.workflow.find_clip_duration(s) or 0.0) for s in story_scenes]
        tw0 = sum(raw0)
        if tw0 < 1e-6:
            messagebox.showwarning(
                "提示",
                "各场景现有 clip 音/视频时长均为 0，无法按比例切分，已改为均分。",
                parent=self.root,
            )
            return self._media_drop_apply_equal_clip_audio_split(wav_path)

        raw = [max(r, 1e-6) for r in raw0]
        tw = sum(raw)

        fa = self.workflow.ffmpeg_audio_processor
        duration = float(fa.get_duration(wav_path) or 0.0)
        if duration <= 0.1:
            messagebox.showerror("错误", f"音频时长无效（{duration}s）", parent=self.root)
            return False

        lengths: list[float] = []
        acc = 0.0
        for i in range(n - 1):
            L = duration * (raw[i] / tw)
            lengths.append(L)
            acc += L
        lengths.append(max(0.01, duration - acc))

        pct = ", ".join(f"{100.0 * raw0[i] / tw0:.1f}%" for i in range(n))
        return self._media_drop_write_clip_audio_slices(
            wav_path, story_scenes, lengths, log_hint=f"比例权重 [{pct}]（依各场景现有 clip 时长）"
        )
