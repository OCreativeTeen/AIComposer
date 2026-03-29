import matplotlib
matplotlib.use('Agg')  # Must be at the TOP of main.py

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.scrolledtext as scrolledtext
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import os
import json
import threading
import time
from datetime import datetime
from io import BytesIO
import pygame
import uuid
from magic_workflow import MagicWorkflow
import config
import config_channel
import config_prompt
from PIL import Image, ImageTk
from project_manager import ProjectConfigManager, create_project_dialog, refresh_scene_media
import project_manager
from gui.picture_in_picture_dialog import PictureInPictureDialog
import cv2
import os
from utility.file_util import get_file_path, is_video_file, check_folder_files, safe_copy_overwrite, make_safe_file_name
from gui.media_review_dialog import AVReviewDialog
#from utility.minimax_speech_service import MinimaxSpeechService, EXPRESSION_STYLES
from utility.voicebox_speech_service import VoiceboxService, EXPRESSION_STYLES
from gui.wan_prompt_editor_dialog import show_wan_prompt_editor  # 添加这一行
import tkinterdnd2 as TkinterDnD
from tkinterdnd2 import DND_FILES
from utility.media_scanner import MediaScanner
import utility.llm_api as llm_api
from gui.downloader import MediaGUIManager
from gui.suno_music_prompt_gui import SunoMusicPromptGUI
import cv2
import json
import shutil
from pathlib import Path
from gui.choice_dialog import askchoice, askchoice_media_preview



STANDARD_FPS = 60  # Match FfmpegProcessor.STANDARD_FPS


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
        self.current_scene_index = 0

        self.llm_api = llm_api.LLMApi(llm_api.LM_STUDIO)

        # 显示项目选择对话框（或 --open-pid 时直接加载指定项目）
        if initial_pid:
            # 从 YT「用Story启动新项目」创建后启动：跳过欢迎屏，直接加载项目
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
        if selection_result == 'yt':
            # 用户选择了 YT 管理/下载，主界面不打开，只保留根窗口供 YT 子窗口使用
            self.root.withdraw()  # 隐藏根窗口，仅显示 YT 子窗口
            return
        
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
        
        # 添加视频效果选择存储
        self.effect_radio_vars = {}  # {scene_index: tk.StringVar}
        
        # 添加当前效果和图像类型选择变量
        self.narration_animation = tk.StringVar(value=config_prompt.ANIMATE_SOURCE[0])
        
        # 创建动画名称到提示语的映射字典（双向）
        self.animation_name_to_prompt = {item["name"]: item["prompt"] for item in config_prompt.ANIMATION_PROMPTS}
        self.animation_prompt_to_name = {item["prompt"]: item["name"] for item in config_prompt.ANIMATION_PROMPTS}
        self.animation_names = [""] + list(self.animation_name_to_prompt.keys())
        
        # 添加旁白轨道音量控制变量
        self.track_volume_var = tk.DoubleVar(value=0.2)
        
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
            self.speech_service = VoiceboxService(self.get_pid())
            
            current_gui_title = self.video_title.get().strip()
            self.workflow.post_init(current_gui_title)
            
            # 初始化YouTube GUI管理器
            self.youtube_gui = MediaGUIManager(
                self.root, 
                config.get_channel_path(config_channel.get_channel_id(channel)),  # 传入项目路径（按 channel_id）
                self.get_pid(), 
                self.tasks, 
                self.log_to_output, 
                self.video_output,  # 使用video_output作为YouTube下载日志输出
                language or "tw",
            )
            
            print("✅ 工作流实例创建完成")
            
        except Exception as e:
            print(f"❌ 创建工作流实例失败: {e}")
            self.workflow = None


    def show_project_selection(self):
        # 使用新的项目管理器
        result, selected_config = create_project_dialog(self.root, youtube_gui=getattr(self, 'youtube_gui', None))
        
        if result == 'cancel':
            return False
        elif result == 'yt':
            # 用户选择了 YT 管理/下载，主界面不打开，只保留根窗口供 YT 子窗口使用
            return 'yt'
        elif result == 'new':
            # 立即创建ProjectConfigManager并保存新项目配置
            pid = selected_config.get('pid')
            try:
                # 先设置全局 project_manager.PROJECT_CONFIG
                ProjectConfigManager.set_global_config(selected_config)
                # 然后创建 ProjectConfigManager 并保存
                config_manager = ProjectConfigManager(pid)
                config_manager.save_project_config(selected_config)
                print(f"✅ 新项目配置已保存: {pid}")
            except Exception as e:
                print(f"❌ 保存新项目配置失败: {e}")
            
            return True
        elif result == 'open':
            # 打开现有项目
            if selected_config is None:
                print("❌ 错误：selected_config 为 None")
                return False
            # 注意：project_manager.PROJECT_CONFIG 已经在 open_selected() 中设置了，这里再次确认设置
            ProjectConfigManager.set_global_config(selected_config)
            return True
        
        return False

   
    def create_shared_info_area(self, parent):
        """创建共享信息区域"""
        shared_frame = ttk.LabelFrame(parent, text="共享配置", padding=10)
        shared_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 第一行：基本项目配置
        row1_frame = ttk.Frame(shared_frame)
        row1_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(row1_frame, text="⏮", width=3, command=self.first_scene).pack(side=tk.LEFT, padx=2)
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Label(row1_frame, text="场景:").pack(side=tk.LEFT)
        ttk.Button(row1_frame, text="◀", width=3, command=self.prev_scene).pack(side=tk.LEFT, padx=2)
        self.scene_label = ttk.Label(row1_frame, text="0 / 0", width=7)
        self.scene_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(row1_frame, text="▶", width=3, command=self.next_scene).pack(side=tk.LEFT, padx=2)
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(row1_frame, text="⏭", width=3, command=self.last_scene).pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(row1_frame, text="拷贝图",   command=self.copy_lastimage_to_next).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1_frame, text="场景交换", command=self.swap_scene).pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)

        pid_frame = ttk.Frame(row1_frame)
        pid_frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(pid_frame, text="PID").pack(side=tk.LEFT)
        self.shared_pid = ttk.Label(pid_frame, width=20, relief="sunken", background="white")
        self.shared_pid.pack(side=tk.LEFT, padx=(5, 0))
        
        # 语言组 (只读)
        lang_frame = ttk.Frame(row1_frame)
        lang_frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(lang_frame, text="语言").pack(side=tk.LEFT)
        self.shared_language = ttk.Label(lang_frame, width=5, relief="sunken", background="white")
        self.shared_language.pack(side=tk.LEFT, padx=(5, 0))
        
        # 视频标题组
        title_frame = ttk.Frame(row1_frame)
        title_frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(title_frame, text="标题").pack(side=tk.LEFT)
        self.video_title = ttk.Entry(title_frame, width=20)
        self.video_title.pack(side=tk.LEFT)
        ttk.Label(title_frame, text="频道").pack(side=tk.LEFT)
        self.shared_channel = ttk.Label(title_frame, width=15, relief="sunken", background="white")
        self.shared_channel.pack(side=tk.LEFT)
        
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)

        #ttk.Button(row1_frame, text="视频合成", command=lambda:self.run_finalize_video()).pack(side=tk.LEFT, padx=2)
        #ttk.Button(row1_frame, text="视背合成", command=lambda:self.run_finalize_video(zero_audio_only=True)).pack(side=tk.LEFT, padx=2)
        #ttk.Button(row1_frame, text="推广合成", command=lambda:self.run_promotion_video()).pack(side=tk.LEFT, padx=2)
        #ttk.Button(row1_frame, text="上传视频", command=self.run_upload_video).pack(side=tk.LEFT, padx=2)
        #ttk.Button(scene_nav_row, text="拼接视频", command=self.run_final_concat_video).pack(side=tk.LEFT, padx=2)


        ttk.Button(row1_frame, text="Video生成", command=lambda:self.run_finalize_video(False)).pack(side=tk.LEFT) 
        ttk.Button(row1_frame, text="Video+生成", command=lambda:self.run_finalize_video(True)).pack(side=tk.LEFT)
        ttk.Button(row1_frame, text="Video提升", command=lambda:self.enhance_video()).pack(side=tk.LEFT)
        # add choice of value (from 0.0 to 2.0) used for "Video生成" as quiet audio add at end of each scene clip

        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(row1_frame, text="媒体清理",  command=self.clean_media).pack(side=tk.LEFT) 
        ttk.Button(row1_frame, text="WAN清理",   command=self.clean_wan).pack(side=tk.LEFT) 
        ttk.Button(row1_frame, text="SUNO管理", command=self._open_suno_gui).pack(side=tk.LEFT) 

   
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


    def swap_zero(self):
        """交换第一轨道与旁白轨道"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        clip_video_path = get_file_path(current_scene, 'clip')
        clip_audio_path = get_file_path(current_scene, 'clip_audio')
        zero_path = get_file_path(current_scene, "zero")
        if not zero_path:
            messagebox.showwarning("警告", "zero轨道视频文件不存在")
            return

        refresh_scene_media(current_scene, "back", '.mp4', clip_video_path)

        start_time_in_story, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scene_detail(current_scene)
        end_time = start_time_in_story + clip_duration

        temp_track = self.workflow.ffmpeg_processor.trim_video(zero_path, start_time_in_story, end_time)
        temp_track = self.workflow.ffmpeg_processor.add_audio_to_video(temp_track, clip_audio_path)

        refresh_scene_media(current_scene, 'clip', '.mp4', temp_track)
        self.refresh_gui_scenes()


    def track_recover(self):
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        clip = current_scene.get('clip', None)
        back = current_scene.get('back', None)
        if not back:
            messagebox.showwarning("警告", "背景视频文件不存在")
            return

        paths = back.split(',') 
        back_path = None
        for i in range(len(paths)):
            back_path = paths[i]
            back = ','.join(paths[i+1:])
            if os.path.exists(back_path):
                break
            back_path = None
            if i == len(paths) - 1:
                back = ""

        if not back_path:
            return

        if clip:
            current_scene['back'] = clip + "," + back

        refresh_scene_media(current_scene, 'clip', '.mp4', back_path)
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


    def choose_from_channel_media(self, track):
        try:
            mp4_path = None

            channel = project_manager.PROJECT_CONFIG.get('channel')
            scene_name = self.workflow.get_scene_by_index(self.current_scene_index)['name']
            source_folder = f"{config.get_channel_path(channel)}/video/{scene_name}"
            if not os.path.exists(source_folder):
                source_folder = f"{config.get_channel_path(channel)}/video/default"

            video_width = int(project_manager.PROJECT_CONFIG.get('video_width'))
            video_height = int(project_manager.PROJECT_CONFIG.get('video_height'))
            if video_width > video_height:
                ratio = "_169_"
            else:
                ratio = "_916_"

            # 优先只列出自 scene_name 开头的 .mp4 文件
            matching = [f for f in os.listdir(source_folder)
                        if ratio in f and f.lower().endswith('.mp4')
                        and os.path.isfile(os.path.join(source_folder, f))]
            if not matching:
                messagebox.showwarning("警告", "没有找到以 {} 开头的视频文件".format(scene_name))
                return

            matching.sort()
            chosen = askchoice_media_preview(
                "从频道媒体选择文件 (以 {} 开头)".format(scene_name),
                matching, source_folder, self.root
            )
            if not chosen:
                return

            mp4_path = os.path.join(source_folder, chosen)
            download_path = config.get_project_path(self.workflow.pid) + "/download"
            if not os.path.exists(download_path):
                os.makedirs(download_path, exist_ok=True)

            rename = os.path.join(download_path, track+"_"+str(self.workflow.get_scene_by_index(self.current_scene_index)["id"]) + "_" + datetime.now().strftime("%H%M%S") + ".mp4")
            shutil.copy(mp4_path, rename)
            self.media_scanner.video_simple_replacement(self.workflow.get_scene_by_index(self.current_scene_index), rename, "keep", track)
            # current scene, update track+"_status" to "ENH2"
            self.workflow.get_scene_by_index(self.current_scene_index)[track+"_status"] = "ENH2"
            self.refresh_gui_scenes()
                
        except Exception as e:
            messagebox.showerror("错误", f"选择文件时出错: {str(e)}")


    def choose_from_download(self, track, media_post):
        media_path = None

        for folder in ["L:"]:
            if check_folder_files(folder, media_post):
                matching = [f for f in os.listdir(folder)
                            if f.lower().endswith(media_post) and os.path.isfile(os.path.join(folder, f))]
                if matching:
                    matching.sort()
                    chosen = askchoice_media_preview("从下载盘选择视频", matching, folder, self.root)
                    if chosen:
                        media_path = os.path.join(folder, chosen)
                    break

        download_path = config.get_project_path(self.workflow.pid) + "/download"
        if not os.path.exists(download_path):
            os.makedirs(download_path, exist_ok=True)

        if media_path:
            rename = os.path.join(download_path, track+"_"+str(self.workflow.get_scene_by_index(self.current_scene_index)["id"]) + "_" + datetime.now().strftime("%H%M%S") + media_post)
            shutil.move(media_path, rename)
        else:
            matching = []
            if os.path.isdir(download_path):
                matching = [f for f in os.listdir(download_path)
                            if f.lower().endswith(media_post) and os.path.isfile(os.path.join(download_path, f))]
            if matching:
                matching.sort()
                chosen = askchoice_media_preview("从项目下载目录选择视频", matching, download_path, self.root)
                if chosen:
                    media_path = os.path.join(download_path, chosen)
                    rename = media_path
                else:
                    return
            else:
                media_path = filedialog.askopenfilename(
                    title="从频道媒体文件夹选择文件",
                    initialdir=download_path,
                    filetypes=[("视频文件", "*"+media_post)]
                )
                if not media_path: 
                    return
                rename = media_path

        if media_post == ".mp4":
            scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if track == "clip" or track == "narration":
                use_scene_audio = messagebox.askyesno(
                    "音频",
                    "是否用本场景已有的「{}」音频轨道替换新视频中的音频？\n\n"
                    "是：使用场景里已保存的 {}_audio（旧音频）\n"
                    "否：保留所选新视频文件里的音频".format(track, track),
                    parent=self.root,
                )
                audio_choice = "replace" if use_scene_audio else "keep"
            else:
                audio_choice = "keep"
            self.media_scanner.video_simple_replacement(scene, rename, audio_choice, track)
        else: # audio
            olda, newa = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), track+"_audio", ".wav", self.workflow.ffmpeg_audio_processor.to_wav(rename))
            vtrack = get_file_path(self.workflow.get_scene_by_index(self.current_scene_index), track)
            if not vtrack:
                vtrack = get_file_path(self.workflow.get_scene_by_index(self.current_scene_index), "clip")
            newv = self.workflow.ffmpeg_processor.add_audio_to_video(vtrack, newa)
            refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), track, ".mp4", newv)

        self.workflow.get_scene_by_index(self.current_scene_index)[track+"_status"] = "ORIG"
        self.refresh_gui_scenes()


    def choose_audio_source_or_tts(self, track):
        """
        先选择音色与审核内容，再选择：从文件选择 或 TTS生成。
        track: "clip" 或 "narration"
        """
        if not self.workflow or not self.speech_service:
            messagebox.showerror("错误", "工作流未就绪，请先选择项目")
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if track == "clip":
            voice_values = config.CHARACTER_PERSON_OPTIONS
            content_field = "speaking"
            role_field = "actor"
            track_label = "Clip"
            role_label = "人物"
        else:  # narration
            voice_values = config.CHARACTER_PERSON_OPTIONS
            content_field = "voiceover"
            role_field = "narrator"
            track_label = "Narration"
            role_label = "讲员"
        current_role = (self.scene_speaker.get() if role_field == "actor" else self.scene_narrator.get() or "").strip()
        current_content = (self.scene_speaking.get("1.0", tk.END) if content_field == "speaking" else self.scene_voiceover.get("1.0", tk.END) or "").strip()
        # 将 '——' 替换为 ', ' 后显示并保存
        current_content = current_content.replace("——", ", ").replace("—", ", ")
        current_content = self.workflow.transcriber.chinese_convert(current_content, "zh")
        content_label = "讲话" if content_field == "speaking" else "旁白"

        def _copy_to_clipboard(text):
            if not text:
                return
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update()
            except tk.TclError:
                pass

        _copy_to_clipboard(current_content)
        # 第一步：音色选择 + 内容审核（可修改）
        dlg = tk.Toplevel(self.root)
        dlg.title(f"{track_label} - 选择音色与审核内容")
        dlg.geometry("450x380")
        dlg.transient(self.root)
        dlg.grab_set()
        frame = ttk.Frame(dlg, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=f"{role_label}:").pack(anchor=tk.W)
        combo = ttk.Combobox(frame, values=voice_values, width=28, state="readonly")
        combo.pack(pady=5, anchor=tk.W)
        combo.set(current_role if current_role in voice_values else (voice_values[0] if voice_values else ""))
        ttk.Label(frame, text=f"{content_label} (可修改):").pack(anchor=tk.W, pady=(10, 2))
        content_text = scrolledtext.ScrolledText(frame, width=50, height=10, wrap=tk.WORD)
        content_text.pack(pady=5, fill=tk.BOTH, expand=True)
        content_text.insert("1.0", current_content)
        result = [None, None]
        def on_ok():
            content_val = content_text.get("1.0", tk.END).strip()
            result[0] = combo.get().strip()
            result[1] = content_val
            _copy_to_clipboard(content_val)
            dlg.destroy()
        btn_f = ttk.Frame(frame)
        btn_f.pack(pady=10)
        ttk.Button(btn_f, text="下一步", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="取消", command=dlg.destroy).pack(side=tk.LEFT)
        dlg.wait_window()
        speaker, content = result[0], result[1]
        if speaker is None:
            return
        # 回写 current_scene 和 GUI（用户已审核的内容）
        scene[role_field] = speaker
        scene[content_field] = content or ""
        if role_field == "actor":
            self.scene_speaker.set(speaker)
        else:
            self.scene_narrator.set(speaker)
        if content_field == "speaking":
            self.scene_speaking.delete("1.0", tk.END)
            self.scene_speaking.insert("1.0", content or "")
        else:
            self.scene_voiceover.delete("1.0", tk.END)
            self.scene_voiceover.insert("1.0", content or "")
        # 第二步：从文件选择 或 TTS生成
        choice = askchoice("选择音频来源", ["从文件选择", "TTS生成"], self.root)
        if choice is None:
            return
        if choice == "从文件选择":
            self.choose_from_download(track, ".mp3")
            return
        # choice == "TTS生成"
        if not content:
            messagebox.showwarning("警告", f"请先填写{content_label}内容")
            return
        lang = "chinese" if project_manager.PROJECT_CONFIG.get("language", "zh") in ("zh", "tw") else "english"
        voice = self.speech_service.get_voice(speaker, lang)
        ssml = self.speech_service.create_ssml(text=content, voice=voice, actions="", language=lang)
        audio_file = self.speech_service.synthesize_speech(ssml)
        if not audio_file:
            messagebox.showerror("错误", "TTS 生成失败")
            return
        tts_wav = self.workflow.ffmpeg_audio_processor.to_wav(audio_file)
        olda, newa = refresh_scene_media(scene, track + "_audio", ".wav", tts_wav)
        vtrack = get_file_path(scene, track)
        if not vtrack:
            vtrack = get_file_path(scene, "clip")
        if not vtrack or not os.path.exists(vtrack):
            messagebox.showwarning("警告", "该轨道无视频，无法合成。请先添加视频。")
            return
        newv = self.workflow.ffmpeg_processor.add_audio_to_video(vtrack, newa)
        refresh_scene_media(scene, track, ".mp4", newv)
        self.refresh_gui_scenes()
        self.workflow.save_scenes_to_json()
        messagebox.showinfo("成功", f"{track_label} 音频已生成并替换")


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
        track_label = {"narration": "旁白(NN)", "zero": "ZZ", "one": "OO"}.get(track, track)
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

    def mix_zero_audio_to_clips(self):
        """将起始场景的 zero_audio 连续混入当前及后续 N 个场景的 clip 视频，最后一个场景末尾 2 秒淡出"""
        try:
            n = int(getattr(self, 'mix_scenes_var', tk.StringVar(value="1")).get())
            n = max(1, min(5, n))
            volume = self.track_volume_var.get()
            volume = max(0.0, min(1.5, volume))

            # 使用起始场景的 zero_audio
            start_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            zero_audio = get_file_path(start_scene, "zero_audio")
            if not zero_audio or not os.path.exists(zero_audio):
                messagebox.showwarning("警告", "当前场景没有 zero_audio，无法混音")
                return

            fp = self.workflow.ffmpeg_processor
            zero_duration = fp.get_duration(zero_audio) or 0
            if zero_duration <= 0:
                messagebox.showwarning("警告", "zero_audio 无法读取时长")
                return

            mixed_count = 0
            total_offset = 0.0
            scenes_to_mix = []
            for i in range(n):
                idx = self.current_scene_index + i
                if idx >= len(self.workflow.scenes):
                    break
                scene = self.workflow.get_scene_by_index(idx)
                clip_path = get_file_path(scene, "clip")
                if not clip_path or not os.path.exists(clip_path):
                    continue
                clip_dur = fp.get_duration(clip_path) or 0
                if clip_dur <= 0:
                    continue
                scenes_to_mix.append((scene, clip_path, clip_dur))

            for idx, (scene, clip_path, clip_dur) in enumerate(scenes_to_mix):
                is_last = (idx == len(scenes_to_mix) - 1)
                if total_offset + clip_dur > zero_duration:
                    break
                fade_out = 2.0 if is_last else 0.0
                segment_audio = fp.extract_audio_segment(zero_audio, total_offset, clip_dur, fade_out_duration=fade_out)
                if not segment_audio:
                    continue
                output_video = fp.video_audio_mix(clip_path, segment_audio, volume=volume)
                if output_video:
                    output_audio = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(output_video)
                    refresh_scene_media(scene, "clip", ".mp4", output_video)
                    refresh_scene_media(scene, "clip_audio", ".wav", output_audio)
                    mixed_count += 1
                total_offset += clip_dur

            if mixed_count > 0:
                self.workflow.save_scenes_to_json()
                self.refresh_gui_scenes()
                messagebox.showinfo("成功", f"已将 zero_audio 混入 {mixed_count} 个场景的 clip 视频（音量: {volume:.2f}）")
            else:
                messagebox.showwarning("警告", "没有可处理的场景")
        except Exception as e:
            messagebox.showerror("错误", f"混零失败: {str(e)}")

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
            background_source = askchoice("选择背景来源", ["clip", "one", "clip_image", "clip_image_last"], self.root)
            if background_source is None:
                return
            if background_source == "clip":
                target_video_track = "clip"  
                background_audio = get_file_path(current_scene, "clip_audio")
                background_video = get_file_path(current_scene, "clip")
            elif background_source == "one":
                target_video_track = "narration"  
                background_audio = get_file_path(current_scene, "one_audio")
                background_video = get_file_path(current_scene, "one")
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

                back = current_scene.get('back', '')
                if background_source == "clip":
                    current_scene['back'] = background_video + "," + back
                
                if settings['position'] == "full":
                    v = self.workflow.ffmpeg_processor.add_audio_to_video(secondary_track_copy, background_audio)
                    refresh_scene_media(current_scene, target_video_track, '.mp4', v)
                elif settings['position'] == "av":
                    refresh_scene_media(current_scene, target_video_track, '.mp4', secondary_track_copy)
                    refresh_scene_media(current_scene, target_video_track+'_audio', '.wav', secondary_audio_copy)
                elif settings['position'] == "audio":
                    if settings['audio_volume'] != 0.0:
                        volume_main = 1
                        volume_overlay = 1
                        if settings['audio_volume'] > 0 :
                            volume_overlay = settings['audio_volume']
                            if volume_overlay > 0.9:
                                volume_overlay = 0.9
                        elif settings['audio_volume'] < 0:
                            volume_main = settings['audio_volume']
                            if volume_main < -0.9:
                                volume_main = -0.9
                            volume_main = 1+volume_main    

                        current_time, total_time = self.get_current_video_time()
                        output_audio = self.workflow.ffmpeg_audio_processor.audio_mix(background_audio, volume_main, current_time, secondary_audio_copy, volume_overlay)
                        olda, output_audio = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), target_video_track+'_audio', ".wav", output_audio)

                        output_video = self.workflow.ffmpeg_processor.add_audio_to_video(background_video, output_audio)
                        olda, output_video = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), target_video_track, ".mp4", output_video)

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

            output_audio = None
            audio_field = output_track + "_audio"
            if settings['audio_volume'] == 0.0:
                olda, output_audio = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), audio_field, ".wav", background_audio, True)
                output_video = self.workflow.ffmpeg_processor.add_audio_to_video(output_video, background_audio)
                olda, output_video = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), output_track, ".mp4", output_video, True)
            else:
                output_audio = background_audio
                if overlay_audio:
                    volume_main = 1
                    volume_overlay = 1
                    if settings['audio_volume'] > 0 :
                        volume_overlay = settings['audio_volume']
                        if volume_overlay > 0.9:
                            volume_overlay = 0.9
                    elif settings['audio_volume'] < 0:
                        volume_main = settings['audio_volume']
                        if volume_main < -0.9:
                            volume_main = -0.9
                        volume_main = 1+volume_main    

                    output_audio = self.workflow.ffmpeg_audio_processor.audio_mix(background_audio, volume_main, current_time, overlay_audio, volume_overlay)
                    olda, output_audio = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), audio_field, ".wav", output_audio, True)

                    output_video = self.workflow.ffmpeg_processor.add_audio_to_video(output_video, output_audio)
                    olda, output_video = refresh_scene_media(self.workflow.get_scene_by_index(self.current_scene_index), output_track, ".mp4", output_video, True)
            
            return output_video, output_audio

        except Exception as e:
            error_msg = f"画中画处理失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)
            return None, None


    def upload_promo_video(self):
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "upload_promo_video",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": self.workflow.pid
        }
        
        def run_task():
            try:
                print(f"🎬 上传宣传视频...")
                title = self.video_title.get().strip()
                
                # 调用工作流的方法
                result_video_path = self.workflow.upload_promo_video(title, "")

                print(f"✅ 宣传视频上传完成: {result_video_path}")
                
                # 更新任务状态
                self.tasks[task_id]["status"] = "完成"
                self.tasks[task_id]["result"] = f"宣传视频已上传: {os.path.basename(result_video_path)}"
                
            except Exception as e:
                error_msg = f"上传宣传视频失败: {str(e)}"
                print(f"❌ {error_msg}")
                
                # 更新状态为失败
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)
                
                # 通知错误
                self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
        # 启动后台任务
        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()
        
        print(f"🚀 上传宣传视频任务已启动，任务ID: {task_id}")
        


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
        self.video_frame.configure(width=1700)
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
        
        # 角色选择组合框框架
        visual_button_frame = ttk.Frame(left_frame)
        visual_button_frame.pack(fill=tk.X, pady=(0, 5))


        ttk.Button(visual_button_frame, text="末帧", width=7, command=lambda: self.fetch_last_image()).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(visual_button_frame, text="提示词", width=7, command=lambda: self.copy_clip_to_download(False)).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(visual_button_frame, text="生场景", width=7, command=lambda: self.regenerate_video("clip", True)).pack(side=tk.LEFT, padx=1)

        ttk.Button(visual_button_frame, text="生解说", width=7, command=lambda: self.regenerate_video("narration", True)).pack(side=tk.LEFT, padx=(1, 10))

        ttk.Button(visual_button_frame, text="SCENE", width=7, command=lambda: self.choose_from_channel_media("clip")).pack(side=tk.LEFT, padx=1)

        ttk.Button(visual_button_frame, text="CLIP_", width=7, command=lambda: self.choose_from_download("clip", ".mp4")).pack(side=tk.LEFT, padx=1)

        ttk.Button(visual_button_frame, text="SECO_", width=7, command=lambda: self.choose_from_download("narration", ".mp4")).pack(side=tk.LEFT, padx=1)

        ttk.Button(visual_button_frame, text="ZERO_", width=7, command=lambda: self.choose_from_download("zero", ".mp4")).pack(side=tk.LEFT, padx=1)

        ttk.Button(visual_button_frame, text="ONE_",  width=7, command=lambda: self.choose_from_download("one", ".mp4")).pack(side=tk.LEFT, padx=(1, 10))

        ttk.Button(visual_button_frame, text="CLI声", width=7, command=lambda: self.choose_audio_source_or_tts("clip")).pack(side=tk.LEFT, padx=1)

        ttk.Button(visual_button_frame, text="SEC声", width=7, command=lambda: self.choose_audio_source_or_tts("narration")).pack(side=tk.LEFT, padx=1)


        # 图片预览区域（原zero位置）
        images_preview_frame = ttk.LabelFrame(left_frame, text="图片预览 (支持拖放)", padding=5)
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
        self.clip_image_canvas.bind('<Double-Button-1>', lambda e: self.on_image_canvas_double_click(e, 'clip_image'))

        self.clip_image_last_canvas = tk.Canvas(clip_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='blue')
        self.clip_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.clip_image_last_canvas.create_text(75, 37, text="Clip\nLast", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.clip_image_last_canvas.drop_target_register(DND_FILES)
        self.clip_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'clip_image_last'))
        self.clip_image_last_canvas.bind('<Double-Button-1>', lambda e: self.on_image_canvas_double_click(e, 'clip_image_last'))


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
        self.narration_image_canvas.bind('<Double-Button-1>', lambda e: self.on_image_canvas_double_click(e, "narration_image"))

        self.narration_image_last_canvas = tk.Canvas(narration_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='green')
        self.narration_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.narration_image_last_canvas.create_text(75, 37, text="Narration\nLast", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.narration_image_last_canvas.drop_target_register(DND_FILES)
        self.narration_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, "narration_image_last"))
        self.narration_image_last_canvas.bind('<Double-Button-1>', lambda e: self.on_image_canvas_double_click(e, "narration_image_last"))
        

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
        self.zero_image_canvas.bind('<Double-Button-1>', lambda e: self.on_image_canvas_double_click(e, 'zero_image'))

        self.zero_image_last_canvas = tk.Canvas(zero_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='orange')
        self.zero_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.zero_image_last_canvas.create_text(75, 37, text="Zero\nLast", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.zero_image_last_canvas.drop_target_register(DND_FILES)
        self.zero_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'zero_image_last'))
        self.zero_image_last_canvas.bind('<Double-Button-1>', lambda e: self.on_image_canvas_double_click(e, 'zero_image_last'))


        # Top: one_image
        one_img_frame = ttk.Frame(images_container)
        one_img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        ttk.Label(one_img_frame, text="One", anchor=tk.CENTER).pack()
        one_canvas_container = ttk.Frame(one_img_frame)
        one_canvas_container.pack(fill=tk.BOTH, expand=True)

        self.one_image_canvas = tk.Canvas(one_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='purple')
        self.one_image_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 1))
        self.one_image_canvas.create_text(75, 37, text="One\nImage", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.one_image_canvas.drop_target_register(DND_FILES)
        self.one_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'one_image'))
        self.one_image_canvas.bind('<Double-Button-1>', lambda e: self.on_image_canvas_double_click(e, 'one_image'))

        self.one_image_last_canvas = tk.Canvas(one_canvas_container, bg='gray20', width=150, height=75, highlightthickness=2, highlightbackground='purple')
        self.one_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.one_image_last_canvas.create_text(75, 37, text="One\nLast", fill="gray", font=("Arial", 8), justify=tk.CENTER, tags="hint")
        self.one_image_last_canvas.drop_target_register(DND_FILES)
        self.one_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'one_image_last'))
        self.one_image_last_canvas.bind('<Double-Button-1>', lambda e: self.on_image_canvas_double_click(e, 'one_image_last'))


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
        ttk.Button(self.track_frame, text="💫OO", command=lambda:self.choose_secondary_track('one'), width=5).pack(side=tk.LEFT, padx=(1, 10))
        #ttk.Button(self.track_frame, text="💫", command=self.swap_narration, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="✨", command=self.swap_zero, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="🔊", command=self.pip_narration_sound, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="🔄", command=self.reset_track_offset, width=3).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.track_frame, text="⏱",  command=self.track_recover, width=3).pack(side=tk.LEFT, padx=1)
        
        # 添加音量控制滑块（共用，根据当前tab自动选择）
        ttk.Label(self.track_frame, text="音量").pack(side=tk.LEFT, padx=(10, 1))
        self.volume_scale = ttk.Scale(self.track_frame, from_=0.0, to=1.5, variable=self.track_volume_var, orient=tk.HORIZONTAL, length=38)
        self.volume_scale.pack(side=tk.LEFT, padx=1)
        self.volume_label = ttk.Label(self.track_frame, text="0.2")
        self.volume_label.pack(side=tk.LEFT, padx=(1, 10))
        # 绑定音量变化事件来更新标签
        self.track_volume_var.trace('w', self.on_track_volume_change)

        # add a button to remove current self.secondary_track (if selected) otherwise disable the button
        # if self.secondary_track is selected, warning user to remove which track ,  then if user confirm, remove this track (video plus audio field) from current scene
        self.remove_track_btn = ttk.Button(self.track_frame, text="🗑", command=self.remove_secondary_track, width=3)
        self.remove_track_btn.pack(side=tk.LEFT, padx=1)
        self.root.after(100, self._update_remove_track_btn_state)  # 延迟设置初始状态

        # add a combobox 'mix_scenes' to choose a number of scene (default 1, choice 1,2,3,4,5), and add a button (mix zero audio to current & following (total mix_scenes number) scent's clip videos  ~  on volume of track_volume_var)
        ttk.Label(self.track_frame, text="混零").pack(side=tk.LEFT, padx=(10, 1))
        self.mix_scenes_var = tk.StringVar(value="1")
        mix_scenes_combo = ttk.Combobox(self.track_frame, textvariable=self.mix_scenes_var, values=["1", "2", "3", "4", "5"], width=3, state="readonly")
        mix_scenes_combo.pack(side=tk.LEFT, padx=1)
        ttk.Button(self.track_frame, text="混零到clip", command=self.mix_zero_audio_to_clips, width=8).pack(side=tk.LEFT, padx=(1, 10))
        


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
        self.video_canvas.create_text(400, 180, text="拖拽MP4文件到此处可替换当前视频片段\n\n注意：\n• 输入视频不能超过当前场景时长\n• 如果输入视频较短，会自动延长", 
                                    fill="gray", font=("Arial", 12), justify=tk.CENTER, tags="drag_hint")
        
        # 绑定配置事件来动态调整提示文本位置
        self.video_canvas.bind('<Configure>', self.on_video_canvas_configure)
        
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

        # 翻转按钮
        ttk.Button(video_control_frame, text="<", command=lambda: self.move_video(-0.25), width=2).pack(side=tk.LEFT, padx=0)
        self.playing_delta_label = ttk.Label(video_control_frame, text="0.0s", width=4)
        self.playing_delta_label.pack(side=tk.LEFT, padx=0)
        ttk.Button(video_control_frame, text=">", command=lambda: self.move_video(0.25), width=2).pack(side=tk.LEFT, padx=0)

        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Button(video_control_frame, text="分离", command=self.split_scene, width=5).pack(side=tk.LEFT, padx=1) 
        ttk.Button(video_control_frame, text="拷贝", command=self.copy_story_scene, width=5).pack(side=tk.LEFT, padx=1)

        ttk.Button(video_control_frame, text="下移", command=lambda: self.shift_scene(True), width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="上移", command=lambda: self.shift_scene(False), width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="删合", command=self.merge_or_delete, width=5).pack(side=tk.LEFT, padx=1)

        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Button(video_control_frame, text="交换", command=self.swap_with_next_image, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="反转", command=self.reverse_video, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="镜像", command=self.mirror_video, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="标题", command=self.print_title, width=5).pack(side=tk.LEFT, padx=1)
        # 前插：仅当前为「本故事第一个场景」时可点；后插：仅当前为「本故事最后一个场景」时可点
        self.btn_add_scene_before = ttk.Button(
            video_control_frame, text="前插", command=self.add_scene_before, width=5
        )
        self.btn_add_scene_before.pack(side=tk.LEFT, padx=1)
        self.btn_add_scene_after = ttk.Button(
            video_control_frame, text="后插", command=self.add_scene_after, width=5
        )
        self.btn_add_scene_after.pack(side=tk.LEFT, padx=1)

        #ttk.Button(video_control_frame, text="背起", command=self.zero_start, width=5).pack(side=tk.LEFT, padx=1)
        #ttk.Button(video_control_frame, text="背继", command=self.zero_continue, width=5).pack(side=tk.LEFT, padx=1)
        #ttk.Button(video_control_frame, text="背终", command=self.zero_end, width=5).pack(side=tk.LEFT, padx=1)

        # 分隔符
        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # 存储按钮引用以便后续控制状态
        # add 2 marks, to mark the current video progress sec，　then add a button 'make_silence'　to make the audio  period between mark1 mark2 be silient
        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        ttk.Button(video_control_frame, text="静音", command=self.make_silence_between_marks, width=6).pack(side=tk.LEFT, padx=1)
        # Mark buttons and labels
        ttk.Button(video_control_frame, text="M1", command=self.set_mark1, width=3).pack(side=tk.LEFT, padx=1)
        self.mark1_label = ttk.Label(video_control_frame, text="--:--.--", width=10)
        self.mark1_label.pack(side=tk.LEFT, padx=1)
        
        ttk.Button(video_control_frame, text="M2", command=self.set_mark2, width=3).pack(side=tk.LEFT, padx=1)
        self.mark2_label = ttk.Label(video_control_frame, text="--:--.--", width=10)
        self.mark2_label.pack(side=tk.LEFT, padx=1)

        # 视频进度标签
        self.video_progress_label = ttk.Label(video_control_frame, text="00:00.00 /00:00.00")
        self.video_progress_label.pack(side=tk.RIGHT, padx=1)
        
        # 初始化视频进度显示
        self.update_video_progress_display()
        
        # 视频播放状态
        self.video_playing = False
        self.video_cap = None
        self.video_after_id = None
        self.video_start_time = None
        self.video_pause_time = None  # 记录暂停时的累计播放时间
        
        # 标记时间点
        self.mark1_time = None
        self.mark2_time = None
        
        # 右侧：场景信息显示区域
        self.video_edit_frame = ttk.LabelFrame(main_content, text="场景信息", padding=10)
        self.video_edit_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        # 设置右侧面板的固定宽度，防止被挤压
        self.video_edit_frame.configure(width=700)
        self.video_edit_frame.pack_propagate(False)
        
        row_number = 1

        # 持续时间和宣传模式在同一行
        duration_promo_frame = ttk.Frame(self.video_edit_frame)
        duration_promo_frame.grid(row=row_number, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)
        row_number += 1

        ttk.Button(duration_promo_frame, text="增主轨", width=8, command=lambda: self.enhance_clip("clip")).pack(side=tk.LEFT)
        ttk.Button(duration_promo_frame, text="增次轨", width=8, command=lambda: self.enhance_clip("narration")).pack(side=tk.LEFT)

        FACE_ENHANCE = ["0", "15", "30", "60"]
        self.enhance_level = ttk.Combobox(duration_promo_frame, width=3, values=FACE_ENHANCE)
        self.enhance_level.pack(side=tk.LEFT, padx=2)
        self.enhance_level.set("30")

        ttk.Button(duration_promo_frame, text="故事描述", width=10, command=self.describe_story_content).pack(side=tk.LEFT)
        ttk.Button(duration_promo_frame, text="场景描述", width=10, command=self.describe_scene_content).pack(side=tk.LEFT)
        #ttk.Button(duration_promo_frame, text="精配", width=5, command=lambda: self.concise_scene_speak("voiceover")).pack(side=tk.LEFT)

        # extension: 场景末尾延长秒数 (0=不写字段, 0.5/1.0/1.5/2.0 秒)，用于 finalize 时每段视频末尾克隆最后一帧延长
        ttk.Label(duration_promo_frame, text="延长:").pack(side=tk.LEFT)
        self.extension_var = tk.StringVar(value="0")
        EXTENSION_VALUES = ["0", "0.5", "1.0", "1.5", "2.0"]
        self.extension_combobox = ttk.Combobox(duration_promo_frame, textvariable=self.extension_var, values=EXTENSION_VALUES, state="readonly", width=5)
        self.extension_combobox.pack(side=tk.LEFT, padx=2)
        self.extension_combobox.bind('<<ComboboxSelected>>', lambda e: self._on_extension_change())


        # 类型、情绪、动作选择（在同一行）
        type_mood_action_frame = ttk.Frame(self.video_edit_frame)
        type_mood_action_frame.grid(row=row_number, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)
        row_number += 1

        # 宣传模式（可编辑）
        ttk.Label(type_mood_action_frame, text="主动画:").pack(side=tk.LEFT)
        self.clip_animate = tk.StringVar(value="")
        self.main_animate_combobox = ttk.Combobox(type_mood_action_frame, textvariable=self.clip_animate, values=config_prompt.ANIMATE_SOURCE, state="readonly", width=5)
        self.main_animate_combobox.pack(side=tk.LEFT)
        self.main_animate_combobox.bind('<<ComboboxSelected>>', lambda event: self.on_scene_field_change("clip_animation", self.clip_animate.get()))
        ttk.Button(type_mood_action_frame, text="生", width=3, command=lambda: self.regenerate_video("clip", False)).pack(side=tk.LEFT)

        ttk.Label(type_mood_action_frame, text="次动画:").pack(side=tk.LEFT, padx=(10, 0))
        self.narration_animation_combobox = ttk.Combobox(type_mood_action_frame, textvariable=self.narration_animation, values=config_prompt.ANIMATE_SOURCE, state="readonly", width=5)
        self.narration_animation_combobox.pack(side=tk.LEFT)
        self.narration_animation_combobox.bind('<<ComboboxSelected>>', lambda event: self.on_scene_field_change("narration_animation", self.narration_animation.get()))
        ttk.Button(type_mood_action_frame, text="生", width=3, command=lambda: self.regenerate_video("narration", False)).pack(side=tk.LEFT)
        row_number += 1

        #ttk.Button(action_frame, text="生主图-英", width=10, command=lambda: self.recreate_clip_image("en", True)).pack(side=tk.LEFT, padx=2)
        #ttk.Button(action_frame, text="生次图-中", width=8, command=lambda: self.recreate_clip_image("zh", False)).pack(side=tk.LEFT, padx=2)
        #ttk.Button(action_frame, text="生次图-英", width=8, command=lambda: self.recreate_clip_image("en", False)).pack(side=tk.LEFT, padx=2)


        action_frame = ttk.Frame(self.video_edit_frame)
        action_frame.grid(row=row_number, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)
        row_number += 1


        #ttk.Button(action_frame, text="插主轨", width=10, command=lambda: self.enhance_clip(True, True)).pack(side=tk.LEFT)
        #ttk.Button(action_frame, text="插次轨", width=10, command=lambda: self.enhance_clip(False, True)).pack(side=tk.LEFT)
        #RIFE_EXP = ["0", "1", "2"]
        #self.rife_exp = ttk.Combobox(action_frame, width=5, values=RIFE_EXP)
        #self.rife_exp.pack(side=tk.LEFT, padx=2)
        #self.rife_exp.set("0")

        ttk.Label(self.video_edit_frame, text="讲话:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_speaking = scrolledtext.ScrolledText(self.video_edit_frame, width=40, height=10)
        self.scene_speaking.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="人物:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_speaker = ttk.Combobox(self.video_edit_frame, width=32, values=config.CHARACTER_PERSON_OPTIONS)
        self.scene_speaker.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="动作:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_actions = scrolledtext.ScrolledText(self.video_edit_frame, width=40, height=1)
        self.scene_actions.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="视觉:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_visual = scrolledtext.ScrolledText(self.video_edit_frame, width=40, height=1)
        self.scene_visual.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        _nar_host_row = ttk.Frame(self.video_edit_frame)
        _nar_host_row.grid(row=row_number, column=0, columnspan=2, sticky=tk.W, pady=2)
        ttk.Label(_nar_host_row, text="讲员:").pack(side=tk.LEFT, padx=(0, 4))
        self.scene_narrator = ttk.Combobox(_nar_host_row, width=22, values=config.CHARACTER_PERSON_OPTIONS)
        self.scene_narrator.pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(_nar_host_row, text="出镜:").pack(side=tk.LEFT, padx=(0, 4))
        self.scene_host_display = ttk.Combobox(
            _nar_host_row,
            width=22,
            values=list(config_prompt.HARRATOR_DISPLAY_OPTIONS),
            state="readonly",
        )
        self.scene_host_display.pack(side=tk.LEFT, padx=(0, 0))
        row_number += 1

        ttk.Label(self.video_edit_frame, text="旁白:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_voiceover = scrolledtext.ScrolledText(self.video_edit_frame, width=40, height=5)
        self.scene_voiceover.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="字幕:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_caption = scrolledtext.ScrolledText(self.video_edit_frame, width=40, height=1)
        self.scene_caption.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        #ttk.Label(self.video_edit_frame, text="摄影:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        #self.scene_cinematography = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        #self.scene_cinematography.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        #row_number += 1

        ttk.Label(self.video_edit_frame, text="字体:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_language = ttk.Combobox(self.video_edit_frame, width=32, values=list(config.FONT_LIST.keys()))
        self.scene_language.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1
        self.scene_language.set(self.shared_language.cget('text'))

        ttk.Label(self.video_edit_frame, text="画面风格:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        _vs_labels = list(config.VISUAL_STYLE_OPTIONS)
        self.scene_visual_style = ttk.Combobox(
            self.video_edit_frame,
            width=32,
            values=_vs_labels,
            state="readonly",
        )
        self.scene_visual_style.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1
        self.scene_visual_style.set(project_manager.LAST_VISUAL_STYLE)

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
        """增强主图或次图"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        level = self.enhance_level.get()
        self.workflow.sd_processor.enhance_clip(self.get_pid(), scene, track, level)
        self.refresh_gui_scenes()


    def enhance_video(self):
        for scene in self.workflow.scenes:
            self.workflow.sd_processor.enhance_clip(self.get_pid(), scene, "clip", "30")
            self.workflow.sd_processor.enhance_clip(self.get_pid(), scene, "narration", "30")
        self.refresh_gui_scenes()
    

    def run_finalize_video(self, add_narration):
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
                self.workflow.finalize_video(self.video_title.get().strip(), add_narration)
                self.log_to_output(self.video_output, "✅ 最终视频生成完成！")
                self.tasks[task_id]["status"] = "完成"
            except Exception as e:
                self.log_to_output(self.video_output, f"❌ 最终视频生成失败: {str(e)}")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)

        threading.Thread(target=run_task, daemon=True).start()


    def run_upload_video(self):
        """上传视频到YouTube（或其他平台）"""
        pid = self.get_pid()
        title = self.video_title.get().strip()

        if not pid:
            messagebox.showerror("错误", "请输入项目ID")
            return

        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "upload_video",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": pid
        }

        def run_task():
            try:
                self.log_to_output(self.video_output, f"开始上传视频 - PID: {pid}")
                workflow = self.workflow
                if workflow is None:
                    raise Exception("无法获取工作流对象")

                workflow.upload_video(title)
                self.log_to_output(self.video_output, "✅ 视频上传完成！")
                self.tasks[task_id]["status"] = "完成"
            except Exception as e:
                self.log_to_output(self.video_output, f"❌ 视频上传失败: {str(e)}")
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
                
                self.video_canvas.create_text(x, y + pil_image.height//2 + 40, 
                                            text="💡 拖拽MP4文件可替换此视频", 
                                            fill="gray", font=("Arial", 10))
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
        
        self.video_canvas.create_text(x, y, text="选择场景后会显示视频预览\n\n💡 可以拖拽MP4文件到此处替换视频片段", fill="white", 
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
                self.resume_audio_playback()
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

    def stop_video_playback(self):
        """停止视频播放"""
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
            # 音频播放完毕，停止视频
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
            
            current_time, total_time = self.get_current_video_time()
            
            # Format time with 0.01 narration precision
            current_time_str = self.format_time_with_centisec(current_time)
            total_time_str = self.format_time_with_centisec(total_time)
            
            self.video_progress_label.config(text=f"{current_time_str} /{total_time_str}")
            
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


    def update_scene_display(self):
        """更新场景显示"""
        if len(self.workflow.scenes) == 0:
            self.scene_label.config(text="0 / 0")
            self.clear_scene_fields()
            self.clear_video_preview()
            return
            
        self.scene_label.config(text=f"{self.current_scene_index + 1} / {len(self.workflow.scenes)}")
        scene_data = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene_data:
            return

        # 设置宣传复选框状态
        clip_animation = scene_data.get("clip_animation", "S2V")
        self.clip_animate.set(clip_animation)
        
        # 加载当前场景的图像类型设置
        narration_animate = scene_data.get("narration_animation", "S2V")
        self.narration_animation.set(narration_animate)

        ext_val = scene_data.get("extension", 0)
        ext_str = str(float(ext_val)) if ext_val is not None else "0"
        self.extension_var.set(ext_str if ext_str in ["0", "0.5", "1.0", "1.5", "2.0"] else "0")

        self.scene_speaking.delete("1.0", tk.END)
        self.scene_speaking.insert("1.0", scene_data.get("speaking", ""))
        
        self.scene_speaker.set(scene_data.get("actor", ""))

        self.scene_actions.delete("1.0", tk.END)
        self.scene_actions.insert("1.0", scene_data.get("actions", ""))

        self.scene_visual.delete("1.0", tk.END)
        self.scene_visual.insert("1.0", scene_data.get("visual", ""))

        self.scene_voiceover.delete("1.0", tk.END)
        self.scene_voiceover.insert("1.0", scene_data.get("voiceover", ""))

        self.scene_caption.delete("1.0", tk.END)
        self.scene_caption.insert("1.0", scene_data.get("caption", ""))

        self.scene_narrator.set(scene_data.get("narrator", project_manager.PROJECT_CONFIG.get("narrator")))
        self.scene_host_display.set(scene_data.get("host_display", project_manager.PROJECT_CONFIG.get("host_display")))
        self.scene_visual_style.set(scene_data.get("visual_style", project_manager.PROJECT_CONFIG.get("visual_style")))

        #self.scene_cinematography.delete("1.0", tk.END)
        # 如果 cinematography 是字典，格式化显示；如果是字符串，直接显示
        #cinematography_value = scene_data.get("cinematography", "")
        #if isinstance(cinematography_value, dict):
        #    self.scene_cinematography.insert("1.0", json.dumps(cinematography_value, ensure_ascii=False, indent=2))
        #else:
        #    self.scene_cinematography.insert("1.0", cinematography_value)
        status = scene_data.get("clip_status", "")
        self.video_edit_frame.config(text=f"视频尺寸: {status}")
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


    def set_mark1(self):
        """Set mark1 to current video time"""
        current_time, total_time = self.get_current_video_time()
        current_time = current_time + self.playing_delta
        self.mark1_time = current_time
        time_str = self.format_time_with_centisec(current_time)
        self.mark1_label.config(text=time_str)
        print(f"✓ 设置标记1: {time_str}")
    

    def set_mark2(self):
        """Set mark2 to current video time"""
        current_time, total_time = self.get_current_video_time()
        current_time = current_time + self.playing_delta
        self.mark2_time = current_time
        time_str = self.format_time_with_centisec(current_time)
        self.mark2_label.config(text=time_str)
        print(f"✓ 设置标记2: {time_str}")
    

    def make_silence_between_marks(self):
        """Make audio silent between mark1 and mark2"""
        if self.mark1_time is None:
            messagebox.showwarning("警告", "请先设置标记1和标记2")
            return
        
        if self.mark2_time and self.mark1_time >= self.mark2_time:
            messagebox.showwarning("警告", "标记1和标记2时间相同或无效")
            return
        
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not current_scene:
                messagebox.showerror("错误", "没有当前场景")
                return
            
            clip_audio_path = get_file_path(current_scene, "clip_audio")
            if not clip_audio_path or not os.path.exists(clip_audio_path):
                messagebox.showerror("错误", "找不到音频文件")
                return
            
            # Get total duration
            total_duration = self.workflow.ffmpeg_processor.get_duration(clip_audio_path)
            if total_duration <= 0:
                messagebox.showerror("错误", "无法获取音频时长")
                return
            
            # Ensure marks are within audio duration
            mark1 = self.mark1_time
            mark2 = self.mark2_time if self.mark2_time else total_duration
            
            if mark1 >= mark2:
                messagebox.showwarning("警告", "标记时间无效")
                return
            
            print(f"🔇 静音处理: {mark1:.2f}s 到 {mark2:.2f}s")
            
            # Split audio into three parts: before mark1, between marks (silent), after mark2
            audio_segments = []
            
            # Part 1: from start to mark1
            if mark1 > 0:
                part1 = self.workflow.ffmpeg_audio_processor.audio_cut_fade(
                    clip_audio_path, 0, mark1, 0, 0, 1.0
                )
                if part1:
                    audio_segments.append(part1)
            
            # Part 2: silent segment from mark1 to mark2
            silent_duration = mark2 - mark1
            silent_segment = self.workflow.ffmpeg_audio_processor.make_silence(silent_duration)
            if silent_segment:
                audio_segments.append(silent_segment)
            
            # Part 3: from mark2 to end
            if mark2 < total_duration:
                part3_duration = total_duration - mark2
                part3 = self.workflow.ffmpeg_audio_processor.audio_cut_fade(
                    clip_audio_path, mark2, part3_duration, 0, 0, 1.0
                )
                if part3:
                    audio_segments.append(part3)
            
            # Concatenate all segments
            if audio_segments:
                output_audio = self.workflow.ffmpeg_audio_processor.concat_audios(audio_segments)
                if output_audio and os.path.exists(output_audio):
                    # Update scene audio file
                    old_audio, new_audio = refresh_scene_media(
                        current_scene, "clip_audio", ".wav", output_audio, True
                    )
                    
                    # Update video with new audio
                    clip_video = get_file_path(current_scene, "clip")
                    if clip_video and os.path.exists(clip_video):
                        output_video = self.workflow.ffmpeg_processor.add_audio_to_video( clip_video, new_audio )
                        if output_video:
                            refresh_scene_media(
                                current_scene, "clip", ".mp4", output_video, True
                            )
                    
                    messagebox.showinfo("成功", f"已将 {mark1:.2f}s 到 {mark2:.2f}s 之间的音频静音")
                    print(f"✅ 静音处理完成")
                else:
                    messagebox.showerror("错误", "音频处理失败")
            else:
                messagebox.showerror("错误", "无法创建音频片段")
                
        except Exception as e:
            error_msg = f"静音处理失败: {str(e)}"
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
                
                if self.video_playing:
                    pass
                else:
                    total_time_str = self.format_time_with_centisec(total_duration)
                    self.video_progress_label.config(text=f"00:00.00 /{total_time_str}")
            else:
                self.video_progress_label.config(text="00:00.00 /00:00.00")
                
        except Exception as e:
            self.video_progress_label.config(text="00:00.00 /00:00.00")
            print(f"⚠️ 更新视频进度显示失败: {e}")


    def clear_scene_fields(self):
        self.clip_animate.set("")
        self.extension_var.set("0")
        
        self.scene_speaking.delete("1.0", tk.END)
        self.scene_speaker.set("")
        self.scene_actions.delete("1.0", tk.END)
        self.scene_visual.delete("1.0", tk.END)
        _pc = project_manager.PROJECT_CONFIG
        self.scene_narrator.set(_pc.get("narrator") or project_manager.LAST_NARRATOR)
        self.scene_host_display.set(_pc.get("host_display") or project_manager.LAST_HOST_DISPLAY)
        self.scene_visual_style.set(_pc.get("visual_style") or project_manager.LAST_VISUAL_STYLE)
        self.scene_voiceover.delete("1.0", tk.END)
        self.scene_caption.delete("1.0", tk.END)


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


    def split_scene(self):
        """分离当前场景"""      
        position = pygame.mixer.music.get_pos() / 1000.0
        self.workflow.split_scene_at_position(self.current_scene_index, position+self.playing_delta)
        self.playing_delta = 0.0
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
        """前插仅在本故事首场景可用，后插仅在本故事尾场景可用。"""
        if not getattr(self, "btn_add_scene_before", None) or not getattr(self, "btn_add_scene_after", None):
            return
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            self.btn_add_scene_before.config(state=tk.DISABLED)
            self.btn_add_scene_after.config(state=tk.DISABLED)
            return
        self.btn_add_scene_before.config(
            state=tk.NORMAL if self.workflow.first_scene_of_story(scene) else tk.DISABLED
        )
        self.btn_add_scene_after.config(
            state=tk.NORMAL if self.workflow.last_scene_of_story(scene) else tk.DISABLED
        )

    def add_scene_before(self):
        """在本故事第一个场景前插入一个复制场景（仅首场景时可操作）。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene or not self.workflow.first_scene_of_story(scene):
            return
        dup = scene.copy()
        dup["id"] = self.workflow.max_id(dup) + 1
        self.workflow.scenes.insert(self.current_scene_index, dup)
        self.workflow.save_scenes_to_json()
        self.current_scene_index += 1
        self.refresh_gui_scenes()

    def add_scene_after(self):
        """在本故事最后一个场景后插入一个复制场景（仅尾场景时可操作）。"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene or not self.workflow.last_scene_of_story(scene):
            return
        dup = scene.copy()
        dup["id"] = self.workflow.max_id(dup) + 1
        self.workflow.scenes.insert(self.current_scene_index + 1, dup)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()

    def copy_story_scene(self):
        story_level = self.workflow.first_scene_of_story(self.workflow.get_scene_by_index(self.current_scene_index))  or  self.workflow.last_scene_of_story(self.workflow.get_scene_by_index(self.current_scene_index))

        if story_level:
            dialog = messagebox.askyesno("场景/故事", "是否要拷贝场景还是故事？")
            if dialog:
                story_level = False

        dup = self.workflow.get_scene_by_index(self.current_scene_index).copy()
        dup["id"] = self.workflow.max_id(dup) + 1

        self.workflow.scenes.insert(self.current_scene_index+1, dup) 

        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def append_scene(self):
        story_level = self.workflow.last_scene_of_story(self.workflow.get_scene_by_index(self.current_scene_index))

        self.workflow.add_story_scene( self.current_scene_index, self.workflow.get_scene_by_index(self.current_scene_index), story_level, True )

        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def reverse_video(self):
        """翻转视频"""
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
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
        oldv, newv = refresh_scene_media(current_scene, "clip", ".mp4")
        os.replace(self.workflow.ffmpeg_processor.mirror_video(oldv), newv)
        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def print_title(self):
        """打印标题"""
        current_scene = self.update_current_scene()
        content = current_scene['caption']
        if not content or content.strip() == "":
            messagebox.showinfo("标题", "标题为空")
            return
        clip_video = get_file_path(current_scene, "clip")
        if not clip_video:
            messagebox.showinfo("标题", "视频为空")
            return
       
        content = self.workflow.transcriber.translate_text(content, self.workflow.language, self.workflow.language)

        content_language = self.scene_language.get()
        if content_language in config.FONT_LIST:
            current_scene["content_language"] = content_language
            font = config.FONT_LIST[content_language]
        else:
            font = self.workflow.font_title

        v = self.workflow.ffmpeg_processor.add_script_to_video(clip_video, content, font)
        back = current_scene.get('back', '')
        current_scene['back'] = clip_video + "," + back
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
                        pygame.mixer.music.set_volume(self.track_volume_var.get())
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


    def _show_image_action_choice(self, parent, image_type):
        """弹出图像操作选择对话框，返回用户选择：1-7 或 None(取消)"""
        choice_var = tk.StringVar(value="")
        dialog = tk.Toplevel(parent)
        dialog.title("选择操作")
        dialog.geometry("420x380")
        dialog.transient(parent)
        dialog.grab_set()

        choices = [
            ("2", "增强现有图"),
            ("4", "(当前图) 生成视频"),
            ("5", "增强 → 生成视频"),
            ("1", "选新图（替换图像）"),
            ("3", "选新图 → 增强"),
            ("6", "选新图 → 增强 → 生成视频"),
            ("7", "选新图 → 生成视频"),
        ]
        ttk.Label(dialog, text=f"对 {image_type.replace('_', ' ')} 执行操作：", font=("", 10)).pack(pady=(15, 10))
        for val, text in choices:
            ttk.Radiobutton(dialog, text=text, variable=choice_var, value=val).pack(anchor=tk.W, padx=20, pady=2)

        result = [None]
        def on_ok():
            result[0] = choice_var.get() or None
            dialog.destroy()
        def on_cancel():
            result[0] = None
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
        dialog.wait_window()
        return result[0]

    def on_image_canvas_double_click(self, event, image_type):
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not current_scene:
                return
            # 与选择对话框同时：先把当前槽位已有图片复制到剪贴板，便于其他应用粘贴处理
            _preview_path = current_scene.get(image_type)
            if _preview_path and os.path.exists(_preview_path):
                self.copy_image_to_clipboard(_preview_path, silent=True)

            source_folder = os.path.join(os.path.expanduser('~'), 'Downloads')
            track = image_type.split("_")[0]  # clip_image -> clip, narration_image -> narration, etc.

            choice = self._show_image_action_choice(self.root, image_type)
            if not choice:
                return

            image_path = None
            need_select = choice in ("1", "3", "6", "7")
            need_enhance = choice in ("2", "3", "5", "6")
            need_gen_video = choice in ("4", "5", "6", "7")

            if need_select:
                image_path = filedialog.askopenfilename(
                    title="选择图像",
                    initialdir=source_folder if os.path.exists(source_folder) else None,
                    filetypes=[("图像文件", "*.png;*.jpg;*.jpeg;*.webp")]
                )
                if not image_path:
                    return
                download_path = config.get_project_path(self.workflow.pid) + "/download"
                os.makedirs(download_path, exist_ok=True)
                image = Path(image_path)
                rename = os.path.join(download_path, image_type+"_"+str(current_scene["id"]) + "_" + datetime.now().strftime("%H%M%S") + image.suffix)
                shutil.move(image_path, rename)
                image_path = rename
            else:
                image_path = current_scene.get(image_type)
                if not image_path or not os.path.exists(image_path):
                    messagebox.showwarning("警告", f"场景中没有有效的 {image_type} 图像")
                    return

            if need_enhance:
                image_path = self.workflow.sd_processor._enhance_image_in_api(image_path, 0.3)
                if not image_path:
                    messagebox.showerror("错误", "图像增强失败")
                    return
            elif not need_gen_video:
                image_path = self.workflow.ffmpeg_processor.resize_image_smart(image_path)

            if need_gen_video:
                audio_path = get_file_path(current_scene, track+"_audio") or get_file_path(current_scene, "clip_audio")
                if not audio_path or not os.path.exists(audio_path):
                    messagebox.showwarning("警告", f"场景中没有有效的 {track}_audio 或 clip_audio")
                    return
                # 未经过增强的图需要先缩放到视频尺寸
                if not need_enhance:
                    image_path = self.workflow.ffmpeg_processor.resize_image_smart(image_path)
                video_path = self.workflow.ffmpeg_processor.image_audio_to_video(image_path, audio_path, 1)
                refresh_scene_media(current_scene, track, ".mp4", video_path, True)
                self.media_scanner.last_image_replacement(current_scene, video_path, track)
            else:
                oldi, image_path = refresh_scene_media(current_scene, image_type, ".webp", image_path)
                if self.copy_image_to_clipboard(image_path):
                    messagebox.showinfo("成功", f"已复制 {image_type.replace('_', ' ')} 到剪贴板\n可以在网页工具中粘贴使用")

            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()

        except Exception as e:
            error_msg = f"处理双击事件失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)


    def on_image_drop(self, event, image_type):
        """处理图片拖放事件
        
        Args:
            event: 拖放事件
            image_type: 'clip_image', "narration_image", 或 'zero_image'
        """
        file_path = event.data.strip('{}').strip('"')
        
        # 检查是否为图片文件
        if not (file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'))):
            messagebox.showerror("错误", "请拖放图片文件 (PNG, JPG, WEBP等)")
            return
        
        if not os.path.exists(file_path):
            messagebox.showerror("错误", "文件不存在")
            return
        
        file_path = self.workflow.ffmpeg_processor.resize_image_smart(file_path)
        try:
            # 获取当前场景
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
            if not current_scene:
                messagebox.showerror("错误", "没有选中场景")
                return
            
            # 复制图片到项目目录
            oldi, image_path = refresh_scene_media(current_scene, image_type, ".webp", file_path, True)

            # 刷新显示
            self.display_image_on_canvas_for_track(image_type)
            
            self.workflow.save_scenes_to_json()
            print(f"✅ 已更新 {image_type}: {os.path.basename(file_path)}")
            messagebox.showinfo("成功", f"已更新 {image_type.replace('_', ' ')}")
            
        except Exception as e:
            error_msg = f"更新图片失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)


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
                'one_image': (self.one_image_canvas, "One\nImage", '_one_image_photo'),
                'one_image_last': (self.one_image_last_canvas, "One\nLast", '_one_image_last_photo'),
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
            self.display_image_on_canvas_for_track('one_image')
            self.display_image_on_canvas_for_track('one_image_last')

            # 根据当前选中的tab加载轨道视频预览
            current_tab_index = self.narration_notebook.index(self.narration_notebook.select())
            if current_tab_index == 0:
                self.load_secondary_track_first_frame()
            elif current_tab_index == 1:
                self.load_pip_lr_first_frame()

        except Exception as e:
            print(f"❌ 加载图片预览失败: {e}")
    
    
    def on_track_volume_change(self, *args):
        """音量变化处理（共用）"""
        volume = self.track_volume_var.get()
        self.volume_label.config(text=f"{volume:.2f}")

        if hasattr(pygame.mixer, 'music') and pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(volume)

    
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
    

    def shift_scene(self, forward=True):
        position = pygame.mixer.music.get_pos() / 1000.0
        if position <= 0.001:
            position = 0.0

        if position == 0.0 and forward and self.playing_delta < 0.0 and self.current_scene_index > 0:
                current_index = self.current_scene_index - 1
                next_index = self.current_scene_index
                position = self.workflow.find_clip_duration(self.workflow.scenes[current_index])
        else:
            current_index = self.current_scene_index
            next_index = current_index + 1 if forward else current_index - 1
            if (next_index < 0 or next_index >= len(self.workflow.scenes)) and position + self.playing_delta <= 0.0 :
                return

        self.workflow.shift_scene(current_index, next_index, position+self.playing_delta)
        self.refresh_gui_scenes()


    def shift_before(self):
        """下移当前场景"""
        position = pygame.mixer.music.get_pos() / 1000.0
        self.workflow.shift_scene(self.current_scene_index, self.current_scene_index-1, position+self.playing_delta)
        self.playing_delta = 0.0

        self.refresh_gui_scenes()


    def merge_or_delete(self):
        """合并当前图片与下一张图片"""
        if len(self.workflow.scenes) == 0:
            messagebox.showinfo("警告", "⚠️ 无场景")
            return

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
            
        self.refresh_gui_scenes()
        messagebox.showinfo("合并场景", "完成")


    def swap_with_next_image(self):
        """交换当前图片与下一张图片"""
        current_index = self.current_scene_index
        current_scene = self.workflow.scenes[current_index]

        ss = self.workflow.scenes_in_story(current_scene)
        if len(ss) <= 1 or current_scene == ss[-1]:
            messagebox.showinfo("警告", "⚠️ 当前场景无法交换")
            return
        
        next_index = current_index + 1
        next_scene = self.workflow.scenes[next_index]

        # 查找当前场景和下一个场景的图像文件
        temp_image = current_scene["clip_image"]
        current_scene["clip_image"] = next_scene["clip_image"]
        next_scene["clip_image"] = temp_image

        # self.workflow._generate_video_from_image(current_scene)
        # self.workflow._generate_video_from_image(next_scene)
        
        # 显示成功消息
        messagebox.showinfo("成功", f"已成功交换场景 {current_index + 1} 和场景 {next_index + 1} 的图片！")


    def swap_scene(self):
        """交换当前场景与下一张场景"""
        self.workflow.swap_scene(self.current_scene_index, self.current_scene_index+1)
        self.refresh_gui_scenes()


    def copy_lastimage_to_next(self):
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        next_scene = self.workflow.next_scene_of_story(current_scene)
        if current_scene and next_scene:
            clip_image_last = current_scene.get("clip_image_last", "")
            if clip_image_last and clip_image_last.endswith(".webp"):
                refresh_scene_media(next_scene, "clip_image", ".webp", clip_image_last, True)

            narration_image_last = current_scene.get("narration_image_last", "")
            if narration_image_last and narration_image_last.endswith(".webp"):
                refresh_scene_media(next_scene, "narration_image", ".webp", narration_image_last, True)

            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()


    def fetch_last_image(self):
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        # fetch last image from clip video, the refresh the clip_image_last field & try to replace next scene['clip_image'] with last_image ? if yes, replace it.
        clip_video = get_file_path(scene, "clip")
        if clip_video:
            last_image = self.workflow.ffmpeg_processor.extract_frame(clip_video, False)
            if last_image:
                refresh_scene_media(scene, "clip_image_last", ".webp", last_image, True)
                next_scene = self.workflow.next_scene_of_story(scene)
                if next_scene:
                    refresh_scene_media(next_scene, "clip_image", ".webp", last_image, True)


    def copy_clip_to_download(self, full:bool):
        """重新创建主图，先打开对话框让用户审查和编辑提示词"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)

        clip_video = get_file_path(scene, "clip")
        if clip_video:
            download_path = os.path.join(os.path.expanduser('~'), 'Downloads')
            shutil.copy(clip_video, download_path)

        if full:
            clip_image = get_file_path(scene, "clip_image")
            if clip_image:
                download_path = os.path.join(os.path.expanduser('~'), 'Downloads')
                shutil.copy(clip_image, download_path)
            #copy the clip_audio to download folder
            clip_audio = get_file_path(scene, "clip_audio")
            if clip_audio:
                download_path = os.path.join(os.path.expanduser('~'), 'Downloads')
                shutil.copy(clip_audio, download_path)


    def describe_scene(self, host=None, visual=False, visual_style=None, motion=None, host_show_image=False):
        """生成场景视频描述（由选项对话框调用，或直接传参）"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("提示", "没有当前场景")
            return

        if visual_style is None:
            visual_style = scene.get("visual_style") or (project_manager.PROJECT_CONFIG or {}).get("visual_style")

        if visual:
            scene_video_desc = f"""
                Make a visual scene like below (use this just as a reference, to help express the speaking & voiceover content): 
                {scene.get("visual", "")}
            """
        else:
            scene_video_desc = "Make a video to express the speaking & voiceover content\n\n"

        # Speaker 形象提示
        scene_video_desc += f"""
            the speaker is character (appears as {visual_style} style) of the story - {scene.get("actor", "")} - {scene.get("actions", "")}
            speaking like below (use this just as a reference, please make a very concise version):  
            {scene.get("speaking", "")}

        """

        if host:
            if host_show_image:
                # Host 形象显示在视频中，呈现为所选形象
                host_hint = f"The host appears as {host} style in the video."
            else:
                # 不显示 Host 画面，仅旁白
                host_hint = "Don't show host's image in the video, just use voiceover."
            scene_video_desc += f"""
                the host-{host}  ({host_hint})
                give voiceover for this scene like below (use this just as a reference, please make a very concise version): 
                {scene.get("voiceover", "")}

            """

        if motion:
            scene_video_desc += f"\nThe scene should have: {motion}.\n"

        # pop up a dialog to show the scene_video_desc & copy to clipboard
        dialog = tk.Toplevel(self.root)
        dialog.title("Scene Video Description")
        dialog.geometry("700x500")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 700) // 2
        y = (dialog.winfo_screenheight() - 500) // 2
        dialog.geometry(f"700x500+{x}+{y}")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(scene_video_desc.strip())
            self.root.update()
        except Exception:
            pass
        ttk.Label(dialog, text="Scene Video Description（已复制到剪贴板）", font=("TkDefaultFont", 10)).pack(anchor="w", padx=15, pady=(15, 5))
        text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, width=80, height=22)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        text_widget.insert("1.0", scene_video_desc.strip())
        ttk.Button(dialog, text="关闭", command=dialog.destroy).pack(pady=10)
        return scene_video_desc


    def _build_and_show_story_content(self, current_story_scenes, visual_style, narrator, host_display, include_visual=True, include_voiceover=True):
        """根据选项构建 Story Content JSON。Speaker/Host 共用 visual_style；narrator 为 NARRATOR id；host_display 为英文 value。"""
        scenes_data = []
        for s in current_story_scenes:
            item = {
                "visual_style": s.get("visual_style", visual_style),
                "actor": str(s.get("actor", "")).strip(),
                "speaking": s.get("speaking", ""),
                "actions": s.get("actions", "")
            }

            nar = s.get("narrator", None)
            if nar:
                item["narrator"] = nar + " | " + s.get("host_display", host_display)

            if include_visual:
                item["visual"] = s.get("visual", "")
            if include_voiceover:
                item["voiceover"] = s.get("voiceover", "")

            scenes_data.append(item)

        payload = {"scenes": scenes_data}
        initial_text = json.dumps(payload, indent=2, ensure_ascii=False)

        dialog = tk.Toplevel(self.root)
        dialog.title("Story Content")
        sw, sh = int(1000 * 1.3), 800  # 加宽约30%
        dialog.geometry(f"{sw}x{sh}")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - sw) // 2
        y = (dialog.winfo_screenheight() - sh) // 2
        dialog.geometry(f"{sw}x{sh}+{x}+{y}")

        ttk.Label(dialog, text="Story Content（已复制到剪贴板）").pack(anchor="w", padx=15, pady=(15, 5))

        opts_frame = ttk.Frame(dialog)
        opts_frame.pack(fill=tk.X, padx=15, pady=(0, 5))
        ttk.Label(opts_frame, text="Visual style:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(opts_frame, text=visual_style).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(opts_frame, text="Host display:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(opts_frame, text=host_display).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(opts_frame, text="Narrator:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(opts_frame, text=narrator).pack(side=tk.LEFT, padx=(0, 12))
        # 四个 checkbox：Speaking、Visual、Voiceover、Actions
        include_visual_chk_var = tk.BooleanVar(value=True)
        include_voiceover_chk_var = tk.BooleanVar(value=False)
        include_actions_chk_var = tk.BooleanVar(value=True)


        def _do_build():
            scenes_data = []
            for s in current_story_scenes:
                item = {}
                item["actions"] = s.get("actions", "")
                item["actor"] = str(s.get("actor", "")).strip()
                item["speaking"] = s.get("speaking", "")
                item["visual"] = s.get("visual", visual_style)
                item["narrator"] = s.get("narrator", narrator)

                hs_display = s.get("host_display", host_display)

                if include_voiceover_chk_var.get():
                    item["voiceover"] = s.get("voiceover", "")

                if item.get("narrator"):
                    if hs_display == config_prompt.HARRATOR_DISPLAY_OPTIONS[-1]:
                        item["narrator"] = "Narrator - " + item["narrator"] + " - not show in the screen, only speaking"
                    else:
                        item["narrator"] = "Narrator - " + item["narrator"] + " - pop up in the screen (if has previous scene, try keep its image back to background, while actor (if has) in previous image not speaking)"

                scenes_data.append(item)

            new_text = json.dumps({"scenes": scenes_data}, indent=2, ensure_ascii=False)
            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", new_text)
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(config_prompt.SLIDESHOW_GENERATION_INSTRUCTION.format(visual_style=visual_style) + "\n\n" + new_text.strip())
                self.root.update()
            except Exception:
                pass
            return new_text


        ttk.Checkbutton(opts_frame, text="Visual", variable=include_visual_chk_var, command=_do_build).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Checkbutton(opts_frame, text="Voiceover", variable=include_voiceover_chk_var, command=_do_build).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Checkbutton(opts_frame, text="Actions", variable=include_actions_chk_var, command=_do_build).pack(side=tk.LEFT)

        text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, width=110, height=24)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        def _on_double_click_paste_hint(e):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append("Use the source named 'Pasted Text / 粘贴的文字' as prompt instruction, and generate the Slide-Show")
                self.root.update()
            except Exception:
                pass
        text_widget.bind("<Double-1>", _on_double_click_paste_hint)
        text_widget.insert("1.0", initial_text)

        new_text = _do_build()

        input_media_path = config.INPUT_MEDIA_PATH
        # get the category of the story
        _cat_raw = project_manager.PROJECT_CONFIG.get('topic_category', '')
        if _cat_raw:
            _cat = make_safe_file_name(_cat_raw, title_length=6)
        else:
            _cat = ""

        filename = project_manager.PROJECT_CONFIG.get('video_title', '').strip() + '_'
        file_path = os.path.join(input_media_path, 'story__' + _cat + '__' + filename + '.txt')
        if os.path.exists(file_path):
            os.remove(file_path)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_text)


    def describe_story_content(self):
        """直接使用默认值生成 Story Content（不再弹出选项对话框）"""
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("提示", "没有当前场景")
            return
        current_story_scenes = self.workflow.scenes_in_story(scene)
        if not current_story_scenes:
            messagebox.showwarning("提示", "当前故事无场景")
            return

        visual_style = project_manager.PROJECT_CONFIG.get("visual_style", config.VISUAL_STYLE_OPTIONS[0])
        narrator = project_manager.PROJECT_CONFIG.get("narrator", config.CHARACTER_PERSON_OPTIONS[0])
        host_display = project_manager.PROJECT_CONFIG.get("host_display", config_prompt.HARRATOR_DISPLAY_OPTIONS[0])

        self._build_and_show_story_content(
            current_story_scenes,
            visual_style=visual_style,
            narrator=narrator,
            host_display=host_display,
            include_visual=True,
            include_voiceover=True,
        )


    def describe_scene_content(self):
        self.root.update_idletasks()
        self.update_current_scene()
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        if not scene:
            messagebox.showwarning("提示", "没有当前场景")
            return

        visual_style = scene.get("visual_style") or project_manager.PROJECT_CONFIG.get("visual_style")
        host_display = scene.get("host_display") or project_manager.PROJECT_CONFIG.get("host_display")

        item = {
            "visual_style": visual_style,
            "visual": scene.get("visual", "")
        }

        if scene.get("actor"):
            item["actor"] = scene.get("actor")
            item["actions"] = scene.get("actions")

        if scene.get("narrator"):
            item["narrator"] = scene.get("narrator") + " | " + host_display
            item["visual"] = "the video image should keep stable as the starting image (keep the narrator in same position), not jump to other background because of the content narration | " + item["visual"]

        if scene.get("speaking"):  
            item["speaking"] = scene.get("speaking")

        scene_video_desc = config_prompt.SCENE_VIDEO_INSTRUCTION.format(visual_style=visual_style) + "\n\n" + json.dumps(item, indent=2, ensure_ascii=False)

        dialog = tk.Toplevel(self.root)
        dialog.title("Scene Video Description")
        dialog.geometry("700x500")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 700) // 2
        y = (dialog.winfo_screenheight() - 500) // 2
        dialog.geometry(f"700x500+{x}+{y}")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(scene_video_desc.strip())
            self.root.update()
        except Exception:
            pass
        ttk.Label(dialog, text="Scene Video Description（已复制到剪贴板）", font=("TkDefaultFont", 10)).pack(anchor="w", padx=15, pady=(15, 5))
        text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, width=80, height=22)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        text_widget.insert("1.0", scene_video_desc.strip())
        ttk.Button(dialog, text="关闭", command=dialog.destroy).pack(pady=10)
		
        return scene_video_desc


    def update_current_scene(self, event=None):
        scene = self.workflow.get_scene_by_index(self.current_scene_index)
        
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

        # 焦点移到模态框时 ttk.Combobox.get() 可能暂时为空，勿用默认值覆盖已选 host_display
        _hd_en = self.scene_host_display.get() or scene.get("host_display")
        _vs_lbl = (self.scene_visual_style.get() or "").strip()
        if _vs_lbl:
            _vs_en = _vs_lbl
        else:
            _vs_en = (
                scene.get("visual_style")
                or (project_manager.PROJECT_CONFIG or {}).get("visual_style")
                or config.VISUAL_STYLE_OPTIONS[0]
            )

        scene.update({
            "speaking": self.scene_speaking.get("1.0", tk.END).strip(),
            "actor": self.scene_speaker.get().strip(),
            "actions": self.scene_actions.get("1.0", tk.END).strip(),
            "visual": self.scene_visual.get("1.0", tk.END).strip(),
            "narrator": self.scene_narrator.get(),
            "host_display": _hd_en,
            "visual_style": _vs_en,
            "voiceover": self.scene_voiceover.get("1.0", tk.END).strip(),
            "caption": self.scene_caption.get("1.0", tk.END).strip(),

            "clip_animation": self.clip_animate.get(),
            "narration_animation": self.narration_animation.get()
        })
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
                self.shared_language.config(text=language)
                
            # 加载频道 (只读标签)
            channel = config_data.get('channel', 'strange_zh')
            if hasattr(self, 'shared_channel'):
                self.shared_channel.config(text=channel)
                
            # 加载视频标题
            video_title = config_data.get('video_title', '默认标题')
            if hasattr(self, 'video_title'):
                self.video_title.delete(0, tk.END)
                self.video_title.insert(0, video_title)
                
            # 加载宣传视频滚动持续时间
            promo_scroll_duration = config_data.get('promo_scroll_duration', 7.0)
            self.promo_scroll_duration = promo_scroll_duration
            
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
        """获取当前的配置数据（以 PROJECT_CONFIG 为基底，保留 topic_category/topic_subtype/init_content 等所有字段）"""
        config_data = (project_manager.PROJECT_CONFIG.copy() if project_manager.PROJECT_CONFIG else {})
        # 仅覆盖 GUI 可编辑的字段
        config_data.update({
            'pid': self.get_pid(),
            'language': self.shared_language.cget('text'),
            'channel': self.shared_channel.cget('text'),
            'video_title': getattr(self, 'video_title', None) and self.video_title.get() or '默认视频标题',
            'video_width': config_data.get('video_width', '1920'),
            'video_height': config_data.get('video_height', '1080'),
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
        """保存当前项目配置（以 PROJECT_CONFIG 为基底，保留 topic_category/topic_subtype/init_content 等所有字段）"""
        try:
            workflow = self.workflow
            # 以现有配置为基底，避免丢失 topic_category/topic_subtype/init_content 等
            config_data = (project_manager.PROJECT_CONFIG.copy() if project_manager.PROJECT_CONFIG else {})
            config_data.pop('debut_content', None)
            # 仅覆盖 GUI 可编辑的字段
            config_data.update({
                'pid': self.get_pid(),
                'language': self.shared_language.cget('text'),
                'channel': self.shared_channel.cget('text'),
                'video_title': getattr(self, 'video_title', None) and self.video_title.get() or '视频标题',
                'video_width': config_data.get('video_width', '1920'),
                'video_height': config_data.get('video_height', '1080'),
            })

            # Save audio_prepares data if available
            if workflow and hasattr(workflow, 'audio_prepares'):
                config_data['audio_prepares'] = workflow.video_prepares

            # 更新当前项目配置（统一通过 set_global_config）
            ProjectConfigManager.set_global_config(config_data)
            
            # 保存到文件
            config_manager = ProjectConfigManager(self.get_pid())
            config_manager.save_project_config(config_data)
                
        except Exception as e:
            print(f"❌ 保存项目配置失败: {e}")



    def bind_edit_events(self):
        """绑定编辑事件"""
        # 绑定场景信息编辑字段的Enter键事件，用于自动保存
        scene_fields = [
            self.scene_speaking,
            self.scene_speaker,
            self.scene_actions,
            self.scene_visual,
            self.scene_narrator,
            self.scene_voiceover,
            self.scene_caption
        ]
        for field in scene_fields:
            # 绑定Enter键事件（Ctrl+Enter在ScrolledText中触发保存）
            field.bind('<Control-Return>', self.on_scene_field_enter)
            field.bind('<Control-Enter>', self.on_scene_field_enter)
            # 也绑定失去焦点事件作为备选保存机制
            field.bind('<FocusOut>', self.on_scene_field_focus_out)
        
        # 为Entry和Combobox字段单独绑定失去焦点事件
        entry_combobox_fields = [
            self.scene_speaker,
            self.scene_narrator,
            self.scene_host_display,
            self.scene_visual_style,
        ]
        for field in entry_combobox_fields:
            field.bind('<FocusOut>', self.on_scene_field_focus_out)
            field.bind('<<ComboboxSelected>>', self.update_current_scene)
        
        print("📝 已绑定场景编辑字段的自动保存事件 (Ctrl+Enter 或失去焦点时保存)")
    


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
        if hasattr(self, '_loading_config') and self._loading_config:
            return
        
        # 直接更新workflow的title属性
        if hasattr(self, 'workflow') and self.workflow is not None:
            gui_title = self.video_title.get().strip()
            if gui_title and gui_title != "......":
                self.workflow.title = gui_title
                print(f"🏷️ Workflow title updated: {gui_title}")
        
        # 保存配置
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


    def on_scene_field_focus_out(self, event=None):
        """当场景编辑字段失去焦点时的回调"""
        # 延迟保存以避免频繁操作（仅取消有效的 after id，避免 None/已失效 id 触发 ValueError）
        tid = getattr(self, '_save_timer', None)
        if tid:
            try:
                self.root.after_cancel(tid)
            except (ValueError, tk.TclError):
                pass
        self._save_timer = self.root.after(500, lambda: self.update_current_scene())


    def on_volume_change(self, *args):
        """当音量滑块值发生变化时的回调"""
        volume = self.track_volume_var.get()
        self.volume_label.config(text=f"{volume:.1f}")


    def on_tab_changed(self, event):
        if not hasattr(self, 'workflow') or self.workflow is None:
            return
        self.refresh_gui_scenes()


    def setup_drag_and_drop(self):
        self.video_canvas.drop_target_register(DND_FILES)
        self.video_canvas.dnd_bind('<<Drop>>', self.on_media_drop)
        self.video_canvas.dnd_bind('<<DragEnter>>', self.on_video_drag_enter)
        self.video_canvas.dnd_bind('<<DragLeave>>', self.on_video_drag_leave)
        
        # 添加双击事件绑定
        self.video_canvas.bind('<Double-Button-1>', self.on_video_canvas_double_click)


    def handle_video_replacement(self, video_path, replace_media_audio, media_type):
        """处理音频替换"""
        try:
            current_scene = self.workflow.get_scene_by_index(self.current_scene_index)

            current_scene[media_type + "_fps"] = self.workflow.ffmpeg_processor.get_video_fps(video_path)
            video_path = self.workflow.ffmpeg_processor.resize_video(video_path, width=None, height=self.workflow.ffmpeg_processor.height)

            print(f"🎬 打开合并编辑器 - 媒体类型: {media_type}, 替换音频: {replace_media_audio}")
            if media_type == "zero":
                replace_media_audio = "keep"

            review_dialog = AVReviewDialog(self, video_path, current_scene, self.workflow.get_previous_scene(self.current_scene_index), self.workflow.get_next_scene(self.current_scene_index), media_type, replace_media_audio)
            self.root.wait_window(review_dialog.dialog)

            if (not review_dialog.result) or ('transcribe_way' not in review_dialog.result) or  ('audio_json' not in review_dialog.result):
                print("场景内容无变化")
                return

            transcribe_way = review_dialog.result['transcribe_way']
            audio_json = review_dialog.result['audio_json']
            if not audio_json or (transcribe_way != "single" and transcribe_way != "multiple"):
                print("场景内容无变化 2")
                return

            if media_type != "clip" and media_type != "narration":
                if transcribe_way == "multiple":
                    scenes_same_story = self.workflow.scenes_in_story(current_scene)
                    for sss in scenes_same_story:
                        sss[media_type] = current_scene.get(media_type, None)
                        sss[media_type+"_audio"]  = current_scene.get(media_type+"_audio", None)
                        sss[media_type+"_image"]  = current_scene.get(media_type+"_image", None)
                        sss[media_type+"_image_last"]  = current_scene.get(media_type+"_image_last", None)
                self.workflow.save_scenes_to_json()
                return

            self.workflow.save_scenes_to_json()

            # media_type == clip
            if len(audio_json) > 1:
                self.workflow.replace_scene_with_others(self.current_scene_index, audio_json)
                current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
                for sss in audio_json:
                    sss[media_type + "_status"] = "ORIG"
            else:
                current_scene[media_type + "_status"] = "ORIG"

            self.media_scanner.last_image_replacement(current_scene, video_path, media_type)
                
        except Exception as e:
            messagebox.showerror("错误", f"视频替换失败: {str(e)}")


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
        
        files = self.root.tk.splitlist(event.data)
        if not files:
            return
        dropped_file = files[0]
        if not os.path.exists(dropped_file) or not is_video_file(dropped_file):
            return
        
        from gui.media_type_selector import MediaTypeSelector
        selector = MediaTypeSelector(self.root, dropped_file, self.workflow.ffmpeg_processor.has_audio_stream(dropped_file), self.workflow.get_scene_by_index(self.current_scene_index))
        replace_media_audio, media_type = selector.show()
        if not media_type:
            return  # 用户取消
        self.handle_video_replacement(dropped_file, replace_media_audio, media_type)
        self.refresh_gui_scenes()


    def on_video_canvas_configure(self, event):
        """当video canvas尺寸改变时，动态调整提示文本位置"""
        canvas_width = event.width
        canvas_height = event.height
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        
        # 更新拖拽提示文本的位置到canvas中心
        self.video_canvas.coords("drag_hint", center_x, center_y)


    def on_video_canvas_double_click(self, event):
        current_scene = self.workflow.get_scene_by_index(self.current_scene_index)
        from gui.media_type_selector import MediaTypeSelector
        selector = MediaTypeSelector(self.root, None, True, current_scene)
        replace_media_audio, media_type = selector.show()
        if not media_type:
            return  # 用户取消

        video_path = get_file_path(current_scene, media_type)
        if media_type != 'clip' and video_path is None:
            oldv, video_path = refresh_scene_media(current_scene, media_type, ".mp4",  get_file_path(current_scene, "clip"), True)
            refresh_scene_media(current_scene, media_type+"_audio", ".wav", get_file_path(current_scene, "clip_audio"), True)
            refresh_scene_media(current_scene, media_type+"_image", ".webp", get_file_path(current_scene, "clip_image"), True)

        temp_video = config.get_temp_file(self.workflow.pid, "mp4")
        video_path = safe_copy_overwrite(video_path, temp_video)

        self.handle_video_replacement(video_path, replace_media_audio, media_type)
        self.refresh_gui_scenes()


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
        if val <= 0:
            if "extension" in scene:
                del scene["extension"]
        else:
            scene["extension"] = val
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
 


def main():
    import sys
    root = TkinterDnD.Tk()

    # 支持 --open-pid <pid> 参数：跳过欢迎屏，直接打开指定项目（用于从 YT「用Story启动新项目」创建后启动）
    initial_pid = None
    if len(sys.argv) >= 3 and sys.argv[1] == '--open-pid':
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

