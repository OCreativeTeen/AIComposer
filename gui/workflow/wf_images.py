"""ImagesMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import json
from io import BytesIO
import config
from PIL import Image, ImageTk
from project_manager import refresh_scene_media
import project_manager
from utility.file_util import show_auto_close_popup
from gui.choice_dialog import post_nested_clipboard_menu
from gui.workflow.wf_common import IMAGE_ACTION_CHOICES, _workflow_channel_display_name


class ImagesMixin:
    def _image_action_choices_for_menu(self) -> dict:
        """视觉框右键菜单：节目名用当前项目 channel 显示名。"""
        channel_name = _workflow_channel_display_name()
        out: dict = {}
        for cat, items in IMAGE_ACTION_CHOICES.items():
            out[cat] = [
                (it.format(channel_name=channel_name) if "{channel_name}" in it else it)
                for it in items
            ]
        return out

    def on_scene_voiceover_image_action_menu(self, event=None):
        """双击右键（视觉框）：IMAGE_ACTION_CHOICES 两级菜单，选中项复制英文指令到剪贴板。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return "break"

        content = config.chinese_convert((scene.get("speaking") or ""), "zh")

        menu_x = menu_y = None
        if event is not None:
            try:
                menu_x = int(event.x_root)
                menu_y = int(event.y_root)
            except (AttributeError, tk.TclError, TypeError, ValueError):
                pass

        return post_nested_clipboard_menu(
            self.root,
            self._image_action_choices_for_menu(),
            "",
            scene.get("actor") or "",
            content,
            event,
            menu_x=menu_x,
            menu_y=menu_y,
        )

    def copy_image_to_clipboard(self, image_path, *, silent=False):
        """将图像复制到 Windows 剪贴板（CF_DIB，供其他应用粘贴）。

        Args:
            image_path: 图像文件路径
            silent: 为 True 时不弹窗（仅 print），用于双击预览时与对话框同时复制
        """
        try:
            if not image_path or not os.path.exists(image_path):
                if not silent:
                    messagebox.showwarning("警告", "图像文件不存在")
                return False

            try:
                import win32clipboard  # type: ignore

                img = Image.open(image_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                output = BytesIO()
                img.save(output, 'BMP')
                data = output.getvalue()[14:]
                output.close()

                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
                win32clipboard.CloseClipboard()

                print(f"✅ 已复制图像到剪贴板: {os.path.basename(image_path)}")
                return True

            except ImportError:
                msg = "需要安装 pywin32 才能复制图像到剪贴板\n请运行: pip install pywin32"
                if not silent:
                    messagebox.showwarning("警告", msg)
                else:
                    print(f"⚠️ {msg}")
                return False

        except Exception as e:
            error_msg = f"复制图像到剪贴板失败: {str(e)}"
            print(f"❌ {error_msg}")
            if not silent:
                messagebox.showerror("错误", error_msg)
            return False

    def _file_paths_from_clipboard(self) -> list[str]:
        """剪贴板里复制的文件路径。图片位图不算。"""
        try:
            from PIL import ImageGrab

            clip = ImageGrab.grabclipboard()
        except Exception:
            return []
        if not isinstance(clip, list):
            return []
        out: list[str] = []
        for item in clip:
            path = os.path.expanduser(str(item).strip().strip('{}"'))
            if os.path.isfile(path):
                out.append(os.path.abspath(path))
        return out

    def _clipboard_mp4_source(self) -> tuple[str, list]:
        """导入片段的「剪贴板」来源：同一目录里复制过来的 mp4。"""
        videos = [path for path in self._file_paths_from_clipboard() if path.lower().endswith(".mp4")]
        if not videos:
            return "", []
        folder = os.path.dirname(videos[0])
        names = [os.path.basename(path) for path in videos if os.path.dirname(path) == folder]
        return folder, names

    def _scene_dict_from_clipboard(self) -> dict | None:
        """剪贴板文字是一场的 JSON，并且带有 visual、speaking、actor 时返回这三项。"""
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            return None
        text = (raw or "").strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(data, list):
            if len(data) != 1 or not isinstance(data[0], dict):
                return None
            data = data[0]
        if not isinstance(data, dict):
            return None
        folded = {str(key).lower(): key for key in data}
        if not all(name in folded for name in ("visual", "speaking", "actor")):
            return None

        def as_text(value) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return " | ".join(str(item) for item in value)
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

        return {
            "visual": as_text(data[folded["visual"]]),
            "speaking": as_text(data[folded["speaking"]]),
            "actor": as_text(data[folded["actor"]]),
        }

    def _confirm_replace_clip_image(self, image_path: str) -> bool:
        """预览剪贴板里的图，问要不要换成当前这一场的 clip 图片。"""
        from PIL import Image, ImageTk

        dlg = tk.Toplevel(self.root)
        dlg.title("替换 clip 图片")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        holder = {"ok": False}
        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="用这张图替换当前这一场的 clip 图片吗？").pack(anchor=tk.W, pady=(0, 8))
        try:
            img = Image.open(image_path)
            img.thumbnail((480, 320), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            img.close()
        except Exception as exc:
            dlg.destroy()
            messagebox.showerror("粘贴", f"这张图打不开：{exc}", parent=self.root)
            return False
        preview = tk.Label(frame, image=photo, bg="gray20")
        preview.image = photo
        preview.pack()
        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(8, 0))

        def accept() -> None:
            holder["ok"] = True
            dlg.destroy()

        ttk.Button(buttons, text="取消", command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="替换", command=accept).pack(side=tk.RIGHT, padx=(0, 6))
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.grab_set()
        dlg.wait_window()
        return holder["ok"]

    def _merge_clipboard_scene_content(self, payload: dict) -> None:
        """把剪贴板里的 visual、speaking、actor 写进当前这一场，其它字段不动。"""
        self.update_current_scene()
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None
        if not isinstance(scene, dict):
            messagebox.showwarning("粘贴", "没有当前场景。", parent=self.root)
            return
        scene["visual"] = payload.get("visual") or ""
        scene["speaking"] = payload.get("speaking") or ""
        scene["actor"] = project_manager.normalize_actor_text(payload.get("actor") or "")
        self.workflow.save_scenes_to_json()
        self.update_scene_display()
        show_auto_close_popup(
            self.root,
            "本场内容",
            "已把剪贴板里的场景描述、讲话和人物合并进这一场。",
            duration_ms=2000,
        )

    def _on_video_canvas_double_click(self, _event=None):
        """大画面双击：拷贝当前这一场的 clip 图片。"""
        try:
            self._copy_preview_slot_image("clip_image")
        except Exception as exc:
            messagebox.showerror("复制", str(exc), parent=self.root)
        return "break"

    def _on_video_canvas_paste(self, _event=None):
        """大画面 Ctrl+V：图片替换 clip 图片，场景 JSON 合并内容，mp4 打开导入片段。"""
        try:
            images = self._image_paths_from_clipboard()
            if images:
                if self._confirm_replace_clip_image(images[0]):
                    self._apply_image_paths_to_preview_slot("clip_image", images[:1])
                return "break"
            videos = self._clipboard_mp4_source()[1]
            if videos:
                self.choose_import_video(initial_source="clipboard")
                return "break"
            payload = self._scene_dict_from_clipboard()
            if payload is not None:
                if messagebox.askyesno(
                    "粘贴本场内容",
                    "剪贴板里是一场的内容，带有场景描述、讲话和人物。\n要合并进当前这一场吗？",
                    parent=self.root,
                ):
                    self._merge_clipboard_scene_content(payload)
                return "break"
            show_auto_close_popup(
                self.root,
                "粘贴",
                "剪贴板里没有图片、场景内容或视频。",
                duration_ms=2000,
            )
        except Exception as exc:
            messagebox.showerror("粘贴", str(exc), parent=self.root)
        return "break"

    def _image_paths_from_clipboard(self) -> list[str]:
        """从系统剪贴板读取图片：位图或文件路径列表。"""
        image_ext = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
        try:
            from PIL import ImageGrab

            clip = ImageGrab.grabclipboard()
        except Exception:
            return []
        if clip is None:
            return []
        if isinstance(clip, list):
            out: list[str] = []
            for p in clip:
                ps = os.path.expanduser(str(p).strip().strip('{}"'))
                if os.path.isfile(ps) and ps.lower().endswith(image_ext):
                    out.append(os.path.abspath(ps))
            return out
        if hasattr(clip, "save"):
            pid = getattr(self.workflow, "pid", None) or "clipboard"
            tmp_png = config.get_temp_file(pid, "png")
            os.makedirs(os.path.dirname(tmp_png) or ".", exist_ok=True)
            img = clip
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img.save(tmp_png, format="PNG")
            return [tmp_png]
        return []

    def _preview_track_title(self, image_type: str) -> str:
        base = image_type[: -len("_last")] if str(image_type).endswith("_last") else image_type
        return {"clip_image": "Clip", "narration_image": "Narration", "zero_image": "Zero"}.get(base, base)

    def _ask_preview_image_action(self, image_type: str, has_clip: bool, has_video: bool) -> str | None:
        is_last = str(image_type).endswith("_last")
        index = self.current_scene_index
        total = len(self.workflow.scenes) if getattr(self, "workflow", None) else 0
        neighbor_ok = index < total - 1 if is_last else index > 0
        title = self._preview_track_title(image_type)
        slot = "结束图" if is_last else "起始图"
        shift_label = "结束图挪到起始，新图放结束" if is_last else "起始图挪到结束，新图放起始"
        neighbor_label = (
            f"用下一场的{title}起始图替换这里"
            if is_last
            else f"用上一场的{title}结束图替换这里"
        )
        frame_label = (
            f"用这条{title}视频的尾帧替换这里"
            if is_last
            else f"用这条{title}视频的首帧替换这里"
        )
        dlg = tk.Toplevel(self.root)
        dlg.title(slot)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        holder = {"choice": None}
        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=f"这张{title}{slot}怎么处理？").pack(anchor=tk.W, pady=(0, 8))

        def choose(action: str) -> None:
            holder["choice"] = action
            dlg.destroy()

        clip_state = tk.NORMAL if has_clip else tk.DISABLED
        neighbor_state = tk.NORMAL if neighbor_ok else tk.DISABLED
        video_state = tk.NORMAL if has_video else tk.DISABLED
        ttk.Button(frame, text="用剪贴板的图替换这里", state=clip_state, command=lambda: choose("replace")).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text=shift_label, state=clip_state, command=lambda: choose("shift")).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text=neighbor_label, state=neighbor_state, command=lambda: choose("neighbor")).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text=frame_label, state=video_state, command=lambda: choose("frame")).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="取消", command=dlg.destroy).pack(fill=tk.X, pady=(8, 0))
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.grab_set()
        dlg.wait_window()
        return holder["choice"]

    def on_image_canvas_paste_from_clipboard(self, event, image_type):
        """右键双击：替换、挪到另一端、拿相邻一场的图，或从这条视频抓首帧/尾帧。"""
        try:
            paths = self._image_paths_from_clipboard()
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            track = str(image_type).split("_")[0]
            video_path = (scene or {}).get(track) or ""
            has_video = bool(video_path and os.path.isfile(video_path))
            action = self._ask_preview_image_action(image_type, bool(paths), has_video)
            if action == "shift":
                self._shift_preview_slot_image(image_type, paths)
            elif action == "replace":
                self._apply_image_paths_to_preview_slot(image_type, paths)
            elif action == "neighbor":
                self._take_neighbor_preview_image(image_type)
            elif action == "frame":
                self._take_track_video_frame(image_type)
        except Exception as e:
            messagebox.showerror("粘贴失败", str(e), parent=self.root)
        return "break"

    def _take_track_video_frame(self, image_type: str) -> None:
        """起始图用这条视频的首帧，结束图用尾帧。抽帧和缩放与导入视频时写末帧相同。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return
        is_last = str(image_type).endswith("_last")
        track = str(image_type).split("_")[0]
        video_path = scene.get(track) or ""
        if not video_path or not os.path.isfile(video_path):
            messagebox.showinfo("放入", "这条轨道没有视频。", parent=self.root)
            return
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            frame = self.workflow.ffmpeg_processor.extract_frame(video_path, not is_last)
            if not frame:
                messagebox.showinfo("放入", "这一帧没有抽出来。", parent=self.root)
                return
            frame = self.workflow.ffmpeg_processor.resize_image_smart(frame)
            if not frame:
                messagebox.showinfo("放入", "这一帧没有缩放好。", parent=self.root)
                return
            refresh_scene_media(scene, image_type, ".webp", frame)
            self._pool_clip_slot_image(scene, image_type, scene.get(image_type) or frame)
            self.workflow.save_scenes_to_json()
            self.display_image_on_canvas_for_track(image_type)
            done_text = "已用这条视频的尾帧换上" if is_last else "已用这条视频的首帧换上"
            if image_type == "clip_image":
                self._after_clip_image_changed(scene, done_text + "，并加进了本集图片库。")
            else:
                show_auto_close_popup(self.root, "放入", done_text)
        finally:
            try:
                self.root.config(cursor="")
            except tk.TclError:
                pass

    def _take_neighbor_preview_image(self, image_type: str) -> None:
        """起始图用上一场的结束图。结束图用下一场的起始图。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return
        is_last = str(image_type).endswith("_last")
        base = image_type[: -len("_last")] if is_last else image_type
        if is_last:
            other = self.workflow.get_next_scene(self.current_scene_index)
            source_key = base
            empty = "下一场没有这张起始图。"
        else:
            other = self.workflow.get_previous_scene(self.current_scene_index)
            source_key = base + "_last"
            empty = "上一场没有这张结束图。"
        if not other:
            messagebox.showinfo("放入", "旁边没有场景。", parent=self.root)
            return
        source = other.get(source_key) or ""
        if not source or not os.path.isfile(source):
            messagebox.showinfo("放入", empty, parent=self.root)
            return
        refresh_scene_media(scene, image_type, ".webp", source, True)
        self._pool_clip_slot_image(scene, image_type, scene.get(image_type) or source)
        self.workflow.save_scenes_to_json()
        self.display_image_on_canvas_for_track(image_type)
        if image_type == "clip_image":
            self._after_clip_image_changed(scene, "已用旁边那场的图换上，并加进了本集图片库。")
        else:
            show_auto_close_popup(self.root, "放入", "已用旁边那场的图换上")

    def _shift_preview_slot_image(self, image_type: str, img_paths: list[str]) -> None:
        """起始：旧起始挪到结束，新图放起始。结束：旧结束挪到起始，新图放结束。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("放入", "没有当前场景。", parent=self.root)
            return
        if not img_paths:
            return
        is_last = str(image_type).endswith("_last")
        if is_last:
            start_key = image_type[: -len("_last")]
            last_key = image_type
        else:
            start_key = image_type
            last_key = image_type + "_last"
        file_path = self.workflow.ffmpeg_processor.resize_image_smart(img_paths[0])
        if not file_path or not os.path.isfile(file_path):
            messagebox.showerror("放入", "新图没有处理好。", parent=self.root)
            return
        if is_last:
            old_path = scene.get(last_key) or ""
            if old_path and os.path.isfile(old_path):
                refresh_scene_media(scene, start_key, ".webp", old_path, True)
                self._pool_clip_slot_image(scene, start_key, scene.get(start_key) or old_path)
            refresh_scene_media(scene, last_key, ".webp", file_path, True)
            self._pool_clip_slot_image(scene, last_key, scene.get(last_key) or file_path)
        else:
            old_path = scene.get(start_key) or ""
            if old_path and os.path.isfile(old_path):
                refresh_scene_media(scene, last_key, ".webp", old_path, True)
            refresh_scene_media(scene, start_key, ".webp", file_path, True)
            self._pool_clip_slot_image(scene, start_key, file_path)
        self.workflow.save_scenes_to_json()
        self.display_image_on_canvas_for_track(start_key)
        self.display_image_on_canvas_for_track(last_key)
        if start_key == "clip_image":
            self._after_clip_image_changed(
                scene, "已把旧图挪到另一端，新图放在你点的这一格，并加进了本集图片库。"
            )
        else:
            show_auto_close_popup(self.root, "放入", "已把旧图挪到另一端，新图放在你点的这一格")

    def _copy_preview_slot_image(self, image_type: str) -> None:
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            return
        image_path = current_scene.get(image_type)
        if image_path and os.path.exists(image_path):
            self.copy_image_to_clipboard(image_path, silent=True)
            show_auto_close_popup(
                self.root,
                "剪贴板",
                f"已拷贝 {os.path.basename(image_path)}",
                duration_ms=1000,
            )
            return
        if image_type != "clip_image":
            messagebox.showwarning(
                "警告", f"场景中没有有效的 {image_type} 图像", parent=self.root
            )

    def on_image_canvas_click(self, event, image_type):
        """单击：把当前槽位的图拷到剪贴板。双击会先取消这次拷贝。"""
        if getattr(event, "state", 0) & 0x4:
            return
        pending = getattr(self, "_image_click_after", None)
        if pending is not None:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
        self._image_click_after = self.root.after(
            280, lambda t=image_type: self._run_preview_image_copy(t)
        )

    def _run_preview_image_copy(self, image_type: str) -> None:
        self._image_click_after = None
        try:
            self._copy_preview_slot_image(image_type)
        except Exception as e:
            messagebox.showerror("复制", str(e), parent=self.root)

    def on_image_canvas_double_click(self, event, image_type):
        """双击 Clip Image：只打开本集 PDF 页面预览，不拷贝。"""
        pending = getattr(self, "_image_click_after", None)
        if pending is not None:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
            self._image_click_after = None
        if image_type != "clip_image":
            try:
                self._copy_preview_slot_image(image_type)
            except Exception as e:
                messagebox.showerror("复制", str(e), parent=self.root)
            return
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not current_scene:
                return
            self._open_clip_image_pdf_review(current_scene)
        except Exception as e:
            messagebox.showerror("错误", f"打开页面预览失败: {e}", parent=self.root)

    def _open_clip_image_pdf_review(self, scene: dict) -> None:
        """本集 PDF 已拆则直接审阅；还没拆就先拆进 media/<episode>/ 再审阅。"""
        pdf_path = self._resolve_scene_episode_pdf(scene)
        group_name = self.workflow.scene_group(scene)
        pages = self._episode_page_pngs(group_name)
        folder = os.path.join(config.get_media_path(self.workflow.pid), group_name)
        if not pdf_path and not pages:
            messagebox.showinfo(
                "页图",
                f"第 {group_name} 集没有 PDF，也没有拆好的页面图。\n"
                "先把 PDF 拖到视频画布上，再双击这里翻页。",
                parent=self.root,
            )
            return
        if not pdf_path:
            pdf_path = self.workflow.episode_pdf_path(group_name)
        if not pages:
            try:
                self.root.config(cursor="watch")
                self.root.update_idletasks()
                folder, pages = self.workflow.export_pdf_pages_to_group(pdf_path, group_name)
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("页图", f"拆分失败：{e}", parent=self.root)
                return
            finally:
                try:
                    self.root.config(cursor="")
                except tk.TclError:
                    pass
        if not pages:
            messagebox.showwarning("页图", "这份 PDF 没有拆出页面。", parent=self.root)
            return
        # 只是翻页查看，不整理页码：PDF 有几页就能看几页，不受本集场数限制。
        pages = self._episode_page_pngs(group_name)
        start_idx = 0
        try:
            page_no = int(scene.get("episode_page") or 0)
        except (TypeError, ValueError):
            page_no = 0
        if page_no > 0:
            for i, path in enumerate(pages):
                stem = os.path.splitext(os.path.basename(path))[0]
                if stem.isdigit() and int(stem) == page_no:
                    start_idx = i
                    break
        self._open_pdf_page_review(
            folder, pages, group_name, os.path.basename(pdf_path), initial_index=start_idx
        )

    @staticmethod
    def _is_approx_16_9_landscape(w: int | None, h: int | None) -> bool:
        if w is None or h is None or h <= 0 or w <= h:
            return False
        r = w / h
        return abs(r - 16.0 / 9.0) < 0.08

    _MOSAIC_PREVIEW_MAX_W = 720

    _MOSAIC_SHIFT_STEP = 8

    _MOSAIC_SHIFT_STEP_FINE = 1

    def _review_mosaic_layer_crop_dialog(
        self,
        image_path: str,
        index_1based: int,
        total: int,
        stage_w: int,
        stage_h: int,
        bottom_trim_px: int,
    ) -> tuple[int, int] | None:
        """返回 ``(图源偏移, 条带视窗偏移)``；取消 ``None``。16∶9 图源通常仅条带视窗可调（1152→1080 等）。"""
        fp = self.workflow.ffmpeg_processor
        try:
            min_src, max_src = fp.mosaic_crop_shift_limits(image_path, stage_w, stage_h)
        except OSError as e:
            messagebox.showerror("拼图预览", f"无法读取图片：{e}", parent=self.root)
            return None
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("拼图预览", f"{type(e).__name__}: {e}", parent=self.root)
            return None

        try:
            out_w = int(fp.width)
        except (TypeError, ValueError):
            out_w = 1080

        min_vp, max_vp = fp.mosaic_viewport_shift_limits(stage_w, out_w)
        src_can_pan = min_src < max_src
        vp_can_pan = min_vp < max_vp

        state = {"src": 0, "vp": 0}
        result: dict[str, tuple[int, int] | None] = {"v": None}
        photo_holder = {"ph": None}

        def clamp_src(v: int) -> int:
            return max(min_src, min(max_src, int(v)))

        def clamp_vp(v: int) -> int:
            return max(min_vp, min(max_vp, int(v)))

        dlg = tk.Toplevel(self.root)
        dlg.title(f"拼图裁切 — 第 {index_1based}/{total} 张")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        main = ttk.Frame(dlg, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        hint_extra = ""
        if src_can_pan:
            hint_extra = "图源有余量时：Ctrl+←/→ 或「图源左/右」。"
        if not vp_can_pan and not src_can_pan:
            hint_extra = "（本张无可平移余量。）"

        ttk.Label(
            main,
            text=(
                f"{os.path.basename(image_path)}\n"
                f"条带 {stage_w}×{stage_h}（底裁 {bottom_trim_px}px）→ 成片宽 {out_w}px。\n"
                f"← / →：在条带内移动 {out_w}px 视窗（Shift=1px）。{hint_extra}"
            ),
            justify=tk.CENTER,
            wraplength=680,
        ).pack(pady=(0, 6))

        status_var = tk.StringVar()

        def update_status() -> None:
            parts = [f"条带视窗: {state['vp']} px  （[{min_vp}, {max_vp}]）"]
            if src_can_pan:
                parts.append(f"图源: {state['src']} px  （[{min_src}, {max_src}]）")
            status_var.set("    ".join(parts))

        preview_host = tk.Frame(
            main,
            takefocus=True,
            highlightthickness=2,
            highlightbackground="#666",
            highlightcolor="#333",
            bd=0,
        )
        preview_host.pack(pady=4)

        img_label = ttk.Label(preview_host)
        img_label.pack(padx=4, pady=4)

        def _focus_preview(_event=None) -> None:
            try:
                preview_host.focus_set()
            except tk.TclError:
                pass

        img_label.bind("<Button-1>", _focus_preview)
        preview_host.bind("<Button-1>", _focus_preview)

        ttk.Label(main, textvariable=status_var, font=("Arial", 10)).pack(pady=(4, 4))

        nudge_row = ttk.Frame(main)
        nudge_row.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(nudge_row, text="视窗：" if vp_can_pan else ("图源：" if src_can_pan else "平移：")).pack(
            side=tk.LEFT, padx=(0, 4)
        )

        def refresh_preview() -> None:
            try:
                tile = fp.prep_mosaic_source_layer(
                    image_path,
                    stage_w,
                    stage_h,
                    bottom_trim_px,
                    shift_x=state["src"],
                )
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("预览", str(e), parent=dlg)
                return
            tw, th = tile.size
            if tw > out_w:
                x0 = (tw - out_w) // 2 + state["vp"]
                x0 = max(0, min(x0, tw - out_w))
                view = tile.crop((x0, 0, x0 + out_w, th))
            else:
                view = tile
            vw, vh = view.size
            max_w = WorkflowGUI._MOSAIC_PREVIEW_MAX_W
            if vw > max_w:
                scale = max_w / vw
                disp = view.resize(
                    (max_w, max(1, int(round(vh * scale)))),
                    Image.Resampling.LANCZOS,
                )
            else:
                disp = view
            photo_holder["ph"] = ImageTk.PhotoImage(disp)
            img_label.configure(image=photo_holder["ph"])
            update_status()

        def _step(event) -> int:
            step = WorkflowGUI._MOSAIC_SHIFT_STEP
            if event is not None and (event.state & 0x0001):
                step = WorkflowGUI._MOSAIC_SHIFT_STEP_FINE
            return step

        def nudge_viewport(delta: int, event=None) -> str | None:
            if not vp_can_pan:
                return "break"
            state["vp"] = clamp_vp(state["vp"] + (delta * _step(event)))
            refresh_preview()
            return "break"

        def nudge_source(delta: int, event=None) -> str | None:
            if not src_can_pan:
                return "break"
            state["src"] = clamp_src(state["src"] + (delta * _step(event)))
            refresh_preview()
            return "break"

        def on_arrow_left(e) -> str | None:
            ctrl = (e.state & 0x0004) != 0
            if ctrl and src_can_pan:
                return nudge_source(-1, e)
            if vp_can_pan:
                return nudge_viewport(-1, e)
            if src_can_pan:
                return nudge_source(-1, e)
            return "break"

        def on_arrow_right(e) -> str | None:
            ctrl = (e.state & 0x0004) != 0
            if ctrl and src_can_pan:
                return nudge_source(1, e)
            if vp_can_pan:
                return nudge_viewport(1, e)
            if src_can_pan:
                return nudge_source(1, e)
            return "break"

        def on_reset() -> None:
            state["src"] = 0
            state["vp"] = 0
            refresh_preview()

        def on_ok() -> None:
            result["v"] = (state["src"], state["vp"])
            dlg.destroy()

        def on_cancel() -> None:
            dlg.destroy()

        if vp_can_pan:
            ttk.Button(nudge_row, text="← 左", width=6, command=lambda: nudge_viewport(-1)).pack(
                side=tk.LEFT, padx=2
            )
            ttk.Button(nudge_row, text="右 →", width=6, command=lambda: nudge_viewport(1)).pack(
                side=tk.LEFT, padx=2
            )
        elif src_can_pan:
            ttk.Button(nudge_row, text="← 左", width=6, command=lambda: nudge_source(-1)).pack(
                side=tk.LEFT, padx=2
            )
            ttk.Button(nudge_row, text="右 →", width=6, command=lambda: nudge_source(1)).pack(
                side=tk.LEFT, padx=2
            )

        if vp_can_pan and src_can_pan:
            src_row = ttk.Frame(main)
            src_row.pack(fill=tk.X, pady=(0, 4))
            ttk.Label(src_row, text="图源：").pack(side=tk.LEFT, padx=(0, 4))
            ttk.Button(src_row, text="图源←", width=8, command=lambda: nudge_source(-1)).pack(
                side=tk.LEFT, padx=2
            )
            ttk.Button(src_row, text="图源→", width=8, command=lambda: nudge_source(1)).pack(
                side=tk.LEFT, padx=2
            )

        btn_f = ttk.Frame(main)
        btn_f.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_f, text="复原（双归零）", command=on_reset).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_f, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btn_f, text="确定", command=on_ok).pack(side=tk.RIGHT)

        def _bind_arrows_recursive(wid: tk.Misc) -> None:
            wid.bind("<Left>", on_arrow_left)
            wid.bind("<Right>", on_arrow_right)
            for ch in wid.winfo_children():
                _bind_arrows_recursive(ch)

        _bind_arrows_recursive(dlg)

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        refresh_preview()
        dlg.update_idletasks()
        dlg.geometry(
            "+{}+{}".format(
                (dlg.winfo_screenwidth() - dlg.winfo_reqwidth()) // 2,
                (dlg.winfo_screenheight() - dlg.winfo_reqheight()) // 2,
            )
        )
        dlg.after_idle(_focus_preview)
        dlg.wait_window()
        return result["v"]

    def _apply_image_paths_to_preview_slot(self, image_type: str, img_paths: list[str]) -> None:
        """将一张或多张图片写入预览槽（拖放与剪贴板粘贴共用）。"""
        if not img_paths:
            messagebox.showerror("错误", "无有效图片", parent=self.root)
            return

        fp = self.workflow.ffmpeg_processor
        pc = project_manager.PROJECT_CONFIG or {}
        try:
            vw = int(pc.get('video_width') or fp.width)
            vh = int(pc.get('video_height') or fp.height)
        except (TypeError, ValueError):
            vw, vh = fp.width, fp.height

        mosaic_mode = None  # "triple" | "dual"

        portrait_mosaic_canvas = vw == 1080 and vh == 1920

        def _dims_ok_for_mosaic(ipath: str) -> tuple[int | None, int | None]:
            return fp.get_resolution(ipath)

        if portrait_mosaic_canvas and len(img_paths) >= 3:
            d0 = _dims_ok_for_mosaic(img_paths[0])
            d1 = _dims_ok_for_mosaic(img_paths[1])
            d2 = _dims_ok_for_mosaic(img_paths[2])
            if (
                WorkflowGUI._is_approx_16_9_landscape(*d0)
                and WorkflowGUI._is_approx_16_9_landscape(*d1)
                and WorkflowGUI._is_approx_16_9_landscape(*d2)
            ):
                mosaic_mode = "triple"

        if portrait_mosaic_canvas and mosaic_mode is None and len(img_paths) >= 2:
            d0 = _dims_ok_for_mosaic(img_paths[0])
            d1 = _dims_ok_for_mosaic(img_paths[1])
            if WorkflowGUI._is_approx_16_9_landscape(*d0) and WorkflowGUI._is_approx_16_9_landscape(*d1):
                mosaic_mode = "dual"

        if len(img_paths) >= 2 and portrait_mosaic_canvas and mosaic_mode is None:
            messagebox.showwarning(
                "竖屏拼图",
                "当前项目为 1080×1920：双图/三图拼接需对应张数均为横向约 16∶9 的图片。\n已对第一张做单图缩放处理。",
                parent=self.root,
            )

        if len(img_paths) > 1 and not portrait_mosaic_canvas:
            messagebox.showinfo(
                "拖放多张图",
                f"检测到 {len(img_paths)} 张图；仅首张将写入（拼图仅适用于 1080×1920 竖屏项目）。",
                parent=self.root,
            )

        if mosaic_mode == "triple" and len(img_paths) > 3:
            messagebox.showinfo(
                "三图拼接",
                f"已使用前 3 张图做竖屏顶对齐拼接；其余 {len(img_paths) - 3} 张未使用。",
                parent=self.root,
            )

        if mosaic_mode == "dual" and len(img_paths) > 2:
            extra = (
                "第三张未同时满足拼图条件或未参与。"
                if len(img_paths) >= 3 and portrait_mosaic_canvas
                else f"其余 {len(img_paths) - 2} 张未使用。"
            )
            messagebox.showinfo(
                "双图拼接",
                f"已使用前 2 张图做竖屏拼接。{extra}",
                parent=self.root,
            )

        if mosaic_mode == "triple":
            sw, sh, btrim = 1152, 648, 20
            shifts_src: list[int] = []
            shifts_vp: list[int] = []
            for i in range(3):
                pair = self._review_mosaic_layer_crop_dialog(
                    img_paths[i], i + 1, 3, sw, sh, btrim
                )
                if pair is None:
                    return
                shifts_src.append(pair[0])
                shifts_vp.append(pair[1])
            file_path = fp.compose_triple_landscape_vertical_mosaic_webp(
                img_paths[0],
                img_paths[1],
                img_paths[2],
                horizontal_crop_shifts=shifts_src,
                viewport_crop_shifts=shifts_vp,
            )
            file_path = self._apply_watermark_to_flat_image_webp(file_path)
        elif mosaic_mode == "dual":
            sw, sh, btrim = 1440, 810, 25
            shifts_src = []
            shifts_vp = []
            for i in range(2):
                pair = self._review_mosaic_layer_crop_dialog(
                    img_paths[i], i + 1, 2, sw, sh, btrim
                )
                if pair is None:
                    return
                shifts_src.append(pair[0])
                shifts_vp.append(pair[1])
            file_path = fp.compose_dual_landscape_vertical_mosaic_webp(
                img_paths[0],
                img_paths[1],
                horizontal_crop_shifts=shifts_src,
                viewport_crop_shifts=shifts_vp,
            )
            file_path = self._apply_watermark_to_flat_image_webp(file_path)
        else:
            file_path = fp.resize_image_smart(img_paths[0])

        if not os.path.exists(file_path):
            messagebox.showerror("错误", "文件不存在", parent=self.root)
            return

        selected_scens = [self.workflow.get_scene_by_index(self.current_scene_index)]
        if not image_type.startswith('clip'):
            dialog = messagebox.askyesno("确认替换", f"确定要替换所有当前故事的 {image_type} 吗？")
            if dialog:
                selected_scens = self.workflow.scenes_in_story(
                    self.workflow.get_scene_by_index(self.current_scene_index)
                )

        for scene in selected_scens:
            refresh_scene_media(scene, image_type, ".webp", file_path, True)
            self._pool_clip_slot_image(scene, image_type, file_path)

        self.workflow.save_scenes_to_json()
        self.display_image_on_canvas_for_track(image_type)
        print(f"✅ 已更新 {image_type}: {os.path.basename(file_path)}")
        if image_type == "clip_image" and selected_scens and selected_scens[0]:
            self._after_clip_image_changed(selected_scens[0], "已换上新的 clip 图片，并加进了本集图片库。")

    def display_image_on_canvas_for_track(self, image_type):
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not current_scene:
                return

            canvas_mapping = {
                'clip_image': (self.clip_image_canvas, "Clip\nImage", '_clip_image_photo'),
                'clip_image_last': (self.clip_image_last_canvas, "Clip\nLast", '_clip_image_last_photo'),
                "narration_image": (self.narration_image_canvas, "Narration\nImage", '_narration_image_photo'),
                "narration_image_last": (self.narration_image_last_canvas, "Narration\nLast", '_narration_image_last_photo'),
                'zero_image': (self.zero_image_canvas, "Zero\nImage", '_zero_image_photo'),
                'zero_image_last': (self.zero_image_last_canvas, "Zero\nLast", '_zero_image_last_photo'),
            }
            
            if image_type not in canvas_mapping:
                return
            
            image_path = current_scene.get(image_type)
            if not image_path or not os.path.exists(image_path):
                # take the first part string from image_type
                video_type = image_type.split("_")[0]
                video_path = current_scene.get(video_type)
                if video_path and os.path.exists(video_path):
                    if image_type.endswith("_last"):
                        image_path = self.workflow.ffmpeg_processor.extract_frame(video_path, False)
                    else:    
                        image_path = self.workflow.ffmpeg_processor.extract_frame(video_path, True)
                    oldi, image_path = refresh_scene_media(current_scene, image_type, ".webp", image_path)
                else:
                    return
            
            canvas, label, photo_attr = canvas_mapping[image_type]
            canvas.delete("all")
            
            from PIL import Image, ImageTk
            img = Image.open(image_path)
            
            canvas.update_idletasks()
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width, canvas_height = 150, 75
            
            img_width, img_height = img.size
            aspect_ratio = img_width / img_height
            
            margin = 5
            available_width = canvas_width - margin
            available_height = canvas_height - margin
            
            if available_width / available_height > aspect_ratio:
                new_height = available_height
                new_width = int(new_height * aspect_ratio)
            else:
                new_width = available_width
                new_height = int(new_width / aspect_ratio)
            
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_resized)
            
            x = canvas_width // 2
            y = canvas_height // 2
            canvas.create_image(x, y, image=photo, anchor=tk.CENTER, tags="image")
            
            setattr(self, photo_attr, photo)
            
            #print(f"✅ 已显示  {image_type}: {os.path.basename(image_path)}")
            
        except Exception as e:
            print(f"❌ 显示图片失败 ({image_type}): {e}")

    def load_all_images_preview(self):
        try:
            self.load_video_first_frame()

            self.display_image_on_canvas_for_track('clip_image')
            self.display_image_on_canvas_for_track('clip_image_last')
            self.display_image_on_canvas_for_track("narration_image")
            self.display_image_on_canvas_for_track("narration_image_last")
            self.display_image_on_canvas_for_track('zero_image')
            self.display_image_on_canvas_for_track('zero_image_last')

            # 根据当前选中的tab加载轨道视频预览
            current_tab_index = self.narration_notebook.index(self.narration_notebook.select())
            if current_tab_index == 0:
                self.load_secondary_track_first_frame()
            elif current_tab_index == 1:
                self.load_pip_lr_first_frame()

        except Exception as e:
            print(f"❌ 加载图片预览失败: {e}")

    def _replace_current_clip_image_from_pil(self, pil_img) -> None:
        """图片提示的手动窗口贴回了一张图：写成当前场景的 clip_image，并刷新预览。"""
        import tempfile

        if pil_img is None or not hasattr(pil_img, "save"):
            return
        if not self.workflow:
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not isinstance(scene, dict):
            messagebox.showwarning("图片提示", "没有当前场景，返回的图没有写入。", parent=self.root)
            return
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            pil_img.save(tmp_path)
            file_path = self.workflow.ffmpeg_processor.resize_image_smart(tmp_path)
        except Exception as exc:
            messagebox.showerror("图片提示", f"返回的图没有写入 clip 图片：{exc}", parent=self.root)
            return
        finally:
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        if not file_path or not os.path.isfile(file_path):
            messagebox.showerror("图片提示", "返回的图没有写成文件。", parent=self.root)
            return
        refresh_scene_media(scene, "clip_image", ".webp", file_path, True)
        self._pool_clip_slot_image(scene, "clip_image", file_path)
        self.workflow.save_scenes_to_json()
        self.display_image_on_canvas_for_track("clip_image")
        print(f"✅ 图片提示已更新 clip_image: {os.path.basename(scene.get('clip_image') or file_path)}")
        self._after_clip_image_changed(scene, "图片提示返回的图已换成这一场的 clip 图片，并加进了本集图片库。")

    def _frame_or_fallback(self, video_path: str, first: bool):
        img = self.workflow.ffmpeg_processor.extract_frame(video_path, first)
        if img:
            return img
        try:
            channel = None
            if project_manager.PROJECT_CONFIG:
                channel = project_manager.PROJECT_CONFIG.get("channel")
            channel = channel or getattr(self.workflow, "channel", None)
            if not channel:
                return None
            fp = self.workflow.ffmpeg_processor
            fallback = config.get_fallback_background_image(channel, fp.width, fp.height)
            if fallback and os.path.exists(fallback):
                return fp.to_webp(fallback)
        except Exception as exc:
            print(f"fallback frame failed: {exc}")
        return None


# verbatim references to WorkflowGUI.<attr> in the methods above resolve to this mixin
WorkflowGUI = ImagesMixin
