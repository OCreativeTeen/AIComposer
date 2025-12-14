import tkinter as tk
from tkinter import ttk
import config
import config_prompt


WAN_VIDEO_STYLE = [
    "",
    "Realistic Style",
    "Felt Style",
    "Time-lapse",
    "Tilt-shift Photography",
    "Long Exposure Photography",
    "3D Cartoon Style",
    "3D Game Scene",
    "Magical Realism",
    "Cinematic",
    "Wondrous Atmosphere",
    "Claymation Style",
    "Watercolor Painting Style",
    "Pencil Drawing Style",
    "Oil Painting Style"
]



WAN_VIDEO_SHOT = [
    "",
    "Wide-angle",
    "Medium",
    "Panoramic Photography",
    "Close-up",
    "Extreme Close-up",
    "Macro Photography",
    "Underwater Photography",
    "Arc",
    "Tracking",
    "Zoom In",
    "Zoom Out",
    "Zoom In & Zoom Out",
    "Camera Pushes In For A Close-up",
    "Camera Pulls Back",
    "Camera Pans To The Right",
    "Camera Pans To The Left",
    "Camera Tilts Up",
    "Handheld Camera",
    "Compound Move"
]

WAN_VIDEO_ANGLE = [
    "",
    "Eye Level",
    "Low",
    "High",
    "Over the Shoulder"
]

WAN_VIDEO_COLOR = [
    "",
    "Warm",
    "Cool",
    "Saturated",
    "Desaturated"
]







class WanPromptEditorDialog:
    """WAN 视频提示词编辑对话框 - 支持风格、镜头、角度、色彩选择"""
    
    def __init__(self, parent, workflow, generate_video_callback, scene, track):
        """
        初始化对话框
        
        Args:
            parent: 父窗口
            workflow: 工作流实例
            generate_video_callback: 生成视频的回调函数
            scene: 场景数据
            track: 轨道类型 ("clip", "second", "zero")
        """
        self.parent = parent
        self.workflow = workflow
        self.scene = scene
        self.track = track
        self.generate_video_callback = generate_video_callback
        
        # 获取或初始化 WAN 参数
        self.extra_description = scene.get("extra", "")
        
        # 创建对话框
        self.dialog = tk.Toplevel(parent.root if hasattr(parent, 'root') else parent)
        self.dialog.title("编辑 WAN 视频提示词")
        self.dialog.geometry("900x800")
        self.dialog.transient(parent.root if hasattr(parent, 'root') else parent)
        self.dialog.grab_set()
        
        # 构建界面
        self._create_ui()
        
        # 居中显示
        self._center_dialog()
    
    def _create_ui(self):
        """创建用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # WAN 参数选择框架
        self._create_wan_params_frame(main_frame)
        
        # 动画预设框架
        self._create_animation_presets_frame(main_frame)
        
        # 提示词编辑框架
        self.prompt_text = self._create_prompt_frame(main_frame)
        
        # 获取已保存的 prompt（可能是字典或字符串）
        saved_prompt = self.scene.get(self.track + "_prompt", "")
        if isinstance(saved_prompt, dict):
            # 如果是字典，格式化为 JSON 字符串显示
            import json
            saved_prompt = json.dumps(saved_prompt, ensure_ascii=False, indent=2)
        elif isinstance(saved_prompt, str) and saved_prompt.strip():
            # 如果是字符串，尝试解析并重新格式化（美化显示）
            try:
                import json
                temp_dict = json.loads(saved_prompt)
                saved_prompt = json.dumps(temp_dict, ensure_ascii=False, indent=2)
            except:
                # 解析失败，保持原样
                pass
        
        self.prompt_text.insert(tk.END, saved_prompt)
        self._create_button_frame(main_frame)

    
    def _create_wan_params_frame(self, parent):
        """创建 WAN 参数选择框架"""
        params_frame = ttk.LabelFrame(parent, text="WAN 视频参数", padding=10)
        params_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 第一行：风格和镜头
        row1 = ttk.Frame(params_frame)
        row1.pack(fill=tk.X, pady=(0, 5))
        
        # 风格
        ttk.Label(row1, text="风格:").pack(side=tk.LEFT, padx=(0, 5))
        self.camear_style_var = tk.StringVar(value=self.scene.get('camear_style', WAN_VIDEO_STYLE[0]))
        style_combo = ttk.Combobox(row1, textvariable=self.camear_style_var,
                                   values=WAN_VIDEO_STYLE, state="readonly", width=25)
        style_combo.pack(side=tk.LEFT, padx=(0, 20))
        style_combo.bind('<<ComboboxSelected>>', self._on_params_change)
        
        # 镜头
        ttk.Label(row1, text="镜头:").pack(side=tk.LEFT, padx=(0, 5))
        self.camera_shot_var = tk.StringVar(value=self.scene.get('camera_shot', WAN_VIDEO_SHOT[0]))
        shot_combo = ttk.Combobox(row1, textvariable=self.camera_shot_var,
                                  values=WAN_VIDEO_SHOT, state="readonly", width=25)
        shot_combo.pack(side=tk.LEFT, padx=(0, 0))
        shot_combo.bind('<<ComboboxSelected>>', self._on_params_change)
        
        # 第二行：角度和色彩
        row2 = ttk.Frame(params_frame)
        row2.pack(fill=tk.X)
        
        # 角度
        ttk.Label(row2, text="角度:").pack(side=tk.LEFT, padx=(0, 5))
        self.camera_angle_var = tk.StringVar(value=self.scene.get('camera_angle', WAN_VIDEO_ANGLE[0]))
        angle_combo = ttk.Combobox(row2, textvariable=self.camera_angle_var,
                                   values=WAN_VIDEO_ANGLE, state="readonly", width=25)
        angle_combo.pack(side=tk.LEFT, padx=(0, 20))
        angle_combo.bind('<<ComboboxSelected>>', self._on_params_change)
        
        # 色彩
        ttk.Label(row2, text="色彩:").pack(side=tk.LEFT, padx=(0, 5))
        self.camera_color_var = tk.StringVar(value=self.scene.get('camera_color', WAN_VIDEO_COLOR[0]))
        color_combo = ttk.Combobox(row2, textvariable=self.camera_color_var,
                                   values=WAN_VIDEO_COLOR, state="readonly", width=25)
        color_combo.pack(side=tk.LEFT, padx=(0, 0))
        color_combo.bind('<<ComboboxSelected>>', self._on_params_change)
    
    def _create_animation_presets_frame(self, parent):
        """创建动画预设选择框架"""
        preset_frame = ttk.LabelFrame(parent, text="动画预设", padding=10)
        preset_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 说明
        desc_label = ttk.Label(preset_frame, 
                              text="选择预设动画效果（会追加到提示词）：",
                              font=("Arial", 9))
        desc_label.pack(anchor=tk.W, pady=(0, 5))
        
        # 预设选择
        combo_frame = ttk.Frame(preset_frame)
        combo_frame.pack(fill=tk.X)
        
        self.animation_combo = ttk.Combobox(combo_frame,
                                           values=[p["name"] for p in config.ANIMATION_PROMPTS],
                                           state="readonly",
                                           width=40)
        self.animation_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.animation_combo.bind('<<ComboboxSelected>>', self._on_animation_select)
        
        # 应用按钮
        apply_btn = ttk.Button(combo_frame, text="追加到提示词", 
                              command=self._append_animation)
        apply_btn.pack(side=tk.LEFT)
    
    def _create_prompt_frame(self, parent):
        """创建提示词编辑框架"""
        prompt_frame = ttk.LabelFrame(parent, text="WAN Prompt 编辑器", padding=10)
        prompt_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 提示词编辑
        text_frame = ttk.Frame(prompt_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        prompt_text = tk.Text(text_frame, wrap=tk.WORD, height=15, font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, 
                                 command=prompt_text.yview)
        prompt_text.configure(yscrollcommand=scrollbar.set)
        
        prompt_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        return prompt_text
    
    def _create_button_frame(self, parent):
        """创建按钮框架"""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X)
        
        # 左侧工具按钮
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        
        ttk.Button(left_buttons, text="清空", 
                  command=self._clear_prompt).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(left_buttons, text="重置", 
                  command=lambda: self._on_params_change(None)).pack(side=tk.LEFT)
        
        # 右侧操作按钮
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(right_buttons, text="取消", 
                  command=self._on_cancel).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(right_buttons, text="确认生成视频", 
                  command=self._on_generate).pack(side=tk.LEFT)
    

    def _on_params_change(self, event):
        """WAN 参数改变时重新构建提示词"""
        # 构建额外描述
        extra = self.extra_description
        
        # 添加 WAN 参数
        style = self.camear_style_var.get()
        shot = self.camera_shot_var.get()
        angle = self.camera_angle_var.get()
        color = self.camera_color_var.get()
        
        wan_params = []
        if style and style != "":
            wan_params.append(f"style: {style}")
        if shot and shot != "":
            wan_params.append(f"shot: {shot}")
        if angle and angle != "":
            wan_params.append(f"angle: {angle}")
        if color and color != "":
            wan_params.append(f"color: {color}")
        
        if wan_params:
            wan_desc = "(" + ", ".join(wan_params) + ")"
            extra = wan_desc + "  :  " + extra if extra else wan_desc
        
        animate_mode = self.scene.get(self.track+"_animation", "")
        new_prompt = self.workflow.build_prompt(self.scene, "", extra, self.track, animate_mode, False, self.workflow.language)

        # 更新文本框（如果是字典，转换为字符串显示）
        self.prompt_text.delete(1.0, tk.END)
        import json
        prompt_str = json.dumps(new_prompt, ensure_ascii=False, indent=2)
        self.prompt_text.insert(tk.END, prompt_str)
        
        print(f"🎬 WAN 提示词已更新 - 风格:{style}, 镜头:{shot}, 角度:{angle}, 色彩:{color}")
    
    def _on_animation_select(self, event):
        """动画预设选择变化"""
        # 仅选择，不自动应用
        pass
    
    def _append_animation(self):
        """追加动画预设到提示词"""
        selection = self.animation_combo.current()
        if selection >= 0:
            preset = config.ANIMATION_PROMPTS[selection]
            current_text = self.prompt_text.get(1.0, tk.END).strip()
            
            # 追加动画提示词
            if current_text:
                new_text = current_text + "\n\nMOTION: [" + preset["prompt"] + "]"
            else:
                new_text = "MOTION: [" + preset["prompt"] + "]"
            
            self.prompt_text.delete(1.0, tk.END)
            self.prompt_text.insert(tk.END, new_text)
            print(f"✅ 已追加动画预设: {preset['name']}")
    
    def _clear_prompt(self):
        """清空提示词"""
        self.prompt_text.delete(1.0, tk.END)
    
    def _on_generate(self):
        """生成视频按钮处理"""
        wan_prompt = self.prompt_text.get(1.0, tk.END).strip()
        
        # 尝试解析 JSON 字符串为字典
        try:
            import json
            wan_prompt = json.loads(wan_prompt)
        except:
            # 如果解析失败，保持为字符串
            pass
        
        # 保存 WAN 参数到场景
        self.scene['camear_style'] = self.camear_style_var.get()
        self.scene['camera_shot'] = self.camera_shot_var.get()
        self.scene['camera_angle'] = self.camera_angle_var.get()
        self.scene['camera_color'] = self.camera_color_var.get()
        
        # 关闭对话框
        self.dialog.destroy()
        
        # 调用生成视频回调
        self.generate_video_callback(wan_prompt)
    
    def _on_cancel(self):
        """取消按钮处理"""
        self.dialog.destroy()
    
    def _center_dialog(self):
        """居中显示对话框"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
        
        # 设置焦点
        self.prompt_text.focus_set()
    
    def show(self):
        """显示对话框（阻塞）"""
        self.dialog.wait_window()


def show_wan_prompt_editor(parent, workflow, generate_video_callback, scene, track):
    """便捷函数：显示 WAN Prompt 编辑对话框"""
    dialog = WanPromptEditorDialog(parent, workflow, generate_video_callback, scene, track)
    dialog.show()
