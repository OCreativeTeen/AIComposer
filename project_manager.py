"""
Reusable Project Configuration Manager Module

This module provides classes for managing project configurations and 
providing a GUI for project selection. Can be used across multiple applications.
"""

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import json
import glob
from datetime import datetime
import config

PROJECT_TYPE_STORY = "story"
PROJECT_TYPE_SONG = "song"
PROJECT_TYPE_MUSIC = "music"
PROJECT_TYPE_TALK = "talk"
PROJECT_TYPE_LIST = [
    PROJECT_TYPE_STORY,
    PROJECT_TYPE_SONG,
    PROJECT_TYPE_MUSIC,
    PROJECT_TYPE_TALK
]


class ProjectConfigManager:
    """管理每个项目的配置文件 - 可重用的项目配置管理器"""
    
    def __init__(self, pid=None):
        self.config_dir = "config"
        os.makedirs(self.config_dir, exist_ok=True)

        self.project_config = None
        self.pid = pid
        if pid:
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
        if not pid:
            return None
        
        self.pid = pid
        if not self.project_config:
            config_path = os.path.join(self.config_dir, f"{pid}.config")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.project_config = json.load(f)
        return self.project_config
    

    def save_project_config(self, config_data=None):
        """保存项目配置"""
        if not self.pid:
            print("❌ 项目ID未设置，无法保存项目配置")
            return False
        
        if not self.project_config:
            print("❌ 项目配置未加载，无法保存项目配置")
            return False
        
        if not config_data:
            config_data = self.project_config

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
        new_project_dialog.geometry("400x500")
        new_project_dialog.transient(self.dialog)
        new_project_dialog.grab_set()
        
        # 居中显示
        new_project_dialog.update_idletasks()
        x = (new_project_dialog.winfo_screenwidth() - 400) // 2
        y = (new_project_dialog.winfo_screenheight() - 500) // 2
        new_project_dialog.geometry(f"400x500+{x}+{y}")
        
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
        
        resolution_var = tk.StringVar(value="1920x1080")  # 默认横向
        ttk.Radiobutton(resolution_frame, text="1920x1080 (横向)", variable=resolution_var, value="1920x1080").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(resolution_frame, text="1080x1920 (纵向)", variable=resolution_var, value="1080x1920").pack(side=tk.LEFT)
        row += 1
        
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
                'story_site': story_site
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


def create_project_dialog(parent, pid=None):
    config_manager = ProjectConfigManager()
    config_manager.load_config(pid)
    dialog = ProjectSelectionDialog(parent, config_manager)
    return dialog.show()

