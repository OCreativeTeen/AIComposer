import tkinter as tk
from tkinter import ttk, messagebox

#
IMAGE_STYLES = [
    "ultra-realistic, cinematic lighting, dramatic shading",

    "watercolor painting",
    "watercolor painting with postcard border",
    "watercolor painting with golden ornate photo frame",
    "watercolor painting with Rococo picture frame",
    "watercolor painting with vintage photo frame",

    "ukiyo-e style",
    "ukiyo-e with vintage photo frame",
    "ukiyo-e with postcard border",
    "ukiyo-e with golden ornate photo frame",
    "ukiyo-e with Rococo picture frame"
]

IMAGE_STYLES_2 = [
    #"ultra-realistic, cinematic lighting, dramatic shading",
    { "style": "vintage postcard look", "frame": "vintage photo frame" },
    { "style": "vintage postcard look", "frame": "postcard border" },
    { "style": "vintage postcard look", "frame": "golden ornate photo frame" },
    { "style": "vintage postcard look", "frame": "baroque frame" },
    { "style": "vintage postcard look", "frame": "Rococo picture frame" },
    { "style": "graphite drawing", "frame": "vintage photo frame" },
    { "style": "graphite drawing", "frame": "postcard border" },
    { "style": "graphite drawing", "frame": "golden ornate photo frame" },
    { "style": "graphite drawing", "frame": "baroque frame" },
    { "style": "graphite drawing", "frame": "Rococo picture frame" },
    { "style": "watercolor painting", "frame": "gallery frame" },
    { "style": "watercolor painting", "frame": "postcard border" },
    { "style": "watercolor painting", "frame": "golden ornate photo frame" },
    { "style": "watercolor painting", "frame": "baroque frame" },
    { "style": "watercolor painting", "frame": "Rococo picture frame" },
    { "style": "rococo painting (baroque art)", "frame": "baroque frame" },
    { "style": "rococo painting (baroque art)", "frame": "postcard border" },
    { "style": "rococo painting (baroque art)", "frame": "golden ornate photo frame" },
    { "style": "rococo painting (baroque art)", "frame": "Rococo picture frame" },
    { "style": "ukiyo-e style", "frame": "ukiyo-e frame" },
    { "style": "ukiyo-e style", "frame": "postcard border" },
    { "style": "ukiyo-e style", "frame": "golden ornate photo frame" },
    { "style": "ukiyo-e style", "frame": "baroque frame" },
    { "style": "ukiyo-e style", "frame": "Rococo picture frame" },
    { "style": "crayon art (pastel drawing)", "frame": "postcard border" },
    { "style": "crayon art (pastel drawing)", "frame": "golden ornate photo frame" },
    { "style": "crayon art (pastel drawing)", "frame": "baroque frame" },
    { "style": "crayon art (pastel drawing)", "frame": "Rococo picture frame" }
]

# 图像提示词预设选项
IMAGE_PROMPT_OPTIONS = [
    "",
    "Ancient Middle-Eastern (story, clothing/head-coverings, tent)",
    "Chinese person (black hair) with traditional chinese dressing, Song-dynasty traditional chinese culture/architecture",
    "Modern Chinese person in business suit, contemporary urban cityscape background",
    "Japanese person in traditional kimono, traditional Japanese temple and garden",
    "Modern Japanese person in casual street fashion, Tokyo neon lights background",
    "Korean person in traditional hanbok, ancient Korean palace architecture",
    "Modern Korean person in K-pop style fashion, Seoul city skyline",
    "European person in medieval clothing, Gothic cathedral and castle",
    "Modern European person in elegant fashion, Paris street café scene",
    "American person in western cowboy attire, wild west desert landscape",
    "Modern American person in casual wear, New York skyscrapers background",
    "Indian person in traditional sari/kurta, Taj Mahal and traditional architecture",
    "Modern Indian person in contemporary dress, Mumbai modern cityscape",
    "Middle Eastern person in traditional robes, ancient desert city architecture",
    "Modern Middle Eastern person in business attire, Dubai futuristic skyline",
    "African person in traditional tribal clothing, savanna and acacia trees",
    "Modern African person in stylish fashion, Lagos or Cape Town cityscape",
    "Russian person in traditional folk costume, Red Square and onion domes",
    "Modern Russian person in winter fashion, Moscow snowy streets",
    "Brazilian person in carnival costume, Rio de Janeiro beach and mountains",
    "Modern Brazilian person in beach wear, São Paulo urban landscape",
    "cozy warm tones, calm atmosphere, subtle textures, psychological wellness, emotional warmth, a heartwarming lifestyle"    
]


# 负面提示词预设选项
NEGATIVE_PROMPT_OPTIONS = [
    "low quality, distorted, overly cartoonish, text, watermark, deformed, ugly, duplicate faces",
    "modern clothing/t-shirt, glasses/watches, guns/rifles/pistols/tactical-outfit, cars, phones, neon-lights",
    "drawing, painting, sketch, illustration",
    "nsfw, nude, sexual, adult content, violence, gore, blood",
    "extra limbs, extra fingers, extra arms, extra legs, missing limbs"
    "crowd, too many people"
]



class ImagePromptsReviewDialog:
    """提示词审查对话框 - 用于在创建图像前预览和编辑提示词"""
    
    def __init__(self, parent, workflow, create_image_callback, scenario, track):
        """
        初始化提示词审查对话框
        
        Args:
            workflow: 工作流实例
            positive_prompt: 初始正面提示词
            negative_prompt: 初始负面提示词
            create_image_callback: 创建图像的回调函数
            scenario: 场景数据（可选）
            speaking_mode: 是否为讲述模式
        """
        self.workflow = workflow
        self.scenario = scenario
        self.track = track

        self.create_image_callback = create_image_callback
        
        # 创建对话框
        self.dialog = tk.Toplevel(parent.root if hasattr(parent, 'root') else parent)
        self.dialog.title("审查提示词")
        self.dialog.geometry("900x750")
        self.dialog.transient(parent.root if hasattr(parent, 'root') else parent)
        self.dialog.grab_set()
        
        # 准备初始提示词
        self.extra_description = scenario.get(track + "_extra", "")
        
        # 构建界面
        self._create_ui()

        # 居中显示
        self._center_dialog()
    
    def _create_ui(self):
        """创建用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 图像特效选择框架
        self._create_style_frame(main_frame)
        
        # 正面提示词框架
        self.positive_text = self._create_positive_frame(main_frame)
        self._on_style_change(None)
        
        # 负面提示词框架
        self.negative_text = self._create_negative_frame(main_frame)
        self.negative_text.insert(tk.END, NEGATIVE_PROMPT_OPTIONS[0])
        
        # 按钮框架
        self._create_button_frame(main_frame)
    
    def _create_style_frame(self, parent):
        """创建图像特效选择框架"""
        style_frame = ttk.LabelFrame(parent, text="图像特效", padding=10)
        style_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(style_frame, text="特效样式:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.image_style_var = tk.StringVar(value=IMAGE_STYLES[0])
        image_style_combo = ttk.Combobox(style_frame, textvariable=self.image_style_var,
                                        values=IMAGE_STYLES, state="readonly", width=60)
        image_style_combo.pack(side=tk.LEFT, padx=(5, 0))
        image_style_combo.bind('<<ComboboxSelected>>', self._on_style_change)
    
    def _create_positive_frame(self, parent):
        """创建正面提示词框架"""
        positive_frame = ttk.LabelFrame(parent, text="正面提示词", padding=10)
        positive_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 预设选项
        positive_preset_label = ttk.Label(positive_frame, text="预设选项:")
        positive_preset_label.pack(anchor=tk.W)
        
        self.positive_preset_combo = ttk.Combobox(positive_frame, 
                                                  values=IMAGE_PROMPT_OPTIONS, 
                                                  width=80, state="readonly")
        self.positive_preset_combo.pack(fill=tk.X, pady=5)
        self.positive_preset_combo.bind('<<ComboboxSelected>>', self._on_style_change)
        
        # 提示词编辑
        positive_text_frame = ttk.Frame(positive_frame)
        positive_text_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        positive_text = tk.Text(positive_text_frame, wrap=tk.WORD, height=8)
        positive_scrollbar = ttk.Scrollbar(positive_text_frame, orient=tk.VERTICAL, 
                                          command=positive_text.yview)
        positive_text.configure(yscrollcommand=positive_scrollbar.set)
        
        positive_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        positive_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        return positive_text
    
    def _create_negative_frame(self, parent):
        """创建负面提示词框架"""
        negative_frame = ttk.LabelFrame(parent, text="负面提示词", padding=10)
        negative_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 预设选项
        negative_preset_label = ttk.Label(negative_frame, text="预设选项:")
        negative_preset_label.pack(anchor=tk.W)
        
        self.negative_preset_combo = ttk.Combobox(negative_frame, 
                                                  values=NEGATIVE_PROMPT_OPTIONS, 
                                                  width=80, state="readonly")
        self.negative_preset_combo.pack(fill=tk.X, pady=5)
        self.negative_preset_combo.bind('<<ComboboxSelected>>', self._on_negative_preset_select)
        
        # 提示词编辑
        negative_text_frame = ttk.Frame(negative_frame)
        negative_text_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        negative_text = tk.Text(negative_text_frame, wrap=tk.WORD, height=8)
        negative_scrollbar = ttk.Scrollbar(negative_text_frame, orient=tk.VERTICAL, 
                                          command=negative_text.yview)
        negative_text.configure(yscrollcommand=negative_scrollbar.set)
        
        negative_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        negative_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        return negative_text
    
    def _create_button_frame(self, parent):
        """创建按钮框架"""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="创建图像", 
                  command=self._on_create_image).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(button_frame, text="取消", 
                  command=self._on_cancel).pack(side=tk.RIGHT)


    def _on_style_change(self, event):
        """图像样式改变时的处理"""
        extra = self.extra_description

        selected = self.positive_preset_combo.get()
        if selected:
            extra = self.image_style_var.get()+ "; " + extra

        new_style = self.image_style_var.get()
        if new_style:
            extra = "(Image-style:"+new_style+ ")  :  " + extra

        # 重新构建正面提示词
        new_positive = self.workflow.build_prompt(self.scenario, new_style, extra, self.track, "IMAGE_GENERATION")
        
        # 更新文本框（如果是字典，转换为字符串显示）
        self.positive_text.delete(1.0, tk.END)
        positive_str = self.workflow.prompt_dict_to_string(new_positive)
        self.positive_text.insert(tk.END, positive_str)
        print(f"🎨 特效已更新为: {new_style}")


    def _on_negative_preset_select(self, event):
        """负面提示词预设选择处理"""
        selected = self.negative_preset_combo.get()
        if selected:
            self.negative_text.delete(1.0, tk.END)
            self.negative_text.insert(tk.END, selected)
    
    def _on_create_image(self):
        """创建图像按钮处理"""
        new_positive = self.positive_text.get(1.0, tk.END).strip()
        new_negative = self.negative_text.get(1.0, tk.END).strip()
        new_style = self.image_style_var.get()
        
        # 尝试解析 JSON 字符串为字典（对于正面提示词）
        try:
            import json
            new_positive = json.loads(new_positive)
        except:
            # 如果解析失败，保持为字符串
            pass
        
        # 关闭对话框
        self.dialog.destroy()
        
        # 调用创建图像回调
        self.create_image_callback(new_positive, new_negative)
    
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
        self.positive_text.focus_set()
    
    def show(self):
        """显示对话框（阻塞）"""
        self.dialog.wait_window()

