import os
import sys
import time
import yt_dlp
import subprocess
import shutil
import json
import re
import string
import threading
import glob

import config
import config_prompt
import config_channel
from datetime import datetime, timedelta

import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility import llm_api
from utility.audio_transcriber import AudioTranscriber
from utility.file_util import write_json, safe_copy_overwrite, safe_remove, parse_json, make_safe_file_name
from gui.choice_dialog import askchoice
from gui.reference_editor_dialog import ReferenceEditorDialog
from gui.tag_picker_menu import build_tag_cascade_menu, post_menu_below_widget
from utility.tags_text import merge_tag_pick, parse_tags_list
import project_manager
        
# 导入所需模块
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
import tkinter.simpledialog as simpledialog


def _format_nb_prompt_template(template: str, **kwargs) -> str:
    """只对模板中出现的 {name} 占位符填入 kwargs，避免各频道模板字段不一致导致 str.format 报错。"""
    names = set()
    for _, field_name, _, _ in string.Formatter().parse(template):
        if not field_name:
            continue
        names.add(field_name.split("!")[0].split(":")[0].strip())
    safe = {k: kwargs.get(k, "") for k in names}
    return template.format(**safe)


def _treeview_item_tags_safe(tree, item):
    """读取 Treeview 行的 tags。populate_tree 会删行重建，旧 iid 失效，必须先 exists。"""
    try:
        if tree.exists(item):
            return tree.item(item, "tags")
    except tk.TclError:
        pass
    return ()


# 频道视频项里 story 字段：持久化为 JSON 文本字符串；若历史数据为 dict/list 则规范为字符串
_STORY_LANG_BRANCH_KEYS = ("concise_speaking", "heart_message", "psychological_micro_story")


def _normalize_channel_videos_story_field_to_str(videos):
    """将每条 video['story'] 规范为 str（JSON 字符串），不把结构直接挂在 dict 上。"""
    if not videos:
        return
    for v in videos:
        if not isinstance(v, dict):
            continue
        s = v.get("story")
        if s is None:
            continue
        if isinstance(s, (dict, list)):
            v["story"] = json.dumps(s, ensure_ascii=False, indent=2)


def _video_youtube_id(v):
    """从频道视频项解析 YouTube 视频 id（11 位）。"""
    if not isinstance(v, dict):
        return ""
    vid = (v.get("id") or "").strip()
    if vid:
        return vid
    url = (v.get("url") or "").strip()
    m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)
    return ""


def _merge_related_id_status(existing, new_id):
    new_id = (new_id or "").strip()
    if not new_id:
        return (existing or "").strip()
    parts = [p.strip() for p in str(existing or "").split("|") if p.strip()]
    if new_id not in parts:
        parts.append(new_id)
    return "|".join(parts)


def _find_video_by_youtube_id(channel_videos, yid):
    yid = (yid or "").strip()
    if not yid:
        return None
    for v in channel_videos or []:
        if _video_youtube_id(v) == yid:
            return v
    return None


def _reference_item_youtube_id(item):
    """从 NotebookLM 参考项 dict 中解析 YouTube id（优先 id 字段，其次 url）。"""
    if not isinstance(item, dict):
        return ""
    return _video_youtube_id(item)


def _norm_path_compare(a, b):
    """比较两条路径是否指向同一文件（规范化 +  basename 兜底）。"""
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    try:
        na, nb = os.path.normcase(os.path.normpath(os.path.abspath(a))), os.path.normcase(
            os.path.normpath(os.path.abspath(b))
        )
        if na == nb:
            return True
    except Exception:
        pass
    return os.path.basename(a).lower() == os.path.basename(b).lower()


def _find_channel_video_for_reference_item(item, channel_videos):
    """
    将参考列表中的单项与 channel_videos 中的 video 对应：
    优先 YouTube id，其次 transcribed_file 路径，再试 url。
    """
    if not isinstance(item, dict):
        return None
    yid = _reference_item_youtube_id(item)
    if yid:
        v = _find_video_by_youtube_id(channel_videos, yid)
        if v:
            return v
    tfp = (item.get("transcribed_file") or "").strip()
    if tfp:
        for v in channel_videos or []:
            vtf = (v.get("transcribed_file") or "").strip()
            if vtf and _norm_path_compare(tfp, vtf):
                return v
    url = (item.get("url") or "").strip()
    if url:
        for v in channel_videos or []:
            if (v.get("url") or "").strip() == url:
                return v
    return None


def _status_display_for_related_field(raw):
    """树与表单展示：忽略历史下载占用的 status。"""
    s = raw if isinstance(raw, str) else str(raw or "")
    if s in ("success", "failed"):
        return ""
    return s


_SIMILAR_SUMMARY_MATCH_SYSTEM = """你是心理咨询类视频摘要的相似度分析助手。
给定一条「参考摘要」和若干「候选视频」（每条含 YouTube id、标题、摘要片段），请判断哪些候选与参考在**心理问题主题、案例结构、临床叙事**上足够接近，可视为「类似案例」。
只输出严格 JSON 对象，不要其它文字。格式：
{"matches":[{"id":"<候选中的 youtube id>","confidence":0.0-1.0,"reason":"一句中文说明相似点"}]}
规则：matches 按 confidence 降序；最多 18 条；id 必须完全来自候选列表；若无合适候选则 {"matches":[]}。"""



class MediaDownloader:

    def __init__(self, pid, youtube_path, language):
        print("YoutubeDownloader init...")
        self.pid = pid
        self.youtube_dir = youtube_path
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)

        self.channel_list_json = ""
        self.channel_videos = []
        self.channel_name = ""
        self.latest_date = datetime.now()
        self.language = language
        
        # Cookies 文件路径（优先检查下载文件夹，然后检查项目路径）
        self.cookie_file = self._find_cookies_file()
        if self.cookie_file and os.path.exists(self.cookie_file):
            print(f"✅ 找到 cookies 文件: {self.cookie_file}")
        else:
            print(f"⚠️ 未找到 cookies 文件")
        
        # 检测 JavaScript 运行时
        self.js_runtime = self._detect_js_runtime()
        self.transcriber = AudioTranscriber(self.pid, model_size="small", device="cuda")


    def _find_cookies_file(self):
        cookies_filename = "www.youtube.com_cookies.txt"
        download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        download_cookies = os.path.join(download_folder, cookies_filename)
        
        if os.path.exists(download_cookies):
            print(f"✅ 在下载文件夹找到 cookies 文件: {download_cookies}")
            # 移动到项目路径
            project_cookies = os.path.join(f"{self.youtube_dir}/work", cookies_filename)
            if os.path.exists(project_cookies):
                os.remove(project_cookies)
                print(f"🗑️ 已删除旧的 cookies 文件: {project_cookies}")
            # 移动文件到项目路径
            shutil.move(download_cookies, project_cookies)
            return project_cookies
        
        return None


    def _check_and_update_cookies(self, wait_forever=True):
        """
        检查 cookies：优先使用项目路径已有文件；仅当没有有效 cookies 时检查 Downloads 并可能弹窗。
        同一次启动内已有有效 cookies 则直接复用，不重复弹窗；弹窗在同 session 内最多一次。
        """
        cookies_filename = "www.youtube.com_cookies.txt"
        project_cookies = os.path.join(f"{self.youtube_dir}/work", cookies_filename)
        download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        download_cookies = os.path.join(download_folder, cookies_filename)

        # 1. 若项目路径已有有效 cookies，直接复用，不弹窗
        if self.cookie_file and os.path.exists(self.cookie_file) and os.path.getsize(self.cookie_file) > 0:
            return True
        if os.path.exists(project_cookies) and os.path.getsize(project_cookies) > 0:
            self.cookie_file = project_cookies
            return True

        # 2. 尝试从 Downloads 获取（可能有新导出的）
        self.cookie_file = self._find_cookies_file()
        if self.cookie_file:
            return True

        # 3. 无有效 cookies：wait_forever=False 时直接返回
        if not wait_forever:
            return False

        # 4. 持续等待：同 session 内弹窗最多一次，避免频繁打扰
        last_prompt_key = '_cookie_prompt_shown_at'
        while True:
            if os.path.exists(download_cookies):
                print(f"🔄 在下载文件夹发现新的 cookies 文件: {download_cookies}")
                
                # 移动到项目路径
                project_cookies = os.path.join(f"{self.youtube_dir}/work", cookies_filename)
                try:
                    # 如果项目路径已有文件，直接删除
                    if os.path.exists(project_cookies):
                        os.remove(project_cookies)
                        print(f"🗑️ 已删除旧的 cookies 文件: {project_cookies}")
                    
                    # 移动新文件
                    shutil.move(download_cookies, project_cookies)

                    self.cookie_file = project_cookies
                    # 重置 cookies 日志标志，以便下次使用新 cookies 时打印信息
                    if hasattr(self, '_cookies_logged'):
                        delattr(self, '_cookies_logged')
                    print(f"✅ 已更新 cookies 文件: {project_cookies}")
                    print(f"🗑️ 已从下载文件夹删除原文件")
                    print(f"🔄 下次请求将使用新的 cookies 文件")
                    return True
                except Exception as e:
                    print(f"⚠️ 更新 cookies 文件时出错: {e}")
                    return False
            
            # 等待并检查
            print(f"⏳  请将新的 cookies 文件保存到: {download_cookies}")
            # 同一次启动内弹窗最多一次，避免频繁打扰
            if not getattr(self, '_cookie_prompt_shown', False):
                self._cookie_prompt_shown = True
                messagebox.showinfo("提示", "请将新的 cookies 文件保存到下载文件夹")
            time.sleep(2)  # 每2秒检查一次，避免 busy loop


    def _detect_js_runtime(self):
        """
        检测系统中可用的 JavaScript 运行时
        
        Returns:
            tuple: (runtime_name, runtime_path) 或 (None, None)
        """
        # 优先检测 Node.js
        node_path = shutil.which('node')
        if node_path:
            try:
                # 验证 Node.js 是否可用
                result = subprocess.run(
                    ['node', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    print(f"✅ 检测到 JavaScript 运行时: Node.js {version}")
                    return ('node', node_path)
            except Exception:
                pass
        
        # 检测 Deno
        deno_path = shutil.which('deno')
        if deno_path:
            try:
                result = subprocess.run(
                    ['deno', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split('\n')[0]
                    print(f"✅ 检测到 JavaScript 运行时: Deno {version}")
                    return ('deno', deno_path)
            except Exception:
                pass
        
        # 未找到 JavaScript 运行时
        print("⚠️ 未检测到 JavaScript 运行时（Node.js 或 Deno）")
        print("   这可能导致某些 YouTube 视频无法下载或格式缺失")
        print("   建议安装 Node.js: https://nodejs.org/")
        return (None, None)


    def _get_ydl_opts_base(self, **kwargs):
        """
        获取基础的 yt-dlp 选项，包含 cookies 支持
        
        Args:
            **kwargs: 额外的选项参数（quiet, skip_download 等）
            
        Returns:
            dict: yt-dlp 选项字典
        """
        # 从 kwargs 中提取基础选项，如果没有提供则使用默认值
        opts = {}
        
        # 只使用 cookies 文件（不从浏览器提取，避免 DPAPI 错误）
        if self.cookie_file and os.path.exists(self.cookie_file) and os.path.getsize(self.cookie_file) > 0:
            opts['cookiefile'] = self.cookie_file
            # 只在第一次使用时打印，避免重复输出
            if not hasattr(self, '_cookies_logged'):
                print(f"🍪 使用 cookies 文件: {self.cookie_file}")
                self._cookies_logged = True
        
        # 添加请求间隔延迟，避免被 YouTube 限流
        # sleep_interval: 每次请求之间的最小延迟（秒）
        # sleep_interval_requests: 每 N 个请求后额外延迟
        if 'sleep_interval' not in kwargs:
            opts['sleep_interval'] = 2  # 每次请求之间至少延迟 2 秒（降低默认值以提高速度）
        if 'sleep_interval_requests' not in kwargs:
            opts['sleep_interval_requests'] = 5  # 每 5 个请求后额外延迟（降低以提高速度）
        
        # 配置 JavaScript 运行时（如果检测到）
        # yt-dlp 期望格式: {runtime_name: {config_dict}}
        if self.js_runtime[0] and 'js_runtimes' not in kwargs:
            runtime_name, runtime_path = self.js_runtime
            # 构建配置字典
            runtime_config = {}
            if runtime_path:
                runtime_config['path'] = runtime_path
            
            # yt-dlp 期望的格式: {runtime_name: {config}}
            opts['js_runtimes'] = {runtime_name: runtime_config}
        
        # 启用远程组件下载，用于解决 YouTube JavaScript 挑战
        # ejs:github 表示从 GitHub 下载 EJS (Extract JavaScript) 组件
        if 'remote_components' not in kwargs:
            opts['remote_components'] = ['ejs:github']
        
        # 添加所有传入的选项（会覆盖上面的默认值）
        opts.update(kwargs)
        
        return opts


    def find_video_basic(self, video_detail):
        if not self.cookie_file:
            return None

        check_opts = self._get_ydl_opts_base(quiet=True, skip_download=True)
        with yt_dlp.YoutubeDL(check_opts) as ydl:
            info = ydl.extract_info(video_detail.get('url', ''), download=False)
            return info


    def download_captions(self, video_detail, target_lang):
        if not target_lang:
            return None

        video_url = video_detail.get('url', '')
        if not video_url:
            return None

        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        
        if self.cookie_file:
            ydl_opts = self._get_ydl_opts_base(
                skip_download=True,
                writesubtitles=True,
                writeautomaticsub=True,
                subtitleslangs=[target_lang],
                subtitlesformat="srt",
                outtmpl=download_prefix,
                quiet=True,
                no_warnings=True,
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                # 与 download_audio_only 保持一致：同次请求获取 upload_date 并更新 video_detail
                if info and 'upload_date' in info:
                    upload_date = info.get('upload_date', '')
                    if upload_date:
                        upload_date = str(upload_date).strip()
                        if upload_date:
                            if len(upload_date) == 10:
                                upload_date = upload_date.replace('-', '')
                            video_detail['upload_date'] = upload_date[:8]
                            print(f"✅ 已更新 upload_date: {upload_date[:8]}")
            print(f"✅ 已下载字幕：语言 {target_lang}")
            src_path = f"{download_prefix}.{target_lang}.srt"
            if os.path.exists(src_path):
                return src_path

        print(f"❌ 下载字幕失败，尝试转录...")
        src_path = f"{download_prefix}.{target_lang}.json"
        if os.path.exists(src_path):
            return src_path

        audio_path = video_detail.get('audio_path', '')
        if not audio_path:
            print(f"❌ 音频文件不存在")
            return None

        scene_min_length = project_manager.PROJECT_CONFIG.get('scene_min_length',9)
        script_json = self.transcriber.transcribe_with_whisper(audio_path, target_lang, scene_min_length, int(scene_min_length*1.5))
        if script_json:
            write_json(src_path, script_json)  
            return src_path
        else:
            return None


    def try_download_caption_with_priority(self, video_detail):
        """按用户选择的语言优先尝试下载字幕，成功返回路径，失败返回 None"""
        if not self.cookie_file:
            return None
        # 优先使用用户选择的语言，再加少量同族 fallback，减少重复请求
        user_lang = self.language or "en"
        if user_lang.startswith("zh"):
            fallbacks = ["zh", "zh-Hans", "zh-Hant"]
        elif user_lang.startswith("en"):
            fallbacks = ["en", "en-US", "en-GB"]
        else:
            fallbacks = []
        seen = set()
        CAPTION_LANG_PRIORITY = []
        for lang in [user_lang] + fallbacks:
            if lang not in seen:
                seen.add(lang)
                CAPTION_LANG_PRIORITY.append(lang)
        for lang in CAPTION_LANG_PRIORITY:
            path = self.download_captions(video_detail, lang)
            if path:
                return path
        return None

    def pick_best_caption_language(self, all_languages):
        """从可用语言中优先选中文，其次英文，否则返回 None"""
        if not all_languages:
            return None
        zh_pattern = re.compile(r'^zh', re.I)  # zh, zh-CN, zh-TW, zh-Hans...
        en_pattern = re.compile(r'^en', re.I)  # en, en-US, en-GB...
        zh_langs = [l for l in all_languages if zh_pattern.match(l)]
        en_langs = [l for l in all_languages if en_pattern.match(l)]
        if zh_langs:
            return zh_langs[0]
        if en_langs:
            return en_langs[0]
        return None

    def download_audio_only(self, video_detail, sleep_interval=2):
        video_url = video_detail.get('url', '')
        if not video_url:
            return None

        video_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)

        video_path = video_prefix + ".mp4"
        if os.path.exists(video_path):
            audio_path = self.ffmpeg_audio_processor.extract_audio_from_video(video_path, "mp3")
            safe_copy_overwrite(audio_path, video_prefix + ".mp3")
            video_detail['audio_path'] = audio_path
            return audio_path

        audio_extensions = ['mp3', 'm4a', 'webm', 'opus', 'wav']
        for ext in audio_extensions:
            audio_path = video_prefix + "." + ext
            if os.path.exists(audio_path):
                if not audio_path.endswith('.mp3'):
                    a = self.ffmpeg_audio_processor.to_mp3(audio_path)
                    safe_remove(audio_path)
                    audio_path = video_prefix + ".mp3"
                    safe_copy_overwrite(a, audio_path)
                video_detail['audio_path'] = audio_path
                return audio_path

        outtmpl = video_prefix + ".%(ext)s"
        format_string = 'bestaudio'
        # 使用基础选项，包含 cookies 支持
        ydl_opts_kwargs = {
            'format': format_string,
            'outtmpl': outtmpl,
            'quiet': False,
            'progress_hooks': [self._progress_hook],
            'skip_download': False,  # 需要下载
            'ignoreerrors': False,  # 不忽略错误,让调用者处理
        }
        if sleep_interval is not None:
            ydl_opts_kwargs['sleep_interval'] = sleep_interval
        
        ydl_opts = self._get_ydl_opts_base(**ydl_opts_kwargs)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                
                # 从 info 中提取 upload_date 并填充到 video_detail
                if info and 'upload_date' in info:
                    upload_date = info.get('upload_date', '')
                    if upload_date:
                        if len(upload_date) == 10:
                            upload_date = upload_date.replace('-', '')
                        video_detail['upload_date'] = upload_date
                        print(f"✅ 已更新 upload_date: {upload_date}")
                
                # 检查各种可能的音频扩展名
                for ext in audio_extensions:
                    expected_path = os.path.abspath(f"{video_prefix}.{ext}")
                    if os.path.exists(expected_path):
                        print(f"✅ 找到下载的音频文件: {expected_path}")
                        if not expected_path.endswith('.mp3'):
                            a = self.ffmpeg_audio_processor.to_mp3(expected_path)
                            #safe_remove(expected_path)
                            expected_path = video_prefix + ".mp3"
                            safe_copy_overwrite(a, expected_path)
                        video_detail['audio_path'] = expected_path
                        return expected_path
                
                # 如果找不到，尝试从 info 中获取实际文件名
                if 'requested_downloads' in info and len(info['requested_downloads']) > 0:
                    actual_path = info['requested_downloads'][0].get('filepath')
                    if actual_path and os.path.exists(actual_path):
                        expected_path = os.path.abspath(actual_path)
                        if not expected_path.endswith('.mp3'):
                            a = self.ffmpeg_audio_processor.to_mp3(expected_path)
                            safe_remove(expected_path)
                            expected_path = video_prefix + ".mp3"
                            safe_copy_overwrite(a, expected_path)
                        video_detail['audio_path'] = expected_path
                        return expected_path
                
                return None
        except Exception as e:
            print(f"❌ 下载音频失败: {str(e)}")
            return None


    def download_video_highest_resolution(self, video_detail, sleep_interval=2):
        video_url = video_detail.get('url', '')
        if not video_url:
            return None
        video_prefix = self.youtube_dir + "/media/__" + self.generate_video_prefix(video_detail)

        target_video_path = video_prefix + ".mp4"
        target_audio_path = video_prefix + ".mp3"
        if os.path.exists(target_video_path):
            if video_detail.get('video_path', '') == target_video_path:
                return video_detail['video_path']
            video_detail['video_path'] = video_prefix + ".mp4"
            audio_path = video_detail.get('audio_path', '')
            if not audio_path or audio_path != target_audio_path:
                a = self.ffmpeg_audio_processor.extract_audio_from_video(target_video_path, "mp3")
                safe_copy_overwrite(a, target_audio_path)
                video_detail['audio_path'] = target_audio_path
            return video_detail['video_path']

        outtmpl = video_prefix + ".%(ext)s"
        # 优先级: MP4 高质量 -> 任何高质量 -> 最佳可用
        format_string = (
            #'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/'  # 1. MP4 1080p + M4A
            'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'                # 2. 任何 MP4 + M4A
            #'bestvideo[height<=1080]+bestaudio/'                    # 3. 1080p 视频 + 音频
            #'bestvideo+bestaudio/'                                  # 4. 最佳视频 + 音频
            #'best[ext=mp4][height<=1080]/'                          # 5. 单文件 MP4 1080p
            #'best[ext=mp4]/'                                        # 6. 任何单文件 MP4
            #'best'                                                  # 7. 最佳可用格式
        )
        
        # 使用基础选项，包含 cookies 支持
        ydl_opts_kwargs = {
            'format': format_string,
            'outtmpl': outtmpl,
            'merge_output_format': 'mp4',
            'quiet': False,
            'progress_hooks': [self._progress_hook],
            'skip_download': False,  # 需要下载
            'ignoreerrors': False,  # 不忽略错误,让调用者处理
        }
        if sleep_interval is not None:
            ydl_opts_kwargs['sleep_interval'] = sleep_interval
        
        ydl_opts = self._get_ydl_opts_base(**ydl_opts_kwargs)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                # 验证文件是否存在
                if not os.path.exists(target_video_path):
                    # 尝试查找其他扩展名
                    base_path = target_video_path.rsplit('.', 1)[0]
                    for ext in ['webm', 'mkv', 'mp4']:
                        alt_path = f"{base_path}.{ext}"
                        if os.path.exists(alt_path):
                            print(f"✅ 找到下载文件: {alt_path}")
                            target_video_path = alt_path
                            break
                
                safe_copy_overwrite(self.ffmpeg_audio_processor.extract_audio_from_video(target_video_path, "mp3"), target_audio_path)
                video_detail['audio_path'] = target_audio_path
                video_detail['video_path'] = target_video_path

                return target_video_path

        except Exception as e:
            return None


    def get_playlist_info(self, playlist_url):
        """获取播放列表信息，不下载视频"""
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,  # 只提取基本信息，不下载
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(playlist_url, download=False)
                
                playlist_info = {
                    'title': info.get('title', 'Unknown Playlist'),
                    'description': info.get('description', ''),
                    'video_count': info.get('playlist_count', 0),
                    'videos': []
                }
                
                if 'entries' in info:
                    for entry in info['entries']:
                        if entry:
                            video_info = {
                                'title': entry.get('title', 'Unknown Title'),
                                'url': entry.get('url', ''),
                                'duration': entry.get('duration', 0),
                                'view_count': entry.get('view_count', 0),
                                'uploader': entry.get('uploader', ''),
                                'upload_date': entry.get('upload_date', '')
                            }
                            playlist_info['videos'].append(video_info)
                
                return playlist_info
                
            except Exception as e:
                print(f"❌ 获取播放列表信息失败: {str(e)}")
                return None


    def get_video_detail(self, video_url, channel_name='Unknown'):
        # 获取详细信息，使用 cookies
        video_info_opts = self._get_ydl_opts_base(
            quiet=True,
            skip_download=True
        )
        try:
            with yt_dlp.YoutubeDL(video_info_opts) as video_ydl:
                video_detail = video_ydl.extract_info(video_url, download=False)
                
                if not video_detail:
                    raise Exception(f"无法获取视频信息: {video_url}")
                
                uploader = video_detail.get('uploader') or video_detail.get('channel') or channel_name
                chan = video_detail.get('channel') or video_detail.get('uploader') or channel_name
                video_data = {
                    'title': video_detail.get('title', 'Unknown Title'),
                    'url': video_url,
                    'id': video_detail.get('id', ''),
                    'duration': video_detail.get('duration', 0),
                    'view_count': video_detail.get('view_count', 0),
                    'uploader': uploader,
                    'channel': chan,  # 优先使用 yt-dlp 提取的频道名，不覆盖
                    'channel_id': video_detail.get('channel_id', ''),
                    'upload_date': video_detail.get('upload_date', ''),
                    'thumbnail': video_detail.get('thumbnail', ''),
                    'description': video_detail.get('description', '')[:200] if video_detail.get('description') else ''
                }
                return video_data
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if '403' in error_msg or 'Forbidden' in error_msg:
                raise Exception(f"HTTP 403 Forbidden - YouTube 访问被拒绝，可能需要更新 cookies 或等待: {video_url}")
            elif 'challenge' in error_msg.lower():
                raise Exception(f"YouTube 挑战验证失败: {video_url}")
            else:
                raise Exception(f"下载错误: {error_msg}")
        except Exception as e:
            # 重新抛出异常，让调用者处理
            raise


    def generate_video_prefix(self, video_detail, title_length=15):
        # 格式: {view_count:010d}_{upload_date}_{title}.{ext}
        view_count = video_detail.get('view_count', 0)
        upload_date = video_detail.get('upload_date', "20260101")
        title = video_detail.get('title', 'Unknown')

        view_count_str = f"{view_count:010d}" if view_count else "0000000000"
        # 处理上传日期
        if upload_date and len(upload_date) >= 8:
            date_str = upload_date[:8]  # YYYYMMDD
        else:
            date_str = "00000000"
        # 清理标题中的非法字符，并限制长度
        safe_title = make_safe_file_name(title, title_length)
        # 构建文件名前缀（用于匹配）
        return f"{view_count_str}_{date_str}_{safe_title}"


    def get_channel_name(self, video_detail):
        """从视频/频道详情提取频道名。空或 Unknown 时尝试下一项；避免返回 untitled。"""
        if not video_detail:
            return 'YouTubeChannel'
        for key in ('channel', 'uploader', 'creator'):
            v = (video_detail.get(key) or '').strip()
            if v and v.lower() not in ('unknown', ''):
                r = make_safe_file_name(v)
                if r != "untitled":
                    print(f"📺 频道名称: {r}")
                    return r
        cid = (video_detail.get('channel_id') or '').strip()
        if cid and len(cid) >= 10:
            r = make_safe_file_name(cid)
            if r != "untitled":
                return r
        print(f"📺 频道名称: YouTubeChannel (fallback)")
        return "YouTubeChannel"

    def _parse_relative_time_to_yyyymmdd(self, s):
        """解析相对时间字符串为 YYYYMMDD。如 "1 day ago"=昨天, "2 weeks ago", "3 months ago"。
        1天=24h, 1周=24*7, 1月≈30*24h。供 flat 抓取无 upload_date 时估算，download 时再更新精确值。"""
        if not s or not isinstance(s, str):
            return ''
        s = s.strip().lower()
        if not s:
            return ''
        # Unix 时间戳（秒）
        if s.isdigit():
            try:
                t = datetime.fromtimestamp(int(s))
                return t.strftime('%Y%m%d')
            except (ValueError, OSError):
                return ''
        # 匹配 "X (second|minute|hour|day|week|month|year)(s)? ago" 或 "X 秒/分/时/天/周/月/年 前"
        now = datetime.now()
        m = re.search(r'(\d+)\s*(second|minute|hour|day|week|month|year|秒|分|时|天|周|月|年)s?\s*(ago|前)?', s, re.I)
        if not m:
            return ''
        n = int(m.group(1))
        unit = (m.group(2) or '').lower()
        mul = {'second': 1/3600, 'minute': 1/60, 'hour': 1, 'day': 24, 'week': 24*7, 'month': 30*24, 'year': 365*24,
               '秒': 1/3600, '分': 1/60, '时': 1, '天': 24, '周': 24*7, '月': 30*24, '年': 365*24}
        if unit not in mul:
            return ''
        hours = n * mul[unit]
        try:
            from datetime import timedelta
            t = now - timedelta(hours=hours)
            return t.strftime('%Y%m%d')
        except Exception:
            return ''

    def _entry_upload_date(self, entry):
        """从 entry 提取 upload_date：优先 upload_date/release_timestamp，否则尝试解析相对时间字符串。"""
        ud = (entry.get('upload_date') or entry.get('release_date') or '').strip()
        if ud:
            if len(ud) == 10 and '-' in ud:
                return ud.replace('-', '')[:8]
            if len(ud) >= 8 and ud.isdigit():
                return ud[:8]
        ts = entry.get('release_timestamp') or entry.get('timestamp')
        if ts is not None:
            try:
                t = datetime.fromtimestamp(int(ts))
                return t.strftime('%Y%m%d')
            except (ValueError, OSError, TypeError):
                pass
        for v in (entry.get(k) for k in ('description', 'title') if entry.get(k)):
            if isinstance(v, str) and ('ago' in v.lower() or '前' in v):
                r = self._parse_relative_time_to_yyyymmdd(v)
                if r:
                    return r
        return ''

    def fetch_channel_info_from_url(self, url):
        """从频道链接或视频链接解析出频道名和频道页 URL。供 YT文字/YT管理 创建新频道时共用。
        返回 (channel_name, channel_url) 或 (None, None) 表示失败。"""
        url = (url or '').strip()
        if not url:
            return None, None
        try:
            self._check_and_update_cookies()
            if '/watch?v=' in url or 'youtu.be/' in url:
                # 视频链接：从视频获取频道信息
                video_data = self.get_video_detail(url, '')
                if not video_data:
                    return None, None
                channel_name = self.get_channel_name(video_data)
                channel_id = (video_data.get('channel_id') or '').strip()
                channel_url = f"https://www.youtube.com/channel/{channel_id}/videos" if channel_id and len(channel_id) >= 10 else None
                return channel_name, channel_url
            # 频道链接：/channel/xxx 或 /@xxx 或 /c/xxx
            ydl_opts = self._get_ydl_opts_base(quiet=True, extract_flat='in_playlist', skip_download=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return None, None
            channel_name = self.get_channel_name(info)
            channel_url = url.rstrip('/')
            if '/videos' not in channel_url:
                channel_url += '/videos'
            return channel_name, channel_url
        except Exception as e:
            print(f"❌ 解析链接失败: {e}")
            return None, None

    def is_video_new(self, video_data):
        """判断是否为列表中尚未存在的视频。只要标题一致即视为已有，不重复展示。"""
        if not self.channel_videos:
            return True
        new_title = (video_data.get('title') or '').strip().lower()
        if not new_title:
            return True
        for existing_video in self.channel_videos:
            existing_title = (existing_video.get('title') or '').strip().lower()
            if existing_title == new_title:
                return False
        return True


    def _parse_relative_time_to_yyyymmdd(self, s):
        """从相对时间字符串解析出近似 YYYYMMDD。如 "1 day ago"->昨天, "2 weeks ago"->14天前, "3 months ago"->90天前。
        下载时再用精确日期更新。"""
        if not s or not isinstance(s, str):
            return ''
        s = s.strip().lower()
        if not s:
            return ''
        # 匹配 X second(s)/minute(s)/hour(s)/day(s)/week(s)/month(s)/year(s) ago，及中文
        multipliers = {
            'second': 1/3600, 'sec': 1/3600, '秒': 1/3600,
            'minute': 1/60, 'min': 1/60, '分钟': 1/60, '分': 1/60,
            'hour': 1, 'hr': 1, '小时': 1, '时': 1,
            'day': 24, '天': 24,
            'week': 24*7, '周': 24*7,
            'month': 30*24, '月': 30*24,
            'year': 365*24, '年': 365*24,
        }
        for unit, hours_per in multipliers.items():
            if unit not in s:
                continue
            m = re.search(r'(\d+)\s*' + re.escape(unit) + r's?\s*(ago|前)?', s, re.I)
            if m:
                n = int(m.group(1))
                hours = n * hours_per
                t = datetime.now() - timedelta(hours=hours)
                return t.strftime('%Y%m%d')
        return ''

    def _entry_upload_date_fallback(self, entry):
        """从 entry 提取 upload_date：优先 upload_date，其次 release_timestamp/timestamp，再试相对时间字符串。"""
        ud = (entry.get('upload_date') or '').strip()
        if ud:
            if len(ud) == 10 and '-' in ud:
                return ud.replace('-', '')
            if len(ud) >= 8:
                return ud[:8]
        ts = entry.get('release_timestamp') or entry.get('timestamp')
        if ts is not None:
            try:
                t = datetime.fromtimestamp(int(ts))
                return t.strftime('%Y%m%d')
            except (ValueError, OSError):
                pass
        for v in entry.values():
            if isinstance(v, str) and ('ago' in v.lower() or '前' in v):
                r = self._parse_relative_time_to_yyyymmdd(v)
                if r:
                    return r
        return ''

    def list_hot_videos(self, channel_url, max_videos=5000, min_view_count=500):
        self._check_and_update_cookies()

        try:
            # 使用基础选项，包含 cookies 支持
            # approximate_date：从频道页相对时间（如 "2 weeks ago"）估算 upload_date，一次请求即可拿到
            # 否则 flat 抓取无 upload_date，需逐个视频请求才能拿到精确日期
            ydl_opts = self._get_ydl_opts_base(
                quiet=False,
                extract_flat='in_playlist',
                skip_download=True,
                extractor_args={'youtubetab': ['approximate_date']},
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)

            channel_name = self.get_channel_name(info)

            with open(f'{self.youtube_dir}/work/info_{channel_name}.json', 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
        
            if not info or 'entries' not in info:
                return None

            self.channel_list_json = f"{self.youtube_dir}/list/{channel_name}.json.txt"
            if os.path.exists(self.channel_list_json):
                with open(self.channel_list_json, 'r', encoding='utf-8') as f:
                    self.channel_videos = json.load(f)
                    _normalize_channel_videos_story_field_to_str(self.channel_videos)
                    self.latest_date = max(
                                            (
                                                datetime.strptime(v["upload_date"], "%Y%m%d")
                                                for v in self.channel_videos
                                                if v.get("upload_date")
                                            ),
                                            default=None
                                        )                    
            else:
                self.channel_videos = []

            for count, entry in enumerate(info['entries']):
                if count >= max_videos:
                    break

                if entry:
                    video_url = entry.get('url', '') or entry.get('webpage_url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                    video_id = entry.get('id', '')
                    
                    # 首先尝试使用 entry 中的基本信息
                    video_data = None
                    if entry.get('view_count') is not None and entry.get('title'):
                        # entry 中已有足够信息，直接使用；upload_date 空时用相对时间推算（下载时再更新精确值）
                        ud = entry.get('upload_date', '') or self._entry_upload_date_fallback(entry)
                        if isinstance(ud, str) and len(ud) == 10 and '-' in ud:
                            ud = ud.replace('-', '')
                        video_data = {
                            'title': entry.get('title', 'Unknown Title'),
                            'url': video_url,
                            'id': video_id,
                            'duration': entry.get('duration', 0),
                            'view_count': entry.get('view_count', 0),
                            'uploader': entry.get('uploader', channel_name),
                            'channel': channel_name,
                            'channel_id': entry.get('channel_id', ''),
                            'upload_date': ud[:8] if ud else '',
                            'thumbnail': entry.get('thumbnail', ''),
                            'description': entry.get('description', '')[:200] if entry.get('description') else ''
                        }
                        print(f"✓ {count} -- {video_data['title'][:50]} -- {video_data['view_count']:,} 观看" + (f" ({ud[:8]})" if ud else "") + " (使用列表信息)")
                    else:
                        # entry 中信息不足，尝试获取详细信息
                        try:
                            video_data = self.get_video_detail(video_url, channel_name)
                            print(f"✓ {count} -- {video_data['title'][:50]} -- {video_data['view_count']:,} 观看")
                        except Exception as e:
                            error_msg = str(e)
                            print(f"⚠️ 跳过视频: {error_msg}")
                            continue
                    
                    if video_data:
                        is_new_video = self.is_video_new(video_data)
                        if is_new_video:
                            self.channel_videos.append(video_data)
            
            self.channel_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
            self.channel_videos = [video for video in self.channel_videos if video.get('view_count', 0) >= min_view_count]
            self.latest_date = max(
                                    (
                                        datetime.strptime(v["upload_date"], "%Y%m%d")
                                        for v in self.channel_videos
                                        if v.get("upload_date")
                                    ),
                                    default=None
                                )                    

            with open(self.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.channel_videos, f, ensure_ascii=False, indent=2)

            return channel_name
            
        except Exception as e:
            print(f"❌ 获取视频列表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # YouTube 元数据字段：更新列表时从抓取结果覆盖，不覆盖用户添加的 audio_path/status/topic_* 等
    YOUTUBE_META_FIELDS = ('title', 'url', 'duration', 'view_count', 'uploader', 'channel', 'channel_id', 'upload_date', 'thumbnail', 'description')

    def fetch_channel_new_videos(self, channel_url, max_videos=5000):
        """抓取频道视频列表，返回 (新视频列表, 全部抓取数据 by_id)。
        全部抓取数据用于更新已有视频的观看次数等信息，不浪费本次调用。"""
        self._check_and_update_cookies()
        try:
            # approximate_date：从频道页相对时间估算 upload_date，一次请求即可拿到
            ydl_opts = self._get_ydl_opts_base(
                quiet=False,
                extract_flat='in_playlist',
                skip_download=True,
                extractor_args={'youtubetab': ['approximate_date']},
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
            if not info or 'entries' not in info:
                return [], {}
            channel_name = self.get_channel_name(info)
            new_videos = []
            all_fetched_by_id = {}
            for count, entry in enumerate(info['entries']):
                if count >= max_videos:
                    break
                if not entry:
                    continue
                video_url = entry.get('url', '') or entry.get('webpage_url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                video_id = entry.get('id', '')
                video_data = None
                if entry.get('view_count') is not None and entry.get('title'):
                    # 优先 entry.upload_date，空则用相对时间推算（1天=24h, 1周=24*7h, 3月=3*30*24h），最后才请求 get_video_detail
                    ud = entry.get('upload_date', '') or self._entry_upload_date_fallback(entry) or ''
                    if isinstance(ud, str) and len(ud) == 10 and '-' in ud:
                        ud = ud.replace('-', '')  # YYYY-MM-DD -> YYYYMMDD
                    video_data = {
                        'title': entry.get('title', 'Unknown Title'),
                        'url': video_url,
                        'id': video_id,
                        'duration': entry.get('duration', 0),
                        'view_count': entry.get('view_count', 0),
                        'uploader': entry.get('uploader', channel_name),
                        'channel': channel_name,
                        'channel_id': entry.get('channel_id', ''),
                        'upload_date': ud[:8] if ud else '',
                        'thumbnail': entry.get('thumbnail', ''),
                        'description': entry.get('description', '')[:200] if entry.get('description') else ''
                    }
                    # 仍无 upload_date 时再请求 get_video_detail 补全（下载时也会更新精确值）
                    if not video_data['upload_date']:
                        try:
                            full = self.get_video_detail(video_url, channel_name)
                            if full and full.get('upload_date'):
                                video_data['upload_date'] = (full['upload_date'] or '').replace('-', '')[:8]
                                video_data['thumbnail'] = full.get('thumbnail') or video_data['thumbnail']
                        except Exception:
                            pass
                    print(f"✓ {count} -- {video_data['title'][:50]} -- {video_data['view_count']:,} 观看" + (f" ({video_data.get('upload_date', '')[:8]})" if video_data.get('upload_date') else ""))
                else:
                    try:
                        video_data = self.get_video_detail(video_url, channel_name)
                        if video_data and video_data.get('upload_date'):
                            ud = video_data['upload_date']
                            if isinstance(ud, str) and len(ud) == 10 and '-' in ud:
                                video_data['upload_date'] = ud.replace('-', '')[:8]
                        print(f"✓ {count} -- {video_data['title'][:50]} -- {video_data['view_count']:,} 观看")
                    except Exception as e:
                        print(f"⚠️ 跳过视频: {e}")
                        continue
                if video_data:
                    all_fetched_by_id[video_id] = video_data
                    if self.is_video_new(video_data):
                        new_videos.append(video_data)
            return new_videos, all_fetched_by_id
        except Exception as e:
            print(f"❌ 抓取视频列表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None  # None 表示出错；([] , {}) 表示无新视频

    def _progress_hook(self, d):
        """下载进度回调函数"""
        if d['status'] == 'downloading':
            if 'total_bytes' in d and d['total_bytes']:
                percent = d['downloaded_bytes'] / d['total_bytes'] * 100
                speed = d.get('speed', 0)
                if speed:
                    speed_mb = speed / 1024 / 1024
                    print(f"📥 下载进度: {percent:.1f}% - 速度: {speed_mb:.1f} MB/s")
                else:
                    print(f"📥 下载进度: {percent:.1f}%")
            else:
                print(f"📥 下载中... {d.get('downloaded_bytes', 0)} bytes")
        elif d['status'] == 'finished':
            print(f"✅ 下载完成: {d.get('filename', 'Unknown file')}")
        elif d['status'] == 'error':
            print(f"❌ 下载错误: {d.get('error', 'Unknown error')}")



    def upload_video(self, file_path, thumbnail_path, title, description, language, script_path, secret_key, channel_id, categoryId, tags, privacy="unlisted"):
        scopes = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]

        # 区分不同频道的 token 文件
        token_file = f"config/token_{channel_id}.json"
        credentials = None

        # 检查是否存在已保存的凭证
        if os.path.exists(token_file):
            credentials = Credentials.from_authorized_user_file(token_file, scopes)
        
        # 如果没有有效凭证，则启动 OAuth 2.0 登录流程
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                # the cient secret json is now just under fold config.get_channel_path(channel_id)
                client_secret_file = os.path.join(config.get_channel_path(channel_id), secret_key)
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(client_secret_file, scopes)
                # 运行时，浏览器会自动打开，请在浏览器中选择您想上传到的频道
                credentials = flow.run_local_server(port=8080)
            
            # 保存凭证以备下次使用
            with open(token_file, 'w') as token:
                token.write(credentials.to_json())

        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

        # Map language codes to YouTube's language format
        language_mapping = {
            "en": "en",
            "zh": "zh-CN",
            "tw": "zh-TW", 
            "ja": "ja",
            "ko": "ko",
            "es": "es",
            "fr": "fr",
            "de": "de",
            "pt": "pt",
            "ru": "ru",
            "ar": "ar"
        }
        
        # Get the proper YouTube language code
        youtube_language = language_mapping.get(language, language)

        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": categoryId,
                "defaultLanguage": youtube_language,  # Video language
                "defaultAudioLanguage": youtube_language  # Audio language
            },
            "status": {
                "privacyStatus": privacy,  # "private", "unlisted", or "public"
                "selfDeclaredMadeForKids": False,  # ✅ FIXED: Use correct field for "made for kids"
                "containsSyntheticMedia": True  # ✅ NEW: Set "Altered content" to YES
            },
            # ✅ NEW: Add localizations for title and description language
            "localizations": {
                youtube_language: {
                    "title": title,
                    "description": description
                }
            }
        }

        media_file = googleapiclient.http.MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)

        request = youtube.videos().insert(
            part="snippet,status,localizations",  # ✅ UPDATED: Include localizations part
            body=request_body,
            media_body=media_file
        )

        response = request.execute()
        video_id = response["id"]
        print("✅ Upload successful! Video ID:", video_id)
        print(f"📝 Video settings applied:")
        print(f"   - Made for Kids: {request_body['status']['selfDeclaredMadeForKids']}")
        print(f"   - Altered Content: {request_body['status']['containsSyntheticMedia']}")
        print(f"   - Video Language: {youtube_language}")
        print(f"   - Title/Description Language: {youtube_language}")

        # 上传缩略图（如果提供了thumbnail_path）
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                self.upload_thumbnail(youtube, video_id, thumbnail_path)
            except Exception as e:
                print(f"⚠️ 缩略图上传失败: {e}")

        # 上传字幕文件（如果提供了script_path）
        if script_path and os.path.exists(script_path):
            try:
                # Use the same language for subtitles
                self.upload_subtitle(youtube, video_id, script_path, youtube_language)
            except Exception as e:
                print(f"⚠️ 字幕上传失败: {e}")

        return video_id


    def upload_thumbnail(self, youtube, video_id, thumbnail_path):
        """上传缩略图到YouTube视频"""
        media_file = googleapiclient.http.MediaFileUpload(
            thumbnail_path,
            mimetype="image/jpeg",
            resumable=True
        )

        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=media_file
        )

        response = request.execute()
        print(f"✅ 缩略图上传成功! Video ID: {video_id}")
        return response


    def upload_subtitle(self, youtube, video_id, script_path, language):
        """上传字幕文件到YouTube视频"""
        subtitle_body = {
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": f"Subtitles ({language})",
            }
        }

        media_file = googleapiclient.http.MediaFileUpload(
            script_path, 
            mimetype="text/plain",
            resumable=True
        )

        request = youtube.captions().insert(
            part="snippet",
            body=subtitle_body,
            media_body=media_file
        )

        response = request.execute()
        print(f"✅ 字幕上传成功! Caption ID: {response['id']}")
        return response["id"]


    def pick_best_caption_language(self, all_languages):
        """优先选择中文，其次英文；若无则返回 None"""
        if not all_languages:
            return None
        zh_langs = [l for l in all_languages if l and (l.startswith('zh') or l in ('zh-Hans', 'zh-Hant', 'zh-CN', 'zh-TW'))]
        en_langs = [l for l in all_languages if l and l.startswith('en')]
        if zh_langs:
            return zh_langs[0]
        if en_langs:
            return en_langs[0]
        return all_languages[0]

    def try_download_caption_only(self, video_detail, target_lang):
        """仅尝试下载字幕，不 fallback 到音频转录；成功返回路径，失败返回 None"""
        if not target_lang or not self.cookie_file:
            return None
        video_url = video_detail.get('url', '')
        if not video_url:
            return None
        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        ydl_opts = self._get_ydl_opts_base(
            skip_download=True,
            writesubtitles=True,
            writeautomaticsub=True,
            subtitleslangs=[target_lang],
            subtitlesformat="srt",
            outtmpl=download_prefix,
            quiet=True,
            no_warnings=True,
        )
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            src_path = f"{download_prefix}.{target_lang}.srt"
            if os.path.exists(src_path):
                print(f"✅ 已下载字幕：语言 {target_lang}")
                return src_path
        except Exception as e:
            print(f"⚠️ 字幕下载失败: {e}")
        return None



# YouTube GUI管理类
class MediaGUIManager:
    """YouTube GUI管理器 - 处理所有YouTube相关的GUI对话框"""
    
    def __init__(self, root, channel_path, pid, tasks, log_to_output_func, download_output, language):
        self.root = root
        self.channel_path = channel_path
        self.youtube_dir = f"{channel_path}/Download"
        os.makedirs(self.youtube_dir, exist_ok=True)
        os.makedirs(f"{self.youtube_dir}/list", exist_ok=True)
        os.makedirs(f"{self.youtube_dir}/media", exist_ok=True)
        os.makedirs(f"{self.youtube_dir}/work", exist_ok=True)

        self.pid = pid
        self.tasks = tasks
        self.log_to_output = log_to_output_func
        self.download_output = download_output
        self._input_language = (language or 'zh').strip().lower()
        self.language = 'en' if self._input_language == 'en' else 'zh'  # 从首层传入，后续 YT 功能可复用
        
        self.llm_api_local = llm_api.LLMApi(llm_api.LM_STUDIO)
        self.llm_api = llm_api.LLMApi()

        # 创建YoutubeDownloader实例
        self.downloader = MediaDownloader(pid, self.youtube_dir, self.language)
        
        # 跟踪活跃的摘要生成线程，确保对话框关闭时不会丢失数据
        self.active_summary_threads = []
        self.active_threads_lock = threading.Lock()

        self.topic_choices, self.topic_categories, self.tag_features_map = config.load_topics(self.channel_path)
        
        # 初始化主主题分类变量
        self.main_topic_category = None

    def _ask_language(self):
        """弹出语言选择对话框，默认选传入的 input language。返回选中的 key 或 None（取消）"""
        options = [f"{label} ({key})" for key, label in config.LANGUAGES.items()]
        display_to_key = {f"{label} ({key})": key for key, label in config.LANGUAGES.items()}
        default_key = self._input_language if self._input_language in config.LANGUAGES else 'zh'
        default_display = f"{config.LANGUAGES[default_key]} ({default_key})"
        dlg = tk.Toplevel(self.root)
        dlg.title("选择语言")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("320x120")
        dlg.resizable(False, False)
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() - 320) // 2
        y = (dlg.winfo_screenheight() - 120) // 2
        dlg.geometry(f"+{x}+{y}")
        result = [None]
        f = ttk.Frame(dlg, padding=15)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="选择视频/字幕语言（用于下载与转录）:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 8))
        lang_var = tk.StringVar(value=default_display)
        lang_combo = ttk.Combobox(f, textvariable=lang_var, values=options, state="readonly", width=28)
        lang_combo.pack(fill=tk.X, pady=(0, 10))
        lang_combo.set(default_display)
        btn_f = ttk.Frame(f)
        btn_f.pack(fill=tk.X)
        def on_ok():
            display = (lang_var.get() or "").strip()
            if display in display_to_key:
                result[0] = display_to_key[display]
            else:
                result[0] = default_key
            dlg.destroy()
        ttk.Button(btn_f, text="确定", command=on_ok).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_f, text="取消", command=dlg.destroy).pack(side=tk.LEFT)
        dlg.wait_window()
        return result[0]

    def _do_create_new_channel_from_url(self):
        """创建新频道：弹窗输入频道/视频链接，解析出频道名，创建列表（可选获取视频）"""
        url = simpledialog.askstring("创建新频道", "输入 YouTube 频道链接或视频链接：", parent=self.root)
        if not url or not url.strip():
            return None
        url = url.strip()
        try:
            channel_name, channel_url = self.downloader.fetch_channel_info_from_url(url)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"解析链接失败: {e}", parent=self.root))
            return None
        if not channel_name:
            self.root.after(0, lambda: messagebox.showerror("错误", "无法解析频道名称", parent=self.root))
            return None
        new_name = simpledialog.askstring("创建新频道", "频道名称（可修改）:", initialvalue=channel_name, parent=self.root)
        if not new_name or not new_name.strip():
            return None
        channel_name = new_name.strip()
        self.downloader.channel_list_json = f"{self.youtube_dir}/list/{channel_name}.json.txt"
        self.downloader.channel_videos = []
        os.makedirs(os.path.dirname(self.downloader.channel_list_json), exist_ok=True)
        if channel_url and messagebox.askyesno("获取视频", f"是否从该频道获取热门视频列表？\n\n频道: {channel_name}", parent=self.root):
            cn = self.downloader.list_hot_videos(channel_url, max_videos=5000, min_view_count=0)
            if not cn:
                self.root.after(0, lambda: messagebox.showwarning("提示", "获取视频列表失败或为空", parent=self.root))
                return None
        else:
            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        self.downloader.channel_name = channel_name
        for v in self.downloader.channel_videos:
            self.check_video_status(v)
        return True

    def manage_hot_videos(self):
        # 打开时先弹出语言选择，默认使用外层传入的 language
        selected = self._ask_language()
        if selected is None:
            return
        self.language = selected
        self.downloader.language = selected

        # 查找所有热门视频JSON文件
        pattern = f"{self.youtube_dir}/list/*.json.txt"
        json_files = glob.glob(pattern)
        
        # 无已有文件时，直接进入创建新频道流程
        if not json_files:
            if self._do_create_new_channel_from_url():
                self._show_channel_videos_dialog()
            return
        
        # 提取频道名称
        channel_data = []
        for json_file in json_files:
            filename = os.path.basename(json_file)
            # 从文件名中提取频道名：频道名.json.txt -> 频道名
            match = re.match(r'(.+?)\.json\.txt', filename)
            if match:
                channel_name = match.group(1)
                # 读取文件获取视频数量
                video_count = 0
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                for encoding in encodings:
                    try:
                        with open(json_file, 'r', encoding=encoding) as f:
                            videos = json.load(f)
                            video_count = len(videos) if isinstance(videos, list) else 0
                        break  # 成功读取后退出循环
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                        if encoding == encodings[-1]:  # 最后一个编码也失败
                            print(f"❌ 读取频道视频列表失败 (尝试了所有编码): {e}")
                        continue
                    except Exception as e:
                        print(f"❌ 读取频道视频列表失败: {e}")
                        break
                
                channel_data.append({
                    'name': channel_name,
                    'file': json_file,
                    'video_count': video_count
                })
        
        if not channel_data:
            messagebox.showwarning("提示", "未找到有效的频道视频列表")
            return
        
        # 准备选项列表和映射，加入【创建新频道】
        channel_choices = []
        choice_to_channel = {}
        for channel in channel_data:
            choice_text = f"{channel['name']} ({channel['video_count']} 个视频)"
            channel_choices.append(choice_text)
            choice_to_channel[choice_text] = channel
        CREATE_NEW = "【创建新频道】"
        channel_choices.append(CREATE_NEW)
        
        # 使用 askchoice 显示选择对话框
        selected_choice = askchoice("选择频道", channel_choices, parent=self.root)
        
        if not selected_choice:
            return  # 用户取消
        if selected_choice == CREATE_NEW:
            # 创建新频道（输入频道/视频链接，解析频道名）
            if self._do_create_new_channel_from_url():
                for v in self.downloader.channel_videos:
                    self.check_video_status(v)
                self._show_channel_videos_dialog()
            return
        
        if selected_choice not in choice_to_channel:
            return
        # 获取选中的频道
        channel = choice_to_channel[selected_choice]
        self.downloader.channel_list_json = channel['file']
        
        # 读出 list：同 title 只保留一条，保留 content + topic_category + topic_subtype 最完整（内容最多）的那条；每条删掉 summary；写回 JSON
        with open(self.downloader.channel_list_json, 'r', encoding='utf-8') as f:
            channel_videos = json.load(f)
        _normalize_channel_videos_story_field_to_str(channel_videos)

        # filter out the videos that have content length less than 100
        channel_videos = [v for v in channel_videos if len(v.get('content', '')) < 180000]
        # save back to the file
        with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
            json.dump(channel_videos, f, ensure_ascii=False, indent=2)

        def _complete_score(v):
            """有 content+topic_category+topic_subtype 的优先；否则按有无 content 及 content 长度比较（同 title 下都没有 category/subtype 时按 content 保留）"""
            c = (v.get('content') or '').strip()
            cat = (v.get('topic_category') or '').strip()
            sub = (v.get('topic_subtype') or '').strip()
            content_len = len(c)
            if cat and sub:
                # 有分类+子类型：完整项，用大基数保证优先于“只有 content”的项
                return 1_000_000 + content_len
            return content_len

        by_title = {}
        for video in channel_videos:
            title = (video.get('title') or '').strip()
            if not title:
                continue
            key = title.lower()
            if key not in by_title:
                by_title[key] = video
                continue
            cur = by_title[key]
            cur_score = _complete_score(cur)
            new_score = _complete_score(video)
            if new_score > cur_score:
                by_title[key] = video

        cleaned = list(by_title.values())

        for video_detail in cleaned:
            video_detail.pop('description', '')
            video_detail.pop('thumbnail', '')
            video_detail.pop('uploader', '')

        with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)

        self.downloader.channel_videos = cleaned
        self.downloader.latest_date = max(
            (
                datetime.strptime(v["upload_date"], "%Y%m%d")
                for v in self.downloader.channel_videos
                if v.get("upload_date")
            ),
            default=None
        )
        if not self.downloader.channel_videos:
            messagebox.showwarning("提示", "视频列表为空")
            return

        self.downloader.channel_name = channel['name']   
        for video in self.downloader.channel_videos:
            self.check_video_status(video)
        # 显示该频道的视频管理对话框
        self._show_channel_videos_dialog()


    def fetch_text_content(self, video_detail):
        text_content = video_detail.get('content', '')
        if text_content and len(text_content) > 100:
            return config.extract_text_from_srt_content(text_content)
            
        srt_file = video_detail.get('transcribed_file', '')
        if not srt_file:
            return None

        if srt_file.endswith('.json'):
            return config.fetch_text_from_json(srt_file)

        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        return config.extract_text_from_srt_content(content)


    def check_video_status(self,video_detail):
        """检查单个视频的下载、转录和摘要状态"""
        status_parts = []
        video_file = None
        audio_file = None
        
        # 使用可重用的方法生成文件名前缀（用于匹配，使用50字符）
        filename_prefix = self.downloader.generate_video_prefix( video_detail )
        
        # 检查是否已下载 - 只扫描 .mp4 文件
        for filename in os.listdir(f"{self.youtube_dir}/media"):
            # 只检查 .mp4 文件
            if not filename_prefix in filename:
                continue
            if filename.lower().endswith('.mp4'):
                video_file = os.path.join(f"{self.youtube_dir}/media", filename)
                video_detail['video_path'] = video_file
            elif filename.lower().endswith('.mp3'):
                audio_file = os.path.join(f"{self.youtube_dir}/media", filename)
                video_detail['audio_path'] = audio_file
            elif filename.lower().endswith('.wav'):
                audio_file = os.path.join(f"{self.youtube_dir}/media", filename)
                a = self.downloader.ffmpeg_audio_processor.to_mp3(audio_file)
                safe_remove(audio_file)
                audio_file = f"{self.youtube_dir}/media/{filename_prefix}.mp3"
                safe_copy_overwrite(a, audio_file)
                video_detail['audio_path'] = audio_file
        
        if video_file and not audio_file:
            a = self.downloader.ffmpeg_audio_processor.extract_audio_from_video(video_file, "mp3")
            audio_file = f"{self.youtube_dir}/media/{filename_prefix}.mp3"
            safe_copy_overwrite(a, audio_file)
            video_detail['audio_path'] = audio_file

        if video_file or audio_file:
            status_parts.append("✅ 已下载")
        else:
            status_parts.append("⬜ 未下载")
        
        # 检查是否已转录 - 检查 .srt 文件（转录生成的字幕文件）
        has_transcript = video_detail.get('content', '') and len(video_detail.get('content', '')) > 100
        if not has_transcript:
            for filename in os.listdir(f"{self.youtube_dir}/media"):
                if filename_prefix in filename and (filename.endswith('.srt') or filename.endswith('.json')):
                    video_detail['transcribed_file'] = os.path.join(f"{self.youtube_dir}/media", filename)
                    has_transcript = True
                    break
        if has_transcript:
            status_parts.append("✅ 已转录")
        else:
            status_parts.append("⬜ 未转录")
        
        
        return " ".join(status_parts), video_file, audio_file


    def get_video_detail(self, video_url):
        video_detail = None
        for video in self.downloader.channel_videos:
            if video.get('url') == video_url:
                video_detail = video
                break
        return video_detail


    def match_media_file(self, video_detail, field, postfixs):
        prefix = self.downloader.generate_video_prefix(video_detail)
        for file in os.listdir(f"{self.youtube_dir}/media"):
            if not prefix in file:
                continue
            for postfix in postfixs:
                if file.endswith(postfix):
                    file = os.path.join(f"{self.youtube_dir}/media", file)
                    video_detail[field] = file
                    return video_detail
        return None


    def update_text_content(self, video_detail, transcribed_file=None):
        if not video_detail:
            return None

        text_content = video_detail.get('content', '')
        if not text_content or not text_content.strip():
            if transcribed_file:
                video_detail['transcribed_file'] = transcribed_file
            else:    
                transcribed_file = video_detail.get('transcribed_file', '')
                if not transcribed_file:
                    return video_detail
            text_content = self.fetch_text_content(video_detail)
            video_detail["content"] = text_content

        return video_detail


    def prepare_category_for_content(self, video_detail, text_content, topic_choices):
        # LLM API 调用在信号量保护下（已在上层 with 语句中）
        result = self.llm_api_local.generate_json(
            config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(language='Chinese', topic_choices=topic_choices), 
            text_content,
            expect_list=False
        )
        if result:
            if result.get('topic_subtype', '') and result.get('topic_subtype', '').strip():
                video_detail['topic_subtype'] = result.get('topic_subtype', '')
                video_detail.pop('topic_type', None)
            if result.get('topic_category', '') and result.get('topic_category', '').strip():
                video_detail['topic_category'] = result.get('topic_category', '')
            raw_tags = result.get('tags')
            if isinstance(raw_tags, list):
                tags_list = [str(t).strip() for t in raw_tags if t and str(t).strip()]
                if tags_list:
                    video_detail['tags'] = tags_list
            elif isinstance(raw_tags, str) and raw_tags.strip():
                video_detail["tags"] = parse_tags_list(raw_tags)
            # 保存到文件（在锁内，确保数据一致性）
            try:
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                print(f"✅ 摘要生成完成并已保存: {video_detail.get('title', 'Unknown')[:50]}")
            except Exception as e:
                print(f"❌ 保存 channel_list_json 失败: {e}")



    def _show_channel_videos_dialog(self):
        # 创建视频管理对话框
        dialog = tk.Toplevel(self.root)
        dialog.title(f"热门视频管理 - {self.downloader.channel_name}")
        dialog.geometry("1600x650")
        dialog.transient(self.root)
        
        # 顶部信息和控制栏
        top_frame = ttk.Frame(dialog)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 第一行：信息标签和刷新按钮
        info_frame = ttk.Frame(top_frame)
        info_frame.pack(fill=tk.X, pady=(0, 5))
        
        info_text = f"频道: {self.downloader.channel_name} | 共 {len(self.downloader.channel_videos)} 个视频"
        info_label = ttk.Label(info_frame, text=info_text, font=("Arial", 12, "bold"))
        info_label.pack(side=tk.LEFT)
        
        #for video in self.downloader.channel_videos:
        #    video.pop('component_tags', None)
        #       transcribed_file = video.get('transcribed_file', '')
        #    if transcribed_file:
        #        content = config.fetch_text_from_json(transcribed_file)
        #        # if content is None or empty, then remove this video from self.downloader.channel_videos
        #        if content:
        #            video['content'] = content
        #        else:
        #            self.downloader.channel_videos.remove(video)
        #
        #with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
        #    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
        
        # 添加刷新按钮
        ttk.Button(info_frame, text="🔄 刷新", command=lambda: populate_tree()).pack(side=tk.RIGHT, padx=5)
        
        # 第二行：过滤和排序控制
        control_frame = ttk.Frame(top_frame)
        control_frame.pack(fill=tk.X)
        
        # 最小观看次数过滤
        ttk.Label(control_frame, text="最小观看次数:").pack(side=tk.LEFT, padx=(0, 5))
        min_view_var = tk.StringVar(value="0")
        min_view_entry = ttk.Entry(control_frame, textvariable=min_view_var, width=15)
        min_view_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # 排序方式
        sort_mode_var = tk.StringVar(value="hot_degree")  # 默认按热度排序
        
        def toggle_sort():
            """切换排序方式"""
            current_mode = sort_mode_var.get()
            if current_mode == "hot_degree":
                sort_mode_var.set("view_count")
                sort_button.config(text="排序: 观看次数 ↓")
            elif current_mode == "view_count":
                sort_mode_var.set("upload_date")
                sort_button.config(text="排序: 上传日期 ↓")
            elif current_mode == "upload_date":
                sort_mode_var.set("duration")
                sort_button.config(text="排序: 时长 ↓")
            else:  # duration
                sort_mode_var.set("hot_degree")
                sort_button.config(text="排序: 热度 ↓")
            populate_tree()
        
        sort_button = ttk.Button(control_frame, text="排序: 热度 ↓", command=toggle_sort)
        sort_button.pack(side=tk.LEFT, padx=5)
        
        # 绑定回车键自动应用过滤
        min_view_entry.bind('<Return>', lambda e: populate_tree())
        
        # Smart Select 功能
        ttk.Label(control_frame, text="智能选择:").pack(side=tk.LEFT, padx=(10, 5))
        smart_select_var = tk.StringVar()
        smart_select_entry = ttk.Entry(control_frame, textvariable=smart_select_var, width=20)
        smart_select_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        # 添加主题类型选择
        # 从 self.topic_choices 中提取 topic_category 字段并去重
        
        topic_category_var = tk.StringVar()
        topic_category_combo = ttk.Combobox(control_frame, textvariable=topic_category_var, values=self.topic_categories, state="readonly", width=20)
        topic_category_combo.pack(side=tk.LEFT, padx=(0, 5))
        
        # 绑定选择事件，将选中的值保存到 self.main_topic_category
        def on_topic_category_selected(event=None):
            selected_value = topic_category_var.get()
            if selected_value:
                self.main_topic_category = selected_value
        
        topic_category_combo.bind('<<ComboboxSelected>>', on_topic_category_selected)
        
        # 关联视频 ID（| 分隔，与摘要窗口「标注」同一字段；双向关联由「找类似案例」写入）
        ttk.Label(control_frame, text="关联ID:").pack(side=tk.LEFT, padx=(10, 5))
        batch_related_var = tk.StringVar(value="")
        batch_related_entry = ttk.Entry(control_frame, textvariable=batch_related_var, width=26)
        batch_related_entry.pack(side=tk.LEFT, padx=(0, 4))

        def on_apply_related_batch():
            val = (batch_related_var.get() or "").strip()
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请先选择要设置关联 ID 的视频", parent=dialog)
                return
            selected_urls = set()
            for item in selected_items:
                item_tags = _treeview_item_tags_safe(tree, item)
                if item_tags:
                    url = item_tags[0]
                    selected_urls.add(url)
                    vd = self.get_video_detail(url)
                    if vd:
                        vd["status"] = val
            with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            populate_tree()
            for item in tree.get_children():
                item_tags = _treeview_item_tags_safe(tree, item)
                if item_tags and item_tags[0] in selected_urls:
                    tree.selection_add(item)

        ttk.Button(control_frame, text="应用到选中", command=on_apply_related_batch).pack(side=tk.LEFT, padx=(0, 5))

        # 画面风格：与欢迎屏一致，只读展示（LAST_VISUAL_STYLE）
        ttk.Label(control_frame, text="画面风格:").pack(side=tk.LEFT, padx=(10, 5))
        ttk.Label(control_frame, text=project_manager.LAST_VISUAL_STYLE, width=22, anchor="w").pack(side=tk.LEFT, padx=(0, 5))


        def smart_select():
            """根据输入文本智能选择匹配的视频（在 title 和 content 中搜索关键字）"""
            search_text = smart_select_var.get().strip().lower()
            if not search_text:
                return
            
            tree.selection_remove(*tree.selection())
            
            # 在 title 和 content 中搜索关键字，匹配则选中
            matched_count = 0
            for item in tree.get_children():
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                url = item_tags[0]
                video_detail = self.get_video_detail(url)
                if not video_detail:
                    continue
                title = (video_detail.get('title') or '').strip().lower()
                content = (video_detail.get('content') or video_detail.get('summary') or '').strip().lower()
                if search_text in title or search_text in content:
                    tree.selection_add(item)
                    matched_count += 1
            
            selected = tree.selection()
            stats_label.config(text=f"已选择: {len(selected)} 个视频")
            
            if matched_count > 0:
                first_matched = None
                for item in tree.get_children():
                    if item in tree.selection():
                        first_matched = item
                        break
                if first_matched:
                    tree.see(first_matched)
                    tree.focus(first_matched)
            
        # 绑定回车键
        smart_select_entry.bind('<Return>', lambda e: smart_select())
        
        # 创建Treeview显示视频列表
        columns = ("title", "views", "duration", "upload_date", "status", "summary", "story", "topic_category", "topic_subtype", "tags", "mark")
        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", 
                            yscrollcommand=scrollbar.set, selectmode="extended")
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        
        # 设置列标题和宽度
        tree.heading("#0", text="序号")
        tree.heading("title", text="标题")
        tree.heading("views", text="观看次数")
        tree.heading("duration", text="时长")
        tree.heading("upload_date", text="上传日期")
        tree.heading("status", text="状态")
        tree.heading("summary", text="摘要")
        tree.heading("story", text="Story")
        tree.heading("topic_category", text="主题分类")
        tree.heading("topic_subtype", text="主题子类型")
        tree.heading("tags", text="标签")
        tree.heading("mark", text="关联ID")
        
        tree.column("#0", width=30, anchor="center")
        tree.column("title", width=360, anchor="w")
        tree.column("views", width=50, anchor="e")
        tree.column("duration", width=30, anchor="center")
        tree.column("upload_date", width=50, anchor="center")
        tree.column("status", width=110, anchor="center")
        tree.column("summary", width=20, anchor="center")
        tree.column("story", width=20, anchor="center")
        tree.column("topic_category", width=150, anchor="w")
        tree.column("topic_subtype", width=100, anchor="w")
        tree.column("tags", width=220, anchor="w")
        tree.column("mark", width=120, anchor="w")
        

        def populate_tree():
            """填充或刷新树视图"""
            # 清空现有项目
            for item in tree.get_children():
                tree.delete(item)
            
            # 获取最小观看次数
            try:
                min_view_count = int(min_view_var.get() or "0")
            except ValueError:
                min_view_count = 0
            
            # 过滤视频：只显示观看次数大于等于最小值的视频
            filtered_videos = []
            for video in self.downloader.channel_videos:
                view_count = video.get('view_count', 0)
                if view_count >= min_view_count:
                    filtered_videos.append(video)
            
            # 排序视频
            sort_mode = sort_mode_var.get()
            if sort_mode == "hot_degree":
                # 计算每个视频的热度值（每日观看次数）
                def calculate_hot_degree(video):
                    view_count = video.get('view_count', 0)
                    upload_date = video.get('upload_date', '')
                    if upload_date and len(upload_date) == 8:
                        try:
                            # 热度 = 观看次数 / 日期范围天数
                            date_obj = datetime.strptime(upload_date, '%Y%m%d')
                            days = (self.downloader.latest_date - date_obj).days + 1
                            return view_count / (days if days > 0 else 1)
                        except:
                            pass
                    # 如果无法计算，返回0
                    return 0.0
                
                filtered_videos.sort(key=calculate_hot_degree, reverse=True)

            elif sort_mode == "upload_date":
                # 按上传日期降序排序（最新的在前）
                filtered_videos.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
            elif sort_mode == "view_count":
                # 按观看次数降序排序
                filtered_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
            elif sort_mode == "duration":
                # 按时长降序排序（时长长的在前）
                def _duration_key(v):
                    d = v.get('duration') or 0
                    if isinstance(d, str):
                        d = float(d) if d else 0
                    return int(float(d))
                filtered_videos.sort(key=_duration_key, reverse=True)
            
            # 检查视频状态并填充数据
            downloaded_count = 0
            transcribed_count = 0
            summarized_count = 0
            hottest_degree = 0.0
            
            for idx, video in enumerate(filtered_videos, 1):
                #video.pop('text_content', None)
                # 格式化时长
                duration_sec = video.get('duration', 0)
                # 确保 duration_sec 是数字类型，并转换为整数
                if duration_sec:
                    if isinstance(duration_sec, str):
                        duration_sec = float(duration_sec)
                    duration_sec = int(float(duration_sec))  # 转换为整数
                    minutes = duration_sec // 60
                    seconds = duration_sec % 60
                    duration_str = f"{minutes}:{seconds:02d}"
                else:
                    duration_str = "N/A"
                
                # 格式化观看次数
                view_count = video.get('view_count', 0)
                view_str = f"{view_count:,}" if view_count else "N/A"
                
                # 格式化上传日期（支持 YYYYMMDD 或 YYYY-MM-DD，有日期即显示，不再依赖 latest_date）
                ud_raw = video.get('upload_date') or ''
                upload_date = str(ud_raw).strip() if ud_raw else ''
                ud_8 = (upload_date.replace('-', '')[:8] if upload_date else '')
                if ud_8 and len(ud_8) == 8:
                    upload_date_str = f"{ud_8[:4]}-{ud_8[4:6]}-{ud_8[6:]}"
                    if self.downloader.latest_date:
                        try:
                            days = (self.downloader.latest_date - datetime.strptime(ud_8, '%Y%m%d')).days + 1
                            degree = view_count / (days if days > 0 else 1)
                            if hottest_degree < degree:
                                hottest_degree = degree
                        except (ValueError, TypeError):
                            pass
                else:
                    upload_date_str = "N/A"
                
                # 检查视频状态
                status_str, video_file, audio_file = self.check_video_status(video)
                
                # 统计
                if "✅ 已下载" in status_str:
                    downloaded_count += 1
                if "✅ 已转录" in status_str:
                    transcribed_count += 1
                if "✅ 已摘要" in status_str:
                    summarized_count += 1
                
                # 获取主题相关字段
                topic_category = video.get('topic_category', '')
                topic_subtype = video.get('topic_subtype', '')
                problem_tags = video.get('tags', '')
                if isinstance(problem_tags, list):
                    problem_tags = " | ".join(str(t) for t in problem_tags if t is not None)
                elif not isinstance(problem_tags, str):
                    problem_tags = str(problem_tags) if problem_tags else ""

                tag_cell = problem_tags
                if len(tag_cell) > 120:
                    tag_cell = tag_cell[:120] + "…"

                # status：用户可编辑的关联视频 ID，| 分隔（旧版 1/2/3 或下载 success/failed 仍显示为可读）
                user_status = _status_display_for_related_field(video.get("status", ""))
                if len(user_status) > 80:
                    user_status = user_status[:77] + "..."
                summary_mark = "✓" if (video.get('summary') or '').strip() else ""
                story_mark = "✓" if (video.get('story') or '').strip() else ""
                tree.insert("", tk.END, text=str(idx), 
                           values=(
                               video.get('title', 'Unknown')[:60],
                               view_str,
                               duration_str,
                               upload_date_str,
                               status_str,
                               summary_mark,
                               story_mark,
                               topic_category[:30] if topic_category else '',
                               topic_subtype[:30] if topic_subtype else "",
                               tag_cell,
                               user_status
                           ),
                           tags=(   video.get('url', ''), 
                                    video.get('title', 'Unknown'), 
                                    video_file or '', 
                                    audio_file or '', 
                                    str(view_count), 
                                    video.get('upload_date', ''), 
                                    str(duration_sec), 
                                    self.downloader.channel_name)
                                )
            
            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)

            # 更新顶部信息标签
            info_text = f"频道: {self.downloader.channel_name} | 共 {len(filtered_videos)}/{len(self.downloader.channel_videos)} 个视频 | 已下载: {downloaded_count} | 已转录: {transcribed_count} | 已摘要: {summarized_count} | 热度: {hottest_degree:.2f}"
            info_label.config(text=info_text)
        

        # 初始填充树视图
        populate_tree()
        
        # 选择统计标签
        stats_label = ttk.Label(dialog, text="已选择: 0 个视频", font=("Arial", 10))
        stats_label.pack(pady=5)
        
        def update_selection_count():
            selected = tree.selection()
            stats_label.config(text=f"已选择: {len(selected)} 个视频")
        tree.bind("<<TreeviewSelect>>", lambda e: update_selection_count())
        

        def delete_selected_videos():
            """删除选中的视频：从列表移除并删除相关文件"""
            selected_items = tree.selection()
            if not selected_items:
                return
            
            # 确认删除
            if not messagebox.askyesno("确认删除", f"确定要删除 {len(selected_items)} 个视频吗？\n\n这将从列表中移除并删除相关的文件（mp4、srt、json）。",
                                           parent=dialog):
                return
            
            deleted_count = 0
            failed_count = 0
            
            # 收集要删除的视频ID和文件
            videos_to_remove = []
            files_to_delete = []
            
            for item in selected_items:
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                
                video_detail = self.get_video_detail(item_tags[0])
                videos_to_remove.append(video_detail)
                filename_prefix = self.downloader.generate_video_prefix(video_detail)
                for filename in os.listdir(f"{self.youtube_dir}/media"):
                    if filename_prefix in filename:
                        file_path = os.path.join(f"{self.youtube_dir}/media", filename)
                        # 收集SRT和TXT文件
                        if filename.endswith('.srt') or filename.endswith('.json'):
                            files_to_delete.append(file_path)
                for filename in os.listdir(f"{self.youtube_dir}/media"):
                    if filename_prefix in filename:
                        file_path = os.path.join(f"{self.youtube_dir}/media", filename)
                        # 收集SRT和TXT文件
                        if filename.endswith('.mp4') or filename.endswith('.mp3') or filename.endswith('.wav'):
                            files_to_delete.append(file_path)
            
            # 删除文件
            for file_path in files_to_delete:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"✅ 已删除文件: {os.path.basename(file_path)}")
            
            # 从videos列表中移除
            for video_detail in videos_to_remove:
                if video_detail in self.downloader.channel_videos:
                    self.downloader.channel_videos.remove(video_detail)
                    deleted_count += 1
            
            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")
            
            # 刷新列表
            populate_tree()
            
            # 显示结果
            if failed_count > 0:
                messagebox.showwarning("删除完成", 
                                          f"已删除 {deleted_count} 个视频\n\n{failed_count} 个文件删除失败",
                                          parent=dialog)
            else:
                messagebox.showinfo("删除完成", 
                                       f"已成功删除 {deleted_count} 个视频及其相关文件",
                                       parent=dialog)
        
        # 绑定Delete键
        def on_key_press(event):
            if event.keysym == 'Delete':
                delete_selected_videos()
        tree.bind('<KeyPress>', on_key_press)
        # 确保tree可以获得焦点以便接收键盘事件
        tree.focus_set()
        # 当点击tree时，确保获得焦点
        tree.bind('<Button-1>', lambda e: tree.focus_set())


        def on_enter_key(event):
            on_focus(event, low_priority=False)

        def on_double_click(event):
            on_focus(event, low_priority=True)

        def on_focus(event, low_priority=False):
            # 处理鼠标事件和键盘事件
            if hasattr(event, 'y') and event.y:
                # 鼠标事件：通过坐标识别行
                item = tree.identify_row(event.y)
            else:
                # 键盘事件：获取当前选中的项
                selected = tree.selection()
                if not selected:
                    return
                item = selected[0]
            
            if not item:
                return

            if item not in tree.selection():
                tree.selection_set(item)
            
            item_tags = _treeview_item_tags_safe(tree, item)
            if not item_tags:
                return
            video_detail = self.get_video_detail(item_tags[0])
            if not video_detail:
                return

            # get index of the selected item & save to a variable
            selected_index = tree.item(item, "text").split(".")[0]
            topic_type = video_detail.get('topic_subtype', '')
            topic_category = video_detail.get('topic_category', '')
            topic_subtype = video_detail.get('topic_subtype', '')
            topic_status = _status_display_for_related_field(video_detail.get("status", ""))
            topic_tags = video_detail.get('tags', '')
            if isinstance(topic_tags, list):
                topic_tags = ' | '.join(topic_tags)
            elif not isinstance(topic_tags, str):
                topic_tags = str(topic_tags) if topic_tags else ''
            if not low_priority or not topic_type or not topic_type.strip() or not topic_category or not topic_category.strip() :
                # show a messagebox to let user know the summary is generating (non-blocking)
                # self.root.after(0, lambda: messagebox.showinfo("提示", "摘要生成中，请稍后...", parent=self.root))
                self.update_text_content(video_detail)
                topic_type = video_detail.get('topic_subtype', '')
                topic_category = video_detail.get('topic_category', '')
                topic_subtype = video_detail.get('topic_subtype', '')
                topic_tags = video_detail.get('tags', '')
                if isinstance(topic_tags, list):
                    topic_tags = ' | '.join(topic_tags)
                elif not isinstance(topic_tags, str):
                    topic_tags = str(topic_tags) if topic_tags else ''

            # show the summary in a new window
            summary_window = tk.Toplevel(dialog)
            summary_window.title(f"{selected_index} - {video_detail['title']} - 摘要")
            summary_window.geometry("1400x1000")
            summary_window.resizable(True, True)
            summary_window.transient(dialog)
            # 创建主框架
            main_frame = ttk.Frame(summary_window, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # 主题信息编辑区域
            topic_frame = ttk.LabelFrame(main_frame, text="主题信息", padding=10)
            topic_frame.pack(fill=tk.X, pady=(0, 10))
            
            # 主题分类选择
            ttk.Label(topic_frame, text="主题分类:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky='w', padx=5, pady=5)
            category_var = tk.StringVar(value=topic_category)
            category_combo = ttk.Combobox(topic_frame, textvariable=category_var, values=self.topic_categories, state="readonly", width=30)
            category_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
            
            # 主题子类型选择
            ttk.Label(topic_frame, text="主题子类型:", font=("Arial", 10, "bold")).grid(row=0, column=2, sticky='w', padx=5, pady=5)
            subtype_var = tk.StringVar(value=topic_subtype)
            subtype_combo = ttk.Combobox(topic_frame, textvariable=subtype_var, values=[], state="readonly", width=30)
            subtype_combo.grid(row=0, column=3, padx=5, pady=5, sticky='ew')
            
            ttk.Label(topic_frame, text="主题标签:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky='nw', padx=5, pady=5)
            tags_var = tk.StringVar(value=topic_tags)
            tags_row = ttk.Frame(topic_frame)
            tags_row.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
            tags_entry = ttk.Entry(tags_row, textvariable=tags_var, width=24)
            tags_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            def _on_tag_pick(feature: str, option: str):
                merged = merge_tag_pick(parse_tags_list(tags_var.get() or ""), feature, option)
                tags_var.set(", ".join(merged))

            def _open_tag_menu():
                m = build_tag_cascade_menu(
                    summary_window,
                    getattr(self, "tag_features_map", None) or {},
                    _on_tag_pick,
                )
                post_menu_below_widget(m, tags_add_btn)

            tags_add_btn = ttk.Button(tags_row, text="添加标签", command=_open_tag_menu)
            tags_add_btn.pack(side=tk.LEFT, padx=(6, 0))

            # 关联视频 ID（| 分隔，网状关系；与列表「关联ID」列同一字段）
            ttk.Label(topic_frame, text="关联视频ID:", font=("Arial", 10, "bold")).grid(row=1, column=2, sticky='w', padx=5, pady=5)
            status_var = tk.StringVar(value=topic_status)
            status_entry = ttk.Entry(topic_frame, textvariable=status_var, width=30)
            status_entry.grid(row=1, column=3, padx=5, pady=5, sticky='ew')
            
            def update_subtypes(*args):
                """根据选择的分类更新子类型选项"""
                selected_category = category_var.get()
                subtypes = []
                if selected_category and self.topic_choices:
                    for item in self.topic_choices:
                        if isinstance(item, dict) and item.get('topic_category') == selected_category:
                            for subtype_item in item.get('topic_subtypes', []):
                                if isinstance(subtype_item, dict):
                                    # 从 topic_subtypes 数组中获取每个项的 topic_subtype 字段
                                    subtype_name = subtype_item.get('topic_subtype', '')
                                    if subtype_name and subtype_name not in subtypes:
                                        subtypes.append(subtype_name)
                subtype_combo['values'] = subtypes
                # 使用 video_detail 当前值，避免闭包中的 topic_subtype 过时（如 do_re_category 刚更新后）
                current_subtype = (video_detail.get('topic_subtype') or subtype_var.get() or '').strip()
                if current_subtype in subtypes:
                    subtype_var.set(current_subtype)
                else:
                    subtype_var.set('')

            def do_re_category():
                """重新分类：重新分类，保存回 video_detail 并持久化"""
                content = video_detail.get("summary", "")
                if not content or not content.strip():
                    content = video_detail.get('content', '')
                    if not content or not content.strip():
                        messagebox.showinfo("提示", "content 不存在或为空", parent=summary_window)
                        return
                self.prepare_category_for_content(video_detail, content, self.topic_choices)
                # 3. 同步 UI 显示
                category_var.set(video_detail.get("topic_category", ""))
                subtype_var.set(video_detail.get("topic_subtype", ""))
                tags_list = video_detail.get("tags", [])
                tags_var.set(", ".join(tags_list) if isinstance(tags_list, list) else str(tags_list or ""))
                update_subtypes()
                refresh_notebooklm_prompt()
                try:
                    populate_tree()
                except Exception:
                    pass


            def do_content_summary():
                if video_detail.get("summary", "").strip():
                    self.root.clipboard_clear()
                    self.root.clipboard_append(video_detail.get("summary", ""))
                    self.root.update()
                    messagebox.showinfo("提示", "summary 已存在，不重新生成", parent=summary_window)
                    do_re_category()
                    return

                text_content = self.fetch_text_content(video_detail)
                if not text_content or not text_content.strip():
                    messagebox.showinfo("提示", "原文不存在或为空", parent=summary_window)
                    return
                # 1. 用 LLM 重写原文
                prompt = config_prompt.REWRITE_MATERIAL_SYSTEM_PROMPT.format(language=config.LANGUAGES[self.language])
                rewritten = self.llm_api_local.generate_text(prompt, text_content)
                if rewritten and rewritten.strip():
                    video_detail["summary"] = rewritten.strip()

                # 4. 弹窗展示概括结果
                self.root.clipboard_clear()
                self.root.clipboard_append(video_detail.get("summary", ""))
                self.root.update()
                messagebox.showinfo("提示", "summary 已存生成", parent=summary_window)
                # 2. 重新分类（更新 topic_category, topic_subtype, tags）
                do_re_category()


            # 绑定事件：用 trace 保证主题分类变更时一定触发子类型更新（<<ComboboxSelected>> 在某些环境下可能不触发）
            def _on_category_var_write(*args):
                update_subtypes()
            category_var.trace_add('write', _on_category_var_write)
            
            # 保存按钮
            def save_story_info():
                """保存主题信息"""
                category = category_var.get().strip()
                subtype = subtype_var.get().strip()
                tags_text = tags_var.get().strip()
                st = status_var.get()
                
                # 解析标签：KEY=value 与旧版纯文本；| 或「逗号+下一段 KEY=」分隔
                tags_list = parse_tags_list(tags_text) if tags_text else []
                
                # 更新视频详情
                if category:
                    video_detail['topic_category'] = category
                else:
                    video_detail.pop('topic_category', None)
                if subtype:
                    video_detail['topic_subtype'] = subtype
                else:
                    video_detail.pop('topic_subtype', None)
                if tags_list:
                    video_detail['tags'] = tags_list
                else:
                    video_detail.pop('tags', None)
                st = (st or "").strip()
                if st:
                    video_detail["status"] = st
                else:
                    video_detail.pop("status", None)

                # 剪贴板有文本时写入 raw_content，再落盘列表
                clip_note = ""
                try:
                    clip_text = (summary_window.clipboard_get() or "").strip()
                except tk.TclError:
                    clip_text = ""
                if clip_text:
                    video_detail["raw_content"] = clip_text
                    clip_note = "（已用剪贴板更新 raw_content）"

                # 保存到文件
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                
                # 刷新树视图（如果对话框还存在）
                try:
                    populate_tree()
                except:
                    pass
                
                messagebox.showinfo("成功", f"主题信息已保存{clip_note}", parent=summary_window)


            def on_raw_start_project():
                try:
                    content = summary_window.clipboard_get()
                except Exception:
                    content = ""
                story_text = video_detail.get('raw_content', '')
                if not story_text:
                    story_text = video_detail.get('summary', '')
                    video_detail['raw_content'] = story_text
                
                if content:
                    # if content is not empty, ask user to confirm if they want to use the content as new story content 
                    if messagebox.askyesno("提示", "剪贴板内容不为空，是否使用剪贴板内容作为新的故事内容？", parent=summary_window):
                        story_text = content
                        # clean the clipboard
                        summary_window.clipboard_clear()
                        summary_window.update()
                        video_detail['raw_content'] = story_text
                        try:
                            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                            dialog.after(0, populate_tree)
                        except Exception:
                            pass

                if not story_text:
                    messagebox.showwarning("提示", "RAW故事内容为空，无法复制风格和人物", parent=summary_window)
                    return

                from project_manager import (
                    create_project_with_initial_raw,
                    LAST_NARRATOR,
                    LAST_VISUAL_STYLE
                )
                ch = os.path.basename(self.channel_path)
                lang = getattr(self, 'language', 'tw') or 'tw'
                result, selected_config = create_project_with_initial_raw(
                    self.root,
                    story_text,
                    ch,
                    lang,
                    LAST_NARRATOR,
                    LAST_VISUAL_STYLE,
                    config_prompt.HARRATOR_DISPLAY_OPTIONS[-1]
                )
                if result == 'new' and selected_config:
                    _pid = selected_config.get('pid', '')
                    if not _pid:
                        return
                    def _open_main_in_same_process():
                        _tk_root = None
                        try:
                            _tk_root = self.root
                            while getattr(_tk_root, 'master', None):
                                _tk_root = _tk_root.master
                            try:
                                self.root.protocol("WM_DELETE_WINDOW", lambda: None)
                            except Exception:
                                pass
                            try:
                                self.root.destroy()
                            except Exception:
                                pass
                            _tk_root.deiconify()
                            import sys
                            _gui_mod = sys.modules.get('GUI') or sys.modules.get('__main__')
                            WorkflowGUI = getattr(_gui_mod, 'WorkflowGUI', None)
                            if WorkflowGUI:
                                WorkflowGUI(_tk_root, initial_pid=_pid)
                            else:
                                messagebox.showerror("错误", "无法加载主界面模块", parent=_tk_root)
                        except Exception as ex:
                            import traceback
                            traceback.print_exc()
                            try:
                                _parent = _tk_root if (_tk_root and _tk_root.winfo_exists()) else None
                                messagebox.showerror("错误", f"打开主界面失败: {ex}", parent=_parent)
                            except Exception:
                                pass
                    self.root.after(100, _open_main_in_same_process)


            def on_find_similar_cases():
                cur_id = _video_youtube_id(video_detail)
                if not cur_id:
                    messagebox.showwarning("提示", "当前视频缺少 YouTube id，无法建立关联", parent=summary_window)
                    return
                ref_sum = (video_detail.get("summary") or "").strip()
                if not ref_sum:
                    messagebox.showwarning("提示", "当前视频摘要为空，请先完成摘要后再找类似案例", parent=summary_window)
                    return

                _channel_key = os.path.basename(self.channel_path)

                reference_filter_prompt = config_channel.get_channel_config(_channel_key).get('channel_prompt', {}).get('prompt_reference_filter', '')
                reference_filter_prompt = reference_filter_prompt.format(topic=video_detail['topic_category'] + " - " + video_detail['topic_subtype'])

                editor = ReferenceEditorDialog(
                    summary_window,
                    current_story=video_detail['summary'],
                    reference_filter=reference_filter_prompt
                )

                prepared = editor.show()
                if not prepared:
                    return
                ch_list = self.downloader.channel_videos
                # 当前视频：把每条参考对应的 YouTube id 合并进 status（| 分隔、去重）
                # 每条参考在 channel_videos 里对应一条：把当前视频 cur_id 合并进其 status
                urls_to_select = []
                for item in prepared:
                    if not isinstance(item, dict):
                        continue
                    ref_v = _find_channel_video_for_reference_item(item, ch_list)
                    ref_yid = ""
                    if ref_v:
                        ref_yid = _video_youtube_id(ref_v)
                        ref_v["status"] = _merge_related_id_status(ref_v.get("status"), cur_id)
                        u = (ref_v.get("url") or "").strip()
                        if u:
                            urls_to_select.append(u)
                    if not ref_yid:
                        ref_yid = _reference_item_youtube_id(item)
                    if ref_yid:
                        video_detail["status"] = _merge_related_id_status(video_detail.get("status"), ref_yid)

                # save the video_detail to the channel_list_json
                with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                # populate the tree, and select the current video & matched reference rows
                _urls = urls_to_select

                def _after_find_similar():
                    populate_tree()
                    try:
                        tree.selection_set(video_detail["url"])
                    except Exception:
                        pass
                    if _urls:
                        try:
                            tree.selection_add(*_urls)
                        except Exception:
                            pass

                dialog.after(0, _after_find_similar)

            # 右侧按钮组：粘贴 NotebookLM 结果启动新项目（从剪贴板读取→保存→启动）、保存主题信息
            button_frame = ttk.Frame(topic_frame)
            button_frame.grid(row=3, column=1, columnspan=3, padx=5, pady=5, sticky='ew')
            right_btns = ttk.Frame(button_frame)
            right_btns.pack(side=tk.RIGHT)
            # 添加标签按钮

            ttk.Button(right_btns, text="启动项目", command=on_raw_start_project).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(right_btns, text="保存信息", command=save_story_info).pack(side=tk.LEFT, padx=(0, 5))

            ttk.Label(right_btns, text="  |  ").pack(side=tk.LEFT, padx=(10, 10))

            ttk.Button(right_btns, text="内容概括", command=do_content_summary).pack(side=tk.LEFT, padx=(5, 5))

            ttk.Button(right_btns, text="找类似案例", command=on_find_similar_cases).pack(side=tk.LEFT, padx=(5, 5))

            ttk.Label(right_btns, text="  |  ").pack(side=tk.LEFT, padx=(10, 10))

            image_en_btn = ttk.Button(right_btns, text="EN图", command=lambda: copy_style_character("en"))
            image_en_btn.pack(side=tk.LEFT, padx=(0, 5))

            image_zh_btn = ttk.Button(right_btns, text="ZH图", command=lambda: copy_style_character("zh"))
            image_zh_btn.pack(side=tk.LEFT, padx=(0, 5))

            ttk.Label(right_btns, text="  |  ").pack(side=tk.LEFT, padx=(10, 10))

            copy_lm_btn = ttk.Button(right_btns, text="无拷贝", command=lambda: copy_lm_instruction())
            copy_lm_btn.pack(side=tk.LEFT, padx=(5, 5))

            
            # 两列输入区同宽：第 1、3 列均分扩展：仅配 weight=1 会让多余宽度只进第 1 列，导致分类/标签 比 子类型/关联ID 更宽
            topic_frame.columnconfigure(1, weight=1, uniform='topic_inputs')
            topic_frame.columnconfigure(3, weight=1, uniform='topic_inputs')
            
            # 初始化子类型选项
            if topic_category:
                update_subtypes()
            
            # NotebookLM Prompt 类型：从当前 channel 的 config 读取（选定 channel 后使用该 channel 下的 notebooklm_prompt_choices）
            _channel_key = os.path.basename(self.channel_path)
            NOTEBOOKLM_PROMPT_CHOICES = config_channel.get_channel_config(_channel_key).get("notebooklm_prompt_choices", [])
            prompt_choice_frame = ttk.Frame(main_frame)
            prompt_choice_frame.pack(anchor=tk.W, pady=(0, 5))
            ttk.Label(prompt_choice_frame, text="选LM提示").pack(side=tk.LEFT, padx=(0, 5))
            prompt_combo_var = tk.StringVar(value=NOTEBOOKLM_PROMPT_CHOICES[0][0])
            prompt_combo = ttk.Combobox(
                prompt_choice_frame,
                textvariable=prompt_combo_var,
                values=[opt[0] for opt in NOTEBOOKLM_PROMPT_CHOICES],
                state="readonly",
                width=16
            )
            prompt_combo.pack(side=tk.LEFT)
            prompt_initial_btn = ttk.Button(
                prompt_choice_frame,
                text="导向说明",
                width=8,
                command=lambda: open_initial_content_dialog(lambda: refresh_notebooklm_prompt()),
            )
            prompt_initial_btn.pack(side=tk.LEFT, padx=(6, 0))

            ttk.Label(prompt_choice_frame, text="   |   ").pack(side=tk.LEFT, padx=(10, 10))

            ttk.Label(prompt_choice_frame, text="主角").pack(side=tk.LEFT, padx=(0, 5))
            char_labels = list(config.CHARACTER_PERSON_OPTIONS)
            character_var = tk.StringVar(value=char_labels[0])
            character_combo = ttk.Combobox(prompt_choice_frame, textvariable=character_var, values=char_labels, state="readonly", width=12)
            character_combo.pack(side=tk.LEFT, padx=(0, 5))
            character_combo.current(0)

            ttk.Label(prompt_choice_frame, text="   |   ").pack(side=tk.LEFT, padx=(10, 10))

            # 画面风格 / 旁白 / Host 显示：与欢迎屏一致，只读（LAST_*）
            ttk.Label(prompt_choice_frame, text="风格:").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(prompt_choice_frame, text=project_manager.LAST_VISUAL_STYLE, width=16, anchor="w").pack(side=tk.LEFT, padx=(0, 5))

            ttk.Label(prompt_choice_frame, text="   |   ").pack(side=tk.LEFT, padx=(10, 10))

            # 旁白：欢迎屏 narrator；Host 显示：欢迎屏选择
            ttk.Label(prompt_choice_frame, text="旁白").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(prompt_choice_frame, text=str(project_manager.LAST_NARRATOR or ""), width=14, anchor="w").pack(side=tk.LEFT, padx=(0, 5))

            ttk.Label(prompt_choice_frame, text="   |   ").pack(side=tk.LEFT, padx=(10, 10))

            ttk.Label(prompt_choice_frame, text="HOST").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(prompt_choice_frame, text=project_manager.LAST_HOST_DISPLAY, width=18, anchor="w").pack(side=tk.LEFT, padx=(0, 5))


            def copy_style_character(language):
                try:
                    content = summary_window.clipboard_get()
                except Exception:
                    content = ""
                story_text = video_detail.get('story', '')

                if content:
                    # if content is not empty, ask user to confirm if they want to use the content as new story content 
                    if messagebox.askyesno("提示", "剪贴板内容不为空，是否使用剪贴板内容作为新的故事内容？", parent=summary_window):
                        story_text = content
                        # clean the clipboard
                        summary_window.clipboard_clear()
                        summary_window.update()
                        video_detail['story'] = story_text
                        try:
                            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                            dialog.after(0, populate_tree)
                        except Exception:
                            pass

                if not story_text:
                    messagebox.showwarning("提示", "故事内容为空，无法复制风格和人物", parent=summary_window)
                    return

                try:
                    story_json = parse_json(story_text, expect_list=False)

                    lang_editor_title = "编辑故事 JSON"
                    concise_win = tk.Toplevel(summary_window)
                    concise_win.title(lang_editor_title)
                    concise_win.geometry("720x620")
                    concise_win.transient(summary_window)
                    concise_win.grab_set()
                    concise_win.update_idletasks()
                    x = (concise_win.winfo_screenwidth() - 720) // 2
                    y = (concise_win.winfo_screenheight() - 620) // 2
                    concise_win.geometry(f"720x620+{x}+{y}")
                    ttk.Label(
                        concise_win,
                        text=f"{lang_editor_title}\n（Story；须为合法 JSON 对象后再保存）",
                        font=("TkDefaultFont", 10),
                    ).pack(anchor="w", padx=15, pady=(15, 5))
                    concise_text_widget = scrolledtext.ScrolledText(concise_win, wrap=tk.WORD, width=88, height=26)
                    concise_text_widget.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
                    concise_text_widget.insert("1.0", json.dumps(story_json, ensure_ascii=False, indent=2))

                    btn_row = ttk.Frame(concise_win)
                    btn_row.pack(pady=10)

                    def _save_story():
                        raw = (concise_text_widget.get("1.0", tk.END) or "").strip()
                        try:
                            parsed = json.loads(raw)
                            video_detail["story"] = json.dumps(parsed, ensure_ascii=False, indent=2)
                            with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                            dialog.after(0, populate_tree)
                        except json.JSONDecodeError as e:
                            messagebox.showerror("JSON 无效", f"请修正后再保存：\n{e}", parent=concise_win)
                            return
                        merged = {k: ("" if parsed.get(k) is None else str(parsed[k])) for k in _STORY_LANG_BRANCH_KEYS}

                        concise_win.destroy()

                    ttk.Button(btn_row, text="确定", command=_save_story).pack(side=tk.LEFT, padx=(0, 8))
                    ttk.Button(btn_row, text="取消", command=concise_win.destroy).pack(side=tk.LEFT)

                    summary_window.wait_window(concise_win)

                    story_json = parse_json(video_detail.get("story", "") or "", expect_list=False)

                except Exception:
                    messagebox.showwarning("提示", "故事内容格式错误，无法复制风格和人物", parent=summary_window)
                    return


                header_parts = []
                
                header_parts.append(f"Visual Style: {project_manager.LAST_VISUAL_STYLE}")

                if character_var.get():
                    header_parts.append(f"Main Character: {character_var.get()}")

                host_str = project_manager.LAST_NARRATOR
                if host_str:
                    header_parts.append(f"Host (voice): {host_str}")
                    hd = project_manager.LAST_HOST_DISPLAY
                    if hd == config_prompt.HARRATOR_DISPLAY_OPTIONS[-1]:
                        host_display_desc = "No Host. The main character performs and narrates."
                    else:
                        header_parts.append(f"Host display: {hd}")

                    header_parts.append(
                        "\n\nIn Video generation:"
                        "** If scene-image contains a Host(Narrator) talking-avatar → use Host to speak about the content of the scene. "
                        "** If scene-image has only a main character (no Host) → use the main character as talking-avatar to speak about the content of the scene."
                    )
                else:
                    header_parts.append("\n\nIn Video generation:"
                        "** No Host (Narrator). Use the main character as talking-avatar to speak about the content of scene."
                    )

                if language == "en":
                    if story_json.get('english', {}).get('concise_speaking', ''):
                        header_parts.append(f"** Generate the speaking words based on : {story_json.get('english', {}).get('concise_speaking', '')}")
                    else:
                        header_parts.append(f"** Generate the speaking words based on : the content in the image")
                    header_parts.append(f"** Speak out the key points, very very concisely (激发人心灵深处) !!!!)")

                    header_parts.append(f"\nScene Expression (In Image or Video generation):")
                    header_parts.append(f"** Heart_Message: {story_json.get('english', {}).get('heart_message', '')}")
                    header_parts.append(f"** Psychological_Story: {story_json.get('english', {}).get('psychological_micro_story', '')}")


                if language == "zh":
                    if story_json.get('chinese', {}).get('concise_speaking', ''):
                        header_parts.append(f"** Generate the speaking words based on : {story_json.get('chinese', {}).get('concise_speaking', '')}")
                    else:
                        header_parts.append(f"** Generate the speaking words based on : the content in the image")
                    header_parts.append(f"** Speak out the key points, very very concisely (激发人心灵深处) !!!!)")

                    header_parts.append(f"\nScene Expression (In Image or Video generation):")
                    header_parts.append(f"** Heart_Message: {story_json.get('chinese', {}).get('heart_message', '')}")
                    header_parts.append(f"** Psychological_Story: {story_json.get('chinese', {}).get('psychological_micro_story', '')}")


                try:
                    summary_window.clipboard_clear()
                    summary_window.clipboard_append("\n".join(header_parts))
                    summary_window.update()
                except Exception:
                    pass

                header_parts.append(f"\n\n\n----------------------------------------------------------\n")

                if language == "zh":
                    if story_json.get('english', {}).get('concise_speaking', ''):
                        header_parts.append(f"** Generate the speaking words based on : {story_json.get('english', {}).get('concise_speaking', '')}")
                    else:
                        header_parts.append(f"** Generate the speaking words based on : the content in the image")
                    header_parts.append(f"** Speak out the key points, very very concisely (激发人心灵深处) !!!!)")

                    header_parts.append(f"\nScene Expression (In Image or Video generation):")
                    header_parts.append(f"** Heart_Message: {story_json.get('english', {}).get('heart_message', '')}")
                    header_parts.append(f"** Psychological_Story: {story_json.get('english', {}).get('psychological_micro_story', '')}")


                if language == "en":
                    if story_json.get('chinese', {}).get('concise_speaking', ''):
                        header_parts.append(f"** Generate the speaking words based on : {story_json.get('chinese', {}).get('concise_speaking', '')}")
                    else:
                        header_parts.append(f"** Generate the speaking words based on : the content in the image")
                    header_parts.append(f"** Speak out the key points, very very concisely (激发人心灵深处) !!!!)")

                    header_parts.append(f"\nScene Expression (In Image or Video generation):")
                    header_parts.append(f"** Heart_Message: {story_json.get('chinese', {}).get('heart_message', '')}")
                    header_parts.append(f"** Psychological_Story: {story_json.get('chinese', {}).get('psychological_micro_story', '')}")

                header_parts.append(f"\n\n\n\n----------------------------------------------------------\n")
                header_parts.append(f"\nCase-Study Summary: \n{video_detail.get('summary', '')}")

                input_media_path = config.INPUT_MEDIA_PATH
                _cat_raw = (category_var.get() or "").strip()
                if _cat_raw:
                    _cat = make_safe_file_name(_cat_raw, title_length=6)
                else:
                    _cat = ""

                filename = make_safe_file_name(video_detail.get('title', '').strip(), title_length=20) + '_'
                file_path = os.path.join(input_media_path, '__' + selected_index + '__' + _cat + '__' + filename + '.txt')
                if os.path.exists(file_path):
                    os.remove(file_path)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(header_parts))


            def _update_copy_btn_text():
                t = last_copied[0]
                copy_lm_btn.config(text=f"已拷 {'LM' if t == 'lm_instruction' else '提示词' if t == 'text_content' else '-'}")

            def copy_lm_instruction():
                """轮替拷贝：上次是 LM 指令则本次拷文本框内容，反之则拷 LM 指令；按钮显示上次拷的内容"""
                try:
                    summary_window.clipboard_clear()
                    if last_copied[0] in (None, "text_content"):
                        summary_window.clipboard_append(LM_INSTRUCTION_STR)
                        last_copied[0] = "lm_instruction"
                    else:
                        content = (text_widget.get(1.0, tk.END) or '').strip()
                        summary_window.clipboard_append(content or '')
                        last_copied[0] = "text_content"
                    summary_window.update()
                    _update_copy_btn_text()
                except Exception:
                    pass



            label = ttk.Label(main_frame, text="视频摘要：", font=("Arial", 10, "bold"))
            label.pack(anchor=tk.W, pady=(0, 5))
            # 创建可滚动的文本区域
            text_widget = scrolledtext.ScrolledText(
                main_frame,
                wrap=tk.WORD,
                width=70,
                height=25,
                font=("Arial", 10),
                padx=10,
                pady=10
            )
            text_widget.pack(fill=tk.BOTH, expand=True)

            # 用户导向说明（非视频正文）：通过模板占位符 {instruction} 嵌入（与 SUNO 等模板一致）
            initial_content_holder = [""]

            def refresh_notebooklm_prompt(*args):
                """根据 combo 选择生成 prompt 并更新 text_widget + 剪贴板；{instruction} 来自导向说明。"""
                sel = prompt_combo_var.get()
                template = next((t for lbl, t in NOTEBOOKLM_PROMPT_CHOICES if lbl == sel), NOTEBOOKLM_PROMPT_CHOICES[0][1])
                topic = category_var.get().strip() + "-" + subtype_var.get().strip()

                # status 中为关联视频的 YouTube id（| 分隔）；在 channel_videos 列表中按 id 查找，拼标题与摘要
                reference_parts = []
                for i, seg in enumerate( (video_detail.get("status") or "").split("|")):
                    yid = (seg or "").strip()
                    if not yid or yid in ("success", "failed"):
                        continue
                    ref_v = _find_video_by_youtube_id(self.downloader.channel_videos, yid)
                    if not ref_v:
                        continue
                    title = (ref_v.get("title") or "").strip()
                    summary = (ref_v.get("summary") or "").strip()
                    reference_parts.append(
                        f"Reference {i+1}: Title: {title}\nReference {i+1}: Summary: {summary}"
                    )
                reference = "\n\n\n----------------------------------------------------------\n".join(reference_parts) if reference_parts else ""
                story_title = video_detail.get('title', '').strip()
                story_summary = video_detail.get('summary', '').strip()
                content = video_detail.get('content', '').strip()
                link = video_detail.get('url', '').strip()
                soul = project_manager.get_soul_for_topic(self.channel_path, category_var.get().strip(), subtype_var.get().strip(), self.topic_choices) or ''
                instruction = (initial_content_holder[0] or "").strip()
                prompt = _format_nb_prompt_template(
                    template,
                    topic=topic,
                    tags=tags_var.get().strip(),
                    language=config.LANGUAGES[self.language],
                    reference=reference,
                    soul=soul,
                    story_title=story_title,
                    story_summary=story_summary,
                    content=content,
                    link=link,
                    instruction=instruction,
                )

                text_widget.config(state=tk.NORMAL)
                text_widget.delete(1.0, tk.END)
                text_widget.insert(tk.END, prompt)
                text_widget.config(state=tk.DISABLED)
                if prompt and prompt.strip():
                    try:
                        summary_window.clipboard_clear()
                        summary_window.clipboard_append(prompt.strip())
                        summary_window.update()
                    except Exception:
                        pass

            def open_initial_content_dialog(on_done=None):
                """弹出窗口编辑导向说明；确定后执行 on_done（默认刷新 LM prompt）。"""
                dlg = tk.Toplevel(summary_window)
                dlg.title("Initial content（导向说明）")
                dlg.geometry("640x320")
                dlg.transient(summary_window)
                dlg.grab_set()
                dlg.update_idletasks()
                px = (dlg.winfo_screenwidth() - 640) // 2
                py = (dlg.winfo_screenheight() - 320) // 2
                dlg.geometry(f"640x320+{px}+{py}")
                ttk.Label(
                    dlg,
                    text=(
                        "补充你希望 NotebookLM 侧重的方向、故事意图、受众等（可选）。\n"
                        "将填入 NotebookLM 提示模板中的「导向说明」占位符；留空则该段为空。"
                    ),
                    wraplength=600,
                    justify="left",
                ).pack(anchor="w", padx=12, pady=(12, 6))
                body = scrolledtext.ScrolledText(dlg, wrap=tk.WORD, width=78, height=12, font=("Arial", 10))
                body.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
                body.insert("1.0", initial_content_holder[0])

                def _ok():
                    initial_content_holder[0] = body.get("1.0", tk.END).strip()
                    dlg.destroy()
                    fn = on_done or refresh_notebooklm_prompt
                    fn()

                def _cancel():
                    dlg.destroy()

                bf = ttk.Frame(dlg)
                bf.pack(pady=(0, 12))
                ttk.Button(bf, text="确定", command=_ok).pack(side=tk.LEFT, padx=6)
                ttk.Button(bf, text="取消", command=_cancel).pack(side=tk.LEFT, padx=6)

            def on_prompt_combo_selected(e):
                open_initial_content_dialog(lambda: refresh_notebooklm_prompt())

            def on_category_change(e):
                update_subtypes()
                refresh_notebooklm_prompt()
            def on_subtype_change(e):
                refresh_notebooklm_prompt()
            prompt_combo.bind("<<ComboboxSelected>>", on_prompt_combo_selected)
            category_combo.bind('<<ComboboxSelected>>', on_category_change)
            subtype_combo.bind('<<ComboboxSelected>>', on_subtype_change)

            refresh_notebooklm_prompt()  # 初始生成（不弹窗）

            LM_INSTRUCTION_STR = "Use the source named 'Pasted Text / 粘贴的文字' as your instruction and execute it as a prompt."
            last_copied = [None]  # 轮替：None -> lm_instruction -> text_content -> lm_instruction -> ...

            summary_window.focus_set()
        
        # 绑定双击事件
        tree.bind("<Double-1>", on_double_click)
        # 绑定 Enter 键（键盘）
        tree.bind("<Return>", on_enter_key)
        
        # 底部按钮框架（先创建框架，按钮在后面定义函数后添加）
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)

        def select_all():
            for item in tree.get_children():
                tree.selection_add(item)
            update_selection_count()
        

        def deselect_all():
            tree.selection_remove(*tree.get_children())
            update_selection_count()


        def update_video_list():
            """重新抓取当前频道视频列表，与现有列表比较，将新视频弹窗展示供用户勾选添加"""
            if not self.downloader.channel_list_json or not self.downloader.channel_videos:
                messagebox.showwarning("提示", "当前没有加载视频列表", parent=dialog)
                return
            channel_id = None
            for v in self.downloader.channel_videos:
                cid = (v.get('channel_id') or '').strip()
                if cid and len(cid) >= 10:
                    channel_id = cid
                    break
            if not channel_id:
                # 从任意视频重新拉取基本信息（含 channel_id）
                for v in self.downloader.channel_videos:
                    video_url = v.get('url', '').strip()
                    if video_url and ('youtube.com/watch' in video_url or 'youtu.be/' in video_url):
                        try:
                            video_data = self.downloader.get_video_detail(video_url, '')
                            if video_data:
                                cid = (video_data.get('channel_id') or '').strip()
                                if cid and len(cid) >= 10:
                                    channel_id = cid
                                    v['channel_id'] = cid
                                    for fld in ('channel', 'uploader'):
                                        if fld in video_data and video_data[fld]:
                                            v[fld] = video_data[fld]
                                    with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                        json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                                    break
                        except Exception:
                            continue
            if not channel_id:
                messagebox.showerror("错误", "无法获取频道ID，请使用「获取热门视频列表」重新导入频道", parent=dialog)
                return
            channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

            def fetch_task():
                result = self.downloader.fetch_channel_new_videos(channel_url, max_videos=5000)
                dialog.after(0, lambda: _show_new_videos_popup(result))

            def _show_new_videos_popup(result):
                if result is None:
                    messagebox.showerror("错误", "抓取视频列表失败", parent=dialog)
                    return
                new_videos, all_fetched = result
                updated_count = 0
                # 用最新抓取数据更新已有视频（观看次数、上传日期等），不浪费本次调用
                if all_fetched:
                    for v in self.downloader.channel_videos:
                        vid = v.get('id') or ''
                        if not vid:
                            t = (v.get('title') or '').strip().lower()
                            for fid, fdata in all_fetched.items():
                                if (fdata.get('title') or '').strip().lower() == t:
                                    vid = fid
                                    break
                        if vid and vid in all_fetched:
                            fetched = all_fetched[vid]
                            for fld in getattr(self.downloader, 'YOUTUBE_META_FIELDS', ('title', 'url', 'duration', 'view_count', 'uploader', 'channel', 'channel_id', 'upload_date', 'thumbnail', 'description')):
                                if fld in fetched:
                                    v[fld] = fetched[fld]
                            updated_count += 1
                    if updated_count:
                        with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                            json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                        if self.downloader.channel_videos and any(v.get('upload_date') for v in self.downloader.channel_videos):
                            self.downloader.latest_date = max(
                                (datetime.strptime(v["upload_date"], "%Y%m%d") for v in self.downloader.channel_videos if v.get("upload_date")),
                                default=self.downloader.latest_date
                            )
                        populate_tree()
                if not new_videos:
                    msg = "没有发现新视频"
                    if updated_count:
                        msg += f"，已更新 {updated_count} 个现有视频的观看次数等信息"
                    messagebox.showinfo("提示", msg + "。", parent=dialog)
                    return

                popup = tk.Toplevel(dialog)
                popup.title("新视频 - 选择要添加的视频")
                popup.geometry("900x500")
                popup.transient(dialog)

                cols = ("title", "views", "duration", "upload_date")
                tree_frame = ttk.Frame(popup)
                tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                scrollbar = ttk.Scrollbar(tree_frame)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                new_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                        yscrollcommand=scrollbar.set, selectmode="extended")
                new_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scrollbar.config(command=new_tree.yview)

                new_tree.heading("title", text="标题")
                new_tree.heading("views", text="观看次数")
                new_tree.heading("duration", text="时长")
                new_tree.heading("upload_date", text="上传日期")
                new_tree.column("title", width=450)
                new_tree.column("views", width=100)
                new_tree.column("duration", width=80)
                new_tree.column("upload_date", width=100)

                def fmt_duration(sec):
                    if not sec:
                        return "-"
                    m, s = divmod(int(sec), 60)
                    h, m = divmod(m, 60)
                    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

                def fmt_upload_date(ud):
                    if not ud:
                        return "-"
                    ud = str(ud).replace("-", "")[:8]
                    if len(ud) == 8:
                        return f"{ud[:4]}-{ud[4:6]}-{ud[6:]}"
                    return ud or "-"

                video_to_iid = {}
                for i, v in enumerate(new_videos):
                    view_count = v.get('view_count', 0)
                    views_str = f"{view_count:,}" if isinstance(view_count, (int, float)) else str(view_count)
                    duration_str = fmt_duration(v.get('duration', 0))
                    upload_date = fmt_upload_date(v.get('upload_date', ''))
                    title = (v.get('title', '') or '')[:120]
                    iid = new_tree.insert("", tk.END, values=(title, views_str, duration_str, upload_date))
                    video_to_iid[iid] = v

                def add_selected():
                    selected = new_tree.selection()
                    to_add = [video_to_iid[iid] for iid in selected if iid in video_to_iid]
                    if not to_add:
                        messagebox.showinfo("提示", "请至少选择一个视频", parent=popup)
                        return
                    for v in to_add:
                        self.downloader.channel_videos.append(v)
                    self.downloader.channel_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
                    with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                        json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                    popup.destroy()
                    populate_tree()
                    messagebox.showinfo("成功", f"已添加 {len(to_add)} 个视频到列表", parent=dialog)

                btn_frame = ttk.Frame(popup)
                btn_frame.pack(fill=tk.X, padx=10, pady=5)
                ttk.Button(btn_frame, text="全选", command=lambda: [new_tree.selection_add(item) for item in new_tree.get_children()]).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="取消全选", command=lambda: new_tree.selection_remove(*new_tree.get_children())).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="添加选中", command=add_selected).pack(side=tk.RIGHT, padx=5)
                ttk.Button(btn_frame, text="关闭", command=popup.destroy).pack(side=tk.RIGHT, padx=5)

            messagebox.showinfo("提示", "正在抓取频道视频列表，请稍候...", parent=dialog)
            thread = threading.Thread(target=fetch_task)
            thread.daemon = True
            thread.start()


        def fetch_info_selected():
            """对选中的、无 upload_date 的视频重新拉取元信息，更新后保存列表"""
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            videos = []
            for item in selected_items:
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                video_detail = self.get_video_detail(item_tags[0])
                if video_detail and not (video_detail.get('upload_date') or '').strip():
                    videos.append(video_detail)
            if not videos:
                messagebox.showinfo("提示", "所选视频均已包含 upload_date，无需更新", parent=dialog)
                return
            if not messagebox.askyesno("确认", f"将为 {len(videos)} 个视频重新拉取 upload_date 等信息，是否继续？", parent=dialog):
                return
            self.downloader._check_and_update_cookies(wait_forever=False)
            total = len(videos)
            success_count = [0]
            failed_count = [0]

            def fetch_task():
                for idx, video_detail in enumerate(videos, 1):
                    try:
                        url = video_detail.get('url', '')
                        if not url:
                            failed_count[0] += 1
                            continue
                        print(f"[{idx}/{total}] 拉取信息: {video_detail.get('title', '')[:50]}")
                        fresh = self.downloader.get_video_detail(url, self.downloader.channel_name or 'Unknown')
                        if fresh and fresh.get('upload_date'):
                            ud = str(fresh['upload_date'] or '').strip()
                            if ud:
                                if len(ud) == 10:
                                    ud = ud.replace('-', '')
                                video_detail['upload_date'] = ud[:8]
                                print(f"  ✅ 已更新 upload_date: {ud[:8]}")
                            for k in ('title', 'duration', 'view_count', 'uploader', 'channel', 'channel_id', 'thumbnail', 'description'):
                                if k in fresh and fresh[k] is not None:
                                    video_detail[k] = fresh[k]
                            success_count[0] += 1
                        else:
                            failed_count[0] += 1
                        try:
                            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"  ❌ 失败: {e}")
                        failed_count[0] += 1
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                dialog.after(0, lambda: [populate_tree(), messagebox.showinfo("完成", f"成功: {success_count[0]} 个，失败: {failed_count[0]} 个", parent=dialog)])

            threading.Thread(target=fetch_task, daemon=True).start()

        def download_selected():
            selected_items = tree.selection()
            if not selected_items:
                return
            # 获取选中视频的信息
            selected_videos = []
            for item in selected_items:
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                video_detail = self.get_video_detail(item_tags[0])
                if video_detail:
                    selected_videos.append(video_detail)
            
            # filter out the videos that are already downloaded
            def needs_download(video):
                audio_path = video.get('audio_path') or ''
                return not audio_path or not os.path.exists(audio_path)
            
            selected_videos = [video for video in selected_videos if needs_download(video)]
            if not selected_videos:
                return
            
            # 确认下载
            if not messagebox.askyesno("确认下载", f"确定要下载 {len(selected_videos)} 个视频吗？", parent=dialog):
                return
                    
            self.downloader._check_and_update_cookies()

            total = len(selected_videos)
            completed = [0]
            failed = [0]

            def download_task():
                for idx, video_detail in enumerate(selected_videos, 1):
                    try:
                        # 已存在 mp3 则跳过
                        prefix = self.downloader.generate_video_prefix(video_detail)
                        mp3_path = f"{self.youtube_dir}/media/{prefix}.mp3"
                        if os.path.exists(mp3_path):
                            video_detail['audio_path'] = mp3_path
                            video_detail["audio_download_status"] = "success"
                            completed[0] += 1
                            print(f"[{idx}/{total}] 跳过（已存在）: {video_detail['title']}")
                            try:
                                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                            continue
                        print(f"[{idx}/{total}] 下载: {video_detail['title']}")
                        file_path = self.downloader.download_audio_only(video_detail)
                        if file_path and os.path.exists(file_path):
                            file_fix = self.youtube_dir + "/media/" + self.downloader.generate_video_prefix(video_detail)+".mp3"
                            os.rename(file_path, file_fix)
                            video_detail['audio_path'] = file_fix
                            file_path = file_fix
                        #if file_path and os.path.exists(file_path):
                        #    video_detail['video_path'] = file_path
                        #    video_detail['audio_path'] = self.downloader.ffmpeg_audio_processor.extract_audio_from_video(file_path, "mp3")
                        
                        if file_path and os.path.exists(file_path):
                            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                            print(f"✅ 完成: {os.path.basename(file_path)} ({file_size:.1f} MB)")
                            video_detail["audio_download_status"] = "success"
                            completed[0] += 1
                            try:
                                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                        else:
                            print(f"❌ 失败: {video_detail['title']}")
                            video_detail["audio_download_status"] = "failed"
                            failed[0] += 1
                        
                    except Exception as e:
                        print(f"❌ 错误: {video_detail['title']} - {str(e)}")
                        video_detail["audio_download_status"] = "failed"
                        failed[0] += 1
                
                # 下载完成
                print(f"\n{'='*50}")
                print(f"批量下载完成！")
                print(f"成功: {completed[0]} 个")
                print(f"失败: {failed[0]} 个")
                
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                    print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")
                # 在主线程中刷新列表
                dialog.after(0, populate_tree)
            
            # 在后台线程中下载
            thread = threading.Thread(target=download_task)
            thread.daemon = True
            thread.start()


        def transcribe_selected():
            selected_items = tree.selection()
            # 检查选中的视频：已下载且没有SRT文件的视频
            videos_to_transcribe = []
            videos_already_transcribed = []
            
            for item in selected_items:
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue

                content = video_detail.get('content', '')
                if content and len(content) > 100:
                    self.update_text_content(video_detail)
                    videos_already_transcribed.append(video_detail)
                else:
                    transcribed_file = self.match_media_file(video_detail,'transcribed_file', ['.srt','.zh.srt','.en.srt','.json','.zh.json','.en.json'])
                    if transcribed_file:
                        self.update_text_content(video_detail)
                        videos_already_transcribed.append(video_detail)
                    else:
                        videos_to_transcribe.append(video_detail)

            # 如果没有可转录的视频，显示提示
            if not videos_to_transcribe:
                messagebox.showwarning("提示", "没有可转录的视频", parent=dialog)
                return
            
            message = f"将转录 {len(videos_to_transcribe)} 个视频\n\n是否继续？"
            if not messagebox.askyesno("确认转录", message, parent=dialog):
                return

            # 在后台线程中转录，避免阻塞主 UI 导致窗口变红/冻结
            self.downloader._check_and_update_cookies(wait_forever=False)

            def transcribe_task():
                success_count = 0
                failed_count = 0
                try:
                    for idx, video_detail in enumerate(videos_to_transcribe, 1):
                        time.sleep(0.05)  # 让出 GIL，避免长时间占用导致主线程 UI 无法响应
                        try:
                            downloaded_file = self.downloader.try_download_caption_with_priority(video_detail)
                            if downloaded_file:
                                print(f"  ✅ 转录成功")
                                self.update_text_content(video_detail, downloaded_file)
                                # 显式将 upload_date 同步到 channel_videos，确保 Tree 刷新时能看到
                                if video_detail.get('upload_date'):
                                    for v in self.downloader.channel_videos:
                                        if v.get('url') == video_detail.get('url'):
                                            v['upload_date'] = video_detail['upload_date']
                                            break
                                success_count += 1
                                try:
                                    with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                        json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                                except Exception:
                                    pass
                            else:
                                print(f"  ❌ 转录失败：无法下载字幕")
                                failed_count += 1
                        except Exception as e:
                            print(f"  ❌ 转录失败: {str(e)}")
                            failed_count += 1

                    with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                        json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                    print(f"\n{'='*50}")
                    print(f"转录任务完成！成功: {success_count} 个，失败: {failed_count} 个")
                finally:
                    # 确保无论成功或异常，都在主线程刷新列表，避免 UI 冻结
                    def _refresh():
                        populate_tree()
                        try:
                            messagebox.showinfo("转录完成", f"成功: {success_count} 个，失败: {failed_count} 个", parent=dialog)
                        except Exception:
                            pass
                    dialog.after(0, _refresh)

            threading.Thread(target=transcribe_task, daemon=True).start()


        def tag_selected():
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            for item in selected_items:
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue
                self.update_text_content(video_detail)
                content = video_detail.get('content', '')
                if not content or not content.strip():
                    continue
                self.prepare_category_for_content(video_detail, content, self.topic_choices)
            populate_tree()


        def list_summary():
            # new list for items in the list, only item with summary,  include fields :  summary, title, url, topic_category, topic_subtype, tags
            summary_list = []
            for item in tree.get_children():
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue
                if video_detail.get('summary', ''):
                    summary_list.append({
                        'summary': video_detail.get('summary', ''),
                        'title': video_detail.get('title', ''),
                        'url': video_detail.get('url', ''),
                        'id': video_detail.get('id', ''),
                        'topic_category': video_detail.get('topic_category', ''),
                        'topic_subtype': video_detail.get('topic_subtype', ''),
                        'tags': video_detail.get('tags', ''),
                    })
            if not summary_list:
                messagebox.showwarning("提示", "没有可简表的视频", parent=dialog)
                return

            # save the summary_list to windows Download folder, file name same as channel_list_json, but with _summary.txt suffix
            with open(os.path.join(os.path.expanduser("~"), "Downloads", os.path.basename(self.downloader.channel_list_json)+"_summary.txt"), "w", encoding="utf-8") as f:
                json.dump(summary_list, f, ensure_ascii=False, indent=2)


        def summarize_selected():
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            summary_list = []
            for item in selected_items:
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue

                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue

                text_content = self.fetch_text_content(video_detail)
                if not text_content or len(text_content) < 100:
                    continue

                summary_content = video_detail.get('summary', '')
                summary_list.append(summary_content)
                if summary_content and summary_content.strip():
                    continue

                prompt = config_prompt.REWRITE_MATERIAL_SYSTEM_PROMPT.format(language=config.LANGUAGES[self.language])
                rewritten = self.llm_api_local.generate_text(prompt, text_content)
                if rewritten and rewritten.strip():
                    video_detail["summary"] = rewritten.strip()
                    summary_list.append(rewritten.strip())
                    self.prepare_category_for_content(video_detail, rewritten.strip(), self.topic_choices)

            if summary_list:
                summaries = ""
                for i, summary_content in enumerate(summary_list):
                    summaries += f"----------------------\nCase-Story {i+1}:\n {summary_content}\n\n"

                input_media_path = config.INPUT_MEDIA_PATH
                file_path = os.path.join(input_media_path, 'adjust_classification_on_case_study_summaries.txt')
                if os.path.exists(file_path):
                    os.remove(file_path)
                with open(file_path, 'w', encoding='utf-8') as f:
                    classification_prompt = "Attached is the existing topics classification, each topic has a subtype. Below are some new case-study content, please adjust the existing topics, and then classify the new content clearly (find non-confusing category/subtype). These are typical psychological consultation problem case-studies:\n\n"
                    f.write(classification_prompt + summaries)

            populate_tree()


        # 在所有函数定义后创建按钮
        ttk.Button(bottom_frame, text="全选", command=select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="不选", command=deselect_all).pack(side=tk.LEFT, padx=5)

        ttk.Button(bottom_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="简表", command=list_summary).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="摘要", command=summarize_selected).pack(side=tk.RIGHT, padx=5)
        #ttk.Button(bottom_frame, text="重摘", command=re_summarize_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="分类", command=tag_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="转录", command=transcribe_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="下载", command=download_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="信息", command=fetch_info_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="更新", command=update_video_list).pack(side=tk.RIGHT, padx=5)



    def download_youtube(self, transcribe):
        """下载YouTube视频并转录"""
        # 弹出对话框让用户输入URL
        dialog = tk.Toplevel(self.root)
        dialog.title("YouTube下载")
        dialog.geometry("600x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # YouTube URL输入
        url_frame = ttk.Frame(dialog)
        url_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(url_frame, text="YouTube链接:").pack(side=tk.LEFT)
        url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=url_var, width=50)
        url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        result_var = tk.StringVar(value="cancel")
        
        def on_confirm():
            url = url_var.get().strip()
            if not url:
                messagebox.showerror("错误", "请输入YouTube链接", parent=dialog)
                return
            result_var.set("confirm")
            dialog.destroy()
        
        def on_cancel():
            result_var.set("cancel")
            dialog.destroy()
        
        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        ttk.Button(button_frame, text="确认", command=on_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        # 等待对话框关闭
        self.root.wait_window(dialog)
        if result_var.get() == "cancel":
            return
        
        # 在对话框关闭后，通过 StringVar 获取值（它们仍然存在）
        video_url = url_var.get().strip()
        
        print(f"📥 开始下载YouTube视频并转录...")
        print(f"URL: {video_url}")

        self.downloader._check_and_update_cookies()
        video_data = self.downloader.get_video_detail(video_url, channel_name='')
        if not video_data:
            self.root.after(0, lambda: messagebox.showerror("错误", "获取视频详情失败"))
            return

        channel_name = self.downloader.get_channel_name(video_data)

        if not transcribe:
            self.downloader.download_video_highest_resolution(video_data)
            return
    
        # 统一频道选择：用较宽松的匹配在已有文件中查找，找到则问用户是否选用；不选则保持空
        self.downloader.channel_list_json = None
        self.downloader.channel_videos = []
        channel_list_json_files = glob.glob(f"{self.youtube_dir}/list/*.json.txt")
        channel_to_file = {}
        channel_names = []
        for json_file in channel_list_json_files:
            filename = os.path.basename(json_file)
            m = re.match(r'(.+?)\.json\.txt', filename)
            if m:
                cn = m.group(1)
                channel_names.append(cn)
                channel_to_file[cn] = json_file

        # 宽松匹配：精确匹配 > 包含关系（channel_name in cn 或 cn in channel_name）
        def _norm(s):
            return (s or "").strip().lower()
        nch = _norm(channel_name)
        exact_match = [cn for cn in channel_names if _norm(cn) == nch]
        loose_match = [cn for cn in channel_names if cn not in exact_match and (nch in _norm(cn) or _norm(cn) in nch)]
        candidates = exact_match + loose_match

        selected_file = None
        CREATE_NEW = "【创建新频道】"
        if candidates:
            choices = candidates + [CREATE_NEW]
            choice = askchoice("选择频道列表", choices, parent=self.root)
            if choice == CREATE_NEW:
                selected_file = None  # 进入下方创建新频道分支
            elif choice and choice in channel_to_file:
                selected_file = channel_to_file[choice]

        if selected_file:
            self.downloader.channel_list_json = selected_file
            try:
                with open(self.downloader.channel_list_json, 'r', encoding='utf-8') as f:
                    self.downloader.channel_videos = json.load(f)
                    _normalize_channel_videos_story_field_to_str(self.downloader.channel_videos)
                    self.downloader.latest_date = max(
                        (datetime.strptime(v["upload_date"], "%Y%m%d") for v in self.downloader.channel_videos if v.get("upload_date")),
                        default=None
                    )
            except Exception as e:
                print(f"❌ 读取视频列表失败: {e}")
                self.downloader.channel_videos = []

        if not self.downloader.channel_videos:
            # 无已有频道或用户未选：弹窗让用户编辑频道名并创建新文件（video 里有 channel 信息则作为默认值）
            new_name = simpledialog.askstring("创建新频道", "频道名称（可修改）:", initialvalue=channel_name, parent=self.root)
            if new_name and new_name.strip():
                channel_name = new_name.strip()
            self.downloader.channel_list_json = f"{self.youtube_dir}/list/{channel_name}.json.txt"
            self.downloader.channel_videos = []
            print(f"✅ 已创建新的视频列表文件: {self.downloader.channel_list_json}")


        is_new_video = self.downloader.is_video_new(video_data)
        if not is_new_video:
            print(f"✅ 视频已存在，跳过下载...")
            return

        # 1. 优先尝试下载 caption（不 fetch 基本信息、不弹窗），按 zh/zh-Hans/.../en 硬试
        transcribed_file = self.downloader.try_download_caption_with_priority(video_data)
        if transcribed_file:
            print(f"✅ 已从字幕获取文本")

        # 2. 若无 caption，下载音频并用 Whisper 转录（默认中文 zh）
        if not transcribed_file:
            file_path = self.downloader.download_audio_only(video_data)
            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path) / (1024 * 1024)
                video_data["audio_path"] = file_path
                video_data["file_size_mb"] = file_size
                video_data["audio_download_status"] = "success"
            else:
                self.root.after(0, lambda: messagebox.showerror("错误", "视频下载失败"))
                return
            transcribed_file = self.downloader.download_captions(video_data, self.language)
        if not transcribed_file:
            print(f"❌ YouTube视频转录失败")
            self.root.after(0, lambda: messagebox.showerror("错误", "YouTube视频转录失败：未生成字幕文件"))
            return

        video_data['transcribed_file'] = transcribed_file
        print(f"✅ YouTube视频转录完成！")
        self.root.after(0, lambda: messagebox.showinfo("转录完成", "YouTube视频转录完成！"))
        self.downloader.channel_videos.append(video_data)
        this_video_date = datetime.strptime(video_data["upload_date"], "%Y%m%d")
        if this_video_date > self.downloader.latest_date:
            self.downloader.latest_date = this_video_date
        self.update_text_content(video_data)
        
        with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
            json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")