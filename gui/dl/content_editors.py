"""ContentEditorsImpl: methods moved verbatim from gui/downloader.py:MediaGUIManager."""
import config_prompt
from utility.file_util import show_auto_close_popup
import project_manager
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
from gui.clipboard_util import _copy_text_to_clipboard
from gui.dl.youtube_dl import _youtube_row_display_title
from gui.dl.program_clipboard import channel_clipboard_append_item
from gui.downloader import _bind_text_editor_replace_from_clipboard_on_double_click, _episode_choice_is_all, _episode_choice_label, _filter_scenes_by_episode


class ContentEditorsImpl:
    def _show_analyzed_content_editor(
        self,
        parent,
        video_detail: dict,
        *,
        on_saved=None,
        on_content_summarized=None,
        enable_content_summary: bool = True,
        persist_fn=None,
    ) -> str | None:
        """编辑 ``video_detail['analyzed_content']``（纯文本）；确认后写回频道列表。"""
        persist = persist_fn or (
            lambda vd, parent=None: self._persist_video_detail_story(vd, parent=parent)
        )
        result_holder: list[str | None] = [None]
        dlg = tk.Toplevel(parent)
        dlg.title("分析内容 / Analyzed")
        dlg.geometry("820x580")
        dlg.minsize(560, 400)
        dlg.transient(parent)
        dlg.grab_set()
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"820x580+{(sw - 820) // 2}+{(sh - 580) // 2}")

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        ttk.Label(
            frm,
            text=(
                f"{title}\n"
                "分析内容 analyzed_content（可编辑；双击编辑区可用剪贴板内容替换全文；"
                "「内容概括」可重新生成；保存后写回本条并保存频道列表）"
            ),
            wraplength=760,
        ).pack(anchor=tk.W, pady=(0, 8))

        tx = scrolledtext.ScrolledText(
            frm, wrap=tk.WORD, width=90, height=24, font=("Arial", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        initial = video_detail.get("analyzed_content")
        if initial:
            tx.insert("1.0", initial)
            _copy_text_to_clipboard(dlg, initial)
        _bind_text_editor_replace_from_clipboard_on_double_click(tx, dlg)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X)

        def on_confirm():
            new_text = tx.get("1.0", tk.END)
            if new_text:
                video_detail["analyzed_content"] = new_text
            else:
                video_detail.pop("analyzed_content", None)
            if not persist(video_detail, parent=dlg):
                return
            result_holder[0] = new_text
            dlg.destroy()
            if callable(on_saved):
                on_saved()

        def on_content_summary():
            try:
                summary_btn.config(state=tk.DISABLED)
                dlg.config(cursor="watch")
                dlg.update_idletasks()
            except tk.TclError:
                pass
            try:
                rewritten = self._generate_analyzed_content_summary_text(
                    video_detail,
                    parent=dlg,
                    source_text=tx.get("1.0", tk.END),
                )
            finally:
                try:
                    summary_btn.config(state=tk.NORMAL)
                    dlg.config(cursor="")
                except tk.TclError:
                    pass
            if not rewritten:
                return
            tx.delete("1.0", tk.END)
            tx.insert("1.0", rewritten)
            video_detail["analyzed_content"] = rewritten
            _copy_text_to_clipboard(dlg, rewritten)
            if not persist(video_detail, parent=dlg):
                return
            if callable(on_content_summarized):
                on_content_summarized()

        if enable_content_summary:
            summary_btn = ttk.Button(
                btn_row, text="内容概括", command=on_content_summary
            )
            summary_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="保存", command=on_confirm).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.wait_window()
        return result_holder[0]

    def _show_poem_editor(
        self,
        parent,
        video_detail: dict,
        *,
        on_saved=None,
        persist_fn=None,
    ) -> str | None:
        """编辑 ``video_detail['poem']``（纯文本）；确认后写回频道列表。"""
        persist = persist_fn or (
            lambda vd, parent=None: self._persist_video_detail_story(vd, parent=parent)
        )
        result_holder: list[str | None] = [None]
        dlg = tk.Toplevel(parent)
        dlg.title("诗歌 / Poem")
        dlg.geometry("820x580")
        dlg.minsize(560, 400)
        dlg.transient(parent)
        dlg.grab_set()
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"820x580+{(sw - 820) // 2}+{(sh - 580) // 2}")

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        ttk.Label(
            frm,
            text=(
                f"{title}\n"
                "诗歌 poem（可编辑；双击编辑区可用剪贴板内容替换全文；"
                "保存后写回本条并保存频道列表）"
            ),
            wraplength=760,
        ).pack(anchor=tk.W, pady=(0, 8))

        tx = scrolledtext.ScrolledText(
            frm, wrap=tk.WORD, width=90, height=24, font=("Arial", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        initial = video_detail.get("poem")
        if initial:
            tx.insert("1.0", initial)
            _copy_text_to_clipboard(dlg, initial)
        _bind_text_editor_replace_from_clipboard_on_double_click(tx, dlg)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X)

        def on_confirm():
            new_text = (tx.get("1.0", tk.END) or "").strip()
            if new_text:
                video_detail["poem"] = new_text
            else:
                video_detail.pop("poem", None)
            if not persist(video_detail, parent=dlg):
                return
            result_holder[0] = new_text
            dlg.destroy()
            if callable(on_saved):
                on_saved()

        ttk.Button(btn_row, text="保存", command=on_confirm).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.wait_window()
        return result_holder[0]

    def _copy_notebooklm_scene_instruction(
        self,
        *,
        parent,
        video_detail: dict,
        scenes: list,
        nb_mode: str,
        main_character: str = "",
        channel_path: str = "",
        scene_index: int = -1,
        visual_style: str = "",
        nb_variant: str = "",
        episode: str = "",
    ) -> bool:
        """scene_content → NotebookLM 导出指令（含图像/视频/口播各子类型）。

        ``episode``：空 / 全部 = 不过滤；否则只带该集的场景。故事、幻灯片、口播都按集过滤。
        ``scene_index``：仅 Video 再往下切一场。-1 为该集全部；0..N-1 为该集内的第几场。
        """
        entries = [e for e in (scenes or []) if isinstance(e, dict)]
        if not entries:
            messagebox.showwarning(
                "无 Scene JSON",
                "请先在编辑区填写有效的 scene_content JSON 数组。",
                parent=parent,
            )
            return False

        try:
            export_base, _export_var = config_prompt.normalize_nb_export_mode(
                nb_mode, nb_variant
            )
        except ValueError:
            export_base = ""

        filtered = _filter_scenes_by_episode(entries, episode)
        ep_label = _episode_choice_label(episode)
        if not filtered:
            messagebox.showwarning(
                "该集没有场景",
                f"第 {ep_label} 集在当前 scene_content 里没有场景。\n"
                "请把集选回「全部」，或改 JSON 里的 episode。",
                parent=parent,
            )
            return False

        image_prompt_only = export_base == "image"
        use_scene_index = export_base == "video"
        idx = scene_index if (use_scene_index and scene_index is not None) else -1
        if idx < 0:
            scene_content = filtered
            if _episode_choice_is_all(episode):
                status_msg = f"已拷贝全部 {len(filtered)} 个场景"
            else:
                status_msg = f"已拷贝第 {ep_label} 集的全部 {len(filtered)} 个场景"
        else:
            if idx >= len(filtered):
                scope = (
                    f"全部场景共 {len(filtered)} 条"
                    if _episode_choice_is_all(episode)
                    else f"第 {ep_label} 集共 {len(filtered)} 条"
                )
                messagebox.showwarning(
                    "场景索引超出范围",
                    f"当前要第 {idx + 1} 个场景，但{scope}。\n"
                    "请点击场按钮调整，或改为 All。",
                    parent=parent,
                )
                return False
            scene_content = [filtered[idx]]
            if _episode_choice_is_all(episode):
                status_msg = f"已拷贝第 {idx + 1} 个场景（共 {len(filtered)} 个）"
            else:
                status_msg = (
                    f"已拷贝第 {ep_label} 集的第 {idx + 1} 个场景"
                    f"（该集共 {len(filtered)} 个）"
                )

        clip_body = config_prompt.build_notebooklm_gen_instruction_clipbody(
            mode=nb_mode,
            variant=nb_variant,
            video_detail=video_detail,
            scene_content=scene_content,
            visual_style=(visual_style or "").strip() or project_manager.LAST_VISUAL_STYLE,
            main_character=(main_character or "").strip(),
            host_narrator=(project_manager.LAST_NARRATOR or "").strip(),
            language=getattr(self, "language", "") or project_manager.LAST_YT_LANGUAGE,
        )

        _copy_text_to_clipboard(parent, clip_body)
        if clip_body and (channel_path or "").strip():
            try:
                base, var = config_prompt.normalize_nb_export_mode(nb_mode, nb_variant)
                export_key = f"{base}/{var}"
            except ValueError:
                export_key = nb_mode
            channel_clipboard_append_item(channel_path, clip_body, export_key)
        if status_msg:
            try:
                title = config_prompt.nb_export_mode_label(nb_mode, nb_variant)
            except ValueError:
                title = nb_mode
            if image_prompt_only:
                status_msg = "已拷贝提示词（不含场景 JSON）"
            show_auto_close_popup(parent, f"Scene → {title}", status_msg)
        return bool(clip_body)

    def open_content_field_editor(
        self,
        parent,
        video_detail: dict,
        field: str,
        *,
        persist_fn=None,
        on_saved=None,
        on_content_summarized=None,
        on_story_title_updated=None,
        main_character: str = "",
        channel_path: str = "",
        embed_in=None,
        on_open_project=None,
        on_regen_project=None,
        on_save_story=None,
        on_resummarize=None,
    ):
        """统一入口：analyzed_content / scene_content 编辑。"""
        if field == "analyzed_content":
            return self._show_analyzed_content_editor(
                parent,
                video_detail,
                on_saved=on_saved,
                on_content_summarized=on_content_summarized,
                persist_fn=persist_fn,
            )
        if field == "scene_content":
            return self._show_scene_content_editor(
                parent,
                video_detail,
                on_saved=on_saved,
                on_title_updated=on_story_title_updated,
                main_character=main_character,
                channel_path=channel_path or self.channel_path or "",
                persist_fn=persist_fn,
                embed_in=embed_in,
                on_open_project=on_open_project,
                on_regen_project=on_regen_project,
                on_save_story=on_save_story,
                on_resummarize=on_resummarize,
            )
        if field == "poem":
            return self._show_poem_editor(
                parent,
                video_detail,
                on_saved=on_saved,
                persist_fn=persist_fn,
            )
        messagebox.showwarning("错误", f"未知字段：{field}", parent=parent)
        return None

    def show_analyzed_content_popup(self, video_detail: dict, *, parent=None) -> None:
        """弹窗只读展示 ``analyzed_content``。"""
        parent = parent or self.root
        ac = video_detail.get("analyzed_content")
        body = (ac if isinstance(ac, str) else str(ac or "")).strip()
        if not body:
            messagebox.showwarning(
                "分析结果",
                "未生成 analyzed_content 或内容为空。",
                parent=parent,
            )
            return
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        top = tk.Toplevel(parent)
        top.title("分析内容 / analyzed content")
        top.minsize(560, 400)
        top.transient(parent)
        top.grab_set()

        hdr = ttk.Frame(top, padding=(12, 10, 12, 0))
        hdr.pack(fill=tk.X)
        ttk.Label(
            hdr,
            text="analyzed_content（只读预览）",
            font=("Arial", 10),
        ).pack(anchor=tk.W)
        ttk.Label(hdr, text=title, wraplength=860, font=("Arial", 11, "bold")).pack(
            anchor=tk.W, pady=(4, 8)
        )

        tx = scrolledtext.ScrolledText(
            top, wrap=tk.WORD, width=100, height=30, font=("Consolas", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        tx.insert("1.0", body)
        tx.configure(state=tk.DISABLED)

        bf = ttk.Frame(top, padding=(12, 0, 12, 12))
        bf.pack(fill=tk.X)

        def _copy():
            try:
                top.clipboard_clear()
                top.clipboard_append(body)
                top.update()
            except tk.TclError:
                pass

        ttk.Button(bf, text="复制全文", command=_copy).pack(side=tk.LEFT)
        ttk.Button(bf, text="关闭", command=top.destroy).pack(side=tk.RIGHT)

        w, h = 900, 640
        top.update_idletasks()
        sw = top.winfo_screenwidth()
        sh = top.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        try:
            top.deiconify()
            top.lift()
            top.focus_force()
            top.attributes("-topmost", True)
            top.after(200, lambda: top.attributes("-topmost", False))
        except tk.TclError:
            pass
        try:
            top.grab_set()
        except tk.TclError:
            pass
        top.protocol("WM_DELETE_WINDOW", top.destroy)
