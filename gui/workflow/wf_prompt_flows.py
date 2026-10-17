"""PromptFlowsMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.messagebox as messagebox
import os
import json
import config
from project_manager import save_project_config
import project_manager
from utility.file_util import show_auto_close_popup


class PromptFlowsMixin:
    def _project_cover_and_slide(self) -> tuple[str, str]:
        from gui.downloader import _find_gen_video_slide_for_row, _find_gen_video_webp_for_row

        pc = project_manager.PROJECT_CONFIG or {}
        row = self._current_feature_row()
        cover = ""
        slide = ""
        for src in (pc, row):
            if not isinstance(src, dict):
                continue
            stored_cover = project_manager.get_primary_cover_image(src)
            stored_slide = (src.get("slide") or "").strip()
            if not cover and stored_cover:
                cover = stored_cover
            if not slide and stored_slide and os.path.isfile(stored_slide):
                slide = os.path.abspath(stored_slide)
        if not cover:
            cover = _find_gen_video_webp_for_row(row) or ""
        if not slide:
            slide = _find_gen_video_slide_for_row(row) or ""
        return cover, slide

    def _cover_prompt_context(self) -> tuple[object | None, dict, str, str]:
        mgr = getattr(self, "youtube_gui", None)
        vd = self._current_feature_row()
        cover, slide = self._project_cover_and_slide()
        if cover:
            vd["cover_image"] = cover
        if slide:
            vd["slide"] = slide
        sc = vd.get("scene_content") or []
        story_raw = json.dumps(sc, ensure_ascii=False, indent=2) if isinstance(sc, list) and sc else ""
        ch = (getattr(self.workflow, "channel", None) or "").strip()
        ch_path = config.get_channel_path(config.get_channel_id(ch)) if ch else ""
        if mgr is not None:
            ch_path = ch_path or getattr(mgr, "channel_path", "")
        return mgr, vd, story_raw, ch_path

    def _open_picture_prompt_flow(self) -> None:
        """图片提示：画风改变 + 叙事风格，再在手动窗口里拷当前图和提示词。"""
        from gui.picture_prompt_dialog import open_picture_prompt_dialog

        if not self.workflow or not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning("图片提示", "没有当前场景", parent=self.root)
            return

        def current_scene():
            self.update_current_scene()
            if not self.workflow:
                return None
            return self.workflow.get_scene_by_index(self.current_scene_index)

        pc = project_manager.PROJECT_CONFIG or {}

        def get_style() -> str:
            return (
                (self.scene_visual_style.get() or "").strip()
                or (pc.get("visual_style") or "").strip()
                or ""
            )

        def get_place() -> tuple:
            return (
                (self.setting_region.get() or "").strip(),
                (self.setting_era.get() or "").strip(),
            )

        def save_choice(choice: dict) -> None:
            cfg = project_manager.PROJECT_CONFIG
            if not isinstance(cfg, dict) or cfg.get("picture_prompt") == choice:
                return
            cfg["picture_prompt"] = choice
            save_project_config(parent=self.root)

        def open_manual(prompt: str, images: list[str]) -> None:
            def _on_image_response(pil_img):
                self._replace_current_clip_image_from_pil(pil_img)

            self.llm_api.show_manual_window(
                prompt, "", images=images, on_image_response=_on_image_response
            )

        open_picture_prompt_dialog(
            self.root,
            self._nb_picture_btn,
            get_scene=current_scene,
            get_style=get_style,
            get_place=get_place,
            open_manual=open_manual,
            host_narrator=project_manager.project_narrator(),
            saved_choice=(project_manager.PROJECT_CONFIG or {}).get("picture_prompt"),
            save_choice=save_choice,
        )

    def _place_popup_near(self, dlg: tk.Toplevel, anchor, *, below: bool) -> None:
        """把弹出窗口放在锚点旁边。below 为真时放在下面，否则放在上面，不挡住锚点。"""
        dlg.withdraw()
        dlg.update_idletasks()
        try:
            anchor.update_idletasks()
            ax = int(anchor.winfo_rootx())
            ay = int(anchor.winfo_rooty())
            aw = max(int(anchor.winfo_width()), 1)
            ah = max(int(anchor.winfo_height()), 1)
        except (tk.TclError, TypeError, ValueError):
            ax = int(self.root.winfo_rootx()) + int(self.root.winfo_width()) - 480
            ay = int(self.root.winfo_rooty()) + 80
            aw, ah = 80, 28
        w = max(int(dlg.winfo_reqwidth()), 200)
        h = max(int(dlg.winfo_reqheight()), 80)
        sw = int(dlg.winfo_screenwidth())
        sh = int(dlg.winfo_screenheight())
        gap = 8
        if below:
            x = ax
            y = ay + ah + gap
            if y + h > sh - 8:
                y = max(8, ay - h - gap)
        else:
            x = ax + aw - w
            y = ay - h - gap
            if y < 8:
                y = min(max(8, sh - h - 8), ay + ah + gap)
        x = max(8, min(x, max(8, sw - w - 8)))
        y = max(8, min(y, max(8, sh - h - 8)))
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.deiconify()
        try:
            dlg.lift()
        except tk.TclError:
            pass

    def _open_video_prompt_flow(self) -> None:
        """视频提示：先选叙事风格、画面、背景、演进，再在手动窗口里拷画面和提示词。"""
        from gui.video_prompt_dialog import open_video_prompt_dialog

        if not self.workflow or not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning("视频提示", "没有当前场景", parent=self.root)
            return

        def current_scene():
            self.update_current_scene()
            if not self.workflow:
                return None
            return self.workflow.get_scene_by_index(self.current_scene_index)

        def get_image(key: str) -> str:
            scene = current_scene()
            path = scene.get(key) if isinstance(scene, dict) else ""
            if isinstance(path, str) and path and os.path.isfile(path):
                return path
            return ""

        def copy_text(text: str) -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()

        pc = project_manager.PROJECT_CONFIG or {}

        def get_style() -> str:
            return (
                (self.scene_visual_style.get() or "").strip()
                or (pc.get("visual_style") or "").strip()
                or config.VISUAL_STYLE_OPTIONS[0]
            )

        def _on_video_image_response(pil_img):
            _mgr, vd, _story_raw, ch_path = self._cover_prompt_context()
            if not isinstance(vd, dict):
                return
            ch = (getattr(self.workflow, "channel", None) or "").strip()
            from gui.downloader import save_pil_image_to_cover_array
            ok, dest, _err = save_pil_image_to_cover_array(
                pil_img,
                vd,
                channel=ch,
                filename_hint="video_prompt",
            )
            if ok and dest:
                project_manager.save_project_config()
                show_auto_close_popup(
                    self.root,
                    "视频提示",
                    f"返回的图片已保存到封面列表：\n{os.path.basename(dest)}",
                )

        def _video_download_dir() -> str:
            """导入视频「下载」来源看的目录：用户 Downloads（存在时），否则项目 download 文件夹。"""
            from gui.workflow.wf_common import _user_downloads_folder

            folder = _user_downloads_folder()
            if folder and os.path.isdir(folder):
                return folder
            folder = config.get_project_path(self.workflow.pid) + "/download"
            os.makedirs(folder, exist_ok=True)
            return folder

        def _on_video_file_response(path: str) -> None:
            """CLI自动 生成的 mp4：打开导入视频，来源=下载，片段列表预选这个文件（不自动导入）。"""
            if not path or not os.path.isfile(path):
                return
            show_auto_close_popup(self.root, "生场视频", f"视频已下载：\n{os.path.basename(path)}")
            self.root.after(
                200,
                lambda: self.choose_import_video(initial_source="download", preselect_file=os.path.basename(path)),
            )

        def save_video_choice(choice: dict) -> None:
            cfg = project_manager.PROJECT_CONFIG
            if not isinstance(cfg, dict) or cfg.get("video_prompt") == choice:
                return
            cfg["video_prompt"] = choice
            save_project_config(parent=self.root)

        open_video_prompt_dialog(
            self.root,
            self._nb_story_video_btn,
            get_scenes=lambda: [s for s in [current_scene()] if isinstance(s, dict)],
            get_style=get_style,
            copy_text=copy_text,
            language=getattr(self.workflow, "language", "") or "",
            host_narrator=project_manager.project_narrator(),
            get_place=lambda: (
                (self.setting_region.get() or "").strip(),
                (self.setting_era.get() or "").strip(),
            ),
            get_image=get_image,
            copy_image=lambda path: bool(self.copy_image_to_clipboard(path, silent=True)),
            open_manual=lambda prompt, images, extra=None: self.llm_api.show_manual_window(
                prompt, "", images=images, on_image_response=_on_video_image_response,
                cli_kind="video", file_dest_dir=_video_download_dir(),
                on_file_response=_on_video_file_response, extra=extra,
            ),
            saved_choice=(project_manager.PROJECT_CONFIG or {}).get("video_prompt"),
            save_choice=save_video_choice,
            simple_actions=[
                ("仅当前场景", lambda: self._run_clip_video("still", "single")),
                ("本集从这一场起", lambda: self._run_clip_video("still", "story")),
                ("全部场景", lambda: self._run_clip_video("still", "all")),
                ("WAN 生成（以后再用）", lambda: self._run_clip_video("wan", "single")),
            ],
        )

    def _open_slide_prompt_flow(self) -> None:
        """全集生成：只取当前场景所在这一集的场景，选叙事风格后拷提示词。"""
        from gui.slide_prompt_dialog import open_slide_prompt_dialog

        self.update_current_scene()
        if not self.workflow or not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning("全集生成", "没有当前场景", parent=self.root)
            return

        def episode_scenes() -> list:
            self.update_current_scene()
            if not self.workflow:
                return []
            cur = self.workflow.get_scene_by_index(self.current_scene_index)
            if not isinstance(cur, dict):
                return []
            return [s for s in self.workflow.scenes_in_story(cur) if isinstance(s, dict)]

        def copy_text(text: str) -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()

        pc = project_manager.PROJECT_CONFIG or {}

        def get_style() -> str:
            return (
                (self.scene_visual_style.get() or "").strip()
                or (pc.get("visual_style") or "").strip()
                or config.VISUAL_STYLE_OPTIONS[0]
            )

        def get_place() -> tuple:
            return (
                (self.setting_region.get() or "").strip(),
                (self.setting_era.get() or "").strip(),
            )

        def save_choice(choice: dict) -> None:
            cfg = project_manager.PROJECT_CONFIG
            if not isinstance(cfg, dict) or cfg.get("slide_prompt") == choice:
                return
            cfg["slide_prompt"] = choice
            save_project_config(parent=self.root)

        def open_slides_manual(prompt: str, kind: str = "slides", notebook_url: str = "", source_pdf: str = "") -> None:
            """提交：手工 LLM 窗口 CLI自动 → NotebookLM Studio（kind）→ 下载 → 系统程序打开。"""
            import os
            from pathlib import Path

            working = r"D:\AI_MEDIA\working"

            def _open_file(path: str) -> None:
                """Studio 下载结果移到 D:\\AI_MEDIA\\working（同名覆盖）。PDF 走拆页预览 / 分配；其余直接打开。"""
                import shutil

                try:
                    os.makedirs(working, exist_ok=True)
                    dest = os.path.join(working, os.path.basename(path))
                    if os.path.abspath(dest) != os.path.abspath(path):
                        if os.path.exists(dest):
                            os.remove(dest)
                        shutil.move(path, dest)
                    path = dest
                except OSError as exc:
                    print(f"⚠️ 移动到 working 失败，用原位置：{exc}")
                if path.lower().endswith(".pdf"):
                    self.root.after(50, lambda p=path: self._on_media_drop_pdf(p))
                    return
                try:
                    os.startfile(path)
                except OSError as exc:
                    messagebox.showwarning("打开失败", f"打不开：{exc}\n{path}", parent=self.root)

            extra = {"output": kind}
            if notebook_url:
                extra["notebook_url"] = notebook_url
            if source_pdf:
                extra["source_pdf"] = source_pdf  # CLI自动：先上传为笔记本来源，再生成
            self.llm_api.show_manual_window(
                prompt, "", auto_cli=True, cli_kind=kind or "slides",
                file_dest_dir=working, on_file_response=_open_file, extra=extra,
            )

        open_slide_prompt_dialog(
            self.root,
            getattr(self, "_slide_prompt_btn", None),
            saved_choice=(project_manager.PROJECT_CONFIG or {}).get("slide_prompt"),
            save_choice=save_choice,
            get_scenes=episode_scenes,
            get_style=get_style,
            copy_text=copy_text,
            host_narrator=project_manager.project_narrator(),
            get_place=get_place,
            main_character="",
            open_manual=open_slides_manual,
        )
