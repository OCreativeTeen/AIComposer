"""
Reusable Project Configuration Manager Module

This module provides classes for managing project configurations and 
providing a GUI for project selection. Can be used across multiple applications.
"""

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
import os
import json
import glob
from datetime import datetime
import config
import config_prompt
from utility.llm_api import LLMApi

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

PROJECT_CONFIG = None


class ProjectConfigManager:
    """管理每个项目的配置文件 - 可重用的项目配置管理器"""
    
    def __init__(self, pid=None):
        self.config_dir = "config"
        os.makedirs(self.config_dir, exist_ok=True)
        self.pid = pid
        self.load_config(pid)
    

    def list_projects(self):
        """列出所有项目配置"""
        config_files = glob.glob(os.path.join(self.config_dir, "*.config"))
        projects = []
        
        for config_file in config_files:
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    
                pid = config_data.get('pid', '')
                title = config_data.get('video_title', config_data.get('title', ''))
                language = config_data.get('language', 'zh')
                project_type = config_data.get('project_type', PROJECT_TYPE_STORY)  # 默认值
                channel = config_data.get('channel', '')
                video_size = f"{config_data.get('video_width', '1920')}x{config_data.get('video_height', '1080')}"
                
                # 获取最后修改时间
                mtime = os.path.getmtime(config_file)
                last_modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                
                projects.append({
                    'pid': pid,
                    'title': title,
                    'language': language,
                    'project_type': project_type,
                    'channel': channel,
                    'video_size': video_size,
                    'last_modified': last_modified,
                    'config_file': config_file,
                    'config_data': config_data
                })
            except Exception as e:
                print(f"⚠️ 无法读取配置文件 {config_file}: {e}")
        
        # 按最后修改时间排序
        projects.sort(key=lambda x: x['last_modified'], reverse=True)
        return projects
    

    def load_config(self, pid):
        global PROJECT_CONFIG
        if not pid:
            return PROJECT_CONFIG
        
        self.pid = pid
        config_path = os.path.join(self.config_dir, f"{pid}.config")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    PROJECT_CONFIG = loaded_config
                    print(f"🔍 load_config: 从文件加载配置成功，PID: {PROJECT_CONFIG.get('pid') if PROJECT_CONFIG else 'None'}")
            except Exception as e:
                print(f"⚠️ load_config: 从文件加载配置失败: {e}，保持现有 PROJECT_CONFIG")
                # 如果文件读取失败，保持现有的 PROJECT_CONFIG 不变
        else:
            print(f"🔍 load_config: 配置文件不存在，保持现有 PROJECT_CONFIG，PID: {PROJECT_CONFIG.get('pid') if PROJECT_CONFIG else 'None'}")
        # 如果文件不存在但 PROJECT_CONFIG 已经设置（例如新建项目），保持现有值
        return PROJECT_CONFIG
    
    @staticmethod
    def set_global_config(config_data):
        """设置全局 PROJECT_CONFIG"""
        global PROJECT_CONFIG
        PROJECT_CONFIG = config_data.copy() if config_data else None
    

    def save_project_config(self, config_data=None):
        """保存项目配置"""
        global PROJECT_CONFIG
        if not self.pid:
            print("❌ 项目ID未设置，无法保存项目配置")
            return False
        
        if not config_data:
            if not PROJECT_CONFIG:
                print("❌ 项目配置未加载，无法保存项目配置")
                return False
            config_data = PROJECT_CONFIG
        else:
            # 如果传入了 config_data，更新全局 PROJECT_CONFIG
            PROJECT_CONFIG = config_data.copy()

        config_path = os.path.join(self.config_dir, f"{self.pid}.config")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            print(f"✅ 项目配置已保存: {config_path}")
            return True
        except Exception as e:
            print(f"❌ 保存项目配置失败: {e}")
            return False
    

    def load_project_config(self, config_file):
        """加载项目配置"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 加载项目配置失败: {e}")
            return None
    
    def delete_project_config(self, config_file):
        """删除项目配置"""
        try:
            os.remove(config_file)
            print(f"🗑️ 已删除项目配置: {config_file}")
            return True
        except Exception as e:
            print(f"❌ 删除项目配置失败: {e}")
            return False


class ContentEditorDialog:
    """内容编辑器对话框 - 统一编辑 Story, Inspiration, Poem 三个字段"""
    
    def __init__(self, parent, project_type, language, channel,
                 initial_story="", initial_inspiration="", initial_poem=""):
        """
        初始化内容编辑器
        
        Args:
            parent: 父窗口
            project_type: 项目类型
            language: 语言
            initial_story: 初始故事内容
            initial_inspiration: 初始灵感内容
            initial_poem: 初始诗歌内容
        """
        self.parent = parent
        self.project_type = project_type
        self.language = language
        self.channel = channel
        # 保存三个字段的内容
        self.result_story = initial_story

        #if self.result_story == "" or self.result_story is None:
        #    self.result_story = config_prompt.STORY_OUTLINE_PROMPT.format(type_name=self.project_type, language=config.LANGUAGES[self.language])
            
        self.result_inspiration = initial_inspiration
        self.result_poem = initial_poem
        
        # 初始化LLM API
        self.llm_api = LLMApi()
        
        self.create_dialog()
    
    def create_dialog(self):
        """创建编辑器对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("内容编辑器 - Story / Inspiration / Poem")
        self.dialog.geometry("1000x800")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 居中显示
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 1000) // 2
        y = (self.dialog.winfo_screenheight() - 800) // 2
        self.dialog.geometry(f"1000x800+{x}+{y}")
        
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建Notebook来组织三个标签页
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Story 标签页
        story_frame = ttk.Frame(notebook, padding=10)
        notebook.add(story_frame, text="Story (故事大纲)")
        ttk.Label(story_frame, text="故事大纲 (Story Outline):", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        self.story_editor = scrolledtext.ScrolledText(story_frame, wrap=tk.WORD, width=90, height=15)
        self.story_editor.pack(fill=tk.BOTH, expand=True)
        self.story_editor.insert('1.0', self.result_story)
        
        # Inspiration 标签页
        inspiration_frame = ttk.Frame(notebook, padding=10)
        notebook.add(inspiration_frame, text="Inspiration (灵感)")
        ttk.Label(inspiration_frame, text="灵感 (Inspiration):", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        self.inspiration_editor = scrolledtext.ScrolledText(inspiration_frame, wrap=tk.WORD, width=90, height=15)
        self.inspiration_editor.pack(fill=tk.BOTH, expand=True)
        self.inspiration_editor.insert('1.0', self.result_inspiration)
        
        # Poem 标签页
        poem_frame = ttk.Frame(notebook, padding=10)
        notebook.add(poem_frame, text="Poem (诗歌)")
        ttk.Label(poem_frame, text="诗歌 (Poem):", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        self.poem_editor = scrolledtext.ScrolledText(poem_frame, wrap=tk.WORD, width=90, height=15)
        self.poem_editor.pack(fill=tk.BOTH, expand=True)
        self.poem_editor.insert('1.0', self.result_poem)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 左侧 Remix 按钮组
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        
        ttk.Button(left_buttons, text="Remix Story (AI生成故事)", command=lambda: self.remix_content("story")).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(left_buttons, text="Remix Inspiration (AI生成灵感)", command=lambda: self.remix_content("inspiration")).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(left_buttons, text="Remix Poem (AI生成诗歌)", command=lambda: self.remix_content("poem")).pack(side=tk.LEFT, padx=(0, 10))
        
        # 右侧按钮
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(right_buttons, text="确定", command=self.on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_buttons, text="取消", command=self.on_cancel).pack(side=tk.LEFT, padx=5)
    

    def remix_content(self, content_type):
        """使用LLM生成内容"""
        if not self.llm_api:
            messagebox.showerror("错误", "LLM API未初始化，无法生成内容")
            return
        
        type_name = self.project_type
        
        # 初始化变量，避免在异常处理时出现未定义错误
        editor = None
        original_content = ""
        prompt = ""
        system_prompt = ""

        language = config.LANGUAGES[self.language]

        try:
            if content_type == "story":
                # 生成故事
                current_story = self.story_editor.get('1.0', tk.END).strip()
                current_inspiration = self.inspiration_editor.get('1.0', tk.END).strip()

                prompt = config_prompt.INITIAL_CONTENT_USER_PROMPT.format(type_name=type_name, topic=config.channel_config[self.channel]["topic"], story=current_story, inspiration=current_inspiration)

                system_prompt = config_prompt.PROJECT_STORY_INIT_PROMPT.format(type_name=type_name, language=language)
                # 保存原始内容
                original_content = current_story
                editor = self.story_editor
            
            elif content_type == "inspiration":
                # 检查依赖：必须先有 story
                current_story = self.story_editor.get('1.0', tk.END).strip()
                if not current_story:
                    messagebox.showwarning("警告", "请先填写故事大纲(Story Outline)内容，才能生成灵感")
                    return

                current_inspiration = self.inspiration_editor.get('1.0', tk.END).strip()

                prompt = config_prompt.INITIAL_CONTENT_USER_PROMPT.format(type_name=type_name, topic=config.channel_config[self.channel]["topic"], story=current_story, inspiration=current_inspiration)

                system_prompt = config_prompt.INSPIRATION_PROMPT.format(type_name=type_name, language=language)
                
                # 保存原始内容
                original_content = current_inspiration
                editor = self.inspiration_editor
            
            elif content_type == "poem":
                # 检查依赖：必须先有 story 和 inspiration
                story_content = self.story_editor.get('1.0', tk.END).strip()
                inspiration_content = self.inspiration_editor.get('1.0', tk.END).strip()
                
                if not story_content:
                    messagebox.showwarning("警告", "请先填写故事大纲(Story Outline)内容，才能生成诗歌")
                    return
                if not inspiration_content:
                    messagebox.showwarning("警告", "请先填写灵感(Inspiration)内容，才能生成诗歌")
                    return
                
                current_poem = self.poem_editor.get('1.0', tk.END).strip()
                system_prompt = config_prompt.POEM_PROMPT.format(
                    type_name=type_name, 
                    language=language,
                    initial_content=current_poem
                )
                prompt = config_prompt.INITIAL_CONTENT_USER_PROMPT.format(type_name=type_name, topic=config.channel_config[self.channel]["topic"], story=story_content, inspiration=inspiration_content)
                
                # 保存原始内容
                original_content = current_poem
                editor = self.poem_editor
            
            else:
                messagebox.showerror("错误", f"未知的内容类型: {content_type}")
                return
            
            # 显示生成中提示
            editor.config(state=tk.DISABLED)
            editor.delete('1.0', tk.END)
            editor.insert('1.0', "正在生成内容，请稍候...")
            self.dialog.update()
            
            # 调用LLM生成内容
            generated_content = self.llm_api.generate_text(system_prompt, prompt)

            if generated_content:
                editor.config(state=tk.NORMAL)
                editor.delete('1.0', tk.END)
                editor.insert('1.0', generated_content.strip())
                messagebox.showinfo("成功", "内容生成完成！")
            else:
                editor.config(state=tk.NORMAL)
                editor.delete('1.0', tk.END)
                editor.insert('1.0', original_content)
                messagebox.showerror("错误", "LLM返回了空内容")
        
        except Exception as e:
            if editor is not None:
                editor.config(state=tk.NORMAL)
                # 如果出错，恢复原始内容
                editor.delete('1.0', tk.END)
                editor.insert('1.0', original_content)
            messagebox.showerror("错误", f"生成内容时发生错误: {str(e)}")
            print(f"❌ Remix错误: {e}")

    
    def on_ok(self):
        """确定按钮 - 保存三个字段的内容"""
        self.result_story = self.story_editor.get('1.0', tk.END).strip()
        self.result_inspiration = self.inspiration_editor.get('1.0', tk.END).strip()
        self.result_poem = self.poem_editor.get('1.0', tk.END).strip()

        self.dialog.destroy()


    def on_cancel(self):
        """取消按钮"""
        self.dialog.destroy()
    

    def show(self):
        """显示对话框并返回结果"""
        self.dialog.wait_window()
        return {
            'story': self.result_story,
            'inspiration': self.result_inspiration,
            'poem': self.result_poem
        }


class ProjectSelectionDialog:
    """项目选择对话框 - 可重用的项目选择界面"""
    
    def __init__(self, parent, config_manager):
        """
        初始化项目选择对话框
        
        Args:
            parent: 父窗口
            config_manager: ProjectConfigManager实例
            project_config: 项目配置字典，用于自定义新项目的默认值和选项
        """
        self.parent = parent
        self.config_manager = config_manager
        self.selected_config = None
        self.result = None
        
        # 默认项目配置选项
        # 从config.py获取可用的频道列表
        available_channels = list(config.channel_config.keys())
        default_channel = available_channels[0] if available_channels else 'default'
        
        self.default_project_config = {
            'languages': ['tw', 'zh', 'en'],
            'default_language': 'tw',
            'channels': available_channels,
            'default_channel': default_channel,
            'default_title': '新项目',
            'default_video_width': '1920',
            'default_video_height': '1080',
            'additional_fields': {},  # 额外的配置字段
            'default_program_keywords': '', # 新增的默认项目关键词
            'default_story_site': '' # 新增的默认故事场景
        }
        
        self.create_dialog()
    
    def create_dialog(self):
        """创建对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("选择项目")
        self.dialog.geometry("1000x600")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 使对话框居中
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (1000 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (600 // 2)
        self.dialog.geometry(f"1000x600+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题
        title_label = ttk.Label(main_frame, text="选择要打开的项目", font=('TkDefaultFont', 14, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # 项目列表框架
        list_frame = ttk.LabelFrame(main_frame, text="现有项目", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # 创建Treeview显示项目列表
        columns = ('PID', '标题', '类型', '语言', '频道', '尺寸', '最后修改')
        self.project_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=12)
        
        # 设置列
        self.project_tree.heading('PID', text='项目ID')
        self.project_tree.heading('标题', text='标题')
        self.project_tree.heading('类型', text='项目类型')
        self.project_tree.heading('语言', text='语言')
        self.project_tree.heading('频道', text='频道')
        self.project_tree.heading('尺寸', text='尺寸')
        self.project_tree.heading('最后修改', text='最后修改时间')
        
        # 设置列宽
        self.project_tree.column('PID', width=120)
        self.project_tree.column('标题', width=150)
        self.project_tree.column('类型', width=80)
        self.project_tree.column('语言', width=60)
        self.project_tree.column('频道', width=100)
        self.project_tree.column('尺寸', width=80)
        self.project_tree.column('最后修改', width=130)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.project_tree.yview)
        self.project_tree.configure(yscrollcommand=scrollbar.set)
        
        self.project_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定双击事件
        self.project_tree.bind('<Double-1>', self.on_double_click)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        # 左侧按钮（项目操作）
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        
        ttk.Button(left_buttons, text="刷新列表", command=self.refresh_projects).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(left_buttons, text="删除项目", command=self.delete_project).pack(side=tk.LEFT, padx=(0, 10))
        
        # 右侧按钮（对话框操作）
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(right_buttons, text="打开选中", command=self.open_selected).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(right_buttons, text="新建项目", command=self.create_new_project).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(right_buttons, text="取消", command=self.cancel).pack(side=tk.LEFT)
        
        # 加载项目列表
        self.refresh_projects()
        
        # 如果有项目，选中第一个
        if self.project_tree.get_children():
            self.project_tree.selection_set(self.project_tree.get_children()[0])
    
    def refresh_projects(self):
        """刷新项目列表"""
        # 清空现有项目
        for item in self.project_tree.get_children():
            self.project_tree.delete(item)
        
        # 加载项目
        projects = self.config_manager.list_projects()
        
        for project in projects:
            self.project_tree.insert('', tk.END, values=(
                project['pid'],
                project['title'],
                project['project_type'],
                project['language'],
                project['channel'],
                project['video_size'],
                project['last_modified']
            ), tags=(project['config_file'],))
    
    def on_double_click(self, event):
        """双击打开项目"""
        self.open_selected()
    
    def delete_project(self):
        """删除选中的项目"""
        selection = self.project_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请选择要删除的项目")
            return
        
        item = selection[0]
        config_file = self.project_tree.item(item)['tags'][0]
        pid = self.project_tree.item(item)['values'][0]
        title = self.project_tree.item(item)['values'][1]
        
        if messagebox.askyesno("确认删除", f"确定要删除项目 '{pid} - {title}' 吗？\n\n这将删除项目配置文件，但不会删除项目数据。"):
            if self.config_manager.delete_project_config(config_file):
                self.refresh_projects()
                messagebox.showinfo("成功", "项目配置已删除")
    
    def create_new_project(self):
        """创建新项目"""
        # 创建新项目配置对话框
        new_project_dialog = tk.Toplevel(self.dialog)
        new_project_dialog.title("创建新项目")
        new_project_dialog.geometry("500x700")
        new_project_dialog.transient(self.dialog)
        new_project_dialog.grab_set()
        
        # 居中显示
        new_project_dialog.update_idletasks()
        x = (new_project_dialog.winfo_screenwidth() - 500) // 2
        y = (new_project_dialog.winfo_screenheight() - 700) // 2
        new_project_dialog.geometry(f"500x700+{x}+{y}")
        
        main_frame = ttk.Frame(new_project_dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        row = 0
        
        # PID输入
        ttk.Label(main_frame, text="项目ID (PID):").grid(row=row, column=0, sticky='w', pady=5)
        pid_entry = ttk.Entry(main_frame, width=25)
        pid_entry.grid(row=row, column=1, padx=(10, 0), pady=5)
        # 自动生成默认PID
        auto_pid = f"project_{datetime.now().strftime('%Y%m%d_%H%M')}"
        pid_entry.insert(0, auto_pid)
        row += 1
        
        # 语言选择
        ttk.Label(main_frame, text="语言:").grid(row=row, column=0, sticky='w', pady=5)
        language_combo = ttk.Combobox(main_frame, values=self.default_project_config['languages'], state="readonly", width=22)
        language_combo.grid(row=row, column=1, padx=(10, 0), pady=5)
        language_combo.set(self.default_project_config['default_language'])
        row += 1
        
        # 项目类型选择
        ttk.Label(main_frame, text="项目类型:").grid(row=row, column=0, sticky='w', pady=5)
        project_type_combo = ttk.Combobox(main_frame, values=PROJECT_TYPE_LIST, state="readonly", width=22)
        project_type_combo.grid(row=row, column=1, padx=(10, 0), pady=5)
        project_type_combo.set(PROJECT_TYPE_STORY)  # 默认设置为 story
        row += 1
        
        # 频道选择
        ttk.Label(main_frame, text="频道:").grid(row=row, column=0, sticky='w', pady=5)
        channel_combo = ttk.Combobox(main_frame, values=self.default_project_config['channels'], state="readonly", width=22)
        channel_combo.grid(row=row, column=1, padx=(10, 0), pady=5)
        channel_combo.set(self.default_project_config['default_channel'])
        row += 1
        
        # 标题
        ttk.Label(main_frame, text="标题:").grid(row=row, column=0, sticky='w', pady=5)
        title_entry = ttk.Entry(main_frame, width=25)
        title_entry.grid(row=row, column=1, padx=(10, 0), pady=5)
        title_entry.insert(0, self.default_project_config['default_title'])
        row += 1
        
        # 项目关键词
        ttk.Label(main_frame, text="项目关键词:").grid(row=row, column=0, sticky='w', pady=5)
        keywords_entry = ttk.Entry(main_frame, width=25)
        keywords_entry.grid(row=row, column=1, padx=(10, 0), pady=5)
        keywords_entry.insert(0, self.default_project_config.get('default_program_keywords', ''))
        row += 1

        # 故事场景
        ttk.Label(main_frame, text="故事场景:").grid(row=row, column=0, sticky='w', pady=5)
        story_site_entry = ttk.Entry(main_frame, width=25)
        story_site_entry.grid(row=row, column=1, padx=(10, 0), pady=5)
        story_site_entry.insert(0, self.default_project_config.get('default_story_site', ''))
        row += 1
        
        # 视频分辨率选择
        ttk.Label(main_frame, text="视频分辨率:").grid(row=row, column=0, sticky='w', pady=5)
        resolution_frame = ttk.Frame(main_frame)
        resolution_frame.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        
        resolution_var = tk.StringVar(value="1080x1920")  # 默认横向
        ttk.Radiobutton(resolution_frame, text="1920x1080 (横向)", variable=resolution_var, value="1920x1080").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(resolution_frame, text="1080x1920 (纵向)", variable=resolution_var, value="1080x1920").pack(side=tk.LEFT)
        row += 1

        # 统一的内容编辑器按钮
        content_label_frame = ttk.LabelFrame(main_frame, text="内容编辑", padding=10)
        content_label_frame.grid(row=row, column=0, columnspan=2, sticky='ew', padx=5, pady=10)
        row += 1
        
        # 使用变量存储三个字段的内容
        story_var = tk.StringVar(value="")
        inspiration_var = tk.StringVar(value="")
        poem_var = tk.StringVar(value="")
        
        # 显示当前内容的预览
        preview_frame = ttk.Frame(content_label_frame)
        preview_frame.pack(fill=tk.X, pady=(0, 10))
        
        story_preview = ttk.Label(preview_frame, text="Story: (未编辑)", foreground="gray")
        story_preview.pack(anchor='w', pady=2)
        
        inspiration_preview = ttk.Label(preview_frame, text="Inspiration: (未编辑)", foreground="gray")
        inspiration_preview.pack(anchor='w', pady=2)
        
        poem_preview = ttk.Label(preview_frame, text="Poem: (未编辑)", foreground="gray")
        poem_preview.pack(anchor='w', pady=2)
        
        # 更新预览显示的函数
        def update_previews():
            story_val = story_var.get()
            inspiration_val = inspiration_var.get()
            poem_val = poem_var.get()
            
            if story_val:
                preview_text = story_val[:50] + "..." if len(story_val) > 50 else story_val
                story_preview.config(text=f"Story: {preview_text}", foreground="black")
            else:
                story_preview.config(text="Story: (未编辑)", foreground="gray")
            
            if inspiration_val:
                preview_text = inspiration_val[:50] + "..." if len(inspiration_val) > 50 else inspiration_val
                inspiration_preview.config(text=f"Inspiration: {preview_text}", foreground="black")
            else:
                inspiration_preview.config(text="Inspiration: (未编辑)", foreground="gray")
            
            if poem_val:
                preview_text = poem_val[:50] + "..." if len(poem_val) > 50 else poem_val
                poem_preview.config(text=f"Poem: {preview_text}", foreground="black")
            else:
                poem_preview.config(text="Poem: (未编辑)", foreground="gray")
        
        # 绑定变量更新到预览显示
        story_var.trace_add('write', lambda *args: update_previews())
        inspiration_var.trace_add('write', lambda *args: update_previews())
        poem_var.trace_add('write', lambda *args: update_previews())
        
        # 统一的编辑按钮
        def open_unified_editor():
            editor = ContentEditorDialog(
                new_project_dialog,
                project_type_combo.get(),
                language_combo.get(),
                channel_combo.get(),
                story_var.get(),
                inspiration_var.get(),
                poem_var.get()
            )
            result = editor.show()
            if result:
                story_var.set(result.get('story', ''))
                inspiration_var.set(result.get('inspiration', ''))
                poem_var.set(result.get('poem', ''))
        
        ttk.Button(content_label_frame, text="编辑 Story / Inspiration / Poem", command=open_unified_editor).pack(pady=5)
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)
        
        def on_create():
            pid = pid_entry.get().strip()
            language = language_combo.get()
            project_type = project_type_combo.get()
            channel = channel_combo.get()
            title = title_entry.get().strip()
            program_keywords = keywords_entry.get().strip()
            story_site = story_site_entry.get().strip()
            resolution = resolution_var.get()
            
            if not pid:
                messagebox.showerror("错误", "请输入项目ID")
                return
            if not title:
                messagebox.showerror("错误", "请输入标题")
                return
            
            # 检查 story 和 inspiration 是否已生成
            story_content = story_var.get().strip()
            inspiration_content = inspiration_var.get().strip()
            
            if not story_content:
                messagebox.showerror("错误", "请先生成故事(Story)内容，才能创建项目")
                return
            
            if not inspiration_content:
                messagebox.showerror("错误", "请先生成灵感(Inspiration)内容，才能创建项目")
                return
            
            # 解析分辨率
            if resolution == "1920x1080":
                video_width = "1920"
                video_height = "1080"
            elif resolution == "1080x1920":
                video_width = "1080"
                video_height = "1920"
            else:
                # 默认值
                video_width = self.default_project_config['default_video_width']
                video_height = self.default_project_config['default_video_height']
                
            # 创建新项目配置
            self.selected_config = {
                'pid': pid,
                'language': language,
                'project_type': project_type,
                'channel': channel,
                'video_title': title,
                'program_keywords': program_keywords,
                'video_width': video_width,
                'video_height': video_height,
                **self.default_project_config.get('additional_fields', {}),
                'story_site': story_site,
                'inspiration': inspiration_var.get(),
                'poem': poem_var.get(),
                'story': story_var.get()
            }
            
            self.result = 'new'
            new_project_dialog.destroy()
            self.dialog.destroy()
        
        def on_cancel():
            new_project_dialog.destroy()
        
        ttk.Button(button_frame, text="创建", command=on_create).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        # 等待对话框关闭
        new_project_dialog.wait_window()
    
    def open_selected(self):
        """打开选中的项目"""
        selection = self.project_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请选择要打开的项目")
            return
        
        item = selection[0]
        config_file = self.project_tree.item(item)['tags'][0]
        self.selected_config = self.config_manager.load_project_config(config_file)
        
        if self.selected_config:
            # 更新全局 PROJECT_CONFIG
            ProjectConfigManager.set_global_config(self.selected_config)
            pid = self.selected_config.get('pid')
            if pid:
                loaded_config = self.config_manager.load_config(pid)
            self.result = 'open'
            self.dialog.destroy()
        else:
            messagebox.showerror("错误", "无法加载项目配置")
    
    def cancel(self):
        """取消"""
        self.result = 'cancel'
        self.dialog.destroy()
    
    def show(self):
        """显示对话框并等待结果"""
        self.dialog.wait_window()
        return self.result, self.selected_config


def create_project_dialog(parent):
    global PROJECT_CONFIG
    config_manager = ProjectConfigManager()
    dialog = ProjectSelectionDialog(parent, config_manager)
    result, selected_config = dialog.show()
    # 确保在返回前 PROJECT_CONFIG 仍然有效
    if PROJECT_CONFIG is None and selected_config is not None:
        PROJECT_CONFIG = selected_config.copy()
    return result, selected_config

