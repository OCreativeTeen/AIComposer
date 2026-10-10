import matplotlib

from utility import audio_transcriber
matplotlib.use('Agg')  # Must be at the TOP of main.py

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.scrolledtext as scrolledtext
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import os
import sys
import subprocess
import json
import threading
import time
from datetime import datetime, timedelta
from io import BytesIO
import pygame
import uuid
from magic_workflow import MagicWorkflow
import config
import config_prompt
from PIL import Image, ImageTk
from project_manager import ProjectConfigManager, create_project_dialog, refresh_scene_media, save_project_config, project_config_from_list_item
import project_manager
from gui.picture_in_picture_dialog import PictureInPictureDialog
import cv2
import os
from utility.file_util import (
    get_file_path,
    is_video_file,
    is_image_file,
    is_audio_file,
    safe_copy_overwrite,
    make_safe_file_name,
    safe_clipboard_json_copy,
    show_auto_close_popup,
)
#from utility.minimax_speech_service import MinimaxSpeechService, EXPRESSION_STYLES
from utility.voicebox_speech_service import VoiceboxService, EXPRESSION_STYLES
from utility.ffmpeg_processor import FfmpegProcessor
from gui.wan_prompt_editor_dialog import show_wan_prompt_editor  # 添加这一行
import tkinterdnd2 as TkinterDnD
from tkinterdnd2 import DND_FILES
from utility.media_scanner import MediaScanner
import utility.llm_api as llm_api
from gui.downloader import MediaGUIManager
from utility.ffmpeg_processor import resolve_watermark_for_project, resolve_headmark_for_project
from gui.suno_music_prompt_gui import SunoMusicPromptGUI
import cv2
import json
import copy
import shutil
from pathlib import Path
from gui.choice_dialog import askchoice, askchoice_media_preview, pack_text_buttons, post_nested_clipboard_menu, ask_speaking_concise_review_dialog
from gui.tag_picker_menu import post_menu_below_widget
from gui.downloader import ask_publish_schedule_dialog
from gui.publish_metadata_dialog import (
    ask_publish_metadata_then_schedule,
    scene_content_list_for_publish,
)


STANDARD_FPS = 60  # Match FfmpegProcessor.STANDARD_FPS

# 图像画布双击：gui.choice_dialog.askchoice 用 (return_value, button_label) 元组列表
IMAGE_ACTION_CHOICES = {
    "人物替换" : [
        "Replace Narrator/Figure in 1st image with the IP in 2nd image",
        "Add IP in 2nd image into 1st image (in front, half body, facing actor)",
        "Add IP in 2nd image into 1st image (in front, half body, facing audience)",
        "Add IP in 2nd image into 1st image (right, half body, facing actor)",
        "Add IP in 2nd image into 1st image (right, half body, facing audience)",
        "Add IP in 2nd image into 1st image (left, half body, facing actor)",
        "Add IP in 2nd image into 1st image (left, half body, facing audience)"
    ],
    "删除元素" : [
        "Remove text in upper part of image",
        "Remove text in lower part of image",
        "Remove PIP (narrator) in the image",
        "Remove Narrator in the image",
        "Remove Narrator in the image left",
        "Remove Narrator in the image right",
        "Remove Narrator in the image bottom",
        "Remove all text in the image",
    ],
    "节目包装" : [
        "Show title '{channel_name}' in header (creative)",
        "Show title '{channel_name}' in footer (creative)"
    ],
    "风格控制" : [
        "Change Person to Realistic Style",
        "Change Person to Pixar Style (Avoid large, wide, exaggerated eyes)",
        "Change Person to Cinematic Style",
        "Make the eyes much much smaller in overall scale (both eye width & height), Shrink the eyelid and visible eye area a lot!."
    ]
}


# Story 片头/片尾包装：菜单选中后复制英文指令到剪贴板；{channel_name} 运行时从 PROJECT_CONFIG.channel 解析
STORY_PACKAGING_MENU = [
    ("片头 · 主持", "Starting: Narrator主持'{channel_name}'节目 (Narrator speak, others react only)"),
    ("片头 · 主持(左)", "Starting: Narrator(Left)主持'{channel_name}'节目 (Narrator speak, others react only)"),
    ("片头 · 主持(右)", "Starting: Narrator(Right)主持'{channel_name}'节目 (Narrator speak, others react only)"),
    ("片头 · 纯音乐", "Starting: Narrator主持'{channel_name}'节目 (no talk+background music)"),
    ("片尾 · 主持", "Ending: Narrator主持'{channel_name}'节目 (Narrator speak, others react only)"),
    ("片尾 · 主持(左)", "Ending: Narrator(Left)主持'{channel_name}'节目 (Narrator speak, others react only)"),
    ("片尾 · 主持(右)", "Ending: Narrator(Right)主持'{channel_name}'节目 (Narrator speak, others react only)"),
    ("片尾 · 纯音乐", "Ending: Narrator主持'{channel_name}'节目 (no talk+background music)"),
]


def _workflow_channel_display_name() -> str:
    """当前项目频道显示名（CHANNEL_CONFIG.channel_name），无则回退 channel id。"""
    pc = project_manager.PROJECT_CONFIG or {}
    ch = (pc.get("channel") or "").strip()
    if ch:
        ch_cfg = config.get_channel_config(ch)
        name = (ch_cfg.get("channel_name") or "").strip()
        if name:
            return name
        return ch
    return "节目"




def _normalize_download_suffixes(media_post):
    """'.mp4' 或 ('.mp3', '.mp4') 等 → 小写后缀元组。"""
    if isinstance(media_post, str):
        s = media_post.strip().lower()
        return (("." + s) if not s.startswith(".") else s,)
    seq = []
    for x in media_post:
        s = str(x).strip().lower()
        seq.append(("." + s) if not s.startswith(".") else s)
    return tuple(seq)


def _download_folder_list_matching_suffixes(folder_path: str, suffixes: tuple) -> list:
    """目录下文件名（仅文件）后缀匹配任一 suffixes。"""
    if not folder_path or not os.path.isdir(folder_path):
        return []
    out = []
    for fn in os.listdir(folder_path):
        fp = os.path.join(folder_path, fn)
        if os.path.isfile(fp) and any(fn.lower().endswith(s) for s in suffixes):
            out.append(fn)
    return sorted(out)


def _user_downloads_folder() -> str:
    """当前用户 Windows Downloads（浏览器/工具默认下载位置）。"""
    return os.path.join(os.path.expanduser("~"), "Downloads")


def _external_media_pick_folders() -> list[str]:
    """场景选 clip 时优先浏览的外部目录：Downloads，其次 L:（旧环境映射盘）。"""
    folders: list[str] = []
    seen: set[str] = set()
    for p in (_user_downloads_folder(), "L:"):
        if not p:
            continue
        try:
            norm = os.path.normcase(os.path.abspath(p))
        except OSError:
            continue
        if norm in seen or not os.path.isdir(p):
            continue
        seen.add(norm)
        folders.append(p)
    return folders


class WorkflowGUI:
    # Standardized framerate to match video processing

    def __init__(self, root, initial_pid=None):
        # 如果拖拽支持可用，则使用TkinterDnD根窗口
        self.root = TkinterDnD.Tk() if not isinstance(root, TkinterDnD.Tk) else root
        # 如果传入的root不是TkinterDnD.Tk，需要重新创建
        if root != self.root:
            root.destroy()

        self.root.title("魔法工作流 GUI")
        try:
            self.root.state('zoomed') # Windows全屏
        except:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        try:
            pygame.mixer.init()
            self.pygame_mixer_available = True
        except Exception as e:
            self.pygame_mixer_available = False
        
        self.playing_delta = 0.0

        # 初始化配置加载标志
        self._loading_config = False
        self._scene_widgets_loading = False  # True 时跳过讲员「同步本故事」提示（避免切换场景时弹窗）
        self._programmatic_video_size = False  # True 时不响应尺寸 Combobox 的「应用」逻辑
        self.current_scene_index = 0

        self.llm_api = llm_api.LLMApi()
        self.llm_api_local = llm_api.LLMApi(llm_api.GEMINI)

        # 显示项目选择对话框（或 --open-pid 时直接加载指定项目）
        if initial_pid:
            # 命令行 --open-pid：跳过欢迎屏，直接加载该项目
            config_manager = ProjectConfigManager()
            selected_config = config_manager.load_config(initial_pid)
            if not selected_config:
                messagebox.showerror("错误", f"无法加载项目 {initial_pid} 的配置", parent=self.root)
                self.root.destroy()
                return
            ProjectConfigManager.set_global_config(selected_config)
            selection_result = True  # 视为已选择项目
        else:
            selection_result = self.show_project_selection()

        if selection_result is False:
            self.root.destroy()
            return
        file_pid = (
            (project_manager.PROJECT_CONFIG or {}).get("pid") or initial_pid or ""
        )
        file_pid = str(file_pid).strip()
        if file_pid:
            self.root.title(f"魔法工作流 | {file_pid}")
        
        # 首先初始化任务状态跟踪 - 增强版
        self.tasks = {}
        self.completed_tasks = []  # 存储已完成的任务
        self.last_notified_tasks = set()  # 跟踪已通知的任务
        self.status_update_timer_id = None  # 状态更新定时器ID
        self.monitoring_scenes = {}  # 跟踪正在监控的场景 {scene_index: {"found_files": [], "start_time": time}}
        self.processed_output_files = set()  # 跟踪已处理的 X:\output 文件
        
        # 单例后台检查线程控制
        self.video_check_thread = None  # 后台检查线程
        self.video_check_running = False  # 线程运行标志
        self.video_check_stop_event = threading.Event()  # 停止事件
        
        # refresh_gui_scenes 节流控制
        self.refresh_gui_scenes_last_time = 0  # 上次执行时间
        self.refresh_gui_scenes_after_id = None  # 延迟任务ID
        self._demo_playthrough_active = False
        self._demo_playthrough_after_id = None
        
        # 添加视频效果选择存储
        self.effect_radio_vars = {}  # {scene_index: tk.StringVar}
        
        # 添加当前效果和图像类型选择变量
        self.narration_animation = tk.StringVar(value=config_prompt.ANIMATE_SOURCE[0])
        
        # 创建动画名称到提示语的映射字典（双向）
        self.animation_name_to_prompt = {item["name"]: item["prompt"] for item in config_prompt.ANIMATION_PROMPTS}
        self.animation_prompt_to_name = {item["prompt"]: item["name"] for item in config_prompt.ANIMATION_PROMPTS}
        self.animation_names = [""] + list(self.animation_name_to_prompt.keys())
        
        # 创建主框架
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建共享信息区域
        self.create_shared_info_area(main_frame)
        
        # 创建标签页控件
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # 创建各个标签页
        self.create_video_tab()
        
        self.setup_drag_and_drop()
        
        # 绑定标签页切换事件
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        # 启动任务状态更新定时器
        self.start_status_update_timer()
        
        # 加载上次保存的配置（必须在所有控件创建完成后，在绑定事件之前）
        self.load_config()
        self.bind_config_change_events()
        
        # 立即创建工作流实例（不再使用懒加载）
        self.create_workflow_instance()
        
        # 初始化媒体扫描器（必须在启动后台线程之前），未选择项目时（如 YT 管理）跳过
        self.media_scanner = MediaScanner(self.workflow, 10) if self.workflow else None

        # 必须先 load_scenes，再启动后台线程：否则 _perform_video_check 里 save_scenes_to_json 会在
        # self.scenes 未就绪时执行，报「无 scenes」或把空列表写盘覆盖项目。
        if self.workflow:
            self.workflow.load_scenes()

        # 启动单例后台视频检查线程
        self.start_video_check_thread()
        # 绑定窗口关闭事件

        self.on_tab_changed(None)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)



    pid = None

    def get_pid(self):
        if self.pid is None and project_manager.PROJECT_CONFIG:
            self.pid = project_manager.PROJECT_CONFIG.get('pid')
        return self.pid
    


    def create_workflow_instance(self):
        """立即创建工作流实例（非懒加载）"""
        # 用户选择 YT 管理/下载时尚未创建或选择项目，PROJECT_CONFIG 为空是正常的
        if project_manager.PROJECT_CONFIG is None:
            self.workflow = None
            return
        try:
            # Get video dimensions from project config
            video_width = project_manager.PROJECT_CONFIG.get('video_width')
            video_height = project_manager.PROJECT_CONFIG.get('video_height')
            language = project_manager.PROJECT_CONFIG.get('language')
            channel = project_manager.PROJECT_CONFIG.get('channel')

            self.workflow = MagicWorkflow(self.get_pid(), language, channel, video_width, video_height)
            #self.speech_service = MinimaxSpeechService(self.get_pid())
            self.speech_service = VoiceboxService(self.workflow.pid)
            
            current_gui_title = self.video_title.get().strip()
            self.workflow.post_init(current_gui_title)
            
            # 初始化YouTube GUI管理器（第二参数为频道 key/id，非 channel_path；路径在 MediaGUIManager 内解析）
            self.youtube_gui = MediaGUIManager(
                self.root,
                channel,
                self.get_pid(), 
                self.tasks, 
                self.log_to_output, 
                self.video_output,  # 使用video_output作为YouTube下载日志输出
                language or "tw",
                workflow_gui=self,
            )
            
            print("✅ 工作流实例创建完成")
            
        except Exception as e:
            print(f"❌ 创建工作流实例失败: {e}")
            self.workflow = None


    def show_project_selection(self):
        """仅「选择项目」列表（无欢迎屏新建入口；新建走 downloader / create_project_with_initial_raw 等）。"""
        result, selected_config = create_project_dialog(self.root, youtube_gui=getattr(self, 'youtube_gui', None))

        if result == 'cancel':
            return False
        if result == 'open':
            if selected_config is None:
                print("❌ 错误：selected_config 为 None")
                return False
            ProjectConfigManager.set_global_config(selected_config)
            return True

        return False

   
    def create_shared_info_area(self, parent):
        """顶栏一行：左边场景切换，隔开一段是项目信息，最右边是成片操作。"""
        shared_frame = ttk.Frame(parent)
        shared_frame.pack(fill=tk.X, pady=(0, 6))

        row = ttk.Frame(shared_frame)
        row.pack(fill=tk.X)

        ttk.Button(row, text="SUNO", command=self._open_suno_gui).pack(side=tk.RIGHT, padx=(4, 0))
        self.btn_clean = ttk.Button(row, text="清理", command=self._open_clean_menu)
        self.btn_clean.pack(side=tk.RIGHT, padx=(4, 0))
        self.btn_finalize = ttk.Button(row, text="成片", command=self._open_finalize_menu)
        self.btn_finalize.pack(side=tk.RIGHT, padx=(16, 0))

        ttk.Label(row, text="场景").pack(side=tk.LEFT)
        ttk.Button(row, text="⏮", width=3, command=self.first_scene).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⏪", width=3, command=self.prev_episode).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="◀", width=3, command=self.prev_scene).pack(side=tk.LEFT, padx=2)
        self.scene_label = ttk.Label(row, text="0 / 0", width=7)
        self.scene_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="▶", width=3, command=self.next_scene).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⏩", width=3, command=self.next_episode).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⏭", width=3, command=self.last_scene).pack(side=tk.LEFT, padx=(2, 4))
        ttk.Label(row, text="│").pack(side=tk.LEFT, padx=(2, 2))
        start_btn = ttk.Button(row, text="开始", width=4, command=lambda: self._set_scene_marker("start"))
        start_btn.pack(side=tk.LEFT, padx=(2, 0))
        end_btn = ttk.Button(row, text="结束", width=4, command=lambda: self._set_scene_marker("end"))
        end_btn.pack(side=tk.LEFT, padx=(2, 0))
        start_btn.bind("<Button-3>", lambda _e: self._clear_scene_markers())
        end_btn.bind("<Button-3>", lambda _e: self._clear_scene_markers())
        self.marker_label = ttk.Label(row, text="", width=9)
        self.marker_label.pack(side=tk.LEFT, padx=(2, 6))

        pid_frame = ttk.Frame(row)
        pid_frame.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(pid_frame, text="PID").pack(side=tk.LEFT)
        self.shared_pid = ttk.Label(pid_frame, width=16, relief="sunken", background="white")
        self.shared_pid.pack(side=tk.LEFT, padx=(4, 0))

        title_frame = ttk.Frame(row)
        title_frame.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(title_frame, text="标题").pack(side=tk.LEFT)
        self.video_title = ttk.Entry(title_frame, width=14)
        self.video_title.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(row, text="频道").pack(side=tk.LEFT)
        self.shared_channel = ttk.Label(row, width=12, relief="sunken", background="white")
        self.shared_channel.pack(side=tk.LEFT, padx=(4, 8))

        ttk.Label(row, text="尺寸").pack(side=tk.LEFT)
        self._video_size_presets = ("1920×1080", "1080×1920")
        self.video_size_combo = ttk.Combobox(
            row, width=11, state="readonly", values=self._video_size_presets
        )
        self.video_size_combo.pack(side=tk.LEFT, padx=(4, 8))
        self.video_size_combo.bind("<<ComboboxSelected>>", self._on_video_output_size_selected)

        ttk.Separator(row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self.btn_copy_project = ttk.Button(
            row, text="回到预览", width=8, command=self._return_to_story_preview
        )
        self.btn_copy_project.pack(side=tk.LEFT, padx=2)

   
    def _parse_video_size_combo_label(self, lbl: str):
        s = (lbl or "").replace("×", "x").replace("X", "x").strip()
        a, b = s.lower().split("x", 1)
        return int(a.strip()), int(b.strip())

    def _set_video_size_combo_values(self, vw: int, vh: int):
        if not hasattr(self, "video_size_combo"):
            return
        label = f"{int(vw)}×{int(vh)}"
        vals = list(self._video_size_presets)
        if label not in vals:
            vals = list(vals) + [label]
        self.video_size_combo["values"] = vals
        self._programmatic_video_size = True
        self.video_size_combo.set(label)
        self._programmatic_video_size = False

    def _revert_video_size_combo(self):
        if not project_manager.PROJECT_CONFIG:
            return
        vw = int(project_manager.PROJECT_CONFIG.get("video_width", 1920))
        vh = int(project_manager.PROJECT_CONFIG.get("video_height", 1080))
        self._set_video_size_combo_values(vw, vh)

    def _on_video_output_size_selected(self, event=None):
        if self._programmatic_video_size or self._loading_config:
            return
        wf = getattr(self, "workflow", None)
        if wf is None:
            return
        sel = self.video_size_combo.get()
        try:
            nw, nh = self._parse_video_size_combo_label(sel)
        except (ValueError, TypeError, AttributeError):
            messagebox.showerror("尺寸", f"无法解析分辨率：{sel!r}", parent=self.root)
            self._revert_video_size_combo()
            return
        pc = project_manager.PROJECT_CONFIG
        if not pc:
            return
        cur_w = int(pc.get("video_width", 1920))
        cur_h = int(pc.get("video_height", 1080))
        if (nw, nh) == (cur_w, cur_h):
            return

        if not messagebox.askyesno(
            "更改成片尺寸",
            f"将输出尺寸由 {cur_w}×{cur_h} 改为 {nw}×{nh}。\n\n"
            "将按频道模板（config.make_backgroud_medias：169_ 横屏 / 916_ 竖屏）"
            "重写所有场景的 zero、zero_image、zero_audio、clip、clip_audio、clip_image。\n\n是否继续？",
            parent=self.root,
        ):
            self._revert_video_size_combo()
            return

        old_w, old_h = cur_w, cur_h
        try:
            pc["video_width"] = nw
            pc["video_height"] = nh
            wf.reapply_all_scenes_template_medias(nw, nh)
            ProjectConfigManager.set_global_config(pc)
            save_project_config(parent=self.root)
            self.refresh_gui_scenes()
            messagebox.showinfo(
                "尺寸",
                f"已更新为 {nw}×{nh}，各场景模板底稿已刷新，项目配置已保存。",
                parent=self.root,
            )
        except Exception as e:
            pc["video_width"] = old_w
            pc["video_height"] = old_h
            ProjectConfigManager.set_global_config(pc)
            try:
                wf.ffmpeg_processor = FfmpegProcessor(wf.pid, wf.language, old_w, old_h)
            except Exception:
                pass
            self._revert_video_size_combo()
            try:
                wf.load_scenes()
            except Exception:
                pass
            try:
                save_project_config(parent=self.root)
            except Exception:
                pass
            self.refresh_gui_scenes()
            messagebox.showerror(
                "尺寸",
                f"更新失败，已恢复配置为 {old_w}×{old_h} 并从磁盘重载场景列表：\n{e}",
                parent=self.root,
            )

    def _load_current_video_detail_row(self) -> dict | None:
        """当前项目绑定的 video detail：目标主题分表 list/<topic_category>.json，按 project_profile.pid 匹配。"""
        return project_manager.load_video_detail_row_for_config(
            project_manager.PROJECT_CONFIG or {}
        )

    def _workflow_video_detail_for_edit(self) -> dict:
        """合并列表行与 ``PROJECT_CONFIG``，供与 downloader 共用的内容编辑弹窗使用。"""
        pc = project_manager.PROJECT_CONFIG or {}
        row = self._load_current_video_detail_row()
        vd = copy.deepcopy(row) if row else {}
        for field in ("analyzed_content", "scene_content", "url", "title", "id"):
            val = pc.get(field)
            if val in (None, "", [], {}):
                continue
            if field not in vd or vd.get(field) in (None, "", [], {}):
                vd[field] = copy.deepcopy(val)
        file_pid = (pc.get("pid") or "").strip()
        if file_pid and not (vd.get("id") or "").strip():
            vd["id"] = file_pid
        return vd

    def _copy_clipboard_text(self, title: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            messagebox.showinfo(title, "这里没有内容。", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        show_auto_close_popup(self.root, title, "已拷贝")

    def _copy_analyzed_content(self) -> None:
        vd = self._workflow_video_detail_for_edit()
        text = vd.get("analyzed_content") if isinstance(vd.get("analyzed_content"), str) else ""
        self._copy_clipboard_text("分析", text)

    def _copy_poem(self) -> None:
        pc = project_manager.PROJECT_CONFIG or {}
        row = self._load_current_video_detail_row() or {}
        text = (pc.get("poem") or row.get("poem") or "")
        self._copy_clipboard_text("诗歌", text if isinstance(text, str) else "")

    def _copy_script(self) -> None:
        row = self._load_current_video_detail_row() or {}
        pc = project_manager.PROJECT_CONFIG or {}
        vd = dict(row)
        if not (vd.get("transcribed_file") or "").strip():
            stored = (pc.get("transcribed_file") or "").strip()
            if stored:
                vd["transcribed_file"] = stored
        self._copy_clipboard_text("脚本", config.read_transcript_text_from_video_detail(vd))

    def _return_to_story_preview(self) -> None:
        """回到这条的故事预览。预览还没开时，请列表打开它，再拿到前面。"""
        from gui.raise_window import find_story_window, raise_window

        pc = project_manager.PROJECT_CONFIG or {}
        row = self._load_current_video_detail_row() or {}
        title = ""
        keys: list[str] = []
        for src in (pc, row):
            if not isinstance(src, dict):
                continue
            if not title:
                title = (src.get("video_title") or src.get("title") or "").strip()
            for key in ("pid", "id", "url"):
                val = (src.get(key) or "").strip()
                if val and val not in keys:
                    keys.append(val)

        def _matches(hwnd: int) -> bool:
            if not hwnd or not title:
                return bool(hwnd) and not title
            try:
                import win32gui

                text = win32gui.GetWindowText(int(hwnd)) or ""
            except Exception:
                return False
            return title[:24] in text

        hwnd = find_story_window()
        if hwnd and _matches(hwnd):
            raise_window(hwnd)
            return
        if not keys:
            messagebox.showinfo(
                "回到预览",
                "这条没有能对上列表的编号，预览打不开。",
                parent=self.root,
            )
            return

        def work() -> None:
            from cli.bridge import send_bridge_command

            ok, _msg = send_bridge_command(
                screen=config.SCREEN_VIDEO_LIST,
                op="set",
                field="open_row",
                value=json.dumps(keys, ensure_ascii=False),
                timeout_s=8.0,
            )
            found = 0
            if ok:
                for _ in range(40):
                    candidate = find_story_window()
                    if candidate and _matches(candidate):
                        found = candidate
                        break
                    time.sleep(0.15)

            def done() -> None:
                if found:
                    raise_window(found)
                    return
                messagebox.showinfo(
                    "回到预览",
                    "列表窗口要开着，才能从这里打开故事预览。",
                    parent=self.root,
                )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _current_feature_row(self) -> dict:
        row = self._load_current_video_detail_row()
        return row if isinstance(row, dict) else {}

    def _reveal_published_video(self, path: str) -> None:
        from gui.downloader import _open_feature_media_in_explorer

        _open_feature_media_in_explorer(path)

    def _project_cover_and_slide(self) -> tuple[str, str]:
        from gui.downloader import _find_gen_video_slide_for_row, _find_gen_video_webp_for_row

        pc = project_manager.PROJECT_CONFIG or {}
        row = self._current_feature_row()
        cover = ""
        slide = ""
        for src in (pc, row):
            if not isinstance(src, dict):
                continue
            stored_cover = (src.get("cover_image") or "").strip()
            stored_slide = (src.get("slide") or "").strip()
            if not cover and stored_cover and os.path.isfile(stored_cover):
                cover = os.path.abspath(stored_cover)
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

    def _open_suno_gui(self):
        """打开SUNO音乐提示词管理窗口"""
        try:
            # 创建SUNO管理窗口
            suno_gui = SunoMusicPromptGUI(self.root)
        except Exception as e:
            messagebox.showerror("错误", f"打开SUNO管理窗口失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def swap_narration(self):
        """交换第一轨道与旁白轨道"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        clip_video_path = get_file_path(current_scene, 'clip')
        clip_audio_path = get_file_path(current_scene, 'clip_audio')
        track_path = get_file_path(current_scene, "narration")
        if not track_path:
            messagebox.showwarning("警告", "narration 轨道视频文件不存在")
            return
        temp_track = self.workflow.ffmpeg_processor.add_audio_to_video(track_path, clip_audio_path)

        refresh_scene_media(current_scene, "narration", '.mp4', clip_video_path)
        refresh_scene_media(current_scene, "narration_audio", '.wav', clip_audio_path, True)

        refresh_scene_media(current_scene, 'clip', '.mp4', temp_track)
        self.refresh_gui_scenes()


    def _backup_clip_to_scene_back(self, scene):
        """改写主轨前，只记住当前这一条 clip 和 clip_audio。恢復Back 只能退这一步。"""
        clip_path = get_file_path(scene, "clip")
        if not clip_path or not os.path.isfile(clip_path):
            return False
        scene["back"] = clip_path
        audio_path = scene.get("clip_audio") if isinstance(scene.get("clip_audio"), str) else ""
        audio_path = audio_path.strip()
        if audio_path and os.path.isfile(audio_path):
            scene["back_audio"] = audio_path
        else:
            scene.pop("back_audio", None)
        return True


    def track_recover(self):
        """把主轨退回上一次改写之前。只退一步，退完就没有更早的版本。"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            messagebox.showwarning("警告", "没有当前场景")
            return
        back = current_scene.get("back") or ""
        if not isinstance(back, str):
            back = ""
        back_path = ""
        for part in back.split(","):
            part = part.strip()
            if part and os.path.isfile(part):
                back_path = part
                break
        if not back_path:
            messagebox.showwarning("警告", "没有可恢复的上一步视频")
            return

        audio_path = current_scene.get("back_audio") or ""
        if not isinstance(audio_path, str):
            audio_path = ""
        audio_path = audio_path.strip()
        if audio_path and not os.path.isfile(audio_path):
            audio_path = ""

        refresh_scene_media(current_scene, "clip", ".mp4", back_path)
        if audio_path:
            refresh_scene_media(current_scene, "clip_audio", ".wav", audio_path, True)
        current_scene.pop("back", None)
        current_scene.pop("back_audio", None)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


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
        spd = round(float(speed or 1.0), 1)
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
    ):
        """在后台线程执行 ``video_simple_replacement``（内含 resize、混音等密集 FFmpeg），避免主界面假死。"""

        def work():
            err = None
            try:
                self.media_scanner.video_simple_replacement(
                    scene, tmp_mp4, tmp_wav, audio_choice, track
                )
            except Exception as e:
                err = str(e)

            def done():
                try:
                    self.root.config(cursor="")
                except tk.TclError:
                    pass
                if err:
                    messagebox.showerror("错误", f"视频处理失败：{err}", parent=self.root)
                else:
                    scene[track + "_status"] = track_status
                    self.workflow.save_scenes_to_json()
                    self.refresh_gui_scenes()

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
                for name in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end"):
                    raw = scene.get(name)
                    if raw is None or raw == "":
                        continue
                    try:
                        scene[name] = round(float(raw) + added, 2)
                    except (TypeError, ValueError):
                        pass

    def _clip_overlay_ffmpeg_batch_async(
        self,
        target_scenes,
        overlay_path,
        opts,
        dialog_title,
        failure_verb,
        apply_overlay,
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


    def _narrator_button_text(self, name: str = "") -> str:
        """按钮上只写讲员本人，例如 woman/qin/chinese。"""
        name = (name or project_manager.project_narrator() or "").strip()
        if not name or project_manager.actor_is_absent(name):
            return "不出现"
        return name

    def _refresh_narrator_button(self, name: str = "") -> None:
        btn = getattr(self, "_narrator_avatar_btn", None)
        if btn is not None:
            text = self._narrator_button_text(name)
            width = sum(2 if ord(ch) > 127 else 1 for ch in text) + 2
            btn.config(text=text, width=max(width, 8))

    def _actor_button_text(self, label: str, body: str, *, full: bool = False) -> str:
        body = (body or "").strip()
        if full and body:
            return f"{label} {body}"
        parts = [p for p in body.split("/") if p]
        if len(parts) >= 4 and not parts[-1].isdigit():
            short = parts[-1]
        else:
            short = parts[1] if len(parts) >= 2 else body
        short = short.strip()
        if len(short) > 8:
            short = short[:8]
        if not short:
            return label
        return f"{label} {short}"

    @staticmethod
    def _motion_chip_text(motion: str) -> str:
        motion = (motion or "").strip()
        if not motion or "已经在画面" in motion:
            return ""
        short = {
            "从容自然地 - 走进画面，讲完走出": "走进走出",
            "淡入画面，讲完淡出": "淡入淡出",
            "边品茶, 边讲述 - 淡入画面，讲完淡出": "茶叙式",
            "跳进画面，讲完跳出": "跳进跳出",
            "自然地 - 骑马走进画面，讲完骑马走出": "骑马进出",
        }
        return short.get(motion, motion)

    def _render_actor_buttons(self) -> None:
        row = getattr(self, "scene_actor_row", None)
        if row is None:
            return
        for child in row.winfo_children():
            child.destroy()
        entries = project_manager.actor_entries(self._actor_text)
        self._actor_buttons = []
        self._actor_drag_index = None
        self._actor_drag_moved = False
        if not entries:
            ttk.Label(row, text="（没有人物）").pack(side=tk.LEFT, padx=(0, 4))
        for entry in entries:
            if entry.get("role") == "host" and project_manager.actor_is_absent(entry.get("body") or ""):
                continue
            self._pack_actor_button(row, entry)

    def _pack_actor_button(self, row, entry: dict) -> None:
        body = (entry.get("body") or "").strip()
        base, motion = project_manager.split_actor_motion(body)
        if entry.get("role") == "host":
            text = self._actor_button_text("讲员", base, full=True) if base else "讲员"
        else:
            text = self._actor_button_text(entry.get("label") or "人物", base)
        motion_text = self._motion_chip_text(motion)
        if motion_text:
            text = f"{text} {motion_text}"
        chip = tk.Frame(row, bg="white", relief="sunken", bd=1, cursor="fleur")
        label = tk.Label(chip, text=text, bg="white", cursor="fleur", anchor="w")
        label.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        chip._actor_entry = dict(entry)
        chip._actor_label = text
        chip.pack(side=tk.LEFT, padx=(0, 4))
        chip.update_idletasks()
        chip.configure(width=max(int(label.winfo_reqwidth() * 1.5) + 12, 72), height=label.winfo_reqheight() + 6)
        chip.pack_propagate(False)
        for widget in (chip, label):
            widget.bind("<ButtonPress-1>", self._actor_press)
            widget.bind("<B1-Motion>", self._actor_motion)
            widget.bind("<ButtonRelease-1>", self._actor_release)
            widget.bind("<Double-Button-1>", self._actor_double)
        self._actor_buttons.append(chip)

    def _actor_chip(self, widget):
        buttons = getattr(self, "_actor_buttons", None) or []
        while widget is not None and widget not in buttons:
            widget = getattr(widget, "master", None)
        return widget

    def _actor_press(self, event) -> None:
        btn = self._actor_chip(event.widget)
        try:
            self._actor_drag_index = self._actor_buttons.index(btn)
        except ValueError:
            self._actor_drag_index = None
        self._actor_drag_moved = False
        self._actor_drag_x = event.x_root

    def _actor_motion(self, event) -> None:
        src = self._actor_drag_index
        buttons = getattr(self, "_actor_buttons", None) or []
        if src is None or not buttons or src >= len(buttons):
            return
        if not self._actor_drag_moved and abs(event.x_root - self._actor_drag_x) < 6:
            return
        target = None
        best = None
        for i, btn in enumerate(buttons):
            center = btn.winfo_rootx() + max(btn.winfo_width(), 1) / 2
            dist = abs(event.x_root - center)
            if best is None or dist < best:
                best = dist
                target = i
        if target is None or target == src:
            return
        self._actor_drag_moved = True
        moved = buttons.pop(src)
        buttons.insert(target, moved)
        self._actor_drag_index = target
        for btn in buttons:
            btn.pack_forget()
        for btn in buttons:
            btn.pack(side=tk.LEFT, padx=(0, 4))

    def _actor_release(self, event) -> None:
        buttons = getattr(self, "_actor_buttons", None) or []
        index = self._actor_drag_index
        moved = self._actor_drag_moved
        self._actor_drag_index = None
        self._actor_drag_moved = False
        if index is None or index >= len(buttons):
            return
        if getattr(self, "_actor_skip_release", False):
            self._actor_skip_release = False
            return
        if not moved:
            chip = buttons[index]
            pending = getattr(self, "_actor_click_after", None)
            if pending:
                try:
                    self.root.after_cancel(pending)
                except tk.TclError:
                    pass
            self._actor_click_after = self.root.after(280, lambda c=chip: self._actor_single_click(c))
            return
        rows = []
        for btn in buttons:
            row = getattr(btn, "_actor_entry", None)
            if not isinstance(row, dict):
                continue
            row = dict(row)
            body = (row.get("body") or "").strip()
            if row.get("role") == "host" and (not body or project_manager.actor_is_absent(body)):
                continue
            if body:
                rows.append(row)
        self._set_actor_text(project_manager.format_actor_entries(rows), save_scene=True)

    def _actor_double(self, event) -> None:
        self._actor_skip_release = True
        pending = getattr(self, "_actor_click_after", None)
        if pending:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
            self._actor_click_after = None
        chip = self._actor_chip(event.widget)
        entry = getattr(chip, "_actor_entry", None) or {}
        self._open_actor_preview(entry)

    def _actor_single_click(self, chip) -> None:
        self._actor_click_after = None
        entry = getattr(chip, "_actor_entry", None) or {}
        path = self._actor_entry_portrait(entry)
        who = getattr(chip, "_actor_label", "") or "这个人"
        body, _motion = project_manager.split_actor_motion((entry.get("body") or "").strip())
        if path:
            self.copy_image_to_clipboard(path, silent=True)
            show_auto_close_popup(self.root, "剪贴板", f"{who} 的参考形象已拷贝", duration_ms=1000)
            return
        if entry.get("role") == "person" and body and not project_manager.actor_is_absent(body):
            self.copy_image_to_clipboard(self._blank_portrait_path(), silent=True)
            show_auto_close_popup(self.root, "剪贴板", f"{who} 没有参考图，已拷贝白板", duration_ms=1000)
            return
        self._open_actor_preview(entry)

    def _open_actor_preview(self, entry: dict) -> None:
        if entry.get("role") == "host":
            self._review_actor_host()
            return
        self._review_actor_person((entry.get("body") or "").strip())

    def _actor_entry_portrait(self, entry: dict) -> str:
        body, _motion = project_manager.split_actor_motion((entry.get("body") or "").strip())
        if project_manager.actor_is_absent(body):
            return ""
        if entry.get("role") == "host":
            names = [body]
            bits = [part for part in body.split("/") if part]
            if len(bits) >= 3:
                names.append("/".join(bits[:3]))
            for name in names:
                path = self._narrator_portrait_path(name)
                if path:
                    return path
            return ""
        return self._person_portrait_path(body)

    def _set_actor_text(self, text: str, *, save_scene: bool = False) -> None:
        self._actor_text = project_manager.normalize_actor_text(text)
        self._render_actor_buttons()
        if not save_scene:
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            return
        old = (scene.get("actor") or "").strip()
        if old == self._actor_text:
            return
        scene["actor"] = self._actor_text
        self.workflow.save_scenes_to_json()

    def _review_actor_host(self) -> None:
        current = project_manager.actor_host_name(self._actor_text)

        def chosen(name: str) -> None:
            self._set_actor_text(project_manager.actor_with_host(self._actor_text, name), save_scene=True)

        host = next(
            (row for row in project_manager.actor_entries(self._actor_text) if row.get("role") == "host"),
            {"role": "host", "label": "讲员", "body": current or "不出现"},
        )
        self.review_project_narrator(current=current, on_confirm=chosen, actor_entry=host)

    @staticmethod
    def _portrait_stem(name: str) -> str:
        stem = (name or "").strip().replace("\\", "/").replace("/", "_")
        for ch in '<>:"|?*':
            stem = stem.replace(ch, "_")
        return stem.strip(" .")

    @staticmethod
    def _narrator_portrait_path(name: str) -> str:
        """voices.json 的 name 把 / 换成 _，对应 avatar 目录里的 png。"""
        stem = WorkflowGUI._portrait_stem(name)
        if not stem:
            return ""
        path = os.path.join(config.AVATAR_PATH, stem + ".png")
        return path if os.path.isfile(path) else ""

    def _narrator_portrait_dest(self, name: str) -> str:
        stem = self._portrait_stem(name)
        if not stem:
            return ""
        return os.path.join(config.AVATAR_PATH, stem + ".png")

    def _blank_portrait_path(self) -> str:
        """背景讲员用的白板图。确定时拷进剪贴板，表示这个人只在背景里说话。"""
        folder = config.AVATAR_PATH
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "_blank.png")
        if not os.path.isfile(path):
            Image.new("RGB", (768, 1024), (255, 255, 255)).save(path, "PNG")
        return path

    def _project_avatar_dir(self) -> str:
        pid = self.get_pid()
        path = os.path.join(config.get_project_path(pid), "avatar")
        os.makedirs(path, exist_ok=True)
        return path

    def _narrator_browse_names(self) -> list:
        return [""] + [x for x in config.narrator_person_options() if (x or "").strip()]

    def _project_person_names(self) -> list:
        """这个项目 avatar 目录里的人物，再加上这一场里还没有图片的人物。"""
        found = []
        folder = ""
        try:
            folder = self._project_avatar_dir()
        except Exception:
            folder = ""
        if folder and os.path.isdir(folder):
            for fn in sorted(os.listdir(folder)):
                low = fn.lower()
                if not low.endswith(".png") or ".bak" in low:
                    continue
                stem = os.path.splitext(fn)[0]
                if not stem or stem.startswith("_"):
                    continue
                raw = stem.replace("_", "/")
                if raw not in found:
                    found.append(raw)
        try:
            rows = self._scene_actor_rows()
        except Exception:
            rows = []
        for row in rows:
            if row.get("role") != "person":
                continue
            body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            if not body or project_manager.actor_is_absent(body) or body in found:
                continue
            found.append(body)
        return found

    def _person_portrait_dest(self, name: str) -> str:
        body, _motion = project_manager.split_actor_motion((name or "").strip())
        stem = self._portrait_stem(body)
        if not stem:
            return ""
        return os.path.join(self._project_avatar_dir(), stem + ".png")

    def _person_portrait_path(self, name: str) -> str:
        path = self._person_portrait_dest(name)
        return path if path and os.path.isfile(path) else ""

    @staticmethod
    def _backup_portrait(path: str) -> None:
        if not path or not os.path.isfile(path):
            return
        folder, base = os.path.split(path)
        stem, ext = os.path.splitext(base)
        n = 1
        while True:
            bak = os.path.join(folder, f"{stem}.bak{n}{ext}")
            if not os.path.exists(bak):
                os.replace(path, bak)
                return
            n += 1

    def _paste_portrait_file(self, dest: str, parent) -> bool:
        """把剪贴板里的图存成 dest。原来有文件就先改名备份。"""
        from PIL import ImageGrab

        if not dest:
            messagebox.showwarning("头像", "先选定一个名字。", parent=parent)
            return False
        clip = ImageGrab.grabclipboard()
        if clip is None:
            messagebox.showwarning("头像", "剪贴板里没有图片。", parent=parent)
            return False
        try:
            if isinstance(clip, list):
                src = next((p for p in clip if p and os.path.isfile(p)), "")
                if not src:
                    messagebox.showwarning("头像", "剪贴板里没有图片。", parent=parent)
                    return False
                img = Image.open(src)
            else:
                img = clip
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            self._backup_portrait(dest)
            img.save(dest, "PNG")
        except Exception as e:
            messagebox.showerror("头像", f"保存失败：{e}", parent=parent)
            return False
        return True

    def _review_actor_person(self, body: str) -> None:
        body, _motion = project_manager.split_actor_motion((body or "").strip())
        if not body:
            return
        names = self._project_person_names()
        if body not in names:
            names.append(body)
        self._open_portrait_dialog(
            title="人物",
            names=names,
            current=body,
            dest_for=self._person_portrait_dest,
            path_for=self._person_portrait_path,
            hint="Ctrl+V 把剪贴板图片存成这个人物。没有就显示没有。人物已经在画面里，拷贝图案直接拷这张图。",
            allow_empty=False,
            ask_motion=False,
            actor_entry={"role": "person", "label": "人物", "body": body},
        )

    def _open_portrait_dialog(
        self,
        *,
        title: str,
        names: list,
        current: str,
        dest_for,
        path_for,
        hint: str,
        allow_empty: bool,
        on_confirm=None,
        ask_motion: bool = False,
        actor_entry: dict | None = None,
        parent=None,
        host_only: bool = False,
    ) -> None:
        """头像预览。左右键换人；Ctrl+V 粘贴图片，旧图先备份。拷贝图案或拷贝背景。"""
        if not names:
            return
        win = parent or self.root
        current = (current or "").strip()
        try:
            index = names.index(current)
        except ValueError:
            index = 0

        dlg = tk.Toplevel(win)
        dlg.title(title)
        dlg.transient(win)
        dlg.grab_set()
        dlg.resizable(False, False)

        name_var = tk.StringVar()
        ttk.Label(dlg, textvariable=name_var, font=("TkDefaultFont", 12, "bold")).pack(pady=(12, 4))
        image_label = ttk.Label(dlg)
        image_label.pack(padx=16, pady=4)
        voice_row = ttk.Frame(dlg)
        voice_row.pack(pady=(0, 8))
        ttk.Label(voice_row, text="声音").pack(side=tk.LEFT, padx=(0, 8))
        voice_var = tk.StringVar()
        voice_box = ttk.Combobox(voice_row, textvariable=voice_var, state="readonly", width=18)
        voice_box.pack(side=tk.LEFT)
        hint_var = tk.StringVar(value=hint)
        ttk.Label(dlg, textvariable=hint_var, wraplength=640).pack(pady=(0, 8))
        holder = {
            "photo": None,
            "index": index,
            "names": list(names),
            "path_for": path_for,
            "dest_for": dest_for,
            "mode": "host" if ask_motion else "person",
            "override_name": "",
            "voice_ready": False,
        }
        host_hint = "左右键在讲员里换。讲员是 D:\\AI_MEDIA\\avatar 里那一份固定名单。最左表示这场没有讲员，名单里不写。拷贝图案拷当前图，并问怎么进出画面。拷贝背景拷白板，人还在，只是不进画面。"
        person_hint = "左右键在这个项目的人物里换。人物图片在项目的 avatar 目录。增加人物只在这一边。没有图片时拷贝用白板。Ctrl+V 可以贴上形象。"

        def remember_voice(name: str, voice: str) -> None:
            pc = project_manager.PROJECT_CONFIG
            if not isinstance(pc, dict) or not name or not voice:
                return
            role = "host" if holder.get("mode") == "host" else "person"
            key = config_prompt.actor_voice_storage_key(name, role)
            if not key:
                return
            table = pc.get("actor_voices")
            if not isinstance(table, dict):
                table = {}
                pc["actor_voices"] = table
            if table.get(key) == voice:
                return
            table[key] = voice
            save_project_config(parent=dlg)

        def show_voice(name: str) -> None:
            holder["voice_ready"] = False
            if not name or project_manager.actor_is_absent(name):
                voice_box.configure(values=())
                voice_var.set("")
                voice_box.state(["disabled"])
                return
            role = "host" if holder.get("mode") == "host" else "person"
            options = list(config_prompt.voice_choices_for_actor(name))
            voice_box.configure(values=options)
            if not options:
                voice_var.set("")
                voice_box.state(["disabled"])
                return
            voice_box.state(["!disabled"])
            saved = config_prompt.chosen_actor_voice(name, role)
            voice_var.set(saved if saved in options else options[0])
            holder["voice_ready"] = True
            if len(options) == 1:
                remember_voice(name, options[0])

        def on_voice_picked(_event=None) -> None:
            if not holder.get("voice_ready"):
                return
            names_now = holder["names"]
            if not names_now:
                return
            name = names_now[holder["index"]]
            remember_voice(name, voice_var.get().strip())

        def show_at(i: int) -> None:
            holder["override_name"] = ""
            names_now = holder["names"]
            if not names_now:
                holder["index"] = 0
                name_var.set("还没有人物")
                holder["photo"] = None
                image_label.config(image="", text="还没有人物")
                show_voice("")
                return
            holder["index"] = max(0, min(i, len(names_now) - 1))
            name = names_now[holder["index"]]
            if not name:
                name_var.set("不出现")
                show_voice("")
                path = self._blank_portrait_path()
                try:
                    img = Image.open(path)
                    img.thumbnail((420, 560), Image.Resampling.LANCZOS)
                    holder["photo"] = ImageTk.PhotoImage(img)
                    image_label.config(image=holder["photo"], text="")
                except OSError:
                    holder["photo"] = None
                    image_label.config(image="", text="不出现")
                return
            name_var.set(name)
            show_voice(name)
            path = holder["path_for"](name)
            if not path:
                holder["photo"] = None
                image_label.config(image="", text="没有头像")
                return
            try:
                img = Image.open(path)
                img.thumbnail((420, 560), Image.Resampling.LANCZOS)
                holder["photo"] = ImageTk.PhotoImage(img)
                image_label.config(image=holder["photo"], text="")
            except OSError:
                holder["photo"] = None
                image_label.config(image="", text="没有头像")

        def shift(step: int) -> None:
            names_now = holder["names"]
            if len(names_now) < 2:
                return
            nxt = max(0, min(holder["index"] + step, len(names_now) - 1))
            show_at(nxt)

        def paste(_event=None) -> str:
            names_now = holder["names"]
            if not names_now:
                return "break"
            name = names_now[holder["index"]]
            if not name:
                messagebox.showinfo(title, "不出现的人不用粘贴图片。", parent=dlg)
                return "break"
            if self._paste_portrait_file(holder["dest_for"](name), dlg):
                show_at(holder["index"])
            return "break"

        def ask_motion_choice() -> str:
            dlg.grab_release()
            picked = askchoice(
                "这个人怎么进出画面",
                [
                    ("走进走出", "从容自然地 - 走进画面，讲完走出"),
                    ("淡入淡出", "淡入画面，讲完淡出"),
                    ("茶叙式",   "边品茶, 边讲述 - 淡入画面，讲完淡出"),
                    ("跳进跳出", "跳进画面，讲完跳出"),
                    ("骑马进出", "自然地 - 骑马走进画面，讲完骑马走出")
                ],
                dlg,
            )
            dlg.grab_set()
            return picked[0] if picked else ""

        def apply_choice(name: str, motion: str) -> None:
            """把打开时的那一格换成现在选定的人。收成性别、年龄段、民族，名字放最后。"""
            role = "host" if holder.get("mode") == "host" else "person"
            bare = (name or "").strip()
            if project_manager.actor_is_absent(bare):
                if role == "host" and actor_entry:
                    self._clear_scene_host(dlg)
                elif on_confirm is not None and role == "host":
                    on_confirm("")
                return
            if role != "host":
                motion = ""
            body = project_manager.actor_body_with_default_age(bare)
            if motion:
                base, _old = project_manager.split_actor_motion(body)
                body = project_manager._with_actor_motion(base, motion)
            if role == "person" and self._scene_has_person(body):
                return
            if actor_entry:
                self._replace_opened_actor(actor_entry, role, body)
                return
            if on_confirm is not None and role == "host":
                on_confirm(bare)

        def finish(copy_blank: bool) -> None:
            if holder.get("override_name"):
                name = holder["override_name"]
            else:
                names_now = holder["names"]
                if holder.get("mode") == "person" and not names_now:
                    messagebox.showinfo("人物", "先选定一个人物。", parent=dlg)
                    return
                name = (names_now[holder["index"]] if names_now else "") or ""
            if holder.get("mode") == "person" and not name:
                messagebox.showinfo("人物", "先选定一个人物。", parent=dlg)
                return
            motion = ""
            if holder.get("mode") == "host" and not copy_blank and name and not project_manager.actor_is_absent(name):
                motion = ask_motion_choice()
                if not motion:
                    return
            if copy_blank or not name or project_manager.actor_is_absent(name):
                portrait = self._blank_portrait_path()
            elif holder.get("override_name"):
                portrait = self._narrator_portrait_path(name) or self._blank_portrait_path()
            else:
                portrait = holder["path_for"](name) or ""
                if not portrait and holder.get("mode") == "person":
                    portrait = self._blank_portrait_path()
            if portrait:
                self.copy_image_to_clipboard(portrait, silent=True)
            apply_choice(name, motion)
            dlg.destroy()

        def delete_entry() -> None:
            if not self._delete_scene_actor(actor_entry, dlg):
                return
            dlg.destroy()

        def add_person() -> None:
            dlg.grab_release()
            try:
                before = list(holder["names"])
                self._add_manual_scene_person(dlg)
            finally:
                try:
                    dlg.grab_set()
                except tk.TclError:
                    pass
            if holder.get("mode") != "person":
                return
            holder["names"] = self._project_person_names()
            added = [name for name in holder["names"] if name not in before]
            show_at(holder["names"].index(added[-1]) if added else holder["index"])

        def apply_domain_chrome() -> None:
            if holder["mode"] == "host":
                dlg.title("讲员")
                hint_var.set(host_hint)
                switch_btn.config(text="切换成人物")
                add_btn.pack_forget()
                return
            dlg.title("人物")
            hint_var.set(person_hint)
            switch_btn.config(text="切换成讲员")
            if not add_btn.winfo_ismapped():
                add_btn.pack(side=tk.LEFT, padx=6, before=delete_btn if actor_entry else cancel_btn)

        def toggle_domain() -> None:
            if holder["mode"] == "host":
                holder["mode"] = "person"
                holder["names"] = self._project_person_names()
                holder["path_for"] = self._person_portrait_path
                holder["dest_for"] = self._person_portrait_dest
                start = 0
                body = ""
                if actor_entry and actor_entry.get("role") == "person":
                    body, _motion = project_manager.split_actor_motion(actor_entry.get("body") or "")
                if body and body in holder["names"]:
                    start = holder["names"].index(body)
            else:
                holder["mode"] = "host"
                holder["names"] = self._narrator_browse_names()
                holder["path_for"] = self._narrator_portrait_path
                holder["dest_for"] = self._narrator_portrait_dest
                current_host = project_manager.project_narrator()
                start = holder["names"].index(current_host) if current_host in holder["names"] else 0
            holder["override_name"] = ""
            apply_domain_chrome()
            show_at(start)

        btns = ttk.Frame(dlg)
        btns.pack(pady=(0, 12))
        ttk.Button(btns, text="拷贝图案", command=lambda: finish(False)).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="拷贝背景", command=lambda: finish(True)).pack(side=tk.LEFT, padx=6)
        switch_btn = ttk.Button(btns, text="切换成人物", command=toggle_domain)
        if not host_only:
            switch_btn.pack(side=tk.LEFT, padx=6)
        add_btn = ttk.Button(btns, text="增加人物", command=add_person)
        delete_btn = None
        if actor_entry:
            delete_btn = ttk.Button(btns, text="删除", command=delete_entry)
            delete_btn.pack(side=tk.LEFT, padx=6)
        cancel_btn = ttk.Button(btns, text="取消", command=dlg.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=6)
        apply_domain_chrome()

        voice_box.bind("<<ComboboxSelected>>", on_voice_picked)
        image_label.bind("<Button-1>", lambda _e: shift(1))
        image_label.bind("<Button-3>", lambda _e: shift(-1))
        dlg.bind("<Left>", lambda _e: shift(-1))
        dlg.bind("<Right>", lambda _e: shift(1))
        dlg.bind("<Control-v>", paste)
        dlg.bind("<Return>", lambda _e: finish(False))
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        show_at(index)
        dlg.update_idletasks()
        x = win.winfo_rootx() + max(0, (win.winfo_width() - dlg.winfo_reqwidth()) // 2)
        y = win.winfo_rooty() + max(0, (win.winfo_height() - dlg.winfo_reqheight()) // 2)
        dlg.geometry(f"+{x}+{y}")
        dlg.focus_set()
        dlg.wait_window()

    def _write_actor_motion(self, name: str, motion: str) -> None:
        """把进出方式写进当前场景里这个人的 actor 名字后面。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            return
        name = (name or "").strip()
        motion = (motion or "").strip()
        if not name or not motion:
            return
        entries = project_manager.actor_entries(scene.get("actor") or self._actor_text)
        for row in entries:
            base, _old = project_manager.split_actor_motion(row.get("body") or "")
            if base == name:
                row["body"] = project_manager._with_actor_motion(base, motion)
                self._set_actor_text(project_manager.format_actor_entries(entries), save_scene=True)
                return

    def _scene_actor_rows(self) -> list:
        return project_manager.actor_entries(self._actor_text)

    def _drop_scene_actor(self, entry: dict) -> tuple[list, bool]:
        target_role = (entry or {}).get("role")
        target_body, _motion = project_manager.split_actor_motion((entry or {}).get("body") or "")
        kept = []
        removed = False
        for row in self._scene_actor_rows():
            body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            same = row.get("role") == target_role and (target_role == "host" or body == target_body)
            if same and not removed:
                removed = True
                continue
            kept.append(row)
        return kept, removed

    def _delete_scene_actor(self, entry: dict | None, parent) -> bool:
        if not entry:
            return False
        rows = self._scene_actor_rows()
        if len(rows) <= 1:
            messagebox.showinfo("删除", "这一场至少要留下一个讲员或人物。", parent=parent)
            return False
        kept, removed = self._drop_scene_actor(entry)
        if not removed:
            messagebox.showinfo("删除", "这一场的名单里没有这一位。", parent=parent)
            return False
        if not messagebox.askyesno("删除", "删除这一位？这一场的人物里就没有他了。", parent=parent):
            return False
        self._set_actor_text(project_manager.format_actor_entries(kept), save_scene=True)
        return True

    def _clear_scene_host(self, parent) -> bool:
        """这场没有讲员。从名单里拿掉，不写「不出现」。"""
        people = [
            row for row in self._scene_actor_rows()
            if row.get("role") != "host" and not project_manager.actor_is_absent(row.get("body") or "")
        ]
        if not people:
            messagebox.showinfo("讲员", "这一场至少要留下一个讲员或人物。", parent=parent)
            return False
        self._set_actor_text(project_manager.format_actor_entries(people), save_scene=True)
        return True

    def _replace_opened_actor(self, entry: dict | None, role: str, body: str) -> None:
        """把打开预览时的那一格换成现在这个人，位置不动。换成讲员时，原来的讲员让开。"""
        role = "host" if role == "host" else "person"
        body = (body or "").strip() or "不出现"
        target_role = (entry or {}).get("role")
        target_body, _motion = project_manager.split_actor_motion((entry or {}).get("body") or "")
        rows = []
        replaced = False
        for row in self._scene_actor_rows():
            row_body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            same = row.get("role") == target_role and (target_role == "host" or row_body == target_body)
            if same and not replaced:
                rows.append({"role": role, "label": "讲员" if role == "host" else "人物", "body": body})
                replaced = True
                continue
            if role == "host" and row.get("role") == "host":
                continue
            rows.append(row)
        if not replaced:
            if role == "person" and self._scene_has_person(body):
                return
            rows.append({"role": role, "label": "讲员" if role == "host" else "人物", "body": body})
        self._set_actor_text(project_manager.format_actor_entries(rows), save_scene=True)

    def _scene_has_person(self, body: str) -> bool:
        want, _motion = project_manager.split_actor_motion(project_manager.actor_body_with_default_age(body))
        if not want or project_manager.actor_is_absent(want):
            return False
        for row in self._scene_actor_rows():
            if row.get("role") != "person":
                continue
            got, _motion = project_manager.split_actor_motion(row.get("body") or "")
            if got == want:
                return True
        return False

    def _switch_scene_actor_to_host(self, entry: dict | None, narrator: str) -> None:
        narrator = (narrator or "").strip() or "不出现"
        rows = []
        replaced = False
        target_role = (entry or {}).get("role")
        target_body, _motion = project_manager.split_actor_motion((entry or {}).get("body") or "")
        for row in self._scene_actor_rows():
            body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            same = row.get("role") == target_role and (target_role == "host" or body == target_body)
            if same and not replaced:
                rows.append({"role": "host", "label": "讲员", "body": narrator})
                replaced = True
                continue
            if row.get("role") == "host":
                continue
            rows.append(row)
        if not replaced:
            rows.append({"role": "host", "label": "讲员", "body": narrator})
        self._set_actor_text(project_manager.format_actor_entries(rows), save_scene=True)

    def _ask_manual_person(self, parent) -> str:
        """手工加一位人物。名字可空，有名字就写在最后。"""
        box = tk.Toplevel(parent)
        box.title("增加人物")
        box.transient(parent)
        box.grab_set()
        box.resizable(False, False)
        result = {"body": ""}
        gender = tk.StringVar(value="woman")
        bucket = tk.StringVar(value="mature")
        race = tk.StringVar(value="chinese")
        person_name = tk.StringVar()

        frm = ttk.Frame(box, padding=12)
        frm.pack()
        ttk.Label(frm, text="男女").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(frm, textvariable=gender, values=("woman", "man"), state="readonly", width=18).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(frm, text="年龄段").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm,
            textvariable=bucket,
            values=("kids", "youth", "teenager", "mature", "senior"),
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="w")
        ttk.Label(frm, text="中英").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(frm, textvariable=race, values=("chinese", "english"), state="readonly", width=18).grid(
            row=2, column=1, sticky="w"
        )
        ttk.Label(frm, text="名字").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=person_name, width=20).grid(row=3, column=1, sticky="w")
        ttk.Label(frm, text="可以不填。有名字就写在最后。").grid(row=3, column=2, sticky="w", padx=8)
        ttk.Label(
            frm,
            text="加上之后可以拖到第几位。没有图片时，参考图用白板。双击这位，Ctrl+V 可以贴上形象。",
            wraplength=360,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        def ok() -> None:
            body = (
                f"{gender.get().strip() or 'woman'}/"
                f"{bucket.get().strip() or 'mature'}/"
                f"{race.get().strip() or 'chinese'}"
            )
            who = person_name.get().strip()
            if who:
                body = f"{body}/{who}"
            result["body"] = body
            box.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btns, text="加上", command=ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="取消", command=box.destroy).pack(side=tk.LEFT, padx=6)
        box.bind("<Return>", lambda _e: ok())
        box.bind("<Escape>", lambda _e: box.destroy())
        box.protocol("WM_DELETE_WINDOW", box.destroy)
        box.focus_set()
        box.wait_window()
        return result["body"]

    def _add_manual_scene_person(self, parent) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            messagebox.showinfo("增加人物", "先打开一场。", parent=parent)
            return
        people = [
            row for row in self._scene_actor_rows()
            if row.get("role") == "person" and not project_manager.actor_is_absent(row.get("body") or "")
        ]
        if len(people) >= 4:
            messagebox.showinfo("增加人物", "这一场最多四个人物。", parent=parent)
            return
        body = self._ask_manual_person(parent)
        if not body:
            return
        rows = list(self._scene_actor_rows())
        rows.append({"role": "person", "label": "人物", "body": body})
        self._set_actor_text(project_manager.format_actor_entries(rows), save_scene=True)

    def review_project_narrator(self, current: str | None = None, on_confirm=None, actor_entry=None, parent=None) -> None:
        """左右键翻讲员头像。默认写回项目 narrator；传入 on_confirm 则交给调用方。"""
        win = parent or self.root
        pc = project_manager.PROJECT_CONFIG
        if parent is None and not isinstance(pc, dict):
            messagebox.showwarning("讲员", "请先加载或创建项目。", parent=win)
            return
        names = [""] + [x for x in config.narrator_person_options() if (x or "").strip()]
        if len(names) == 1:
            messagebox.showwarning("讲员", "voices.json 里没有可选讲员。", parent=win)
            return
        if current is None:
            current = project_manager.project_narrator()

        def chosen(name: str) -> None:
            if on_confirm is not None:
                on_confirm(name)
                return
            if isinstance(pc, dict):
                pc["narrator"] = name
            project_manager.LAST_NARRATOR = name
            save_project_config(parent=win)
            self._refresh_narrator_button(name)

        self._open_portrait_dialog(
            title="讲员",
            names=names,
            current=(current or "").strip(),
            dest_for=self._narrator_portrait_dest,
            path_for=self._narrator_portrait_path,
            hint="← 最左是不出现：不进画面，也不说话。拷贝图案拷当前图，并问怎么进出画面。拷贝背景拷白板，人选不变。",
            allow_empty=True,
            on_confirm=chosen,
            ask_motion=True,
            actor_entry=actor_entry,
            parent=win,
            host_only=parent is not None,
        )

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
            landscape = int(project_manager.PROJECT_CONFIG.get("video_width", 1920)) > int(
                project_manager.PROJECT_CONFIG.get("video_height", 1080)
            )
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


    def _ask_radio_choice(self, title: str, options: list) -> str | None:
        """选项是 (值, 文字)。确定返回选中的值，取消返回空。"""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        var = tk.StringVar(value=options[0][0])
        holder = {"value": None}
        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=title).pack(anchor=tk.W, pady=(0, 8))
        for value, label in options:
            ttk.Radiobutton(frame, text=label, value=value, variable=var).pack(anchor=tk.W, pady=2)

        def ok() -> None:
            holder["value"] = var.get()
            dlg.destroy()

        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(row, text="确定", command=ok).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)
        dlg.update_idletasks()
        w, h = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - w) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - h) // 2)
        dlg.geometry(f"+{x}+{y}")
        dlg.grab_set()
        dlg.wait_window()
        return holder["value"]

    def _pick_media_from_download_to_project_folder(
        self, suffixes_tuple, *, track_rename_key: str, confirm_actions=None, radios=None
    ):
        """从用户 Downloads（或 L:）或项目 download 选一文件→整理到项目 download。

        顺序：① ``~/Downloads``（及可选 ``L:``）中新下载的源文件；② 项目 ``download/`` 内已整理好的成片。
        """
        suffixes = _normalize_download_suffixes(suffixes_tuple)
        single_mp4_only = suffixes == (".mp4",)
        pv_kw: dict = {}
        if single_mp4_only:
            pv_kw = {
                "use_mp4_video_preview": True,
                "build_volume_adjusted_pair": self._build_volume_adjusted_mp4_wav_pair,
            }
            if confirm_actions:
                pv_kw["confirm_actions"] = confirm_actions
            if radios:
                pv_kw["radios"] = radios
        place_mode = None
        picked_radio = None

        def _unpack_mp4_pick(r):
            nonlocal place_mode, picked_radio
            if r is not None and len(r) >= 4:
                if confirm_actions and radios and len(r) >= 5:
                    place_mode = r[3]
                    picked_radio = r[4]
                elif radios and not confirm_actions:
                    picked_radio = r[3]
                else:
                    place_mode = r[3]
            return r[0], r[1], r[2]

        title_drive = "从 Downloads 选择视频" if single_mp4_only else "从 Downloads 选择媒体（MP3/MP4）"
        title_proj = "从项目 download 选择视频" if single_mp4_only else "从项目 download 选择媒体（MP3/MP4）"

        media_path = None
        temp_adj_mp4 = None
        temp_adj_wav = None

        scene0 = self.workflow.get_scene_by_index(self.current_scene_index)
        sid = scene0["id"] if scene0 else 0

        for folder in _external_media_pick_folders():
            matching = _download_folder_list_matching_suffixes(folder, suffixes)
            if not matching:
                continue
            pick_title = title_drive
            if folder != _user_downloads_folder():
                pick_title = "从下载盘选择视频" if single_mp4_only else "从下载盘选择媒体（MP3/MP4）"
            r = askchoice_media_preview(pick_title, matching, folder, self.root, **pv_kw)
            if not r:
                return None
            if single_mp4_only:
                fn, temp_adj_mp4, temp_adj_wav = _unpack_mp4_pick(r)
                media_path = os.path.join(folder, fn)
            else:
                media_path = os.path.join(folder, r)
            break

        download_path = config.get_project_path(self.workflow.pid) + "/download"
        if not os.path.exists(download_path):
            os.makedirs(download_path, exist_ok=True)

        if media_path:
            ext = os.path.splitext(media_path)[1].lower() or (suffixes[0] if suffixes else ".mp4")
            rename_dest = os.path.join(
                download_path,
                f'{(picked_radio or track_rename_key)}_{sid}_{datetime.now().strftime("%H%M%S")}{ext}',
            )
            shutil.move(media_path, rename_dest)
            media_final = rename_dest
            if (
                media_final.lower().endswith(".mp4")
                and not single_mp4_only
                and (temp_adj_mp4 is None or temp_adj_wav is None)
            ):
                dn = os.path.dirname(media_final)
                bn = os.path.basename(media_final)
                pv2 = {
                    "use_mp4_video_preview": True,
                    "build_volume_adjusted_pair": self._build_volume_adjusted_mp4_wav_pair,
                }
                rv = askchoice_media_preview(
                    "确认视频与试听音量",
                    [bn],
                    dn,
                    self.root,
                    **pv2,
                )
                if not rv:
                    return None
                _, temp_adj_mp4, temp_adj_wav = rv
            if media_final.lower().endswith(".mp4"):
                if temp_adj_mp4 is None or temp_adj_wav is None:
                    messagebox.showerror(
                        "错误",
                        "内部错误：未取得音量处理后的临时视频/音频。",
                        parent=self.root,
                    )
                    return None
        else:
            matching = _download_folder_list_matching_suffixes(download_path, suffixes)
            if matching:
                r = askchoice_media_preview(title_proj, matching, download_path, self.root, **pv_kw)
                if not r:
                    return None
                if single_mp4_only:
                    fn, temp_adj_mp4, temp_adj_wav = _unpack_mp4_pick(r)
                    media_final = os.path.join(download_path, fn)
                else:
                    bn = r
                    media_final = os.path.join(download_path, bn)
                if (
                    media_final.lower().endswith(".mp4")
                    and not single_mp4_only
                    and (temp_adj_mp4 is None or temp_adj_wav is None)
                ):
                    dn = os.path.dirname(media_final)
                    pv2 = {
                        "use_mp4_video_preview": True,
                        "build_volume_adjusted_pair": self._build_volume_adjusted_mp4_wav_pair,
                    }
                    rv = askchoice_media_preview(
                        "确认视频与试听音量",
                        [bn],
                        dn,
                        self.root,
                        **pv2,
                    )
                    if not rv:
                        return None
                    _, temp_adj_mp4, temp_adj_wav = rv
                if media_final.lower().endswith(".mp4"):
                    if temp_adj_mp4 is None or temp_adj_wav is None:
                        messagebox.showerror(
                            "错误",
                            "内部错误：未取得音量处理后的临时视频/音频。",
                            parent=self.root,
                        )
                        return None
            else:
                star_patterns = " ".join(f"*{s}" for s in suffixes)
                ftypes = [("所选格式", star_patterns)] + [(s.upper().lstrip("."), f"*{s}") for s in suffixes]
                media_path = filedialog.askopenfilename(
                    title="从磁盘选择文件",
                    initialdir=_user_downloads_folder()
                    if os.path.isdir(_user_downloads_folder())
                    else download_path,
                    filetypes=ftypes,
                )
                if not media_path:
                    return None
                low = media_path.lower()
                if not any(low.endswith(s) for s in suffixes):
                    messagebox.showerror("错误", "所选文件扩展名不匹配。", parent=self.root)
                    return None
                if radios and not picked_radio:
                    picked_radio = self._ask_radio_choice(radios[0], radios[1])
                    if not picked_radio:
                        return None
                media_final = media_path
                rename_dest = os.path.join(
                    download_path,
                    f'{(picked_radio or track_rename_key)}_{sid}_{datetime.now().strftime("%H%M%S")}{os.path.splitext(media_final)[1].lower()}',
                )
                try:
                    shutil.copy2(media_final, rename_dest)
                except OSError:
                    shutil.copy(media_final, rename_dest)
                media_final = rename_dest
                if media_final.lower().endswith(".mp4"):
                    dn = os.path.dirname(media_final)
                    bn = os.path.basename(media_final)
                    pv2 = {
                        "use_mp4_video_preview": True,
                        "build_volume_adjusted_pair": self._build_volume_adjusted_mp4_wav_pair,
                    }
                    rv = askchoice_media_preview(
                        "确认视频与试听音量",
                        [bn],
                        dn,
                        self.root,
                        **pv2,
                    )
                    if not rv:
                        return None
                    _, temp_adj_mp4, temp_adj_wav = rv

        lowf = media_final.lower()
        if lowf.endswith((".mp3", ".wav")):
            return {"final_path": media_final, "temp_adj_mp4": None, "temp_adj_wav": None}

        if lowf.endswith(".mp4"):
            if temp_adj_mp4 is None or temp_adj_wav is None:
                messagebox.showerror(
                    "错误",
                    "内部错误：未取得音量处理后的临时视频/音频。",
                    parent=self.root,
                )
                return None
            return {
                "final_path": media_final,
                "temp_adj_mp4": temp_adj_mp4,
                "temp_adj_wav": temp_adj_wav,
                "place": place_mode,
                "track": picked_radio,
            }

        messagebox.showerror("错误", f"暂不支持的格式：{media_final}", parent=self.root)
        return None

    _CLIP_DEST_OPTIONS = (
        ("clip", "Clip"),
        ("narration", "旁白"),
        ("zero", "Zero"),
    )

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
            self._blend_audio_across_scenes(scene, mp4, audio)
            return
        if audio:
            if audio.get("use") == "mix":
                mp4, mixed_wav = self._blend_audio_into_video(mp4, audio)
            else:
                mp4, mixed_wav = self._mix_audio_onto_video(mp4, audio)
            if mixed_wav:
                wav = mixed_wav
        dest = (pick.get("dest") or "clip").strip() or "clip"
        if dest == "clip":
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
                scene, mp4, wav, pick.get("radio") or "keep", dest, track_status="ENH2",
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
                dest,
                dest,
            )
            if res:
                self._apply_download_video_result(res, dest)
            return
        refresh_scene_media(scene, dest, ".mp4", mp4)
        if wav and os.path.isfile(wav):
            refresh_scene_media(scene, dest + "_audio", ".wav", wav, True)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, "片段", "已写回这一场。")

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
        landscape = int(project_manager.PROJECT_CONFIG.get("video_width", 1920)) > int(
            project_manager.PROJECT_CONFIG.get("video_height", 1080)
        )
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

    def _apply_download_video_result(self, res: dict, track: str) -> None:
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

    def choose_import_video(self) -> None:
        """导入视频。默认先看项目 media/input_video，也可以改到下载或频道。"""
        project_folder, project_files = self._project_video_source()
        download_folder, download_files = self._download_mp4_source()
        channel_folder, channel_files = self._channel_mp4_source()
        video_actions = [
            ("replace", "替换"),
        ]
        sources = [
            {
                "key": "project",
                "label": "项目",
                "folder": project_folder,
                "choices": project_files,
                "radios": None,
                "confirm_actions": video_actions,
            },
            {
                "key": "download",
                "label": "下载",
                "folder": download_folder,
                "choices": download_files,
                "radios": None,
                "confirm_actions": video_actions,
            },
            {
                "key": "channel",
                "label": "频道",
                "folder": channel_folder,
                "choices": channel_files,
                "radios": ("声音", [("keep", "原声"), ("replace_speed", "配声")]),
                "confirm_actions": [("replace", "替换")],
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

    def _apply_reviewed_segments_to_current_clip(self, segments: list) -> None:
        root = self.root
        scene_index = self.current_scene_index

        def work() -> None:
            err = ""
            out = ""
            temps: list[str] = []
            try:
                ff = self.workflow.ffmpeg_processor
                pieces: list[str] = []
                for seg in segments:
                    src = (seg.get("path") or "").strip()
                    if not src or not os.path.isfile(src):
                        raise RuntimeError(f"片段不在了：{os.path.basename(src) or src}")
                    start = float(seg.get("start") or 0.0)
                    end = float(seg.get("end") or 0.0)
                    speed = float(seg.get("speed") or 1.0)
                    if end <= start:
                        raise RuntimeError(f"区间无效：{os.path.basename(src)}")
                    piece = ff.trim_video(src, start, end, volume=1.0, speed=speed)
                    if not piece or not os.path.isfile(piece):
                        raise RuntimeError(f"处理失败：{os.path.basename(src)}")
                    temps.append(piece)
                    pieces.append(piece)
                if len(pieces) == 1:
                    out = pieces[0]
                else:
                    out = ff.concat_videos(pieces, True) or ""
                    if out:
                        temps.append(out)
                if not out or not os.path.isfile(out):
                    raise RuntimeError("没有拼出这一场的视频。")
            except Exception as exc:
                err = str(exc)

            def done() -> None:
                if err or not out:
                    messagebox.showerror("编辑当前片段", err or "没有写回这一场。", parent=root)
                    return
                scene = self.workflow.get_scene_by_index(scene_index)
                if not scene:
                    messagebox.showerror("编辑当前片段", "这一场已经不在了。", parent=root)
                    return
                refresh_scene_media(scene, "clip", ".mp4", out)
                self.workflow.save_scenes_to_json()
                self.refresh_gui_scenes()
                show_auto_close_popup(root, "编辑当前片段", "已写回这一场。")

            root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def choose_from_download(self, track, media_post=".mp4", radios=None):
        res = self._pick_media_from_download_to_project_folder(
            media_post,
            track_rename_key=track,
            confirm_actions=[
                ("replace", "替换"),
                ("prepend", "前加"),
                ("append", "后加"),
            ],
            radios=radios,
        )
        if not res:
            return
        self._apply_download_video_result(res, track)

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
    ):
        """
        对单个场景：TTS 生成音频并 mux 到指定轨道视频（clip / narration）。
        用于「生场音频」单镜流程，以及本故事批量生主轨音频。
        """
        text = (content or "").strip()
        if not text:
            if show_error_messages:
                messagebox.showwarning("警告", "讲话/旁白内容为空", parent=self.root)
            return False
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


    @staticmethod
    def _strip_narrator_export_markup(raw: str) -> str:
        """
        从 Story Content 里为 NotebookLM 拼好的长串中还原讲员简选项（如 woman/qin/chinese）。
        若 REMIX 等把带「Narrator - … - pop up…」的导出写回场景，再导出会层层套娃，需在展示与导出前剥掉。
        """
        if raw is None:
            return ""
        s = str(raw).strip()
        if not s:
            return ""
        sfx_not_show = " - not show in the screen, only speaking"
        sfx_popup = (
            " - pop up in the screen (if has previous scene, try keep its image back to background, "
            "while actor (if has) in previous image not speaking)"
        )
        while True:
            if s.endswith(sfx_popup):
                s = s[: -len(sfx_popup)].rstrip()
            elif s.endswith(sfx_not_show):
                s = s[: -len(sfx_not_show)].rstrip()
            else:
                break
        prefix = "Narrator - "
        while s.startswith(prefix):
            s = s[len(prefix) :].strip()
        if " | " in s:
            s = s.rsplit(" | ", 1)[0].strip()
        return s.strip()

    def choose_clip_audio_scope(self):
        """生主轨 clip 音频：`askchoice` 四选一（范围 × 音源）。后台线程执行。"""
        clip_choices = [
            (
                ("single", "speaker"),
                "仅当前场景 · 人物 + 对白（actor + speaking）",
            ),
            (
                ("single", "narrator"),
                "仅当前场景 · 讲员 + 旁白（narrator + voiceover）",
            ),
            (
                ("story", "speaker"),
                "本故事全部 · 各镜 人物 + 对白",
            ),
            (
                ("story", "narrator"),
                "本故事全部 · 各镜 讲员 + 旁白",
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
        if scope not in ("single", "story") or source_mode not in ("speaker", "narrator"):
            return
        do_all_story = scope == "story"

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

                if not do_all_story:
                    try:
                        out = self.regenerate_story_clip_for_scene(
                            scene_anchor, source_mode=source_mode
                        )
                    except Exception as e:
                        root.after(
                            0,
                            lambda: (
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

                ok, skipped, err = self._run_story_clip_audio_all(scene_anchor, source_mode=source_mode)

                def finish_batch():
                    clear_busy()
                    self.workflow.save_scenes_to_json()
                    self.refresh_gui_scenes()
                    if err:
                        messagebox.showerror("本故事生音频", err, parent=root)
                        return
                    story_scenes = self.workflow.scenes_in_story(scene_anchor)
                    nstory = len(story_scenes) if story_scenes else 0
                    tail = "\n".join(skipped[:12])
                    if len(skipped) > 12:
                        tail += f"\n… 另有 {len(skipped) - 12} 条"
                    src_note = "人物+对白" if source_mode == "speaker" else "讲员+旁白"
                    msg = f"完成（{src_note}）：成功 {ok} / {nstory} 个场景。"
                    if skipped:
                        msg += f"\n\n跳过或失败 ({len(skipped)}):\n{tail}"
                    messagebox.showinfo("本故事生音频", msg, parent=root)

                root.after(0, finish_batch)
            except Exception as e:
                root.after(
                    0,
                    lambda: (
                        clear_busy(),
                        messagebox.showerror("Clip 音频", f"任务异常：{e}", parent=root),
                    ),
                )

        threading.Thread(target=work, daemon=True).start()


    def regenerate_story_clip_for_scene(self, scene, source_mode: str = "speaker"):
        """单场景：TTS 主轨 clip 音频（无审核对话框）。

        source_mode:
          - ``speaker``: actor + speaking（人物口型/对白轨）
          - ``narrator``: 讲员 + voiceover（主持旁白）

        返回：'ok' 成功，'fail' TTS/合成失败，'no_content' / 'no_speaker' 跳过，'no_scene' 无场景。"""
        if not scene:
            return "no_scene"
        if source_mode == "narrator":
            speaker = project_manager.actor_host_name(scene.get("actor") or "") or project_manager.project_narrator()
            raw = (scene.get("voiceover") or "").strip()
        else:
            speaker = project_manager.actor_entries(scene.get("actor") or "")
            speaker = next((row["body"] for row in speaker if row["role"] == "person"), "")
            raw = (scene.get("speaking") or "").strip()
        content = raw.replace("——", ", ").replace("—", ", ")
        if not content:
            return "no_content"
        if not speaker:
            return "no_speaker"
        speaker = project_manager.resolve_actor_voice(speaker) or speaker
        ok = self.apply_tts_audio_to_scene_track(
            scene,
            "clip",
            speaker,
            content,
            track_label="Clip",
            save_scenes=False,
            refresh_gui=False,
            show_success_message=False,
            show_error_messages=False,
        )
        return "ok" if ok else "fail"

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



    def create_video_tab(self):
        """创建视频生成标签页"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="生成视频--")
        
        # 主内容区域
        main_content = ttk.Frame(tab)
        main_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 左侧：视频预览区域
        self.secondary_track_after_id = "narration"
        self.video_frame = ttk.LabelFrame(main_content, text=f"预览 - secondary ({self.secondary_track_after_id})", padding=10)
        self.video_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        # 设置左侧面板的最大宽度，为右侧面板留出空间
        self.video_frame.configure(width=1600)
        self.video_frame.pack_propagate(False)

        # 创建水平布局框架来并排显示图像标签和视频画布
        preview_frame = ttk.Frame(self.video_frame)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧区域：背景轨道和旁白轨道（减少宽度给video_canvas更多空间）
        left_frame = ttk.Frame(preview_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        # 设置左侧框架的宽度，为video_canvas留出更多空间
        left_frame.configure(width=640)
        left_frame.pack_propagate(False)
        
        # 图片预览区域（原zero位置）
        images_preview_frame = ttk.LabelFrame(left_frame, text="图片预览 (拖放 / 单击复制 / 右键双击放入)", padding=5)
        images_preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建3个图片预览canvas (clip_image, narration_image, zero_image)
        images_container = ttk.Frame(images_preview_frame)
        images_container.pack(fill=tk.BOTH, expand=True)
        
        # Top: clip_image
        clip_img_frame = ttk.Frame(images_container)
        clip_img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2))
        ttk.Label(clip_img_frame, text="Clip", anchor=tk.CENTER).pack()
        clip_canvas_container = ttk.Frame(clip_img_frame)
        clip_canvas_container.pack(fill=tk.BOTH, expand=True)

        self.clip_image_canvas = tk.Canvas(clip_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='blue')
        self.clip_image_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 1))
        self.clip_image_canvas.create_text(75, 37, text="Clip\nImage", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.clip_image_canvas.drop_target_register(DND_FILES)
        self.clip_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'clip_image'))
        self.clip_image_canvas.bind('<Control-Button-1>', lambda e: self.choose_from_channel_media("clip_image", "keep"))

        self.clip_image_last_canvas = tk.Canvas(clip_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='blue')
        self.clip_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.clip_image_last_canvas.create_text(75, 37, text="Clip\nLast", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.clip_image_last_canvas.drop_target_register(DND_FILES)
        self.clip_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'clip_image_last'))

        # Top: narration_image
        narration_img_frame = ttk.Frame(images_container)
        narration_img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 0))
        ttk.Label(narration_img_frame, text="Narration", anchor=tk.CENTER).pack()
        narration_canvas_container = ttk.Frame(narration_img_frame)
        narration_canvas_container.pack(fill=tk.BOTH, expand=True)

        self.narration_image_canvas = tk.Canvas(narration_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='green')
        self.narration_image_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 1))
        self.narration_image_canvas.create_text(75, 37, text="Narration\nImage", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.narration_image_canvas.drop_target_register(DND_FILES)
        self.narration_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, "narration_image"))
        self.narration_image_canvas.bind('<Control-Button-1>', lambda e: self.choose_from_channel_media("narration_image", "image"))

        self.narration_image_last_canvas = tk.Canvas(narration_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='green')
        self.narration_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.narration_image_last_canvas.create_text(75, 37, text="Narration\nLast", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.narration_image_last_canvas.drop_target_register(DND_FILES)
        self.narration_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, "narration_image_last"))
        

        # Top: zero_image
        zero_img_frame = ttk.Frame(images_container)
        zero_img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        ttk.Label(zero_img_frame, text="Zero", anchor=tk.CENTER).pack()
        zero_canvas_container = ttk.Frame(zero_img_frame)
        zero_canvas_container.pack(fill=tk.BOTH, expand=True)

        self.zero_image_canvas = tk.Canvas(zero_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='orange')
        self.zero_image_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 1))
        self.zero_image_canvas.create_text(75, 37, text="Zero\nImage", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.zero_image_canvas.drop_target_register(DND_FILES)
        self.zero_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'zero_image'))
        self.zero_image_canvas.bind('<Control-Button-1>', lambda e: self.choose_from_channel_media("zero_image", "image"))

        self.zero_image_last_canvas = tk.Canvas(zero_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='orange')
        self.zero_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.zero_image_last_canvas.create_text(75, 37, text="Zero\nLast", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.zero_image_last_canvas.drop_target_register(DND_FILES)
        self.zero_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'zero_image_last'))

        for _img_canvas, _img_type in (
            (self.clip_image_canvas, "clip_image"),
            (self.clip_image_last_canvas, "clip_image_last"),
            (self.narration_image_canvas, "narration_image"),
            (self.narration_image_last_canvas, "narration_image_last"),
            (self.zero_image_canvas, "zero_image"),
            (self.zero_image_last_canvas, "zero_image_last"),
        ):
            _img_canvas.bind(
                "<Button-1>",
                lambda e, t=_img_type: self.on_image_canvas_click(e, t),
            )
            _img_canvas.bind(
                "<Double-Button-1>",
                lambda e, t=_img_type: self.on_image_canvas_double_click(e, t),
            )
            _img_canvas.bind(
                "<Double-Button-3>",
                lambda e, t=_img_type: self.on_image_canvas_paste_from_clipboard(e, t),
            )

        # 视频轨道预览区域 - 使用Tab控件（包含narration和zero）
        track_video_frame = ttk.LabelFrame(left_frame, text="轨道视频预览", padding=5)
        track_video_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建Notebook (Tab控件)
        self.narration_notebook = ttk.Notebook(track_video_frame)
        self.narration_notebook.pack(fill=tk.BOTH, expand=True)
        
        # === Tab 1: 完整旁白轨道 ===
        tab_full_narration = ttk.Frame(self.narration_notebook)
        self.narration_notebook.add(tab_full_narration, text="完整视频")
        
        # 旁白轨道视频画布
        self.secondary_track_canvas = tk.Canvas(tab_full_narration, bg='black', width=360, height=180)
        self.secondary_track_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # 旁白轨道提示文本
        self.secondary_track_canvas.create_text(160, 90, text="旁白轨道视频预览\n选择视频后播放显示", 
                                            fill="gray", font=("Arial", 10), justify=tk.CENTER, tags="hint")
        
        # 旁白轨道时间滑块
        self.secondary_track_scale_var = tk.DoubleVar(value=0.0)
        self.secondary_track_scale = tk.Scale(tab_full_narration, 
                                              from_=0.0, 
                                              to=1.0, 
                                              orient=tk.HORIZONTAL,
                                              variable=self.secondary_track_scale_var,
                                              command=self.on_secondary_track_scale_changed,
                                              length=360,
                                              resolution=0.1)
        self.secondary_track_scale.pack(fill=tk.X, padx=2, pady=(0, 2))
        self.secondary_track_scale.config(state=tk.DISABLED)  # 初始状态禁用
        
        # === Tab 2: 画中画 Left & Right ===
        tab_pip_lr = ttk.Frame(self.narration_notebook)
        self.narration_notebook.add(tab_pip_lr, text="画中画L/R")
        
        # 创建左右并排的画布框架
        pip_lr_frame = ttk.Frame(tab_pip_lr)
        pip_lr_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # 左侧视频画布
        left_canvas_frame = ttk.Frame(pip_lr_frame)
        left_canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2))
        ttk.Label(left_canvas_frame, text="Left", anchor=tk.CENTER).pack()
        self.pip_left_canvas = tk.Canvas(left_canvas_frame, bg='black', width=175, height=180)
        self.pip_left_canvas.pack(fill=tk.BOTH, expand=True)
        self.pip_left_canvas.create_text(77, 80, text="Left\n画中画左侧", fill="gray", font=("Arial", 9), justify=tk.CENTER, tags="hint")
        
        # 右侧视频画布
        right_canvas_frame = ttk.Frame(pip_lr_frame)
        right_canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 0))
        ttk.Label(right_canvas_frame, text="Right", anchor=tk.CENTER).pack()
        self.pip_right_canvas = tk.Canvas(right_canvas_frame, bg='black', width=175, height=180)
        self.pip_right_canvas.pack(fill=tk.BOTH, expand=True)
        self.pip_right_canvas.create_text(77, 80, text="Right\n画中画右侧", fill="gray", font=("Arial", 9), justify=tk.CENTER, tags="hint")
        
        # 轨道视频控制器（在预览区域下方，所有tab共用）
        self.track_frame = ttk.Frame(left_frame)
        self.track_frame.pack(fill=tk.X, pady=5)
        
        # 旁白轨道播放按钮
        self.track_play_button = ttk.Button(self.track_frame, text="▶", command=self.toggle_track_playback,width=3)
        self.track_play_button.pack(side=tk.LEFT, padx=1)

        # add field to display current playing time / duration of narration track, and 2 buttons to move forward and backward sec
        self.track_time_label = ttk.Label(self.track_frame, text="00:00/00:00")
        self.track_time_label.pack(side=tk.LEFT, padx=(1, 10))
        
        #ttk.Button(self.secondary_track_frame, text="◀", command=self.move_secondary_track_backward, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.secondary_track_frame, text="▶", command=self.move_secondary_track_forward, width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="📺11", command=lambda:self.pip_secondary_track(), width=5).pack(side=tk.LEFT, padx=(1, 10))
        ttk.Button(self.track_frame, text="💫NN", command=lambda:self.choose_secondary_track("narration"), width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.track_frame, text="💫ZZ", command=lambda:self.choose_secondary_track('zero'), width=5).pack(side=tk.LEFT, padx=1)

        # add a button to remove current self.secondary_track (if selected) otherwise disable the button
        # if self.secondary_track is selected, warning user to remove which track ,  then if user confirm, remove this track (video plus audio field) from current scene
        self.remove_track_btn = ttk.Button(self.track_frame, text="🗑", command=self.remove_secondary_track, width=3)
        self.remove_track_btn.pack(side=tk.LEFT, padx=1)
        self.root.after(100, self._update_remove_track_btn_state)  # 延迟设置初始状态

        


        # 初始化所有轨道播放相关变量
        # 图片预览引用（防止垃圾回收）
        self._clip_image_photo = None
        self._narration_image_photo = None
        self._zero_image_photo = None
        
        # 绑定tab切换事件
        self.narration_notebook.bind("<<NotebookTabChanged>>", self.on_secondary_track_tab_changed)

        # 右侧区域：视频画布和控制按钮
        right_frame = ttk.Frame(preview_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # 视频预览画布（用于显示视频帧）
        self.video_canvas = tk.Canvas(right_frame, bg='black', height=480)
        self.video_canvas.pack(fill=tk.BOTH, expand=True)
        
        # 添加拖拽提示文本（位置会在canvas配置后动态调整）
        self.video_canvas.create_text(400, 180, text="选择场景后会显示视频预览",
                                    fill="gray", font=("Arial", 12), justify=tk.CENTER, tags="drag_hint")
        
        # 绑定配置事件来动态调整提示文本位置
        self.video_canvas.bind('<Configure>', self.on_video_canvas_configure)

        span_row = ttk.Frame(right_frame)
        span_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(span_row, text="检测", width=5, command=self.detect_speech_spans).pack(side=tk.LEFT, padx=(0, 4))
        self.speech_span_canvas = tk.Canvas(span_row, height=24, bg="#d9d9d9", highlightthickness=1, highlightbackground="#b0b0b0")
        self.speech_span_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._speech_spans = {
            "speaking_start": None,
            "speaking_end": None,
            "voiceover_start": None,
            "voiceover_end": None,
        }
        self._speech_span_duration = 0.0
        self._speech_span_drag = None
        self._preview_playhead = 0.0
        self._span_bar_scene = None
        self._span_press_seek = False
        self._span_press_on_edge = False
        self.speech_span_canvas.bind("<Configure>", lambda _e: self._draw_speech_span_bar())
        self.speech_span_canvas.bind("<ButtonPress-1>", self._speech_span_press)
        self.speech_span_canvas.bind("<B1-Motion>", self._speech_span_drag_move)
        self.speech_span_canvas.bind("<ButtonRelease-1>", self._speech_span_release)
        self.speech_span_canvas.bind("<Double-Button-1>", self._speech_span_double)

        span_info = ttk.Frame(right_frame)
        span_info.pack(fill=tk.X, pady=(2, 0))
        self.speech_span_label = ttk.Label(span_info, text="")
        self.speech_span_label.pack(side=tk.LEFT, padx=(2, 8))
        self.video_progress_label = ttk.Label(span_info, text="现在 00:00.00 / 共 00:00.00")
        self.video_progress_label.pack(side=tk.RIGHT, padx=(8, 2))
        
        # 视频控制按钮框架（在视频画布下方）
        video_control_frame = ttk.Frame(right_frame)
        video_control_frame.pack(fill=tk.X, pady=5)
        
        # 播放/暂停按钮
        self.video_play_button = ttk.Button(video_control_frame, text="▶", 
                                          command=self.toggle_video_playback, width=3)
        self.video_play_button.pack(side=tk.LEFT, padx=1)
        
        # 停止按钮
        self.video_stop_button = ttk.Button(video_control_frame, text="⏹", 
                                          command=self.stop_video_playback, width=3)
        self.video_stop_button.pack(side=tk.LEFT, padx=1)

        ttk.Button(video_control_frame, text="<", command=lambda: self.move_video(-0.25), width=2).pack(side=tk.LEFT, padx=0)
        self.playing_delta_label = ttk.Label(video_control_frame, text="0.0s", width=4)
        self.playing_delta_label.pack(side=tk.LEFT, padx=0)
        ttk.Button(video_control_frame, text=">", command=lambda: self.move_video(0.25), width=2).pack(side=tk.LEFT, padx=0)

        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        self.btn_scene_edit = ttk.Button(
            video_control_frame, text="场景分合", command=self._ask_scene_structure, width=8
        )
        self.btn_scene_edit.pack(side=tk.LEFT, padx=1)
        self.btn_playhead_split = ttk.Button(
            video_control_frame, text="分界处理", command=self._ask_playhead_split, width=8
        )
        self.btn_playhead_split.pack(side=tk.LEFT, padx=1)

        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        self.btn_video_treat = ttk.Button(
            video_control_frame, text="视频效果", command=self._ask_video_treatment, width=8
        )
        self.btn_video_treat.pack(side=tk.LEFT, padx=1)
        self.btn_overlay = ttk.Button(
            video_control_frame, text="图文叠加", command=self._ask_clip_overlay, width=8
        )
        self.btn_overlay.pack(side=tk.LEFT, padx=1)

        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(
            video_control_frame,
            text="导入片段",
            width=8,
            command=self.choose_import_video,
        ).pack(side=tk.LEFT, padx=1)
        ttk.Button(
            video_control_frame,
            text="编辑片段",
            width=8,
            command=self._edit_current_scene_clip,
        ).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="⏱", command=self.track_recover, width=3).pack(side=tk.RIGHT, padx=(8, 2))

        #ttk.Button(video_control_frame, text="背起", command=self.zero_start, width=5).pack(side=tk.LEFT, padx=1)
        #ttk.Button(video_control_frame, text="背继", command=self.zero_continue, width=5).pack(side=tk.LEFT, padx=1)
        #ttk.Button(video_control_frame, text="背终", command=self.zero_end, width=5).pack(side=tk.LEFT, padx=1)

        # 初始化视频进度显示（时间在时间条下面那一行，不放在按钮中间）
        self.update_video_progress_display()
        
        # 视频播放状态
        self.video_playing = False
        self.video_cap = None
        self.video_after_id = None
        self.video_start_time = None
        self.video_pause_time = None  # 记录暂停时的累计播放时间
        
        # 右侧：最上是 AI 生成，然后是这一集，再下面是这一场
        right_panel = ttk.Frame(main_content, width=700)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_panel.pack_propagate(False)

        ai_tools_frame = ttk.LabelFrame(right_panel, text="全场内容", padding=(8, 2))
        ai_tools_frame.pack(side=tk.TOP, fill=tk.X)
        self._ai_tools_frame = ai_tools_frame
        look_row1 = ttk.Frame(ai_tools_frame)
        look_row1.pack(side=tk.TOP, fill=tk.X)
        look_row2 = ttk.Frame(ai_tools_frame)
        look_row2.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))
        ttk.Label(look_row1, text="语言").pack(side=tk.LEFT)
        self.shared_language = ttk.Combobox(
            look_row1, width=4, values=list(config.LANGUAGES.keys()), state="readonly"
        )
        self.shared_language.pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(look_row1, text="字体").pack(side=tk.LEFT)
        self.scene_language = ttk.Combobox(
            look_row1, width=4, values=list(config.FONT_LIST.keys()), state="readonly"
        )
        self.scene_language.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Separator(look_row1, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=22)
        ttk.Label(look_row1, text="地域").pack(side=tk.LEFT)
        self.setting_region = ttk.Combobox(
            look_row1,
            width=7,
            values=list(config_prompt.SETTING_PLACES.keys()),
            state="readonly",
        )
        self.setting_region.pack(side=tk.LEFT, padx=(4, 6))
        ttk.Label(look_row1, text="时代").pack(side=tk.LEFT)
        self.setting_era = ttk.Combobox(look_row1, width=8, state="readonly")
        self.setting_era.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(look_row2, text="选择").pack(side=tk.LEFT, padx=(0, 4))
        self._narrator_avatar_btn = ttk.Button(
            look_row2,
            text="不出现",
            width=8,
            command=self.review_project_narrator,
        )
        self._narrator_avatar_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.scene_visual_style = ttk.Combobox(
            look_row2,
            width=16,
            values=list(config.VISUAL_STYLE_OPTIONS),
            state="readonly",
        )
        self.scene_visual_style.pack(side=tk.LEFT, padx=(4, 4))
        self.scene_dialogue_mode = ttk.Combobox(
            look_row2,
            width=12,
            values=list(config.DIALOGUE_MODE_OPTIONS),
            state="readonly",
        )
        self.scene_dialogue_mode.pack(side=tk.LEFT, padx=(0, 0))

        episode_gap = ttk.Frame(right_panel, height=24)
        episode_gap.pack(side=tk.TOP)
        episode_gap.pack_propagate(False)
        episode_tools_frame = ttk.LabelFrame(right_panel, text="本集内容", padding=(8, 2))
        episode_tools_frame.pack(side=tk.TOP, fill=tk.X)
        episode_btn_row = ttk.Frame(episode_tools_frame)
        episode_btn_row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(episode_btn_row, text="延长").pack(side=tk.LEFT)
        self.extension_var = tk.StringVar(value="0")
        self.extension_values = ["0", "0.2", "0.3", "0.5", "1.0"]
        self.extension_combobox = ttk.Combobox(
            episode_btn_row,
            textvariable=self.extension_var,
            values=self.extension_values,
            state="readonly",
            width=5,
        )
        self.extension_combobox.pack(side=tk.LEFT, padx=(4, 0))
        self.extension_combobox.bind("<<ComboboxSelected>>", lambda e: self._on_extension_change())
        ttk.Separator(episode_btn_row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=22)
        ttk.Button(
            episode_btn_row,
            text="拷贝提示",
            width=8,
            command=self.copy_episode_prompt,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            episode_btn_row,
            text="拷贝PDF",
            width=8,
            command=self.copy_current_episode_pdf,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            episode_btn_row,
            text="拆成新集",
            width=8,
            command=self.split_current_group,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            episode_btn_row,
            text="贴回本集",
            width=8,
            command=self.paste_episode_scenes,
        ).pack(side=tk.LEFT)

        scene_gap = ttk.Frame(right_panel, height=24)
        scene_gap.pack(side=tk.TOP)
        scene_gap.pack_propagate(False)
        self.video_edit_frame = ttk.LabelFrame(right_panel, text="本场内容", padding=10)
        self.video_edit_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.video_edit_frame.columnconfigure(1, weight=1)

        row_number = 1

        scene_text_row = ttk.Frame(self.video_edit_frame)
        scene_text_row.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        self._scene_speech_btn = ttk.Button(
            scene_text_row,
            text="场景变换",
            width=8,
            command=self._ask_scene_speech_transform,
        )
        self._scene_speech_btn.pack(side=tk.LEFT)
        self._scene_split_btn = ttk.Button(
            scene_text_row,
            text="场景拆分",
            width=8,
            command=self._ask_scene_split,
        )
        self._scene_split_btn.pack(side=tk.LEFT, padx=(4, 0))
        self.btn_add_scene = ttk.Button(
            scene_text_row,
            text="插入过渡",
            width=8,
            command=self.add_scene_insert,
        )
        self.btn_add_scene.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Separator(scene_text_row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=22)
        ttk.Button(
            scene_text_row,
            text="对话互换",
            width=8,
            command=self.swap_speaking_voiceover,
        ).pack(side=tk.LEFT)
        ttk.Separator(scene_text_row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=22)
        self._nb_picture_btn = ttk.Button(
            scene_text_row,
            text="图片提示",
            width=8,
            command=self._open_picture_prompt_flow,
        )
        self._nb_picture_btn.pack(side=tk.LEFT)
        self._nb_story_video_btn = ttk.Button(
            scene_text_row,
            text="视频提示",
            width=8,
            command=self._open_video_prompt_flow,
        )
        self._nb_story_video_btn.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(
            scene_text_row,
            text="生场音频",
            width=8,
            command=self.choose_clip_audio_scope,
        ).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(self.video_edit_frame, text="讲话:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        # Tk Text 内置撤销/重做：Ctrl+Z 撤销，Ctrl+Y 重做（Windows 常见）；maxundo=0 为不限制深度
        self.scene_speaking = scrolledtext.ScrolledText(
            self.video_edit_frame,
            width=20,
            height=5,
            undo=True,
            maxundo=0,
            font=("Arial", 16),
            wrap=tk.WORD,
        )
        self.scene_speaking.grid(row=row_number, column=1, sticky=tk.EW, padx=5, pady=2)
        self.scene_speaking.bind(
            "<Double-1>",
            lambda event: self.on_scene_text_review("speaking", event, title="审阅文案 — 讲话"),
        )
        row_number += 1

        ttk.Label(self.video_edit_frame, text="人物:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self._actor_text = ""
        self.scene_actor_row = ttk.Frame(self.video_edit_frame)
        self.scene_actor_row.grid(row=row_number, column=1, sticky=tk.EW, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="视觉:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_visual = scrolledtext.ScrolledText(
            self.video_edit_frame, width=20, height=1, undo=True, maxundo=0, wrap=tk.WORD
        )
        self.scene_visual.grid(row=row_number, column=1, sticky=tk.EW, padx=5, pady=2)
        self.scene_visual.bind(
            "<Double-1>",
            lambda event: self.on_scene_text_review("visual", event, title="审阅文案 — 视觉"),
        )
        self.scene_visual.bind("<Double-3>", self.on_scene_voiceover_image_action_menu)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="旁白:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_voiceover = scrolledtext.ScrolledText(
            self.video_edit_frame, width=20, height=5, undo=True, maxundo=0, wrap=tk.WORD
        )
        self.scene_voiceover.grid(row=row_number, column=1, sticky=tk.EW, padx=5, pady=2)
        self.scene_voiceover.bind(
            "<Double-1>",
            lambda event: self.on_scene_text_review("voiceover", event, title="审阅文案 — 旁白"),
        )
        row_number += 1

        _caption_lbl = ttk.Label(self.video_edit_frame, text="字幕:")
        _caption_lbl.grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_caption = scrolledtext.ScrolledText(
            self.video_edit_frame, width=20, height=1, undo=True, maxundo=0, wrap=tk.WORD
        )
        self.scene_caption.grid(row=row_number, column=1, sticky=tk.EW, padx=5, pady=2)
        self.scene_caption.bind(
            "<Double-1>",
            lambda event: self.on_scene_text_review(
                "caption",
                event,
                title="审阅文案 — 字幕",
                source_field="speaking",
                remix_system_prompt=config_prompt.SCREEN_CORE_PROMPT,
            ),
        )
        row_number += 1

        track_tools_frame = ttk.Frame(self.video_edit_frame)
        track_tools_frame.grid(row=row_number, column=0, columnspan=2, sticky=tk.W + tk.E, pady=(8, 2))
        row_number += 1
        # 主动画 / 次动画 / 增主轨 / WAN（生场视频）已从界面拿掉。
        # sd_processor 里的生成和增强代码还在，见 utility/sd_image_processor.py。
        self.clip_animate = tk.StringVar(value="")
        ttk.Label(
            track_tools_frame,
            text="主动画、次动画、增主轨、WAN（生场视频）已停用。sd_processor 里的生成和增强代码还留着，界面上先不接。",
            wraplength=640,
        ).pack(side=tk.LEFT)

        #ttk.Label(self.video_edit_frame, text="摄影:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        #self.scene_cinematography = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        #self.scene_cinematography.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        #row_number += 1

        # 旁白轨道播放状态
        self.secondary_track_playing = False
        self.secondary_track_cap = None
        self.secondary_track_after_id = None
        
        # 旁白轨道音频播放状态
        self.secondary_track_audio_playing = False
        self.secondary_track_audio_start_time = None
        
        # 旁白轨道暂停位置
        self.secondary_track_paused_time = None
        self.secondary_track_cap = None
        self.secondary_track_after_id = None
        self.secondary_track_start_time = None

        self.secondary_track_playing = False
        self.secondary_track_offset = 0.0
        self.selected_secondary_track = "narration"
        
        # PIP L/R (画中画左右)
        self.pip_lr_playing = False
        self.pip_left_cap = None
        self.pip_right_cap = None
        self.pip_lr_after_id = None
        self.pip_lr_start_time = None
        self.pip_lr_paused_time = None
        
        self.track_time_label.config(text="00:00/00:00")

        # 底部：日志区域
        log_frame = ttk.LabelFrame(tab, text="操作日志", padding=10)
        log_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.video_output = scrolledtext.ScrolledText(log_frame, height=6)
        self.video_output.pack(fill=tk.BOTH, expand=True)
        
        # 绑定配置变化事件
        # 绑定编辑事件
        self.bind_edit_events()
        self.bind_scene_navigation_shortcuts()
        self.bind_config_change_events()


    def log_to_output(self, output_widget, message):
        """向输出控件写入日志信息"""
        if output_widget and hasattr(output_widget, 'insert'):
            timestamp = datetime.now().strftime("%H:%M:%S")
            output_widget.insert(tk.END, f"[{timestamp}] {message}\n")
            output_widget.see(tk.END)
            output_widget.update_idletasks()


    def start_status_update_timer(self):
        """启动状态更新定时器"""
        # 如果已有定时器，先取消
        if self.status_update_timer_id is not None:
            self.root.after_cancel(self.status_update_timer_id)
        
        self.update_status_and_check_completion()
        # 每5秒更新一次状态，并保存定时器ID
        self.status_update_timer_id = self.root.after(5000, self.start_status_update_timer)


    def update_status_and_check_completion(self):
        """更新状态并检查任务完成情况"""
        # 检查是否有新完成的任务
        newly_completed = []
        for task_id, task_info in list(self.tasks.items()):
            if task_info["status"] in ["完成", "失败"] and task_id not in self.last_notified_tasks:
                newly_completed.append((task_id, task_info))
                self.last_notified_tasks.add(task_id)
                
                # 将完成的任务移到完成列表
                self.completed_tasks.append({
                    "id": task_id,
                    "info": task_info.copy(),
                    "completion_time": datetime.now()
                })
        
        # 通知新完成的任务
        for task_id, task_info in newly_completed:
            """通知任务完成"""
            task_type = task_info.get("type", "未知任务")
            task_status = task_info.get("status", "未知状态")
            pid = task_info.get("pid", "")
            
            if task_status == "完成":
                title = "✅ 任务完成"
                message = f"任务类型: {task_type}\n项目ID: {pid}\n状态: 成功完成"
                if "result" in task_info:
                    message += f"\n结果: {task_info['result']}"
            else:
                title = "❌ 任务失败"
                message = f"任务类型: {task_type}\n项目ID: {pid}\n状态: 执行失败"
                if "error" in task_info:
                    message += f"\n错误: {task_info['error']}"
            
            # 显示通知对话框
            messagebox.showinfo(title, message)



        
        # 检查生成的视频（后台持续检查）
        self.check_generated_videos_background()


    def start_video_check_thread(self):
        if not hasattr(self, 'workflow') or self.workflow is None:
            return  # 未选择项目时（如 YT 管理）工作流为空是正常的，静默跳过

        if self.video_check_running:
            print("⚠️ 后台检查线程已在运行")
            return
        
        self.video_check_running = True
        self.video_check_stop_event.clear()
        
        def video_check_loop():
            """单例后台线程的主循环"""
            print("🚀 启动后台视频检查线程")
            
            while not self.video_check_stop_event.is_set():
                try:
                    self._perform_video_check()
                except Exception as e:
                    print(f"❌ 后台检查线程出错: {str(e)}")
                # 出错后等待5秒再继续
                self.video_check_stop_event.wait(5)
            
            print("🛑 后台视频检查线程已停止")
            self.video_check_running = False
        
        # 创建并启动daemon线程
        self.video_check_thread = threading.Thread(target=video_check_loop, daemon=True)
        self.video_check_thread.start()
    

    def stop_video_check_thread(self):
        """停止后台视频检查线程"""
        if self.video_check_running:
            print("🛑 正在停止后台视频检查线程...")
            self.video_check_stop_event.set()
            if self.video_check_thread:
                self.video_check_thread.join(timeout=2)
    

    def _perform_video_check(self):
        """执行视频检查任务（由单例线程调用）"""
        #animate_gen_list = []
        #for scene_index, scene in enumerate(self.workflow.scenes):
        #    #clip_animation = scene.get("clip_animation", "")
        #    #if clip_animation in config_prompt.ANIMATE_SOURCE and clip_animation != "":
        #    scene_name = build_scene_media_prefix(self.workflow.pid, str(scene["id"]), "clip", "", False)
        #    animate_gen_list.append((scene_name, "clip", scene))
        #    #narration_animation = scene.get("narration_animation", "")
        #    #if narration_animation in config_prompt.ANIMATE_SOURCE and narration_animation != "":
        #    scene_name = build_scene_media_prefix(self.workflow.pid, str(scene["id"]), "narration", "", False)
        #    animate_gen_list.append((scene_name, "narration", scene))

        #if animate_gen_list == []:
        #    return
        
        try:
            # 1. 检查 X:\output 中新生成的原始视频（监控逻辑）
            self.media_scanner.scanning("X:\\output")                      # clip_p202512231259_10005_S2V__00003-audio.mp4
            #self.media_scanner.scanning("Z:\\wan_video\\output_mp4")                     # clip_p202512231259_10005_INT_25115141_30__00001.mp4  ~~~ interpolate
            self.media_scanner.scanning("W:\\wan_video\\output_mp4")      # clip_p20251208_10708_ENH_13231028_0_.mp4   clip_p202512231259_10005_EHN_.mp4  ~~~ enhance

            self.workflow.save_scenes_to_json()

        except Exception as e:
            # 忽略单个场景的错误，继续检查其他场景
            print(f"❌ 后台检查线程出错: {str(e)}")
            pass


    def check_generated_videos_background(self):
        """定时器调用此方法，但不再创建新线程（单例线程已在运行）"""
        if not hasattr(self, 'workflow') or self.workflow is None:
            return  # 未选择项目时（如 YT 管理）静默跳过
        # 检查单例线程是否还在运行，如果没有则重启
        if not self.video_check_running or not self.video_check_thread or not self.video_check_thread.is_alive():
            print("⚠️ 检测到后台线程未运行，正在重启...")
            self.start_video_check_thread()
    

    def enhance_clip(self, track:str):
        """已停用。界面上的「增主轨」已去掉。sd_processor.enhance_clip 还留着。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        self.workflow.sd_processor.enhance_clip(self.get_pid(), scene, track, "30")
        self.refresh_gui_scenes()


    def enhance_video(self):
        for scene in self.workflow.scenes:
            self.workflow.sd_processor.enhance_clip(self.get_pid(), scene, "clip", "30")
            self.workflow.sd_processor.enhance_clip(self.get_pid(), scene, "narration", "30")
        self.refresh_gui_scenes()
    

    def publish_video(self):
        lang = getattr(self.workflow, "language", None) or "zh"
        pc = project_manager.PROJECT_CONFIG or {}
        scenes = getattr(self.workflow, "scenes", None) or []

        gui_title = ""
        if hasattr(self, "video_title"):
            gui_title = (self.video_title.get() or "").strip()
        wf_title = (getattr(self.workflow, "title", None) or "").strip()
        ch_name = config.get_channel_config(self.workflow.channel)["channel_name"]
        default_title = ch_name + "：" + (gui_title or wf_title)

        list_row = project_manager.load_video_detail_row_for_config(pc) or {}
        item_summary = (list_row.get("summary") or pc.get("summary") or "")
        analyzed = pc.get("analyzed_content") or list_row.get("analyzed_content") or ""
        review_script = config.read_transcript_text_from_video_detail(list_row)
        flow = ask_publish_metadata_then_schedule(
            self.root,
            language=lang,
            default_title=default_title,
            scene_content_list=scene_content_list_for_publish(
                language=lang,
                project_config=pc,
                workflow_scenes=scenes,
            ),
            analyzed_content=analyzed if isinstance(analyzed, str) else str(analyzed or ""),
            review_script_text=review_script,
            summary_text=item_summary if isinstance(item_summary, str) else str(item_summary or ""),
            poem_text=(
                (pc.get("poem") or "").strip()
                or (
                    (project_manager.load_video_detail_row_for_config(pc) or {}).get(
                        "poem"
                    )
                    or ""
                ).strip()
            ),
            video_detail=list_row or None,
            generate_text_fn=self.llm_api_local.generate_text,
            schedule_dialog_fn=ask_publish_schedule_dialog,
            caption_scenes=scenes,
            metadata_dialog_title="上传视频 — 标题与描述",
        )
        if flow is None:
            return
        conv = config.chinese_convert(flow["title"].replace("\n", " "), lang)
        title_slug = make_safe_file_name(conv.replace("\n", " "), title_length=180)
        mode = flow["mode"]
        publish_at = flow["publish_at"]
        try:
            tg_lines = self.workflow.upload_video(
                title_slug,
                publish_at=publish_at,
                description=flow["description"],
                telegram_title=conv,
            )
        except Exception as e:
            messagebox.showerror("上传失败", str(e), parent=self.root)
            return
        tg_block = ""
        if tg_lines:
            tg_block = "\n\n--- Telegram ---\n" + "\n".join(tg_lines)
        if mode == "scheduled":
            messagebox.showinfo(
                "提示",
                "视频已以「私有 + 定时公开」上传。\n"
                "到点后将按 YouTube 规则自动公开。\n\n"
                "若需「首映 Premiere」或改为不公开列出，请在 YouTube Studio 中调整。"
                + tg_block,
                parent=self.root,
            )
        else:
            msg = "视频发布成功！"
            if vid := (project_manager.PROJECT_CONFIG or {}).get("published_youtube_video_id"):
                msg += f"\nhttps://www.youtube.com/watch?v={vid}"
            messagebox.showinfo("提示", msg + tg_block, parent=self.root)


    def _do_speaking_summarize(self):
        _lang_code = (project_manager.PROJECT_CONFIG or {}).get("language", "tw")
        _lang_name = config.llm_language_label(_lang_code)
        # 
        system_prompt = config_prompt.SPEAKING_SUMMARY_SYSTEM_PROMPT.format(language=_lang_name)
        user_prompt = json.dumps(self.workflow.scenes, ensure_ascii=False)
        try:
            out = self.llm_api.generate_text(system_prompt, user_prompt)
        except Exception as e:
            messagebox.showerror("SUMMARIZE", f"调用模型失败：{e}", parent=self.root)
            return
        # copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(out)
        self.root.update()

        dlg = tk.Toplevel(self.root)
        dlg.title("SUMMARIZE — 摘要（可编辑）")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("720x480")
        dlg.update_idletasks()
        _px = (dlg.winfo_screenwidth() - 720) // 2
        _py = (dlg.winfo_screenheight() - 480) // 2
        dlg.geometry(f"720x480+{_px}+{_py}")

        ttk.Label(
            dlg,
            text="已复制到剪贴板。可编辑后点「保存到故事摘要」，写入这一条列表的 summary。",
            wraplength=680,
        ).pack(anchor="w", padx=12, pady=(12, 6))

        body = scrolledtext.ScrolledText(dlg, wrap=tk.WORD, width=88, height=20, font=("Arial", 10))
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        body.insert("1.0", out)

        btn_f = ttk.Frame(dlg)
        btn_f.pack(fill=tk.X, padx=12, pady=(0, 12))

        def on_save():
            text = body.get("1.0", tk.END).strip()
            if project_manager.PROJECT_CONFIG is None:
                messagebox.showwarning("摘要", "没有打开的故事，写不进去。", parent=dlg)
                return
            project_manager.PROJECT_CONFIG["summary"] = text
            if not save_project_config(parent=dlg):
                messagebox.showwarning("摘要", "没有写进故事列表。", parent=dlg)
                return
            dlg.destroy()
            messagebox.showinfo("摘要", "概述已写入这一条故事的 summary。", parent=self.root)

        def on_cancel():
            dlg.destroy()

        ttk.Button(btn_f, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_f, text="保存到故事摘要", command=on_save).pack(side=tk.RIGHT)

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)


    def _marker_number(self, key: str, count: int):
        pc = project_manager.PROJECT_CONFIG if isinstance(project_manager.PROJECT_CONFIG, dict) else {}
        try:
            n = int(pc.get(key))
        except (TypeError, ValueError):
            return None
        if count <= 0 or n < 1 or n > count:
            return None
        return n

    def _refresh_marker_label(self) -> None:
        label = getattr(self, "marker_label", None)
        if label is None:
            return
        count = len(self.workflow.scenes) if getattr(self, "workflow", None) else 0
        if count <= 0:
            label.config(text="")
            return
        start = self._marker_number("marker_start", count)
        end = self._marker_number("marker_end", count)
        if start and end:
            label.config(text=f"{start}–{end}")
        elif start:
            label.config(text=f"{start}–")
        elif end:
            label.config(text=f"–{end}")
        else:
            label.config(text=f"1–{count}")

    def _set_scene_marker(self, which: str) -> None:
        """开始记下当前场为起点，结束记下当前场为终点。颠倒时把另一头拉到同一场。"""
        pc = project_manager.PROJECT_CONFIG
        if not isinstance(pc, dict) or not getattr(self, "workflow", None):
            return
        count = len(self.workflow.scenes)
        if count <= 0:
            return
        current = self.current_scene_index + 1
        start = self._marker_number("marker_start", count)
        end = self._marker_number("marker_end", count)
        if which == "start":
            start = current
            if end is not None and end < start:
                end = start
        else:
            end = current
            if start is not None and end < start:
                start = end
        if start is None:
            pc.pop("marker_start", None)
        else:
            pc["marker_start"] = start
        if end is None:
            pc.pop("marker_end", None)
        else:
            pc["marker_end"] = end
        save_project_config(parent=self.root)
        self._refresh_marker_label()

    def _clear_scene_markers(self) -> None:
        pc = project_manager.PROJECT_CONFIG
        if not isinstance(pc, dict):
            return
        pc.pop("marker_start", None)
        pc.pop("marker_end", None)
        save_project_config(parent=self.root)
        self._refresh_marker_label()

    def _marker_scene_bounds(self) -> tuple[int, int]:
        """返回要生成的场景下标，含首尾。没标完整时用第一场到最后一场。"""
        count = len(self.workflow.scenes)
        if count <= 0:
            return 0, 0
        start = self._marker_number("marker_start", count)
        end = self._marker_number("marker_end", count)
        if start and end:
            return start - 1, end - 1
        return 0, count - 1

    def play_finalize_video(self):
        """与 magic_workflow.finalize_video 相同的路径规则；用系统默认播放器打开（独立窗口、含声音）。"""
        final_path = config.publish_final_video_path(self.workflow.pid)
        if not os.path.isfile(final_path):
            messagebox.showwarning(
                "Video播放",
                f"未找到最终成片：\n{final_path}\n请先使用「Video生成」导出。",
                parent=self.root,
            )
            return
        try:
            if os.name == "nt":
                os.startfile(os.path.normpath(final_path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", final_path], start_new_session=True)
            else:
                subprocess.Popen(["xdg-open", final_path], start_new_session=True)
        except Exception as e:
            messagebox.showerror("Video播放", f"无法打开播放器：{e}", parent=self.root)

    def run_finalize_video(self):
        picked = askchoice(
            "最终视频生成方式",
            [
                ("plain_zero", "无转场，用ZERO音轨"),
                ("plain", "无转场 (简单拼接)"),
                ("transitions", "带转场"),
                ("transitions_zero", "带转场，用ZERO音轨"),
            ],
            self.root,
        )
        if picked is None:
            return
        _, mode = picked
        if mode == "transitions":
            with_transitions, replace_final_audio_with_zero = True, False
        elif mode == "transitions_zero":
            with_transitions, replace_final_audio_with_zero = True, True
        elif mode == "plain":
            with_transitions, replace_final_audio_with_zero = False, False
        else:
            with_transitions, replace_final_audio_with_zero = False, True

        pid = self.get_pid()
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "video_finalize",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": pid
        }

        def run_task():
            try:
                start, end = self._marker_scene_bounds()
                self.log_to_output(self.video_output, f"视频生成：第 {start + 1}–{end + 1} 场")
                self.workflow.finalize_video(
                    with_transitions,
                    replace_final_audio_with_zero,
                    scene_start=start,
                    scene_end=end,
                )
                self.log_to_output(self.video_output, "✅ 最终视频生成完成！")
                self.tasks[task_id]["status"] = "完成"
                final_path = config.publish_final_video_path(self.workflow.pid)
                self.root.after(0, lambda p=final_path: self._reveal_published_video(p))
            except Exception as e:
                self.log_to_output(self.video_output, f"❌ 最终视频生成失败: {str(e)}")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)

        threading.Thread(target=run_task, daemon=True).start()


    def _cleanup_video_before_switch(self):
        """切换场景前清理视频资源"""
        # 停止视频播放
        if self.video_playing:
            self.stop_video_playback()
        
        # 清理视频捕获对象
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None
        
        # 取消定时器
        if self.video_after_id:
            self.root.after_cancel(self.video_after_id)
            self.video_after_id = None
        
        # 停止音频
        self.stop_audio_playback()
        
        # 重置播放状态
        self.video_playing = False
        self.video_play_button.config(text="▶")
        
        # 更新视频进度显示
        self.update_video_progress_display()
        
        # 清空画布
        self.video_canvas.delete("all")
        
        # 重置视频相关变量
        self.video_start_time = None
        self.video_pause_time = None
        
        # 清理图片引用，防止内存泄漏
        if hasattr(self, 'current_video_frame'):
            self.current_video_frame = None


    def load_video_first_frame(self):
        self._cleanup_video_before_switch()

        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            
        video_path = get_file_path(current_scene, "clip")
        if not video_path:
            return

        if not video_path:
            self.clear_video_preview()
            return
            
        try:
            self.video_canvas.delete("all")
            
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                cap.release()
                self.clear_video_preview()
                return
            
            ret, frame = cap.read()
            cap.release()
            
            if ret and frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                pil_image = Image.fromarray(frame_rgb)
                
                canvas_width = self.video_canvas.winfo_width()
                canvas_height = self.video_canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:  # 确保画布已经初始化
                    pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
                else:
                    pil_image.thumbnail((630, 350), Image.Resampling.LANCZOS)
                
                # 转换为Tkinter可用的格式
                self.current_video_frame = ImageTk.PhotoImage(pil_image)
                
                # 在画布中央显示图像
                self.video_canvas.delete("all")
                canvas_width = self.video_canvas.winfo_width() or 640
                canvas_height = self.video_canvas.winfo_height() or 360
                x = canvas_width // 2
                y = canvas_height // 2
                
                # 确保图像对象存在后再创建画布图像
                if self.current_video_frame:
                    try:
                        self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)
                    except tk.TclError as e:
                        # 如果图像对象无效，重新创建
                        print(f"⚠️ 图像对象无效，重新创建: {e}")
                        self.current_video_frame = ImageTk.PhotoImage(pil_image)
                        self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)
                
                self.video_canvas.create_text(x, y + pil_image.height//2 + 20, 
                                            text="点击 '▶ 播放' 开始播放视频", 
                                            fill="white", font=("Arial", 12))
            else:
                self.clear_video_preview()
                self.log_to_output(self.video_output, f"❌ 无法读取视频第一帧")
                
        except Exception as e:
            self.clear_video_preview()
            self.log_to_output(self.video_output, f"❌ 加载视频预览失败: {str(e)}")


    def clear_video_preview(self):
        """清空视频预览"""
        # 先清理图片引用，防止内存泄漏
        if hasattr(self, 'current_video_frame'):
            self.current_video_frame = None
        
        # 清空画布
        self.video_canvas.delete("all")
        
        # 显示提示文本
        canvas_width = self.video_canvas.winfo_width() or 640
        canvas_height = self.video_canvas.winfo_height() or 360
        x = canvas_width // 2
        y = canvas_height // 2
        
        self.video_canvas.create_text(x, y, text="选择场景后会显示视频预览", fill="white",
                                    font=("Arial", 12), justify=tk.CENTER, tags="no_video_hint")


    def toggle_video_playback(self):
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        video_path = None
        if current_scene:
            video_path = get_file_path(current_scene, "clip")
            
        if not video_path:
            self.log_to_output(self.video_output, "❌ 没有可播放的视频文件")
            return
            
        if self.video_playing:
            self.pause_video()
        else:
            # 如果是从暂停状态恢复，需要特殊处理
            if self.video_cap is not None:
                self.video_playing = True
                self.video_play_button.config(text="⏸")
                # 重新设置开始时间，考虑之前暂停的时间
                self.video_start_time = time.time()
                self._park_preview_audio(self.video_pause_time or 0, paused=False)
                print(f"▶️ 恢复播放，已播放时间: {self.video_pause_time or 0:.2f}秒")
                self.play_next_frame()
            else:
                self.play_video()


    def play_video(self):
        """播放视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        video_path = None
        if current_scene:
            video_path = get_file_path(current_scene, "clip")
            
        if not video_path:
            return

        if self.video_cap is None:
            self.video_cap = cv2.VideoCapture(video_path)
            
        if not self.video_cap.isOpened():
            self.log_to_output(self.video_output, "❌ 无法打开视频文件")
            return
            
        self.video_playing = True
        self.video_play_button.config(text="⏸")
        
        # 记录播放开始时间，重置暂停时间
        self.video_start_time = time.time()
        self.video_pause_time = None  # 重置暂停时间
        
        # 开始播放音频（如果有）
        self.start_audio_playback()
        
        self.play_next_frame()


    def start_audio_playback(self):
        clip = get_file_path(self.workflow.get_scene_by_index(self.current_scene_index), "clip_audio")
        if not clip:
            return
        pygame.mixer.music.load(clip)
        pygame.mixer.music.play()

    def pause_audio_playback(self):
        pygame.mixer.music.pause()

    def resume_audio_playback(self):
        pygame.mixer.music.unpause()

    def stop_audio_playback(self):
        pygame.mixer.music.stop()
    

    def pause_video(self):
        """暂停视频"""
        self.video_playing = False
        self.video_play_button.config(text="▶")
        if self.video_after_id:
            self.root.after_cancel(self.video_after_id)
            self.video_after_id = None
        
        # 记录暂停时已播放的时间
        if self.video_start_time:
            elapsed = time.time() - self.video_start_time
            self.video_pause_time = (self.video_pause_time or 0) + elapsed
            
        # 暂停音频
        self.pause_audio_playback()
        print(f"⏸️ 视频暂停，总播放时间: {self.video_pause_time or 0:.2f}秒")

    def _demo_cleanup_playback(self):
        """停止当前视频/音频，不刷新 GUI（全文演示衔接用）"""
        self.video_playing = False
        self.video_play_button.config(text="▶")
        if self.video_after_id:
            try:
                self.root.after_cancel(self.video_after_id)
            except Exception:
                pass
            self.video_after_id = None
        if self.video_cap:
            try:
                self.video_cap.release()
            except Exception:
                pass
            self.video_cap = None
        self.stop_audio_playback()
        self.video_start_time = None
        self.video_pause_time = None

    def stop_video_playback(self, cancel_demo=True):
        """停止视频播放"""
        if cancel_demo:
            self._demo_playthrough_active = False
            if getattr(self, "_demo_playthrough_after_id", None):
                try:
                    self.root.after_cancel(self._demo_playthrough_after_id)
                except Exception:
                    pass
                self._demo_playthrough_after_id = None
        self.video_playing = False
        self.video_play_button.config(text="▶")
        
        if self.video_after_id:
            self.root.after_cancel(self.video_after_id)
            self.video_after_id = None
            
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None
            
        # 停止音频
        self.stop_audio_playback()
            
        # 重置时间相关变量
        self.video_start_time = None
        self.video_pause_time = None
        self._preview_playhead = 0.0
            
        self.refresh_gui_scenes()


    def get_current_video_time(self):
        if not self.video_cap:
            return 0, 0
        return self.video_cap.get(cv2.CAP_PROP_POS_MSEC) / 1000, self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT) / STANDARD_FPS


    def play_next_frame(self):
        """播放下一帧"""
        if not self.video_playing or not self.video_cap:
            return
        
        # 首先检查音频是否还在播放
        audio_is_playing = pygame.mixer.music.get_busy()
        if not audio_is_playing:
            if getattr(self, "_demo_playthrough_active", False):
                elapsed = 0.0
                if self.video_start_time:
                    elapsed = (time.time() - self.video_start_time) + (self.video_pause_time or 0)
                if elapsed < 0.2:
                    self.video_after_id = self.root.after(50, self.play_next_frame)
                    return
                self.log_to_output(self.video_output, "✅ 音频播放完毕，继续下一场景")
                self._demo_after_clip_finished()
                return
            self.stop_video_playback()
            self.log_to_output(self.video_output, "✅ 音频播放完毕，视频同步停止")
            return
            
        # 计算应该播放的帧位置以保持与音频同步
        total_frames = self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT)
        
        if self.video_start_time:
            # 计算实际经过的时间
            elapsed_time = time.time() - self.video_start_time
            current_time = elapsed_time + (self.video_pause_time or 0)
            
            # 计算应该在第几帧 (正常1倍速播放)
            target_frame = int(current_time * STANDARD_FPS)
            current_frame = int(self.video_cap.get(cv2.CAP_PROP_POS_FRAMES))
            
            # 如果视频帧落后于音频进度，跳帧追赶
            if target_frame > current_frame + 2:  # 允许2帧的容错
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        
        ret, frame = self.video_cap.read()
        
        if ret:
            # 转换颜色格式
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # 调整图像大小
            canvas_width = self.video_canvas.winfo_width()
            canvas_height = self.video_canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
            else:
                pil_image.thumbnail((630, 350), Image.Resampling.LANCZOS)
            
            # 更新画布
            self.current_video_frame = ImageTk.PhotoImage(pil_image)
            self.video_canvas.delete("all")
            
            canvas_width = canvas_width or 640
            canvas_height = canvas_height or 360
            x = canvas_width // 2
            y = canvas_height // 2
            
            # 确保图像对象存在后再创建画布图像
            if self.current_video_frame:
                try:
                    self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)
                except tk.TclError as e:
                    # 如果图像对象无效，重新创建
                    print(f"⚠️ 图像对象无效，重新创建: {e}")
                    self.current_video_frame = ImageTk.PhotoImage(pil_image)
                    self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)
            
            current_time, _total_time = self.get_current_video_time()
            self._preview_playhead = current_time
            self._draw_speech_span_bar()
            
            # 计算下一帧的延迟时间（毫秒）- 正常1倍播放速度
            delay = int(1000 / STANDARD_FPS)  # 正常播放速度
            self.video_after_id = self.root.after(delay, self.play_next_frame)

        else:
            # 视频文件读取完毕，但仍需等待音频播放完成
            if audio_is_playing:
                # 重新开始视频循环播放以配合音频
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.video_after_id = self.root.after(33, self.play_next_frame)
                print("🔄 视频循环播放以等待音频完成")
            else:
                if getattr(self, "_demo_playthrough_active", False):
                    self.log_to_output(self.video_output, "✅ 视频播放完毕，继续下一场景")
                    self._demo_after_clip_finished()
                    return
                self.stop_video_playback()
                self.log_to_output(self.video_output, "✅ 视频播放完毕")


    def refresh_gui_scenes(self):
        """刷新场景列表（节流：每秒最多执行一次）"""
        current_time = time.time()
        time_since_last = current_time - self.refresh_gui_scenes_last_time
        
        # 如果距离上次执行不到1秒，取消之前的延迟任务，安排新的延迟执行
        if time_since_last < 1.0:
            # 取消之前的延迟任务（如果存在）
            if self.refresh_gui_scenes_after_id is not None:
                self.root.after_cancel(self.refresh_gui_scenes_after_id)
            
            # 安排延迟执行，确保距离上次执行至少1秒
            delay_ms = int((1.0 - time_since_last) * 1000)
            self.refresh_gui_scenes_after_id = self.root.after(delay_ms, self._refresh_gui_scenes_impl)
            return
        
        # 如果距离上次执行超过1秒，立即执行
        self._refresh_gui_scenes_impl()
    
    def _refresh_gui_scenes_impl(self):
        """刷新场景列表的实际实现"""
        self.refresh_gui_scenes_last_time = time.time()
        self.refresh_gui_scenes_after_id = None
        
        # self.workflow.load_scenes()
        if self.current_scene_index >= len(self.workflow.scenes) :
            self.current_scene_index = 0

        # 清理所有轨道的 VideoCapture（避免使用旧场景的视频）
        self.cleanup_track_video_captures()

        # 检查现有图像
        self.update_scene_display()
        
        # 更新视频进度显示
        self.update_video_progress_display()

        # 重置轨道偏移量到新场景的起始位置
        self.reset_track_offset()

        # 延迟加载第一帧，确保canvas已完全渲染
        self.load_all_images_preview()

        self.update_add_scene_insert_buttons_state()

    
    def cleanup_track_video_captures(self):
        if hasattr(self, 'secondary_track_cap') and self.secondary_track_cap:
            try:
                self.secondary_track_cap.release()
            except:
                pass
            self.secondary_track_cap = None
        
        # 重置旁白轨道的播放状态
        if hasattr(self, 'secondary_track_playing'):
            self.secondary_track_playing = False
        if hasattr(self, 'secondary_track_after_id') and self.secondary_track_after_id:
            try:
                self.root.after_cancel(self.secondary_track_after_id)
            except:
                pass
            self.secondary_track_after_id = None
        
        # 清理 PIP 左右轨道
        if hasattr(self, 'pip_left_cap') and self.pip_left_cap:
            try:
                self.pip_left_cap.release()
            except:
                pass
            self.pip_left_cap = None
            
        if hasattr(self, 'pip_right_cap') and self.pip_right_cap:
            try:
                self.pip_right_cap.release()
            except:
                pass
            self.pip_right_cap = None
        
        # 重置 PIP 的播放状态
        if hasattr(self, 'pip_lr_playing'):
            self.pip_lr_playing = False
        if hasattr(self, 'pip_lr_after_id') and self.pip_lr_after_id:
            try:
                self.root.after_cancel(self.pip_lr_after_id)
            except:
                pass
            self.pip_lr_after_id = None


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


    def _extension_scene_value_to_combo_string(self, ext_val):
        """将 JSON 中的 extension 数值映射为 extension_values 中的项；无法匹配则 '0'。"""
        try:
            fv = float(ext_val) if ext_val is not None else 0.0
        except (TypeError, ValueError):
            fv = 0.0
        allowed = getattr(self, "extension_values", ("0", "0.2", "0.3", "0.5", "1.0"))
        for s in allowed:
            try:
                if abs(fv - float(s)) < 1e-6:
                    return s
            except ValueError:
                continue
        return "0"

    def update_scene_display(self):
        """更新场景显示"""
        if len(self.workflow.scenes) == 0:
            self.scene_label.config(text="0 / 0")
            self._refresh_marker_label()
            self.clear_scene_fields()
            self.clear_video_preview()
            self._refresh_speech_span_bar()
            return

        self._scene_widgets_loading = True
        try:
            self._update_scene_display_impl()
        finally:
            self._scene_widgets_loading = False
            self._refresh_speech_span_bar()

    def _update_scene_display_impl(self):
        self.scene_label.config(text=f"{self.current_scene_index + 1} / {len(self.workflow.scenes)}")
        self._refresh_marker_label()
        scene_data = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene_data:
            self._scene_form_scene = None
            return
        self._scene_form_scene = scene_data

        # 设置宣传复选框状态
        clip_animation = scene_data.get("clip_animation", "S2V")
        self.clip_animate.set(clip_animation)
        
        # 加载当前场景的图像类型设置
        narration_animate = scene_data.get("narration_animation", "S2V")
        self.narration_animation.set(narration_animate)

        self.extension_var.set(self._extension_scene_value_to_combo_string(scene_data.get("extension", 0)))

        self.scene_speaking.delete("1.0", tk.END)
        self.scene_speaking.insert("1.0", scene_data.get("speaking", ""))

        normalized_actor = project_manager.normalize_actor_text(scene_data.get("actor", ""))
        if normalized_actor != (scene_data.get("actor") or "").strip():
            scene_data["actor"] = normalized_actor
            self.workflow.save_scenes_to_json()
        self._set_actor_text(normalized_actor)

        self.scene_visual.delete("1.0", tk.END)
        self.scene_visual.insert("1.0", scene_data.get("visual", ""))

        self.scene_voiceover.delete("1.0", tk.END)
        self.scene_voiceover.insert("1.0", scene_data.get("voiceover", ""))

        self.scene_caption.delete("1.0", tk.END)
        self.scene_caption.insert("1.0", scene_data.get("caption", ""))
        if scene_data.pop("narrator", None) is not None:
            self.workflow.save_scenes_to_json()
        #self.scene_cinematography.delete("1.0", tk.END)
        # 如果 cinematography 是字典，格式化显示；如果是字符串，直接显示
        #cinematography_value = scene_data.get("cinematography", "")
        #if isinstance(cinematography_value, dict):
        #    self.scene_cinematography.insert("1.0", json.dumps(cinematography_value, ensure_ascii=False, indent=2))
        #else:
        #    self.scene_cinematography.insert("1.0", cinematography_value)
        status = scene_data.get("clip_status", "")
        self.video_edit_frame.config(text=f"本场内容: {status}" if status else "本场内容")
        self.video_edit_frame.update()

    def format_time_with_centisec(self, sec):
        """Format time as MM:SS.CC (minutes:sec.centisec)"""
        if sec is None or sec < 0:
            return "00:00.00"
        
        minutes = int(sec // 60)
        remaining_sec = sec % 60
        secs = int(remaining_sec)
        centisec = int((remaining_sec - secs) * 100)
        
        return f"{minutes:02d}:{secs:02d}.{centisec:02d}"


    def get_current_video_time(self):
        """Get current video playback time in sec"""
        if self.video_cap is None:
            return 0.0, 0.0
        current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
        current_time = current_frame / STANDARD_FPS

        total_time = self.workflow.find_clip_duration(self.workflow.get_scene_by_index(self.current_scene_index))
        
        if current_time > total_time:
            current_time = total_time

        return current_time, total_time

    def mute_scene_clip_audio(self):
        """将当前场景整条 clip_audio 替换为等长静音，并写回 clip 视频音轨。"""
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not current_scene:
                messagebox.showerror("错误", "没有当前场景")
                return

            self._backup_clip_to_scene_back(current_scene)

            clip_audio_path = get_file_path(current_scene, "clip_audio")
            if not clip_audio_path or not os.path.exists(clip_audio_path):
                messagebox.showerror("错误", "找不到主轨音频 clip_audio")
                return

            total_duration = self.workflow.ffmpeg_processor.get_duration(clip_audio_path)
            if total_duration <= 0:
                messagebox.showerror("错误", "无法获取音频时长")
                return

            silent_wav = self.workflow.ffmpeg_audio_processor.make_silence(total_duration)
            if not silent_wav or not os.path.exists(silent_wav):
                messagebox.showerror("错误", "生成静音失败")
                return

            _, new_audio = refresh_scene_media(
                current_scene, "clip_audio", ".wav", silent_wav, True
            )

            clip_video = get_file_path(current_scene, "clip")
            if clip_video and os.path.exists(clip_video) and new_audio:
                output_video = self.workflow.ffmpeg_processor.add_audio_to_video(clip_video, new_audio)
                if output_video:
                    refresh_scene_media(current_scene, "clip", ".mp4", output_video, True)

            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()
            messagebox.showinfo("成功", "本场景主轨音频已整条静音")
            print("✅ 整条 clip_audio 已静音")
        except Exception as e:
            error_msg = f"静音失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)


    def update_video_progress_display(self):
        """更新视频进度显示（未播放时显示总时长）"""
        if not hasattr(self, 'workflow'):
            return

        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if current_scene:
                clip_video = get_file_path(current_scene, "clip")
                if clip_video:
                    total_duration = self.workflow.ffmpeg_processor.get_duration(clip_video)
                else:
                    total_duration = 0.0
                
                current = float(getattr(self, "_preview_playhead", 0) or 0)
                self.video_progress_label.config(
                    text=f"现在 {self.format_time_with_centisec(current)} / 共 {self.format_time_with_centisec(total_duration)}"
                )
            else:
                self.video_progress_label.config(text="现在 00:00.00 / 共 00:00.00")
                
        except Exception as e:
            self.video_progress_label.config(text="现在 00:00.00 / 共 00:00.00")
            print(f"⚠️ 更新视频进度显示失败: {e}")


    def _speech_media_path(self, scene: dict | None) -> str:
        if not scene:
            return ""
        audio = get_file_path(scene, "clip_audio")
        if audio and os.path.isfile(audio):
            return audio
        video = get_file_path(scene, "clip")
        if video and os.path.isfile(video):
            return video
        return ""

    def _clip_duration(self, scene: dict | None) -> float:
        path = self._speech_media_path(scene)
        if not path or not getattr(self, "workflow", None):
            return 0.0
        try:
            return float(self.workflow.ffmpeg_processor.get_duration(path) or 0.0)
        except Exception:
            return 0.0

    def _refresh_speech_span_bar(self) -> None:
        spans = {
            "speaking_start": None,
            "speaking_end": None,
            "voiceover_start": None,
            "voiceover_end": None,
        }
        duration = 0.0
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if scene:
            duration = self._clip_duration(scene)
            for key in spans:
                raw = scene.get(key)
                if raw is None or raw == "":
                    continue
                try:
                    spans[key] = float(raw)
                except (TypeError, ValueError):
                    spans[key] = None
        if getattr(self, "_span_bar_scene", None) != self.current_scene_index:
            self._preview_playhead = 0.0
            self._span_bar_scene = self.current_scene_index
        self._speech_spans = spans
        self._speech_span_duration = duration
        if duration > 0 and self._clamp_speech_spans():
            self._save_speech_spans()
        self._draw_speech_span_bar()

    def _clamp_speech_spans(self) -> bool:
        """旁白开始不得早于讲话结束。讲话结尾是分界。"""
        duration = float(self._speech_span_duration or 0.0)
        if duration <= 0:
            return False
        changed = False

        def put(key: str, value) -> None:
            nonlocal changed
            if value is None:
                if self._speech_spans.get(key) is not None:
                    self._speech_spans[key] = None
                    changed = True
                return
            value = round(max(0.0, min(duration, float(value))), 2)
            if self._speech_spans.get(key) != value:
                self._speech_spans[key] = value
                changed = True

        for key in ("speaking", "voiceover"):
            start = self._speech_spans.get(f"{key}_start")
            end = self._speech_spans.get(f"{key}_end")
            if start is None or end is None:
                continue
            if end < start:
                start, end = end, start
            put(f"{key}_start", start)
            put(f"{key}_end", end)
        speaking_end = self._speech_spans.get("speaking_end")
        voice_start = self._speech_spans.get("voiceover_start")
        voice_end = self._speech_spans.get("voiceover_end")
        if speaking_end is not None and voice_start is not None and voice_start < speaking_end:
            put("voiceover_start", speaking_end)
            voice_start = self._speech_spans.get("voiceover_start")
        if voice_start is not None and voice_end is not None and voice_end <= voice_start:
            put("voiceover_start", None)
            put("voiceover_end", None)
        return changed

    def _second_from_x(self, x: int) -> float:
        duration = float(self._speech_span_duration or 0.0)
        width = max(self.speech_span_canvas.winfo_width(), 2)
        if duration <= 0:
            return 0.0
        return max(0.0, min(duration, x / width * duration))

    def _draw_speech_span_bar(self) -> None:
        canvas = getattr(self, "speech_span_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 2)
        height = max(canvas.winfo_height(), 24)
        duration = self._speech_span_duration or 0.0
        canvas.create_rectangle(0, 0, width, height, fill="#d9d9d9", outline="")
        play = float(getattr(self, "_preview_playhead", 0) or 0)
        if duration > 0:
            play = max(0.0, min(duration, play))
        if hasattr(self, "video_progress_label"):
            self.video_progress_label.config(
                text=f"现在 {self.format_time_with_centisec(play)} / 共 {self.format_time_with_centisec(duration)}"
            )
        if duration <= 0:
            canvas.create_text(8, height / 2, anchor="w", text="没有可标注的声音", fill="#666666")
            if hasattr(self, "speech_span_label"):
                self.speech_span_label.config(text="讲话 —    旁白 —")
            return

        def x_at(second: float) -> int:
            return int(max(0.0, min(duration, second)) / duration * width)

        bits = []
        top, bottom = 1, height - 1
        for key, color, title in (("speaking", "#2f6fed", "讲话"), ("voiceover", "#e07a2f", "旁白")):
            start = self._speech_spans.get(f"{key}_start")
            end = self._speech_spans.get(f"{key}_end")
            if start is None or end is None or end <= start:
                bits.append(f"{title} —")
                continue
            x0, x1 = x_at(start), x_at(end)
            canvas.create_rectangle(x0, top, max(x1, x0 + 2), bottom, fill=color, outline="")
            canvas.create_rectangle(x0, top, min(x0 + 4, x1), bottom, fill="#1a1a1a", outline="")
            canvas.create_rectangle(max(x0, x1 - 4), top, x1, bottom, fill="#1a1a1a", outline="")
            if x1 - x0 > 36:
                canvas.create_text(x0 + 8, height / 2, anchor="w", text=title, fill="white")
            bits.append(f"{title} {start:.2f}–{end:.2f}")
        px = x_at(play)
        tag = f"{play:.2f}"
        chip = 40
        if px < width / 2:
            chip_x0, text_x, anchor = px + 3, px + 6, "w"
        else:
            chip_x0, text_x, anchor = px - 3 - chip, px - 6, "e"
        canvas.create_rectangle(chip_x0, 2, chip_x0 + chip, height - 2, fill="#ffffff", outline="")
        canvas.create_line(px, 0, px, height, fill="#111111", width=2)
        canvas.create_text(text_x, height / 2, anchor=anchor, text=tag, fill="#111111")
        if hasattr(self, "speech_span_label"):
            self.speech_span_label.config(text="    ".join(bits))

    def _speech_span_edge_at(self, x: int, _y: int):
        duration = self._speech_span_duration or 0.0
        if duration <= 0:
            return None
        width = max(self.speech_span_canvas.winfo_width(), 2)

        def x_at(second: float) -> int:
            return int(max(0.0, min(duration, second)) / duration * width)

        hits = []
        for key in ("speaking", "voiceover"):
            for edge in ("start", "end"):
                value = self._speech_spans.get(f"{key}_{edge}")
                if value is None:
                    continue
                dist = abs(x - x_at(value))
                if dist <= 8:
                    hits.append((dist, key, edge))
        if not hits:
            return None
        kinds = {(key, edge) for _dist, key, edge in hits}
        if ("speaking", "end") in kinds and ("voiceover", "start") in kinds:
            return ("join", "boundary")
        hits.sort()
        return hits[0][1], hits[0][2]

    def _move_span_edge(self, key: str, edge: str, second: float) -> None:
        duration = float(self._speech_span_duration or 0.0)
        start = self._speech_spans.get(f"{key}_start")
        end = self._speech_spans.get(f"{key}_end")
        if start is None or end is None or duration <= 0:
            return
        if edge == "start":
            second = min(second, end - 0.15)
            second = max(0.0, second)
            if key == "voiceover":
                speaking_end = self._speech_spans.get("speaking_end")
                if speaking_end is not None:
                    second = max(second, speaking_end)
            self._speech_spans[f"{key}_start"] = round(second, 2)
        else:
            second = max(second, start + 0.15)
            second = min(duration, second)
            if key == "speaking":
                voice_end = self._speech_spans.get("voiceover_end")
                if voice_end is not None and self._speech_spans.get("voiceover_start") is not None:
                    second = min(second, voice_end - 0.15)
                self._speech_spans["speaking_end"] = round(second, 2)
                voice_start = self._speech_spans.get("voiceover_start")
                if voice_start is not None and self._speech_spans["speaking_end"] > voice_start:
                    self._speech_spans["voiceover_start"] = self._speech_spans["speaking_end"]
            else:
                self._speech_spans["voiceover_end"] = round(second, 2)
        self._clamp_speech_spans()

    def _move_span_boundary(self, second: float) -> None:
        duration = float(self._speech_span_duration or 0.0)
        speaking_start = self._speech_spans.get("speaking_start") or 0.0
        voice_end = self._speech_spans.get("voiceover_end") or duration
        second = max(speaking_start + 0.15, min(voice_end - 0.15, second))
        second = max(0.0, min(duration, second))
        self._speech_spans["speaking_end"] = round(second, 2)
        self._speech_spans["voiceover_start"] = round(second, 2)

    def _speech_span_press(self, event) -> None:
        hit = self._speech_span_edge_at(event.x, event.y)
        if hit:
            self._speech_span_drag = hit
            self._span_press_seek = False
            self._span_press_on_edge = True
            return
        self._speech_span_drag = None
        self._span_press_on_edge = False
        if (self._speech_span_duration or 0) <= 0:
            self._span_press_seek = False
            return
        self._span_press_seek = True
        self._seek_preview_to(self._second_from_x(event.x), park_audio=False)

    def _speech_span_drag_move(self, event) -> None:
        drag = getattr(self, "_speech_span_drag", None)
        if drag:
            second = self._second_from_x(event.x)
            key, edge = drag
            if key == "join":
                self._move_span_boundary(second)
            else:
                self._move_span_edge(key, edge, second)
            self._draw_speech_span_bar()
            return
        if getattr(self, "_span_press_seek", False):
            self._seek_preview_to(self._second_from_x(event.x), park_audio=False)

    def _speech_span_release(self, _event) -> None:
        if getattr(self, "_speech_span_drag", None):
            self._clamp_speech_spans()
            self._save_speech_spans()
        elif getattr(self, "_span_press_seek", False):
            self._park_preview_audio(float(getattr(self, "_preview_playhead", 0) or 0))
        self._speech_span_drag = None
        self._span_press_seek = False

    def _halt_preview_loop(self) -> None:
        self.video_playing = False
        try:
            self.video_play_button.config(text="▶")
        except tk.TclError:
            pass
        if self.video_after_id:
            try:
                self.root.after_cancel(self.video_after_id)
            except Exception:
                pass
            self.video_after_id = None
        try:
            pygame.mixer.music.pause()
        except Exception:
            pass

    def _open_preview_cap(self) -> bool:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        video_path = get_file_path(scene, "clip") if scene else ""
        if not video_path or not os.path.isfile(video_path):
            return False
        if self.video_cap is None or not self.video_cap.isOpened():
            if self.video_cap:
                self.video_cap.release()
            self.video_cap = cv2.VideoCapture(video_path)
        return bool(self.video_cap and self.video_cap.isOpened())

    def _show_preview_frame_at(self, second: float) -> None:
        if not self._open_preview_cap():
            return
        target = max(0, int(float(second) * STANDARD_FPS))
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, frame = self.video_cap.read()
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        if not ok or frame is None:
            return
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        canvas_width = self.video_canvas.winfo_width()
        canvas_height = self.video_canvas.winfo_height()
        if canvas_width > 1 and canvas_height > 1:
            pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
        else:
            pil_image.thumbnail((630, 350), Image.Resampling.LANCZOS)
        self.current_video_frame = ImageTk.PhotoImage(pil_image)
        self.video_canvas.delete("all")
        x = (canvas_width or 640) // 2
        y = (canvas_height or 360) // 2
        self.video_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_video_frame)

    def _seek_preview_to(self, second: float, park_audio: bool = True) -> None:
        self._halt_preview_loop()
        duration = float(self._speech_span_duration or 0.0)
        second = max(0.0, min(duration, float(second))) if duration > 0 else 0.0
        self._preview_playhead = second
        self.video_pause_time = second
        self.video_start_time = None
        self._show_preview_frame_at(second)
        self._draw_speech_span_bar()
        if park_audio:
            self._park_preview_audio(second)

    def _park_preview_audio(self, second: float, paused: bool = True) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        clip = get_file_path(scene, "clip_audio") if scene else ""
        if not clip or not os.path.isfile(clip):
            return
        try:
            pygame.mixer.music.load(clip)
            pygame.mixer.music.play(start=max(0.0, float(second)))
            if paused:
                pygame.mixer.music.pause()
        except Exception as exc:
            print(f"⚠️ 声音停到 {second:.2f} 秒失败: {exc}")

    def _span_key_at(self, second: float) -> str:
        speaking_start = self._speech_spans.get("speaking_start")
        speaking_end = self._speech_spans.get("speaking_end")
        if speaking_start is not None and speaking_end is not None and speaking_start <= second < speaking_end:
            return "speaking"
        voice_start = self._speech_spans.get("voiceover_start")
        voice_end = self._speech_spans.get("voiceover_end")
        if voice_start is not None and voice_end is not None and voice_start <= second <= voice_end:
            return "voiceover"
        return ""

    def _release_preview_lock(self) -> None:
        self._halt_preview_loop()
        if self.video_cap:
            try:
                self.video_cap.release()
            except Exception:
                pass
            self.video_cap = None
        self.stop_audio_playback()
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
        self.video_start_time = None
        self.video_pause_time = None

    def _retarget_spans_for_trim(self, cut_at: float, drop_head: bool) -> None:
        def convert(start, end):
            if start is None or end is None:
                return None, None
            if drop_head:
                start -= cut_at
                end -= cut_at
                if end <= 0.05:
                    return None, None
                start = max(0.0, start)
            else:
                if start >= cut_at - 0.01:
                    return None, None
                end = min(end, cut_at)
            if end - start < 0.05:
                return None, None
            return round(start, 2), round(end, 2)

        for key in ("speaking", "voiceover"):
            start, end = convert(
                self._speech_spans.get(f"{key}_start"),
                self._speech_spans.get(f"{key}_end"),
            )
            self._speech_spans[f"{key}_start"] = start
            self._speech_spans[f"{key}_end"] = end
        self._speech_span_duration = max(0.0, (self._speech_span_duration or 0.0) - cut_at) if drop_head else cut_at
        self._clamp_speech_spans()
        self._save_speech_spans()

    def trim_clip_at_playhead(self, drop_head: bool, *, confirm: bool = True) -> None:
        """裁前丢掉播放线之前，裁后丢掉播放线之后。画面和声音一起切。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            return
        video = get_file_path(scene, "clip")
        if not video or not os.path.isfile(video):
            messagebox.showinfo("裁切", "这一场没有画面。", parent=self.root)
            return
        duration = self._clip_duration(scene)
        if duration <= 0.2:
            messagebox.showinfo("裁切", "这一场太短，切不开。", parent=self.root)
            return
        cut_at = float(getattr(self, "_preview_playhead", 0) or 0)
        cut_at = max(0.0, min(duration, cut_at))
        title = "裁前" if drop_head else "裁后"
        if drop_head and cut_at <= 0.08:
            messagebox.showinfo(title, "播放线还在开头，前面没有可去掉的部分。", parent=self.root)
            return
        if (not drop_head) and cut_at >= duration - 0.08:
            messagebox.showinfo(title, "播放线已经在结尾，后面没有可去掉的部分。", parent=self.root)
            return
        if confirm:
            if drop_head:
                question = f"去掉 {cut_at:.2f} 秒之前的画面和声音？"
            else:
                question = f"去掉 {cut_at:.2f} 秒之后的画面和声音？"
            if not messagebox.askyesno(title, question, parent=self.root):
                return
        self._release_preview_lock()
        try:
            if drop_head:
                new_video = self.workflow.ffmpeg_processor.trim_video(video, start_time=cut_at)
            else:
                new_video = self.workflow.ffmpeg_processor.trim_video(video, start_time=0, end_time=cut_at)
        except Exception as exc:
            messagebox.showerror(title, f"画面没有切开：{exc}", parent=self.root)
            return
        if not new_video or not os.path.isfile(new_video):
            messagebox.showerror(title, "画面没有切开。", parent=self.root)
            return
        audio = get_file_path(scene, "clip_audio")
        new_audio = None
        if audio and os.path.isfile(audio):
            head, tail = self.workflow.ffmpeg_audio_processor.split_audio(audio, cut_at)
            new_audio = tail if drop_head else head
            if not new_audio or not os.path.isfile(new_audio):
                messagebox.showerror(title, "声音没有切开。", parent=self.root)
                return
        self._backup_clip_to_scene_back(scene)
        refresh_scene_media(scene, "clip", ".mp4", new_video, True)
        if new_audio:
            refresh_scene_media(scene, "clip_audio", ".wav", new_audio, True)
        self._retarget_spans_for_trim(cut_at, drop_head)
        self._preview_playhead = 0.0
        self.video_pause_time = 0.0
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, title, "已去掉前面。" if drop_head else "已去掉后面。")

    def _save_speech_spans(self) -> None:
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        if not scene:
            return
        for key, value in self._speech_spans.items():
            if value is None:
                scene.pop(key, None)
            else:
                scene[key] = round(float(value), 2)
        self.workflow.save_scenes_to_json()

    def detect_speech_spans(self) -> None:
        """按静音把主轨声音分成先说的讲话、后说的旁白。"""
        import re
        from utility.ffmpeg_processor import ffmpeg_path

        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        path = self._speech_media_path(scene)
        if not path:
            messagebox.showinfo("检测", "这一场没有主轨声音。", parent=self.root)
            return
        duration = self._clip_duration(scene)
        if duration <= 0:
            messagebox.showinfo("检测", "读不出这段声音有多长。", parent=self.root)
            return
        try:
            result = subprocess.run(
                [ffmpeg_path, "-i", path, "-af", "silencedetect=noise=-30dB:d=0.28", "-f", "null", "-"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
        except OSError as exc:
            messagebox.showerror("检测", f"ffmpeg 没有跑起来：{exc}", parent=self.root)
            return
        silences = []
        pending = None
        for line in (result.stderr or "").splitlines():
            start_hit = re.search(r"silence_start:\s*([0-9.]+)", line)
            end_hit = re.search(r"silence_end:\s*([0-9.]+)", line)
            if start_hit:
                pending = float(start_hit.group(1))
            elif end_hit and pending is not None:
                silences.append((pending, float(end_hit.group(1))))
                pending = None
        if pending is not None:
            silences.append((pending, duration))
        speech = []
        cursor = 0.0
        for start, end in silences:
            if start - cursor > 0.12:
                speech.append((cursor, min(start, duration)))
            cursor = max(cursor, end)
        if duration - cursor > 0.12:
            speech.append((cursor, duration))
        merged = []
        for start, end in speech:
            if merged and start - merged[-1][1] < 0.35:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        speaking = voiceover = None
        if len(merged) == 1:
            speaking = merged[0]
        elif len(merged) >= 2:
            gaps = [(merged[i + 1][0] - merged[i][1], i) for i in range(len(merged) - 1)]
            _gap, index = max(gaps)
            speaking = (merged[0][0], merged[index][1])
            voiceover = (merged[index + 1][0], merged[-1][1])
        self._speech_span_duration = duration
        self._speech_spans = {
            "speaking_start": round(speaking[0], 2) if speaking else None,
            "speaking_end": round(speaking[1], 2) if speaking else None,
            "voiceover_start": round(voiceover[0], 2) if voiceover else None,
            "voiceover_end": round(voiceover[1], 2) if voiceover else None,
        }
        self._clamp_speech_spans()
        self._save_speech_spans()
        self._draw_speech_span_bar()
        if speaking and voiceover:
            show_auto_close_popup(self.root, "检测", "已标出讲话和旁白，边缘可以拖")
        elif speaking:
            show_auto_close_popup(self.root, "检测", "只听到一段声音，标成了讲话")
        else:
            messagebox.showinfo("检测", "没有听到人声。", parent=self.root)

    def _speech_span_double(self, event) -> None:
        if getattr(self, "_span_press_on_edge", False):
            return
        self._speech_span_drag = None
        self._span_press_seek = False
        key = self._span_key_at(self._second_from_x(event.x))
        if not key:
            return
        self._ask_regenerate_span(key)

    def _span_voice_names(self) -> list[str]:
        try:
            config.reload_character_person_options()
        except Exception:
            pass
        names = []
        for name in config.narrator_person_options():
            name = (name or "").strip()
            if name and name not in names:
                names.append(name)
        return names or ["woman/mature/chinese"]

    def _ask_span_action(self, title: str, who: str, voice: str, start: float, end: float, has_text: bool) -> dict | None:
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.withdraw()
        holder = {"choice": None}
        voices = self._span_voice_names()
        if voice not in voices:
            voices.insert(0, voice)
        voice_var = tk.StringVar(value=voice)
        speed_var = tk.DoubleVar(value=1.0)
        speed_text = tk.StringVar(value="1.00 倍")

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text=f"{title}  {start:.2f}–{end:.2f} 秒\n这一段现在对的是 {who}",
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))
        ttk.Label(frame, text="声音").grid(row=1, column=0, sticky=tk.W, padx=(0, 6))
        combo = ttk.Combobox(frame, textvariable=voice_var, values=voices, state="readonly", width=28)
        combo.grid(row=1, column=1, columnspan=2, sticky=tk.EW)
        ttk.Button(
            frame,
            text="按这个声音重做",
            command=lambda: self._close_span_action(dlg, holder, "regen", voice_var, speed_var, has_text, title),
        ).grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(8, 10))
        ttk.Label(frame, text="速度").grid(row=3, column=0, sticky=tk.W)
        tk.Scale(
            frame,
            from_=0.7,
            to=1.5,
            resolution=0.01,
            orient=tk.HORIZONTAL,
            length=260,
            variable=speed_var,
            showvalue=False,
            command=lambda val: speed_text.set(f"{float(val):.2f} 倍"),
        ).grid(row=3, column=1, sticky=tk.EW)
        ttk.Label(frame, textvariable=speed_text, width=8).grid(row=3, column=2, sticky=tk.W, padx=(6, 0))
        ttk.Label(frame, text="0.7 倍更慢更长，1.5 倍更快更短。画面跟着这段声音对齐。").grid(
            row=4, column=0, columnspan=3, sticky=tk.W, pady=(2, 4)
        )
        ttk.Button(
            frame,
            text="套用这个速度",
            command=lambda: self._close_span_action(dlg, holder, "speed", voice_var, speed_var, True, title),
        ).grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(0, 10))
        ttk.Button(
            frame,
            text="拷贝这一段声音",
            command=lambda: self._close_span_action(dlg, holder, "copy", voice_var, speed_var, True, title),
        ).grid(row=6, column=0, columnspan=3, sticky=tk.EW)
        ttk.Button(
            frame,
            text="把这一段转成文字",
            command=lambda: self._close_span_action(dlg, holder, "transcribe", voice_var, speed_var, True, title),
        ).grid(row=7, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        ttk.Button(
            frame,
            text="把这一段静音",
            command=lambda: self._close_span_action(dlg, holder, "mute", voice_var, speed_var, True, title),
        ).grid(row=8, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        ttk.Button(frame, text="关闭", command=dlg.destroy).grid(row=9, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        self._place_popup_near(dlg, self.speech_span_canvas, below=False)
        dlg.grab_set()
        dlg.wait_window()
        return holder["choice"]

    def _close_span_action(self, dlg, holder, action: str, voice_var, speed_var, has_text: bool, title: str) -> None:
        speed = float(speed_var.get() or 1.0)
        if action == "regen" and not has_text:
            messagebox.showinfo(title, f"这一场的{title}是空的，不能重做。", parent=dlg)
            return
        if action == "speed" and abs(speed - 1.0) < 0.005:
            messagebox.showinfo(title, "速度还是 1 倍，这一段不用变。", parent=dlg)
            return
        holder["choice"] = {"action": action, "voice": (voice_var.get() or "").strip(), "speed": speed}
        dlg.destroy()

    def _ask_regenerate_span(self, key: str) -> None:
        scene = None
        if getattr(self, "workflow", None):
            try:
                scene = self.update_current_scene()
            except Exception:
                scene = None
            if not scene:
                scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return
        start = self._speech_spans.get(f"{key}_start")
        end = self._speech_spans.get(f"{key}_end")
        title = "讲话" if key == "speaking" else "旁白"
        if start is None or end is None or end <= start:
            messagebox.showinfo(title, "先标出这一段的开始和结束。", parent=self.root)
            return
        actor_text = (getattr(self, "_actor_text", "") or "").strip() or (scene.get("actor") or "")
        active = project_manager.active_actor_entries(actor_text)
        index = 0 if key == "speaking" else 1
        voice = "woman/mature/chinese"
        who = "这一段"
        if len(active) > index:
            row = active[index]
            body = (row.get("body") or "").strip()
            voice = project_manager.resolve_actor_voice(body) or voice
            who = "讲员" if row.get("role") == "host" else (row.get("label") or "人物")
        text = (scene.get(key) or "").strip()
        choice = self._ask_span_action(title, who, voice, float(start), float(end), bool(text))
        if not choice:
            return
        if choice["action"] == "copy":
            self._copy_span_audio(key, float(start), float(end))
            return
        if choice["action"] in ("transcribe", "mute"):
            if getattr(self, "_span_regen_busy", False):
                messagebox.showinfo(title, "上一段还在处理。", parent=self.root)
                return
            self._span_regen_busy = True
            try:
                self.root.config(cursor="watch")
            except tk.TclError:
                pass
            target = self._transcribe_span_audio if choice["action"] == "transcribe" else self._mute_span_audio
            threading.Thread(
                target=target,
                args=(key, float(start), float(end)),
                daemon=True,
            ).start()
            return
        if getattr(self, "_span_regen_busy", False):
            messagebox.showinfo(title, "上一段还在处理。", parent=self.root)
            return
        self._span_regen_busy = True
        try:
            self.root.config(cursor="watch")
        except tk.TclError:
            pass
        if choice["action"] == "speed":
            threading.Thread(
                target=self._speed_span_audio,
                args=(key, float(choice["speed"]), float(start), float(end)),
                daemon=True,
            ).start()
            return
        threading.Thread(
            target=self._regenerate_span_audio,
            args=(key, choice["voice"], text, float(start), float(end)),
            daemon=True,
        ).start()

    def _span_source_audio(self, scene: dict) -> str:
        audio = get_file_path(scene, "clip_audio")
        if audio and os.path.isfile(audio):
            return audio
        video = get_file_path(scene, "clip")
        if video and os.path.isfile(video):
            return video
        return ""

    def _cut_span_wav(self, source: str, start: float, end: float, dest: str) -> bool:
        from utility.ffmpeg_processor import ffmpeg_path

        try:
            subprocess.run(
                [
                    ffmpeg_path, "-y",
                    "-ss", f"{start:.3f}",
                    "-to", f"{end:.3f}",
                    "-i", source,
                    "-vn",
                    "-c:a", "pcm_s16le",
                    "-ar", "44100",
                    "-ac", "2",
                    dest,
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return False
        return os.path.isfile(dest) and os.path.getsize(dest) > 100

    def _atempo_wav(self, source: str, speed: float, dest: str) -> bool:
        from utility.ffmpeg_processor import ffmpeg_path

        speed = max(0.7, min(1.5, float(speed)))
        try:
            subprocess.run(
                [
                    ffmpeg_path, "-y",
                    "-i", source,
                    "-filter:a", f"atempo={speed:.4f}",
                    "-c:a", "pcm_s16le",
                    "-ar", "44100",
                    "-ac", "2",
                    dest,
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return False
        return os.path.isfile(dest) and os.path.getsize(dest) > 100

    def _copy_span_audio(self, key: str, start: float, end: float) -> None:
        title = "讲话" if key == "speaking" else "旁白"
        scene = self.workflow.get_scene_by_index(self.current_scene_index) if getattr(self, "workflow", None) else None
        source = self._span_source_audio(scene) if scene else ""
        if not source:
            messagebox.showinfo(title, "这一场没有声音。", parent=self.root)
            return
        pid = getattr(self.workflow, "pid", None) or "span"
        folder = os.path.join(config.get_project_path(str(pid)), "temp")
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, f"{key}_{start:.2f}_{end:.2f}.wav")
        if not self._cut_span_wav(source, start, end, dest):
            messagebox.showerror(title, "这一段声音没有切出来。", parent=self.root)
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(dest)
            self.root.update()
        except tk.TclError:
            messagebox.showwarning(title, f"文件已经写好，但没能放进剪贴板：\n{dest}", parent=self.root)
            return
        show_auto_close_popup(self.root, title, "这一段 wav 的路径已经拷贝")

    def _mute_span_audio(self, key: str, start: float, end: float) -> None:
        """把主轨上这一段换成等长静音，画面长短不动。"""
        root = self.root
        title = "讲话" if key == "speaking" else "旁白"

        def finish(ok: bool, message: str) -> None:
            self._span_regen_busy = False
            try:
                root.config(cursor="")
            except tk.TclError:
                pass
            if ok:
                self.refresh_gui_scenes()
                show_auto_close_popup(root, title, message)
            else:
                messagebox.showerror(title, message, parent=root)

        try:
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            audio = get_file_path(scene, "clip_audio") if scene else ""
            if not audio or not os.path.isfile(audio):
                root.after(0, lambda: finish(False, "这一场没有主轨声音。"))
                return
            ap = self.workflow.ffmpeg_audio_processor
            duration = float(ap.get_duration(audio) or 0.0)
            if duration <= 0.2:
                root.after(0, lambda: finish(False, "读不出这段声音有多长。"))
                return
            cut_start = max(0.0, min(duration, float(start)))
            cut_end = max(0.0, min(duration, float(end)))
            if cut_end - cut_start < 0.15:
                root.after(0, lambda: finish(False, "这一段太短。"))
                return
            parts = []
            if cut_start > 0.08:
                head = ap.audio_cut_fade(audio, 0.0, cut_start, 0, 0)
                if not head or not os.path.isfile(head):
                    root.after(0, lambda: finish(False, "前面一段没有切开。"))
                    return
                parts.append(head)
            silence = ap.make_silence(cut_end - cut_start)
            if not silence or not os.path.isfile(silence):
                root.after(0, lambda: finish(False, "静音没有做好。"))
                return
            parts.append(silence)
            if duration - cut_end > 0.08:
                tail = ap.audio_cut_fade(audio, cut_end, duration - cut_end, 0, 0)
                if not tail or not os.path.isfile(tail):
                    root.after(0, lambda: finish(False, "后面一段没有切开。"))
                    return
                parts.append(tail)
            merged = ap.concat_audios(parts) if len(parts) > 1 else parts[0]
            if not merged or not os.path.isfile(merged):
                root.after(0, lambda: finish(False, "静音没有接回去。"))
                return
            self._backup_clip_to_scene_back(scene)
            refresh_scene_media(scene, "clip_audio", ".wav", merged, True)
            new_audio = get_file_path(scene, "clip_audio")
            clip_video = get_file_path(scene, "clip")
            if clip_video and os.path.isfile(clip_video) and new_audio:
                output_video = self.workflow.ffmpeg_processor.add_audio_to_video(clip_video, new_audio)
                if output_video and os.path.isfile(output_video):
                    refresh_scene_media(scene, "clip", ".mp4", output_video, True)
            self.workflow.save_scenes_to_json()
            root.after(0, lambda: finish(True, "这一段已经静音。"))
        except Exception as exc:
            err = str(exc)
            root.after(0, lambda msg=err: finish(False, msg))

    def _ask_near_choices(self, anchor, title: str, choices: list[tuple[str, str]], hint: str = "") -> str | None:
        """在按钮上方弹出几个选项。点一项就返回，取消返回空。"""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.withdraw()
        holder = {"value": None}
        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=title).pack(anchor=tk.W, pady=(0, 6))
        if hint:
            ttk.Label(frame, text=hint, wraplength=360, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

        def pick(value: str) -> None:
            holder["value"] = value
            dlg.destroy()

        def text_width(text: str) -> int:
            return sum(2 if ord(ch) > 127 else 1 for ch in text) + 2

        width = max(text_width(label) for _value, label in choices)
        width = max(width, text_width("取消"), 12)
        for value, label in choices:
            ttk.Button(frame, text=label, width=width, command=lambda v=value: pick(v)).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="取消", width=width, command=dlg.destroy).pack(fill=tk.X, pady=(8, 0))
        self._place_popup_near(dlg, anchor, below=False)
        dlg.grab_set()
        dlg.wait_window()
        return holder["value"]

    def _ask_video_treatment(self) -> None:
        picked = self._ask_near_choices(
            self.btn_video_treat,
            "视频效果",
            [("reverse", "反转"), ("mirror", "镜像")],
        )
        if picked == "reverse":
            self.reverse_video()
        elif picked == "mirror":
            self.mirror_video()

    def _ask_clip_overlay(self) -> None:
        picked = self._ask_near_choices(
            self.btn_overlay,
            "图文叠加",
            [
                ("logo", "右下角 Logo"),
                ("head", "顶部角标"),
                ("title", "烧上标题"),
            ],
        )
        if picked == "logo":
            self.add_watermark()
        elif picked == "head":
            self.add_headmark()
        elif picked == "title":
            self.print_title()

    def _transcribe_span_audio(self, key: str, start: float, end: float) -> None:
        """把播放条上这一段声音交给 Voicebox 转写，写回讲话或旁白。"""
        root = self.root
        title = "讲话" if key == "speaking" else "旁白"

        def finish(ok: bool, message: str) -> None:
            self._span_regen_busy = False
            try:
                root.config(cursor="")
            except tk.TclError:
                pass
            if ok:
                self.refresh_gui_scenes()
                show_auto_close_popup(root, title, message)
            else:
                messagebox.showerror(title, message, parent=root)

        try:
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            source = self._span_source_audio(scene) if scene else ""
            if not source:
                root.after(0, lambda: finish(False, "这一场没有主轨声音。"))
                return
            wav = config.get_temp_file(self.workflow.pid, "wav")
            if not self._cut_span_wav(source, start, end, wav):
                root.after(0, lambda: finish(False, "这一段声音没有切出来。"))
                return
            service = getattr(self, "speech_service", None)
            if service is None:
                service = VoiceboxService(self.workflow.pid)
                self.speech_service = service
            raw = service.transcribe(wav)
            text = ""
            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
                if isinstance(data, dict):
                    text = str(data.get("text") or "").strip()
                else:
                    text = str(raw).strip()
            if not text:
                root.after(0, lambda: finish(False, "这一段没有转出文字。"))
                return
            scene[key] = text
            self.workflow.save_scenes_to_json()
            root.after(0, lambda: finish(True, f"已写进{title}。"))
        except Exception as exc:
            err = str(exc)
            root.after(0, lambda msg=err: finish(False, msg))

    def _install_span_wav(self, key: str, wav: str, start: float, end: float, scene: dict, clip: str, finish, success: str) -> None:
        root = self.root
        new_len = float(self.workflow.ffmpeg_processor.get_duration(wav) or 0.0)
        if new_len <= 0.2:
            root.after(0, lambda: finish(False, "这一段声音太短。"))
            return
        duration = float(self.workflow.ffmpeg_processor.get_duration(clip) or 0.0)
        if duration <= 0:
            root.after(0, lambda: finish(False, "读不出视频有多长。"))
            return
        end = min(end, duration)
        if end - start < 0.15:
            root.after(0, lambda: finish(False, "这一段太短。"))
            return
        ff = self.workflow.ffmpeg_processor
        pieces = []
        if start > 0.08:
            head = ff.trim_video(clip, 0, start)
            if not head:
                root.after(0, lambda: finish(False, "切开前面一段失败。"))
                return
            pieces.append(head)
        middle = ff.trim_video(clip, start, end)
        if not middle:
            root.after(0, lambda: finish(False, "切开这一段失败。"))
            return
        sped = ff.adjust_video_to_duration(middle, new_len, when_longer="speed")
        muxed = ff.add_audio_to_video(sped, wav, match_audio_length=True, when_longer="speed")
        if not muxed or not os.path.isfile(muxed):
            root.after(0, lambda: finish(False, "新的声音没有接到画面上。"))
            return
        pieces.append(muxed)
        if duration - end > 0.08:
            tail = ff.trim_video(clip, end, duration)
            if not tail:
                root.after(0, lambda: finish(False, "切开后面一段失败。"))
                return
            pieces.append(tail)
        merged = ff.concat_videos(pieces, True)
        if not merged or not os.path.isfile(merged):
            root.after(0, lambda: finish(False, "接回整段视频失败。"))
            return
        self._backup_clip_to_scene_back(scene)
        refresh_scene_media(scene, "clip", ".mp4", merged)
        new_clip = get_file_path(scene, "clip")
        extracted = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(new_clip, "wav")
        if extracted and os.path.isfile(extracted):
            refresh_scene_media(scene, "clip_audio", ".wav", extracted)
        old_len = end - start
        delta = new_len - old_len
        scene[f"{key}_start"] = round(start, 2)
        scene[f"{key}_end"] = round(start + new_len, 2)
        other = "voiceover" if key == "speaking" else "speaking"
        other_start = scene.get(f"{other}_start")
        other_end = scene.get(f"{other}_end")
        try:
            other_start_f = float(other_start)
            other_end_f = float(other_end)
        except (TypeError, ValueError):
            other_start_f = None
            other_end_f = None
        if other_start_f is not None and other_end_f is not None and other_start_f >= end - 0.08:
            scene[f"{other}_start"] = round(other_start_f + delta, 2)
            scene[f"{other}_end"] = round(other_end_f + delta, 2)
        self.workflow.save_scenes_to_json()
        root.after(0, lambda: finish(True, success))

    def _speed_span_audio(self, key: str, speed: float, start: float, end: float) -> None:
        root = self.root

        def finish(ok: bool, message: str) -> None:
            self._span_regen_busy = False
            try:
                root.config(cursor="")
            except tk.TclError:
                pass
            if ok:
                self.refresh_gui_scenes()
                show_auto_close_popup(root, "声音", message)
            else:
                messagebox.showerror("声音", message, parent=root)

        try:
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            clip = get_file_path(scene, "clip") if scene else ""
            source = self._span_source_audio(scene) if scene else ""
            if not clip or not os.path.isfile(clip) or not source:
                root.after(0, lambda: finish(False, "这一场没有主轨声音。"))
                return
            raw = config.get_temp_file(self.workflow.pid, "wav")
            sped = config.get_temp_file(self.workflow.pid, "wav")
            if not self._cut_span_wav(source, start, end, raw):
                root.after(0, lambda: finish(False, "这一段声音没有切出来。"))
                return
            if not self._atempo_wav(raw, speed, sped):
                root.after(0, lambda: finish(False, "速度没有套上。"))
                return
            self._install_span_wav(
                key, sped, start, end, scene, clip, finish,
                f"这一段已经按 {speed:.2f} 倍放好，画面也跟着对齐了。",
            )
        except Exception as exc:
            err = str(exc)
            root.after(0, lambda msg=err: finish(False, msg))

    def _regenerate_span_audio(self, key: str, voice: str, text: str, start: float, end: float) -> None:
        root = self.root

        def finish(ok: bool, message: str) -> None:
            self._span_regen_busy = False
            try:
                root.config(cursor="")
            except tk.TclError:
                pass
            if ok:
                self.refresh_gui_scenes()
                show_auto_close_popup(root, "声音", message)
            else:
                messagebox.showerror("声音", message, parent=root)

        try:
            if not getattr(self, "speech_service", None):
                root.after(0, lambda: finish(False, "语音服务还没准备好。"))
                return
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            clip = get_file_path(scene, "clip") if scene else ""
            if not clip or not os.path.isfile(clip):
                root.after(0, lambda: finish(False, "这一场没有主轨视频。"))
                return
            wav = self.speech_service.synthesize_speaker_text_to_wav(voice, text, self.workflow.language)
            if not wav or not os.path.isfile(wav):
                root.after(0, lambda: finish(False, "语音没有生成出来。"))
                return
            self._install_span_wav(
                key, wav, start, end, scene, clip, finish,
                "这一段声音已经换上，画面也跟着对齐了。",
            )
        except Exception as exc:
            err = str(exc)
            root.after(0, lambda msg=err: finish(False, msg))

    def clear_scene_fields(self):
        self._scene_widgets_loading = True
        try:
            self.clip_animate.set("")
            self.extension_var.set("0")

            self.scene_speaking.delete("1.0", tk.END)
            self._set_actor_text("")
            self.scene_visual.delete("1.0", tk.END)
            self.scene_voiceover.delete("1.0", tk.END)
            self.scene_caption.delete("1.0", tk.END)
            self._scene_form_scene = None
        finally:
            self._scene_widgets_loading = False


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

    def start_demo_playthrough(self):
        """从第一场景起依次导航并播放主轨 clip，串成整条故事预览。"""
        if not self.workflow or not self.workflow.scenes:
            messagebox.showwarning("提示", "没有场景", parent=self.root)
            return
        if self._demo_playthrough_active:
            messagebox.showinfo("提示", "全文演示已在进行中", parent=self.root)
            return
        if self.video_playing:
            self.stop_video_playback(cancel_demo=False)
        if hasattr(self, "_save_timer") and self._save_timer:
            self.root.after_cancel(self._save_timer)
            self._save_timer = None
        self._demo_playthrough_active = True
        if self._demo_playthrough_after_id:
            try:
                self.root.after_cancel(self._demo_playthrough_after_id)
            except Exception:
                pass
            self._demo_playthrough_after_id = None
        self.update_current_scene()
        self.current_scene_index = 0
        self.refresh_gui_scenes()
        self.log_to_output(self.video_output, "▶ 全文演示：从场景 1 开始")
        self.root.after(400, self._demo_start_play_scene)

    def _demo_video_duration_sec(self, path: str) -> float:
        cap = cv2.VideoCapture(path)
        try:
            if not cap.isOpened():
                return 3.0
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if fps <= 0:
                return 3.0
            return max(0.5, float(n) / float(fps))
        finally:
            cap.release()

    def _demo_start_play_scene(self):
        if not self._demo_playthrough_active:
            return
        if not self.workflow or not self.workflow.scenes:
            self._demo_playthrough_active = False
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        clip = get_file_path(scene, "clip") if scene else None
        clip_audio = get_file_path(scene, "clip_audio") if scene else None
        if not clip:
            self.log_to_output(self.video_output, f"场景 {self.current_scene_index + 1} 无 clip，跳过")
            self._demo_after_clip_finished()
            return
        if not clip_audio:
            d = self._demo_video_duration_sec(clip)
            self.log_to_output(
                self.video_output,
                f"场景 {self.current_scene_index + 1} 无 clip_audio，按视频时长 {d:.1f}s 后切下一场景",
            )
            self.load_all_images_preview()
            ms = max(100, int(d * 1000) + 200)
            self._demo_playthrough_after_id = self.root.after(ms, self._demo_after_clip_finished)
            return
        self.play_video()

    def _demo_after_clip_finished(self):
        if not self._demo_playthrough_active:
            return
        self._demo_playthrough_after_id = None
        self._demo_cleanup_playback()
        n = len(self.workflow.scenes)
        if n == 0:
            self._demo_playthrough_active = False
            return
        next_i = self.current_scene_index + 1
        if next_i >= n:
            self._demo_playthrough_active = False
            self.log_to_output(self.video_output, "✅ 全文演示结束（已播完所有场景）")
            self.refresh_gui_scenes()
            return
        self.current_scene_index = next_i
        self.refresh_gui_scenes()
        self.root.after(300, self._demo_start_play_scene)

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
                ("split", "从播放点分离"),
                ("delete", "删除本场"),
                ("merge_next", "与下一场合并"),
                ("merge_prev", "与上一场合并"),
                ("swap_next", "与下一场交换"),
                ("swap_prev", "与上一场交换"),
            ],
        )
        confirm = {
            "split": "从播放点把这一场分成前后两场？",
            "delete": "删除这一场？删掉以后回不来。",
            "merge_next": "把这一场和下一场合成一场？",
            "merge_prev": "把上一场和这一场合成一场？",
            "swap_next": "把这一场和下一场对调？",
            "swap_prev": "把这一场和上一场对调？",
        }.get(picked or "")
        if not confirm:
            return
        if not messagebox.askyesno("场景分合", confirm, parent=self.root):
            return
        if picked == "split":
            self.split_scene()
        elif picked == "delete":
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
        self.playing_delta = 0.0
        self._preview_playhead = 0.0
        self.playing_delta_label.config(text=f"{self.playing_delta:.1f}s")
        self.refresh_gui_scenes()


    def clean_media_mark(self):
        """标记清理"""
        for scene in self.workflow.scenes:
            scene["clip_animation"] = "S2V"

        self.workflow.save_scenes_to_json()
        messagebox.showinfo("成功", "标记清理成功！")


    def start_video_gen_batch(self):
        """启动WAN批生成"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        previous_scene = self.workflow.get_previous_scene(self.current_scene_index)
        next_scene = self.workflow.get_next_scene(self.current_scene_index)

        ss = self.workflow.scenes_in_story(current_scene)
        for scene in ss:
            self.generate_video(scene, previous_scene, next_scene, "clip")
            self.generate_video(scene, previous_scene, next_scene, "narration")

        self.refresh_gui_scenes()
        messagebox.showinfo("成功", "WAN视频批量生成成功！")


    def _open_finalize_menu(self) -> None:
        picked = self._ask_near_choices(
            self.btn_finalize,
            "成片",
            [
                ("generate", "视频生成"),
                ("publish", "视频发布"),
                ("play", "视频播放"),
                ("demo", "演示"),
            ],
        )
        if picked == "generate":
            self.run_finalize_video()
        elif picked == "publish":
            self.publish_video()
        elif picked == "play":
            self.play_finalize_video()
        elif picked == "demo":
            self.start_demo_playthrough()

    def _open_clean_menu(self) -> None:
        picked = self._ask_near_choices(
            self.btn_clean,
            "清理",
            [("media", "清媒体"), ("wan", "清WAN")],
        )
        if picked == "media":
            self.clean_media()
        elif picked == "wan":
            self.clean_wan()

    def clean_wan(self):
        self.workflow.clean_folder("/wan_video/interpolated")
        self.workflow.clean_folder("/wan_video/enhanced")
        self.workflow.clean_folder("/wan_video/original")


    def clean_media(self):
        """媒体清理"""
        self.workflow.clean_media()
        self.workflow.save_scenes_to_json()
        messagebox.showinfo("成功", "媒体清理成功！")


    def move_video(self, delta):
        self.playing_delta = self.playing_delta + delta
        if self.playing_delta < -2.0:
            self.playing_delta = -2.0
        if self.playing_delta > 2.0:
            self.playing_delta = 2.0
        
        self.playing_delta_label.config(text=f"{self.playing_delta:.1f}s")


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

    _TRANSITION_SPACE = (
        ("不变", "地方和时间都保持"),
        ("换地方", "例如从室外走进室内"),
        ("换时间", "白天到黑夜，或反过来"),
        ("一起变", "地方和时间一起变。场面大，过渡很短"),
    )
    _TRANSITION_PEOPLE = (
        ("没有变化", "在场的人不动"),
        ("自然增减", "平淡地走进来，或平静地走开"),
        ("意外增减", "由意外带出来，例如车忽然停下、有人下来"),
    )
    _TRANSITION_SPEECH = (
        ("不说话", "不开口，可以用音乐带过"),
        ("简单寒暄", "一两句没有实际内容的招呼"),
        ("人声", "人来人走时，嬉笑、叹息或一声短招呼"),
        ("小动作", "碰杯、吃饭，声音跟着动作"),
        ("场景烘托", "对话停一下，把谈到的气氛在环境里托出来"),
    )
    _TRANSITION_EFFECTS = (
        ("自然转换", "从起始图到终止图自然过渡"),
        ("叠化", "两张图慢慢融在一起"),
        ("嗖一下", "一声掠过，画面很快甩过去"),
        ("翻书", "像翻过一页书"),
        ("擦除", "后一张图从一边推开前一张"),
        ("闪白", "先闪白，再落到终止图"),
    )

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
            parsed = self.llm_api.generate_json(system_prompt, user_prompt, expect_list=False)
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

    def _put_clipboard_speaking(self, text: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
        except tk.TclError:
            pass


    @staticmethod
    def _speaking_join_prev_then_moved(prev_tail: str, moved_head: str) -> str:
        """上一段末尾接上移入的首段；若上一段末尾无句读则插入中文句号。"""
        a = (prev_tail or "").rstrip()
        b = (moved_head or "").lstrip()
        if not b:
            return a
        if not a:
            return b
        if a[-1] in "。！？；…":
            return a + b
        return a + "。" + b

    @staticmethod
    def _speaking_join_moved_then_next(moved_tail: str, next_head: str) -> str:
        """移入的尾段拼在下一场景原文前；中间按需加中文句号。"""
        a = (moved_tail or "").rstrip()
        b = (next_head or "").lstrip()
        if not a:
            return b
        if not b:
            return a
        if a[-1] in "。！？；…":
            return a + b
        return a + "。" + b

    def _speaking_shortcuts_guard(self) -> bool:
        if getattr(self, "_scene_widgets_loading", False):
            return False
        if not self.workflow or not getattr(self.workflow, "scenes", None):
            return False
        if self.current_scene_index < 0 or self.current_scene_index >= len(self.workflow.scenes):
            return False
        return True

    @staticmethod
    def _speaking_ctrl_arrow_shift_held(event) -> bool:
        """若同时按住 Shift，则应为全局场景导航（Ctrl+Shift+←/→），讲话框勿拦截。"""
        if event is None:
            return False
        try:
            st = int(getattr(event, "state", 0) or 0)
        except (TypeError, ValueError):
            return False
        return bool(st & 0x0001)  # Shift

    def _on_speaking_ctrl_s_split_clone(self, event=None):
        """Ctrl+S：以光标为界拆分讲话；当前镜保留光标前，下一镜为深拷贝场景，讲话为光标后。"""
        if not self._speaking_shortcuts_guard():
            return "break"
        self.update_current_scene()
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return "break"
        ins = self.scene_speaking.index("insert")
        before = self.scene_speaking.get("1.0", ins)
        after = self.scene_speaking.get(ins, "end-1c")
        dup = copy.deepcopy(scene)
        dup["id"] = self.workflow.max_id(dup) + 1
        scene["speaking"] = before
        dup["speaking"] = after
        self.workflow.scenes.insert(self.current_scene_index + 1, dup)
        self.workflow.touch_episode_media(self.workflow.scene_group(dup))
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        return "break"

    def _on_speaking_ctrl_right_move_tail_to_next(self, event=None):
        """Ctrl+Right：光标至文末移入下一镜讲话开头，与原文用中文句号衔接。"""
        if self._speaking_ctrl_arrow_shift_held(event):
            return  # 不 break，交给 bind_all：Ctrl+Shift+→ 切换场景
        if not self._speaking_shortcuts_guard():
            return "break"
        self.update_current_scene()
        if self.current_scene_index + 1 >= len(self.workflow.scenes):
            messagebox.showinfo("提示", "没有下一场景", parent=self.root)
            return "break"
        ins = self.scene_speaking.index("insert")
        tail = self.scene_speaking.get(ins, "end-1c")
        if not tail.strip():
            messagebox.showinfo("提示", "光标后无内容可移动", parent=self.root)
            return "break"
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        nxt = self.workflow.get_scene_by_index(self.current_scene_index + 1)
        if not scene or not nxt:
            return "break"
        head_kept = self.scene_speaking.get("1.0", ins)
        scene["speaking"] = head_kept
        nxt["speaking"] = self._speaking_join_moved_then_next(tail, nxt.get("speaking") or "")
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        return "break"

    def _on_speaking_ctrl_left_move_head_to_prev(self, event=None):
        """Ctrl+Left：文首至光标移入上一镜讲话末尾，与上一镜原文用中文句号衔接。"""
        if self._speaking_ctrl_arrow_shift_held(event):
            return  # 不 break，交给 bind_all：Ctrl+Shift+← / Ctrl+Shift+Alt+← 等
        if not self._speaking_shortcuts_guard():
            return "break"
        self.update_current_scene()
        if self.current_scene_index <= 0:
            messagebox.showinfo("提示", "没有上一场景", parent=self.root)
            return "break"
        ins = self.scene_speaking.index("insert")
        head = self.scene_speaking.get("1.0", ins)
        if not head.strip():
            messagebox.showinfo("提示", "光标前无内容可移动", parent=self.root)
            return "break"
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        prev = self.workflow.get_scene_by_index(self.current_scene_index - 1)
        if not scene or not prev:
            return "break"
        tail_kept = self.scene_speaking.get(ins, "end-1c")
        scene["speaking"] = tail_kept
        prev["speaking"] = self._speaking_join_prev_then_moved(prev.get("speaking") or "", head)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        return "break"

    def _speaking_merge_next_pair_or_error(self):
        """合并讲话：须存在下一场景，且列表中下一条即本故事内紧随当前镜的下一条。成功返回 (current, next_scene)，否则返回错误字符串。"""
        wf = self.workflow
        idx = self.current_scene_index
        if idx + 1 >= len(wf.scenes):
            return "没有下一场景"
        current = wf.get_scene_by_index(idx)
        nxt = wf.get_scene_by_index(idx + 1)
        if not current or not nxt:
            return "无法读取场景"
        ss = wf.scenes_in_story(current)
        if len(ss) <= 1:
            return "本故事内没有可合并的下一场景"
        try:
            pos = ss.index(current)
        except ValueError:
            return "无法定位当前场景"
        if pos + 1 >= len(ss):
            return "已是本故事最后一镜"
        if ss[pos + 1] is not nxt:
            return "列表中的下一场景不是本故事中的下一场景，无法合并讲话"
        return (current, nxt)

    def _on_speaking_ctrl_m_merge_next_speaking(self, event=None):
        """Ctrl+M：把本故事下一场景的 speaking 并入当前（中缝按需加中文句号），音视频不变；删除下一场景。"""
        if not self._speaking_shortcuts_guard():
            return "break"
        self.update_current_scene()
        r = self._speaking_merge_next_pair_or_error()
        if isinstance(r, str):
            messagebox.showinfo("提示", r, parent=self.root)
            return "break"
        current, nxt = r
        if not messagebox.askyesno(
            "合并讲话",
            "将「下一场景」的讲话合并到当前场景的讲话（中间按需加中文句号）。\n\n"
            "当前场景的视频、音频、图片等媒体保持不变，不合并音轨。\n"
            "下一场景将从场景列表中删除。\n\n"
            "是否继续？",
            parent=self.root,
        ):
            return "break"
        current["speaking"] = self._speaking_join_prev_then_moved(
            current.get("speaking") or "",
            nxt.get("speaking") or "",
        )
        self.workflow.release_scene_page_png(nxt)
        self.workflow.scenes.pop(self.current_scene_index + 1)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        return "break"

    def _on_speaking_ctrl_shift_nav_prev(self, event=None):
        """讲话框内 Ctrl+Shift+←：上一场景（优先于 Text 默认行为，与 bind_scene_navigation_shortcuts 一致）。"""
        if getattr(self, "workflow", None) and getattr(self.workflow, "scenes", None):
            self.prev_scene()
        return "break"

    def _on_speaking_ctrl_shift_nav_next(self, event=None):
        """讲话框内 Ctrl+Shift+→：下一场景（同上）。"""
        if getattr(self, "workflow", None) and getattr(self.workflow, "scenes", None):
            self.next_scene()
        return "break"

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


    def on_scene_text_review(
        self,
        text_field,
        event=None,
        *,
        title="审阅文案",
        source_field=None,
        remix_system_prompt=None,
    ):
        """双击左键：审阅 / Remix 文案，确定后写回当前场景对应字段。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return "break"
        lang = getattr(self.workflow, "language", None) or "tw"
        lang_label = config.llm_language_label(lang)
        src_field = source_field or text_field
        source_text = config.chinese_convert((scene.get(src_field) or ""), lang)
        if source_field:
            initial_edit = config.chinese_convert((scene.get(text_field) or ""), lang)
        else:
            initial_edit = None

        prompt_tpl = remix_system_prompt or config_prompt.SPEAKING_CONCISE_PROMPT
        system_prompt = prompt_tpl.format(language=lang_label)

        def _remix(t: str) -> str:
            out = self.llm_api_local.generate_text(
                system_prompt, (t or "").strip()
            )
            return config.chinese_convert(out, lang)

        confirmed = ask_speaking_concise_review_dialog(
            self.root,
            source_text,
            remix_fn=_remix,
            title=title,
            initial_edit=initial_edit,
        )
        if confirmed is None:
            return "break"

        scene[text_field] = confirmed
        widget_map = {
            "speaking": self.scene_speaking,
            "visual": self.scene_visual,
            "voiceover": self.scene_voiceover,
            "caption": self.scene_caption,
        }
        widget = widget_map.get(text_field)
        if widget is not None:
            widget.delete("1.0", tk.END)
            widget.insert("1.0", confirmed)
        self.workflow.save_scenes_to_json()
        return "break"


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

    def _show_story_packaging_menu(self) -> None:
        """Story 片头/片尾包装：选中项复制英文指令到剪贴板。"""
        channel_name = _workflow_channel_display_name()
        m = tk.Menu(self.root, tearoff=0)
        for label, tmpl in STORY_PACKAGING_MENU:
            text = tmpl.format(channel_name=channel_name)

            def _copy(t=text, lbl=label):
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(t)
                    self.root.update()
                except tk.TclError:
                    return
                show_auto_close_popup(
                    self.root,
                    "故事包装",
                    f"已复制：{lbl}（{channel_name}）",
                )

            m.add_command(label=label, command=_copy)
        post_menu_below_widget(m, self._story_packaging_btn)

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


    def append_scene(self):
        story_level = self.workflow.last_scene_of_story(self.workflow.get_scene_by_index(self.current_scene_index))

        self.workflow.add_story_scene( self.current_scene_index, self.workflow.get_scene_by_index(self.current_scene_index), story_level, True )

        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def reverse_video(self):
        """翻转视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        self._backup_clip_to_scene_back(current_scene)
        oldv, newv = refresh_scene_media(current_scene, "clip", ".mp4")
        os.replace(self.workflow.ffmpeg_processor.reverse_video(oldv), newv)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def get_current_playback_position(self):
        """
        获取当前主场景的播放位置（而不是其他轨道的位置）
        优先级：暂停位置 > 实时播放位置 > 0
        """
        # 调试信息
        has_pause_time = hasattr(self, 'video_pause_time')
        pause_time_value = self.video_pause_time if has_pause_time else "属性不存在"
        is_playing = self.video_playing if hasattr(self, 'video_playing') else False
        
        # 1. 如果有暂停位置，使用它（最准确）
        if has_pause_time and self.video_pause_time is not None and self.video_pause_time > 0:
            print(f"🎬 使用主视频暂停位置: {self.video_pause_time:.2f}s")
            return self.video_pause_time
        
        # 2. 如果正在播放，基于时间计算当前位置
        if is_playing and hasattr(self, 'video_start_time') and self.video_start_time:
            try:
                elapsed = time.time() - self.video_start_time
                # 如果有累积的暂停时间，加上它
                total_time = elapsed + (self.video_pause_time if self.video_pause_time else 0)
                print(f"🎬 使用主视频播放位置（实时计算）: {total_time:.2f}s (当前片段: {elapsed:.2f}s, 累积暂停: {self.video_pause_time or 0:.2f}s)")
                return total_time
            except:
                pass
        
        # 3. 默认返回 0
        print(f"🎬 主视频未播放或无暂停位置，返回 0")
        print(f"    调试: video_pause_time={pause_time_value}, video_playing={is_playing}")
        return 0.0


    def mirror_video(self):
        """镜像视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        self._backup_clip_to_scene_back(current_scene)
        oldv, newv = refresh_scene_media(current_scene, "clip", ".mp4")
        os.replace(self.workflow.ffmpeg_processor.mirror_video(oldv), newv)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def _resolve_watermark_config(self):
        """解析水印 PNG 路径与选项（与 NotebookLM add_watermark_cli 的 config.watermark 一致）。"""
        return resolve_watermark_for_project(project_manager.PROJECT_CONFIG or {})


    def _resolve_headmark_config(self):
        """解析左上角角标：优先 PROJECT_CONFIG.headmark，缺字段时并入当前频道 headmark。"""
        return resolve_headmark_for_project(project_manager.PROJECT_CONFIG or {})


    def _apply_watermark_to_flat_image_webp(self, webp_path: str) -> str:
        """在静态图右下角叠加当前频道水印，写入新 WEBP；无水印配置则返回原路径。"""
        wm_path, wm_opts = self._resolve_watermark_config()
        if not wm_path or not os.path.isfile(webp_path):
            return webp_path
        return self.workflow.ffmpeg_processor.apply_watermark_to_flat_image(
            webp_path, wm_path, wm_opts
        )


    def swap_speaking_voiceover(self):
        """交换当前场景的「讲话」与「旁白」。"""
        if not getattr(self, "workflow", None) or not self.workflow.scenes:
            messagebox.showwarning("提示", "没有当前工作流", parent=self.root)
            return
        current_scene = self.update_current_scene()
        if not current_scene:
            messagebox.showwarning("提示", "没有当前场景", parent=self.root)
            return

        sp = current_scene.get("speaking") or ""
        vo = current_scene.get("voiceover") or ""
        if sp == vo:
            return
        current_scene["speaking"] = vo
        current_scene["voiceover"] = sp
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def add_headmark(self):
        """为当前场景或本故事全部场景的主轨 clip 左上角叠加角标 PNG（headmark 配置，默认 program/<channel_id>/headmark.png）。"""
        if not getattr(self, "workflow", None) or not self.workflow.scenes:
            messagebox.showwarning("提示", "没有当前工作流", parent=self.root)
            return
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            messagebox.showwarning("提示", "没有当前场景", parent=self.root)
            return
        hm_path, hm_opts = self._resolve_headmark_config()
        if not hm_path:
            messagebox.showerror(
                "顶标",
                "未找到左上角角标图片。\n"
                "请在项目 JSON 中配置 headmark.path，或将 PNG 放在 program/<频道>/ 下（如 headmark.png）。",
                parent=self.root,
            )
            return

        scope = messagebox.askyesnocancel(
            "顶标范围",
            "请选择叠加左上角角标范围：\n\n"
            "「是」本故事全部场景\n"
            "「否」仅当前场景\n"
            "「取消」不处理",
            parent=self.root,
        )
        if scope is None:
            return

        target_scenes = self.workflow.scenes_in_story(current_scene) if scope else [current_scene]

        self._clip_overlay_ffmpeg_batch_async(
            target_scenes,
            hm_path,
            hm_opts,
            "顶标",
            "加顶标失败",
            lambda fp, sr, dt, op, ot: fp.headmark_clip_with_preprocess(sr, dt, op, ot),
        )


    def add_watermark(self):
        """为当前场景或本故事全部场景的主轨 clip 加水印（PNG 见频道 program/<channel_id>/ 或项目 watermark 配置）。"""
        if not getattr(self, "workflow", None) or not self.workflow.scenes:
            messagebox.showwarning("提示", "没有当前工作流", parent=self.root)
            return
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not current_scene:
            messagebox.showwarning("提示", "没有当前场景", parent=self.root)
            return
        wm_path, wm_opts = self._resolve_watermark_config()
        if not wm_path:
            messagebox.showerror(
                "水印",
                "未找到水印图片。\n"
                "请在项目 JSON 中配置 watermark.path，或将 PNG 放在 program/<频道>/ 下（如 watermark.png）。",
                parent=self.root,
            )
            return

        scope = messagebox.askyesnocancel(
            "水印范围",
            "请选择加水印范围：\n\n"
            "「是」本故事全部场景\n"
            "「否」仅当前场景\n"
            "「取消」不处理",
            parent=self.root,
        )
        if scope is None:
            return

        target_scenes = self.workflow.scenes_in_story(current_scene) if scope else [current_scene]

        self._clip_overlay_ffmpeg_batch_async(
            target_scenes,
            wm_path,
            wm_opts,
            "水印",
            "加水印失败",
            lambda fp, sr, dt, op, ot: fp.watermark_clip_with_preprocess(sr, dt, op, ot),
        )


    def print_title(self):
        """将 caption 烧录为视频标题字幕（字体用本集内容里的字体）。"""
        current_scene = self.update_current_scene()
        content = current_scene['caption']
        if not content or content.strip() == "":
            messagebox.showinfo("加标题", "标题为空")
            return
        clip_video = get_file_path(current_scene, "clip")
        if not clip_video:
            messagebox.showinfo("加标题", "视频为空")
            return
       
        content = config.chinese_convert(content, self.workflow.language)

        title_font_key = self.scene_language.get()
        if title_font_key in config.FONT_LIST:
            font = config.FONT_LIST[title_font_key]
        else:
            font = self.workflow.font_title

        self._backup_clip_to_scene_back(current_scene)
        v = self.workflow.ffmpeg_processor.add_script_to_video(clip_video, content, font)
        refresh_scene_media(current_scene, "clip", ".mp4", v)

        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


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


    # ========== PIP L/R 播放控制函数 ==========
    
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


    def _show_auto_dismiss_tip(self, title: str, message: str, ms: int = 2000):
        """非模态提示，约 ms 毫秒后自动关闭，无需点确定。"""
        tip = tk.Toplevel(self.root)
        tip.title(title)
        tip.transient(self.root)
        tip.resizable(False, False)
        frm = ttk.Frame(tip, padding=16)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text=message, justify=tk.CENTER).pack()
        tip.update_idletasks()
        w = tip.winfo_reqwidth()
        h = tip.winfo_reqheight()
        rx = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - w) // 2)
        ry = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - h) // 2)
        tip.geometry(f"+{rx}+{ry}")
        tip.after(ms, tip.destroy)


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
            if image_type == "clip_image":
                self.workflow.write_scene_page_png(scene, scene.get("clip_image") or frame)
            self.workflow.save_scenes_to_json()
            self.display_image_on_canvas_for_track(image_type)
            show_auto_close_popup(
                self.root,
                "放入",
                "已用这条视频的尾帧换上" if is_last else "已用这条视频的首帧换上",
            )
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
        if image_type == "clip_image":
            self.workflow.write_scene_page_png(scene, scene.get("clip_image") or source)
        self.workflow.save_scenes_to_json()
        self.display_image_on_canvas_for_track(image_type)
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
                if start_key == "clip_image":
                    self.workflow.write_scene_page_png(scene, scene.get(start_key) or old_path)
            refresh_scene_media(scene, last_key, ".webp", file_path, True)
        else:
            old_path = scene.get(start_key) or ""
            if old_path and os.path.isfile(old_path):
                refresh_scene_media(scene, last_key, ".webp", old_path, True)
            refresh_scene_media(scene, start_key, ".webp", file_path, True)
            if start_key == "clip_image":
                self.workflow.write_scene_page_png(scene, file_path)
        self.workflow.save_scenes_to_json()
        self.display_image_on_canvas_for_track(start_key)
        self.display_image_on_canvas_for_track(last_key)
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
        if not pdf_path:
            return
        group_name = self.workflow.scene_group(scene)
        pages = self._episode_page_pngs(group_name)
        folder = os.path.join(config.get_media_path(self.workflow.pid), group_name)
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
        self.workflow.compact_episode_pages(group_name)
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
            if image_type == "clip_image":
                self.workflow.write_scene_page_png(scene, file_path)

        self.workflow.save_scenes_to_json()
        self.display_image_on_canvas_for_track(image_type)
        print(f"✅ 已更新 {image_type}: {os.path.basename(file_path)}")

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
    

    def _ask_playhead_split(self) -> None:
        """以播放线为界：前面移到上一场，后面移到下一场，或清掉其中一边。"""
        picked = self._ask_near_choices(
            self.btn_playhead_split,
            "分界处理",
            [
                ("move_prev", "播放线前面，移到上一场"),
                ("move_next", "播放线后面，移到下一场"),
                ("cut_prev", "清掉播放线前面"),
                ("cut_next", "清掉播放线后面"),
            ],
            hint="以这条播放线为界。前面是线的左边，后面是线的右边。画面和声音一起动。",
        )
        if picked == "move_prev":
            self._shift_at_playhead(forward=False)
        elif picked == "move_next":
            self._shift_at_playhead(forward=True)
        elif picked == "cut_prev":
            self.trim_clip_at_playhead(True, confirm=False)
        elif picked == "cut_next":
            self.trim_clip_at_playhead(False, confirm=False)

    def _shift_at_playhead(self, forward: bool) -> None:
        """按播放线把一段画面和声音接到相邻场景。forward 为真时后面接到下一场。"""
        self.update_current_scene()
        if not self.workflow or not self.workflow.scenes:
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return
        title = "分界处理"
        video = get_file_path(scene, "clip")
        if not video or not os.path.isfile(video):
            messagebox.showinfo(title, "这一场没有画面。", parent=self.root)
            return
        duration = self._clip_duration(scene)
        if duration <= 0.2:
            messagebox.showinfo(title, "这一场太短，分不开。", parent=self.root)
            return
        cut_at = float(getattr(self, "_preview_playhead", 0) or 0)
        cut_at = max(0.0, min(duration, cut_at))
        if (not forward) and cut_at <= 0.08:
            messagebox.showinfo(title, "播放线还在开头，前面没有可移走的部分。", parent=self.root)
            return
        if forward and cut_at >= duration - 0.08:
            messagebox.showinfo(title, "播放线已经在结尾，后面没有可移走的部分。", parent=self.root)
            return
        current_index = self.current_scene_index
        other_index = current_index + 1 if forward else current_index - 1
        if other_index < 0 or other_index >= len(self.workflow.scenes):
            messagebox.showinfo(title, "没有下一场。" if forward else "没有上一场。", parent=self.root)
            return
        self._release_preview_lock()
        moved = self.workflow.shift_scene(current_index, other_index, cut_at, False)
        if not moved:
            messagebox.showinfo(title, "这一段没有移过去。", parent=self.root)
            return
        self._preview_playhead = 0.0
        self.video_pause_time = 0.0
        self.refresh_gui_scenes()
        show_auto_close_popup(
            self.root,
            title,
            "后面已接到下一场。" if forward else "前面已接到上一场。",
        )


    def merge_or_delete(self):
        """合并当前图片与下一张图片"""
        if len(self.workflow.scenes) == 0:
            messagebox.showinfo("警告", "⚠️ 无场景")
            return

        self._cancel_scene_debounce_timer()
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        ss = self.workflow.scenes_in_story(current_scene)
        if len(ss) <= 1:
            result = messagebox.askyesnocancel("警告", "⚠️ 删除唯一场景?")
            if result is True:
                ss = self.workflow.replace_scene(self.current_scene_index)
        else:
            if ss[-1] == current_scene:
                result = messagebox.askyesnocancel("警告", "⚠️ 删除当前场景?")
                if result is True:
                    ss = self.workflow.replace_scene(self.current_scene_index)
            else:
                result = messagebox.askyesnocancel("警告", "⚠️ 请选择操作：\n是: 合并场景\n否: 删除场景\n取消: 取消操作")
                if result is True:
                    self.workflow.merge_scene(self.current_scene_index, self.current_scene_index+1)
                else:
                    result = messagebox.askyesno("警告", "⚠️ 删除当前场景?")
                    if result:
                        ss = self.workflow.replace_scene(self.current_scene_index)

        self._cancel_scene_debounce_timer()
        self._refresh_gui_scenes_impl()
        messagebox.showinfo("合并场景", "完成")


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

    def _current_story_scenes(self) -> list:
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return []
        return list(self.workflow.scenes_in_story(scene) or [])

    def _notebooklm_video_detail_stub(self) -> dict:
        pc = project_manager.PROJECT_CONFIG or {}
        return {
            "id": pc.get("pid"),
            "topic_category": pc.get("topic_category"),
            "topic_subtype": pc.get("topic_subtype"),
        }

    def _copy_workflow_notebooklm_instruction(
        self,
        scenes: list,
        nb_mode: str,
        nb_variant: str = "",
    ) -> None:
        """工作流场景 → NotebookLM 指令剪贴板（与 downloader 分镜窗同一套 build）。"""
        self.update_current_scene()
        entries: list[dict] = [s for s in scenes if isinstance(s, dict)]
        if not entries:
            messagebox.showwarning("NotebookLM", "无可用场景内容。", parent=self.root)
            return

        pc = project_manager.PROJECT_CONFIG or {}
        vs = (
            (self.scene_visual_style.get() or "").strip()
            or pc.get("visual_style")
            or config.VISUAL_STYLE_OPTIONS[0]
        )
        cur = self.workflow.get_scene_by_index(self.current_scene_index)
        main_char = ""
        if cur:
            main_char = (cur.get("actor") or self._actor_text or "").strip()
        host_nar = project_manager.project_narrator()

        try:
            clip_body = config_prompt.build_notebooklm_gen_instruction_clipbody(
                mode=nb_mode,
                variant=nb_variant,
                video_detail=self._notebooklm_video_detail_stub(),
                scene_content=entries,
                visual_style=vs,
                main_character=main_char,
                host_narrator=host_nar,
            )
        except ValueError as exc:
            messagebox.showerror("NotebookLM", str(exc), parent=self.root)
            return
        if not (clip_body or "").strip():
            return
        try:
            title = config_prompt.nb_export_mode_label(nb_mode, nb_variant)
        except ValueError:
            title = nb_mode
        if nb_mode == "video":
            self._open_gen_prompt_window(
                f"视频 · {title}",
                clip_body,
                with_last=nb_variant != "act_one",
                anchor=self._nb_story_video_btn,
            )
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(clip_body)
        self.root.update()
        show_auto_close_popup(
            self.root,
            f"NotebookLM · {title}",
            f"已拷贝 {len(entries)} 个场景到剪贴板",
        )

    def _show_nb_variant_menu(self, widget, base: str, scenes: list) -> None:
        if not scenes:
            messagebox.showwarning("提示", "没有可用场景", parent=self.root)
            return
        m = tk.Menu(self.root, tearoff=0)
        for var, var_label in config_prompt.NOTEBOOKLM_EXPORT_VARIANTS.get(base, []):
            m.add_command(
                label=var_label,
                command=lambda v=var: self._copy_workflow_notebooklm_instruction(
                    scenes, base, v
                ),
            )
        post_menu_below_widget(m, widget)

    def _open_picture_prompt_flow(self) -> None:
        """图片提示：先选画风和说明文字，再在手动窗口里拷当前图和提示词。"""
        if not self.workflow or not self.workflow.get_scene_by_index(self.current_scene_index):
            messagebox.showwarning("图片提示", "没有当前场景", parent=self.root)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("图片提示")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.withdraw()

        main = ttk.Frame(dlg, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        hint = ttk.Label(main, wraplength=520, justify=tk.LEFT)
        hint.pack(anchor=tk.W)
        body = ttk.Frame(main)
        body.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        actions = ttk.Frame(main)
        actions.pack(fill=tk.X)

        task_var = tk.StringVar(value="keep")
        text_var = tk.StringVar(value="keep")

        groups = ttk.Frame(body)
        groups.pack(anchor=tk.W)

        task_box = ttk.LabelFrame(groups, text="处理", padding=(8, 4))
        task_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
        task_buttons = []
        for value, label in config_prompt.PICTURE_FLOW_TASK_CHOICES:
            btn = ttk.Radiobutton(task_box, text=label, value=value, variable=task_var)
            btn.pack(anchor=tk.W)
            task_buttons.append(btn)

        text_box = ttk.LabelFrame(groups, text="说明文字", padding=(8, 4))
        text_box.pack(side=tk.LEFT, anchor=tk.N)
        text_buttons = []
        for value, label in config_prompt.PICTURE_FLOW_TEXT_CHOICES:
            btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
            btn.pack(anchor=tk.W)
            text_buttons.append(btn)

        cover_var = tk.StringVar(value="none")
        cover_choices: list[tuple[str, str, str]] = []
        for label, template in config_prompt.DIRECT_VIDEO_PROMPT_CHOICES:
            if not label.startswith("Image to Detail-Single-Step-Image"):
                continue
            cover_choices.append((str(len(cover_choices) + 1), template, label))
        cover_box = ttk.LabelFrame(groups, text="封面处理", padding=(8, 4))
        cover_box.pack(side=tk.LEFT, anchor=tk.N, padx=(8, 0))
        ttk.Radiobutton(cover_box, text="无", value="none", variable=cover_var).pack(anchor=tk.W)
        for key, _template, _full in cover_choices:
            ttk.Radiobutton(cover_box, text=key, value=key, variable=cover_var).pack(anchor=tk.W)

        def current_scene():
            self.update_current_scene()
            if not self.workflow:
                return None
            return self.workflow.get_scene_by_index(self.current_scene_index)

        def current_style() -> str:
            pc = project_manager.PROJECT_CONFIG or {}
            return (
                (self.scene_visual_style.get() or "").strip()
                or (pc.get("visual_style") or "").strip()
                or ""
            )

        def refresh_choices(*_args) -> None:
            cover_on = cover_var.get() != "none"
            extract = task_var.get() == "extract"
            for btn in task_buttons:
                btn.configure(state=("disabled" if cover_on else "normal"))
            for btn in text_buttons:
                btn.configure(state=("disabled" if cover_on or extract else "normal"))
            go.config(text="打开提示")
            if cover_on:
                hint.config(text="用封面图再生成一张图。选好编号后打开提示窗口，封面和提示词都在里面。")
            elif extract:
                hint.config(text="人物提取用固定提示。选好后打开提示窗口，当前图和提示词都在里面。")
            else:
                hint.config(text="先选定画风和说明文字。选好后打开提示窗口，当前图和提示词都在里面。封面处理选「无」。")

        def open_manual(prompt: str, images: list[str]) -> None:
            dlg.destroy()
            self.llm_api.show_manual_window(prompt, "", images=images)

        def on_go() -> None:
            cover_key = cover_var.get()
            if cover_key != "none":
                picked = next((item for item in cover_choices if item[0] == cover_key), None)
                if picked is None:
                    return
                cover, _slide = self._project_cover_and_slide()
                if not cover:
                    messagebox.showinfo("图片提示", "还没有封面图。", parent=dlg)
                    return
                _mgr, vd, _story_raw, _ch_path = self._cover_prompt_context()
                sc = vd.get("scene_content") if isinstance(vd, dict) else []
                prompt = config_prompt.build_direct_video_clipbody(
                    instruction=picked[1],
                    story_entries=sc if isinstance(sc, list) else [],
                    main_character=project_manager.project_narrator(),
                    visual_style=current_style() or project_manager.LAST_VISUAL_STYLE,
                )
                open_manual(prompt, [cover])
                return
            if task_var.get() != "extract" and not current_style():
                messagebox.showwarning("图片提示", "请先在上面选定画面风格。", parent=dlg)
                return
            scene = current_scene()
            if not isinstance(scene, dict):
                messagebox.showwarning("图片提示", "没有当前场景", parent=dlg)
                return
            path = scene.get("clip_image") if isinstance(scene, dict) else ""
            images = [path] if isinstance(path, str) and path and os.path.isfile(path) else []
            if not images:
                messagebox.showinfo("图片提示", "这一场没有当前图。提示窗口里只放提示词。", parent=dlg)
            try:
                prompt = config_prompt.build_picture_flow_prompt(
                    task=task_var.get(),
                    text=text_var.get(),
                    visual_style=current_style(),
                    region=(self.setting_region.get() or "").strip(),
                    era=(self.setting_era.get() or "").strip(),
                )
            except ValueError as exc:
                messagebox.showwarning("图片提示", str(exc), parent=dlg)
                return
            open_manual(prompt, images)

        go = ttk.Button(actions, text="打开提示", command=on_go)
        go.pack(side=tk.LEFT)
        task_var.trace_add("write", refresh_choices)
        cover_var.trace_add("write", refresh_choices)
        refresh_choices()
        self._place_popup_near(dlg, self._nb_picture_btn, below=True)

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

    def _open_gen_prompt_window(self, title: str, prompt: str, *, with_last: bool, anchor=None) -> None:
        """提示词先放进剪贴板。图片只再拷起始图。视频接着再拷尾图，然后窗口关掉。"""
        prompt = (prompt or "").strip()
        if not prompt:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt)
            self.root.update_idletasks()
        except tk.TclError:
            pass

        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.withdraw()

        main = ttk.Frame(dlg, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        hint = ttk.Label(main, wraplength=430, justify=tk.LEFT)
        hint.pack(anchor=tk.W)
        box = scrolledtext.ScrolledText(main, wrap=tk.WORD, height=8, width=52)
        box.pack(fill=tk.BOTH, expand=True, pady=(6, 8))
        box.insert("1.0", prompt)
        box.configure(state=tk.DISABLED)

        actions = ttk.Frame(main)
        actions.pack(fill=tk.X)
        step = {"n": 0}

        def put_prompt() -> None:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(prompt)
                self.root.update_idletasks()
            except tk.TclError:
                messagebox.showwarning(title, "提示词没有放进剪贴板。", parent=dlg)

        def current_scene():
            self.update_current_scene()
            return self.workflow.get_scene_by_index(self.current_scene_index) if self.workflow else None

        def copy_slot(key: str, missing: str) -> bool:
            scene = current_scene()
            path = scene.get(key) if isinstance(scene, dict) else ""
            if not isinstance(path, str) or not path or not os.path.isfile(path):
                messagebox.showinfo(title, missing, parent=dlg)
                return False
            if not self.copy_image_to_clipboard(path, silent=True):
                messagebox.showwarning(title, "这张图没有拷到剪贴板。", parent=dlg)
                return False
            return True

        go = ttk.Button(actions)

        def advance() -> None:
            if step["n"] == 0:
                if not copy_slot("clip_image", "这一场没有起始图。"):
                    return
                if not with_last:
                    dlg.destroy()
                    return
                step["n"] = 1
                hint.config(text="起始图已拷贝。贴进视频生成工具以后，再按按钮拷尾图。")
                go.config(text="拷贝尾图")
                return
            if not copy_slot("clip_image_last", "这一场没有尾图。"):
                return
            dlg.destroy()

        if with_last:
            hint.config(text="提示词已拷贝。先贴进视频生成工具。贴好以后回来，按按钮拷起始图，然后再拷尾图。")
        else:
            hint.config(text="提示词已拷贝。先贴进图片生成工具。贴好以后回来，按按钮拷这一张起始图。")
        ttk.Button(actions, text="再拷提示词", command=put_prompt).pack(side=tk.LEFT)
        go.config(text="拷贝起始图", command=advance)
        go.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT)

        near = anchor if anchor is not None else getattr(self, "_ai_tools_frame", None) or self.root
        self._place_popup_near(dlg, near, below=True)

    def _open_video_prompt_flow(self) -> None:
        """视频提示：先选画面、背景、演进，再在手动窗口里拷画面和提示词。"""
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

        open_video_prompt_dialog(
            self.root,
            self._nb_story_video_btn,
            get_scenes=lambda: [s for s in [current_scene()] if isinstance(s, dict)],
            get_style=get_style,
            copy_text=copy_text,
            language=getattr(self.workflow, "language", "") or "",
            host_narrator=project_manager.project_narrator(),
            get_image=get_image,
            copy_image=lambda path: bool(self.copy_image_to_clipboard(path, silent=True)),
            open_manual=lambda prompt, images: self.llm_api.show_manual_window(
                prompt, "", images=images
            ),
        )

    _SCENE_IMPORT_ALWAYS_KEYS = frozenset({
        "speaking", "caption", "voiceover", "visual", "actor",
        "clip_animation", "narration_animation", "extension", "cinematography",
    })
    _SCENE_IMPORT_SKIP_KEYS = frozenset({"start", "end", "duration", "transition"})

    def _scene_import_extractable_fields(self, scene: dict) -> dict:
        """从场景 dict 提取可导入/导出的文案字段（作 JSON 编辑初始模板）。"""
        if not isinstance(scene, dict):
            return {}
        keys = (
        "speaking", "caption", "voiceover", "visual", "actor",
        "clip_animation", "narration_animation", "extension", "cinematography",
        )
        out = {}
        for k in keys:
            v = scene.get(k)
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            out[k] = v
        return out

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

    def _ask_scene_speech_transform(self) -> None:
        """场景变换：选改一场、两场还是三场，直接调用语言模型，结果写回这一场。"""
        picked = self._ask_near_choices(
            self._scene_speech_btn,
            "场景变换",
            [
                ("1", "只改这一场的讲话和旁白"),
                ("2", "这一场和下一场合成一段"),
                ("3", "这一场连后面两场合成一段"),
            ],
            hint="按现在的人物重写说法。结果直接写回这一场的讲话和旁白。",
        )
        if picked in ("1", "2", "3"):
            self.apply_scene_speech_transform(int(picked))

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
            parsed = self.llm_api.generate_json(text, "按要求重写，只返回 JSON 对象。", expect_list=False)
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

    def _ask_scene_split(self) -> None:
        """场景拆分：直接调用语言模型，把这一场的文字拆成多场。媒体整段复制。"""
        picked = self._ask_near_choices(
            self._scene_split_btn,
            "场景拆分",
            [
                ("content", "按文字内容拆分，媒体照原样复制"),
                ("audio", "音频转录拆分，按语句切开画面和声音"),
            ],
            hint="文字拆分只改说法，每场复制原来的整段。音频转录按每句的起止，把画面和声音切开。",
        )
        if picked == "content":
            self.split_scene_content_by_llm()
        elif picked == "audio":
            self.split_scene_by_transcription()

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
            raw = self.llm_api.generate_json(text, "按要求拆开，只返回 JSON 数组。", expect_list=True)
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
            for key in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end"):
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
            start = float(segments[-1].get("start") or 0.0)
            segments[-1]["duration"] = max(0.0, full - start)
        if len(segments) < 2:
            messagebox.showinfo(title, "没有拆成多场，这一场保持原样。", parent=self.root)
            return
        pieces = self._scenes_from_transcript(scene, segments)
        if len(pieces) < 2:
            messagebox.showinfo(title, "没有拆成多场，这一场保持原样。", parent=self.root)
            return
        try:
            self._cut_transcript_scenes(pieces, video, audio)
        except Exception as exc:
            messagebox.showerror(title, f"切开失败: {exc}", parent=self.root)
            return
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
            for key in ("start", "end", "duration"):
                if key in item and item.get(key) is not None:
                    piece[key] = item.get(key)
            if "start" in item and "end" in item:
                piece.pop("narrator_audio", None)
                piece.pop("clip_audio", None)
                piece.pop("clip", None)
            for key in ("speaking_start", "speaking_end", "voiceover_start", "voiceover_end"):
                piece.pop(key, None)
            pieces.append(piece)
        return pieces

    def _cut_transcript_scenes(self, pieces: list, video: str, audio: str) -> None:
        """按每场的 start、end 切开源画面和声音，并抽出这一段的首尾图。"""
        fp = self.workflow.ffmpeg_processor
        fa = self.workflow.ffmpeg_audio_processor
        for i, item in enumerate(pieces):
            try:
                duration = float(item.get("duration") or 0.0)
                start = float(item.get("start") or 0.0)
                end = float(item.get("end") or 0.0)
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

    def import_scene_data(self):
        """从 JSON array 批量导入场景文案：array[0] 对应当前场景，依次向后覆盖同名字段。"""
        scenes = self.workflow.scenes
        if not scenes:
            messagebox.showwarning("Import", "没有可导入的场景。", parent=self.root)
            return

        self.update_current_scene()
        start_idx = self.current_scene_index

        preview_items = []
        for i in range(start_idx, min(start_idx + 8, len(scenes))):
            extracted = self._scene_import_extractable_fields(scenes[i])
            preview_items.append(extracted if extracted else {})

        if preview_items:
            initial_text = json.dumps(preview_items, ensure_ascii=False, indent=2)
        else:
            initial_text = '[\n  {\n    "speaking": "",\n    "caption": "",\n    "voiceover": ""\n  }\n]'

        dlg = tk.Toplevel(self.root)
        dlg.title("Import 场景数据")
        dlg.geometry("820x620")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() - 820) // 2
        y = (dlg.winfo_screenheight() - 620) // 2
        dlg.geometry(f"820x620+{x}+{y}")

        frame = ttk.Frame(dlg, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text=(
                f"请输入场景 JSON array（从当前场景 #{start_idx + 1} 起依次应用；"
                "同名字段覆盖：speaking / caption / voiceover / visual / actor 等）"
            ),
            font=("TkDefaultFont", 10, "bold"),
            wraplength=760,
        ).pack(anchor=tk.W, pady=(0, 5))

        text_w = scrolledtext.ScrolledText(frame, wrap=tk.WORD, width=94, height=28, font=("Consolas", 10))
        text_w.pack(fill=tk.BOTH, expand=True)
        text_w.insert(tk.END, initial_text)

        def paste_from_clipboard(_event=None):
            try:
                s = safe_clipboard_json_copy(dlg.clipboard_get())
                if s:
                    text_w.delete("1.0", tk.END)
                    text_w.insert(tk.END, s)
            except tk.TclError:
                pass

        text_w.bind("<Double-1>", paste_from_clipboard)

        holder = {"text": None, "confirmed": False}

        def on_ok():
            holder["text"] = text_w.get("1.0", tk.END).strip()
            holder["confirmed"] = True
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_row, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="导入", command=on_ok).pack(side=tk.RIGHT)
        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        dlg.wait_window()

        if not holder["confirmed"]:
            return

        raw_txt = (holder["text"] or "").strip()
        if not raw_txt:
            return

        parsed = config.parse_json_from_text(raw_txt)
        if not isinstance(parsed, list):
            messagebox.showerror(
                "Import",
                "JSON 必须是 array（例如 [{\"speaking\": \"...\"}, ...]）。",
                parent=self.root,
            )
            return
        if not parsed:
            messagebox.showwarning("Import", "JSON array 为空，未导入任何场景。", parent=self.root)
            return

        updated_scenes = 0
        updated_fields = 0
        overflow = max(0, len(parsed) - (len(scenes) - start_idx))

        for offset, item in enumerate(parsed):
            scene_idx = start_idx + offset
            if scene_idx >= len(scenes):
                break
            n = self._apply_scene_import_item(scenes[scene_idx], item)
            if n > 0:
                updated_scenes += 1
                updated_fields += n

        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()

        msg = (
            f"已从场景 #{start_idx + 1} 起导入 {min(len(parsed), len(scenes) - start_idx)} 项，"
            f"更新 {updated_scenes} 个场景、共 {updated_fields} 个字段。"
        )
        if overflow:
            msg += f"\n\n注意：JSON 有 {overflow} 项超出可用场景，已忽略。"
        messagebox.showinfo("Import", msg, parent=self.root)

    def _load_project_look_into_controls(self):
        """字体和风格记在项目上，不跟某一场走。"""
        pc = project_manager.PROJECT_CONFIG or {}
        font_key = (pc.get("title_font") or pc.get("language") or "").strip()
        if font_key not in config.FONT_LIST:
            font_key = "zh" if "zh" in config.FONT_LIST else next(iter(config.FONT_LIST))
        self.scene_language.set(font_key)
        style = config.match_visual_style(
            (pc.get("visual_style") or project_manager.LAST_VISUAL_STYLE or "")
        )
        if not style and config.VISUAL_STYLE_OPTIONS:
            style = config.VISUAL_STYLE_OPTIONS[0]
        if style:
            self.scene_visual_style.set(style)
        talk = config.normalize_dialogue_mode(pc.get("dialogue_mode") or "")
        if talk:
            self.scene_dialogue_mode.set(talk)
        region = (pc.get("setting_region") or "").strip()
        if region not in config_prompt.SETTING_PLACES:
            region = ""
        self.setting_region.set(region)
        eras = config_prompt.setting_era_labels(region)
        self.setting_era["values"] = eras
        era = (pc.get("setting_era") or "").strip()
        if era not in eras:
            era = eras[0] if eras else ""
        self.setting_era.set(era)

    def _on_setting_region_selected(self, event=None):
        """换地域后，时代只保留这一地域里的项，并选中第一项。"""
        region = (self.setting_region.get() or "").strip()
        eras = config_prompt.setting_era_labels(region)
        self.setting_era["values"] = eras
        if self.setting_era.get() not in eras:
            self.setting_era.set(eras[0] if eras else "")
        self._save_project_look()

    def _save_project_look(self, event=None):
        """把字体、风格写回项目配置。"""
        pc = project_manager.PROJECT_CONFIG
        if not isinstance(pc, dict):
            return
        font_key = (self.scene_language.get() or "").strip()
        style = (self.scene_visual_style.get() or "").strip()
        changed = False
        if font_key in config.FONT_LIST and pc.get("title_font") != font_key:
            pc["title_font"] = font_key
            changed = True
        if style and pc.get("visual_style") != style:
            pc["visual_style"] = style
            project_manager.LAST_VISUAL_STYLE = style
            changed = True
        talk = config.normalize_dialogue_mode(self.scene_dialogue_mode.get() or "")
        if talk and pc.get("dialogue_mode") != talk:
            pc["dialogue_mode"] = talk
            changed = True
        region = (self.setting_region.get() or "").strip()
        era = (self.setting_era.get() or "").strip()
        if pc.get("setting_region") != region:
            pc["setting_region"] = region
            changed = True
        if pc.get("setting_era") != era:
            pc["setting_era"] = era
            changed = True
        lang = (self.shared_language.get() or "").strip()
        if lang and pc.get("language") != lang:
            pc["language"] = lang
            if getattr(self, "workflow", None):
                self.workflow.language = lang
            changed = True
        if changed:
            save_project_config(parent=self.root)

    def update_current_scene(self, event=None):
        if getattr(self, "_scene_widgets_loading", False):
            return None
        if not getattr(self, "workflow", None):
            return None
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return None
        # 输入框还停在上一场时，不能写进已经滑到这个位置的下一场。
        bound = getattr(self, "_scene_form_scene", None)
        if bound is not None and bound is not scene:
            return None
        
        # 处理 cinematography 字段：尝试解析 JSON 字符串
        #cinematography_text = self.scene_cinematography.get("1.0", tk.END).strip()
        #cinematography_value = cinematography_text
        #if cinematography_text:
        #    try:
                # 尝试解析为 JSON 对象
        #        cinematography_value = json.loads(cinematography_text)
        #    except json.JSONDecodeError:
        #        # 如果不是有效 JSON，保持为字符串
        #        cinematography_value = cinematography_text
        ext_val = float(self.extension_var.get() or 0)
        if ext_val <= 0:
            if "extension" in scene:
                del scene["extension"]
        else:
            scene["extension"] = ext_val

        scene.update({
            "speaking": self.scene_speaking.get("1.0", tk.END).strip(),
            "actor": (self._actor_text or "").strip(),
            "visual": self.scene_visual.get("1.0", tk.END).strip(),
            "voiceover": self.scene_voiceover.get("1.0", tk.END).strip(),
            "caption": self.scene_caption.get("1.0", tk.END).strip(),

            "clip_animation": self.clip_animate.get(),
            "narration_animation": self.narration_animation.get()
        })
        scene.pop("visual_style", None)
        scene.pop("title_font", None)
        scene.pop("narrator", None)
        self.workflow.save_scenes_to_json()
        return scene


    def load_config(self):
        """加载当前项目的配置"""
        try:
            # 用户选择 YT 管理/下载时尚未创建或选择项目，PROJECT_CONFIG 为空是正常的
            if project_manager.PROJECT_CONFIG is None:
                return
            
            # 临时禁用自动保存，避免加载过程中触发保存
            self._loading_config = True
            self.apply_config_to_gui(project_manager.PROJECT_CONFIG)
            
            # 检查是否有有效PID
            saved_pid = project_manager.PROJECT_CONFIG.get('pid', '')
            if not saved_pid:
                print("⚠️ 项目配置中没有有效的PID")
                exit()

            # 同步标题到workflow
            saved_video_title = project_manager.PROJECT_CONFIG.get('video_title', '默认标题')
            if saved_video_title and saved_video_title != '默认标题':
                self.video_title.delete(0, tk.END)
                self.video_title.insert(0, saved_video_title)
                # 只在workflow已创建时设置标题
                if hasattr(self, 'workflow') and self.workflow is not None:
                    self.workflow.set_title(saved_video_title)

        except Exception as e:
            print(f"❌ 加载配置失败: {e}")
            exit()
        finally:
            # 重新启用自动保存
            self._loading_config = False


    def apply_config_to_gui(self, config_data):
        """将配置数据应用到GUI组件"""
        try:
            # 加载PID (只读标签)
            pid = config_data.get('pid', '')
            if hasattr(self, 'shared_pid'):
                self.shared_pid.config(text=pid)
                
            # 加载语言 (只读标签)
            language = config_data.get('language', 'tw')
            if hasattr(self, 'shared_language'):
                values = list(self.shared_language.cget("values") or [])
                if language and language not in values:
                    self.shared_language["values"] = [language] + values
                self.shared_language.set(language or "tw")
                
            # 加载频道 (只读标签)
            channel = config_data.get('channel', 'strange_zh')
            if hasattr(self, 'shared_channel'):
                self.shared_channel.config(text=channel)

            vw = int(config_data.get('video_width', 1920))
            vh = int(config_data.get('video_height', 1080))
            self._set_video_size_combo_values(vw, vh)
                
            # 加载视频标题
            video_title = config_data.get('video_title', '默认标题')
            if hasattr(self, 'video_title'):
                self.video_title.delete(0, tk.END)
                self.video_title.insert(0, video_title)
                
            # 加载宣传视频滚动持续时间
            promo_scroll_duration = config_data.get('promo_scroll_duration', 7.0)
            self.promo_scroll_duration = promo_scroll_duration
            
            if hasattr(self, "scene_language"):
                self._load_project_look_into_controls()
            self._refresh_narrator_button()
            print(f"✅ 已将配置应用到GUI: 频道={channel}, 语言={language}, PID={pid}")
            
        except Exception as e:
            print(f"❌ 应用配置到GUI时出错: {e}")

    def on_closing(self):
        """处理窗口关闭事件"""
        try:
            # 显示保存确认对话框
            if not self.show_save_confirmation_on_exit():
                return  # 用户取消了，不关闭应用
        
            print("🔄 正在关闭应用...")
            
            # 停止后台视频检查线程
            self.stop_video_check_thread()
            
            # 停止状态更新定时器
            if hasattr(self, 'status_update_timer_id') and self.status_update_timer_id is not None:
                self.root.after_cancel(self.status_update_timer_id)
                self.status_update_timer_id = None
            
            # 停止视频播放并释放资源
            if hasattr(self, 'video_cap') and self.video_cap:
                self.video_cap.release()
            if hasattr(self, 'video_after_id') and self.video_after_id:
                self.root.after_cancel(self.video_after_id)
                
            # 清理临时音频文件
            self.cleanup_temp_audio_files()
            
            print("✅ 应用已正常关闭")
            
        except Exception as e:
            print(f"❌ 关闭时出错: {e}")
        finally:
            self.root.destroy()
            
                
    def show_save_confirmation_on_exit(self):
        """退出时显示保存确认对话框"""
        try:
            pid = project_manager.PROJECT_CONFIG.get('pid', '未知PID')
            title = project_manager.PROJECT_CONFIG.get('video_title', '未知标题')
            
            # 检查是否有未保存的更改
            current_data = self.get_current_config_data()
            has_changes = current_data != project_manager.PROJECT_CONFIG
            
            if has_changes:
                result = messagebox.askyesnocancel(
                    "保存项目配置", 
                    f"是否保存当前项目的配置？\n\n项目: {pid}\n标题: {title}\n\n点击'是'保存并退出\n点击'否'不保存直接退出\n点击'取消'返回应用",
                    icon='question'
                )
                
                if result is None:  # 用户点击取消
                    return False  # 不关闭应用
                elif result:  # 用户点击是
                    self.save_config()
                    print(f"✅ 已保存项目配置: {pid} - {title}")
                else:  # 用户点击否
                    print(f"⚠️ 项目配置未保存: {pid} - {title}")
            else:
                print(f"📋 项目配置无变化，无需保存: {pid} - {title}")
                
            return True  # 继续关闭应用
            
        except Exception as e:
            print(f"❌ 保存确认对话框出错: {e}")
            return True  # 出错时继续关闭应用
    
    def get_current_config_data(self):
        """获取当前的配置数据（以 PROJECT_CONFIG 为基底，保留 topic_category/topic_subtype 等所有字段）"""
        config_data = (project_manager.PROJECT_CONFIG.copy() if project_manager.PROJECT_CONFIG else {})
        # 仅覆盖 GUI 可编辑的字段
        config_data.update({
            'pid': self.get_pid(),
            'language': (self.shared_language.get() or "").strip(),
            'channel': self.shared_channel.cget('text'),
            'video_title': getattr(self, 'video_title', None) and self.video_title.get() or '默认视频标题',
            'video_width': config_data.get('video_width', '1920'),
            'video_height': config_data.get('video_height', '1080'),
            'visual_style': (self.scene_visual_style.get() or "").strip() or config_data.get("visual_style"),
            'dialogue_mode': config.normalize_dialogue_mode(
                (self.scene_dialogue_mode.get() or "").strip() or config_data.get("dialogue_mode")
            ),
            'title_font': (self.scene_language.get() or "").strip() or config_data.get("title_font"),
            'setting_region': (self.setting_region.get() or "").strip(),
            'setting_era': (self.setting_era.get() or "").strip(),
        })

        # Add audio_prepares data if available
        workflow = self.workflow
        if workflow and hasattr(workflow, 'audio_prepares'):
            config_data['audio_prepares'] = workflow.video_prepares

        return config_data


    def cleanup_temp_audio_files(self):
        """清理临时音频文件"""
        try:
            import glob
            temp_files = glob.glob("temp_audio_*.wav")
            for temp_file in temp_files:
                try:
                    os.remove(temp_file)
                    print(f"🗑️ 已清理临时音频文件: {temp_file}")
                except:
                    pass
        except Exception as e:
            print(f"⚠️ 清理临时文件时出错: {e}")

    def save_config(self):
        """保存当前项目配置（以 PROJECT_CONFIG 为基底，保留 topic_category/topic_subtype 等所有字段）"""
        try:
            workflow = self.workflow
            # 以现有配置为基底，避免丢失 topic_category/topic_subtype 等
            config_data = (project_manager.PROJECT_CONFIG.copy() if project_manager.PROJECT_CONFIG else {})
            config_data.pop('debut_content', None)
            # 仅覆盖 GUI 可编辑的字段
            config_data.update({
                'pid': self.get_pid(),
                'language': (self.shared_language.get() or "").strip(),
                'channel': self.shared_channel.cget('text'),
                'video_title': getattr(self, 'video_title', None) and self.video_title.get() or '视频标题',
                'video_width': config_data.get('video_width', '1920'),
                'video_height': config_data.get('video_height', '1080'),
                'visual_style': (self.scene_visual_style.get() or "").strip() or config_data.get("visual_style"),
                'dialogue_mode': config.normalize_dialogue_mode(
                    (self.scene_dialogue_mode.get() or "").strip() or config_data.get("dialogue_mode")
                ),
                'title_font': (self.scene_language.get() or "").strip() or config_data.get("title_font"),
                'setting_region': (self.setting_region.get() or "").strip(),
                'setting_era': (self.setting_era.get() or "").strip(),
            })

            # Save audio_prepares data if available
            if workflow and hasattr(workflow, 'audio_prepares'):
                config_data['audio_prepares'] = workflow.video_prepares

            # 更新当前项目配置（统一通过 set_global_config）
            ProjectConfigManager.set_global_config(config_data)
            save_project_config(parent=self.root)
                
        except Exception as e:
            print(f"❌ 保存项目配置失败: {e}")


    def bind_scene_navigation_shortcuts(self):
        """全局：Ctrl+Shift+←/→ 上一/下一场景；Ctrl+Shift+Alt+←/→ 首/末场景。"""
        def _has_scenes():
            return getattr(self, "workflow", None) and getattr(self.workflow, "scenes", None)

        def _prev(event=None):
            if not _has_scenes():
                return
            self.prev_scene()
            return "break"

        def _next(event=None):
            if not _has_scenes():
                return
            self.next_scene()
            return "break"

        def _first(event=None):
            if not _has_scenes():
                return
            self.first_scene()
            return "break"

        def _last(event=None):
            if not _has_scenes():
                return
            self.last_scene()
            return "break"

        for seq in (
            "<Control-Shift-Left>",
            "<Control-Shift-KP_Left>",
        ):
            self.root.bind_all(seq, _prev)
        for seq in (
            "<Control-Shift-Right>",
            "<Control-Shift-KP_Right>",
        ):
            self.root.bind_all(seq, _next)
        # Alt 左右键在部分 Tk 下需写成 Alt-Control-Shift（与 Control-Shift-Alt 等价）
        for seq in (
            "<Control-Shift-Alt-Left>",
            "<Control-Shift-Alt-KP_Left>",
            "<Alt-Control-Shift-Left>",
            "<Control-Alt-Shift-Left>",
        ):
            self.root.bind_all(seq, _first)
        for seq in (
            "<Control-Shift-Alt-Right>",
            "<Control-Shift-Alt-KP_Right>",
            "<Alt-Control-Shift-Right>",
            "<Control-Alt-Shift-Right>",
        ):
            self.root.bind_all(seq, _last)


    def bind_edit_events(self):
        """绑定编辑事件"""
        # 绑定场景信息编辑字段的Enter键事件，用于自动保存
        scene_text_fields = [
            self.scene_speaking,
            self.scene_visual,
            self.scene_voiceover,
            self.scene_caption,
        ]
        for field in scene_text_fields:
            # Ctrl+Enter：保存且不插入换行
            field.bind('<Control-Return>', self.on_scene_field_enter)
            field.bind('<Control-Enter>', self.on_scene_field_enter)
            # Enter：立即写回场景与 JSON，并保留默认换行
            field.bind('<Return>', self.on_scene_field_return_commit)
            field.bind('<KP_Enter>', self.on_scene_field_return_commit)
            field.bind('<FocusOut>', self.on_scene_field_focus_out)

        for field in (self.shared_language, self.scene_visual_style, self.scene_dialogue_mode, self.scene_language, self.setting_era):
            field.bind("<<ComboboxSelected>>", self._save_project_look)
            field.bind("<FocusOut>", self._save_project_look)
        self.setting_region.bind("<<ComboboxSelected>>", self._on_setting_region_selected)
        self.setting_region.bind("<FocusOut>", self._save_project_look)
        
        # 讲话：仅在此框 — Ctrl+S 拆分克隆；Ctrl+←/→ 移动片段；Ctrl+M 合并下一场景讲话并删下一场景（仅讲话，不碰音视频）
        self.scene_speaking.bind("<Control-s>", self._on_speaking_ctrl_s_split_clone)
        self.scene_speaking.bind("<Control-S>", self._on_speaking_ctrl_s_split_clone)
        self.scene_speaking.bind("<Control-Right>", self._on_speaking_ctrl_right_move_tail_to_next)
        self.scene_speaking.bind("<Control-Left>", self._on_speaking_ctrl_left_move_head_to_prev)
        self.scene_speaking.bind("<Control-m>", self._on_speaking_ctrl_m_merge_next_speaking)
        self.scene_speaking.bind("<Control-M>", self._on_speaking_ctrl_m_merge_next_speaking)
        for seq in ("<Control-Shift-Left>", "<Control-Shift-KP_Left>"):
            self.scene_speaking.bind(seq, self._on_speaking_ctrl_shift_nav_prev)
        for seq in ("<Control-Shift-Right>", "<Control-Shift-KP_Right>"):
            self.scene_speaking.bind(seq, self._on_speaking_ctrl_shift_nav_next)
        for _w in (self.scene_speaking, self.scene_voiceover):
            _w.bind("<Insert>", self._on_scene_insert_silence_marker)

        print("📝 已绑定场景编辑字段：Enter 立即保存；Ctrl+Enter 保存不换行；失焦 500ms 防抖保存；讲话 Ctrl+S/←/→/M；讲话/旁白 Insert→静音菜单")
    


    def bind_config_change_events(self):
        """绑定配置变化事件"""
        # PID, 语言和频道现在都是只读的，不需要绑定变化事件
            
        # 绑定video_title变化事件
        if hasattr(self, 'video_title'):
            self.video_title.bind('<KeyRelease>', self.on_video_title_change)
            self.video_title.bind('<FocusOut>', self.on_video_title_change)


    def on_video_title_change(self, event=None):
        """当视频标题发生变化时的回调函数"""
        # 如果正在加载配置，不要自动保存
        gui_title = self.video_title.get().strip()
        if gui_title and gui_title != "......":
            gui_title = config.chinese_convert(gui_title, self.workflow.language)
            self.workflow.title = gui_title
            print(f"🏷️ Workflow title updated: {gui_title}")
            # save summary to project_manager.PROJECT_CONFIG
            project_manager.PROJECT_CONFIG["video_title"] = gui_title
            self.save_config()


    def on_config_change(self, event=None):
        """当配置发生变化时的回调函数"""
        # 如果正在加载配置，不要自动保存
        if hasattr(self, '_loading_config') and self._loading_config:
            return
        
        self.save_config()

    def on_scene_edit(self, event=None):
        """当场景信息被编辑时的回调（现在不需要）"""
        # 保存按钮现在总是可用
        pass


    def on_scene_field_enter(self, event=None):
        """当在场景编辑字段中按下Ctrl+Enter时的回调"""
        # 保存当前场景信息到JSON并传播到相同raw_scene_index的场景
        self.update_current_scene()
        return "break"  # 阻止默认的换行行为

    def _cancel_scene_debounce_timer(self):
        tid = getattr(self, "_save_timer", None)
        if tid:
            try:
                self.root.after_cancel(tid)
            except (ValueError, tk.TclError):
                pass
        self._save_timer = None

    def on_scene_field_return_commit(self, event=None):
        """多行文本框内按 Enter：立即写回当前场景与 JSON（仍插入换行）。"""
        if getattr(self, "_scene_widgets_loading", False):
            return
        if not getattr(self, "workflow", None) or not self.workflow.scenes:
            return
        self._cancel_scene_debounce_timer()
        self.update_current_scene()

    def on_scene_combobox_return_commit(self, event=None):
        """下拉框按 Enter：立即写回当前场景与 JSON。"""
        if getattr(self, "_scene_widgets_loading", False):
            return
        if not getattr(self, "workflow", None) or not self.workflow.scenes:
            return
        self._cancel_scene_debounce_timer()
        self.update_current_scene()

    def on_scene_field_focus_out(self, event=None):
        """当场景编辑字段失去焦点时的回调"""
        # 延迟保存以避免频繁操作（仅取消有效的 after id，避免 None/已失效 id 触发 ValueError）
        self._cancel_scene_debounce_timer()
        self._save_timer = self.root.after(500, lambda: self.update_current_scene())


    def on_tab_changed(self, event):
        if not hasattr(self, 'workflow') or self.workflow is None:
            return
        self.refresh_gui_scenes()


    def setup_drag_and_drop(self):
        self.video_canvas.drop_target_register(DND_FILES)
        self.video_canvas.dnd_bind('<<Drop>>', self.on_media_drop)
        self.video_canvas.dnd_bind('<<DragEnter>>', self.on_video_drag_enter)
        self.video_canvas.dnd_bind('<<DragLeave>>', self.on_video_drag_leave)


    def handle_image_replacement(self, source_image_path):
        """处理图像替换"""
        try:
            # 导入图像区域选择对话框
            from gui.image_area_selector_dialog import show_image_area_selector
            # 显示图像区域选择对话框
            selected_image_path, vertical_line_position, target_field = show_image_area_selector(
                self, source_image_path, self.workflow.ffmpeg_processor.width, self.workflow.ffmpeg_processor.height
            )
            
            if selected_image_path is None:
                return  # 用户取消了选择
            
            field_names = {
                "clip_image": "当前场景图片",
                "clip_image_last": "最后场景图片"
            }
            
            dialog = messagebox.askyesno("确认替换场景的图像/视频", 
                                       f"确定要替换 {field_names.get(target_field, target_field)} 吗？\n垂直分割线位置: {vertical_line_position}")
            if not dialog:
                # 清理临时文件
                try:
                    os.remove(selected_image_path)
                except:
                    pass
                return
            
            selected_image_path = self.workflow.ffmpeg_processor.resize_image_smart(selected_image_path)

            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            self.workflow.replace_scene_image(current_scene, selected_image_path, vertical_line_position, target_field)
            
            # 刷新GUI显示
            self.refresh_gui_scenes()
            
            # 记录操作
            print(f"✅ 图像已替换到 {field_names.get(target_field, target_field)}，垂直分割线位置: {vertical_line_position}")
            
        except Exception as e:
            messagebox.showerror("错误", f"图像替换失败: {str(e)}")


    # 视频拖拽相关方法
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

    def split_current_group(self):
        """从当前场景起，把连续的同一集划成新的一集。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("拆集", "请先选中一个场景。", parent=self.root)
            return
        new_name = self.workflow.split_group_at(self.current_scene_index)
        if not new_name:
            return
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        show_auto_close_popup(self.root, "拆集", f"从当前场景起为第 {new_name} 集")

    def _on_media_drop_pdf(self, pdf_path: str) -> None:
        """视频画布拖入 PDF：按当前 episode 拆成 1.webp、2.webp…，再打开翻页预览。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("PDF", "请先选中一个场景。", parent=self.root)
            return
        group_name = self.workflow.scene_group(scene)
        if not str(scene.get("episode") or "").strip():
            scene["episode"] = group_name
            scene.pop("group", None)
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            folder, pages = self.workflow.export_pdf_pages_to_group(pdf_path, group_name)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("PDF", f"拆分失败：{e}", parent=self.root)
            return
        finally:
            try:
                self.root.config(cursor="")
            except tk.TclError:
                pass
        if not pages:
            messagebox.showwarning("PDF", "这份 PDF 没有拆出页面。", parent=self.root)
            return
        print(f"✅ PDF 已拆成 {len(pages)} 页：{folder}")
        self._open_pdf_page_review(folder, pages, group_name, os.path.basename(pdf_path))

    def _episode_page_pngs(self, group_name: str) -> list[str]:
        """media/<episode>/ 里按页码排好的页面图。"""
        return self.workflow._episode_png_paths(group_name)

    def _resolve_scene_episode_pdf(self, scene: dict) -> str:
        """当前场景 episode_pdf 指向的文件。找不到就返回空。"""
        name = str(scene.get("episode_pdf") or "").strip()
        if not name:
            return ""
        if os.path.isfile(name):
            return os.path.abspath(name)
        base = os.path.basename(name)
        group_name = self.workflow.scene_group(scene)
        media = config.get_media_path(self.workflow.pid)
        gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
        candidates = [
            os.path.join(gen_dir, base) if gen_dir else "",
            os.path.join(media, group_name, base),
            os.path.join(media, base),
        ]
        pc = project_manager.PROJECT_CONFIG
        slide = (pc.get("slide") or "").strip() if isinstance(pc, dict) else ""
        if slide and os.path.basename(slide) == base:
            candidates.append(slide)
        for path in candidates:
            if path and os.path.isfile(path):
                return os.path.abspath(path)
        return ""

    def _scenes_as_prompt_content(self, scenes: list, episode_name: str) -> str:
        """把这一集（或一场）的场景描述收成提示词材料，不带媒体路径。"""
        fields = ("caption", "visual", "speaking", "voiceover", "actor")
        blocks = [f"Episode {episode_name}. {len(scenes)} scene(s)."]
        for i, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            lines = [f"Scene {i}"]
            for key in fields:
                text = str(scene.get(key) or "").strip()
                if text:
                    lines.append(f"{key}: {text}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks).strip()

    def _episode_pdf_for_prompt(self, scene: dict) -> str:
        group_name = self.workflow.scene_group(scene)
        generated = self.workflow.episode_pdf_path(group_name)
        if os.path.isfile(generated):
            return generated
        return self._resolve_scene_episode_pdf(scene)

    def _ask_episode_prompt(self, choices: list, materials: list) -> tuple[str, str] | None:
        """一个窗口里选提示词，材料用下拉框，默认这一集的内容。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("拷贝哪一种提示词？")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()
        result: list = [None]
        material_labels = [label for _, label in materials]
        material_by_label = {label: key for key, label in materials}

        main = ttk.Frame(dlg, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main, text="拷贝哪一种提示词？", font=("Arial", 12, "bold")).pack(pady=(4, 10))

        mat_row = ttk.Frame(main)
        mat_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(mat_row, text="材料").pack(side=tk.LEFT, padx=(0, 8))
        material_var = tk.StringVar(value=material_labels[0])
        ttk.Combobox(
            mat_row,
            textvariable=material_var,
            values=material_labels,
            state="readonly",
            width=22,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def on_choice(label: str):
            result[0] = (label, material_by_label.get(material_var.get(), materials[0][0]))
            dlg.destroy()

        for choice_label, _template in choices:
            ttk.Button(
                main,
                text=choice_label,
                width=36,
                command=lambda lb=choice_label: on_choice(lb),
            ).pack(pady=3, fill=tk.X)
        ttk.Button(main, text="取消", width=16, command=dlg.destroy).pack(pady=(12, 4))

        dlg.update_idletasks()
        width = max(420, dlg.winfo_reqwidth())
        height = dlg.winfo_reqheight()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dlg.geometry(f"{width}x{height}+{x}+{y}")
        dlg.wait_window()
        return result[0]

    def copy_episode_prompt(self):
        """按频道里的场景提示词，用这一集的文字或 PDF 填好，拷到剪贴板。"""
        from gui.downloader import (
            _format_nb_prompt_template,
            _pdf_pages_as_scene_source,
            _prompt_choice_entries,
            _prompt_text_for_material,
        )

        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("拷提", "请先选中一个场景。", parent=self.root)
            return
        pc = project_manager.PROJECT_CONFIG or {}
        channel = (pc.get("channel") or getattr(self.workflow, "channel", "") or "").strip()
        choices = _prompt_choice_entries(channel)
        if not choices:
            messagebox.showwarning("拷提", "这个频道没有场景提示词。", parent=self.root)
            return
        materials = [
            ("episode_text", "这一集的内容"),
            ("scene_text", "当前场景的文字"),
            ("pdf", "这一集的 PDF"),
        ]
        picked = self._ask_episode_prompt(choices, materials)
        if not picked:
            return
        label, kind = picked
        template = ""
        for choice_label, choice_template in choices:
            if choice_label == label:
                template = choice_template
                break
        if not template:
            return
        group_name = self.workflow.scene_group(scene)
        if kind == "scene_text":
            content = self._scenes_as_prompt_content([scene], group_name)
        elif kind == "pdf":
            pdf_path = self._episode_pdf_for_prompt(scene)
            content, _page_count, _ = _pdf_pages_as_scene_source(pdf_path)
            if not content:
                messagebox.showwarning("拷提", "这一集没有可引用的 PDF。", parent=self.root)
                return
        else:
            indices = self.workflow.group_scene_indices(group_name)
            episode_scenes = [
                self.workflow.scenes[i]
                for i in indices
                if 0 <= i < len(self.workflow.scenes)
            ]
            content = self._scenes_as_prompt_content(episode_scenes, group_name)
        if not content:
            messagebox.showwarning("拷提", "这一集没有可拷贝的场景文字。", parent=self.root)
            return
        ch_cfg = config.get_channel_config(channel) or {}
        topic = (pc.get("topic") or ch_cfg.get("topic") or "").strip()
        narrator = (pc.get("narrator") or "").strip()
        language = config.llm_language_label(
            getattr(self.workflow, "language", "") or pc.get("language") or ""
        )
        prompt = _format_nb_prompt_template(
            template,
            content=content,
            instruction="",
            language=language,
            topic=topic,
            narrator=narrator,
        )
        if kind == "pdf":
            prompt = _prompt_text_for_material(prompt, "pdf")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt)
            self.root.update_idletasks()
        except tk.TclError:
            messagebox.showwarning("拷提", "没能写入剪贴板。", parent=self.root)
            return
        show_auto_close_popup(self.root, "拷提", f"已拷贝提示词：{label}")

    def paste_episode_scenes(self):
        """把剪贴板里的场景 JSON 合并回这一集。只覆盖 JSON 里有的文案字段。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("贴回", "请先选中一个场景。", parent=self.root)
            return
        try:
            raw = safe_clipboard_json_copy(self.root.clipboard_get())
        except tk.TclError:
            raw = ""
        parsed = config.parse_json_from_text(raw) if raw else None
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list) or not parsed or not all(isinstance(item, dict) for item in parsed):
            messagebox.showwarning(
                "贴回",
                "剪贴板里不是场景 JSON。需要一个场景对象，或一组场景。",
                parent=self.root,
            )
            return
        picked = askchoice(
            "贴回到哪里？只覆盖 JSON 里有的字段，图片和声音留着。",
            [
                ("from_start", "从本集开头写入"),
                ("from_here", "从当前场景往后"),
            ],
            self.root,
        )
        if not picked:
            return
        self.update_current_scene()
        group_name = self.workflow.scene_group(scene)
        indices = self.workflow.group_scene_indices(group_name)
        if picked[1] == "from_here":
            indices = [i for i in indices if i >= self.current_scene_index]
        if not indices:
            messagebox.showwarning("贴回", "这一集没有可写入的场景。", parent=self.root)
            return
        keep = self._SCENE_IMPORT_SKIP_KEYS | {
            "id",
            "episode",
            "group",
            "episode_page",
            "episode_pdf",
            "group_page",
            "group_pdf",
            "clip",
            "zero",
            "narration",
            "background_music",
        }
        written = 0
        fields = 0
        for offset, item in enumerate(parsed):
            if offset >= len(indices):
                break
            cleaned = {
                key: val
                for key, val in item.items()
                if key not in keep and not str(key).endswith(("_image", "_audio", "_last"))
            }
            n = self._apply_scene_import_item(self.workflow.scenes[indices[offset]], cleaned)
            if n:
                written += 1
                fields += n
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()
        used = min(len(parsed), len(indices))
        extra = len(parsed) - used
        msg = f"写入了 {used} 场，覆盖了 {fields} 个字段。"
        if extra > 0:
            msg += f" 剪贴板里还有 {extra} 场没有落下去，这一集后面没有空位了。"
        messagebox.showinfo("贴回", msg, parent=self.root)

    def copy_current_episode_pdf(self):
        """拷贝这一集的 PDF。有页面图时才在这里合成；文件夹时间和 PDF 一致就直接拷。"""
        from gui.downloader import _copy_file_to_clipboard_hdrop

        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            return
        group_name = self.workflow.scene_group(scene)
        pngs = self.workflow._episode_png_paths(group_name)
        rebuilt = False
        if pngs:
            pdf_path = self.workflow.episode_pdf_path(group_name)
            if not self.workflow.episode_pdf_is_current(group_name):
                try:
                    self.root.config(cursor="watch")
                    self.root.update_idletasks()
                    pdf_path = self.workflow.build_episode_pdf(group_name)
                    rebuilt = True
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("拷集", f"合成 PDF 失败：{e}", parent=self.root)
                    return
                finally:
                    try:
                        self.root.config(cursor="")
                    except tk.TclError:
                        pass
        else:
            pdf_path = self._resolve_scene_episode_pdf(scene)
        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showwarning("拷集", "这一集没有可拷贝的 PDF。", parent=self.root)
            return
        if _copy_file_to_clipboard_hdrop(self.root, pdf_path):
            note = "已重新生成并拷贝" if rebuilt else "已拷贝"
            show_auto_close_popup(
                self.root,
                "拷集",
                f"{note}这一集的 PDF：\n{os.path.basename(pdf_path)}",
            )

    def _assign_scene_clip_image_from_file(self, scene: dict, image_path: str) -> None:
        """把已经拆好的页图拷到场景的 clip_image，不缩放、不转格式。"""
        ext = os.path.splitext(image_path)[1].lower() or ".webp"
        refresh_scene_media(scene, "clip_image", ext, image_path, True)

    def _tag_scene_pdf_page(self, scene: dict, group_name: str, page_no: int, pdf_name: str) -> None:
        scene["episode"] = group_name
        scene["episode_page"] = int(page_no)
        scene["episode_pdf"] = pdf_name
        scene.pop("group", None)
        scene.pop("group_page", None)
        scene.pop("group_pdf", None)

    def _open_pdf_page_review(
        self,
        folder: str,
        pages: list[str],
        group_name: str,
        pdf_name: str,
        initial_index: int = 0,
    ) -> None:
        """翻页查看拆出的 PNG。左右方向键翻页；从当前页写到本集结束。"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"PDF 页面 · 第 {group_name} 集")
        dlg.geometry("980x800")
        dlg.minsize(720, 560)
        dlg.transient(self.root)
        idx = [max(0, min(int(initial_index or 0), len(pages) - 1))]
        photo_holder: list = [None]
        showing = [False]

        canvas = tk.Canvas(dlg, bg="#222", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        status = ttk.Label(dlg, text="", anchor="w")
        status.pack(fill=tk.X, padx=8, pady=(6, 2))
        path_lbl = ttk.Label(dlg, text=folder, anchor="w")
        path_lbl.pack(fill=tk.X, padx=8)

        def _scene_label() -> str:
            n = len(self.workflow.group_scene_indices(group_name))
            return f"第 {group_name} 集 · {pdf_name} · 本集 {n} 个场景"

        def _show_page(_event=None):
            if showing[0] or not dlg.winfo_exists():
                return
            showing[0] = True
            try:
                _show_page_body()
            finally:
                showing[0] = False

        def _show_page_body():
            i = idx[0]
            path = pages[i]
            try:
                img = Image.open(path).convert("RGB")
            except Exception as e:  # noqa: BLE001
                status.config(text=f"无法打开 {os.path.basename(path)}：{e}")
                return
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()
            if cw < 80 or ch < 80:
                cw, ch = 900, 560
            iw, ih = img.size
            scale = min(cw / iw, ch / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            img = img.resize((nw, nh), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            photo_holder[0] = photo
            canvas.delete("all")
            canvas.create_image(cw // 2, ch // 2, image=photo)
            status.config(text=f"第 {i + 1} / {len(pages)} 页   {os.path.basename(path)}    {_scene_label()}")

        def _step(delta: int):
            idx[0] = (idx[0] + delta) % len(pages)
            _show_page()

        def _assign_current():
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not scene:
                messagebox.showwarning("PDF", "请先在主窗口选中一个场景。", parent=dlg)
                return
            page_no = idx[0] + 1
            try:
                self._assign_scene_clip_image_from_file(scene, pages[idx[0]])
                self._tag_scene_pdf_page(scene, group_name, page_no, pdf_name)
                self.workflow.save_scenes_to_json()
                self.display_image_on_canvas_for_track("clip_image")
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("PDF", f"写入 clip_image 失败：{e}", parent=dlg)
                return
            show_auto_close_popup(
                dlg, "PDF", f"第 {page_no} 页已写入当前场景（第 {group_name} 集）"
            )
            _show_page()

        def _assign_forward():
            """从正在看的这一页起，写入当前场景和本集后面的场景。场数不改。"""
            scene_i = self.current_scene_index
            if scene_i < 0 or scene_i >= len(self.workflow.scenes):
                messagebox.showwarning("PDF", "请先在主窗口选中一个场景。", parent=dlg)
                return
            page_i = idx[0]
            written = 0
            first_page = page_i + 1
            try:
                while scene_i < len(self.workflow.scenes) and page_i < len(pages):
                    scene = self.workflow.scenes[scene_i]
                    if not isinstance(scene, dict) or self.workflow.scene_group(scene) != group_name:
                        break
                    self._assign_scene_clip_image_from_file(scene, pages[page_i])
                    self._tag_scene_pdf_page(scene, group_name, page_i + 1, pdf_name)
                    written += 1
                    scene_i += 1
                    page_i += 1
                self.workflow.save_scenes_to_json()
                self.display_image_on_canvas_for_track("clip_image")
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("PDF", f"写入 clip_image 失败：{e}", parent=dlg)
                return
            last_page_no = first_page + written - 1 if written else first_page
            show_auto_close_popup(
                dlg,
                "PDF",
                f"从第 {first_page} 页起，写入了当前场景及本集后面共 {written} 场"
                + (f"（到第 {last_page_no} 页）" if written else ""),
            )
            _show_page()

        bar = ttk.Frame(dlg)
        bar.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(bar, text="上一页", command=lambda: _step(-1)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="下一页", command=lambda: _step(1)).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Button(bar, text="当前页 → 当前场景", command=_assign_current).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="写到本集结束", command=_assign_forward).pack(side=tk.LEFT)

        def _on_left(_event=None):
            _step(-1)
            return "break"

        def _on_right(_event=None):
            _step(1)
            return "break"

        dlg.bind_all("<Left>", _on_left)
        dlg.bind_all("<Right>", _on_right)

        def _release_keys(_event=None):
            try:
                dlg.unbind_all("<Left>")
                dlg.unbind_all("<Right>")
            except tk.TclError:
                pass

        dlg.bind("<Destroy>", _release_keys)
        canvas.bind("<Configure>", _show_page)
        dlg.after(50, _show_page)
        dlg.after(80, canvas.focus_set)

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


    def on_video_canvas_configure(self, event):
        """当video canvas尺寸改变时，动态调整提示文本位置"""
        canvas_width = event.width
        canvas_height = event.height
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        
        # 更新拖拽提示文本的位置到canvas中心
        self.video_canvas.coords("drag_hint", center_x, center_y)


    def on_clip_animation_change(self, event=None):
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        current_scene["clip_animation"] = self.clip_animate.get()
        self.workflow.save_scenes_to_json()


    def on_scene_field_change(self, field_name, field_value, event=None):
        self.workflow.get_scene_by_index(self.current_scene_index)[field_name] = field_value 
        self.workflow.save_scenes_to_json()


    def on_narration_animation_change(self, event=None):
        """处理图像类型选择变化"""
        self.workflow.get_scene_by_index(self.current_scene_index)["narration_animation"] = self.narration_animation.get()
        # 标记配置已更改
        self._config_changed = True

    def _on_extension_change(self):
        """延长秒数变化：0 则不写 extension 字段，否则写入 float"""
        if not self.workflow.scenes or self.current_scene_index >= len(self.workflow.scenes):
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        val = float(self.extension_var.get() or 0)

        def _apply_extension_to_scene(target, ext_val):
            if ext_val <= 0:
                if "extension" in target:
                    del target["extension"]
            else:
                target["extension"] = ext_val

        story_scenes = self.workflow.scenes_in_story(scene)
        if len(story_scenes) > 1:
            if messagebox.askyesno(
                "延长秒数",
                "是否将本延长秒数设置应用到当前故事的全部场景？\n"
                "选择「否」则仅修改当前场景。",
                parent=self.root,
            ):
                for s in story_scenes:
                    _apply_extension_to_scene(s, val)
            else:
                _apply_extension_to_scene(scene, val)
        else:
            _apply_extension_to_scene(scene, val)

        self.workflow.save_scenes_to_json()


    def generate_video(self, scene, previous_scene, next_scene, track):
        image_path = get_file_path(scene, track+"_image")
        image_last_path = get_file_path(scene, track+"_image_last")
        next_sound_path = get_file_path(next_scene, track+"_audio")
        sound_path = get_file_path(scene, track+"_audio")
        if not sound_path:
            return

        animate_mode = scene.get(track+"_animation", "S2V")
        if animate_mode not in config_prompt.ANIMATE_SOURCE or animate_mode.strip() == "":
            return

        wan_prompt = scene.get(track+"_prompt", "")
        
        # 如果 wan_prompt 是字符串（JSON格式），尝试解析为字典
        if isinstance(wan_prompt, str) and wan_prompt.strip():
            try:
                wan_prompt = json.loads(wan_prompt)
            except:
                print("none json wan_prompt")
        
        # 检查 prompt 是否为空（支持字符串和字典两种格式）
        if not wan_prompt or (isinstance(wan_prompt, str) and wan_prompt.strip() == "") or (isinstance(wan_prompt, dict) and len(wan_prompt) == 0):
            #wan_prompt = self.workflow.build_prompt(scene, "", track, animate_mode, False)
            wan_prompt = "..."
            scene[track+"_prompt"] = wan_prompt

        action_path = get_file_path(scene, self.selected_secondary_track)

        self.workflow.rebuild_scene_video(scene, track, animate_mode, image_path, image_last_path, sound_path, next_sound_path, action_path, wan_prompt)
        self.workflow.save_scenes_to_json()


    def regenerate_video(self, track, prompt_only):
        """打开 WAN 提示词编辑对话框并生成主轨道视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        
        # 定义生成视频的回调函数
        def generate_callback(scene, wan_prompt):
            scene[track+"_prompt"] = wan_prompt
            # 使用编辑后的 prompt 生成视频
            if not prompt_only:
                if track == "clip":
                    new_scenes = self.workflow.split_smart_scene(scene)
                    if new_scenes is None:
                        return
                    if len(new_scenes) > 1:
                        for s in new_scenes:
                            generate_callback(s, wan_prompt)
                    else:
                        previous_scene = self.workflow.get_previous_scene(self.current_scene_index)
                        next_scene = self.workflow.get_next_scene(self.current_scene_index)
                        self.generate_video(scene, previous_scene, next_scene, track)
                else:
                    previous_scene = self.workflow.get_previous_scene(self.current_scene_index)
                    next_scene = self.workflow.get_next_scene(self.current_scene_index)
                    self.generate_video(scene, previous_scene, next_scene, track)

            self.workflow.save_scenes_to_json()

            self.playing_delta = 0.0
            self.playing_delta_label.config(text=f"{self.playing_delta:.1f}s")
            self.refresh_gui_scenes()
        
        # 显示编辑对话框
        show_wan_prompt_editor(self, self.workflow, generate_callback, current_scene, track)
 


def open_narrator_portrait(parent, current: str, on_confirm) -> None:
    """主题列表里选讲员：用工作流同一套头像预览，选定后交给调用方保存。"""
    host = WorkflowGUI.__new__(WorkflowGUI)
    host.root = parent
    host.review_project_narrator(current=current, on_confirm=on_confirm, parent=parent)


def main():
    import sys
    root = TkinterDnD.Tk()

    initial_pid = None
    if len(sys.argv) >= 4 and sys.argv[1] == "--open-from-list-json":
        list_path = sys.argv[2]
        try:
            idx = int(sys.argv[3])
        except ValueError:
            messagebox.showerror("启动错误", "--open-from-list-json 需要整数 index")
            root.destroy()
            return
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                arr = json.load(f)
            if not isinstance(arr, list) or idx < 0 or idx >= len(arr):
                raise ValueError("index 超出列表范围")
            item = arr[idx]
            cfg = project_config_from_list_item(item, os.path.normpath(list_path), idx)
            ProjectConfigManager.set_global_config(cfg)
            initial_pid = (cfg or {}).get("pid")
            if not initial_pid:
                raise ValueError("列表项中无有效 pid / project_profile")
        except Exception as e:
            try:
                messagebox.showerror("启动错误", f"无法从频道列表项载入项目：{e}")
            except Exception:
                pass
            root.destroy()
            return
    elif len(sys.argv) >= 3 and sys.argv[1] == '--open-pid':
        initial_pid = sys.argv[2]

    try:
        app = WorkflowGUI(root, initial_pid=initial_pid)
        root.mainloop()
    except Exception as e:
        import traceback
        try:
            messagebox.showerror("启动错误", f"启动失败: {e}\n\n详见终端输出")
        except Exception:
            pass
        print(traceback.format_exc())
        raise

if __name__ == "__main__":
    main()

