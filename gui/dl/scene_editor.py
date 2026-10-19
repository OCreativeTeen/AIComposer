"""SceneEditorImpl: methods moved verbatim from gui/downloader.py:MediaGUIManager."""
import os
import json
import config
import config_channel
import config_prompt
from utility.file_util import safe_copy_overwrite, safe_clipboard_json_copy, show_auto_close_popup
import project_manager
try:
    from tkinterdnd2 import DND_FILES
    import tkinterdnd2 as _tkinterdnd2

    _TKINTER_DND_TK = _tkinterdnd2.Tk
    _TK_DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    _tkinterdnd2 = None  # type: ignore
    _TKINTER_DND_TK = None
    _TK_DND_AVAILABLE = False
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
from tkinter import filedialog
from utility.file_util import _is_plain_text_file_path, _media_kind_for_path, _read_plain_text_file
from utility.tags_text import _strip_markdown_embedded_images
from utility.scene_json import _parse_scene_json_list
from gui.raise_window import _raise_own_window
from gui.clipboard_util import _copy_file_to_clipboard_hdrop, _copy_text_to_clipboard, _dnd_normalize_file_paths
from gui.dl.youtube_dl import _youtube_row_display_title, _youtube_row_source_title
from gui.dl.list_store import GEN_VIDEO_SLIDE_KEY, _find_gen_video_slide_for_row
from gui.dl.gen_video_files import STORY_MEDIA_KEY, STORY_TRANSCRIPT_KEY, _find_gen_video_webp_for_row, _find_item_media_file, _find_item_transcript_file, _gen_video_slide_pdf_dest_filename, _item_transcript_text
from gui.downloader import _apply_scene_lm_combo, _bind_text_editor_replace_from_clipboard_on_double_click, _episode_choice_label, _episode_ids_in_scenes, _filter_scenes_by_episode, _fit_story_summary_window, _image_material_override, _media_material_override, _open_cover_image_for_row, _pdf_pages_as_scene_source, _pdf_scene_generation_instruction, _project_look_from_row, _prompt_choice_entries, _prompt_text_for_material, apply_scene_content_from_editor_text, ask_download_slide_pdf, save_cover_image_as_gen_video_webp, save_pil_image_to_cover_array


class SceneEditorImpl:
    def _show_scene_content_editor(
        self,
        parent,
        video_detail: dict,
        *,
        on_saved=None,
        on_title_updated=None,
        main_character: str = "",
        channel_path: str = "",
        persist_fn=None,
        embed_in=None,
        on_open_project=None,
        on_regen_project=None,
        on_save_story=None,
        on_resummarize=None,
    ) -> list | None:
        """编辑 ``video_detail['scene_content']``（JSON array）；确认后写回频道列表。"""
        persist = persist_fn or (
            lambda vd, parent=None: self._persist_video_detail_story(vd, parent=parent)
        )
        result_holder: list[list | None] = [None]
        embedded = embed_in is not None
        if not embedded:
            existing = getattr(self, "_scene_content_dialog", None)
            if existing is not None:
                try:
                    if existing.winfo_exists():
                        from gui.cli_bridge import is_screen_bound

                        if is_screen_bound(config.SCREEN_STORY_SCENE):
                            _raise_own_window(existing)
                            return None
                        try:
                            existing.destroy()
                        except tk.TclError:
                            pass
                        self._scene_content_dialog = None
                except tk.TclError:
                    self._scene_content_dialog = None
            dlg = tk.Toplevel(parent)
            self._scene_content_dialog = dlg
            dlg.title("SCENE")
            dlg.geometry("980x930")
            dlg.minsize(980, 930)
            # 非模态：允许切回摘要窗 / 列表等其它窗口（勿 grab_set / transient）
            dlg.update_idletasks()
            sw = dlg.winfo_screenwidth()
            sh = dlg.winfo_screenheight()
            dlg.geometry(f"980x930+{(sw - 980) // 2}+{(sh - 930) // 2}")
            frm = tk.Frame(dlg, padx=12, pady=12, bg="#f0f0f0")
            frm.pack(fill=tk.BOTH, expand=True)
        else:
            dlg = parent
            self._scene_content_dialog = dlg
            frm = tk.Frame(embed_in, padx=4, pady=2, bg="#f0f0f0")
            # Only the materials panel expands inside frm; it gets the spare height.
            frm.pack(fill=tk.BOTH, expand=True)

        def _dismiss_scene_window() -> None:
            if embedded:
                return
            try:
                dlg.destroy()
            except tk.TclError:
                pass
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        short = title[:48].rstrip() + ("…" if len(title) > 48 else "")
        if not embedded:
            dlg.title(f"SCENE | {short}")

        def _raise_scene_dialog() -> None:
            _raise_own_window(dlg)

        loading_lbl = tk.Label(
            frm,
            text="正在加载 SCENE 编辑器…",
            bg="#f0f0f0",
            fg="#222222",
            font=("Arial", 12),
            anchor=tk.W,
        )
        loading_lbl.pack(anchor=tk.W, pady=(0, 8))
        _raise_scene_dialog()

        from gui.cli_bridge import bind_screen as _bind_scene_early, unbind_screen as _unbind_scene_early

        def _stub_cancel():
            _unbind_scene_early(config.SCREEN_STORY_SCENE)
            if getattr(self, "_scene_content_dialog", None) is dlg:
                self._scene_content_dialog = None
            _dismiss_scene_window()

        # ready=False: the bridge reports "still building" instead of timing out
        # while the (large) editor body is created on the next Tk tick.
        _bind_scene_early(
            config.SCREEN_STORY_SCENE,
            dlg,
            {"cancel": {"click": _stub_cancel}},
            ready=False,
        )

        scene_ui: dict = {}

        def _build_editor_ui():
            channel_key = self._channel_config_key()
            nb_prompt_choices = _prompt_choice_entries(channel_key)
            prompt_row = ttk.Frame(frm)
            prompt_row.pack(fill=tk.X, pady=(0, 6))
            default_prompt_label = _prompt_choice_entries(channel_key)[0][0]
            prompt_combo_var = tk.StringVar(value=default_prompt_label)
            prompt_combo = ttk.Combobox(
                prompt_row,
                textvariable=prompt_combo_var,
                values=[opt[0] for opt in nb_prompt_choices],
                state="readonly" if nb_prompt_choices else "disabled",
                width=28,
            )
            prompt_combo.pack(side=tk.LEFT, padx=(0, 8))
            # Step Story：步数；直接生成系列节目：共 N 集 / 第 k 集。只在选中对应模板时显示。
            step_count_var = tk.StringVar(value=str(config_channel.STEP_STORY_DEFAULT))
            step_frm = ttk.Frame(prompt_row)
            step_lbl = ttk.Label(step_frm, text="步数")
            step_lbl.pack(side=tk.LEFT, padx=(0, 2))
            step_count_combo = ttk.Combobox(
                step_frm,
                textvariable=step_count_var,
                values=[
                    str(i)
                    for i in range(config_channel.STEP_STORY_MIN, config_channel.STEP_STORY_MAX + 1)
                ],
                state="readonly",
                width=3,
            )
            step_count_combo.pack(side=tk.LEFT)
            series_total_var = tk.StringVar(value=str(config_channel.SERIES_DIRECT_DEFAULT_EPISODES))
            series_ep_var = tk.StringVar(value="1")
            series_frm = ttk.Frame(prompt_row)
            ttk.Label(series_frm, text="共").pack(side=tk.LEFT, padx=(0, 2))
            series_total_combo = ttk.Combobox(
                series_frm,
                textvariable=series_total_var,
                values=[str(i) for i in range(1, config_channel.SERIES_DIRECT_MAX_EPISODES + 1)],
                state="readonly",
                width=3,
            )
            series_total_combo.pack(side=tk.LEFT)
            ttk.Label(series_frm, text="集  第").pack(side=tk.LEFT, padx=(2, 2))
            series_ep_combo = ttk.Combobox(
                series_frm, textvariable=series_ep_var, state="readonly", width=3
            )
            series_ep_combo.pack(side=tk.LEFT)
            ttk.Label(series_frm, text="集").pack(side=tk.LEFT, padx=(2, 0))

            def _int_of(var, default: int) -> int:
                try:
                    return int((var.get() or "").strip())
                except (TypeError, ValueError):
                    return default

            def _sync_series_episode_choices(*_a):
                n = max(1, _int_of(series_total_var, config_channel.SERIES_DIRECT_DEFAULT_EPISODES))
                series_ep_combo.configure(values=[str(i) for i in range(1, n + 1)])
                if _int_of(series_ep_var, 1) > n:
                    series_ep_var.set(str(n))

            _sync_series_episode_choices()
            series_total_var.trace_add("write", _sync_series_episode_choices)

            # 步数下拉两用：Step Story = 共几场（默认 3），图片分解 = 取第几步（默认 1）；各自记住自己的值。
            _step_memory = {"story": str(config_channel.STEP_STORY_DEFAULT), "image": "1"}
            _step_kind = [None]

            def _sync_dynamic_prompt_widgets(*_a):
                sel = (prompt_combo_var.get() or "").strip()
                kind = (
                    "image" if config_channel.is_step_image_label(sel)
                    else "story" if config_channel.is_step_story_label(sel)
                    else None
                )
                if kind != _step_kind[0]:
                    if _step_kind[0] is not None:
                        _step_memory[_step_kind[0]] = step_count_var.get() or _step_memory[_step_kind[0]]
                    if kind is not None:
                        step_count_var.set(_step_memory[kind])
                    _step_kind[0] = kind
                step_frm.pack_forget()
                series_frm.pack_forget()
                if config_channel.is_step_story_label(sel) or config_channel.is_step_image_label(sel):
                    # Step Story：共几场；图片分解：取图里的第几步
                    step_lbl.configure(
                        text="第几步" if config_channel.is_step_image_label(sel) else "步数"
                    )
                    step_frm.pack(side=tk.LEFT, padx=(0, 8), after=prompt_combo)
                elif config_channel.is_series_direct_label(sel):
                    series_frm.pack(side=tk.LEFT, padx=(0, 8), after=prompt_combo)

            prompt_combo_var.trace_add("write", _sync_dynamic_prompt_widgets)
            _sync_dynamic_prompt_widgets()
            action_bar = ttk.Frame(prompt_row)
            action_bar.pack(side=tk.LEFT, fill=tk.X, expand=not embedded, padx=(12, 0))
            scene_ui["action_bar"] = action_bar

            material_var = tk.StringVar(value="analyzed")
            pdf_layout_var = tk.StringVar(value="ai")
            pdf_source_cache = {"path": "", "text": "", "pages": 0, "has_text": False}
            material_row = ttk.Frame(frm)
            material_row.pack(fill=tk.X, pady=(0, 6))
            ttk.Label(material_row, text="材料").pack(side=tk.LEFT, padx=(0, 8))
            btn_analyzed = tk.Button(
                material_row,
                text="分析报告",
                width=8,
                relief=tk.SUNKEN,
                bd=1,
            )
            btn_analyzed.pack(side=tk.LEFT, padx=(0, 4))
            # PDF / 图片 / 媒体 三个按钮合并成一个「材料」区（下面的列表），拖进来的文件按类型分流。
            btn_materials = tk.Button(
                material_row,
                text="材料",
                relief=tk.RAISED,
                bd=1,
            )
            btn_materials.pack(side=tk.LEFT, padx=(0, 8))
            slide_info_var = None
            drop_ctx = getattr(dlg, "_summary_drop_ctx", None)
            if isinstance(drop_ctx, dict):
                slide_info_var = drop_ctx.get("feature_media_var")
            scene_count_var = slide_info_var if slide_info_var is not None else tk.StringVar(value="")
            scene_count_lbl = ttk.Label(material_row, textvariable=scene_count_var)
            scene_count_lbl.pack(side=tk.LEFT, padx=(4, 4))
            ttk.Separator(material_row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=28)
            smart_slot = ttk.Frame(material_row)
            smart_slot.pack(side=tk.LEFT, padx=(4, 0))
            scene_ui["smart_slot"] = smart_slot
            pdf_layout_combo = ttk.Combobox(
                material_row,
                state="readonly",
                width=28,
                values=["由 AI 判断场数", "每一页一个场景"],
            )
            pdf_layout_combo.set("每一页一个场景")

            material_preview = scrolledtext.ScrolledText(
                frm, wrap=tk.WORD, width=100, height=10, font=("Arial", 10)
            )
            material_preview.pack(fill=tk.X, expand=False, pady=(0, 8))

            def _copy_slide_pdf():
                slide = (_find_gen_video_slide_for_row(video_detail) or "").strip()
                if _copy_file_to_clipboard_hdrop(dlg, slide):
                    show_auto_close_popup(
                        dlg,
                        "已复制",
                        f"PDF 已复制到剪贴板，可以粘贴到 AI 工具：\n{os.path.basename(slide)}",
                    )

            _analyzed_edit = {"text": None, "reload": False}

            def _analyzed_widget_text() -> str:
                raw = (material_preview.get("1.0", "end-1c") or "").strip()
                if raw == "（这一条没有分析报告）":
                    return ""
                hint = "双击这里，把分析报告拷到剪贴板。"
                if raw.endswith(hint):
                    raw = raw[: -len(hint)].strip()
                return raw

            def _read_analyzed_draft():
                """分析报告正在显示时返回编辑区文字；正在看 PDF 或媒体时返回切走前记下的草稿。"""
                if material_var.get() != "analyzed":
                    return _analyzed_edit["text"]
                return _analyzed_widget_text()

            if embedded and isinstance(drop_ctx, dict):
                drop_ctx["read_analyzed_draft"] = _read_analyzed_draft

                def _reload_analyzed_draft():
                    _analyzed_edit["text"] = None
                    _analyzed_edit["reload"] = True

                drop_ctx["reload_analyzed_draft"] = _reload_analyzed_draft

            def _copy_analyzed_text():
                text = _analyzed_widget_text()
                if not text and material_var.get() != "analyzed":
                    raw = video_detail.get("analyzed_content") or ""
                    text = raw.strip() if isinstance(raw, str) else str(raw).strip()
                if not text.strip():
                    show_auto_close_popup(dlg, "分析报告", "这一条没有分析报告。")
                    return
                _copy_text_to_clipboard(dlg, text)
                show_auto_close_popup(dlg, "已复制", "分析报告已拷到剪贴板。")

            def _on_material_preview_double(_event=None):
                if material_var.get() == "image":
                    if (_find_gen_video_webp_for_row(video_detail) or "").strip():
                        _open_cover_image_for_row(dlg, video_detail)
                    else:
                        _pick_cover_image()
                    return "break"
                if material_var.get() == "pdf":
                    _copy_slide_pdf()
                elif material_var.get() == "media":
                    media_path = _find_item_media_file(video_detail)
                    if not media_path:
                        show_auto_close_popup(dlg, "媒体", "这一条还没有音频或视频。")
                    else:
                        target = media_path
                        transcript_path = _find_item_transcript_file(video_detail)
                        if transcript_path:
                            from utility import media_transcript

                            choice = media_transcript.ask_copy_choice(
                                dlg, os.path.basename(media_path), os.path.basename(transcript_path)
                            )
                            if not choice:
                                return "break"
                            if choice == "transcript":
                                target = transcript_path
                        if _copy_file_to_clipboard_hdrop(dlg, target):
                            show_auto_close_popup(
                                dlg,
                                "已复制",
                                f"文件已拷到剪贴板，可以粘贴到别处：\n{os.path.basename(target)}",
                            )
                else:
                    _copy_analyzed_text()
                return "break"

            material_preview.bind("<Double-Button-1>", _on_material_preview_double)

            def _on_material_preview_key(_event=None):
                if material_var.get() in ("pdf", "media", "image"):
                    return "break"

            material_preview.bind("<Key>", _on_material_preview_key)

            def _pdf_layout_mode() -> str:
                shown = (pdf_layout_combo.get() or "").strip()
                return "page" if shown.startswith("每一页") else "ai"

            def _remember_pdf_source(path: str | None = None) -> dict:
                slide = (path if path is not None else _find_gen_video_slide_for_row(video_detail) or "").strip()
                if slide and slide == pdf_source_cache["path"]:
                    return pdf_source_cache
                text, pages, has_text = _pdf_pages_as_scene_source(slide) if slide else ("", 0, False)
                pdf_source_cache["path"] = slide
                pdf_source_cache["text"] = text
                pdf_source_cache["pages"] = pages
                pdf_source_cache["has_text"] = has_text
                return pdf_source_cache

            def _fill_material_preview():
                slide = (_find_gen_video_slide_for_row(video_detail) or "").strip()
                on_pdf = material_var.get() == "pdf"
                if not _analyzed_edit["reload"]:
                    current = (material_preview.get("1.0", "end-1c") or "").strip()
                    pdfish = (
                        "双击这里，把这份 PDF" in current
                        or current.startswith("还没有图文 PDF")
                        or current.startswith("音频：")
                        or current.startswith("视频：")
                        or current.startswith("还没有媒体")
                        or current.startswith("封面图片：")
                        or current.startswith("还没有封面图片")
                    )
                    if current and not pdfish:
                        kept = current
                        if kept == "（这一条没有分析报告）":
                            kept = ""
                        hint = "双击这里，把分析报告拷到剪贴板。"
                        if kept.endswith(hint):
                            kept = kept[: -len(hint)].strip()
                        _analyzed_edit["text"] = kept
                _analyzed_edit["reload"] = False
                material_preview.configure(state=tk.NORMAL)
                material_preview.delete("1.0", tk.END)
                if material_var.get() in ("pdf", "image", "media"):
                    _show_materials(True)
                    materials_panel.refresh(material_var.get())
                    return
                _show_materials(False)
                if on_pdf and slide:
                    cached = _remember_pdf_source(slide)
                    pages = int(cached.get("pages") or 0)
                    material_preview.insert(
                        "1.0",
                        f"{os.path.basename(slide)}\n共 {pages} 页\n\n"
                        "双击这里，把这份 PDF 拷到剪贴板。\n"
                        "双击上面的 PDF 按钮，可以从下载文件夹换一份 PDF，或按顺序把图片合成 PDF。",
                    )
                elif on_pdf:
                    material_preview.insert(
                        "1.0",
                        "还没有图文 PDF。\n\n"
                        "双击上面的 PDF 按钮，从下载文件夹选择一份 PDF，"
                        "或按点击顺序选择图片，合成一份 PDF。",
                    )
                elif material_var.get() == "image":
                    img = (_find_gen_video_webp_for_row(video_detail) or "").strip()
                    if img:
                        material_preview.insert(
                            "1.0",
                            f"封面图片：{os.path.basename(img)}\n{img}\n\n"
                            "双击这里，打开这张图片。\n"
                            "双击上面的图片按钮，可以换一张图片。",
                        )
                    else:
                        material_preview.insert(
                            "1.0",
                            "还没有封面图片。\n\n双击上面的「（没有图片）」按钮，选一张图片挂到这一条。",
                        )
                elif material_var.get() == "media":
                    media_path = _find_item_media_file(video_detail)
                    kind = _media_kind_for_path(media_path)
                    transcript_path = _find_item_transcript_file(video_detail)
                    transcript_line = (
                        f"文字稿：{os.path.basename(transcript_path)}\n" if transcript_path else ""
                    )
                    if media_path and kind == "audio":
                        material_preview.insert(
                            "1.0",
                            f"音频：{os.path.basename(media_path)}\n{transcript_line}\n"
                            "双击这里，把这个音频文件拷到剪贴板。\n"
                            "再拖一个音频或 mp4 进来，会换掉这一个。",
                        )
                    elif media_path and kind == "video":
                        material_preview.insert(
                            "1.0",
                            f"视频：{os.path.basename(media_path)}\n{transcript_line}\n"
                            "双击这里，把这个视频文件拷到剪贴板。\n"
                            "再拖一个音频或 mp4 进来，会换掉这一个。",
                        )
                    else:
                        material_preview.insert(
                            "1.0",
                            "还没有媒体。\n\n"
                            "把音频（mp3、wav、m4a 等）或 mp4 拖到这里。"
                            "一条只保留一个媒体文件，新的会换掉原来的。",
                        )
                else:
                    if _analyzed_edit["text"] is not None:
                        text = _analyzed_edit["text"]
                    else:
                        raw = video_detail.get("analyzed_content") or ""
                        text = raw.strip() if isinstance(raw, str) else str(raw).strip()
                    body, removed = _strip_markdown_embedded_images(text)
                    if removed and _analyzed_edit["text"] is None:
                        video_detail["analyzed_content"] = body
                        _analyzed_edit["text"] = body
                        try:
                            persist(video_detail, parent=dlg)
                        except Exception:
                            pass
                    if body:
                        material_preview.insert("1.0", body)

            def _pdf_button_caption() -> str:
                slide = (_find_gen_video_slide_for_row(video_detail) or "").strip()
                if not slide:
                    return "（没有 PDF）"
                return os.path.basename(slide)

            def _image_button_caption() -> str:
                img = (_find_gen_video_webp_for_row(video_detail) or "").strip()
                if not img:
                    return "（没有图片）"
                name = os.path.basename(img)
                return name if len(name) <= 22 else name[:21] + "…"

            def _media_button_caption() -> str:
                media_path = _find_item_media_file(video_detail)
                if not media_path:
                    return "媒体"
                name = os.path.basename(media_path)
                if len(name) > 22:
                    name = name[:21] + "…"
                return name

            def _paint_material_buttons():
                mode = material_var.get()
                btn_analyzed.configure(
                    relief=tk.SUNKEN if mode == "analyzed" else tk.RAISED,
                    bg="#d7e6f8" if mode == "analyzed" else "#f3f3f3",
                )
                in_materials = mode in ("pdf", "image", "media")
                if in_materials:
                    _last_material[0] = mode
                btn_materials.configure(
                    text=_materials_button_caption(),
                    state=tk.NORMAL,
                    relief=tk.SUNKEN if in_materials else tk.RAISED,
                    bg="#d7e6f8" if in_materials else "#f3f3f3",
                )

            def _import_slide_pdf(pdf_path: str) -> None:
                temp_made = os.path.basename(pdf_path).startswith("aicomposer_slide_")
                try:
                    _text, page_count, _has_text = _pdf_pages_as_scene_source(pdf_path)
                    if page_count <= 0:
                        messagebox.showwarning("PDF", "这份 PDF 没有页面。", parent=dlg)
                        return
                    try:
                        gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
                        if not gen_dir:
                            raise OSError("没有 gen_video 目录")
                        os.makedirs(gen_dir, exist_ok=True)
                        dest = os.path.join(
                            gen_dir, _gen_video_slide_pdf_dest_filename(video_detail)
                        )
                        safe_copy_overwrite(pdf_path, dest)
                        video_detail[GEN_VIDEO_SLIDE_KEY] = os.path.abspath(dest)
                    except Exception as exc:
                        messagebox.showerror("PDF", f"无法保存这份 PDF：\n{exc}", parent=dlg)
                        return
                    pdf_source_cache["path"] = ""
                    material_var.set("pdf")
                    _sync_material_widgets()
                    drop_ctx = getattr(dlg, "_summary_drop_ctx", None)
                    refresh_media = (
                        drop_ctx.get("refresh_feature_media_row")
                        if isinstance(drop_ctx, dict)
                        else None
                    )
                    if callable(refresh_media):
                        refresh_media()
                    persist(video_detail, parent=dlg)
                    note = f"这份 PDF 已挂到这一条（{page_count} 页）。"
                    if "series" in (prompt_combo_var.get() or "").lower():
                        note += "\n\n系列提示词可以在材料旁边选择：每一页一个场景，或由 AI 判断场数。"
                    show_auto_close_popup(dlg, "PDF", note)
                finally:
                    if temp_made and pdf_path and os.path.isfile(pdf_path):
                        try:
                            os.remove(pdf_path)
                        except OSError:
                            pass

            scene_ui["import_slide_pdf"] = _import_slide_pdf

            def _import_analyzed_text_file(text_path: str) -> None:
                try:
                    text = (_read_plain_text_file(text_path) or "").strip()
                except OSError as exc:
                    messagebox.showerror("文本", f"读不了这个文件：\n{exc}", parent=dlg)
                    return
                if not text:
                    messagebox.showwarning("文本", "这个文件是空的。", parent=dlg)
                    return
                ext = os.path.splitext(text_path)[1].lower()
                removed = 0
                if ext in (".md", ".markdown"):
                    text, removed = _strip_markdown_embedded_images(text)
                    if not text:
                        messagebox.showwarning("文本", "去掉嵌入图片之后，这个文件没有正文了。", parent=dlg)
                        return
                video_detail["analyzed_content"] = text
                _analyzed_edit["text"] = text
                _analyzed_edit["reload"] = True
                material_var.set("analyzed")
                _sync_material_widgets()
                persist(video_detail, parent=dlg)
                note = f"已用这个文件替换分析报告：\n{os.path.basename(text_path)}"
                if removed:
                    note += f"\n\n嵌入图片已去掉（{removed} 处），没有写进分析报告。"
                show_auto_close_popup(dlg, "分析报告", note)

            def _import_item_media(src_path: str) -> None:
                kind = _media_kind_for_path(src_path)
                if not kind:
                    return
                channel_dir = (self.channel_path or "").strip()
                if not channel_dir:
                    messagebox.showerror("媒体", "没有频道目录，不能保存这个文件。", parent=dlg)
                    return
                dest_dir = os.path.join(channel_dir, "Download", "media")
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    stem, ext = os.path.splitext(os.path.basename(src_path))
                    from utility.file_util import make_safe_file_name

                    row_id = (video_detail.get("id") or "item").strip() or "item"
                    safe_stem = make_safe_file_name(stem, title_length=48)
                    dest = os.path.join(dest_dir, f"{row_id}_{safe_stem}{ext.lower()}")
                    if not safe_copy_overwrite(src_path, dest):
                        raise OSError("复制失败")
                    dest = os.path.abspath(dest)
                    old = (video_detail.get(STORY_MEDIA_KEY) or "").strip()
                    video_detail[STORY_MEDIA_KEY] = dest
                    # 换了媒体，原来的文字稿就对不上了：同一个文件夹里的删掉，记录清掉。
                    old_transcript = (video_detail.pop(STORY_TRANSCRIPT_KEY, "") or "").strip()
                    stale = [p for p in (old_transcript, os.path.splitext(old)[0] + ".txt" if old else "") if p]
                    new_transcript = os.path.splitext(dest)[0] + ".txt"
                    for cand in stale:
                        t_abs = os.path.abspath(cand)
                        if os.path.normcase(t_abs) == os.path.normcase(new_transcript):
                            continue  # 同名媒体重新拖进来，文字稿留着
                        if not os.path.isfile(t_abs):
                            continue
                        if os.path.normcase(os.path.dirname(t_abs)) == os.path.normcase(os.path.abspath(dest_dir)):
                            try:
                                os.remove(t_abs)
                            except OSError:
                                pass
                    if os.path.isfile(new_transcript):
                        video_detail[STORY_TRANSCRIPT_KEY] = os.path.abspath(new_transcript)
                    if old:
                        old_abs = os.path.abspath(old)
                        same_dir = os.path.normcase(os.path.dirname(old_abs)) == os.path.normcase(
                            os.path.abspath(dest_dir)
                        )
                        if same_dir and os.path.normcase(old_abs) != os.path.normcase(dest) and os.path.isfile(old_abs):
                            try:
                                os.remove(old_abs)
                            except OSError:
                                pass
                except Exception as exc:
                    messagebox.showerror("媒体", f"无法保存这个文件：\n{exc}", parent=dlg)
                    return
                material_var.set("media")
                _sync_material_widgets()
                persist(video_detail, parent=dlg)
                kind_name = "音频" if kind == "audio" else "视频"
                show_auto_close_popup(
                    dlg,
                    "媒体",
                    f"这条的{kind_name}已换成：\n{os.path.basename(dest)}",
                )
                if not _find_item_transcript_file(video_detail):
                    _offer_item_transcript(dest, dest_dir)

            def _offer_item_transcript(media_path: str, dest_dir: str) -> None:
                """问用户要不要把这段声音转成带时间戳、带说话人的文字稿；要的话转好存在媒体旁边，记进这一行。"""
                if not messagebox.askyesno(
                    "转录",
                    "要不要把这段声音转成文字稿？\n\n"
                    "文字稿每一句前面有时间戳，并标出是谁在说话。\n"
                    "转好的文字稿存在媒体文件旁边，建项目时会跟媒体一起拷进项目。",
                    parent=dlg,
                ):
                    return
                _run_item_transcript(media_path, dest_dir)

            def _run_item_transcript(media_path: str, dest_dir: str) -> bool:
                """转录并记进这一行。成功返回 True；取消或失败返回 False。"""
                from utility import media_transcript

                downloader = getattr(self, "downloader", None)
                pid = str(getattr(downloader, "pid", "") or getattr(self, "pid", "") or "")
                language = str(getattr(downloader, "language", "") or getattr(self, "language", "") or "zh")
                path, error = media_transcript.transcribe_with_progress_dialog(
                    dlg, media_path, pid=pid, language=language, out_dir=dest_dir
                )
                if error == "cancelled":
                    show_auto_close_popup(dlg, "转录", "已取消，这一条没有文字稿。")
                    return False
                if error:
                    messagebox.showerror("转录", error, parent=dlg)
                    return False
                video_detail[STORY_TRANSCRIPT_KEY] = os.path.abspath(path)
                _sync_material_widgets()
                persist(video_detail, parent=dlg)
                show_auto_close_popup(
                    dlg,
                    "转录",
                    f"文字稿已存好，和媒体在同一个文件夹：\n{os.path.abspath(path)}",
                )
                return True

            def _require_media_transcript(media_path: str) -> bool:
                """智能生成前：没有文字稿就提醒用户必须先转录；已有文字稿就确认是用它还是重新转录。

                返回 True 表示可以接着生成；取消、转录取消或失败返回 False。
                """
                existing, existing_text = _item_transcript_text(video_detail)
                if existing_text:
                    from utility import media_transcript

                    choice = media_transcript.ask_choice(
                        dlg,
                        "文字稿",
                        "这条媒体已经有文字稿了：\n"
                        f"{os.path.basename(existing)}\n\n"
                        "用现有的文字稿生成场景，还是重新转录一遍？\n"
                        "（重新转录会覆盖现有的文字稿。）",
                        [("use", "用现有文字稿"), ("redo", "重新转录")],
                    )
                    if choice == "use":
                        return True
                    if choice == "redo":
                        return _run_item_transcript(
                            media_path, os.path.dirname(os.path.abspath(media_path))
                        )
                    return False
                if not messagebox.askyesno(
                    "需要文字稿",
                    "这条媒体还没有文字稿。\n\n"
                    "媒体的场景一律根据文字稿生成：文字稿里有每一句的精确时间和说话的人，"
                    "场景的起止时间和人物转换才准。\n\n"
                    "现在就去转录吗？转好以后会接着生成场景。",
                    parent=dlg,
                ):
                    return False
                return _run_item_transcript(media_path, os.path.dirname(os.path.abspath(media_path)))

            scene_ui["import_analyzed_text_file"] = _import_analyzed_text_file
            scene_ui["import_item_media"] = _import_item_media
            scene_ui["require_media_transcript"] = _require_media_transcript

            # ---- 合并后的「材料」区：PDF、全部图片、音频/视频、文字稿一个列表（gui/dl/materials_panel.py）----
            from gui.dl.materials_panel import MaterialsPanel, ROW_H

            _last_material = [None]

            def _open_path(path: str) -> None:
                try:
                    os.startfile(path)  # type: ignore[attr-defined]
                except (OSError, AttributeError) as exc:
                    messagebox.showerror("打开", f"打不开：\n{exc}", parent=dlg)

            def _material_images() -> list:
                imgs = project_manager.get_cover_images(video_detail)
                if not imgs:
                    one = (_find_gen_video_webp_for_row(video_detail) or "").strip()
                    if one and os.path.isfile(one):
                        imgs = [one]
                return imgs

            def _default_material_mode() -> str:
                if _find_item_media_file(video_detail):
                    return "media"
                if (_find_gen_video_slide_for_row(video_detail) or "").strip():
                    return "pdf"
                if _material_images():
                    return "image"
                return "media"

            def _material_entries() -> list:
                out = []
                slide = (_find_gen_video_slide_for_row(video_detail) or "").strip()
                if slide and os.path.isfile(slide):
                    pages = int(_remember_pdf_source(slide).get("pages") or 0)
                    out.append({"kind": "pdf", "path": slide, "select": "pdf", "analyze": True,
                                "title": f"PDF：{os.path.basename(slide)}", "detail": f"共 {pages} 页"})
                else:
                    out.append({"kind": "pdf", "path": "", "select": "", "placeholder": True,
                                "tile": "无 PDF", "title": "（没有 PDF）",
                                "detail": "双击：从下载文件夹选一份 PDF，或按点击顺序把图片合成 PDF"})
                imgs = _material_images()
                for i, path in enumerate(imgs, 1):
                    out.append({"kind": "image", "path": path, "select": "image",
                                "title": f"图片 {i}/{len(imgs)}：{os.path.basename(path)}",
                                "detail": "封面（第一张）" if i == 1 else ""})
                if not imgs:
                    out.append({"kind": "image", "path": "", "select": "", "placeholder": True,
                                "tile": "无图片", "title": "（没有图片）", "detail": "双击：选一张图片挂到这一条"})
                media_path = _find_item_media_file(video_detail)
                mkind = _media_kind_for_path(media_path) if media_path else ""
                have = (mkind or "video") if media_path else ""
                for slot, label in (("audio", "音频"), ("video", "视频")):
                    if have == slot:
                        out.append({"kind": slot, "path": media_path, "select": "media",
                                    "title": f"{label}：{os.path.basename(media_path)}",
                                    "detail": "▶ 播放。再拖一个音频或 mp4 进来，会换掉这一个。"})
                    else:
                        out.append({"kind": slot, "path": "", "select": "", "placeholder": True,
                                    "tile": f"无{label}", "title": f"（没有{label}）",
                                    "detail": "双击：选一个音频或 mp4"})
                transcript_path = _find_item_transcript_file(video_detail)
                if transcript_path:
                    _tp, ttext = _item_transcript_text(video_detail)
                    n_lines = len([x for x in (ttext or "").splitlines() if x.strip()])
                    out.append({"kind": "transcript", "path": transcript_path, "select": "media", "analyze": True,
                                "title": f"文字稿：{os.path.basename(transcript_path)}",
                                "detail": f"{n_lines} 行。双击把文字稿文件拷到剪贴板"})
                else:
                    out.append({"kind": "transcript", "path": "", "select": "", "placeholder": True,
                                "tile": "无文字稿", "title": "（没有文字稿）",
                                "detail": "双击：现在转录" if media_path else "先加音频或 mp4，才能转录"})
                return out

            def _offer_rename_now(path: str) -> None:
                """问一次：把这一条的名称改成文件名吗？任何文件类型都问；同名或自动起的文件名不问。

                有名称栏（STORY 窗）：写名称栏，走「保存」按钮的路径。没有名称栏 / 还没有项目：
                直接写列表行（外层 title；有项目时 project_profile.video_title，没有时记下来供新建项目用）并保存。
                """
                from gui.dl.materials_panel import rename_offer_stem

                field = scene_ui.get("name_field")  # (StringVar, save_fn) 或 None
                if field:
                    current = (field[0].get() or "").strip()
                else:
                    current = _youtube_row_source_title(video_detail)
                stem = rename_offer_stem(path, current)
                if not stem:
                    return
                if not messagebox.askyesno(
                    "项目名称",
                    f"要把项目名称改成「{stem}」吗？\n\n现在的名称：{current or '（空）'}",
                    parent=dlg,
                ):
                    return
                project_manager.apply_project_name_to_row(video_detail, stem)
                if field:
                    field[0].set(stem)
                    field[1]()
                else:
                    persist(video_detail, parent=dlg)
                    drop_ctx_t = getattr(dlg, "_summary_drop_ctx", None)
                    refresh_t = drop_ctx_t.get("refresh_title_fields") if isinstance(drop_ctx_t, dict) else None
                    if callable(refresh_t):
                        refresh_t()
                    elif not embedded:
                        try:
                            dlg.title(f"SCENE | {stem[:48]}")
                        except tk.TclError:
                            pass
                if callable(on_title_updated):
                    try:
                        on_title_updated()
                    except Exception:
                        pass

            def _offer_rename(path: str) -> None:
                try:
                    _offer_rename_now(path)
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 改项目名称失败：{exc}")

            scene_ui["offer_rename"] = _offer_rename

            def _pick_item_media() -> None:
                picked = filedialog.askopenfilename(
                    parent=dlg,
                    title="选择音频或 mp4",
                    filetypes=[
                        ("音频 / 视频", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.mp4 *.mov *.mkv *.webm"),
                        ("所有文件", "*.*"),
                    ],
                )
                if picked:
                    _import_item_media(picked)
                    _offer_rename(picked)

            def _material_pick(entry: dict) -> None:
                kind = entry.get("kind") or ""
                if kind == "pdf":
                    picked = ask_download_slide_pdf(dlg)
                    if picked:
                        name_src = picked
                        _import_slide_pdf(picked)
                        _offer_rename(name_src)
                elif kind == "image":
                    _pick_cover_image()
                elif kind in ("audio", "video", "media"):
                    _pick_item_media()
                elif kind == "transcript":
                    media_path = _find_item_media_file(video_detail)
                    if media_path:
                        _run_item_transcript(media_path, os.path.dirname(os.path.abspath(media_path)))

            def _material_copy(entry: dict) -> None:
                if entry.get("placeholder"):
                    _material_pick(entry)
                    return
                kind = entry.get("kind") or ""
                path = entry.get("path") or ""
                if kind == "transcript":
                    path = path if path and os.path.isfile(path) else (_find_item_transcript_file(video_detail) or "")
                    if not path or not os.path.isfile(path):
                        show_auto_close_popup(dlg, "没有文字稿", "这一条还没有文字稿文件。")
                        return
                if path and _copy_file_to_clipboard_hdrop(dlg, path):
                    show_auto_close_popup(
                        dlg, "已复制", f"文件已拷到剪贴板，可以粘贴到别处：\n{os.path.basename(path)}"
                    )

            def _material_select(entry: dict) -> None:
                sel = entry.get("select") or ""
                if sel:
                    _last_material[0] = sel
                    material_var.set(sel)

            def _set_cover_list(paths: list) -> None:
                project_manager.set_cover_images(video_detail, paths)
                drop_ctx3 = getattr(dlg, "_summary_drop_ctx", None)
                refresh_media = drop_ctx3.get("refresh_feature_media_row") if isinstance(drop_ctx3, dict) else None
                if callable(refresh_media):
                    try:
                        refresh_media()
                    except Exception:
                        pass
                persist(video_detail, parent=dlg)
                _sync_material_widgets()

            def _material_menu(menu, entry: dict) -> None:
                kind = entry.get("kind") or ""
                path = entry.get("path") or ""
                real = bool(path) and not entry.get("placeholder")
                if real:
                    if entry.get("select"):
                        menu.add_command(label="选作生成材料", command=lambda: _material_select(entry))
                    menu.add_command(label="拷到剪贴板", command=lambda: _material_copy(entry))
                    if kind in ("audio", "video"):
                        menu.add_command(
                            label="播放 / 停止", command=lambda: materials_panel.player.toggle(path, kind)
                        )
                    menu.add_command(label="打开", command=lambda: _open_path(path))
                    menu.add_separator()
                if real and entry.get("analyze"):
                    menu.add_command(label="分析（只用这一项）…", command=lambda: _material_analyze(entry))
                    menu.add_separator()
                if kind in ("pdf", ""):
                    menu.add_command(label="选择 / 换一份 PDF …", command=lambda: _material_pick({"kind": "pdf"}))
                if kind in ("image", ""):
                    menu.add_command(label="添加图片 …", command=_pick_cover_image)
                if kind == "image" and real:
                    imgs = _material_images()
                    key = os.path.normcase(os.path.abspath(path))
                    rest = [p for p in imgs if os.path.normcase(os.path.abspath(p)) != key]
                    menu.add_command(label="设为第一张（封面）", command=lambda: _set_cover_list([path] + rest))
                    menu.add_command(label="从列表移除（不删文件）", command=lambda: _set_cover_list(rest))
                if kind in ("audio", "video", "media", ""):
                    menu.add_command(label="选择 / 换一个音频或 mp4 …", command=_pick_item_media)
                media_path = _find_item_media_file(video_detail)
                if media_path and kind in ("audio", "video", "transcript"):
                    menu.add_command(
                        label="重新转录" if _find_item_transcript_file(video_detail) else "转录成文字稿",
                        command=lambda: _run_item_transcript(
                            media_path, os.path.dirname(os.path.abspath(media_path))
                        ),
                    )

            # ---- 分析报告：先选分析方式（频道 analyze_prompt 选项）和结果放法，再生成 ----
            def _analyze_options() -> list:
                try:
                    return config.get_channel_analyze_options(self._channel_config_key())
                except Exception:
                    return config.get_channel_analyze_options("")

            def _analyze_choice_saved():
                cfg = project_manager.PROJECT_CONFIG
                if isinstance(cfg, dict) and (cfg.get("pid") or "") and (
                    cfg.get("pid") == project_manager.list_json_row_workflow_pid(video_detail)
                ) and isinstance(cfg.get("analyze_choice"), dict):
                    return cfg["analyze_choice"]
                pp = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
                if isinstance(pp, dict) and isinstance(pp.get("analyze_choice"), dict):
                    return pp["analyze_choice"]
                return video_detail.get("analyze_choice")

            def _analyze_choice_remember(choice: dict) -> None:
                """记在这一条的项目配置里（project_profile；同一项目开着时也写进 PROJECT_CONFIG）。"""
                keep = {"key": choice.get("key") or "", "mode": choice.get("mode") or "replace"}
                pp = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
                if isinstance(pp, dict) and pp:
                    pp["analyze_choice"] = keep
                else:
                    video_detail["analyze_choice"] = keep
                cfg = project_manager.PROJECT_CONFIG
                if isinstance(cfg, dict) and (cfg.get("pid") or "") and (
                    cfg.get("pid") == project_manager.list_json_row_workflow_pid(video_detail)
                ):
                    cfg["analyze_choice"] = keep

            def _run_analyze(source_text=None, source_label: str = "") -> None:
                """``source_text`` 为 None：原来的「重新生成分析报告」（文字稿，没有就用现有分析报告）。"""
                if not callable(on_resummarize):
                    messagebox.showinfo("分析", "这里不能生成分析报告。", parent=dlg)
                    return
                from gui.dl.analyze_picker import ask_analyze_choice

                choice = ask_analyze_choice(
                    dlg,
                    _analyze_options(),
                    saved=_analyze_choice_saved(),
                    title="重新生成分析报告" if source_text is None else "分析这一项",
                    source_label=source_label,
                )
                if not choice:
                    return
                _analyze_choice_remember(choice)
                kw = {"analyze_key": choice["key"], "append": choice["mode"] == "append"}
                if source_text is not None:
                    kw["source_text"] = source_text
                try:
                    on_resummarize(**kw)
                except TypeError:
                    if source_text is not None:
                        messagebox.showwarning("分析", "这个窗口还不支持只用这一项生成。", parent=dlg)
                        return
                    on_resummarize()
                _analyzed_edit["text"] = None
                _analyzed_edit["reload"] = True
                if material_var.get() != "analyzed":
                    material_var.set("analyzed")
                _fill_material_preview()

            def _material_analyze(entry: dict) -> None:
                kind = entry.get("kind") or ""
                path = entry.get("path") or ""
                text = ""
                if kind == "pdf" and path and os.path.isfile(path):
                    src = _remember_pdf_source(path)
                    text = (src.get("text") or "").strip() if src.get("has_text") else ""
                    if not text:
                        messagebox.showwarning("分析", "这份 PDF 没有可以提取的文字（可能是扫描图片）。", parent=dlg)
                        return
                elif kind == "transcript":
                    _tp, ttext = _item_transcript_text(video_detail)
                    text = (ttext or "").strip()
                    if not text:
                        messagebox.showwarning("分析", "这一条的文字稿是空的。", parent=dlg)
                        return
                else:
                    return
                label = f"{'PDF' if kind == 'pdf' else '文字稿'}：{os.path.basename(path)}（{len(text)} 字）"
                _run_analyze(text, label)

            def _walk_materials_drop(widget) -> None:
                walker = scene_ui.get("walk_drop")
                if callable(walker):
                    walker(widget)

            materials_panel = MaterialsPanel(
                frm,
                get_entries=_material_entries,
                # 5 rows x ROW_H plus a little margin, so nothing scrolls.
                height=5 * ROW_H + 12,
                on_select=_material_select,
                on_copy=_material_copy,
                build_menu=_material_menu,
                on_rebuilt=_walk_materials_drop,
                on_analyze=_material_analyze,
            )
            scene_ui["materials_panel"] = materials_panel

            def _show_materials(on: bool) -> None:
                if on:
                    material_preview.pack_forget()
                    materials_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 8), after=material_row)
                else:
                    materials_panel.pack_forget()
                    material_preview.pack(fill=tk.X, expand=False, pady=(0, 8), after=material_row)

            def _materials_button_caption() -> str:
                parts = ["PDF" if (_find_gen_video_slide_for_row(video_detail) or "").strip() else "无 PDF"]
                parts.append(f"图片 {len(_material_images())}")
                media_path = _find_item_media_file(video_detail)
                kind = _media_kind_for_path(media_path) if media_path else ""
                parts.append("音频" if kind == "audio" else "视频" if media_path else "无媒体")
                if _find_item_transcript_file(video_detail):
                    parts.append("文字稿")
                return "材料：" + " · ".join(parts)

            def _on_materials_press(_event=None):
                material_var.set(_last_material[0] or _default_material_mode())
                return "break"

            def _sync_material_widgets(*_args):
                # PDF 一律一页一个场景，不再让人选。
                pdf_layout_combo.pack_forget()
                _paint_material_buttons()
                _fill_material_preview()

            def _on_material_selected(*_args):
                _sync_material_widgets()

            _analyzed_press = {"was_on": False, "when": 0}

            def _on_analyzed_press(event=None):
                now = int(getattr(event, "time", 0) or 0)
                if now - _analyzed_press["when"] > 450:
                    _analyzed_press["was_on"] = material_var.get() == "analyzed"
                _analyzed_press["when"] = now
                material_var.set("analyzed")

            def _on_analyzed_double(_event=None):
                if _analyzed_press["was_on"] and callable(on_resummarize):
                    # 原来的确认框换成选择窗：分析方式 + 替换 / 追加；材料照旧（文字稿，没有就用现有分析报告）。
                    _run_analyze(None, "原始材料（文字稿；没有文字稿时用现有的分析报告）")
                return "break"

            _pdf_press = {"was_on": False, "when": 0}

            def _on_pdf_press(event=None):
                now = int(getattr(event, "time", 0) or 0)
                if now - _pdf_press["when"] > 450:
                    _pdf_press["was_on"] = material_var.get() == "pdf"
                _pdf_press["when"] = now
                material_var.set("pdf")
                return "break"

            def _on_pdf_double(_event=None):
                if _pdf_press["was_on"]:
                    picked = ask_download_slide_pdf(dlg)
                    if picked:
                        name_src = picked
                        _import_slide_pdf(picked)
                        _offer_rename(name_src)
                return "break"

            _image_press = {"was_on": False, "when": 0}

            def _import_cover_image(image_path: str) -> None:
                """挂一张图片到这一条：与摘要窗封面同一流程（加水印 → gen_video/*.webp → cover_image）；
                没有水印配置时退回原图复制到 gen_video。"""
                ok, dest, err = save_cover_image_as_gen_video_webp(
                    image_path,
                    video_detail,
                    channel=self._channel_config_key(),
                )
                if not ok:
                    try:
                        gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
                        if not gen_dir:
                            raise OSError(err or "没有 gen_video 目录")
                        os.makedirs(gen_dir, exist_ok=True)
                        dest = os.path.join(gen_dir, os.path.basename(image_path))
                        if os.path.abspath(dest) != os.path.abspath(image_path):
                            safe_copy_overwrite(image_path, dest)
                        project_manager.append_cover_image(video_detail, os.path.abspath(dest))
                    except Exception as exc:
                        messagebox.showerror("图片", f"无法保存这张图片：\n{exc}", parent=dlg)
                        return
                material_var.set("image")
                _sync_material_widgets()
                drop_ctx2 = getattr(dlg, "_summary_drop_ctx", None)
                refresh_media = (
                    drop_ctx2.get("refresh_feature_media_row") if isinstance(drop_ctx2, dict) else None
                )
                if callable(refresh_media):
                    try:
                        refresh_media()
                    except Exception:
                        pass
                persist(video_detail, parent=dlg)
                primary_cover = project_manager.get_primary_cover_image(video_detail)
                show_auto_close_popup(
                    dlg, "图片", f"封面图片已挂到这一条：\n{os.path.basename(primary_cover) if primary_cover else ''}"
                )

            def _pick_cover_image() -> None:
                picked = filedialog.askopenfilename(
                    parent=dlg,
                    title="选择封面图片",
                    filetypes=[
                        ("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                        ("所有文件", "*.*"),
                    ],
                )
                if picked:
                    _import_cover_image(picked)
                    _offer_rename(picked)

            scene_ui["import_cover_image"] = _import_cover_image

            def _on_image_press(event=None):
                now = int(getattr(event, "time", 0) or 0)
                if now - _image_press["when"] > 450:
                    _image_press["was_on"] = material_var.get() == "image"
                _image_press["when"] = now
                material_var.set("image")
                return "break"

            def _on_image_double(_event=None):
                if _image_press["was_on"] or not (_find_gen_video_webp_for_row(video_detail) or "").strip():
                    _pick_cover_image()
                return "break"

            btn_analyzed.bind("<ButtonPress-1>", _on_analyzed_press)
            btn_analyzed.bind("<Double-Button-1>", _on_analyzed_double)
            btn_materials.bind("<ButtonPress-1>", _on_materials_press)

            def _on_media_press(_event=None):
                material_var.set("media")
                return "break"


            material_var.trace_add("write", _on_material_selected)
            _sync_material_widgets()

            _vs_opts = list(config.VISUAL_STYLE_OPTIONS)
            _vs_cur, _talk_cur, _ = _project_look_from_row(video_detail)
            visual_style_var = tk.StringVar(value=_vs_cur)
            visual_style_combo_opts = list(_vs_opts)
            dialogue_mode_var = tk.StringVar(value=_talk_cur)
            dialogue_mode_opts = list(config.DIALOGUE_MODE_OPTIONS)

            # 画面风格：与新建项目 / 欢迎屏同一份 config.VISUAL_STYLE_OPTIONS；默认取项目配置。
            style_frm = ttk.Frame(prompt_row)
            ttk.Label(style_frm, text="风格").pack(side=tk.LEFT, padx=(0, 2))
            visual_style_combo = ttk.Combobox(
                style_frm,
                textvariable=visual_style_var,
                values=visual_style_combo_opts,
                state="readonly" if visual_style_combo_opts else "disabled",
                width=20,
            )
            visual_style_combo.pack(side=tk.LEFT)
            style_frm.pack(side=tk.LEFT, padx=(0, 8), before=action_bar)

            def _commit_visual_style(_e=None):
                vs = config.match_visual_style(visual_style_var.get() or "")
                if not vs:
                    return
                video_detail["visual_style"] = vs
                pp = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
                if isinstance(pp, dict):
                    pp["visual_style"] = vs
                project_manager.LAST_VISUAL_STYLE = vs
                try:
                    persist(video_detail, parent=dlg)
                except Exception:
                    pass

            visual_style_combo.bind("<<ComboboxSelected>>", _commit_visual_style)

            def _scene_prompt_params() -> dict:
                return {
                    "steps": _int_of(step_count_var, config_channel.STEP_STORY_DEFAULT),
                    "episode": _int_of(series_ep_var, 1),
                    "episodes": _int_of(
                        series_total_var, config_channel.SERIES_DIRECT_DEFAULT_EPISODES
                    ),
                    "visual_style": (visual_style_var.get() or "").strip(),
                }

            def _pdf_instruction_for(label: str, pages: int) -> str:
                if config_channel.is_series_direct_label(label):
                    p = _scene_prompt_params()
                    return (
                        f"The PDF has {int(pages)} pages and describes the whole series. "
                        f"Read it all, then use only the part for episode {p['episode']} of {p['episodes']}. "
                        "One scene per page does not apply."
                    )
                return _pdf_scene_generation_instruction(
                    label,
                    int(pages),
                    _pdf_layout_mode() if "series" in label.lower() else "ai",
                )

            ttk.Label(frm, text="导向说明（{instruction}，可选）：").pack(
                anchor=tk.W, pady=(0, 2)
            )
            instruction_frm = ttk.Frame(frm)
            instruction_frm.pack(fill=tk.X, pady=(0, 8))
            instruction_tx = scrolledtext.ScrolledText(
                instruction_frm, wrap=tk.WORD, width=100, height=2, font=("Arial", 9)
            )
            instruction_tx.pack(fill=tk.X, pady=(0, 4))

            def _selected_material_kind() -> str:
                mode = material_var.get()
                if mode == "pdf":
                    return "pdf"
                if mode == "image":
                    return "image"
                if mode == "media":
                    if _item_transcript_text(video_detail)[1]:
                        return "transcript"
                    return _media_kind_for_path(_find_item_media_file(video_detail)) or "audio"
                return "analyzed"

            def _scene_prompt_text_now() -> str:
                sel = (prompt_combo_var.get() or "").strip()
                if not sel or not nb_prompt_choices:
                    return ""
                instr = (instruction_tx.get("1.0", tk.END) or "").strip()
                kind = _selected_material_kind()
                override = None
                if config_channel.is_step_image_label(sel) or config_channel.is_scene_summary_image_label(sel):
                    _, prompt = self._combined_prompt_text_for_label(
                        video_detail, sel, prompt_params=_scene_prompt_params()
                    )
                    return prompt or ""
                if kind == "image":
                    override = _image_material_override(video_detail)
                elif kind == "pdf":
                    cached = _remember_pdf_source()
                    override = cached.get("text") or ""
                    extra = _pdf_instruction_for(sel, int(cached.get("pages") or 0))
                    instr = (instr + "\n\n" + extra).strip() if instr else extra
                elif material_var.get() == "media":
                    media_path = _find_item_media_file(video_detail)
                    if media_path and not _item_transcript_text(video_detail)[1]:
                        return ""  # 媒体一律按文字稿处理；没有文字稿就还不能出提示词
                    override = _media_material_override(video_detail, media_path) if media_path else ""
                try:
                    _, prompt = self._combined_prompt_text_for_label(
                        video_detail,
                        sel,
                        instruction=instr,
                        content_override=override,
                        dialogue_mode=(dialogue_mode_var.get() or "").strip(),
                        prompt_params=_scene_prompt_params(),
                    )
                    return _prompt_text_for_material(prompt, kind) or ""
                except Exception:
                    return ""

            def _copy_selected_scene_prompt(_event=None):
                text = (_scene_prompt_text_now() or "").strip()
                if (
                    not text
                    and material_var.get() == "media"
                    and _find_item_media_file(video_detail)
                    and not _item_transcript_text(video_detail)[1]
                ):
                    show_auto_close_popup(
                        dlg, "生成场景", "这条媒体还没有文字稿。点「智能生成」时会先帮你转录。"
                    )
                    return
                if not text:
                    show_auto_close_popup(dlg, "生成场景", "这一项没有可拷贝的提示词。")
                    return
                _copy_text_to_clipboard(dlg, text)
                show_auto_close_popup(dlg, "生成场景", "场景提示词已拷到剪贴板。")

            if nb_prompt_choices:
                prompt_combo.bind("<<ComboboxSelected>>", _copy_selected_scene_prompt)
                for _w in (step_count_combo, series_total_combo, series_ep_combo, visual_style_combo):
                    _w.bind("<<ComboboxSelected>>", _copy_selected_scene_prompt, add="+")

            _sync_material_widgets()

            from gui.cli_bridge import bind_screen, match_choice, unbind_screen

            def _unbind_scene_cli(_event=None):
                if _event is not None and getattr(_event, "widget", None) is not dlg:
                    return
                unbind_screen(config.SCREEN_STORY_SCENE)

            def _close_scene_editor():
                if getattr(self, "_scene_content_dialog", None) is dlg:
                    self._scene_content_dialog = None
                _unbind_scene_cli()
                _dismiss_scene_window()

            def _set_lm_early(value: str):
                labels = [opt[0] for opt in nb_prompt_choices]
                matched = match_choice(value, labels)
                if not matched:
                    return False, "unknown LM prompt: " + value + "\nchoices: " + " | ".join(labels)
                _apply_scene_lm_combo(
                    prompt_combo, prompt_combo_var, labels, matched, host=dlg
                )
                return True, f"{matched} — 选LM提示下拉已切换。"

            def _set_style_early(value: str):
                matched = match_choice(value, visual_style_combo_opts)
                if not matched:
                    return False, "unknown style: " + value + "\nchoices: " + " | ".join(visual_style_combo_opts)
                visual_style_var.set(matched)
                return True, matched

            def _set_instruction_early(value: str):
                instruction_tx.delete("1.0", tk.END)
                instruction_tx.insert("1.0", value)
                return True, "instruction set"

            def _get_content_bridge() -> str:
                txw = scene_ui.get("tx")
                if txw is None:
                    return ""
                return (txw.get("1.0", tk.END) or "").strip()

            def _set_content_bridge(value: str):
                txw = scene_ui.get("tx")
                if txw is None:
                    return False, "scene_content 编辑区仍在加载，请几秒后重试"
                try:
                    txw.delete("1.0", tk.END)
                    if value:
                        txw.insert("1.0", value)
                except tk.TclError as exc:
                    return False, f"scene_content set failed: {exc}"
                if value:
                    ok, _msg, parsed = apply_scene_content_from_editor_text(
                        video_detail, value
                    )
                    if ok and parsed is not None:
                        result_holder[0] = parsed
                return True, "scene_content set"

            def _persist_content_bridge():
                txw = scene_ui.get("tx")
                if txw is None:
                    return False, "scene_content 编辑区仍在加载，请几秒后重试"
                raw = (txw.get("1.0", tk.END) or "").strip()
                ok, msg, parsed = apply_scene_content_from_editor_text(
                    video_detail, raw
                )
                if not ok:
                    return False, msg
                result_holder[0] = parsed
                if not persist(video_detail, parent=dlg):
                    return False, "写入频道列表失败"
                if callable(on_saved):
                    try:
                        on_saved()
                    except Exception:
                        pass
                return True, (
                    f"saved {len(parsed or [])} scene(s) to channel list "
                    "(window kept open)"
                )

            _scene_copy_index = [-1]
            scene_ui["_scene_copy_index"] = _scene_copy_index
            _episode_choice = [""]
            scene_ui["_episode_choice"] = _episode_choice

            def _scene_index_button_label_bridge(idx: int) -> str:
                return "All" if idx < 0 else str(idx + 1)

            def _scene_list_for_bridge() -> list | None:
                txw = scene_ui.get("tx")
                if txw is not None:
                    raw = (txw.get("1.0", tk.END) or "").strip()
                    if raw:
                        try:
                            parsed = json.loads(safe_clipboard_json_copy(raw))
                        except (json.JSONDecodeError, TypeError):
                            parsed = None
                        if isinstance(parsed, list) and parsed:
                            return parsed
                scenes = video_detail.get("scene_content") or []
                if isinstance(scenes, list) and scenes:
                    return scenes
                return None

            def _scenes_in_episode_bridge() -> list:
                return _filter_scenes_by_episode(
                    _scene_list_for_bridge() or [], _episode_choice[0]
                )

            def _scene_count_for_bridge() -> int:
                return len(_scenes_in_episode_bridge())

            def _episode_choice_labels_bridge():
                ids = _episode_ids_in_scenes(_scene_list_for_bridge())
                return ["全部"] + ids

            def _sync_episode_button_bridge():
                btn = scene_ui.get("episode_btn")
                if btn is None:
                    return
                try:
                    btn.config(text=_episode_choice_label(_episode_choice[0]))
                except tk.TclError:
                    pass

            def _set_episode_choice_early(value: str):
                raw = (value or "").strip().translate(
                    str.maketrans("０１２３４５６７８９", "0123456789")
                )
                if not raw:
                    return False, "empty episode_choice"
                ids = _episode_ids_in_scenes(_scene_list_for_bridge())
                low = raw.lower().replace(" ", "")
                if low in ("all", "全部", "0", "-1"):
                    _episode_choice[0] = ""
                elif not ids:
                    return False, "当前场景没有 episode，只能选全部"
                elif raw in ids:
                    _episode_choice[0] = raw
                else:
                    return False, (
                        "unknown episode_choice: " + value
                        + "\nchoices: " + " | ".join(_episode_choice_labels_bridge())
                    )
                _scene_copy_index[0] = -1
                _sync_episode_button_bridge()
                btn = scene_ui.get("scene_index_btn")
                if btn is not None:
                    try:
                        btn.config(text=_scene_index_button_label_bridge(-1))
                    except tk.TclError:
                        pass
                return True, f"episode_choice={_episode_choice_label(_episode_choice[0])}"

            def _scene_choice_labels_bridge():
                n = _scene_count_for_bridge()
                return ["All"] + [str(i) for i in range(1, n + 1)]

            def _set_scene_choice_early(value: str):
                raw = (value or "").strip().translate(
                    str.maketrans("０１２３４５６７８９", "0123456789")
                )
                if not raw:
                    return False, "empty scene_choice"
                n = _scene_count_for_bridge()
                low = raw.lower().replace(" ", "")
                if low in ("all", "全部", "0", "-1"):
                    _scene_copy_index[0] = -1
                elif raw.isdigit():
                    i = int(raw)
                    if i < 1:
                        return False, "scene_choice 用 all 或 1/2/3/…"
                    if n > 0 and i > n:
                        return False, f"scene {i} out of range (1..{n})"
                    _scene_copy_index[0] = i - 1
                else:
                    return False, (
                        "unknown scene_choice: " + value
                        + "（用 all / 1 / 2 / …）\nchoices: "
                        + " | ".join(_scene_choice_labels_bridge())
                    )
                btn = scene_ui.get("scene_index_btn")
                if btn is not None:
                    try:
                        btn.config(
                            text=_scene_index_button_label_bridge(_scene_copy_index[0])
                        )
                    except tk.TclError:
                        pass
                scene_msg = (
                    f"scene_choice={_scene_index_button_label_bridge(_scene_copy_index[0])}"
                )
                if _scene_copy_index[0] >= 0:
                    from utility.telegram_session import load_grok_scene_video_nb_index

                    nb_idx = load_grok_scene_video_nb_index()
                    base, var, _ = config_prompt.grok_scene_video_nb_export(nb_idx)
                    copied = self._copy_notebooklm_scene_instruction(
                        parent=dlg,
                        video_detail=video_detail,
                        scenes=_scene_list_for_bridge() or [],
                        nb_mode=base,
                        nb_variant=var,
                        main_character=main_character,
                        channel_path=channel_path or self.channel_path or "",
                        scene_index=_scene_copy_index[0],
                        visual_style=(visual_style_var.get() or "").strip(),
                        episode=_episode_choice[0],
                    )
                    if not copied:
                        return False, (
                            f"{scene_msg}; failed to copy NotebookLM video 提示词 — "
                            "scene_content 需要有效 JSON 数组"
                        )
                    try:
                        nb_label = config_prompt.grok_scene_video_nb_choice_label(nb_idx)
                    except ValueError:
                        nb_label = config_prompt.nb_export_mode_label(base, var)
                    return True, (
                        f"{scene_msg}; copied [{nb_idx}] {nb_label} to clipboard"
                    )
                return True, scene_msg

            def _nb_choice_rows_bridge():
                lang = config.llm_language_label(getattr(self, "language", "") or "")
                return config_prompt.notebooklm_export_flat_choices(lang)

            def _nb_labels_bridge():
                return [row[0] for row in _nb_choice_rows_bridge()]

            def _set_notebooklm_early(value: str):
                rows = _nb_choice_rows_bridge()
                labels = [row[0] for row in rows]
                matched = match_choice(value, labels)
                base = var = ""
                if matched:
                    for label, b, v in rows:
                        if label == matched:
                            base, var = b, v
                            break
                else:
                    parsed = config_prompt.parse_nb_export_choice(value)
                    if parsed:
                        base, var = parsed
                        try:
                            matched = next(
                                label for label, b, v in rows if b == base and v == var
                            )
                        except StopIteration:
                            matched = config_prompt.nb_export_mode_label(base, var)
                if not base:
                    return False, (
                        "unknown NotebookLM export: " + value
                        + "\nchoices: " + " | ".join(labels)
                    )
                scenes = _scene_list_for_bridge()
                if not scenes:
                    return False, (
                        "failed to copy NotebookLM prompt — "
                        "scene_content 需要有效 JSON 数组"
                    )
                copied = self._copy_notebooklm_scene_instruction(
                    parent=dlg,
                    video_detail=video_detail,
                    scenes=scenes,
                    nb_mode=base,
                    nb_variant=var,
                    main_character=main_character,
                    channel_path=channel_path or self.channel_path or "",
                    scene_index=_scene_copy_index[0],
                    visual_style=(visual_style_var.get() or "").strip(),
                    episode=_episode_choice[0],
                )
                if not copied:
                    return False, (
                        "failed to copy NotebookLM prompt — "
                        "scene_content 需要有效 JSON 数组"
                    )
                return True, f"copied {matched} ({base}/{var}) to clipboard"

            # ready=True as soon as the top half exists — scn / scnlm / scnvs must not wait
            # for the large JSON editor + button row to finish building.
            _raise_scene_dialog()
            bind_screen(
                config.SCREEN_STORY_SCENE,
                dlg,
                {
                    "lm": {
                        "get": lambda: (prompt_combo_var.get() or "").strip(),
                        "set": _set_lm_early,
                        "choices": lambda: [opt[0] for opt in nb_prompt_choices],
                    },
                    "style": {
                        "get": lambda: (visual_style_var.get() or "").strip(),
                        "set": _set_style_early,
                        "choices": lambda: list(visual_style_combo_opts),
                    },
                    "instruction": {
                        "get": lambda: (instruction_tx.get("1.0", tk.END) or "").strip(),
                        "set": _set_instruction_early,
                    },
                    "prompt": {
                        "get": _scene_prompt_text_now,
                    },
                    "content": {
                        "get": _get_content_bridge,
                        "set": _set_content_bridge,
                        "persist": _persist_content_bridge,
                    },
                    "scene_choice": {
                        "get": lambda: _scene_index_button_label_bridge(
                            _scene_copy_index[0]
                        ),
                        "set": _set_scene_choice_early,
                        "choices": _scene_choice_labels_bridge,
                    },
                    "episode_choice": {
                        "get": lambda: _episode_choice_label(_episode_choice[0]),
                        "set": _set_episode_choice_early,
                        "choices": _episode_choice_labels_bridge,
                    },
                    "notebooklm": {
                        "get": lambda: "",
                        "set": _set_notebooklm_early,
                        "choices": _nb_labels_bridge,
                    },
                    "cancel": {"click": _close_scene_editor},
                },
            )
            _raise_scene_dialog()
            try:
                loading_lbl.destroy()
            except tk.TclError:
                pass
            scene_ui.update(
                {
                    "prompt_combo_var": prompt_combo_var,
                    "material_var": material_var,
                    "pdf_layout_var": pdf_layout_var,
                    "sync_material_widgets": _sync_material_widgets,
                    "remember_pdf_source": _remember_pdf_source,
                    "prompt_combo": prompt_combo,
                    "nb_prompt_choices": nb_prompt_choices,
                    "instruction_tx": instruction_tx,
                    "visual_style_var": visual_style_var,
                    "visual_style_combo_opts": visual_style_combo_opts,
                    "dialogue_mode_var": dialogue_mode_var,
                    "dialogue_mode_opts": dialogue_mode_opts,
                    "pdf_layout_mode": _pdf_layout_mode,
                    "scene_prompt_text_now": _scene_prompt_text_now,
                    "selected_material_kind": _selected_material_kind,
                    "scene_prompt_params": _scene_prompt_params,
                    "pdf_instruction_for": _pdf_instruction_for,
                    "pick_cover_image": _pick_cover_image,
                }
            )
            dlg.after(50, _build_editor_ui_rest)

        def _build_editor_ui_rest():
            prompt_combo_var = scene_ui["prompt_combo_var"]
            prompt_combo = scene_ui["prompt_combo"]
            nb_prompt_choices = scene_ui["nb_prompt_choices"]
            instruction_tx = scene_ui["instruction_tx"]
            visual_style_var = scene_ui["visual_style_var"]
            visual_style_combo_opts = scene_ui["visual_style_combo_opts"]
            material_var = scene_ui["material_var"]
            dialogue_mode_var = scene_ui["dialogue_mode_var"]
            dialogue_mode_opts = scene_ui["dialogue_mode_opts"]
            _remember_pdf_source = scene_ui["remember_pdf_source"]
            _scene_prompt_params = scene_ui["scene_prompt_params"]
            _pdf_instruction_for = scene_ui["pdf_instruction_for"]
            _pick_cover_image = scene_ui["pick_cover_image"]
            _scene_prompt_text_now = scene_ui["scene_prompt_text_now"]
            _selected_material_kind = scene_ui["selected_material_kind"]
            _require_media_transcript = scene_ui["require_media_transcript"]
            ttk.Label(frm, text="scene_content（JSON 数组）：").pack(anchor=tk.W, pady=(0, 2))
            tx = scrolledtext.ScrolledText(
                frm, wrap=tk.WORD, width=100, height=5, font=("Consolas", 10)
            )
            tx.pack(fill=tk.X, expand=False, pady=(0, 8))
            _bind_text_editor_replace_from_clipboard_on_double_click(tx, dlg)
            scene_ui["tx"] = tx

            def _fill_scene_editor_rest():
                _SCENE_JSON_CHUNK = 1024

                def _insert_scene_json_chunked(scene_json: str, pos: int = 0) -> None:
                    """Small slices so Tk can pump the CLI bridge between inserts."""
                    if not scene_json:
                        return
                    end = min(pos + _SCENE_JSON_CHUNK, len(scene_json))
                    try:
                        if pos == 0:
                            tx.insert("1.0", scene_json[pos:end])
                        else:
                            tx.insert(tk.END, scene_json[pos:end])
                    except tk.TclError:
                        return
                    if end < len(scene_json):
                        dlg.after(
                            5,
                            lambda e=end, s=scene_json: _insert_scene_json_chunked(s, e),
                        )

                def _sync_tx_from_video_detail() -> None:
                    """Show video_detail.scene_content in editor (no validation)."""
                    try:
                        if (tx.get("1.0", tk.END) or "").strip():
                            return
                    except tk.TclError:
                        return
                    scenes = video_detail.get("scene_content") or []
                    if not isinstance(scenes, list) or not scenes:
                        return

                    def _worker() -> None:
                        try:
                            scene_json = json.dumps(scenes, ensure_ascii=False, indent=2)
                        except Exception:
                            scene_json = ""
                        if not scene_json:
                            return
                        try:
                            dlg.after(
                                0,
                                lambda s=scene_json: _insert_scene_json_chunked(s, 0),
                            )
                        except tk.TclError:
                            pass

                    import threading

                    threading.Thread(
                        target=_worker, daemon=True, name="scene-json-dump"
                    ).start()

                scene_ui["_sync_tx_from_video_detail"] = _sync_tx_from_video_detail
                dlg.after_idle(_sync_tx_from_video_detail)

                def _fill_scene_editor_rest_body():
                    def _scene_list_from_editor() -> list | None:
                        raw = (tx.get("1.0", tk.END) or "").strip()
                        if not raw:
                            return None
                        try:
                            parsed = json.loads(safe_clipboard_json_copy(raw))
                        except (json.JSONDecodeError, TypeError):
                            return None
                        if not isinstance(parsed, list):
                            return None
                        return parsed if parsed else None

                    btn_row = ttk.Frame(scene_ui["action_bar"])
                    btn_row.pack(side=tk.LEFT)

                    _scene_copy_index = scene_ui["_scene_copy_index"]
                    _episode_choice = scene_ui["_episode_choice"]

                    def _scene_index_button_label(idx: int) -> str:
                        return "All" if idx < 0 else str(idx + 1)

                    def _scenes_in_episode() -> list:
                        return _filter_scenes_by_episode(
                            _scene_list_from_editor() or [], _episode_choice[0]
                        )

                    def _scene_count() -> int:
                        return len(_scenes_in_episode())

                    def _scene_choice_labels():
                        n = _scene_count()
                        return ["All"] + [str(i) for i in range(1, n + 1)]

                    def _episode_choice_labels():
                        return ["全部"] + _episode_ids_in_scenes(_scene_list_from_editor())

                    def _sync_choice_buttons():
                        try:
                            episode_btn.config(text=_episode_choice_label(_episode_choice[0]))
                        except (NameError, tk.TclError):
                            pass
                        try:
                            scene_index_btn.config(
                                text=_scene_index_button_label(_scene_copy_index[0])
                            )
                        except (NameError, tk.TclError):
                            pass





                    def _busy(btn):
                        try:
                            btn.config(state=tk.DISABLED)
                            dlg.config(cursor="watch")
                            dlg.update_idletasks()
                        except tk.TclError:
                            pass

                    def _idle(btn):
                        try:
                            btn.config(state=tk.NORMAL)
                            dlg.config(cursor="")
                        except tk.TclError:
                            pass

                    def _on_smart_saved():
                        """智能生成成功并保存之后：照旧 on_saved，再自动打开项目名称建议。"""
                        if callable(on_saved):
                            on_saved()
                        offer = scene_ui.get("offer_title_suggest")
                        if callable(offer):
                            dlg.after(300, offer)

                    def on_smart_generate():
                        label = (prompt_combo_var.get() or "").strip()
                        user_instr = (instruction_tx.get("1.0", tk.END) or "").strip()
                        kind = _selected_material_kind()
                        override = None
                        if config_channel.is_scene_summary_image_label(label):
                            # 场景总图不调 LLM / 图片 API：按编辑区（或已存）的 scene_content 出提示词。
                            scenes = _parse_scene_json_list(tx.get("1.0", tk.END) or "") or []
                            params = dict(_scene_prompt_params())
                            if scenes:
                                params["scenes"] = scenes
                            _, img_prompt = self._combined_prompt_text_for_label(
                                video_detail, label, prompt_params=params
                            )
                            if not (img_prompt or "").strip():
                                messagebox.showwarning(
                                    "场景总图",
                                    "这一条还没有场景（scene_content 为空）。\n先用其他模板生成场景，再选「场景总图」。",
                                    parent=dlg,
                                )
                                return
                            def _on_scene_summary_image(pil_img):
                                ok, dest, _err = save_pil_image_to_cover_array(
                                    pil_img,
                                    video_detail,
                                    channel=self._channel_config_key(),
                                    filename_hint="scene_summary",
                                )
                                if ok and dest:
                                    persist(video_detail, parent=dlg)
                                    drop_ctx2 = getattr(dlg, "_summary_drop_ctx", None)
                                    refresh_media = (
                                        drop_ctx2.get("refresh_feature_media_row")
                                        if isinstance(drop_ctx2, dict)
                                        else None
                                    )
                                    if callable(refresh_media):
                                        try:
                                            refresh_media()
                                        except Exception:
                                            pass
                                    show_auto_close_popup(
                                        dlg,
                                        "场景总图",
                                        f"返回的图片已保存到封面列表：\n{os.path.basename(dest)}",
                                    )

                            # 不调图片 API：打开 LLM 手动窗口（提示词在左），人把提示词拿去处理。
                            # 返回的图片会通过 on_image_response 回调保存到 cover_image 数组。
                            self.llm_api.show_manual_window(
                                img_prompt, "", on_image_response=_on_scene_summary_image
                            )
                            return
                        if config_channel.is_step_image_label(label):
                            # 图片分解不调 LLM / 图片 API：给出提示词 + 封面图片，用户自己带到 AI 图片工具。
                            img = (_find_gen_video_webp_for_row(video_detail) or "").strip()
                            if not img:
                                if messagebox.askyesno(
                                    "图片分解",
                                    "这一条还没有封面图片。现在选一张吗？",
                                    parent=dlg,
                                ):
                                    _pick_cover_image()
                                img = (_find_gen_video_webp_for_row(video_detail) or "").strip()
                                if not img:
                                    return
                            step_params = _scene_prompt_params()
                            _, img_prompt = self._combined_prompt_text_for_label(
                                video_detail, label, prompt_params=step_params
                            )
                            try:
                                step_no = max(1, int(step_params.get("steps") or 1))
                            except (TypeError, ValueError):
                                step_no = 1
                            scene_list = _parse_scene_json_list(tx.get("1.0", tk.END) or "") or []
                            style_now = str(
                                step_params.get("visual_style")
                                or project_manager.LAST_VISUAL_STYLE
                                or ""
                            )

                            # 第 2 步的提示词：沿用「生场视频」的提示词构建函数，选项用默认
                            # （单画面、不加背景文字、风格不变、不指定运镜和动画），按第 k 场的内容拼。
                            video_scene = (
                                [scene_list[step_no - 1]] if step_no <= len(scene_list) else []
                            )
                            saved_video = (project_manager.PROJECT_CONFIG or {}).get("video_prompt")
                            video_narrative = "story"
                            video_text = "erase"
                            if isinstance(saved_video, dict):
                                picked = saved_video.get("narrative")
                                if picked in {k for k, _ in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES}:
                                    video_narrative = picked
                                picked_text = saved_video.get("text")
                                if picked_text in {k for k, _ in config_prompt.FLOW_CAPTION_CHOICES}:
                                    video_text = picked_text
                            video_prompt = config_prompt.build_video_flow_prompt(
                                frames="one",
                                background="none",
                                evolve="keep",
                                visual_style=style_now,
                                scene_content=video_scene,
                                language=getattr(self, "language", "") or "",
                                host_narrator=_project_look_from_row(video_detail)[2],
                                narrative=video_narrative,
                                text=video_text,
                            )

                            def _on_workflow_image(step_idx, step_title, pil_img):
                                ok, dest, _err = save_pil_image_to_cover_array(
                                    pil_img,
                                    video_detail,
                                    channel=self._channel_config_key(),
                                    filename_hint=f"step_{step_no}_{step_idx + 1}",
                                )
                                if ok and dest:
                                    persist(video_detail, parent=dlg)
                                    drop_ctx2 = getattr(dlg, "_summary_drop_ctx", None)
                                    refresh_media = (
                                        drop_ctx2.get("refresh_feature_media_row")
                                        if isinstance(drop_ctx2, dict)
                                        else None
                                    )
                                    if callable(refresh_media):
                                        try:
                                            refresh_media()
                                        except Exception:
                                            pass
                                    return dest
                                return None

                            # 两步手动流程（LLM 手动窗口，不调任何图片 / 视频 API）：
                            # 第 1 步：提示词在左，封面图片在右，做第 k 步细节图；
                            # 第 2 步：用第 1 步的图做视频，只放提示词（那张图已经在 AI 工具里）。
                            # 返回的图片会通过 on_image_response 回调保存到 cover_image 数组。
                            results = self.llm_api.show_manual_workflow(
                                [
                                    {
                                        "title": f"封面图 → 第 {step_no} 步细节图",
                                        "system": img_prompt,
                                        "images": [img],
                                    },
                                    {
                                        "title": f"第 {step_no} 步的图 → 视频",
                                        "system": video_prompt,
                                    },
                                ],
                                title="图片分解",
                                on_image_response=_on_workflow_image,
                            )
                            saved_any = any(
                                r.get("saved_path") for r in results if isinstance(r, dict)
                            )
                            if saved_any:
                                show_auto_close_popup(
                                    dlg,
                                    "图片分解",
                                    "返回的图片已保存到封面列表。",
                                )
                            return
                        if kind == "image":
                            override = _image_material_override(video_detail)
                        elif kind == "pdf":
                            cached = _remember_pdf_source()
                            if not (cached.get("text") or "").strip():
                                messagebox.showwarning(
                                    "PDF",
                                    "这条没有可用的 PDF。",
                                    parent=dlg,
                                )
                                return
                            override = cached["text"]
                            extra = _pdf_instruction_for(label, int(cached.get("pages") or 0))
                            user_instr = (user_instr + "\n\n" + extra).strip() if user_instr else extra
                        elif material_var.get() == "media":
                            media_path = _find_item_media_file(video_detail)
                            if not media_path:
                                messagebox.showwarning(
                                    "媒体",
                                    "先把音频或 mp4 拖到材料区。",
                                    parent=dlg,
                                )
                                return
                            if not _require_media_transcript(media_path):
                                return
                            kind = _selected_material_kind()
                            override = _media_material_override(video_detail, media_path)
                        source_note = _prompt_text_for_material(" ", kind).strip()
                        if source_note:
                            user_instr = (user_instr + "\n\n" + source_note).strip() if user_instr else source_note
                        attachment = ""
                        if kind == "pdf":
                            attachment = _find_gen_video_slide_for_row(video_detail)
                        elif kind == "image":
                            attachment = _find_gen_video_webp_for_row(video_detail)
                        elif material_var.get() == "media" and kind != "transcript":
                            # 有文字稿就直接用文字稿，不再附媒体；没有再附媒体本身。
                            attachment = _find_item_media_file(video_detail)
                        self._run_scene_smart_generate_async(
                            dlg,
                            video_detail,
                            label,
                            lambda merged: (tx.delete("1.0", tk.END), tx.insert("1.0", merged)),
                            get_instruction=lambda instr=user_instr: instr,
                            on_busy=lambda: _busy(smart_btn),
                            on_idle=lambda: _idle(smart_btn),
                            persist_fn=persist,
                            on_saved=_on_smart_saved,
                            on_title_updated=on_title_updated,
                            content_override=override,
                            dialogue_mode=(dialogue_mode_var.get() or "").strip(),
                            attachment=attachment,
                            prompt_params=_scene_prompt_params(),
                        )

                    def on_persist_keep_open():
                        raw = (tx.get("1.0", tk.END) or "").strip()
                        ok, msg, parsed = apply_scene_content_from_editor_text(
                            video_detail, raw
                        )
                        if not ok:
                            return False, msg
                        result_holder[0] = parsed
                        if not persist(video_detail, parent=dlg):
                            return False, "写入频道列表失败"
                        if callable(on_saved):
                            try:
                                on_saved()
                            except Exception:
                                pass
                        return True, (
                            f"saved {len(parsed or [])} scene(s) to channel list "
                            "(window kept open)"
                        )

                    def on_confirm():
                        raw = (tx.get("1.0", tk.END) or "").strip()
                        if not raw:
                            if not messagebox.askyesno(
                                "清空场景",
                                "内容为空，将删除本条 scene_content。继续？",
                                parent=dlg,
                            ):
                                return
                            video_detail.pop("scene_content", None)
                            result_holder[0] = []
                        else:
                            ok, msg, parsed = apply_scene_content_from_editor_text(
                                video_detail, raw
                            )
                            if not ok:
                                show_auto_close_popup(
                                    dlg,
                                    "JSON 无效",
                                    msg,
                                    kind="error",
                                )
                                return
                            result_holder[0] = parsed
                        if not persist(video_detail, parent=dlg):
                            return
                        _dismiss_scene_window()
                        if callable(on_saved):
                            on_saved()

                    smart_style = "StorySmartGenerate.TButton"
                    ttk.Style().configure(
                        smart_style,
                        font=("Microsoft YaHei UI", 9, "bold"),
                        padding=(11, 6),
                    )
                    smart_btn = ttk.Button(
                        scene_ui["prompt_combo"].master,
                        text="智能生成",
                        command=on_smart_generate,
                        style=smart_style,
                        width=11,
                    )
                    smart_btn.pack(
                        side=tk.LEFT, padx=(0, 6), before=scene_ui["prompt_combo"]
                    )
                    if embedded:
                        def _summary_scenes() -> list:
                            parsed = _parse_scene_json_list(tx.get("1.0", tk.END) or "")
                            if parsed:
                                return parsed
                            sc = video_detail.get("scene_content")
                            return [item for item in sc if isinstance(item, dict)] if isinstance(sc, list) else []

                        sum_btn = ttk.Button(scene_ui["smart_slot"], text="生成摘要", width=8)

                        def _on_summarize() -> None:
                            sum_btn.config(state=tk.DISABLED)

                            def _enable() -> None:
                                try:
                                    sum_btn.config(state=tk.NORMAL)
                                except tk.TclError:
                                    pass

                            self._summarize_scene_list(
                                dlg, video_detail, _summary_scenes(), on_done=_enable
                            )

                        sum_btn.config(command=_on_summarize)
                        sum_btn.pack(side=tk.LEFT, padx=(0, 8))
                    if callable(on_save_story):
                        title_host = scene_ui["prompt_combo"].master
                        title_var = None
                        host_ctx = getattr(dlg, "_summary_drop_ctx", None)
                        if isinstance(host_ctx, dict):
                            title_var = host_ctx.get("story_title_var")
                        if title_var is None:
                            title_var = tk.StringVar(value=_youtube_row_source_title(video_detail))
                        ttk.Entry(title_host, textvariable=title_var).pack(
                            side=tk.LEFT, fill=tk.X, expand=True, padx=(16, 6)
                        )
                        ttk.Button(
                            title_host, text="保存", width=8, command=on_save_story
                        ).pack(side=tk.LEFT, padx=(0, 8))

                        # 拖进文件改名时用这个名称栏和「保存」按钮的保存
                        scene_ui["name_field"] = (title_var, on_save_story)

                        def _offer_title_suggestions(_var=title_var) -> None:
                            """智能生成之后：按场景内容出 3 个项目名建议，选了新名称就走「保存」按钮的路径改名。"""
                            from gui.project_title_suggest import ask_project_title

                            sc = video_detail.get("scene_content")
                            scenes_now = [x for x in sc if isinstance(x, dict)] if isinstance(sc, list) else []
                            if not scenes_now:
                                return

                            def _chosen(name: str) -> None:
                                # 名称栏 → 外层 title；有项目时也改 project_profile.video_title（标题栏显示的就是它）
                                prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
                                if isinstance(prof, dict) and prof:
                                    prof["video_title"] = name
                                _var.set(name)
                                on_save_story()
                                cfg = project_manager.PROJECT_CONFIG
                                if isinstance(cfg, dict) and (cfg.get("pid") or "") and (
                                    cfg.get("pid") == project_manager.list_json_row_workflow_pid(video_detail)
                                ):
                                    cfg["video_title"] = name  # 同一项目开着时，以后保存项目配置不会改回旧名

                            ask_project_title(dlg, current=(_var.get() or "").strip(), scenes=scenes_now, on_chosen=_chosen)

                        scene_ui["offer_title_suggest"] = _offer_title_suggestions
                    if callable(on_regen_project):
                        ttk.Button(
                            scene_ui["smart_slot"], text="重新生成项目", command=on_regen_project
                        ).pack(side=tk.LEFT, padx=(0, 4))

                    def _offer_pdf_scene_generate(pdf_path: str) -> None:
                        importer = scene_ui.get("import_slide_pdf")
                        if callable(importer):
                            importer(pdf_path)

                    def _on_scene_pdf_drop(event):
                        master = getattr(event, "widget", None) or dlg
                        paths = _dnd_normalize_file_paths(master, getattr(event, "data", None))
                        if not paths:
                            return
                        text_file = next((p for p in paths if _is_plain_text_file_path(p)), "")
                        pdf_file = next((p for p in paths if p.lower().endswith(".pdf")), "")
                        media_file = next((p for p in paths if _media_kind_for_path(p)), "")
                        image_files = [
                            p for p in paths
                            if os.path.splitext(p)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
                        ]
                        offer = scene_ui.get("offer_rename")
                        if text_file:
                            importer = scene_ui.get("import_analyzed_text_file")
                            if callable(importer):
                                importer(text_file)
                            if callable(offer):
                                offer(paths[0])  # 这一批第一个文件（任何类型）问一次
                            return
                        # 材料区：音频/视频换掉原来的，PDF 换掉原来的，图片加进列表；同时拖几种也都收下。
                        if media_file:
                            importer = scene_ui.get("import_item_media")
                            if callable(importer):
                                importer(media_file)
                        if pdf_file:
                            _offer_pdf_scene_generate(pdf_file)
                        if image_files:
                            importer = scene_ui.get("import_cover_image")
                            if callable(importer):
                                for img_path in image_files:
                                    importer(img_path)
                        # 这一批第一个文件（任何类型）：问一次要不要改项目名称
                        if callable(offer):
                            offer(paths[0])

                    if DND_FILES and callable(getattr(dlg, "drop_target_register", None)):
                        def _bind_pdf_drop(widget):
                            try:
                                widget.drop_target_register(DND_FILES)
                                widget.dnd_bind("<<Drop>>", _on_scene_pdf_drop)
                            except (tk.TclError, AttributeError, Exception):
                                pass

                        def _walk_pdf_drop(widget):
                            _bind_pdf_drop(widget)
                            try:
                                for child in widget.winfo_children():
                                    _walk_pdf_drop(child)
                            except tk.TclError:
                                pass

                        _walk_pdf_drop(frm)
                        scene_ui["walk_drop"] = _walk_pdf_drop
                    if not nb_prompt_choices:
                        smart_btn.config(state=tk.DISABLED)
                    _narr_opts = [
                        x for x in config.narrator_person_options() if (x or "").strip()
                    ]
                    _narr_named = ""
                    _pp = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
                    if isinstance(_pp, dict):
                        _narr_named = (_pp.get("narrator") or "").strip()
                    if not _narr_named:
                        _narr_named = (video_detail.get("narrator") or "").strip()
                    if not _narr_named:
                        _narr_named = (project_manager.LAST_NARRATOR or "").strip()
                    if _narr_named and _narr_named not in _narr_opts:
                        _narr_opts = [_narr_named] + _narr_opts
                    if not _narr_named and _narr_opts:
                        _narr_named = _narr_opts[0]
                    narrator_var = tk.StringVar(value=_narr_named)
                    scene_ui["narrator_var"] = narrator_var

                    def _commit_story_narrator(persist=False):
                        nar = (narrator_var.get() or "").strip()
                        if not nar:
                            return
                        video_detail["narrator"] = nar
                        pp = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
                        if isinstance(pp, dict):
                            pp["narrator"] = nar
                        project_manager.LAST_NARRATOR = nar
                        if not persist:
                            return
                        try:
                            config.save_yt_tools_prefs({"narrator": nar})
                        except Exception:
                            pass
                        self._persist_video_detail_story(video_detail, parent=dlg)

                    _commit_story_narrator(False)
                    ttk.Label(btn_row, text="讲员").pack(side=tk.LEFT, padx=(0, 4))
                    narrator_combo = ttk.Combobox(
                        btn_row,
                        textvariable=narrator_var,
                        values=_narr_opts,
                        state="readonly" if _narr_opts else "disabled",
                        width=26,
                    )
                    narrator_combo.pack(side=tk.LEFT, padx=(0, 8))
                    narrator_combo.bind(
                        "<<ComboboxSelected>>",
                        lambda _e: _commit_story_narrator(True),
                    )
                    if callable(on_open_project):
                        open_host = scene_ui["prompt_combo"].master
                        open_style = "StoryOpenProject.TButton"
                        ttk.Style().configure(
                            open_style,
                            font=("Microsoft YaHei UI", 9, "bold"),
                            padding=(10, 5),
                        )
                        ttk.Button(
                            open_host,
                            text="打开项目",
                            style=open_style,
                            width=10,
                            command=on_open_project,
                        ).pack(side=tk.RIGHT, padx=(8, 0))
                        ttk.Separator(open_host, orient=tk.VERTICAL).pack(
                            side=tk.RIGHT, fill=tk.Y, padx=(16, 10)
                        )
                    save_btn = ttk.Button(btn_row, text="保存", command=on_confirm)
                    if not embedded:
                        save_btn.pack(side=tk.LEFT, padx=(0, 8))
                    drop_ctx = getattr(dlg, "_summary_drop_ctx", None)
                    if isinstance(drop_ctx, dict):
                        drop_ctx["save_scene_content"] = on_persist_keep_open
                    cancel_btn = ttk.Button(btn_row, text="取消", command=_dismiss_scene_window)
                    if not embedded:
                        cancel_btn.pack(side=tk.LEFT)

                    from gui.cli_bridge import bind_screen, match_choice, unbind_screen

                    def _unbind_scene_cli(_event=None):
                        if _event is not None and getattr(_event, "widget", None) is not dlg:
                            return
                        unbind_screen(config.SCREEN_STORY_SCENE)

                    def _close_scene_editor():
                        if getattr(self, "_scene_content_dialog", None) is dlg:
                            self._scene_content_dialog = None
                        _unbind_scene_cli()
                        _dismiss_scene_window()

                    def on_confirm_cli():
                        on_confirm()
                        try:
                            if not dlg.winfo_exists():
                                _unbind_scene_cli()
                        except tk.TclError:
                            _unbind_scene_cli()

                    def _set_lm(value: str):
                        labels = [opt[0] for opt in nb_prompt_choices]
                        matched = match_choice(value, labels)
                        if not matched:
                            return False, "unknown LM prompt: " + value + "\nchoices: " + " | ".join(labels)
                        _apply_scene_lm_combo(
                            prompt_combo, prompt_combo_var, labels, matched, host=dlg
                        )
                        return True, f"{matched} — 选LM提示下拉已切换。"

                    def _set_style(value: str):
                        matched = match_choice(value, visual_style_combo_opts)
                        if not matched:
                            return False, "unknown style: " + value + "\nchoices: " + " | ".join(visual_style_combo_opts)
                        visual_style_var.set(matched)
                        return True, matched

                    def _set_dialogue(value: str):
                        matched = match_choice(value, dialogue_mode_opts)
                        if not matched:
                            return False, "unknown dialogue: " + value + "\nchoices: " + " | ".join(dialogue_mode_opts)
                        dialogue_mode_var.set(matched)
                        return True, matched

                    def _set_instruction(value: str):
                        instruction_tx.delete("1.0", tk.END)
                        instruction_tx.insert("1.0", value)
                        return True, "instruction set"

                    def _set_content(value: str):
                        tx.delete("1.0", tk.END)
                        tx.insert("1.0", value)
                        return True, "scene_content set"

                    def _set_episode_choice(value: str):
                        raw = (value or "").strip().translate(
                            str.maketrans("０１２３４５６７８９", "0123456789")
                        )
                        if not raw:
                            return False, "empty episode_choice"
                        ids = _episode_ids_in_scenes(_scene_list_from_editor())
                        low = raw.lower().replace(" ", "")
                        if low in ("all", "全部", "0", "-1"):
                            _episode_choice[0] = ""
                        elif not ids:
                            return False, "当前场景没有 episode，只能选全部"
                        elif raw in ids:
                            _episode_choice[0] = raw
                        else:
                            return False, (
                                "unknown episode_choice: " + value
                                + "\nchoices: " + " | ".join(_episode_choice_labels())
                            )
                        _scene_copy_index[0] = -1
                        _sync_choice_buttons()
                        return True, (
                            f"episode_choice={_episode_choice_label(_episode_choice[0])}"
                        )

                    def _set_scene_choice(value: str):
                        raw = (value or "").strip().translate(
                            str.maketrans("０１２３４５６７８９", "0123456789")
                        )
                        if not raw:
                            return False, "empty scene_choice"
                        n = _scene_count()
                        low = raw.lower().replace(" ", "")
                        if low in ("all", "全部", "0", "-1"):
                            _scene_copy_index[0] = -1
                        elif raw.isdigit():
                            i = int(raw)
                            if i < 1:
                                return False, "scene_choice 用 all 或 1/2/3/…"
                            if n > 0 and i > n:
                                return False, f"scene {i} out of range (1..{n})"
                            _scene_copy_index[0] = i - 1
                        else:
                            return False, (
                                "unknown scene_choice: " + value
                                + "（用 all / 1 / 2 / …）\nchoices: "
                                + " | ".join(_scene_choice_labels())
                            )
                        try:
                            scene_index_btn.config(
                                text=_scene_index_button_label(_scene_copy_index[0])
                            )
                        except (NameError, tk.TclError):
                            pass
                        scene_msg = (
                            f"scene_choice={_scene_index_button_label(_scene_copy_index[0])}"
                        )
                        if _scene_copy_index[0] >= 0:
                            from utility.telegram_session import load_grok_scene_video_nb_index

                            nb_idx = load_grok_scene_video_nb_index()
                            base, var, _ = config_prompt.grok_scene_video_nb_export(nb_idx)
                            copied = self._copy_notebooklm_scene_instruction(
                                parent=dlg,
                                video_detail=video_detail,
                                scenes=_scene_list_from_editor() or [],
                                nb_mode=base,
                                nb_variant=var,
                                main_character=main_character,
                                channel_path=channel_path or self.channel_path or "",
                                scene_index=_scene_copy_index[0],
                                visual_style=(visual_style_var.get() or "").strip(),
                                episode=_episode_choice[0],
                            )
                            if not copied:
                                return False, (
                                    f"{scene_msg}; failed to copy NotebookLM video 提示词 — "
                                    "scene_content 需要有效 JSON 数组"
                                )
                            try:
                                nb_label = config_prompt.grok_scene_video_nb_choice_label(nb_idx)
                            except ValueError:
                                nb_label = config_prompt.nb_export_mode_label(base, var)
                            return True, (
                                f"{scene_msg}; copied [{nb_idx}] {nb_label} to clipboard"
                            )
                        return True, scene_msg

                    def _nb_choice_rows():
                        lang = config.llm_language_label(getattr(self, "language", "") or "")
                        return config_prompt.notebooklm_export_flat_choices(lang)

                    def _nb_labels():
                        return [row[0] for row in _nb_choice_rows()]

                    def _set_notebooklm(value: str):
                        rows = _nb_choice_rows()
                        labels = [row[0] for row in rows]
                        matched = match_choice(value, labels)
                        base = var = ""
                        if matched:
                            for label, b, v in rows:
                                if label == matched:
                                    base, var = b, v
                                    break
                        else:
                            parsed = config_prompt.parse_nb_export_choice(value)
                            if parsed:
                                base, var = parsed
                                try:
                                    matched = next(
                                        label for label, b, v in rows if b == base and v == var
                                    )
                                except StopIteration:
                                    matched = config_prompt.nb_export_mode_label(base, var)
                        if not base:
                            return False, (
                                "unknown NotebookLM export: " + value
                                + "\nchoices: " + " | ".join(labels)
                            )
                        copied = self._copy_notebooklm_scene_instruction(
                            parent=dlg,
                            video_detail=video_detail,
                            scenes=_scene_list_from_editor() or [],
                            nb_mode=base,
                            nb_variant=var,
                            main_character=main_character,
                            channel_path=channel_path or self.channel_path or "",
                            scene_index=_scene_copy_index[0],
                            visual_style=(visual_style_var.get() or "").strip(),
                            episode=_episode_choice[0],
                        )
                        if not copied:
                            return False, (
                                "failed to copy NotebookLM prompt — "
                                "scene_content 需要有效 JSON 数组"
                            )
                        return True, f"copied {matched} ({base}/{var}) to clipboard"

                    save_btn.config(command=on_confirm_cli)
                    cancel_btn.config(command=_close_scene_editor)
                    bind_screen(
                        config.SCREEN_STORY_SCENE,
                        dlg,
                        {
                            "lm": {
                                "get": lambda: (prompt_combo_var.get() or "").strip(),
                                "set": _set_lm,
                                "choices": lambda: [opt[0] for opt in nb_prompt_choices],
                            },
                            "style": {
                                "get": lambda: (visual_style_var.get() or "").strip(),
                                "set": _set_style,
                                "choices": lambda: list(visual_style_combo_opts),
                            },
                            "dialogue": {
                                "get": lambda: (dialogue_mode_var.get() or "").strip(),
                                "set": _set_dialogue,
                                "choices": lambda: list(dialogue_mode_opts),
                            },
                            "instruction": {
                                "get": lambda: (instruction_tx.get("1.0", tk.END) or "").strip(),
                                "set": _set_instruction,
                            },
                            "content": {
                                "get": lambda: (tx.get("1.0", tk.END) or "").strip(),
                                "set": _set_content,
                                "persist": on_persist_keep_open,
                            },
                            "scene_choice": {
                                "get": lambda: _scene_index_button_label(_scene_copy_index[0]),
                                "set": _set_scene_choice,
                                "choices": _scene_choice_labels,
                            },
                            "episode_choice": {
                                "get": lambda: _episode_choice_label(_episode_choice[0]),
                                "set": _set_episode_choice,
                                "choices": _episode_choice_labels,
                            },
                            "prompt": {
                                "get": _scene_prompt_text_now,
                            },
                            "notebooklm": {
                                "get": lambda: "",
                                "set": _set_notebooklm,
                                "choices": _nb_labels,
                            },
                            "save": {"click": on_confirm_cli},
                            "cancel": {"click": _close_scene_editor},
                            "generate": {"click": on_smart_generate},
                        },
                    )
                    dlg.bind("<Destroy>", _unbind_scene_cli)
                    if not embedded:
                        dlg.protocol("WM_DELETE_WINDOW", _close_scene_editor)
                    _raise_scene_dialog()

                # 这一排和窗口一起出现。场景 JSON 仍按小段写入，避免一次插进大段文字卡住界面。
                _fill_scene_editor_rest_body()
                if embedded:
                    dlg.after_idle(lambda: _fit_story_summary_window(dlg))
                    dlg.after(250, lambda: _fit_story_summary_window(dlg))

            dlg.after_idle(_fill_scene_editor_rest)


        def _build_editor_ui_guarded():
            try:
                _build_editor_ui()
            except Exception as exc:
                # Without this the stub bind stays ready=False forever and every
                # SCENE command would answer "仍在加载".
                try:
                    loading_lbl.config(text=f"SCENE 编辑器加载失败：{exc}")
                except tk.TclError:
                    pass
                _unbind_scene_early(config.SCREEN_STORY_SCENE)
                if getattr(self, "_scene_content_dialog", None) is dlg:
                    self._scene_content_dialog = None
                raise

        parent.after(1, _build_editor_ui_guarded)
        return result_holder[0]
