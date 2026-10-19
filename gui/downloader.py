import os
import sys
import subprocess
import json
import re
import threading
import glob
import copy

import config
import config_channel
import config_prompt
from datetime import datetime


from utility import llm_api
from utility.file_util import safe_copy_overwrite, safe_remove, safe_clipboard_json_copy, show_auto_close_popup
from gui.choice_dialog import askchoice
import project_manager

try:
    from tkcalendar import Calendar as TkCalendar
except ImportError:
    TkCalendar = None

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

# 导入所需模块
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog
from tkinter import filedialog
from utility.file_util import _AUDIO_DROP_SUFFIXES, _TEXT_DROP_SUFFIXES, _VIDEO_DROP_SUFFIXES, _collect_unique_file_paths, _drop_suffix, _is_existing_file, _is_plain_text_file_path, _is_windows_file_in_use, _media_kind_for_path, _move_file_to_dest_with_fallback, _read_plain_text_file, _sanitize_list_row_id_stem, _win_long_path  # re-export
from utility.media_probe import _ffprobe_video_height, _media_duration_seconds  # re-export
from utility.pdf_util import _images_to_temp_pdf, _pdf_page_count  # re-export
from utility.tags_text import _plain_item_tags, _strip_markdown_embedded_images  # re-export
from utility.time_util import _format_publish_display_date, _should_update_upload_date  # re-export
from utility.scene_json import _parse_scene_json_list, _scene_content_nonempty_value  # re-export
from gui.raise_window import _drop_topmost, _force_tk_repaint, _hwnds_for_tk, _map_tk_window_noactivate, _raise_own_window  # re-export
from gui.clipboard_util import _copy_file_to_clipboard_hdrop, _copy_text_to_clipboard, _dnd_normalize_file_paths, _dnd_paths_splitlist, _read_host_clipboard_text  # re-export
from gui.dl.youtube_dl import MediaDownloader, YOUTUBE_AUDIO_FORMAT_FALLBACKS, YOUTUBE_VIDEO_FORMAT_FALLBACKS, YOUTUBE_VIDEO_MIN_HEIGHT_TO_SKIP_REDOWNLOAD, _GENERIC_PROJECT_VIDEO_TITLES, _YT_DOWNLOAD_PREFS_JSON, _channel_list_dir_for_media_downloader, _downloader_aux_dir, _infer_channel_list_item_media_dir, _iter_node_executable_candidates, _log_yt_downloaded_format_info, _normalize_channel_list_item_for_storage, _normalize_channel_videos_for_storage, _normalize_youtube_watch_url, _sync_project_video_title_on_list_row, _verify_node_executable, _video_youtube_id, _write_channel_list_json_file, _youtube_best_video_ydl_opts, _youtube_format_error_message, _youtube_row_display_title, _youtube_row_project_title, _youtube_row_source_title  # re-export
from gui.dl.list_store import GEN_VIDEO_SLIDE_KEY, _STORY_COPY_PROJECT_KEYS, _apply_project_config_to_list_row, _channel_list_row_complete_score, _channel_list_row_dedupe_key, _channel_list_row_tree_key, _copy_story_list_row, _drop_cloned_duplicates_of_row, _find_cloned_project_pids_for_source, _find_gen_video_slide_for_row, _fresh_story_row_id, _gen_video_id_stem_candidates_for_row, _is_viewing_topic_category_program_list, _list_json_item_matches_pid, _list_row_index_for_pid, _persist_channel_videos, _remove_pid_from_topic_category_lists, _topic_category_program_list_path, _upsert_topic_category_program_list_row, _video_detail_project_pid, _video_detail_source_keys, _youtube_row_list_display_title, _youtube_row_list_suffix_title, _youtube_row_scene_meta_title, dedupe_channel_video_list  # re-export
from gui.dl.gen_video_files import GEN_VIDEO_CLIP_SEGMENTS_KEY, STORY_MEDIA_KEY, STORY_TRANSCRIPT_KEY, _find_gen_video_mp4_for_row, _find_gen_video_webp_for_row, _find_item_media_file, _find_item_transcript_file, _gen_video_cover_webp_dest_filename, _gen_video_slide_pdf_dest_filename, _gen_video_storage_dir, _gen_video_watermark_dest_filename, _get_gen_video_clip_segments, _item_transcript_text, _normalize_gen_video_clip_segment, _set_gen_video_clip_segments, _title_from_cover_image_path  # re-export
from gui.dl.program_clipboard import ChannelClipboardManagerWindow, LEGACY_CHANNEL_CLIPBOARD_JSON_NAME, PROGRAM_CLIPBOARD_JSON_NAME, _dedupe_program_clipboard_items_by_preview, _load_program_clipboard_data, _merge_legacy_clipboard_file_into_items, _migrate_legacy_channel_clipboards, _program_clipboard_file, _program_clipboard_make_id, _program_clipboard_manager_window, _program_clipboard_preview_key, _program_clipboard_source_label, _save_program_clipboard_data, channel_clipboard_append_item, program_clipboard_append_item  # re-export
from gui.dl.publish_schedule import _INPUT_PUBLISH_TXT_RE, _apply_publish_create_date, _find_category_subfolder, _folder_english_prefix, _gen_video_publish_mp4_if_ready, _is_already_in_category_folder, _move_published_input_media_files, _parse_input_media_category_short_code, _publish_cell_display, _resolve_review_publish_mp4_path, _scan_input_media_publish_map, ask_publish_schedule_dialog  # re-export
from gui.dl.workflow_launch import _begin_workflow_launch, _focus_open_workflow, _launch_gui_wf_from_list_json, _launch_gui_wf_open_pid, _release_workflow_launch, _watch_workflow_launch, _workflow_launch_guard, _workflow_launch_guard_lock  # re-export
from gui.dl.prompts_notebooklm import _MEDIA_SCENE_LENGTH_NOTE, _MEDIA_SCENE_TIMING_NOTE, _build_notebooklm_prompt_for_row, _format_nb_prompt_template, _image_material_override, _media_length_line, _media_material_override, _media_source_blurb, _notebooklm_prompt_context_from_video_detail, _notebooklm_row_tags_text, _notebooklm_row_topic_fields, _pdf_scene_generation_instruction, _prompt_choice_entries, _prompt_text_for_material, _resolve_combined_prompt_template, _scene_entry_heading, _scene_prompt_narrator, _transcript_source_blurb  # re-export
from gui.dl.slides_pdf import _SUMMARY_IMAGE_SUFFIXES, _download_slide_files, _pdf_pages_as_scene_source, _slide_thumb_image, ask_download_slide_pdf  # re-export
from gui.dl.summary_window import _fit_story_summary_window, _refresh_summary_window_title, _run_summary_gen_video_clip_review, schedule_summary_gen_video_clip_review  # re-export
from gui.dl.cover_title import _apply_project_video_title, _apply_video_title_before_cover_save, _ask_video_title_before_cover_save_dialog, _cover_save_story_title, _cover_title_preset_options, _scene_captions_for_cover_title, accept_summary_cover_image, save_cover_image_as_gen_video_webp, save_pil_image_to_cover_array  # re-export

















































def _bind_text_editor_replace_from_clipboard_on_double_click(tx, clipboard_host) -> None:
    """双击编辑区：若系统剪贴板有非空内容，则用其替换全文。"""
    def _on_double(_event=None):
        clip = (_read_host_clipboard_text(clipboard_host) or "").strip()
        if not clip:
            return "break"
        tx.delete("1.0", tk.END)
        tx.insert("1.0", clip)
        return "break"

    tx.bind("<Double-Button-1>", _on_double, add="+")
































































def _project_look_from_row(vd, cfg=None) -> tuple[str, str, str]:
    """一条故事上的风格、对话方式、解说员。项目配置优先，没有再用这条上的值。"""
    sources = []
    if isinstance(cfg, dict):
        sources.append(cfg)
    if isinstance(vd, dict):
        pp = vd.get(project_manager.PROJECT_PROFILE_KEY)
        if isinstance(pp, dict):
            sources.append(pp)
        sources.append(vd)
    visual_style = ""
    dialogue_mode = ""
    narrator = ""
    for src in sources:
        if not visual_style:
            vs = config.match_visual_style(src.get("visual_style") or "")
            if vs:
                visual_style = vs
        if not dialogue_mode:
            talk = (src.get("dialogue_mode") or "").strip()
            if talk in config.DIALOGUE_MODE_OPTIONS:
                dialogue_mode = talk
        if not narrator:
            nar = (src.get("narrator") or "").strip()
            if nar:
                narrator = nar
    if not visual_style:
        visual_style = config.match_visual_style(project_manager.LAST_VISUAL_STYLE)
        if not visual_style and config.VISUAL_STYLE_OPTIONS:
            visual_style = config.VISUAL_STYLE_OPTIONS[0]
    return (
        visual_style,
        dialogue_mode or config.normalize_dialogue_mode(""),
        narrator or (project_manager.LAST_NARRATOR or ""),
    )



























































def apply_scene_content_from_editor_text(
    video_detail: dict,
    raw: str,
    *,
    allow_clear: bool = False,
) -> tuple[bool, str, list | None]:
    """Parse scene_content JSON from the editor and assign to ``video_detail`` (no disk I/O)."""
    if not isinstance(video_detail, dict):
        return False, "invalid video_detail", None
    text = (raw or "").strip()
    if not text:
        if not allow_clear:
            return False, "scene_content 为空", None
        video_detail.pop("scene_content", None)
        return True, "cleared scene_content", []
    try:
        parsed = json.loads(safe_clipboard_json_copy(text))
    except (json.JSONDecodeError, TypeError) as e:
        return False, f"无法解析 scene_content：{e}", None
    if not isinstance(parsed, list):
        return False, "scene_content 必须是 JSON 数组（以 [ 开头的 list）。", None
    if not parsed:
        return False, "解析后无有效场景条目，请检查 JSON 结构。", None
    video_detail["scene_content"] = parsed
    return True, f"parsed {len(parsed)} scene(s)", parsed


def _normalize_scene_dict_entry(item: dict) -> dict | None:
    """单条 scene JSON：保留 LLM 返回的全部字段。"""
    if not isinstance(item, dict):
        return None
    out: dict = {}
    for k, v in item.items():
        if isinstance(v, str):
            sv = v.strip()
            if sv:
                out[k] = sv
        elif v is not None:
            out[k] = v
    if not out:
        return None
    episode = out.get("episode")
    if isinstance(episode, bool):
        out.pop("episode", None)
    elif isinstance(episode, (int, float)):
        out["episode"] = str(int(episode))
    elif isinstance(episode, str):
        episode = episode.strip()
        if episode:
            out["episode"] = episode
        else:
            out.pop("episode", None)
    project_manager.normalize_scene_content_item_for_workflow(out)
    heading = _scene_entry_heading(out)
    body = (out.get("visual") or out.get("content") or "").strip()
    speaking = (out.get("speaking") or "").strip()
    voiceover = (out.get("voiceover") or "").strip()
    actor = (out.get("actor") or "").strip()
    if not heading and not body and not speaking and not voiceover and not actor:
        return None
    return out


def _episode_choice_is_all(episode: str) -> bool:
    ep = (episode or "").strip().lower()
    return ep in ("", "all", "全部")


def _episode_choice_label(episode: str) -> str:
    if _episode_choice_is_all(episode):
        return "全部"
    return (episode or "").strip()


def _episode_ids_in_scenes(scenes: list | None) -> list[str]:
    """JSON 里实际出现的 episode，按数字排序。没有任何 episode 时为空。"""
    seen: list[str] = []
    for item in scenes or []:
        if not isinstance(item, dict):
            continue
        ep = item.get("episode")
        if ep is None:
            continue
        text = str(ep).strip()
        if text and text not in seen:
            seen.append(text)
    if seen and all(text.isdigit() for text in seen):
        seen.sort(key=int)
    return seen


def _filter_scenes_by_episode(scenes: list | None, episode: str) -> list:
    entries = [item for item in (scenes or []) if isinstance(item, dict)]
    if _episode_choice_is_all(episode):
        return entries
    want = (episode or "").strip()
    return [item for item in entries if str(item.get("episode") or "").strip() == want]










































def _treeview_item_tags_safe(tree, item):
    """读取 Treeview 行的 tags。populate_tree 会删行重建，旧 iid 失效，必须先 exists。"""
    try:
        if tree.exists(item):
            return tree.item(item, "tags")
    except tk.TclError:
        pass
    return ()


def _configure_channel_list_treeview(tree: ttk.Treeview) -> None:
    """频道视频列表：固定列不拉伸（默认 stretch=True 会在宽窗口撑出列间空白）。"""
    present = set(tree["columns"])
    for col, width, anchor in (
        ("#0", 46, "center"),
        ("views", 66, "e"),
        ("duration", 50, "center"),
        ("upload_date", 86, "center"),
        ("status", 150, "center"),
        ("analyzed", 100, "center"),
        ("topic_category", 200, "w"),
        ("topic_subtype", 200, "w"),
        ("tags", 200, "w"),
    ):
        if col != "#0" and col not in present:
            continue
        tree.column(col, width=width, minwidth=width, stretch=False, anchor=anchor)
    tree.column("title", width=350, minwidth=200, stretch=True, anchor="w")


def _configure_video_pick_treeview(tree: ttk.Treeview) -> None:
    """新视频选择弹窗：仅标题列拉伸。"""
    for col, width, anchor in (
        ("views", 72, "e"),
        ("duration", 56, "center"),
        ("upload_date", 88, "center"),
    ):
        tree.column(col, width=width, minwidth=width, stretch=False, anchor=anchor)
    tree.column("title", width=450, minwidth=200, stretch=True, anchor="w")








# --- 全频道共享 persistent 剪贴板：``{BASE_AIAGENT_PATH}/program_clipboard.json`` ---

























































def _apply_scene_lm_combo(
    combo,
    combo_var,
    labels: list[str],
    matched: str,
    *,
    host=None,
) -> None:
    """Switch a readonly ttk.Combobox and force the label to repaint on screen."""
    combo_var.set(matched)
    idx = None
    try:
        idx = labels.index(matched)
    except ValueError:
        pass
    state = "readonly"
    try:
        state = str(combo.cget("state"))
    except tk.TclError:
        pass
    try:
        if state == "readonly":
            combo.configure(state="normal")
        if idx is not None:
            combo.current(idx)
        combo.set(matched)
    except tk.TclError:
        try:
            combo.set(matched)
        except Exception:
            pass
    finally:
        try:
            if state == "readonly":
                combo.configure(state="readonly")
        except tk.TclError:
            pass
    if host is not None:
        try:
            combo.update_idletasks()
            host.update_idletasks()
        except tk.TclError:
            pass






_CHANNEL_LIST_TREE_TITLE_MAX_SRC_CHARS = 40




def _apply_video_detail_titles_from_ui(
    video_detail: dict,
    *,
    source_title: str,
    project_title: str = "",
    channel_path: str = "",
) -> None:
    """将摘要窗「视频名称」写回列表行：无项目时改 ``title``；有项目时改 ``title`` + ``project_profile.video_title``。"""
    if not isinstance(video_detail, dict):
        return
    src = (source_title or "").strip()
    proj = (project_title or "").strip()
    prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict) and prof:
        if src:
            video_detail["title"] = src
        if proj:
            merged = copy.deepcopy(prof)
            merged["video_title"] = proj
            video_detail[project_manager.PROJECT_PROFILE_KEY] = (
                project_manager.profile_for_list_storage(merged)
            )
    elif src:
        video_detail["title"] = src
    _normalize_channel_list_item_for_storage(video_detail, channel_path or "")


















































































def _open_feature_media_in_explorer(*preferred_files: str) -> None:
    """打开 ``publish/gen_video``；若已有成片/封面则选中对应文件。"""
    gen_dir = _gen_video_storage_dir()
    target = ""
    for fp in preferred_files:
        p = (fp or "").strip()
        if p and os.path.isfile(p):
            target = os.path.normpath(p)
            break
    if target:
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", target], check=False)
        else:
            folder = os.path.dirname(target)
            if folder and os.path.isdir(folder):
                if sys.platform == "darwin":
                    subprocess.run(["open", "-R", target], check=False)
                else:
                    subprocess.run(["xdg-open", folder], check=False)
        return
    if gen_dir and os.path.isdir(gen_dir):
        if sys.platform == "win32":
            os.startfile(gen_dir)
        elif sys.platform == "darwin":
            subprocess.run(["open", gen_dir], check=False)
        else:
            subprocess.run(["xdg-open", gen_dir], check=False)










def _open_cover_image_for_row(parent, video_detail: dict) -> bool:
    """用 Windows 默认看图程序（如「照片」）打开 gen_video 封面。"""
    cover_path = _find_gen_video_webp_for_row(video_detail)
    if not cover_path or not os.path.isfile(cover_path):
        messagebox.showwarning(
            "提示",
            "尚无封面图。\n请拖入图片到本窗口生成封面（.webp）。",
            parent=parent,
        )
        return False
    try:
        os.startfile(cover_path)
    except OSError as exc:
        messagebox.showerror(
            "打开失败",
            f"无法打开封面：\n{cover_path}\n\n{exc}",
            parent=parent,
        )
        return False
    return True




def _video_detail_has_scene_content(vd: dict) -> bool:
    if not isinstance(vd, dict):
        return False
    return _scene_content_nonempty_value(vd.get("scene_content"))


def _video_detail_can_create_project(vd: dict) -> bool:
    """有 ``scene_content`` 即可新建项目；``analyzed_content`` 可选。"""
    return _video_detail_has_scene_content(vd)





















# INPUT_MEDIA_PATH 下 __数字__简码__标题_.txt，JSON 含 id → 同目录同 stem 的 .mp4 可发布；发布后同 stem 的 mp4/png/txt 可归档到简码/topic_category 对应的子文件夹（如 Identity__...）
































# YouTube GUI管理类
class MediaGUIManager:
    """YouTube GUI管理器 - 处理所有YouTube相关的GUI对话框"""
    
    def __init__(
        self,
        root,
        channel,
        pid,
        tasks,
        log_to_output_func,
        download_output,
        language,
        workflow_gui=None,
        *,
        content_mode: bool = False,
    ):
        self.root = root
        self.workflow_gui = workflow_gui
        self.content_mode = bool(content_mode)

        self.channel = channel
        channel_path = config.get_channel_path(config.get_channel_id(channel))
        self.channel_path = channel_path
        self.youtube_dir = f"{channel_path}/Download"

        os.makedirs(self.youtube_dir, exist_ok=True)
        os.makedirs(f"{self.youtube_dir}/media", exist_ok=True)

        self.pid = pid
        self.tasks = tasks
        self.log_to_output = log_to_output_func
        self.download_output = download_output
        self._input_language = (language or 'zh').strip().lower()
        if self._input_language not in config.LANGUAGES:
            self._input_language = 'zh'
        self.language = self._input_language  # 与 config.LANGUAGES 键一致（欢迎屏已选）
        _dl_lang = 'en' if self._input_language == 'en' else 'zh'  # yt-dlp 字幕常用 en/zh
        
        self.llm_api_local = llm_api.LLMApi(llm_api.TEXT_MODEL)
        self.llm_api = llm_api.LLMApi()
        self.llm_api_manual = llm_api.LLMApi(llm_api.MODEL_MANUAL)  # 最难：直接手动窗口

        # 创建YoutubeDownloader实例
        self.downloader = MediaDownloader(pid, self.youtube_dir, _dl_lang)
        if self.content_mode:
            self.downloader.channel_list_dir = config.ensure_channel_list_by_topic_dir(
                self.channel_path
            )
        
        # 跟踪活跃的摘要生成线程，确保对话框关闭时不会丢失数据
        self.active_summary_threads = []
        self.active_threads_lock = threading.Lock()

        self.topic_choices, self.topic_categories, self.tag_features_map = config.load_topics(channel)
        
        # 初始化主主题分类变量
        self.main_topic_category = None

    def _channel_config_key(self) -> str:
        ch = (self.channel or "").strip()
        if ch:
            return ch
        return os.path.basename(self.channel_path or "")


    def _do_create_new_channel_from_url(self):
        """创建新频道：弹窗输入频道/视频链接，解析出频道名，创建列表（可选获取视频）"""
        url = simpledialog.askstring("创建新频道", "输入 YouTube 频道链接或视频链接：", parent=self.root)
        if not url or not url.strip():
            return None
        url = url.strip()
        try:
            channel_name, channel_url = self.downloader.fetch_channel_info_from_url(url)
        except Exception as e:
            self.root.after(0, lambda e=e: show_auto_close_popup(self.root, "错误", f"解析链接失败: {e}", kind="error"))
            return None
        if not channel_name:
            self.root.after(0, lambda: show_auto_close_popup(self.root, "错误", "无法解析频道名称", kind="error"))
            return None
        new_name = simpledialog.askstring("创建新频道", "频道名称（可修改）:", initialvalue=channel_name, parent=self.root)
        if not new_name or not new_name.strip():
            return None
        channel_name = new_name.strip()
        self.downloader.channel_list_json = os.path.join(self.downloader.channel_list_dir, f"{channel_name}.json")
        self.downloader.channel_videos = []
        os.makedirs(os.path.dirname(self.downloader.channel_list_json), exist_ok=True)
        if channel_url and messagebox.askyesno("获取视频", f"是否从该频道获取热门视频列表？\n\n频道: {channel_name}", parent=self.root):
            cn = self.downloader.list_hot_videos(channel_url, max_videos=5000, min_view_count=0)
            if not cn:
                self.root.after(0, lambda: messagebox.showwarning("提示", "获取视频列表失败或为空", parent=self.root))
                return None
        else:
            _write_channel_list_json_file(self.downloader.channel_list_json, [])
        self.downloader.channel_name = channel_name
        for v in self.downloader.channel_videos:
            self.check_video_status(v)
        return True

    def _load_channel_list_json_into_downloader(self, list_json_path: str) -> bool:
        """读取 ``list/*.json`` 到 ``downloader.channel_videos``（与「频道列表项目管理」选列表后相同）。"""
        list_json_path = (list_json_path or "").strip()
        if not list_json_path or not os.path.isfile(list_json_path):
            messagebox.showwarning("提示", f"列表文件不存在：{list_json_path}", parent=self.root)
            return False

        self.downloader.channel_list_json = list_json_path
        basename = os.path.basename(list_json_path)
        self.downloader.channel_name = os.path.splitext(basename)[0]

        with open(list_json_path, "r", encoding="utf-8") as f:
            channel_videos = json.load(f)

        _normalize_channel_videos_for_storage(channel_videos, self.channel_path or "")

        for video in channel_videos:
            scene_content = video.get("scene_content")
            if isinstance(scene_content, str):
                try:
                    scene_content = json.loads(scene_content)
                except Exception:
                    video.pop("scene_content", None)
                    continue
            if isinstance(scene_content, list) and scene_content:
                video["scene_content"] = scene_content
            else:
                video.pop("scene_content", None)

        cleaned = dedupe_channel_video_list(channel_videos)

        for video_detail in cleaned:
            video_detail.pop("description", "")
            video_detail.pop("thumbnail", "")
            video_detail.pop("uploader", "")

        _normalize_channel_videos_for_storage(cleaned, self.channel_path or "")
        _write_channel_list_json_file(self.downloader.channel_list_json, cleaned)

        self.downloader.channel_videos = cleaned
        self.downloader.latest_date = max(
            (
                datetime.strptime(v["upload_date"], "%Y%m%d")
                for v in self.downloader.channel_videos
                if v.get("upload_date")
            ),
            default=None,
        )
        if not self.downloader.channel_videos:
            messagebox.showwarning("提示", "视频列表为空", parent=self.root)
            return False

        for video in self.downloader.channel_videos:
            self.check_video_status(video)
        return True

    def open_hot_videos_from_list_json(
        self,
        list_json_path: str,
        *,
        auto_open_summary_row_keys: list[str] | None = None,
    ) -> None:
        """跳过「选择频道列表」弹窗，直接打开热门视频管理；可选自动打开摘要编辑。"""
        self.downloader.language = "en" if self.language == "en" else "zh"
        if not self._load_channel_list_json_into_downloader(list_json_path):
            return
        keys = [str(k).strip() for k in (auto_open_summary_row_keys or []) if str(k).strip()]
        self._show_channel_videos_dialog(auto_open_summary_row_keys=keys)

    def manage_hot_videos(self):
        # 语言已在 YT 欢迎屏（project_manager.show_initial_choice_dialog）选择
        self.downloader.language = 'en' if self.language == 'en' else 'zh'

        # 查找所有热门视频JSON文件
        pattern = os.path.join(self.downloader.channel_list_dir, "*.json")
        json_files = glob.glob(pattern)
        
        # 无已有文件时，直接进入创建新频道流程
        if not json_files:
            if self._do_create_new_channel_from_url():
                self._show_channel_videos_dialog()
            return
        
        # 提取频道名称
        channel_data = []
        for json_file in json_files:
            filename = os.path.basename(json_file)
            # 从文件名中提取频道名：频道名.json -> 频道名
            match = re.match(r'(.+?)\.json', filename)
            if match:
                channel_name = match.group(1)
                # 读取文件获取视频数量
                video_count = 0
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                for encoding in encodings:
                    try:
                        with open(json_file, 'r', encoding=encoding) as f:
                            videos = json.load(f)
                            video_count = len(videos) if isinstance(videos, list) else 0
                        break  # 成功读取后退出循环
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                        if encoding == encodings[-1]:  # 最后一个编码也失败
                            print(f"❌ 读取频道视频列表失败 (尝试了所有编码): {e}")
                        continue
                    except Exception as e:
                        print(f"❌ 读取频道视频列表失败: {e}")
                        break
                
                channel_data.append({
                    'name': channel_name,
                    'file': json_file,
                    'video_count': video_count
                })
        
        if not channel_data:
            messagebox.showwarning("提示", "未找到有效的频道视频列表")
            return
        
        # 准备选项列表和映射，加入【创建新频道】
        channel_choices = []
        choice_to_channel = {}
        for channel in channel_data:
            choice_text = f"{channel['name']} ({channel['video_count']} 个视频)"
            channel_choices.append(choice_text)
            choice_to_channel[choice_text] = channel
        CREATE_NEW = "【创建新频道】"
        channel_choices.append(CREATE_NEW)
        
        # 使用 askchoice 显示选择对话框
        picked = askchoice("选择频道", channel_choices, parent=self.root)
        if not picked:
            return  # 用户取消
        _, selected_choice = picked
        if selected_choice == CREATE_NEW:
            # 创建新频道（输入频道/视频链接，解析频道名）
            if self._do_create_new_channel_from_url():
                for v in self.downloader.channel_videos:
                    self.check_video_status(v)
                self._show_channel_videos_dialog()
            return
        
        if selected_choice not in choice_to_channel:
            return
        # 获取选中的频道
        channel = choice_to_channel[selected_choice]
        if not self._load_channel_list_json_into_downloader(channel["file"]):
            return
        self._show_channel_videos_dialog()




    def _topic_subtype_filter_names(self) -> list:
        """当前这份 topic 列表里可选的子类型，前面加「全部」。"""
        cat = (self.downloader.channel_name or "").strip()
        names = []
        for item in self.topic_choices or []:
            if not isinstance(item, dict):
                continue
            item_cat = (item.get("topic_category") or item.get("category") or "").strip()
            if item_cat != cat:
                continue
            for sub in item.get("topic_subtypes") or []:
                if isinstance(sub, dict):
                    name = (sub.get("topic_subtype") or "").strip()
                else:
                    name = str(sub or "").strip()
                if name and name not in names:
                    names.append(name)
        for video in self.downloader.channel_videos or []:
            name = (video.get("topic_subtype") or "").strip()
            if name and name not in names:
                names.append(name)
        return ["全部"] + names


    def open_topic_list_file(self, json_path: str):
        """直接打开 ``list_by_topic`` 里指定的一份列表。"""
        self.downloader.language = "en" if self.language == "en" else "zh"
        path = (json_path or "").strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("提示", "主题列表不存在", parent=self.root)
            return
        if not self._load_channel_list_json_into_downloader(path):
            return
        self._show_channel_videos_dialog()


    def fetch_text_content(self, video_detail):
        text = config.read_transcript_text_from_video_detail(video_detail)
        return text if text else None

    def _analyze_content_source_text(
        self, video_detail: dict, *, override: str | None = None
    ) -> str:
        """内容概括 / 生成 analyzed_content 的 LLM 用户输入：优先 override → 转录 → 已有 analyzed_content。"""
        if override is not None:
            ov = str(override).strip()
            if ov:
                return ov
        t = (self.fetch_text_content(video_detail) or "").strip()
        if t:
            return t
        return video_detail.get("analyzed_content")





    def _combined_prompt_text_for_label(
        self,
        video_detail: dict,
        prompt_label: str,
        *,
        instruction: str = "",
        content_override: str | None = None,
        dialogue_mode: str = "",
        prompt_params: dict | None = None,
    ) -> tuple[str, str]:
        """按频道 LM 提示 label 生成完整 prompt 文本（``{content}`` = analyzed_content）。

        ``prompt_params``（可选）：``steps``（Step Story 步数）、``episode`` / ``episodes``
        （直接生成系列节目 第 k 集 / 共 N 集）、``visual_style``（画面风格）。不传 = 旧行为。
        """
        channel_key = self._channel_config_key()
        params = dict(prompt_params or {})
        legacy = config_channel.legacy_step_label(prompt_label or "")
        if legacy and not any(
            (l or "").strip() == (prompt_label or "").strip()
            for l, _ in _prompt_choice_entries(channel_key)
        ):
            prompt_label = config_channel.STEP_STORY_LABEL
            params.setdefault("steps", legacy)
        lbl, template, idx = _resolve_combined_prompt_template(
            channel_key, label=prompt_label
        )
        if not template:
            return "", ""
        if config_channel.is_step_image_label(lbl):
            # 图片分解：只出图片指令（无 {content} / soul），图片由用户带到 AI 图片工具。
            return lbl, config_prompt.build_step_image_clipbody(
                params.get("steps") or 1,
                visual_style=str(params.get("visual_style") or project_manager.LAST_VISUAL_STYLE or ""),
            )
        if config_channel.is_scene_summary_image_label(lbl):
            # 场景总图：全部 scene_content → 一张总图（幻灯提示「单图」同一构建函数）；没有场景时为空。
            scenes = params.get("scenes")
            if not isinstance(scenes, list):
                scenes = video_detail.get("scene_content") if isinstance(video_detail, dict) else None
            scenes = [s for s in (scenes or []) if isinstance(s, dict)] if isinstance(scenes, list) else []
            if not scenes:
                return lbl, ""
            return lbl, config_prompt.build_scene_summary_image_prompt(
                scenes,
                visual_style=str(params.get("visual_style") or project_manager.LAST_VISUAL_STYLE or ""),
                host_narrator=_project_look_from_row(video_detail)[2],
            )
        template = config_channel.resolve_dynamic_scene_template(lbl, template, params)
        cat, sub, topic = _notebooklm_row_topic_fields(video_detail)
        prompt = _build_notebooklm_prompt_for_row(
            self,
            video_detail,
            template,
            instruction=instruction,
            sections=idx + 1,
            topic=topic,
            tags=_notebooklm_row_tags_text(video_detail),
            topic_category=cat,
            topic_subtype=sub,
            content_override=content_override,
            dialogue_mode=dialogue_mode,
            visual_style=str(params.get("visual_style") or ""),
        )
        return lbl, prompt


    def _generate_scene_content_from_notebooklm_prompt(
        self,
        video_detail: dict,
        prompt_label: str,
        *,
        instruction: str = "",
        content_override: str | None = None,
        dialogue_mode: str = "",
        attachment: str = "",
        prompt_params: dict | None = None,
    ) -> list | None:
        """用所选 LM 提示生成 scene_content array。默认 {content} 为 analyzed_content。"""
        has_override = content_override is not None and str(content_override).strip()
        if not has_override and not (video_detail.get("analyzed_content") or "").strip():
            return None
        _, prompt = self._combined_prompt_text_for_label(
            video_detail,
            prompt_label,
            instruction=instruction,
            content_override=content_override,
            dialogue_mode=dialogue_mode,
            prompt_params=prompt_params,
        )
        if not (prompt or "").strip():
            return None
        parsed = self.llm_api_manual.generate_json(
            prompt, "", expect_list=True, attachment=(attachment or "").strip() or None
        )
        if isinstance(parsed, dict):
            one = _normalize_scene_dict_entry(parsed)
            return [one] if one else None
        if isinstance(parsed, list):
            out: list[dict] = []
            for it in parsed:
                n = _normalize_scene_dict_entry(it) if isinstance(it, dict) else None
                if n:
                    out.append(n)
            return out if out else None
        return None

    def _run_scene_smart_generate_async(
        self,
        parent,
        video_detail: dict,
        prompt_label: str,
        set_scene_json,
        *,
        get_instruction=None,
        on_busy=None,
        on_idle=None,
        persist_fn=None,
        on_saved=None,
        on_title_updated=None,
        content_override: str | None = None,
        dialogue_mode: str = "",
        attachment: str = "",
        prompt_params: dict | None = None,
    ) -> bool:
        """智能生成 scene_content：替换现有内容并自动保存。"""
        channel_key = self._channel_config_key()
        if not prompt_label:
            prompt_label = _prompt_choice_entries(channel_key)[0][0]
        has_override = content_override is not None and str(content_override).strip()
        if not has_override and not (video_detail.get("analyzed_content") or "").strip():
            messagebox.showwarning(
                "提示",
                "智能生成需要 analyzed_content 作为 {content} 原始材料。\n请先在「分析」中填写或生成内容。",
                parent=parent,
            )
            return False
        if not prompt_label and not _prompt_choice_entries(channel_key):
            messagebox.showwarning(
                "提示",
                "当前频道未配置可用的 LM 提示词，无法智能生成。",
                parent=parent,
            )
            return False
        if on_busy:
            on_busy()

        def work():
            err_msg = ""
            scenes: list | None = None
            instr = (get_instruction() or "").strip() if callable(get_instruction) else ""
            try:
                scenes = self._generate_scene_content_from_notebooklm_prompt(
                    video_detail,
                    prompt_label,
                    instruction=instr,
                    content_override=content_override,
                    dialogue_mode=dialogue_mode,
                    attachment=attachment,
                    prompt_params=prompt_params,
                )
            except Exception as ex:
                err_msg = str(ex)

            def apply():
                if on_idle:
                    on_idle()
                if err_msg:
                    show_auto_close_popup(parent, "生成失败", err_msg, kind="error")
                    return
                if not scenes:
                    messagebox.showwarning(
                        "提示",
                        "LLM 未返回有效 scene_content（须为 JSON array）。",
                        parent=parent,
                    )
                    return
                scene_json = json.dumps(scenes, ensure_ascii=False, indent=2)
                video_detail["scene_content"] = scenes
                new_title = project_manager.caption_from_scene_content_item(scenes[0])
                if new_title:
                    _apply_project_video_title(video_detail, new_title)
                    ch_path = self.channel_path or ""
                    _normalize_channel_list_item_for_storage(video_detail, ch_path)
                set_scene_json(scene_json)
                if callable(on_title_updated):
                    try:
                        on_title_updated()
                    except Exception:
                        pass
                persist = persist_fn or (
                    lambda vd, parent=None: self._persist_video_detail_story(
                        vd, parent=parent
                    )
                )
                if not persist(video_detail, parent=parent):
                    return
                try:
                    _copy_text_to_clipboard(parent, scene_json)
                except Exception:
                    pass
                if callable(on_saved):
                    try:
                        on_saved()
                    except Exception:
                        pass
                show_auto_close_popup(
                    parent,
                    "已生成场景",
                    f"已用「{prompt_label}」生成 {len(scenes)} 个场景，并已保存到频道列表。"
                    + (
                        f"\n项目成片名已更新为：{new_title}"
                        if new_title
                        and project_manager.list_json_row_has_project_profile(
                            video_detail
                        )
                        else ""
                    ),
                )

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()
        return True

    def _story_profile(self, video_detail: dict) -> dict:
        prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY) if isinstance(video_detail, dict) else None
        return prof if isinstance(prof, dict) else {}

    def _summarize_scene_list(self, *args, **kwargs):
        from gui.dl.story_summary import StorySummaryImpl as _impl
        return _impl._summarize_scene_list(self, *args, **kwargs)


    def _show_story_summary_editor(self, *args, **kwargs):
        from gui.dl.story_summary import StorySummaryImpl as _impl
        return _impl._show_story_summary_editor(self, *args, **kwargs)


    def _persist_video_detail_story(self, *args, **kwargs):
        from gui.dl.story_summary import StorySummaryImpl as _impl
        return _impl._persist_video_detail_story(self, *args, **kwargs)



    def _show_analyzed_content_editor(self, *args, **kwargs):
        from gui.dl.content_editors import ContentEditorsImpl as _impl
        return _impl._show_analyzed_content_editor(self, *args, **kwargs)


    def _show_poem_editor(self, *args, **kwargs):
        from gui.dl.content_editors import ContentEditorsImpl as _impl
        return _impl._show_poem_editor(self, *args, **kwargs)


    def _copy_notebooklm_scene_instruction(self, *args, **kwargs):
        from gui.dl.content_editors import ContentEditorsImpl as _impl
        return _impl._copy_notebooklm_scene_instruction(self, *args, **kwargs)







    def _show_scene_content_editor(self, *args, **kwargs):
        from gui.dl.scene_editor import SceneEditorImpl as _impl
        return _impl._show_scene_content_editor(self, *args, **kwargs)


    def open_content_field_editor(self, *args, **kwargs):
        from gui.dl.content_editors import ContentEditorsImpl as _impl
        return _impl.open_content_field_editor(self, *args, **kwargs)




    def check_video_status(self,video_detail):
        """检查单个视频的下载、转录和摘要状态"""
        status_parts = []
        video_file = None
        audio_file = None
        
        # 使用可重用的方法生成文件名前缀（用于匹配，使用50字符）
        filename_prefix = self.downloader.generate_video_prefix( video_detail )
        
        # 检查是否已下载 - 只扫描 .mp4 文件
        for filename in os.listdir(f"{self.youtube_dir}/media"):
            # 只检查 .mp4 文件
            if not filename_prefix in filename:
                continue
            if filename.lower().endswith('.mp4'):
                video_file = os.path.join(f"{self.youtube_dir}/media", filename)
                video_detail['video_path'] = video_file
            elif filename.lower().endswith('.mp3'):
                audio_file = os.path.join(f"{self.youtube_dir}/media", filename)
                video_detail['audio_path'] = audio_file
            elif filename.lower().endswith('.wav'):
                audio_file = os.path.join(f"{self.youtube_dir}/media", filename)
                a = self.downloader.ffmpeg_audio_processor.to_mp3(audio_file)
                safe_remove(audio_file)
                audio_file = f"{self.youtube_dir}/media/{filename_prefix}.mp3"
                safe_copy_overwrite(a, audio_file)
                video_detail['audio_path'] = audio_file
        
        if video_file and not audio_file:
            a = self.downloader.ffmpeg_audio_processor.extract_audio_from_video(video_file, "mp3")
            audio_file = f"{self.youtube_dir}/media/{filename_prefix}.mp3"
            safe_copy_overwrite(a, audio_file)
            video_detail['audio_path'] = audio_file

        if video_file or audio_file:
            status_parts.append("✅ 已下载")
        else:
            status_parts.append("⬜ 未下载")
        
        # 检查是否已转录 - 检查 .srt 文件（转录生成的字幕文件）
        has_transcript = bool((video_detail.get("transcribed_file") or "").strip())
        if not has_transcript:
            for filename in os.listdir(f"{self.youtube_dir}/media"):
                if filename_prefix in filename and (
                    filename.endswith(".srt")
                    or filename.endswith(".json")
                    or filename.endswith(".txt")
                ):
                    video_detail['transcribed_file'] = os.path.join(f"{self.youtube_dir}/media", filename)
                    has_transcript = True
                    break
        if has_transcript:
            status_parts.append("✅ 已转录")
        else:
            status_parts.append("⬜ 未转录")
        
        
        return " ".join(status_parts), video_file, audio_file


    def get_video_detail(self, row_key):
        """按树 tag（``id`` 或 ``url``）或 ``project_profile.pid`` 查找列表行。"""
        key = (row_key or "").strip()
        if not key:
            return None
        for video in self.downloader.channel_videos:
            if (video.get("url") or "").strip() == key or (video.get("id") or "").strip() == key:
                return video
        for video in self.downloader.channel_videos:
            if _video_detail_project_pid(video) == key:
                return video
        return None


    def match_media_file(self, video_detail, field, postfixs):
        prefix = self.downloader.generate_video_prefix(video_detail)
        for file in os.listdir(f"{self.youtube_dir}/media"):
            if not prefix in file:
                continue
            for postfix in postfixs:
                if file.endswith(postfix):
                    file = os.path.join(f"{self.youtube_dir}/media", file)
                    video_detail[field] = file
                    return video_detail
        return None


    def update_text_content(self, video_detail, transcribed_file=None):
        """确保 ``transcribed_file`` 已绑定；``content`` 仅在迁移到文件后移除。"""
        if not video_detail:
            return None
        if transcribed_file:
            video_detail["transcribed_file"] = transcribed_file
        config.migrate_content_to_transcribed_file(
            video_detail,
            media_dir=_infer_channel_list_item_media_dir(
                video_detail, getattr(self, "channel_path", "") or ""
            ),
        )
        return video_detail

    def _format_analyze_prompt(self, video_detail=None, analyze_key: str = "") -> str:
        """``analyze_key``：频道分析方式（config.get_channel_analyze_options 的 key）；空 = 第一项（原来的分析提示）。"""
        raw = config.get_channel_analyze_prompt(
            self._channel_config_key(),
            language=self.language,
            key=analyze_key or "",
        )

        url = ""
        if isinstance(video_detail, dict):
            url = (video_detail.get("url") or "").strip()
        lang_label = config.llm_language_label(self.language)
        try:
            return raw.format(url=url, language=lang_label)
        except KeyError:
            return raw

    def generate_analyzed_content_for_video(
        self,
        video_detail,
        *,
        force_rewrite: bool = False,
        analyze_key: str = "",
        source_text: str | None = None,
        append: bool = False,
    ) -> bool:
        """用 LLM 从转录/字幕文本生成 ``analyzed_content``（纯文本，当前频道语言）。

        ``analyze_key``：用哪一种分析方式（空 = 第一项）。``source_text``：只用这段文字作原始材料
        （STORY 窗材料列表的「分析」：PDF 文字或文字稿）。``append``：追加到原分析报告末尾，而不是替换。
        """
        if not isinstance(video_detail, dict):
            return False
        if not force_rewrite and video_detail.get("analyzed_content"):
            return True
        if source_text is not None:
            text_content = (source_text or "").strip()
            url = ""
            if not text_content:
                return False
        else:
            text_content = self._analyze_content_source_text(video_detail)
            url = (video_detail.get("url") or "").strip()
        if not text_content and not url:
            return False
        if text_content and len(text_content) < 100 and not url and source_text is None:
            return False
        prompt = self._format_analyze_prompt(video_detail, analyze_key=analyze_key)
        lang_label = config.llm_language_label(self.language)
        user_prompt = text_content if text_content else (f"YouTube URL: {url}" if url else " ")
        rewritten = self.llm_api_manual.generate_text(
            prompt.format(url=url, language=lang_label),
            user_prompt,
        )
        rewritten = (rewritten or "").strip()
        if not rewritten:
            return False
        old = (video_detail.get("analyzed_content") or "").rstrip() if append else ""
        video_detail["analyzed_content"] = (old + "\n\n" + rewritten) if old else rewritten
        return True

    def _generate_analyzed_content_summary_text(
        self,
        video_detail: dict,
        *,
        parent=None,
        source_text: str | None = None,
    ) -> str | None:
        """LLM 内容概括 → ``analyzed_content`` 纯文本（与摘要窗原「内容概括」相同逻辑）。"""
        text_content = self._analyze_content_source_text(
            video_detail, override=source_text
        )
        url = (video_detail.get("url") or "").strip()
        if not text_content and not url:
            messagebox.showwarning(
                "内容概括",
                "无转录原文且无 YouTube 链接，也无法从编辑区取得内容。",
                parent=parent,
            )
            return None
        prompt = self._format_analyze_prompt(video_detail)
        lang_label = config.llm_language_label(self.language)
        user_prompt = text_content if text_content else f"YouTube URL: {url}"
        rewritten = self.llm_api_manual.generate_text(
            prompt.format(language=lang_label, url=url),
            user_prompt,
        )
        rewritten = (rewritten or "").strip()
        if not rewritten:
            messagebox.showwarning(
                "内容概括",
                "LLM 未返回内容。",
                parent=parent,
            )
            return None
        return rewritten


    def show_analyzed_content_popup(self, *args, **kwargs):
        from gui.dl.content_editors import ContentEditorsImpl as _impl
        return _impl.show_analyzed_content_popup(self, *args, **kwargs)


    def _bind_yt_text_download_channel_list(self) -> None:
        """按 ``YT_text_download.json`` 绑定当前欢迎屏频道的 list JSON（不再弹窗选频道文件）。"""
        ch_id = config.get_channel_id(self.channel)
        list_path = config.yt_text_download_list_json_path(ch_id)
        os.makedirs(os.path.dirname(list_path), exist_ok=True)
        self.downloader.channel_list_json = list_path
        self.downloader.channel_videos = []
        self.downloader.latest_date = datetime.now()
        if os.path.isfile(list_path):
            try:
                with open(list_path, "r", encoding="utf-8") as f:
                    self.downloader.channel_videos = json.load(f)
                if not isinstance(self.downloader.channel_videos, list):
                    self.downloader.channel_videos = []
                else:
                    _normalize_channel_videos_for_storage(
                        self.downloader.channel_videos, self.channel_path or ""
                    )
                    dates = [
                        datetime.strptime(v["upload_date"], "%Y%m%d")
                        for v in self.downloader.channel_videos
                        if isinstance(v, dict) and v.get("upload_date")
                    ]
                    if dates:
                        self.downloader.latest_date = max(dates)
            except Exception as e:
                print(f"❌ 读取视频列表失败: {e}")
                self.downloader.channel_videos = []
        print(f"✅ YT 文字下载列表: {list_path}")


    def prepare_category_for_content(self, video_detail, topic_choices):
        valid_content = video_detail.get("analyzed_content")
        if not valid_content:
            valid_content = config.read_transcript_text_from_video_detail(video_detail)

        # LLM API 调用在信号量保护下（已在上层 with 语句中）
        result = self.llm_api_manual.generate_json(
            config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(language='Chinese', topic_choices=topic_choices), 
            valid_content,
            expect_list=False
        )
        if result:
            if result.get('topic_subtype', '') and result.get('topic_subtype', '').strip():
                video_detail['topic_subtype'] = result.get('topic_subtype', '')
                video_detail.pop('topic_type', None)
            if result.get('topic_category', '') and result.get('topic_category', '').strip():
                video_detail['topic_category'] = result.get('topic_category', '')
            # 保存到文件（在锁内，确保数据一致性）
            try:
                _write_channel_list_json_file(
                    self.downloader.channel_list_json, self.downloader.channel_videos
                )
                dn = _youtube_row_display_title(video_detail)
                print(f"✅ 摘要生成完成并已保存: {dn[:50] or 'Unknown'}")
            except Exception as e:
                print(f"❌ 保存 channel_list_json 失败: {e}")


    def _show_channel_videos_dialog(self, *args, **kwargs):
        from gui.dl.channel_videos_dialog import ChannelVideosDialogImpl as _impl
        return _impl._show_channel_videos_dialog(self, *args, **kwargs)



    def transcribe_media(self, transcribe):
        """选择本地 MP4/MP3：预览播放 → 转写，同目录保存 TXT 并复制到剪贴板。"""
        _ = transcribe
        from gui.transcribe_media_dialog import open_transcribe_media_dialog

        path = filedialog.askopenfilename(
            parent=self.root,
            title="选择 MP4 或 MP3",
            filetypes=[
                ("音视频", "*.mp4 *.mp3"),
                ("MP4", "*.mp4"),
                ("MP3", "*.mp3"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        path = os.path.abspath(path)
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".mp4", ".mp3"):
            messagebox.showwarning("提示", "请选择 .mp4 或 .mp3 文件", parent=self.root)
            return
        open_transcribe_media_dialog(self.root, self, path)

    def download_youtube(self, transcribe, analyze):
        """下载YouTube视频并转录"""
        # 弹出对话框让用户输入URL
        dialog = tk.Toplevel(self.root)
        dialog.title("YouTube下载")
        dialog.minsize(480, 160)
        dialog.transient(self.root)
        dialog.grab_set()
        w, h = 600, 200
        dialog.update_idletasks()
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        dialog.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        
        # YouTube URL输入
        url_frame = ttk.Frame(dialog)
        url_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(url_frame, text="YouTube链接:").pack(side=tk.LEFT)
        url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=url_var, width=50)
        url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        result_var = tk.StringVar(value="cancel")
        
        def on_confirm():
            url = url_var.get().strip()
            if not url:
                show_auto_close_popup(dialog, "错误", "请输入YouTube链接", kind="error")
                return
            result_var.set("confirm")
            dialog.destroy()
        
        def on_cancel():
            result_var.set("cancel")
            dialog.destroy()
        
        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        ttk.Button(button_frame, text="确认", command=on_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        # 等待对话框关闭
        self.root.wait_window(dialog)
        if result_var.get() == "cancel":
            return
        
        # 在对话框关闭后，通过 StringVar 获取值（它们仍然存在）
        video_url = url_var.get().strip()
        video_url = _normalize_youtube_watch_url(video_url)
        
        print(f"📥 开始下载YouTube视频并转录...")
        print(f"URL: {video_url}")

        self.downloader._check_and_update_cookies()
        try:
            video_data = self.downloader.get_video_detail(video_url, channel_name='')
        except Exception as e:
            err = str(e)
            print(f"❌ {err}")
            self.root.after(
                0,
                lambda m=err: show_auto_close_popup(self.root, "YouTube 下载失败", m, kind="error"),
            )
            return
        if not video_data:
            self.root.after(0, lambda: show_auto_close_popup(self.root, "错误", "获取视频详情失败", kind="error"))
            return

        if not transcribe:
            path = self.downloader.download_video_highest_resolution(video_data)
            if path and os.path.isfile(path):
                h = _ffprobe_video_height(path)
                msg = f"已保存:\n{path}"
                if h:
                    msg = f"已保存 ({h}p):\n{path}"
                self.root.after(
                    0,
                    lambda m=msg: show_auto_close_popup(self.root, "下载完成", m),
                )
            else:
                self.root.after(
                    0,
                    lambda: show_auto_close_popup(
                        self.root,
                        "下载失败",
                        "未能下载最高画质视频。\n\n"
                        "请确认：\n"
                        "1) 已安装 ffmpeg 并在 PATH 中\n"
                        "2) program/<频道>/Download 下有有效的 YouTube cookies\n"
                        "3) yt-dlp 为最新版: pip install -U yt-dlp",
                        kind="error",
                    ),
                )
            return

        self._bind_yt_text_download_channel_list()

        is_new_video = self.downloader.is_video_new(video_data)
        if not is_new_video:
            print(f"✅ 视频已存在，跳过下载...")
            return

        # 1. 优先尝试下载 caption（不 fetch 基本信息、不弹窗），按 zh/zh-Hans/.../en 硬试
        transcribed_file = self.downloader.try_download_caption_with_priority(video_data)
        if transcribed_file:
            print(f"✅ 已从字幕获取文本")

        # 2. 若无 caption，按 config 决定是否下载音频并用 Whisper 转录
        if not transcribed_file and config.TRANSCRIBE_FALLBACK_TO_AUDIO:
            file_path = self.downloader.download_audio_only(video_data)
            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path) / (1024 * 1024)
                video_data["audio_path"] = file_path
                video_data["file_size_mb"] = file_size
                video_data["audio_download_status"] = "success"
            else:
                self.root.after(0, lambda: show_auto_close_popup(self.root, "错误", "视频下载失败", kind="error"))
                return
            transcribed_file = self.downloader.download_captions(
                video_data, self.language, allow_audio_fallback=True
            )
        if not transcribed_file:
            print(f"❌ YouTube视频转录失败")
            self.root.after(0, lambda: show_auto_close_popup(self.root, "错误", "YouTube视频转录失败：未生成字幕文件", kind="error"))
            return

        video_data['transcribed_file'] = transcribed_file
        print(f"✅ YouTube视频转录完成！")
        self.downloader.channel_videos.append(video_data)
        this_video_date = datetime.strptime(video_data["upload_date"], "%Y%m%d")
        if this_video_date > self.downloader.latest_date:
            self.downloader.latest_date = this_video_date
        self.update_text_content(video_data)
        analyzed_ok = False
        if analyze:
            analyzed_ok = self.generate_analyzed_content_for_video(
                video_data, force_rewrite=True
            )
            if analyzed_ok:
                print("✅ analyzed_content 已生成")
            else:
                print("⚠️ analyzed_content 未生成（文本不足或 LLM 失败）")
        _normalize_channel_videos_for_storage(self.downloader.channel_videos, self.channel_path or "")

        _write_channel_list_json_file(
            self.downloader.channel_list_json, self.downloader.channel_videos
        )
        print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")

        def _finish_download_ui():
            if analyze:
                if analyzed_ok:
                    self.show_analyzed_content_popup(video_data, parent=self.root)
                else:
                    messagebox.showwarning(
                        "分析未完成",
                        "转录已完成，但 analyzed_content 未生成（文本不足或 LLM 失败）。",
                        parent=self.root,
                    )
            else:
                show_auto_close_popup(
                    self.root,
                    "转录完成",
                    "YouTube 视频转录完成！",
                )

        try:
            self.root.update_idletasks()
            _finish_download_ui()
            self.root.update()
        except Exception:
            self.root.after(0, _finish_download_ui)
