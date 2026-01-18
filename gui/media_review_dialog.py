import tkinter as tk
from tkinter import ttk, messagebox
import os, time, threading
from PIL import Image, ImageTk
from utility.file_util import get_file_path, safe_remove, safe_file
from utility.audio_transcriber import AudioTranscriber
from project_manager import refresh_scene_media
import config, config_channel
from utility.llm_api import LLMApi
import json
from config import parse_json_from_text
from utility.file_util import is_audio_file, is_video_file, is_image_file
import config_prompt


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


PROJECT_TYPE_STORY = "story"
PROJECT_TYPE_TALK = "talk"
PROJECT_TYPE_SONG = "song"
PROJECT_TYPE_MUSIC = "music"

PROJECT_TYPE_LIST = [
    PROJECT_TYPE_STORY,
    PROJECT_TYPE_SONG,
    PROJECT_TYPE_MUSIC,
    PROJECT_TYPE_TALK
]



class AVReviewDialog:
    """Dialog for reviewing and configuring audio replacement with drag-and-drop support"""
    
    def __init__(self, parent, video_path, current_scene, previous_scene, next_scene, media_type, replace_media_audio):
        self.parent = parent
        self.current_scene = current_scene
        self.previous_scene = previous_scene
        self.next_scene = next_scene
        self.workflow = parent.workflow
        # Get video dimensions from workflow's ffmpeg_processor
        video_width = self.workflow.ffmpeg_processor.width
        video_height = self.workflow.ffmpeg_processor.height
        self.transcriber = AudioTranscriber(self.workflow.pid, model_size="small", device="cuda")
        self.llm_api = LLMApi()

        self.media_type_names = {
            "clip": "场景媒体 (clip)",
            "narration": "旁白轨道 (narration)",
            "zero": "背景轨道 (zero)",
            "one": "第一轨道 (one)"
        }

        self.transcribe_way = "single"

        self.media_type = media_type
        self.replace_media_audio = replace_media_audio

        if self.media_type == "clip":
            self.SPEAKER_KEY = "speaker"
            self.SPEAKING_KEY = "speaking"
            self.ACTORS = config_prompt.SPEAKER
        else:
            self.SPEAKER_KEY = "narrator"
            self.SPEAKING_KEY = "voiceover"
            self.ACTORS = config_prompt.NARRATOR
        
        # 媒体字段名映射
        if media_type == "clip":
            self.video_field = "clip"
            self.audio_field = "clip_audio"
            self.image_field = "clip_image"
        elif media_type == "narration":
            self.video_field = "narration"
            self.audio_field = "narration_audio"
            self.image_field = "narration_image"
        elif media_type == "zero":
            self.video_field = "zero"
            self.audio_field = "zero_audio"
            self.image_field = "zero_image"
        elif media_type == "one":
            self.video_field = "one"
            self.audio_field = "one_audio"
            self.image_field = "one_image"

        self.source_video_path = get_file_path(self.current_scene, self.video_field)
        self.source_audio_path = get_file_path(self.current_scene, self.audio_field)
        self.source_image_path = get_file_path(self.current_scene, self.image_field)
        
        self.audio_duration = 0.0
        # 使用 _pending_boundaries 统一管理时间边界，移除重复的 start_time_var 和 end_time_var
        self._pending_boundaries = None
        self._boundaries_initialized = False

        # 新增拖放媒体
        self.animation_choice = 1

        self.current_playback_time = 0.0
        self.av_playing = False
        self.av_paused = False
        self.playback_start_time = None  # Time when playback started
        self.pause_accumulated_time = 0.0  # Total time played before pausing

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
        
        self.process_new_media(video_path)

        self.create_dialog()

        self.current_scene["start"] = 0.0
        self.current_scene["end"] = self.audio_duration
        if self.current_scene.get("caption", None):
            self.current_scene[self.SPEAKER_KEY+"_audio"] = self.source_audio_path
        self.audio_json = [ self.current_scene ]
        self._update_fresh_json_text()

        self.dialog.after(100, self.init_load)



    def init_load(self):
        self.draw_waveform_placeholder()
        self.display_image_on_canvas()
        self.load_video_first_frame()
        # 初始化时间轴
        self._draw_progress_bar()
        self._draw_edit_timeline()



    def create_dialog(self):
        """Create the review dialog window"""
        self.dialog = tk.Toplevel(self.parent.root)
        self.dialog.geometry("1800x1000")
        self.dialog.resizable(True, True)
        self.dialog.transient(self.parent.root)
        self.dialog.grab_set()
        self.dialog.title( f"{self.media_type_names.get(self.media_type)} - {self.transcribe_way}" )

        # Main container
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Media info section
        info_frame = ttk.LabelFrame(main_frame, text="", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Media info row
        info_row = ttk.Frame(info_frame)
        info_row.pack(fill=tk.X, pady=2)
        
        ttk.Label(info_row, text=f"视频时长: { (self.audio_duration):.2f}秒").pack(side=tk.LEFT)
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
        
        # ========== 时间轴区域 (Timeline Section) ==========
        timeline_container = ttk.LabelFrame(main_frame, text="时间轴控制", padding=5)
        timeline_container.pack(fill=tk.X, pady=(5, 5))
        
        # --- Progress Bar (播放进度条) ---
        progress_frame = ttk.Frame(timeline_container)
        progress_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(progress_frame, text="播放位置:", width=10).pack(side=tk.LEFT, padx=(0, 5))
        
        # Progress bar canvas for playback position
        self.progress_canvas = tk.Canvas(progress_frame, height=30, bg='#2d2d2d', highlightthickness=1, highlightbackground='#555')
        self.progress_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # Progress bar 内部元素（稍后初始化）
        self.progress_bar_bg = None
        self.progress_playhead = None
        self.progress_dragging = False
        
        # 绑定 Progress Bar 事件
        self.progress_canvas.bind('<Configure>', self._on_progress_canvas_configure)
        self.progress_canvas.bind('<Button-1>', self._on_progress_click)
        self.progress_canvas.bind('<B1-Motion>', self._on_progress_drag)
        self.progress_canvas.bind('<ButtonRelease-1>', self._on_progress_release)
        
        # 当前播放时间显示
        self.progress_time_label = ttk.Label(progress_frame, text="0.00", width=8)
        self.progress_time_label.pack(side=tk.LEFT)
        
        # --- Edit Timeline (剪辑时间轴) ---
        edit_timeline_frame = ttk.Frame(timeline_container)
        edit_timeline_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(edit_timeline_frame, text="剪辑区间:", width=10).pack(side=tk.LEFT, padx=(0, 5))
        
        # Edit timeline canvas for scene boundaries
        self.edit_timeline_canvas = tk.Canvas(edit_timeline_frame, height=40, bg='#1a1a2e', highlightthickness=1, highlightbackground='#555')
        self.edit_timeline_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # Edit Timeline 内部元素
        self.edit_timeline_bg = None
        self.edit_handles = []  # 存储所有可拖动节点
        self.edit_handle_dragging = None  # 当前正在拖动的节点索引
        self.edit_regions = []  # 存储场景区域显示
        # _pending_boundaries 和 _boundaries_initialized 已在 __init__ 中初始化
        
        # 绑定 Edit Timeline 事件
        self.edit_timeline_canvas.bind('<Configure>', self._on_edit_timeline_configure)
        self.edit_timeline_canvas.bind('<Button-1>', self._on_edit_timeline_click)
        self.edit_timeline_canvas.bind('<B1-Motion>', self._on_edit_timeline_drag)
        self.edit_timeline_canvas.bind('<ButtonRelease-1>', self._on_edit_timeline_release)
        
        # 场景数量显示
        self.scene_count_label = ttk.Label(edit_timeline_frame, text="1 场景", width=10)
        self.scene_count_label.pack(side=tk.LEFT)
        
        # Media controls (placed below the media visualization)
        control_container = ttk.Frame(main_frame)
        control_container.pack(fill=tk.X, pady=(0, 10))
        
        # Media controls
        control_frame = ttk.Frame(control_container)
        control_frame.pack(fill=tk.X, pady=5)
        
        self.play_button = ttk.Button(control_frame, text="▶ 播放", command=self.toggle_playback)
        self.play_button.pack(side=tk.LEFT, padx=15)
        
        self.play_time_label = ttk.Label(control_frame, text="0.00 / 0.00", foreground="blue")
        self.play_time_label.pack(side=tk.LEFT, padx=15)

        max_duration = self.workflow.ffmpeg_processor.get_duration(self.source_video_path) if self.source_video_path else self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)

        separator = ttk.Separator(control_frame, orient='vertical')
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=15)

        ttk.Button(control_frame, text="恢复剪辑变动", command=self.restore_edit_timeline_change).pack(side=tk.LEFT, padx=15)
        ttk.Button(control_frame, text="确认剪辑变动", command=self.confirm_edit_timeline_change).pack(side=tk.LEFT, padx=15)
        
        # 分隔符
        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        
        # add a button to let user record the audio from microphone, then put it as source_audio_path, then transcribe it, set self.regenerate_audio to True
        ttk.Button(control_frame, text="录音", command=self.record_audio).pack(side=tk.LEFT, padx=(0, 10))

        # Initialize play time display
        self.update_play_time_display()
        
        # 不再需要 trace 回调，因为已移除 start_time_var 和 end_time_var
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
        
        self.fresh_label = ttk.Label(fresh_frame, text="Converation Script")
        self.fresh_label.pack(anchor="w", pady=(0, 5))
        
        # Fresh JSON text editor with scrollbar
        fresh_text_frame = ttk.Frame(fresh_frame)
        fresh_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.fresh_json_text = tk.Text(fresh_text_frame, wrap=tk.WORD, width=40, height=15)
        fresh_scrollbar = ttk.Scrollbar(fresh_text_frame, orient="vertical", command=self.fresh_json_text.yview)
        self.fresh_json_text.configure(yscrollcommand=fresh_scrollbar.set)
        
        self.fresh_json_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fresh_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 标志位，防止循环更新
        self._updating_from_json = False
        
        # Buttons for fresh JSON editor
        fresh_buttons_frame = ttk.Frame(fresh_frame)
        fresh_buttons_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 旁白语音组
        ttk.Label(fresh_buttons_frame, text="角色").pack(side=tk.LEFT, padx=(0, 5))
        self.speaker = ttk.Combobox(fresh_buttons_frame, values=self.ACTORS, state="normal", width=30)
        self.speaker.pack(side=tk.LEFT, padx=(0, 10))
        self.speaker.current(0)
        self.speaker.bind("<<ComboboxSelected>>", lambda e: self.on_speaker_changed(e))
        self.speaker.bind("<FocusOut>", lambda e: self.on_speaker_changed(e))

        # transcribe exsiting conversation (if >>30 sec), then remix single conversation
        ttk.Button(fresh_buttons_frame, text="单重建", command=lambda: self.remix_conversation("single", False)).pack(side=tk.LEFT)
        ttk.Button(fresh_buttons_frame, text="多重建", command=lambda: self.remix_conversation("multiple", False)).pack(side=tk.LEFT)
        
        ttk.Button(fresh_buttons_frame, text="前接重", command=lambda: self.remix_conversation("connect_prev", False)).pack(side=tk.LEFT)
        ttk.Button(fresh_buttons_frame, text="后接重", command=lambda: self.remix_conversation("connect_next", False)).pack(side=tk.LEFT)
        # transcribe exsiting conversation (if >>30 sec), then remix multiple conversation

        ttk.Button(fresh_buttons_frame, text="单转录", command=lambda: self.transcribe_audio("single")).pack(side=tk.LEFT)
        ttk.Button(fresh_buttons_frame, text="多转录", command=lambda: self.transcribe_audio("multiple")).pack(side=tk.LEFT)
        ttk.Button(fresh_buttons_frame, text="生音频", command=self.regenerate_audio).pack(side=tk.LEFT)
        
        # ttk.Button(fresh_buttons_frame, text="剪音视", command=lambda: self.trim_video(False)).pack(side=tk.LEFT)
        # ttk.Button(fresh_buttons_frame, text="剪视频", command=lambda: self.trim_video(True)).pack(side=tk.LEFT)
        
        ttk.Button(fresh_buttons_frame, text="替换", command=self.confirm_replacement).pack(side=tk.RIGHT)
        ttk.Button(fresh_buttons_frame, text="取消", command=self.cancel).pack(side=tk.RIGHT)
        
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
            start = self._get_start_time()
            end = self._get_end_time()
            if end > start:
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
        except:
            pass
    

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
            
            # 同时更新 Progress Bar 播放头位置
            self._update_progress_playhead()
            
        except Exception as e:
            print(f"⚠️ 更新时间显示失败: {e}")
            self.play_time_label.config(text="0.00 / 0.00")
    

    # ========== Progress Bar (播放进度条) 方法 ==========
    
    def _on_progress_canvas_configure(self, event=None):
        """Progress Bar canvas 大小变化时重绘"""
        self._draw_progress_bar()
    
    def _draw_progress_bar(self):
        """绘制 Progress Bar 背景和播放头"""
        canvas = self.progress_canvas
        canvas.delete('all')
        
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            return
        
        padding = 10
        bar_height = 8
        bar_y = (height - bar_height) // 2
        
        # 绘制进度条背景
        canvas.create_rectangle(padding, bar_y, width - padding, bar_y + bar_height,
                               fill='#404040', outline='#606060', tags='progress_bg')
        
        # 绘制已播放部分
        if self.audio_duration > 0:
            progress_ratio = min(1.0, self.current_playback_time / self.audio_duration)
            progress_x = padding + (width - 2 * padding) * progress_ratio
            canvas.create_rectangle(padding, bar_y, progress_x, bar_y + bar_height,
                                   fill='#4CAF50', outline='', tags='progress_fill')
        
        # 绘制播放头（可拖动的圆形按钮）
        self._draw_playhead()
    
    def _draw_playhead(self):
        """绘制播放头"""
        canvas = self.progress_canvas
        canvas.delete('playhead')
        
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or self.audio_duration <= 0:
            return
        
        padding = 10
        progress_ratio = min(1.0, max(0, self.current_playback_time / self.audio_duration))
        playhead_x = padding + (width - 2 * padding) * progress_ratio
        playhead_y = height // 2
        playhead_radius = 8
        
        # 绘制播放头圆形
        canvas.create_oval(playhead_x - playhead_radius, playhead_y - playhead_radius,
                          playhead_x + playhead_radius, playhead_y + playhead_radius,
                          fill='#FF5722', outline='white', width=2, tags='playhead')
        
        # 更新时间显示
        self.progress_time_label.config(text=f"{self.current_playback_time:.2f}")
    
    def _update_progress_playhead(self):
        """更新播放头位置（播放时调用）"""
        self._draw_progress_bar()
    
    def _on_progress_click(self, event):
        """Progress Bar 点击事件"""
        self.progress_dragging = True
        self._seek_to_position(event.x)
    
    def _on_progress_drag(self, event):
        """Progress Bar 拖动事件"""
        if self.progress_dragging:
            self._seek_to_position(event.x)
    
    def _on_progress_release(self, event):
        """Progress Bar 释放事件"""
        if self.progress_dragging:
            self._seek_to_position(event.x)
            self.progress_dragging = False
    
    def _seek_to_position(self, x):
        """跳转到指定位置"""
        canvas = self.progress_canvas
        width = canvas.winfo_width()
        padding = 10
        
        # 计算时间
        bar_width = width - 2 * padding
        if bar_width <= 0:
            return
        
        ratio = max(0, min(1, (x - padding) / bar_width))
        new_time = ratio * self.audio_duration
        
        # 更新播放位置
        self.current_playback_time = new_time
        self.pause_accumulated_time = new_time
        
        # 拖动进度条会导致需要重新加载音频，所以清除暂停状态
        was_playing = self.av_playing
        self.av_paused = False
        
        # 如果正在播放，需要重新设置播放位置
        if was_playing:
            self.playback_start_time = time.time()
            
            # 更新视频位置
            if self.source_video_path and self.video_cap:
                fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 30
                frame_num = int(new_time * fps)
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            
            # 更新音频位置（需要重新加载）
            if self.source_audio_path:
                pygame.mixer.music.stop()
                pygame.mixer.music.load(self.source_audio_path)
                pygame.mixer.music.play(start=new_time)
                print(f"🔍 进度条拖动: 跳转到 {new_time:.2f}s")
        
        # 更新显示
        self.update_play_time_display()
        self._draw_progress_bar()
    
    # ========== Edit Timeline (剪辑时间轴) 方法 ==========
    
    def _on_edit_timeline_configure(self, event=None):
        """Edit Timeline canvas 大小变化时重绘"""
        self._draw_edit_timeline()
    
    def _draw_edit_timeline(self):
        """绘制剪辑时间轴"""
        canvas = self.edit_timeline_canvas
        canvas.delete('all')
        
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            return
        
        padding = 10
        bar_y = height // 2
        bar_height = 16
        
        # 获取场景边界时间点
        boundaries = self._get_scene_boundaries()
        num_scenes = len(boundaries) - 1 if len(boundaries) > 1 else 1
        
        # 调试：打印边界信息
        if len(boundaries) >= 2:
            print(f"🎨 绘制时间轴 - 边界: start={boundaries[0]:.2f}, end={boundaries[-1]:.2f}, 场景数={num_scenes}")
        
        # 更新场景数量显示
        self.scene_count_label.config(text=f"{num_scenes} 场景")
        
        # 定义颜色列表（用于区分不同场景）
        colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e']
        
        # 绘制时间轴背景
        canvas.create_rectangle(padding, bar_y - bar_height // 2, width - padding, bar_y + bar_height // 2,
                               fill='#2c3e50', outline='#7f8c8d', tags='timeline_bg')
        
        # 绘制场景区域
        self.edit_regions = []
        for i in range(len(boundaries) - 1):
            start_time = boundaries[i]
            end_time = boundaries[i + 1]
            
            if self.audio_duration > 0:
                start_x = padding + (width - 2 * padding) * (start_time / self.audio_duration)
                end_x = padding + (width - 2 * padding) * (end_time / self.audio_duration)
            else:
                start_x = padding
                end_x = width - padding
            
            color = colors[i % len(colors)]
            region_id = canvas.create_rectangle(start_x, bar_y - bar_height // 2 + 2,
                                               end_x, bar_y + bar_height // 2 - 2,
                                               fill=color, outline='', tags=f'region_{i}')
            self.edit_regions.append(region_id)
            
            # 在区域中央显示场景编号
            center_x = (start_x + end_x) / 2
            if end_x - start_x > 20:  # 只有空间足够时才显示文字
                canvas.create_text(center_x, bar_y, text=str(i + 1), fill='white',
                                  font=('Arial', 8, 'bold'), tags=f'region_text_{i}')
        
        # 绘制可拖动的边界节点
        self._draw_edit_handles(boundaries)
    
    def _draw_edit_handles(self, boundaries):
        """绘制可拖动的边界节点"""
        canvas = self.edit_timeline_canvas
        canvas.delete('handle')
        
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        padding = 10
        handle_radius = 6
        bar_y = height // 2
        
        self.edit_handles = []
        
        for i, boundary_time in enumerate(boundaries):
            if self.audio_duration > 0:
                x = padding + (width - 2 * padding) * (boundary_time / self.audio_duration)
            else:
                x = padding if i == 0 else width - padding
            
            # 绘制节点（三角形 + 线条）
            # 垂直线
            canvas.create_line(x, bar_y - 12, x, bar_y + 12, fill='white', width=2, tags=('handle', f'handle_line_{i}'))
            
            # 顶部三角形
            canvas.create_polygon(x - 5, bar_y - 12, x + 5, bar_y - 12, x, bar_y - 6,
                                 fill='#FFD700', outline='white', tags=('handle', f'handle_top_{i}'))
            
            # 底部三角形
            canvas.create_polygon(x - 5, bar_y + 12, x + 5, bar_y + 12, x, bar_y + 6,
                                 fill='#FFD700', outline='white', tags=('handle', f'handle_bottom_{i}'))
            
            self.edit_handles.append({
                'index': i,
                'time': boundary_time,
                'x': x
            })
    
    def _ensure_boundaries_initialized(self):
        """确保边界已初始化"""
        if not self._boundaries_initialized or self._pending_boundaries is None:
            self._pending_boundaries = self._get_boundaries_from_audio_json()
            if not self._pending_boundaries or len(self._pending_boundaries) < 2:
                self._pending_boundaries = [0.0, self.audio_duration]
            self._boundaries_initialized = True
    
    def _get_start_time(self):
        """获取开始时间：从 _pending_boundaries[0] 获取"""
        self._ensure_boundaries_initialized()
        if self._pending_boundaries and len(self._pending_boundaries) > 0:
            return self._pending_boundaries[0]
        return 0.0
    
    def _get_end_time(self):
        """获取结束时间：从 _pending_boundaries[-1] 获取"""
        self._ensure_boundaries_initialized()
        if self._pending_boundaries and len(self._pending_boundaries) > 1:
            return self._pending_boundaries[-1]
        return self.audio_duration
    
    def _set_start_time(self, value):
        """设置开始时间：更新 _pending_boundaries[0]"""
        self._ensure_boundaries_initialized()
        if self._pending_boundaries:
            self._pending_boundaries[0] = value
            self._boundaries_initialized = True
        self.update_duration_display()
    
    def _set_end_time(self, value):
        """设置结束时间：更新 _pending_boundaries[-1]"""
        self._ensure_boundaries_initialized()
        if self._pending_boundaries:
            self._pending_boundaries[-1] = value
            self._boundaries_initialized = True
        self.update_duration_display()
    
    def _get_scene_boundaries(self):
        """获取场景边界时间点列表"""
        # 确保边界已初始化
        self._ensure_boundaries_initialized()
        
        # 返回当前边界的副本
        if self._pending_boundaries and len(self._pending_boundaries) >= 2:
            return self._pending_boundaries.copy()
        
        # 如果仍然没有有效边界，返回默认值
        return [0.0, self.audio_duration]
    
    def _on_edit_timeline_click(self, event):
        """Edit Timeline 点击事件"""
        # 检查是否点击了某个节点
        handle_index = self._find_handle_at(event.x, event.y)
        if handle_index is not None:
            self.edit_handle_dragging = handle_index
    
    def _on_edit_timeline_drag(self, event):
        """Edit Timeline 拖动事件"""
        if self.edit_handle_dragging is not None:
            self._drag_handle_to(self.edit_handle_dragging, event.x)
    
    def _on_edit_timeline_release(self, event):
        """Edit Timeline 释放事件"""
        if self.edit_handle_dragging is not None:
            self._drag_handle_to(self.edit_handle_dragging, event.x)
            self.edit_handle_dragging = None
            # 注意：不再立即更新 audio_json，保持 pending 状态
            # 用户需要点击"确认剪辑区间变动"来应用更改
    
    def _find_handle_at(self, x, y):
        """查找指定位置的节点索引"""
        for handle in self.edit_handles:
            if abs(x - handle['x']) < 15:  # 15 像素容差
                return handle['index']
        return None
    
    def _drag_handle_to(self, handle_index, x):
        """拖动节点到指定位置"""
        canvas = self.edit_timeline_canvas
        width = canvas.winfo_width()
        padding = 10
        
        # 计算新时间
        bar_width = width - 2 * padding
        if bar_width <= 0:
            return
        
        ratio = max(0, min(1, (x - padding) / bar_width))
        new_time = ratio * self.audio_duration
        
        # 确保边界已初始化
        self._ensure_boundaries_initialized()
        
        # 拖动时只更新 _pending_boundaries，audio_json 的 start/end 在确认时才更新
        boundaries = self._pending_boundaries
        
        # 确保不越界（保持顺序）
        # 第一个 handle 可以移动，但不能超过第二个
        # 最后一个 handle 可以移动，但不能小于倒数第二个
        if handle_index == 0:
            min_time = 0.0
            max_time = boundaries[1] - 0.1 if len(boundaries) > 1 else self.audio_duration
        elif handle_index == len(boundaries) - 1:
            min_time = boundaries[handle_index - 1] + 0.1
            max_time = self.audio_duration
        else:
            min_time = boundaries[handle_index - 1] + 0.1
            max_time = boundaries[handle_index + 1] - 0.1
        
        new_time = max(min_time, min(max_time, new_time))
        
        # 更新边界
        boundaries[handle_index] = new_time
        self._pending_boundaries = boundaries
        
        # 当开始或结束时间改变时，触发更新显示
        if handle_index == 0 or handle_index == len(boundaries) - 1:
            self.update_duration_display()
        
        # 重绘时间轴
        self._draw_edit_timeline()
    

    def _get_boundaries_from_audio_json(self):
        """从 audio_json 的 start/end 字段生成边界列表"""
        if not hasattr(self, 'audio_json') or not self.audio_json:
            return [0.0, self.audio_duration]
        
        boundaries = []
        current_time = 0.0
        
        for i, scene in enumerate(self.audio_json):
            # 确保每个场景都有 start/end 字段
            if 'start' not in scene or 'end' not in scene:
                # 如果没有，从 duration 计算并添加
                duration = scene.get('duration', 0)
                scene['start'] = current_time
                scene['end'] = current_time + duration
            
            # 添加起始边界（只在第一个场景时）
            if i == 0:
                boundaries.append(scene['start'])
            
            # 添加结束边界
            boundaries.append(scene['end'])
            current_time = scene['end']
        
        return boundaries if len(boundaries) >= 2 else [0.0, self.audio_duration]
    
    def _update_scene_durations_from_boundaries(self, boundaries):
        """根据边界时间更新 audio_json 中的 start/end/duration 字段"""
        if not hasattr(self, 'audio_json') or not self.audio_json:
            return
        
        for i in range(len(self.audio_json)):
            if i < len(boundaries) - 1:
                start_time = boundaries[i]
                end_time = boundaries[i + 1]
                self.audio_json[i]['start'] = start_time
                self.audio_json[i]['end'] = end_time
                self.audio_json[i]['duration'] = end_time - start_time
    
    def _update_audio_json_from_timeline(self):
        """从时间轴更新 audio_json"""
        # duration 已经在拖动过程中更新了
        pass
    
    def refresh_edit_timeline(self):
        """刷新剪辑时间轴（当 audio_json 变化时调用）"""
        # 清除待确认状态和边界，强制重新计算
        self._pending_boundaries = None
        self._boundaries_initialized = False
        
        # 重新初始化边界（从 audio_json 的 start/end 字段读取）
        self._ensure_boundaries_initialized()
        
        self._draw_edit_timeline()
        self.update_duration_display()


    def restore_edit_timeline_change(self):
        if self.media_type != "clip":
            return
        
        """恢复剪辑区间变动 - 从 audio_json 的 start/end 字段重新读取边界"""
        self.stop_playback()
        
        # 清除待确认的边界变化，强制从 audio_json 重新读取
        self._pending_boundaries = None
        self._boundaries_initialized = False
        
        # 从 audio_json 的 start/end 字段重新初始化边界
        self._ensure_boundaries_initialized()
        
        print("✓ 已恢复剪辑区间到原始状态（从 audio_json 读取）")
        
        # 重绘时间轴
        self._draw_edit_timeline()
        self.update_duration_display()


    def confirm_edit_timeline_change(self):
        if self.media_type != "clip":
            return
        
        """确认剪辑区间变动 - 将时间轴的值保存到 audio_json"""
        self.stop_playback()
        
        # 获取边界：优先使用 _pending_boundaries，否则从 audio_json 计算
        if self._pending_boundaries is not None:
            boundaries = self._pending_boundaries
            print(f"📍 使用 pending_boundaries: {len(boundaries)} 个边界点")
        else:
            # 没有 pending 状态时，从当前 audio_json 计算边界
            boundaries = self._get_boundaries_from_audio_json()
            print(f"📍 从 audio_json 计算边界: {len(boundaries)} 个边界点")
        
        # 更新 audio_json 中每个场景的 start/end/duration（仅当有 pending 变更时）
        if self._pending_boundaries is not None and self.audio_json:
            for i in range(len(self.audio_json)):
                if i < len(boundaries) - 1:
                    start_time = boundaries[i]
                    end_time = boundaries[i + 1]
                    self.audio_json[i]['start'] = start_time
                    self.audio_json[i]['end'] = end_time
                    self.audio_json[i]['duration'] = end_time - start_time
            
            self._update_fresh_json_text()
        
        # 从 audio_json 重新计算边界（start/end 字段已在上面更新）
        self._pending_boundaries = None
        self._boundaries_initialized = False
        self._ensure_boundaries_initialized()
        
        # 重绘时间轴
        self._draw_edit_timeline()
        self.update_duration_display()



    def trim_video(self, audio_unchange):
        video_path = safe_file(self.source_video_path)
        audio_path = safe_file(self.source_audio_path)
        if not audio_path or not video_path:
            return

        start_time = float(self._get_start_time())
        end_time = float(self._get_end_time())
        duration = self.workflow.ffmpeg_processor.get_duration(video_path)
        
        if end_time <= start_time:
            messagebox.showerror("错误", "结束时间必须大于开始时间")
            return
        
        if end_time > duration:
            end_time = duration
        if start_time < 0:
            start_time = 0.0

        if start_time > 0.05 or abs(duration-end_time) > 0.05:
            video_path = self.workflow.ffmpeg_processor.trim_video( video_path, start_time, end_time, volume=1.0 )
            if audio_unchange:
                video_path = self.workflow.ffmpeg_processor.add_audio_to_video(video_path, audio_path, True)
            else:    
                self.source_audio_path = self.workflow.ffmpeg_audio_processor.audio_cut_fade( audio_path, start_time, end_time-start_time )

        if self.crop_start_x and self.crop_start_y:
            crop_x =self.crop_start_x
            crop_y = self.crop_start_y
            
            crop_width = self.workflow.ffmpeg_processor.width - crop_x
            crop_height = self.workflow.ffmpeg_processor.height - crop_y
            if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height: # 16:9
                if crop_width/crop_height <= self.workflow.ffmpeg_processor.width/self.workflow.ffmpeg_processor.height:
                    crop_height = int(crop_width/16.0*9.0)
                else:
                    crop_width = int(crop_height/9.0*16.0)
            else:  # 9:16
                if crop_width/crop_height <= self.workflow.ffmpeg_processor.width/self.workflow.ffmpeg_processor.height:
                    crop_height = int(crop_width/9.0*16.0)
                else:
                    crop_width = int(crop_height/16.0*9.0)
            video_path = self.workflow.ffmpeg_processor.resize_video(video_path, width=crop_width, height=crop_height, startx=crop_x, starty=crop_y )
            video_path = self.workflow.ffmpeg_processor.resize_video(video_path, width=self.workflow.ffmpeg_processor.width, height=self.workflow.ffmpeg_processor.height)

        self.source_video_path = video_path



    def _transcribe_recorded_audio(self):
        """转录录制的音频"""
        if self.audio_duration <= 30:
            return False

        print("🔄 开始转录录音...")
        
        # 使用音频转录器转录
        audio_json = self.transcriber.transcribe_with_whisper(
            self.source_audio_path, 
            self.workflow.language, 
            3,
            15
        )

        if not audio_json or len(audio_json) == 0:
            print("⚠️ 录音转录失败")
            return False

        duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
        audio_json[-1]["end"] = duration

        if self.transcribe_way == "single" or len(audio_json) == 1:
            all_captions = ". ".join([json_item["caption"] for json_item in audio_json])
            self.current_scene["caption"] = all_captions
            self.current_scene[self.SPEAKING_KEY] = all_captions
            self.audio_json = [self.current_scene]
        else: # multiple ~ only for self.media_type == "clip"
            raw_id = int((self.current_scene["id"]/100)*100)
            for item in audio_json:
                raw_id += 100
                item["id"] = raw_id
                item[self.SPEAKING_KEY] = item["caption"]
            self.audio_json = self.align_json_to_current_scene(audio_json)

        return True



    def toggle_playback(self):
        """Toggle media playback (audio or video+audio)"""
        if not self.av_playing:
            self.start_playback()
        else:
            self.pause_playback()


    def start_playback(self):
        self.av_playing = True
        was_paused = self.av_paused  # 记录是否是从暂停状态恢复
        self.av_paused = False
        self.play_button.config(text="⏸ 暂停")
        
        # 设置累计时间为当前播放位置，这样线程中的计算才正确
        # current_playback_time = pause_accumulated_time + elapsed_since_start
        self.pause_accumulated_time = self.current_playback_time
        
        # *** 关键修复：在启动视频和线程之前先设置计时基准 ***
        # 这样 update_video_frame 和更新线程从一开始就使用正确的时间
        self.playback_start_time = time.time()
        print(f"▶ 开始播放: current_time={self.current_playback_time:.2f}s, pause_accumulated={self.pause_accumulated_time:.2f}s, was_paused={was_paused}, playback_start_time={self.playback_start_time:.3f}")
        
        if self.source_video_path:
            # 如果视频捕获对象不存在，或者不是从暂停恢复，就重新创建
            if self.video_cap is None or (not was_paused and self.current_playback_time < 0.1):
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
            
            # 如果需要从指定位置开始播放（非暂停恢复），设置视频位置
            if not was_paused and self.current_playback_time > 0:
                fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 30
                start_frame = int(self.current_playback_time * fps)
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            elif was_paused:
                # 从暂停恢复，确保视频位置正确
                fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 30
                current_frame = int(self.current_playback_time * fps)
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
                print(f"🎬 视频从暂停位置恢复: {self.current_playback_time:.2f}s, 帧: {current_frame}")
            
            # Start video frame updates
            self.update_video_frame()
            
        if self.source_audio_path:
            # 只有在真正超过结束位置时才重置（不是接近）
            if self.current_playback_time >= self.audio_duration:
                print(f"⚠️ 播放位置 {self.current_playback_time:.2f}s 已超过音频时长 {self.audio_duration:.2f}s，重置到开始")
                self.current_playback_time = 0.0
                self.pause_accumulated_time = 0.0
                self.playback_start_time = time.time()  # 重置后更新时间基准
                was_paused = False
            
            if was_paused and self.current_playback_time > 0:
                # 从暂停状态恢复，使用 unpause
                pygame.mixer.music.unpause()
                print(f"🎵 音频从暂停位置恢复播放: {self.current_playback_time:.2f}s")
            else:
                # 首次播放或从指定位置开始
                pygame.mixer.music.stop()
                pygame.mixer.music.load(self.source_audio_path)
                pygame.mixer.music.play(start=self.current_playback_time)
                print(f"🎵 音频从 {self.current_playback_time:.2f}s 开始播放")
    
        self.start_time_update_thread()


    def pause_playback(self):
        """Pause audio-only playback"""
        # 立即设置状态，防止更新线程继续运行
        self.av_playing = False
        self.av_paused = True
        
        # 先计算当前播放位置
        if self.playback_start_time is not None:
            elapsed_since_start = time.time() - self.playback_start_time
            self.current_playback_time = self.pause_accumulated_time + elapsed_since_start
            print(f"⏸ 暂停播放: current_time={self.current_playback_time:.2f}s, pause_accumulated={self.pause_accumulated_time:.2f}s, elapsed={elapsed_since_start:.2f}s")
        else:
            print(f"⚠️ 暂停时 playback_start_time 为 None")
        
        # 更新按钮
        self.play_button.config(text="▶ 播放")
        
        # Cancel video frame updates
        if self.video_after_id:
            self.dialog.after_cancel(self.video_after_id)
            
        # Pause audio (使用 pause 而不是 stop，这样可以保留播放位置)
        if self.source_audio_path:
            print(f"⏸ 正在暂停音频播放，位置: {self.current_playback_time:.2f}s")
            pygame.mixer.music.pause()
        
        print(f"⏸ 暂停完成，最终位置: {self.current_playback_time:.2f}s")
        # 更新线程会在下一次迭代（100ms内）检测到状态变化并退出


    def stop_playback(self):
        """Stop media playback (audio or video+audio)"""
        print(f"⏹ stop_playback 被调用: av_playing={self.av_playing}, av_paused={self.av_paused}, current_time={self.current_playback_time:.2f}s")
        
        # 如果已经暂停，这是一个错误调用（可能是竞态条件），直接返回
        if self.av_paused:
            print(f"⚠️ stop_playback 在暂停状态下被调用，忽略（竞态条件）")
            return
        
        self.av_playing = False
        self.av_paused = False
        self.play_button.config(text="▶ 播放")
        self.current_playback_time = 0.0
        self.pause_accumulated_time = 0.0
        
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



    def transcribe_audio(self, transcribe_way):
        self.transcribe_way = transcribe_way
        if self.media_type != 'clip' and self.media_type != 'narration':
            return
        self._transcribe_recorded_audio()
        self._update_fresh_json_text()


    def remix_conversation(self, mode, transcribe):
        if mode == "connect_prev" or mode == "connect_next" :
            self.transcribe_way = "single"
        else:
            self.transcribe_way = mode
        self.dialog.title( f"{self.media_type_names.get(self.media_type)} - {self.transcribe_way}" )
        
        if self.media_type != 'clip' and self.media_type != 'narration':
            return

        if transcribe:
            self._transcribe_recorded_audio()
            self._update_fresh_json_text()

        #topic = config_channel.CHANNEL_CONFIG[project_manager.PROJECT_CONFIG.get('channel', 'default')]["topic"]
        refresh_conversation = self.fresh_json_text.get(1.0, tk.END).strip()
        if mode == "connect_next":
            selected_prompt = config_channel.CHANNEL_CONFIG[self.workflow.channel]["channel_prompt"]["connection"]
            selected_prompt_example_file = self.workflow.channel + "_connection.json"
            refresh_json = [
                {
                    "name": "connection_addon_content",
                    "speaking": refresh_conversation
                },
                {
                    "name":"previous_scene",
                    "explicit": self.current_scene.get("explicit", "explicit"),
                    "implicit": self.current_scene.get("implicit", "implicit"),
                    "speaking": self.current_scene.get("speaking", ""),
                    "speaker": self.current_scene.get("speaker", ""),
                    "voiceover": self.current_scene.get("voiceover", "")
                },
                {
                    "name":"next_scene",
                    "explicit": self.next_scene.get("explicit", "explicit"),
                    "implicit": self.next_scene.get("implicit", "implicit"),
                    "speaking": self.next_scene.get("speaking", ""),
                    "speaker": self.next_scene.get("speaker", ""),
                    "voiceover": self.next_scene.get("voiceover", "")
                }
            ]
            refresh_conversation = json.dumps(refresh_json, indent=2, ensure_ascii=False)
        elif mode == "connect_prev":
            selected_prompt = config_channel.CHANNEL_CONFIG[self.workflow.channel]["channel_prompt"]["connection"]
            selected_prompt_example_file = self.workflow.channel + "_connection.json"
            refresh_json = [
                {
                    "name": "connection_addon_content",
                    "speaking": refresh_conversation
                },
                {
                    "name":"previous_scene",
                    "explicit": self.previous_scene.get("explicit", "explicit"),
                    "implicit": self.previous_scene.get("implicit", "implicit"),
                    "speaking": self.previous_scene.get("speaking", ""),
                    "speaker": self.previous_scene.get("speaker", ""),
                    "voiceover": self.previous_scene.get("voiceover", "")
                },
                {
                    "name":"next_scene",
                    "explicit": self.current_scene.get("explicit", "explicit"),
                    "implicit": self.current_scene.get("implicit", "implicit"),
                    "speaking": self.current_scene.get("speaking", ""),
                    "speaker": self.current_scene.get("speaker", ""),
                    "voiceover": self.current_scene.get("voiceover", "")
                }
            ]
            refresh_conversation = json.dumps(refresh_json, indent=2, ensure_ascii=False)
        else:
            refresh_json = None
            if refresh_conversation:
                try:
                    refresh_json = json.loads(refresh_conversation)
                    refresh_json_copy = []
                    for item in refresh_json:
                        new_item = {
                            "explicit": self.current_scene.get("explicit", "explicit"),
                            "implicit": self.current_scene.get("implicit", "implicit"),
                            "story_details": self.current_scene.get("story_details", ""),
                            "speaking": item.get("speaking", ""),
                            "speaker": item.get("speaker", ""),
                            "voiceover": item.get("voiceover", "")
                        }
                        refresh_json_copy.append(new_item)
                    refresh_conversation = json.dumps(refresh_json_copy, indent=2, ensure_ascii=False)
                except:
                    refresh_json = None

            if not refresh_json:
                refresh_json = [
                    {
                        "name": self.current_scene.get("name", "story"),
                        "explicit": self.current_scene.get("explicit", "explicit"),
                        "implicit": self.current_scene.get("implicit", "implicit"),
                        "story_details": self.current_scene.get("story_details", ""),
                        "speaking": refresh_conversation if refresh_conversation else self.current_scene.get("speaking", ""),
                        "speaker": self.current_scene.get("speaker", ""),
                        "voiceover": refresh_conversation if refresh_conversation else self.current_scene.get("voiceover", "")
                    }
                ]
                refresh_conversation = json.dumps(refresh_json, indent=2, ensure_ascii=False)

            selected_prompt = config_channel.CHANNEL_CONFIG[self.workflow.channel]["channel_prompt"][self.current_scene["name"]]
            selected_prompt_example_file = self.workflow.channel + "_" + self.current_scene["name"] + ".json"

        # read file from media folder
        example_file = os.path.join(os.path.dirname(__file__), "../media", selected_prompt_example_file)
        with open(example_file, "r", encoding="utf-8") as f:
            selected_prompt_example_text = f.read()
        selected_prompt_example = parse_json_from_text(selected_prompt_example_text)
        if selected_prompt_example is None:
            messagebox.showerror("错误", f"无法解析示例文件: {example_file}")
            return

        if self.transcribe_way == "multiple":
            # Convert array back to JSON string for formatting
            example_json_str = json.dumps(selected_prompt_example, indent=2, ensure_ascii=False)
            if len(self.audio_json) > 1:
                selected_prompt = selected_prompt.format(json=f"json array holding {len(self.audio_json)} scenes", example=example_json_str)
            else:
                selected_prompt = selected_prompt.format(json="json array holding scenes", example=example_json_str)
        else:
            # Use first element of the array
            selected_prompt_example_item = selected_prompt_example[0] if selected_prompt_example else {}
            example_json_str = json.dumps(selected_prompt_example_item, indent=2, ensure_ascii=False)
            selected_prompt = selected_prompt.format(json="a single json item describing a scene", example=example_json_str)
        #format_args = selected_prompt.get("format_args", {}).copy()  # 复制预设参数

        new_scenes = self.llm_api.generate_json(
            system_prompt=selected_prompt,
            user_prompt=refresh_conversation,
            expect_list=True
        )
        if not new_scenes or len(new_scenes) == 0:
            return

        if self.transcribe_way == "single" or (len(self.audio_json) == 1 and len(new_scenes) == 1):
            self.current_scene[self.SPEAKER_KEY] = new_scenes[0].get(self.SPEAKER_KEY, "")
            self.current_scene[self.SPEAKER_KEY+"_audio"] = self.source_audio_path
            self.current_scene["actions"] = new_scenes[0].get("actions", "")
            self.current_scene["visual"] = new_scenes[0].get("visual", "")
            self.current_scene["start"] = 0.0
            self.current_scene["extend"] = 0.0
            self.current_scene["end"] = self.audio_duration
            self.current_scene["duration"] = self.audio_duration
            self.current_scene["caption"] = ". ".join([item.get("caption", "") for item in new_scenes])
            self.current_scene["speaking"] = ". ".join([item.get("speaking", "") for item in new_scenes])
            self.current_scene["voiceover"] = ". ".join([item.get("voiceover", "") for item in new_scenes])
            self.audio_json = [self.current_scene]

        else:
            start_id = self.current_scene.get("id", 0)
            start_time = 0.0
            for i, scene in enumerate(new_scenes):
                fresh_scene = self.audio_json[i] if i < len(self.audio_json) else self.audio_json[-1]
                scene["caption"] = fresh_scene["caption"]
                duration = fresh_scene.get("duration", self.audio_duration)
                scene["duration"] = duration if len(self.audio_json) == len(new_scenes) else self.audio_duration / len(new_scenes)
                scene["start"] = start_time
                scene["extend"] = 0.0
                start_time = start_time + scene["duration"]
                scene["end"] = start_time
                scene["id"] = start_id + 1
                start_id = scene["id"]

                scene[self.SPEAKER_KEY+"_audio"] = None

            self.audio_json = self.align_json_to_current_scene(new_scenes)

        self._update_fresh_json_text()


    def align_json_to_current_scene(self, json_array):
        new_json_array = []
        for item in json_array:
            new_item = self.current_scene.copy()
            new_item["name"] = self.current_scene.get("name", "story")
            new_item["explicit"] = self.current_scene.get("explicit", "explicit")
            new_item["implicit"] = self.current_scene.get("implicit", "implicit")

            if "id" in item:
                new_item["id"] = item["id"]
            if self.SPEAKER_KEY in item:
                new_item[self.SPEAKER_KEY] = item[self.SPEAKER_KEY]
            if self.SPEAKER_KEY+"_audio" in item:
                new_item[self.SPEAKER_KEY+"_audio"] = item[self.SPEAKER_KEY+"_audio"]
            if "duration" in item:
                new_item["duration"] = item["duration"]
            if "visual" in item:
                new_item["visual"] = item["visual"]
            if "actions" in item:
                new_item["actions"] = item["actions"]
            if "start" in item:
                new_item["start"] = item["start"]
            if "end" in item:
                new_item["end"] = item["end"]
            if "caption" in item:
                new_item["caption"] = item["caption"]
            if "speaking" in item:
                new_item["speaking"] = item["speaking"]
            if "voiceover" in item:
                new_item["voiceover"] = item["voiceover"]
            new_json_array.append(new_item)
        return new_json_array


    def regenerate_audio(self):
        fresh_text = self.fresh_json_text.get(1.0, tk.END).strip()
        try:
            fresh_json = json.loads(fresh_text)
            if self.transcribe_way == "single":
                self.current_scene[self.SPEAKER_KEY] = fresh_json[0].get(self.SPEAKER_KEY, "")
                self.current_scene["actions"] = fresh_json[0].get("actions", "")
                self.current_scene["visual"] = fresh_json[0].get("visual", "")
                self.current_scene["caption"] = ". ".join([item.get("caption", "") for item in fresh_json])
                self.current_scene["speaking"] = ". ".join([item.get("speaking", "") for item in fresh_json])
                self.current_scene["voiceover"] = ". ".join([item.get("voiceover", "") for item in fresh_json])
                self.audio_json = [self.current_scene]
            else:
                self.audio_json = self.align_json_to_current_scene(fresh_json)
        except:
            messagebox.showerror("错误", "Fresh JSON格式不正确")
            return

        #self.audio_json, self.source_audio_path = self.parent.workflow.regenerate_audio(self.audio_json, self.workflow.language)
        lang = "chinese" if self.workflow.language == "zh" or self.workflow.language == "tw" else "english"
        start_time = 0.0
        for json_item in self.audio_json:
            speaker = json_item[self.SPEAKER_KEY]
            content = json_item[self.SPEAKING_KEY]
            actions = json_item["actions"]
            tts_wav = self.workflow.regenerate_audio_item(speaker, content, actions, lang)
            if tts_wav:
                olda, a = refresh_scene_media(json_item, self.SPEAKER_KEY+"_audio", ".wav", tts_wav, True)
                refresh_scene_media(json_item, self.media_type+"_audio", ".wav", a, True)
                v = self.workflow.ffmpeg_processor.add_audio_to_video(self.source_video_path, json_item[self.media_type+"_audio"])
                refresh_scene_media(json_item, self.media_type, ".mp4", v)
                if self.media_type == "clip":
                    json_item["duration"] = self.workflow.ffmpeg_audio_processor.get_duration(json_item[self.media_type+"_audio"])
                    json_item["extend"] = 1.0
                    json_item["start"] = start_time
                    start_time = start_time + json_item["duration"]
                    json_item["end"] = start_time
                    json_item["caption"] = json_item["speaking"]
            else:
                json_item[self.media_type+"_audio"] = None
                json_item[self.SPEAKER_KEY+"_audio"] = None
                json_item[self.media_type] = None
                if self.media_type == "clip":
                    json_item["duration"] = 0.0
                    json_item["start"] = 0.0
                    json_item["end"] = 0.0
                    json_item["caption"] = None

        # filter out json_item with clip_audio is None
        temp_json = [json_item for json_item in self.audio_json if json_item[self.SPEAKER_KEY+"_audio"] is not None]
        self.source_audio_path = self.workflow.ffmpeg_audio_processor.concat_audios([json_item[self.SPEAKER_KEY+"_audio"] for json_item in temp_json])
        self.audio_duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
        self._set_start_time(0.0)
        self._set_end_time(self.audio_duration)

        self.source_video_path = self.workflow.ffmpeg_processor.adjust_video_to_duration( self.source_video_path, self.audio_duration )

        self._update_fresh_json_text()

        self.refresh_edit_timeline()
        self.draw_waveform_placeholder()
        # pop up a messagebox to confirm the audio is regenerated
        messagebox.showinfo("成功", "音频已重新生成")


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
            sec = int(elapsed % 60)
            time_str = f"{minutes:02d}:{sec:02d}"
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
            self.source_video_path = self.workflow.ffmpeg_processor.add_audio_to_video(self.source_video_path, self.source_audio_path, True, True)
            
            # 更新音频时长和时间选择器
            self.audio_duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
            self._set_start_time(0.0)
            self._set_end_time(self.audio_duration)
            
            # 更新时间选择器的最大值
            for widget in self.dialog.winfo_children():
                if isinstance(widget, ttk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Spinbox):
                            try:
                                child.configure(to=self.audio_duration)
                            except:
                                pass
            # 重新绘制波形
            self.draw_waveform_placeholder()
            
            messagebox.showinfo("成功", f"录音完成！\n文件保存到: {os.path.basename(recorded_file_path)}\n时长: {self.audio_duration:.2f} 秒")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存录音失败: {str(e)}")
            print(f"保存录音错误: {e}")



    def confirm_replacement(self):
        self.confirm_edit_timeline_change()
        video_path = self.source_video_path
        
        v = self.current_scene.get(self.video_field, None)
        a = self.current_scene.get(self.audio_field, None)
        i = self.current_scene.get(self.image_field, None)
        if i != self.source_image_path:
            refresh_scene_media(self.current_scene, self.image_field, ".webp", self.source_image_path, True)
        if a != self.source_audio_path and self.workflow.ffmpeg_audio_processor.get_duration(a) != self.audio_duration:
            refresh_scene_media(self.current_scene, self.audio_field, ".wav", self.source_audio_path, True)
        if v != self.source_video_path and self.workflow.ffmpeg_processor.get_duration(v) != self.audio_duration:
            #v = self.workflow.ffmpeg_processor.add_audio_to_video(self.source_video_path, self.source_audio_path, True)
            refresh_scene_media(self.current_scene, self.video_field, ".mp4", self.source_video_path, True)

        # 执行音视频切割（只有在边界被手动调整后才执行）
        # 判断是否需要切割：
        # 1. 有多个场景
        # 2. 场景的边界不是默认的（即被手动编辑过）

        if self.media_type != "clip" or len(self.audio_json) == 1:
            scene = self.audio_json[0]
            start = scene.get('start', 0)
            end = scene.get('end', self.audio_duration)
            # 如果是完整音频（从0到结束），不需要切割
            if abs(start) > 0.1 or abs(end - self.audio_duration) > 0.1:
                clip_wav = self.workflow.ffmpeg_audio_processor.audio_cut_fade(self.source_audio_path, start, end - start)
                refresh_scene_media(self.current_scene, self.SPEAKER_KEY+"_audio", ".wav", clip_wav, True)
                refresh_scene_media(self.current_scene, self.audio_field, ".wav", clip_wav, True)
                v = self.workflow.ffmpeg_processor.trim_video(self.source_video_path, start, end)
                refresh_scene_media(self.current_scene, self.video_field, ".mp4", v, True)
            else:
                v = self.source_video_path

            first_image = self.current_scene.get(self.image_field, None)
            if  not first_image or not os.path.exists(first_image):
                first_image = self.workflow.ffmpeg_processor.extract_frame(v, True)
                refresh_scene_media(self.current_scene, self.image_field, ".webp", first_image)
            last_image = self.workflow.ffmpeg_processor.extract_frame(v, False)
            refresh_scene_media(self.current_scene, self.image_field+"_last", ".webp", last_image, True)

        elif self.clip_multiple_audio_changed():
            print(f"✓ 确认剪辑区间，共 {len(self.audio_json)} 个场景，开始切割音视频...")
            for i, item in enumerate(self.audio_json):
                duration = item.get("duration", 0)
                if duration <= 0:
                    print(f"⚠️ 场景 {i+1} duration={duration}，跳过")
                    continue
                clip_wav = self.workflow.ffmpeg_audio_processor.audio_cut_fade(self.source_audio_path, item["start"], item["duration"])
                olda, item["speaker_audio"] = refresh_scene_media(item, "clip_audio", ".wav", clip_wav)
                v = self.workflow.ffmpeg_processor.trim_video(self.source_video_path, item["start"], item["end"])
                refresh_scene_media(item, "clip", ".mp4", v)
                first_image = item.get(self.image_field, None)
                if  not first_image or not os.path.exists(first_image):
                    first_image = self.workflow.ffmpeg_processor.extract_frame(v, True)
                    refresh_scene_media(item, self.image_field, ".webp", first_image)
                last_image = self.workflow.ffmpeg_processor.extract_frame(v, False)
                refresh_scene_media(item, self.image_field+"_last", ".webp", last_image, True)

            print(f"✓ 音视频切割完成")
        else:
            print(f"ℹ️ 边界未被手动调整，无需切割")
        
        self.result = {
            'audio_json': self.audio_json,
            'transcribe_way': self.transcribe_way
        }
        
        self.close_dialog()


    def clip_multiple_audio_changed(self):
        if self.media_type != "clip" or len(self.audio_json) == 1:
            return False
        
        # 检查场景是否已经有独立的音频文件
        scenes_need_cutting = 0
        for i, scene in enumerate(self.audio_json):
            # 检查是否有 speaker_audio 字段
            scene_audio = scene.get(self.SPEAKER_KEY+"_audio", None)
            if not scene_audio or not os.path.exists(scene_audio):
                # 没有音频文件或文件不存在，需要切割
                scenes_need_cutting += 1
            elif scene_audio == self.source_audio_path:
                # 音频文件就是源文件，说明没有被切割过，需要切割
                scenes_need_cutting += 1
        
        # 如果至少有一个场景需要切割，就返回 True
        if scenes_need_cutting > 0:
            print(f"📊 检测到 {scenes_need_cutting}/{len(self.audio_json)} 个场景需要切割")
            return True
        
        print(f"📊 所有 {len(self.audio_json)} 个场景都已有独立音频，无需切割")
        return False



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
    


    def start_time_update_thread(self):
        """Start a thread to update playback time"""
        def update_time():
            iteration = 0
            # 第一次迭代时等待音频稳定，然后重置时间基准
            first_iteration = True
            
            while self.av_playing and not self.av_paused:
                try:
                    # 再次检查状态，防止暂停后仍然更新时间
                    if not self.av_playing or self.av_paused:
                        print(f"DEBUG: 更新线程在迭代 {iteration} 时检测到状态改变，退出")
                        break
                    
                    # 第一次迭代：等待音频稳定后重置基准
                    if first_iteration:
                        print(f"DEBUG: 首次迭代，等待音频稳定...")
                        time.sleep(0.15)  # 等待150ms
                        # 同步更新基准时间，避免累积误差
                        self.pause_accumulated_time = self.current_playback_time
                        self.playback_start_time = time.time()
                        first_iteration = False
                        print(f"DEBUG: 时间基准已同步: pause_acc={self.pause_accumulated_time:.2f}s, start_time={self.playback_start_time:.3f}")
                        iteration += 1
                        continue
                        
                    if self.playback_start_time is not None:
                        elapsed_since_start = time.time() - self.playback_start_time
                        
                        # 只在播放状态下更新时间
                        if self.av_playing and not self.av_paused:
                            calculated_time = self.pause_accumulated_time + elapsed_since_start
                            
                            # 防止时间异常跳跃
                            time_diff = calculated_time - self.current_playback_time
                            if time_diff < -0.2:
                                # 时间向后跳超过200ms，可能是bug，重置基准
                                print(f"⚠️ 时间向后跳跃: {self.current_playback_time:.2f}s -> {calculated_time:.2f}s，重置基准")
                                self.pause_accumulated_time = self.current_playback_time
                                self.playback_start_time = time.time()
                            elif time_diff > 0.3:
                                # 时间向前跳超过300ms，可能是音频延迟，重置基准
                                print(f"⚠️ 时间向前跳跃: {self.current_playback_time:.2f}s -> {calculated_time:.2f}s，重置基准")
                                self.pause_accumulated_time = self.current_playback_time
                                self.playback_start_time = time.time()
                            else:
                                # 正常更新
                                self.current_playback_time = calculated_time
                            
                            # 每秒打印一次调试信息
                            if iteration % 10 == 0:
                                print(f"DEBUG: 更新 {iteration}: pause_acc={self.pause_accumulated_time:.2f}s + elapsed={elapsed_since_start:.2f}s = {self.current_playback_time:.2f}s")
                            
                            # Update display in main thread
                            self.dialog.after(0, self.update_play_time_display)
                            
                            # Check if we've reached the end
                            if self.current_playback_time >= self.audio_duration + 0.5:
                                print(f"⏹ 到达结束: {self.current_playback_time:.2f}s >= {self.audio_duration:.2f}s")
                                if self.av_playing and not self.av_paused:
                                    self.dialog.after(0, self.stop_playback)
                                break
                        else:
                            print(f"DEBUG: 更新线程检测到状态改变，退出")
                            break
                    
                    iteration += 1
                    time.sleep(0.1)  # Update every 100ms
                except Exception as e:
                    print(f"ERROR: 更新线程异常: {e}")
                    import traceback
                    traceback.print_exc()
                    break
            
            print(f"DEBUG: 更新线程已退出，迭代: {iteration}")
        
        # Start the update thread
        if self.av_playing:
            print(f"DEBUG: 启动更新线程，pause_acc={self.pause_accumulated_time:.2f}s, current={self.current_playback_time:.2f}s")
            threading.Thread(target=update_time, daemon=True).start()

    

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
                
                # 安全检查：如果计算的时间明显不合理，使用当前时间
                if target_time < 0 or target_time > self.audio_duration + 1.0:
                    print(f"⚠️ 视频目标时间异常: {target_time:.2f}s (pause_acc={self.pause_accumulated_time:.2f}s, elapsed={elapsed_since_start:.2f}s)")
                    target_time = self.current_playback_time
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
                # 不要在这里更新 current_playback_time，因为更新线程已经在处理
                # 这里只负责显示正确的视频帧
                current_frame = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
                # self.current_playback_time 由更新线程维护，这里不修改
                
                # 不需要在这里更新显示，更新线程会处理
                # self.update_play_time_display()
                
                # Check if we're still in the selected time range
                try:
                    end_time = self._get_end_time()
                    # 添加 0.5 秒容差，避免在接近结束时误判
                    if self.current_playback_time >= end_time + 0.5:
                        # Reached end of selected range
                        print(f"⏹ 视频播放到达结束位置: {self.current_playback_time:.2f}s >= {end_time:.2f}s")
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


    def _extract_speaker_from_json(self):
        """从 fresh_json_text 中提取 narrator 和 speaker 的值，并设置到下拉框"""
        if self._updating_from_json:
            return
        
        try:
            # 获取 fresh_json_text 的内容
            fresh_text = self.fresh_json_text.get(1.0, tk.END).strip()
            if not fresh_text:
                return
            
            # 尝试解析为 JSON
            fresh_json = parse_json_from_text(fresh_text)
            if fresh_json is None or not isinstance(fresh_json, list) or len(fresh_json) == 0:
                return
            
            # 设置标志，防止循环更新
            self._updating_from_json = True
            
            speaker_found = False
            for item in fresh_json:
                if not isinstance(item, dict):
                    continue
                if not speaker_found and self.SPEAKER_KEY in item:
                    speaker_value = str(item[self.SPEAKER_KEY]).strip()
                    if speaker_value:
                        for actor in self.ACTORS:
                            if actor and speaker_value.startswith(actor):
                                try:
                                    self.speaker.set(actor)
                                    speaker_found = True
                                    break
                                except:
                                    pass
                if speaker_found:
                    break
            
        except Exception as e:
            print(f"⚠️ 从 JSON 提取 narrator/speaker 失败: {e}")
        finally:
            # 重置标志
            self._updating_from_json = False


    def _update_fresh_json_text(self):
        """更新 fresh_json_text 的内容并触发提取 narrator 和 speaker 值"""
        self.fresh_json_text.delete(1.0, tk.END)
        self.fresh_json_text.insert(1.0, json.dumps(self.audio_json, indent=2, ensure_ascii=False))
        # 触发提取 narrator 和 speaker 值
        self._extract_speaker_from_json()
        # 刷新剪辑时间轴
        self.refresh_edit_timeline()


    def on_speaker_changed(self, event=None):
        if self._updating_from_json:
            return
        
        try:
            person_value = self.speaker.get()
            if not person_value:
                return

            # 设置标志，避免触发文本改变事件
            self._updating_from_json = True
            
            for item in self.audio_json:
                if isinstance(item, dict):
                    person = item.get(self.SPEAKER_KEY, "")
                    for actor in self.ACTORS:
                        person = person.replace(actor, "")
                    item[self.SPEAKER_KEY] = person_value + person

            self._update_fresh_json_text()
        
        except Exception as e:
            print(f"⚠️ 更新 speaker 字段失败: {e}")
        finally:
            self._updating_from_json = False


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



    def on_image_dnd_drop(self, event):
        """处理图片拖放"""
        file_path = event.data.strip('{}').strip('"')
        if is_image_file(file_path):
            self.handle_new_media(file_path)


    def on_audio_dnd_drop(self, event):
        """处理音频拖放"""
        file_path = event.data.strip('{}').strip('"')
        if is_audio_file(file_path):
            self.handle_new_media(file_path)


    def process_new_media(self, av_path):
        if is_image_file(av_path):
            self.source_image_path = av_path
            self.source_video_path = self.workflow.ffmpeg_processor.image_audio_to_video(self.source_image_path, self.source_audio_path)
        elif is_audio_file(av_path):
            self.source_audio_path = self.workflow.ffmpeg_audio_processor.to_wav(av_path)
            self.source_video_path = self.workflow.ffmpeg_processor.add_audio_to_video(self.source_video_path, self.source_audio_path, True, True)
        elif is_video_file(av_path):
            self.source_video_path = av_path  # self.workflow.ffmpeg_processor.resize_video(av_path, width=self.workflow.ffmpeg_processor.width, height=None)
            if self.replace_media_audio=="keep":
                self.source_audio_path = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(self.source_video_path)
            else:
                self.source_video_path = self.workflow.ffmpeg_processor.add_audio_to_video(self.source_video_path, self.source_audio_path, True, True)

        self.audio_duration = self.workflow.ffmpeg_audio_processor.get_duration(self.source_audio_path)
        self._set_end_time(self.audio_duration)
        self._set_start_time(0.0)


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

        self.process_new_media(av_path)
        # 重置播放状态
        self.current_playback_time = 0.0
        self.pause_accumulated_time = 0.0
        self.playback_start_time = None

        self.update_play_time_display()
        self.update_duration_display()

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
        # Get canvas dimensions
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            return
        # Get canvas coordinates
        canvas_x = event.x
        canvas_y = event.y
        # Calculate start and end canvas coordinates
        start_canvas_x = min(self.selection_start_x, canvas_x)
        start_canvas_y = min(self.selection_start_y, canvas_y)
        end_canvas_x = max(self.selection_start_x, canvas_x)
        end_canvas_y = max(self.selection_start_y, canvas_y)
        # Default canvas coordinates
        default_start_x = 0
        default_start_y = 0
        default_end_x = canvas_width
        default_end_y = canvas_height
        # Get image bounds on canvas
        image_bounds = self.get_image_bounds()
        if not image_bounds:
            return
        # Check if each coordinate is within canvas bounds (0 to canvas_width/height)
        start_x_in_bounds = 0 <= start_canvas_x <= canvas_width
        start_y_in_bounds = 0 <= start_canvas_y <= canvas_height
        end_x_in_bounds = 0 <= end_canvas_x <= canvas_width
        end_y_in_bounds = 0 <= end_canvas_y <= canvas_height
        # Convert each coordinate individually
        # Use actual coordinate if in canvas bounds, otherwise use default
        # Then clamp to image bounds
        start_x_canvas = start_canvas_x if start_x_in_bounds else default_start_x
        start_y_canvas = start_canvas_y if start_y_in_bounds else default_start_y
        # Clamp coordinates to image bounds
        start_x_canvas = max(image_bounds['left'], min(image_bounds['right'], start_x_canvas))
        start_y_canvas = max(image_bounds['top'], min(image_bounds['bottom'], start_y_canvas))
        
        start_x_video, start_y_video = self.canvas_to_video_coords(start_x_canvas, start_y_canvas)
        # If conversion failed, try with image bounds
        if start_x_video is None or start_y_video is None:
            start_x_video, start_y_video = self.canvas_to_video_coords(image_bounds['left'], image_bounds['top'])
        # For end_x and end_y: use end_canvas_x/y if in bounds, else defaults
        end_x_canvas = end_canvas_x if end_x_in_bounds else default_end_x
        end_y_canvas = end_canvas_y if end_y_in_bounds else default_end_y
        # Clamp coordinates to image bounds
        end_x_canvas = max(image_bounds['left'], min(image_bounds['right'], end_x_canvas))
        end_y_canvas = max(image_bounds['top'], min(image_bounds['bottom'], end_y_canvas))
        
        end_x_video, end_y_video = self.canvas_to_video_coords(end_x_canvas, end_y_canvas)
        # If conversion failed, try with image bounds
        if end_x_video is None or end_y_video is None:
            end_x_video, end_y_video = self.canvas_to_video_coords(image_bounds['right'], image_bounds['bottom'])
        
        # Final check - if any conversion still failed, return early
        if start_x_video is None or start_y_video is None or end_x_video is None or end_y_video is None:
            return
        if start_x_video > end_x_video:
            start_x_video, end_x_video = end_x_video, start_x_video
        if start_y_video > end_y_video:
            start_y_video, end_y_video = end_y_video, start_y_video
        # Update crop parameters
        self.crop_start_x = max(0, int(start_x_video))
        self.crop_start_y = max(0, int(start_y_video))
        crop_w = max(1, int(end_x_video - start_x_video))
        crop_h = max(1, int(end_y_video - start_y_video))
        # Store crop dimensions
        self.crop_width = crop_w
        self.crop_height = crop_h
        # Update UI controls
        self.crop_x_var.set(self.crop_start_x)
        self.crop_y_var.set(self.crop_start_y)
        self.crop_width_var.set(crop_w)
        print(f"✓ 选择裁剪区域: ({self.crop_start_x}, {self.crop_start_y}), 尺寸: {crop_w}x{crop_h}")

    
    def get_image_bounds(self):
        """Get the actual image bounds on canvas"""
        try:
            # Get displayed image dimensions (from first frame)
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
            return {
                'left': img_left,
                'right': img_right,
                'top': img_top,
                'bottom': img_bottom
            }
        except Exception as e:
            print(f"⚠️ 获取图像边界失败: {e}")
            return None


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



    def try_update_scene_visual_fields(self, current_scene, scene_data):
        # 显示对比对话框，让用户比较和编辑
        updated_data = self._show_scene_comparison_dialog(current_scene, scene_data)
        if updated_data is None:
            return  # 用户取消

        content = scene_data.get("speaking", "")
        if content:
            current_scene["speaking"] = content
        story = scene_data.get("visual", "")
        speaker = scene_data.get("speaker", "")
        if speaker:
            current_scene["speaker"] = speaker
        if story:
            current_scene["visual"] = story
        actions = scene_data.get("actions", "")
        if actions:
            current_scene["actions"] = actions
        #cinematography = scene_data.get("cinematography", "")
        #if cinematography:
        #    # 规范化 cinematography 字段，确保正确处理 JSON 字符串
        #    current_scene["cinematography"] = self._normalize_json_string_field(cinematography)
        narrator = scene_data.get("narrator", "")
        if narrator:
            current_scene["narrator"] = narrator
        actions = scene_data.get("actions", "")
        if actions:
            current_scene["actions"] = actions
        kernel = scene_data.get("kernel", "")
        if kernel:
            current_scene["kernel"] = kernel

        self.save_scenes_to_json()



    def _show_scene_comparison_dialog(self, current_scene, new_scene_data):
        """显示场景数据对比对话框，让用户比较和编辑字段值"""
        import tkinter as tk
        import tkinter.ttk as ttk
        import tkinter.scrolledtext as scrolledtext
        
        # 字段名称映射
        field_labels = {
            "speaking": "内容",
            "speaker": "主体",
            "visual": "画面",
            "action": "动作",
            "voiceover": "旁白"
            #"cinematography": "电影摄影",
        }
        
        # 需要对比的字段列表
        fields_to_compare = list(field_labels.keys())
        
        # 创建对话框
        try:
            root = tk._default_root
            if root is None:
                root = tk.Tk()
                root.withdraw()
        except:
            root = tk.Tk()
            root.withdraw()
        
        dialog = tk.Toplevel(root)
        dialog.title("对比和编辑场景数据")
        dialog.geometry("1200x800")
        dialog.transient(root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 1200) // 2
        y = (dialog.winfo_screenheight() - 800) // 2
        dialog.geometry(f"1200x800+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text=f"新旧场景数据对比",  font=('TkDefaultFont', 11, 'bold'))
        title_label.pack(pady=(0, 10))
        
        # 创建滚动框架
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 存储编辑控件和复选框
        comparison_widgets = {}
        
        # 为每个字段创建对比行
        for field in fields_to_compare:
            field_frame = ttk.LabelFrame(scrollable_frame, text=field_labels[field], padding=5)
            field_frame.pack(fill=tk.X, pady=5, padx=5)
            
            # 复选框：是否更新此字段
            checkbox_frame = ttk.Frame(field_frame)
            checkbox_frame.pack(fill=tk.X, pady=(0, 5))
            
            update_var = tk.BooleanVar(value=False)
            checkbox = ttk.Checkbutton(checkbox_frame, text="更新此字段", variable=update_var)
            checkbox.pack(side=tk.LEFT)
            
            # 两列布局：当前值 vs 新值
            comparison_frame = ttk.Frame(field_frame)
            comparison_frame.pack(fill=tk.BOTH, expand=True)
            
            # 当前值列
            current_frame = ttk.Frame(comparison_frame)
            current_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
            ttk.Label(current_frame, text="当前值:", font=('TkDefaultFont', 9, 'bold')).pack(anchor='w')
            current_text = scrolledtext.ScrolledText(current_frame, wrap=tk.WORD, height=3, width=50)
            current_text.pack(fill=tk.BOTH, expand=True)
            current_value = str(current_scene.get(field, ""))
            current_text.insert('1.0', current_value)
            current_text.config(state=tk.DISABLED)  # 当前值只读
            
            # 新值列（可编辑）
            new_frame = ttk.Frame(comparison_frame)
            new_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
            ttk.Label(new_frame, text="新值（可编辑）:", font=('TkDefaultFont', 9, 'bold')).pack(anchor='w')
            new_text = scrolledtext.ScrolledText(new_frame, wrap=tk.WORD, height=3, width=50)
            new_text.pack(fill=tk.BOTH, expand=True)
            new_value = str(new_scene_data.get(field, ""))
            new_text.insert('1.0', new_value)
            
            if not current_value or current_value.strip() == "":
                update_var.set(True)
            else:
                update_var.set(False)
            # 保存控件引用
            comparison_widgets[field] = {
                'update_var': update_var,
                'new_text': new_text
            }
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        result = [None]  # 使用列表以便在闭包中修改
        
        def on_ok():
            # 收集用户选择的数据
            updated_data = {}
            for field, widgets in comparison_widgets.items():
                if widgets['update_var'].get():
                    # 用户选择了更新此字段
                    new_value = widgets['new_text'].get('1.0', tk.END).strip()
                    if new_value:  # 只添加非空值
                        updated_data[field] = new_value
            result[0] = updated_data if updated_data else None
            dialog.destroy()
        
        def on_cancel():
            result[0] = None
            dialog.destroy()
        
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=5)
        
        # 等待对话框关闭
        dialog.wait_window()
        
        return result[0]
