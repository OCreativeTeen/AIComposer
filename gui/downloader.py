import os
import time
import yt_dlp
import subprocess
import shutil
import json
import re
import threading
import uuid
import glob
from datetime import datetime

import config_prompt

import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.llm_api import LLMApi, OLLAMA
from utility.audio_transcriber import AudioTranscriber
from utility.file_util import write_json, safe_copy_overwrite, safe_remove
from gui.choice_dialog import askchoice
        
# 导入所需模块
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.filedialog as filedialog
import tkinter.scrolledtext as scrolledtext
import tkinter.simpledialog as simpledialog

        



class MediaDownloader:

    def __init__(self, pid, project_path):
        print("YoutubeDownloader init...")
        self.pid = pid
        self.project_path = project_path
        self.youtube_dir = f"{self.project_path}/Youtbue_download"
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)
        
        # Cookies 文件路径（优先检查下载文件夹，然后检查项目路径）
        self.cookies_file = self._find_cookies_file()
        
        # Cookies 有效性标志
        self.cookie_valid = True
        
        # 不使用浏览器自动提取（由于 DPAPI 解密问题）
        self.use_browser_cookies = False
        self.browser = None
        
        # 检查 cookies 文件是否存在
        if os.path.exists(self.cookies_file):
            print(f"✅ 找到 cookies 文件: {self.cookies_file}")
            # 验证文件不为空
            if os.path.getsize(self.cookies_file) > 0:
                print(f"📊 Cookies 文件大小: {os.path.getsize(self.cookies_file)} 字节")
            else:
                print(f"⚠️ Cookies 文件为空！")
                self._print_cookies_help()
        else:
            print(f"⚠️ 未找到 cookies 文件: {self.cookies_file}")
            self._print_cookies_help()
        
        # 检测 JavaScript 运行时
        self.js_runtime = self._detect_js_runtime()
        self.transcriber = AudioTranscriber(self.pid, model_size="small", device="cuda")


    def _find_cookies_file(self):
        """
        查找 cookies 文件，按优先级检查以下位置：
        1. Windows 下载文件夹（找到后移动到项目路径并删除原文件）
        2. 项目路径
        
        Returns:
            str: cookies 文件的完整路径
        """
        cookies_filename = "www.youtube.com_cookies.txt"
        
        # 优先级 1: Windows 下载文件夹
        try:
            # 获取 Windows 下载文件夹路径
            download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
            download_cookies = os.path.join(download_folder, cookies_filename)
            
            if os.path.exists(download_cookies):
                print(f"✅ 在下载文件夹找到 cookies 文件: {download_cookies}")
                
                # 移动到项目路径
                project_cookies = os.path.join(self.project_path, cookies_filename)
                try:
                    # 如果项目路径已有文件，直接删除
                    if os.path.exists(project_cookies):
                        os.remove(project_cookies)
                        print(f"🗑️ 已删除旧的 cookies 文件: {project_cookies}")
                    
                    # 移动文件到项目路径
                    shutil.move(download_cookies, project_cookies)
                    print(f"📦 已将 cookies 文件移动到项目路径: {project_cookies}")
                    print(f"🗑️ 已从下载文件夹删除原文件")
                    return project_cookies
                except Exception as e:
                    print(f"⚠️ 移动 cookies 文件时出错: {e}")
                    # 如果移动失败，仍然使用下载文件夹的文件
                    return download_cookies
        except Exception as e:
            print(f"⚠️ 检查下载文件夹时出错: {e}")
        
        # 优先级 2: 项目路径
        project_cookies = os.path.join(self.project_path, cookies_filename)
        if os.path.exists(project_cookies):
            print(f"✅ 在项目路径找到 cookies 文件: {project_cookies}")
            return project_cookies
        
        # 如果都不存在，返回项目路径（用于创建新文件）
        print(f"📁 Cookies 文件位置（将在此处查找）: {project_cookies}")
        return project_cookies

    def _check_cookie_invalid(self, error_msg):
        """
        检查错误信息是否表示 cookies 无效
        
        Args:
            error_msg: 错误消息字符串
            
        Returns:
            bool: 如果 cookies 无效返回 True
        """
        invalid_keywords = [
            'no longer valid',
            'invalid',
            'Sign in to confirm',
            'rate-limited',
            'Video unavailable',
            'This content isn\'t available'
        ]
        
        error_lower = str(error_msg).lower()
        for keyword in invalid_keywords:
            if keyword.lower() in error_lower:
                return True
        return False

    def _check_and_update_cookies(self, wait_forever=True):
        """
        检查下载文件夹是否有新的 cookies 文件，如果有则更新
        如果未找到且 wait_forever=True，将持续等待直到找到
        
        Args:
            wait_forever: 如果为 True，会持续等待直到找到新的 cookies 文件
        
        Returns:
            bool: 如果找到并更新了新的 cookies 文件返回 True
        """
        cookies_filename = "www.youtube.com_cookies.txt"
        download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        download_cookies = os.path.join(download_folder, cookies_filename)
        
        # 持续等待直到找到新的 cookies 文件
        while True:
            if os.path.exists(download_cookies):
                print(f"🔄 在下载文件夹发现新的 cookies 文件: {download_cookies}")
                
                # 移动到项目路径
                project_cookies = os.path.join(self.project_path, cookies_filename)
                try:
                    # 如果项目路径已有文件，直接删除
                    if os.path.exists(project_cookies):
                        os.remove(project_cookies)
                        print(f"🗑️ 已删除旧的 cookies 文件: {project_cookies}")
                    
                    # 移动新文件
                    shutil.move(download_cookies, project_cookies)

                    self.cookies_file = project_cookies
                    self.cookie_valid = True
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
            
            # 如果未找到且不需要等待，返回 False
            if not wait_forever:
                return False
            
            # 等待并检查
            print("⏳ 等待下载文件夹中的新 cookies 文件...")
            print(f"   请将新的 cookies 文件保存到: {download_cookies}")
            time.sleep(5)  # 每 5 秒检查一次


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

    def _print_cookies_help(self):
        """打印如何获取 cookies 的帮助信息"""
        print("\n" + "="*60)
        print("💡 如何获取 YouTube Cookies：")
        print("="*60)
        print("\n方法 1：使用浏览器扩展（推荐）")
        print("  1. 安装扩展：")
        print("     Chrome/Edge: 搜索 'Get cookies.txt LOCALLY'")
        print("     Firefox: 搜索 'cookies.txt'")
        print("  2. 访问 youtube.com 并登录")
        print("  3. 点击扩展图标，导出 cookies")
        print("  4. 保存为: www.youtube.com_cookies.txt")
        print("  5. 放入以下任一位置（按优先级）：")
        download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        print(f"     - Windows 下载文件夹: {download_folder}")
        print(f"     - 项目路径: {self.project_path}")
        
        print("\n方法 2：使用 yt-dlp 命令（需要先关闭浏览器）")
        print("  PowerShell 命令：")
        download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        print(f'  cd "{download_folder}"  # 或 cd "{self.project_path}"')
        print('  yt-dlp --cookies-from-browser chrome --cookies www.youtube.com_cookies.txt "https://www.youtube.com"')
        
        print("\n⚠️ 注意：")
        print("  - Cookies 文件包含登录信息，请勿分享")
        print("  - Cookies 会过期，需要定期更新")
        print("  - 某些视频可能仍需要 cookies 才能访问")
        print("="*60 + "\n")


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
        if os.path.exists(self.cookies_file) and os.path.getsize(self.cookies_file) > 0:
            opts['cookiefile'] = self.cookies_file
            # 只在第一次使用时打印，避免重复输出
            if not hasattr(self, '_cookies_logged'):
                print(f"🍪 使用 cookies 文件: {self.cookies_file}")
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
        check_opts = self._get_ydl_opts_base(quiet=True, skip_download=True)
        with yt_dlp.YoutubeDL(check_opts) as ydl:
            info = ydl.extract_info(video_detail.get('url', ''), download=False)
            return info
        return None


    def download_captions(self, video_detail, target_lang):
        if not target_lang:
            return None

        video_url = video_detail.get('url', '')
        if not video_url:
            return None

        download_prefix = self.youtube_dir + "/__" + self.generate_video_prefix(video_detail)
        
        #ydl_opts = self._get_ydl_opts_base(
        #    skip_download=True,
        #    writesubtitles=True,
        #    writeautomaticsub=True,
        #    subtitleslangs=[target_lang],
        #    subtitlesformat=format,
        #    outtmpl=download_prefix,
        #    quiet=True,  # 使用 quiet 模式减少输出
        #    no_warnings=True,  # 禁用警告
        #)
        #with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        #    ydl.download([video_url])
        # 检查文件是否真的下载了
        #file_path = f"{download_prefix}.{target_lang}.{format}"
        #if os.path.exists(file_path):
        #    return file_path

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
            ydl.download([video_url])
        print(f"✅ 已下载字幕：语言 {target_lang}")
        src_path = f"{download_prefix}.{target_lang}.srt"
        if os.path.exists(src_path):
            return src_path

        # 如果下载失败，尝试转录
        print(f"❌ 下载字幕失败，尝试转录...")
        src_path = f"{download_prefix}.{target_lang}.json"
        if os.path.exists(src_path):
            return src_path

        audio_path = video_detail.get('audio_path', '')
        if not audio_path:
            video_path = video_detail.get('video_path', '')
            if video_path:
                audio_path = download_prefix + ".mp3"
                safe_copy_overwrite(self.ffmpeg_audio_processor.extract_audio_from_video(video_path, "mp3"), audio_path)
                video_detail['audio_path'] = audio_path
            else:
                audio_path = self.download_audio_only(video_detail)

            if not audio_path:
                print(f"❌ 音频文件不存在")
                return None

        script_json = self.transcriber.transcribe_with_whisper(audio_path, target_lang, 3, 15, re_org=False)
        write_json(src_path, script_json)  
        return src_path


    def download_audio_only(self, video_detail, sleep_interval=2):
        video_url = video_detail.get('url', '')
        if not video_url:
            return None

        video_prefix = self.youtube_dir + "/__" + self.generate_video_prefix(video_detail)

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
                
                # 检查各种可能的音频扩展名
                for ext in audio_extensions:
                    expected_path = os.path.abspath(f"{video_prefix}.{ext}")
                    if os.path.exists(expected_path):
                        print(f"✅ 找到下载的音频文件: {expected_path}")
                        if not expected_path.endswith('.mp3'):
                            a = self.ffmpeg_audio_processor.to_mp3(expected_path)
                            safe_remove(expected_path)
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
            error_msg = str(e)
            # 检查是否是 cookies 无效的错误
            if self._check_cookie_invalid(error_msg):
                print("❌ 检测到 cookies 可能已失效")
                self.cookie_valid = False

            return None


    def download_video_highest_resolution(self, video_detail, sleep_interval=2):
        video_url = video_detail.get('url', '')
        if not video_url:
            return None
        video_prefix = self.youtube_dir + "/__" + self.generate_video_prefix(video_detail)

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
        with yt_dlp.YoutubeDL(video_info_opts) as video_ydl:
            video_detail = video_ydl.extract_info(video_url, download=False)
            
            video_data = {
                'title': video_detail.get('title', 'Unknown Title'),
                'url': video_url,
                'id': video_detail.get('id', ''),
                'duration': video_detail.get('duration', 0),
                'view_count': video_detail.get('view_count', 0),
                'uploader': video_detail.get('uploader', channel_name),
                'channel': channel_name,  # 添加独立的 channel 字段
                'channel_id': video_detail.get('channel_id', ''),
                'upload_date': video_detail.get('upload_date', ''),
                'thumbnail': video_detail.get('thumbnail', ''),
                'description': video_detail.get('description', '')[:200] if video_detail.get('description') else ''
            }
            
            return video_data


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
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        safe_title = safe_title[:title_length]  # 限制长度
        # 构建文件名前缀（用于匹配）
        return f"{view_count_str}_{date_str}_{safe_title}"


    def list_hot_videos(self, channel_url, max_videos=200, min_view_count=500):
        try:
            # 使用基础选项，包含 cookies 支持
            ydl_opts = self._get_ydl_opts_base(
                quiet=False,
                extract_flat='in_playlist',  # 只提取播放列表中的基本信息
                skip_download=True,
            )
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)

            channel_name = info.get('channel', 'Unknown')
            if channel_name.lower() == 'unknown':
                channel_name = info.get('uploader', 'Unknown')
            if channel_name.lower() == 'unknown':
                channel_name = info.get('channel_id', 'Unknown')

            with open(f'{self.youtube_dir}/info_{channel_name}.json', 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
        
            if not info or 'entries' not in info:
                return []

        
            video_list_json_path = f"{self.youtube_dir}/{channel_name}_hotvideos.json"
            if os.path.exists(video_list_json_path) and max_videos > 0:
                return json.load(open(video_list_json_path, 'r', encoding='utf-8'))

            # 记录循环开始时间，用于每10分钟检查一次 cookies
            loop_start_time = time.time()
            cookie_check_interval = 600  # 10分钟 = 600秒
            
            videos = []

            for count, entry in enumerate(info['entries']):
                if count >= max_videos:
                    break

                if entry:
                    video_url = entry.get('url', '') or entry.get('webpage_url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                    
                    try:
                        video_data = self.get_video_detail(video_url, channel_name)
                        print(f"✓ {count} -- {video_data['title'][:50]} -- {video_data['view_count']:,} 观看")
                        videos.append(video_data)
                    except Exception as e:
                        error_msg = str(e)
                        print(f"⚠️ 跳过视频: {error_msg}")
                        self.cookie_valid = False
                    finally:
                        # 检查是否已经过了10分钟，如果是则检查并更新 cookies
                        current_time = time.time()
                        elapsed_time = current_time - loop_start_time
                        
                        if elapsed_time >= cookie_check_interval:
                            print(f"⏰ 已过去 {elapsed_time/60:.1f} 分钟，检查并更新 cookies...")
                            if self._check_and_update_cookies(wait_forever=False):
                                print("✅ 已更新 cookies，继续处理...")
                            # 重置计时器
                            loop_start_time = time.time()
                        
                        # 如果 cookies 无效，检查并等待新的 cookies 文件
                        if not self.cookie_valid:
                            print("⏳ Cookies 已失效，等待新的 cookies 文件...")
                            # _check_and_update_cookies 会持续等待直到找到新的 cookies 文件
                            if self._check_and_update_cookies(wait_forever=True):
                                print("✅ 已更新 cookies，继续处理...")
                        else:
                            # YouTube 建议使用延迟来避免 rate limit
                            print("⏳ 等待 2 秒以避免限流...")
                            time.sleep(2)
            
            # 按观看次数排序
            videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)

            # 过滤掉观看次数小于min_view_count的视频
            videos = [video for video in videos if video.get('view_count', 0) >= min_view_count]

            # 保存视频列表到JSON
            with open(video_list_json_path, 'w', encoding='utf-8') as f:
                json.dump(videos, f, ensure_ascii=False, indent=2)

            print(f"✅ 成功获取 {len(videos)} 个视频")
            return videos
            
        except Exception as e:
            print(f"❌ 获取视频列表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return []


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


    def convert_vtt_to_srt(self, vid, lang):
        # ffmpeg_path = os.path.abspath("ffmpeg/bin/ffmpeg.exe")         
        ffmpeg_path = os.path.abspath("ffmpeg.exe") 
        vtt_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{vid}.{lang}.vtt")
        srt_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{vid}.{lang}.srt")
        try:
            subprocess.run([
                ffmpeg_path,
                '-y',  # overwrite
                '-i', str(vtt_path),
                str(srt_path)
            ], check=True, encoding='utf-8', errors='ignore')
            print(f"🎉 Converted to SRT: {srt_path}")
            os.remove(vtt_path)

            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return content
        except subprocess.CalledProcessError as e:
            print(f"⚠️ FFmpeg failed: {e}")
            return ""


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
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(secret_key, scopes)
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




# YouTube GUI管理类
class MediaGUIManager:
    """YouTube GUI管理器 - 处理所有YouTube相关的GUI对话框"""
    
    def __init__(self, root, project_path, pid, tasks, log_to_output_func, download_output):
        self.root = root
        self.project_path = project_path
        self.youtube_dir = f"{self.project_path}/Youtbue_download"
        # 在导入模块之前先导入os，避免局部变量错误
        import os
        os.makedirs(self.youtube_dir, exist_ok=True)

        self.pid = pid
        self.tasks = tasks
        self.log_to_output = log_to_output_func
        self.download_output = download_output
        
        self.llm_api = LLMApi(OLLAMA)

        # 创建YoutubeDownloader实例
        self.downloader = MediaDownloader(pid, project_path)

        self.channel_list_json = ""
        self.channel_videos = []
        self.channel_name = ""
        

    def manage_hot_videos(self):
        # 查找所有热门视频JSON文件
        pattern = f"{self.youtube_dir}/*_hotvideos.json"
        json_files = glob.glob(pattern)
        
        if not json_files:
            messagebox.showinfo("提示", "未找到任何热门视频列表文件\n\n请先使用 '获取热门视频' 功能获取频道视频列表")
            return
        
        # 提取频道名称
        channel_data = []
        for json_file in json_files:
            filename = os.path.basename(json_file)
            # 从文件名中提取频道名：_频道名_hotvideos.json -> 频道名
            match = re.match(r'_(.+?)_hotvideos\.json', filename)
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
        
        # 显示频道选择对话框
        channel_dialog = tk.Toplevel(self.root)
        channel_dialog.title("选择频道")
        channel_dialog.geometry("600x400")
        channel_dialog.transient(self.root)
        channel_dialog.grab_set()
        
        # 顶部提示
        top_frame = ttk.Frame(channel_dialog)
        top_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(top_frame, text="请选择要管理的频道：", 
                  font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        
        # 创建频道列表
        list_frame = ttk.Frame(channel_dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, 
                            font=("Arial", 11), selectmode=tk.SINGLE)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # 填充频道列表
        for channel in channel_data:
            listbox.insert(tk.END, f"{channel['name']} ({channel['video_count']} 个视频)")
        
        # 默认选择第一个
        if channel_data:
            listbox.selection_set(0)
        
        # 底部按钮
        bottom_frame = ttk.Frame(channel_dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def on_confirm():
            selected = listbox.curselection()
            if not selected:
                messagebox.showwarning("提示", "请选择一个频道", parent=channel_dialog)
                return
            
            channel = channel_data[selected[0]]
            self.channel_list_json = channel['file']
            channel_dialog.destroy()
            
            """显示频道视频管理对话框"""
            with open(self.channel_list_json, 'r', encoding='utf-8') as f:
                self.channel_videos = json.load(f)
            if not self.channel_videos:
                messagebox.showwarning("提示", "视频列表为空")
                return

            self.channel_name = channel['name']   
            self.check_channel_videos()
            # 显示该频道的视频管理对话框
            self._show_channel_videos_dialog()
        
        ttk.Button(bottom_frame, text="确定", command=on_confirm).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="取消", command=channel_dialog.destroy).pack(side=tk.RIGHT, padx=5)


    def check_channel_videos(self):
        for video in self.channel_videos:
            self.check_video_status(video)

    def fetch_text_content(self, srt_file):
        if srt_file.endswith('.json'):
            return self.downloader.transcriber.fetch_text_from_json(srt_file)

        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 使用正则表达式匹配SRT格式
        # SRT格式：序号\n时间戳\n文本内容\n\n
        # 匹配模式：数字开头，然后是时间戳行（包含-->），然后是文本内容
        pattern = r'^\d+\s*\n\s*\d{2}:\d{2}:\d{2}[,\d]+\s*-->\s*\d{2}:\d{2}:\d{2}[,\d]+\s*\n(.*?)(?=\n\d+\s*\n|\Z)'
        matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
        
        text_lines = []
        for match in matches:
            # 清理匹配的文本内容
            text_block = match.strip()
            if text_block:
                # 分割多行文本，去除空行
                lines = [line.strip() for line in text_block.split('\n') if line.strip()]
                text_lines.extend(lines)
        
        # 如果没有匹配到，使用备用方法：逐行解析
        if not text_lines:
            lines = content.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue
                
                # 检查是否是序号（纯数字）
                if line.isdigit():
                    i += 1
                    # 跳过时间戳行（包含 -->）
                    if i < len(lines) and '-->' in lines[i]:
                        i += 1
                    # 读取文本内容（直到遇到空行或下一个序号）
                    while i < len(lines):
                        text_line = lines[i].strip()
                        if not text_line:
                            break
                        if text_line.isdigit():
                            break
                        text_lines.append(text_line)
                        i += 1
                else:
                    i += 1
        
        return '\n'.join(text_lines) if text_lines else None


    def check_video_status(self,video_detail):
        """检查单个视频的下载、转录和摘要状态"""
        status_parts = []
        video_file = None
        audio_file = None
        
        # 使用可重用的方法生成文件名前缀（用于匹配，使用50字符）
        filename_prefix = self.downloader.generate_video_prefix( video_detail )
        
        # 检查是否已下载 - 只扫描 .mp4 文件
        for filename in os.listdir(self.youtube_dir):
            # 只检查 .mp4 文件
            if not filename_prefix in filename:
                continue
            if filename.lower().endswith('.mp4'):
                video_file = os.path.join(self.youtube_dir, filename)
                video_detail['video_path'] = video_file
            elif filename.lower().endswith('.mp3'):
                audio_file = os.path.join(self.youtube_dir, filename)
                video_detail['audio_path'] = audio_file
            elif filename.lower().endswith('.wav'):
                audio_file = os.path.join(self.youtube_dir, filename)
                a = self.downloader.ffmpeg_audio_processor.to_mp3(audio_file)
                safe_remove(audio_file)
                audio_file = f"{self.youtube_dir}/__{filename_prefix}.mp3"
                safe_copy_overwrite(a, audio_file)
                video_detail['audio_path'] = audio_file
        
        if video_file and not audio_file:
            a = self.downloader.ffmpeg_audio_processor.extract_audio_from_video(video_file, "mp3")
            audio_file = f"{self.youtube_dir}/__{filename_prefix}.mp3"
            safe_copy_overwrite(a, audio_file)
            video_detail['audio_path'] = audio_file

        if video_file or audio_file:
            status_parts.append("✅ 已下载")
        else:
            status_parts.append("⬜ 未下载")
        
        # 检查是否已转录 - 检查 .srt 文件（转录生成的字幕文件）
        has_transcript = False
        for filename in os.listdir(self.youtube_dir):
            if filename_prefix in filename and (filename.endswith('.srt') or filename.endswith('.json')):
                has_transcript = True
                break
        if has_transcript:
            status_parts.append("✅ 已转录")
        else:
            status_parts.append("⬜ 未转录")
        
        # 检查是否已生成摘要 - 检查 video_detail 中是否有非空的 'summary' 字段
        summary = video_detail.get('summary', '')
        if summary and summary.strip():
            status_parts.append("✅ 已摘要")
        else:
            status_parts.append("⬜ 未摘要")
        
        return " ".join(status_parts), video_file, audio_file


    def get_video_detail(self, video_url):
        video_detail = None
        for video in self.channel_videos:
            if video.get('url') == video_url:
                video_detail = video
                break
        return video_detail


    def match_video_file(self, video_detail, field, postfixs):
        prefix = self.downloader.generate_video_prefix(video_detail)
        for file in os.listdir(self.youtube_dir):
            if not prefix in file:
                continue
            for postfix in postfixs:
                if file.endswith(postfix):
                    file = os.path.join(self.youtube_dir, file)
                    video_detail[field] = file
                    return video_detail
        return None


    def update_text_content(self, video_url, video_detail=None, transcribed_file=None):
        if not video_url and not video_detail:
            return None
        if not video_detail:
            video_detail = self.get_video_detail(video_url)
            if not video_detail:
                return None

        if transcribed_file:
            video_detail['transcribed_file'] = transcribed_file
        else:    
            transcribed_file = video_detail.get('transcribed_file', '')
            if not transcribed_file:
                return video_detail

        # 如果已有摘要，立即返回
        if video_detail.get('summary', ''):
            return video_detail

        text_content = self.fetch_text_content(transcribed_file)
        url = video_detail.get('url', '')
        # 摘要生成改为后台线程执行（非阻塞）
        def generate_summary_background(url, text_content):
            """在后台线程中生成摘要"""
            try:
                summary = self.llm_api.generate_text(
                    config_prompt.SUMMERIZE_COUNSELING_STORY_SYSTEM_PROMPT.format(language='Chinese'), 
                    text_content
                )
                video_detail = self.get_video_detail(url)
                video_detail['summary'] = summary
                video_detail.pop('description', None)
                # 保存更新后的摘要
                with open(self.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.channel_videos, f, ensure_ascii=False, indent=2)
                print(f"✅ 摘要生成完成并已保存: {video_detail.get('title', 'Unknown')[:50]}")
            except Exception as e:
                print(f"❌ 摘要生成失败: {str(e)}")
        
        # 启动后台线程
        thread = threading.Thread(target=generate_summary_background, args=(url, text_content))
        thread.daemon = True
        thread.start()

        return video_detail


    def get_channel_name(self, video_detail):
        # 从第一个视频获取频道名 - 尝试多个字段
        if not video_detail:
            return 'Unknown'
        channel_name = video_detail.get('channel', 'Unknown')
        if channel_name.lower() == 'unknown':
            channel_name = video_detail.get('uploader', 'Unknown')
        if channel_name.lower() == 'unknown':
            channel_name = video_detail.get('channel_id', 'Unknown')
        print(f"📺 频道名称: {channel_name}")
        print(f"🔍 调试信息 - channel: {video_detail.get('channel')}, uploader: {video_detail.get('uploader')}, channel_id: {video_detail.get('channel_id')}")
        return channel_name


    def _show_channel_videos_dialog(self):
        # 创建视频管理对话框
        dialog = tk.Toplevel(self.root)
        dialog.title(f"热门视频管理 - {self.channel_name}")
        dialog.geometry("1500x650")
        dialog.transient(self.root)
        
        # 顶部信息和控制栏
        top_frame = ttk.Frame(dialog)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 第一行：信息标签和刷新按钮
        info_frame = ttk.Frame(top_frame)
        info_frame.pack(fill=tk.X, pady=(0, 5))
        
        info_text = f"频道: {self.channel_name} | 共 {len(self.channel_videos)} 个视频"
        info_label = ttk.Label(info_frame, text=info_text, font=("Arial", 12, "bold"))
        info_label.pack(side=tk.LEFT)
        
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
        sort_mode_var = tk.StringVar(value="view_count")  # 默认按观看次数排序
        
        def toggle_sort():
            """切换排序方式"""
            if sort_mode_var.get() == "view_count":
                sort_mode_var.set("upload_date")
                sort_button.config(text="排序: 上传日期 ↓")
            else:
                sort_mode_var.set("view_count")
                sort_button.config(text="排序: 观看次数 ↓")
            populate_tree()
        
        sort_button = ttk.Button(control_frame, text="排序: 观看次数 ↓", command=toggle_sort)
        sort_button.pack(side=tk.LEFT, padx=5)
        
        # 绑定回车键自动应用过滤
        min_view_entry.bind('<Return>', lambda e: populate_tree())
        
        # Smart Select 功能
        ttk.Label(control_frame, text="智能选择:").pack(side=tk.LEFT, padx=(10, 5))
        smart_select_var = tk.StringVar()
        smart_select_entry = ttk.Entry(control_frame, textvariable=smart_select_var, width=20)
        smart_select_entry.pack(side=tk.LEFT, padx=(0, 5))
        

        def smart_select():
            """根据输入文本智能选择匹配的视频"""
            search_text = smart_select_var.get().strip().lower()
            if not search_text:
                return
            
            tree.selection_remove(*tree.selection())
            
            # 搜索并选择匹配的视频
            matched_count = 0
            for item in tree.get_children():
                item_tags = tree.item(item, "tags")
                if item_tags:
                    video_title = item_tags[1]
                    if search_text in video_title.lower():
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
        columns = ("title", "views", "duration", "upload_date", "status")
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
        
        tree.column("#0", width=20, anchor="center")
        tree.column("title", width=500, anchor="w")
        tree.column("views", width=40, anchor="e")
        tree.column("duration", width=40, anchor="center")
        tree.column("upload_date", width=60, anchor="center")
        tree.column("status", width=200, anchor="center")
        

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
            for video in self.channel_videos:
                view_count = video.get('view_count', 0)
                if view_count >= min_view_count:
                    filtered_videos.append(video)
            
            # 排序视频
            sort_mode = sort_mode_var.get()
            if sort_mode == "view_count":
                # 按观看次数降序排序
                filtered_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
            elif sort_mode == "upload_date":
                # 按上传日期降序排序（最新的在前）
                filtered_videos.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
            
            # 检查视频状态并填充数据
            downloaded_count = 0
            transcribed_count = 0
            summarized_count = 0
            
            for idx, video in enumerate(filtered_videos, 1):
                # 格式化时长
                duration_sec = video.get('duration', 0)
                duration_str = f"{duration_sec // 60}:{duration_sec % 60:02d}" if duration_sec else "N/A"
                
                # 格式化观看次数
                view_count = video.get('view_count', 0)
                view_str = f"{view_count:,}" if view_count else "N/A"
                
                # 格式化上传日期
                upload_date = video.get('upload_date', '')
                if upload_date and len(upload_date) == 8:  # YYYYMMDD
                    upload_date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
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
                
                tree.insert("", tk.END, text=str(idx), 
                           values=(
                               video.get('title', 'Unknown')[:60],
                               view_str,
                               duration_str,
                               upload_date_str,
                               status_str
                           ),
                           tags=(   video.get('url', ''), 
                                    video.get('title', 'Unknown'), 
                                    video_file or '', 
                                    audio_file or '', 
                                    str(view_count), 
                                    video.get('upload_date', ''), 
                                    str(duration_sec), 
                                    self.channel_name)
                                )
            
            with open(self.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.channel_videos, f, ensure_ascii=False, indent=2)

            # 更新顶部信息标签
            info_text = f"频道: {self.channel_name} | 共 {len(filtered_videos)}/{len(self.channel_videos)} 个视频 | 已下载: {downloaded_count} | 已转录: {transcribed_count} | 已摘要: {summarized_count}"
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
                item_tags = tree.item(item, "tags")
                if not item_tags:
                    continue
                
                video_url = item_tags[0]
                
                # 找到对应的视频数据
                video_detail = self.get_video_detail(video_url)
                if video_detail:
                    videos_to_remove.append(video_detail)
                    filename_prefix = self.downloader.generate_video_prefix(video_detail)
                    if os.path.exists(self.youtube_dir):
                        for filename in os.listdir(self.youtube_dir):
                            if filename_prefix in filename:
                                file_path = os.path.join(self.youtube_dir, filename)
                                # 收集SRT和TXT文件
                                if filename.endswith('.srt') or filename.endswith('.json') or filename.endswith('.mp4') or filename.endswith('.mp3') or filename.endswith('.wav'):
                                    files_to_delete.append(file_path)
            
            # 删除文件
            for file_path in files_to_delete:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"✅ 已删除文件: {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"❌ 删除文件失败 {os.path.basename(file_path)}: {str(e)}")
                    failed_count += 1
            
            # 从videos列表中移除
            for video_detail in videos_to_remove:
                if video_detail in self.channel_videos:
                    self.channel_videos.remove(video_detail)
                    deleted_count += 1
            
            # 保存回JSON文件
            try:
                with open(self.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.channel_videos, f, ensure_ascii=False, indent=2)
                print(f"✅ 已保存更新后的视频列表到: {self.channel_list_json}")
            except Exception as e:
                print(f"❌ 保存视频列表失败: {str(e)}")
                messagebox.showerror("错误", f"保存视频列表失败: {str(e)}", parent=dialog)
                return
            
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


        def on_double_click(event):
            """双击事件处理：提取SRT内容并显示（异步执行，不阻塞UI）"""
            # 获取被双击的项目
            item = tree.identify_row(event.y)
            if not item:
                return
            
            # 选中该项目（如果还没有选中）
            if item not in tree.selection():
                tree.selection_set(item)
            
            item_tags = tree.item(item, "tags")
            if not item_tags:
                return
            
            # 异步调用 update_text_content（不阻塞UI）
            def update_async():
                self.update_text_content(item_tags[0])
                messagebox.showinfo("提示", "摘要生成中，请稍后...", parent=dialog)
            
            # 在后台线程中执行
            thread = threading.Thread(target=update_async)
            thread.daemon = True
            thread.start()
        
        # 绑定双击事件
        tree.bind("<Double-1>", on_double_click)
        
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


        def summarize_selected():
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            for item in selected_items:
                item_tags = tree.item(item, "tags")
                self.update_text_content(item_tags[0])
            messagebox.showinfo("提示", "摘要生成中，请稍后...", parent=dialog)


        def download_selected():
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            # 获取选中视频的信息
            selected_videos = []
            for item in selected_items:
                item_tags = tree.item(item, "tags")
                video_detail = self.get_video_detail(item_tags[0])
                if video_detail:
                    selected_videos.append(video_detail)
            
            if not selected_videos:
                messagebox.showwarning("提示", "无法获取视频信息", parent=dialog)
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
                        print(f"[{idx}/{total}] 下载: {video_detail['title']}")
                        # 使用可重用的方法生成文件名前缀（下载时使用100字符）
                        #file_path = self.downloader.download_video_highest_resolution(video_detail)
                        file_path = self.downloader.download_audio_only(video_detail)
                        video_detail['audio_path'] = file_path
                        
                        if file_path and os.path.exists(file_path):
                            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                            print(f"✅ 完成: {os.path.basename(file_path)} ({file_size:.1f} MB)")
                            video_detail["status"] = "success"
                            completed[0] += 1
                        else:
                            print(f"❌ 失败: {video_detail['title']}")
                            video_detail["status"] = "failed"
                            failed[0] += 1
                        
                    except Exception as e:
                        print(f"❌ 错误: {video_detail['title']} - {str(e)}")
                        video_detail["status"] = "failed"
                        failed[0] += 1
                
                # 下载完成
                print(f"\n{'='*50}")
                print(f"批量下载完成！")
                print(f"成功: {completed[0]} 个")
                print(f"失败: {failed[0]} 个")
                
                with open(self.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.channel_videos, f, ensure_ascii=False, indent=2)
                    print(f"✅ 已保存更新后的视频列表到: {self.channel_list_json}")
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
            videos_not_downloaded = []
            
            for item in selected_items:
                item_tags = tree.item(item, "tags")
                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue

                video_file = self.match_video_file(video_detail,'video_path',['.mp4'])
                audio_file = self.match_video_file(video_detail,'audio_path',['.mp3'])
                if not video_file and not audio_file:
                    videos_not_downloaded.append(video_detail)
                    continue

                transcribed_file = self.match_video_file(video_detail,'transcribed_file', ['.srt','.zh.srt','.en.srt','.json','.zh.json','.en.json'])
                if transcribed_file:
                    self.update_text_content(None, video_detail)
                    videos_already_transcribed.append(video_detail)
                else:
                    videos_to_transcribe.append(video_detail)

            # 如果没有可转录的视频，显示提示
            if not videos_to_transcribe:
                messagebox.showwarning("提示", "选中的视频都未下载，请先下载。", parent=dialog)
                return
            
            message = f"将转录 {len(videos_to_transcribe)} 个视频\n\n是否继续？"
            if not messagebox.askyesno("确认转录", message, parent=dialog):
                return

            # 开始转录（不关闭对话框，转录完成后刷新列表）
            self.downloader._check_and_update_cookies()

            basic_info = self.downloader.find_video_basic(videos_to_transcribe[0])
            if basic_info:
                # subtitles 和 auto_captions 的格式示例：
                # subtitles = {
                #     'zh': [{'ext': 'vtt', 'url': 'https://...'}, {'ext': 'srt', 'url': 'https://...'}],
                #     'en': [{'ext': 'vtt', 'url': 'https://...'}],
                #     'zh-Hans': [{'ext': 'vtt', 'url': 'https://...'}]
                # }
                # auto_captions = {
                #     'zh': [{'ext': 'vtt', 'url': 'https://...'}],
                #     'en': [{'ext': 'vtt', 'url': 'https://...'}, {'ext': 'srt', 'url': 'https://...'}]
                # }
                # 键是语言代码（如 'zh', 'en', 'zh-Hans'），值是包含字幕格式信息的列表
                subtitles = basic_info.get('subtitles', {})
                auto_captions = basic_info.get('automatic_captions', {})
                # 将字典的键（语言代码）转换为列表
                all_languages = list(subtitles.keys() if subtitles else []) + list(auto_captions.keys() if auto_captions else [])
                # 去重并保持顺序
                all_languages = list(dict.fromkeys(all_languages))
            if not all_languages:
                all_languages = ["zh", "en"]

            target_lang = askchoice("选择语言", all_languages, parent=dialog)
            if not target_lang:
                return

            # 初始化计数器
            success_count = 0
            failed_count = 0

            for idx, video_detail in enumerate(videos_to_transcribe, 1):
                try:
                    downloaded_file = self.downloader.download_captions( video_detail, target_lang )
                    if downloaded_file:
                        print(f"  ✅ 转录成功")
                        self.update_text_content(None, video_detail, downloaded_file)
                        success_count += 1
                    else:
                        print(f"  ❌ 转录失败：无法下载字幕")
                        failed_count += 1
                        
                except Exception as e:
                    print(f"  ❌ 转录失败: {str(e)}")
                    failed_count += 1
            
            # 保存更新后的视频列表
            with open(self.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.channel_videos, f, ensure_ascii=False, indent=2)
            
            # 显示完成信息
            print(f"\n{'='*50}")
            print(f"转录任务完成！成功: {success_count} 个，失败: {failed_count} 个")
            
            # 刷新列表
            populate_tree()


        def compile_selected():
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            user_prompt = "case story: \n"  # 暂时为空，等待实现用户输入对话框
            # popup dialog to ask user to input the case story
            case_story = simpledialog.askstring("输入案例故事", "请输入案例故事", parent=dialog)
            if case_story:
                user_prompt += case_story
            else:
                return

            for item in selected_items:
                item_tags = tree.item(item, "tags")

                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue
                text_content = self.fetch_text_content(video_detail.get('transcribed_file', ''))
                user_prompt += "Title: " + video_detail['title'] + "\n\n" + "Content: " + text_content + "\n----------------------------\n\n\n"

            system_prompt = config_prompt.COMPILE_COUNSELING_STORY_SYSTEM_PROMPT
            response = self.llm_api.generate_text(system_prompt, user_prompt)
            
            # popup dialog to show response
            response_dialog = tk.Toplevel(dialog)
            response_dialog.title("编撰结果")
            response_dialog.geometry("700x500")
            response_dialog.transient(dialog)
            response_dialog.grab_set()
            
            # 创建可滚动的文本框来显示响应内容
            text_frame = ttk.Frame(response_dialog)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            response_text = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, width=80, height=25)
            response_text.pack(fill=tk.BOTH, expand=True)
            response_text.insert(tk.END, response)
            response_text.config(state=tk.DISABLED)  # 设置为只读
            
            # 自动复制到剪贴板
            response_dialog.clipboard_clear()
            response_dialog.clipboard_append(response)
            
            # 按钮框架
            button_frame = ttk.Frame(response_dialog)
            button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
            
            ttk.Button(button_frame, text="关闭", command=response_dialog.destroy).pack(side=tk.RIGHT, padx=5)

        # 在所有函数定义后创建按钮
        ttk.Button(bottom_frame, text="全选", command=select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="不选", command=deselect_all).pack(side=tk.LEFT, padx=5)

        ttk.Button(bottom_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="编撰", command=compile_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="摘要", command=summarize_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="转录", command=transcribe_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="下载", command=download_selected).pack(side=tk.RIGHT, padx=5)


    def fetch_hot_videos(self):
        """获取频道热门视频列表，保存到JSON文件"""
        # 第一步：输入URL和参数
        url_dialog = tk.Toplevel(self.root)
        url_dialog.title("获取热门视频列表")
        url_dialog.geometry("600x200")
        url_dialog.transient(self.root)
        url_dialog.grab_set()
        
        # URL输入框
        url_frame = ttk.Frame(url_dialog)
        url_frame.pack(fill=tk.X, padx=20, pady=20)
        ttk.Label(url_frame, text="频道或播放列表URL:").pack(side=tk.LEFT)
        channel_url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=channel_url_var, width=50)
        url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 参数输入
        param_frame = ttk.Frame(url_dialog)
        param_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Label(param_frame, text="最大视频数量:").pack(side=tk.LEFT, padx=5)
        max_videos_var = tk.StringVar(value="200")
        max_videos_entry = ttk.Entry(param_frame, textvariable=max_videos_var, width=10)
        max_videos_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(param_frame, text="最小观看次数:").pack(side=tk.LEFT, padx=5)
        min_view_count_var = tk.StringVar(value="200")
        min_view_count_entry = ttk.Entry(param_frame, textvariable=min_view_count_var, width=10)
        min_view_count_entry.pack(side=tk.LEFT, padx=5)
        
        result_var = tk.StringVar(value="cancel")
        
        def on_url_confirm():
            url = channel_url_var.get().strip()
            if not url:
                messagebox.showerror("错误", "请输入URL", parent=url_dialog)
                return
            result_var.set("confirm")
            url_dialog.destroy()
        
        def on_url_cancel():
            result_var.set("cancel")
            url_dialog.destroy()

        # 按钮
        button_frame = ttk.Frame(url_dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Button(button_frame, text="确认", command=on_url_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_url_cancel).pack(side=tk.LEFT, padx=5)
        
        # 等待对话框关闭
        self.root.wait_window(url_dialog)
        
        if result_var.get() == "cancel":
            return
        
        channel_url = channel_url_var.get().strip()
        if not channel_url.endswith("/videos"):
            if channel_url.endswith("/"):
                channel_url = channel_url[:-1]
            channel_url = channel_url + "/videos"

        # 显示加载对话框
        loading_dialog = tk.Toplevel(self.root)
        loading_dialog.title("获取视频列表中")
        loading_dialog.geometry("300x100")
        loading_dialog.transient(self.root)
        loading_dialog.grab_set()
        ttk.Label(loading_dialog, text="正在获取视频列表，请稍候...", font=("Arial", 12)).pack(pady=30)
        self.root.update()
        
        # 在后台线程中获取视频列表
        fetch_complete = [False]  # 用于跟踪是否完成

        def fetch_video_list():
            try:
                self.channel_videos = self.downloader.list_hot_videos(
                    channel_url, 
                    max_videos=int(max_videos_var.get()), 
                    min_view_count=int(min_view_count_var.get())
                )
            except Exception as e:
                error_msg = str(e)
            finally:
                fetch_complete[0] = True
        
        thread = threading.Thread(target=fetch_video_list)
        thread.daemon = True
        thread.start()
        
        # 使用轮询方式等待完成，而不是 join()
        def check_completion():
            if fetch_complete[0]:
                loading_dialog.destroy()
                
                if not self.channel_videos:
                    messagebox.showwarning("提示", "未找到符合条件的视频")
                    return
            else:
                # 继续检查，每100ms检查一次
                self.root.after(100, check_completion)
        
        # 开始检查
        self.root.after(100, check_completion)



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
        
        # 语言选择
        lang_frame = ttk.Frame(dialog)
        ttk.Label(lang_frame, text="语言:").pack(side=tk.LEFT, padx=(20, 0))
        target_lang_var = tk.StringVar(value="zh")
        target_lang_combo = ttk.Combobox(lang_frame, textvariable=target_lang_var, 
                                          values=["zh", "en", "ja", "ko", "es", "fr", "de"], 
                                          width=10, state="readonly")
        target_lang_combo.pack(side=tk.LEFT, padx=5)
        
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
        target_lang = target_lang_var.get()
        
        # 确认下载
        if not messagebox.askyesno("确认下载", f"确定要下载并转录这个视频吗？\n\nURL: {video_url}\n目标语言: {target_lang}\n\n转录结果将保存到项目的 Youtbue_download 文件夹中。"):
            return
        
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "type": "download_youtube",
            "status": "运行中",
            "start_time": datetime.now(),
            "pid": self.pid
        }
        
        def run_task():
            print(f"📥 开始下载YouTube视频并转录...")
            print(f"URL: {video_url}")
            print(f"语言: {target_lang}")

            self.downloader._check_and_update_cookies()

            video_data = self.downloader.get_video_detail(video_url, channel_name='Unknown')
            if not video_data:
                self.root.after(0, lambda: messagebox.showerror("错误", "获取视频详情失败"))
                return

            channel_name = self.get_channel_name(video_data)
        
            self.channel_list_json = f"{self.youtube_dir}/{channel_name}_hotvideos.json"
            if os.path.exists(self.channel_list_json):
                self.channel_videos = json.load(open(self.channel_list_json, 'r', encoding='utf-8'))

            if not self.channel_videos:
                self.root.after(0, lambda: messagebox.showerror("错误", "获取视频列表失败"))
                return

            file_path = self.downloader.download_video_highest_resolution(video_data)

            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                video_data["video_path"] = file_path
                video_data["file_size_mb"] = file_size
                video_data["status"] = "success"
            else:
                self.root.after(0, lambda: messagebox.showerror("错误", "视频下载失败"))
                return
            
            if transcribe:
                transcribed_file = self.downloader.download_captions( video_data, target_lang )
                if transcribed_file:
                    print(f"✅ YouTube视频转录完成！")
                    video_data['transcribed_file'] = transcribed_file
                    self.tasks[task_id]["status"] = "完成"
                    self.tasks[task_id]["result"] = transcribed_file
                    self.root.after(0, lambda: messagebox.showinfo("转录完成", "YouTube视频转录完成！"))
                else:
                    print(f"❌ YouTube视频转录失败")
                    self.tasks[task_id]["status"] = "失败"
                    self.tasks[task_id]["error"] = "转录失败，未生成字幕文件"
                    self.root.after(0, lambda: messagebox.showerror("错误", "YouTube视频转录失败：未生成字幕文件"))
            
            self.channel_videos.append(video_data)
            with open(self.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.channel_videos, f, ensure_ascii=False, indent=2)
                print(f"✅ 已保存更新后的视频列表到: {self.channel_list_json}")

        # 在独立线程中运行任务
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
