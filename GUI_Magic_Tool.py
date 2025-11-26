import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import uuid
import os
import json
from datetime import datetime
from magic_workflow import MagicWorkflow
import config
from pathlib import Path
from project_manager import ProjectConfigManager, create_project_dialog




class TitleSelectionDialog:
    """标题和标签选择对话框"""
    
    def __init__(self, parent, pid, language, current_title="", current_tags=""):
        self.parent = parent
        self.pid = pid
        self.language = language
        self.current_title = current_title
        self.current_tags = current_tags
        self.selected_title = None
        self.selected_tags = None
        self.result = None
        
        self.create_dialog()
    
    def create_dialog(self):
        """创建对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("选择视频标题和标签 - 魔法工作流")
        self.dialog.geometry("1000x800")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 使对话框居中
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (1000 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (800 // 2)
        self.dialog.geometry(f"1000x800+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题
        title_label = ttk.Label(main_frame, text="选择或编辑视频标题和标签", font=('TkDefaultFont', 14, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # 说明文字
        info_label = ttk.Label(main_frame, text="从以下AI生成的标题和标签中选择，或者编辑现有内容:", 
                              font=('TkDefaultFont', 10), foreground='gray')
        info_label.pack(pady=(0, 15))
        
        # 创建左右分栏
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # 左侧：标题选择
        title_frame = ttk.LabelFrame(content_frame, text="标题选择", padding=10)
        title_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # 标题选择滚动框架
        title_canvas = tk.Canvas(title_frame)
        title_scrollbar = ttk.Scrollbar(title_frame, orient="vertical", command=title_canvas.yview)
        title_scrollable_frame = ttk.Frame(title_canvas)
        
        title_scrollable_frame.bind(
            "<Configure>",
            lambda e: title_canvas.configure(scrollregion=title_canvas.bbox("all"))
        )
        
        title_canvas.create_window((0, 0), window=title_scrollable_frame, anchor="nw")
        title_canvas.configure(yscrollcommand=title_scrollbar.set)
        
        title_canvas.pack(side="left", fill="both", expand=True)
        title_scrollbar.pack(side="right", fill="y")
        
        # 标题选择变量
        self.title_var = tk.StringVar()
        
        # 加载标题选项
        title_options = self.load_title_options()
        
        for i, title_option in enumerate(title_options):
            # 创建单选按钮，限制文本长度避免过长
            display_text = title_option
            if len(title_option) > 60:  # 如果标题太长，截断显示
                display_text = title_option[:57] + "..."
            
            rb = ttk.Radiobutton(title_scrollable_frame, text=display_text, 
                               variable=self.title_var, value=title_option,
                               command=self.on_title_select)
            rb.pack(anchor='w', pady=2, padx=5, fill='x')
            
            # 默认选择第一个选项
            if i == 0:
                self.title_var.set(title_option)
        
        # 右侧：标签选择
        tags_frame = ttk.LabelFrame(content_frame, text="标签选择", padding=10)
        tags_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        # 标签选择滚动框架
        tags_canvas = tk.Canvas(tags_frame)
        tags_scrollbar = ttk.Scrollbar(tags_frame, orient="vertical", command=tags_canvas.yview)
        tags_scrollable_frame = ttk.Frame(tags_canvas)
        
        tags_scrollable_frame.bind(
            "<Configure>",
            lambda e: tags_canvas.configure(scrollregion=tags_canvas.bbox("all"))
        )
        
        tags_canvas.create_window((0, 0), window=tags_scrollable_frame, anchor="nw")
        tags_canvas.configure(yscrollcommand=tags_scrollbar.set)
        
        tags_canvas.pack(side="left", fill="both", expand=True)
        tags_scrollbar.pack(side="right", fill="y")
        
        # 标签选择变量
        self.tags_var = tk.StringVar()
        
        # 加载标签选项
        tags_options = self.load_tags_options()
        
        for i, tag_option in enumerate(tags_options):
            # 创建单选按钮
            display_text = tag_option
            if len(tag_option) > 60:
                display_text = tag_option[:57] + "..."
            
            rb = ttk.Radiobutton(tags_scrollable_frame, text=display_text, 
                               variable=self.tags_var, value=tag_option,
                               command=self.on_tags_select)
            rb.pack(anchor='w', pady=2, padx=5, fill='x')
            
            # 默认选择第一个选项
            if i == 0:
                self.tags_var.set(tag_option)
        
        # 编辑框架
        edit_frame = ttk.LabelFrame(main_frame, text="编辑选择的内容", padding=10)
        edit_frame.pack(fill=tk.X, pady=(0, 20))
        
        # 标题编辑
        title_edit_frame = ttk.Frame(edit_frame)
        title_edit_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(title_edit_frame, text="标题:").pack(side=tk.LEFT, padx=(0, 10))
        self.title_edit_text = tk.Text(title_edit_frame, height=3, wrap=tk.WORD, font=('TkDefaultFont', 11))
        self.title_edit_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 标签编辑
        tags_edit_frame = ttk.Frame(edit_frame)
        tags_edit_frame.pack(fill=tk.X)
        
        ttk.Label(tags_edit_frame, text="标签:").pack(side=tk.LEFT, padx=(0, 10))
        self.tags_edit_text = tk.Text(tags_edit_frame, height=3, wrap=tk.WORD, font=('TkDefaultFont', 11))
        self.tags_edit_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 初始化编辑框内容
        if title_options:
            first_title = title_options[0]
            if '] ' in first_title:
                actual_title = first_title.split('] ', 1)[1]
            else:
                actual_title = first_title
            self.title_edit_text.insert('1.0', actual_title)
        
        if tags_options:
            first_tag = tags_options[0]
            if '] ' in first_tag:
                actual_tag = first_tag.split('] ', 1)[1]
            else:
                actual_tag = first_tag
            self.tags_edit_text.insert('1.0', actual_tag)
        
        # 绑定文本改变事件
        self.title_edit_text.bind('<KeyRelease>', self.on_title_text_change)
        self.tags_edit_text.bind('<KeyRelease>', self.on_tags_text_change)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="确认", command=self.confirm_selection).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(button_frame, text="取消", command=self.cancel).pack(side=tk.RIGHT)
    
    def load_title_options(self):
        """加载标题选项"""
        title_options = []
        
        # 1. 添加当前标题（如果有）
        if self.current_title and self.current_title.strip():
            title_options.append(f"[当前] {self.current_title}")
        
        # 2. 从项目配置中加载生成的标题
        try:
            # 获取项目配置管理器
            config_manager = ProjectConfigManager(self.pid)
            
            # 获取生成的标题
            generated_titles = config_manager.project_config.get('generated_titles', [])
            for i, title in enumerate(generated_titles):
                if title and title.strip():
                    title_options.append(f"[AI-{i+1}] {title}")
                    
        except Exception as e:
            print(f"从项目配置加载生成标题失败: {e}")
        
        # 3. 如果没有任何标题，添加默认选项
        if not title_options:
            title_options.append("[默认] 未命名视频")
        
        return title_options
    
    def load_tags_options(self):
        """加载标签选项"""
        tags_options = []
        
        # 1. 添加当前标签（如果有）
        if self.current_tags and self.current_tags.strip():
            tags_options.append(f"[当前] {self.current_tags}")
        
        # 2. 从项目配置中加载生成的标签
        try:
            # 获取项目配置管理器
            config_manager = ProjectConfigManager(self.pid)
            
            # 获取生成的标签
            generated_tags = config_manager.project_config.get('generated_tags', [])
            for i, tag in enumerate(generated_tags):
                if tag and tag.strip():
                    tags_options.append(f"[AI-{i+1}] {tag}")
                    
        except Exception as e:
            print(f"从项目配置加载生成标签失败: {e}")
        
        # 3. 如果没有任何标签，添加默认选项
        if not tags_options:
            tags_options.append("[默认] 无标签")
        
        return tags_options
    
    def on_title_select(self):
        """标题选择事件"""
        selected = self.title_var.get()
        # 移除前缀标签，提取实际标题
        if '] ' in selected:
            actual_title = selected.split('] ', 1)[1]
        else:
            actual_title = selected
        
        # 更新编辑框
        self.title_edit_text.delete('1.0', tk.END)
        self.title_edit_text.insert('1.0', actual_title)
    
    def on_tags_select(self):
        """标签选择事件"""
        selected = self.tags_var.get()
        # 移除前缀标签，提取实际标签
        if '] ' in selected:
            actual_tags = selected.split('] ', 1)[1]
        else:
            actual_tags = selected
        
        # 更新编辑框
        self.tags_edit_text.delete('1.0', tk.END)
        self.tags_edit_text.insert('1.0', actual_tags)
    
    def on_title_text_change(self, event=None):
        """标题文本改变事件"""
        # 当用户手动编辑时，清除单选按钮选择
        current_text = self.title_edit_text.get('1.0', tk.END).strip()
        
        # 检查是否与任何预设选项匹配
        for option in self.load_title_options():
            if '] ' in option:
                actual_title = option.split('] ', 1)[1]
                if actual_title == current_text:
                    self.title_var.set(option)
                    return
        
        # 如果不匹配任何预设，清除单选按钮选择
        self.title_var.set("")
    
    def on_tags_text_change(self, event=None):
        """标签文本改变事件"""
        # 当用户手动编辑时，清除单选按钮选择
        current_text = self.tags_edit_text.get('1.0', tk.END).strip()
        
        # 检查是否与任何预设选项匹配
        for option in self.load_tags_options():
            if '] ' in option:
                actual_tags = option.split('] ', 1)[1]
                if actual_tags == current_text:
                    self.tags_var.set(option)
                    return
        
        # 如果不匹配任何预设，清除单选按钮选择
        self.tags_var.set("")
    
    def confirm_selection(self):
        """确认选择"""
        final_title = self.title_edit_text.get('1.0', tk.END).strip()
        final_tags = self.tags_edit_text.get('1.0', tk.END).strip()
        
        # 保存选择的标题和标签到项目配置
        try:
            # 获取项目配置管理器
            config_manager = ProjectConfigManager()
            config_manager.load_config(self.pid)
            config_manager.project_config['video_title'] = final_title
            config_manager.project_config['video_tags'] = final_tags
            config_manager.save_project_config()
            
            print(f"✅ 已保存选择的标题和标签到项目配置: {final_title}, {final_tags}")
            
            self.selected_title = final_title
            self.selected_tags = final_tags
            self.result = "confirm"
            self.dialog.destroy()
            
        except Exception as e:
            messagebox.showerror("错误", f"保存标题和标签失败: {e}")
    
    def cancel(self):
        """取消"""
        self.result = "cancel"
        self.dialog.destroy()
    
    def show(self):
        """显示对话框并返回结果"""
        # 等待对话框关闭
        self.dialog.wait_window()
        return self.result, self.selected_title, self.selected_tags





class MagicToolGUI:
    def __init__(self, root=None):
        try:
            from tkinterdnd2 import TkinterDnD
            self.root = root or TkinterDnD.Tk()
        except ImportError:
            self.root = root or tk.Tk()
        self.root.title("Magic Tools - 工具集")
        self.root.geometry("900x800")  # Slightly larger for project config area
        
        # Initialize variables
        self.tasks = {}
        self.workflow = None
        self.current_language = "zh"  # Default language
        self.current_project_config = None
        
        # Initialize checkbox variables
        self.enable_starting = tk.BooleanVar(value=True)
        self.enable_ending = tk.BooleanVar(value=True)
        
        # Show project selection dialog first
        if not self.show_project_selection():
            # User canceled, exit application
            self.root.destroy()
            return
        
        self.setup_ui()
        
        # Bind window close event to save config
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def show_project_selection(self):
        result, selected_config = create_project_dialog(self.root)
        
        if result == 'cancel':
            return False
        elif result == 'new':
            # 使用从新项目对话框获取的配置
            self.current_project_config = selected_config
            self.current_language = selected_config.get('language', 'zh')
            
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
            
            # 立即创建workflow
            self.create_workflow()
            return True
        elif result == 'open':
            # 打开现有项目
            self.current_project_config = selected_config
            self.current_language = selected_config.get('language', 'zh')
            # 立即创建workflow
            self.create_workflow()
            return True
        
        return False
    
    def create_workflow(self):
        """立即创建workflow实例"""
        try:
            pid = self.get_pid()
            language = self.get_language()
            channel = self.get_channel()
            story_site = self.get_story_site()
            if pid and language and channel:
                self.workflow = MagicWorkflow(pid, language, channel, story_site)
                print(f"✅ Workflow已创建: PID={pid}, Language={language}, Channel={channel}")
            else:
                print(f"⚠️ 无法创建Workflow: PID={pid}, Language={language}, Channel={channel}")
        except Exception as e:
            print(f"❌ 创建Workflow失败: {str(e)}")
            self.workflow = None
    
    def save_project_config(self):
        try:
            # 更新当前配置
            config_data = self.current_project_config.copy()
            config_data['language'] = self.current_language
            config_data['video_title'] = self.video_title.get() or config_data.get('video_title', '')
            config_data['video_tags'] = self.video_tags.get() or config_data.get('video_tags', '')
            config_data['program_keywords'] = self.project_keywords.get() or config_data.get('program_keywords', '')
            config_data['story_site'] = self.story_site_entry.get() or config_data.get('story_site', '')
            config_data['video_width'] = config_data.get('video_width', str(config.VIDEO_WIDTH))
            config_data['video_height'] = config_data.get('video_height', str(config.VIDEO_HEIGHT))
            
            # 保存 WAN 视频参数
            if hasattr(self, 'wan_style_var'):
                config_data['wan_style'] = self.wan_style_var.get()
            if hasattr(self, 'wan_shot_var'):
                config_data['wan_shot'] = self.wan_shot_var.get()
            if hasattr(self, 'wan_angle_var'):
                config_data['wan_angle'] = self.wan_angle_var.get()
            if hasattr(self, 'wan_color_var'):
                config_data['wan_color'] = self.wan_color_var.get()
            
            # Save thumbnail font color if available
            if hasattr(self, 'thumbnail_font_color'):
                config_data['thumbnail_font_color'] = self.thumbnail_font_color.get()
            
            # Preserve generated titles and tags if they exist
            if 'generated_titles' in self.current_project_config:
                config_data['generated_titles'] = self.current_project_config['generated_titles']
            if 'generated_tags' in self.current_project_config:
                config_data['generated_tags'] = self.current_project_config['generated_tags']
            
            # Preserve video_id if it exists
            if 'video_id' in self.current_project_config:
                config_data['video_id'] = self.current_project_config['video_id']
            
            # 保存到文件
            pid = config_data['pid']
            if pid:
                config_manager = ProjectConfigManager(pid)
                config_manager.project_config = config_data.copy()
                config_manager.save_project_config(config_data)
                self.current_project_config = config_data
                print(f"✅ Magic Tool项目配置已保存: {pid}")
                
        except Exception as e:
            print(f"❌ 保存Magic Tool项目配置失败: {e}")
    
    def on_closing(self):
        """窗口关闭时的处理"""
        self.save_project_config()
        self.root.destroy()
        
    def setup_ui(self):
        """Setup the main UI"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Project configuration area at the top
        self.create_project_config_area(main_frame)
        
        # Language selection
        self.create_language_selector(main_frame)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create tabs
        self.create_audio_project_tab()
        self.create_thumbnail_tab()
        self.create_audio_transcript_tab()
        self.create_script_tab()
        
        # Status bar
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        
        # 确保在UI创建完成后加载生成的标题和标签
        self.root.after(200, self.load_generated_titles_and_tags_to_combobox)
        
        # 恢复缩略图字体颜色设置
        self.root.after(300, self.restore_thumbnail_font_color)
    
    def create_project_config_area(self, parent):
        """创建项目配置区域"""
        project_frame = ttk.LabelFrame(parent, text="项目配置", padding="10")
        project_frame.pack(fill=tk.X, padx=5, pady=(0, 10))
        
        # 第一行：基本项目信息
        row1 = ttk.Frame(project_frame)
        row1.pack(fill=tk.X, pady=2)
        #
        row2 = ttk.Frame(project_frame)
        row2.pack(fill=tk.X, pady=2)
        #
        row3 = ttk.Frame(project_frame)
        row3.pack(fill=tk.X, pady=2)
        
        # PID (只读)
        ttk.Label(row1, text="项目ID:").pack(side=tk.LEFT)
        self.project_pid = ttk.Label(row1, text=self.current_project_config.get('pid', ''), 
                                    relief="sunken", width=25, background="white")
        self.project_pid.pack(side=tk.LEFT, padx=(5, 15))
        
        # 频道 (只读)
        ttk.Label(row1, text="频道:").pack(side=tk.LEFT)
        self.project_channel = ttk.Label(row1, text=self.current_project_config.get('channel', ''), 
                                        relief="sunken", width=12, background="white")
        self.project_channel.pack(side=tk.LEFT, padx=(5, 15))
        
        # 语言 (只读，从语言选择器更新)
        ttk.Label(row1, text="语言:").pack(side=tk.LEFT)
        self.project_language = ttk.Label(row1, text=self.current_language, 
                                         relief="sunken", width=5, background="white")
        self.project_language.pack(side=tk.LEFT, padx=(5, 15))
        
        # 项目选择按钮
        ttk.Button(row1, text="选择项目", command=self.change_project).pack(side=tk.RIGHT, padx=5)
        
        # 项目标题 (使用Combobox)
        ttk.Label(row2, text="项目标题:").pack(side=tk.LEFT)
        self.video_title = ttk.Combobox(row2, width=70)
        self.video_title.pack(side=tk.LEFT, padx=(5, 15))
        self.video_title.bind('<FocusOut>', self.on_project_config_change)
        self.video_title.bind('<<ComboboxSelected>>', self.on_project_config_change)
        self.video_title.set(self.current_project_config.get('video_title', ''))

        # 项目标签 (使用Combobox)
        ttk.Label(row3, text="项目标签:").pack(side=tk.LEFT)
        self.video_tags = ttk.Combobox(row3, width=35)
        self.video_tags.pack(side=tk.LEFT, padx=(5, 15))
        self.video_tags.bind('<FocusOut>', self.on_project_config_change)
        self.video_tags.bind('<<ComboboxSelected>>', self.on_project_config_change)
        self.video_tags.set(self.current_project_config.get('video_tags', ''))
        
        # 关键字
        ttk.Label(row3, text="关键字:").pack(side=tk.LEFT)
        self.project_keywords = ttk.Entry(row3, width=25)
        self.project_keywords.insert(0, self.current_project_config.get('program_keywords', ''))
        self.project_keywords.pack(side=tk.LEFT, padx=(5, 15))
        self.project_keywords.bind('<FocusOut>', self.on_project_config_change)
        
        # 故事场地
        ttk.Label(row3, text="故事场地:").pack(side=tk.LEFT)
        self.story_site_entry = ttk.Entry(row3, width=20)
        self.story_site_entry.insert(0, self.current_project_config.get('story_site', ''))
        self.story_site_entry.pack(side=tk.LEFT, padx=(5, 15))
        self.story_site_entry.bind('<FocusOut>', self.on_project_config_change)
        
        # 保存按钮
        ttk.Button(row3, text="保存配置", command=self.save_project_config).pack(side=tk.RIGHT, padx=5)
        
        # 第四行：WAN 视频生成选项（风格/镜头/角度/色彩）
        row4 = ttk.Frame(project_frame)
        row4.pack(fill=tk.X, pady=2)
        
        # 视频风格
        wan_style_frame = ttk.Frame(row4)
        wan_style_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(wan_style_frame, text="视频风格:").pack(side=tk.LEFT)
        self.wan_style_var = tk.StringVar(value=self.current_project_config.get('wan_style', config.WAN_VIDEO_STYLE[0]) if hasattr(self, 'current_project_config') and self.current_project_config else config.WAN_VIDEO_STYLE[0])
        self.wan_style_combo = ttk.Combobox(wan_style_frame, textvariable=self.wan_style_var,
                                            values=config.WAN_VIDEO_STYLE, state="readonly", width=20)
        self.wan_style_combo.pack(side=tk.LEFT, padx=(5, 0))
        self.wan_style_combo.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        # 镜头类型
        wan_shot_frame = ttk.Frame(row4)
        wan_shot_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(wan_shot_frame, text="镜头类型:").pack(side=tk.LEFT)
        self.wan_shot_var = tk.StringVar(value=self.current_project_config.get('wan_shot', config.WAN_VIDEO_SHOT[0]) if hasattr(self, 'current_project_config') and self.current_project_config else config.WAN_VIDEO_SHOT[0])
        self.wan_shot_combo = ttk.Combobox(wan_shot_frame, textvariable=self.wan_shot_var,
                                           values=config.WAN_VIDEO_SHOT, state="readonly", width=20)
        self.wan_shot_combo.pack(side=tk.LEFT, padx=(5, 0))
        self.wan_shot_combo.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        # 拍摄角度
        wan_angle_frame = ttk.Frame(row4)
        wan_angle_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(wan_angle_frame, text="拍摄角度:").pack(side=tk.LEFT)
        self.wan_angle_var = tk.StringVar(value=self.current_project_config.get('wan_angle', config.WAN_VIDEO_ANGLE[0]) if hasattr(self, 'current_project_config') and self.current_project_config else config.WAN_VIDEO_ANGLE[0])
        self.wan_angle_combo = ttk.Combobox(wan_angle_frame, textvariable=self.wan_angle_var,
                                            values=config.WAN_VIDEO_ANGLE, state="readonly", width=20)
        self.wan_angle_combo.pack(side=tk.LEFT, padx=(5, 0))
        self.wan_angle_combo.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        # 色彩风格
        wan_color_frame = ttk.Frame(row4)
        wan_color_frame.pack(side=tk.LEFT)
        ttk.Label(wan_color_frame, text="色彩风格:").pack(side=tk.LEFT)
        self.wan_color_var = tk.StringVar(value=self.current_project_config.get('wan_color', config.WAN_VIDEO_COLOR[0]) if hasattr(self, 'current_project_config') and self.current_project_config else config.WAN_VIDEO_COLOR[0])
        self.wan_color_combo = ttk.Combobox(wan_color_frame, textvariable=self.wan_color_var,
                                            values=config.WAN_VIDEO_COLOR, state="readonly", width=20)
        self.wan_color_combo.pack(side=tk.LEFT, padx=(5, 0))
        self.wan_color_combo.bind('<<ComboboxSelected>>', self.on_project_config_change)
    
    def change_project(self):
        """更改项目"""
        if self.show_project_selection():
            # 更新显示
            self.project_pid.config(text=self.current_project_config.get('pid', ''))
            self.project_channel.config(text=self.current_project_config.get('channel', ''))
            self.project_language.config(text=self.current_language)
            
            # 更新字段内容
            self.video_title.delete(0, tk.END)
            self.video_title.insert(0, self.current_project_config.get('video_title', ''))

            self.video_tags.delete(0, tk.END)
            self.video_tags.insert(0, self.current_project_config.get('video_tags', ''))

            self.project_keywords.delete(0, tk.END)
            self.project_keywords.insert(0, self.current_project_config.get('program_keywords', ''))

            self.story_site_entry.delete(0, tk.END)
            self.story_site_entry.insert(0, self.current_project_config.get('story_site', ''))
            
            # 更新 WAN 视频参数
            self.wan_style_var.set(self.current_project_config.get('wan_style', config.WAN_VIDEO_STYLE[0]))
            self.wan_shot_var.set(self.current_project_config.get('wan_shot', config.WAN_VIDEO_SHOT[0]))
            self.wan_angle_var.set(self.current_project_config.get('wan_angle', config.WAN_VIDEO_ANGLE[0]))
            self.wan_color_var.set(self.current_project_config.get('wan_color', config.WAN_VIDEO_COLOR[0]))
            
            # 更新语言选择器
            self.language_var.set(self.current_language)
            self.on_language_change()
            
            # 重新加载生成的标题和标签
            self.load_generated_titles_and_tags_to_combobox()
            
            # 如果自动加载没有找到数据，尝试强制从JSON文件加载
            if (not self.current_project_config.get('generated_titles') or 
                not self.current_project_config.get('generated_tags')):
                try:
                    self.force_reload_titles_and_tags()
                except:
                    pass  # 静默失败，避免影响项目切换
            
            # 恢复缩略图字体颜色设置
            if hasattr(self, 'thumbnail_font_color'):
                saved_color = self.current_project_config.get('thumbnail_font_color', '白色')
                self.thumbnail_font_color.set(saved_color)
                print(f"🎨 已恢复字体颜色设置: {saved_color}")
            
            # Workflow已经在show_project_selection中创建了
            
            messagebox.showinfo("成功", f"已切换到项目: {self.current_project_config.get('pid', '')}")
    
    def load_generated_titles_and_tags_to_combobox(self):
        """加载生成的标题和标签到Combobox选择列表"""
        try:
            print(f"🔍 开始加载标题和标签到Combobox...")
            
            # 检查widgets是否已经创建
            if not hasattr(self, 'video_title') or not hasattr(self, 'video_tags'):
                print("⚠️ Combobox widgets not ready yet, will retry later")
                print(f"   video_title exists: {hasattr(self, 'video_title')}")
                print(f"   video_tags exists: {hasattr(self, 'video_tags')}")
                # 如果widgets还没准备好，延迟重试
                self.root.after(100, self.load_generated_titles_and_tags_to_combobox)
                return
            
            print(f"✅ Widgets are ready, proceeding with data loading...")
            
            # 获取生成的标题和标签
            generated_titles = self.current_project_config.get("generated_titles", None)
            generated_tags = self.current_project_config.get("generated_tags", None)
            
            # 如果项目配置中没有生成的标题和标签，尝试从titles_choices.json文件加载
            if not generated_titles or not generated_tags:
                try:
                    titles_choices_path = f"{config.get_project_path(self.get_pid())}/titles_choices.json"
                    if os.path.exists(titles_choices_path):
                        with open(titles_choices_path, 'r', encoding='utf-8') as f:
                            titles_choices_data = json.loads(f.read())
                        
                        if not generated_titles and 'titles' in titles_choices_data:
                            generated_titles = titles_choices_data['titles']
                            print(f"✅ 从titles_choices.json加载了 {len(generated_titles)} 个标题")
                            
                        if not generated_tags and 'tags' in titles_choices_data:
                            generated_tags = titles_choices_data['tags']
                            print(f"✅ 从titles_choices.json加载了 {len(generated_tags)} 个标签")
                        
                        # 更新当前配置，避免下次重复读取文件
                        if generated_titles:
                            self.current_project_config['generated_titles'] = generated_titles
                        if generated_tags:
                            self.current_project_config['generated_tags'] = generated_tags
                            
                except Exception as e:
                    print(f"⚠️ 从titles_choices.json加载标题和标签失败: {str(e)}")
            
            # 获取当前保存的值
            current_title = self.current_project_config.get('video_title', '')
            current_tags = self.current_project_config.get('video_tags', '')
            
            print(f"📝 当前值: title='{current_title}', tags='{current_tags}'")
            
            if generated_titles:
                title_options = []
                if current_title and current_title not in generated_titles:
                    title_options.append(f"[当前] {current_title}")
                title_options.extend(generated_titles)
                
                if title_options:
                    self.video_title['values'] = title_options
                    # 设置当前值
                    if current_title:
                        self.video_title.set(current_title)
                    else:
                        self.video_title.set('')
                    print(f"   标题选项: {title_options[:3]}...")  # 只显示前3个
                else:
                    self.video_title['values'] = []
                    self.video_title.set('')
                    print("⚠️ 没有可用的生成标题")
                
            # 为标签Combobox设置选项
            if generated_tags:
                tags_options = []
                if current_tags and current_tags not in generated_tags:
                    tags_options.append(f"[当前] {current_tags}")
                tags_options.extend(generated_tags)
                
                if tags_options:
                    self.video_tags['values'] = tags_options
                    # 设置当前值
                    if current_tags:
                        self.video_tags.set(current_tags)
                    else:
                        self.video_tags.set('')
                    print(f"✅ 已加载 {len(generated_tags)} 个生成标签到选择列表")
                    print(f"   标签选项: {tags_options[:3]}...")  # 只显示前3个
                else:
                    self.video_tags['values'] = []
                    self.video_tags.set('')
                    print("⚠️ 没有可用的生成标签")
                
        except Exception as e:
            print(f"❌ 加载生成标题和标签到Combobox失败: {str(e)}")
            import traceback
            traceback.print_exc()
            # 如果出错，延迟重试
            self.root.after(100, self.load_generated_titles_and_tags_to_combobox)
    
    def update_combobox_after_titles_generation(self):
        """在生成标题和标签后更新Combobox选项"""
        try:
            # 重新加载生成的标题和标签
            self.load_generated_titles_and_tags_to_combobox()
            print("✅ 已更新标题和标签选择列表")
        except Exception as e:
            print(f"❌ 更新Combobox选项失败: {str(e)}")
    
    def force_reload_titles_and_tags(self):
        """强制从titles_choices.json重新加载标题和标签"""
        try:
            titles_choices_path = f"{config.get_project_path(self.get_pid())}/titles_choices.json"
            if os.path.exists(titles_choices_path):
                with open(titles_choices_path, 'r', encoding='utf-8') as f:
                    titles_choices_data = json.loads(f.read())
                
                # 强制更新配置
                if 'titles' in titles_choices_data:
                    self.current_project_config['generated_titles'] = titles_choices_data['titles']
                    print(f"✅ 强制重新加载了 {len(titles_choices_data['titles'])} 个标题")
                
                if 'tags' in titles_choices_data:
                    self.current_project_config['generated_tags'] = titles_choices_data['tags']
                    print(f"✅ 强制重新加载了 {len(titles_choices_data['tags'])} 个标签")
                
                # 更新Combobox
                self.load_generated_titles_and_tags_to_combobox()
                
                # 保存到项目配置文件
                self.save_project_config()
                
                self.log_to_output(self.script_output, f"✅ 已从titles_choices.json重新加载标题和标签")
                messagebox.showinfo("成功", "已重新加载标题和标签选项")
                
            else:
                self.log_to_output(self.script_output, f"❌ titles_choices.json文件不存在: {titles_choices_path}")
                messagebox.showerror("错误", "titles_choices.json文件不存在")
                
        except Exception as e:
            error_msg = f"重新加载标题和标签失败: {str(e)}"
            self.log_to_output(self.script_output, f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)
    
    def on_project_config_change(self, event=None):
        """项目配置改变时的处理"""
        # 自动保存配置
        self.root.after(100, self.save_project_config)  # 延迟保存避免频繁写入
        
    def create_language_selector(self, parent):
        """Create language selection frame"""
        lang_frame = ttk.LabelFrame(parent, text="语言设置", padding="5")
        lang_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(lang_frame, text="操作语言:").pack(side=tk.LEFT, padx=5)
        self.language_var = tk.StringVar(value=self.current_language)
        language_combo = ttk.Combobox(lang_frame, textvariable=self.language_var, 
                                     values=["zh", "tw", "en"], state="readonly", width=10)
        language_combo.pack(side=tk.LEFT, padx=5)
        language_combo.bind("<<ComboboxSelected>>", self.on_language_change)
        
        # Language descriptions
        lang_desc = ttk.Label(lang_frame, text="(zh=简体中文, tw=繁體中文, en=English)", 
                             font=("TkDefaultFont", 8))
        lang_desc.pack(side=tk.LEFT, padx=10)
        


        
    def create_thumbnail_tab(self):
        """Create thumbnail generation tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="缩略图生成")
        
        # Thumbnail generation section
        thumbnail_frame = ttk.LabelFrame(tab, text="缩略图生成", padding="10")
        thumbnail_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Image selection
        image_frame = ttk.Frame(thumbnail_frame)
        image_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(image_frame, text="图片文件:").pack(side=tk.LEFT)
        self.thumbnail_image_path = tk.StringVar()
        ttk.Entry(image_frame, textvariable=self.thumbnail_image_path, width=10).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(image_frame, text="选择", command=self.select_thumbnail_image).pack(side=tk.LEFT, padx=5)

        ttk.Label(image_frame, text="字体:").pack(side=tk.LEFT)
        self.thumbnail_font = ttk.Combobox(image_frame, state="readonly", width=10)
        self.thumbnail_font.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Label(image_frame, text="字体大小:").pack(side=tk.LEFT)
        self.thumbnail_font_size = ttk.Combobox(image_frame, state="readonly", width=6,
                                               values=["280", "260", "240", "220", "200", "180", "160", "140", "120", "100"])
        self.thumbnail_font_size.set("240")
        self.thumbnail_font_size.pack(side=tk.LEFT, padx=5)
        
        # Font color picker - will be used in add_title_to_image call (replaces hardcoded white)
        ttk.Label(image_frame, text="字体颜色:").pack(side=tk.LEFT)
        self.thumbnail_font_color = ttk.Combobox(image_frame, state="readonly", width=6)
        self.thumbnail_font_color['values'] = [
            "白色", "黑色", "红色", "蓝色", "绿色", "黄色", "橙色", "紫色", "粉色", "青色", "灰色", "金色", "银色"
        ]
        self.thumbnail_font_color.set("白色")  # Default to white
        self.thumbnail_font_color.pack(side=tk.LEFT, padx=5)
        self.thumbnail_font_color.bind("<<ComboboxSelected>>", self.on_thumbnail_font_color_change)

        ttk.Label(image_frame, text="主持形象").pack(side=tk.LEFT)
        self.thumbnail_figure = ttk.Combobox(image_frame, state="readonly", width=20,
                                values=["china_serious_left", "china_scared_left",  "china_happy_left", 
                                        "china_serious_center", "china_scared_center", "china_happy_center",
                                        "china_serious_right", "china_scared_right", "china_happy_right"])
        self.thumbnail_figure.set("china_serious_left")
        self.thumbnail_figure.pack(side=tk.LEFT, padx=5)

        gen_frame = ttk.Frame(thumbnail_frame)
        gen_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(gen_frame, text="缩略图  ", 
                  command=lambda: self.run_generate_thumbnail(False, False)).pack(side=tk.LEFT, padx=5)

        ttk.Button(gen_frame, text="缩略图F ", 
                  command=lambda: self.run_generate_thumbnail(False, True)).pack(side=tk.LEFT, padx=5)

        ttk.Button(gen_frame, text="缩略图2 ", 
                  command=lambda: self.run_generate_thumbnail(True, False)).pack(side=tk.LEFT, padx=5)

        ttk.Button(gen_frame, text="缩略图2F", 
                  command=lambda: self.run_generate_thumbnail(True, True)).pack(side=tk.LEFT, padx=5)

        # Preview area in a separate row
        preview_frame = ttk.Frame(thumbnail_frame)
        preview_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(preview_frame, text="缩略图预览:").pack(side=tk.LEFT, padx=(0, 5))
        
        # add a pre-view area (with 320, height 180) to show the thumbnail image after generate
        self.thumbnail_preview = tk.Canvas(preview_frame, width=320, height=180, bg='white', relief=tk.SUNKEN, bd=1)
        self.thumbnail_preview.pack(side=tk.LEFT, padx=5)

        # Initialize preview with placeholder
        self.clear_thumbnail_preview()
        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.thumbnail_output = scrolledtext.ScrolledText(output_frame, height=15)
        self.thumbnail_output.pack(fill=tk.BOTH, expand=True)
        
        # Update font options based on current language
        self.update_thumbnail_font_options()
        

    def on_thumbnail_font_color_change(self, event=None):
        """Handle font color selection change"""
        selected_color = self.thumbnail_font_color.get()
        print(f"🎨 字体颜色已更改为: {selected_color}")
        

    def get_selected_font_color(self):
        """Get the selected font color as a color name string"""
        color_mapping = {
            "白色": "white",
            "黑色": "black", 
            "红色": "red",
            "蓝色": "blue",
            "绿色": "green",
            "黄色": "yellow",
            "橙色": "orange",
            "紫色": "purple",
            "粉色": "pink",
            "青色": "cyan",
            "灰色": "gray",
            "金色": "gold",
            "银色": "silver"
        }
        selected_color = self.thumbnail_font_color.get()
        return color_mapping.get(selected_color, "white")  # Default to white if not found
        

    def restore_thumbnail_font_color(self):
        """Restore thumbnail font color from saved config"""
        try:
            if hasattr(self, 'thumbnail_font_color') and self.current_project_config:
                saved_color = self.current_project_config.get('thumbnail_font_color', '白色')
                self.thumbnail_font_color.set(saved_color)
                print(f"🎨 已恢复字体颜色设置: {saved_color}")
        except Exception as e:
            print(f"⚠️ 恢复字体颜色设置失败: {str(e)}")


    def update_thumbnail_preview(self, thumbnail_path):
        """Update the thumbnail preview canvas with the generated thumbnail image"""
        try:
            if not os.path.exists(thumbnail_path):
                print(f"⚠️ Thumbnail file not found: {thumbnail_path}")
                self.clear_thumbnail_preview()
                return
            
            # Load and resize the thumbnail image
            from PIL import Image, ImageTk
            
            # Open the thumbnail image
            image = Image.open(thumbnail_path)
            
            # Get canvas dimensions
            canvas_width = 320
            canvas_height = 180
            
            # Calculate aspect ratio to maintain proportions
            img_width, img_height = image.size
            aspect_ratio = img_width / img_height
            canvas_aspect_ratio = canvas_width / canvas_height
            
            if aspect_ratio > canvas_aspect_ratio:
                # Image is wider than canvas, fit to width
                new_width = canvas_width
                new_height = int(canvas_width / aspect_ratio)
            else:
                # Image is taller than canvas, fit to height
                new_height = canvas_height
                new_width = int(canvas_height * aspect_ratio)
            
            # Resize image
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Clear canvas and display image
            self.thumbnail_preview.delete("all")
            
            # Center the image in the canvas
            x = (canvas_width - new_width) // 2
            y = (canvas_height - new_height) // 2
            
            self.thumbnail_preview.create_image(x, y, anchor=tk.NW, image=photo)
            
            # Keep a reference to prevent garbage collection
            self.thumbnail_preview_image = photo
            
            print(f"✅ 缩略图预览已更新: {os.path.basename(thumbnail_path)}")
            
        except Exception as e:
            print(f"❌ 更新缩略图预览失败: {str(e)}")
            self.clear_thumbnail_preview()
            

    def clear_thumbnail_preview(self):
        """Clear the thumbnail preview canvas"""
        try:
            if hasattr(self, 'thumbnail_preview'):
                self.thumbnail_preview.delete("all")
                # Add placeholder text
                existing_thumbnail = self.current_project_config.get('thumbnail_image', None)
                if existing_thumbnail:
                    self.update_thumbnail_preview(existing_thumbnail)
                else:    
                    self.thumbnail_preview.create_text(160, 90, text="预览区域\n320×180", fill="gray", font=("Arial", 12))

        except Exception as e:
            print(f"⚠️ 清空缩略图预览失败: {str(e)}")
            
        
    def create_audio_transcript_tab(self):
        """Create audio transcription tab with drag & drop"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="音频转录")
        
        # Audio transcription section
        audio_frame = ttk.LabelFrame(tab, text="音频文件转录", padding="10")
        audio_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Drag & drop area
        drop_frame = ttk.Frame(audio_frame)
        drop_frame.pack(fill=tk.X, padx=5, pady=10)
        
        # Create a frame for the drop zone
        self.drop_zone = ttk.Frame(drop_frame, relief=tk.RAISED, borderwidth=2)
        self.drop_zone.pack(fill=tk.X, padx=10, pady=10)
        
        # Add the wave sound image
        try:
            wave_image_path = os.path.join("media", "wave_sound.png")
            if os.path.exists(wave_image_path):
                from PIL import Image, ImageTk
                image = Image.open(wave_image_path)
                # Resize image to reasonable size
                image = image.resize((200, 100), Image.Resampling.LANCZOS)
                self.wave_photo = ImageTk.PhotoImage(image)
                wave_label = ttk.Label(self.drop_zone, image=self.wave_photo)
                wave_label.pack(pady=10)
            else:
                # Fallback text if image not found
                ttk.Label(self.drop_zone, text="🎵", font=("TkDefaultFont", 48)).pack(pady=10)
        except Exception as e:
            # Fallback text if image loading fails
            ttk.Label(self.drop_zone, text="🎵", font=("TkDefaultFont", 48)).pack(pady=10)
        
        # Drop zone instructions
        ttk.Label(self.drop_zone, text="拖拽或点击选择音频文件", 
                 font=("TkDefaultFont", 12, "bold")).pack(pady=5)
        ttk.Label(self.drop_zone, text="支持格式: mp3, wav, m4a, ogg, flac", 
                 font=("TkDefaultFont", 9)).pack(pady=2)
        
        # File path display
        self.audio_file_path = tk.StringVar()
        path_frame = ttk.Frame(audio_frame)
        path_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(path_frame, text="音频文件:").pack(side=tk.LEFT)
        ttk.Entry(path_frame, textvariable=self.audio_file_path, width=60, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(path_frame, text="选择文件", command=self.select_audio_file).pack(side=tk.LEFT, padx=5)
        
        # Language selection for audio transcription
        audio_lang_frame = ttk.Frame(audio_frame)
        audio_lang_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(audio_lang_frame, text="音频语言:").pack(side=tk.LEFT)
        self.audio_language = ttk.Combobox(audio_lang_frame, values=[
            "tw", "en", "zh", "ja", "ko", "es", "fr", "de", "ru", "ar", "hi", "pt"
        ], state="readonly", width=10)
        self.audio_language.set("tw")
        self.audio_language.pack(side=tk.LEFT, padx=5)
        
        # Transcribe button
        button_frame = ttk.Frame(audio_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        ttk.Button(button_frame, text="开始转录", 
                  command=self.run_transcript_audio).pack(side=tk.LEFT, padx=25)
        
        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.audio_output = scrolledtext.ScrolledText(output_frame, height=15)
        self.audio_output.pack(fill=tk.BOTH, expand=True)
        
        # Setup drag & drop
        self.setup_drag_drop()
        
    def setup_drag_drop(self):
        """Setup drag and drop functionality"""
        try:
            from tkinterdnd2 import DND_FILES
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind('<<Drop>>', self.on_drop)
            
            # Change appearance on drag enter/leave
            self.drop_zone.bind('<Enter>', self.on_drag_enter)
            self.drop_zone.bind('<Leave>', self.on_drag_leave)
        except ImportError:
            # Fallback to click-based selection if tkinterdnd2 is not available
            self.drop_zone.bind('<Button-1>', self.on_drop_zone_click)
            self.drop_zone.bind('<Enter>', self.on_drop_zone_enter)
            self.drop_zone.bind('<Leave>', self.on_drop_zone_leave)
        
    def on_drop_zone_click(self, event):
        """Handle drop zone click to select file (fallback)"""
        self.select_audio_file()
        
    def on_drop_zone_enter(self, event):
        """Handle mouse enter event (fallback)"""
        self.drop_zone.configure(relief=tk.SUNKEN)
        
    def on_drop_zone_leave(self, event):
        """Handle mouse leave event (fallback)"""
        self.drop_zone.configure(relief=tk.RAISED)
        
    def on_drag_enter(self, event):
        """Handle drag enter event"""
        self.drop_zone.configure(relief=tk.SUNKEN)
        
    def on_drag_leave(self, event):
        """Handle drag leave event"""
        self.drop_zone.configure(relief=tk.RAISED)
        
    def on_drop(self, event):
        """Handle file drop event"""
        self.drop_zone.configure(relief=tk.RAISED)
        
        # Get dropped file path
        file_path = event.data
        
        # Clean up the path (remove {} if present)
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path[1:-1]
        
        # Check if it's an audio file
        audio_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma']
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in audio_extensions:
            self.audio_file_path.set(file_path)
            self.log_to_output(self.audio_output, f"✅ 已选择音频文件: {os.path.basename(file_path)}")
        else:
            messagebox.showerror("错误", f"不支持的文件格式: {file_ext}\n支持的格式: {', '.join(audio_extensions)}")
            
    def select_audio_file(self):
        """Select audio file manually"""
        file_path = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[
                ("音频文件", "*.mp3 *.wav *.m4a *.ogg *.flac *.aac *.wma"),
                ("MP3文件", "*.mp3"),
                ("WAV文件", "*.wav"),
                ("M4A文件", "*.m4a"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.audio_file_path.set(file_path)
            self.log_to_output(self.audio_output, f"✅ 已选择音频文件: {os.path.basename(file_path)}")
            
            
    def run_transcript_audio(self):
        """Run audio transcription"""
        audio_path = self.audio_file_path.get().strip()
        language = self.audio_language.get()
        
        if not audio_path:
            messagebox.showerror("错误", "请选择音频文件")
            return
            
        if not os.path.exists(audio_path):
            messagebox.showerror("错误", "选择的音频文件不存在")
            return
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "transcript_audio",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                self.status_var.set("转录中...")
                self.log_to_output(self.audio_output, f"🎵 开始转录音频文件...")
                self.log_to_output(self.audio_output, f"文件: {os.path.basename(audio_path)}")
                self.log_to_output(self.audio_output, f"语言: {language}")
                
                file_stem = Path(audio_path).stem
                
                # Create output paths
                script_path = self.workflow.transcriber.transcribe_to_file( audio_path, language, 10, 26 )
                
                self.log_to_output(self.audio_output, f"✅ 转录完成！")
                self.log_to_output(self.audio_output, f"字幕文件: {script_path}")
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
                # Show success message in main thread
                self.root.after(0, lambda: messagebox.showinfo("成功", f"转录完成！\n字幕文件: {script_path}"))
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.audio_output, f"❌ 转录失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                # Show error message in main thread
                self.root.after(0, lambda: messagebox.showerror("错误", f"转录失败: {error_msg}"))
        
        # Run in separate thread to avoid blocking GUI
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
        
    def on_language_change(self, event=None):
        """Handle language change"""
        self.current_language = self.language_var.get()
        
        # 更新项目语言显示
        if hasattr(self, 'project_language'):
            self.project_language.config(text=self.current_language)
        
        self.update_thumbnail_font_options()
        
        # 记录日志
        self.log_to_output(self.transcript_output, f"语言已切换到: {self.current_language}")
        self.log_to_output(self.thumbnail_output, f"语言已切换到: {self.current_language}")
        self.log_to_output(self.audio_output, f"语言已切换到: {self.current_language}")
        
        # 保存项目配置
        self.save_project_config()
        
        # 重新创建workflow以使用新语言
        self.create_workflow()
        
    def update_thumbnail_font_options(self):
        """Update font options based on current language"""
        try:
            # Get fonts for current language
            fonts = config.FONTS_BY_LANGUAGE.get(self.current_language, [])
            
            # Create font display names list
            font_names = [font["name"] for font in fonts]
            
            # Update combobox values
            self.thumbnail_font["values"] = font_names
            
            # Set default selection if fonts available
            if font_names:
                self.thumbnail_font.set(font_names[0])
                
        except Exception as e:
            self.log_to_output(self.thumbnail_output, f"更新字体选项失败: {str(e)}")
            
    def log_to_output(self, output_widget, message):
        """Add message to output text area"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        output_widget.see(tk.END)
        

        
    def select_thumbnail_image(self):
        """Select thumbnail image file"""
        file_path = filedialog.askopenfilename(
            title="选择图片文件",
            filetypes=[
                ("图片文件", "*.webp *.png *.jpg"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.thumbnail_image_path.set(file_path)
            self.log_to_output(self.thumbnail_output, f"✅ 已选择图片: {os.path.basename(file_path)}")
            
            self.update_config_json(
                [
                    {"name":"thumbnail_image", "value":file_path}
                ]
            )
            # Show the selected image in preview
            self.update_thumbnail_preview(file_path)


    def run_generate_thumbnail2(self):
        tags_text = self.video_tags.get().strip()
        tags_text = self.get_current_workflow().transcriber.translate_text(tags_text, self.current_language, self.current_language)
        tags_text = tags_text.replace("-", "\n")
        selected_font_name = self.thumbnail_font.get().strip()
        
        for scenario in self.get_current_workflow().scenarios:
            if scenario.get('promo_mode', None) == "IMAGE_MAIN":
                if os.path.exists(scenario['image']):
                    if scenario['image'] != self.thumbnail_image_path.get().strip():
                        self.thumbnail_image_path.set(scenario['image'])
                        break

        self.run_generate_thumbnail()



    def run_generate_thumbnail(self, search, figure):
        """Generate thumbnail"""
        selected_font_name = self.thumbnail_font.get().strip()
        if not selected_font_name:
            messagebox.showerror("错误", "请选择字体")
            return

        if search: 
            for scenario in self.get_current_workflow().scenarios:
                if scenario.get('promo_mode', None) == "IMAGE_MAIN":
                    if os.path.exists(scenario['image']):
                        if scenario['image'] != self.thumbnail_image_path.get().strip():
                            self.thumbnail_image_path.set(scenario['image'])
                            break

        image_path = self.thumbnail_image_path.get().strip()

        if not image_path:
            messagebox.showerror("错误", "请选择图片文件")
            return
        # Check if image file exists
        if not os.path.exists(image_path):
            messagebox.showerror("错误", "选择的图片文件不存在")
            return

        tags_text = self.video_tags.get().strip()
        tags_text = self.get_current_workflow().transcriber.translate_text(tags_text, self.current_language, self.current_language)
        tags_text = tags_text.replace("-", "\n")
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "generate_thumbnail",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                # Get selected font information
                fonts = config.FONTS_BY_LANGUAGE.get(self.current_language, [])
                selected_font = None
                
                for font in fonts:
                    if font["name"] == selected_font_name:
                        selected_font = font
                        break
                
                if not selected_font:
                    raise Exception(f"未找到字体: {selected_font_name}")
                
                self.log_to_output(self.thumbnail_output, f"🖼️ 开始生成缩略图")
                
                # Get selected font size
                font_size = int(self.thumbnail_font_size.get())
                figure_name = self.thumbnail_figure.get()
                
                # Generate thumbnail
                thumbnail_path = f"{config.get_project_path(self.get_pid())}/thumbnail.png"
                
                # Get selected font color
                font_color = self.get_selected_font_color()
                
                # Add bold effect with selected color
                if figure_name.find("left") != -1:
                    temp_output = self.workflow.ffmpeg_processor.add_title_to_image(
                        image_path, tags_text, selected_font, font_size, "top-right", font_color, True
                    )
                elif figure_name.find("center") != -1:
                    temp_output = self.workflow.ffmpeg_processor.add_title_to_image(
                        image_path, tags_text, selected_font, font_size, "top-center", font_color, True
                    )
                else:
                    temp_output = self.workflow.ffmpeg_processor.add_title_to_image(
                        image_path, tags_text, selected_font, font_size, "top-left", font_color, True
                    )

                background_img = self.workflow.sd_processor.read_image(temp_output)

                if figure:
                    r_figure_path = self.workflow.find_matched_file(self.workflow.channel_path, "host_image/"+figure_name, "png", None)
                    r_figure_img = self.workflow.sd_processor.read_image(r_figure_path)
                    #r_figure_img = self.workflow.sd_image_processor.remove_background(r_figure_img)
                    if figure_name.find("left") != -1:
                        background_img = self.workflow.sd_processor.add_image_to_image(r_figure_img, background_img, "left")
                    elif figure_name.find("center") != -1:
                        background_img = self.workflow.sd_processor.add_image_to_image(r_figure_img, background_img, "center")
                    elif figure_name.find("right") != -1:
                        background_img = self.workflow.sd_processor.add_image_to_image(r_figure_img, background_img, "right")

                background_img = self.workflow.sd_processor.resize_image(background_img, 960, 540)

                self.workflow.sd_processor.save_image(background_img, thumbnail_path)
                
                self.log_to_output(self.thumbnail_output, f"✅ 缩略图生成成功！")
                self.log_to_output(self.thumbnail_output, f"保存位置: {thumbnail_path}")
                
                self.tasks[task_id]["status"] = "完成"
                self.tasks[task_id]["result"] = f"缩略图已保存到: {thumbnail_path}"
                
                # Update thumbnail preview in main thread
                self.root.after(0, lambda: self.update_thumbnail_preview(thumbnail_path))
                
                # Show success message in main thread
                self.root.after(0, lambda: messagebox.showinfo("成功", f"缩略图生成成功！\n保存位置: {thumbnail_path}"))
                
            except Exception as e:
                error_msg = f"缩略图生成失败: {str(e)}"
                self.log_to_output(self.thumbnail_output, f"❌ {error_msg}")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)
                
                # Show error message in main thread
                self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
                
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
        
    def create_audio_project_tab(self):
        """创建音频项目配置标签页"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="音频项目配置")
        
        # 创建主容器，使用垂直分布
        main_container = ttk.Frame(tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 音频文件选择区域
        audio_frame = ttk.LabelFrame(main_container, text="主音频文件", padding=15)
        audio_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 当前选择的音频文件显示
        current_frame = ttk.Frame(audio_frame)
        current_frame.pack(fill=tk.X, pady=(0, 10))
        
        selected_main_audio = config.get_main_audio_path(self.get_pid())
        foreground = 'gray'
        if os.path.exists(selected_main_audio):
            foreground = 'green'

        self.current_audio_label = ttk.Label(current_frame, text=selected_main_audio, foreground=foreground, wraplength=500)
        self.current_audio_label.pack(anchor=tk.W, pady=(5, 0))
        
        # 音频选择选项
        option_frame = ttk.Frame(audio_frame)
        option_frame.pack(fill=tk.X)
        
        
        # 沉浸故事区域
        story_frame = ttk.LabelFrame(main_container, text="沉浸故事 (可选内容)", padding=15)
        story_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 沉浸故事状态显示
        story_status_frame = ttk.Frame(story_frame)
        story_status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.story_status_label = ttk.Label(story_status_frame, text="检查中...", foreground='gray')
        self.story_status_label.pack(anchor=tk.W)
        
        # 沉浸故事操作按钮
        story_button_frame = ttk.Frame(story_frame)
        story_button_frame.pack(fill=tk.X)
        
        def open_immersive_story():
            self.show_story_editor()
            self.root.after(1000, self.check_immersive_story_audio_status)

        ttk.Button(story_button_frame, text="打开沉浸故事编辑器", 
                  command=open_immersive_story).pack(side=tk.LEFT, padx=(0, 10))
        
        # 说明文本
        info_frame = ttk.Frame(main_container)
        info_frame.pack(fill=tk.X, pady=(0, 15))
        
        info_text = ("说明:\n"
                   "• 主音频文件: 项目的主要音频内容，用于生成脚本和场景（必需）\n"
                   "• 沉浸故事: 专门用于生成对话文本和沉浸式音频的工具（可选）\n"
                   "• 选择沉浸故事音频: 选择或确认沉浸故事音频文件（显示在沉浸故事区域）\n"
                   "• 点击'生成项目'将传递主音频和沉浸故事音频到 prepare_project_from_audio")
        
        info_label = ttk.Label(info_frame, text=info_text, 
                             font=('Arial', 9), foreground='gray',
                             wraplength=550, justify=tk.LEFT)
        info_label.pack(anchor=tk.W)
        
        # 按钮区域
        button_frame = ttk.Frame(main_container)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        # 按钮区域

        ttk.Button(button_frame, text="生成项目", command=self.run_prepare_project_from_audio).pack(side=tk.RIGHT, padx=(10, 0))
    
        ttk.Button(button_frame, text="生成题目", command=self.run_create_titles_and_tags).pack(side=tk.RIGHT, padx=(10, 0))
        
        self.starting_checkbox = ttk.Checkbutton(button_frame, text="启用开始视频", variable=self.enable_starting, onvalue=True, offvalue=False)
        self.starting_checkbox.pack(side=tk.LEFT, padx=(10, 0)) 

        self.ending_checkbox = ttk.Checkbutton(button_frame, text="启用结束视频", variable=self.enable_ending, onvalue=True, offvalue=False)
        self.ending_checkbox.pack(side=tk.LEFT, padx=(10, 0)) 

        ttk.Button(button_frame, text="重新加载题目", command=self.force_reload_titles_and_tags).pack(side=tk.LEFT, padx=(10, 0))
        # 刷新按钮
        ttk.Button(button_frame, text="刷新状态", 
                  command=self.check_immersive_story_audio_status).pack(side=tk.LEFT)
        
        # 输出日志区域
        output_frame = ttk.LabelFrame(main_container, text="输出日志", padding=10)
        output_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        self.script_output = scrolledtext.ScrolledText(output_frame, height=15)
        self.script_output.pack(fill=tk.BOTH, expand=True)
                
        # 初始检查状态
        self.root.after(200, self.check_immersive_story_audio_status)  # 延迟200ms执行，确保UI完全加载


    def check_immersive_story_audio_status(self):
        """检查沉浸故事和主音频状态"""
        try:
            pid = self.get_pid()
            language = self.get_language()
            if not pid or not language:
                self.story_status_label.config(text="❌ 请先配置PID和语言", foreground='red')
                return
           
            # 检查沉浸故事音频文件
            try:
                story_audio_path = config.get_story_audio_path(pid)
                if os.path.exists(story_audio_path):
                    filename = os.path.basename(story_audio_path)
                    size = os.path.getsize(story_audio_path) / (1024 * 1024)  # MB
                    story_audio_status = f"✅ 沉浸故事音频已就绪: {filename} ({size:.1f}MB)"
                else:
                    # 检查JSON文件
                    json_path = config.get_story_json_path(pid)
                    if os.path.exists(json_path):
                        story_audio_status = "⚠️ 沉浸故事JSON存在，但音频缺失"
                    else:
                        story_audio_status = "⚠️ 沉浸故事未配置"
            except:
                story_audio_status = "⚠️ 沉浸故事未配置"
            
            # 更新状态显示
            self.story_status_label.config(text=story_audio_status, foreground='green')
                
        except Exception as e:
            self.story_status_label.config(text=f"⚠️ 检查状态失败", foreground='orange')


    def run_create_titles_and_tags(self):
        pid = self.get_pid()

        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "create_titles_and_tags",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": pid
        }
        
        def run_task():
            try:
                titles_content = self.get_current_workflow().create_titles_and_tags()
                if isinstance(titles_content, list) and len(titles_content) > 0:
                    titles_content = titles_content[0]

                if titles_content and isinstance(titles_content, dict):
                    self.update_config_json(
                        [
                            {"name":"generated_titles", "value":titles_content['titles']},
                            {"name":"generated_tags", "value":titles_content['tags']},
                        ]
                    )

                    self.log_to_output(self.script_output, f"✅ 题目和标签已保存到项目配置: {len(titles_content.get('titles', []))} 个题目, {len(titles_content.get('tags', []))} 个标签")
                    
                    # 在主线程中更新Combobox选项
                    self.root.after(0, self.update_combobox_after_titles_generation)
                else:
                    self.log_to_output(self.script_output, f"⚠️ 生成的题目内容格式无效: {titles_content}")

                # 显示成功消息
                success_msg = f"音频项目题目生成完成！"
                
                self.root.after(0, lambda: messagebox.showinfo("完成", success_msg))

                self.tasks[task_id]["status"] = "完成"
                self.tasks[task_id]["result"] = f"生成了题目"
            except Exception as e:
                self.log_to_output(self.script_output, f"❌ 项目题目生成失败: {str(e)}")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)
                
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()


    def run_prepare_project_from_audio(self):
        """从音频项目配置运行项目准备"""
        pid = self.get_pid()
        language = self.get_language()

        """确认配置并生成项目脚本"""
        if not os.path.exists(config.get_main_audio_path(self.get_pid())):
            messagebox.showerror("错误", "请先选择主音频文件")
            return

        # Extract filename from audio path and set as project title
        new_title = self.video_title.get().strip()

        program_keywords = self.project_keywords.get().strip() if hasattr(self, 'project_keywords') else ""
            
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "create_script",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": pid
        }
        
        def run_task():
            try:
                self.log_to_output(self.script_output, f"🎬 开始视频: {'启用' if self.enable_starting.get() else '禁用'}")
                self.log_to_output(self.script_output, f"🎬 结束视频: {'启用' if self.enable_ending.get() else '禁用'}")
                
                # 调用workflow方法，传递主音频和沉浸故事音频
                workflow = self.get_current_workflow()
                
                if self.enable_starting.get():
                    starting_mode = "full"
                else:
                    starting_mode = "simple"

                wan_style = getattr(self, 'wan_style_var', None) and self.wan_style_var.get() or config.WAN_VIDEO_STYLE[0]
                wan_shot = getattr(self, 'wan_shot_var', None) and self.wan_shot_var.get() or config.WAN_VIDEO_SHOT[0]
                wan_angle = getattr(self, 'wan_angle_var', None) and self.wan_angle_var.get() or config.WAN_VIDEO_ANGLE[0]
                wan_color = getattr(self, 'wan_color_var', None) and self.wan_color_var.get() or config.WAN_VIDEO_COLOR[0]
                large_site_name = self.story_site_entry.get().strip() if hasattr(self, 'story_site_entry') else ''
                result = workflow.prepare_project( starting_mode, self.enable_ending.get(), 26.0, new_title, None, program_keywords, large_site_name, wan_style, wan_shot, wan_angle, wan_color )
                
                message = f"生成了 {len(result)} 个段落"
                self.log_to_output(self.script_output, f"✅ 项目脚本生成成功！{message}")
                                
                self.root.after(0, lambda: messagebox.showinfo("完成", message))
                                
                # 在主线程中显示标题选择对话框
                self.root.after(500, self.show_title_selection_dialog)  # 延迟500ms确保JSON加载完成

                self.tasks[task_id]["status"] = "完成"
                self.tasks[task_id]["result"] = message
            except Exception as e:
                self.log_to_output(self.script_output, f"❌ 项目脚本生成失败: {str(e)}")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = str(e)
                
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()


    def get_pid(self):
        """获取当前项目ID"""
        return self.current_project_config.get('pid', '') if self.current_project_config else ''
    
    def get_language(self):
        """获取当前语言"""
        return self.current_language
    
    def get_channel(self):
        """获取当前频道"""
        return self.current_project_config.get('channel', 'strange_zh') if self.current_project_config else 'strange_zh'
    
    def get_story_site(self):
        """获取当前场地"""
        return self.current_project_config.get('story_site', '') if self.current_project_config else ''
    
    def get_current_workflow(self):
        """获取当前工作流实例"""
        # Workflow现在在项目加载时立即创建，这里只需要返回
        return self.workflow
    
    

    def use_story_music(self):
        self.use_story_audio(config.get_selected_music_path(self.get_pid()))

    def use_promot_story_audio(self):
        self.use_story_audio(config.get_short_audio_path(self.get_pid()))


    def use_story_audio(self, story_audio):
        try:
            story_audio = filedialog.askopenfilename(
                title=f"选择(沉浸)故事音频文件",
                filetypes=[
                    ("音频文件", "*.wav *.mp3 *.aac *.m4a")
                ]
            )
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {str(e)}")

        if os.path.exists(story_audio):
            filename = os.path.basename(story_audio)
            size = os.path.getsize(story_audio) / (1024 * 1024)  # MB
            self.story_status_label.config(text=f"✅ 沉浸故事音频已就绪: {filename} ({size:.1f}MB)", foreground='green')


    def use_pre_video(self):
        pre_video = config.get_pre_video_path(self.get_pid())
        try:
            file_path = filedialog.askopenfilename(
                title=f"选择前奏视频文件",
                filetypes=[
                    ("视频文件", "*.mp4 *.mkv")
                ]
            )
            if file_path:
                try:
                    converted_video = self.workflow.ffmpeg_processor.convert_to_mp4(file_path)
                    os.replace(converted_video, pre_video)
                except Exception as e:
                    messagebox.showerror("错误", f"导入前奏视频失败: {str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {str(e)}")

        if os.path.exists(pre_video):
            filename = os.path.basename(pre_video)
            size = os.path.getsize(pre_video) / (1024 * 1024)  # MB
            self.story_status_label.config(text=f"✅ 前奏视频已就绪: {filename} ({size:.1f}MB)", foreground='green')


    def show_story_editor(self):
        pid = self.get_pid()
        language = self.get_language()

        """显示沉浸式故事编辑器"""
        # 创建新窗口
        editor_window = tk.Toplevel(self.root)
        editor_window.title(f"沉浸故事编辑器 - PID: {pid}")
        editor_window.state('zoomed')  # 最大化窗口
        
        # Make the window modal
        editor_window.transient(self.root)  # Set to be on top of the main window
        editor_window.grab_set()  # Make it modal
        editor_window.focus_set()  # Grab focus
        
        # 创建主框架
        main_frame = ttk.Frame(editor_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建标题框架
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 语音配置框架
        voice_config_frame = ttk.LabelFrame(main_frame, text="语音配置", padding=10)
        voice_config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 语音配置区域
        controls_frame = ttk.Frame(voice_config_frame)
        controls_frame.pack(fill=tk.X)
        
        # 旁白语音组
        narrator_frame = ttk.Frame(controls_frame)
        narrator_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(narrator_frame, text="旁白语音").pack(side=tk.LEFT)
        narrator_controls = ttk.Frame(narrator_frame)
        narrator_controls.pack(side=tk.LEFT, padx=(5, 0))
        actor_narrator = ttk.Combobox(narrator_controls, values=config.ACTORS_NARRATOR, state="readonly", width=30)
        actor_narrator.set(config.ACTORS_NARRATOR[0])  # Default to voice1
        actor_narrator.pack(side=tk.TOP)
        
        # add a text fields to keep the story scenarios duration, default to config.VIDEO_DURATION_DEFAULT
        duration_frame = ttk.Frame(controls_frame)
        duration_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(duration_frame, text="片段时长").pack(side=tk.LEFT)
        duration_controls = ttk.Frame(duration_frame)
        duration_controls.pack(side=tk.LEFT, padx=(5, 0))
        duration_entry = ttk.Entry(duration_controls, width=15)
        duration_entry.insert(0, str(7))
        duration_entry.pack(side=tk.TOP)

        # 头部重要操作按钮
        header_actions_frame = ttk.Frame(controls_frame)
        header_actions_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(header_actions_frame, text="选择宣传音频555", 
            command=self.use_promot_story_audio).pack(side=tk.RIGHT, padx=15)

        ttk.Button(header_actions_frame, text="选择短片音乐666", 
            command=self.use_story_music).pack(side=tk.RIGHT, padx=15)

        ttk.Button(header_actions_frame, text="选择前奏视频777", 
            command=self.use_pre_video).pack(side=tk.RIGHT, padx=15)


        ttk.Button(header_actions_frame, text="🎬 宣传短片生成888", 
                  command=self.open_promo_video_gen_dialog, 
                  style="Accent.TButton").pack(side=tk.RIGHT, padx=15)

        ttk.Button(header_actions_frame, text="🎬 宣传短片上传999", 
                  command=self.upload_promo_video, 
                  style="Accent.TButton").pack(side=tk.RIGHT, padx=15)
        

        # 创建动态标题标签
        title_label = ttk.Label(title_frame, text="", font=('Arial', 12, 'bold'))
        title_label.pack()
        
        # 定义更新标题的函数
        def update_title():
            title_text = f"沉浸故事编辑器 - PID: {pid} | 语言: {language} | 旁白: {actor_narrator.get()}"
            title_label.config(text=title_text)
        
        # 初始更新标题
        update_title()
        
        # 绑定语音配置变化事件
        def on_voice_config_change(event=None):
            update_title()
        
        actor_narrator.bind('<<ComboboxSelected>>', on_voice_config_change)
        
        # 添加提示信息
        tip_frame = ttk.Frame(voice_config_frame)
        tip_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(tip_frame, text="💡 提示：语音配置已集成到编辑器中，可直接在此处调整", 
                 font=('Arial', 9), foreground='gray').pack(anchor=tk.W)
        
        # 定义自动保存函数
        def auto_save_story_content():
            """自动保存故事内容到临时文件"""
            try:
                content = story_content_widget.get("1.0", tk.END).strip()
                with open(config.get_project_path(pid) + "/story.srt.json", "w", encoding='utf-8') as f:
                    f.write(content)

            except Exception as e:
                print(f"自动保存故事内容失败: {str(e)}")
        
        # 定义重新生成对话JSON函数
        def on_regenerate_dialog():
            """重新生成沉浸故事对话JSON"""
            # 在后台线程中重新生成
            def regenerate_task():
                try:
                    # 获取选中的prompt pair
                    selected_prompt_name = prompt_selector.get()
                    selected_prompt = config.SPEAKING_PROMPTS[selected_prompt_name]

                    format_args = selected_prompt.get("format_args", {}).copy()  # 复制预设参数

                    formatted_user_prompt = story_content_widget.get("1.0", tk.END).strip()
                    if not formatted_user_prompt or formatted_user_prompt.strip() == "":
                        formatted_user_prompt = self.workflow.transcriber.fetch_text_from_json(config.get_project_path(pid) + "/main.srt.json")
                    else:    
                        auto_save_story_content() 

                    if language == "zh" or language == "tw":
                        lang = "Chinese"
                    else:
                        lang = "English"

                    format_args.update({  # 添加运行时变量
                        "speaker_style": actor_narrator.get(),
                        "language": lang
                    })
                    formatted_system_prompt = selected_prompt["system_prompt"].format(**format_args)
                    print("🤖 系统提示:")
                    print(formatted_system_prompt)

                    story_json_path = config.get_story_json_path(pid)
                    # 调用generate_immersive_story，使用用户输入的故事内容和格式化后的prompt
                    result = self.get_current_workflow().summarizer.generate_json_summary(
                        system_prompt=formatted_system_prompt,
                        user_prompt=formatted_user_prompt,
                        output_path=story_json_path
                    )
 
                    if result:
                        self.root.after(0, lambda: self.load_story_content(story_json_widget))
                        self.root.after(0, lambda: messagebox.showinfo("成功", "重新生成完成！"))
                        # 延迟更新简化内容显示
                        self.root.after(300, update_simplified_content)

                except Exception as e:
                    error_msg = f"重新生成失败: {str(e)}"
                    self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            
            import threading
            thread = threading.Thread(target=regenerate_task)
            thread.daemon = True
            thread.start()


        def on_generate_immersive_story_images():
            """生成故事图像"""
            try:
                # 调用工作流生成图像
                workflow = self.get_current_workflow()                # Use appropriate output widget
                # 在后台线程中生成图像
                def generate_images_task():
                    try:
                        system_prompt = config.STORY_IMAGE_SUMMARY_SYSTEM_PROMPT
                        user_prompt = simplified_content_widget.get(1.0, tk.END)
                        story_summary_content = self.get_current_workflow().summarizer.generate_text_summary(system_prompt, user_prompt, 1)
                        with open(config.get_story_summary_path(pid, language), "w", encoding='utf-8') as f:
                            f.write(story_summary_content)

                        image_style = config.IMAGE_STYLES[0]
                        negative = config.NEGATIVE_PROMPT_OPTIONS[0]

                        # 调用生成图像的方法
                        result = workflow.create_story_images(story_json_widget.get(1.0, tk.END), image_style, config.story_summary_content, negative,"3")
                        
                        if result:
                            self.root.after(0, lambda: messagebox.showinfo("成功", f"故事图像生成完成！\n结果: {result}"))
                        else:
                            self.root.after(0, lambda: messagebox.showerror("错误", "图像生成失败"))

                    except Exception as e:
                        error_msg = f"生成图像失败: {str(e)}"
                        self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
                
                import threading
                thread = threading.Thread(target=generate_images_task)
                thread.daemon = True
                thread.start()

            except Exception as e:
                messagebox.showerror("错误", f"操作失败: {str(e)}")


        # 定义生成音频函数
        def on_generate_audio():
            """生成沉浸故事音频"""
            try:
                # 保存当前编辑的内容
                content = story_json_widget.get(1.0, tk.END).strip()
                if not content:
                    messagebox.showerror("错误", "沉浸故事内容不能为空")
                    return

                story_path = config.get_story_json_path(self.get_pid())
                audio_path = config.get_story_audio_path(self.get_pid())

                with open(story_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                # 验证JSON格式
                try:
                    import json
                    json.loads(content)
                except json.JSONDecodeError as e:
                    messagebox.showerror("错误", f"JSON格式错误: {str(e)}")
                    return
                
                # 停止音频播放器（如果正在播放目标文件）
                if pygame_available and 'audio_player_state' in locals():
                    try:
                        if audio_player_state['is_playing'] or audio_player_state['is_paused']:
                            if audio_player_state['current_file'] == audio_path:
                                print(f"🛑 停止音频播放器，准备生成新音频...")
                                pygame.mixer.music.stop()
                                audio_player_state['is_playing'] = False
                                audio_player_state['is_paused'] = False
                                audio_player_state['position'] = 0
                                if 'play_btn' in locals():
                                    play_btn.config(text="▶️")
                                if 'progress_var' in locals():
                                    progress_var.set(0)
                                if 'time_label' in locals():
                                    time_label.config(text="00:00 / 00:00")
                                if 'stop_position_update' in locals():
                                    stop_position_update()
                    except Exception as e:
                        print(f"⚠️ 停止音频播放器时出错: {str(e)}")
                
                # 调用工作流生成音频
                workflow = self.get_current_workflow()
                
                # 在后台线程中生成音频
                def generate_audio_task():
                    try:
                        duration = float(duration_entry.get().strip())
                        result = workflow.create_story_audio(story_path, audio_path, duration)
                        if result:
                            self.root.after(0, lambda: messagebox.showinfo("成功", f"沉浸故事音频生成完成！\n文件: {result}"))
                            self.root.after(0, self.check_immersive_story_audio_status)
                            # 刷新音频播放器显示
                            if pygame_available:
                                self.root.after(100, refresh_audio_path)
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
                messagebox.showerror("错误", f"操作失败: {str(e)}")


        # Add prompt selector frame before button_frame
        prompt_selector_frame = ttk.Frame(main_frame)
        prompt_selector_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(prompt_selector_frame, text="选择提示词模板:").pack(side=tk.LEFT, padx=(0, 10))
        prompt_selector = ttk.Combobox(prompt_selector_frame, state="readonly")
        prompt_selector.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 从config获取提示词对列表
        prompt_pairs = config.SPEAKING_PROMPTS_LIST
        prompt_selector["values"] = prompt_pairs
        prompt_selector.current(0)  # 默认选择第一个

        # 绑定选择变化事件
        def on_prompt_selection_change(event=None):
            """提示词模板选择变化时重新加载内容"""
            self.load_story_content(story_json_widget)
            # 延迟更新简化内容，确保JSON内容已加载完成
            editor_window.after(200, update_simplified_content)
            # 刷新音频播放器的文件检测
            if pygame_available:
                editor_window.after(100, refresh_audio_path)
        
        prompt_selector.bind('<<ComboboxSelected>>', on_prompt_selection_change)

        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(button_frame, text="重新生成对话111", 
                  command=on_regenerate_dialog).pack(side=tk.LEFT, padx=(20, 20))

        ttk.Button(button_frame, text="生成故事音频222", 
                  command=on_generate_audio).pack(side=tk.LEFT, padx=(20, 20))


        ttk.Button(button_frame, text="生成沉浸故事图像333", 
                  command=on_generate_immersive_story_images).pack(side=tk.LEFT, padx=(20, 20))

        # Audio Player Section
        audio_player_frame = ttk.LabelFrame(main_frame, text="音频播放器", padding=10)
        audio_player_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Audio file info and controls
        audio_info_frame = ttk.Frame(audio_player_frame)
        audio_info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Audio file path display
        audio_file_label = ttk.Label(audio_info_frame, text="音频文件:", font=('TkDefaultFont', 9))
        audio_file_label.pack(side=tk.LEFT)
        
        audio_file_path_var = tk.StringVar()
        audio_file_display = ttk.Label(audio_info_frame, textvariable=audio_file_path_var, 
                                     font=('TkDefaultFont', 8), foreground='gray', wraplength=400)
        audio_file_display.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # Refresh audio path button
        def refresh_audio_path():
            """Refresh the audio file path based on current selection"""
            try:
                audio_filename = "story.wav"
                audio_path = config.get_media_path(self.get_pid()) + "/" + audio_filename
                
                if os.path.exists(audio_path):
                    file_size = os.path.getsize(audio_path) / (1024 * 1024)  # MB
                    audio_file_path_var.set(f"✅ {audio_filename} ({file_size:.1f}MB)")
                    return audio_path
                else:
                    audio_file_path_var.set(f"❌ {audio_filename} 不存在")
                    return None
            except Exception as e:
                audio_file_path_var.set(f"❌ 错误: {str(e)}")
                return None
        
        ttk.Button(audio_info_frame, text="刷新", command=refresh_audio_path).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Audio controls frame
        controls_frame = ttk.Frame(audio_player_frame)
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Initialize pygame mixer for audio playback
        try:
            import pygame
            # Initialize pygame mixer with appropriate settings
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=2048)
            pygame.mixer.init()
            pygame_available = True
            print("✅ pygame mixer initialized successfully")
        except ImportError:
            pygame_available = False
            error_msg = "❌ 需要安装pygame库才能播放音频 (pip install pygame)"
            ttk.Label(controls_frame, text=error_msg, foreground='red').pack()
            print(error_msg)
        except Exception as e:
            pygame_available = False
            error_msg = f"❌ pygame初始化失败: {str(e)}"
            ttk.Label(controls_frame, text=error_msg, foreground='red').pack()
            print(error_msg)
        
        if pygame_available:
            # Audio player state variables
            audio_player_state = {
                'is_playing': False,
                'is_paused': False,
                'current_file': None,
                'duration': 0,
                'position': 0,
                'update_timer': None
            }
            
            # Control buttons frame
            buttons_frame = ttk.Frame(controls_frame)
            buttons_frame.pack(side=tk.LEFT)
            
            def play_audio():
                """Play or resume audio"""
                try:
                    audio_path = refresh_audio_path()
                    if not audio_path:
                        print(f"❌ 无法获取音频文件路径")
                        return
                    
                    print(f"🎵 尝试播放音频: {audio_path}")
                    print(f"🔍 文件存在: {os.path.exists(audio_path)}")
                    
                    if audio_player_state['is_paused'] and audio_player_state['current_file'] == audio_path:
                        # Resume paused audio
                        pygame.mixer.music.unpause()
                        audio_player_state['is_paused'] = False
                        audio_player_state['is_playing'] = True
                        play_btn.config(text="⏸️")
                        start_position_update()
                        print(f"▶️ 恢复播放")
                    else:
                        # Load and play new audio
                        pygame.mixer.music.load(audio_path)
                        pygame.mixer.music.play()
                        audio_player_state['is_playing'] = True
                        audio_player_state['is_paused'] = False
                        audio_player_state['current_file'] = audio_path
                        audio_player_state['position'] = 0
                        
                        # Get audio duration using wave module
                        try:
                            import wave
                            with wave.open(audio_path, 'r') as wav_file:
                                frames = wav_file.getnframes()
                                rate = wav_file.getframerate()
                                audio_player_state['duration'] = frames / float(rate)
                                print(f"⏱️ 音频时长: {audio_player_state['duration']:.1f} 秒")
                        except Exception as duration_error:
                            audio_player_state['duration'] = 0
                            print(f"⚠️ 无法获取音频时长: {duration_error}")
                        
                        play_btn.config(text="⏸️")
                        start_position_update()
                        print(f"🎵 开始播放: {os.path.basename(audio_path)}")
                        
                except Exception as e:
                    error_msg = f"❌ 播放失败: {str(e)}"
                    audio_file_path_var.set(error_msg)
                    print(error_msg)
                    import traceback
                    traceback.print_exc()
            
            def pause_audio():
                """Pause or resume audio"""
                if audio_player_state['is_playing']:
                    pygame.mixer.music.pause()
                    audio_player_state['is_paused'] = True
                    audio_player_state['is_playing'] = False
                    play_btn.config(text="▶️")
                    stop_position_update()
                elif audio_player_state['is_paused']:
                    pygame.mixer.music.unpause()
                    audio_player_state['is_paused'] = False
                    audio_player_state['is_playing'] = True
                    play_btn.config(text="⏸️")
                    start_position_update()
            
            def stop_audio():
                """Stop audio playback"""
                pygame.mixer.music.stop()
                audio_player_state['is_playing'] = False
                audio_player_state['is_paused'] = False
                audio_player_state['position'] = 0
                play_btn.config(text="▶️")
                progress_var.set(0)
                time_label.config(text="00:00 / 00:00")
                stop_position_update()
            
            def start_position_update():
                """Start updating position"""
                update_position()
            
            def stop_position_update():
                """Stop updating position"""
                if audio_player_state['update_timer']:
                    editor_window.after_cancel(audio_player_state['update_timer'])
                    audio_player_state['update_timer'] = None
            
            def update_position():
                """Update playback position"""
                if audio_player_state['is_playing']:
                    if pygame.mixer.music.get_busy():
                        audio_player_state['position'] += 0.1
                        
                        # Update progress bar
                        if audio_player_state['duration'] > 0:
                            progress = (audio_player_state['position'] / audio_player_state['duration']) * 100
                            progress_var.set(min(progress, 100))
                        
                        # Update time display
                        current_min = int(audio_player_state['position'] // 60)
                        current_sec = int(audio_player_state['position'] % 60)
                        total_min = int(audio_player_state['duration'] // 60)
                        total_sec = int(audio_player_state['duration'] % 60)
                        time_label.config(text=f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}")
                        
                        # Schedule next update
                        audio_player_state['update_timer'] = editor_window.after(100, update_position)
                    else:
                        # Audio finished
                        stop_audio()
            
            # Play/Pause button
            def toggle_play_pause():
                """Toggle between play and pause"""
                if not audio_player_state['is_playing'] and not audio_player_state['is_paused']:
                    # Start playing
                    play_audio()
                else:
                    # Pause or resume
                    pause_audio()
            
            play_btn = ttk.Button(buttons_frame, text="▶️", command=toggle_play_pause, width=4)
            play_btn.pack(side=tk.LEFT, padx=(0, 5))
            
            # Stop button
            stop_btn = ttk.Button(buttons_frame, text="⏹️", command=stop_audio, width=4)
            stop_btn.pack(side=tk.LEFT, padx=(0, 10))
            
            # Progress bar frame
            progress_frame = ttk.Frame(controls_frame)
            progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 10))
            
            # Progress bar
            progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
            progress_bar.pack(fill=tk.X, pady=(0, 5))
            
            # Time display
            time_label = ttk.Label(progress_frame, text="00:00 / 00:00", font=('TkDefaultFont', 8))
            time_label.pack()
            
            # Bind progress bar click for seeking
            def on_progress_click(event):
                """Handle progress bar click for seeking"""
                if audio_player_state['duration'] > 0 and audio_player_state['current_file']:
                    # Calculate clicked position
                    click_pos = event.x / progress_bar.winfo_width()
                    new_position = click_pos * audio_player_state['duration']
                    
                    # For pygame, we need to restart from the beginning
                    # This is a limitation of pygame mixer
                    if audio_player_state['is_playing'] or audio_player_state['is_paused']:
                        pygame.mixer.music.load(audio_player_state['current_file'])
                        pygame.mixer.music.play(start=new_position)
                        audio_player_state['position'] = new_position
                        audio_player_state['is_playing'] = True
                        audio_player_state['is_paused'] = False
                        play_btn.config(text="⏸️")
                        start_position_update()
            
            progress_bar.bind('<Button-1>', on_progress_click)
            
            # Volume control frame
            volume_frame = ttk.Frame(controls_frame)
            volume_frame.pack(side=tk.RIGHT, padx=(10, 0))
            
            ttk.Label(volume_frame, text="🔊").pack(side=tk.LEFT)
            
            def on_volume_change(value):
                """Handle volume change"""
                volume = float(value) / 100
                pygame.mixer.music.set_volume(volume)
            
            volume_scale = ttk.Scale(volume_frame, from_=0, to=100, orient=tk.HORIZONTAL, 
                                   command=on_volume_change, length=100)
            volume_scale.set(70)  # Default volume
            volume_scale.pack(side=tk.LEFT, padx=(5, 0))
            
            # Cleanup function for window close
            def cleanup_audio():
                """Cleanup audio resources"""
                stop_position_update()
                try:
                    pygame.mixer.music.stop()
                    pygame.mixer.quit()
                except:
                    pass
            
            # Bind cleanup to window close
            original_destroy = editor_window.destroy
            def enhanced_destroy():
                cleanup_audio()
                original_destroy()
            editor_window.destroy = enhanced_destroy
            
            # Smart audio file detection
            def detect_available_audio_files():
                """Detect and display all available audio files"""
                try:
                    audio_dir = config.get_media_path(self.get_pid())
                    available_files = []
                    
                    # Check for both possible audio files
                    short_path = config.get_short_audio_path(self.get_pid())
                    story_path = config.get_story_audio_path(self.get_pid())
                    
                    if os.path.exists(short_path):
                        size = os.path.getsize(short_path) / (1024 * 1024)
                        available_files.append(f"{short_path} ({size:.1f}MB)")
                    
                    if os.path.exists(story_path):
                        size = os.path.getsize(story_path) / (1024 * 1024)
                        available_files.append(f"{story_path} ({size:.1f}MB)")
                    
                    if available_files:
                        print(f"🎵 检测到音频文件: {', '.join(available_files)}")
                        # Set initial display based on current prompt selection
                        refresh_audio_path()
                    else:
                        audio_file_path_var.set("❌ 未找到音频文件 (short.wav 或 story.wav)")
                        print(f"❌ 音频目录中未找到文件: {audio_dir}")
                        
                except Exception as e:
                    audio_file_path_var.set(f"❌ 检测音频文件失败: {str(e)}")
                    print(f"❌ 检测音频文件失败: {str(e)}")
            
            # Initial detection and refresh
            detect_available_audio_files()
            
            # Add detection button for debugging
            debug_frame = ttk.Frame(audio_player_frame)
            debug_frame.pack(fill=tk.X, pady=(5, 0))
            
            ttk.Button(debug_frame, text="检测所有音频文件", command=detect_available_audio_files).pack(side=tk.LEFT, padx=(0, 10))
            
            def open_audio_folder():
                """Open the audio folder in file explorer"""
                try:
                    audio_dir = config.get_media_path(self.get_pid())
                    if os.path.exists(audio_dir):
                        import subprocess
                        import platform
                        if platform.system() == "Windows":
                            subprocess.run(['explorer', audio_dir])
                        elif platform.system() == "Darwin":  # macOS
                            subprocess.run(['open', audio_dir])
                        else:  # Linux
                            subprocess.run(['xdg-open', audio_dir])
                    else:
                        print(f"❌ 音频目录不存在: {audio_dir}")
                except Exception as e:
                    print(f"❌ 打开音频文件夹失败: {str(e)}")
            
            ttk.Button(debug_frame, text="打开音频文件夹", command=open_audio_folder).pack(side=tk.LEFT)

        # at this row, want to show the audio player to review the result audio  (has player control)  

        # 保存JSON内容的函数
        def save_story_json_content():
            """保存story_json_widget的内容到对应的文件"""
            try:
                # 获取JSON内容
                json_content = story_json_widget.get(1.0, tk.END).strip()
                
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
                file_path = config.get_story_json_path(pid)
                
                # 确保目录存在
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # 保存文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(json_content)
                
                update_simplified_content()

                print(f"✅ 已保存JSON内容到: {file_path}")
                messagebox.showinfo("成功", f"JSON内容已保存到:\n{os.path.basename(file_path)}")
                
            except Exception as e:
                error_msg = f"保存JSON内容失败: {str(e)}"
                print(f"❌ {error_msg}")
                messagebox.showerror("错误", error_msg)
        
        # 保存按钮
        ttk.Button(button_frame, text="保存JSON", 
                  command=save_story_json_content).pack(side=tk.RIGHT, padx=(0, 10))
        
        ttk.Button(button_frame, text="关闭", 
                  command=editor_window.destroy).pack(side=tk.RIGHT)
        
        # 文件路径显示
        path_frame = ttk.Frame(main_frame)
        path_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 创建双栏编辑区域
        edit_frame = ttk.Frame(main_frame)
        edit_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建水平分割窗格
        paned_window = ttk.PanedWindow(edit_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # 左侧：故事内容输入区域
        left_frame = ttk.LabelFrame(paned_window, text="故事内容输入", padding=10)
        paned_window.add(left_frame, weight=1)
        
        # 创建左侧的垂直分割窗格
        left_paned = ttk.PanedWindow(left_frame, orient=tk.VERTICAL)
        left_paned.pack(fill=tk.BOTH, expand=True)
        
        # 上部：故事内容输入区域 (2/3)
        story_input_frame = ttk.Frame(left_paned)
        left_paned.add(story_input_frame, weight=2)
        
        story_content_widget = scrolledtext.ScrolledText(story_input_frame, wrap=tk.WORD, font=('Consolas', 11))
        story_content_widget.pack(fill=tk.BOTH, expand=True)
        
        # 下部：简化JSON内容显示区域 (1/3)
        simplified_frame = ttk.LabelFrame(left_paned, text="对话内容预览", padding=5)
        left_paned.add(simplified_frame, weight=1)
        
        # 创建简化内容显示区域
        simplified_content_frame = ttk.Frame(simplified_frame)
        simplified_content_frame.pack(fill=tk.BOTH, expand=True)
        
        simplified_content_widget = tk.Text(simplified_content_frame, wrap=tk.WORD, font=('Arial', 9),
                                          state=tk.DISABLED, bg='#f0f0f0', height=24)
        simplified_scrollbar = ttk.Scrollbar(simplified_content_frame, orient=tk.VERTICAL, command=simplified_content_widget.yview)
        simplified_content_widget.configure(yscrollcommand=simplified_scrollbar.set)
        
        simplified_content_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        simplified_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 定义解析JSON并提取对话内容的函数
        def extract_dialogue_content(json_text):
            """从JSON文本中提取对话内容并格式化为简化显示"""
            try:
                import json
                data = json.loads(json_text.strip())
                if isinstance(data, list):
                    dialogue_lines = []
                    for i, item in enumerate(data, 1):
                        if isinstance(item, dict) and 'content' in item:
                            content = item['content'].strip()
                            # 限制每行长度，避免过长
                            if len(content) > 100:
                                content = content[:100] + "..."
                            dialogue_lines.append(f"  {content}")
                    v = "\n".join(dialogue_lines)
                    return self.workflow.transcriber.chinese_convert(v, "zh")
                else:
                    return "JSON格式不是数组"
            except json.JSONDecodeError:
                return "JSON格式错误"
            except Exception as e:
                return f"解析错误: {str(e)}"
        
        # 定义更新简化对话内容的函数
        def update_simplified_content():
            """更新简化对话内容显示"""
            try:
                json_content = story_json_widget.get(1.0, tk.END)
                simplified_content = extract_dialogue_content(json_content)
                with open(config.get_story_extract_text_path(pid), 'w', encoding='utf-8') as f:
                    f.write(simplified_content)

                simplified_content_widget.config(state=tk.NORMAL)
                simplified_content_widget.delete(1.0, tk.END)
                simplified_content_widget.insert(1.0, simplified_content)
                simplified_content_widget.config(state=tk.DISABLED)
                
                promote_srt_path = config.get_promote_srt_path(pid)
                story_audio = config.get_story_audio_path(pid)
                story_audio_duration = self.workflow.ffmpeg_audio_processor.get_duration(story_audio)
                simplified_content_lines = simplified_content.split("\n")
                # make a srt file, show time split for each line from story_audio_duration
                start_seconds = 0
                line_duration = story_audio_duration / len(simplified_content_lines)
                srt_content = ""
                for i, line in enumerate(simplified_content_lines):
                    end_seconds = start_seconds + line_duration
                    srt_content += f"{i+1}\n{start_seconds} --> {end_seconds}\n{line}\n\n"
                    start_seconds = end_seconds
                 
                srt_content = self.workflow.transcriber.chinese_convert(srt_content, self.get_language())
                with open(promote_srt_path, 'w', encoding='utf-8') as f:
                    f.write(srt_content)

            except Exception as e:
                simplified_content_widget.config(state=tk.NORMAL)
                simplified_content_widget.delete(1.0, tk.END)
                simplified_content_widget.insert(1.0, f"更新失败: {str(e)}")
                simplified_content_widget.config(state=tk.DISABLED)
        
        # 右侧：生成的JSON结果编辑区域
        right_frame = ttk.LabelFrame(paned_window, text="生成的对话JSON结果", padding=10)
        paned_window.add(right_frame, weight=1)
        
        # Enable undo/redo functionality for the JSON editor
        story_json_widget = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, font=('Consolas', 11), 
                                                      undo=True, maxundo=-1)
        story_json_widget.pack(fill=tk.BOTH, expand=True)
        
        # Add undo/redo keyboard shortcuts
        def undo_action(event=None):
            """Perform undo operation"""
            try:
                story_json_widget.edit_undo()
            except tk.TclError:
                pass  # No more undo operations available
            return "break"  # Prevent default handling
        
        def redo_action(event=None):
            """Perform redo operation"""
            try:
                story_json_widget.edit_redo()
            except tk.TclError:
                pass  # No more redo operations available
            return "break"  # Prevent default handling
        
        # Bind keyboard shortcuts for undo/redo
        story_json_widget.bind('<Control-z>', undo_action)
        story_json_widget.bind('<Control-y>', redo_action)
        story_json_widget.bind('<Control-Shift-Z>', redo_action)  # Alternative redo shortcut
        
        # 绑定JSON编辑器内容变化事件，更新简化内容显示
        def on_json_content_change(event=None):
            """JSON内容改变时更新简化显示"""
            editor_window.after(100, update_simplified_content)  # 延迟100ms更新，避免频繁更新
        
        story_json_widget.bind('<KeyRelease>', on_json_content_change)
        story_json_widget.bind('<Button-1>', on_json_content_change)
        story_json_widget.bind('<FocusOut>', on_json_content_change)
        
        # 加载现有内容
        self.load_story_content(story_json_widget)
        
        # 初始化简化内容显示
        editor_window.after(200, update_simplified_content)
        
        

        # 加载临时故事内容
        def load_temp_story_content():
            """加载临时故事内容"""
            try:
                content = self.workflow.transcriber.fetch_text_from_json(config.get_project_path(self.get_pid()) + "/story.srt.json")

                if content:
                    story_content_widget.delete(1.0, tk.END)
                    story_content_widget.insert(1.0, content)
                    print(f"✅ 已加载临时故事内容")
                else:
                    print(f"ℹ️ 未找到临时故事内容")
            except Exception as e:
                print(f"❌ 加载临时故事内容失败: {str(e)}")
        
        # 初始加载临时故事内容
        load_temp_story_content()
        
        # 绑定自动保存事件
        def on_content_change(event=None):
            """内容改变时自动保存"""
            editor_window.after(1000, auto_save_story_content)  # 延迟1秒保存
        
        story_content_widget.bind('<KeyRelease>', on_content_change)
        
        # 窗口关闭时保存内容
        def on_window_close():
            """窗口关闭时保存内容"""
            auto_save_story_content()
            editor_window.destroy()
        
        editor_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        # 居中显示
        editor_window.update_idletasks()
        x = (editor_window.winfo_screenwidth() // 2) - (editor_window.winfo_width() // 2)
        y = (editor_window.winfo_screenheight() // 2) - (editor_window.winfo_height() // 2)
        editor_window.geometry(f"+{x}+{y}")


    def load_story_content(self, text_widget):
        """加载沉浸故事内容到文本框"""
        try:
            file_path = config.get_story_json_path(self.get_pid())

            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                text_widget.delete(1.0, tk.END)
                text_widget.insert(1.0, content)
            else:
                text_widget.delete(1.0, tk.END)
                text_widget.insert(1.0, "[]")  # 空的JSON数组
        except Exception as e:
            text_widget.delete(1.0, tk.END)
            text_widget.insert(1.0, f"加载失败: {str(e)}")


    def show_title_selection_dialog(self):
        """显示标题选择对话框"""
        dialog = TitleSelectionDialog(self.root, self.get_pid(), self.get_language(), self.video_title.get(), self.video_tags.get())
        result, selected_title, selected_tags = dialog.show()
        
        if result == 'confirm':
            # 更新GUI中的标题显示
            if selected_title:
                self.video_title.delete(0, tk.END)
                self.video_title.insert(0, selected_title)
            
            # 更新GUI中的标签显示
            if selected_tags:
                self.video_tags.delete(0, tk.END)
                self.video_tags.insert(0, selected_tags)
            
            # 同步标题到所有地方
            if selected_title:
                try:
                    # 同步到workflow
                    self.workflow.title = selected_title
                    
                    # 保存配置
                    self.save_project_config()
                    
                    print(f"✅ 标题已更新: {selected_title}")
                    if selected_tags:
                        print(f"✅ 标签已更新: {selected_tags}")
                        
                except Exception as e:
                    print(f"❌ 同步标题失败: {e}")
        
        return False


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
        audio_file = config.get_short_audio_path(self.get_pid())
        if not os.path.exists(audio_file):
            messagebox.showerror("错误", f"音频文件不存在: {audio_file}")
            return
    
        print(f"🎵 选择的音频文件: {audio_file}")
 
        start_duration=10
        image_duration=5
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "open_promo_video_gen_dialog",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": self.get_current_workflow().pid
        }
        
        def run_task():
            try:
                print(f"🎬 开始生成频道宣传视频...")
                title = self.video_title.get().strip()
                
                # 调用工作流的方法
                result_video_path = self.get_current_workflow().create_channel_promote_video(audio_file, title, self.project_keywords.get().strip(), config.get_promote_srt_path(self.get_pid()), start_duration, image_duration)
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

    # Script tab methods moved from GUI_Magic_Workflow.py
    
    def create_script_tab(self):
        """创建脚本生成标签页"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="生成脚本")
        
        # 创建主容器，使用垂直分布
        main_container = ttk.Frame(tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 输入区域
        input_frame = ttk.LabelFrame(main_container, text="脚本生成", padding=10)
        input_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 执行按钮区域
        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)
        
        ttk.Button(button_frame, text="加载所有文件", 
                  command=self.load_all_script_files).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="保存所有文件", 
                  command=self.save_all_script_files).pack(side=tk.LEFT, padx=(0, 10))
        
        # 文件编辑区域 - 使用标签页组织
        edit_frame = ttk.LabelFrame(main_container, text="文件编辑器", padding=10)
        edit_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        
        # 创建文件编辑标签页
        self.file_editors_notebook = ttk.Notebook(edit_frame)
        self.file_editors_notebook.pack(fill=tk.BOTH, expand=True)
        
        # 创建各个文件编辑标签页
        self.create_file_editor_tabs()
        
        # 启动文件修改检查定时器（仅在脚本标签页激活时运行）
        self.json_file_check_timer_id = None
        self.start_json_file_check_timer()
        
        # 输出日志区域
        output_frame = ttk.LabelFrame(main_container, text="输出日志", padding=10)
        output_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.script_output = scrolledtext.ScrolledText(output_frame, height=8)
        self.script_output.pack(fill=tk.BOTH, expand=True)

    def create_file_editor_tabs(self):
        """创建文件编辑器标签页"""
        # 定义文件编辑器配置
        editors_config = [
            {
                'name': 'scenarios_json', 
                'title': '场景文件 (JSON)',
                'file_suffix': 'full_scenarios.json',
                'file_type': 'json',
                'description': '存储所有场景的详细信息，包括时间戳和音频信息'
            },
            {
                'name': 'short_conversation_json',
                'title': '短视频对话 (JSON)',
                'file_suffix': 'shot_story.json',
                'file_type': 'json',
                'description': '短视频对话脚本，用于生成音频和视频'
            },
            {
                'name': 'story_json',
                'title': '沉浸故事 (JSON)',
                'file_suffix': 'story.json',
                'file_type': 'json',
                'description': '沉浸式故事脚本，用于生成沉浸式音频体验'
            },
            {
                'name': 'script_srt',
                'title': '字幕文件 (SRT)',
                'file_suffix': 'main.srt',
                'file_type': 'text',
                'description': '视频的时间轴字幕文件'
            },
            {
                'name': 'sum_long',
                'title': '详细摘要 (TXT)',
                'file_suffix': 'main_summary.txt',
                'file_type': 'text',
                'description': '视频内容的详细摘要'
            },
            {
                'name': 'sum_short',
                'title': '简短摘要 (TXT)',
                'file_suffix': 'story_summary.txt',
                'file_type': 'text',
                'description': '视频内容的简短摘要，用于视频描述'
            }
        ]
        
        # 存储编辑器引用
        self.file_editors = {}
        
        for editor_config in editors_config:
            self.create_single_file_editor(editor_config)

    def create_single_file_editor(self, config):
        """创建单个文件编辑器标签页"""
        # 创建标签页框架
        tab_frame = ttk.Frame(self.file_editors_notebook)
        self.file_editors_notebook.add(tab_frame, text=config['title'])
        
        # 创建顶部信息和按钮区域
        header_frame = ttk.Frame(tab_frame)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 文件描述
        desc_label = ttk.Label(header_frame, text=config['description'], 
                              font=('TkDefaultFont', 8), foreground='gray')
        desc_label.pack(side=tk.LEFT)
        
        # 按钮区域
        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        # 加载按钮
        load_btn = ttk.Button(btn_frame, text="加载", 
                             command=lambda: self.load_file_content(config['name']))
        load_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 保存按钮  
        save_btn = ttk.Button(btn_frame, text="保存",
                             command=lambda: self.save_file_content(config['name']))
        save_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 如果是JSON文件，添加格式化按钮
        if config['file_type'] == 'json':
            format_btn = ttk.Button(btn_frame, text="格式化",
                                   command=lambda: self.format_json_content(config['name']))
            format_btn.pack(side=tk.LEFT, padx=(0, 5))
            
            # 如果是scenarios JSON，添加更新时长按钮
            if config['name'] == 'scenarios_json':
                duration_btn = ttk.Button(btn_frame, text="更新时长",
                                        command=lambda: self.update_duration_displays())
                duration_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 刷新按钮
        refresh_btn = ttk.Button(btn_frame, text="刷新",
                               command=lambda: self.refresh_file_content(config['name']))
        refresh_btn.pack(side=tk.LEFT)

        # Duration display area for scenarios JSON files
        duration_frame = None
        if config['name'] == 'scenarios_json':
            duration_frame = ttk.Frame(tab_frame)
            duration_frame.pack(fill=tk.X, pady=(0, 5))
            
            # Duration label
            duration_label = ttk.Label(duration_frame, text="场景时长 (秒):", 
                                     font=('TkDefaultFont', 9, 'bold'), foreground='blue')
            duration_label.pack(side=tk.LEFT, padx=(0, 10))
            
            # Duration display text
            duration_display = ttk.Label(duration_frame, text="未加载数据", 
                                       font=('TkDefaultFont', 8), foreground='gray',
                                       wraplength=800)
            duration_display.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 文件路径显示
        path_frame = ttk.Frame(tab_frame)
        path_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(path_frame, text="文件路径:", font=('TkDefaultFont', 8)).pack(side=tk.LEFT)
        path_label = ttk.Label(path_frame, text="", font=('TkDefaultFont', 8, 'italic'), 
                              foreground='blue')
        path_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # 编辑器区域
        editor_frame = ttk.Frame(tab_frame)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建文本编辑器
        editor = scrolledtext.ScrolledText(editor_frame, height=20, wrap=tk.WORD)
        editor.pack(fill=tk.BOTH, expand=True)
        
        # 存储编辑器和配置信息
        editor_info = {
            'editor': editor,
            'config': config,
            'path_label': path_label,
            'last_modified_time': None  # 用于跟踪文件修改时间
        }
        
        # Add duration display reference if it exists
        if duration_frame is not None:
            editor_info['duration_display'] = duration_display
        
        self.file_editors[config['name']] = editor_info

    def get_file_path(self, editor_name):
        """获取文件的完整路径"""
        workflow = self.get_current_workflow()
        
        config = self.file_editors[editor_name]['config']
        file_suffix = config['file_suffix']
       
        return f"{workflow.project_path}/{file_suffix}"

    def load_file_content(self, editor_name):
        """加载文件内容到编辑器"""
        file_path = self.get_file_path(editor_name)
        if file_path is None:
            return
        
        editor_info = self.file_editors[editor_name]
        editor = editor_info['editor']
        path_label = editor_info['path_label']
        config = editor_info['config']
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 清空编辑器并插入内容
                editor.delete("1.0", tk.END)
                editor.insert("1.0", content)
                
                # 更新路径显示
                path_label.config(text=file_path)
                
                # 记录文件修改时间
                try:
                    editor_info['last_modified_time'] = os.path.getmtime(file_path)
                except:
                    pass
                
                self.log_to_output(self.script_output, 
                                 f"✅ 已加载{config['title']}: {os.path.basename(file_path)}")
                
                # 如果是JSON文件且是scenarios，更新时长显示
                if config['file_type'] == 'json' and editor_name == 'scenarios_json':
                    self.root.after(50, self.update_duration_displays)
            else:
                editor.delete("1.0", tk.END)
                editor.insert("1.0", f"// {config['title']}不存在，请先生成脚本")
                path_label.config(text=f"文件不存在: {file_path}")
                self.log_to_output(self.script_output, 
                                 f"⚠️ {config['title']}不存在: {file_path}")
                
        except Exception as e:
            self.log_to_output(self.script_output, f"❌ 加载{config['title']}失败: {str(e)}")

    def save_file_content(self, editor_name):
        """保存编辑器内容到文件"""
        file_path = self.get_file_path(editor_name)
        if file_path is None:
            return
        
        editor_info = self.file_editors[editor_name]
        editor = editor_info['editor']
        config = editor_info['config']
        
        try:
            # 获取编辑器中的内容
            content = editor.get("1.0", tk.END).strip()
            
            if not content or content.startswith("//"):
                self.log_to_output(self.script_output, f"⚠️ 没有有效的内容可保存到{config['title']}")
                return
            
            # 如果是JSON文件，验证格式
            if config['file_type'] == 'json':
                try:
                    json.loads(content)
                except json.JSONDecodeError as e:
                    messagebox.showerror("JSON格式错误", f"{config['title']}格式不正确:\n{str(e)}")
                    return
            
            # 确保项目目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.log_to_output(self.script_output, 
                             f"✅ {config['title']}已保存: {os.path.basename(file_path)}")
            messagebox.showinfo("成功", f"{config['title']}保存成功！")
            
        except Exception as e:
            self.log_to_output(self.script_output, f"❌ 保存{config['title']}失败: {str(e)}")
            messagebox.showerror("保存失败", f"保存{config['title']}失败:\n{str(e)}")

    def format_json_content(self, editor_name):
        """格式化JSON内容"""
        editor_info = self.file_editors[editor_name]
        editor = editor_info['editor']
        config = editor_info['config']
        
        if config['file_type'] != 'json':
            return
        
        try:
            content = editor.get("1.0", tk.END).strip()
            
            if not content or content.startswith("//"):
                self.log_to_output(self.script_output, f"⚠️ 没有有效的JSON内容可格式化")
                return
            
            # 解析并格式化JSON
            parsed_json = json.loads(content)
            formatted_content = json.dumps(parsed_json, ensure_ascii=False, indent=2)
            
            # 更新编辑器内容
            editor.delete("1.0", tk.END)
            editor.insert("1.0", formatted_content)
            
            self.log_to_output(self.script_output, f"✅ {config['title']}已格式化")
            
            # 如果是scenarios，更新时长显示
            if editor_name == 'scenarios_json':
                self.root.after(50, self.update_duration_displays)
            
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON格式错误", f"{config['title']}格式不正确:\n{str(e)}")
        except Exception as e:
            self.log_to_output(self.script_output, f"❌ 格式化失败: {str(e)}")

    def refresh_file_content(self, editor_name):
        """刷新文件内容（重新加载）"""
        self.load_file_content(editor_name)

    def load_all_script_files(self):
        """加载所有脚本相关文件"""
        loaded_files = []
        for editor_name in self.file_editors.keys():
            file_path = self.get_file_path(editor_name)
            if file_path and os.path.exists(file_path):
                self.load_file_content(editor_name)
                loaded_files.append(self.file_editors[editor_name]['config']['title'])
        
        if loaded_files:
            self.log_to_output(self.script_output, f"🔄 已加载现有文件: {', '.join(loaded_files)}")
            # 更新时长显示
            self.root.after(100, self.update_duration_displays)
        else:
            self.log_to_output(self.script_output, "⚠️ 未找到可加载的脚本文件")

    def save_all_script_files(self):
        """保存所有脚本相关文件"""
        saved_count = 0
        for editor_name in self.file_editors.keys():
            try:
                self.save_file_content(editor_name)
                saved_count += 1
            except:
                pass
        self.log_to_output(self.script_output, f"💾 已保存 {saved_count} 个文件")

    def load_scenarios_json(self):
        """加载scenarios.json文件"""
        if hasattr(self, 'file_editors') and 'scenarios_json' in self.file_editors:
            self.load_file_content('scenarios_json')

    def save_scenarios_json(self):
        """保存scenarios.json文件"""
        if hasattr(self, 'file_editors') and 'scenarios_json' in self.file_editors:
            self.save_file_content('scenarios_json')

    def format_scenarios_json(self):
        """格式化scenarios.json内容"""
        if hasattr(self, 'file_editors') and 'scenarios_json' in self.file_editors:
            self.format_json_content('scenarios_json')

    def extract_durations_from_json(self, json_content, data_type):
        """从JSON内容中提取时长信息
        
        Args:
            json_content: JSON字符串内容
            data_type: 'scenarios' 
        
        Returns:
            list: 时长列表（秒）
        """
        durations = []
        
        try:
            data = json.loads(json_content)
            
            if data_type == 'scenarios':
                # 从scenarios中提取duration字段
                self.log_to_output(self.script_output, f"🔍 scenarios数据类型: {type(data)}, 长度: {len(data) if isinstance(data, list) else 'N/A'}")
                
                if isinstance(data, list):
                    for i, scenario in enumerate(data):
                        if isinstance(scenario, dict) and 'duration' in scenario:
                            duration = scenario.get('duration', 0)
                            try:
                                durations.append(float(duration))
                            except (ValueError, TypeError):
                                durations.append(0.0)
                                if i < 3:  # 只显示前3个的详细信息
                                    self.log_to_output(self.script_output, f"🔍 场景{i}: duration转换失败: {duration}")
                        else:
                            durations.append(0.0)
                            if i < 3:
                                available_keys = list(scenario.keys())[:5] if isinstance(scenario, dict) else []
                                self.log_to_output(self.script_output, f"🔍 场景{i}: 无duration字段, 可用字段: {available_keys}")
                else:
                    self.log_to_output(self.script_output, f"❌ scenarios数据不是列表格式: {type(data)}")
                    
        except json.JSONDecodeError as e:
            self.log_to_output(self.script_output, f"❌ JSON解析失败: {str(e)[:100]}")
        except Exception as e:
            self.log_to_output(self.script_output, f"❌ 时长提取失败: {str(e)[:100]}")
        
        return durations

    def update_duration_displays(self):
        """更新时长显示"""
        self.log_to_output(self.script_output, "🔍 开始更新时长显示...")
        
        # 更新scenarios时长显示
        if 'scenarios_json' in self.file_editors and 'duration_display' in self.file_editors['scenarios_json']:
            self.log_to_output(self.script_output, "🔍 正在处理scenarios时长...")
            scenarios_editor = self.file_editors['scenarios_json']['editor']
            scenarios_content = scenarios_editor.get("1.0", tk.END).strip()
            
            if scenarios_content and scenarios_content != "" and not scenarios_content.startswith("//"):
                self.log_to_output(self.script_output, f"🔍 scenarios内容长度: {len(scenarios_content)} 字符")
                scenario_durations = self.extract_durations_from_json(scenarios_content, 'scenarios')
                
                if scenario_durations and any(d > 0 for d in scenario_durations):
                    # 格式化显示：保留1位小数，用颜色标识过长的场景
                    duration_texts = []
                    for i, duration in enumerate(scenario_durations):
                        if duration > 15:  # 超过15秒的场景用红色警告
                            duration_texts.append(f"⚠️{duration:.1f}")
                        elif duration > 12:  # 超过12秒的场景用橙色提醒
                            duration_texts.append(f"⚡{duration:.1f}")
                        else:
                            duration_texts.append(f"{duration:.1f}")
                    
                    display_text = f"[{', '.join(duration_texts)}]"
                    total_duration = sum(scenario_durations)
                    avg_duration = total_duration / len(scenario_durations) if scenario_durations else 0
                    display_text += f" | 总计: {total_duration:.1f}s, 平均: {avg_duration:.1f}s, 共{len(scenario_durations)}个"
                    
                    self.file_editors['scenarios_json']['duration_display'].config(
                        text=display_text, foreground='black')
                    self.log_to_output(self.script_output, f"✅ 场景时长已更新: 平均 {avg_duration:.1f}s, 共{len(scenario_durations)}个场景")
                else:
                    self.file_editors['scenarios_json']['duration_display'].config(
                        text="无法解析场景时长数据 (可能缺少duration字段)", foreground='red')
                    self.log_to_output(self.script_output, f"❌ 场景时长解析失败，提取到 {len(scenario_durations)} 个时长值")
            else:
                self.file_editors['scenarios_json']['duration_display'].config(
                    text="未加载数据", foreground='gray')
                self.log_to_output(self.script_output, "⚠️ scenarios编辑器为空或包含默认文本")
        else:
            self.log_to_output(self.script_output, "⚠️ scenarios_json编辑器或duration_display不存在")

    def check_and_reload_modified_json_files(self):
        """检查JSON文件是否被外部修改，如果是则重新加载并更新时长显示"""
        try:
            modified_files = []
            
            # 只检查scenarios JSON文件
            for editor_name in ['scenarios_json']:
                if editor_name not in self.file_editors:
                    continue
                    
                editor_info = self.file_editors[editor_name]
                file_path = self.get_file_path(editor_name)
                
                if not file_path or not os.path.exists(file_path):
                    continue
                
                try:
                    # 获取文件的修改时间
                    current_mtime = os.path.getmtime(file_path)
                    last_known_mtime = editor_info.get('last_modified_time')
                    
                    # 如果文件修改时间发生变化，说明文件被外部修改
                    if last_known_mtime is not None and current_mtime > last_known_mtime:
                        self.log_to_output(self.script_output, f"🔄 检测到{editor_info['config']['title']}被外部修改，正在重新加载...")
                        
                        # 重新加载文件内容
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        editor = editor_info['editor']
                        editor.delete("1.0", tk.END)
                        editor.insert("1.0", content)
                        
                        # 更新修改时间
                        editor_info['last_modified_time'] = current_mtime
                        modified_files.append(editor_info['config']['title'])
                        
                    elif last_known_mtime is None:
                        # 第一次记录修改时间
                        editor_info['last_modified_time'] = current_mtime
                        
                except Exception as e:
                    self.log_to_output(self.script_output, f"❌ 检查文件修改时间失败 {file_path}: {str(e)}")
            
            # 如果有文件被修改，更新时长显示
            if modified_files:
                self.log_to_output(self.script_output, f"✅ 已重新加载外部修改的文件: {', '.join(modified_files)}")
                self.root.after(50, self.update_duration_displays)
                
        except Exception as e:
            self.log_to_output(self.script_output, f"❌ 检查文件修改失败: {str(e)}")

    def start_json_file_check_timer(self):
        """启动JSON文件修改检查定时器"""
        if hasattr(self, 'json_file_check_timer_id') and self.json_file_check_timer_id is not None:
            self.root.after_cancel(self.json_file_check_timer_id)
        
        # 每3秒检查一次文件修改（仅在脚本标签页激活时）
        self.json_file_check_timer_id = self.root.after(3000, self.periodic_json_file_check)

    def periodic_json_file_check(self):
        """定期检查JSON文件是否被修改"""
        try:
            # 只在脚本标签页激活时检查
            current_tab = self.notebook.select()
            tab_text = self.notebook.tab(current_tab, "text")
            
            if tab_text == "生成脚本":
                self.check_and_reload_modified_json_files()
        except:
            pass  # 静默处理错误，避免干扰用户
        
        # 继续下一次检查
        self.start_json_file_check_timer()


    def stop_json_file_check_timer(self):
        """停止JSON文件修改检查定时器"""
        if hasattr(self, 'json_file_check_timer_id') and self.json_file_check_timer_id is not None:
            self.root.after_cancel(self.json_file_check_timer_id)
            self.json_file_check_timer_id = None


    # name_values will be [{"name":"n1", "value":"v1"}, {"name":"n2", "value":"v2"}]
    def update_config_json(self, name_values):
        try:
            updated_config = self.current_project_config.copy()
            for nv in name_values:
                updated_config[nv["name"]] = nv["value"]  # Fixed typo: was "vlaue"
            self.current_project_config = updated_config
            
            config_manager = ProjectConfigManager(self.get_pid())
            config_manager.save_project_config(updated_config)
            return True
        except Exception as e:
            self.log_to_output(self.script_output, f"❌ 保存题目内容到配置失败: {str(e)}")
            return False

 
    def run(self):
        """Start the application"""
        self.root.mainloop()


if __name__ == "__main__":
    app = MagicToolGUI()
    app.run() 