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
import re
import json
import glob
from datetime import datetime
import config
import config_prompt
import config_channel
from utility.llm_api import LLMApi, LM_STUDIO
from utility.file_util import safe_copy_overwrite, safe_remove
from config import LANGUAGES
from gui.downloader import MediaGUIManager



PROJECT_CONFIG = None

# 欢迎屏选择的旁白 narrator，供 YT → RAW 启动新项目 等路径复用（与 config_prompt.NARRATOR 一致）
LAST_NARRATOR = config_prompt.CHARACTOR[0]

# 欢迎屏选择的画面风格（英文，与 config.VISUAL_STYLE_OPTIONS 一致）
LAST_VISUAL_STYLE = config.VISUAL_STYLE_OPTIONS[0]

LAST_HOST_DISPLAY = config_prompt.HARRATOR_DISPLAY_OPTIONS[0]


media_count = 0
pid = None

def refresh_scene_media(scene, media_type, media_postfix, replacement=None, make_replacement_copy=False):
    global media_count, pid, PROJECT_CONFIG
    scene_id = scene.get("id", int(datetime.now().timestamp() * 1000) + media_count)
    new_media_stem = media_type + "_" + str(scene_id) + "_" + str(int(datetime.now().timestamp()*100 + media_count%100))
    media_count = (media_count + 1) % 100

    old_media_path = scene.get(media_type, None)
    if pid is None and PROJECT_CONFIG:
        pid = PROJECT_CONFIG.get('pid')
    if not pid:
        raise ValueError("无法获取项目ID，请先选择项目")
    scene[media_type] = config.get_media_path(pid) + "/" + new_media_stem + media_postfix

    if replacement:
        safe_copy_overwrite(replacement, scene[media_type])
        if not make_replacement_copy:
            safe_remove(replacement)
    return old_media_path, scene[media_type]


def _load_soul_content(channel_path, soul_spec):
    """将 soul 规格（文件路径或内联文本）转为实际内容。"""
    if not soul_spec or not isinstance(soul_spec, str):
        return ''
    soul = soul_spec.strip()
    if channel_path and soul and (soul.endswith('.md') or ('.' in soul and '\n' not in soul and len(soul) < 200)):
        file_path = os.path.join(channel_path, soul)
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception:
                pass
    return soul


def get_soul_for_topic(channel_path, topic_category, topic_subtype, topics_data):
    """从 topics_data 根据 topic_category/topic_subtype 查找 soul，支持文件路径或内联文本。

    流程：先按 topic_category 找到主题，加载 category 级 soul；若有 topic_subtype 再加载 subtype 级 soul；
    两者都存在时用 --- 分隔拼接返回；仅 category 存在则只返回 category；都不存在则返回空字符串。

    Args:
        channel_path: 频道目录路径（soul 文件所在目录）
        topic_category: 主题分类
        topic_subtype: 主题子类型
        topics_data: 从 config.load_topics 返回的 topic_choices 列表

    Returns:
        加载的 soul 文本，未找到则返回空字符串
    """
    if not topics_data or not isinstance(topics_data, list):
        return ''
    topic_category = (topic_category or '').strip()
    topic_subtype = (topic_subtype or '').strip()

    for topic in topics_data:
        if not isinstance(topic, dict):
            continue
        cat = topic.get('topic_category') or topic.get('category') or ''
        if cat.strip() != topic_category:
            continue
        # 先加载 category 级 soul
        cat_soul_spec = topic.get('soul') or ''
        category_soul = _load_soul_content(channel_path, cat_soul_spec) if cat_soul_spec else ''
        # 若有 subtype，再找并加载 subtype 级 soul
        subtype_soul = ''
        if topic_subtype:
            for st in topic.get('topic_subtypes') or []:
                if not isinstance(st, dict):
                    continue
                if (st.get('topic_subtype') or '').strip() == topic_subtype:
                    sub_spec = st.get('soul') or ''
                    subtype_soul = _load_soul_content(channel_path, sub_spec) if sub_spec else ''
                    break
        # 组合：两者都有则 category + --- + subtype；仅 category 有则只返回 category；都无则返回空
        parts = [p for p in (category_soul, subtype_soul) if p]
        return '\n---\n'.join(parts) if parts else ''

    return ''  # 未找到匹配的 topic_category


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
                channel = config_data.get('channel', '')
                video_size = f"{config_data.get('video_width', '1920')}x{config_data.get('video_height', '1080')}"
                
                # 获取最后修改时间
                mtime = os.path.getmtime(config_file)
                last_modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                
                projects.append({
                    'pid': pid,
                    'title': title,
                    'language': language,
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
        if PROJECT_CONFIG is not None:
            PROJECT_CONFIG.pop('debut_content', None)


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


class ProjectSelectionDialog:
    """项目选择对话框 - 可重用的项目选择界面"""
    
    def __init__(self, parent, config_manager, youtube_gui=None, create_only=False, selection_only=False, initial_channel=None, initial_language=None, initial_raw_content=None, initial_narrator=None, initial_visual_style=None, initial_host_display=None):
        """
        初始化项目选择对话框
        
        Args:
            parent: 父窗口
            config_manager: ProjectConfigManager实例
            youtube_gui: 可选，YT 相关功能的 GUI 管理器（下载/寻找/管理）
            create_only: 若为 True，直接打开创建新项目窗口，不显示项目列表
            selection_only: 若为 True，只显示项目列表，不显示「新建项目」按钮
            initial_channel: 首层选择的频道（用于创建新项目预填、YT 等）
            initial_language: 首层选择的语言
            initial_raw_content: 预设的 RAW 内容（用于从 NotebookLM Story 启动新项目）
            initial_narrator: 首层选择的旁白 narrator（config_prompt.NARRATOR）
            initial_visual_style: 首层选择的画面风格（config.VISUAL_STYLE_OPTIONS 的 value）
            initial_host_display: 首层选择的 Host 显示（HOST_DISPLAY_OPTIONS_DOWNLOADER 的英文 value）
        """
        self.parent = parent
        self.config_manager = config_manager
        self.youtube_gui = youtube_gui
        self.selected_config = None
        self.llm_api = LLMApi()
        self.llm_api_local = LLMApi(LM_STUDIO)

        available_channels = list(config_channel.CHANNEL_CONFIG.keys())
        default_channel = initial_channel or (available_channels[0] if available_channels else 'default')
        default_lang = initial_language or 'tw'

        _nar = initial_narrator or LAST_NARRATOR
        _vs = initial_visual_style or LAST_VISUAL_STYLE
        _hd = initial_host_display or LAST_HOST_DISPLAY
        
        self.default_project_config = {
            'languages': ['tw', 'zh', 'en'],
            'default_language': default_lang,
            'channels': available_channels,
            'default_channel': default_channel,
            'default_title': '新项目',
            'default_video_width': '1920',
            'default_video_height': '1080'
        }
        self.story_result = {
            'channel': default_channel,
            'language': default_lang,
            'narrator': _nar,
            'visual_style': _vs,
            'host_display': _hd,
            'channel_template': None,
            'topic_category': None,
            'topic_subtype': None,
            'tags': None,  # list of selected tag values from tags.json (one per tag_type)
            'soul': None,
            'content': None,
            'action': None,
        }
        self.initial_raw_content = initial_raw_content
        if create_only:
            # 创建隐藏的父窗口（用于后续销毁），创建表单必须挂在可见的 parent 下否则会白屏
            self.dialog = tk.Toplevel(parent)
            self.dialog.withdraw()
            self._form_parent = parent  # 创建新项目窗口的父窗口须为可见
            self.create_new_project()
            if self.story_result.get('action') != 'new' and self.dialog.winfo_exists():
                self.dialog.destroy()
        else:
            self.create_dialog(selection_only=selection_only)

    def build_soul(self, channel, topic_category, topic_subtype, topics_data):
        """从 topics_data 根据 topic_category/topic_subtype 加载并组合 soul（支持文件路径或内联文本）"""
        channel_path = config.get_channel_path(config_channel.get_channel_id(channel)) if channel else None
        return get_soul_for_topic(channel_path, topic_category, topic_subtype, topics_data)

    def create_dialog(self, selection_only=False):
        """创建对话框

        Args:
            selection_only: 若为 True，不显示「新建项目」按钮（该入口已移至启动首屏）
        """
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("选择项目")
        self.dialog.geometry("1000x600")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (1000 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (600 // 2)
        self.dialog.geometry(f"1000x600+{x}+{y}")

        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        title_label = ttk.Label(main_frame, text="选择要打开的项目", font=('TkDefaultFont', 14, 'bold'))
        title_label.pack(pady=(0, 20))

        list_frame = ttk.LabelFrame(main_frame, text="现有项目", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))

        columns = ('PID', '标题', '类型', '语言', '频道', '尺寸', '最后修改')
        self.project_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=12)
        self.project_tree.heading('PID', text='项目ID')
        self.project_tree.heading('标题', text='标题')
        self.project_tree.heading('类型', text='项目类型')
        self.project_tree.heading('语言', text='语言')
        self.project_tree.heading('频道', text='频道')
        self.project_tree.heading('尺寸', text='尺寸')
        self.project_tree.heading('最后修改', text='最后修改时间')
        self.project_tree.column('PID', width=120)
        self.project_tree.column('标题', width=150)
        self.project_tree.column('类型', width=80)
        self.project_tree.column('语言', width=60)
        self.project_tree.column('频道', width=100)
        self.project_tree.column('尺寸', width=80)
        self.project_tree.column('最后修改', width=130)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.project_tree.yview)
        self.project_tree.configure(yscrollcommand=scrollbar.set)
        self.project_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.project_tree.bind('<Double-1>', self.on_double_click)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        ttk.Button(left_buttons, text="刷新列表", command=self.refresh_projects).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(left_buttons, text="删除项目", command=self.delete_project).pack(side=tk.LEFT, padx=(0, 10))
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        ttk.Button(right_buttons, text="打开选中", command=self.open_selected).pack(side=tk.LEFT, padx=(0, 10))
        if not selection_only:
            ttk.Button(right_buttons, text="新建项目", command=self.create_new_project).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(right_buttons, text="取消", command=self.cancel).pack(side=tk.LEFT)

        self.refresh_projects()
        if self.project_tree.get_children():
            self.project_tree.selection_set(self.project_tree.get_children()[0])

    def refresh_projects(self):
        """刷新项目列表"""
        for item in self.project_tree.get_children():
            self.project_tree.delete(item)
        projects = self.config_manager.list_projects()
        for project in projects:
            self.project_tree.insert('', tk.END, values=(
                project['pid'],
                project['title'],
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
        # 创建新项目配置对话框；create_only 时父窗口须为可见的 parent，否则会白屏
        form_parent = getattr(self, '_form_parent', self.dialog)
        new_project_dialog = tk.Toplevel(form_parent)
        new_project_dialog.title("创建新项目")
        new_project_dialog.geometry("800x400")
        new_project_dialog.transient(form_parent)
        new_project_dialog.grab_set()
        
        # 居中显示
        new_project_dialog.update_idletasks()
        x = (new_project_dialog.winfo_screenwidth() - 800) // 2
        y = (new_project_dialog.winfo_screenheight() - 400) // 2
        new_project_dialog.geometry(f"800x400+{x}+{y}")
        
        main_frame = ttk.Frame(new_project_dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(1, weight=1)

        row = 0

        # PID、标题、视频分辨率：同一行横向排列
        top_fields_row = ttk.Frame(main_frame)
        top_fields_row.grid(row=row, column=0, columnspan=2, sticky='ew', pady=5)
        ttk.Label(top_fields_row, text="PID:").pack(side=tk.LEFT, padx=(0, 4))
        pid_entry = ttk.Entry(top_fields_row, width=18)
        pid_entry.pack(side=tk.LEFT, padx=(0, 16))
        auto_pid = f"p{datetime.now().strftime('%Y%m%d%H%M')}"
        pid_entry.insert(0, auto_pid)

        ttk.Label(top_fields_row, text="标题:").pack(side=tk.LEFT, padx=(0, 4))
        title_entry = ttk.Entry(top_fields_row, width=28)
        title_entry.pack(side=tk.LEFT, padx=(0, 16))
        title_entry.insert(0, self.default_project_config['default_title'])

        ttk.Label(top_fields_row, text="视频:").pack(side=tk.LEFT, padx=(0, 4))
        resolution_frame = ttk.Frame(top_fields_row)
        resolution_frame.pack(side=tk.LEFT, padx=(0, 0))
        resolution_var = tk.StringVar(value="1920x1080")
        ttk.Radiobutton(resolution_frame, text="1920x1080 (横向)", variable=resolution_var, value="1920x1080").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(resolution_frame, text="1080x1920 (纵向)", variable=resolution_var, value="1080x1920").pack(side=tk.LEFT)
        row += 1

        # 频道、语言只读；画面风格 / HOST / 旁白 与欢迎屏一致，此处用 Combobox 可改，创建时从控件写入 story_result
        welcome_info_row = ttk.Frame(main_frame)
        welcome_info_row.grid(row=row, column=0, columnspan=2, sticky='ew', pady=5)
        _np_styles = list(config.VISUAL_STYLE_OPTIONS)
        _vs_cur = self.story_result.get('visual_style')
        _hd_init = self.story_result.get('host_display')
        _nar_init = self.story_result.get('narrator')
        new_project_visual_style_var = tk.StringVar(value=_vs_cur)
        new_project_host_display_var = tk.StringVar(value=_hd_init)
        new_project_narrator_var = tk.StringVar(value=_nar_init)
        ttk.Label(welcome_info_row, text="频道:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(welcome_info_row, text=str(self.story_result.get('channel', '')), foreground="gray").pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(welcome_info_row, text="语言:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(welcome_info_row, text=str(self.story_result.get('language', '')), foreground="gray").pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(welcome_info_row, text="画面风格:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(
            welcome_info_row,
            textvariable=new_project_visual_style_var,
            values=_np_styles,
            state="readonly",
            width=14,
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(welcome_info_row, text="HOST:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(
            welcome_info_row,
            textvariable=new_project_host_display_var,
            values=list(config_prompt.HARRATOR_DISPLAY_OPTIONS),
            state="readonly",
            width=16,
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(welcome_info_row, text="旁白:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(
            welcome_info_row,
            textvariable=new_project_narrator_var,
            values=config_prompt.CHARACTOR,
            state="readonly",
            width=18,
        ).pack(side=tk.LEFT, padx=(0, 8))
        row += 1

        def sync_channel_template(*args):
            """频道变更时同步单一 channel_template 到 story_result"""
            templates_list, _ = config_channel.get_channel_templates(self.story_result['channel'])
            self.story_result['channel_template'] = templates_list[0] if templates_list else None

        sync_channel_template()

        # 主题分类选择（两级：category 和 subtype，各单选）
        topics_data = []  # 存储完整的 topics.json 数据
        tag_choices_data = []  # 存储 tags.json 数据 [{tag_type, tags}, ...]
        
        # 主题分类、主题子类型：同一行横向排列
        topic_row = ttk.Frame(main_frame)
        topic_row.grid(row=row, column=0, columnspan=2, sticky='ew', pady=5)
        ttk.Label(topic_row, text="主题分类:").pack(side=tk.LEFT)
        topic_category_combo = ttk.Combobox(topic_row, values=[], state="readonly", width=32)
        topic_category_combo.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(topic_row, text="主题子类:").pack(side=tk.LEFT)
        topic_subtype_combo = ttk.Combobox(topic_row, values=[], state="readonly", width=32)
        topic_subtype_combo.pack(side=tk.LEFT, padx=(0, 20))
        row += 1

        # 主题标签显示（可编辑，支持 a,b, GENRE=Jazz 格式，单选变更会同步至此）
        ttk.Label(main_frame, text="主题标签:").grid(row=row, column=0, sticky='w', padx=(0, 8), pady=5)
        _tags_initial = self.story_result.get('tags')
        _tags_str = ', '.join(_tags_initial) if isinstance(_tags_initial, list) else (str(_tags_initial) if _tags_initial else '')
        tags_var = tk.StringVar(value=_tags_str)
        tags_entry = ttk.Entry(main_frame, textvariable=tags_var, width=80)
        tags_entry.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='ew')
        row += 1
        
        # 显示说明文本的标签（支持多行）
        topic_explanation_label = ttk.Label(main_frame, text="", foreground="gray", wraplength=700, justify='left')
        topic_explanation_label.grid(row=row, column=1, columnspan=2, padx=(10, 0), pady=5, sticky='nw')
        row += 1
        
        def _tags_analysis_part(tags):
            """从 tags 中提取分析得来的部分（不含 '=' 的项）"""
            if not tags:
                return []
            lst = [t.strip() for t in (tags if isinstance(tags, list) else re.split(r'[|,]', str(tags))) if t and isinstance(t, str)]
            return [t for t in lst if '=' not in t]

        def _tags_manual_part(tags):
            """从 tags 中提取手动选择的 name=value 部分"""
            if not tags:
                return []
            lst = [t.strip() for t in (tags if isinstance(tags, list) else re.split(r'[|,]', str(tags))) if t and isinstance(t, str)]
            return [t for t in lst if '=' in t]

        def _parse_tags_entry_text(text):
            """解析 tags 输入框文本为 (analysis, manual)"""
            parts = [t.strip() for t in re.split(r'[|,]', text or '') if t.strip()]
            return [p for p in parts if '=' not in p], [p for p in parts if '=' in p]

        def _on_tags_entry_change(*args):
            """用户手动编辑 tags 时同步到 story_result"""
            combined = [t.strip() for t in re.split(r'[|,]', tags_var.get() or '') if t.strip()]
            self.story_result['tags'] = combined if combined else None

        tags_var.trace_add('write', _on_tags_entry_change)

        tag_combo_refs = []  # 存储 (tag_type, [(val, BooleanVar), ...]) 多选用
        
        # 更新主题子类型选项的函数（根据选择的 category）
        def update_topic_subtype(*args):
            selected_category = topic_category_combo.get()
            self.story_result['topic_category'] = selected_category.strip() if selected_category else None
            self.story_result['topic_subtype'] = None
            self.story_result['tags'] = _tags_manual_part(self.story_result.get('tags')) or None  # 保留手动选择的 name=value 标签
            tags_var.set(', '.join(self.story_result['tags'] or []))
            self.story_result['soul'] = None
            topic_subtype_combo.set('')
            topic_subtype_combo['values'] = []
            topic_explanation_label.config(text="")
            
            if selected_category and topics_data:
                subtypes = []
                for topic in topics_data:
                    if topic.get('topic_category') == selected_category:
                        for subtype_item in topic.get('topic_subtypes', []):
                            if isinstance(subtype_item, dict):
                                subtype_name = subtype_item.get('topic_subtype', '')
                                if subtype_name and subtype_name not in subtypes:
                                    subtypes.append(subtype_name)
                topic_subtype_combo['values'] = sorted(subtypes)
        
        # 更新说明文本的函数（显示 soul 和 sample_topic），并更新 self.topic_category/subtype/soul
        def update_explanation(*args):
            selected_category = topic_category_combo.get()
            selected_subtype = topic_subtype_combo.get()
            self.story_result['topic_category'] = selected_category.strip() if selected_category else None
            self.story_result['topic_subtype'] = selected_subtype.strip() if selected_subtype else None
            self.story_result['soul'] = self.build_soul(self.story_result['channel'], self.story_result['topic_category'], self.story_result['topic_subtype'], topics_data)
            
            if selected_category and topics_data:
                for topic in topics_data:
                    if topic.get('topic_category') == selected_category:
                        sample = topic.get('sample_topic', '')
                        display_parts = []
                        if self.story_result['soul']:
                            first_line = (self.story_result['soul'].split('\n')[0] or self.story_result['soul']).strip()
                            display_soul = (first_line[:64] + '…') if len(first_line) > 64 else first_line
                            display_parts.append(f"灵魂: {display_soul}")
                        if sample:
                            display_parts.append(f"示例: {sample}")
                        if display_parts:
                            topic_explanation_label.config(text="\n".join(display_parts), foreground="gray")
                        else:
                            topic_explanation_label.config(text="")
                        break
                else:
                    topic_explanation_label.config(text="")
            else:
                topic_explanation_label.config(text="")
        
        # 绑定事件在下方内容区域统一设置（含 update_buttons_state）

        # 加载主题分类选项的函数（从 topics.json）；channel/language 已从首层传入，不再从 UI 同步
        def update_topic_choices(*args):
            topics_data.clear()  # 清空旧数据
            tag_choices_data.clear()
            topic_category_combo.set('')  # 清空选择
            topic_category_combo['values'] = []
            topic_subtype_combo.set('')
            topic_subtype_combo['values'] = []
            topic_explanation_label.config(text="")
            self.story_result['topic_category'] = None
            self.story_result['topic_subtype'] = None
            self.story_result['tags'] = None
            self.story_result['soul'] = None
            tags_var.set('')
            
            if self.story_result['channel']:
                channel_path = config.get_channel_path(config_channel.get_channel_id(self.story_result['channel']))
                loaded_choices, loaded_categories, loaded_tags = config.load_topics(channel_path)
                topics_data.extend(loaded_choices)
                tag_choices_data.extend(loaded_tags)
                topic_category_combo['values'] = sorted(loaded_categories)
            # 频道切换后需更新编辑按钮状态
            try:
                update_buttons_state()
            except NameError:
                pass  # 初次加载时 update_buttons_state 尚未定义

        # 频道/语言已从首层传入，无需绑定变更事件；初始化加载主题分类与模板
        update_topic_choices()
        sync_channel_template()

        # 内容编辑区域：RAW | INIT（两列并排）
        content_panels_frame = ttk.Frame(main_frame)
        content_panels_frame.grid(row=row, column=0, columnspan=2, sticky='ew', padx=5, pady=10)
        content_panels_frame.columnconfigure(0, weight=1)
        content_panels_frame.columnconfigure(1, weight=1)
        row += 1

        # 第一列：RAW 内容（需先选 topic）
        raw_label_frame = ttk.LabelFrame(content_panels_frame, text="RAW内容", padding=10)
        raw_label_frame.grid(row=0, column=0, padx=(5, 5), sticky='nsew')
        raw_preview = ttk.Label(raw_label_frame, text="RAW: (未生成)", foreground="gray", wraplength=200)
        raw_preview.pack(anchor='w', pady=(0, 10))
        edit_raw_btn = ttk.Button(raw_label_frame, text="RAW内容", command=lambda: None)
        edit_raw_btn.pack(pady=5)

        # 第二列：INIT 内容
        story_label_frame = ttk.LabelFrame(content_panels_frame, text="INIT内容", padding=10)
        story_label_frame.grid(row=0, column=1, padx=5, sticky='nsew')
        init_preview = ttk.Label(story_label_frame, text="INIT: (未编辑)", foreground="gray", wraplength=200)
        init_preview.pack(anchor='w', pady=(0, 10))
        edit_init_btn = ttk.Button(story_label_frame, text="INIT编辑", command=lambda: None)
        edit_init_btn.pack(pady=5)

        _editor_open = [False]  # 用 list 以便在闭包中修改；同一时刻只允许打开一个编辑器

        def update_previews():
            """根据 story_result 更新 RAW/INIT 预览文本"""
            def _preview_text(val):
                """预览用：兼容 str/dict/list，转成短文本。"""
                if val is None:
                    return ""
                if isinstance(val, str):
                    return val.strip()
                if isinstance(val, (dict, list)):
                    try:
                        return json.dumps(val, ensure_ascii=False)
                    except Exception:
                        return str(val)
                return str(val).strip()

            # RAW
            raw_str = _preview_text(self.story_result.get('raw_content'))
            if raw_str:
                preview = (raw_str[:40] + '…') if len(raw_str) > 40 else raw_str
                raw_preview.config(text=f"RAW: {preview}", foreground="black")
            else:
                raw_preview.config(text="RAW: (未生成)", foreground="gray")
            # INIT
            init_str = _preview_text(self.story_result.get('init_content'))
            if init_str:
                preview = (init_str[:40] + '…') if len(init_str) > 40 else init_str
                init_preview.config(text=f"INIT: {preview}", foreground="black")
            else:
                init_preview.config(text="INIT: (未编辑)", foreground="gray")

        # 根据 topic、raw 状态启用/禁用编辑按钮
        def update_buttons_state(*args):
            has_topic = bool(self.story_result['topic_category'] and self.story_result['topic_subtype'])
            has_raw = bool(self.story_result.get('raw_content'))
            editor_busy = _editor_open[0]
            edit_raw_btn.config(state='normal' if has_topic and not editor_busy else 'disabled')
            # INIT：需已选 topic 且已有 raw_content
            can_edit_init = has_topic and has_raw and not editor_busy
            edit_init_btn.config(state='normal' if can_edit_init else 'disabled')


        def on_topic_category_selected(e):
            update_topic_subtype()
            update_explanation()
            update_buttons_state()

        def on_topic_subtype_selected(e):
            update_explanation()
            update_buttons_state()

        topic_category_combo.bind('<<ComboboxSelected>>', on_topic_category_selected)
        topic_subtype_combo.bind('<<ComboboxSelected>>', on_topic_subtype_selected)

        def _apply_category_result_to_ui(category_result, raw_preview_widget):
            """根据 category_result 更新 topic/title/tags 等 UI"""
            if not category_result:
                return
            cat = category_result.get('topic_category')
            sub = category_result.get('topic_subtype')
            if cat and sub:
                self.story_result['topic_category'] = cat
                topic_category_combo.set(cat)
                update_topic_subtype()
                self.story_result['topic_subtype'] = sub
                topic_subtype_combo.set(sub)
                topic_choices, _, _ = config.load_topics(config.get_channel_path(config_channel.get_channel_id(self.story_result['channel'])))
                self.story_result['soul'] = self.build_soul(self.story_result['channel'], cat, sub, topic_choices)
                update_explanation()
            title = category_result.get('title', '')
            if title:
                title_entry.delete(0, tk.END)
                title_entry.insert(0, title)
                self.story_result['title'] = title
            analysis_logic = category_result.get('analysis_logic', '')
            if analysis_logic:
                self.story_result['analysis_logic'] = analysis_logic
            problem_tags = category_result.get('tags', '')
            if problem_tags:
                analysis_tags = _tags_analysis_part(problem_tags)
                manual_tags = _tags_manual_part(self.story_result.get('tags'))
                self.story_result['tags'] = (analysis_tags + manual_tags) if (analysis_tags or manual_tags) else None
                tags_var.set(', '.join(self.story_result['tags'] or []))
            story_str = json.dumps(category_result, indent=2, ensure_ascii=False)
            new_project_dialog.clipboard_clear()
            new_project_dialog.clipboard_append(story_str)
            # RAW 预览显示 raw_content（原始故事），不显示 category_result JSON
            raw_str = (self.story_result.get('raw_content') or '').strip()
            if raw_str:
                preview = (raw_str[:40] + '…') if len(raw_str) > 40 else raw_str
                raw_preview_widget.config(text=f"RAW: {preview}", foreground="black")


        def open_raw_editor(initial_text=None):
            """输入 raw case-story，生成 system_prompt 并复制到剪贴板。initial_text 为预填内容时显示「直接使用」按钮；否则从 story_result['raw_content'] 读取"""
            # 未显式传入时，从 story_result 或 project config 读取已有 raw_content
            if initial_text is None:
                initial_text = self.story_result.get('raw_content') or ''
            if isinstance(initial_text, str) and initial_text.strip():
                initial_text = initial_text.strip()
            else:
                initial_text = None
            raw_dialog = tk.Toplevel(new_project_dialog)
            raw_dialog.title("RAW Case-Story 输入")
            raw_dialog.geometry("700x400")
            raw_dialog.transient(new_project_dialog)
            raw_dialog.grab_set()
            raw_dialog.update_idletasks()
            x = (raw_dialog.winfo_screenwidth() - 700) // 2
            y = (raw_dialog.winfo_screenheight() - 400) // 2
            raw_dialog.geometry(f"700x400+{x}+{y}")
            frame = ttk.Frame(raw_dialog, padding=20)
            frame.pack(fill=tk.BOTH, expand=True)
            ttk.Label(frame, text="请输入 Raw Case-Story 内容:", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
            case_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, width=70, height=12)
            case_text.pack(fill=tk.BOTH, expand=True)

            _prefill = (initial_text if initial_text is not None else '') or (self.story_result.get('raw_content') or '')
            if _prefill:
                case_text.insert(tk.END, _prefill)

            def paste_on_double_click(e):
                try:
                    s = raw_dialog.clipboard_get()
                    if s:
                        case_text.delete(1.0, tk.END)
                        case_text.insert(tk.END, s)
                except tk.TclError:
                    pass
            case_text.bind('<Double-1>', paste_on_double_click)

            raw_input_holder = [None]

            def on_ok():
                # 必须在 destroy 前读取文本；否则 wait_window 返回后控件已销毁会触发 TclError
                try:
                    raw_input_holder[0] = case_text.get('1.0', tk.END).strip()
                except tk.TclError:
                    raw_input_holder[0] = ""
                raw_dialog.destroy()

            btn_f = ttk.Frame(frame)
            btn_f.pack(fill=tk.X, pady=(10, 0))
            ttk.Button(btn_f, text="确认", command=on_ok).pack(side=tk.LEFT, padx=5)

            raw_dialog.wait_window()

            raw_input = (raw_input_holder[0] or "").strip()
            if not raw_input:
                return
            self.story_result['raw_content'] = raw_input

            topic_choices, topic_categories, _ = config.load_topics(config.get_channel_path(config_channel.get_channel_id(self.story_result['channel'])))
            category_result = self.llm_api_local.generate_json(
                config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(language=LANGUAGES.get(self.story_result['language'], self.story_result['language']), topic_choices=topic_choices),
                self.story_result['raw_content'],
                expect_list=False
            )
            if category_result:
                _apply_category_result_to_ui(category_result, raw_preview)
            update_buttons_state()
            update_previews()


        edit_raw_btn.config(command=open_raw_editor)

        # 若有预设 RAW（如从 NotebookLM Story 启动），预填并自动打开 RAW 编辑器
        _init_raw = getattr(self, 'initial_raw_content', None)
        if _init_raw and isinstance(_init_raw, str) and _init_raw.strip():
            self.story_result['raw_content'] = _init_raw.strip()
            update_previews()
            update_buttons_state()
            new_project_dialog.after(300, lambda: open_raw_editor(initial_text=_init_raw.strip()))


        def open_init_editor():
            _editor_open[0] = True
            update_buttons_state()

            topic = self.story_result.get('topic_category','') + " - " + self.story_result.get('topic_subtype','')
            user_prompt = f"On topic of {topic}, the initial story script is : \n{self.story_result.get('raw_content','')}\n\n\n\
                        And the core-insight ('soul') is: \n{self.story_result.get('soul', '')}"
            system_prompt = config_channel.get_channel_config(self.story_result['channel']).get('channel_prompt', {}).get('prompt_story_init', '')
            narrator = self.story_result.get('narrator') or config_prompt.CHARACTOR[0]
            system_prompt = system_prompt.format(
                language=LANGUAGES[self.story_result['language']],
                topic=topic,
                narrator=narrator
            )
            # 调用LLM生成内容
            self.story_result['init_content'] = self.llm_api.generate_json(system_prompt, user_prompt)

            update_previews()


        edit_init_btn.config(command=open_init_editor)

        # 初始状态：按钮禁用（topic 未选时）
        update_buttons_state()
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)

        def on_create():
            pid = pid_entry.get().strip()
            title = title_entry.get().strip()
            resolution = resolution_var.get()
            
            if not pid:
                messagebox.showerror("错误", "请输入项目ID")
                return
            if not title:
                messagebox.showerror("错误", "请输入标题")
                return
            
            if not self.story_result.get('init_content', None):
                self.story_result['init_content'] = ""

            if not self.story_result['raw_content']:
                messagebox.showerror("错误", "请先生成故事(Story)内容，才能创建项目")
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

            # self.story_result
            self.story_result['pid'] = pid
            self.story_result['video_title'] = title
            self.story_result['video_width'] = video_width
            self.story_result['video_height'] = video_height
            self.story_result['visual_style'] = new_project_visual_style_var.get()
            self.story_result['host_display'] = new_project_host_display_var.get()
            self.story_result['narrator'] = new_project_narrator_var.get()

            global LAST_NARRATOR, LAST_HOST_DISPLAY, LAST_VISUAL_STYLE
            LAST_VISUAL_STYLE = self.story_result['visual_style']
            LAST_HOST_DISPLAY = self.story_result['host_display']
            LAST_NARRATOR = self.story_result['narrator']

            self.story_result['action'] = 'new'
            # 保存 channel_id（多个 config key 可对应同一 channel_id）
            self.story_result['channel'] = config_channel.get_channel_id(self.story_result['channel'])
            self.story_result['prompts'] = config_channel.get_channel_config(self.story_result['channel']).get('channel_prompt', {})

            self.selected_config = self.story_result

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
            # 更新全局 PROJECT_CONFIG（selected_config 已由 load_project_config 读取，无需重复 load_config）
            ProjectConfigManager.set_global_config(self.selected_config)
            self.config_manager.pid = self.selected_config.get('pid')
            self.story_result['action'] = 'open'
            self.dialog.destroy()
        else:
            messagebox.showerror("错误", "无法加载项目配置")
    
    def cancel(self):
        """取消"""
        self.story_result['action'] = 'cancel'
        self.dialog.destroy()
    
    def show(self):
        """显示对话框并等待结果"""
        self.dialog.wait_window()
        return self.story_result.get('action', 'cancel'), self.selected_config


def show_initial_choice_dialog(parent):
    """GUI 启动时首先显示的选择：频道、语言、旁白 narrator、画面风格 + 创建新项目/选择项目/YT 操作"""
    result = {
        'choice': 'cancel',
        'channel': '',
        'language': '',
        'narrator': LAST_NARRATOR,
        'visual_style': LAST_VISUAL_STYLE,
        'host_display': LAST_HOST_DISPLAY
    }

    dialog = tk.Toplevel(parent)
    dialog.title("欢迎")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.resizable(False, False)

    main_frame = ttk.Frame(dialog, padding=30)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 顶部：频道、语言（从创建新项目移至此处，供所有后续操作使用）
    available_channels = list(config_channel.CHANNEL_CONFIG.keys())
    default_channel = available_channels[0] if available_channels else 'default'
    languages = ['tw', 'zh', 'en']
    default_lang = 'tw'

    opt_frame = ttk.Frame(main_frame)
    opt_frame.pack(fill=tk.X, pady=(0, 15))
    ttk.Label(opt_frame, text="频道").pack(side=tk.LEFT)
    channel_var = tk.StringVar(value=default_channel)
    channel_combo = ttk.Combobox(opt_frame, textvariable=channel_var, values=available_channels, state="readonly", width=16)
    channel_combo.pack(side=tk.LEFT, padx=(0, 5))

    ttk.Label(opt_frame, text="语言").pack(side=tk.LEFT)
    language_var = tk.StringVar(value=default_lang)
    language_combo = ttk.Combobox(opt_frame, textvariable=language_var, values=languages, state="readonly", width=3)
    language_combo.pack(side=tk.LEFT, padx=(0, 5))

    _styles = list(config.VISUAL_STYLE_OPTIONS)
    try:
        _style_default = _styles[_styles.index(LAST_VISUAL_STYLE)]
    except ValueError:
        _style_default = _styles[0]

    ttk.Label(opt_frame, text="风格").pack(side=tk.LEFT)
    visual_style_var = tk.StringVar(value=_style_default)
    visual_style_combo = ttk.Combobox(
        opt_frame,
        textvariable=visual_style_var,
        values=_styles,
        state="readonly",
        width=16,
    )
    visual_style_combo.pack(side=tk.LEFT)

    opt_frame2 = ttk.Frame(main_frame)
    opt_frame2.pack(fill=tk.X, pady=(0, 15))
    ttk.Label(opt_frame2, text="旁白").pack(side=tk.LEFT)
    narrator_var = tk.StringVar(
        value=LAST_NARRATOR
    )
    narrator_combo = ttk.Combobox(
        opt_frame2,
        textvariable=narrator_var,
        values=config_prompt.CHARACTOR,
        state="readonly",
        width=20,
    )
    narrator_combo.pack(side=tk.LEFT, padx=(0, 5))

    _hd_cur = config_prompt.HARRATOR_DISPLAY_OPTIONS[0]
    _host_opts = list(config_prompt.HARRATOR_DISPLAY_OPTIONS)
    _host_default = _hd_cur if _hd_cur in _host_opts else _host_opts[0]

    ttk.Label(opt_frame2, text="HOST").pack(side=tk.LEFT)
    host_display_var = tk.StringVar(value=_host_default)
    host_display_combo_welcome = ttk.Combobox(
        opt_frame2,
        textvariable=host_display_var,
        values=_host_opts,
        state="readonly",
        width=20,
    )
    host_display_combo_welcome.pack(side=tk.LEFT)

    ttk.Label(main_frame, text="请选择操作", font=('TkDefaultFont', 14, 'bold')).pack(pady=(0, 25))

    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(pady=15)

    def _sync_result_narrator():
        global LAST_NARRATOR
        result['narrator'] = narrator_var.get()
        LAST_NARRATOR = result['narrator']

    def _sync_result_visual_style():
        global LAST_VISUAL_STYLE
        result['visual_style'] = visual_style_var.get()
        LAST_VISUAL_STYLE = result['visual_style']

    def _sync_result_host_display():
        global LAST_HOST_DISPLAY
        result['host_display'] = host_display_var.get()
        LAST_HOST_DISPLAY = result['host_display']

    def _sync_welcome_choices():
        _sync_result_narrator()
        _sync_result_visual_style()
        _sync_result_host_display()

    def on_new():
        result['choice'] = 'new'
        result['channel'] = channel_var.get().strip()
        result['language'] = language_var.get().strip()
        _sync_welcome_choices()
        dialog.destroy()

    def on_open():
        result['choice'] = 'open'
        result['channel'] = channel_var.get().strip()
        result['language'] = language_var.get().strip()
        _sync_welcome_choices()
        dialog.destroy()

    def on_cancel():
        result['choice'] = 'cancel'
        dialog.destroy()

    def _create_yt_gui_and_run(yt_method, *args):
        """按当前 channel/language 创建 MediaGUIManager 并执行 YT 方法"""
        ch = channel_var.get().strip()
        lang = language_var.get().strip()
        if not ch:
            messagebox.showwarning("提示", "请先选择频道", parent=dialog)
            return
        _sync_welcome_choices()
        result['choice'] = 'yt'  # 标记为 YT 操作，避免调用方误判为取消而退出 App
        dialog.destroy()  # YT 操作时先关闭欢迎窗口
        # 使用独立 Toplevel 作为 YT 父窗口（无 parent），避免主窗口 withdraw 导致 YT 子窗被隐藏
        yt_parent = tk.Toplevel()
        yt_parent.title("YT 管理")
        yt_parent.geometry("300x80+100+100")  # 小窗口，用户可见且可关闭以退出应用
        yt_parent.lift()  # 确保显示在最前
        yt_parent.focus_force()
        def _on_yt_parent_close():
            yt_parent.destroy()
            try:
                parent.quit()
            except Exception:
                pass
        yt_parent.protocol("WM_DELETE_WINDOW", _on_yt_parent_close)
        yt_parent.lift()
        yt_parent.focus_force()
        # 不在此处 withdraw(parent)，否则 Windows 下可能导致所有窗口消失；等 YT 方法返回后再隐藏
        channel_path = config.get_channel_path(config_channel.get_channel_id(ch))
        _yt_log = tk.Text(yt_parent, height=1)
        def _yt_log_fn(w, m):
            try:
                w.insert(tk.END, m + '\n')
            except Exception:
                pass
        yt_gui = MediaGUIManager(yt_parent, channel_path, 'temp', {}, _yt_log_fn, _yt_log, language=lang)
        getattr(yt_gui, yt_method)(*args)
        # YT 方法返回后再隐藏主窗口（若提前 withdraw 可能导致 YT 子窗被一起隐藏）
        parent.withdraw()

    # 按钮垂直排列
    ttk.Button(btn_frame, text="选择项目", command=on_open, width=18).pack(fill=tk.X, pady=8)
    ttk.Button(btn_frame, text="创建新项目", command=on_new, width=18).pack(fill=tk.X, pady=8)

    yt_frame = ttk.Frame(btn_frame)
    yt_frame.pack(fill=tk.X, pady=(8, 0))
    ttk.Button(yt_frame, text="YT管理", command=lambda: _create_yt_gui_and_run('manage_hot_videos'), width=18).pack(side=tk.LEFT, padx=(0, 5))
    ttk.Button(yt_frame, text="YT文字", command=lambda: _create_yt_gui_and_run('download_youtube', True), width=18).pack(side=tk.LEFT, padx=(0, 5))
    ttk.Button(yt_frame, text="YT視頻", command=lambda: _create_yt_gui_and_run('download_youtube', False), width=18).pack(side=tk.LEFT)

    ttk.Button(btn_frame, text="取消", command=on_cancel, width=18).pack(fill=tk.X, pady=8)

    dialog.update_idletasks()
    w, h = 450, 580
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    dialog.protocol("WM_DELETE_WINDOW", on_cancel)
    dialog.wait_window()
    return (
        result['choice'],
        result['channel'] or default_channel,
        result['language'] or default_lang,
        result.get('narrator') or LAST_NARRATOR,
        result.get('visual_style') or LAST_VISUAL_STYLE,
        result.get('host_display') or config_prompt.HARRATOR_DISPLAY_OPTIONS[-1],
    )


def create_project_dialog(parent, youtube_gui=None):
    global PROJECT_CONFIG
    # 首先显示初始选择：频道、语言 + 创建新项目 / 选择项目 / YT
    choice, initial_channel, initial_language, initial_narrator, initial_visual_style, initial_host_display = show_initial_choice_dialog(parent)
    if choice == 'cancel':
        return 'cancel', None
    if choice == 'yt':
        # YT 操作已打开独立窗口，不创建/打开项目，但需让 App 保持运行
        return 'yt', None

    config_manager = ProjectConfigManager()

    if choice == 'new':
        # 直接打开创建新项目窗口，传入首层选择的 channel/language
        dialog = ProjectSelectionDialog(
            parent, config_manager, youtube_gui=youtube_gui, create_only=True,
            initial_channel=initial_channel, initial_language=initial_language,
            initial_narrator=initial_narrator,
            initial_visual_style=initial_visual_style,
            initial_host_display=initial_host_display,
        )
        result = dialog.story_result.get('action', 'cancel')
        selected_config = dialog.selected_config
        if dialog.dialog.winfo_exists():
            dialog.dialog.destroy()
    else:
        # 选择项目：显示项目列表（不含「新建项目」按钮），传入 channel/language
        dialog = ProjectSelectionDialog(
            parent, config_manager, youtube_gui=youtube_gui, selection_only=True,
            initial_channel=initial_channel, initial_language=initial_language,
            initial_narrator=initial_narrator,
            initial_visual_style=initial_visual_style,
            initial_host_display=initial_host_display,
        )
        result, selected_config = dialog.show()

    # 确保在返回前 PROJECT_CONFIG 仍然有效
    if PROJECT_CONFIG is None and selected_config is not None:
        PROJECT_CONFIG = selected_config.copy()
    return result, selected_config


def create_project_with_initial_raw(parent, raw_content, channel, language, initial_narrator=None, initial_visual_style=None, initial_host_display=None):
    """用现有 RAW 材料（如 NotebookLM Story）直接启动创建新项目，跳过初始选择"""
    global PROJECT_CONFIG
    if not raw_content or not raw_content.strip():
        return 'cancel', None
    config_manager = ProjectConfigManager()
    _nar = initial_narrator if initial_narrator is not None else LAST_NARRATOR
    _vs = initial_visual_style if initial_visual_style is not None else LAST_VISUAL_STYLE
    _hd = initial_host_display if initial_host_display is not None else config_prompt.HARRATOR_DISPLAY_OPTIONS[-1]
    dialog = ProjectSelectionDialog(
        parent, config_manager, youtube_gui=None, create_only=True,
        initial_channel=channel, initial_language=language,
        initial_raw_content=raw_content.strip(),
        initial_narrator=_nar,
        initial_visual_style=_vs,
        initial_host_display=_hd,
    )
    result = dialog.story_result.get('action', 'cancel')
    selected_config = dialog.selected_config
    if dialog.dialog.winfo_exists():
        dialog.dialog.destroy()
    if PROJECT_CONFIG is None and selected_config is not None:
        PROJECT_CONFIG = selected_config.copy()
    # 创建成功时保存项目配置，确保重启后能在项目列表中看到
    if result == 'new' and selected_config:
        pid = selected_config.get('pid')
        if pid:
            try:
                config_manager.pid = pid
                config_manager.save_project_config(selected_config)
            except Exception:
                pass
    return result, selected_config

