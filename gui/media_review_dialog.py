import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os, time, threading
import subprocess
import tempfile
import copy  # 添加 copy 模块导入
from PIL import Image, ImageTk
from utility.file_util import get_file_path, safe_remove, safe_file
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.ffmpeg_processor import FfmpegProcessor
from utility.audio_transcriber import AudioTranscriber
import config
from utility.llm_api import LLMApi
import json
from utility.file_util import is_audio_file, is_video_file, is_image_file

# 尝试导入拖放支持
try:
    from tkinterdnd2 import DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    print("警告: tkinterdnd2 不可用，拖放功能将被禁用")

# Audio recording imports
try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    RECORDING_AVAILABLE = True
except ImportError:
    RECORDING_AVAILABLE = False
    print("警告: sounddevice 或 soundfile 不可用，录音功能将被禁用")

# Video playback imports
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("警告: cv2 不可用，视频播放功能将被禁用")


# Audio playback imports
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("警告: pygame 不可用，音频播放功能将被禁用")


class AVReviewDialog:
    """Dialog for reviewing and configuring audio replacement with drag-and-drop support"""
    
    def __init__(self, parent, av_path, current_scenario, previous_scenario, next_scenario, media_type, replace_media_audio, initial_start_time, initial_end_time):
        self.parent = parent
        self.current_scenario = current_scenario
        self.previous_scenario = previous_scenario
        self.next_scenario = next_scenario
        self.language = parent.workflow.language
        self.pid = parent.workflow.pid
        self.workflow = parent.workflow
        # Get video dimensions from workflow's ffmpeg_processor
        video_width = self.workflow.ffmpeg_processor.width
        video_height = self.workflow.ffmpeg_processor.height
        self.transcriber = AudioTranscriber(self.workflow, model_size="small", device="cuda")
        self.summarizer = LLMApi(model=LLMApi.GEMINI_2_0_FLASH)

        self.media_type_names = {
            "clip": "场景媒体 (clip)",
            "one": "第一轨道 (one)",
            "second": "第二轨道 (second)",
            "zero": "背景轨道 (zero)"
        }

        # 媒体类型选择 ("clip", "second", "zero")
        self.media_type = media_type
        self.replace_media_audio = replace_media_audio
        
        # 媒体字段名映射
        if media_type == "clip":
            self.video_field = "clip"
            self.audio_field = "clip_audio"
            self.image_field = "clip_image"
        elif media_type == "second":
            self.video_field = "second"
            self.audio_field = "second_audio"
            self.image_field = "second_image"
        elif media_type == "zero":
            self.video_field = "zero"
            self.audio_field = "zero_audio"
            self.image_field = "zero_image"
        elif media_type == "one":
            self.video_field = "one"
            self.audio_field = "one_audio"
            self.image_field = "one_image"
        # Initialize source paths
        self.source_audio_path = get_file_path(self.current_scenario, self.audio_field)
        self.source_video_path = get_file_path(self.current_scenario, self.video_field)
        self.source_image_path = get_file_path(self.current_scenario, self.image_field)
        
        self.transcribe_way = "single"
        
        # 新增拖放媒体
        self.animation_choice = 1

        # only keep "content", "speaker", "story_expression", "mood", "era_time" fields of each element
        #self.audio_json = [{"content": item["content"], "speaker": item["speaker"], "story_expression": item["story_expression"], "mood": item["mood"]} for item in [self.current_scenario]]
        self.audio_json = [self.current_scenario]
        self.audio_regenerated = False

        self.current_playback_time = 0.0
        self.av_playing = False
        self.av_paused = False
        self.playback_start_time = None  # Time when playback started
        self.pause_accumulated_time = 0.0  # Total time played before pausing

        self.start_time = initial_start_time if initial_start_time else 0.0
        if initial_end_time:
            self.end_time = initial_end_time
        elif replace_media_audio=="replace" or replace_media_audio=="trim" or is_image_file(av_path):
            self.end_time = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
        elif is_audio_file(av_path):
            self.end_time = self.workflow.ffmpeg_audio_processor.get_duration(av_path)
        else:
            self.end_time = self.workflow.ffmpeg_processor.get_duration(av_path)

        self.result = None  # Will store the result when dialog is closed
        
        # Recording state variables
        self.recording = False
        self.recorded_audio = None
        self.recording_thread = None

        # Initialize video-specific states if in video mode
        self.av_playing = False
        self.video_cap = None
        self.video_after_id = None
        # Keep a list of image references to prevent garbage collection
        self.image_references = []
        
        # Crop selection variables
        self.crop_start_x = 0
        self.crop_start_y = 0
        self.crop_width = None  # None means use full width
        self.crop_height = None  # None means use full height
        self.selection_rect = None  # Canvas rectangle ID for selection
        self.selecting = False  # Whether user is currently selecting
        self.selection_start_x = 0
        self.selection_start_y = 0
        self.video_original_width = None
        self.video_original_height = None
        
        self.create_dialog()

        self.handle_new_media(av_path)
        # Load video first frame after dialog is fully created
        self.dialog.after(100, self.init_load)


    def init_load(self):
        try:
            self.audio_json_text.delete(1.0, tk.END)
            self.audio_json_text.insert(1.0, json.dumps(self.audio_json, indent=2, ensure_ascii=False))

            # Draw simple waveform representation
            self.draw_waveform_placeholder()
            
            self.display_image_on_canvas()
            # 加载当前场景的图片
            self.load_video_first_frame()
        except:
            print("error: audio_json is not valid json")


    def update_dialog_title(self, transcribe_audio):
        self.transcribe_way = transcribe_audio
        self.dialog.title( f"{self.media_type_names.get(self.media_type)} - {self.transcribe_way}" )


    def create_dialog(self):
        """Create the review dialog window"""
        self.dialog = tk.Toplevel(self.parent.root)
        
        # 根据媒体类型显示标题
        self.update_dialog_title("none")

        self.dialog.geometry("1800x1000")
        self.dialog.resizable(True, True)
        self.dialog.transient(self.parent.root)
        self.dialog.grab_set()
        
        # Main container
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Media info section
        info_frame = ttk.LabelFrame(main_frame, text="", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Media info row
        info_row = ttk.Frame(info_frame)
        info_row.pack(fill=tk.X, pady=2)
        
        ttk.Label(info_row, text=f"视频时长: { (self.end_time-self.start_time):.2f}秒").pack(side=tk.LEFT)
        ttk.Separator(info_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        if self.source_video_path:
            if self.workflow.ffmpeg_processor.has_audio_stream(self.source_video_path):
                audio_status = "有音频"
                audio_color = "green"
            else:
                audio_status = "无音频"
                audio_color = "red"
            audio_label = ttk.Label(info_row, text=f"音频状态: {audio_status}", foreground=audio_color)
            audio_label.pack(side=tk.LEFT)
            ttk.Separator(info_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)

        av_path = self.source_video_path if self.source_video_path else self.source_audio_path
        ttk.Label(info_row, text=f"源媒体: {av_path}").pack(side=tk.LEFT)
        
        # Media visualization section - 三栏布局：视频 | 图片 | 音频
        media_container = ttk.Frame(main_frame)
        media_container.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 左栏：视频预览 + 拖放
        video_frame = ttk.LabelFrame(media_container, text="视频预览 (可拖放视频文件)", padding=10)
        video_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Video preview canvas (支持拖放)
        self.preview_canvas = tk.Canvas(video_frame, bg='black', height=300, highlightthickness=2, highlightbackground='blue')
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        if DND_AVAILABLE:
            self.preview_canvas.drop_target_register(DND_FILES)
            self.preview_canvas.dnd_bind('<<Drop>>', self.on_video_dnd_drop)
        
        # Bind mouse events for crop selection
        self.preview_canvas.bind("<Button-1>", self.on_canvas_click)
        self.preview_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
        # Add crop controls below video preview
        crop_control_frame = ttk.Frame(video_frame)
        crop_control_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(crop_control_frame, text="裁剪区域:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(crop_control_frame, text="X:").pack(side=tk.LEFT, padx=(0, 2))
        self.crop_x_var = tk.IntVar(value=0)
        ttk.Spinbox(crop_control_frame, from_=0, to=9999, textvariable=self.crop_x_var, width=8, command=self.on_crop_params_changed).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(crop_control_frame, text="Y:").pack(side=tk.LEFT, padx=(0, 2))
        self.crop_y_var = tk.IntVar(value=0)
        ttk.Spinbox(crop_control_frame, from_=0, to=9999, textvariable=self.crop_y_var, width=8, command=self.on_crop_params_changed).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(crop_control_frame, text="宽度:").pack(side=tk.LEFT, padx=(0, 2))
        self.crop_width_var = tk.IntVar(value=0)  # 0 means auto
        crop_width_spinbox = ttk.Spinbox(crop_control_frame, from_=0, to=9999, textvariable=self.crop_width_var, width=8, command=self.on_crop_params_changed)
        crop_width_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(crop_control_frame, text="(0=自动)").pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(crop_control_frame, text="清除选择", command=self.clear_crop_selection).pack(side=tk.LEFT, padx=(5, 0))
        
        # 中栏：图片显示 + 拖放
        image_frame = ttk.LabelFrame(media_container, text="图片 (可拖放图片文件)", padding=10)
        image_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # Image canvas (支持拖放)
        self.image_canvas = tk.Canvas(image_frame, bg='gray20', height=300, highlightthickness=2, highlightbackground='green')
        self.image_canvas.pack(fill=tk.BOTH, expand=True)
        if DND_AVAILABLE:
            self.image_canvas.drop_target_register(DND_FILES)
            self.image_canvas.dnd_bind('<<Drop>>', self.on_image_dnd_drop)
        
        # 动画选择
        anim_frame = ttk.Frame(image_frame)
        anim_frame.pack(fill=tk.X, pady=2)
        ttk.Label(anim_frame, text="动画:").pack(side=tk.LEFT, padx=2)
        
        self.animation_var = tk.IntVar(value=4)
        for value, text in [(1, "静止"), (2, "左"), (3, "右"), (4, "动画")]:
            ttk.Radiobutton(anim_frame, text=text, variable=self.animation_var, value=value).pack(side=tk.LEFT, padx=2)

        # 绑定 animation_var 变化事件
        self.animation_var.trace('w', self.on_animation_changed)
        
        # 右栏：音频波形 + 拖放
        waveform_frame = ttk.LabelFrame(media_container, text="音频波形 (可拖放音频文件)", padding=10)
        waveform_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Waveform canvas (支持拖放)
        self.waveform_canvas = tk.Canvas(waveform_frame, bg='black', height=300, highlightthickness=2, highlightbackground='orange')
        self.waveform_canvas.pack(fill=tk.BOTH, expand=True)
        if DND_AVAILABLE:
            self.waveform_canvas.drop_target_register(DND_FILES)
            self.waveform_canvas.dnd_bind('<<Drop>>', self.on_audio_dnd_drop)
        
        # Media controls (placed below the media visualization)
        control_container = ttk.Frame(main_frame)
        control_container.pack(fill=tk.X, pady=(0, 10))
        
        # Media controls
        control_frame = ttk.Frame(control_container)
        control_frame.pack(fill=tk.X, pady=5)
        
        self.play_button = ttk.Button(control_frame, text="▶ 播放", command=self.toggle_playback)
        self.play_button.pack(side=tk.LEFT, padx=15)
        
        self.stop_button = ttk.Button(control_frame, text="⏹ 停止", command=self.stop_playback)
        self.stop_button.pack(side=tk.LEFT, padx=15)

        separator = ttk.Separator(control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=15)

        ttk.Button(control_frame, text="跳转开始", command=self.jump_to_start).pack(side=tk.LEFT, padx=15)
        ttk.Button(control_frame, text="播放选定", command=self.play_selected_range).pack(side=tk.LEFT, padx=15)
        
        separator = ttk.Separator(control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=15)

        self.play_time_label = ttk.Label(control_frame, text="0.00 / 0.00", foreground="blue")
        self.play_time_label.pack(side=tk.LEFT, padx=15)

        separator = ttk.Separator(control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=15)

        ttk.Label(control_frame, text="开始(秒):").pack(side=tk.LEFT, padx=(0, 5))
        self.start_time_var = tk.DoubleVar(value=self.start_time)
        max_duration = self.workflow.ffmpeg_processor.get_duration(self.source_video_path) if self.source_video_path else self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
        start_spinbox = ttk.Spinbox(control_frame, from_=0, to=max_duration, 
                                   textvariable=self.start_time_var, increment=0.1, width=8)
        start_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="设为当前", command=self.set_start_to_current).pack(side=tk.LEFT, padx=(0, 10))
        
        # 分隔符
        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        # 结束时间组
        ttk.Label(control_frame, text="结束时间 (秒):").pack(side=tk.LEFT, padx=(5, 5))
        self.end_time_var = tk.DoubleVar(value=self.end_time)
        end_spinbox = ttk.Spinbox(control_frame, from_=0, to=max_duration, 
                                 textvariable=self.end_time_var, increment=0.1, width=8)
        end_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="设为当前", command=self.set_end_to_current).pack(side=tk.LEFT)
        
        # 分隔符
        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)

        self.selected_duration_label = ttk.Label(control_frame, text="", foreground="blue")
        self.selected_duration_label.pack(side=tk.LEFT)

        # 分隔符
        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        # add a button to let user record the audio from microphone, then put it as source_audio_path, then transcribe it, set self.regenerate_audio to True
        ttk.Button(control_frame, text="录音", command=self.record_audio).pack(side=tk.LEFT, padx=(0, 10))

        # Initialize play time display
        self.update_play_time_display()
        
        # Bind changes to update duration display
        self.start_time_var.trace('w', self.update_duration_display)
        self.end_time_var.trace('w', self.update_duration_display)
        self.update_duration_display()
        
        # Text editors section for JSON data
        editors_frame = ttk.LabelFrame(main_frame, text="JSON编辑器", padding=10)
        editors_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create horizontal frame for side-by-side editors
        editors_container = ttk.Frame(editors_frame)
        editors_container.pack(fill=tk.BOTH, expand=True)
        
        # Editor 1: Fresh JSON (left side)
        fresh_frame = ttk.Frame(editors_container)
        fresh_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        fresh_label = ttk.Label(fresh_frame, text="Fresh JSON")
        fresh_label.pack(anchor="w", pady=(0, 5))
        
        # Fresh JSON text editor with scrollbar
        fresh_text_frame = ttk.Frame(fresh_frame)
        fresh_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.fresh_json_text = tk.Text(fresh_text_frame, wrap=tk.WORD, width=40, height=15)
        fresh_scrollbar = ttk.Scrollbar(fresh_text_frame, orient="vertical", command=self.fresh_json_text.yview)
        self.fresh_json_text.configure(yscrollcommand=fresh_scrollbar.set)
        
        self.fresh_json_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fresh_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定 Alt+Enter 快捷键到 fresh_json_text
        self.fresh_json_text.bind('<Alt-Return>', self.copy_fresh_to_audio_json)
        
        # Buttons for fresh JSON editor
        fresh_buttons_frame = ttk.Frame(fresh_frame)
        fresh_buttons_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 提示词模板组
        ttk.Label(fresh_buttons_frame, text="模板:").pack(side=tk.LEFT, padx=(0, 5))
        self.prompt_selector = ttk.Combobox(fresh_buttons_frame, values=config.SPEAKING_PROMPTS_LIST, state="readonly", width=25)
        self.prompt_selector.pack(side=tk.LEFT, padx=(0, 10))
        self.prompt_selector.current(0)  # 默认选择第一个

        # 旁白语音组
        ttk.Label(fresh_buttons_frame, text="主持").pack(side=tk.LEFT, padx=(0, 5))
        self.narrators = ttk.Combobox(fresh_buttons_frame, values=config.HOSTS, state="normal", width=30)
        self.narrators.pack(side=tk.LEFT, padx=(0, 10))
        self.narrators.current(0)

        # 旁白语音组
        ttk.Label(fresh_buttons_frame, text="演员").pack(side=tk.LEFT, padx=(0, 5))
        self.actors = ttk.Combobox(fresh_buttons_frame, values=config.ACTORS, state="normal", width=30)
        self.actors.pack(side=tk.LEFT, padx=(0, 10))
        self.actors.current(0)

        ttk.Label(fresh_buttons_frame, text="补充").pack(side=tk.LEFT, padx=(0, 5))
        self.speaking_addon = ttk.Combobox(fresh_buttons_frame, values=config.SPEAKING_ADDON, state="readonly", width=15)
        self.speaking_addon.pack(side=tk.LEFT, padx=(0, 10))
        self.speaking_addon.current(0)

        ttk.Button(fresh_buttons_frame, text="REMIX JSON", command=self.remix_json).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(fresh_buttons_frame, text="重生音频", command=self.regenerate_audio).pack(side=tk.LEFT)
        
        # Editor 2: Audio JSON (right side)
        audio_frame = ttk.Frame(editors_container)
        audio_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        audio_label = ttk.Label(audio_frame, text="Audio JSON")
        audio_label.pack(anchor="w", pady=(0, 5))
        
        # Audio JSON text editor with scrollbar
        audio_text_frame = ttk.Frame(audio_frame)
        audio_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.audio_json_text = tk.Text(audio_text_frame, wrap=tk.WORD, width=40, height=15)
        audio_scrollbar = ttk.Scrollbar(audio_text_frame, orient="vertical", command=self.audio_json_text.yview)
        self.audio_json_text.configure(yscrollcommand=audio_scrollbar.set)
        
        self.audio_json_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        audio_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Button for audio JSON editor
        audio_buttons_frame = ttk.Frame(audio_frame)
        audio_buttons_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(audio_buttons_frame, text="渐进", command=self.audio_fade).pack(side=tk.LEFT)
        ttk.Button(audio_buttons_frame, text="剪音视", command=self.trim_media).pack(side=tk.LEFT)
        ttk.Button(audio_buttons_frame, text="剪视频", command=self.trim_video).pack(side=tk.LEFT)
        ttk.Button(audio_buttons_frame, text="单转录", command=self.trim_transcribe_single).pack(side=tk.LEFT)
        ttk.Button(audio_buttons_frame, text="多转录", command=self.trim_transcribe_multiple).pack(side=tk.LEFT)
        
        # Audio transcription options section
        transcribe_frame = ttk.LabelFrame(main_frame, text="音频转录选项", padding=10)
        transcribe_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Video-specific controls (only show in video mode)
        self.track_mode = tk.IntVar(value=1)  # Default to mode 2
        if self.source_video_path:
            video_control_frame = ttk.LabelFrame(main_frame, text="处理模式", padding=10)
            video_control_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
            
            ttk.Radiobutton(video_control_frame, text="正常", variable=self.track_mode, value=1).pack(side=tk.LEFT, padx=5)
            ttk.Radiobutton(video_control_frame, text="渐入", variable=self.track_mode, value=2).pack(side=tk.LEFT, padx=5)
            ttk.Radiobutton(video_control_frame, text="渐出", variable=self.track_mode, value=3).pack(side=tk.LEFT, padx=5)
            ttk.Radiobutton(video_control_frame, text="出入", variable=self.track_mode, value=4).pack(side=tk.LEFT, padx=5)

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="确认替换", command=self.confirm_replacement).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="取消", command=self.cancel).pack(side=tk.RIGHT)
        
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        

    def draw_waveform_placeholder(self):
        """Draw a simple waveform placeholder"""
        if not self.source_audio_path:
            return

        width = 750
        height = 180
        center_y = height // 2
        
        # Clear canvas
        self.waveform_canvas.delete("all")
        
        # Draw simple waveform simulation
        import math
        for x in range(0, width, 2):
            # Create random-looking waveform
            amplitude = 50 * math.sin(x * 0.05) * (0.5 + 0.5 * math.sin(x * 0.01))
            y1 = center_y - amplitude
            y2 = center_y + amplitude
            self.waveform_canvas.create_line(x, y1, x, y2, fill="green", width=1)
        
        # Draw time markers  
        display_duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
        if display_duration > 0:
            for i in range(0, int(display_duration) + 1, max(1, int(display_duration) // 10)):
                x = (i / display_duration) * width
                self.waveform_canvas.create_line(x, 0, x, height, fill="gray", width=1)
                self.waveform_canvas.create_text(x, height - 10, text=f"{i}s", fill="white", anchor="n")
    

    def update_duration_display(self, *args):
        """Update the selected duration display"""
        if not self.source_audio_path:
            return
        try:
            start = self.start_time_var.get()
            end = self.end_time_var.get()
            if end > start:
                duration = end - start
                self.selected_duration_label.config(text=f"{duration:.2f}秒")

                # Update waveform selection visualization
                self.waveform_canvas.delete("selection")
                # Draw selection overlay
                width = self.waveform_canvas.winfo_width()
                height = self.waveform_canvas.winfo_height()
                
                display_duration = self.workflow.ffmpeg_processor.get_duration(self.source_video_path) if self.source_video_path else self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
                if display_duration > 0:
                    start_x = (start / display_duration) * width
                    end_x = (end / display_duration) * width
                else:
                    start_x = end_x = 0
                # Draw selection rectangle
                self.waveform_canvas.create_rectangle(start_x, 0, end_x, height, 
                                                    fill="yellow", stipple="gray50", tags="selection")

            else:
                self.selected_duration_label.config(text="无效时间段")
        except:
            self.selected_duration_label.config(text="--")
    

    def update_play_time_display(self):
        """Update the play time display"""
        try:
            current_time = self.current_playback_time
            
            # Get total duration from video or audio
            if self.source_video_path:
                total_duration = self.workflow.ffmpeg_processor.get_duration(self.source_video_path)
            elif self.source_audio_path:
                total_duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
            else:
                total_duration = 0.0
            
            # Ensure we have valid values
            if total_duration is None or total_duration <= 0:
                total_duration = 0.0
            if current_time is None or current_time < 0:
                current_time = 0.0
                
            current_str = f"{current_time:.2f}"
            total_str = f"{total_duration:.2f}"
            
            self.play_time_label.config(text=f"{current_str} / {total_str}")
            
        except Exception as e:
            print(f"⚠️ 更新时间显示失败: {e}")
            self.play_time_label.config(text="0.00 / 0.00")
    

    def set_start_to_current(self):
        """Set start time to current playback position"""
        self.start_time_var.set(self.current_playback_time)
        self.update_play_time_display()
    

    def set_end_to_current(self):
        """Set end time to current playback position"""
        self.end_time_var.set(self.current_playback_time)
        self.update_play_time_display()
    

    def audio_fade(self):
        """Audio fade"""
        if self.source_audio_path:
            self.source_audio_path = self.workflow.ffmpeg_audio_processor.audio_change(self.source_audio_path, 1.5, 1.5, 1.0, 0.0)
        if self.source_video_path:
            self.source_video_path = self.workflow.ffmpeg_processor.add_audio_to_video(self.source_video_path, self.source_audio_path)


    def trim_video(self):
        self.update_dialog_title("none")

        video_path = safe_file(self.source_video_path)
        audio_path = safe_file(self.source_audio_path)
        if not audio_path or not video_path:
            return

        start_time = float(self.start_time_var.get())
        end_time = float(self.end_time_var.get())
        duration = self.workflow.ffmpeg_processor.get_duration(video_path)
        
        if end_time <= start_time:
            messagebox.showerror("错误", "结束时间必须大于开始时间")
            return
        
        if start_time < 0 or end_time > duration:
            messagebox.showerror("错误", "时间选择超出音频范围")
            return

        if start_time > 0 or end_time != duration:
            # Get crop parameters if selection exists
            crop_width = self.crop_width if self.crop_width else None
            crop_height = self.crop_height if self.crop_height else None
            
            video_path = self.workflow.ffmpeg_processor.resize_video( video_path, crop_width, start_time, end_time, 
                                                                      volume=1.0, start_x=self.crop_start_x, start_y=self.crop_start_y )
            self.source_video_path = self.workflow.ffmpeg_processor.add_audio_to_video(video_path, audio_path, True)



    def trim_media(self):
        self.update_dialog_title("none")

        """Trim media"""
        """Trim and transcribe audio"""
        video_path = safe_file(self.source_video_path)
        audio_path = safe_file(self.source_audio_path)
        if not audio_path or not video_path:
            return

        start_time = float(self.start_time_var.get())
        end_time = float(self.end_time_var.get())
        duration = self.workflow.ffmpeg_processor.get_duration(video_path) if video_path else self.workflow.ffmpeg_audio_processor.get_duration(audio_path)
        
        if end_time <= start_time:
            messagebox.showerror("错误", "结束时间必须大于开始时间")
            return
        
        if start_time < 0 or end_time > duration:
            messagebox.showerror("错误", "时间选择超出音频范围")
            return
        
        if start_time > 0 or end_time != duration:
            self.source_audio_path = self.workflow.ffmpeg_audio_processor.audio_cut_fade( audio_path, start_time, end_time-start_time )
            
            # Get crop parameters if selection exists
            crop_width = self.crop_width if self.crop_width else None
            crop_height = self.crop_height if self.crop_height else None
            
            self.source_video_path = self.workflow.ffmpeg_processor.resize_video( video_path, crop_width, start_time, end_time, 
                                                                                  volume=1.0, start_x=self.crop_start_x, start_y=self.crop_start_y )


    def trim_transcribe_single(self):
        self.trim_media()
        self.update_dialog_title("single")
        if not self.audio_regenerated or self.media_type=="clip":
            self._transcribe_recorded_audio()


    def trim_transcribe_multiple(self):
        self.trim_media()
        self.update_dialog_title("multiple")
        if not self.audio_regenerated and self.media_type=="clip":
            self._transcribe_recorded_audio()


    def _transcribe_recorded_audio(self):
        """转录录制的音频"""
        if not self.source_audio_path:
            return
        
        print("🔄 开始转录录音...")
        
        # 使用音频转录器转录
        self.audio_json = self.transcriber.transcribe_with_whisper(
            self.source_audio_path, 
            self.language, 
            10,  # min_sentence_duration
            28   # max_sentence_duration
        )
        
        if self.audio_json:
            try:
                formatted_json = json.dumps(self.audio_json, indent=2, ensure_ascii=False)
                self.fresh_json_text.delete(1.0, tk.END)
                self.fresh_json_text.insert(1.0, formatted_json)
                self.audio_json_text.delete(1.0, tk.END)
                self.audio_json_text.insert(1.0, formatted_json)
            except Exception as e:
                print(f"JSON格式错误: {str(e)}")
        else:
            print("⚠️ 录音转录失败")


    def toggle_playback(self):
        """Toggle media playback (audio or video+audio)"""
        if not self.av_playing:
            self.start_playback()
        else:
            self.pause_playback()


    def start_playback(self):
        self.av_playing = True
        self.av_paused = False
        self.play_button.config(text="⏸ 暂停")
        
        if self.source_video_path:
            # 如果视频捕获对象不存在，或者需要从头开始播放，就重新创建
            if self.video_cap is None or self.current_playback_time == 0.0:
                # 释放旧的视频捕获对象（如果存在）
                if self.video_cap:
                    self.video_cap.release()
                # 创建新的视频捕获对象
                self.video_cap = cv2.VideoCapture(self.source_video_path)
                if not self.video_cap.isOpened():
                    print(f"❌ 无法打开视频文件: {self.source_video_path}")
                    self.av_playing = False
                    self.play_button.config(text="▶ 播放")
                    return
                print(f"✓ 已加载视频: {os.path.basename(self.source_video_path)}")
            
            # 如果需要从指定位置开始播放，设置视频位置
            if self.current_playback_time > 0:
                fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 30
                start_frame = int(self.current_playback_time * fps)
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            
            # Start video frame updates
            self.update_video_frame()
            
        if self.source_audio_path:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(self.source_audio_path)
            pygame.mixer.music.play(start=self.current_playback_time)
            
        # Record the start time for tracking
        self.playback_start_time = time.time()
    
        self.start_time_update_thread()


    def pause_playback(self):
        """Pause audio-only playback"""
        if self.playback_start_time is not None:
            elapsed_since_start = time.time() - self.playback_start_time
            self.pause_accumulated_time += elapsed_since_start
            self.current_playback_time = self.pause_accumulated_time

        self.av_playing = False
        self.play_button.config(text="▶ 播放")
        
        # Cancel video frame updates
        if self.video_after_id:
            self.dialog.after_cancel(self.video_after_id)
            
        # Pause audio BEFORE changing the state
        if self.source_audio_path:
            print("🔄 正在停止音频播放...")
            pygame.mixer.music.stop()
            self.av_paused = True


    def stop_playback(self):
        """Stop media playback (audio or video+audio)"""
        self.av_playing = False
        self.av_paused = False
        self.play_button.config(text="▶ 播放")
        self.current_playback_time = 0.0
        
        # Cancel video frame updates
        if self.source_video_path:
            if self.video_after_id:
                self.dialog.after_cancel(self.video_after_id)
            # Reset video to beginning
            if self.video_cap:
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        if self.source_audio_path:
            pygame.mixer.music.stop()
            print(f"⏹ 音频播放停止")
        
        # Reset playback time tracking
        self.pause_accumulated_time = 0.0
        self.playback_start_time = None
        
        # Update play time display to show 0.00 / total_duration
        self.update_play_time_display()
    

    def remix_json(self):
        refresh_content = self.fresh_json_text.get(1.0, tk.END).strip()
        if not refresh_content or refresh_content.strip() == "":
            return

        # try to format formatted_user_prompt as json , if success, take 'content' field of each elemet, concat together as whole content
        try:
            refresh_json = json.loads(refresh_content)
            refresh_content = " ".join([item["content"] for item in refresh_json])
        except:
            print(f"⚠️ 刷新内容格式化失败")


        previous_scenario_content = self.previous_scenario["content"] if self.previous_scenario and hasattr(self.previous_scenario, "content") else ""
        previous_story_content = self.previous_scenario["story_summary"] if self.previous_scenario and hasattr(self.previous_scenario, "story_summary") else ""

        next_scenario_content = self.next_scenario["content"] if self.next_scenario and hasattr(self.next_scenario, "content") else ""
        next_story_content = self.next_scenario["story_summary"] if self.next_scenario and hasattr(self.next_scenario, "story_summary")  else ""

        prompt_name = self.prompt_selector.get()
        if prompt_name == "Reorganize-Text":
            engaging = ""
            selected_prompt = config.SPEAKING_PROMPTS["Reorganize-Text"]
        elif prompt_name == "Reorganize-Text-with-Previous-Scenario":
            engaging = "[the conversation is following the previous speaking like: " + previous_scenario_content + "]"
            selected_prompt = config.SPEAKING_PROMPTS["Reorganize-Text"]
        elif prompt_name == "Reorganize-Text-with-Previous-Story":
            engaging = "[the conversation is following the previous story : " + previous_story_content + "]"
            selected_prompt = config.SPEAKING_PROMPTS["Reorganize-Text"]
        elif prompt_name == "Reorganize-Text-with-Next-Scenario":
            engaging = "[the conversation will be followed by the next speaking like: " + next_scenario_content + "]"
            selected_prompt = config.SPEAKING_PROMPTS["Reorganize-Text"]
        elif prompt_name == "Reorganize-Text-with-Next-Story":
            engaging = "[the conversation will be followed by the next story : " + next_story_content + "]"
            selected_prompt = config.SPEAKING_PROMPTS["Reorganize-Text"]
        else:
            selected_prompt = config.SPEAKING_PROMPTS[prompt_name]
            engaging = ""

        format_args = selected_prompt.get("format_args", {}).copy()  # 复制预设参数
        format_args.update({
            "speaker_style": f"with {self.narrators.get()} and {self.actors.get()}",
            "language": "Chinese" if self.language == "zh" or self.language == "tw" else "English",
            "engaging": engaging
        })

        formatted_system_prompt = selected_prompt["system_prompt"].format(**format_args)
        print("🤖 系统提示:")
        print(formatted_system_prompt)
        
        # pop up a dialog to show the system prompt, user can edit the system prompt, then click confirm to continue  to self.summarizer.generate_json_summary ..
        system_prompt_dialog = tk.Toplevel(self.dialog)
        system_prompt_dialog.title("系统提示")
        system_prompt_dialog.geometry("600x400")
        system_prompt_dialog.resizable(True, True)
        system_prompt_dialog.transient(self.dialog)
        system_prompt_dialog.grab_set()

        # 添加标签说明
        instruction_label = tk.Label(system_prompt_dialog, text="请编辑系统提示（可修改后点击确认）：")
        instruction_label.pack(pady=(10, 5))

        # 使用Text小部件代替Label，以便用户可以编辑
        system_prompt_text = tk.Text(system_prompt_dialog, wrap=tk.WORD, height=15, width=70)
        system_prompt_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        # 插入当前的系统提示文本
        system_prompt_text.insert(1.0, formatted_system_prompt)

        # 添加滚动条
        scrollbar = tk.Scrollbar(system_prompt_dialog, command=system_prompt_text.yview)
        system_prompt_text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 用于存储用户编辑后的提示
        edited_prompt = [formatted_system_prompt]  # 使用列表以便在闭包中修改

        def confirm_and_close():
            # 获取编辑后的文本
            edited_prompt[0] = system_prompt_text.get(1.0, tk.END).strip()
            system_prompt_dialog.destroy()

        confirm_button = tk.Button(system_prompt_dialog, text="确认", command=confirm_and_close)
        confirm_button.pack(pady=10)

        system_prompt_dialog.wait_window()

        # 使用编辑后的系统提示
        formatted_system_prompt = edited_prompt[0]

        new_scenarios = self.summarizer.llm.generate_json_summary(
            system_prompt=formatted_system_prompt,
            user_prompt=refresh_content,
            expect_list=True
        )

        formatted_json = json.dumps(new_scenarios, indent=2, ensure_ascii=False)
        # clean self.fresh_json_text, then insert formatted_json
        self.fresh_json_text.delete(1.0, tk.END)
        self.fresh_json_text.insert(1.0, formatted_json)
        self.audio_regenerated = False
         

    def copy_fresh_to_audio_json(self, event=None):
        fresh_text = self.fresh_json_text.get(1.0, tk.END).strip()
        # 验证JSON格式
        try:
            self.audio_json = json.loads(fresh_text)
            # JSON格式有效，清空audio_json_text并复制内容
            self.audio_json_text.delete(1.0, tk.END)
            self.audio_json_text.insert(1.0, fresh_text)
        except Exception as e:
            # 其他错误
            messagebox.showerror("错误", f"复制过程中发生错误: {str(e)}")


    def regenerate_audio(self):
        fresh_text = self.fresh_json_text.get(1.0, tk.END).strip()
        # check if fresh_json_text is valid json
        fresh_json = None
        try:
            fresh_json = json.loads(fresh_text)
        except:
            messagebox.showerror("错误", "Fresh JSON格式不正确")
            return

        fresh_json, self.source_audio_path = self.parent.workflow.regenerate_audio(fresh_json, self.language)
        if self.source_video_path:
            duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
            self.source_video_path = self.workflow.ffmpeg_processor.adjust_video_to_duration( self.source_video_path, duration )

        self.audio_json = fresh_json
        audio_text = json.dumps(fresh_json, indent=2, ensure_ascii=False)

        self.audio_json_text.delete(1.0, tk.END)
        self.audio_json_text.insert(1.0, audio_text)

        self.fresh_json_text.delete(1.0, tk.END)
        self.fresh_json_text.insert(1.0, audio_text)

        self.audio_regenerated = True
        self.update_dialog_title("multiple")


    def record_audio(self):
        """录音功能：从麦克风录音并设置为源音频"""
        if not RECORDING_AVAILABLE:
            messagebox.showerror("错误", "录音功能不可用。请安装 sounddevice 和 soundfile 库。")
            return
        
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()


    def start_recording(self):
        """开始录音"""
        try:
            # 创建录音对话框
            self.recording_dialog = tk.Toplevel(self.dialog)
            self.recording_dialog.title("录音中...")
            self.recording_dialog.geometry("400x200")
            self.recording_dialog.resizable(False, False)
            self.recording_dialog.transient(self.dialog)
            self.recording_dialog.grab_set()
            
            # 录音对话框布局
            main_frame = ttk.Frame(self.recording_dialog, padding=20)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # 录音状态显示
            self.recording_status_label = ttk.Label(main_frame, text="正在录音...", 
                                                  font=("Arial", 14), foreground="red")
            self.recording_status_label.pack(pady=10)
            
            # 录音时长显示
            self.recording_time_label = ttk.Label(main_frame, text="00:00", 
                                                font=("Arial", 12))
            self.recording_time_label.pack(pady=5)
            
            # 停止录音按钮
            ttk.Button(main_frame, text="停止录音", command=self.stop_recording).pack(pady=20)
            
            # 录音参数
            self.sample_rate = 44100  # 采样率
            self.channels = 1  # 单声道
            self.recording = True
            self.recorded_audio = []
            self.recording_start_time = time.time()
            
            # 开始录音线程
            self.recording_thread = threading.Thread(target=self._recording_worker, daemon=True)
            self.recording_thread.start()
            
            # 开始时间更新线程
            self._update_recording_time()
            
            print("🎤 开始录音...")
            
        except Exception as e:
            messagebox.showerror("错误", f"启动录音失败: {str(e)}")
            self.recording = False


    def _recording_worker(self):
        """录音工作线程"""
        try:
            # 回调函数用于接收音频数据
            def audio_callback(indata, frames, time, status):
                if status:
                    print(f"录音状态: {status}")
                if self.recording:
                    self.recorded_audio.append(indata.copy())
            
            # 开始音频流
            with sd.InputStream(samplerate=self.sample_rate, 
                              channels=self.channels, 
                              callback=audio_callback,
                              dtype='float32'):
                while self.recording:
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"录音线程错误: {e}")
            self.recording = False
            # 在主线程中显示错误
            self.dialog.after(0, lambda: messagebox.showerror("错误", f"录音失败: {str(e)}"))


    def _update_recording_time(self):
        """更新录音时间显示"""
        if self.recording and hasattr(self, 'recording_dialog') and self.recording_dialog.winfo_exists():
            elapsed = time.time() - self.recording_start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            self.recording_time_label.config(text=time_str)
            
            # 每100ms更新一次
            self.recording_dialog.after(100, self._update_recording_time)


    def stop_recording(self):
        """停止录音并保存文件"""
        if not self.recording:
            return
            
        self.recording = False
        
        try:
            # 关闭录音对话框
            if hasattr(self, 'recording_dialog') and self.recording_dialog.winfo_exists():
                self.recording_dialog.destroy()
            
            if not self.recorded_audio:
                messagebox.showwarning("警告", "没有录制到音频数据")
                return
            
            # 合并录音数据
            audio_data = np.concatenate(self.recorded_audio, axis=0)
            
            # 保存录音文件
            recorded_file_path = config.get_temp_file(self.parent.workflow.pid, "wav")
            sf.write(recorded_file_path, audio_data, self.sample_rate)
            
            print(f"✓ 录音保存到: {recorded_file_path}")
            print(f"✓ 录音时长: {len(audio_data) / self.sample_rate:.2f} 秒")
            
            # 设置为源音频路径
            if self.source_audio_path:
                safe_remove(self.source_audio_path)  # 清理之前的音频文件
            
            self.source_audio_path = recorded_file_path
            
            # 更新音频时长和时间选择器
            duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
            self.start_time = 0.0
            self.end_time = duration
            self.start_time_var.set(0.0)
            self.end_time_var.set(duration)
            
            # 更新时间选择器的最大值
            for widget in self.dialog.winfo_children():
                if isinstance(widget, ttk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Spinbox):
                            try:
                                child.configure(to=duration)
                            except:
                                pass
            
            # 重新绘制波形
            self.draw_waveform_placeholder()
            
            # 自动转录录音
            self._transcribe_recorded_audio()
            
            # 设置音频重新生成标志
            self.audio_regenerated = False
            
            messagebox.showinfo("成功", f"录音完成！\n文件保存到: {os.path.basename(recorded_file_path)}\n时长: {duration:.2f} 秒")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存录音失败: {str(e)}")
            print(f"保存录音错误: {e}")


    def confirm_replacement(self):
        """Confirm the media replacement with selected parameters"""
        try:
            # Validate source paths
            audio_path = self.source_audio_path
            video_path = self.source_video_path
            
            if self.track_mode.get() == 2:
                if audio_path:
                    audio_path = self.workflow.ffmpeg_audio_processor.audio_change(audio_path, 1.0, 0.0, 1.0, 0.0)
                if video_path:
                    video_path = self.workflow.ffmpeg_processor.fade_video(video_path, 1.0, 0.0)
            elif self.track_mode.get() == 3:
                if audio_path:
                    audio_path = self.workflow.ffmpeg_audio_processor.audio_change(audio_path, 0.0, 1.0, 1.0, 0.0)
                if video_path:
                    video_path = self.workflow.ffmpeg_processor.fade_video(video_path, 0.0, 1.0)
            elif self.track_mode.get() == 4:
                if audio_path:
                    audio_path = self.workflow.ffmpeg_audio_processor.audio_change(audio_path, 1.0, 1.0, 1.0, 0.0)
                if video_path:
                    video_path = self.workflow.ffmpeg_processor.fade_video(video_path, 1.0, 1.0)

            v = self.current_scenario.get(self.video_field, None)
            a = self.current_scenario.get(self.audio_field, None)
            i = self.current_scenario.get(self.image_field, None)

            if v != video_path:
                self.parent.workflow.refresh_scenario_media(self.current_scenario, self.video_field, ".mp4", video_path, True)
            if a != audio_path:
                self.parent.workflow.refresh_scenario_media(self.current_scenario, self.audio_field, ".wav", audio_path, True)
            if i != self.source_image_path:
                self.parent.workflow.refresh_scenario_media(self.current_scenario, self.image_field, ".webp", self.source_image_path, True)

            self.result = {
                'audio_json': self.audio_json,
                'transcribe_way': self.transcribe_way
            }
            
            self.close_dialog()
            
        except Exception as e:
            messagebox.showerror("错误", f"参数验证失败: {str(e)}")
    

    def cancel(self):
        """Cancel the operation"""
        self.result = {'confirmed': False}
        self.close_dialog()
    

    def close_dialog(self):
        """Close the dialog and cleanup"""
        # Stop recording if in progress
        if self.recording:
            self.recording = False
            if hasattr(self, 'recording_dialog') and self.recording_dialog.winfo_exists():
                self.recording_dialog.destroy()
        
        # Stop all playback and reset states
        self.av_playing = False
        self.av_playing = False
        self.av_paused = False
        self.playback_start_time = None
        self.pause_accumulated_time = 0.0
        # Stop audio
        if self.source_audio_path:
            pygame.mixer.music.stop()
        
        # Cleanup video resources
        if self.source_video_path:
            # Cancel video frame updates
            if self.video_after_id:
                self.dialog.after_cancel(self.video_after_id)
            
            # Release video capture
            if self.video_cap:
                self.video_cap.release()
            
        self.image_references.clear()
        
        # Close dialog
        self.dialog.destroy()
    

    def jump_to_start(self):
        """Jump to the start of selected time range"""
        try:
            start_time = self.start_time_var.get()
            
            if self.source_video_path:
                # Video mode: jump video and stop audio
                if self.video_cap:
                    fps = self.video_cap.get(cv2.CAP_PROP_FPS)
                    start_frame = int(start_time * fps) if fps > 0 else 0
                    self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                    
            # Stop video audio and reset state
            if self.source_audio_path:
                if self.pygame_initialized:
                    pygame.mixer.music.stop()
                
            # Reset time tracking
            self.pause_accumulated_time = start_time
            self.playback_start_time = None
            self.av_paused = False
            
            self.current_playback_time = start_time
            print(f"✓ 跳转到开始位置: {start_time:.2f}秒")
            
            # Update play time display
            self.update_play_time_display()
            
        except Exception as e:
            print(f"⚠️ 跳转失败: {e}")
   
    
    def play_selected_range(self):
        """Play only the selected time range"""
        try:
            # Jump to start first
            self.jump_to_start()
            
            # Start playback based on mode
            if self.source_video_path:
                if not self.av_playing:
                    self.start_video_playback()
            else:
                if not self.av_playing:
                    self.start_playback()
            
            print(f"▶ 开始播放选定范围")
            
        except Exception as e:
            print(f"⚠️ 播放选定范围失败: {e}")


    def start_time_update_thread(self):
        """Start a thread to update playback time"""
        def update_time():
            while self.av_playing and not self.av_paused:
                try:
                    if self.playback_start_time is not None:
                        elapsed_since_start = time.time() - self.playback_start_time
                        self.current_playback_time = self.pause_accumulated_time + elapsed_since_start
                        
                        # Update display in main thread
                        self.dialog.after(0, self.update_play_time_display)
                        
                        # Check if we've reached the end of audio
                        if self.current_playback_time >= self.audio_duration:
                            self.dialog.after(0, self.stop_playback)
                            break
                    
                    time.sleep(0.1)  # Update every 100ms
                except:
                    break
        
        # Start the update thread
        if self.av_playing:
            threading.Thread(target=update_time, daemon=True).start()

    def get_fresh_json_from_editor(self):
        """Get JSON data from fresh JSON editor"""
        import json
        try:
            content = self.fresh_json_text.get(1.0, tk.END).strip()
            if content:
                return json.loads(content)
            return None
        except json.JSONDecodeError as e:
            messagebox.showerror("错误", f"Fresh JSON格式无效: {str(e)}")
            return None


    def get_audio_json_from_editor(self):
        """Get JSON data from audio JSON editor"""
        import json
        try:
            content = self.audio_json_text.get(1.0, tk.END).strip()
            if content:
                return json.loads(content)
            return None
        except json.JSONDecodeError as e:
            messagebox.showerror("错误", f"Audio JSON格式无效: {str(e)}")
            return None
        
    
    def load_video_first_frame(self):
        """Load and display the first frame of the video in preview canvas"""
        if not self.source_video_path:
            return
            
        try:
            # Clear canvas first
            self.preview_canvas.delete("all")
            
            # Open video file
            cap = cv2.VideoCapture(self.source_video_path)
            
            if not cap.isOpened():
                cap.release()
                self.preview_canvas.create_text(
                    self.preview_canvas.winfo_width()//2, 
                    self.preview_canvas.winfo_height()//2,
                    text="无法打开视频文件", fill="white", font=("Arial", 12)
                )
                return
            
            # Get video dimensions
            self.video_original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.video_original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Update crop controls max values
            if self.video_original_width and self.video_original_height:
                # Update spinbox max values
                self._update_crop_spinbox_max()
            
            # Read first frame
            ret, frame = cap.read()
            cap.release()
            
            if ret and frame is not None:
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Get canvas dimensions
                canvas_width = self.preview_canvas.winfo_width()
                canvas_height = self.preview_canvas.winfo_height()
                
                # If canvas is not ready, use default size
                if canvas_width <= 1 or canvas_height <= 1:
                    canvas_width, canvas_height = 640, 360
                
                # Calculate aspect ratio and resize
                height, width = frame_rgb.shape[:2]
                aspect_ratio = width / height
                
                if canvas_width / canvas_height > aspect_ratio:
                    new_height = canvas_height - 20  # Leave some margin
                    new_width = int(new_height * aspect_ratio)
                else:
                    new_width = canvas_width - 20  # Leave some margin
                    new_height = int(new_width / aspect_ratio)
                
                # Resize frame
                frame_resized = cv2.resize(frame_rgb, (new_width, new_height))
                
                # Convert to PIL Image and then to PhotoImage
                pil_image = Image.fromarray(frame_resized)
                self.first_frame_photo = ImageTk.PhotoImage(pil_image)
                
                # Add to image references to prevent garbage collection
                if not hasattr(self, 'image_references'):
                    self.image_references = []
                self.image_references.append(self.first_frame_photo)
                
                # Display the image in canvas center
                self.preview_canvas.create_image(
                    canvas_width//2, canvas_height//2, 
                    image=self.first_frame_photo, anchor=tk.CENTER
                )
                
                # Add helpful text below the frame
                self.preview_canvas.create_text(
                    canvas_width//2, canvas_height//2 + new_height//2 + 20,
                    text="点击 '▶ 播放' 开始播放视频", 
                    fill="white", font=("Arial", 12)
                )
                
                self.preview_canvas.create_text(
                    canvas_width//2, canvas_height//2 + new_height//2 + 40,
                    text="💡 视频第一帧预览", 
                    fill="gray", font=("Arial", 10)
                )
                
            else:
                self.preview_canvas.create_text(
                    self.preview_canvas.winfo_width()//2, 
                    self.preview_canvas.winfo_height()//2,
                    text="无法读取视频第一帧", fill="white", font=("Arial", 12)
                )
                
        except Exception as e:
            print(f"⚠️ 加载视频第一帧失败: {e}")
            self.preview_canvas.create_text(
                self.preview_canvas.winfo_width()//2, 
                self.preview_canvas.winfo_height()//2,
                text=f"加载视频失败: {str(e)}", fill="red", font=("Arial", 10)
            )


    def update_video_frame(self):
        """Update video frame in preview canvas with audio sync"""
        if not self.av_playing or not self.video_cap:
            return
        
        try:
            # Calculate target time based on actual elapsed time (audio sync)
            if self.playback_start_time is not None:
                elapsed_since_start = time.time() - self.playback_start_time
                target_time = self.pause_accumulated_time + elapsed_since_start
            else:
                target_time = self.current_playback_time
            
            fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 30  # Default to 30 if FPS is unknown
            target_frame = int(target_time * fps)
            current_frame = int(self.video_cap.get(cv2.CAP_PROP_POS_FRAMES))
            
            # Calculate frame difference and skip frames if needed
            frame_diff = target_frame - current_frame
            
            if frame_diff > 1:
                # Video is behind audio, skip frames to catch up
                print(f"🎬 视频同步: 跳过 {frame_diff - 1} 帧 (目标帧: {target_frame}, 当前帧: {current_frame})")
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = self.video_cap.read()
            elif frame_diff < -1:
                # Video is ahead of audio (unlikely but handle it)
                print(f"🎬 视频同步: 视频超前音频 {abs(frame_diff)} 帧")
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = self.video_cap.read()
            else:
                # Normal playback - read next frame
                ret, frame = self.video_cap.read()
            
            if ret:
                # Update current playback time based on actual video position
                current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
                self.current_playback_time = current_frame / fps if fps > 0 else target_time
                
                # Update play time display
                self.update_play_time_display()
                
                # Check if we're still in the selected time range
                try:
                    end_time = self.end_time_var.get()
                    if self.current_playback_time >= end_time:
                        # Reached end of selected range
                        self.stop_playback()
                        return
                except:
                    pass
                
                # Convert frame to display in canvas
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width = frame.shape[:2]
                
                # Resize frame to fit canvas
                canvas_width = self.preview_canvas.winfo_width()
                canvas_height = self.preview_canvas.winfo_height()
                if canvas_width > 1 and canvas_height > 1:
                    aspect_ratio = width / height
                    if canvas_width / canvas_height > aspect_ratio:
                        new_height = canvas_height
                        new_width = int(canvas_height * aspect_ratio)
                    else:
                        new_width = canvas_width
                        new_height = int(canvas_width / aspect_ratio)
                    
                    frame = cv2.resize(frame, (new_width, new_height))
                    
                    # Convert to PhotoImage and display
                    image = Image.fromarray(frame)
                    photo = ImageTk.PhotoImage(image)
                    
                    # Manage image references to prevent garbage collection
                    self.image_references.append(photo)
                    # Keep only the last few images to avoid memory buildup
                    if len(self.image_references) > 5:
                        self.image_references.pop(0)
                    
                    self.preview_canvas.delete("all")
                    self.preview_canvas.create_image(canvas_width//2, canvas_height//2, 
                                                   image=photo, anchor=tk.CENTER)
                
                # Calculate dynamic delay for next frame update
                # Use shorter delay for better sync accuracy
                next_frame_time = (current_frame + 1) / fps
                time_until_next_frame = next_frame_time - target_time
                
                if time_until_next_frame > 0:
                    delay = max(int(time_until_next_frame * 1000), 16)  # Minimum 16ms (~60 FPS max)
                else:
                    delay = 16  # Immediate update if we're behind
                
                self.video_after_id = self.dialog.after(delay, self.update_video_frame)
            else:
                # End of video
                self.stop_playback()
        except Exception as e:
            print(f"Video playback error: {e}")
            self.stop_playback()


    def display_image_on_canvas(self):
        """在canvas上显示图片"""
        try:
            img = Image.open(self.source_image_path)
            
            # 清空 canvas
            self.image_canvas.delete("all")
            
            # 获取 canvas 的实际大小
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()
            
            # 如果 canvas 还没有准备好，使用默认大小
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width, canvas_height = 600, 600
            
            # 计算宽高比并调整大小以填满 canvas
            img_width, img_height = img.size
            aspect_ratio = img_width / img_height
            
            # 计算新的尺寸，留一些边距
            margin = 20
            available_width = canvas_width - margin
            available_height = canvas_height - margin
            
            if available_width / available_height > aspect_ratio:
                # canvas 更宽，以高度为基准
                new_height = available_height
                new_width = int(new_height * aspect_ratio)
            else:
                # canvas 更高，以宽度为基准
                new_width = available_width
                new_height = int(new_width / aspect_ratio)
            
            # 调整图片大小
            img_resized = img.resize((new_width, new_height), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img_resized)
            
            # 在 canvas 中心显示图片
            x = canvas_width // 2
            y = canvas_height // 2
            self.image_canvas.create_image(x, y, image=photo, anchor=tk.CENTER, tags="image")
            
            # 保持引用以防止被垃圾回收
            self.image_canvas.image = photo
            
        except Exception as e:
            print(f"显示图片失败: {e}")


    def on_animation_changed(self, *args):
        """处理动画选项变化"""
        try:
            # 检查是否有图片和音频
            if not self.source_image_path or not os.path.exists(self.source_image_path):
                print("⚠️ 没有图片，无法重新生成视频")
                return
            
            if not self.source_audio_path or not os.path.exists(self.source_audio_path):
                print("⚠️ 没有音频，无法重新生成视频")
                return
            
            # 获取新的动画选择
            animation_choice = self.animation_var.get()
            self.animation_choice = animation_choice
            
            print(f"🎬 动画选项变化: {animation_choice} ({'静止' if animation_choice == 1 else '左' if animation_choice == 2 else '右' if animation_choice == 3 else '动画'})")
            
            # 停止当前播放
            if self.av_playing:
                self.stop_playback()
            
            # 释放旧的视频捕获对象
            if self.video_cap:
                self.video_cap.release()
                self.video_cap = None
                print("🔄 已释放旧视频资源")
            
            # 重新生成视频
            print(f"🔄 正在重新生成视频...")
            self.source_video_path = self.workflow.ffmpeg_processor.image_audio_to_video(
                self.source_image_path, 
                self.source_audio_path, 
                animation_choice
            )
            
            if self.source_video_path and os.path.exists(self.source_video_path):
                print(f"✓ 视频重新生成成功: {self.source_video_path}")
                
                # 重置播放状态
                self.current_playback_time = 0.0
                self.pause_accumulated_time = 0.0
                self.playback_start_time = None
                
                # 刷新视频显示
                self.dialog.after(100, self.load_video_first_frame)
            else:
                print(f"❌ 视频重新生成失败")
                
        except Exception as e:
            print(f"❌ 处理动画变化失败: {e}")
    

    def on_video_dnd_drop(self, event):
        """处理视频拖放"""
        file_path = event.data.strip('{}').strip('"')
        if is_video_file(file_path):
            self.handle_new_media(file_path)
            self.update_dialog_title("none")


    def on_image_dnd_drop(self, event):
        """处理图片拖放"""
        file_path = event.data.strip('{}').strip('"')
        if is_image_file(file_path):
            self.handle_new_media(file_path)
            self.update_dialog_title("none")

    
    def on_audio_dnd_drop(self, event):
        """处理音频拖放"""
        file_path = event.data.strip('{}').strip('"')
        if is_audio_file(file_path):
            self.handle_new_media(file_path)
            self.update_dialog_title("none")


    def handle_new_media(self, av_path):
        if not av_path:
            return

        # 停止当前播放
        if self.av_playing:
            self.stop_playback()
        
        # 释放旧的视频捕获对象
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None

        # 清除裁剪选择
        self.clear_crop_selection()
        
        # 重置视频尺寸
        self.video_original_width = None
        self.video_original_height = None

        self.start_time = 0.0

        if is_audio_file(av_path):
            self.source_audio_path = self.workflow.ffmpeg_audio_processor.audio_change(av_path)
            self.source_video_path = self.workflow.ffmpeg_processor.add_audio_to_video(self.source_video_path, self.source_audio_path)
        elif is_image_file(av_path):
            self.source_image_path = av_path
            self.source_video_path = self.workflow.ffmpeg_processor.image_audio_to_video(self.source_image_path, self.source_audio_path, self.animation_choice)
        elif is_video_file(av_path):
            if self.workflow.ffmpeg_processor.has_audio_stream(av_path) and self.replace_media_audio=="keep":
                self.source_video_path = self.workflow.ffmpeg_processor.resize_video(av_path, self.workflow.ffmpeg_processor.width)
                self.source_audio_path = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(av_path)
            else:
                self.source_video_path = self.workflow.ffmpeg_processor.add_audio_to_video(av_path, self.source_audio_path, True, True)
                self.source_video_path = self.workflow.ffmpeg_processor.resize_video(self.source_video_path, self.workflow.ffmpeg_processor.width)

        self.audio_duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
        self.end_time = self.audio_duration

        # 重置播放状态
        self.current_playback_time = 0.0
        self.pause_accumulated_time = 0.0
        self.playback_start_time = None

        self.display_image_on_canvas()

        # 刷新视频显示（延迟加载确保视频资源准备就绪）
        self.dialog.after(100, self.load_video_first_frame)
    
    
    def on_canvas_click(self, event):
        """Handle mouse click on preview canvas to start crop selection"""
        if not self.source_video_path:
            return
        
        # Get canvas coordinates
        canvas_x = event.x
        canvas_y = event.y
        
        # Convert canvas coordinates to video coordinates
        video_x, video_y = self.canvas_to_video_coords(canvas_x, canvas_y)
        
        if video_x is not None and video_y is not None:
            self.selecting = True
            self.selection_start_x = canvas_x
            self.selection_start_y = canvas_y
            
            # Clear previous selection
            if self.selection_rect:
                self.preview_canvas.delete(self.selection_rect)
            self.selection_rect = None
    
    
    def on_canvas_drag(self, event):
        """Handle mouse drag on preview canvas to update crop selection"""
        if not self.selecting:
            return
        
        # Get current canvas coordinates
        canvas_x = event.x
        canvas_y = event.y
        
        # Update selection rectangle
        if self.selection_rect:
            self.preview_canvas.delete(self.selection_rect)
        
        # Draw selection rectangle
        x1 = min(self.selection_start_x, canvas_x)
        y1 = min(self.selection_start_y, canvas_y)
        x2 = max(self.selection_start_x, canvas_x)
        y2 = max(self.selection_start_y, canvas_y)
        
        self.selection_rect = self.preview_canvas.create_rectangle(
            x1, y1, x2, y2,
            outline='yellow', width=2, dash=(5, 5)
        )
    
    
    def on_canvas_release(self, event):
        """Handle mouse release on preview canvas to finalize crop selection"""
        if not self.selecting:
            return
        
        self.selecting = False
        
        # Get canvas coordinates
        canvas_x = event.x
        canvas_y = event.y
        
        # Convert to video coordinates
        start_x, start_y = self.canvas_to_video_coords(
            min(self.selection_start_x, canvas_x),
            min(self.selection_start_y, canvas_y)
        )
        end_x, end_y = self.canvas_to_video_coords(
            max(self.selection_start_x, canvas_x),
            max(self.selection_start_y, canvas_y)
        )

        if start_x > end_x:
            start_x, end_x = end_x, start_x
        if start_y > end_y:
            start_y, end_y = end_y, start_y
        
        if start_x is not None and start_y is not None and end_x is not None and end_y is not None:
            # Update crop parameters
            self.crop_start_x = max(0, int(start_x))
            self.crop_start_y = max(0, int(start_y))
            crop_w = max(1, int(end_x - start_x))
            crop_h = max(1, int(end_y - start_y))
            
            # Store crop dimensions
            self.crop_width = crop_w
            self.crop_height = crop_h
            
            # Update UI controls
            self.crop_x_var.set(self.crop_start_x)
            self.crop_y_var.set(self.crop_start_y)
            self.crop_width_var.set(crop_w)
            
            print(f"✓ 选择裁剪区域: ({self.crop_start_x}, {self.crop_start_y}), 尺寸: {crop_w}x{crop_h}")
    
    
    def canvas_to_video_coords(self, canvas_x, canvas_y):
        """Convert canvas coordinates to video coordinates"""
        if not self.source_video_path or not self.video_original_width or not self.video_original_height:
            return None, None
        
        try:
            # Get canvas dimensions
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                return None, None
            
            # Get displayed image dimensions (from first frame)
            if not hasattr(self, 'first_frame_photo') or not self.first_frame_photo:
                return None, None
            
            # Find the image item on canvas
            items = self.preview_canvas.find_all()
            image_item = None
            for item in items:
                if self.preview_canvas.type(item) == 'image':
                    image_item = item
                    break
            
            if not image_item:
                return None, None
            
            # Get image coordinates and dimensions
            coords = self.preview_canvas.coords(image_item)
            img_x = coords[0]
            img_y = coords[1]
            
            # Get image dimensions from photo
            img_width = self.first_frame_photo.width()
            img_height = self.first_frame_photo.height()
            
            # Calculate image bounds
            img_left = img_x - img_width // 2
            img_right = img_x + img_width // 2
            img_top = img_y - img_height // 2
            img_bottom = img_y + img_height // 2
            
            # Check if click is within image bounds
            if canvas_x < img_left or canvas_x > img_right or canvas_y < img_top or canvas_y > img_bottom:
                return None, None
            
            # Convert to relative coordinates (0.0 to 1.0)
            rel_x = (canvas_x - img_left) / img_width
            rel_y = (canvas_y - img_top) / img_height
            
            # Convert to video coordinates
            video_x = int(rel_x * self.video_original_width)
            video_y = int(rel_y * self.video_original_height)
            
            return video_x, video_y
            
        except Exception as e:
            print(f"⚠️ 坐标转换失败: {e}")
            return None, None
    
    
    def on_crop_params_changed(self, *args):
        """Handle changes to crop parameter controls"""
        try:
            self.crop_start_x = self.crop_x_var.get()
            self.crop_start_y = self.crop_y_var.get()
            
            width_val = self.crop_width_var.get()
            if width_val == 0:
                self.crop_width = None
            else:
                self.crop_width = width_val
                # Calculate height based on aspect ratio if not set
                if self.crop_width and self.video_original_width and self.video_original_height:
                    aspect_ratio = self.video_original_height / self.video_original_width
                    self.crop_height = int(self.crop_width * aspect_ratio)
            
            # Update selection rectangle display
            self.update_crop_selection_display()
        except Exception as e:
            print(f"⚠️ 更新裁剪参数失败: {e}")
    
    
    def update_crop_selection_display(self):
        """Update the visual selection rectangle on canvas"""
        if not self.source_video_path or self.crop_width is None or self.crop_width == 0:
            # Clear selection if no crop is set
            if self.selection_rect:
                self.preview_canvas.delete(self.selection_rect)
                self.selection_rect = None
            return
        
        try:
            # Clear previous selection
            if self.selection_rect:
                self.preview_canvas.delete(self.selection_rect)
            
            # Calculate crop height if not set
            crop_h = self.crop_height
            if not crop_h and self.video_original_width and self.video_original_height:
                # Calculate height based on aspect ratio
                aspect_ratio = self.video_original_height / self.video_original_width
                crop_h = int(self.crop_width * aspect_ratio)
            elif not crop_h:
                crop_h = self.crop_width  # Fallback to square
            
            # Convert video coordinates to canvas coordinates
            canvas_coords = self.video_to_canvas_coords(
                self.crop_start_x, self.crop_start_y,
                self.crop_start_x + self.crop_width,
                self.crop_start_y + crop_h
            )
            
            if canvas_coords:
                x1, y1, x2, y2 = canvas_coords
                self.selection_rect = self.preview_canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline='yellow', width=2, dash=(5, 5)
                )
        except Exception as e:
            print(f"⚠️ 更新选择显示失败: {e}")
    
    
    def video_to_canvas_coords(self, video_x1, video_y1, video_x2, video_y2):
        """Convert video coordinates to canvas coordinates"""
        if not self.source_video_path or not self.video_original_width or not self.video_original_height:
            return None
        
        try:
            # Get canvas dimensions
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                return None
            
            # Get displayed image dimensions
            if not hasattr(self, 'first_frame_photo') or not self.first_frame_photo:
                return None
            
            # Find the image item on canvas
            items = self.preview_canvas.find_all()
            image_item = None
            for item in items:
                if self.preview_canvas.type(item) == 'image':
                    image_item = item
                    break
            
            if not image_item:
                return None
            
            # Get image coordinates
            coords = self.preview_canvas.coords(image_item)
            img_x = coords[0]
            img_y = coords[1]
            
            # Get image dimensions
            img_width = self.first_frame_photo.width()
            img_height = self.first_frame_photo.height()
            
            # Calculate image bounds
            img_left = img_x - img_width // 2
            img_top = img_y - img_height // 2
            
            # Convert to relative coordinates
            rel_x1 = video_x1 / self.video_original_width
            rel_y1 = video_y1 / self.video_original_height
            rel_x2 = video_x2 / self.video_original_width
            rel_y2 = video_y2 / self.video_original_height
            
            # Convert to canvas coordinates
            canvas_x1 = img_left + rel_x1 * img_width
            canvas_y1 = img_top + rel_y1 * img_height
            canvas_x2 = img_left + rel_x2 * img_width
            canvas_y2 = img_top + rel_y2 * img_height
            
            return (canvas_x1, canvas_y1, canvas_x2, canvas_y2)
            
        except Exception as e:
            print(f"⚠️ 坐标转换失败: {e}")
            return None
    
    
    def clear_crop_selection(self):
        """Clear the crop selection"""
        self.crop_start_x = 0
        self.crop_start_y = 0
        self.crop_width = None
        self.crop_height = None
        
        if self.selection_rect:
            self.preview_canvas.delete(self.selection_rect)
            self.selection_rect = None
        
        self.crop_x_var.set(0)
        self.crop_y_var.set(0)
        self.crop_width_var.set(0)
        
        print("✓ 已清除裁剪选择")
    
    
    def _update_crop_spinbox_max(self):
        """Update max values for crop spinboxes based on video dimensions"""
        if not self.video_original_width or not self.video_original_height:
            return
        
        try:
            # Find and update crop spinboxes
            def update_widget(widget):
                if isinstance(widget, ttk.Spinbox):
                    var = widget.cget('textvariable')
                    if var:
                        var_obj = self.dialog.nametowidget(var) if isinstance(var, str) else var
                        if var_obj == self.crop_x_var:
                            widget.configure(to=self.video_original_width)
                        elif var_obj == self.crop_y_var:
                            widget.configure(to=self.video_original_height)
                        elif hasattr(self, 'crop_width_var') and var_obj == self.crop_width_var:
                            widget.configure(to=self.video_original_width)
                elif isinstance(widget, (ttk.Frame, tk.Frame)):
                    for child in widget.winfo_children():
                        update_widget(child)
            
            # Update all widgets
            for widget in self.dialog.winfo_children():
                update_widget(widget)
        except Exception as e:
            print(f"⚠️ 更新裁剪控件最大值失败: {e}")
