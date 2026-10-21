"""LayoutMixin: methods moved verbatim from GUI_wf.py:WorkflowGUI."""
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.scrolledtext as scrolledtext
import config
import config_prompt
from tkinterdnd2 import DND_FILES


class LayoutMixin:
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
        self.btn_finalize.pack(side=tk.RIGHT, padx=(20, 0))

        # 场景切换按钮和“开始/结束”标记都在右边“全场内容”标题旁边；上一场/下一场用 Alt+←/→。
        # PID 已经显示在窗口标题上，这里不再重复显示。

        title_frame = ttk.Frame(row)
        title_frame.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(title_frame, text="标题").pack(side=tk.LEFT)
        self.video_title = ttk.Entry(title_frame, width=21)
        self.video_title.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(row, text="频道").pack(side=tk.LEFT)
        self.shared_channel = ttk.Label(row, width=12, relief="sunken", background="white")
        self.shared_channel.pack(side=tk.LEFT, padx=(4, 8))

        ttk.Label(row, text="分类").pack(side=tk.LEFT, padx=(0, 2))
        self.topic_category_var = tk.StringVar()
        self.topic_category_combo = ttk.Combobox(
            row, textvariable=self.topic_category_var, state="readonly", width=12
        )
        self.topic_category_combo.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(row, text="子类").pack(side=tk.LEFT, padx=(0, 2))
        self.topic_subtype_var = tk.StringVar()
        self.topic_subtype_combo = ttk.Combobox(
            row, textvariable=self.topic_subtype_var, state="readonly", width=9
        )
        self.topic_subtype_combo.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(row, text="标签").pack(side=tk.LEFT, padx=(0, 2))
        self.topic_tags_var = tk.StringVar()
        self.topic_tags_entry = ttk.Entry(row, textvariable=self.topic_tags_var, width=18)
        self.topic_tags_entry.pack(side=tk.LEFT, padx=(0, 4))

        ttk.Separator(row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=24)

        ttk.Label(row, text="尺寸").pack(side=tk.LEFT)
        self._video_size_presets = ("1920×1080", "1080×1920")
        self.video_size_combo = ttk.Combobox(
            row, width=11, state="readonly", values=self._video_size_presets
        )
        self.video_size_combo.pack(side=tk.LEFT, padx=(4, 8))
        self.video_size_combo.bind("<<ComboboxSelected>>", self._on_video_output_size_selected)

        ttk.Separator(row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self.btn_copy_project = ttk.Button(
            row, text="回到预览", width=8, command=self._return_to_story_preview
        )
        self.btn_copy_project.pack(side=tk.LEFT, padx=2)

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
        self.video_canvas.configure(takefocus=True)
        self.video_canvas.bind("<Button-1>", lambda _e: self.video_canvas.focus_set())
        self.video_canvas.bind("<Double-Button-1>", self._on_video_canvas_double_click)
        self.video_canvas.bind("<Control-v>", self._on_video_canvas_paste)
        self.video_canvas.bind("<Control-V>", self._on_video_canvas_paste)

        bars = ttk.Frame(right_frame)
        bars.pack(fill=tk.X, pady=(6, 0))
        bars.columnconfigure(1, weight=1)
        icon_font = ("Segoe UI Symbol", 11)
        self.video_play_button = tk.Button(
            bars,
            text="▶",
            command=self.toggle_video_playback,
            font=icon_font,
            width=2,
            padx=0,
            pady=0,
            relief=tk.GROOVE,
            borderwidth=1,
        )
        self.video_play_button.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Button(
            bars,
            text="↺",
            command=self._reset_speaking_timing,
            font=icon_font,
            width=2,
            padx=0,
            pady=0,
            relief=tk.GROOVE,
            borderwidth=1,
        ).grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=(4, 0))
        self.progress_canvas = tk.Canvas(
            bars, height=32, bg="#ececec", highlightthickness=1, highlightbackground="#8a8a8a", cursor="hand2",
        )
        self.progress_canvas.grid(row=0, column=1, sticky="ew")
        self._progress_grabbed = False
        self._progress_grab_after = None
        self.progress_canvas.bind("<Configure>", lambda _e: self._draw_progress_bar())
        self.progress_canvas.bind("<ButtonPress-1>", self._progress_press)
        self.progress_canvas.bind("<B1-Motion>", self._progress_drag)
        self.progress_canvas.bind("<ButtonRelease-1>", self._progress_release)
        self.progress_canvas.bind("<Double-Button-1>", self._progress_double)

        self.speech_span_canvas = tk.Canvas(bars, height=24, bg="#d9d9d9", highlightthickness=1, highlightbackground="#b0b0b0")
        self.speech_span_canvas.grid(
            row=1, column=1, sticky="ew", pady=(4, 0), padx=(0, self._PROGRESS_KNOB),
        )
        self._speech_sections = []
        self._speech_span_duration = 0.0
        self._speech_span_drag = None
        self._preview_playhead = 0.0
        self._span_bar_scene = None
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

        self.btn_scene_edit = ttk.Button(
            video_control_frame, text="场景分合", command=self._ask_scene_structure, width=8
        )
        self.btn_scene_edit.pack(side=tk.LEFT, padx=1)

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

        # 标题旁边放“第一场 / 最后一场”两个按钮。
        ai_title = ttk.Frame(right_panel)
        ttk.Label(ai_title, text="全场内容").pack(side=tk.LEFT)
        ttk.Button(ai_title, text="⏮", width=3, command=self.first_scene).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Button(ai_title, text="⏭", width=3, command=self.last_scene).pack(side=tk.LEFT, padx=2)
        ttk.Separator(ai_title, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)
        start_btn = ttk.Button(ai_title, text="开始", width=4, command=lambda: self._set_scene_marker("start"))
        start_btn.pack(side=tk.LEFT, padx=(0, 0))
        end_btn = ttk.Button(ai_title, text="结束", width=4, command=lambda: self._set_scene_marker("end"))
        end_btn.pack(side=tk.LEFT, padx=(2, 0))
        start_btn.bind("<Button-3>", lambda _e: self._clear_scene_markers())
        end_btn.bind("<Button-3>", lambda _e: self._clear_scene_markers())
        self.marker_label = ttk.Label(ai_title, text="", width=9)
        self.marker_label.pack(side=tk.LEFT, padx=(4, 0))
        ai_tools_frame = ttk.LabelFrame(right_panel, labelwidget=ai_title, padding=(8, 2))
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
        # 延长对所有场景生效（见 _on_extension_change），所以放在全场内容里。
        ttk.Label(look_row1, text="延长").pack(side=tk.LEFT, padx=(10, 0))
        self.extension_var = tk.StringVar(value="0")
        self.extension_values = ["0", "0.4", "0.6", "0.8"]
        self.extension_combobox = ttk.Combobox(
            look_row1,
            textvariable=self.extension_var,
            values=self.extension_values,
            state="readonly",
            width=4,
        )
        self.extension_combobox.pack(side=tk.LEFT, padx=(4, 0))
        self.extension_combobox.bind("<<ComboboxSelected>>", lambda e: self._on_extension_change())
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
        # 对话方式已从界面移除：控件保留但不显示，旧的读写代码照常运行（旧存值被忽略）。
        self.scene_style = ttk.Combobox(
            look_row2,
            width=14,
            values=list(config_prompt.SCENE_STYLE_LABELS),
            state="readonly",
        )
        self.scene_style.set(config_prompt.SCENE_STYLE_LABELS[0])
        self.scene_style.pack(side=tk.LEFT, padx=(0, 0))

        episode_gap = ttk.Frame(right_panel, height=24)
        episode_gap.pack(side=tk.TOP)
        episode_gap.pack_propagate(False)
        # 标题旁边放“第几集”和上一集 / 下一集按钮。
        episode_title = ttk.Frame(right_panel)
        ttk.Label(episode_title, text="本集内容").pack(side=tk.LEFT)
        self.episode_label = ttk.Label(episode_title, text="第 1 集")
        self.episode_label.pack(side=tk.LEFT, padx=(8, 4))
        # 单击 = 本集第一场 / 最后一场；双击 = 上一集 / 下一集的第一场（没有 command，免得点一下触发两次）。
        ep_prev_btn = ttk.Button(episode_title, text="⏪", width=3)
        ep_prev_btn.pack(side=tk.LEFT, padx=2)
        ep_next_btn = ttk.Button(episode_title, text="⏩", width=3)
        ep_next_btn.pack(side=tk.LEFT, padx=2)
        self._bind_single_double(ep_prev_btn, lambda: self._jump_episode_edge("first"), self.prev_episode)
        self._bind_single_double(ep_next_btn, lambda: self._jump_episode_edge("last"), self.next_episode)
        self._attach_hover_hint(ep_prev_btn, "单击：本集第一场\n双击：上一集第一场（Ctrl+Shift+←）")
        self._attach_hover_hint(ep_next_btn, "单击：本集最后一场\n双击：下一集第一场（Ctrl+Shift+→）")
        episode_tools_frame = ttk.LabelFrame(right_panel, labelwidget=episode_title, padding=(8, 2))
        episode_tools_frame.pack(side=tk.TOP, fill=tk.X)
        episode_btn_row = ttk.Frame(episode_tools_frame)
        episode_btn_row.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(
            episode_btn_row,
            text="拷贝提示",
            width=8,
            command=self.copy_episode_prompt,
        ).pack(side=tk.LEFT, padx=(0, 4))
        # 「拷贝PDF」已移入「全集生成」（content.pdf 上传为 NotebookLM 来源）。
        ttk.Button(
            episode_btn_row,
            text="贴回本集",
            width=8,
            command=self.paste_episode_scenes,
        ).pack(side=tk.LEFT, padx=(0, 4))
        self._slide_prompt_btn = ttk.Button(
            episode_btn_row,
            text="全集生成",
            width=8,
            command=self._open_slide_prompt_flow,
        )
        self._slide_prompt_btn.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            episode_btn_row,
            text="调整集",
            width=8,
            command=self.open_adjust_episode_dialog,
        ).pack(side=tk.LEFT)

        scene_gap = ttk.Frame(right_panel, height=24)
        scene_gap.pack(side=tk.TOP)
        scene_gap.pack_propagate(False)
        # 标题旁边显示当前是第几场 / 一共几场。
        scene_title = ttk.Frame(right_panel)
        self._scene_title_label = ttk.Label(scene_title, text="本场内容")
        self._scene_title_label.pack(side=tk.LEFT)
        self.scene_label = ttk.Label(scene_title, text="0 / 0")
        self.scene_label.pack(side=tk.LEFT, padx=(8, 0))
        self.video_edit_frame = ttk.LabelFrame(right_panel, labelwidget=scene_title, padding=10)
        self.video_edit_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.video_edit_frame.columnconfigure(1, weight=1)

        row_number = 1

        # 本场内容的按钮分两排：第一排改文字，第二排出提示和生成媒体。
        scene_text_box = ttk.Frame(self.video_edit_frame)
        scene_text_box.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        scene_text_row = ttk.Frame(scene_text_box)
        scene_text_row.pack(side=tk.TOP, anchor=tk.W)
        # 出提示和生成媒体的按钮接在同一排后面，中间一条分隔线（见下面 btn_add_scene 之后）。
        scene_prompt_row = ttk.Frame(scene_text_row)
        # 场景变换和场景拆分合在同一个窗口里：上面变换，下面拆分。
        self._scene_speech_btn = ttk.Button(
            scene_text_row,
            text="变换/拆分",
            width=8,
            command=self._ask_scene_transform_or_split,
        )
        self._scene_speech_btn.pack(side=tk.LEFT)
        self._scene_split_btn = self._scene_speech_btn
        self.btn_add_scene = ttk.Button(
            scene_text_row,
            text="插入过渡",
            width=8,
            command=self.add_scene_insert,
        )
        self.btn_add_scene.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Separator(scene_text_row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
        scene_prompt_row.pack(side=tk.LEFT)
        self._nb_picture_btn = ttk.Button(
            scene_prompt_row,
            text="图片修改",
            width=8,
            command=self._open_picture_prompt_flow,
        )
        self._nb_picture_btn.pack(side=tk.LEFT)
        self._nb_story_video_btn = ttk.Button(
            scene_prompt_row,
            text="生场视频",
            width=8,
            command=self._open_video_prompt_flow,
        )
        self._nb_story_video_btn.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(
            scene_prompt_row,
            text="生场音频",
            width=8,
            command=self.choose_clip_audio_scope,
        ).pack(side=tk.LEFT, padx=(4, 0))
        self.btn_clip_transcribe = ttk.Button(
            scene_prompt_row,
            text="音频转录",
            width=8,
            command=self.choose_clip_transcribe_scope,
        )
        self.btn_clip_transcribe.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(self.video_edit_frame, text="讲话:").grid(row=row_number, column=0, sticky=tk.NW, pady=2)
        # Tk Text 内置撤销/重做：Ctrl+Z 撤销，Ctrl+Y 重做（Windows 常见）；maxundo=0 为不限制深度
        self.scene_speaking = scrolledtext.ScrolledText(
            self.video_edit_frame,
            width=20,
            height=8,
            undo=True,
            maxundo=0,
            font=("Arial", 16),
            wrap=tk.WORD,
        )
        self.scene_speaking.grid(row=row_number, column=1, sticky=tk.EW, padx=5, pady=2)
        self.scene_speaking.bind("<Double-1>", self._on_speaking_double_click_switch)
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
            text="主动画、次动画、增主轨已停用。sd_processor 里的生成和增强代码还留着，界面上先不接。WAN 在「生场视频」里还能选。",
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

    def on_tab_changed(self, event):
        if not hasattr(self, 'workflow') or self.workflow is None:
            return
        self.refresh_gui_scenes()

    def on_video_canvas_configure(self, event):
        """当video canvas尺寸改变时，动态调整提示文本位置"""
        canvas_width = event.width
        canvas_height = event.height
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        
        # 更新拖拽提示文本的位置到canvas中心
        self.video_canvas.coords("drag_hint", center_x, center_y)
