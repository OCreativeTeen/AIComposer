import matplotlib

matplotlib.use('Agg')  # Must be at the TOP of main.py

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import os
import json
import threading
import time
import pygame
from magic_workflow import MagicWorkflow
import config
import config_prompt
from project_manager import ProjectConfigManager, create_project_dialog, project_config_from_list_item
import project_manager
#from utility.minimax_speech_service import MinimaxSpeechService, EXPRESSION_STYLES
from utility.voicebox_speech_service import VoiceboxService
import tkinterdnd2 as TkinterDnD
from utility.media_scanner import MediaScanner
import utility.llm_api as llm_api
from gui.downloader import MediaGUIManager
from gui.suno_music_prompt_gui import SunoMusicPromptGUI
from gui.workflow.wf_common import IMAGE_ACTION_CHOICES, STANDARD_FPS, _download_folder_list_matching_suffixes, _external_media_pick_folders, _user_downloads_folder, _workflow_channel_display_name  # re-export
from gui.workflow.wf_actors import ActorsMixin  # re-export
from gui.workflow.wf_tracks import TracksMixin  # re-export
from gui.workflow.wf_pdf_episode import PdfEpisodeMixin  # re-export
from gui.workflow.wf_media_drop import MediaDropMixin  # re-export
from gui.workflow.wf_media_import import MediaImportMixin  # re-export
from gui.workflow.wf_clip_audio import ClipAudioMixin  # re-export
from gui.workflow.wf_player import PlayerMixin  # re-export
from gui.workflow.wf_timeline import TimelineMixin  # re-export
from gui.workflow.wf_speaking import SpeakingMixin  # re-export
from gui.workflow.wf_span_audio import SpanAudioMixin  # re-export
from gui.workflow.wf_scene_structure import SceneStructureMixin  # re-export
from gui.workflow.wf_scene_display import SceneDisplayMixin  # re-export
from gui.workflow.wf_images import ImagesMixin  # re-export
from gui.workflow.wf_prompt_flows import PromptFlowsMixin  # re-export
from gui.workflow.wf_finalize_publish import FinalizePublishMixin  # re-export
from gui.workflow.wf_config import ConfigMixin  # re-export
from gui.workflow.wf_layout import LayoutMixin  # re-export



# 图像画布双击：gui.choice_dialog.askchoice 用 (return_value, button_label) 元组列表


# Story 片头/片尾包装：菜单选中后复制英文指令到剪贴板；{channel_name} 运行时从 PROJECT_CONFIG.channel 解析














class WorkflowGUI(LayoutMixin, ConfigMixin, FinalizePublishMixin, PromptFlowsMixin, ImagesMixin, SceneDisplayMixin, SceneStructureMixin, SpanAudioMixin, SpeakingMixin, TimelineMixin, PlayerMixin, ClipAudioMixin, MediaImportMixin, MediaDropMixin, PdfEpisodeMixin, TracksMixin, ActorsMixin):
    # Standardized framerate to match video processing

    def __init__(self, root, initial_pid=None):
        # 如果拖拽支持可用，则使用TkinterDnD根窗口
        self.root = TkinterDnD.Tk() if not isinstance(root, TkinterDnD.Tk) else root
        # 如果传入的root不是TkinterDnD.Tk，需要重新创建
        if root != self.root:
            root.destroy()

        self.root.title("魔法工作流 GUI")
        try:
            self.root.state('zoomed') # Windows全屏
        except:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        try:
            pygame.mixer.init()
            self.pygame_mixer_available = True
        except Exception:
            self.pygame_mixer_available = False
        
        # 初始化配置加载标志
        self._loading_config = False
        self._scene_widgets_loading = False  # True 时跳过讲员「同步本故事」提示（避免切换场景时弹窗）
        self._programmatic_video_size = False  # True 时不响应尺寸 Combobox 的「应用」逻辑
        self._block_video_size_apply = True  # 场景加载完成前，忽略启动时排队的尺寸事件
        self.current_scene_index = 0

        self.llm_api = llm_api.LLMApi()
        self.llm_api_local = llm_api.LLMApi(llm_api.TEXT_MODEL)
        self.llm_api_manual = llm_api.LLMApi(llm_api.MODEL_MANUAL)  # 难任务直接走手动窗口

        # 显示项目选择对话框（或 --open-pid 时直接加载指定项目）
        if initial_pid:
            # 命令行 --open-pid：跳过欢迎屏，直接加载该项目
            config_manager = ProjectConfigManager()
            selected_config = config_manager.load_config(initial_pid)
            if not selected_config:
                messagebox.showerror("错误", f"无法加载项目 {initial_pid} 的配置", parent=self.root)
                self.root.destroy()
                return
            ProjectConfigManager.set_global_config(selected_config)
            selection_result = True  # 视为已选择项目
        else:
            selection_result = self.show_project_selection()

        if selection_result is False:
            self.root.destroy()
            return
        file_pid = (
            (project_manager.PROJECT_CONFIG or {}).get("pid") or initial_pid or ""
        )
        file_pid = str(file_pid).strip()
        if file_pid:
            self.root.title(f"魔法工作流 | {file_pid}")
        
        # 首先初始化任务状态跟踪 - 增强版
        self.tasks = {}
        self.completed_tasks = []  # 存储已完成的任务
        self.last_notified_tasks = set()  # 跟踪已通知的任务
        self.status_update_timer_id = None  # 状态更新定时器ID
        self.monitoring_scenes = {}  # 跟踪正在监控的场景 {scene_index: {"found_files": [], "start_time": time}}
        self.processed_output_files = set()  # 跟踪已处理的 X:\output 文件
        
        # 单例后台检查线程控制
        self.video_check_thread = None  # 后台检查线程
        self.video_check_running = False  # 线程运行标志
        self.video_check_stop_event = threading.Event()  # 停止事件
        
        # refresh_gui_scenes 节流控制
        self.refresh_gui_scenes_last_time = 0  # 上次执行时间
        self.refresh_gui_scenes_after_id = None  # 延迟任务ID
        self._demo_playthrough_active = False
        self._demo_playthrough_after_id = None
        
        # 添加视频效果选择存储
        self.effect_radio_vars = {}  # {scene_index: tk.StringVar}
        
        # 添加当前效果和图像类型选择变量
        self.narration_animation = tk.StringVar(value=config_prompt.ANIMATE_SOURCE[0])
        
        # 创建动画名称到提示语的映射字典（双向）
        self.animation_name_to_prompt = {item["name"]: item["prompt"] for item in config_prompt.ANIMATION_PROMPTS}
        self.animation_prompt_to_name = {item["prompt"]: item["name"] for item in config_prompt.ANIMATION_PROMPTS}
        self.animation_names = [""] + list(self.animation_name_to_prompt.keys())
        
        # 创建主框架
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建共享信息区域
        self.create_shared_info_area(main_frame)
        
        # 创建标签页控件
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # 创建各个标签页
        self.create_video_tab()
        
        self.setup_drag_and_drop()
        
        # 绑定标签页切换事件
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        # 启动任务状态更新定时器
        self.start_status_update_timer()
        
        # 加载上次保存的配置（必须在所有控件创建完成后，在绑定事件之前）
        self.load_config()
        self.bind_config_change_events()
        
        # 立即创建工作流实例（不再使用懒加载）
        self.create_workflow_instance()
        
        # 初始化媒体扫描器（必须在启动后台线程之前），未选择项目时（如 YT 管理）跳过
        self.media_scanner = MediaScanner(self.workflow, 10) if self.workflow else None

        # 必须先 load_scenes，再启动后台线程：否则 _perform_video_check 里 save_scenes_to_json 会在
        # self.scenes 未就绪时执行，报「无 scenes」或把空列表写盘覆盖项目。
        if self.workflow:
            self.workflow.load_scenes()
            pc = project_manager.PROJECT_CONFIG or {}
            try:
                vw, vh = project_manager.video_size_pair(pc.get("video_width"), pc.get("video_height"))
                self._set_video_size_combo_values(vw, vh)
            except (TypeError, ValueError):
                pass

        def _release_video_size_apply():
            self._block_video_size_apply = False

        self.root.after_idle(_release_video_size_apply)

        # 启动单例后台视频检查线程
        self.start_video_check_thread()
        # 绑定窗口关闭事件

        self.on_tab_changed(None)
        # t172u: 新项目用了预览的封面（2-6 场一集）：窗口起来后自动从封面逐场提取第 N 步
        if getattr(self.workflow, "cover_seeded_path", ""):
            self.root.after(1500, self._maybe_auto_extract_steps_from_cover)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)



    pid = None

    def get_pid(self):
        if self.pid is None and project_manager.PROJECT_CONFIG:
            self.pid = project_manager.PROJECT_CONFIG.get('pid')
        return self.pid
    


    def create_workflow_instance(self):
        """立即创建工作流实例（非懒加载）"""
        # 用户选择 YT 管理/下载时尚未创建或选择项目，PROJECT_CONFIG 为空是正常的
        if project_manager.PROJECT_CONFIG is None:
            self.workflow = None
            return
        try:
            # Get video dimensions from project config
            video_width = project_manager.PROJECT_CONFIG.get('video_width')
            video_height = project_manager.PROJECT_CONFIG.get('video_height')
            language = project_manager.PROJECT_CONFIG.get('language')
            channel = project_manager.PROJECT_CONFIG.get('channel')

            # 第一次打开没有 scenes.json，要从媒体切场景、合成视频，可能几分钟。先把窗口亮出来说明。
            busy_label = None
            try:
                if not os.path.exists(config.get_scenes_path(self.get_pid())):
                    busy_label = tk.Label(
                        self.root,
                        text="正在准备项目：切分音频、合成每一场的视频。\n场景多时要几分钟，请稍候，窗口会自己出来。",
                        font=("Microsoft YaHei", 14),
                        padx=40,
                        pady=30,
                        justify=tk.CENTER,
                    )
                    busy_label.place(relx=0.5, rely=0.5, anchor="center")
                    self.root.update()
            except Exception:
                busy_label = None
            try:
                self.workflow = MagicWorkflow(self.get_pid(), language, channel, video_width, video_height)
                #self.speech_service = MinimaxSpeechService(self.get_pid())
                self.speech_service = VoiceboxService(self.workflow.pid)

                current_gui_title = self.video_title.get().strip()
                self.workflow.post_init(current_gui_title)
            finally:
                if busy_label is not None:
                    try:
                        busy_label.destroy()
                    except tk.TclError:
                        pass
            
            # 初始化YouTube GUI管理器（第二参数为频道 key/id，非 channel_path；路径在 MediaGUIManager 内解析）
            self.youtube_gui = MediaGUIManager(
                self.root,
                channel,
                self.get_pid(), 
                self.tasks, 
                self.log_to_output, 
                self.video_output,  # 使用video_output作为YouTube下载日志输出
                language or "tw",
                workflow_gui=self,
            )
            
            print("✅ 工作流实例创建完成")
            
        except Exception as e:
            print(f"❌ 创建工作流实例失败: {e}")
            self.workflow = None


    def show_project_selection(self):
        """仅「选择项目」列表（无欢迎屏新建入口；新建走 downloader / create_project_with_initial_raw 等）。"""
        result, selected_config = create_project_dialog(self.root, youtube_gui=getattr(self, 'youtube_gui', None))

        if result == 'cancel':
            return False
        if result == 'open':
            if selected_config is None:
                print("❌ 错误：selected_config 为 None")
                return False
            ProjectConfigManager.set_global_config(selected_config)
            return True

        return False

   

   




    def _load_current_video_detail_row(self) -> dict | None:
        """当前项目绑定的 video detail：目标主题分表 list/<topic_category>.json，按 project_profile.pid 匹配。"""
        return project_manager.load_video_detail_row_for_config(
            project_manager.PROJECT_CONFIG or {}
        )






    def _return_to_story_preview(self) -> None:
        """回到这条的故事预览。预览还没开时，请列表打开它，再拿到前面。"""
        from gui.raise_window import find_story_window, raise_window

        pc = project_manager.PROJECT_CONFIG or {}
        row = self._load_current_video_detail_row() or {}
        title = ""
        keys: list[str] = []
        for src in (pc, row):
            if not isinstance(src, dict):
                continue
            if not title:
                title = (src.get("video_title") or src.get("title") or "").strip()
            for key in ("pid", "id", "url"):
                val = (src.get(key) or "").strip()
                if val and val not in keys:
                    keys.append(val)

        def _matches(hwnd: int) -> bool:
            if not hwnd or not title:
                return bool(hwnd) and not title
            try:
                import win32gui

                text = win32gui.GetWindowText(int(hwnd)) or ""
            except Exception:
                return False
            return title[:24] in text

        hwnd = find_story_window()
        if hwnd and _matches(hwnd):
            raise_window(hwnd)
            return
        if not keys:
            messagebox.showinfo(
                "回到预览",
                "这条没有能对上列表的编号，预览打不开。",
                parent=self.root,
            )
            return

        def work() -> None:
            from cli.bridge import send_bridge_command

            ok, _msg = send_bridge_command(
                screen=config.SCREEN_VIDEO_LIST,
                op="set",
                field="open_row",
                value=json.dumps(keys, ensure_ascii=False),
                timeout_s=8.0,
            )
            found = 0
            if ok:
                for _ in range(40):
                    candidate = find_story_window()
                    if candidate and _matches(candidate):
                        found = candidate
                        break
                    time.sleep(0.15)

            def done() -> None:
                if found:
                    raise_window(found)
                    return
                messagebox.showinfo(
                    "回到预览",
                    "列表窗口要开着，才能从这里打开故事预览。",
                    parent=self.root,
                )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _current_feature_row(self) -> dict:
        row = self._load_current_video_detail_row()
        return row if isinstance(row, dict) else {}




    def _open_suno_gui(self):
        """打开SUNO音乐提示词管理窗口"""
        try:
            # 创建SUNO管理窗口
            SunoMusicPromptGUI(self.root)
        except Exception as e:
            messagebox.showerror("错误", f"打开SUNO管理窗口失败: {str(e)}")
            import traceback
            traceback.print_exc()





































































    _CLIP_DEST_OPTIONS = (
        ("clip", "Clip"),
        ("narration", "旁白"),
        ("zero_episode", "Zero 整集"),
        ("zero_scene", "Zero 本场"),
    )










































    _MIN_SECTION_GAP_SEC = 0.3

    # speaking_timing 只有一个字段：{"text": 记下时间时的 speaking, "sections": [每段 speaker/start/end/text]}。
    # text 和 speaking 不一样，就说明 speaking 后来被改过，这份时间不能再用。




















    

    



    



    











    _FINAL_SPEED_CHOICES = tuple(f"{0.70 + 0.05 * i:.2f}" for i in range(13))

















    









    

    

















    _SPEAKER_BAR_COLORS = {1: "#2f6fed", 2: "#e09a2f", 3: "#2f9e4f"}








    _PROGRESS_KNOB = 22






























































































































    _TRANSITION_SPACE = (
        ("不变", "地方和时间都保持"),
        ("换地方", "例如从室外走进室内"),
        ("换时间", "白天到黑夜，或反过来"),
        ("一起变", "地方和时间一起变。场面大，过渡很短"),
    )
    _TRANSITION_PEOPLE = (
        ("没有变化", "在场的人不动"),
        ("自然增减", "平淡地走进来，或平静地走开"),
        ("意外增减", "由意外带出来，例如车忽然停下、有人下来"),
    )
    _TRANSITION_SPEECH = (
        ("不说话", "不开口，可以用音乐带过"),
        ("简单寒暄", "一两句没有实际内容的招呼"),
        ("人声", "人来人走时，嬉笑、叹息或一声短招呼"),
        ("小动作", "碰杯、吃饭，声音跟着动作"),
        ("场景烘托", "对话停一下，把谈到的气氛在环境里托出来"),
    )
    _TRANSITION_EFFECTS = (
        ("自然转换", "从起始图到终止图自然过渡"),
        ("叠化", "两张图慢慢融在一起"),
        ("嗖一下", "一声掠过，画面很快甩过去"),
        ("翻书", "像翻过一页书"),
        ("擦除", "后一张图从一边推开前一张"),
        ("闪白", "先闪白，再落到终止图"),
    )
































































    



    # ========== PIP L/R 播放控制函数 ==========
    
    
    
    
    
    


    

    
    
    

































    
    



    

    


    










    _SCENE_IMPORT_ALWAYS_KEYS = frozenset({
        "speaking", "caption", "voiceover", "visual", "actor",
        "clip_animation", "narration_animation", "extension", "cinematography",
    })
    _SCENE_IMPORT_SKIP_KEYS = frozenset({"start", "end", "duration", "transition"})






















            
                
    







    



























    # 视频拖拽相关方法









































 




def main():
    import sys
    root = TkinterDnD.Tk()

    initial_pid = None
    if len(sys.argv) >= 4 and sys.argv[1] == "--open-from-list-json":
        list_path = sys.argv[2]
        try:
            idx = int(sys.argv[3])
        except ValueError:
            messagebox.showerror("启动错误", "--open-from-list-json 需要整数 index")
            root.destroy()
            return
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                arr = json.load(f)
            if not isinstance(arr, list) or idx < 0 or idx >= len(arr):
                raise ValueError("index 超出列表范围")
            item = arr[idx]
            cfg = project_config_from_list_item(item, os.path.normpath(list_path), idx)
            ProjectConfigManager.set_global_config(cfg)
            initial_pid = (cfg or {}).get("pid")
            if not initial_pid:
                raise ValueError("列表项中无有效 pid / project_profile")
        except Exception as e:
            try:
                messagebox.showerror("启动错误", f"无法从频道列表项载入项目：{e}")
            except Exception:
                pass
            root.destroy()
            return
    elif len(sys.argv) >= 3 and sys.argv[1] == '--open-pid':
        initial_pid = sys.argv[2]

    try:
        WorkflowGUI(root, initial_pid=initial_pid)
        root.mainloop()
    except Exception as e:
        import traceback
        try:
            messagebox.showerror("启动错误", f"启动失败: {e}\n\n详见终端输出")
        except Exception:
            pass
        print(traceback.format_exc())
        raise

if __name__ == "__main__":
    main()

