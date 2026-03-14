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
from config import parse_json_from_text
import config_channel
from utility.llm_api import LLMApi, LM_STUDIO
from utility.file_util import safe_copy_overwrite, safe_remove
from config import LANGUAGES
from gui.downloader import MediaGUIManager



PROJECT_CONFIG = None



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



class ProgramInitEditorDialog:
    
    def __init__(self, parent, reference_story):
        self.parent = parent
        self.init_story = reference_story
        # 初始化LLM API
        self.llm_api = LLMApi()
        self.llm_api_local = LLMApi(LM_STUDIO)
        
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
        self.story_editor.insert('1.0', self.init_story.get('raw_content', ''))

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
        topic = self.init_story.get('topic_category','') + " - " + self.init_story.get('topic_subtype','')
        user_prompt = f"On topic of {topic}, the initial story script is : \n{self.init_story.get('raw_content','')}\n\n\n\
                      And the core-insight ('soul') is: \n{self.init_story.get('soul', '')}\n\n\n\
                      And the reference stories are: \n{self.init_story.get('reference_content',{}).get('story','')}"
        system_prompt = config_channel.CHANNEL_CONFIG[self.init_story['channel']]['channel_prompt'].get('prompt_story_init', '')
        system_prompt = system_prompt.format(language=LANGUAGES[self.init_story['language']], topic=topic)
        # 调用LLM生成内容
        generated_content = self.llm_api.generate_text(system_prompt, user_prompt)

        self.story_editor.config(state=tk.NORMAL)
        self.story_editor.delete('1.0', tk.END)
        self.story_editor.insert('1.0', generated_content)
        self.init_story['init_content'] = generated_content


    def on_cancel(self):
        self.init_story['init_content'] = self.story_editor.get('1.0', tk.END).strip()
        self.dialog.destroy()
    

    def show(self):
        """显示对话框并返回结果"""
        self.dialog.wait_window()
        return self.init_story['init_content']



class DebutEditorDialog:
    """分析内容编辑器 - 使用 INIT 内容调用 LLM 生成分析"""

    def __init__(self, parent, init_story):
        self.parent = parent
        self.debut_story = init_story
        #self.story_content = story_content
        #self.reference_content = reference_content
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
        init_text = self.debut_story.get('init_content') or self.debut_story.get('raw_content') or ''
        self.analysis_editor.insert('1.0', init_text)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="确定", command=self.on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_cancel).pack(side=tk.LEFT, padx=5)


    def on_ok(self):
        """使用 INIT 或 RAW 内容调用 LLM 生成分析（可不等 INIT 完成，用 raw_content 作为 K-Story）"""
        if not self.llm_api:
            messagebox.showerror("错误", "LLM API 未初始化")
            return

        k_story = self.debut_story.get('init_content')
        if not k_story:
            messagebox.showerror("错误", "请先完成 RAW 或 INIT 内容，再生成分析")
            return

        topic = self.debut_story['topic_category'] + " - " + self.debut_story['topic_subtype']
        ref_analysis = self.debut_story.get('reference_content').get('analysis', [])

        user_prompt = f"On topic of {topic}, the K-Story: \n{k_story}\n\n\n\
                        And the reference analysises are: \n{ref_analysis}\n\n\n\
                        And the core-insight ('soul') is: \n{self.debut_story.get('soul')}"

        system_prompt = config_channel.CHANNEL_CONFIG[self.debut_story['channel']]['channel_prompt'].get('prompt_program_debut', '')
        system_prompt = system_prompt.format(
            language=LANGUAGES.get(self.debut_story['language']),
            topic=topic
        )

        generated = self.llm_api.generate_text(system_prompt, user_prompt)
        self.analysis_editor.config(state=tk.NORMAL)
        self.analysis_editor.delete('1.0', tk.END)
        self.analysis_editor.insert('1.0', generated)
        self.debut_story['debut_content'] = generated

        self.dialog.destroy()


    def on_cancel(self):
        self.debut_story['debut_content'] = self.analysis_editor.get('1.0', tk.END).strip()
        self.dialog.destroy()

    def show(self):
        """显示对话框并返回结果"""
        self.dialog.wait_window()
        return self.debut_story['debut_content']



class ReferenceEditorDialog:
    """参考内容编辑器 - 基于 Story 分析的参考案例与素材（搜索/生成逻辑待后续集成）"""

    def __init__(self, parent, init_story, reference_filter):
        self.parent = parent
        self.reference_story = init_story
        self.reference_filter = reference_filter
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
        self.reference_editor.insert('1.0', self.reference_story['raw_content'])
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
        if not self.reference_story['raw_content'] or not self.reference_story['raw_content'].strip():
            messagebox.showerror("错误", "请先完成 RAW 内容，再获取参考")
            return

        try:
            self.dialog.clipboard_clear()
            self.dialog.clipboard_append(self.reference_filter  + "\n---------\n" + self.reference_story['raw_content'])
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
            clipboard_content = paste_dialog.clipboard_get()
            paste_text.insert(tk.INSERT, clipboard_content)

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
        self.reference_story['reference_content'] = result

    #  result format is like this:
    #{
    #    "story": [
    #        {
    #            "content": "the content of the story",
    #            "transcribed_file": "file name of the transcribed_file",
    #            "source_name": "the name of source which give the transcribed_file"
    #            "reason": "Explanation of relevance"
    #        }
    #    ]
    #    "analysis": [
    #        {
    #            "content": "the content of the analysis",
    #            "transcribed_file": "file name of the transcribed_file",
    #            "source_name": "the name of source which give the transcribed_file"
    #            "reason": "Explanation of relevance"
    #        }
    #    ]
    #}
    #
    #  based on the reference result, you can compose a 'Case-Story' and a 'Analysis' for the 'the reference content for the story and analysis, which is used to generate the story and analysis.
    #
        self.reference_editor.delete('1.0', tk.END)
        self.reference_editor.insert('1.0', json.dumps(result, indent=2, ensure_ascii=False))


    def on_confirm(self):
        self.dialog.destroy()

    def on_cancel(self):
        self.dialog.destroy()

    def show(self):
        self.dialog.wait_window()
        return self.reference_story.get('reference_content', {'story': [], 'analysis': []})




class ProjectSelectionDialog:
    """项目选择对话框 - 可重用的项目选择界面"""
    
    def __init__(self, parent, config_manager, youtube_gui=None, create_only=False, selection_only=False, initial_channel=None, initial_language=None, initial_raw_content=None):
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
        if not channel or not topic_category or not topics_data:
            return None
        category_soul = ''
        subtype_soul = ''
        channel_path = config.get_channel_path(channel)
        for topic in topics_data:
            if topic.get('topic_category') == topic_category:
                cs = topic.get('soul', '')
                try:
                    fp = os.path.join(channel_path, cs)
                    if os.path.isfile(fp):
                        with open(fp, 'r', encoding='utf-8') as f:
                            category_soul = f.read()
                    else:
                        category_soul = cs if cs else ''
                except (OSError, TypeError):
                    category_soul = cs if isinstance(cs, str) else ''
                if topic_subtype:
                    for st in topic.get('topic_subtypes', []):
                        if isinstance(st, dict) and st.get('topic_subtype') == topic_subtype:
                            ss = st.get('soul', '')
                            try:
                                fp = os.path.join(channel_path, ss)
                                if os.path.isfile(fp):
                                    with open(fp, 'r', encoding='utf-8') as f:
                                        subtype_soul = f.read()
                                else:
                                    subtype_soul = ss if ss else ''
                            except (OSError, TypeError):
                                subtype_soul = ss if isinstance(ss, str) else ''
                            break
                break
        parts = [p for p in (category_soul, subtype_soul) if p]
        return ' | '.join(parts) if parts else None

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
        if not selection_only:
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
        # 创建新项目配置对话框；create_only 时父窗口须为可见的 parent，否则会白屏
        form_parent = getattr(self, '_form_parent', self.dialog)
        new_project_dialog = tk.Toplevel(form_parent)
        new_project_dialog.title("创建新项目")
        new_project_dialog.geometry("1600x1000")
        new_project_dialog.transient(form_parent)
        new_project_dialog.grab_set()
        
        # 居中显示
        new_project_dialog.update_idletasks()
        x = (new_project_dialog.winfo_screenwidth() - 1600) // 2
        y = (new_project_dialog.winfo_screenheight() - 1000) // 2
        new_project_dialog.geometry(f"1600x1000+{x}+{y}")
        
        main_frame = ttk.Frame(new_project_dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(1, weight=1)

        row = 0
        
        # PID输入
        ttk.Label(main_frame, text="项目ID (PID):").grid(row=row, column=0, sticky='w', pady=5)
        pid_entry = ttk.Entry(main_frame, width=80)
        pid_entry.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        # 自动生成默认PID
        auto_pid = f"p{datetime.now().strftime('%Y%m%d%H%M')}"
        pid_entry.insert(0, auto_pid)
        row += 1
        
        # 频道、语言已从首层选择框传入，显示为只读（不可在此修改）
        ttk.Label(main_frame, text="频道:").grid(row=row, column=0, sticky='w', pady=5)
        ttk.Label(main_frame, text=self.story_result['channel'], foreground="gray").grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        row += 1
        ttk.Label(main_frame, text="语言:").grid(row=row, column=0, sticky='w', pady=5)
        ttk.Label(main_frame, text=self.story_result['language'], foreground="gray").grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        row += 1

        def sync_channel_template(*args):
            """频道变更时同步单一 channel_template 到 story_result"""
            templates_list, _ = config_channel.get_channel_templates(self.story_result['channel'])
            self.story_result['channel_template'] = templates_list[0] if templates_list else None

        sync_channel_template()

        # 主题分类选择（两级：category 和 subtype，各单选）
        topics_data = []  # 存储完整的 topics.json 数据
        tag_choices_data = []  # 存储 tags.json 数据 [{tag_type, tags}, ...]
        
        ttk.Label(main_frame, text="主题分类:").grid(row=row, column=0, sticky='w', pady=5)
        topic_category_combo = ttk.Combobox(main_frame, values=[], state="readonly", width=80)
        topic_category_combo.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        row += 1
        
        ttk.Label(main_frame, text="主题子类型:").grid(row=row, column=0, sticky='w', pady=5)
        topic_subtype_combo = ttk.Combobox(main_frame, values=[], state="readonly", width=80)
        topic_subtype_combo.grid(row=row, column=1, padx=(10, 0), pady=5, sticky='w')
        row += 1
        
        # 主题标签显示（可编辑，支持 a,b, GENRE=Jazz 格式，单选变更会同步至此）
        ttk.Label(main_frame, text="主题标签 (可编辑):").grid(row=row, column=0, sticky='nw', padx=10, pady=5)
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
        
        # 主题标签选择（根据 tags.json，每个 tag_type 选一个值）
        tag_tags_frame = ttk.LabelFrame(main_frame, text="主题标签 (选填)", padding=5)
        tag_tags_frame.grid(row=row, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
        main_frame.columnconfigure(1, weight=1)
        tag_tags_inner = ttk.Frame(tag_tags_frame)
        tag_tags_inner.pack(fill=tk.X, expand=True)
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

        def sync_tags_from_ui(*args):
            """合并：从 tags_entry 读取分析部分 + 多选选择（值用/连接），更新 tags_entry 与 story_result"""
            analysis_tags, _ = _parse_tags_entry_text(tags_var.get())
            manual_selected = []
            for tag_type, check_vars in tag_combo_refs:
                vals = [v for v, cb_var in check_vars if cb_var.get()]
                if vals:
                    manual_selected.append(f"{tag_type}={'/'.join(vals)}")
            combined = analysis_tags + manual_selected
            tags_var.set(', '.join(combined))
            self.story_result['tags'] = combined if combined else None

        def _on_tags_entry_change(*args):
            """用户手动编辑 tags 时同步到 story_result"""
            combined = [t.strip() for t in re.split(r'[|,]', tags_var.get() or '') if t.strip()]
            self.story_result['tags'] = combined if combined else None

        tags_var.trace_add('write', _on_tags_entry_change)

        tag_combo_refs = []  # 存储 (tag_type, [(val, BooleanVar), ...]) 多选用

        def update_tag_selectors(*args):
            """根据 tag_choices_data 更新标签选择 UI（loaded_tags 即 name=value 结构），多选用 Checkbutton，值用/连接"""
            for w in tag_tags_inner.winfo_children():
                w.destroy()
            tag_combo_refs.clear()
            if not tag_choices_data:
                ttk.Label(tag_tags_inner, text="当前频道无可选标签", foreground="gray").pack(anchor='w')
                self.story_result['tags'] = _tags_analysis_part(self.story_result.get('tags')) or None
                tags_var.set(', '.join(self.story_result['tags'] or []))
                return
            existing_manual = {t.split('=', 1)[0]: t.split('=', 1)[-1] for t in _tags_manual_part(self.story_result.get('tags'))}
            for tag_item in tag_choices_data:
                if not isinstance(tag_item, dict):
                    continue
                tag_type = tag_item.get('tag_type', '')
                tags_list = tag_item.get('tags') or []
                if not tags_list:
                    continue
                r = ttk.LabelFrame(tag_tags_inner, text=f"{tag_type}:", padding=5)
                r.pack(fill=tk.X, pady=5)
                existing_vals = existing_manual.get(tag_type, '').split('/') if existing_manual.get(tag_type) else []
                existing_set = {v.strip() for v in existing_vals if v.strip()}
                check_vars = []
                inner = ttk.Frame(r)
                inner.pack(fill=tk.X, expand=True)
                n_cols = 10  # 更多列以充分利用横向空间
                for col_idx, val in enumerate(sorted(tags_list)):
                    row_idx, col = col_idx // n_cols, col_idx % n_cols
                    cb_var = tk.BooleanVar(value=val in existing_set)
                    cb = ttk.Checkbutton(inner, text=val, variable=cb_var, command=sync_tags_from_ui)
                    cb.grid(row=row_idx, column=col, sticky='w', padx=(0, 8), pady=1)
                    check_vars.append((val, cb_var))
                for c in range(n_cols):
                    inner.columnconfigure(c, weight=1)  # 列均匀扩张填满可用宽度
                tag_combo_refs.append((tag_type, check_vars))
            sync_tags_from_ui()
        
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
            update_tag_selectors()
        
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
                channel_path = config.get_channel_path(self.story_result['channel'])
                loaded_choices, loaded_categories, loaded_tags = config.load_topics(channel_path)
                topics_data.extend(loaded_choices)
                tag_choices_data.extend(loaded_tags)
                topic_category_combo['values'] = sorted(loaded_categories)
            # 频道切换后需更新编辑按钮状态
            try:
                update_buttons_state()
            except NameError:
                pass  # 初次加载时 update_buttons_state 尚未定义
            try:
                update_tag_selectors()
            except NameError:
                pass

        # 频道/语言已从首层传入，无需绑定变更事件；初始化加载主题分类与模板
        update_topic_choices()
        sync_channel_template()
        
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

        # 内容编辑区域：RAW | INIT | 参考 | DEBUT（四列并排）
        content_panels_frame = ttk.Frame(main_frame)
        content_panels_frame.grid(row=row, column=0, columnspan=2, sticky='ew', padx=5, pady=10)
        content_panels_frame.columnconfigure(0, weight=1)
        content_panels_frame.columnconfigure(1, weight=1)
        content_panels_frame.columnconfigure(2, weight=1)
        content_panels_frame.columnconfigure(3, weight=1)
        row += 1

        reference_content_var = tk.StringVar(value="")

        # 第三列：参考内容
        reference_label_frame = ttk.LabelFrame(content_panels_frame, text="参考内容", padding=10)
        reference_label_frame.grid(row=0, column=0, padx=(5, 0), sticky='nsew')
        reference_preview = ttk.Label(reference_label_frame, text="REF: (未编辑)", foreground="gray", wraplength=200)
        reference_preview.pack(anchor='w', pady=(0, 10))
        edit_reference_btn = ttk.Button(reference_label_frame, text="参考收集", command=lambda: None)
        edit_reference_btn.pack(pady=5)

        # 第一列：RAW 内容（需先选 topic）
        raw_label_frame = ttk.LabelFrame(content_panels_frame, text="RAW内容", padding=10)
        raw_label_frame.grid(row=0, column=1, padx=5, sticky='nsew')
        raw_preview = ttk.Label(raw_label_frame, text="RAW: (未生成)", foreground="gray", wraplength=200)
        raw_preview.pack(anchor='w', pady=(0, 10))
        edit_raw_btn = ttk.Button(raw_label_frame, text="RAW内容", command=lambda: None)
        edit_raw_btn.pack(pady=5)

        # 第二列：INIT 内容
        story_label_frame = ttk.LabelFrame(content_panels_frame, text="INIT内容", padding=10)
        story_label_frame.grid(row=0, column=2, padx=5, sticky='nsew')
        init_preview = ttk.Label(story_label_frame, text="INIT: (未编辑)", foreground="gray", wraplength=200)
        init_preview.pack(anchor='w', pady=(0, 10))
        edit_init_btn = ttk.Button(story_label_frame, text="INIT编辑", command=lambda: None)
        edit_init_btn.pack(pady=5)

        # 第四列：DEBUT 内容
        debut_label_frame = ttk.LabelFrame(content_panels_frame, text="DEBUT内容", padding=10)
        debut_label_frame.grid(row=0, column=3, padx=(0, 5), sticky='nsew')
        debut_preview = ttk.Label(debut_label_frame, text="DEBUT: (未编辑)", foreground="gray", wraplength=200)
        debut_preview.pack(anchor='w', pady=(0, 10))
        edit_debut_btn = ttk.Button(debut_label_frame, text="DEBUT编辑", command=lambda: None)
        edit_debut_btn.pack(pady=5)


        _editor_open = [False]  # 用 list 以便在闭包中修改；同一时刻只允许打开一个编辑器

        def update_previews():
            """根据 story_result 更新 RAW/INIT/REF/DEBUT 预览文本"""
            # RAW
            raw_str = (self.story_result.get('raw_content') or '').strip()
            if raw_str:
                preview = (raw_str[:40] + '…') if len(raw_str) > 40 else raw_str
                raw_preview.config(text=f"RAW: {preview}", foreground="black")
            else:
                raw_preview.config(text="RAW: (未生成)", foreground="gray")
            # INIT
            init_str = (self.story_result.get('init_content') or '').strip()
            if init_str:
                preview = (init_str[:40] + '…') if len(init_str) > 40 else init_str
                init_preview.config(text=f"INIT: {preview}", foreground="black")
            else:
                init_preview.config(text="INIT: (未编辑)", foreground="gray")
            # REF
            ref = self.story_result.get('reference_content')
            if isinstance(ref, dict) and (ref.get('story') or ref.get('analysis')):
                n_story = len(ref.get('story', []))
                n_analysis = len(ref.get('analysis', []))
                preview = f"{n_story}故事,{n_analysis}分析"
                reference_preview.config(text=f"REF: {preview}", foreground="black")
            else:
                reference_preview.config(text="REF: (未编辑)", foreground="gray")
            # DEBUT
            debut_str = (self.story_result.get('debut_content') or '').strip()
            if debut_str:
                preview = (debut_str[:40] + '…') if len(debut_str) > 40 else debut_str
                debut_preview.config(text=f"DEBUT: {preview}", foreground="black")
            else:
                debut_preview.config(text="DEBUT: (未编辑)", foreground="gray")

        # 根据 topic、raw、reference 状态启用/禁用编辑按钮
        def update_buttons_state(*args):
            has_topic = bool(self.story_result['topic_category'] and self.story_result['topic_subtype'])
            ref = self.story_result.get('reference_content')
            has_reference = isinstance(ref, dict) and (bool(ref.get('story')) or bool(ref.get('analysis')))
            # has raw content
            has_raw = bool(self.story_result.get('raw_content'))
            editor_busy = _editor_open[0]
            edit_raw_btn.config(state='normal' if has_topic and not editor_busy else 'disabled')
            # 参考收集：raw_content 不空 且 频道配置了 reference_filter
            edit_reference_btn.config(state='normal' if has_topic and has_raw and not editor_busy else 'disabled')
            # INIT编辑、DEBUT编辑：需参考收集完成（reference_content 不空），不必等 INIT 完成
            can_edit_after_ref = has_topic and has_reference and not editor_busy
            edit_init_btn.config(state='normal' if can_edit_after_ref else 'disabled')
            edit_debut_btn.config(state='normal' if can_edit_after_ref else 'disabled')


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
                topic_choices, _, _ = config.load_topics(config.get_channel_path(self.story_result['channel']))
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
            # 预填：优先用 initial_text，否则从 story_result 读取（如从 project config 加载或从 NotebookLM 传入）
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
            case_story_result = [None]
            use_directly_result = [False]
            def on_ok():
                case_story_result[0] = case_text.get('1.0', tk.END).strip()
                raw_dialog.destroy()
            def on_use_directly():
                """直接使用文本框内容作为 raw_content，不调 LLM"""
                txt = case_text.get('1.0', tk.END).strip()
                if not txt:
                    messagebox.showwarning("提示", "请输入或粘贴内容", parent=raw_dialog)
                    return
                use_directly_result[0] = True
                case_story_result[0] = txt
                raw_dialog.destroy()
            def on_cancel():
                raw_dialog.destroy()
            btn_f = ttk.Frame(frame)
            btn_f.pack(fill=tk.X, pady=(10, 0))
            if _prefill:
                ttk.Button(btn_f, text="直接使用", command=on_use_directly).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_f, text="确定", command=on_ok).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_f, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
            raw_dialog.wait_window()
            if case_story_result[0] is None or not case_story_result[0]:
                return
            raw_input = case_story_result[0]
            if use_directly_result[0]:
                self.story_result['raw_content'] = raw_input
                update_buttons_state()
                #topic_choices, _, _ = config.load_topics(config.get_channel_path(self.story_result['channel']))
                #category_result = self.llm_api_local.generate_json(
                #    config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(
                #        language=LANGUAGES.get(self.story_result['language'], self.story_result['language']),
                #        topic_choices=topic_choices
                #    ),
                #    raw_input,
                #    expect_list=False
                #)
                #_apply_category_result_to_ui(category_result, raw_preview)
                #update_buttons_state()
                return

            raw_story_system_prompt = config_channel.CHANNEL_CONFIG[self.story_result['channel']]['channel_prompt'].get('prompt_program_raw', '')
            raw_story_system_prompt = raw_story_system_prompt.format( language=LANGUAGES.get(self.story_result['language'], self.story_result['language']), topic=self.story_result['topic_category'] + "|" + self.story_result['topic_subtype'] )

            self.story_result['raw_content'] = self.llm_api.generate_text(raw_story_system_prompt, case_story_result[0])
            # raw_content 就绪后立即刷新按钮状态（参考收集应立即可用）
            update_buttons_state()

            topic_choices, topic_categories, _ = config.load_topics(config.get_channel_path(self.story_result['channel']))

            category_result = self.llm_api_local.generate_json(
                config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(language=LANGUAGES.get(self.story_result['language'], self.story_result['language']), topic_choices=topic_choices),
                self.story_result['raw_content'],
                expect_list=False
            )
            if category_result:
                cat = category_result.get('topic_category')
                sub = category_result.get('topic_subtype')
                if cat and sub:
                    self.story_result['topic_category'] = cat
                    topic_category_combo.set(cat)
                    update_topic_subtype()
                    self.story_result['topic_subtype'] = sub
                    topic_subtype_combo.set(sub)

                    self.story_result['soul'] = self.build_soul(self.story_result['channel'], self.story_result['topic_category'], self.story_result['topic_subtype'], topic_choices)
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

                preview = (story_str[:40] + '…') if len(story_str) > 40 else story_str
                raw_preview.config(text=f"RAW: {preview}", foreground="black")
        # RAW 生成后刷新按钮状态（参考收集、DEBUT 等需 raw_content 不为空）
        update_buttons_state()

        edit_raw_btn.config(command=lambda: open_raw_editor())

        # 若有预设 RAW（如从 NotebookLM Story 启动），预填并自动打开 RAW 编辑器
        _init_raw = getattr(self, 'initial_raw_content', None)
        if _init_raw and _init_raw.strip():
            self.story_result['raw_content'] = _init_raw.strip()
            update_previews()  # RAW 面板显示传入的内容
            update_buttons_state()
            try:
                topic_choices, _, _ = config.load_topics(config.get_channel_path(self.story_result['channel']))
                category_result = self.llm_api_local.generate_json(
                    config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(
                        language=LANGUAGES.get(self.story_result['language'], self.story_result['language']),
                        topic_choices=topic_choices
                    ),
                    _init_raw.strip(),
                    expect_list=False
                )
                _apply_category_result_to_ui(category_result, raw_preview)
            except Exception:
                pass
            update_buttons_state()
            new_project_dialog.after(300, lambda: open_raw_editor(initial_text=_init_raw.strip()))


        def open_init_editor():
            _editor_open[0] = True
            update_buttons_state()
            try:
                editor = ProgramInitEditorDialog(
                    parent=new_project_dialog,
                    reference_story=self.story_result
                )
                self.story_result['init_content'] = editor.show()
                update_previews()
            finally:
                _editor_open[0] = False
                update_buttons_state()


        def open_debut_editor():
            _editor_open[0] = True
            update_buttons_state()

            try:
                # Analysis Editor (edit comprehensive_analysis)
                editor_debut = DebutEditorDialog(
                    new_project_dialog,
                    init_story=self.story_result
                )
                analysis = editor_debut.show()
                self.story_result['debut_content'] = analysis
                update_previews()
            finally:
                _editor_open[0] = False
                update_buttons_state()


        def open_reference_editor():
            _editor_open[0] = True
            update_buttons_state()
            try:
                reference_filter_prompt = config_channel.CHANNEL_CONFIG[self.story_result['channel']].get('channel_prompt', {}).get('prompt_reference_filter', '')
                reference_filter_prompt = reference_filter_prompt.format(topic=self.story_result['topic_category'] + " - " + self.story_result['topic_subtype'])

                editor = ReferenceEditorDialog(
                    new_project_dialog,
                    init_story=self.story_result,
                    reference_filter=reference_filter_prompt
                )

                result_json = editor.show()
                story_list = result_json.get('story', [])
                story_list = [item for item in story_list if item['content'] is not None]

                analysis_list = result_json.get('analysis', [])
                analysis_list = [item for item in analysis_list if item['content'] is not None]

                result_json['story'] = story_list
                result_json['analysis'] = analysis_list

                self.story_result['reference_content'] = result_json
                update_previews()
            finally:
                _editor_open[0] = False
                update_buttons_state()

        edit_reference_btn.config(command=open_reference_editor)

        edit_init_btn.config(command=open_init_editor)

        edit_debut_btn.config(command=open_debut_editor)

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
            if not self.story_result.get('debut_content', None):
                self.story_result['debut_content'] = ""

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

            self.story_result['action'] = 'new'

            self.story_result['prompts'] = config_channel.CHANNEL_CONFIG[self.story_result['channel']]['channel_prompt']

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
    """GUI 启动时首先显示的选择：频道、语言 + 创建新项目/选择项目/YT 操作"""
    result = {'choice': 'cancel', 'channel': '', 'language': ''}

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
    ttk.Label(opt_frame, text="频道：", font=('TkDefaultFont', 10)).pack(side=tk.LEFT, padx=(0, 5))
    channel_var = tk.StringVar(value=default_channel)
    channel_combo = ttk.Combobox(opt_frame, textvariable=channel_var, values=available_channels, state="readonly", width=18)
    channel_combo.pack(side=tk.LEFT, padx=(0, 15))
    ttk.Label(opt_frame, text="语言：", font=('TkDefaultFont', 10)).pack(side=tk.LEFT, padx=(0, 5))
    language_var = tk.StringVar(value=default_lang)
    language_combo = ttk.Combobox(opt_frame, textvariable=language_var, values=languages, state="readonly", width=10)
    language_combo.pack(side=tk.LEFT)

    ttk.Label(main_frame, text="请选择操作", font=('TkDefaultFont', 14, 'bold')).pack(pady=(0, 25))

    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(pady=15)

    def on_new():
        result['choice'] = 'new'
        result['channel'] = channel_var.get().strip()
        result['language'] = language_var.get().strip()
        dialog.destroy()

    def on_open():
        result['choice'] = 'open'
        result['channel'] = channel_var.get().strip()
        result['language'] = language_var.get().strip()
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
        channel_path = config.get_channel_path(ch)
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
    w, h = 450, 420
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    dialog.protocol("WM_DELETE_WINDOW", on_cancel)
    dialog.wait_window()
    return result['choice'], result['channel'] or default_channel, result['language'] or default_lang


def create_project_dialog(parent, youtube_gui=None):
    global PROJECT_CONFIG
    # 首先显示初始选择：频道、语言 + 创建新项目 / 选择项目 / YT
    choice, initial_channel, initial_language = show_initial_choice_dialog(parent)
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
            initial_channel=initial_channel, initial_language=initial_language
        )
        result = dialog.story_result.get('action', 'cancel')
        selected_config = dialog.selected_config
        if dialog.dialog.winfo_exists():
            dialog.dialog.destroy()
    else:
        # 选择项目：显示项目列表（不含「新建项目」按钮），传入 channel/language
        dialog = ProjectSelectionDialog(
            parent, config_manager, youtube_gui=youtube_gui, selection_only=True,
            initial_channel=initial_channel, initial_language=initial_language
        )
        result, selected_config = dialog.show()

    # 确保在返回前 PROJECT_CONFIG 仍然有效
    if PROJECT_CONFIG is None and selected_config is not None:
        PROJECT_CONFIG = selected_config.copy()
    return result, selected_config


def create_project_with_initial_raw(parent, raw_content, channel, language):
    """用现有 RAW 材料（如 NotebookLM Story）直接启动创建新项目，跳过初始选择"""
    global PROJECT_CONFIG
    if not raw_content or not raw_content.strip():
        return 'cancel', None
    config_manager = ProjectConfigManager()
    dialog = ProjectSelectionDialog(
        parent, config_manager, youtube_gui=None, create_only=True,
        initial_channel=channel, initial_language=language,
        initial_raw_content=raw_content.strip()
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

