import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import uuid
import os
import json
from datetime import datetime
from magic_workflow import MagicWorkflow
import config
import config_prompt
from pathlib import Path
from project_manager import ProjectConfigManager, create_project_dialog
import project_manager
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.ffmpeg_processor import FfmpegProcessor
from PIL import Image, ImageTk
from utility.llm_api import LLMApi
import shutil

# Try to import TkinterDnD for drag and drop support
try:
    import tkinterdnd2 as TkinterDnD
    from tkinterdnd2 import DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False





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
        self.dialog.geometry("1600x1000")
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
            generated_titles = PROJECT_CONFIG.get('generated_titles', [])
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
            generated_tags = PROJECT_CONFIG.get('generated_tags', [])
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
            PROJECT_CONFIG['video_title'] = final_title
            PROJECT_CONFIG['video_tags'] = final_tags
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
        if DND_AVAILABLE:
            self.root = root or TkinterDnD.Tk()
        else:
            self.root = root or tk.Tk()
        self.root.title("Youtube Tools - 工具集")
        self.root.geometry("2000x1000")  # Increased width for side-by-side layout
        
        # Initialize variables
        self.tasks = {}
        self.workflow = None
        self.current_language = "zh"  # Default language
        self.current_project_config = None
        
        # Show project selection dialog first
        if not self.show_project_selection():
            # User canceled, exit application
            self.root.destroy()
            return
        
        self.setup_ui()
        
        self.llm_api = LLMApi()

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
                    config_manager.save_project_config()
                    print(f"✅ 新项目配置已保存: {pid}")
                except Exception as e:
                    print(f"❌ 保存新项目配置失败: {e}")
            
            # 立即创建workflow
            self.create_workflow()
            return True
        elif result == 'open':
            # 打开现有项目
            ProjectConfigManager.set_global_config(selected_config)
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
            if pid and language and channel:
                # Get video dimensions from project config
                video_width = None
                video_height = None
                if self.current_project_config:
                    video_width = self.current_project_config.get('video_width')
                    video_height = self.current_project_config.get('video_height')
                self.workflow = MagicWorkflow(pid, language, channel, video_width, video_height)
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
            # video_width and video_height are read-only from project config, not saved
            # Keep existing values from project config
            if 'video_width' not in config_data:
                config_data['video_width'] = self.current_project_config.get('video_width', '1920') if self.current_project_config else '1920'
            if 'video_height' not in config_data:
                config_data['video_height'] = self.current_project_config.get('video_height', '1080') if self.current_project_config else '1080'
            
            # 保存音乐视频配置
            if hasattr(self, 'mv_name') and hasattr(self, 'mv_json_content'):
                config_data['mv_name'] = self.mv_name.get() or config_data.get('mv_name', '')
                config_data['mv_json_content'] = self.mv_json_content.get(1.0, tk.END).strip() or config_data.get('mv_json_content', '')
            
            # 保存Veo提示词配置
            if hasattr(self, 'veo_scene_number') and hasattr(self, 'veo_ending_words') and hasattr(self, 'veo_json_content') and hasattr(self, 'host_choice'):
                config_data['veo_scene_number'] = self.veo_scene_number.get() or config_data.get('veo_scene_number', '6')
                config_data['veo_ending_words'] = self.veo_ending_words.get() or config_data.get('veo_ending_words', 'None')
                config_data['host_choice'] = self.host_choice.get() or config_data.get('host_choice', 'No host')
                config_data['veo_json_content'] = self.veo_json_content.get(1.0, tk.END).strip() or config_data.get('veo_json_content', '')
            
            # 保存SUNO音乐提示词配置
            config_data['suno_language'] = self.suno_language.get() or config_data.get('suno_language', config_prompt.SUNO_LANGUAGE[0])
            config_data['suno_expression'] = self.suno_expression.get() or config_data.get('suno_expression', list(config_prompt.SUNO_CONTENT.keys())[0])
            config_data['music_atmosphere'] = self.suno_atmosphere.get() or config_data.get('music_atmosphere', config_prompt.SUNO_ATMOSPHERE[0])
            config_data['music_structure_category'] = self.suno_structure_category.get() or config_data.get('music_structure_category', self.suno_structure_categories[0] if hasattr(self, 'suno_structure_categories') else '')
            config_data['music_structure_comparison'] = self.suno_structure.get() or config_data.get('music_structure_comparison', '')
            config_data['music_melody_category'] = self.suno_melody_category.get() or config_data.get('music_melody_category', self.suno_melody_categories[0] if hasattr(self, 'suno_melody_categories') else '')
            config_data['music_leading_melody'] = self.suno_leading_melody.get() or config_data.get('music_leading_melody', '')
            config_data['music_instruments_category'] = self.suno_instruments_category.get() or config_data.get('music_instruments_category', self.suno_instruments_categories[0] if hasattr(self, 'suno_instruments_categories') else '')
            config_data['music_leading_instruments'] = self.suno_instruments.get() or config_data.get('music_leading_instruments', '')
            config_data['music_rhythm_groove_category'] = self.suno_rhythm_category.get() or config_data.get('music_rhythm_groove_category', self.suno_rhythm_categories[0] if hasattr(self, 'music_rhythm_groove_categories') else '')
            config_data['music_rhythm_groove_style'] = self.suno_rhythm.get() or config_data.get('music_rhythm_groove_style', '')
            
            config_data['music_json_content'] = self.music_content.get(1.0, tk.END).strip() or config_data.get('music_json_content', '')
            config_data['music_prompt_content'] = self.music_prompt.get(1.0, tk.END).strip() or config_data.get('music_prompt_content', '') if hasattr(self, 'music_prompt') else config_data.get('music_prompt_content', '')
            config_data['music_lyricsp_content'] = self.music_lyrics.get(1.0, tk.END).strip() or config_data.get('music_lyrics_content', '') if hasattr(self, 'music_lyrics') else config_data.get('music_lyrics_content', '')
            
            # 保存NotebookLM配置
            if hasattr(self, 'notebooklm_style') and hasattr(self, 'notebooklm_topic') and hasattr(self, 'notebooklm_prompt_content'):
                config_data['notebooklm_style'] = self.notebooklm_style.get() or config_data.get('notebooklm_style', '1 male & 1 female hosts')
                config_data['notebooklm_topic'] = self.notebooklm_topic.get() or config_data.get('notebooklm_topic', '')
                config_data['notebooklm_avoid'] = self.notebooklm_avoid.get() or config_data.get('notebooklm_avoid', '')
                config_data['notebooklm_location'] = self.notebooklm_location.get() or config_data.get('notebooklm_location', '')
                config_data['notebooklm_introduction_type'] = self.notebooklm_introduction_type.get() or config_data.get('notebooklm_introduction_type', 'listened radio-play-style introducation-story')
                config_data['notebooklm_prompt_content'] = self.notebooklm_prompt_content.get(1.0, tk.END).strip() or config_data.get('notebooklm_prompt_content', '')
                config_data['notebooklm_previous_file'] = getattr(self, 'notebooklm_previous_file', None)
                config_data['notebooklm_introduction_file'] = getattr(self, 'notebooklm_introduction_file', None)
            
            # Preserve generated titles, tags, and video_id if they exist
            if 'generated_titles' in self.current_project_config:
                config_data['generated_titles'] = self.current_project_config['generated_titles']
            if 'generated_tags' in self.current_project_config:
                config_data['generated_tags'] = self.current_project_config['generated_tags']
            if 'video_id' in self.current_project_config:
                config_data['video_id'] = self.current_project_config['video_id']
            
            # 保存到文件
            pid = config_data['pid']
            if pid:
                config_manager = ProjectConfigManager(pid)
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
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create tabs
        self.create_transcript_tab()
        self.create_download_tab()
        self.create_music_video_tab()  # Add new music video tab
        self.create_split_tab() # Add new split tab
        self.create_music_prompts_tab()  # Add new music prompts tab
        self.create_notebooklm_tab()  # Add new NotebookLM tab
        
        # Status bar
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        
        # 确保在UI创建完成后加载生成的标题和标签以及所有配置
        self.root.after(200, self.load_generated_titles_and_tags_to_combobox)
        self.root.after(300, self.load_initial_config_values)
    
    def load_initial_config_values(self):
        """Load initial config values for all tabs after UI creation"""
        try:
            print(f"🔄 Loading initial config values for all tabs...")
            
            # 加载音乐视频配置
            if hasattr(self, 'mv_name') and hasattr(self, 'mv_json_content'):
                self.mv_name.delete(0, tk.END)
                self.mv_name.insert(0, self.current_project_config.get('mv_name', ''))
                
                self.mv_json_content.delete(1.0, tk.END)
                self.mv_json_content.insert(1.0, self.current_project_config.get('mv_json_content', ''))
            
            # 加载Veo提示词配置
            if hasattr(self, 'veo_scene_number') and hasattr(self, 'veo_ending_words') and hasattr(self, 'veo_json_content') and hasattr(self, 'host_choice'):
                
                self.veo_scene_number.delete(0, tk.END)
                self.veo_scene_number.insert(0, self.current_project_config.get('veo_scene_number', '6'))
                
                self.veo_ending_words.delete(0, tk.END)
                self.veo_ending_words.insert(0, self.current_project_config.get('veo_ending_words', 'None'))
                
                self.host_choice.set(self.current_project_config.get('host_choice', 'No host'))
                
                self.veo_json_content.delete(1.0, tk.END)
                self.veo_json_content.insert(1.0, self.current_project_config.get('veo_json_content', ''))
            
            # 加载SUNO音乐提示词配置
            self.suno_language.set(self.current_project_config.get('suno_language', config_prompt.SUNO_LANGUAGE[0]))
            self.suno_expression.set(self.current_project_config.get('suno_expression', list(config_prompt.SUNO_CONTENT.keys())[0]))
            # Load new music parameters
            self.suno_atmosphere.set(self.current_project_config.get('music_atmosphere', config_prompt.SUNO_ATMOSPHERE[0]))
            
            # Load structure category and specific structure
            structure_category = self.current_project_config.get('music_structure_category', self.suno_structure_categories[0] if hasattr(self, 'suno_structure_categories') else '')
            self.suno_structure_category.set(structure_category)
            # Update the structure combobox based on the loaded category
            self.on_structure_category_change()
            # Now set the specific structure if it was saved
            if hasattr(self, 'suno_structure'):
                structure = self.current_project_config.get('music_structure_comparison', '')
                if structure and structure in self.suno_structure['values']:
                    self.suno_structure.set(structure)
            
            # Load melody category and specific melody
            melody_category = self.current_project_config.get('music_melody_category', self.suno_melody_categories[0] if hasattr(self, 'suno_melody_categories') else '')
            self.suno_melody_category.set(melody_category)
            # Update the melody combobox based on the loaded category
            self.on_melody_category_change()
            # Now set the specific melody if it was saved
            if hasattr(self, 'suno_leading_melody'):
                melody = self.current_project_config.get('music_leading_melody', '')
                if melody and melody in self.suno_leading_melody['values']:
                    self.suno_leading_melody.set(melody)
            
            # Load instruments category and specific instrument
            instruments_category = self.current_project_config.get('music_instruments_category', self.suno_instruments_categories[0] if hasattr(self, 'suno_instruments_categories') else '')
            self.suno_instruments_category.set(instruments_category)
            # Update the instruments combobox based on the loaded category
            self.on_instruments_category_change()
            # Now set the specific instrument if it was saved
            if hasattr(self, 'suno_instruments'):
                instrument = self.current_project_config.get('music_leading_instruments', '')
                if instrument and instrument in self.suno_instruments['values']:
                    self.suno_instruments.set(instrument)
            
            category = self.current_project_config.get('music_rhythm_groove_category', self.suno_rhythm_categories[0] if hasattr(self, 'music_rhythm_groove_categories') else '')
            self.suno_rhythm_category.set(category)
            # Update the style combobox based on the loaded category
            self.on_rhythm_category_change()
            # Now set the style if it was saved
            if hasattr(self, 'music_rhythm_groove_style'):
                style = self.current_project_config.get('music_rhythm_groove_style', '')
                if style and style in self.suno_rhythm['values']:
                    self.suno_rhythm.set(style)
            
            self.music_content.delete(1.0, tk.END)
            self.music_content.insert(1.0, self.current_project_config.get('music_json_content', ''))
            
            if hasattr(self, 'music_prompt'):
                self.music_prompt.delete(1.0, tk.END)
                self.music_prompt.insert(1.0, self.current_project_config.get('music_prompt_content', ''))

            if hasattr(self, 'music_lyrics'):
                self.music_lyrics.delete(1.0, tk.END)
                self.music_lyrics.insert(1.0, self.current_project_config.get('music_lyrics_content', ''))

            # 加载NotebookLM配置
            if hasattr(self, 'notebooklm_style') and hasattr(self, 'notebooklm_topic') and hasattr(self, 'notebooklm_prompt_content'):
                
                self.notebooklm_style.set(self.current_project_config.get('notebooklm_style', '1 male & 1 female hosts'))
                
                self.notebooklm_topic.delete(0, tk.END)
                self.notebooklm_topic.insert(0, self.current_project_config.get('notebooklm_topic', ''))
                
                self.notebooklm_avoid.delete(0, tk.END)
                self.notebooklm_avoid.insert(0, self.current_project_config.get('notebooklm_avoid', ''))
                
                self.notebooklm_location.delete(0, tk.END)
                self.notebooklm_location.insert(0, self.current_project_config.get('notebooklm_location', ''))
                
                self.notebooklm_introduction_type.set(self.current_project_config.get('notebooklm_introduction_type', 'listened radio-play-style introducation-story'))
                
                self.notebooklm_prompt_content.delete(1.0, tk.END)
                self.notebooklm_prompt_content.insert(1.0, self.current_project_config.get('notebooklm_prompt_content', ''))
                
                # 恢复文件选择状态
                self.notebooklm_previous_file = self.current_project_config.get('notebooklm_previous_file', None)
                self.notebooklm_introduction_file = self.current_project_config.get('notebooklm_introduction_file', None)
                
                # 更新画布显示
                if self.notebooklm_previous_file and os.path.exists(self.notebooklm_previous_file):
                    self.process_notebooklm_file(self.notebooklm_previous_file, 'previous')
                else:
                    self.clear_notebooklm_previous()
                    
                if self.notebooklm_introduction_file and os.path.exists(self.notebooklm_introduction_file):
                    self.process_notebooklm_file(self.notebooklm_introduction_file, 'introduction')
                else:
                    self.clear_notebooklm_introduction()
            
            print(f"✅ Initial config values loaded successfully for all tabs")
                
        except Exception as e:
            print(f"❌ Failed to load initial config values: {str(e)}")
            import traceback
            traceback.print_exc()
            # If error occurs, retry after a delay
            self.root.after(100, self.load_initial_config_values)
    
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

        ttk.Separator(row1, orient='vertical').pack(padx=5)

        # 项目标题 (使用Combobox)
        ttk.Label(row1, text="项目标题:").pack(side=tk.LEFT)
        self.video_title = ttk.Combobox(row1, width=70)
        self.video_title.pack(side=tk.LEFT, padx=(5, 15))
        self.video_title.bind('<FocusOut>', self.on_project_config_change)
        self.video_title.bind('<<ComboboxSelected>>', self.on_project_config_change)
        self.video_title.set(self.current_project_config.get('video_title', ''))

        ttk.Separator(row1, orient='vertical').pack(padx=5)

        # 项目标签 (使用Combobox)
        ttk.Label(row1, text="项目标签:").pack(side=tk.LEFT)
        self.video_tags = ttk.Combobox(row1, width=35)
        self.video_tags.pack(side=tk.LEFT, padx=(5, 15))
        self.video_tags.bind('<FocusOut>', self.on_project_config_change)
        self.video_tags.bind('<<ComboboxSelected>>', self.on_project_config_change)
        self.video_tags.set(self.current_project_config.get('video_tags', ''))
        
        ttk.Separator(row1, orient='vertical').pack(padx=5)

        ttk.Button(row1, text="选择项目", command=self.change_project).pack(side=tk.RIGHT, padx=5)
        ttk.Button(row1, text="保存配置", command=self.save_project_config).pack(side=tk.RIGHT, padx=5)
    
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
            
            # 更新音乐视频配置
            if hasattr(self, 'mv_name') and hasattr(self, 'mv_json_content'):
                self.mv_name.delete(0, tk.END)
                self.mv_name.insert(0, self.current_project_config.get('mv_name', ''))
                
                self.mv_json_content.delete(1.0, tk.END)
                self.mv_json_content.insert(1.0, self.current_project_config.get('mv_json_content', ''))
            
            # 更新Veo提示词配置
            if hasattr(self, 'veo_scene_number') and hasattr(self, 'veo_ending_words') and hasattr(self, 'veo_json_content') and hasattr(self, 'host_choice'):
                
                self.veo_scene_number.delete(0, tk.END)
                self.veo_scene_number.insert(0, self.current_project_config.get('veo_scene_number', '6'))
                
                self.veo_ending_words.delete(0, tk.END)
                self.veo_ending_words.insert(0, self.current_project_config.get('veo_ending_words', 'None'))
                
                self.host_choice.set(self.current_project_config.get('host_choice', 'No host'))
                
                self.veo_json_content.delete(1.0, tk.END)
                self.veo_json_content.insert(1.0, self.current_project_config.get('veo_json_content', ''))
            
            # 更新SUNO音乐提示词配置
            self.suno_language.set(self.current_project_config.get('suno_language', config_prompt.SUNO_LANGUAGE[0]))
            self.suno_expression.set(self.current_project_config.get('suno_expression', list(config_prompt.SUNO_CONTENT.keys())[0]))
            self.suno_atmosphere.set(self.current_project_config.get('music_atmosphere', config_prompt.SUNO_ATMOSPHERE[0]))
            
            # Update structure category and specific structure
            structure_category = self.current_project_config.get('music_structure_category', self.suno_structure_categories[0] if hasattr(self, 'suno_structure_categories') else '')
            self.suno_structure_category.set(structure_category)
            self.on_structure_category_change()
            if hasattr(self, 'suno_structure'):
                structure = self.current_project_config.get('music_structure_comparison', '')
                if structure and structure in self.suno_structure['values']:
                    self.suno_structure.set(structure)
            
            # Update melody category and specific melody
            melody_category = self.current_project_config.get('music_melody_category', self.suno_melody_categories[0] if hasattr(self, 'suno_melody_categories') else '')
            self.suno_melody_category.set(melody_category)
            self.on_melody_category_change()
            if hasattr(self, 'suno_leading_melody'):
                melody = self.current_project_config.get('music_leading_melody', '')
                if melody and melody in self.suno_leading_melody['values']:
                    self.suno_leading_melody.set(melody)
            
            # Update instruments category and specific instrument
            instruments_category = self.current_project_config.get('music_instruments_category', self.suno_instruments_categories[0] if hasattr(self, 'suno_instruments_categories') else '')
            self.suno_instruments_category.set(instruments_category)
            self.on_instruments_category_change()
            if hasattr(self, 'suno_instruments'):
                instrument = self.current_project_config.get('music_leading_instruments', '')
                if instrument and instrument in self.suno_instruments['values']:
                    self.suno_instruments.set(instrument)
            
            # Update rhythm category and specific rhythm
            rhythm_category = self.current_project_config.get('music_rhythm_groove_category', self.suno_rhythm_categories[0] if hasattr(self, 'suno_rhythm_categories') else '')
            self.suno_rhythm_category.set(rhythm_category)
            self.on_rhythm_category_change()
            if hasattr(self, 'suno_rhythm'):
                rhythm = self.current_project_config.get('music_rhythm_groove_style', '')
                if rhythm and rhythm in self.suno_rhythm['values']:
                    self.suno_rhythm.set(rhythm)

            self.music_content.delete(1.0, tk.END)
            self.music_content.insert(1.0, self.current_project_config.get('music_json_content', ''))
            
            self.music_lyrics.delete(1.0, tk.END)
            self.music_lyrics.insert(1.0, self.current_project_config.get('music_lyrics_content', ''))
            
            self.music_prompt.delete(1.0, tk.END)
            self.music_prompt.insert(1.0, self.current_project_config.get('music_prompt_content', ''))
            
            # 更新NotebookLM配置
            if hasattr(self, 'notebooklm_style') and hasattr(self, 'notebooklm_topic') and hasattr(self, 'notebooklm_prompt_content'):
                
                self.notebooklm_style.set(self.current_project_config.get('notebooklm_style', '1 male & 1 female hosts'))
                
                self.notebooklm_topic.delete(0, tk.END)
                self.notebooklm_topic.insert(0, self.current_project_config.get('notebooklm_topic', ''))
                
                self.notebooklm_avoid.delete(0, tk.END)
                self.notebooklm_avoid.insert(0, self.current_project_config.get('notebooklm_avoid', ''))
                
                self.notebooklm_location.delete(0, tk.END)
                self.notebooklm_location.insert(0, self.current_project_config.get('notebooklm_location', ''))
                
                self.notebooklm_prompt_content.delete(1.0, tk.END)
                self.notebooklm_prompt_content.insert(1.0, self.current_project_config.get('notebooklm_prompt_content', ''))
                
                # 恢复文件选择状态
                self.notebooklm_previous_file = self.current_project_config.get('notebooklm_previous_file', None)
                self.notebooklm_introduction_file = self.current_project_config.get('notebooklm_introduction_file', None)
                
                # 更新画布显示
                if self.notebooklm_previous_file and os.path.exists(self.notebooklm_previous_file):
                    self.process_notebooklm_file(self.notebooklm_previous_file, 'previous')
                else:
                    self.clear_notebooklm_previous()
                    
                if self.notebooklm_introduction_file and os.path.exists(self.notebooklm_introduction_file):
                    self.process_notebooklm_file(self.notebooklm_introduction_file, 'introduction')
                else:
                    self.clear_notebooklm_introduction()
            
            # 更新语言显示
            self.project_language.config(text=self.current_language)
            
            # 重新加载生成的标题和标签
            self.load_generated_titles_and_tags_to_combobox()
            

            
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
    
    def on_project_config_change(self, event=None):
        """项目配置改变时的处理"""
        # 自动保存配置
        self.root.after(100, self.save_project_config)  # 延迟保存避免频繁写入
        
        
    def create_transcript_tab(self):
        """Create YouTube transcription tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="YouTube转录")
        
        # YouTube transcription section
        youtube_frame = ttk.LabelFrame(tab, text="YouTube视频转录", padding="10")
        youtube_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # URL input
        url_frame = ttk.Frame(youtube_frame)
        url_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(url_frame, text="YouTube链接:").pack(side=tk.LEFT)
        self.transcript_url = ttk.Entry(url_frame, width=60)
        self.transcript_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Source language selection
        lang_frame1 = ttk.Frame(youtube_frame)
        lang_frame1.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(lang_frame1, text="源语言:").pack(side=tk.LEFT)
        self.source_language = ttk.Combobox(lang_frame1, values=[
            "zh", "en", "ja", "ko", "es", "fr", "de", "ru", "ar", "hi", "pt"
        ], state="readonly", width=10)
        self.source_language.set("zh")
        self.source_language.pack(side=tk.LEFT, padx=5)
        
        # Target language selection
        lang_frame2 = ttk.Frame(youtube_frame)
        lang_frame2.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(lang_frame2, text="目标语言:").pack(side=tk.LEFT)
        self.target_language = ttk.Combobox(lang_frame2, values=[
            "tw", "en", "zh", "ja", "ko", "es", "fr", "de", "ru", "ar", "hi", "pt"
        ], state="readonly", width=10)
        self.target_language.set("tw")
        self.target_language.pack(side=tk.LEFT, padx=5)
        
        # Transcribe button
        button_frame = ttk.Frame(youtube_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        ttk.Button(button_frame, text="开始转录", 
                  command=self.run_transcript_youtube).pack(side=tk.LEFT, padx=25)
        
        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.transcript_output = scrolledtext.ScrolledText(output_frame, height=15)
        self.transcript_output.pack(fill=tk.BOTH, expand=True)
        
    
    def create_download_tab(self):
        """Create YouTube download tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="YouTube下载")
        
        # YouTube Playlist Download Section
        playlist_frame = ttk.LabelFrame(tab, text="YouTube播放列表下载", padding="10")
        playlist_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Playlist URL input
        playlist_url_frame = ttk.Frame(playlist_frame)
        playlist_url_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(playlist_url_frame, text="播放列表链接:").pack(side=tk.LEFT)
        self.playlist_url = ttk.Entry(playlist_url_frame, width=60)
        self.playlist_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Playlist controls
        playlist_controls_frame = ttk.Frame(playlist_frame)
        playlist_controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Max videos limit
        ttk.Label(playlist_controls_frame, text="最大视频数:").pack(side=tk.LEFT)
        self.max_videos_var = tk.StringVar(value="10")
        max_videos_entry = ttk.Entry(playlist_controls_frame, textvariable=self.max_videos_var, width=8)
        max_videos_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(playlist_controls_frame, text="(留空下载全部)").pack(side=tk.LEFT, padx=5)
        
        # Buttons
        playlist_button_frame = ttk.Frame(playlist_frame)
        playlist_button_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(playlist_button_frame, text="获取播放列表信息", 
                  command=self.get_playlist_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(playlist_button_frame, text="下载播放列表", 
                  command=self.download_playlist).pack(side=tk.LEFT, padx=5)
        ttk.Button(playlist_button_frame, text="下载单个视频", 
                  command=self.download_single_video).pack(side=tk.LEFT, padx=5)
        
        # Playlist info display
        playlist_info_frame = ttk.LabelFrame(playlist_frame, text="播放列表信息", padding="5")
        playlist_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.playlist_info_text = scrolledtext.ScrolledText(playlist_info_frame, height=8, wrap=tk.WORD)
        self.playlist_info_text.pack(fill=tk.BOTH, expand=True)
        
        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.download_output = scrolledtext.ScrolledText(output_frame, height=15)
        self.download_output.pack(fill=tk.BOTH, expand=True)
    
    def create_music_video_tab(self):
        """Create music video tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="音乐视频制作")
        
        # Music Video Configuration Section
        mv_frame = ttk.LabelFrame(tab, text="音乐视频配置", padding="10")
        mv_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # MV Name input
        mv_name_frame = ttk.Frame(mv_frame)
        mv_name_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(mv_name_frame, text="MV名称:").pack(side=tk.LEFT)
        self.mv_name = ttk.Entry(mv_name_frame, width=60)
        self.mv_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.mv_name.bind('<FocusOut>', self.on_project_config_change)
        
        # JSON Content area
        json_frame = ttk.LabelFrame(mv_frame, text="关键词JSON配置", padding="5")
        json_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # JSON explanation
        json_info = ttk.Label(json_frame, text="请输入关键词列表的JSON格式数据，例如: [\"关键词1\", \"关键词2\", \"关键词3\"]", 
                             foreground="gray", font=('TkDefaultFont', 9))
        json_info.pack(anchor=tk.W, pady=(0, 5))
        
        self.mv_json_content = scrolledtext.ScrolledText(json_frame, height=8, wrap=tk.WORD)
        self.mv_json_content.pack(fill=tk.BOTH, expand=True)
        self.mv_json_content.bind('<FocusOut>', self.on_project_config_change)
        
        # Build button
        button_frame = ttk.Frame(mv_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        ttk.Button(button_frame, text="制作音乐视频", 
                  command=self.build_music_video).pack(side=tk.LEFT, padx=25)
        
        # Build full music video button with checkbox
        full_mv_frame = ttk.Frame(button_frame)
        full_mv_frame.pack(side=tk.LEFT, padx=5)
        
        # Checkbox for full MV parameter
        self.full_mv_checkbox_var = tk.BooleanVar(value=True)  # Default to True
        self.full_mv_checkbox = ttk.Checkbutton(full_mv_frame, text="启用完整流程", 
                                               variable=self.full_mv_checkbox_var)
        self.full_mv_checkbox.pack(side=tk.TOP, pady=(0, 2))
        
        ttk.Button(full_mv_frame, text="制作完整MV", 
                  command=self.build_full_music_video).pack(side=tk.TOP)
        
        # Clear button
        ttk.Button(button_frame, text="清空配置", 
                  command=self.clear_mv_config).pack(side=tk.LEFT, padx=5)
        
        # Validate JSON button
        ttk.Button(button_frame, text="验证JSON", 
                  command=self.validate_json).pack(side=tk.LEFT, padx=5)
        
        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.mv_output = scrolledtext.ScrolledText(output_frame, height=15)
        self.mv_output.pack(fill=tk.BOTH, expand=True)
    
    def clear_mv_config(self):
        """Clear music video configuration"""
        self.mv_name.delete(0, tk.END)
        self.mv_json_content.delete(1.0, tk.END)
        self.on_project_config_change()
    
    def validate_json(self):
        """Validate JSON content"""
        try:
            json_content = self.mv_json_content.get(1.0, tk.END).strip()
            if not json_content:
                messagebox.showwarning("警告", "JSON内容为空")
                return
            
            kernel_list = json.loads(json_content)
            if not isinstance(kernel_list, list):
                messagebox.showerror("错误", "JSON内容必须是一个列表")
                return
            
            if not all(isinstance(item, str) for item in kernel_list):
                messagebox.showerror("错误", "JSON列表中的所有项目必须是字符串")
                return
            
            messagebox.showinfo("成功", f"JSON验证通过！\n包含 {len(kernel_list)} 个关键词:\n" + 
                               "\n".join(f"- {keyword}" for keyword in kernel_list[:10]) + 
                               (f"\n... 还有 {len(kernel_list) - 10} 个" if len(kernel_list) > 10 else ""))
            
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON错误", f"JSON格式错误: {str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"验证失败: {str(e)}")
    
    def build_music_video(self):
        """Build music video"""
        mv_name = self.mv_name.get().strip()
        json_content = self.mv_json_content.get(1.0, tk.END).strip()
        
        if not mv_name:
            messagebox.showerror("错误", "请输入MV名称")
            return
        
        if not json_content:
            messagebox.showerror("错误", "请输入关键词JSON内容")
            return
        
        # Validate JSON
        try:
            json_content = json.loads(json_content)
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON错误", f"JSON格式错误: {str(e)}")
            return
        
        # Confirm build
        if not messagebox.askyesno("确认制作", f"确定要制作音乐视频吗？\n\nMV名称: {mv_name}"):
            return
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "build_music_video",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                self.status_var.set("制作音乐视频中...")
                self.log_to_output(self.mv_output, f"🎵 开始制作音乐视频...")
                self.log_to_output(self.mv_output, f"MV名称: {mv_name}")
                # Build music video using workflow
                result = self.workflow.build_channel_music_video(mv_name, json_content)
                
                self.log_to_output(self.mv_output, f"✅ 音乐视频制作完成！")
                self.log_to_output(self.mv_output, f"结果: {result}")
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
                # Show success message in main thread
                self.root.after(0, lambda: messagebox.showinfo("成功", f"音乐视频制作完成！\n\nMV名称: {mv_name}\n结果: {result}"))
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.mv_output, f"❌ 音乐视频制作失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                # Show error message in main thread
                self.root.after(0, lambda: messagebox.showerror("错误", f"音乐视频制作失败: {error_msg}"))
        
        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
    
    def build_full_music_video(self):
        """Build full music video using magic_workflow.build_full_music_video"""
        mv_name = self.mv_name.get().strip()
        json_content = self.mv_json_content.get(1.0, tk.END).strip()
        
        if not mv_name:
            messagebox.showerror("错误", "请输入MV名称")
            return
        
        if not json_content:
            messagebox.showerror("错误", "请输入关键词JSON内容")
            return
        
        # Validate JSON
        try:
            kernel_list = json.loads(json_content)
            if not isinstance(kernel_list, list):
                messagebox.showerror("错误", "JSON内容必须是一个列表")
                return
                 
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON错误", f"JSON格式错误: {str(e)}")
            return
        
        # Get checkbox state
        full_process_enabled = self.full_mv_checkbox_var.get()
        
        # Confirm build
        confirm_msg = f"确定要制作完整音乐视频吗？\n\nMV名称: {mv_name}\n关键词数量: {len(kernel_list)}\n启用完整流程: {'是' if full_process_enabled else '否'}\n\n注意：这将调用完整的MV制作流程"
        if not messagebox.askyesno("确认制作", confirm_msg):
            return
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "build_full_music_video",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                self.status_var.set("制作完整音乐视频中...")
                self.log_to_output(self.mv_output, f"🎵 开始制作完整音乐视频...")
                self.log_to_output(self.mv_output, f"MV名称: {mv_name}")
                self.log_to_output(self.mv_output, f"关键词数量: {len(kernel_list)}")
                self.log_to_output(self.mv_output, f"启用完整流程: {'是' if full_process_enabled else '否'}")
                
                # Build full music video using workflow
                result = self.workflow.build_full_music_video(mv_name, kernel_list, full_process_enabled)
                
                self.log_to_output(self.mv_output, f"✅ 完整音乐视频制作完成！")
                self.log_to_output(self.mv_output, f"结果: {result}")
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
                # Show success message in main thread
                self.root.after(0, lambda: messagebox.showinfo("成功", f"完整音乐视频制作完成！\n\nMV名称: {mv_name}\n结果: {result}"))
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.mv_output, f"❌ 完整音乐视频制作失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                # Show error message in main thread
                self.root.after(0, lambda: messagebox.showerror("错误", f"完整音乐视频制作失败: {error_msg}"))
        
        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
    
    def get_pid(self):
        """Get current project ID"""
        return self.current_project_config.get('pid', '') if self.current_project_config else ''
    
    def get_language(self):
        """Get current language"""
        return self.current_language
    
    def get_channel(self):
        """Get current channel"""
        return self.current_project_config.get('channel', '') if self.current_project_config else ''
    
    def on_language_change(self, event=None):
        """Handle language change"""
        # This method is kept for compatibility but language changes are handled through project selection
        pass

            
    def log_to_output(self, output_widget, message):
        """Add message to output text area"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        output_widget.see(tk.END)
        

    def run_transcript_youtube(self):
        """Run YouTube transcription"""
        url = self.transcript_url.get().strip()
        if url.find("&ab_channel=") != -1:
            url = url.split("&ab_channel=")[0]
        if url.find("&list=") != -1:
            url = url.split("&list=")[0]
        source_lang = self.source_language.get()
        target_lang = self.target_language.get() if self.target_language.get() != "" else source_lang
        
        if not url:
            messagebox.showerror("错误", "请输入YouTube链接")
            return
            
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "transcript_youtube",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                self.status_var.set("转录中...")
                self.log_to_output(self.transcript_output, f"开始转录YouTube视频...")
                self.log_to_output(self.transcript_output, f"URL: {url}")
                self.log_to_output(self.transcript_output, f"源语言: {source_lang}")
                self.log_to_output(self.transcript_output, f"目标语言: {target_lang}")

                # Run transcription
                result = self.workflow.transcript_youtube_video(url, source_lang, target_lang)
                
                self.log_to_output(self.transcript_output, f"✅ 转录完成！")
                self.log_to_output(self.transcript_output, f"输出保存到: {result}")
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
                # Show success message in main thread
                self.root.after(0, lambda: messagebox.showinfo("成功", f"转录完成！\n输出保存到: {result}"))
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.transcript_output, f"❌ 转录失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                # Show error message in main thread
                self.root.after(0, lambda: messagebox.showerror("错误", f"转录失败: {error_msg}"))
        
        # Run in separate thread to avoid blocking GUI
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()

    def get_playlist_info(self):
        """获取播放列表信息"""
        playlist_url = self.playlist_url.get().strip()
        
        if not playlist_url:
            messagebox.showerror("错误", "请输入播放列表链接")
            return
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "get_playlist_info",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                self.status_var.set("获取播放列表信息中...")
                self.log_to_output(self.download_output, f"🔍 正在获取播放列表信息...")
                self.log_to_output(self.download_output, f"URL: {playlist_url}")
                
                # Get playlist info
                playlist_info = self.workflow.downloader.get_playlist_info(playlist_url)
                
                if playlist_info:
                    # Display playlist info in the GUI
                    info_text = f"📋 播放列表: {playlist_info['title']}\n"
                    info_text += f"📝 描述: {playlist_info['description'][:200]}...\n" if len(playlist_info['description']) > 200 else f"📝 描述: {playlist_info['description']}\n"
                    info_text += f"🎬 视频数量: {playlist_info['video_count']}\n\n"
                    info_text += "📺 视频列表:\n"
                    
                    for i, video in enumerate(playlist_info['videos'][:20], 1):  # Show first 20 videos
                        duration_min = video['duration'] // 60 if video['duration'] else 0
                        duration_sec = video['duration'] % 60 if video['duration'] else 0
                        info_text += f"{i}. {video['title']}\n"
                        info_text += f"   时长: {duration_min}:{duration_sec:02d} | 上传者: {video['uploader']}\n\n"
                    
                    if len(playlist_info['videos']) > 20:
                        info_text += f"... 还有 {len(playlist_info['videos']) - 20} 个视频\n"
                    
                    # Update GUI in main thread
                    self.root.after(0, lambda: self.playlist_info_text.delete(1.0, tk.END))
                    self.root.after(0, lambda: self.playlist_info_text.insert(1.0, info_text))
                    
                    self.log_to_output(self.download_output, f"✅ 播放列表信息获取完成！")
                    self.log_to_output(self.download_output, f"播放列表: {playlist_info['title']}")
                    self.log_to_output(self.download_output, f"视频数量: {playlist_info['video_count']}")
                    
                else:
                    self.log_to_output(self.download_output, f"❌ 无法获取播放列表信息")
                    self.root.after(0, lambda: messagebox.showerror("错误", "无法获取播放列表信息"))
                
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.download_output, f"❌ 获取播放列表信息失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                self.root.after(0, lambda: messagebox.showerror("错误", f"获取播放列表信息失败: {error_msg}"))
        
        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()


    def download_playlist(self):
        """下载播放列表中的所有视频"""
        playlist_url = self.playlist_url.get().strip()
        max_videos_str = self.max_videos_var.get().strip()
        
        if not playlist_url:
            messagebox.showerror("错误", "请输入播放列表链接")
            return
        
        # Parse max videos limit
        max_videos = None
        if max_videos_str:
            try:
                max_videos = int(max_videos_str)
                if max_videos <= 0:
                    messagebox.showerror("错误", "最大视频数必须大于0")
                    return
            except ValueError:
                messagebox.showerror("错误", "最大视频数必须是数字")
                return
        
        # Confirm download
        confirm_msg = f"确定要下载播放列表吗？"
        if max_videos:
            confirm_msg += f"\n将下载前 {max_videos} 个视频"
        else:
            confirm_msg += "\n将下载所有视频"
        confirm_msg += "\n\n下载的视频将保存到项目的 download 文件夹中。"
        
        if not messagebox.askyesno("确认下载", confirm_msg):
            return
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "download_playlist",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                self.status_var.set("下载播放列表中...")
                self.log_to_output(self.download_output, f"📥 开始下载播放列表...")
                self.log_to_output(self.download_output, f"URL: {playlist_url}")
                if max_videos:
                    self.log_to_output(self.download_output, f"最大视频数: {max_videos}")
                
                # Download playlist
                downloaded_files = self.workflow.downloader.download_playlist_highest_resolution(playlist_url, max_videos)
                
                if downloaded_files:
                    self.log_to_output(self.download_output, f"✅ 播放列表下载完成！")
                    self.log_to_output(self.download_output, f"成功下载 {len(downloaded_files)} 个视频:")
                    
                    for file_info in downloaded_files:
                        duration_min = file_info['duration'] // 60 if file_info['duration'] else 0
                        duration_sec = file_info['duration'] % 60 if file_info['duration'] else 0
                        self.log_to_output(self.download_output, f"  📹 {file_info['title']}")
                        self.log_to_output(self.download_output, f"     时长: {duration_min}:{duration_sec:02d} | 文件: {os.path.basename(file_info['file_path'])}")
                    
                    self.root.after(0, lambda: messagebox.showinfo("下载完成", 
                        f"播放列表下载完成！\n成功下载 {len(downloaded_files)} 个视频\n\n文件保存在: {config.get_project_path(self.get_pid())}/download"))
                else:
                    self.log_to_output(self.download_output, f"❌ 播放列表下载失败或没有视频被下载")
                    self.root.after(0, lambda: messagebox.showerror("错误", "播放列表下载失败"))
                
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.download_output, f"❌ 播放列表下载失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                self.root.after(0, lambda: messagebox.showerror("错误", f"播放列表下载失败: {error_msg}"))
        
        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()

    def download_single_video(self):
        """下载单个视频"""
        video_url = self.playlist_url.get().strip()
        
        if not video_url:
            messagebox.showerror("错误", "请输入视频链接")
            return
        
        # Confirm download
        if not messagebox.askyesno("确认下载", "确定要下载这个视频吗？\n\n下载的视频将保存到项目的 download 文件夹中。"):
            return
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "download_single_video",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                self.status_var.set("下载视频中...")
                self.log_to_output(self.download_output, f"📥 开始下载视频...")
                self.log_to_output(self.download_output, f"URL: {video_url}")
                
                # Download video
                file_path = self.workflow.downloader.download_video_highest_resolution(video_url)
                
                if file_path and os.path.exists(file_path):
                    file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                    self.log_to_output(self.download_output, f"✅ 视频下载完成！")
                    self.log_to_output(self.download_output, f"文件: {os.path.basename(file_path)}")
                    self.log_to_output(self.download_output, f"大小: {file_size:.1f} MB")
                    self.log_to_output(self.download_output, f"路径: {file_path}")
                    
                    self.root.after(0, lambda: messagebox.showinfo("下载完成", 
                        f"视频下载完成！\n\n文件: {os.path.basename(file_path)}\n大小: {file_size:.1f} MB\n路径: {file_path}"))
                else:
                    self.log_to_output(self.download_output, f"❌ 视频下载失败")
                    self.root.after(0, lambda: messagebox.showerror("错误", "视频下载失败"))
                
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.download_output, f"❌ 视频下载失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                self.root.after(0, lambda: messagebox.showerror("错误", f"视频下载失败: {error_msg}"))
        
        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()

    def create_split_tab(self):
        """Create audio/video split tab with drag & drop"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="音频/视频分割")

        # Instructions
        instruction_frame = ttk.Frame(tab)
        instruction_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        instruction_text = "将MP3或MP4文件拖拽到下方图像区域以进行分割处理\n• MP3文件将进行音频分割\n• MP4文件将进行视频分割\n• 结果文件保存在源文件同一目录，文件名添加'__'后缀"
        ttk.Label(instruction_frame, text=instruction_text, font=('TkDefaultFont', 10), foreground='gray').pack()

        # Drop zone with wave image
        drop_frame = ttk.LabelFrame(tab, text="拖拽区域", padding="20")
        drop_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Canvas for the wave image and drop zone
        self.split_canvas = tk.Canvas(drop_frame, height=300, bg='white', relief=tk.RAISED, bd=2)
        self.split_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Load and display wave image
        self.load_wave_image()

        # Setup drag and drop if available
        self.setup_split_drag_drop()

        # Settings frame
        settings_frame = ttk.LabelFrame(tab, text="分割设置", padding="10")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)

        # Time input for splitting
        time_frame = ttk.Frame(settings_frame)
        time_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(time_frame, text="开始时间 (秒):").pack(side=tk.LEFT)
        self.split_start_time = ttk.Entry(time_frame, width=10)
        self.split_start_time.insert(0, "0")
        self.split_start_time.pack(side=tk.LEFT, padx=(5, 15))
        
        ttk.Label(time_frame, text="结束时间 (秒):").pack(side=tk.LEFT)
        self.split_end_time = ttk.Entry(time_frame, width=10)
        self.split_end_time.insert(0, "30")
        self.split_end_time.pack(side=tk.LEFT, padx=(5, 15))
        
        ttk.Label(time_frame, text="(留空结束时间表示到文件末尾)").pack(side=tk.LEFT, padx=5)

        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.split_output = scrolledtext.ScrolledText(output_frame, height=10)
        self.split_output.pack(fill=tk.BOTH, expand=True)

    def load_wave_image(self):
        """Load and display the wave image in the canvas"""
        try:
            image_path = os.path.join(os.path.dirname(__file__), "media", "wave_sound.png")
            if os.path.exists(image_path):
                # Load and resize image to fit canvas
                pil_image = Image.open(image_path)
                # Calculate size to fit canvas while maintaining aspect ratio
                canvas_width = 400
                canvas_height = 250
                pil_image.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)
                
                self.wave_image = ImageTk.PhotoImage(pil_image)
                
                # Center image in canvas
                canvas_width_actual = self.split_canvas.winfo_reqwidth() or 400
                canvas_height_actual = self.split_canvas.winfo_reqheight() or 300
                x = canvas_width_actual // 2
                y = canvas_height_actual // 2
                
                self.split_canvas.create_image(x, y, image=self.wave_image, anchor=tk.CENTER)
                self.split_canvas.create_text(x, y + 140, text="拖拽 MP3/MP4 文件到此处", 
                                            font=('TkDefaultFont', 12, 'bold'), fill='gray')
            else:
                # Fallback if image not found
                self.split_canvas.create_text(200, 150, text="拖拽 MP3/MP4 文件到此处", 
                                            font=('TkDefaultFont', 14, 'bold'), fill='gray')
                self.split_canvas.create_rectangle(50, 50, 350, 250, outline='gray', dash=(5, 5))
                
        except Exception as e:
            print(f"加载波形图片失败: {e}")
            # Fallback to text only
            self.split_canvas.create_text(200, 150, text="拖拽 MP3/MP4 文件到此处", 
                                        font=('TkDefaultFont', 14, 'bold'), fill='gray')
            self.split_canvas.create_rectangle(50, 50, 350, 250, outline='gray', dash=(5, 5))

    def setup_split_drag_drop(self):
        """Setup drag and drop functionality for the split canvas"""
        if DND_AVAILABLE:
            try:
                self.split_canvas.drop_target_register(DND_FILES)
                self.split_canvas.dnd_bind('<<Drop>>', self.on_split_drop)
                self.split_canvas.dnd_bind('<<DragEnter>>', self.on_split_drag_enter)
                self.split_canvas.dnd_bind('<<DragLeave>>', self.on_split_drag_leave)
            except Exception as e:
                print(f"设置拖拽功能失败: {e}")
                # Fallback to click
                self.split_canvas.bind('<Button-1>', self.on_split_click)
        else:
            # Fallback to click if drag & drop not available
            self.split_canvas.bind('<Button-1>', self.on_split_click)

    def on_split_drag_enter(self, event):
        """Visual feedback when dragging enters canvas"""
        self.split_canvas.configure(relief=tk.SUNKEN, bd=3)

    def on_split_drag_leave(self, event):
        """Visual feedback when dragging leaves canvas"""
        self.split_canvas.configure(relief=tk.RAISED, bd=2)

    def on_split_click(self, event):
        """Fallback file selection when drag & drop not available"""
        file_path = filedialog.askopenfilename(
            title="选择音频/视频文件",
            filetypes=(
                ("音频/视频文件", "*.mp3 *.mp4 *.wav *.m4a *.avi *.mov *.mkv"),
                ("音频文件", "*.mp3 *.wav *.m4a *.flac *.aac"),
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.wmv"),
                ("所有文件", "*.*")
            )
        )
        if file_path:
            self.process_dropped_file(file_path)

    def on_split_drop(self, event):
        """Handle file drop event"""
        files = event.data.split()
        if files:
            file_path = files[0]
            # Remove quotes if present
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]
            self.process_dropped_file(file_path)
        
        # Reset visual feedback
        self.split_canvas.configure(relief=tk.RAISED, bd=2)

    def process_dropped_file(self, file_path):
        """Process the dropped/selected file"""
        if not os.path.exists(file_path):
            messagebox.showerror("错误", f"文件不存在: {file_path}")
            return

        # Check file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in ['.mp3', '.wav', '.m4a', '.flac', '.aac']:
            self.process_audio_file(file_path)
        elif file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv']:
            self.process_video_file(file_path)
        else:
            messagebox.showerror("错误", f"不支持的文件格式: {file_ext}\n支持的格式: MP3, MP4, WAV, M4A, AVI, MOV, MKV")

    def process_audio_file(self, file_path):
        """Process audio file using split_audio"""
        start_time = self.split_start_time.get().strip()
        end_time = self.split_end_time.get().strip()
        
        # Validate time inputs
        try:
            start_time_val = float(start_time) if start_time else 0
            end_time_val = float(end_time) if end_time else None
            
            if start_time_val < 0:
                messagebox.showerror("错误", "开始时间不能为负数")
                return
            
            if end_time_val is not None and end_time_val <= start_time_val:
                messagebox.showerror("错误", "结束时间必须大于开始时间")
                return
                
        except ValueError:
            messagebox.showerror("错误", "时间格式错误，请输入数字")
            return

        # Confirm processing
        confirm_msg = f"确定要分割音频文件吗？\n\n文件: {os.path.basename(file_path)}\n开始时间: {start_time_val}秒\n结束时间: {end_time_val if end_time_val else '文件末尾'}秒"
        if not messagebox.askyesno("确认分割", confirm_msg):
            return

        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "split_audio",
            "status": "运行中",
            "start_time": datetime.now()
        }

        def run_task():
            try:
                self.status_var.set("分割音频中...")
                self.log_to_output(self.split_output, f"🎵 开始分割音频文件...")
                self.log_to_output(self.split_output, f"文件: {file_path}")
                self.log_to_output(self.split_output, f"开始时间: {start_time_val}秒")
                self.log_to_output(self.split_output, f"结束时间: {end_time_val if end_time_val else '文件末尾'}秒")

                # Split audio
                temp_output = self.workflow.ffmpeg_audio_processor.audio_cut_fade(file_path, start_time_val, end_time_val - start_time_val)
                
                # Create output filename with '__' suffix
                source_dir = os.path.dirname(file_path)
                source_name = os.path.splitext(os.path.basename(file_path))[0]
                source_ext = os.path.splitext(file_path)[1]
                output_path = os.path.join(source_dir, f"{source_name}__{source_ext}")
                
                # Move temp file to final location
                import shutil
                shutil.move(temp_output, output_path)

                self.log_to_output(self.split_output, f"✅ 音频分割完成！")
                self.log_to_output(self.split_output, f"输出文件: {output_path}")
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"

                # Show success message
                self.root.after(0, lambda: messagebox.showinfo("成功", f"音频分割完成！\n\n输出文件: {os.path.basename(output_path)}"))

            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.split_output, f"❌ 音频分割失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                self.root.after(0, lambda: messagebox.showerror("错误", f"音频分割失败: {error_msg}"))

        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()


        
    def create_music_prompts_tab(self):
        """Create music prompts generation tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="SUNO音乐提示词")
        
        # Music Prompts Configuration Section
        music_frame = ttk.LabelFrame(tab, text="SUNO音乐提示词配置", padding="10")
        music_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Container frame for text area and input fields
        inputs_container = ttk.Frame(music_frame)
        inputs_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Text area for music_style on the left
        text_area_frame = ttk.LabelFrame(inputs_container, text="音乐风格", padding="5")
        text_area_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        
        # Scrollbar for text area (pack first to ensure it's on the right)
        text_scrollbar = ttk.Scrollbar(text_area_frame, orient=tk.VERTICAL)
        text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.music_style = tk.Text(text_area_frame, width=80, height=10, wrap=tk.WORD,
                                   yscrollcommand=text_scrollbar.set)
        self.music_style.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure scrollbar command
        text_scrollbar.config(command=self.music_style.yview)
        
        # Input fields frame - organized in rows
        inputs_frame = ttk.Frame(inputs_container)
        inputs_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Row 1: Target and Topic
        row1_frame = ttk.Frame(inputs_frame)
        row1_frame.pack(fill=tk.X, pady=2)
        
        # Target input
        ttk.Label(row1_frame, text="语言:").pack(side=tk.LEFT)
        self.suno_language = ttk.Combobox(row1_frame, values=config_prompt.SUNO_LANGUAGE, state="normal", width=30)
        self.suno_language.set(config_prompt.SUNO_LANGUAGE[0])
        self.suno_language.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_language.bind('<FocusOut>', self.on_project_config_change)
        self.suno_language.bind('<<ComboboxSelected>>', self.on_project_config_change)

        # Overall Atmosphere input
        ttk.Label(row1_frame, text="内容:").pack(side=tk.LEFT)
        self.suno_expression = ttk.Combobox(row1_frame, values=list(config_prompt.SUNO_CONTENT.keys()), state="normal", width=30)
        self.suno_expression.set(list(config_prompt.SUNO_CONTENT.keys())[0])
        self.suno_expression.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_expression.bind('<FocusOut>', self.on_project_config_change)
        self.suno_expression.bind('<<ComboboxSelected>>', self.on_project_config_change)

        # Overall Atmosphere input
        ttk.Label(row1_frame, text="氛围:").pack(side=tk.LEFT)
        self.suno_atmosphere = ttk.Combobox(row1_frame, values=config_prompt.SUNO_ATMOSPHERE, state="normal", width=30)
        self.suno_atmosphere.set(config_prompt.SUNO_ATMOSPHERE[0])
        self.suno_atmosphere.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_atmosphere.bind('<FocusOut>', self.on_project_config_change)
        self.suno_atmosphere.bind('<<ComboboxSelected>>', self.on_project_config_change)

        
        # Row 2: Structure - 2-level selection
        row2_frame = ttk.Frame(inputs_frame)
        row2_frame.pack(fill=tk.X, pady=2)

        # Structure Category input
        ttk.Label(row2_frame, text="结构:").pack(side=tk.LEFT)
        self.suno_structure_categories = [list(structure.keys())[0] for structure in config_prompt.SUNO_STRUCTURE]
        self.suno_structure_category = ttk.Combobox(row2_frame, values=self.suno_structure_categories, state="normal", width=30)
        self.suno_structure_category.set(self.suno_structure_categories[0])
        self.suno_structure_category.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_structure_category.bind('<<ComboboxSelected>>', self.on_structure_category_change)
        self.suno_structure_category.bind('<FocusOut>', self.on_project_config_change)
        
        # Specific Structure input (dependent on category)
        ttk.Label(row2_frame, text="结构-").pack(side=tk.LEFT)
        self.suno_structure = ttk.Combobox(row2_frame, values=[], state="normal", width=30)
        self.suno_structure.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_structure.bind('<FocusOut>', self.on_project_config_change)
        self.suno_structure.bind('<<ComboboxSelected>>', self.on_project_config_change)

        # Melody Category input
        ttk.Label(row2_frame, text="旋律:").pack(side=tk.LEFT)
        self.suno_melody_categories = [list(melody.keys())[0] for melody in config_prompt.SUNO_MELODY]
        self.suno_melody_category = ttk.Combobox(row2_frame, values=self.suno_melody_categories, state="normal", width=30)
        self.suno_melody_category.set(self.suno_melody_categories[0])
        self.suno_melody_category.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_melody_category.bind('<<ComboboxSelected>>', self.on_melody_category_change)
        self.suno_melody_category.bind('<FocusOut>', self.on_project_config_change)
        
        # Specific Melody input (dependent on category)
        ttk.Label(row2_frame, text="旋律-").pack(side=tk.LEFT)
        self.suno_leading_melody = ttk.Combobox(row2_frame, values=[], state="normal", width=30)
        self.suno_leading_melody.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_leading_melody.bind('<FocusOut>', self.on_project_config_change)
        self.suno_leading_melody.bind('<<ComboboxSelected>>', self.on_project_config_change)

        # Row 3:
        row3_frame = ttk.Frame(inputs_frame)
        row3_frame.pack(fill=tk.X, pady=2)

        # Leading Instruments input - 2-level selection
        ttk.Label(row3_frame, text="乐器:").pack(side=tk.LEFT)
        self.suno_instruments_categories = [list(instrument.keys())[0] for instrument in config_prompt.SUNO_INSTRUMENTS]
        self.suno_instruments_category = ttk.Combobox(row3_frame, values=self.suno_instruments_categories, state="normal", width=30)
        self.suno_instruments_category.set(self.suno_instruments_categories[0])
        self.suno_instruments_category.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_instruments_category.bind('<<ComboboxSelected>>', self.on_instruments_category_change)
        self.suno_instruments_category.bind('<FocusOut>', self.on_project_config_change)
        
        # Specific Instruments input (dependent on category)
        ttk.Label(row3_frame, text="乐器-").pack(side=tk.LEFT)
        self.suno_instruments = ttk.Combobox(row3_frame, values=[], state="normal", width=30)
        self.suno_instruments.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_instruments.bind('<FocusOut>', self.on_project_config_change)
        self.suno_instruments.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        # Rhythm Groove Category input
        ttk.Label(row3_frame, text="律动:").pack(side=tk.LEFT)
        self.suno_rhythm_categories = [list(groove.keys())[0] for groove in config_prompt.SUNO_RHYTHM_GROOVE]
        self.suno_rhythm_category = ttk.Combobox(row3_frame, values=self.suno_rhythm_categories, state="normal", width=30)
        self.suno_rhythm_category.set(self.suno_rhythm_categories[0])
        self.suno_rhythm_category.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_rhythm_category.bind('<<ComboboxSelected>>', self.on_rhythm_category_change)
        self.suno_rhythm_category.bind('<FocusOut>', self.on_project_config_change)
        
        # Rhythm Groove Style input (dependent on category)
        ttk.Label(row3_frame, text="律动-").pack(side=tk.LEFT)
        self.suno_rhythm = ttk.Combobox(row3_frame, values=[], state="normal", width=30)
        self.suno_rhythm.pack(side=tk.LEFT, padx=(5, 15))
        self.suno_rhythm.bind('<FocusOut>', self.on_project_config_change)
        self.suno_rhythm.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        # Button frame - placed below comboboxes in inputs_frame
        button_frame = ttk.Frame(inputs_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(button_frame, text="生成SUNO提示词222", 
                  command=lambda: self.generate_music_prompt(False)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="保存音乐风格", 
                  command=self.save_music_style).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="清空内容", 
                  command=self.clear_music_prompts).pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="Refine", 
                  command=self.refine_music_prompt).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(button_frame, text="生成SUNO歌词", 
                  command=self.concise_music_lyrics).pack(side=tk.LEFT, padx=(0, 5))
        

        
        # Initialize the style comboboxes with the first category's values
        self.on_structure_category_change()
        self.on_melody_category_change()
        self.on_instruments_category_change()
        self.on_rhythm_category_change()
        
        # Content areas frame - side by side layout
        content_areas_frame = ttk.Frame(music_frame)
        content_areas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        content_areas_frame.grid_columnconfigure(0, weight=1)  # left_frame weight
        content_areas_frame.grid_columnconfigure(1, weight=1)  # prompt_frame weight
        content_areas_frame.grid_columnconfigure(2, weight=2)  # lyrics_frame weight (wider, 2x)
        
        # Left side - Original content area
        left_frame = ttk.LabelFrame(content_areas_frame, text="音乐内容", padding="5")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        
        # Content explanation - Combobox and button in same row
        content_info_frame = ttk.Frame(left_frame)
        content_info_frame.pack(fill=tk.X, pady=(0, 5))
        
        content_info_var = tk.StringVar()
        content_info = ttk.Combobox(content_info_frame, textvariable=content_info_var, 
                                    font=('TkDefaultFont', 9), state="readonly", width=50)
        
        # Set options from config_prompt.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT
        enhance_options = [f"选项 {i+1}: {example[:50]}..." if len(example) > 50 
                                                else f"示例 {i+1}: {example}" 
                                                for i, example in enumerate(config_prompt.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT)]
        content_info['values'] = enhance_options
        content_info.set("选择内容增强提示词...")
        content_info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Insert button - append selected content to self.music_content, placed right after combobox
        def insert_to_music_content():
            selected_index = content_info.current()
            if selected_index >= 0 and selected_index < len(config_prompt.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT):
                selected_content = config_prompt.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT[selected_index] + "\n>>>>\n"
                # Append to music_content
                cursor_pos = self.music_content.index(tk.INSERT)
                self.music_content.insert(cursor_pos, selected_content)
            
        copy_btn = ttk.Button(content_info_frame, text="插入", command=insert_to_music_content)
        copy_btn.pack(side=tk.LEFT, padx=(0, 0))


        # Example selection frame
        example_frame = ttk.Frame(left_frame)
        example_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(example_frame, text="示例内容:", font=('TkDefaultFont', 9)).pack(side=tk.LEFT, padx=(0, 5))
        
        # Example selection combobox
        self.music_example_var = tk.StringVar()
        self.music_example_combobox = ttk.Combobox(example_frame, textvariable=self.music_example_var, 
                                                  state="normal", width=50)
        
        # Set example options from config
        example_options = ["选择示例内容..."] + [f"示例 {i+1}: {example[:50]}..." if len(example) > 50 
                                                else f"示例 {i+1}: {example}" 
                                                for i, example in enumerate(config_prompt.SUNO_CONTENT_EXAMPLES)]
        self.music_example_combobox['values'] = example_options
        self.music_example_combobox.set("选择示例内容...")
        self.music_example_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.music_example_combobox.bind('<<ComboboxSelected>>', self.on_music_example_selected)
        
        # Insert button - placed right after combobox
        ttk.Button(example_frame, text="插入", 
                  command=self.insert_selected_music_example).pack(side=tk.LEFT, padx=(0, 0))
        

        self.music_content = scrolledtext.ScrolledText(left_frame, height=12, wrap=tk.WORD)
        self.music_content.pack(fill=tk.BOTH, expand=True)
        self.music_content.bind('<FocusOut>', self.on_project_config_change)
        
        # Music prompt - directly child of content_areas_frame
        prompt_frame = ttk.LabelFrame(content_areas_frame, text="提示词", padding="5")
        prompt_frame.grid(row=0, column=1, sticky="nsew", padx=(2, 2))
        prompt_frame.grid_rowconfigure(1, weight=1)
        
        self.music_prompt = scrolledtext.ScrolledText(prompt_frame, height=12, wrap=tk.WORD)
        self.music_prompt.grid(row=1, column=0, sticky="nsew")
        self.music_prompt.bind('<FocusOut>', self.on_project_config_change)

        # Music lyrics - directly child of content_areas_frame
        lyrics_frame = ttk.LabelFrame(content_areas_frame, text="歌词", padding="5")
        lyrics_frame.grid(row=0, column=2, sticky="nsew", padx=(0, 0))
        lyrics_frame.grid_rowconfigure(1, weight=1)
        
        self.music_lyrics = scrolledtext.ScrolledText(lyrics_frame, height=12, wrap=tk.WORD)
        self.music_lyrics.grid(row=1, column=0, sticky="nsew")
        self.music_lyrics.bind('<FocusOut>', self.on_project_config_change)
        
        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.music_output = scrolledtext.ScrolledText(output_frame, height=10)
        self.music_output.pack(fill=tk.BOTH, expand=True)
    
    def on_structure_category_change(self, event=None):
        """Handle structure category selection change"""
        if hasattr(self, 'suno_structure_category') and hasattr(self, 'suno_structure'):
            selected_category = self.suno_structure_category.get()
            # Find the corresponding structure object in SUNO_STRUCTURE
            for structure in config_prompt.SUNO_STRUCTURE:
                if selected_category in structure:
                    structures = structure[selected_category]
                    self.suno_structure['values'] = structures
                    if structures:
                        self.suno_structure.set(structures[0])
                    break
            # Trigger config save if this is from user interaction
            if event is not None:
                self.on_project_config_change()
    
    def on_melody_category_change(self, event=None):
        """Handle melody category selection change"""
        if hasattr(self, 'suno_melody_category') and hasattr(self, 'suno_leading_melody'):
            selected_category = self.suno_melody_category.get()
            # Find the corresponding melody object in SUNO_MELODY
            for melody in config_prompt.SUNO_MELODY:
                if selected_category in melody:
                    melodies = melody[selected_category]
                    self.suno_leading_melody['values'] = melodies
                    if melodies:
                        self.suno_leading_melody.set(melodies[0])
                    break
            # Trigger config save if this is from user interaction
            if event is not None:
                self.on_project_config_change()
    
    def on_instruments_category_change(self, event=None):
        """Handle instruments category selection change"""
        if hasattr(self, 'suno_instruments_category') and hasattr(self, 'suno_instruments'):
            selected_category = self.suno_instruments_category.get()
            # Find the corresponding instrument object in SUNO_INSTRUMENTS
            for instrument in config_prompt.SUNO_INSTRUMENTS:
                if selected_category in instrument:
                    instruments = instrument[selected_category]
                    self.suno_instruments['values'] = instruments
                    if instruments:
                        self.suno_instruments.set(instruments[0])
                    break
            # Trigger config save if this is from user interaction
            if event is not None:
                self.on_project_config_change()
    
    def on_rhythm_category_change(self, event=None):
        """Handle rhythm groove category selection change"""
        if hasattr(self, 'suno_rhythm_category') and hasattr(self, 'suno_rhythm'):
            selected_category = self.suno_rhythm_category.get()
            # Find the corresponding groove object in SUNO_RHYTHM_GROOVE
            for groove in config_prompt.SUNO_RHYTHM_GROOVE:
                if selected_category in groove:
                    styles = groove[selected_category]
                    self.suno_rhythm['values'] = styles
                    if styles:
                        self.suno_rhythm.set(styles[0])
                    break
            # Trigger config save if this is from user interaction
            if event is not None:
                self.on_project_config_change()
    
    def on_music_example_selected(self, event=None):
        """Handle music example selection change"""
        # No need to do anything on selection, user will click insert button
        pass
    
    def insert_selected_music_example(self):
        """Insert selected music example into the music content text area"""
        if not hasattr(self, 'music_example_combobox') or not hasattr(self, 'music_content'):
            return
            
        selected = self.music_example_combobox.get()
        if selected == "选择示例内容..." or not selected:
            return
        
        try:
            # Extract the example index from the selection
            if selected.startswith("示例 "):
                example_num = int(selected.split(":")[0].replace("示例 ", "")) - 1
                if 0 <= example_num < len(config_prompt.SUNO_CONTENT_EXAMPLES):
                    example_content = config_prompt.SUNO_CONTENT_EXAMPLES[example_num]
                    
                    # Get current cursor position
                    cursor_pos = self.music_content.index(tk.INSERT)
                    
                    # Insert the example content at cursor position
                    self.music_content.insert(cursor_pos, example_content)
                    
                    # Reset combobox selection
                    self.music_example_combobox.set("选择示例内容...")
                    
                    # Trigger config save
                    self.on_project_config_change()
                    
                    self.log_to_output(self.music_output, f"📝 已插入示例内容: 示例 {example_num + 1}")
        except (ValueError, IndexError) as e:
            self.log_to_output(self.music_output, f"❌ 插入示例内容时出错: {str(e)}")
    

    def generate_music_prompt(self, is_lyrics=False):
        """Generate music prompts for the project"""
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "generate_music_prompts",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                # Generate music prompts using workflow
                content = self.music_content.get(1.0, tk.END).strip()

                music_prompt = self.prepare_suno_music( content=content )
                self.root.after(0, lambda: self.music_prompt.delete(1.0, tk.END))
                self.root.after(0, lambda: self.music_prompt.insert(1.0, music_prompt))

                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
                # Auto-save the configuration
                self.root.after(100, self.save_project_config)
                
                # Show success message in main thread
                self.root.after(0, lambda: messagebox.showinfo("成功", f"SUNO音乐提示词生成完成！"))
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.music_output, f"❌ SUNO音乐提示词生成失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                # Show error message in main thread
                self.root.after(0, lambda: messagebox.showerror("错误", f"SUNO音乐提示词生成失败: {error_msg}"))
        
        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
    

    def save_music_style(self):
        language = self.suno_language.get() 
        expression = self.suno_expression.get()
        # Get new parameters
        atmosphere = self.suno_atmosphere.get()
        structure = self.suno_structure.get()
        leading_melody = self.suno_leading_melody.get()
        instruments = self.suno_instruments.get()
        rhythm_groove = self.suno_rhythm.get()
        
        # Confirm generation
        instruments_category = self.suno_instruments_category.get()
        confirm_msg = f"确定要生成SUNO音乐提示词吗？\n\n音乐类型: {language}"
        if instruments_category and instruments:
            confirm_msg += f"\n乐器类别: {instruments_category}\n具体乐器: {instruments}"
        elif instruments:
            confirm_msg += f"\n乐器: {instruments}"
        if not messagebox.askyesno("确认生成", confirm_msg):
            return

        """Save music prompts configuration"""
        suno_style_prompt = config_prompt.SUNO_STYLE_PROMPT.format(
            target=language,
            atmosphere=atmosphere,
            expression=expression+" ("+config_prompt.SUNO_CONTENT[expression]+")",
            structure=structure,
            melody=leading_melody,
            instruments=instruments,
            rhythm=rhythm_groove
        )
        self.root.after(0, lambda: self.music_style.delete(1.0, tk.END))
        self.root.after(0, lambda: self.music_style.insert(1.0, suno_style_prompt))
    


    def prepare_suno_music(self, content):
        system_prompt = "You are a professional to make SUNO-AI prompt for music creation according to the content of 'user-prompt' (in English, try add more details with richer musical guidance)"
        return self.llm_api.generate_text(system_prompt, content)



    def prepare_suno_lyrics(self, suno_lang, styles, content):
        system_prompt = f"""
You are a professional to make SUNO-AI prompt for song lyrics to cover the content in 'user-prompt' (in English, make it transcend/distill/elevated realm of resonance that moves and inspires).
**FYI: music-style details are in the 'music-style' section of the user-prompt**
"""
        return self.llm_api.generate_text(system_prompt, content + "\n\n\n***music-style***\n" + styles)
    
    def refine_music_prompt(self):
        """Refine and reorganize the music prompt content using LLM"""
        current_content = self.music_prompt.get(1.0, tk.END).strip()
        if not current_content:
            messagebox.showwarning("警告", "提示词内容为空，无法优化")
            return
        
        def run_refine():
            try:
                self.status_var.set("优化提示词中...")
                self.log_to_output(self.music_output, "🔄 开始优化提示词...")
                
                system_prompt = """You are a professional music prompt organizer. Your task is to make the music prompt more concise (try to keep it less than 1000 characters) and impactful while preserving the core meaning and emotional essence. 
Remove redundant words and phrases, but keep all important information and maintain the music prompt flow. 
Output the concise version of the music prompt."""

                refined_content = self.llm_api.generate_text(system_prompt, current_content)
                
                if refined_content:
                    self.root.after(0, lambda: self.music_prompt.delete(1.0, tk.END))
                    self.root.after(0, lambda: self.music_prompt.insert(1.0, refined_content.strip()))
                    self.root.after(0, lambda: self.on_project_config_change())
                    self.status_var.set("就绪")
                    self.log_to_output(self.music_output, "✅ 提示词优化完成")
                    self.root.after(0, lambda: messagebox.showinfo("成功", "提示词优化完成！"))
                else:
                    self.status_var.set("发生错误")
                    self.log_to_output(self.music_output, "❌ 提示词优化失败：未获得有效响应")
                    self.root.after(0, lambda: messagebox.showerror("错误", "提示词优化失败：未获得有效响应"))
                    
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.music_output, f"❌ 提示词优化失败: {error_msg}")
                self.status_var.set("发生错误")
                self.root.after(0, lambda: messagebox.showerror("错误", f"提示词优化失败: {error_msg}"))
        
        thread = threading.Thread(target=run_refine)
        thread.daemon = True
        thread.start()
    
    
    def concise_music_lyrics(self):
        """Make the music lyrics content more concise using LLM"""
        current_lyrics = self.music_lyrics.get(1.0, tk.END).strip()
        if not current_lyrics:
            messagebox.showwarning("警告", "歌词起始内容为空，无法进行生成")
            return
        
        def run_concise():
            try:
                language = self.suno_language.get()
                music_styles = self.music_style.get(1.0, tk.END).strip()
                music_prompt = self.music_prompt.get(1.0, tk.END).strip()

                lyrics_prompt = self.prepare_suno_lyrics(
                    suno_lang=language,
                    styles=music_prompt + "\n\n\n***music-style***\n" + music_styles,
                    content=current_lyrics
                )
                
                if lyrics_prompt:
                    self.root.after(0, lambda: self.music_lyrics.delete(1.0, tk.END))
                    self.root.after(0, lambda: self.music_lyrics.insert(1.0, lyrics_prompt.strip()))
                    self.root.after(0, lambda: self.on_project_config_change())
                    self.status_var.set("就绪")
                    self.log_to_output(self.music_output, "✅ 歌词精简完成")
                    self.root.after(0, lambda: messagebox.showinfo("成功", "歌词精简完成！"))
                else:
                    self.status_var.set("发生错误")
                    self.log_to_output(self.music_output, "❌ 歌词精简失败：未获得有效响应")
                    self.root.after(0, lambda: messagebox.showerror("错误", "歌词精简失败：未获得有效响应"))
                    
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.music_output, f"❌ 歌词精简失败: {error_msg}")
                self.status_var.set("发生错误")
                self.root.after(0, lambda: messagebox.showerror("错误", f"歌词精简失败: {error_msg}"))
        
        thread = threading.Thread(target=run_concise)
        thread.daemon = True
        thread.start()



    def clear_music_prompts(self):
        """Clear music prompts configuration"""
        self.suno_language.set(config_prompt.SUNO_LANGUAGE[0])
        self.suno_expression.set(list(config_prompt.SUNO_CONTENT.keys())[0])
        self.suno_atmosphere.set(config_prompt.SUNO_ATMOSPHERE[0])
        
        # Reset structure to first category and first structure
        if hasattr(self, 'suno_structure_category'):
            self.suno_structure_category.set(self.suno_structure_categories[0])
            self.on_structure_category_change()
        
        # Reset melody to first category and first melody
        if hasattr(self, 'suno_melody_category'):
            self.suno_melody_category.set(self.suno_melody_categories[0])
            self.on_melody_category_change()
        
        # Reset instruments to first category and first instrument
        if hasattr(self, 'suno_instruments_category'):
            self.suno_instruments_category.set(self.suno_instruments_categories[0])
            self.on_instruments_category_change()
        
        # Reset rhythm to first category and first rhythm
        if hasattr(self, 'suno_rhythm_category'):
            self.suno_rhythm_category.set(self.suno_rhythm_categories[0])
            self.on_rhythm_category_change()
        
        self.music_content.delete(1.0, tk.END)
        self.music_prompt.delete(1.0, tk.END)
        self.music_lyrics.delete(1.0, tk.END)
        self.on_project_config_change()
        self.log_to_output(self.music_output, f"🗑️ SUNO音乐提示词配置已清空")


    def run(self):
        """Start the application"""
        self.root.mainloop()


   
    def create_notebooklm_tab(self):
        """Create NotebookLM dialogue prompt generation tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="NotebookLM对话")
        
        # NotebookLM Configuration Section
        notebooklm_frame = ttk.LabelFrame(tab, text="NotebookLM对话配置", padding="10")
        notebooklm_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Input fields frame - organized in rows
        inputs_frame = ttk.Frame(notebooklm_frame)
        inputs_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Row 1: Style selection
        row1_frame = ttk.Frame(inputs_frame)
        row1_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(row1_frame, text="对话风格:").pack(side=tk.LEFT)
        self.notebooklm_style = ttk.Combobox(row1_frame, values=[
            "1 male & 1 female hosts",
            "1 male host", 
            "1 female host",
            "1 host & 2 actors",
            "2 hosts & 2 actors"
        ], state="readonly", width=25)
        self.notebooklm_style.set("1 male & 1 female hosts")
        self.notebooklm_style.pack(side=tk.LEFT, padx=(5, 15))
        self.notebooklm_style.bind('<FocusOut>', self.on_project_config_change)
        self.notebooklm_style.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        # Row 2: Topic
        row2_frame = ttk.Frame(inputs_frame)
        row2_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(row2_frame, text="对话主题:").pack(side=tk.LEFT)
        self.notebooklm_topic = ttk.Entry(row2_frame, width=60)
        self.notebooklm_topic.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.notebooklm_topic.bind('<FocusOut>', self.on_project_config_change)
        
        # Row 3: Avoid content
        row3_frame = ttk.Frame(inputs_frame)
        row3_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(row3_frame, text="避免内容:").pack(side=tk.LEFT)
        self.notebooklm_avoid = ttk.Entry(row3_frame, width=60)
        self.notebooklm_avoid.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.notebooklm_avoid.bind('<FocusOut>', self.on_project_config_change)
        
        # Row 4: Location
        row4_frame = ttk.Frame(inputs_frame)
        row4_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(row4_frame, text="对话地点:").pack(side=tk.LEFT)
        self.notebooklm_location = ttk.Entry(row4_frame, width=60)
        self.notebooklm_location.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.notebooklm_location.bind('<FocusOut>', self.on_project_config_change)
        
        # Row 5: Introduction Type
        row5_frame = ttk.Frame(inputs_frame)
        row5_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(row5_frame, text="前置类型:").pack(side=tk.LEFT)
        self.notebooklm_introduction_type = ttk.Combobox(row5_frame, values=[
            "listened radio-play-style introducation-story",
            "talked introduction-facts", 
            "talked introduction-news"
        ], state="readonly", width=60)
        self.notebooklm_introduction_type.set("listened radio-play-style introducation-story")
        self.notebooklm_introduction_type.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.notebooklm_introduction_type.bind('<FocusOut>', self.on_project_config_change)
        self.notebooklm_introduction_type.bind('<<ComboboxSelected>>', self.on_project_config_change)
        
        
        # File upload section
        files_frame = ttk.LabelFrame(notebooklm_frame, text="文件上传", padding="10")
        files_frame.pack(fill=tk.X, padx=5, pady=10)
        
        # Instructions
        instruction_text = "拖拽MP3或TXT文件到下方区域 (左侧：前置对话文件，右侧：介绍故事文件)"
        ttk.Label(files_frame, text=instruction_text, font=('TkDefaultFont', 10), foreground='gray').pack(pady=(0, 10))
        
        # Create left and right drop zones
        drop_zones_frame = ttk.Frame(files_frame)
        drop_zones_frame.pack(fill=tk.X, pady=5)
        
        # Left drop zone for previous dialogue
        left_zone_frame = ttk.LabelFrame(drop_zones_frame, text="前置对话文件", padding="10")
        left_zone_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.notebooklm_left_canvas = tk.Canvas(left_zone_frame, height=150, bg='lightblue', relief=tk.RAISED, bd=2)
        self.notebooklm_left_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Right drop zone for introduction story
        right_zone_frame = ttk.LabelFrame(drop_zones_frame, text="介绍故事文件", padding="10")
        right_zone_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.notebooklm_right_canvas = tk.Canvas(right_zone_frame, height=150, bg='lightgreen', relief=tk.RAISED, bd=2)
        self.notebooklm_right_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Load wave images and setup drag and drop
        self.load_notebooklm_images()
        self.setup_notebooklm_drag_drop()
        
        # File path storage
        self.notebooklm_previous_file = None
        self.notebooklm_introduction_file = None
        
        # Clear files button
        button_frame = ttk.Frame(files_frame)
        button_frame.pack(fill=tk.X, pady=5)
        ttk.Button(button_frame, text="生成NotebookLM提示词", 
                    command=self.generate_notebooklm_prompt).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="保存配置", 
                    command=self.save_notebooklm_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="清空配置", 
                    command=self.clear_notebooklm_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="清空前置对话", 
                    command=self.clear_notebooklm_previous).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="清空介绍故事", 
                    command=self.clear_notebooklm_introduction).pack(side=tk.LEFT, padx=(0, 10))

        # Generated prompt area
        prompt_frame = ttk.LabelFrame(notebooklm_frame, text="生成的提示词", padding="5")
        prompt_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.notebooklm_prompt_content = scrolledtext.ScrolledText(prompt_frame, height=12, wrap=tk.WORD)
        self.notebooklm_prompt_content.pack(fill=tk.BOTH, expand=True)
        self.notebooklm_prompt_content.bind('<FocusOut>', self.on_project_config_change)
        
        # Output area
        output_frame = ttk.LabelFrame(tab, text="输出日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.notebooklm_output = scrolledtext.ScrolledText(output_frame, height=10)
        self.notebooklm_output.pack(fill=tk.BOTH, expand=True)
    
    def load_notebooklm_images(self):
        """Load and display wave images in the NotebookLM canvases"""
        try:
            image_path = os.path.join(os.path.dirname(__file__), "media", "wave_sound.png")
            if os.path.exists(image_path):
                # Load and resize image for left canvas
                pil_image = Image.open(image_path)
                pil_image.thumbnail((150, 120), Image.Resampling.LANCZOS)
                self.notebooklm_left_image = ImageTk.PhotoImage(pil_image)
                self.notebooklm_right_image = ImageTk.PhotoImage(pil_image.copy())
                
                # Center images in canvases
                self.notebooklm_left_canvas.create_image(75, 75, image=self.notebooklm_left_image, anchor=tk.CENTER)
                self.notebooklm_left_canvas.create_text(75, 130, text="拖拽前置对话文件", font=('TkDefaultFont', 10, 'bold'), fill='darkblue')
                
                self.notebooklm_right_canvas.create_image(75, 75, image=self.notebooklm_right_image, anchor=tk.CENTER)
                self.notebooklm_right_canvas.create_text(75, 130, text="拖拽介绍故事文件", font=('TkDefaultFont', 10, 'bold'), fill='darkgreen')
            else:
                # Fallback if image not found
                self.notebooklm_left_canvas.create_text(75, 75, text="拖拽前置对话文件\n(MP3/TXT)", 
                                                      font=('TkDefaultFont', 12, 'bold'), fill='darkblue')
                self.notebooklm_right_canvas.create_text(75, 75, text="拖拽介绍故事文件\n(MP3/TXT)", 
                                                       font=('TkDefaultFont', 12, 'bold'), fill='darkgreen')
                
        except Exception as e:
            print(f"加载NotebookLM波形图片失败: {e}")
            # Fallback to text only
            self.notebooklm_left_canvas.create_text(75, 75, text="拖拽前置对话文件\n(MP3/TXT)", 
                                                  font=('TkDefaultFont', 12, 'bold'), fill='darkblue')
            self.notebooklm_right_canvas.create_text(75, 75, text="拖拽介绍故事文件\n(MP3/TXT)", 
                                                   font=('TkDefaultFont', 12, 'bold'), fill='darkgreen')
    
    def setup_notebooklm_drag_drop(self):
        """Setup drag and drop functionality for NotebookLM canvases"""
        if DND_AVAILABLE:
            try:
                # Setup left canvas (previous dialogue)
                self.notebooklm_left_canvas.drop_target_register(DND_FILES)
                self.notebooklm_left_canvas.dnd_bind('<<Drop>>', lambda e: self.on_notebooklm_drop(e, 'previous'))
                self.notebooklm_left_canvas.dnd_bind('<<DragEnter>>', lambda e: self.on_notebooklm_drag_enter(e, 'left'))
                self.notebooklm_left_canvas.dnd_bind('<<DragLeave>>', lambda e: self.on_notebooklm_drag_leave(e, 'left'))
                
                # Setup right canvas (introduction story)
                self.notebooklm_right_canvas.drop_target_register(DND_FILES)
                self.notebooklm_right_canvas.dnd_bind('<<Drop>>', lambda e: self.on_notebooklm_drop(e, 'introduction'))
                self.notebooklm_right_canvas.dnd_bind('<<DragEnter>>', lambda e: self.on_notebooklm_drag_enter(e, 'right'))
                self.notebooklm_right_canvas.dnd_bind('<<DragLeave>>', lambda e: self.on_notebooklm_drag_leave(e, 'right'))
            except Exception as e:
                print(f"设置NotebookLM拖拽功能失败: {e}")
                # Fallback to click
                self.notebooklm_left_canvas.bind('<Button-1>', lambda e: self.on_notebooklm_click('previous'))
                self.notebooklm_right_canvas.bind('<Button-1>', lambda e: self.on_notebooklm_click('introduction'))
        else:
            # Fallback to click if drag & drop not available
            self.notebooklm_left_canvas.bind('<Button-1>', lambda e: self.on_notebooklm_click('previous'))
            self.notebooklm_right_canvas.bind('<Button-1>', lambda e: self.on_notebooklm_click('introduction'))
    
    def on_notebooklm_drag_enter(self, event, side):
        """Visual feedback when dragging enters NotebookLM canvas"""
        if side == 'left':
            self.notebooklm_left_canvas.configure(relief=tk.SUNKEN, bd=3)
        else:
            self.notebooklm_right_canvas.configure(relief=tk.SUNKEN, bd=3)
    
    def on_notebooklm_drag_leave(self, event, side):
        """Visual feedback when dragging leaves NotebookLM canvas"""
        if side == 'left':
            self.notebooklm_left_canvas.configure(relief=tk.RAISED, bd=2)
        else:
            self.notebooklm_right_canvas.configure(relief=tk.RAISED, bd=2)
    
    def on_notebooklm_click(self, file_type):
        """Fallback file selection when drag & drop not available"""
        file_path = filedialog.askopenfilename(
            title=f"选择{'前置对话' if file_type == 'previous' else '介绍故事'}文件",
            filetypes=(
                ("音频/文本文件", "*.mp3 *.wav *.txt *.m4a"),
                ("音频文件", "*.mp3 *.wav *.m4a *.flac *.aac"),
                ("文本文件", "*.txt"),
                ("所有文件", "*.*")
            )
        )
        if file_path:
            self.process_notebooklm_file(file_path, file_type)
    
    def on_notebooklm_drop(self, event, file_type):
        """Handle file drop event for NotebookLM"""
        files = event.data.split()
        if files:
            file_path = files[0]
            # Remove quotes if present
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]
            self.process_notebooklm_file(file_path, file_type)
        
        # Reset visual feedback
        if file_type == 'previous':
            self.notebooklm_left_canvas.configure(relief=tk.RAISED, bd=2)
        else:
            self.notebooklm_right_canvas.configure(relief=tk.RAISED, bd=2)
    
    def process_notebooklm_file(self, file_path, file_type):
        """Process the dropped/selected file for NotebookLM"""
        if not os.path.exists(file_path):
            messagebox.showerror("错误", f"文件不存在: {file_path}")
            return
        
        # Check file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext not in ['.mp3', '.wav', '.txt', '.m4a', '.flac', '.aac']:
            messagebox.showerror("错误", f"不支持的文件格式: {file_ext}\n支持的格式: MP3, WAV, TXT, M4A")
            return
        
        # Store file path
        if file_type == 'previous':
            target_file = config.get_project_path(self.get_pid()) + "/notebooklm_previous" + file_ext
            if target_file != file_path:
                shutil.copy(file_path, target_file)
            self.notebooklm_previous_file = target_file
            # Update canvas display
            self.notebooklm_left_canvas.delete("all")
            filename = os.path.basename(file_path)
            self.notebooklm_left_canvas.create_text(75, 60, text="已选择文件:", font=('TkDefaultFont', 10, 'bold'), fill='darkblue')
            self.notebooklm_left_canvas.create_text(75, 80, text=filename[:20] + "..." if len(filename) > 20 else filename, 
                                                   font=('TkDefaultFont', 9), fill='darkblue')
            self.notebooklm_left_canvas.create_text(75, 120, text=f"类型: {file_ext.upper()}", font=('TkDefaultFont', 8), fill='gray')
        else:
            target_file = config.get_project_path(self.get_pid()) + "/notebooklm_introduction" + file_ext
            if target_file != file_path:
                shutil.copy(file_path, target_file)
            self.notebooklm_introduction_file = target_file
            # Update canvas display
            self.notebooklm_right_canvas.delete("all")
            filename = os.path.basename(file_path)
            self.notebooklm_right_canvas.create_text(75, 60, text="已选择文件:", font=('TkDefaultFont', 10, 'bold'), fill='darkgreen')
            self.notebooklm_right_canvas.create_text(75, 80, text=filename[:20] + "..." if len(filename) > 20 else filename, 
                                                    font=('TkDefaultFont', 9), fill='darkgreen')
            self.notebooklm_right_canvas.create_text(75, 120, text=f"类型: {file_ext.upper()}", font=('TkDefaultFont', 8), fill='gray')
        
        self.log_to_output(self.notebooklm_output, f"✅ {'前置对话' if file_type == 'previous' else '介绍故事'}文件已选择: {os.path.basename(file_path)}")
    
    def clear_notebooklm_previous(self):
        """Clear previous dialogue file"""
        self.notebooklm_previous_file = None
        self.notebooklm_left_canvas.delete("all")
        self.load_notebooklm_images()
        self.log_to_output(self.notebooklm_output, f"🗑️ 前置对话文件已清空")
    
    def clear_notebooklm_introduction(self):
        """Clear introduction story file"""
        self.notebooklm_introduction_file = None
        self.notebooklm_right_canvas.delete("all")
        self.load_notebooklm_images()
        self.log_to_output(self.notebooklm_output, f"🗑️ 介绍故事文件已清空")
    
    def generate_notebooklm_prompt(self):
        """Generate NotebookLM dialogue prompt"""
        style = self.notebooklm_style.get().strip()
        topic = self.notebooklm_topic.get().strip()
        avoid_content = self.notebooklm_avoid.get().strip()
        location = self.notebooklm_location.get().strip()
        introduction_type = self.notebooklm_introduction_type.get().strip()
        
        # Validate required inputs
        if not topic:
            messagebox.showerror("错误", "请输入对话主题")
            return
        
        # Process file inputs (read content if txt files)
        previous_dialogue = self.notebooklm_previous_file
        introduction_story = self.notebooklm_introduction_file
        
        # Confirm generation
        confirm_msg = f"确定要生成NotebookLM提示词吗？\n\n对话风格: {style}\n主题: {topic}\n地点: {location or '未指定'}\n前置类型: {introduction_type}"
        if not messagebox.askyesno("确认生成", confirm_msg):
            return
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "generate_notebooklm_prompt",
            "status": "运行中",
            "start_time": datetime.now()
        }
        
        def run_task():
            try:
                self.status_var.set("生成NotebookLM提示词中...")
                self.log_to_output(self.notebooklm_output, f"🎙️ 开始生成NotebookLM提示词...")
                self.log_to_output(self.notebooklm_output, f"对话风格: {style}")
                self.log_to_output(self.notebooklm_output, f"主题: {topic}")
                self.log_to_output(self.notebooklm_output, f"地点: {location or '未指定'}")
                self.log_to_output(self.notebooklm_output, f"前置类型: {introduction_type}")
                self.log_to_output(self.notebooklm_output, f"前置对话: {'已提供' if previous_dialogue else '未提供'}")
                self.log_to_output(self.notebooklm_output, f"介绍故事: {'已提供' if introduction_story else '未提供'}")
                
                # Generate NotebookLM prompt using workflow
                result = self.workflow.prepare_notebooklm_for_project(
                    style=style,
                    topic=topic,
                    avoid_content=avoid_content,
                    location=location,
                    previous_dialogue=previous_dialogue,
                    introduction_story=introduction_story,
                    introduction_type=introduction_type
                )
                
                notebookln_prompt_path = config.get_project_path(self.get_pid()) + "/notebooklm_prompt.json"
                with open(notebookln_prompt_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=4)

                # Update GUI in main thread
                self.root.after(0, lambda: self.notebooklm_prompt_content.delete(1.0, tk.END))
                self.root.after(0, lambda: self.notebooklm_prompt_content.insert(1.0, result))
                
                self.log_to_output(self.notebooklm_output, f"✅ NotebookLM提示词生成完成！")
                self.status_var.set("就绪")
                self.tasks[task_id]["status"] = "完成"
                
                # Auto-save the configuration
                self.root.after(100, self.save_project_config)
                
                # Show success message in main thread
                self.root.after(0, lambda: messagebox.showinfo("成功", f"NotebookLM提示词生成完成！"))
                
            except Exception as e:
                error_msg = str(e)
                self.log_to_output(self.notebooklm_output, f"❌ NotebookLM提示词生成失败: {error_msg}")
                self.status_var.set("发生错误")
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                # Show error message in main thread
                self.root.after(0, lambda: messagebox.showerror("错误", f"NotebookLM提示词生成失败: {error_msg}"))
        
        # Run in separate thread
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
    
    def save_notebooklm_config(self):
        """Save NotebookLM configuration"""
        try:
            self.save_project_config()
            messagebox.showinfo("成功", "NotebookLM配置已保存")
            self.log_to_output(self.notebooklm_output, f"✅ NotebookLM配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
            self.log_to_output(self.notebooklm_output, f"❌ 保存失败: {str(e)}")
    
    def clear_notebooklm_config(self):
        """Clear NotebookLM configuration"""
        self.notebooklm_style.set("1 male & 1 female hosts")
        self.notebooklm_topic.delete(0, tk.END)
        self.notebooklm_avoid.delete(0, tk.END)
        self.notebooklm_location.delete(0, tk.END)
        self.notebooklm_introduction_type.set("listened radio-play-style introducation-story")
        self.notebooklm_prompt_content.delete(1.0, tk.END)
        self.clear_notebooklm_previous()
        self.clear_notebooklm_introduction()
        self.on_project_config_change()
        self.log_to_output(self.notebooklm_output, f"🗑️ NotebookLM配置已清空")

    def run(self):
        """Start the application"""
        self.root.mainloop()


if __name__ == "__main__":
    app = MagicToolGUI()
    app.run() 