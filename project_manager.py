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
from config import parse_json_from_text
import config_channel
from utility.llm_api import LLMApi, OLLAMA
from utility.file_util import safe_copy_overwrite, safe_remove
from utility.audio_transcriber import LANGUAGES



PROJECT_CONFIG = None



media_count = 0
pid = None

def refresh_scene_media(scene, media_type, media_postfix, replacement=None, make_replacement_copy=False):
    global media_count, pid, PROJECT_CONFIG
    new_media_stem = media_type + "_" + str(scene["id"]) + "_" + str(int(datetime.now().timestamp()*100 + media_count%100))
    media_count = (media_count + 1) % 100

    old_media_path = scene.get(media_type, None)
    if pid is None:
        pid = PROJECT_CONFIG.get('pid')
    scene[media_type] = config.get_media_path(pid) + "/" + new_media_stem + media_postfix

    if replacement:
        safe_copy_overwrite(replacement, scene[media_type])
        if not make_replacement_copy:
            safe_remove(replacement)
    return old_media_path, scene[media_type]



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
    
    def __init__(self, parent, language, channel, initial_story=""):
        self.parent = parent
        self.language = language
        self.channel = channel

        self.result_story = initial_story
        # 初始化LLM API
        self.llm_api = LLMApi()
        self.llm_api_local = LLMApi(OLLAMA)
        
        self.create_dialog()
    

    def create_dialog(self):
        """创建编辑器对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("内容编辑器 - Story")
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

        self.story_editor.bind('<Double-1>', self.on_story_editor_double_click)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 左侧 Remix 按钮组
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        
        # 右侧按钮
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(right_buttons, text="重整", command=self.on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_buttons, text="返回", command=self.on_cancel).pack(side=tk.LEFT, padx=5)
    

    def on_story_editor_double_click(self, event):
        """双击事件处理：从剪贴板粘贴内容"""
        try:
            # 获取剪贴板内容
            clipboard_content = self.dialog.clipboard_get()
            if clipboard_content:
                # 在当前位置插入剪贴板内容
                self.story_editor.insert(tk.INSERT, clipboard_content)
        except tk.TclError:
            # 剪贴板为空或无法访问时，静默处理
            pass
        except Exception as e:
            # 其他错误时，可以显示提示（可选）
            print(f"粘贴剪贴板内容时出错: {e}")


    def on_ok(self):
        topic=config_channel.CHANNEL_CONFIG[self.channel]["topic"]
        story=self.story_editor.get('1.0', tk.END).strip()
        user_prompt = f"Here is the Initial story script on topic of {topic}:  {story}"
        raw_prompt = config_channel.CHANNEL_CONFIG[self.channel]["channel_prompt"]["program_story"]
        try:
            system_prompt = raw_prompt.format(language=LANGUAGES[self.language])
        except KeyError:
            system_prompt = raw_prompt
        # 调用LLM生成内容
        generated_content = self.llm_api.generate_text(system_prompt, user_prompt)

        topic_choices, topic_categories = config.load_topics(config.get_channel_path(self.channel))

        category_result = self.llm_api_local.generate_json(
            config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(language=LANGUAGES.get(self.language, self.language), topic_choices=topic_choices), 
            generated_content,
            expect_list=False
        )
        if category_result:
            category_result['story'] = generated_content

            self.story_editor.config(state=tk.NORMAL)
            self.story_editor.delete('1.0', tk.END)
            self.story_editor.insert('1.0', json.dumps(category_result, indent=2, ensure_ascii=False))
            self.result_story = self.story_editor.get('1.0', tk.END).strip()


    def on_cancel(self):
        self.result_story = self.story_editor.get('1.0', tk.END).strip()
        self.dialog.destroy()
    

    def show(self):
        """显示对话框并返回结果"""
        self.dialog.wait_window()
        return self.result_story



class AnalysisEditorDialog:
    """分析内容编辑器 - 使用 Story 内容调用 LLM 生成分析"""

    def __init__(self, parent, initial_analysis="", story_content="", reference_content="", language="tw", channel=""):
        self.parent = parent
        self.result_analysis = initial_analysis
        self.story_content = story_content
        self.reference_content = reference_content
        self.language = language
        self.channel = channel
        self.llm_api = LLMApi()
        self.create_dialog()

    def create_dialog(self):
        """创建编辑器对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("分析内容编辑器")
        self.dialog.geometry("800x500")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 800) // 2
        y = (self.dialog.winfo_screenheight() - 500) // 2
        self.dialog.geometry(f"800x500+{x}+{y}")

        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="分析内容 (Analysis):", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        self.analysis_editor = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=80, height=15)
        self.analysis_editor.pack(fill=tk.BOTH, expand=True)
        self.analysis_editor.insert('1.0', self.result_analysis)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="确定", command=self.on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_cancel).pack(side=tk.LEFT, padx=5)

    def on_ok(self):
        """使用 Story 内容调用 LLM 生成分析"""
        if not self.llm_api:
            messagebox.showerror("错误", "LLM API 未初始化")
            return

        if not self.story_content or not self.story_content.strip():
            messagebox.showerror("错误", "请先编辑并保存 Story 内容，再生成分析")
            return

        topic = config_channel.CHANNEL_CONFIG.get(self.channel, {}).get("topic", "")

        user_prompt = f"Here is the K-Story:\n{self.story_content}\n\n\nHere is the Reference: \n{self.reference_content}"
        # user_prompt = f"Here is the Initial analysis script on topic of {topic}:  {self.result_analysis}"

        raw_prompt = config_channel.CHANNEL_CONFIG.get(self.channel, {}).get("channel_prompt", {}).get("program_analysis", "")
        try:
            system_prompt = raw_prompt.format(language=LANGUAGES.get(self.language, self.language)) if raw_prompt else ""
        except (KeyError, ValueError):
            system_prompt = raw_prompt

        generated_json = self.llm_api.generate_json(system_prompt, user_prompt, expect_list=False)
        if generated_json:
            self.analysis_editor.config(state=tk.NORMAL)
            self.analysis_editor.delete('1.0', tk.END)
            self.analysis_editor.insert('1.0', json.dumps(generated_json, indent=2, ensure_ascii=False))
            self.result_analysis = self.analysis_editor.get('1.0', tk.END).strip()
            messagebox.showinfo("成功", "分析内容生成完成！")
        else:
            messagebox.showerror("错误", "分析内容生成失败")

        self.dialog.destroy()


    def on_cancel(self):
        self.dialog.destroy()

    def show(self):
        """显示对话框并返回结果"""
        self.dialog.wait_window()
        return self.result_analysis



class ReferenceEditorDialog:
    """参考内容编辑器 - 基于 Story 分析的参考案例与素材（搜索/生成逻辑待后续集成）"""

    def __init__(self, parent, initial_reference="", story_content="", topic_category="", topic_subtype=""):
        self.parent = parent
        self.result_reference = initial_reference
        self.story_content = story_content
        self.topic_category = topic_category
        self.topic_subtype = topic_subtype
        self.llm_api = LLMApi()
        self.create_dialog()

    def create_dialog(self):
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("参考内容编辑器")
        self.dialog.geometry("800x500")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 800) // 2
        y = (self.dialog.winfo_screenheight() - 500) // 2
        self.dialog.geometry(f"800x500+{x}+{y}")

        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="参考内容 (References)：分析与案例素材，供主持人参考，亦作为生成分析内容的输入", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        self.reference_editor = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=80, height=15)
        self.reference_editor.pack(fill=tk.BOTH, expand=True)
        self.reference_editor.insert('1.0', self.result_reference)
        self.reference_editor.bind('<Double-1>', self._on_paste_from_clipboard)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="从 NotebookLM 获取", command=self._fetch_from_notebooklm).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="确定", command=self.on_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_cancel).pack(side=tk.LEFT, padx=5)

    def _on_paste_from_clipboard(self, event=None):
        try:
            clipboard_content = self.dialog.clipboard_get()
            if clipboard_content:
                self.reference_editor.insert(tk.INSERT, clipboard_content)
        except tk.TclError:
            pass

    def _fetch_from_notebooklm(self):
        """工作流：复制 prompt 到剪贴板 → 用户在 NotebookLM 生成 → 粘贴结果 → 勾选需要的项 → 写入 reference_editor"""
        if not self.story_content or not self.story_content.strip():
            messagebox.showerror("错误", "请先完成 Story 内容，再获取参考")
            return

        reference_filter_prompt = config_channel.COUNSELING_REFERENCE_FILTER + "\n---------\n" + "Topic-Category: " + self.topic_category + "\nTopic-Subtype: " + self.topic_subtype + "\n\n" + self.story_content
        try:
            self.dialog.clipboard_clear()
            self.dialog.clipboard_append(reference_filter_prompt)
        except tk.TclError:
            pass

        messagebox.showinfo("提示", "已将筛选 Prompt 复制到剪贴板。\n\n请到 NotebookLM 中使用该 prompt 生成参考列表。\n\n点击确定后，将打开粘贴窗口，请将生成的 JSON 粘贴到该窗口中（双击可快速粘贴剪贴板），然后确认以继续勾选需要的参考项。")

        paste_dialog = tk.Toplevel(self.dialog)
        paste_dialog.title("粘贴 NotebookLM 生成内容")
        paste_dialog.geometry("700x400")
        paste_dialog.transient(self.dialog)
        paste_dialog.grab_set()
        paste_dialog.update_idletasks()
        x = (paste_dialog.winfo_screenwidth() - 700) // 2
        y = (paste_dialog.winfo_screenheight() - 400) // 2
        paste_dialog.geometry(f"700x400+{x}+{y}")

        ttk.Label(paste_dialog, text="请将 NotebookLM 生成的 JSON 粘贴到下方（双击可从剪贴板粘贴）", font=('TkDefaultFont', 10)).pack(anchor='w', padx=20, pady=(20, 5))
        paste_text = scrolledtext.ScrolledText(paste_dialog, wrap=tk.WORD, width=80, height=12)
        paste_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        def paste_on_double_click(e):
            try:
                clipboard_content = paste_dialog.clipboard_get()
                json_content = self.llm_api.parse_json(clipboard_content, expect_list=True)
                if json_content:
                    paste_text.insert(tk.INSERT, json.dumps(json_content, indent=2, ensure_ascii=False))
                else:
                    paste_text.insert(tk.INSERT, clipboard_content)
            except tk.TclError:
                pass

        paste_text.bind('<Double-1>', paste_on_double_click)

        generated_content = [None]

        def on_paste_confirm():
            raw = paste_text.get('1.0', tk.END).strip()
            if not raw:
                messagebox.showerror("错误", "请先粘贴 NotebookLM 生成的内容")
                return
            
            parsed = parse_json_from_text(raw)
            if not parsed:
                messagebox.showerror("错误", "无法解析为 JSON 对象，请确认粘贴的是包含 story 与 analysis 的 JSON")
                return
            if isinstance(parsed, list):
                if len(parsed) == 0:
                    messagebox.showerror("错误", "JSON array size = 0")
                    return
                parsed = parsed[0]

            story_list = parsed.get("story")
            analysis_list = parsed.get("analysis")
            if not isinstance(story_list, list):
                story_list = []
            if not isinstance(analysis_list, list):
                analysis_list = []
            if len(story_list) == 0 and len(analysis_list) == 0:
                messagebox.showerror("错误", "JSON 中 story 与 analysis 均为空或不存在，请确认格式正确")
                return
            generated_content[0] = {"story": story_list, "analysis": analysis_list}
            paste_dialog.destroy()

        btn_f = ttk.Frame(paste_dialog)
        btn_f.pack(fill=tk.X, pady=10)
        ttk.Button(btn_f, text="确认", command=on_paste_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="取消", command=paste_dialog.destroy).pack(side=tk.LEFT, padx=5)
        paste_dialog.wait_window()

        if generated_content[0] is None:
            return

        data = generated_content[0]

        def show_section_select_dialog(section_title, items):
            """显示一个区块的勾选对话框，返回用户勾选后的列表；取消则返回 None。"""
            if not items:
                return []
            select_dialog = tk.Toplevel(self.dialog)
            select_dialog.title(section_title)
            select_dialog.geometry("650x450")
            select_dialog.transient(self.dialog)
            select_dialog.grab_set()
            select_dialog.update_idletasks()
            x = (select_dialog.winfo_screenwidth() - 650) // 2
            y = (select_dialog.winfo_screenheight() - 450) // 2
            select_dialog.geometry(f"650x450+{x}+{y}")

            ttk.Label(select_dialog, text="勾选需要保留的参考项，然后点击确认", font=('TkDefaultFont', 10)).pack(anchor='w', padx=20, pady=(20, 5))
            canvas_frame = ttk.Frame(select_dialog)
            canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
            canvas = tk.Canvas(canvas_frame)
            scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
            scrollable = ttk.Frame(canvas)
            scrollable.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.create_window((0, 0), window=scrollable, anchor='nw')
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            vars_items = []
            for i, item in enumerate(items):
                cb_var = tk.BooleanVar(value=True)
                vars_items.append((cb_var, item))
                if isinstance(item, dict):
                    source = item.get("source_name", "") or ""
                    fpath = item.get("transcribed_file", "") or ""
                    fpath_tail = fpath[-36:] if len(fpath) > 36 else fpath
                    reason = item.get("reason", "") or ""
                    lines = []
                    if source:
                        lines.append(f"来源: {source}")
                    if fpath_tail:
                        lines.append(f"文件名: {fpath_tail}")
                    if reason:
                        lines.append(f"原因: {reason}")
                    display_text = "\n".join(lines) if lines else json.dumps(item, ensure_ascii=False)[:120] + ("..." if len(json.dumps(item, ensure_ascii=False)) > 120 else "")
                else:
                    display_text = json.dumps(item, ensure_ascii=False)[:120] + ("..." if len(json.dumps(item, ensure_ascii=False)) > 120 else "")
                row_f = ttk.Frame(scrollable)
                row_f.pack(fill=tk.X, pady=6)
                ttk.Checkbutton(row_f, variable=cb_var).pack(side=tk.LEFT, padx=(0, 8), anchor='n')
                ttk.Label(row_f, text=display_text, wraplength=520, justify='left').pack(side=tk.LEFT, fill=tk.X, expand=True)

            selected_result = [None]

            def on_confirm():
                selected_result[0] = [item for (cb_var, item) in vars_items if cb_var.get()]
                select_dialog.destroy()

            btn_f2 = ttk.Frame(select_dialog)
            btn_f2.pack(fill=tk.X, pady=10)
            ttk.Button(btn_f2, text="确认", command=on_confirm).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_f2, text="取消", command=select_dialog.destroy).pack(side=tk.LEFT, padx=5)
            select_dialog.wait_window()
            return selected_result[0]

        selected_story = show_section_select_dialog("勾选参考项：Story（故事/案例）", data.get("story", []))
        if selected_story is None:
            return
        selected_analysis = show_section_select_dialog("勾选参考项：Analysis（分析/理论）", data.get("analysis", []))
        if selected_analysis is None:
            return

        result = {"story": selected_story, "analysis": selected_analysis}
        self.reference_editor.delete('1.0', tk.END)
        self.reference_editor.insert('1.0', json.dumps(result, indent=2, ensure_ascii=False))

    def on_confirm(self):
        self.result_reference = self.reference_editor.get('1.0', tk.END).strip()
        self.dialog.destroy()

    def on_cancel(self):
        self.dialog.destroy()

    def show(self):
        self.dialog.wait_window()
        return self.result_reference


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
        self.llm_api = LLMApi()    
        
        # 默认项目配置选项
        # 从config.py获取可用的频道列表
        available_channels = list(config_channel.CHANNEL_CONFIG.keys())
        default_channel = available_channels[0] if available_channels else 'default'
        
        self.default_project_config = {
            'languages': ['tw', 'zh', 'en'],
            'default_language': 'tw',
            'channels': available_channels,
            'default_channel': default_channel,
            'default_title': '新项目',
            'default_video_width': '1920',
            'default_video_height': '1080'
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
        new_project_dialog.geometry("1000x600")
        new_project_dialog.transient(self.dialog)
        new_project_dialog.grab_set()
        
        # 居中显示
        new_project_dialog.update_idletasks()
        x = (new_project_dialog.winfo_screenwidth() - 1000) // 2
        y = (new_project_dialog.winfo_screenheight() - 600) // 2
        new_project_dialog.geometry(f"1000x600+{x}+{y}")
        
        main_frame = ttk.Frame(new_project_dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        row = 0
        
        # PID输入
        ttk.Label(main_frame, text="项目ID (PID):").grid(row=row, column=0, sticky='w', pady=5)
        pid_entry = ttk.Entry(main_frame, width=80)
        pid_entry.grid(row=row, column=1, padx=(10, 0), pady=5)
        # 自动生成默认PID
        auto_pid = f"p{datetime.now().strftime('%Y%m%d%H%M')}"
        pid_entry.insert(0, auto_pid)
        row += 1
        
        # 语言选择
        ttk.Label(main_frame, text="语言:").grid(row=row, column=0, sticky='w', pady=5)
        language_combo = ttk.Combobox(main_frame, values=self.default_project_config['languages'], state="readonly", width=80)
        language_combo.grid(row=row, column=1, padx=(10, 0), pady=5)
        language_combo.set(self.default_project_config['default_language'])
        row += 1
        
        # 频道选择
        ttk.Label(main_frame, text="频道:").grid(row=row, column=0, sticky='w', pady=5)
        channel_combo = ttk.Combobox(main_frame, values=self.default_project_config['channels'], state="readonly", width=80)
        channel_combo.grid(row=row, column=1, padx=(10, 0), pady=5)
        channel_combo.set(self.default_project_config['default_channel'])
        row += 1
        
        # 主题分类选择（两级：category 和 subtype，各单选）
        topics_data = []  # 存储完整的 topics.json 数据
        
        ttk.Label(main_frame, text="主题分类:").grid(row=row, column=0, sticky='w', pady=5)
        topic_category_combo = ttk.Combobox(main_frame, values=[], state="readonly", width=80)
        topic_category_combo.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        row += 1
        
        ttk.Label(main_frame, text="主题子类型:").grid(row=row, column=0, sticky='w', pady=5)
        topic_subtype_combo = ttk.Combobox(main_frame, values=[], state="readonly", width=80)
        topic_subtype_combo.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        row += 1
        
        # 显示说明文本的标签（支持多行）
        topic_explanation_label = ttk.Label(main_frame, text="", foreground="gray", wraplength=700, justify='left')
        topic_explanation_label.grid(row=row, column=1, columnspan=2, padx=(10, 0), pady=5, sticky='nw')
        row += 1
        
        # 更新主题子类型选项的函数（根据选择的 category）
        def update_topic_subtype(*args):
            selected_category = topic_category_combo.get()
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
        
        # 更新说明文本的函数（显示 topic_core_question 和 sample_topic）
        def update_explanation(*args):
            selected_category = topic_category_combo.get()
            
            if selected_category and topics_data:
                for topic in topics_data:
                    if topic.get('topic_category') == selected_category:
                        core_q = topic.get('topic_core_question', '')
                        sample = topic.get('sample_topic', '')
                        parts = []
                        if core_q:
                            parts.append(f"核心问题: {core_q}")
                        if sample:
                            parts.append(f"示例: {sample}")
                        if parts:
                            topic_explanation_label.config(text="\n".join(parts), foreground="gray")
                        else:
                            topic_explanation_label.config(text="")
                        break
                else:
                    topic_explanation_label.config(text="")
            else:
                topic_explanation_label.config(text="")
        
        # 绑定事件在下方内容区域统一设置（含 update_buttons_state）

        # 加载主题分类选项的函数（从 topics.json）
        def update_topic_choices(*args):
            channel = channel_combo.get()
            topics_data.clear()  # 清空旧数据
            topic_category_combo.set('')  # 清空选择
            topic_category_combo['values'] = []
            topic_subtype_combo.set('')
            topic_subtype_combo['values'] = []
            topic_explanation_label.config(text="")
            
            if channel:
                channel_path = config.get_channel_path(channel)
                loaded_choices, loaded_categories = config.load_topics(channel_path)
                topics_data.extend(loaded_choices)
                topic_category_combo['values'] = sorted(loaded_categories)
            # 频道切换后需更新编辑按钮状态
            try:
                update_buttons_state()
            except NameError:
                pass  # 初次加载时 update_buttons_state 尚未定义

        # 绑定频道改变事件
        channel_combo.bind('<<ComboboxSelected>>', update_topic_choices)
        # 初始化加载主题分类
        update_topic_choices()
        
        # 标题
        ttk.Label(main_frame, text="标题:").grid(row=row, column=0, sticky='w', pady=5)
        title_entry = ttk.Entry(main_frame, width=80)
        title_entry.grid(row=row, column=1, padx=(10, 0), pady=5)
        title_entry.insert(0, self.default_project_config['default_title'])
        row += 1
        
        # 视频分辨率选择
        ttk.Label(main_frame, text="视频分辨率:").grid(row=row, column=0, sticky='w', pady=5)
        resolution_frame = ttk.Frame(main_frame)
        resolution_frame.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        
        resolution_var = tk.StringVar(value="1080x1920")  # 默认横向
        ttk.Radiobutton(resolution_frame, text="1920x1080 (横向)", variable=resolution_var, value="1920x1080").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(resolution_frame, text="1080x1920 (纵向)", variable=resolution_var, value="1080x1920").pack(side=tk.LEFT)
        row += 1

        # 内容编辑区域：分析内容 | Story 内容 | 参考内容（三列并排）
        content_panels_frame = ttk.Frame(main_frame)
        content_panels_frame.grid(row=row, column=0, columnspan=2, sticky='ew', padx=5, pady=10)
        content_panels_frame.columnconfigure(0, weight=1)
        content_panels_frame.columnconfigure(1, weight=1)
        content_panels_frame.columnconfigure(2, weight=1)
        row += 1

        story_var = tk.StringVar(value="")
        analysis_var = tk.StringVar(value="")
        reference_var = tk.StringVar(value="")

        # 第二列：Story 内容
        story_label_frame = ttk.LabelFrame(content_panels_frame, text="Story 内容", padding=10)
        story_label_frame.grid(row=0, column=0, padx=5, sticky='nsew')
        story_preview = ttk.Label(story_label_frame, text="Story: (未编辑)", foreground="gray", wraplength=200)
        story_preview.pack(anchor='w', pady=(0, 10))
        edit_story_btn = ttk.Button(story_label_frame, text="故事起始", command=lambda: None)
        edit_story_btn.pack(pady=5)

        # 第三列：参考内容
        reference_label_frame = ttk.LabelFrame(content_panels_frame, text="参考内容", padding=10)
        reference_label_frame.grid(row=0, column=1, padx=(5, 0), sticky='nsew')
        reference_preview = ttk.Label(reference_label_frame, text="References: (未编辑)", foreground="gray", wraplength=200)
        reference_preview.pack(anchor='w', pady=(0, 10))
        edit_reference_btn = ttk.Button(reference_label_frame, text="参考收集", command=lambda: None)
        edit_reference_btn.pack(pady=5)

        # 第一列：分析内容
        analysis_label_frame = ttk.LabelFrame(content_panels_frame, text="分析内容", padding=10)
        analysis_label_frame.grid(row=0, column=2, padx=(0, 5), sticky='nsew')
        analysis_preview = ttk.Label(analysis_label_frame, text="Analysis: (未编辑)", foreground="gray", wraplength=200)
        analysis_preview.pack(anchor='w', pady=(0, 10))
        edit_analysis_btn = ttk.Button(analysis_label_frame, text="完成编辑", command=lambda: None)
        edit_analysis_btn.pack(pady=5)


        # 更新预览显示
        def update_previews():
            story_val = story_var.get()
            if story_val:
                preview_text = story_val[:50] + "..." if len(story_val) > 50 else story_val
                story_preview.config(text=f"Story: {preview_text}", foreground="black")
            else:
                story_preview.config(text="Story: (未编辑)", foreground="gray")

            analysis_val = analysis_var.get()
            if analysis_val:
                preview_text = analysis_val[:50] + "..." if len(analysis_val) > 50 else analysis_val
                analysis_preview.config(text=f"Analysis: {preview_text}", foreground="black")
            else:
                analysis_preview.config(text="Analysis: (未编辑)", foreground="gray")

            reference_val = reference_var.get()
            if reference_val:
                preview_text = reference_val[:50] + "..." if len(reference_val) > 50 else reference_val
                reference_preview.config(text=f"References: {preview_text}", foreground="black")
            else:
                reference_preview.config(text="References: (未编辑)", foreground="gray")

        _editor_open = [False]  # 用 list 以便在闭包中修改；同一时刻只允许打开一个编辑器

        # 根据 topic 与 story 状态启用/禁用编辑按钮
        def update_buttons_state(*args):
            has_topic = bool(topic_category_combo.get().strip() and topic_subtype_combo.get().strip())
            has_story = bool(story_var.get().strip())
            editor_busy = _editor_open[0]
            edit_story_btn.config(state='normal' if has_topic and not editor_busy else 'disabled')
            # Analysis、参考 仅在已有 Story 内容时可编辑
            can_edit_derived = has_topic and has_story and not editor_busy
            edit_analysis_btn.config(state='normal' if can_edit_derived else 'disabled')
            edit_reference_btn.config(state='normal' if can_edit_derived else 'disabled')

        story_var.trace_add('write', lambda *args: (update_previews(), update_buttons_state()))
        analysis_var.trace_add('write', lambda *args: update_previews())
        reference_var.trace_add('write', lambda *args: update_previews())

        def on_topic_category_selected(e):
            update_topic_subtype()
            update_explanation()
            update_buttons_state()

        def on_topic_subtype_selected(e):
            update_explanation()
            update_buttons_state()

        topic_category_combo.bind('<<ComboboxSelected>>', on_topic_category_selected)
        topic_subtype_combo.bind('<<ComboboxSelected>>', on_topic_subtype_selected)

        def open_story_editor():
            _editor_open[0] = True
            update_buttons_state()
            try:
                editor = ContentEditorDialog(
                    new_project_dialog,
                    language_combo.get(),
                    channel_combo.get(),
                    story_var.get()
                )
                result = editor.show()
                if result:
                    obj = parse_json_from_text(result) if isinstance(result, str) else result
                    if isinstance(obj, dict):
                        name = obj.pop('story_name', '')
                        if name:
                            title_entry.delete(0, tk.END)
                            title_entry.insert(0, name)
                        category = obj.pop('topic_category', '')
                        if category:
                            topic_category_combo.set(category)
                        subtype = obj.pop('topic_subtype', '')
                        if subtype:
                            topic_subtype_combo.set(subtype)

                        obj.pop('problem_tags', '')
                        obj.pop('component_tags', '')
                        story_var.set(obj.get('story', ''))
                    else:
                        story_var.set(result)
            finally:
                _editor_open[0] = False
                update_buttons_state()

        def open_analysis_editor():
            _editor_open[0] = True
            update_buttons_state()

            try:
                # Analysis Editor (edit comprehensive_analysis)
                editor_analysis = AnalysisEditorDialog(
                    new_project_dialog,
                    initial_analysis=analysis_var.get(),
                    story_content=story_var.get(),
                    reference_content=reference_var.get(),
                    language=language_combo.get(),
                    channel=channel_combo.get()
                )
                res_analysis = editor_analysis.show()
                if res_analysis:
                    analysis_var.set(res_analysis)
            finally:
                _editor_open[0] = False
                update_buttons_state()

        def open_reference_editor():
            _editor_open[0] = True
            update_buttons_state()
            try:
                editor = ReferenceEditorDialog(
                    new_project_dialog,
                    initial_reference=reference_var.get(),
                    story_content=story_var.get(),
                    topic_category=topic_category_combo.get().strip(),
                    topic_subtype=topic_subtype_combo.get().strip()
                )
                result = editor.show()
                # get json from result
                result_json = parse_json_from_text(result) if isinstance(result, str) else result
                story_list = result_json.get('story', [])
                # for each item in story_list, get transcribed_file, source_name, reason
                for item in story_list:
                    fpath = item.pop('transcribed_file', '')
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            item['content'] = config.extract_text_from_srt_content(f.read())
                        item['name'] = fpath[-36:] if len(fpath) > 36 else fpath
                    except Exception as e:
                        item['content'] = None
                # filter out None  content item in story_list        
                story_list = [item for item in story_list if item['content'] is not None]

                analysis_list = result_json.get('analysis', [])
                for item in analysis_list:
                    fpath = item.pop('transcribed_file', '')
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            item['content'] = config.extract_text_from_srt_content(f.read())
                        item['name'] = fpath[-36:] if len(fpath) > 36 else fpath
                    except Exception as e:
                        item['content'] = None
                # filter out None  content item in analysis_list
                analysis_list = [item for item in analysis_list if item['content'] is not None]

                result_json['story'] = story_list
                result_json['analysis'] = analysis_list

                reference_var.set(json.dumps(result_json, indent=2, ensure_ascii=False))
            finally:
                _editor_open[0] = False
                update_buttons_state()

        edit_story_btn.config(command=open_story_editor)
        edit_reference_btn.config(command=open_reference_editor)
        edit_analysis_btn.config(command=open_analysis_editor)

        # 初始状态：按钮禁用（topic 未选时）
        update_buttons_state()
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)
        
        def on_create():
            pid = pid_entry.get().strip()
            language = language_combo.get()
            channel = channel_combo.get()
            title = title_entry.get().strip()
            resolution = resolution_var.get()
            topic_category = topic_category_combo.get().strip()
            topic_subtype = topic_subtype_combo.get().strip()
            
            if not pid:
                messagebox.showerror("错误", "请输入项目ID")
                return
            if not title:
                messagebox.showerror("错误", "请输入标题")
                return
            
            # 检查 story 和 kernel 是否已生成
            story_content = story_var.get().strip()
            
            if not story_content:
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
                
            # 创建新项目配置
            self.selected_config = {
                'pid': pid,
                'language': language,
                'channel': channel,
                'video_title': title,
                'video_width': video_width,
                'video_height': video_height,
                **self.default_project_config.get('additional_fields', {}),
                'story_details': [ 
                    { 
                        'name': 'story', 
                        'topic_category': topic_category,
                        'topic_subtype': topic_subtype,
                        'story_details': story_var.get()
                    }, 
                    { 
                        'name': 'analysis', 
                        'topic_category': topic_category, 
                        'topic_subtype': topic_subtype, 
                        'story_details': analysis_var.get()
                    },
                    { 
                        'name': 'reference', 
                        'topic_category': topic_category, 
                        'topic_subtype': topic_subtype, 
                        'story_details': reference_var.get()
                    }
                ]
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

