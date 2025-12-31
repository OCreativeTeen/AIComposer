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
import pygame
import uuid
from magic_workflow import MagicWorkflow
import config
import config_prompt
import utility.sd_image_processor as sd_image_processor
from PIL import Image, ImageTk
from project_manager import ProjectConfigManager, create_project_dialog
import project_manager
from gui.picture_in_picture_dialog import PictureInPictureDialog
import cv2
import os
from utility.file_util import get_file_path, is_image_file, is_audio_file, is_video_file, refresh_scene_media, build_scene_media_prefix
from gui.media_review_dialog import AVReviewDialog
from utility.minimax_speech_service import MinimaxSpeechService, EXPRESSION_STYLES
from gui.wan_prompt_editor_dialog import show_wan_prompt_editor  # 添加这一行
from gui.image_prompts_review_dialog import IMAGE_PROMPT_OPTIONS, NEGATIVE_PROMPT_OPTIONS
import tkinterdnd2 as TkinterDnD
from tkinterdnd2 import DND_FILES
from utility.media_scanner import MediaScanner
import cv2
from pathlib import Path

from moviepy import VideoFileClip
import moviepy
mp = moviepy  # Create an alias for compatibility


def askchoice(title, choices):
    """
    自定义的多选择对话框函数
    返回用户选择的选项字符串
    """
    # 创建一个简单的选择对话框
    root = tk.Toplevel()
    root.title(title)
    root.geometry("300x200")
    root.resizable(False, False)
    
    # 居中显示
    root.transient()
    root.grab_set()
    
    result = None
    
    def on_choice(choice):
        nonlocal result
        result = choice
        root.destroy()
    
    # 添加标题
    label = tk.Label(root, text=title, font=("Arial", 12, "bold"))
    label.pack(pady=10)
    
    # 添加选择按钮
    for choice in choices:
        btn = tk.Button(root, text=choice, width=20, 
                       command=lambda c=choice: on_choice(c))
        btn.pack(pady=5)
    
    # 添加取消按钮
    cancel_btn = tk.Button(root, text="取消", width=20, 
                          command=lambda: root.destroy())
    cancel_btn.pack(pady=10)
    
    # 等待用户选择
    root.wait_window()
    return result

# askchoice函数定义完成，可以直接调用



STANDARD_FPS = 60  # Match FfmpegProcessor.STANDARD_FPS


class WorkflowGUI:
    # Standardized framerate to match video processing

    def __init__(self, root):
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
        self.second_delta = 0.0

        # 初始化配置加载标志
        self._loading_config = False
        self.current_scene_index = 0

        # 显示项目选择对话框
        if not self.show_project_selection():
            self.root.destroy()
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
        
        # 添加视频效果选择存储
        self.effect_radio_vars = {}  # {scene_index: tk.StringVar}
        
        # 添加当前效果和图像类型选择变量
        self.scene_second_animation = tk.StringVar(value=config_prompt.ANIMATE_SOURCE[0])
        
        # 创建动画名称到提示语的映射字典（双向）
        self.animation_name_to_prompt = {item["name"]: item["prompt"] for item in config_prompt.ANIMATION_PROMPTS}
        self.animation_prompt_to_name = {item["prompt"]: item["name"] for item in config_prompt.ANIMATION_PROMPTS}
        self.animation_names = [""] + list(self.animation_name_to_prompt.keys())
        
        # 添加第二轨道音量控制变量
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
        
        # 启动单例后台视频检查线程
        self.start_video_check_thread()
        
        self.media_scanner = MediaScanner(self.workflow, 10)
        # 绑定窗口关闭事件

        self.workflow.load_scenes()
        self.on_tab_changed(None)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)



    pid = None

    def get_pid(self):
        if self.pid is None:
            self.pid = project_manager.PROJECT_CONFIG.get('pid')
        return self.pid
    


    def create_workflow_instance(self):
        """立即创建工作流实例（非懒加载）"""
        try:
            # Get video dimensions from project config
            video_width = project_manager.PROJECT_CONFIG.get('video_width')
            video_height = project_manager.PROJECT_CONFIG.get('video_height')
            language = project_manager.PROJECT_CONFIG.get('language')
            channel = project_manager.PROJECT_CONFIG.get('channel')

            self.workflow = MagicWorkflow(self.get_pid(), language, channel, video_width, video_height)
            self.speech_service = MinimaxSpeechService(self.get_pid())
            
            current_gui_title = self.video_title.get().strip()
            self.workflow.post_init(current_gui_title)
            
            print("✅ 工作流实例创建完成")
            
        except Exception as e:
            print(f"❌ 创建工作流实例失败: {e}")
            self.workflow = None


    def get_current_scene(self):
        if not hasattr(self, 'workflow') or self.workflow is None or not hasattr(self.workflow, 'scenes') or self.workflow.scenes is None:
            return None
            
        if self.workflow.scenes and self.current_scene_index >= 0 and self.current_scene_index < len(self.workflow.scenes):
            return self.workflow.scenes[self.current_scene_index]
        else:
            return None
    

    def get_previous_scene(self):
        if self.workflow.scenes and self.current_scene_index > 0 and self.current_scene_index < len(self.workflow.scenes):
            return self.workflow.scenes[self.current_scene_index - 1]
        else:
            return None    


    def get_next_scene(self):
        if self.workflow.scenes and self.current_scene_index >= 0 and self.current_scene_index < len(self.workflow.scenes)-1:
            return self.workflow.scenes[self.current_scene_index + 1]
        else:
            return None


    def get_previous_story_last_scene(self):
        if self.workflow.scenes and self.current_scene_index > 0 and self.current_scene_index < len(self.workflow.scenes):
            # loop from self.current_scene_index to 0,  
            for i in range(self.current_scene_index, 0, -1):
                if self.workflow.scenes[i]["id"]%10000 != self.workflow.scenes[self.current_scene_index]["id"]%10000:
                    return self.workflow.scenes[i]
        return None    

    
    def show_project_selection(self):
        # 使用新的项目管理器
        result, selected_config = create_project_dialog(self.root)
        
        if result == 'cancel':
            return False
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
        
        scene_nav_row = ttk.Frame(row1_frame)
        scene_nav_row.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Separator(scene_nav_row, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(scene_nav_row, text="⏮", width=3, command=self.first_scene).pack(side=tk.LEFT, padx=2)
        ttk.Separator(scene_nav_row, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Label(scene_nav_row, text="场景:").pack(side=tk.LEFT)
        ttk.Button(scene_nav_row, text="◀", width=3, command=self.prev_scene).pack(side=tk.LEFT, padx=2)
        self.scene_label = ttk.Label(scene_nav_row, text="0 / 0", width=7)
        self.scene_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(scene_nav_row, text="▶", width=3, command=self.next_scene).pack(side=tk.LEFT, padx=2)
        ttk.Separator(scene_nav_row, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(scene_nav_row, text="⏭", width=3, command=self.last_scene).pack(side=tk.LEFT, padx=2)
        ttk.Separator(scene_nav_row, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(row1_frame, text="拷贝图",   command=self.copy_images_to_next).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1_frame, text="场景交换", command=self.swap_scene).pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(row1_frame, text="视频合成", command=lambda:self.run_finalize_video()).pack(side=tk.LEFT, padx=2)
        #ttk.Button(row1_frame, text="视背合成", command=lambda:self.run_finalize_video(zero_audio_only=True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1_frame, text="推广合成", command=lambda:self.run_promotion_video()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1_frame, text="上传视频", command=self.run_upload_video).pack(side=tk.LEFT, padx=2)
        #ttk.Button(scene_nav_row, text="拼接视频", command=self.run_final_concat_video).pack(side=tk.LEFT, padx=2)

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

        tool_frame = ttk.Frame(row1_frame)
        tool_frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(tool_frame, text="Video生成", command=self.start_video_gen_batch).pack(side=tk.LEFT) 
        ttk.Button(tool_frame, text="媒体清理",  command=self.clean_media).pack(side=tk.LEFT) 
        ttk.Button(tool_frame, text="WAN清理",   command=self.clean_wan).pack(side=tk.LEFT) 
        ttk.Button(tool_frame, text="标记清理",  command=self.clean_media_mark).pack(side=tk.LEFT)

   
    def open_image_prompt_dialog(self, create_image_callback, scene, image_mode, language:str):
        """打开提示词审查对话框，用于在创建图像前预览和编辑提示词"""
        from gui.image_prompts_review_dialog import ImagePromptsReviewDialog
        
        dialog = ImagePromptsReviewDialog(
            parent=self,
            workflow=self.workflow,
            create_image_callback=create_image_callback,
            scene=scene,
            track=image_mode,
            language=language
        )
        dialog.show()


    def swap_second(self):
        """交换第一轨道与第二轨道"""
        current_scene = self.get_current_scene()
        clip_video_path = get_file_path(current_scene, 'clip')
        clip_audio_path = get_file_path(current_scene, 'clip_audio')
        track_path = get_file_path(current_scene, "second")
        if not track_path:
            messagebox.showwarning("警告", "second 轨道视频文件不存在")
            return
        temp_track = self.workflow.ffmpeg_processor.add_audio_to_video(track_path, clip_audio_path)

        refresh_scene_media(current_scene, "second", '.mp4', clip_video_path)
        refresh_scene_media(current_scene, "second_audio", '.wav', clip_audio_path, True)

        refresh_scene_media(current_scene, 'clip', '.mp4', temp_track)
        self.refresh_gui_scenes()


    def swap_zero(self):
        """交换第一轨道与第二轨道"""
        current_scene = self.get_current_scene()
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
        current_scene = self.get_current_scene()
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
        """重置第二轨道播放偏移量到当前场景的起始位置"""
        current_scene = self.get_current_scene()
        if not current_scene:
            self.second_track_offset = 0
            self.second_track_paused_time = None
            return
            
        self.second_track_offset, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scene_detail(current_scene)
        self.second_track_paused_time = None
        print(f"🔄 重置第二轨道偏移量: {self.second_track_offset:.2f}s")
        self.update_second_track_time_display()


    def fetch_second_clip(self, to_end, volume):
        current_scene = self.get_current_scene()
        second_track_path = get_file_path(current_scene, 'second')
        second_audio_path = get_file_path(current_scene, 'second_audio')
        if not second_track_path:
            messagebox.showwarning("警告", "第二轨道视频文件不存在")
            return
        
        second_track_duration = self.workflow.ffmpeg_processor.get_duration(second_track_path)

        if not self.second_track_cap:
            second_time = 0
        else:
            second_pos = self.second_track_cap.get(cv2.CAP_PROP_POS_FRAMES)
            second_time = second_pos / STANDARD_FPS

        if second_time <= 0:
            second_time, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scene_detail(current_scene)

        if second_track_duration < second_time:
            second_time = 0

        if to_end:
            second_v = self.workflow.ffmpeg_processor.trim_video(second_track_path, second_time, None, volume)
            second_a = self.workflow.ffmpeg_audio_processor.audio_cut_fade(second_audio_path, second_time, None, 1.0, 1.0,volume)
        else:
            clip_duration = self.workflow.find_clip_duration(current_scene)
            second_v = self.workflow.ffmpeg_processor.trim_video(second_track_path, second_time, second_time+clip_duration, volume)
            second_a = self.workflow.ffmpeg_audio_processor.audio_cut_fade(second_audio_path, second_time, clip_duration, 1.0, 1.0, volume)

        return second_v, second_a


    def choose_second_track(self, track_id):
        """选择第二轨道并重置播放状态"""
        self.selected_second_track = track_id
        # 重置播放偏移量到当前场景的起始位置
        self.reset_track_offset()
        # 切换 tab 并加载第一帧
        self.on_second_track_tab_changed()



    def pip_second_track(self, from_zero):
        """将第二轨道作为画中画叠加到主轨道视频上"""
        try:
            current_scene = self.get_current_scene()
            second_path = get_file_path(current_scene, self.selected_second_track)
            second_audio = get_file_path(current_scene, self.selected_second_track+'_audio')
            second_left = get_file_path(current_scene, self.selected_second_track+'_left')
            second_right = get_file_path(current_scene, self.selected_second_track+'_right')
            if not second_path or not second_audio:
                messagebox.showwarning("警告", "第二轨道视频文件不存在")
                return

            clip_video = get_file_path(current_scene, "clip")
            clip_audio = get_file_path(current_scene, "clip_audio")
            start_time, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scene_detail(current_scene)
            if from_zero:
                start_time = 0

            start_time = start_time + self.second_delta

            if is_story_last_clip: 
                second_track_copy = self.workflow.ffmpeg_processor.trim_video(second_path, start_time)
                second_audio_copy = self.workflow.ffmpeg_audio_processor.audio_cut_fade(second_audio, start_time, None, 0, 0, 1.0)
            else:    
                second_track_copy = self.workflow.ffmpeg_processor.trim_video(second_path, start_time, start_time+clip_duration)
                second_audio_copy = self.workflow.ffmpeg_audio_processor.audio_cut_fade(second_audio, start_time, clip_duration, 0, 0, 1.0)
            print(f"📺 打开画中画设置对话框...")
            
            # 创建画中画设置对话框
            pip_dialog = PictureInPictureDialog(self.root, clip_video, second_track_copy, second_left, second_right)
            
            # 等待对话框关闭
            self.root.wait_window(pip_dialog.dialog)
            
            # 检查用户的选择
            if pip_dialog.result:
                settings = pip_dialog.result
                print(f"📺 用户选择的画中画设置: {settings}")

                back = current_scene.get('back', '')
                current_scene['back'] = clip_video + "," + back

                if settings['position'] == "full":
                    v = self.workflow.ffmpeg_processor.add_audio_to_video(second_track_copy, clip_audio)
                    refresh_scene_media(current_scene, 'clip', '.mp4', v)
                elif settings['position'] == "av":
                    refresh_scene_media(current_scene, 'clip', '.mp4', second_track_copy)
                    refresh_scene_media(current_scene, 'clip_audio', '.wav', second_audio_copy)
                else:
                    # 处理画中画
                    self.process_picture_in_picture(
                        background_audio=clip_audio,
                        background_video=clip_video,
                        overlay_video=second_track_copy,
                        overlay_audio=second_audio_copy,
                        overlay_left=second_left,
                        overlay_right=second_right,
                        settings=settings
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


    def process_picture_in_picture(self, background_video, background_audio, overlay_video, overlay_audio, overlay_left, overlay_right, settings):
        """处理画中画视频生成"""
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
            if settings['audio_volume'] == 0.0:
                olda, output_audio = refresh_scene_media(self.get_current_scene(), "clip_audio", ".wav", background_audio, True)
                output_video = self.workflow.ffmpeg_processor.add_audio_to_video(output_video, background_audio)
                olda, output_video = refresh_scene_media(self.get_current_scene(), "clip", ".mp4", output_video, True)
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
                    olda, output_audio = refresh_scene_media(self.get_current_scene(), "clip_audio", ".wav", output_audio, True)

                    output_video = self.workflow.ffmpeg_processor.add_audio_to_video(output_video, output_audio)
                    olda, output_video = refresh_scene_media(self.get_current_scene(), "clip", ".mp4", output_video, True)
            
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
        video_frame = ttk.LabelFrame(main_content, text="预览", padding=10)
        video_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        # 设置左侧面板的最大宽度，为右侧面板留出空间
        video_frame.configure(width=1700)
        video_frame.pack_propagate(False)

        # 创建水平布局框架来并排显示图像标签和视频画布
        preview_frame = ttk.Frame(video_frame)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧区域：背景轨道和第二轨道（减少宽度给video_canvas更多空间）
        left_frame = ttk.Frame(preview_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        # 设置左侧框架的宽度，为video_canvas留出更多空间
        left_frame.configure(width=640)
        left_frame.pack_propagate(False)
        
        # 角色选择组合框框架
        roles_frame = ttk.Frame(left_frame)
        roles_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 图片预览区域（原zero位置）
        images_preview_frame = ttk.LabelFrame(left_frame, text="图片预览 (支持拖放)", padding=5)
        images_preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建3个图片预览canvas (clip_image, second_image, zero_image)
        images_container = ttk.Frame(images_preview_frame)
        images_container.pack(fill=tk.BOTH, expand=True)
        
        # Replace the images_preview_frame section (lines 794-859) with this enhanced version:
        # === Clip Image Canvas (clip_image + clip_image_last) ===
        clip_img_frame = ttk.Frame(images_container)
        clip_img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2))
        ttk.Label(clip_img_frame, text="Clip", anchor=tk.CENTER).pack()

        # Clip image container with two sub-canvases
        clip_canvas_container = ttk.Frame(clip_img_frame)
        clip_canvas_container.pack(fill=tk.BOTH, expand=True)

        # Top: clip_image
        self.clip_image_canvas = tk.Canvas(clip_canvas_container, bg='gray20', width=150, height=75, 
                                        highlightthickness=2, highlightbackground='blue')
        self.clip_image_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 1))
        self.clip_image_canvas.create_text(75, 37, text="Clip\nImage", fill="gray", font=("Arial", 8), 
                                        justify=tk.CENTER, tags="hint")

        self.clip_image_canvas.drop_target_register(DND_FILES)
        self.clip_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'clip_image'))

        # Bottom: clip_image_last
        self.clip_image_last_canvas = tk.Canvas(clip_canvas_container, bg='gray20', width=150, height=75, 
                                                highlightthickness=2, highlightbackground='blue')
        self.clip_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.clip_image_last_canvas.create_text(75, 37, text="Clip\nLast", fill="gray", font=("Arial", 8), 
                                            justify=tk.CENTER, tags="hint")

        self.clip_image_last_canvas.drop_target_register(DND_FILES)
        self.clip_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'clip_image_last'))

        # === Zero Image Canvas (zero_image + zero_image_last) ===
        zero_img_frame = ttk.Frame(images_container)
        zero_img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        ttk.Label(zero_img_frame, text="Zero", anchor=tk.CENTER).pack()

        zero_canvas_container = ttk.Frame(zero_img_frame)
        zero_canvas_container.pack(fill=tk.BOTH, expand=True)

        # Top: zero_image
        self.zero_image_canvas = tk.Canvas(zero_canvas_container, bg='gray20', width=150, height=75, 
                                        highlightthickness=2, highlightbackground='orange')
        self.zero_image_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 1))
        self.zero_image_canvas.create_text(75, 37, text="Zero\nImage", fill="gray", font=("Arial", 8), 
                                        justify=tk.CENTER, tags="hint")

        self.zero_image_canvas.drop_target_register(DND_FILES)
        self.zero_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'zero_image'))

        # Bottom: zero_image_last
        self.zero_image_last_canvas = tk.Canvas(zero_canvas_container, bg='gray20', width=150, height=75, 
                                                highlightthickness=2, highlightbackground='orange')
        self.zero_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.zero_image_last_canvas.create_text(75, 37, text="Zero\nLast", fill="gray", font=("Arial", 8), 
                                            justify=tk.CENTER, tags="hint")

        self.zero_image_last_canvas.drop_target_register(DND_FILES)
        self.zero_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'zero_image_last'))

        # === One Image Canvas (one_image + one_image_last) ===
        one_img_frame = ttk.Frame(images_container)
        one_img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        ttk.Label(one_img_frame, text="One", anchor=tk.CENTER).pack()

        one_canvas_container = ttk.Frame(one_img_frame)
        one_canvas_container.pack(fill=tk.BOTH, expand=True)

        # Top: one_image
        self.one_image_canvas = tk.Canvas(one_canvas_container, bg='gray20', width=150, height=75, 
                                        highlightthickness=2, highlightbackground='purple')
        self.one_image_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 1))
        self.one_image_canvas.create_text(75, 37, text="One\nImage", fill="gray", font=("Arial", 8), 
                                        justify=tk.CENTER, tags="hint")

        self.one_image_canvas.drop_target_register(DND_FILES)
        self.one_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'one_image'))

        # Bottom: one_image_last
        self.one_image_last_canvas = tk.Canvas(one_canvas_container, bg='gray20', width=150, height=75, 
                                            highlightthickness=2, highlightbackground='purple')
        self.one_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.one_image_last_canvas.create_text(75, 37, text="One\nLast", fill="gray", font=("Arial", 8), 
                                            justify=tk.CENTER, tags="hint")

        self.one_image_last_canvas.drop_target_register(DND_FILES)
        self.one_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'one_image_last'))

        # === Second Image Canvas (second_image + second_image_last) ===
        second_img_frame = ttk.Frame(images_container)
        second_img_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 0))
        ttk.Label(second_img_frame, text="Second", anchor=tk.CENTER).pack()

        second_canvas_container = ttk.Frame(second_img_frame)
        second_canvas_container.pack(fill=tk.BOTH, expand=True)

        # Top: second_image
        self.second_image_canvas = tk.Canvas(second_canvas_container, bg='gray20', width=150, height=75, 
                                            highlightthickness=2, highlightbackground='green')
        self.second_image_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 1))
        self.second_image_canvas.create_text(75, 37, text="Second\nImage", fill="gray", font=("Arial", 8), 
                                            justify=tk.CENTER, tags="hint")

        self.second_image_canvas.drop_target_register(DND_FILES)
        self.second_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'second_image'))

        # Bottom: second_image_last
        self.second_image_last_canvas = tk.Canvas(second_canvas_container, bg='gray20', width=150, height=75, 
                                                highlightthickness=2, highlightbackground='green')
        self.second_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.second_image_last_canvas.create_text(75, 37, text="Second\nLast", fill="gray", font=("Arial", 8), 
                                                justify=tk.CENTER, tags="hint")

        self.second_image_last_canvas.drop_target_register(DND_FILES)
        self.second_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'second_image_last'))
        

        # 视频轨道预览区域 - 使用Tab控件（包含second和zero）
        track_video_frame = ttk.LabelFrame(left_frame, text="轨道视频预览", padding=5)
        track_video_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建Notebook (Tab控件)
        self.second_notebook = ttk.Notebook(track_video_frame)
        self.second_notebook.pack(fill=tk.BOTH, expand=True)
        
        # === Tab 1: 完整第二轨道 ===
        tab_full_second = ttk.Frame(self.second_notebook)
        self.second_notebook.add(tab_full_second, text="完整视频")
        
        # 第二轨道视频画布
        self.second_track_canvas = tk.Canvas(tab_full_second, bg='black', width=360, height=180)
        self.second_track_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # 第二轨道提示文本
        self.second_track_canvas.create_text(160, 90, text="第二轨道视频预览\n选择视频后播放显示", 
                                            fill="gray", font=("Arial", 10), justify=tk.CENTER, tags="hint")
        
        # === Tab 2: 画中画 Left & Right ===
        tab_pip_lr = ttk.Frame(self.second_notebook)
        self.second_notebook.add(tab_pip_lr, text="画中画L/R")
        
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
        
        # 第二轨道播放按钮
        self.track_play_button = ttk.Button(self.track_frame, text="▶", command=self.toggle_track_playback,width=3)
        self.track_play_button.pack(side=tk.LEFT, padx=2)

        # add field to display current playing time / duration of second track, and 2 buttons to move forward and backward seconds
        self.track_time_label = ttk.Label(self.track_frame, text="00:00 / 00:00")
        self.track_time_label.pack(side=tk.LEFT, padx=2)
        
        #ttk.Button(self.second_track_frame, text="◀", command=self.move_second_track_backward, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.second_track_frame, text="▶", command=self.move_second_track_forward, width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="📺", command=lambda:self.pip_second_track(False), width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="📺", command=lambda:self.pip_second_track(True), width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="🔄", command=self.reset_track_offset, width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="💫", command=lambda:self.choose_second_track('zero'), width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="💫", command=lambda:self.choose_second_track('one'), width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="💫", command=lambda:self.choose_second_track('second'), width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="💫", command=self.swap_second, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="✨", command=self.swap_zero, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="🔊", command=self.pip_second_sound, width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="⏱",  command=self.track_recover, width=3).pack(side=tk.LEFT, padx=2)
        
        # 添加音量控制滑块（共用，根据当前tab自动选择）
        ttk.Label(self.track_frame, text="音量:").pack(side=tk.LEFT, padx=(10, 2))
        self.volume_scale = ttk.Scale(self.track_frame, from_=0.0, to=1.5, 
                                     variable=self.track_volume_var, orient=tk.HORIZONTAL, length=60)
        self.volume_scale.pack(side=tk.LEFT, padx=2)
        self.volume_label = ttk.Label(self.track_frame, text="0.2")
        self.volume_label.pack(side=tk.LEFT, padx=2)

        ttk.Button(self.track_frame, text="《《", command=lambda: self.adjust_second_delta(-0.5), width=3).pack(side=tk.LEFT, padx=1)
        self.second_delta_label = ttk.Label(self.track_frame, text="0.0s", width=4)
        self.second_delta_label.pack(side=tk.LEFT, padx=1)
        ttk.Button(self.track_frame, text="》》", command=lambda: self.adjust_second_delta(0.25), width=3).pack(side=tk.LEFT, padx=1)

        
        # 绑定音量变化事件来更新标签
        self.track_volume_var.trace('w', self.on_track_volume_change)
        
        # 初始化所有轨道播放相关变量
        # 图片预览引用（防止垃圾回收）
        self._clip_image_photo = None
        self._second_image_photo = None
        self._zero_image_photo = None
        
        # 绑定tab切换事件
        self.second_notebook.bind("<<NotebookTabChanged>>", self.on_second_track_tab_changed)

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
        ttk.Button(video_control_frame, text="《《", command=lambda: self.move_video(-0.25), width=3).pack(side=tk.LEFT, padx=1)
        self.playing_delta_label = ttk.Label(video_control_frame, text="0.0s", width=4)
        self.playing_delta_label.pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="》》", command=lambda: self.move_video(0.25), width=3).pack(side=tk.LEFT, padx=1)

        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Button(video_control_frame, text="分离", command=self.split_scene, width=5).pack(side=tk.LEFT, padx=1) 
        ttk.Button(video_control_frame, text="下移", command=lambda: self.shift_scene(True), width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="上移", command=lambda: self.shift_scene(False), width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="智分", command=self.split_smart_scene, width=5).pack(side=tk.LEFT, padx=1) 
        ttk.Button(video_control_frame, text="删合", command=self.merge_or_delete, width=5).pack(side=tk.LEFT, padx=1)

        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Button(video_control_frame, text="交换", command=self.swap_with_next_image, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="反转", command=self.reverse_video, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="镜像", command=self.mirror_video, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="标题", command=self.print_title, width=5).pack(side=tk.LEFT, padx=1)
        #ttk.Button(video_control_frame, text="背起", command=self.zero_start, width=5).pack(side=tk.LEFT, padx=1)
        #ttk.Button(video_control_frame, text="背继", command=self.zero_continue, width=5).pack(side=tk.LEFT, padx=1)
        #ttk.Button(video_control_frame, text="背终", command=self.zero_end, width=5).pack(side=tk.LEFT, padx=1)

        # 分隔符
        separator = ttk.Separator(video_control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # 存储按钮引用以便后续控制状态
        self.insert_scene_button = ttk.Button(video_control_frame, text="前插", command=self.insert_story_scene, width=6)
        self.insert_scene_button.pack(side=tk.LEFT, padx=1)

        self.append_scene_button = ttk.Button(video_control_frame, text="后插", command=self.append_scene, width=6)
        self.append_scene_button.pack(side=tk.LEFT, padx=1)

        # add 2 marks, to mark the current video progress seconds，　then add a button 'make_silence'　to make the audio  period between mark1 mark2 be silient
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
        self.video_progress_label = ttk.Label(video_control_frame, text="00:00.00 / 00:00.00")
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
        self.video_edit_frame.configure(width=650)
        self.video_edit_frame.pack_propagate(False)
        
        row_number = 1

        # 持续时间和宣传模式在同一行
        duration_promo_frame = ttk.Frame(self.video_edit_frame)
        duration_promo_frame.grid(row=row_number, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)
        row_number += 1

        # 持续时间（只读）
        ttk.Label(duration_promo_frame, text="持续:").pack(side=tk.LEFT)
        self.scene_duration = ttk.Entry(duration_promo_frame, width=12, state="readonly")
        self.scene_duration.pack(side=tk.LEFT, padx=(2, 10))
        
        # 宣传模式（可编辑）
        ttk.Label(duration_promo_frame, text="主动画:").pack(side=tk.LEFT, padx=(5, 5))
        self.scene_main_animate = tk.StringVar(value="")
        self.main_animate_combobox = ttk.Combobox(duration_promo_frame, textvariable=self.scene_main_animate, 
                                               values=config_prompt.ANIMATE_SOURCE, 
                                               state="readonly", width=10)
        self.main_animate_combobox.pack(side=tk.LEFT)
        self.main_animate_combobox.bind('<<ComboboxSelected>>', self.on_video_clip_animation_change)


        ttk.Label(duration_promo_frame, text="次动画:").pack(side=tk.LEFT, padx=(0, 5))
        self.second_animation_combobox = ttk.Combobox(duration_promo_frame, textvariable=self.scene_second_animation,
                                               values=config_prompt.ANIMATE_SOURCE, 
                                               state="readonly", width=10)
        self.second_animation_combobox.pack(side=tk.LEFT, padx=(0, 10))
        self.second_animation_combobox.bind('<<ComboboxSelected>>', self.on_image_type_change)

        # 类型、情绪、动作选择（在同一行）
        type_mood_action_frame = ttk.Frame(self.video_edit_frame)
        type_mood_action_frame.grid(row=row_number, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)
        row_number += 1

        ttk.Button(type_mood_action_frame, text="视觉提示", width=10, command=lambda: self.recreate_clip_image("en")).pack(side=tk.LEFT)
        ttk.Button(type_mood_action_frame, text="生视觉化", width=10, command=lambda: self.refresh_scene_visual()).pack(side=tk.LEFT)
        #ttk.Button(action_frame, text="生主图-英", width=10, command=lambda: self.recreate_clip_image("en", True)).pack(side=tk.LEFT, padx=2)
        #ttk.Button(action_frame, text="生次图-中", width=8, command=lambda: self.recreate_clip_image("zh", False)).pack(side=tk.LEFT, padx=2)
        #ttk.Button(action_frame, text="生次图-英", width=8, command=lambda: self.recreate_clip_image("en", False)).pack(side=tk.LEFT, padx=2)
        ttk.Button(type_mood_action_frame, text="生场音频", width=10, command=lambda: self.regenerate_audio()).pack(side=tk.LEFT)
        ttk.Button(type_mood_action_frame, text="生主动画", width=10, command=lambda: self.regenerate_video("clip")).pack(side=tk.LEFT)
        ttk.Button(type_mood_action_frame, text="生次动画", width=10, command=lambda: self.regenerate_video(None)).pack(side=tk.LEFT)


        action_frame = ttk.Frame(self.video_edit_frame)
        action_frame.grid(row=row_number, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)
        row_number += 1

        ttk.Button(action_frame, text="增主轨", width=10, command=lambda: self.enhance_clip(True, False)).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="增次轨", width=10, command=lambda: self.enhance_clip(False, False)).pack(side=tk.LEFT)

        # add a choice list to choose the enhance level, values are from config.FACE_ENHANCE, default value to "0"
        FACE_ENHANCE = ["0", "15", "30", "60"]
        self.enhance_level = ttk.Combobox(action_frame, width=5, values=FACE_ENHANCE)
        self.enhance_level.pack(side=tk.LEFT, padx=2)
        self.enhance_level.set("30")

        ttk.Button(action_frame, text="插主轨", width=10, command=lambda: self.enhance_clip(True, True)).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="插次轨", width=10, command=lambda: self.enhance_clip(False, True)).pack(side=tk.LEFT)
        #RIFE_EXP = ["0", "1", "2"]
        #self.rife_exp = ttk.Combobox(action_frame, width=5, values=RIFE_EXP)
        #self.rife_exp.pack(side=tk.LEFT, padx=2)
        #self.rife_exp.set("0")

        ttk.Label(self.video_edit_frame, text="内容:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_story_content = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_story_content.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        # add the text field to show the kernel
        ttk.Label(self.video_edit_frame, text="核心:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_kernel = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_kernel.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        # add the text field to show the kernel
        ttk.Label(self.video_edit_frame, text="故事:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_story = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_story.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="主体:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_subject = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_subject.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1
        
        ttk.Label(self.video_edit_frame, text="开场:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_visual_image = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_visual_image.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="结束:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_person_action = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_person_action.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="时代:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_era_time = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=1)
        self.scene_era_time.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1
        
        ttk.Label(self.video_edit_frame, text="环境:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_environment = ttk.Entry(self.video_edit_frame, width=35)
        self.scene_environment.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1
        
        ttk.Label(self.video_edit_frame, text="摄影:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_cinematography = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_cinematography.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1
        
        ttk.Label(self.video_edit_frame, text="音效:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_sound_effect = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_sound_effect.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="FYI:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_extra =  scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_extra.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="讲员:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_speaker_action = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_speaker_action.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="情绪:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_mood = ttk.Combobox(self.video_edit_frame, width=35, values=EXPRESSION_STYLES, state="readonly")
        self.scene_mood.set("calm")  # 设置默认值
        self.scene_mood.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="讲员:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_speaker = ttk.Combobox(self.video_edit_frame, width=32, values=config_prompt.ROLES)
        self.scene_speaker.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        ttk.Label(self.video_edit_frame, text="左右:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_speaker_position = ttk.Combobox(self.video_edit_frame, width=32, values=config_prompt.SPEAKER_POSITIONS)
        self.scene_speaker_position.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        # add a choice list to choose font of the title, values are from config.FONT_LIST(choose from all languages, show language name in choice, keep value), default value to self.workflow.font_video
        ttk.Label(self.video_edit_frame, text="字体:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_language = ttk.Combobox(self.video_edit_frame, width=32, values=list(config.FONT_LIST.keys()))
        self.scene_language.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1
        self.scene_language.set(self.shared_language.cget('text'))

        # add a text field "promotion info" here, default empty, if enter text, then need to save to current scene["promotion"] 
        ttk.Label(self.video_edit_frame, text="信息:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        self.scene_promotion = scrolledtext.ScrolledText(self.video_edit_frame, width=35, height=2)
        self.scene_promotion.grid(row=row_number, column=1, sticky=tk.W, padx=5, pady=2)
        row_number += 1

        # 第二轨道播放状态
        self.second_track_playing = False
        self.second_track_cap = None
        self.second_track_after_id = None
        
        # 第二轨道音频播放状态
        self.second_track_audio_playing = False
        self.second_track_audio_start_time = None
        
        # 第二轨道暂停位置
        self.second_track_paused_time = None
        self.second_track_paused_audio_time = None
        self.second_track_cap = None
        self.second_track_after_id = None
        self.second_track_start_time = None

        self.second_track_playing = False
        self.second_track_offset = 0.0
        self.second_track_end_time = 0.0
        self.selected_second_track = "second"
        
        # PIP L/R (画中画左右)
        self.pip_lr_playing = False
        self.pip_left_cap = None
        self.pip_right_cap = None
        self.pip_lr_after_id = None
        self.pip_lr_start_time = None
        self.pip_lr_paused_time = None
        
        self.track_time_label.config(text="00:00 / 00:00")

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
        if not hasattr(self, 'workflow'):
            print("⚠️ 工作流实例未创建")
            return

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
        animate_gen_list = []
        for scene_index, scene in enumerate(self.workflow.scenes):
            #clip_animation = scene.get("clip_animation", "")
            #if clip_animation in config_prompt.ANIMATE_SOURCE and clip_animation != "":
            scene_name = build_scene_media_prefix(self.workflow.pid, str(scene["id"]), "clip", "", False)
            animate_gen_list.append((scene_name, "clip", scene))
            #second_animation = scene.get("second_animation", "")
            #if second_animation in config_prompt.ANIMATE_SOURCE and second_animation != "":
            scene_name = build_scene_media_prefix(self.workflow.pid, str(scene["id"]), "second", "", False)
            animate_gen_list.append((scene_name, "second", scene))

        if animate_gen_list == []:
            return
        
        try:
            # 1. 检查 X:\output 中新生成的原始视频（监控逻辑）
            self.media_scanner.scanning("X:\\output", config.BASE_MEDIA_PATH+"\\input_mp4")                      # clip_p202512231259_10005_S2V__00003-audio.mp4
            self.media_scanner.scanning("Z:\\wan_video\\output_mp4", config.BASE_MEDIA_PATH+"\\input_mp4")                     # clip_p202512231259_10005_INT_25115141_30__00001.mp4  ~~~ interpolate
            self.media_scanner.scanning("W:\\wan_video\\output_mp4", config.BASE_MEDIA_PATH+"\\input_mp4")      # clip_p20251208_10708_ENH_13231028_0_.mp4   clip_p202512231259_10005_EHN_.mp4  ~~~ enhance

            self.media_scanner.check_gen_video(config.BASE_MEDIA_PATH+"\\input_mp4", animate_gen_list)                 # clip_p202512231259_10005_S2V_23155421.mp4
            #self.media_scanner.scanning("Y:\\output", config.BASE_MEDIA_PATH+"\\input_mp4")

            self.workflow.save_scenes_to_json()

        except Exception as e:
            # 忽略单个场景的错误，继续检查其他场景
            print(f"❌ 后台检查线程出错: {str(e)}")
            pass


    def check_generated_videos_background(self):
        """定时器调用此方法，但不再创建新线程（单例线程已在运行）"""
        # 检查单例线程是否还在运行，如果没有则重启
        if not self.video_check_running or not self.video_check_thread or not self.video_check_thread.is_alive():
            print("⚠️ 检测到后台线程未运行，正在重启...")
            self.start_video_check_thread()
    
    
    def run_promotion_video(self):
        pid = self.get_pid()
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "promotion_video",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": pid
        }
        def run_task():
            try:
                self.workflow.promotion_video(self.video_title.get().strip())
                self.log_to_output(self.video_output, "✅ 最终视频生成完成！")
                self.tasks[task_id]["status"] = "完成"
            except Exception as e:
                self.log_to_output(self.video_output, f"❌ 最终视频生成失败: {str(e)}")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)

        threading.Thread(target=run_task, daemon=True).start()


    def run_finalize_video(self):
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
                self.workflow.finalize_video(self.video_title.get().strip(), False)
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


    def clear_video_scene_fields(self):
        self.scene_duration.config(state="normal")
        self.scene_duration.delete(0, tk.END)
        self.scene_duration.config(state="readonly")
        
        self.clear_video_preview()


    def load_video_first_frame(self):
        self._cleanup_video_before_switch()

        current_scene = self.get_current_scene()
            
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
        current_scene = self.get_current_scene()
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
        current_scene = self.get_current_scene()
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
        clip = get_file_path(self.get_current_scene(), "clip_audio")
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
            
            # Format time with 0.01 second precision
            current_time_str = self.format_time_with_centiseconds(current_time)
            total_time_str = self.format_time_with_centiseconds(total_time)
            
            self.video_progress_label.config(text=f"{current_time_str} / {total_time_str}")
            
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
        """刷新场景列表"""
        # self.workflow.load_scenes()
        if self.current_scene_index >= len(self.workflow.scenes) :
            self.current_scene_index = 0

        # 清理所有轨道的 VideoCapture（避免使用旧场景的视频）
        self.cleanup_track_video_captures()

        # 检查现有图像
        self.update_scene_display()
        
        # 更新视频进度显示
        self.update_video_progress_display()

        # 更新按钮状态
        self.update_scene_buttons_state()

        self.reset_track_offset()

        # 延迟加载第一帧，确保canvas已完全渲染
        self.root.after(100, self.load_all_first_frames)


    
    def cleanup_track_video_captures(self):
        if hasattr(self, 'second_track_cap') and self.second_track_cap:
            try:
                self.second_track_cap.release()
            except:
                pass
            self.second_track_cap = None
        
        # 重置第二轨道的播放状态
        if hasattr(self, 'second_track_playing'):
            self.second_track_playing = False
        if hasattr(self, 'second_track_after_id') and self.second_track_after_id:
            try:
                self.root.after_cancel(self.second_track_after_id)
            except:
                pass
            self.second_track_after_id = None
        
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


    def load_all_first_frames(self):
        """加载所有轨道的第一帧"""
        self.load_video_first_frame()
        
        # 加载所有图片预览
        if hasattr(self, 'clip_image_canvas'):
            self.load_all_images_preview()
        
        # 根据当前选中的tab加载轨道视频预览
        current_tab_index = self.second_notebook.index(self.second_notebook.select())
        if current_tab_index == 0:
            self.load_second_track_first_frame()
        elif current_tab_index == 1:
            self.load_pip_lr_first_frame()


    def load_second_track_first_frame(self):
        """加载第二轨道视频的第一帧到画布（从当前偏移位置）"""
        current_scene = self.get_current_scene()
        if not current_scene:
            return
            
        track_path = get_file_path(current_scene, self.selected_second_track)

        try:
            self.second_track_canvas.delete("all")

            if not track_path:
                # 清除画布显示提示信息
                self.second_track_canvas.create_text(160, 90, text="第二轨道视频预览\n选择视频后播放显示",
                                                   fill='white', font=('Arial', 12), 
                                                   justify=tk.CENTER, tags="hint")
                self.track_time_label.config(text="00:00 / 00:00")
                return
            
            # 打开视频文件
            temp_cap = cv2.VideoCapture(track_path)
            if not temp_cap.isOpened():
                print(f"❌ 无法打开第二轨道视频文件: {track_path}")
                return
            
            # 计算应该显示的帧位置（基于 offset + delta）
            start_position = self.second_track_offset + self.second_delta
            if start_position < 0:
                start_position = 0
            
            # 跳到正确的帧位置
            temp_cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_position * STANDARD_FPS))
            
            ret, frame = temp_cap.read()
            if ret:
                # 显示第一帧到Canvas
                from PIL import Image, ImageTk
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                
                # 调整图像大小适应Canvas
                canvas_width = self.second_track_canvas.winfo_width()
                canvas_height = self.second_track_canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:
                    pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
                else:
                    pil_image.thumbnail((310, 170), Image.Resampling.LANCZOS)
                
                # 更新画布显示第一帧
                self.current_second_track_frame = ImageTk.PhotoImage(pil_image)
                
                canvas_width = canvas_width or 320
                canvas_height = canvas_height or 180
                x = canvas_width // 2
                y = canvas_height // 2
                self.second_track_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_second_track_frame)
                
            # 更新时间显示
            total_frames = temp_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_duration = total_frames / STANDARD_FPS
            total_str = f"{int(total_duration // 60):02d}:{int(total_duration % 60):02d}"
            
            # 显示当前偏移位置和总时长
            current_str = f"{int(start_position // 60):02d}:{int(start_position % 60):02d}"
            self.track_time_label.config(text=f"{current_str} / {total_str}")
            
            temp_cap.release()
            print(f"✅ 已加载第二轨道视频帧 (位置: {start_position:.2f}s): {os.path.basename(track_path)}")

        except Exception as e:
            print(f"❌ 加载第二轨道视频第一帧失败: {e}")
            self.second_track_canvas.delete("all")
            self.second_track_canvas.create_text(160, 90, text="第二轨道视频预览\n选择视频后播放显示",
                                               fill='white', font=('Arial', 12), 
                                               justify=tk.CENTER, tags="hint")


    def update_scene_display(self):
        """更新场景显示"""
        if len(self.workflow.scenes) == 0:
            self.scene_label.config(text="0 / 0")
            self.clear_scene_fields()
            self.clear_video_scene_fields()
            return
            
        self.scene_label.config(text=f"{self.current_scene_index + 1} / {len(self.workflow.scenes)}")
        scene_data = self.get_current_scene()
        if not scene_data:
            return
        
        # 显示持续时间
        self.scene_duration.config(state="normal")
        self.scene_duration.delete(0, tk.END)
        duration = self.workflow.find_clip_duration(scene_data)
        self.scene_duration.insert(0, f"{duration:.2f} 秒")
        self.scene_duration.config(state="readonly")
        
        # 设置宣传复选框状态
        clip_animation = scene_data.get("clip_animation", "")
        self.scene_main_animate.set(clip_animation)
        
        # 加载当前场景的图像类型设置
        current_image_type = scene_data.get("second_animation", config_prompt.ANIMATE_SOURCE[0])
        self.scene_second_animation.set(current_image_type)
        
        self.scene_visual_image.delete("1.0", tk.END)
        self.scene_visual_image.insert("1.0", scene_data.get("visual_image", ""))
        
        self.scene_subject.delete("1.0", tk.END)
        self.scene_subject.insert("1.0", scene_data.get("subject", ""))
        
        self.scene_person_action.delete("1.0", tk.END)
        self.scene_person_action.insert("1.0", scene_data.get("person_action", ""))
        
        self.scene_era_time.delete("1.0", tk.END)
        self.scene_era_time.insert("1.0", scene_data.get("era_time", ""))
        
        self.scene_environment.delete(0, tk.END)
        self.scene_environment.insert(0, scene_data.get("environment", ""))

        self.scene_cinematography.delete("1.0", tk.END)
        # 如果 cinematography 是字典，格式化显示；如果是字符串，直接显示
        cinematography_value = scene_data.get("cinematography", "")
        if isinstance(cinematography_value, dict):
            self.scene_cinematography.insert("1.0", json.dumps(cinematography_value, ensure_ascii=False, indent=2))
        else:
            self.scene_cinematography.insert("1.0", cinematography_value)
        
        self.scene_sound_effect.delete("1.0", tk.END)
        self.scene_sound_effect.insert("1.0", scene_data.get("sound_effect", ""))
        
        self.scene_kernel.delete("1.0", tk.END)
        self.scene_kernel.insert("1.0", scene_data.get("kernel", ""))

        self.scene_story.delete("1.0", tk.END)
        self.scene_story.insert("1.0", scene_data.get("story", ""))

        
        self.scene_extra.delete("1.0", tk.END)   
        self.scene_extra.insert("1.0", scene_data.get("caption", ""))

        self.scene_speaker_action.delete("1.0", tk.END)
        self.scene_speaker_action.insert("1.0", scene_data.get("speaker_action", ""))

        # scene_mood字段用于语音合成情绪
        self.scene_speaker.set(scene_data.get("speaker", ""))
        self.scene_speaker_position.set(scene_data.get("speaker_position", ""))
        voice_synthesis_mood = scene_data.get("mood", "calm")
        if voice_synthesis_mood in EXPRESSION_STYLES:
            self.scene_mood.set(voice_synthesis_mood)
        else:
            self.scene_mood.set("calm")
        
        self.scene_story_content.delete("1.0", tk.END)
        self.scene_story_content.insert("1.0", scene_data.get("content", ""))
        
        # 加载宣传信息
        self.scene_promotion.delete("1.0", tk.END)
        self.scene_promotion.insert("1.0", scene_data.get("promotion", ""))

        status = scene_data.get("clip_status", "")
        self.video_edit_frame.config(text=f"视频尺寸: {status}")
        self.video_edit_frame.update()
        # video_width, video_height = self.workflow.ffmpeg_processor.check_video_size(input_media_path)
            # set self.video_edit_frame text tobe "视频尺寸: width x height"



    def format_time_with_centiseconds(self, seconds):
        """Format time as MM:SS.CC (minutes:seconds.centiseconds)"""
        if seconds is None or seconds < 0:
            return "00:00.00"
        
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        secs = int(remaining_seconds)
        centiseconds = int((remaining_seconds - secs) * 100)
        
        return f"{minutes:02d}:{secs:02d}.{centiseconds:02d}"


    def get_current_video_time(self):
        """Get current video playback time in seconds"""
        #if self.video_start_time:
        #    elapsed_time = time.time() - self.video_start_time
        #    current_time = elapsed_time + (self.video_pause_time or 0)
        #else:
        current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
        current_time = current_frame / STANDARD_FPS

        total_time = self.workflow.find_clip_duration(self.get_current_scene())
        
        if current_time > total_time:
            current_time = total_time

        return current_time, total_time


    def set_mark1(self):
        """Set mark1 to current video time"""
        current_time, total_time = self.get_current_video_time()
        current_time = current_time + self.playing_delta
        self.mark1_time = current_time
        time_str = self.format_time_with_centiseconds(current_time)
        self.mark1_label.config(text=time_str)
        print(f"✓ 设置标记1: {time_str}")
    

    def set_mark2(self):
        """Set mark2 to current video time"""
        current_time, total_time = self.get_current_video_time()
        current_time = current_time + self.playing_delta
        self.mark2_time = current_time
        time_str = self.format_time_with_centiseconds(current_time)
        self.mark2_label.config(text=time_str)
        print(f"✓ 设置标记2: {time_str}")
    

    def make_silence_between_marks(self):
        """Make audio silent between mark1 and mark2"""
        if self.mark1_time is None or self.mark2_time is None:
            messagebox.showwarning("警告", "请先设置标记1和标记2")
            return
        
        mark1 = min(self.mark1_time, self.mark2_time)
        mark2 = max(self.mark1_time, self.mark2_time)
        
        if mark1 >= mark2:
            messagebox.showwarning("警告", "标记1和标记2时间相同或无效")
            return
        
        try:
            current_scene = self.get_current_scene()
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
            mark1 = max(0.0, min(mark1, total_duration))
            mark2 = max(mark1, min(mark2, total_duration))
            
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
                        output_video = self.workflow.ffmpeg_processor.add_audio_to_video(
                            clip_video, new_audio
                        )
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
            current_scene = self.get_current_scene()
            if current_scene:
                clip_video = get_file_path(current_scene, "clip")
                if clip_video:
                    total_duration = self.workflow.ffmpeg_processor.get_duration(clip_video)
                else:
                    total_duration = 0.0
                
                if self.video_playing:
                    pass
                else:
                    total_time_str = self.format_time_with_centiseconds(total_duration)
                    self.video_progress_label.config(text=f"00:00.00 / {total_time_str}")
            else:
                self.video_progress_label.config(text="00:00.00 / 00:00.00")
                
        except Exception as e:
            self.video_progress_label.config(text="00:00.00 / 00:00.00")
            print(f"⚠️ 更新视频进度显示失败: {e}")


    def clear_scene_fields(self):
        self.scene_duration.config(state="normal")
        self.scene_duration.delete(0, tk.END)
        self.scene_duration.config(state="readonly")
        
        self.scene_main_animate.set("")
        
        self.scene_visual_image.delete("1.0", tk.END)
        self.scene_era_time.delete("1.0", tk.END)
        self.scene_environment.delete(0, tk.END)
        self.scene_speaker.delete("1.0", tk.END)
        self.scene_speaker_action.delete("1.0", tk.END)
        self.scene_extra.delete("1.0", tk.END)
        self.scene_story.delete("1.0", tk.END)
        self.scene_speaker_position.set("")
        self.scene_mood.set("calm")
        self.scene_story_content.delete("1.0", tk.END)
        self.scene_kernel.delete("1.0", tk.END)
        self.scene_cinematography.delete("1.0", tk.END)
        self.scene_promotion.delete("1.0", tk.END)



    def first_scene(self):
        """上一个场景"""
        self.update_current_scene()
        
        self.current_scene_index = 0
        self.refresh_gui_scenes()


    def last_scene(self):
        """上一个场景"""
        self.update_current_scene()
        self.current_scene_index = len(self.workflow.scenes) - 1
        self.refresh_gui_scenes()


    def prev_scene(self):
        """上一个场景"""
        self.update_current_scene()
        
        self.current_scene_index -= 1
        if self.current_scene_index < 0:
            self.current_scene_index = len(self.workflow.scenes) - 1

        self.refresh_gui_scenes()


    def next_scene(self):
        """下一个场景"""
        self.update_current_scene()
        
        self.current_scene_index += 1
        if self.current_scene_index >= len(self.workflow.scenes):
            self.current_scene_index = 0

        self.refresh_gui_scenes()



    def split_smart_scene(self):
        """分离当前场景"""
        current_scene = self.get_current_scene()
        original_duration = self.workflow.find_clip_duration(current_scene)
        if original_duration <= 0:
            return False

        gen_config = [
            sd_image_processor.GEN_CONFIG["S2V"].copy(),
            sd_image_processor.GEN_CONFIG["FS2V"].copy()
        ]

        for server_config in gen_config:
            section_duration = (server_config["max_frames"]-4) * 1.0 / server_config["frame_rate"]
            server_config["section_duration"] = section_duration
            sections = int(original_duration / section_duration)
            if original_duration / section_duration > sections:
                sections += 1
            server_config["sections"] = sections

        min_sections = 1000000
        best_config = None
        for server_config in gen_config:
            if server_config["sections"] < min_sections:
                min_sections = server_config["sections"]
                best_config = server_config

        if best_config is None:
            gen_config = gen_config[0]

        if gen_config[0]["sections"] == gen_config[1]["sections"]:
            best_config = gen_config[0]

        if best_config["sections"] == 1:
            return False

        if best_config == gen_config[0]:
            animate_mode = "S2V"
        else:
            animate_mode = "FS2V"
        current_scene["clip_animation"] = animate_mode

        new_scenes = self.workflow.split_smart_scene(current_scene, best_config["sections"])

        self.playing_delta = 0.0
        self.playing_delta_label.config(text=f"{self.playing_delta:.1f}s")
        self.refresh_gui_scenes()

        return new_scenes



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
            scene["clip_animation"] = ""

        self.workflow.save_scenes_to_json()
        messagebox.showinfo("成功", "标记清理成功！")


    def start_video_gen_batch(self):
        """启动WAN批生成"""
        current_scene = self.get_current_scene()
        previous_scene = self.get_previous_scene()
        next_scene = self.get_next_scene()

        ss = self.workflow.scenes_in_story(current_scene)
        for scene in ss:
            self.generate_video(scene, previous_scene, next_scene, "clip")
            self.generate_video(scene, previous_scene, next_scene, "second")

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


    def adjust_second_delta(self, delta):
        self.second_delta = self.second_delta + delta
        if self.second_delta < -10:
            self.second_delta = -10
        if self.second_delta > 10:
            self.second_delta = 10
        
        self.second_delta_label.config(text=f"{self.second_delta:.1f}s")


    def move_video(self, delta):
        self.playing_delta = self.playing_delta + delta
        if self.playing_delta < -2.0:
            self.playing_delta = -2.0
        if self.playing_delta > 2.0:
            self.playing_delta = 2.0
        
        self.playing_delta_label.config(text=f"{self.playing_delta:.1f}s")


    def insert_story_scene(self):
        self.update_scene_buttons_state()
        current_scene = self.get_current_scene()
        if current_scene and not self.workflow.first_scene_of_story(current_scene):
            return

        self.workflow.add_story_scene(
            self.current_scene_index,
            "",
            True,
            False,
        )

        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def append_scene(self):
        self.update_scene_buttons_state()
        current_scene = self.get_current_scene()
        if current_scene and not self.workflow.last_scene_of_story(current_scene):
            return

        self.workflow.add_story_scene(
            self.current_scene_index,
            "",
            True,
            True,
        )

        self.workflow.save_scenes_to_json()
        self.refresh_gui_scenes()


    def reverse_video(self):
        """翻转视频"""
        current_scene = self.get_current_scene()
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
        current_scene = self.get_current_scene()
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
        current_tab_index = self.second_notebook.index(self.second_notebook.select())

        if current_tab_index == 1:
            if self.pip_lr_playing:
                self.pause_pip_lr() 
            else:
                self.play_pip_lr()
        else:
            if self.second_track_playing:
                self.pause_second_track()
            else:
                self.play_second_track()


    def play_second_track(self):
        """播放第二轨道视频的当前场景时间段（支持从暂停状态和偏移位置恢复）"""
        second_video_path = get_file_path(self.get_current_scene(), self.selected_second_track)
        second_audio_path = get_file_path(self.get_current_scene(), self.selected_second_track+'_audio')
        try:
            # 检查是否是从暂停状态恢复
            is_resuming = (self.second_track_cap and self.second_track_paused_time)

            #elif self.second_track_paused_time:
            #    play_start_time = self.second_track_paused_time
            #    print(f"▶️ 从暂停位置 {self.second_track_paused_time:.1f}s 恢复播放")
            #else:
            #    print(f"▶️ 从头开始播放第二轨道")
            
            if is_resuming:
                play_start_time = self.second_track_paused_time
                # === 从暂停状态恢复（但没有设置偏移） ===
                self.second_track_start_time = time.time()
                self.second_track_playing = True
                self.track_play_button.config(text="⏸")
                if self.second_track_cap:
                    self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(self.second_track_paused_time * STANDARD_FPS))
                try:
                    pygame.mixer.music.unpause()
                    print("▶️ 第二轨道音频已恢复")
                except Exception as e:
                    print(f"❌ 恢复第二轨道音频失败: {e}")
                    self.play_second_track_audio(second_audio_path)
                
            else:
                play_start_time = self.second_track_offset + self.second_delta
                # === 全新开始播放或从偏移位置播放 ===
                if self.second_track_cap:
                    self.second_track_cap.release()
                self.second_track_cap = cv2.VideoCapture(second_video_path)
                if not self.second_track_cap.isOpened():
                    return

                self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(play_start_time * STANDARD_FPS))
                
                self.second_track_end_time = self.workflow.ffmpeg_audio_processor.get_duration(second_video_path)
                
                self.second_track_playing = True
                self.track_play_button.config(text="⏸")
                
                self.second_track_start_time = time.time()
                self.second_track_paused_time = None
                
                self.play_second_track_audio(second_audio_path)
                
                print(f"▶ 开始播放第二轨道视频片段: {play_start_time:.1f}s - {self.second_track_end_time:.1f}s")
            
            # === 通用处理 - 开始播放循环
            self.play_second_track_frame()
            
            # 更新时间显示
            self.update_second_track_time_display()
            
        except Exception as e:
            print(f"❌ 播放第二轨道视频失败: {e}")


    def play_second_track_audio(self, audio_path):
        """播放第二轨道音频（支持从偏移位置开始）"""
        try:
            # 初始化pygame mixer（如果还没有初始化）
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # 停止任何正在播放的音频
            pygame.mixer.music.stop()
            
            # 加载音频文件
            pygame.mixer.music.load(audio_path)
            
            # 确定音频开始播放的偏移时间
            audio_start_offset = self.second_track_offset + self.second_delta
            if self.second_track_paused_time:
                audio_start_offset = self.second_track_paused_time
            
            try:
                if audio_start_offset > 0:
                    pygame.mixer.music.play(start=audio_start_offset)
                else:
                    pygame.mixer.music.play()
            except TypeError:
                print("⚠️ 当前pygame版本不支持从指定位置播放音频，将从头播放")
                pygame.mixer.music.play()
            
            # 设置音频播放状态
            self.second_track_audio_playing = True
            
        except Exception as e:
            print(f"❌ 播放第二轨道音频失败: {e}")


    def stop_second_track_audio(self):
        """停止第二轨道音频播放"""
        try:
            if self.second_track_audio_playing:
                pygame.mixer.music.stop()
                self.second_track_audio_playing = False
                self.second_track_audio_start_time = None
                print(f"⏹ 第二轨道音频播放停止")
        except Exception as e:
            print(f"❌ 停止第二轨道音频失败: {e}")


    def play_second_track_frame(self):
        """播放第二轨道视频的下一帧（带同步机制）"""
        if not self.second_track_playing or not self.second_track_cap:
            return
            
        try:
            # 检查音频是否还在播放
            audio_is_playing = pygame.mixer.music.get_busy()
            if not audio_is_playing:
                # 音频播放完毕，停止视频
                self.stop_second_track()
                print("✅ 第二轨道音频播放完毕，视频同步停止")
                return
            
            if self.second_track_start_time:
                # 计算实际经过的时间
                current_time = (time.time() - self.second_track_start_time) + self.second_track_offset + self.second_delta
                
                # 计算应该在第几帧
                target_frame = int(current_time * STANDARD_FPS)
                current_frame = int(self.second_track_cap.get(cv2.CAP_PROP_POS_FRAMES))
                
                # 如果视频帧落后于音频进度，跳帧追赶
                if target_frame > current_frame + 2:  # 允许2帧的容错
                    self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                
                # 检查是否超过了视频结束时间
                if current_time >= self.second_track_end_time:
                    self.stop_second_track()
                    return
            
            ret, frame = self.second_track_cap.read()
            if not ret:
                # 视频结束，停止播放
                self.stop_second_track()
                return
            
            # 显示视频帧到Canvas
            from PIL import Image, ImageTk
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # 调整图像大小适应Canvas
            canvas_width = self.second_track_canvas.winfo_width()
            canvas_height = self.second_track_canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                pil_image.thumbnail((canvas_width - 10, canvas_height - 10), Image.Resampling.LANCZOS)
            else:
                pil_image.thumbnail((310, 170), Image.Resampling.LANCZOS)
            
            # 更新画布
            self.current_second_track_frame = ImageTk.PhotoImage(pil_image)
            self.second_track_canvas.delete("all")
            
            canvas_width = canvas_width or 320
            canvas_height = canvas_height or 180
            x = canvas_width // 2
            y = canvas_height // 2
            self.second_track_canvas.create_image(x, y, anchor=tk.CENTER, image=self.current_second_track_frame)
            
            # 更新时间显示
            self.update_second_track_time_display()
            
            # 安排下一帧播放
            delay = max(1, int(1000 / STANDARD_FPS))  # 毫秒
            self.second_track_after_id = self.root.after(delay, self.play_second_track_frame)
            
        except Exception as e:
            print(f"❌ 播放第二轨道视频帧失败: {e}")
            self.stop_second_track()


    def pause_second_track(self):
        if not self.second_track_playing:
            return

        """暂停第二轨道视频播放"""
        self.second_track_playing = False
        self.track_play_button.config(text="▶")
        
        # 计算并保存当前播放偏移时间（关键！与新的同步机制兼容）
        if self.second_track_start_time:
            try:
                self.second_track_paused_time = (time.time() - self.second_track_start_time) + self.second_track_offset + self.second_delta
                print(f"⏸ 保存第二轨道暂停位置: {self.second_track_paused_time:.1f}s")
            except Exception as e:
                print(f"❌ 保存暂停位置失败: {e}")
        
        # 暂停音频播放
        try:
            pygame.mixer.music.pause()
            print("⏸ 第二轨道音频已暂停")
        except Exception as e:
            print(f"❌ 暂停第二轨道音频失败: {e}")
        
        if self.second_track_after_id:
            self.root.after_cancel(self.second_track_after_id)
            self.second_track_after_id = None
            
        # 更新时间显示
        self.update_second_track_time_display()
    

    def stop_second_track(self):
        """停止第二轨道视频播放"""
        self.second_track_playing = False
        self.track_play_button.config(text="▶")
        
        # 停止音频播放
        self.stop_second_track_audio()
        
        if self.second_track_after_id:
            self.root.after_cancel(self.second_track_after_id)
            self.second_track_after_id = None
            
        if self.second_track_cap:
            self.second_track_cap.release()
            self.second_track_cap = None
            
        # 清除所有状态变量
        self.second_track_paused_time = None
        self.second_track_paused_audio_time = None
        self.second_track_start_time = None
        self.reset_track_offset() # self.second_track_pause_offset
        
        print("⏹ 清除第二轨道所有状态")
            
        self.second_track_canvas.delete("all")
        self.second_track_canvas.create_text(160, 90, text="第二轨道视频预览\n选择视频后播放显示", 
                                            fill="gray", font=("Arial", 10), justify=tk.CENTER, tags="hint")
        
        # 更新时间显示
        self.update_second_track_time_display()


    # ========== PIP L/R 播放控制函数 ==========
    
    def play_pip_lr(self):
        """同步播放 second_left 和 second_right 视频（支持从暂停恢复）"""
        try:
            current_scene = self.get_current_scene()
            if not current_scene:
                return
            
            # 获取视频路径
            left_path = current_scene.get('second_left')
            right_path = current_scene.get('second_right')
            audio_path = current_scene.get('clip_audio')
            
            if not left_path or not right_path:
                messagebox.showwarning("提示", "当前场景没有 second_left 或 second_right 视频")
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
            self.track_time_label.config(text=f"{current_str} / {total_str}")
            
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
        self.track_time_label.config(text="00:00 / 00:00")
        
        print("⏹ 停止 PIP L/R 播放")

    
    def on_second_track_tab_changed(self, event=None):
        """tab切换时停止正在播放的视频并加载预览帧"""
        # 先停止所有播放
        self.pause_second_track()
        self.pause_pip_lr()
        
        # 根据当前 tab 加载相应的预览帧
        current_tab_index = self.second_notebook.index(self.second_notebook.select())
        if current_tab_index == 0:
            # 第二轨道 tab：从当前偏移位置加载第一帧
            self.load_second_track_first_frame()
        elif current_tab_index == 1:
            # PIP L/R tab：从起始位置加载第一帧
            self.load_pip_lr_first_frame()

    
    def load_pip_lr_first_frame(self):
        """加载 PIP L/R 视频的第一帧"""
        try:
            current_scene = self.get_current_scene()
            if not current_scene:
                return
            
            left_path = current_scene.get(self.selected_second_track+'_left')
            right_path = current_scene.get(self.selected_second_track+'_right')
            
            if not left_path or not right_path:
                # 清空画布显示提示
                self.pip_left_canvas.delete("all")
                self.pip_left_canvas.create_text(77, 80, text="Left\n画中画左侧\n未生成", 
                                                 fill='gray', font=('Arial', 9), justify=tk.CENTER, tags="hint")
                self.pip_right_canvas.delete("all")
                self.pip_right_canvas.create_text(77, 80, text="Right\n画中画右侧\n未生成", 
                                                  fill='gray', font=('Arial', 9), justify=tk.CENTER, tags="hint")
                self.track_time_label.config(text="00:00 / 00:00")
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
                self.track_time_label.config(text=f"00:00 / {total_str}")
                
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
    
    
    def on_image_drop(self, event, image_type):
        """处理图片拖放事件
        
        Args:
            event: 拖放事件
            image_type: 'clip_image', 'second_image', 或 'zero_image'
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
            current_scene = self.get_current_scene()
            if not current_scene:
                messagebox.showerror("错误", "没有选中场景")
                return
            
            # 复制图片到项目目录
            oldi, image_path = refresh_scene_media(current_scene, image_type, ".webp", file_path, True)

            if image_type == 'clip_image' or image_type == 'clip_image_last':
                self.workflow.ask_replace_scene_info_from_image(current_scene, image_path)

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
            current_scene = self.get_current_scene()
            if not current_scene:
                return
            
            image_path = current_scene.get(image_type)
            if not image_path or not os.path.exists(image_path):
                return
            
            canvas_mapping = {
                'clip_image': (self.clip_image_canvas, "Clip\nImage", '_clip_image_photo'),
                'clip_image_last': (self.clip_image_last_canvas, "Clip\nLast", '_clip_image_last_photo'),
                'second_image': (self.second_image_canvas, "Second\nImage", '_second_image_photo'),
                'second_image_last': (self.second_image_last_canvas, "Second\nLast", '_second_image_last_photo'),
                'zero_image': (self.zero_image_canvas, "Zero\nImage", '_zero_image_photo'),
                'zero_image_last': (self.zero_image_last_canvas, "Zero\nLast", '_zero_image_last_photo'),
                'one_image': (self.one_image_canvas, "One\nImage", '_one_image_photo'),
                'one_image_last': (self.one_image_last_canvas, "One\nLast", '_one_image_last_photo'),
            }
            
            if image_type not in canvas_mapping:
                return
            
            canvas, label, photo_attr = canvas_mapping[image_type]
            
            from PIL import Image, ImageTk
            img = Image.open(image_path)
            
            canvas.delete("all")
            
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
            
            print(f"✅ 已显示  {image_type}: {os.path.basename(image_path)}")
            
        except Exception as e:
            print(f"❌ 显示图片失败 ({image_type}): {e}")



    def load_all_images_preview(self):
        """加载所有图片预览"""
        self.display_image_on_canvas_for_track('clip_image')
        self.display_image_on_canvas_for_track('clip_image_last')
        self.display_image_on_canvas_for_track('second_image')
        self.display_image_on_canvas_for_track('second_image_last')
        self.display_image_on_canvas_for_track('zero_image')
        self.display_image_on_canvas_for_track('zero_image_last')
        self.display_image_on_canvas_for_track('one_image')
        self.display_image_on_canvas_for_track('one_image_last')

    
    def on_track_volume_change(self, *args):
        """音量变化处理（共用）"""
        volume = self.track_volume_var.get()
        self.volume_label.config(text=f"{volume:.2f}")

        if hasattr(pygame.mixer, 'music') and pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(volume)

    
    def update_second_track_time_display(self):
        """更新第二轨道播放时间显示"""
        try:
            if not hasattr(self, 'second_track_cap') or not self.second_track_cap:
                self.track_time_label.config(text="00:00 / 00:00")
                return
            
            # 获取视频总时长
            total_frames = self.second_track_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_duration = total_frames / STANDARD_FPS
            
            # 确定当前播放时间
            current_time = 0.0
            if self.second_track_playing and self.second_track_start_time:
                # 播放状态：根据实际经过时间计算
                current_time = (time.time() - self.second_track_start_time) + self.second_track_offset + self.second_delta
            elif self.second_track_paused_time:
                # 暂停状态：使用暂停时间
                current_time = self.second_track_paused_time
            elif self.second_track_offset:
                # 使用偏移位置
                current_time = self.second_track_offset + self.second_delta
            else:
                # 默认：从视频帧位置计算
                current_pos = self.second_track_cap.get(cv2.CAP_PROP_POS_FRAMES)
                current_time = current_pos / STANDARD_FPS
            
            # 确保时间在合理范围内
            current_time = max(0, min(current_time, total_duration))
            
            # 格式化时间显示 (MM:SS 格式)
            current_str = f"{int(current_time // 60):02d}:{int(current_time % 60):02d}"
            total_str = f"{int(total_duration // 60):02d}:{int(total_duration % 60):02d}"
            
            self.track_time_label.config(text=f"{current_str} / {total_str}")
            
        except Exception as e:
            print(f"❌ 更新第二轨道时间显示失败: {e}")
            self.track_time_label.config(text="00:00 / 00:00")


    def move_second_track_forward(self):
        """第二轨道前进1秒"""
        try:
            if not hasattr(self, 'second_track_cap') or not self.second_track_cap:
                return
                
            # 获取当前播放位置
            current_pos = self.second_track_cap.get(cv2.CAP_PROP_POS_FRAMES)
            current_time = current_pos / STANDARD_FPS
            
            # 前进1秒
            new_time = current_time + 1.0
            
            # 获取视频总时长
            total_frames = self.second_track_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_duration = total_frames / STANDARD_FPS
            
            # 确保不超过视频总时长
            if new_time >= total_duration:
                new_time = total_duration - 0.1
                
            # 跳转到新位置
            self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(new_time * STANDARD_FPS))
            
            # 更新时间显示
            self.update_second_track_time_display()
            
            print(f"⏩ 第二轨道前进1秒: {current_time:.1f}s -> {new_time:.1f}s")
            
        except Exception as e:
            print(f"❌ 第二轨道前进失败: {e}")


    def move_second_track_backward(self):
        """第二轨道后退1秒"""
        try:
            if not hasattr(self, 'second_track_cap') or not self.second_track_cap:
                return
            # 获取当前播放位置
            current_pos = self.second_track_cap.get(cv2.CAP_PROP_POS_FRAMES)
            # 后退1秒
            new_time = current_pos / STANDARD_FPS - 1.0
            if new_time < 0:
                new_time = 0
                
            # 跳转到新位置
            self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(new_time * STANDARD_FPS))
            
            # 更新时间显示
            self.update_second_track_time_display()
            
            print(f"⏪ 第二轨道后退1秒")
            
        except Exception as e:
            print(f"❌ 第二轨道后退失败: {e}")
    

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

        current_scene = self.get_current_scene()
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
                    result = messagebox.askyesno("警告", "⚠️ 请选择保留场景：\n是: 保留当前场景\n否: 保留下一场景")
                    if result is True:
                        self.workflow.merge_scene(self.current_scene_index, self.current_scene_index+1, keep_current=True)
                    else :
                        self.workflow.merge_scene(self.current_scene_index, self.current_scene_index+1, False)
                elif result is False:
                    # 删除场景
                    result = messagebox.askyesno("警告", "⚠️ 删除当前场景?")
                    if result:
                        ss = self.workflow.replace_scene(self.current_scene_index)
                # result is None 表示取消，不做任何操作
            
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


    def refresh_scene_visual(self):
        self.workflow.refresh_scene_visual( self.get_current_scene() )
        self.refresh_gui_scenes()


    def copy_images_to_next(self):
        current_scene = self.get_current_scene()
        next_scene = self.workflow.next_scene_of_story(current_scene)
        if current_scene and next_scene:
            clip_image_split = current_scene.get("clip_image_split", "")
            clip_animation = current_scene.get("clip_animation", "")
            second_animation = current_scene.get("second_animation", "")

            next_scene["clip_image_split"] = clip_image_split
            next_scene["clip_animation"] =  clip_animation
            next_scene["second_animation"] = second_animation

            clip_image = current_scene.get("clip_image", "")
            clip_image_last = current_scene.get("clip_image_last", "")
            if clip_image:
                refresh_scene_media(next_scene, "clip_image", ".webp", clip_image, True)
            if clip_image_last:
                refresh_scene_media(next_scene, "clip_image_last", ".webp", clip_image_last, True)

            second_image = current_scene.get("second_image", "")
            second_image_last = current_scene.get("second_image_last", "")
            if second_image:
                refresh_scene_media(next_scene, "second_image", ".webp", second_image, True)
            if second_image_last:
                refresh_scene_media(next_scene, "second_image_last", ".webp", second_image_last, True)

            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()


    def enhance_clip(self, clip_or_second:bool, fps_enhace:bool):
        """增强主图或次图"""
        scene = self.get_current_scene()
        level = self.enhance_level.get()
        self.workflow.sd_processor.enhance_clip(self.get_pid(), scene, "clip" if clip_or_second else "second", level, fps_enhace)
        self.refresh_gui_scenes()


    def recreate_clip_image(self, language:str):
        """重新创建主图，先打开对话框让用户审查和编辑提示词"""
        scene = self.get_current_scene()
        
        # 定义创建图像的回调函数
        def create_clip_image(edited_positive, edited_negative):
            pass
            #oldi, newi = refresh_scene_media(scene, "clip_image", ".webp")
            #self.workflow._create_image(self.workflow.sd_processor.gen_config["Story"], 
            #                                    newi,
            #                                    None,
            #                                    newi,
            #                                    edited_positive,
            #                                    edited_negative,
            #                                    int(time.time())
            #                                )
            #self.workflow.save_scenes_to_json()
            #self.refresh_gui_scenes()
            #print("✅ 主图已重新创建")
        
        # 构建正面提示词预览
        self.open_image_prompt_dialog(create_clip_image, scene, "clip", language)


    def update_current_scene(self):
        scene = self.get_current_scene()
        
        # 处理 cinematography 字段：尝试解析 JSON 字符串
        cinematography_text = self.scene_cinematography.get("1.0", tk.END).strip()
        cinematography_value = cinematography_text
        if cinematography_text:
            try:
                # 尝试解析为 JSON 对象
                cinematography_value = json.loads(cinematography_text)
            except json.JSONDecodeError:
                # 如果不是有效 JSON，保持为字符串
                cinematography_value = cinematography_text
        
        scene.update({
            "content": self.scene_story_content.get("1.0", tk.END).strip(),
            "kernel": self.scene_kernel.get("1.0", tk.END).strip(),
            "story": self.scene_story.get("1.0", tk.END).strip(),
            "subject": self.scene_subject.get("1.0", tk.END).strip(),
            "visual_image": self.scene_visual_image.get("1.0", tk.END).strip(),
            "person_action": self.scene_person_action.get("1.0", tk.END).strip(),
            "era_time": self.scene_era_time.get("1.0", tk.END).strip(),
            "environment": self.scene_environment.get(),
            "cinematography": cinematography_value,
            "sound_effect": self.scene_sound_effect.get("1.0", tk.END).strip(),
            "caption": self.scene_extra.get("1.0", tk.END).strip(),
            "speaker_action": self.scene_speaker_action.get("1.0", tk.END).strip(),
            "speaker": self.scene_speaker.get(),
            "speaker_position": self.scene_speaker_position.get(),  # 添加讲员位置字段
            "mood": self.scene_mood.get(),         # 语音合成情绪
            "clip_animation": self.scene_main_animate.get(),
            "promotion": self.scene_promotion.get("1.0", tk.END).strip()
        })
        self.workflow.save_scenes_to_json()
        return scene


    def load_config(self):
        """加载当前项目的配置"""
        try:
            # 检查 project_manager.PROJECT_CONFIG 是否已设置
            if project_manager.PROJECT_CONFIG is None:
                print("❌ 错误：project_manager.PROJECT_CONFIG 未设置！请确保已选择项目。")
                print(f"   调试信息：show_project_selection 应该已经设置了 project_manager.PROJECT_CONFIG")
                exit()
            
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
        """获取当前的配置数据"""
        config_data = {
            'pid': self.get_pid(),
            'language': self.shared_language.cget('text'), 
            'channel': self.shared_channel.cget('text'),
            'video_title': getattr(self, 'video_title', None) and self.video_title.get() or '默认视频标题',
            # video_width and video_height are read-only from project config, not saved
            'video_width': project_manager.PROJECT_CONFIG.get('video_width', '1920') if project_manager.PROJECT_CONFIG else '1920',
            'video_height': project_manager.PROJECT_CONFIG.get('video_height', '1080') if project_manager.PROJECT_CONFIG else '1080',
            'kernel': project_manager.PROJECT_CONFIG.get('kernel', ''),
            'promo': project_manager.PROJECT_CONFIG.get('promo', ''),
            'story': project_manager.PROJECT_CONFIG.get('story', '')
        }

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
        """保存当前项目配置"""
        try:
            workflow = self.workflow
            
            config_data = {
                'pid': self.get_pid(),
                'language': self.shared_language.cget('text'),
                'channel': self.shared_channel.cget('text'),
                'video_title': getattr(self, 'video_title', None) and self.video_title.get() or '视频标题',
                # video_width and video_height are read-only from project config, not saved
                'video_width': project_manager.PROJECT_CONFIG.get('video_width', '1920') if project_manager.PROJECT_CONFIG else '1920',
                'video_height': project_manager.PROJECT_CONFIG.get('video_height', '1080') if project_manager.PROJECT_CONFIG else '1080',
                'kernel': project_manager.PROJECT_CONFIG.get('kernel', ''),
                'promo': project_manager.PROJECT_CONFIG.get('promo', ''),
                'story': project_manager.PROJECT_CONFIG.get('story', '')
            }

            # Save audio_prepares data if available
            if workflow and hasattr(workflow, 'audio_prepares'):
                config_data['audio_prepares'] = workflow.video_prepares
            
            # Preserve video_id and other important fields from existing config
            if project_manager.PROJECT_CONFIG:
                if 'video_id' in project_manager.PROJECT_CONFIG:
                    config_data['video_id'] = project_manager.PROJECT_CONFIG['video_id']
                if 'generated_titles' in project_manager.PROJECT_CONFIG:
                    config_data['generated_titles'] = project_manager.PROJECT_CONFIG['generated_titles']
                if 'generated_tags' in project_manager.PROJECT_CONFIG:
                    config_data['generated_tags'] = project_manager.PROJECT_CONFIG['generated_tags']
                # Preserve kernel, story from existing config
                if 'kernel' in project_manager.PROJECT_CONFIG:
                    config_data['kernel'] = project_manager.PROJECT_CONFIG['kernel']
                if 'promo' in project_manager.PROJECT_CONFIG:
                    config_data['promo'] = project_manager.PROJECT_CONFIG['promo']
                if 'story' in project_manager.PROJECT_CONFIG:
                    config_data['story'] = project_manager.PROJECT_CONFIG['story']
            
            # 更新当前项目配置
            project_manager.PROJECT_CONFIG = config_data
            
            # 保存到文件
            config_manager = ProjectConfigManager(self.get_pid())
            config_manager.save_project_config(config_data)
                
        except Exception as e:
            print(f"❌ 保存项目配置失败: {e}")



    def bind_edit_events(self):
        """绑定编辑事件"""
        # 绑定场景信息编辑字段的Enter键事件，用于自动保存
        scene_fields = [
            self.scene_visual_image,
            self.scene_story,
            self.scene_era_time,
            self.scene_environment,
            self.scene_speaker,
            self.scene_speaker_action,
            self.scene_extra,
            self.scene_kernel,
            self.scene_cinematography,
            self.scene_subject,
            self.scene_person_action,
            self.scene_story_content,
            self.scene_promotion
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
            self.scene_mood,
            self.scene_speaker_position
        ]
        
        for field in entry_combobox_fields:
            field.bind('<FocusOut>', self.on_scene_field_focus_out)
            field.bind('<<ComboboxSelected>>', self.on_scene_field_change)
        
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
        # 延迟保存以避免频繁操作
        if hasattr(self, '_save_timer'):
            self.root.after_cancel(self._save_timer)
        self._save_timer = self.root.after(500, lambda: self.update_current_scene())  # 500ms延迟

    def on_scene_field_change(self, event=None):
        """当场景字段值发生变化时的回调（如Combobox选择变化）"""
        # 立即保存当前场景信息
        self.update_current_scene()
        print(f"✅ 场景 {self.current_scene_index + 1} 情绪已更新为: {self.scene_mood.get()}")

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


    def handle_av_replacement(self, av_path, replace_media_audio, media_type):
        """处理音频替换"""
        try:
            current_scene = self.get_current_scene()
            previous_scene = self.get_previous_scene()
            next_scene = self.get_next_scene()
            scenes_same_story = self.workflow.scenes_in_story(current_scene)

            if not av_path:
                if media_type == 'clip':
                    av_path = get_file_path(current_scene, "clip")
                elif media_type == 'zero':
                    av_path = get_file_path(current_scene, "zero")
                elif media_type == 'one':
                    av_path = get_file_path(current_scene, "one")
                else:
                    av_path = get_file_path(current_scene, "second")
            else:
                current_scene[media_type + "_fps"] = self.workflow.ffmpeg_processor.get_video_fps(av_path)
                current_scene[media_type + "_status"] = "DND"
                av_path = self.workflow.ffmpeg_processor.resize_video(av_path, width=None, height=self.workflow.ffmpeg_processor.height)

            print(f"🎬 打开合并编辑器 - 媒体类型: {media_type}, 替换音频: {replace_media_audio}")
            if media_type != "clip":
                replace_media_audio = "keep"
            review_dialog = AVReviewDialog(self, av_path, current_scene, previous_scene, next_scene, media_type, replace_media_audio)
            
            # 等待对话框关闭
            self.root.wait_window(review_dialog.dialog)

            if media_type != "clip" :
                transcribe_way = "" if ('transcribe_way' not in review_dialog.result) else review_dialog.result['transcribe_way']
                if transcribe_way == "multiple" or media_type == "zero":
                    for sss in scenes_same_story:
                        sss[media_type] = current_scene[media_type]
                        sss[media_type+"_audio"]  = current_scene[media_type+"_audio"]
                        sss[media_type+"_image"]  = current_scene[media_type+"_image"]
                        if "camear_style" in current_scene:
                            sss["camear_style"] = current_scene["camear_style"]
                        if "camera_shot" in current_scene:
                            sss["camera_shot"] = current_scene["camera_shot"]
                        if "camera_angle" in current_scene:
                            sss["camera_angle"] = current_scene["camera_angle"]
                        if "camera_color" in current_scene:
                            sss["camera_color"] = current_scene["camera_color"]

                self.workflow.save_scenes_to_json()
                return

            self.workflow.save_scenes_to_json()

            # media_type == clip
            if (not review_dialog.result) or ('transcribe_way' not in review_dialog.result) or (review_dialog.result['transcribe_way'] == "none"):
                print("场景内容无变化")
                return

            transcribe_way = review_dialog.result['transcribe_way']
            audio_json = review_dialog.result['audio_json']

            current_scene["clip_animation"] = ""

            if transcribe_way == "single":
                current_scene["content"] = "\n".join([segment["content"] for segment in audio_json])
                self.workflow.refresh_scene_visual(current_scene)
            elif transcribe_way == "multiple":
                self.workflow.prepare_scenes_from_json( raw_scene=current_scene, audio_json=audio_json )
                self.workflow.replace_scene_with_others(self.current_scene_index, audio_json)
            else: # transcribe_way == "multiple_merge":
                self.workflow.merge_scenes_from_json( raw_scene=current_scene, audio_json=audio_json )

            messagebox.showinfo("成功", f"音频已成功替换！\n\n")
                
        except Exception as e:
            messagebox.showerror("错误", f"音频替换失败: {str(e)}")


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

            current_scene = self.get_current_scene()
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
        if not os.path.exists(dropped_file):
            return
        
        if is_image_file(dropped_file):
            self.handle_image_replacement(dropped_file)
        elif is_audio_file(dropped_file):
            # ask user if want to replace audio for just current scene, all scenes, or extend to all scenes
            choice = askchoice("确认替换音频", [
                "替换当前场景音频",
                "替换所有场景音频",
                "缩放所有场景音频"
            ])
            if not choice:
                return  # 用户取消


            if choice == "替换当前场景音频":
                clip_duration = self.workflow.ffmpeg_processor.get_duration(self.get_current_scene()["clip_audio"])
                self.workflow.replace_scene_audio(self.get_current_scene(), dropped_file, 0, clip_duration)

            elif choice == "替换所有场景音频":
                start_time = 0.0
                for scene in self.workflow.scenes:
                    clip_duration = self.workflow.ffmpeg_processor.get_duration(scene["clip_audio"])
                    self.workflow.replace_scene_audio(scene, dropped_file, start_time, clip_duration)
                    start_time += clip_duration

            elif choice == "缩放所有场景音频":
                total_duration = self.workflow.ffmpeg_processor.get_duration(dropped_file)
                clip_duration = total_duration / len(self.workflow.scenes)
                # Extend audio to total duration and assign to each scene
                start_time = 0.0
                for scene in self.workflow.scenes:
                    self.workflow.replace_scene_audio(scene, dropped_file, start_time, clip_duration)
                    start_time += clip_duration

        elif is_video_file(dropped_file):
            from gui.media_type_selector import MediaTypeSelector
            selector = MediaTypeSelector(self.root, dropped_file, self.workflow.ffmpeg_processor.has_audio_stream(dropped_file), self.get_current_scene())
            replace_media_audio, media_type = selector.show()
            if not media_type:
                return  # 用户取消
            self.handle_av_replacement(dropped_file, replace_media_audio, media_type)

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
        current_scene = self.get_current_scene()
        from gui.media_type_selector import MediaTypeSelector
        selector = MediaTypeSelector(self.root, None, True, current_scene)
        replace_media_audio, media_type = selector.show()
        if not media_type:
            return  # 用户取消
        elif media_type == 'clip':
            dropped_file = get_file_path(current_scene, "clip")
        elif media_type == 'zero':
            dropped_file = get_file_path(current_scene, "zero")
        elif media_type == 'one':
            dropped_file = get_file_path(current_scene, "one")
        else:
            dropped_file = get_file_path(current_scene, "second")

        self.handle_av_replacement(dropped_file, replace_media_audio, media_type)

        self.refresh_gui_scenes()


    def on_clip_animation_change(self, event=None):
        current_scene = self.get_current_scene()
        current_scene["clip_animation"] = self.scene_main_animate.get()
        self.workflow.save_scenes_to_json()

    def on_video_clip_animation_change(self, event=None):
        """当视频标签页宣传模式发生变化时的回调函数"""
        # 保存当前场景的宣传模式到JSON
        current_scene = self.get_current_scene()
        current_scene["clip_animation"] = self.scene_main_animate.get()
        self.workflow.save_scenes_to_json()
        self.log_to_output(self.video_output, f"✅ 宣传模式已更新为: {self.scene_main_animate.get()}")


    def on_image_type_change(self, event=None):
        """处理图像类型选择变化"""
        selected_image_type = self.scene_second_animation.get()
        print(f"✅ 场景 {self.current_scene_index + 1} 图像类型已设置为: {selected_image_type}")
        
        # 保存图像类型到scenes JSON文件
        self.save_second_animation_to_scenes_json(self.current_scene_index, selected_image_type)
        
        # 标记配置已更改
        self._config_changed = True


    def update_scene_field(self, scene_index, field_name, field_value):
        """更新单个场景的特定字段"""
        try:
            workflow = self.workflow
            
            if scene_index >= len(workflow.scenes):
                print(f"❌ 场景索引 {scene_index} 超出范围")
                return False
            
            # 调试：显示更新前的状态
            old_value = workflow.scenes[scene_index].get(field_name, "未设置")
            print(f"🔍 调试: 场景 {scene_index + 1} 的 {field_name} 从 '{old_value}' 更新为 '{field_value}'")
            
            # 更新workflow内存中的数据
            workflow.scenes[scene_index][field_name] = field_value
            
            # 验证更新
            new_value = workflow.scenes[scene_index].get(field_name)
            print(f"✅ 验证: 场景 {scene_index + 1} 的 {field_name} 现在是 '{new_value}'")
            
            return self.workflow.save_scenes_to_json()
            
        except Exception as e:
            print(f"❌ 更新场景字段失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


    def update_scene_fields(self, scene_index, field_updates):
        """批量更新单个场景的多个字段"""
        try:
            workflow = self.workflow
            
            if scene_index >= len(workflow.scenes):
                print(f"❌ 场景索引 {scene_index} 超出范围")
                return False
            
            # 批量更新workflow内存中的数据
            for field_name, field_value in field_updates.items():
                workflow.scenes[scene_index][field_name] = field_value
            # 立即保存到JSON文件
            field_names = list(field_updates.keys())
            return self.workflow.save_scenes_to_json()
            
        except Exception as e:
            print(f"❌ 批量更新场景字段失败: {str(e)}")
            return False

        
    def save_second_animation_to_scenes_json(self, scene_index, image_type):
        """保存单个场景的图像类型到scenes JSON文件"""
        return self.update_scene_field(scene_index, "second_animation", image_type)
        

    def generate_video(self, scene, previous_scene, next_scene, track):
        image_path = get_file_path(scene, track+"_image")
        image_last_path = get_file_path(scene, track+"_image_last")

        animate_mode = scene.get(track+"_animation", "")
        if animate_mode not in config_prompt.ANIMATE_SOURCE or animate_mode.strip() == "":
            return

        wan_prompt = scene.get(track+"_prompt", "")
        
        # 如果 wan_prompt 是字符串（JSON格式），尝试解析为字典
        if isinstance(wan_prompt, str) and wan_prompt.strip():
            try:
                import json
                p = json.loads(wan_prompt)
                wan_prompt = p
            except:
                print("none json wan_prompt")
        
        # 检查 prompt 是否为空（支持字符串和字典两种格式）
        if not wan_prompt or (isinstance(wan_prompt, str) and wan_prompt.strip() == "") or (isinstance(wan_prompt, dict) and len(wan_prompt) == 0):
            #wan_prompt = self.workflow.build_prompt(scene, "", "", track, animate_mode, False, self.workflow.language)
            wan_prompt = "..."
            scene[track+"_prompt"] = wan_prompt

        action_path = get_file_path(scene, self.selected_second_track)

        sound_path = get_file_path(scene, "clip_audio")
        next_sound_path = get_file_path(next_scene, "clip_audio")

        self.workflow.rebuild_scene_video(scene, track, animate_mode, image_path, image_last_path, sound_path, next_sound_path, action_path, wan_prompt)
        self.workflow.save_scenes_to_json()


    def regenerate_video(self, track):
        """打开 WAN 提示词编辑对话框并生成主轨道视频"""
        if track == None:
            track = self.selected_second_track

        scene = self.get_current_scene()
        previous_scene = self.get_previous_scene()
        next_scene = self.get_next_scene()
        
        # 定义生成视频的回调函数
        def generate_callback(wan_prompt):
            # 保存提示词
            scene[track+"_prompt"] = wan_prompt
            # 使用编辑后的 prompt 生成视频
            self.generate_video(scene, previous_scene, next_scene, track)
            # 监控已集成到后台定时器中，无需单独调用 trace_scene_wan_video
            # 后台检查会自动开始监控有 clip_animation 的场景
            self.workflow.save_scenes_to_json()
            self.refresh_gui_scenes()
        
        # 显示编辑对话框
        show_wan_prompt_editor(self, self.workflow, generate_callback, scene, track)
 

    def regenerate_audio(self):
        """音频重生"""
        scene = self.get_current_scene()
        t, mix_audio = self.workflow.regenerate_audio_item(scene, 0, self.workflow.language)

        olda, clip_audio = refresh_scene_media(scene, "clip_audio", ".wav", mix_audio)

        clip_video = get_file_path(scene, "clip")
        if clip_video:
            clip_video = self.workflow.ffmpeg_processor.add_audio_to_video(clip_video, clip_audio)
            oldv, clip_video = refresh_scene_media(scene, "clip", ".mp4", clip_video)

        self.refresh_gui_scenes()



    def update_scene_buttons_state(self):
        """更新场景插入按钮的状态"""
        current_scene = self.get_current_scene()
        
        # 更新前插按钮状态
        if not current_scene or self.workflow.first_scene_of_story(current_scene):
            self.insert_scene_button.config(state="normal")
        else:
            self.insert_scene_button.config(state="disabled")
        
        # 更新后插按钮状态
        if current_scene and self.workflow.last_scene_of_story(current_scene):
            self.append_scene_button.config(state="normal")
        else:
            self.append_scene_button.config(state="disabled")




def main():
    root = TkinterDnD.Tk()

    app = WorkflowGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()

