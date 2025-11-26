import matplotlib
matplotlib.use('Agg')  # Must be at the TOP of main.py

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.scrolledtext as scrolledtext
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import os
import threading
import time
from datetime import datetime
import pygame
import uuid
from magic_workflow import MagicWorkflow
import config
from PIL import Image, ImageTk
from pathlib import Path
from project_manager import ProjectConfigManager, create_project_dialog
from gui.picture_in_picture_dialog import PictureInPictureDialog
from gui.video_review_dialog import VideoReviewDialog
from gui.background_selector_dialog import BackgroundSelectorDialog
from gui.animation_selector_dialog import show_animation_selector
from gui.raw_scenarios_editor import RawScenariosEditor
import cv2
import os
from utility.file_util import get_file_path, is_image_file, is_audio_file, is_video_file, copy_file
from gui.media_review_dialog import AVReviewDialog
from gui.enhanced_media_editor import show_enhanced_media_editor
from utility.minimax_speech_service import MinimaxSpeechService, EXPRESSION_STYLES
from gui.raw_scenarios_editor import RawScenariosEditor
from gui.wan_prompt_editor_dialog import show_wan_prompt_editor  # 添加这一行
from gui.image_prompts_review_dialog import IMAGE_PROMPT_OPTIONS, NEGATIVE_PROMPT_OPTIONS
import tkinterdnd2 as TkinterDnD
from tkinterdnd2 import DND_FILES

import cv2


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



class WorkflowGUI:
    # Standardized framerate to match video processing
    STANDARD_FPS = 60  # Match FfmpegProcessor.STANDARD_FPS

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
        self.current_project_config = None
        self.current_scenario_index = 0

        # 显示项目选择对话框
        if not self.show_project_selection():
            self.root.destroy()
            return
        
        # 首先初始化任务状态跟踪 - 增强版
        self.tasks = {}
        self.completed_tasks = []  # 存储已完成的任务
        self.last_notified_tasks = set()  # 跟踪已通知的任务
        self.status_update_timer_id = None  # 状态更新定时器ID
        self.monitoring_scenarios = {}  # 跟踪正在监控的场景 {scenario_index: {"found_files": [], "start_time": time}}
        self.processed_output_files = set()  # 跟踪已处理的 X:\output 文件
        
        # 单例后台检查线程控制
        self.video_check_thread = None  # 后台检查线程
        self.video_check_running = False  # 线程运行标志
        self.video_check_stop_event = threading.Event()  # 停止事件
        
        # 添加视频效果选择存储
        self.effect_radio_vars = {}  # {scenario_index: tk.StringVar}
        
        # 添加当前效果和图像类型选择变量
        self.current_effect_var = tk.StringVar(value=config.SPECIAL_EFFECTS[0])
        self.scenario_second_animation = tk.StringVar(value=config.ANIMATE_TYPES[0])
        
        # 创建动画名称到提示语的映射字典（双向）
        self.animation_name_to_prompt = {item["name"]: item["prompt"] for item in config.ANIMATION_PROMPTS}
        self.animation_prompt_to_name = {item["prompt"]: item["name"] for item in config.ANIMATION_PROMPTS}
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
        self.create_promo_video_tab()
        
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
        
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)


    def get_pid(self):
        return self.shared_pid.cget('text').strip() or ''
    

    def create_workflow_instance(self):
        """立即创建工作流实例（非懒加载）"""
        try:
            pid = self.get_pid()
            language = self.shared_language.cget('text')
            channel = self.shared_channel.cget('text')
            story_site = self.story_site_entry.get().strip()
            keywords = self.project_keywords.get().strip()
            
            self.workflow = MagicWorkflow(pid, language, channel, story_site)
            self.speech_service = MinimaxSpeechService(pid)
            
            current_gui_title = self.video_title.get().strip()
            self.workflow.post_init(current_gui_title, keywords)

            self.on_tab_changed(None)
            
            print(f"✅ 工作流实例创建完成 - PID: {pid}")
            
        except Exception as e:
            print(f"❌ 创建工作流实例失败: {e}")
            self.workflow = None


    def get_current_scenario(self):
        if not hasattr(self, 'workflow') or self.workflow is None or not hasattr(self.workflow, 'scenarios') or self.workflow.scenarios is None:
            return None
            
        if self.workflow.scenarios and self.current_scenario_index >= 0 and self.current_scenario_index < len(self.workflow.scenarios):
            return self.workflow.scenarios[self.current_scenario_index]
        else:
            return None
    

    def get_previous_scenario(self):
        if self.workflow.scenarios and self.current_scenario_index > 0 and self.current_scenario_index < len(self.workflow.scenarios):
            return self.workflow.scenarios[self.current_scenario_index - 1]
        else:
            return None    


    def get_next_scenario(self):
        if self.workflow.scenarios and self.current_scenario_index >= 0 and self.current_scenario_index < len(self.workflow.scenarios)-1:
            return self.workflow.scenarios[self.current_scenario_index + 1]
        else:
            return None


    def get_previous_story_last_scenario(self):
        if self.workflow.scenarios and self.current_scenario_index > 0 and self.current_scenario_index < len(self.workflow.scenarios):
            # loop from self.current_scenario_index to 0,  
            for i in range(self.current_scenario_index, 0, -1):
                if self.workflow.scenarios[i]["id"]%10000 != self.workflow.scenarios[self.current_scenario_index]["id"]%10000:
                    return self.workflow.scenarios[i]
        return None    

    
    def show_project_selection(self):
        # 使用新的项目管理器
        result, selected_config = create_project_dialog(self.root)
        
        if result == 'cancel':
            return False
        elif result == 'new':
            # 使用从新项目对话框获取的配置
            self.current_project_config = selected_config
            
            # 立即创建ProjectConfigManager并保存新项目配置
            pid = selected_config.get('pid')
            if pid:
                try:
                    config_manager = ProjectConfigManager(pid)
                    config_manager.project_config = selected_config.copy()
                    config_manager.save_project_config()
                    print(f"✅ 新项目配置已保存: {pid}")
                except Exception as e:
                    print(f"❌ 保存新项目配置失败: {e}")
            
            return True
        elif result == 'open':
            # 打开现有项目
            self.current_project_config = selected_config
            return True
        
        return False

   
    def create_default_config(self):
        """创建默认配置"""
        return {
            'pid': '',
            'language': 'tw',
            'channel': 'strange_zh',
            'video_title': '默认标题',

            'program_keywords': '',
            'story_site': '',
            'video_width': str(config.VIDEO_WIDTH),
            'video_height': str(config.VIDEO_HEIGHT)
        }
        
    def create_shared_info_area(self, parent):
        """创建共享信息区域"""
        shared_frame = ttk.LabelFrame(parent, text="共享配置", padding=10)
        shared_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 第一行：基本项目配置
        row1_frame = ttk.Frame(shared_frame)
        row1_frame.pack(fill=tk.X, pady=(0, 5))
        
        scenario_nav_row = ttk.Frame(row1_frame)
        scenario_nav_row.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(scenario_nav_row, text="场景:").pack(side=tk.LEFT)
        ttk.Button(scenario_nav_row, text="◀", width=3, command=self.prev_scenario).pack(side=tk.LEFT, padx=2)
        self.scenario_label = ttk.Label(scenario_nav_row, text="0 / 0", width=7)
        self.scenario_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(scenario_nav_row, text="▶", width=3, command=self.next_scenario).pack(side=tk.LEFT, padx=2)
        
        # 分隔符
        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(row1_frame, text="拷贝图",   command=self.copy_images_to_next).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1_frame, text="场景交换", command=self.swap_scenario).pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(row1_frame, text="视频合成", command=lambda:self.run_finalize_video(zero_audio_only=False)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1_frame, text="视背合成", command=lambda:self.run_finalize_video(zero_audio_only=True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1_frame, text="上传视频", command=self.run_upload_video).pack(side=tk.LEFT, padx=2)
        #ttk.Button(scenario_nav_row, text="拼接视频", command=self.run_final_concat_video).pack(side=tk.LEFT, padx=2)

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
        ttk.Label(title_frame, text="场地").pack(side=tk.LEFT)
        self.story_site_entry = ttk.Entry(title_frame, width=15)
        self.story_site_entry.pack(side=tk.LEFT)
        ttk.Label(title_frame, text="KEY").pack(side=tk.LEFT)
        self.project_keywords = ttk.Entry(title_frame, width=15)
        self.project_keywords.pack(side=tk.LEFT)
        
        # 视频尺寸组
        size_frame = ttk.Frame(row1_frame)
        size_frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(size_frame, text="尺寸").pack(side=tk.LEFT)
        self.video_width = ttk.Entry(size_frame, width=5)
        self.video_width.pack(side=tk.LEFT)
        ttk.Label(size_frame, text="×").pack(side=tk.LEFT)
        self.video_height = ttk.Entry(size_frame, width=5)
        self.video_height.pack(side=tk.LEFT)


        ttk.Separator(row1_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)

        tool_frame = ttk.Frame(row1_frame)
        tool_frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(tool_frame, text="Video生成", command=self.start_video_gen_batch).pack(side=tk.LEFT) 
        ttk.Button(tool_frame, text="媒体清理",  command=self.clean_media).pack(side=tk.LEFT) 
        ttk.Button(tool_frame, text="WAN清理",   command=self.clean_wan).pack(side=tk.LEFT) 
        ttk.Button(tool_frame, text="标记清理",  command=self.clean_media_mark).pack(side=tk.LEFT)

   
    def open_image_prompt_dialog(self, create_image_callback, scenario, image_mode):
        """打开提示词审查对话框，用于在创建图像前预览和编辑提示词"""
        from gui.image_prompts_review_dialog import ImagePromptsReviewDialog
        
        dialog = ImagePromptsReviewDialog(
            parent=self,
            workflow=self.workflow,
            create_image_callback=create_image_callback,
            scenario=scenario,
            track=image_mode
        )
        dialog.show()


    def swap_second(self):
        """交换第一轨道与第二轨道"""
        current_scenario = self.get_current_scenario()
        clip_video_path = get_file_path(current_scenario, 'clip')
        clip_audio_path = get_file_path(current_scenario, 'clip_audio')
        track_path = get_file_path(current_scenario, "second")
        if not track_path:
            messagebox.showwarning("警告", "second 轨道视频文件不存在")
            return
        temp_track = self.workflow.ffmpeg_processor.add_audio_to_video(track_path, clip_audio_path)

        self.workflow.refresh_scenario_media(current_scenario, "second", '.mp4', clip_video_path)
        self.workflow.refresh_scenario_media(current_scenario, "second_audio", '.wav', clip_audio_path, True)

        self.workflow.refresh_scenario_media(current_scenario, 'clip', '.mp4', temp_track)
        self.refresh_gui_scenarios()


    def swap_zero(self):
        """交换第一轨道与第二轨道"""
        current_scenario = self.get_current_scenario()
        clip_video_path = get_file_path(current_scenario, 'clip')
        clip_audio_path = get_file_path(current_scenario, 'clip_audio')
        zero_path = get_file_path(current_scenario, "zero")
        if not zero_path:
            messagebox.showwarning("警告", "zero轨道视频文件不存在")
            return

        self.workflow.refresh_scenario_media(current_scenario, "back", '.mp4', clip_video_path)

        start_time_in_story, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scenario_detail(current_scenario)
        end_time = start_time_in_story + clip_duration

        temp_track = self.workflow.ffmpeg_processor.resize_video(zero_path, None, None, start_time_in_story, end_time)
        temp_track = self.workflow.ffmpeg_processor.add_audio_to_video(temp_track, clip_audio_path)

        self.workflow.refresh_scenario_media(current_scenario, 'clip', '.mp4', temp_track)
        self.refresh_gui_scenarios()


    def track_recover(self):
        current_scenario = self.get_current_scenario()
        clip = current_scenario.get('clip', None)
        back = current_scenario.get('back', None)
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
            current_scenario['back'] = clip + "," + back

        self.workflow.refresh_scenario_media(current_scenario, 'clip', '.mp4', back_path)
        self.workflow.save_scenarios_to_json()
        self.refresh_gui_scenarios()


    def reset_second_track_playing_offset(self):
        self.second_track_offset, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scenario_detail(self.get_current_scenario())
        self.second_track_paused_time = None
        self.update_second_track_time_display()


    def fetch_second_clip(self, to_end, volume):
        current_scenario = self.get_current_scenario()
        second_track_path = get_file_path(current_scenario, 'second')
        second_audio_path = get_file_path(current_scenario, 'second_audio')
        if not second_track_path:
            messagebox.showwarning("警告", "第二轨道视频文件不存在")
            return
        
        second_track_duration = self.workflow.ffmpeg_processor.get_duration(second_track_path)

        if not self.second_track_cap:
            second_time = 0
        else:
            second_pos = self.second_track_cap.get(cv2.CAP_PROP_POS_FRAMES)
            second_time = second_pos / self.STANDARD_FPS

        if second_time <= 0:
            second_time, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scenario_detail(current_scenario)

        if second_track_duration < second_time:
            second_time = 0

        if to_end:
            second_v = self.workflow.ffmpeg_processor.resize_video(second_track_path, None, None, second_time, None, volume)
            second_a = self.workflow.ffmpeg_audio_processor.audio_cut_fade(second_audio_path, second_time, None, 1.0, 1.0,volume)
        else:
            clip_duration = self.workflow.find_clip_duration(current_scenario)
            second_v = self.workflow.ffmpeg_processor.resize_video(second_track_path, None, None, second_time, second_time+clip_duration, volume)
            second_a = self.workflow.ffmpeg_audio_processor.audio_cut_fade(second_audio_path, second_time, clip_duration, 1.0, 1.0, volume)

        return second_v, second_a


    def select_second_track(self, track_id):
       self.selected_second_track = track_id
       self.on_second_track_tab_changed()



    def pip_second_track(self):
        """将第二轨道作为画中画叠加到主轨道视频上"""
        try:
            current_scenario = self.get_current_scenario()
            second_path = get_file_path(current_scenario, self.selected_second_track)
            second_audio = get_file_path(current_scenario, self.selected_second_track+'_audio')
            second_left = get_file_path(current_scenario, self.selected_second_track+'_left')
            second_right = get_file_path(current_scenario, self.selected_second_track+'_right')
            if not second_path or not second_audio:
                messagebox.showwarning("警告", "第二轨道视频文件不存在")
                return

            clip_video = get_file_path(current_scenario, "clip")
            clip_audio = get_file_path(current_scenario, "clip_audio")
            start_time, clip_duration, story_duration, indx, count, is_story_last_clip = self.workflow.get_scenario_detail(current_scenario)
            start_time = start_time + self.second_delta

            if is_story_last_clip: 
                second_track_copy = self.workflow.ffmpeg_processor.resize_video(second_path, None, None, start_time, None)
                second_audio_copy = self.workflow.ffmpeg_audio_processor.audio_cut_fade(second_audio, start_time, None, 0, 0, 1.0)
            else:    
                second_track_copy = self.workflow.ffmpeg_processor.resize_video(second_path, None, None, start_time, start_time + clip_duration)
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

                back = current_scenario.get('back', '')
                current_scenario['back'] = clip_video + "," + back

                if settings['position'] == "full":
                    v = self.workflow.ffmpeg_processor.add_audio_to_video(second_track_copy, clip_audio)
                    self.workflow.refresh_scenario_media(current_scenario, 'clip', '.mp4', v)
                elif settings['position'] == "av":
                    self.workflow.refresh_scenario_media(current_scenario, 'clip', '.mp4', second_track_copy)
                    self.workflow.refresh_scenario_media(current_scenario, 'clip_audio', '.wav', second_audio_copy)
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
                self.workflow.save_scenarios_to_json()
                self.refresh_gui_scenarios()
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
                current_time = current_frame / self.STANDARD_FPS

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
                olda, output_audio = self.workflow.refresh_scenario_media(self.get_current_scenario(), "clip_audio", ".wav", background_audio, True)
                output_video = self.workflow.ffmpeg_processor.add_audio_to_video(output_video, background_audio)
                olda, output_video = self.workflow.refresh_scenario_media(self.get_current_scenario(), "clip", ".mp4", output_video, True)
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
                    olda, output_audio = self.workflow.refresh_scenario_media(self.get_current_scenario(), "clip_audio", ".wav", output_audio, True)

                    output_video = self.workflow.ffmpeg_processor.add_audio_to_video(output_video, output_audio)
                    olda, output_video = self.workflow.refresh_scenario_media(self.get_current_scenario(), "clip", ".mp4", output_video, True)
            
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
        


    def open_promo_video_gen_dialog(self):
        audio_file = config.get_media_path(self.get_pid()) + "/short.wav"
        if not os.path.exists(audio_file):
            messagebox.showerror("错误", f"音频文件不存在: {audio_file}")
            return

        # read short.json, for each json item, read the 'content' field, concat them by \n, as srt_content
        srt_content = None
        if os.path.exists(config.get_project_path(self.get_pid()) + "/short.json"):
            # read short.json as text
            with open(config.get_project_path(self.get_pid()) + "/short.json", 'r', encoding='utf-8') as f:
                srt_content = f.read()

        start_duration=10
        image_duration=5
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "open_promo_video_gen_dialog",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": self.workflow.pid
        }
        
        def run_task():
            try:
                print(f"🎬 开始生成频道宣传视频...")
                title = self.video_title.get().strip()
                
                # 调用工作流的方法
                result_video_path = self.workflow.create_channel_promote_video(audio_file, title, self.project_keywords.get().strip(), srt_content, start_duration, image_duration)

                print(f"✅ 频道宣传视频生成完成: {result_video_path}")
                
                # 更新任务状态
                self.tasks[task_id]["status"] = "完成"
                self.tasks[task_id]["result"] = f"宣传视频已生成: {os.path.basename(result_video_path)}"
                
            except Exception as e:
                error_msg = f"频道宣传视频生成失败: {str(e)}"
                print(f"❌ {error_msg}")
                
                # 更新状态为失败
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)
                
                # 通知错误
                self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
        
        # 启动后台任务
        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()
        
        print(f"🚀 频道宣传视频生成任务已启动，任务ID: {task_id}")



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
        try:
            self.clip_image_canvas.drop_target_register(DND_FILES)
            self.clip_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'clip_image'))
        except: pass
        self.clip_image_canvas.bind('<Double-Button-1>', lambda e: self.on_image_double_click('clip_image'))

        # Bottom: clip_image_last
        self.clip_image_last_canvas = tk.Canvas(clip_canvas_container, bg='gray20', width=150, height=75, 
                                                highlightthickness=2, highlightbackground='blue')
        self.clip_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.clip_image_last_canvas.create_text(75, 37, text="Clip\nLast", fill="gray", font=("Arial", 8), 
                                            justify=tk.CENTER, tags="hint")
        try:
            self.clip_image_last_canvas.drop_target_register(DND_FILES)
            self.clip_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'clip_image_last'))
        except: pass
        self.clip_image_last_canvas.bind('<Double-Button-1>', lambda e: self.on_image_double_click('clip_image_last'))

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
        try:
            self.zero_image_canvas.drop_target_register(DND_FILES)
            self.zero_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'zero_image'))
        except: pass
        self.zero_image_canvas.bind('<Double-Button-1>', lambda e: self.on_image_double_click('zero_image'))

        # Bottom: zero_image_last
        self.zero_image_last_canvas = tk.Canvas(zero_canvas_container, bg='gray20', width=150, height=75, 
                                                highlightthickness=2, highlightbackground='orange')
        self.zero_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.zero_image_last_canvas.create_text(75, 37, text="Zero\nLast", fill="gray", font=("Arial", 8), 
                                            justify=tk.CENTER, tags="hint")
        try:
            self.zero_image_last_canvas.drop_target_register(DND_FILES)
            self.zero_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'zero_image_last'))
        except: pass
        self.zero_image_last_canvas.bind('<Double-Button-1>', lambda e: self.on_image_double_click('zero_image_last'))

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
        try:
            self.one_image_canvas.drop_target_register(DND_FILES)
            self.one_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'one_image'))
        except: pass
        self.one_image_canvas.bind('<Double-Button-1>', lambda e: self.on_image_double_click('one_image'))

        # Bottom: one_image_last
        self.one_image_last_canvas = tk.Canvas(one_canvas_container, bg='gray20', width=150, height=75, 
                                            highlightthickness=2, highlightbackground='purple')
        self.one_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.one_image_last_canvas.create_text(75, 37, text="One\nLast", fill="gray", font=("Arial", 8), 
                                            justify=tk.CENTER, tags="hint")
        try:
            self.one_image_last_canvas.drop_target_register(DND_FILES)
            self.one_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'one_image_last'))
        except: pass
        self.one_image_last_canvas.bind('<Double-Button-1>', lambda e: self.on_image_double_click('one_image_last'))

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
        try:
            self.second_image_canvas.drop_target_register(DND_FILES)
            self.second_image_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'second_image'))
        except: pass
        self.second_image_canvas.bind('<Double-Button-1>', lambda e: self.on_image_double_click('second_image'))

        # Bottom: second_image_last
        self.second_image_last_canvas = tk.Canvas(second_canvas_container, bg='gray20', width=150, height=75, 
                                                highlightthickness=2, highlightbackground='green')
        self.second_image_last_canvas.pack(fill=tk.BOTH, expand=True, pady=(1, 0))
        self.second_image_last_canvas.create_text(75, 37, text="Second\nLast", fill="gray", font=("Arial", 8), 
                                                justify=tk.CENTER, tags="hint")
        try:
            self.second_image_last_canvas.drop_target_register(DND_FILES)
            self.second_image_last_canvas.dnd_bind('<<Drop>>', lambda e: self.on_image_drop(e, 'second_image_last'))
        except: pass
        self.second_image_last_canvas.bind('<Double-Button-1>', lambda e: self.on_image_double_click('second_image_last'))
        

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
        ttk.Button(self.track_frame, text="📺", command=lambda:self.pip_second_track(), width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="💫", command=lambda:self.select_second_track('zero'), width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="💫", command=lambda:self.select_second_track('one'), width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="💫", command=lambda:self.select_second_track('second'), width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="💫", command=self.swap_second, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="✨", command=self.swap_zero, width=3).pack(side=tk.LEFT, padx=2)
        #ttk.Button(self.track_frame, text="🔊", command=self.pip_second_sound, width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.track_frame, text="🔄", command=self.reset_second_track_playing_offset, width=3).pack(side=tk.LEFT, padx=2)
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

        ttk.Button(video_control_frame, text="分离", command=self.split_current_scenario, width=5).pack(side=tk.LEFT, padx=1) 
        ttk.Button(video_control_frame, text="下移", command=self.shift_forward, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="上移", command=self.shift_before, width=5).pack(side=tk.LEFT, padx=1)
        ttk.Button(video_control_frame, text="延伸", command=self.extend_scenario, width=5).pack(side=tk.LEFT, padx=1)
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
        self.insert_scenario_button = ttk.Button(video_control_frame, text="前插", command=self.insert_scenario, width=6)
        self.insert_scenario_button.pack(side=tk.LEFT, padx=1)

        self.append_scenario_button = ttk.Button(video_control_frame, text="后插", command=self.append_scenario, width=6)
        self.append_scenario_button.pack(side=tk.LEFT, padx=1)

        #ttk.Button(scenario_nav_row, text="智分场景", 
        #          command=self.split_smart_scenario).pack(side=tk.LEFT, padx=2) 

        # 视频进度标签
        self.video_progress_label = ttk.Label(video_control_frame, text="00:00 / 00:00")
        self.video_progress_label.pack(side=tk.RIGHT, padx=1)
        
        # 初始化视频进度显示
        self.update_video_progress_display()
        
        # 视频播放状态
        self.video_playing = False
        self.video_cap = None
        self.video_after_id = None
        self.video_start_time = None
        self.video_pause_time = None  # 记录暂停时的累计播放时间
        
        # 右侧：场景信息显示区域
        video_edit_frame = ttk.LabelFrame(main_content, text="场景信息", padding=10)
        video_edit_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        # 设置右侧面板的固定宽度，防止被挤压
        video_edit_frame.configure(width=650)
        video_edit_frame.pack_propagate(False)
        
        # 持续时间和宣传模式在同一行
        duration_promo_frame = ttk.Frame(video_edit_frame)
        duration_promo_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)
        
        # 持续时间（只读）
        ttk.Label(duration_promo_frame, text="持续:").pack(side=tk.LEFT)
        self.scenario_duration = ttk.Entry(duration_promo_frame, width=12, state="readonly")
        self.scenario_duration.pack(side=tk.LEFT, padx=(2, 10))
        
        # 宣传模式（可编辑）
        ttk.Label(duration_promo_frame, text="主动画:").pack(side=tk.LEFT, padx=(5, 5))
        self.scenario_main_animate = tk.StringVar(value="")
        self.main_animate_combobox = ttk.Combobox(duration_promo_frame, textvariable=self.scenario_main_animate, 
                                               values=config.ANIMATE_TYPES, 
                                               state="readonly", width=10)
        self.main_animate_combobox.pack(side=tk.LEFT)
        self.main_animate_combobox.bind('<<ComboboxSelected>>', self.on_video_clip_animation_change)


        ttk.Label(duration_promo_frame, text="次动画:").pack(side=tk.LEFT, padx=(0, 5))
        self.second_animation_combobox = ttk.Combobox(duration_promo_frame, textvariable=self.scenario_second_animation,
                                               values=config.ANIMATE_TYPES, 
                                               state="readonly", width=10)
        self.second_animation_combobox.pack(side=tk.LEFT, padx=(0, 10))
        self.second_animation_combobox.bind('<<ComboboxSelected>>', self.on_image_type_change)

        # 类型、情绪、动作选择（在同一行）
        type_mood_action_frame = ttk.Frame(video_edit_frame)
        type_mood_action_frame.grid(row=2, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)

        ttk.Button(type_mood_action_frame, text="生场视频", width=8,  command=self.regenerate_scenario).pack(side=tk.LEFT)

        ttk.Button(type_mood_action_frame, text="生场音频", width=8,  command=self.regenerate_audio).pack(side=tk.LEFT)



        action_frame = ttk.Frame(video_edit_frame)
        action_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W+tk.E, pady=2)

        ttk.Button(action_frame, text="生主图片", width=8, command=self.recreate_clip_image).pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="生次图片", width=8, command=self.recreate_second_image).pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="生主动画", width=8,  command=lambda: self.regenerate_video("clip")).pack(side=tk.LEFT)

        ttk.Button(action_frame, text="生次动画", width=8,  command=lambda: self.regenerate_video(None)).pack(side=tk.LEFT)


        ttk.Label(video_edit_frame, text="故事:").grid(row=4, column=0, sticky=tk.NW, pady=2)
        self.scenario_story_expression = scrolledtext.ScrolledText(video_edit_frame, width=35, height=2)
        self.scenario_story_expression.grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)
        
        # 时代时间
        ttk.Label(video_edit_frame, text="时代:").grid(row=5, column=0, sticky=tk.NW, pady=2)
        self.scenario_era_time = scrolledtext.ScrolledText(video_edit_frame, width=35, height=1)
        self.scenario_era_time.grid(row=5, column=1, sticky=tk.W, padx=5, pady=2)
        
        # 具体地点
        ttk.Label(video_edit_frame, text="地点:").grid(row=6, column=0, sticky=tk.NW, pady=2)
        self.scenario_location = ttk.Entry(video_edit_frame, width=35)
        self.scenario_location.grid(row=6, column=1, sticky=tk.W, padx=5, pady=2)

        # 镜头光影
        ttk.Label(video_edit_frame, text="镜头:").grid(row=7, column=0, sticky=tk.NW, pady=2)
        self.scenario_camera_light = scrolledtext.ScrolledText(video_edit_frame, width=35, height=2)
        self.scenario_camera_light.grid(row=7, column=1, sticky=tk.W, padx=5, pady=2)

        # 故事内容
        ttk.Label(video_edit_frame, text="内容:").grid(row=8, column=0, sticky=tk.NW, pady=2)
        self.scenario_story_content = scrolledtext.ScrolledText(video_edit_frame, width=35, height=2)
        self.scenario_story_content.grid(row=8, column=1, sticky=tk.W, padx=5, pady=2)

        # 人物关系
        ttk.Label(video_edit_frame, text="人物:").grid(row=9, column=0, sticky=tk.NW, pady=2)
        self.scenario_person_in_story = scrolledtext.ScrolledText(video_edit_frame, width=35, height=2)
        self.scenario_person_in_story.grid(row=9, column=1, sticky=tk.W, padx=5, pady=2)

        # 动作情绪
        ttk.Label(video_edit_frame, text="动作:").grid(row=10, column=0, sticky=tk.NW, pady=2)
        self.scenario_speaker_action = scrolledtext.ScrolledText(video_edit_frame, width=35, height=2)
        self.scenario_speaker_action.grid(row=10, column=1, sticky=tk.W, padx=5, pady=2)

        # extra
        ttk.Label(video_edit_frame, text="FYI:").grid(row=11, column=0, sticky=tk.NW, pady=2)
        self.scenario_extra =  scrolledtext.ScrolledText(video_edit_frame, width=35, height=2)
        self.scenario_extra.grid(row=11, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(video_edit_frame, text="情绪:").grid(row=13, column=0, sticky=tk.NW, pady=2)
        self.scenario_mood = ttk.Combobox(video_edit_frame, width=35, values=EXPRESSION_STYLES, state="readonly")
        self.scenario_mood.set("calm")  # 设置默认值
        self.scenario_mood.grid(row=13, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(video_edit_frame, text="讲员:").grid(row=14, column=0, sticky=tk.NW, pady=2)
        self.scenario_speaker = ttk.Combobox(video_edit_frame, width=32, values=config.ROLES)
        self.scenario_speaker.grid(row=14, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(video_edit_frame, text="左右:").grid(row=15, column=0, sticky=tk.NW, pady=2)
        self.scenario_speaker_position = ttk.Combobox(video_edit_frame, width=32, values=config.SPEAKER_POSITIONS)
        self.scenario_speaker_position.grid(row=15, column=1, sticky=tk.W, padx=5, pady=2)

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

        
    def create_promo_video_tab(self):
        """Create promo video tab with drag & drop for MP3 files"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="宣传视频制作333")

        # Instructions
        instruction_frame = ttk.Frame(tab)
        instruction_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        instruction_text = "将MP3音频文件拖拽到左侧区域以制作宣传视频\n• 系统将自动生成带有音频的宣传视频\n• 在右侧输入字幕脚本（每行一句）\n• 结果文件保存在项目的输出目录中"
        ttk.Label(instruction_frame, text=instruction_text, font=('TkDefaultFont', 10), foreground='gray').pack()

        # Main content frame with three columns: drag area, story editor, and script area
        content_frame = ttk.Frame(tab)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Middle: Story JSON Editor
        story_frame = ttk.LabelFrame(content_frame, text="故事JSON编辑器", padding="10")
        story_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 5))

        # Story JSON editor with undo/redo functionality
        self.promo_story_json_widget = scrolledtext.ScrolledText(story_frame, wrap=tk.WORD, font=('Consolas', 11), 
                                                               undo=True, maxundo=-1)
        self.promo_story_json_widget.pack(fill=tk.BOTH, expand=True)

        # Add undo/redo keyboard shortcuts for story editor
        self.promo_story_json_widget.bind('<Control-z>', self.promo_undo_action)
        self.promo_story_json_widget.bind('<Control-y>', self.promo_redo_action)
        self.promo_story_json_widget.bind('<Control-Shift-Z>', self.promo_redo_action)

        self.promo_load_story_content()

        # Right side: Script input area
        script_frame = ttk.LabelFrame(content_frame, text="字幕脚本", padding="10")
        script_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 5))

        # Script text area
        self.promo_script_text = scrolledtext.ScrolledText(script_frame, height=20, wrap=tk.WORD, font=('TkDefaultFont', 10))
        self.promo_script_text.pack(fill=tk.BOTH, expand=True)

        # Left side: Drop zone with wave image (reduced width)
        drop_frame = ttk.LabelFrame(content_frame, text="拖拽区域", padding="10")
        drop_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(5, 5))
        drop_frame.config(width=250)  # Fixed reduced width

        # Canvas for the wave image and drop zone
        self.promo_canvas = tk.Canvas(drop_frame, height=300, width=200, bg='white', relief=tk.RAISED, bd=2)
        self.promo_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Load and display wave image
        self.load_promo_wave_image()

        # Setup drag and drop if available
        self.setup_promo_drag_drop()


        # Settings frame
        settings_frame = ttk.LabelFrame(tab, text="宣传视频设置", padding="10")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)

        # Settings display
        settings_info_frame = ttk.Frame(settings_frame)
        settings_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(settings_info_frame, text="开始持续时间: 10秒").pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(settings_info_frame, text="图像持续时间: 5秒").pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(settings_info_frame, text="字幕: 自动生成SRT").pack(side=tk.LEFT)

        # Voice and duration controls
        controls_frame = ttk.Frame(settings_frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 旁白语音组
        narrator_frame = ttk.Frame(controls_frame)
        narrator_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(narrator_frame, text="旁白语音").pack(side=tk.LEFT)
        narrator_controls = ttk.Frame(narrator_frame)
        narrator_controls.pack(side=tk.LEFT, padx=(5, 0))
        self.promo_actor_narrator = ttk.Combobox(narrator_controls, values=config.HOSTS, state="readonly", width=15)
        self.promo_actor_narrator.set(config.HOSTS[0])  # Default to voice1
        self.promo_actor_narrator.pack(side=tk.TOP)
        
        # add a text fields to keep the story scenarios duration, default to config.VIDEO_DURATION_DEFAULT
        duration_frame = ttk.Frame(controls_frame)
        duration_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(duration_frame, text="片段时长").pack(side=tk.LEFT)
        duration_controls = ttk.Frame(duration_frame)
        duration_controls.pack(side=tk.LEFT, padx=(5, 0))
        self.promo_duration_entry = ttk.Entry(duration_controls, width=15)
        self.promo_duration_entry.insert(0, str(config.VIDEO_DURATION_DEFAULT))
        self.promo_duration_entry.pack(side=tk.TOP)

        # Action buttons frame
        action_frame = ttk.Frame(settings_frame)
        action_frame.pack(fill=tk.X, padx=5, pady=10)

        ttk.Button(action_frame, text="加载故事", 
                  command=self.promo_load_story_content).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_frame, text="重新生成对话", 
                  command=self.promo_on_regenerate_dialog).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_frame, text="保存JSON", 
                  command=self.promo_save_story_json_content).pack(side=tk.LEFT, padx=(0, 30))

        ttk.Button(action_frame, text="生成音频", 
                  command=self.promo_on_generate_audio).pack(side=tk.LEFT, padx=(0, 30))

        ttk.Button(action_frame, text="🎬 宣传短片生成", 
                  command=self.open_promo_video_gen_dialog, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(action_frame, text="🎬 上传宣传短片", 
                  command=self.upload_promo_video, 
                  style="Accent.TButton").pack(side=tk.LEFT)

        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.promo_output = scrolledtext.ScrolledText(output_frame, height=10)
        self.promo_output.pack(fill=tk.BOTH, expand=True)

    def load_promo_wave_image(self):
        """Load and display the wave image in the promo canvas"""
        try:
            image_path = os.path.join(os.path.dirname(__file__), "media", "wave_sound.png")
            if os.path.exists(image_path):
                # Load and resize image to fit canvas
                pil_image = Image.open(image_path)
                # Calculate size to fit canvas while maintaining aspect ratio
                canvas_width = 400
                canvas_height = 250
                pil_image.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)
                
                self.promo_wave_image = ImageTk.PhotoImage(pil_image)
                
                # Center image in canvas
                canvas_width_actual = self.promo_canvas.winfo_reqwidth() or 400
                canvas_height_actual = self.promo_canvas.winfo_reqheight() or 300
                x = canvas_width_actual // 2
                y = canvas_height_actual // 2
                
                self.promo_canvas.create_image(x, y, image=self.promo_wave_image, anchor=tk.CENTER)
                self.promo_canvas.create_text(x, y + 140, text="拖拽 MP3 音频文件到此处", 
                                            font=('TkDefaultFont', 12, 'bold'), fill='gray')
            else:
                # Fallback if image not found
                self.promo_canvas.create_text(200, 150, text="拖拽 MP3 音频文件到此处", 
                                            font=('TkDefaultFont', 14, 'bold'), fill='gray')
                self.promo_canvas.create_rectangle(50, 50, 350, 250, outline='gray', dash=(5, 5))
                
        except Exception as e:
            print(f"加载波形图片失败: {e}")
            # Fallback to text only
            self.promo_canvas.create_text(200, 150, text="拖拽 MP3 音频文件到此处", 
                                        font=('TkDefaultFont', 14, 'bold'), fill='gray')
            self.promo_canvas.create_rectangle(50, 50, 350, 250, outline='gray', dash=(5, 5))

    def setup_promo_drag_drop(self):
        """Setup drag and drop functionality for the promo canvas and script text"""
        # Setup canvas drag & drop for audio files
        self.promo_canvas.drop_target_register(DND_FILES)
        self.promo_canvas.dnd_bind('<<Drop>>', self.on_promo_drop)
        self.promo_canvas.dnd_bind('<<DragEnter>>', self.on_promo_drag_enter)
        self.promo_canvas.dnd_bind('<<DragLeave>>', self.on_promo_drag_leave)
        
        # Setup script text drag & drop for text files
        self.promo_script_text.drop_target_register(DND_FILES)
        self.promo_script_text.dnd_bind('<<Drop>>', self.on_promo_script_drop)
        self.promo_script_text.dnd_bind('<<DragEnter>>', self.on_promo_script_drag_enter)
        self.promo_script_text.dnd_bind('<<DragLeave>>', self.on_promo_script_drag_leave)

    def on_promo_drag_enter(self, event):
        """Visual feedback when dragging enters promo canvas"""
        self.promo_canvas.configure(relief=tk.SUNKEN, bd=3)

    def on_promo_drag_leave(self, event):
        """Visual feedback when dragging leaves promo canvas"""
        self.promo_canvas.configure(relief=tk.RAISED, bd=2)

    def on_promo_click(self, event):
        """Fallback file selection when drag & drop not available"""
        file_path = filedialog.askopenfilename(
            title="选择MP3音频文件",
            filetypes=(
                ("MP3音频文件", "*.mp3"),
                ("音频文件", "*.mp3 *.wav *.m4a *.flac *.aac"),
                ("所有文件", "*.*")
            )
        )
        if file_path:
            self.process_promo_audio_file(file_path)

    def on_promo_script_drag_enter(self, event):
        """Visual feedback when dragging enters script text area"""
        self.promo_script_text.configure(relief=tk.SUNKEN, bd=2)

    def on_promo_script_drag_leave(self, event):
        """Visual feedback when dragging leaves script text area"""
        self.promo_script_text.configure(relief=tk.FLAT, bd=1)

    def on_promo_script_drop(self, event):
        """Handle text file drop event for script area"""
        files = event.data.split()
        if files:
            file_path = files[0]
            # Remove quotes if present
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]
            self.process_promo_script_file(file_path)
        
        # Reset visual feedback
        self.promo_script_text.configure(relief=tk.FLAT, bd=1)


    def process_promo_script_file(self, file_path):
        """Process the dropped text file for script content"""
        if not os.path.exists(file_path):
            messagebox.showerror("错误", f"文件不存在: {file_path}")
            return

        # Check file extension for text files
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext not in ['.json', '.txt', '.srt', '.vtt', '.text', '.log']:
            messagebox.showerror("错误", f"不支持的文本格式: {file_ext}\n支持的格式: JSON, TXT, SRT, VTT, TEXT, LOG")
            return

        try:
            # Try different encodings
            encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                messagebox.showerror("错误", "无法读取文件，不支持的编码格式")
                return
                
            # Ask user if they want to replace or append
            if self.promo_script_text.get(1.0, tk.END).strip():
                choice = messagebox.askyesnocancel("脚本内容", "当前已有脚本内容\n\n是：替换现有内容\n否：追加到末尾\n取消：取消操作")
                if choice is None:  # Cancel
                    return
                elif choice:  # Yes - Replace
                    self.promo_script_text.delete(1.0, tk.END)
                    self.promo_script_text.insert(1.0, content)
                else:  # No - Append
                    self.promo_script_text.insert(tk.END, "\n" + content)
            else:
                # Empty text area, just insert
                self.promo_script_text.insert(1.0, content)
                
            self.log_to_output(self.promo_output, f"📝 已加载脚本文件: {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {str(e)}")

    def load_promo_script_content(self):
        """自动加载宣传视频脚本内容从promote SRT文件"""
        try:
            # 获取promote SRT文件路径
            promote_srt_path = config.get_promote_srt_path(self.get_pid())
            
            # 检查文件是否存在
            if not os.path.exists(promote_srt_path):
                return
                
            # 检查promo_script_text是否已有内容
            if self.promo_script_text.get(1.0, tk.END).strip():
                return  # 如果已有内容，不自动覆盖
                
            # 读取SRT文件内容
            try:
                encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312']
                content = None
                
                for encoding in encodings:
                    try:
                        with open(promote_srt_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                
                if content is None:
                    return
                    
                # 从SRT内容中提取纯文本（去除时间戳和序号）
                script_lines = []
                lines = content.split('\n')
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    # 跳过空行
                    if not line:
                        i += 1
                        continue
                    # 跳过数字序号行
                    if line.isdigit():
                        i += 1
                        continue
                    # 跳过时间戳行
                    if '-->' in line and ':' in line:
                        i += 1
                        continue
                    # 这是字幕文本行
                    if line:
                        script_lines.append(line)
                    i += 1
                
                if script_lines:
                    script_content = '\n'.join(script_lines)
                    self.promo_script_text.insert(1.0, script_content)
                    print(f"✅ 已自动加载宣传视频脚本内容: {len(script_lines)} 行")
                    
            except Exception as e:
                print(f"⚠️ 读取promote SRT文件失败: {e}")
                
        except Exception as e:
            print(f"⚠️ 加载宣传视频脚本内容失败: {e}")

    def on_promo_drop(self, event):
        """Handle file drop event for promo video"""
        files = event.data.split()
        if files:
            file_path = files[0]
            # Remove quotes if present
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]
            self.process_promo_audio_file(file_path)
        
        # Reset visual feedback
        self.promo_canvas.configure(relief=tk.RAISED, bd=2)

    def process_promo_audio_file(self, file_path):
        """Process the dropped/selected audio file for promo video creation"""
        if not os.path.exists(file_path):
            messagebox.showerror("错误", f"文件不存在: {file_path}")
            return

        # Check file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext not in ['.mp3', '.wav', '.m4a', '.flac', '.aac']:
            messagebox.showerror("错误", f"不支持的音频格式: {file_ext}\n支持的格式: MP3, WAV, M4A, FLAC, AAC")
            return

        # Get script text
        script_text = self.promo_script_text.get(1.0, tk.END).strip()
        has_subtitles = bool(script_text)

        # Confirm processing
        confirm_msg = f"确定要制作宣传视频吗？\n\n音频文件: {os.path.basename(file_path)}\n开始持续时间: 10秒\n图像持续时间: 5秒\n字幕: {'是' if has_subtitles else '无'}"
        if script_text!="":
            # save script_text to config.get_promote_srt_path(self.get_pid())
            with open(config.get_promote_srt_path(self.get_pid()), 'w', encoding='utf-8') as f:
                f.write(script_text)

        if not messagebox.askyesno("确认制作", confirm_msg):
            return

        promo_duration = self.promo_duration_entry.get().strip()
        if promo_duration == "":
            promo_duration = None
        else:
            promo_duration = float(promo_duration)


        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "create_promo_video",
            "status": "运行中",
            "pid": self.get_pid(),
            "start_time": datetime.now()
        }

        def run_task():
            try:
                self.log_to_output(self.promo_output, f"🎬 开始制作宣传视频...")
                self.log_to_output(self.promo_output, f"音频文件: {file_path}")
                self.log_to_output(self.promo_output, f"开始持续时间: 10秒")
                self.log_to_output(self.promo_output, f"图像持续时间: 5秒")
                

                # Create promo video using workflow
                result = self.workflow.create_channel_promote_video(
                    promo_audio_path=file_path,
                    title=self.workflow.title,
                    program_keywords=self.project_keywords.get().strip(),
                    subtitle=script_text,
                    start_duration=10,
                    image_duration=5,
                    promo_duration=promo_duration
                )

                self.log_to_output(self.promo_output, f"✅ 宣传视频制作完成！")
                self.log_to_output(self.promo_output, f"输出文件: {result}")
                self.tasks[task_id]["status"] = "完成"

                # Show success message
                success_msg = f"宣传视频制作完成！\n\n输出文件: {result}"
                self.root.after(0, lambda: messagebox.showinfo("成功", success_msg))

            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.promo_output, f"❌ 宣传视频制作失败: {error_msg}")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                self.root.after(0, lambda: messagebox.showerror("错误", f"宣传视频制作失败: {error_msg}"))

        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()


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
            self.notify_task_completion(task_id, task_info)
        
        # 检查生成的视频（后台持续检查）
        self.check_generated_videos_background()


    def start_video_check_thread(self):
        """启动单例后台视频检查线程"""
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
                    # 执行检查任务
                    self._perform_video_check()
                    
                    # 等待5秒或直到收到停止信号
                    self.video_check_stop_event.wait(5)
                    
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
        if not hasattr(self, 'workflow') or not self.workflow:
            return
        
        try:
            if not hasattr(self.workflow, 'scenarios') or not self.workflow.scenarios:
                return
            
            # 遍历所有场景，检查是否有新生成的视频
            for scenario_index, scenario in enumerate(self.workflow.scenarios):
                if self.video_check_stop_event.is_set():
                    break
                
                try:
                    # 1. 检查 /wan_video/output_mp4 中已增强的视频
                    self.workflow.check_generated_clip_video(scenario, "clip", "clip_audio")
                    self.workflow.check_generated_clip_video(scenario, "second", "second_audio")
                    self.workflow.check_generated_clip_video(scenario, "zero", "zero_audio")
                    
                    # 2. 检查 X:\output 中新生成的原始视频（监控逻辑）
                    #self._check_output_folder(scenario_index, scenario)
                except Exception as e:
                    # 忽略单个场景的错误，继续检查其他场景
                    pass
        except Exception as e:
            # 忽略整体错误
            pass
    
    def check_generated_videos_background(self):
        """定时器调用此方法，但不再创建新线程（单例线程已在运行）"""
        # 检查单例线程是否还在运行，如果没有则重启
        if not self.video_check_running or not self.video_check_thread or not self.video_check_thread.is_alive():
            print("⚠️ 检测到后台线程未运行，正在重启...")
            self.start_video_check_thread()
    
    
    def _check_output_folder(self, scenario_index, scenario):
        """检查 X:\output 文件夹中的新视频文件"""
        import glob
        import time
        
        clip_animation = scenario.get("clip_animation", "")
        if clip_animation not in ["S2V", "FS2V", "WS2V", "2I2V", "I2V", "AI2V"]:
            # 不需要监控的场景，清理监控记录
            if scenario_index in self.monitoring_scenarios:
                del self.monitoring_scenarios[scenario_index]
            return
        
        output_folder = "X:\\output"
        if not os.path.exists(output_folder):
            return
        
        scenario_id = scenario.get('id', '')
        
        # 初始化监控记录
        if scenario_index not in self.monitoring_scenarios:
            self.monitoring_scenarios[scenario_index] = {
                "found_files": [],
                "start_time": time.time()
            }
        
        monitor_info = self.monitoring_scenarios[scenario_index]
        
        # 持续监控，不设置超时限制，直到GUI退出或找到文件
        
        try:
            if clip_animation in ["S2V", "FS2V", "PS2V", "I2V", "2I2V", "AI2V"]:
                # 查找以场景ID开头的mp4文件
                if clip_animation == "I2V":
                    pattern = os.path.join(output_folder, f"{self.get_pid()}_{scenario_id}_I2V_*.mp4")
                elif clip_animation == "2I2V":
                    pattern = os.path.join(output_folder, f"{self.get_pid()}_{scenario_id}_2I2V_*.mp4")
                elif clip_animation == "S2V":
                    pattern = os.path.join(output_folder, f"{self.get_pid()}_{scenario_id}_S2V_*-audio.mp4")
                elif clip_animation == "FS2V":
                    pattern = os.path.join(output_folder, f"{self.get_pid()}_{scenario_id}_FS2V_*-audio.mp4")
                elif clip_animation == "PS2V":
                    pattern = os.path.join(output_folder, f"{self.get_pid()}_{scenario_id}_PS2V_*-audio.mp4")
                elif clip_animation == "AI2V":
                    pattern = os.path.join(output_folder, f"{self.get_pid()}_{scenario_id}_AI2V_*.mp4")

                left_files = glob.glob(pattern)
                
                if not monitor_info["found_files"]:
                    monitor_info["found_files"] = left_files
                    return
                
                # 检查是否有新文件
                new_files = [f for f in left_files if f not in monitor_info["found_files"] and f not in self.processed_output_files]
                if new_files:
                    for file_path in new_files:
                        print(f"🎬 发现新视频文件: {os.path.basename(file_path)}")
                        monitor_info["found_files"].append(file_path)
                        self.processed_output_files.add(file_path)
                    
                    # 在主线程中处理文件
                    self.root.after(0, lambda idx=scenario_index, files=new_files: 
                        self._process_output_files(idx, files, "single"))
                    
                    # 处理完成，移除监控
                    del self.monitoring_scenarios[scenario_index]
            
            elif clip_animation == "WS2V":
                pattern = os.path.join(output_folder, f"{self.get_pid()}_{scenario_id}_L_WS2V_*-audio.mp4")
                left_files = glob.glob(pattern)

                pattern = os.path.join(output_folder, f"{self.get_pid()}_{scenario_id}_R_WS2V_*-audio.mp4")
                right_files = glob.glob(pattern)
                
                # 过滤掉已处理的文件
                new_left_files = [f for f in left_files if f not in self.processed_output_files]
                new_right_files = [f for f in right_files if f not in self.processed_output_files]
                
                # 检查是否两边都有文件
                if new_left_files and new_right_files:
                    # 排序确保配对的一致性
                    new_left_files.sort()
                    new_right_files.sort()
                    
                    # 取每组的第一个文件
                    left_file = new_left_files[0]
                    right_file = new_right_files[0]
                    
                    print(f"🎬 发现左侧视频: {os.path.basename(left_file)}")
                    print(f"🎬 发现右侧视频: {os.path.basename(right_file)}")
                    
                    # 将这两个文件放入 found_files
                    files_to_process = [left_file, right_file]
                    
                    # 标记所有找到的文件为已处理（不仅是配对的两个）
                    for file_path in left_files + right_files:
                        self.processed_output_files.add(file_path)
                    
                    # 在主线程中处理文件
                    self.root.after(0, lambda idx=scenario_index, files=files_to_process: 
                        self._process_output_files(idx, files, "dual"))
                    
                    # 处理完成，移除监控
                    del self.monitoring_scenarios[scenario_index]
        
        except Exception as e:
            print(f"❌ 检查输出文件夹时出错: {str(e)}")
    
    def _process_output_files(self, scenario_index, files, file_type):
        """处理从 X:\output 发现的文件"""
        try:
            if scenario_index >= len(self.workflow.scenarios):
                return
            
            scenario = self.workflow.scenarios[scenario_index]
            
            if file_type == "single":
                self.workflow._process_single_files(scenario, files)
            elif file_type == "dual":
                self.workflow._process_dual_files(scenario, files)
            
            # 处理完成后刷新GUI
            self.root.after(0, lambda: self.refresh_gui_scenarios())
            
        except Exception as e:
            print(f"❌ 处理输出文件时出错: {str(e)}")
    

    def notify_task_completion(self, task_id, task_info):
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


    def run_finalize_video(self, zero_audio_only):
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
                self.workflow.finalize_video(self.video_title.get().strip(), "", zero_audio_only) #self.program_keywords.get().strip())
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


    def clear_video_scenario_fields(self):
        self.scenario_duration.config(state="normal")
        self.scenario_duration.delete(0, tk.END)
        self.scenario_duration.config(state="readonly")
        
        self.clear_video_preview()


    def load_video_first_frame(self):
        self._cleanup_video_before_switch()

        current_scenario = self.get_current_scenario()
            
        video_path = get_file_path(current_scenario, "clip")
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
        current_scenario = self.get_current_scenario()
        video_path = None
        if current_scenario:
            video_path = get_file_path(current_scenario, "clip")
            
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
        current_scenario = self.get_current_scenario()
        video_path = None
        if current_scenario:
            video_path = get_file_path(current_scenario, "clip")
            
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
        clip = get_file_path(self.get_current_scenario(), "clip_audio")
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
            
        self.refresh_gui_scenarios()


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
            target_frame = int(current_time * self.STANDARD_FPS)
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
            
            # 更新进度显示 - 使用音频实际时长
            if self.video_start_time:
                elapsed_time = time.time() - self.video_start_time
                current_time = elapsed_time + (self.video_pause_time or 0)
            else:
                current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
                current_time = current_frame / self.STANDARD_FPS
            
            # 获取音频实际时长
            current_scenario = self.get_current_scenario()
            total_time = self.workflow.find_clip_duration(current_scenario)
            if total_time <= 0:
                total_time = total_frames / self.STANDARD_FPS
            
            # 确保不超过总时长
            if current_time > total_time:
                current_time = total_time
            
            current_min = int(current_time // 60)
            current_sec = int(current_time % 60)
            total_min = int(total_time // 60)
            total_sec = int(total_time % 60)
            
            self.video_progress_label.config(text=f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}")
            
            # 计算下一帧的延迟时间（毫秒）- 正常1倍播放速度
            delay = int(1000 / self.STANDARD_FPS)  # 正常播放速度
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


    def refresh_gui_scenarios(self):
        """刷新场景列表"""
        # self.workflow.load_scenarios()
        if self.current_scenario_index >= len(self.workflow.scenarios) :
            self.current_scenario_index = 0

        # 清理所有轨道的 VideoCapture（避免使用旧场景的视频）
        self.cleanup_track_video_captures()

        # 检查现有图像
        self.update_scenario_display()
        
        # 更新视频进度显示
        self.update_video_progress_display()

        # 更新按钮状态
        self.update_scenario_buttons_state()

        self.reset_second_track_playing_offset()

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
        track_path = get_file_path(self.get_current_scenario(), self.selected_second_track)

        """加载第二轨道视频的第一帧到画布"""
        try:
            self.second_track_canvas.delete("all")

            if not track_path:
                # 清除画布显示提示信息
                self.second_track_canvas.create_text(160, 90, text="第二轨道视频预览\n选择视频后播放显示",
                                                   fill='white', font=('Arial', 12), 
                                                   justify=tk.CENTER, tags="hint")
                self.track_time_label.config(text="00:00 / 00:00")
                return
            
            # 打开视频文件获取第一帧
            temp_cap = cv2.VideoCapture(track_path)
            if not temp_cap.isOpened():
                print(f"❌ 无法打开第二轨道视频文件: {track_path}")
                return
            
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
            total_duration = total_frames / self.STANDARD_FPS
            total_str = f"{int(total_duration // 60):02d}:{int(total_duration % 60):02d}"
            self.track_time_label.config(text=f"00:00 / {total_str}")
            
            temp_cap.release()
            print(f"✅ 已加载第二轨道视频第一帧: {os.path.basename(track_path)}")

        except Exception as e:
            print(f"❌ 加载第二轨道视频第一帧失败: {e}")
            self.second_track_canvas.delete("all")
            self.second_track_canvas.create_text(160, 90, text="第二轨道视频预览\n选择视频后播放显示",
                                               fill='white', font=('Arial', 12), 
                                               justify=tk.CENTER, tags="hint")


    def update_scenario_display(self):
        """更新场景显示"""
        if len(self.workflow.scenarios) == 0:
            self.scenario_label.config(text="0 / 0")
            self.clear_scenario_fields()
            self.clear_video_scenario_fields()
            return
            
        self.scenario_label.config(text=f"{self.current_scenario_index + 1} / {len(self.workflow.scenarios)}")
        scenario_data = self.get_current_scenario()
        if not scenario_data:
            return
        
        # 显示持续时间
        self.scenario_duration.config(state="normal")
        self.scenario_duration.delete(0, tk.END)
        duration = self.workflow.find_clip_duration(scenario_data)
        self.scenario_duration.insert(0, f"{duration:.2f} 秒")
        self.scenario_duration.config(state="readonly")
        
        # 设置宣传复选框状态
        clip_animation = scenario_data.get("clip_animation", "")
        self.scenario_main_animate.set(clip_animation)
        
        # 加载当前场景的效果设置 - 直接从scenarios JSON中读取
        current_effect = scenario_data.get("effect", config.SPECIAL_EFFECTS[0])
        self.current_effect_var.set(current_effect)
        
        # 加载当前场景的图像类型设置
        current_image_type = scenario_data.get("second_animation", config.ANIMATE_TYPES[0])
        self.scenario_second_animation.set(current_image_type)
        
        self.scenario_story_expression.delete("1.0", tk.END)
        self.scenario_story_expression.insert("1.0", scenario_data.get("story_expression", ""))
        
        self.scenario_era_time.delete("1.0", tk.END)
        self.scenario_era_time.insert("1.0", scenario_data.get("era_time", ""))
        
        self.scenario_location.delete(0, tk.END)
        self.scenario_location.insert(0, scenario_data.get("location", ""))

        self.scenario_person_in_story.delete("1.0", tk.END)
        self.scenario_person_in_story.insert("1.0", scenario_data.get("person_in_story_action", ""))
        
        self.scenario_speaker_action.delete("1.0", tk.END)
        self.scenario_speaker_action.insert("1.0", scenario_data.get("speaker_action", ""))

        self.scenario_extra.delete("1.0", tk.END)   
        self.scenario_extra.insert("1.0", scenario_data.get("extra", ""))

        # scenario_mood字段用于语音合成情绪
        self.scenario_speaker.set(scenario_data.get("speaker", ""))
        self.scenario_speaker_position.set(scenario_data.get("speaker_position", ""))
        voice_synthesis_mood = scenario_data.get("mood", "calm")
        if voice_synthesis_mood in EXPRESSION_STYLES:
            self.scenario_mood.set(voice_synthesis_mood)
        else:
            self.scenario_mood.set("calm")
        
        self.scenario_camera_light.delete("1.0", tk.END)
        self.scenario_camera_light.insert("1.0", scenario_data.get("camera_light", ""))
        
        self.scenario_story_content.delete("1.0", tk.END)
        self.scenario_story_content.insert("1.0", scenario_data.get("content", ""))


    def update_video_progress_display(self):
        """更新视频进度显示（未播放时显示总时长）"""
        if not hasattr(self, 'workflow'):
            return

        try:
            current_scenario = self.get_current_scenario()
            if current_scenario:
                clip_video = get_file_path(current_scenario, "clip")
                if clip_video:
                    total_duration = self.workflow.ffmpeg_processor.get_duration(clip_video)
                else:
                    total_duration = 0.0
                
                total_min = int(total_duration // 60)
                total_sec = int(total_duration % 60)
                
                if self.video_playing:
                    pass
                else:
                    self.video_progress_label.config(text=f"00:00 / {total_min:02d}:{total_sec:02d}")
            else:
                self.video_progress_label.config(text="00:00 / 00:00")
                
        except Exception as e:
            self.video_progress_label.config(text="00:00 / 00:00")
            print(f"⚠️ 更新视频进度显示失败: {e}")


    def clear_scenario_fields(self):
        self.scenario_duration.config(state="normal")
        self.scenario_duration.delete(0, tk.END)
        self.scenario_duration.config(state="readonly")
        
        self.scenario_main_animate.set("")
        
        self.scenario_story_expression.delete("1.0", tk.END)
        self.scenario_era_time.delete("1.0", tk.END)
        self.scenario_location.delete(0, tk.END)
        self.scenario_person_in_story.delete("1.0", tk.END)
        self.scenario_speaker_action.delete("1.0", tk.END)
        self.scenario_extra.delete("1.0", tk.END)
        self.scenario_speaker.set("")
        self.scenario_speaker_position.set("")
        self.scenario_mood.set("calm")
        self.scenario_camera_light.delete("1.0", tk.END)
        self.scenario_story_content.delete("1.0", tk.END)


    def prev_scenario(self):
        """上一个场景"""
        self.update_current_scenario()
        
        self.current_scenario_index -= 1
        if self.current_scenario_index < 0:
            self.current_scenario_index = len(self.workflow.scenarios) - 1

        self.refresh_gui_scenarios()


    def next_scenario(self):
        """下一个场景"""
        self.update_current_scenario()
        
        self.current_scenario_index += 1
        if self.current_scenario_index >= len(self.workflow.scenarios):
            self.current_scenario_index = 0

        self.refresh_gui_scenarios()


    def split_current_scenario(self):
        """分离当前场景"""      
        position = pygame.mixer.music.get_pos() / 1000.0
        self.workflow.split_scenario_at_position(self.current_scenario_index, position+self.playing_delta)
        self.playing_delta = 0.0
        self.playing_delta_label.config(text=f"{self.playing_delta:.1f}s")
        self.refresh_gui_scenarios()


    def clean_media_mark(self):
        """标记清理"""
        for scenario in self.workflow.scenarios:
            scenario["clip_animation"] = ""

        self.workflow.save_scenarios_to_json()
        messagebox.showinfo("成功", "标记清理成功！")


    def start_video_gen_batch(self):
        """启动WAN批生成"""
        current_scenario = self.get_current_scenario()
        previous_scenario = self.get_previous_scenario()
        next_scenario = self.get_next_scenario()

        ss = self.workflow.scenarios_in_story(current_scenario)
        for scenario in ss:
            self.generate_video(scenario, previous_scenario, next_scenario, "clip")
            self.generate_video(scenario, previous_scenario, next_scenario, "second")

        self.refresh_gui_scenarios()
        messagebox.showinfo("成功", "WAN视频批量生成成功！")


    def clean_wan(self):
        self.workflow.clean_folder("/wan_video/interpolated")
        self.workflow.clean_folder("/wan_video/enhanced")
        self.workflow.clean_folder("/wan_video/original")


    def clean_media(self):
        """媒体清理"""
        self.workflow.clean_media()
        self.workflow.save_scenarios_to_json()
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
        if self.playing_delta < -1.5:
            self.playing_delta = -1.5
        if self.playing_delta > 1.5:
            self.playing_delta = 1.5
        
        self.playing_delta_label.config(text=f"{self.playing_delta:.1f}s")


    def insert_scenario(self):
        self.update_scenario_buttons_state()
        current_scenario = self.get_current_scenario()
        if current_scenario and not self.workflow.first_scenario_of_story(current_scenario):
            return
        self.add_root_scenario(False)


    def append_scenario(self):
        self.update_scenario_buttons_state()
        current_scenario = self.get_current_scenario()
        if current_scenario and not self.workflow.last_scenario_of_story(current_scenario):
            return
        self.add_root_scenario(True)


    def add_root_scenario(self, is_append):
        """增加场景"""
        #dialog = BackgroundSelectorDialog(self, self.workflow, new_clip_image)
        #self.root.wait_window(dialog.dialog)

        # 检查用户是否确认了选择
        #if dialog.result and dialog.result.get('confirmed'):

        #background_images = dialog.result.get('background_images')  # 获取图片列表
        #background_music = dialog.result.get('background_music')

        background_images = [self.workflow.find_default_background_image()]  # 传递图片列表
        background_music = self.workflow.find_default_background_music()
        background_video = self.workflow.find_default_background_video()

        # 创建新场景
        self.workflow.add_root_scenario(
            self.current_scenario_index,
            self.story_site_entry.get(), 
            background_images[0],  # 传递图片列表
            background_music,
            background_video,
            is_append
        )
        self.refresh_gui_scenarios()
        
        # 显示成功消息
        image_names = ", ".join([os.path.basename(img) for img in background_images])
        messagebox.showinfo("成功", f"场景已添加\n背景图片 ({len(background_images)} 张): {image_names}\n背景音乐: {os.path.basename(background_music)}")
        #else:
        #    # 用户取消了操作
        #    messagebox.showinfo("取消", "未添加新场景")


    def reverse_video(self):
        """翻转视频"""
        current_scenario = self.get_current_scenario()
        oldv, newv = self.workflow.refresh_scenario_media(current_scenario, "clip", ".mp4")
        os.replace(self.workflow.ffmpeg_processor.reverse_video(oldv), newv)
        self.workflow.save_scenarios_to_json()
        self.refresh_gui_scenarios()


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
        current_scenario = self.get_current_scenario()
        oldv, newv = self.workflow.refresh_scenario_media(current_scenario, "clip", ".mp4")
        os.replace(self.workflow.ffmpeg_processor.mirror_video(oldv), newv)
        self.workflow.save_scenarios_to_json()
        self.refresh_gui_scenarios()


    def print_title(self):
        """打印标题"""
        current_scenario = self.update_current_scenario()
        title = current_scenario['content']
        if not title or title.strip() == "":
            messagebox.showinfo("标题", "标题为空")
            return
        clip_video = get_file_path(current_scenario, "clip")
        if not clip_video:
            messagebox.showinfo("标题", "视频为空")
            return
       
        title = self.workflow.transcriber.translate_text(title, self.workflow.language, self.workflow.language)
        current_scenario["keywords"] = title

        position = "footer"
        font_size = 105
        if title.startswith("h_"):
            position = "header"
            title = title[2:]   
        elif title.startswith("b_"):
            position = "body"
            title = title[2:]
        elif title.startswith("f_"):
            position = "footer"
            title = title[2:]
        if title.startswith("hl_"):
            font_size = 190
            position = "header"
            title = title[2:]   
        elif title.startswith("bl_"):
            font_size = 190
            position = "body"
            title = title[2:]
        elif title.startswith("fl_"):
            font_size = 190
            position = "footer"
            title = title[2:]
        elif title.startswith("hm_"):
            position = "header"
            font_size = 80
            title = title[3:]
        elif title.startswith("bm_"):
            position = "body"
            font_size = 80
            title = title[3:]
        elif title.startswith("fm_"):
            position = "footer"
            font_size = 80
            title = title[3:]
        elif title.startswith("hs_"):
            position = "header"
            font_size = 60
            title = title[3:]
        elif title.startswith("bs_"):
            position = "body"
            font_size = 60
            title = title[3:]
        elif title.startswith("fs_"):
            position = "footer"
            font_size = 60
            title = title[3:]

        v = self.workflow.ffmpeg_processor.add_script_to_video(clip_video, title, self.workflow.font_video, font_size, position)
        back = current_scenario.get('back', '')
        current_scenario['back'] = clip_video + "," + back
        self.workflow.refresh_scenario_media(current_scenario, "clip", ".mp4", v)

        self.workflow.save_scenarios_to_json()
        self.refresh_gui_scenarios()


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
        second_video_path = get_file_path(self.get_current_scenario(), self.selected_second_track)
        second_audio_path = get_file_path(self.get_current_scenario(), self.selected_second_track+'_audio')
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
                    self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(self.second_track_paused_time * self.STANDARD_FPS))
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

                self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(play_start_time * self.STANDARD_FPS))
                
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
                target_frame = int(current_time * self.STANDARD_FPS)
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
            delay = max(1, int(1000 / self.STANDARD_FPS))  # 毫秒
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
        self.reset_second_track_playing_offset() # self.second_track_pause_offset
        
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
            current_scenario = self.get_current_scenario()
            if not current_scenario:
                return
            
            # 获取视频路径
            left_path = current_scenario.get('second_left')
            right_path = current_scenario.get('second_right')
            audio_path = current_scenario.get('clip_audio')
            
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
                target_frame = int(elapsed_time * self.STANDARD_FPS)
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
            total_duration = total_frames_left / fps
            
            current_str = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
            total_str = f"{int(total_duration // 60):02d}:{int(total_duration % 60):02d}"
            self.track_time_label.config(text=f"{current_str} / {total_str}")
            
            # 安排下一帧
            delay = max(1, int(1000 / fps))
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
        """tab切换时停止正在播放的视频"""
        self.pause_second_track()
        self.pause_pip_lr()
        
        current_tab_index = self.second_notebook.index(self.second_notebook.select())
        if current_tab_index == 0:
            self.load_second_track_first_frame()
        elif current_tab_index == 1:
            self.load_pip_lr_first_frame()

    
    def load_pip_lr_first_frame(self):
        """加载 PIP L/R 视频的第一帧"""
        try:
            current_scenario = self.get_current_scenario()
            if not current_scenario:
                return
            
            left_path = current_scenario.get(self.selected_second_track+'_left')
            right_path = current_scenario.get(self.selected_second_track+'_right')
            
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
                total_duration = total_frames / self.STANDARD_FPS
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
        
        try:
            # 获取当前场景
            current_scenario = self.get_current_scenario()
            if not current_scenario:
                messagebox.showerror("错误", "没有选中场景")
                return
            
            # 复制图片到项目目录
            self.workflow.refresh_scenario_media(current_scenario, image_type, ".webp", file_path, True)
            
            # 刷新显示
            self.display_image_on_canvas_for_track(image_type)
            
            self.workflow.save_scenarios_to_json()
            print(f"✅ 已更新 {image_type}: {os.path.basename(file_path)}")
            messagebox.showinfo("成功", f"已更新 {image_type.replace('_', ' ')}")
            
        except Exception as e:
            error_msg = f"更新图片失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)


    def display_image_on_canvas_for_track(self, image_type):
        try:
            current_scenario = self.get_current_scenario()
            if not current_scenario:
                return
            
            image_path = current_scenario.get(image_type)
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

    
    def on_image_double_click(self, image_type):
        """处理图片双击事件 - 使用OpenAI描述图片"""
        try:
            current_scenario = self.get_current_scenario()
            if not current_scenario:
                messagebox.showwarning("警告", "请先选择一个场景")
                return
            
            # 获取对应的图片路径
            from utility.file_util import get_file_path
            image_path = get_file_path(current_scenario, image_type)
            
            if not image_path or not os.path.exists(image_path):
                messagebox.showwarning("警告", f"未找到 {image_type} 图片")
                return
            
            # 确定要保存描述的字段名
            if image_type == 'clip_image':
                extra_field = 'clip_extra'
                display_name = "场景图片"
            elif image_type == 'second_image':
                extra_field = 'second_extra'
                display_name = "第二轨道图片"
            elif image_type == 'zero_image':
                extra_field = 'zero_extra'
                display_name = "背景轨道图片"
            else:
                return
            
            # 显示处理中的提示
            print(f"🔍 正在使用 OpenAI 描述 {display_name}...")
            
            # 在后台线程中调用 OpenAI API
            def describe_in_background():
                try:
                    # 调用 OpenAI 描述图片
                    description = self.workflow.sd_processor.describe_image_openai(image_path)
                    
                    # 在主线程中更新场景数据
                    def update_scenario():
                        current_scenario[extra_field] = description
                        self.workflow.save_scenarios_to_json()
                        print(f"✅ {display_name} 描述已保存到 {extra_field}")
                        print(f"📝 描述内容: {description[:100]}..." if len(description) > 100 else f"📝 描述内容: {description}")
                        messagebox.showinfo("成功", f"{display_name} 描述已保存到 {extra_field}\n\n{description[:200]}..." if len(description) > 200 else f"{display_name} 描述已保存到 {extra_field}\n\n{description}")
                    
                    self.root.after(0, update_scenario)
                    
                except Exception as e:
                    error_msg = f"描述图片失败: {str(e)}"
                    print(f"❌ {error_msg}")
                    self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            
            # 启动后台线程
            import threading
            thread = threading.Thread(target=describe_in_background, daemon=True)
            thread.start()
            
        except Exception as e:
            error_msg = f"处理双击事件失败: {str(e)}"
            print(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)


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
            total_duration = total_frames / self.STANDARD_FPS
            
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
                current_time = current_pos / self.STANDARD_FPS
            
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
            current_time = current_pos / self.STANDARD_FPS
            
            # 前进1秒
            new_time = current_time + 1.0
            
            # 获取视频总时长
            total_frames = self.second_track_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            total_duration = total_frames / self.STANDARD_FPS
            
            # 确保不超过视频总时长
            if new_time >= total_duration:
                new_time = total_duration - 0.1
                
            # 跳转到新位置
            self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(new_time * self.STANDARD_FPS))
            
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
            new_time = current_pos / self.STANDARD_FPS - 1.0
            if new_time < 0:
                new_time = 0
                
            # 跳转到新位置
            self.second_track_cap.set(cv2.CAP_PROP_POS_FRAMES, int(new_time * self.STANDARD_FPS))
            
            # 更新时间显示
            self.update_second_track_time_display()
            
            print(f"⏪ 第二轨道后退1秒")
            
        except Exception as e:
            print(f"❌ 第二轨道后退失败: {e}")
    

    def shift_forward(self):
        """前移当前场景"""
        position = pygame.mixer.music.get_pos() / 1000.0
        self.workflow.shift_scenario(self.current_scenario_index, self.current_scenario_index+1, position+self.playing_delta)
        self.playing_delta = 0.0

        self.refresh_gui_scenarios()


    def shift_before(self):
        """下移当前场景"""
        position = pygame.mixer.music.get_pos() / 1000.0
        self.workflow.shift_scenario(self.current_scenario_index, self.current_scenario_index-1, position+self.playing_delta)
        self.playing_delta = 0.0

        self.refresh_gui_scenarios()


    def extend_scenario(self):
        """扩展当前场景"""
        if self.playing_delta <= 0:
            messagebox.showinfo("警告", "⚠️ 当前场景无法扩展 - " + str(self.playing_delta))
            return
        self.workflow.extend_scenario(self.current_scenario_index, self.playing_delta)
        self.refresh_gui_scenarios()


    def merge_or_delete(self):
        """合并当前图片与下一张图片"""
        if len(self.workflow.scenarios) == 0:
            messagebox.showinfo("警告", "⚠️ 无场景")
            return

        current_scenario = self.get_current_scenario()
        ss = self.workflow.scenarios_in_story(current_scenario)
        if len(ss) <= 1:
            result = messagebox.askyesno("警告", "⚠️ 删除唯一场景?")
            if result:
                ss = self.workflow.replace_scenario(self.current_scenario_index)
        else:
            if ss[-1] == current_scenario:
                result = messagebox.askyesno("警告", "⚠️ 删除当前场景?")
                if result:
                    ss = self.workflow.replace_scenario(self.current_scenario_index)
            else:
                result = messagebox.askyesno("警告", "⚠️ 合并还是删除场景\nYes: 合并\nNo: 删除")
                if result:
                    self.workflow.merge_scenario(self.current_scenario_index, self.current_scenario_index+1)
                else:
                    result = messagebox.askyesno("警告", "⚠️ 删除当前场景?")
                    if result:
                        ss = self.workflow.replace_scenario(self.current_scenario_index)
            
        self.refresh_gui_scenarios()
        messagebox.showinfo("合并场景", "完成")


    def swap_with_next_image(self):
        """交换当前图片与下一张图片"""
        current_index = self.current_scenario_index
        current_scenario = self.workflow.scenarios[current_index]

        ss = self.workflow.scenarios_in_story(current_scenario)
        if len(ss) <= 1 or current_scenario == ss[-1]:
            messagebox.showinfo("警告", "⚠️ 当前场景无法交换")
            return
        
        next_index = current_index + 1
        next_scenario = self.workflow.scenarios[next_index]

        # 查找当前场景和下一个场景的图像文件
        temp_image = current_scenario["clip_image"]
        current_scenario["clip_image"] = next_scenario["clip_image"]
        next_scenario["clip_image"] = temp_image

        # self.workflow._generate_video_from_image(current_scenario)
        # self.workflow._generate_video_from_image(next_scenario)
        
        # 显示成功消息
        messagebox.showinfo("成功", f"已成功交换场景 {current_index + 1} 和场景 {next_index + 1} 的图片！")


    def swap_scenario(self):
        """交换当前场景与下一张场景"""
        self.workflow.swap_scenario(self.current_scenario_index, self.current_scenario_index+1)
        self.refresh_gui_scenarios()


    def regenerate_scenario(self):
        self.workflow.refresh_scenario( self.get_current_scenario() )
        self.refresh_gui_scenarios()


    def copy_images_to_next(self):
        current_scenario = self.get_current_scenario()
        next_scenario = self.workflow.next_scenario_of_story(current_scenario)
        if current_scenario and next_scenario:
            clip_image_split = current_scenario.get("clip_image_split", "")
            clip_animation = current_scenario.get("clip_animation", "")
            second_animation = current_scenario.get("second_animation", "")

            next_scenario["clip_image_split"] = clip_image_split
            next_scenario["clip_animation"] =  clip_animation
            next_scenario["second_animation"] = second_animation

            clip_image = current_scenario.get("clip_image", "")
            clip_image_last = current_scenario.get("clip_image_last", "")
            if clip_image:
                self.workflow.refresh_scenario_media(next_scenario, "clip_image", ".webp", clip_image, True)
            if clip_image_last:
                self.workflow.refresh_scenario_media(next_scenario, "clip_image_last", ".webp", clip_image_last, True)

            second_image = current_scenario.get("second_image", "")
            second_image_last = current_scenario.get("second_image_last", "")
            if second_image:
                self.workflow.refresh_scenario_media(next_scenario, "second_image", ".webp", second_image, True)
            if second_image_last:
                self.workflow.refresh_scenario_media(next_scenario, "second_image_last", ".webp", second_image_last, True)

            self.workflow.save_scenarios_to_json()
            self.refresh_gui_scenarios()


    def recreate_second_image(self):
        """重新创建次图，先打开对话框让用户审查和编辑提示词"""
        scenario = self.get_current_scenario()
        # 定义创建图像的回调函数
        def create_second_image(edited_positive, edited_negative):
            oldi, newi = self.workflow.refresh_scenario_media(scenario, "second_image", ".webp")
            self.workflow._create_image(self.workflow.sd_processor.gen_config["Story"], 
                                        newi,
                                        None,
                                        edited_positive,
                                        edited_negative,
                                        int(time.time())
                                    )
            self.workflow.save_scenarios_to_json()
            self.refresh_gui_scenarios()
            print("✅ 次图已重新创建")
        
        # 构建正面提示词预览
        self.open_image_prompt_dialog(create_second_image, scenario, "second")


    def recreate_clip_image(self):
        """重新创建主图，先打开对话框让用户审查和编辑提示词"""
        scenario = self.get_current_scenario()
        
        # 定义创建图像的回调函数
        def create_clip_image(edited_positive, edited_negative):
            oldi, newi = self.workflow.refresh_scenario_media(scenario, "clip_image", ".webp")
            self.workflow._create_image(self.workflow.sd_processor.gen_config["Story"], 
                                        newi,
                                        None,
                                        newi,
                                        edited_positive,
                                        edited_negative,
                                        int(time.time())
                                    )
            self.workflow.save_scenarios_to_json()
            self.refresh_gui_scenarios()
            print("✅ 主图已重新创建")
        
        # 构建正面提示词预览
        self.open_image_prompt_dialog(create_clip_image, scenario, "clip")


    def update_current_scenario(self):
        scenario = self.get_current_scenario()
        scenario.update({
            "story_expression": self.scenario_story_expression.get("1.0", tk.END).strip(),
            "era_time": self.scenario_era_time.get("1.0", tk.END).strip(),
            "location": self.scenario_location.get(),
            "person_in_story_action": self.scenario_person_in_story.get("1.0", tk.END).strip(),
            "speaker_action": self.scenario_speaker_action.get("1.0", tk.END).strip(),
            "extra": self.scenario_extra.get("1.0", tk.END).strip(),
            "speaker": self.scenario_speaker.get(),
            "speaker_position": self.scenario_speaker_position.get(),  # 添加讲员位置字段
            "mood": self.scenario_mood.get(),         # 语音合成情绪
            "camera_light": self.scenario_camera_light.get("1.0", tk.END).strip(),
            "clip_animation": self.scenario_main_animate.get(),
            "content": self.scenario_story_content.get("1.0", tk.END).strip()
        })
        self.workflow.save_scenarios_to_json()
        return scenario


    def load_config(self):
        """加载当前项目的配置"""
        try:
            # 临时禁用自动保存，避免加载过程中触发保存
            self._loading_config = True
            config_loaded = False
            
            if self.current_project_config:
                # 使用统一的配置应用方法
                self.apply_config_to_gui(self.current_project_config)
                
                # 检查是否有有效PID
                saved_pid = self.current_project_config.get('pid', '')
                if saved_pid:
                    config_loaded = True
                    
                # 同步标题到workflow
                saved_video_title = self.current_project_config.get('video_title', '默认标题')
                if saved_video_title and saved_video_title != '默认标题':
                    self.video_title.delete(0, tk.END)
                    self.video_title.insert(0, saved_video_title)
                    # 只在workflow已创建时设置标题
                    if hasattr(self, 'workflow') and self.workflow is not None:
                        self.workflow.set_title(saved_video_title)

                if config_loaded:
                    saved_language = self.current_project_config.get('language', 'tw')
                    saved_channel = self.current_project_config.get('channel', 'strange_zh')
                    saved_video_width = self.current_project_config.get('video_width', str(config.VIDEO_WIDTH))
                    saved_video_height = self.current_project_config.get('video_height', str(config.VIDEO_HEIGHT))
                    saved_promo_scroll_duration = self.current_project_config.get('promo_scroll_duration', 7.0)
                    
                    print(f"✅ 已加载项目配置: PID={saved_pid}, 语言={saved_language}, 频道={saved_channel}")
                    print(f"   视频标题: {saved_video_title}")
                    print(f"   视频尺寸: {saved_video_width}x{saved_video_height}")
                    print(f"   宣传视频滚动持续时间: {saved_promo_scroll_duration}秒")
                else:
                    print("⚠️ 项目配置中没有有效的PID，将自动生成新PID")
            else:
                print("⚠️ 没有当前项目配置，将使用默认配置")
                # 使用默认配置初始化所有字段
                default_config = self.create_default_config()
                self.apply_config_to_gui(default_config)
            
            # PID现在在项目创建时设置，不再自动生成
            if not config_loaded:
                print("⚠️ 项目配置无效，PID/语言/频道将保持默认值")
                
        except Exception as e:
            print(f"❌ 加载配置失败: {e}")
            print("⚠️ 将使用默认配置")
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
                
            # 加载关键字
            program_keywords = config_data.get('program_keywords', '')
            if hasattr(self, 'project_keywords'):
                self.project_keywords.delete(0, tk.END)
                self.project_keywords.insert(0, program_keywords)
                
            # 故事场地组
            story_site_entry = config_data.get('story_site', '')
            if hasattr(self, 'story_site_entry'):
                self.story_site_entry.delete(0, tk.END)
                self.story_site_entry.insert(0, story_site_entry)
                

                    
            # 加载视频尺寸
            video_width = config_data.get('video_width', str(config.VIDEO_WIDTH))
            if hasattr(self, 'video_width'):
                self.video_width.delete(0, tk.END)
                self.video_width.insert(0, video_width)
                
            video_height = config_data.get('video_height', str(config.VIDEO_HEIGHT))
            if hasattr(self, 'video_height'):
                self.video_height.delete(0, tk.END)
                self.video_height.insert(0, video_height)
            
            # WAN 选项已移到 WanPromptEditorDialog 中，不再需要加载到 GUI
                
            # 加载宣传视频滚动持续时间
            promo_scroll_duration = config_data.get('promo_scroll_duration', 7.0)
            self.promo_scroll_duration = promo_scroll_duration
            
            # 自动加载宣传视频脚本内容
            self.load_promo_script_content()
            
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
            if self.current_project_config:
                pid = self.current_project_config.get('pid', '未知PID')
                title = self.current_project_config.get('video_title', '未知标题')
                
                # 检查是否有未保存的更改
                current_data = self.get_current_config_data()
                has_changes = current_data != self.current_project_config
                
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
            else:
                print("⚠️ 没有当前项目配置")
                
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
            'program_keywords': getattr(self, 'program_keywords', None) and self.program_keywords.get() or '',
            'story_site': getattr(self, 'story_site_entry', None) and self.story_site_entry.get() or '',
            'video_width': getattr(self, 'video_width', None) and self.video_width.get() or str(config.VIDEO_WIDTH),
            'video_height': getattr(self, 'video_height', None) and self.video_height.get() or str(config.VIDEO_HEIGHT),
            'promo_scroll_duration': getattr(self, 'promo_scroll_duration', None) or 7.0,
            'conversation_content': getattr(self, 'conversation_content', None) or ''
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

                'program_keywords': getattr(self, 'program_keywords', None) and self.program_keywords.get() or '',
                'story_site': getattr(self, 'story_site_entry', None) and self.story_site_entry.get() or '',
                'video_width': getattr(self, 'video_width', None) and self.video_width.get() or str(config.VIDEO_WIDTH),
                'video_height': getattr(self, 'video_height', None) and self.video_height.get() or str(config.VIDEO_HEIGHT),
                'promo_scroll_duration': getattr(self, 'promo_scroll_duration', None) or 7.0,
                'conversation_content': getattr(self, 'conversation_content', None) or ''
            }

            # Save audio_prepares data if available
            if workflow and hasattr(workflow, 'audio_prepares'):
                config_data['audio_prepares'] = workflow.video_prepares
            
            # Preserve video_id and other important fields from existing config
            if hasattr(self, 'current_project_config') and self.current_project_config:
                if 'video_id' in self.current_project_config:
                    config_data['video_id'] = self.current_project_config['video_id']
                if 'generated_titles' in self.current_project_config:
                    config_data['generated_titles'] = self.current_project_config['generated_titles']
                if 'generated_tags' in self.current_project_config:
                    config_data['generated_tags'] = self.current_project_config['generated_tags']
            
            # 更新当前项目配置
            self.current_project_config = config_data
            
            # 保存到文件
            config_manager = ProjectConfigManager(self.get_pid())
            config_manager.project_config = config_data.copy()
            config_manager.save_project_config(config_data)
                
        except Exception as e:
            print(f"❌ 保存项目配置失败: {e}")



    def bind_edit_events(self):
        """绑定编辑事件"""
        # 绑定场景信息编辑字段的Enter键事件，用于自动保存
        scenario_fields = [
            self.scenario_story_expression,
            self.scenario_era_time,
            self.scenario_location,
            self.scenario_person_in_story,
            self.scenario_speaker_action,
            self.scenario_extra,
            self.scenario_camera_light,
            self.scenario_story_content
        ]
        
        for field in scenario_fields:
            # 绑定Enter键事件（Ctrl+Enter在ScrolledText中触发保存）
            field.bind('<Control-Return>', self.on_scenario_field_enter)
            field.bind('<Control-Enter>', self.on_scenario_field_enter)
            # 也绑定失去焦点事件作为备选保存机制
            field.bind('<FocusOut>', self.on_scenario_field_focus_out)
        
        # 为Entry和Combobox字段单独绑定失去焦点事件
        entry_combobox_fields = [
            self.scenario_speaker,
            self.scenario_mood,
            self.scenario_speaker_position
        ]
        
        for field in entry_combobox_fields:
            field.bind('<FocusOut>', self.on_scenario_field_focus_out)
            field.bind('<<ComboboxSelected>>', self.on_scenario_field_change)
        
        print("📝 已绑定场景编辑字段的自动保存事件 (Ctrl+Enter 或失去焦点时保存)")
    

    def bind_config_change_events(self):
        """绑定配置变化事件"""
        # PID, 语言和频道现在都是只读的，不需要绑定变化事件
            
        # 绑定video_title变化事件
        if hasattr(self, 'video_title'):
            self.video_title.bind('<KeyRelease>', self.on_video_title_change)
            self.video_title.bind('<FocusOut>', self.on_video_title_change)
        
        # 绑定program_keywords变化事件
        if hasattr(self, 'program_keywords'):
            self.program_keywords.bind('<KeyRelease>', self.on_config_change)
            self.program_keywords.bind('<FocusOut>', self.on_config_change)
            
        # 绑定story_site变化事件
        if hasattr(self, 'story_site_entry'):
            self.story_site_entry.bind('<KeyRelease>', self.on_config_change)
            self.story_site_entry.bind('<FocusOut>', self.on_config_change)
            

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

    def on_scenario_edit(self, event=None):
        """当场景信息被编辑时的回调（现在不需要）"""
        # 保存按钮现在总是可用
        pass

    def on_scenario_field_enter(self, event=None):
        """当在场景编辑字段中按下Ctrl+Enter时的回调"""
        # 保存当前场景信息到JSON并传播到相同raw_scenario_index的场景
        self.update_current_scenario()
        return "break"  # 阻止默认的换行行为

    def on_scenario_field_focus_out(self, event=None):
        """当场景编辑字段失去焦点时的回调"""
        # 延迟保存以避免频繁操作
        if hasattr(self, '_save_timer'):
            self.root.after_cancel(self._save_timer)
        self._save_timer = self.root.after(500, lambda: self.update_current_scenario())  # 500ms延迟

    def on_scenario_field_change(self, event=None):
        """当场景字段值发生变化时的回调（如Combobox选择变化）"""
        # 立即保存当前场景信息
        self.update_current_scenario()
        print(f"✅ 场景 {self.current_scenario_index + 1} 情绪已更新为: {self.scenario_mood.get()}")

    def on_volume_change(self, *args):
        """当音量滑块值发生变化时的回调"""
        volume = self.track_volume_var.get()
        self.volume_label.config(text=f"{volume:.1f}")

    def on_tab_changed(self, event):
        if not hasattr(self, 'workflow') or self.workflow is None:
            return
        self.refresh_gui_scenarios()


    def setup_drag_and_drop(self):
        self.video_canvas.drop_target_register(DND_FILES)
        self.video_canvas.dnd_bind('<<Drop>>', self.on_media_drop)
        self.video_canvas.dnd_bind('<<DragEnter>>', self.on_video_drag_enter)
        self.video_canvas.dnd_bind('<<DragLeave>>', self.on_video_drag_leave)
        
        # 添加双击事件绑定
        self.video_canvas.bind('<Double-Button-1>', self.on_video_canvas_double_click)


    def handle_av_replacement(self, av_path, replace_media_audio, media_type, initial_start_time=None, initial_end_time=None):
        """处理音频替换"""
        try:
            current_scenario = self.get_current_scenario()
            previous_scenario = self.get_previous_scenario()
            next_scenario = self.get_next_scenario()
            scenarios_same_story = self.workflow.scenarios_in_story(current_scenario)

            print(f"🎬 打开合并编辑器 - 媒体类型: {media_type}, 替换音频: {replace_media_audio}")
            review_dialog = AVReviewDialog(self, av_path, current_scenario, previous_scenario, next_scenario, media_type, replace_media_audio, initial_start_time, initial_end_time)
            
            # 等待对话框关闭
            self.root.wait_window(review_dialog.dialog)

            if media_type != "clip" :
                transcribe_way = "" if ('transcribe_way' not in review_dialog.result) else review_dialog.result['transcribe_way']
                if transcribe_way == "multiple":
                    for sss in scenarios_same_story:
                        sss[media_type] = current_scenario[media_type]
                        sss[media_type+"_audio"]  = current_scenario[media_type+"_audio"]
                        sss[media_type+"_image"]  = current_scenario[media_type+"_image"]
                self.workflow.save_scenarios_to_json()
                return

            self.workflow.save_scenarios_to_json()

            # media_type == clip
            if (not review_dialog.result) or ('transcribe_way' not in review_dialog.result) or (review_dialog.result['transcribe_way'] == "none"):
                print("场景内容无变化")
                return

            transcribe_way = review_dialog.result['transcribe_way']
            audio_json = review_dialog.result['audio_json']

            # WAN 参数现在保存在对话框中，使用场景中已有的值或默认值
            if "wan_style" not in current_scenario:
                current_scenario["wan_style"] = ""
            if "wan_shot" not in current_scenario:
                current_scenario["wan_shot"] = ""
            if "wan_angle" not in current_scenario:
                current_scenario["wan_angle"] = ""
            if "wan_color" not in current_scenario:
                current_scenario["wan_color"] = ""

            current_scenario["clip_animation"] = ""

            if transcribe_way == "single":
                current_scenario["content"] = "\n".join([segment["content"] for segment in audio_json])
                self.workflow.refresh_scenario(current_scenario)
            elif transcribe_way == "multiple":
                self.workflow.prepare_scenarios_from_json(  raw_scenario=current_scenario,
                                                            raw_index=self.current_scenario_index,
                                                            audio_json=audio_json, 
                                                            style=current_scenario["wan_style"],
                                                            shot=current_scenario["wan_shot"],
                                                            angle=current_scenario["wan_angle"],
                                                            color=current_scenario["wan_color"] )

            messagebox.showinfo("成功", f"音频已成功替换！\n\n")
                
        except Exception as e:
            messagebox.showerror("错误", f"音频替换失败: {str(e)}")


    def handle_image_replacement(self, source_image_path):
        """处理图像替换"""
        try:
            # 获取视频尺寸
            video_width = self.video_width.get() or "1920"
            video_height = self.video_height.get() or "1080"
            
            # 导入图像区域选择对话框
            from gui.image_area_selector_dialog import show_image_area_selector
            
            # 显示图像区域选择对话框
            selected_image_path, vertical_line_position, target_field = show_image_area_selector(
                self, source_image_path, video_width, video_height
            )
            
            if selected_image_path is None:
                return  # 用户取消了选择
            
            # 字段名映射
            field_names = {
                "clip_image": "当前场景图片",
                "clip_image_last": "最后场景图片"
            }
            
            # 弹出确认对话框
            dialog = messagebox.askyesno("确认替换场景的图像/视频", 
                                       f"确定要替换 {field_names.get(target_field, target_field)} 吗？\n垂直分割线位置: {vertical_line_position}")
            if not dialog:
                # 清理临时文件
                try:
                    os.remove(selected_image_path)
                except:
                    pass
                return
            
            current_scenario = self.get_current_scenario()
            self.workflow.replace_scenario_image(current_scenario, selected_image_path, vertical_line_position, target_field)
            
            # 刷新GUI显示
            self.refresh_gui_scenarios()
            
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
        elif is_audio_file(dropped_file) or is_video_file(dropped_file):
            from gui.enhanced_media_editor import MediaTypeSelector
            selector = MediaTypeSelector(self.root, dropped_file, self.get_current_scenario())
            replace_media_audio, media_type = selector.show()
            if not media_type:
                return  # 用户取消
            self.handle_av_replacement(dropped_file, replace_media_audio, media_type)

        self.refresh_gui_scenarios()


    def on_video_canvas_configure(self, event):
        """当video canvas尺寸改变时，动态调整提示文本位置"""
        canvas_width = event.width
        canvas_height = event.height
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        
        # 更新拖拽提示文本的位置到canvas中心
        self.video_canvas.coords("drag_hint", center_x, center_y)


    def on_video_canvas_double_click(self, event):
        current_scenario = self.get_current_scenario()
        from gui.enhanced_media_editor import MediaTypeSelector
        selector = MediaTypeSelector(self.root, None, current_scenario)
        replace_media_audio, media_type = selector.show()
        if not media_type:
            return  # 用户取消
        elif media_type == 'clip':
            dropped_file = get_file_path(current_scenario, "clip")
        elif media_type == 'zero':
            dropped_file = get_file_path(current_scenario, "zero")
        elif media_type == 'one':
            dropped_file = get_file_path(current_scenario, "one")
        else:
            dropped_file = get_file_path(current_scenario, "second")

        self.handle_av_replacement(dropped_file, replace_media_audio, media_type)

        self.refresh_gui_scenarios()


    def on_clip_animation_change(self, event=None):
        current_scenario = self.get_current_scenario()
        current_scenario["clip_animation"] = self.scenario_main_animate.get()
        self.workflow.save_scenarios_to_json()

    def on_video_clip_animation_change(self, event=None):
        """当视频标签页宣传模式发生变化时的回调函数"""
        # 保存当前场景的宣传模式到JSON
        current_scenario = self.get_current_scenario()
        current_scenario["clip_animation"] = self.scenario_main_animate.get()
        self.workflow.save_scenarios_to_json()
        self.log_to_output(self.video_output, f"✅ 宣传模式已更新为: {self.scenario_main_animate.get()}")


    def on_image_type_change(self, event=None):
        """处理图像类型选择变化"""
        selected_image_type = self.scenario_second_animation.get()
        print(f"✅ 场景 {self.current_scenario_index + 1} 图像类型已设置为: {selected_image_type}")
        
        # 保存图像类型到scenarios JSON文件
        self.save_second_animation_to_scenarios_json(self.current_scenario_index, selected_image_type)
        
        # 标记配置已更改
        self._config_changed = True


    def update_scenario_field(self, scenario_index, field_name, field_value):
        """更新单个场景的特定字段"""
        try:
            workflow = self.workflow
            
            if scenario_index >= len(workflow.scenarios):
                print(f"❌ 场景索引 {scenario_index} 超出范围")
                return False
            
            # 调试：显示更新前的状态
            old_value = workflow.scenarios[scenario_index].get(field_name, "未设置")
            print(f"🔍 调试: 场景 {scenario_index + 1} 的 {field_name} 从 '{old_value}' 更新为 '{field_value}'")
            
            # 更新workflow内存中的数据
            workflow.scenarios[scenario_index][field_name] = field_value
            
            # 验证更新
            new_value = workflow.scenarios[scenario_index].get(field_name)
            print(f"✅ 验证: 场景 {scenario_index + 1} 的 {field_name} 现在是 '{new_value}'")
            
            return self.workflow.save_scenarios_to_json()
            
        except Exception as e:
            print(f"❌ 更新场景字段失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


    def update_scenario_fields(self, scenario_index, field_updates):
        """批量更新单个场景的多个字段"""
        try:
            workflow = self.workflow
            
            if scenario_index >= len(workflow.scenarios):
                print(f"❌ 场景索引 {scenario_index} 超出范围")
                return False
            
            # 批量更新workflow内存中的数据
            for field_name, field_value in field_updates.items():
                workflow.scenarios[scenario_index][field_name] = field_value
            # 立即保存到JSON文件
            field_names = list(field_updates.keys())
            return self.workflow.save_scenarios_to_json()
            
        except Exception as e:
            print(f"❌ 批量更新场景字段失败: {str(e)}")
            return False

        
    def save_second_animation_to_scenarios_json(self, scenario_index, image_type):
        """保存单个场景的图像类型到scenarios JSON文件"""
        return self.update_scenario_field(scenario_index, "second_animation", image_type)
        

    def generate_video(self, scenario, previous_scenario, next_scenario, image_typ):
        image_path = get_file_path(scenario, image_typ+"_image")
        image_last_path = get_file_path(scenario, image_typ+"_image_last")

        animate_mode = scenario.get(image_typ+"_animation", "")
        if animate_mode not in config.ANIMATE_TYPES or animate_mode.strip() == "":
            return

        if animate_mode == "2I2V" and not image_last_path:
            animate_mode = "I2V"

        wan_prompt = scenario.get(image_typ+"_prompt", "")
        
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
            wan_prompt = self.workflow.build_prompt(scenario, "", "", image_typ, animate_mode)

        action_path = get_file_path(scenario, "clip_action")

        sound_path = get_file_path(scenario, "clip_audio")
        if animate_mode == "PS2V":
            previous_sound = None
            next_sound = None

            if previous_scenario:
                previous_sound = get_file_path(previous_scenario, "clip_audio")
                if previous_sound:
                    previous_sound_duration = self.workflow.ffmpeg_audio_processor.get_duration(previous_sound)
                    if previous_sound_duration > 3.0:
                        previous_sound = self.workflow.ffmpeg_audio_processor.audio_cut_fade(previous_sound, previous_sound_duration-3.0, 3.0)
            
            if next_scenario:
                next_sound = get_file_path(next_scenario, "clip_audio")
                if next_sound:
                    if self.workflow.ffmpeg_audio_processor.get_duration(next_sound) > 3.0:
                        next_sound = self.workflow.ffmpeg_audio_processor.audio_cut_fade(next_sound, 0.0, 3.0)
            
            audio_list = []
            if previous_sound:
                scenario["previous_sound_duration"] = self.workflow.ffmpeg_audio_processor.get_duration(previous_sound)
                audio_list.append(previous_sound)
            else:
                scenario["previous_sound_duration"] = 0.0
            if sound_path:
                audio_list.append(sound_path)
            if next_sound:
                scenario["next_sound_duration"] = self.workflow.ffmpeg_audio_processor.get_duration(next_sound)
                audio_list.append(next_sound)
            else:
                scenario["next_sound_duration"] = 0.0

            sound_path = self.workflow.ffmpeg_audio_processor.concat_audios(audio_list)

        self.workflow.rebuild_scenario_video(scenario, image_typ, animate_mode, image_path, image_last_path, sound_path, action_path, wan_prompt)
        self.workflow.save_scenarios_to_json()


    def regenerate_video(self, track):
        """打开 WAN 提示词编辑对话框并生成主轨道视频"""
        if track == None:
            track = self.selected_second_track

        scenario = self.get_current_scenario()
        previous_scenario = self.get_previous_scenario()
        next_scenario = self.get_next_scenario()
        
        # 定义生成视频的回调函数
        def generate_callback(wan_prompt):
            # 保存提示词
            scenario[track+"_prompt"] = wan_prompt
            # 使用编辑后的 prompt 生成视频
            self.generate_video(scenario, previous_scenario, next_scenario, track)
            # 监控已集成到后台定时器中，无需单独调用 trace_scenario_wan_video
            # 后台检查会自动开始监控有 clip_animation 的场景
            self.workflow.save_scenarios_to_json()
            self.refresh_gui_scenarios()
        
        # 显示编辑对话框
        show_wan_prompt_editor(self, self.workflow, generate_callback, scenario, track)
 

    def regenerate_audio(self):
        """音频重生"""
        scenario = self.get_current_scenario()
        t, mix_audio = self.workflow.regenerate_audio_item(scenario, 0, self.workflow.language)

        olda, clip_audio = self.workflow.refresh_scenario_media(scenario, "clip_audio", ".wav", mix_audio)

        clip_video = get_file_path(scenario, "clip")
        if clip_video:
            clip_video = self.workflow.ffmpeg_processor.add_audio_to_video(clip_video, clip_audio)
            oldv, clip_video = self.workflow.refresh_scenario_media(scenario, "clip", ".mp4", clip_video)

        self.refresh_gui_scenarios()


    def promo_load_story_content(self):
        """加载沉浸故事内容到文本框"""
        try:
            file_path = config.get_project_path(self.get_pid()) + "/short.json"

            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.promo_story_json_widget.delete(1.0, tk.END)
                self.promo_story_json_widget.insert(1.0, content)
                print(f"✅ 已加载故事内容: {file_path}")
            else:
                self.promo_story_json_widget.delete(1.0, tk.END)
                self.promo_story_json_widget.insert(1.0, "[]")  # 空的JSON数组
                print(f"ℹ️ 未找到故事文件，已加载空JSON: {file_path}")
        except Exception as e:
            self.promo_story_json_widget.delete(1.0, tk.END)
            self.promo_story_json_widget.insert(1.0, f"加载失败: {str(e)}")
            print(f"❌ 加载故事内容失败: {str(e)}")


    def promo_on_regenerate_dialog(self):
        """重新生成沉浸故事对话JSON"""
        # 在后台线程中重新生成
        def regenerate_task():
            try:
                male_actor = self.promo_actor_male_number.get()
                if male_actor == "0":
                    male_actor = ""
                else:
                    male_actor = f"There are {self.promo_actor_male_number.get()} male-actors in the story conversation"

                female_actor = self.promo_actor_female_number.get()
                if female_actor == "0":
                    female_actor = ""
                else:
                    female_actor = f"There are {self.promo_actor_female_number.get()} female-actors in the story conversation"

                format_args = config.SHORT_STORY_PROMPT.get("format_args", {}).copy()  # 复制预设参数
                format_args.update({  # 添加运行时变量
                    "narrator": f"Narrator is {self.promo_actor_narrator.get()}",
                    "actor_male": male_actor,
                    "actor_female": female_actor,
                    "language": self.shared_language.cget('text')
                })
                
                # 使用合并后的参数格式化system_prompt
                formatted_system_prompt = config.SHORT_STORY_PROMPT["system_prompt"].format(**format_args)
                print("🤖 系统提示:")
                print(formatted_system_prompt)

                formatted_user_prompt = self.workflow.transcriber.fetch_text_from_json(config.get_project_path(self.get_pid()) + "/main.srt.json")
                print("🤖 用户提示:")
                print(formatted_user_prompt)

                # 调用generate_immersive_story，使用用户输入的故事内容和格式化后的prompt
                result = self.workflow.summarizer.generate_json_summary(
                    system_prompt = formatted_system_prompt,
                    user_prompt = formatted_user_prompt,
                    output_path = config.get_project_path(self.get_pid()) + "/short.json"
                )
                    
                if result:
                    self.root.after(0, lambda: self.promo_load_story_content())
                    self.root.after(0, lambda: messagebox.showinfo("成功", "重新生成完成！"))

            except Exception as e:
                error_msg = f"重新生成失败: {str(e)}"
                self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
        
        import threading
        thread = threading.Thread(target=regenerate_task)
        thread.daemon = True
        thread.start()


    def promo_on_generate_audio(self):
        """生成沉浸故事音频"""
        try:
            # 保存当前编辑的内容
            content = self.promo_story_json_widget.get(1.0, tk.END).strip()
            if not content:
                messagebox.showerror("错误", "沉浸故事内容不能为空")
                return

            # Use current project path or create temp path
            story_path = config.get_project_path(self.get_pid()) + "/short.json"
            audio_path = config.get_media_path(self.get_pid()) + "/short.wav"

            with open(story_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 验证JSON格式
            try:
                import json
                json.loads(content)
            except json.JSONDecodeError as e:
                messagebox.showerror("错误", f"JSON格式错误: {str(e)}")
                return
            
            # Log the audio generation task
            self.log_to_output(self.promo_output, f"🎵 开始生成故事音频...")
            self.log_to_output(self.promo_output, f"📁 故事文件: {story_path}")
            self.log_to_output(self.promo_output, f"🎧 音频文件: {audio_path}")

            # 在后台线程中生成音频
            def generate_audio_task():
                try:
                    duration = float(self.promo_duration_entry.get().strip())
                    result = self.workflow.create_story_audio(story_path, audio_path, duration)
                    if result:
                        self.root.after(0, lambda: messagebox.showinfo("成功", f"宣传故事音频生成完成！\n文件: {result}"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("错误", "音频生成失败"))
                except Exception as e:
                    error_msg = f"生成音频失败: {str(e)}"
                    self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            
            import threading
            thread = threading.Thread(target=generate_audio_task)
            thread.daemon = True
            thread.start()
                
        except Exception as e:
            error_msg = f"生成音频失败: {str(e)}"
            print(f"❌ {error_msg}")
            self.log_to_output(self.promo_output, f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)

    def promo_save_story_json_content(self):
        """保存story_json_widget的内容到对应的文件"""
        try:
            # 获取JSON内容
            json_content = self.promo_story_json_widget.get(1.0, tk.END).strip()
            
            if not json_content:
                messagebox.showwarning("警告", "JSON内容为空，无法保存")
                return
            
            # 验证JSON格式
            try:
                import json
                json.loads(json_content)
            except json.JSONDecodeError as e:
                messagebox.showerror("错误", f"JSON格式错误: {str(e)}")
                return
            
            # 构建文件路径
            file_path = config.get_project_path(self.get_pid()) + "/short.json"
            
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(json_content)
            
            print(f"✅ 已保存JSON内容到: {file_path}")
            self.log_to_output(self.promo_output, f"✅ JSON内容已保存到: {os.path.basename(file_path)}")
            messagebox.showinfo("成功", f"JSON内容已保存到:\n{os.path.basename(file_path)}")
            
        except Exception as e:
            error_msg = f"保存JSON内容失败: {str(e)}"
            print(f"❌ {error_msg}")
            self.log_to_output(self.promo_output, f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)

    def promo_undo_action(self, event=None):
        """Perform undo operation on promo story editor"""
        try:
            self.promo_story_json_widget.edit_undo()
        except tk.TclError:
            pass  # No more undo operations available
        return "break"  # Prevent default handling

    def promo_redo_action(self, event=None):
        """Perform redo operation on promo story editor"""
        try:
            self.promo_story_json_widget.edit_redo()
        except tk.TclError:
            pass  # No more redo operations available
        return "break"  # Prevent default handling


    def update_scenario_buttons_state(self):
        """更新场景插入按钮的状态"""
        current_scenario = self.get_current_scenario()
        
        # 更新前插按钮状态
        if not current_scenario or self.workflow.first_scenario_of_story(current_scenario):
            self.insert_scenario_button.config(state="normal")
        else:
            self.insert_scenario_button.config(state="disabled")
        
        # 更新后插按钮状态
        if current_scenario and self.workflow.last_scenario_of_story(current_scenario):
            self.append_scenario_button.config(state="normal")
        else:
            self.append_scenario_button.config(state="disabled")







def main():
    root = TkinterDnD.Tk()

    app = WorkflowGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()

