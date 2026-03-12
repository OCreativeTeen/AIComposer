import os
import yt_dlp
import subprocess
import shutil
import json
import re
import threading
import glob

import config
import config_prompt
from datetime import datetime

import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility import llm_api
from utility.audio_transcriber import AudioTranscriber
from utility.file_util import write_json, safe_copy_overwrite, safe_remove
from gui.choice_dialog import askchoice
        
# 导入所需模块
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
import tkinter.simpledialog as simpledialog

        

class MediaDownloader:

    def __init__(self, pid, youtube_path):
        print("YoutubeDownloader init...")
        self.pid = pid
        self.youtube_dir = youtube_path
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)

        self.channel_list_json = ""
        self.channel_videos = []
        self.channel_name = ""
        self.latest_date = datetime.now()

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
            # 如果未找到且不需要等待，返回 False
            if not wait_forever:
                return False
            # show a dialog to tell user to save the new cookies file to the download folder
            messagebox.showinfo("提示", "请将新的 cookies 文件保存到下载文件夹")


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
        if os.path.exists(self.cookie_file) and os.path.getsize(self.cookie_file) > 0:
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
                audio_path = self.youtube_dir + "/media/__" + self.generate_video_prefix(video_detail) + ".mp3"
                safe_copy_overwrite(self.ffmpeg_audio_processor.extract_audio_from_video(video_path, "mp3"), audio_path)
                video_detail['audio_path'] = audio_path
            else:
                audio_path = self.download_audio_only(video_detail)

            if not audio_path:
                print(f"❌ 音频文件不存在")
                return None

        script_json = self.transcriber.transcribe_with_whisper(audio_path, target_lang)
        if script_json:
            write_json(src_path, script_json)  
            return src_path
        else:
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
            self.cookie_file = None
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
        safe_title = self.make_safe_file_name(title, title_length)
        # 构建文件名前缀（用于匹配）
        return f"{view_count_str}_{date_str}_{safe_title}"


    def get_channel_name(self, video_detail):
        if not video_detail:
            return 'Unknown'
        channel_name = video_detail.get('channel', 'Unknown')
        if channel_name.lower() == 'unknown':
            channel_name = video_detail.get('uploader', 'Unknown')
        if channel_name.lower() == 'unknown':
            channel_name = video_detail.get('channel_id', 'Unknown')
        channel_name = self.make_safe_file_name(channel_name)
        print(f"📺 频道名称: {channel_name}")
        return channel_name


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


    def make_safe_file_name(self, title, title_length=15):
        if not title:
            return "untitled"
        
        # 将空格替换为下划线
        safe_title = title.replace(' ', '_')
        
        # 移除 Windows 和 Unix 系统不允许的字符
        # Windows: < > : " / \ | ? *
        # Unix: / (以及控制字符)
        safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', safe_title)
        
        # 移除 Windows 保留名称（CON, PRN, AUX, NUL, COM1-9, LPT1-9）
        reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + \
                        [f'COM{i}' for i in range(1, 10)] + \
                        [f'LPT{i}' for i in range(1, 10)]
        if safe_title.upper() in reserved_names:
            safe_title = '_' + safe_title
        
        # 移除尾随空格和点（Windows 不允许）
        safe_title = safe_title.rstrip(' .')
        
        # 如果清理后为空，使用默认名称
        if not safe_title.strip():
            safe_title = "untitled"
        
        # 限制长度
        safe_title = safe_title[:title_length] if title_length > 0 else safe_title
        
        # 再次移除尾随空格和点（可能在截断后产生）
        safe_title = safe_title.rstrip(' .')
        
        return safe_title


    def list_hot_videos(self, channel_url, max_videos=200, min_view_count=500):
        self._check_and_update_cookies()

        try:
            # 使用基础选项，包含 cookies 支持
            ydl_opts = self._get_ydl_opts_base(
                quiet=False,
                extract_flat='in_playlist',  # 只提取播放列表中的基本信息
                skip_download=True,
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
                        # entry 中已有足够信息，直接使用
                        video_data = {
                            'title': entry.get('title', 'Unknown Title'),
                            'url': video_url,
                            'id': video_id,
                            'duration': entry.get('duration', 0),
                            'view_count': entry.get('view_count', 0),
                            'uploader': entry.get('uploader', channel_name),
                            'channel': channel_name,
                            'channel_id': entry.get('channel_id', ''),
                            'upload_date': entry.get('upload_date', ''),
                            'thumbnail': entry.get('thumbnail', ''),
                            'description': entry.get('description', '')[:200] if entry.get('description') else ''
                        }
                        print(f"✓ {count} -- {video_data['title'][:50]} -- {video_data['view_count']:,} 观看 (使用列表信息)")
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

    def fetch_channel_new_videos(self, channel_url, max_videos=200):
        """抓取频道视频列表，返回当前列表中不存在的新视频列表（不修改 channel_videos）"""
        self._check_and_update_cookies()
        try:
            ydl_opts = self._get_ydl_opts_base(
                quiet=False,
                extract_flat='in_playlist',
                skip_download=True,
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
            if not info or 'entries' not in info:
                return []
            channel_name = self.get_channel_name(info)
            new_videos = []
            for count, entry in enumerate(info['entries']):
                if count >= max_videos:
                    break
                if not entry:
                    continue
                video_url = entry.get('url', '') or entry.get('webpage_url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                video_id = entry.get('id', '')
                video_data = None
                if entry.get('view_count') is not None and entry.get('title'):
                    video_data = {
                        'title': entry.get('title', 'Unknown Title'),
                        'url': video_url,
                        'id': video_id,
                        'duration': entry.get('duration', 0),
                        'view_count': entry.get('view_count', 0),
                        'uploader': entry.get('uploader', channel_name),
                        'channel': channel_name,
                        'channel_id': entry.get('channel_id', ''),
                        'upload_date': entry.get('upload_date', ''),
                        'thumbnail': entry.get('thumbnail', ''),
                        'description': entry.get('description', '')[:200] if entry.get('description') else ''
                    }
                    print(f"✓ {count} -- {video_data['title'][:50]} -- {video_data['view_count']:,} 观看")
                else:
                    try:
                        video_data = self.get_video_detail(video_url, channel_name)
                        print(f"✓ {count} -- {video_data['title'][:50]} -- {video_data['view_count']:,} 观看")
                    except Exception as e:
                        print(f"⚠️ 跳过视频: {e}")
                        continue
                if video_data and self.is_video_new(video_data):
                    new_videos.append(video_data)
            return new_videos
        except Exception as e:
            print(f"❌ 抓取视频列表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None  # None 表示出错，[] 表示无新视频

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


    def select_language(self, video_detail):
        basic_info = self.find_video_basic(video_detail)
        if not basic_info:
            return "zh"
        subtitles = basic_info.get('subtitles', {})
        auto_captions = basic_info.get('automatic_captions', {})

        target_lang = None

        all_languages = list(subtitles.keys() if subtitles else []) + list(auto_captions.keys() if auto_captions else [])
        if all_languages:
            all_languages = list(dict.fromkeys(all_languages))
            target_lang = askchoice("选择语言", all_languages)
        if not target_lang:
            target_lang = "zh"
        return target_lang



# YouTube GUI管理类
class MediaGUIManager:
    """YouTube GUI管理器 - 处理所有YouTube相关的GUI对话框"""
    
    def __init__(self, root, channel_path, pid, tasks, log_to_output_func, download_output):
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
        
        self.llm_api = llm_api.LLMApi(llm_api.LM_STUDIO)

        # 创建YoutubeDownloader实例
        self.downloader = MediaDownloader(pid, self.youtube_dir)
        
        # 添加线程锁，保护 channel_videos 的并发访问
        self.channel_videos_lock = threading.Lock()
        
        # LLM API 并发控制：限制同时进行的 API 调用数量（默认3个）
        self.llm_api_semaphore = threading.Semaphore(3)
        
        # 跟踪活跃的摘要生成线程，确保对话框关闭时不会丢失数据
        self.active_summary_threads = []
        self.active_threads_lock = threading.Lock()

        self.topic_choices, self.topic_categories, self.tag_choices = config.load_topics(self.channel_path)
        
        # 初始化主主题分类变量
        self.main_topic_category = None

        

    def manage_hot_videos(self):
        # 查找所有热门视频JSON文件
        pattern = f"{self.youtube_dir}/list/*.json.txt"
        json_files = glob.glob(pattern)
        
        if not json_files:
            messagebox.showinfo("提示", "未找到任何热门视频列表文件\n\n请先使用 '获取热门视频' 功能获取频道视频列表")
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
        
        # 准备选项列表和映射
        channel_choices = []
        choice_to_channel = {}
        for channel in channel_data:
            choice_text = f"{channel['name']} ({channel['video_count']} 个视频)"
            channel_choices.append(choice_text)
            choice_to_channel[choice_text] = channel
        
        # 使用 askchoice 显示选择对话框
        selected_choice = askchoice("选择频道", channel_choices, parent=self.root)
        
        if not selected_choice or selected_choice not in choice_to_channel:
            return  # 用户取消或无效选择
        
        # 获取选中的频道
        channel = choice_to_channel[selected_choice]
        self.downloader.channel_list_json = channel['file']
        
        # 读出 list：同 title 只保留一条，保留 content + topic_category + topic_subtype 最完整（内容最多）的那条；每条删掉 summary；写回 JSON
        with open(self.downloader.channel_list_json, 'r', encoding='utf-8') as f:
            channel_videos = json.load(f)

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
                audio_file = f"{self.youtube_dir}/media/___{filename_prefix}.mp3"
                safe_copy_overwrite(a, audio_file)
                video_detail['audio_path'] = audio_file
        
        if video_file and not audio_file:
            a = self.downloader.ffmpeg_audio_processor.extract_audio_from_video(video_file, "mp3")
            audio_file = f"{self.youtube_dir}/media/___{filename_prefix}.mp3"
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
                video_detail['transcribed_file'] = os.path.join(self.youtube_dir, filename)
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
        for video in self.downloader.channel_videos:
            if video.get('url') == video_url:
                video_detail = video
                break
        return video_detail


    def match_video_file(self, video_detail, field, postfixs):
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


    def update_text_content(self, video_detail=None, transcribed_file=None, tag_again=False, in_background=True):
        if not video_detail:
            return None

        if transcribed_file:
            video_detail['transcribed_file'] = transcribed_file
        else:    
            transcribed_file = video_detail.get('transcribed_file', '')
            if not transcribed_file:
                return video_detail

        summary = video_detail.get('summary', '')
        topic_type = video_detail.get('topic_subtype', '')
        topic_category = video_detail.get('topic_category', '')
        problem_tags = video_detail.get('tags', '')
        if in_background and not tag_again and summary and summary.strip() and topic_type and topic_type.strip() and topic_category and topic_category.strip() and problem_tags and problem_tags.strip():
            return video_detail

        text_content = self.fetch_text_content(video_detail)
        video_detail["content"] = text_content
        url = video_detail.get('url', '')

        # 摘要生成改为后台线程执行（非阻塞）
        def generate_summary_background(url, text_content):
            """在后台线程中生成摘要，使用信号量控制并发"""
            # 使用信号量限制并发 LLM API 调用
            with self.llm_api_semaphore:
                try:
                    # 使用锁保护，获取视频详情
                    with self.channel_videos_lock:
                        video_detail = self.get_video_detail(url)
                        if not video_detail:
                            print(f"❌ 未找到视频详情: {url}")
                            return
                    
                    summary = video_detail.get('summary', '')
                    if not in_background or not summary or not summary.strip():
                        # LLM API 调用在信号量保护下（已在上层 with 语句中）
                        result = self.llm_api.generate_text(
                            config_prompt.SUMMERIZE_ONLY_COUNSELING_STORY_SYSTEM_PROMPT.format(language='Chinese', topic=video_detail.get('topic_category', '') + " - " + video_detail.get('topic_subtype', '')), 
                            text_content
                        )
                        if result:
                            # 使用锁保护，更新视频详情
                            with self.channel_videos_lock:
                                video_detail.pop('description', None)
                                video_detail['summary'] = result
                        else:
                            print(f"⚠️ 摘要生成失败: {video_detail.get('title', 'Unknown')[:50]}")
                            return

                    self.prepare_category_for_content(video_detail, text_content, self.topic_choices)

                except Exception as e:
                    print(f"❌ 后台摘要生成出错: {str(e)}")
                    import traceback
                    traceback.print_exc()
        
        
        if in_background:
            # 创建一个包装函数来清理线程引用
            def cleanup_thread():
                current_thread = threading.current_thread()
                try:
                    generate_summary_background(url, text_content)
                finally:
                    with self.active_threads_lock:
                        if current_thread in self.active_summary_threads:
                            self.active_summary_threads.remove(current_thread)
            
            thread = threading.Thread(target=cleanup_thread)
            thread.daemon = False  # 改为非 daemon 线程，确保数据保存完成，不依赖对话框
            with self.active_threads_lock:
                self.active_summary_threads.append(thread)
            thread.start()
        else:
            generate_summary_background(url, text_content)

        return video_detail



    def prepare_category_for_content(self, video_detail, text_content, topic_choices):
        # LLM API 调用在信号量保护下（已在上层 with 语句中）
        result = self.llm_api.generate_json(
            config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(language='Chinese', topic_choices=topic_choices), 
            text_content,
            expect_list=False
        )
        if result:
            # 使用锁保护，更新主题信息
            with self.channel_videos_lock:
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
                    video_detail['tags'] = [t.strip() for t in raw_tags.split(',') if t.strip()]
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
        dialog.geometry("1500x650")
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
            else:  # upload_date
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
        
        # 标注选择：对选中视频设置 status 为 "", "1", "2", "3"
        ttk.Label(control_frame, text="标注:").pack(side=tk.LEFT, padx=(10, 5))
        status_var = tk.StringVar(value="")
        status_combo = ttk.Combobox(control_frame, textvariable=status_var, values=("", "1", "2", "3"), state="readonly", width=6)
        status_combo.pack(side=tk.LEFT, padx=(0, 5))
        def on_status_selected(event=None):
            val = status_var.get()
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请先选择要标注的视频", parent=dialog)
                return
            selected_urls = set()
            for item in selected_items:
                item_tags = tree.item(item, "tags")
                if item_tags:
                    url = item_tags[0]
                    selected_urls.add(url)
                    video_detail = self.get_video_detail(url)
                    if video_detail:
                        video_detail['status'] = val
            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            populate_tree()
            # 重新选中之前选中的行（按 url 匹配）
            for item in tree.get_children():
                item_tags = tree.item(item, "tags")
                if item_tags and item_tags[0] in selected_urls:
                    tree.selection_add(item)
        status_combo.bind('<<ComboboxSelected>>', on_status_selected)
        
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
        columns = ("title", "views", "duration", "upload_date", "status", "topic_category", "topic_subtype", "tags", "mark")
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
        tree.heading("topic_category", text="主题分类")
        tree.heading("topic_subtype", text="主题子类型")
        tree.heading("tags", text="问题标签")
        tree.heading("mark", text="标注")
        
        tree.column("#0", width=20, anchor="center")
        tree.column("title", width=400, anchor="w")
        tree.column("views", width=40, anchor="e")
        tree.column("duration", width=40, anchor="center")
        tree.column("upload_date", width=60, anchor="center")
        tree.column("status", width=150, anchor="center")
        tree.column("topic_category", width=120, anchor="w")
        tree.column("topic_subtype", width=150, anchor="w")
        tree.column("tags", width=200, anchor="w")
        tree.column("mark", width=50, anchor="center")
        

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
            
            # 检查视频状态并填充数据
            downloaded_count = 0
            transcribed_count = 0
            summarized_count = 0
            hottest_degree = 0.0
            
            for idx, video in enumerate(filtered_videos, 1):
                video.pop('text_content', None)
                summary = video.get('summary', None)
                if summary:
                    video.pop('description', None)
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
                
                # 格式化上传日期
                upload_date = video.get('upload_date', '') 
                # can be YYYYMMDD  or YYYY-MM-DD
                if self.downloader.latest_date and upload_date and len(upload_date) == 8:  # YYYYMMDD
                    days = (self.downloader.latest_date - datetime.strptime(upload_date, '%Y%m%d')).days + 1
                    degree = view_count / (days if days > 0 else 1)
                    if hottest_degree < degree:
                        hottest_degree = degree
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
                
                # 获取主题相关字段
                topic_category = video.get('topic_category', '')
                topic_subtype = video.get('topic_subtype', '')
                problem_tags = video.get('tags', '')
                if isinstance(problem_tags, list):
                    problem_tags = ' | '.join(problem_tags)
                elif not isinstance(problem_tags, str):
                    problem_tags = str(problem_tags) if problem_tags else ''
                
                # video_detail 的 status 字段：用户可编辑的标注，默认 ""，可选 "", "1", "2", "3"
                user_status = video.get('status', '')
                if user_status not in ('', '1', '2', '3'):
                    user_status = ''
                tree.insert("", tk.END, text=str(idx), 
                           values=(
                               video.get('title', 'Unknown')[:60],
                               view_str,
                               duration_str,
                               upload_date_str,
                               status_str,
                               topic_category[:30] if topic_category else '',
                               topic_subtype[:30] if topic_subtype else '',
                               problem_tags[:50] if problem_tags else '',
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
                item_tags = tree.item(item, "tags")
                if not item_tags:
                    continue
                
                video_detail = self.get_video_detail(item_tags[0])
                videos_to_remove.append(video_detail)
                filename_prefix = self.downloader.generate_video_prefix(video_detail)
                for filename in os.listdir(self.youtube_dir):
                    if filename_prefix in filename:
                        file_path = os.path.join(self.youtube_dir, filename)
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


        def edit_topic_info(video_detail):
            """编辑视频的主题信息对话框"""
            edit_dialog = tk.Toplevel(dialog)
            edit_dialog.title("编辑主题信息")
            edit_dialog.geometry("700x550")
            edit_dialog.transient(dialog)
            edit_dialog.grab_set()
            
            # 获取当前值
            current_category = video_detail.get('topic_category', '')
            current_subtype = video_detail.get('topic_subtype', '')
            current_status = video_detail.get('status', '')
            if current_status not in ('', '1', '2', '3'):
                current_status = ''
            current_tags_raw = video_detail.get('tags', '')
            if isinstance(current_tags_raw, list):
                current_tags = ', '.join(str(t) for t in current_tags_raw)
            elif isinstance(current_tags_raw, str):
                current_tags = current_tags_raw
            else:
                current_tags = str(current_tags_raw) if current_tags_raw else ''
            
            # 主题分类选择
            ttk.Label(edit_dialog, text="主题分类:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
            category_var = tk.StringVar(value=current_category)
            category_combo = ttk.Combobox(edit_dialog, textvariable=category_var, values=self.topic_categories, state="readonly", width=50)
            category_combo.grid(row=0, column=1, padx=10, pady=5, sticky='ew')
            
            # 主题子类型选择
            ttk.Label(edit_dialog, text="主题子类型:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
            subtype_var = tk.StringVar(value=current_subtype)
            subtype_combo = ttk.Combobox(edit_dialog, textvariable=subtype_var, values=[], state="readonly", width=50)
            subtype_combo.grid(row=1, column=1, padx=10, pady=5, sticky='ew')
            
            # 标注选择 (status: "", "1", "2", "3")
            ttk.Label(edit_dialog, text="标注:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
            status_var = tk.StringVar(value=current_status)
            status_combo = ttk.Combobox(edit_dialog, textvariable=status_var, values=("", "1", "2", "3"), state="readonly", width=10)
            status_combo.grid(row=2, column=1, padx=10, pady=5, sticky='w')
            
            # 辅助：解析标签为 analysis(无=) 与 manual(name=value)
            def _parse_tags_to_parts(tags_text):
                parts = [t.strip() for t in re.split(r'[|,]', tags_text or '') if t.strip()]
                analysis = [p for p in parts if '=' not in p]
                manual = [p for p in parts if '=' in p]
                return analysis, manual
            
            # 主题标签（可编辑，支持 a,b, GENRE=Jazz 格式）
            ttk.Label(edit_dialog, text="主题标签 (可编辑, 用 , 或 | 分隔):").grid(row=3, column=0, sticky='nw', padx=10, pady=5)
            tags_var = tk.StringVar(value=current_tags)
            tags_entry = ttk.Entry(edit_dialog, textvariable=tags_var, width=60)
            tags_entry.grid(row=3, column=1, padx=10, pady=5, sticky='ew')
            
            # tag_choices 多选组（来自 tags.json，如 GENRE=、Rhythm=，值用/连接）
            tag_radio_refs = []
            row_tag_radios = 4
            if self.tag_choices:
                tag_radios_frame = ttk.LabelFrame(edit_dialog, text="标签选择 (name=value，可多选，值用/连接)", padding=5)
                tag_radios_frame.grid(row=row_tag_radios, column=0, columnspan=2, sticky='ew', padx=10, pady=5)
                tag_radios_frame.columnconfigure(0, weight=1)
                existing_manual = {t.split('=', 1)[0]: t.split('=', 1)[-1] for t in _parse_tags_to_parts(current_tags)[1]}
                for tag_item in self.tag_choices:
                    if not isinstance(tag_item, dict):
                        continue
                    tag_type = tag_item.get('tag_type', '')
                    tags_list = tag_item.get('tags') or []
                    if not tags_list:
                        continue
                    r = ttk.LabelFrame(tag_radios_frame, text=f"{tag_type}:", padding=3)
                    r.pack(fill=tk.X, pady=3)
                    existing_vals = existing_manual.get(tag_type, '').split('/') if existing_manual.get(tag_type) else []
                    existing_set = {v.strip() for v in existing_vals if v.strip()}
                    check_vars = []
                    inner = ttk.Frame(r)
                    inner.pack(fill=tk.X, expand=True)
                    n_cols = 10
                    for col_idx, val in enumerate(sorted(tags_list)):
                        ri, ci = col_idx // n_cols, col_idx % n_cols
                        cb_var = tk.BooleanVar(value=val in existing_set)
                        cb = ttk.Checkbutton(inner, text=val, variable=cb_var, command=lambda: _sync_tags_from_radios())
                        cb.grid(row=ri, column=ci, sticky='w', padx=(0, 8), pady=1)
                        check_vars.append((val, cb_var))
                    for c in range(n_cols):
                        inner.columnconfigure(c, weight=1)
                    tag_radio_refs.append((tag_type, check_vars))
                row_tag_radios += 1
            
            def _sync_tags_from_radios():
                """从多选组更新 tags_var：保留分析标签 + 手动 name=value（多选用/连接）"""
                analysis, _ = _parse_tags_to_parts(tags_var.get())
                manual = []
                for tag_type, check_vars in tag_radio_refs:
                    vals = [v for v, cb_var in check_vars if cb_var.get()]
                    if vals:
                        manual.append(f"{tag_type}={'/'.join(vals)}")
                combined = analysis + manual
                tags_var.set(', '.join(combined))
            
            
            # 标签选择列表（来自 topics 子类型的可选标签）
            ttk.Label(edit_dialog, text="可选标签:").grid(row=row_tag_radios, column=0, sticky='nw', padx=10, pady=5)
            tags_listbox_frame = ttk.Frame(edit_dialog)
            tags_listbox_frame.grid(row=row_tag_radios, column=1, padx=10, pady=5, sticky='nsew')
            
            tags_listbox = tk.Listbox(tags_listbox_frame, selectmode=tk.EXTENDED, height=8)
            tags_listbox_scrollbar = ttk.Scrollbar(tags_listbox_frame, orient=tk.VERTICAL, command=tags_listbox.yview)
            tags_listbox.configure(yscrollcommand=tags_listbox_scrollbar.set)
            tags_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tags_listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
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
                if current_subtype in subtypes:
                    subtype_var.set(current_subtype)
                else:
                    subtype_var.set('')
                update_tags()
            
            def update_tags(*args):
                """根据选择的子类型更新标签选项"""
                selected_category = category_var.get()
                selected_subtype = subtype_var.get()
                tags = []
                if selected_category and selected_subtype and self.topic_choices:
                    for item in self.topic_choices:
                        if isinstance(item, dict) and item.get('topic_category') == selected_category:
                            for subtype_item in item.get('topic_subtypes', []):
                                # 匹配选中的 topic_subtype
                                if isinstance(subtype_item, dict) and subtype_item.get('topic_subtype') == selected_subtype:
                                    # tags 为字符串数组，直接使用
                                    for tag in subtype_item.get('tags', []):
                                        if tag not in tags:
                                            tags.append(tag)
                tags_listbox.delete(0, tk.END)
                for tag in tags:
                    tags_listbox.insert(tk.END, tag)
            
            def add_selected_tags():
                """将选中的标签添加到输入框"""
                selected_indices = tags_listbox.curselection()
                if selected_indices:
                    current_tags_text = tags_var.get().strip()
                    selected_tags = [tags_listbox.get(i) for i in selected_indices]
                    new_part = ', '.join(selected_tags)
                    if current_tags_text:
                        tags_var.set(f"{current_tags_text}, {new_part}")
                    else:
                        tags_var.set(new_part)

            # 绑定事件
            category_combo.bind('<<ComboboxSelected>>', update_subtypes)
            subtype_combo.bind('<<ComboboxSelected>>', update_tags)
            
            # 添加标签按钮
            add_tags_btn = ttk.Button(edit_dialog, text="添加选中标签", command=add_selected_tags)
            add_tags_btn.grid(row=row_tag_radios + 1, column=1, padx=10, pady=5, sticky='w')

            # 初始化
            if current_category:
                update_subtypes()
            
            # 按钮框架
            button_frame = ttk.Frame(edit_dialog)
            button_frame.grid(row=row_tag_radios + 2, column=0, columnspan=2, pady=20)
            
            def save_changes():
                """保存更改"""
                category = category_var.get().strip()
                subtype = subtype_var.get().strip()
                tags_text = tags_var.get().strip()
                
                # 解析标签（支持 , 或 | 分隔，保留 GENRE=xxx 等格式）
                if tags_text:
                    tags_list = [tag.strip() for tag in re.split(r'[|,]', tags_text) if tag.strip()]
                else:
                    tags_list = []
                
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
                
                # 保存标注 (status)
                st = status_var.get()
                if st in ('', '1', '2', '3'):
                    video_detail['status'] = st
                else:
                    video_detail.pop('status', None)
                
                # 保存到文件
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                
                # 刷新树视图
                populate_tree()
                edit_dialog.destroy()
            
            ttk.Button(button_frame, text="保存", command=save_changes).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="取消", command=edit_dialog.destroy).pack(side=tk.LEFT, padx=5)
            
            # 配置网格权重
            edit_dialog.columnconfigure(1, weight=1)
            edit_dialog.rowconfigure(row_tag_radios, weight=1)
        
        def edit_selected_topics():
            """编辑选中视频的主题信息"""
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            
            # 只编辑第一个选中的视频
            item = selected_items[0]
            item_tags = tree.item(item, "tags")
            if item_tags:
                video_detail = self.get_video_detail(item_tags[0])
                if video_detail:
                    edit_topic_info(video_detail)
        
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
            
            item_tags = tree.item(item, "tags")
            video_detail = self.get_video_detail(item_tags[0])
            if not video_detail:
                return

            summary = video_detail.get('summary', '')
            topic_type = video_detail.get('topic_subtype', '')
            topic_category = video_detail.get('topic_category', '')
            topic_subtype = video_detail.get('topic_subtype', '')
            topic_status = video_detail.get('status', '')
            if topic_status not in ('', '1', '2', '3'):
                topic_status = ''
            topic_tags = video_detail.get('tags', '')
            if isinstance(topic_tags, list):
                topic_tags = ' | '.join(topic_tags)
            elif not isinstance(topic_tags, str):
                topic_tags = str(topic_tags) if topic_tags else ''
            if not low_priority or not summary or not summary.strip() or not topic_type or not topic_type.strip() or not topic_category or not topic_category.strip() :
                # show a messagebox to let user know the summary is generating (non-blocking)
                # self.root.after(0, lambda: messagebox.showinfo("提示", "摘要生成中，请稍后...", parent=self.root))
                self.update_text_content(video_detail, in_background=low_priority)
                topic_type = video_detail.get('topic_subtype', '')
                topic_category = video_detail.get('topic_category', '')
                topic_subtype = video_detail.get('topic_subtype', '')
                topic_tags = video_detail.get('tags', '')
                if isinstance(topic_tags, list):
                    topic_tags = ' | '.join(topic_tags)
                elif not isinstance(topic_tags, str):
                    topic_tags = str(topic_tags) if topic_tags else ''
                summary = video_detail.get('summary', '')

            # show the summary in a new window
            summary_window = tk.Toplevel(dialog)
            summary_window.title(f"{video_detail['title']} - 摘要")
            summary_window.geometry("1000x800")
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
            category_combo = ttk.Combobox(topic_frame, textvariable=category_var, values=self.topic_categories, state="readonly", width=40)
            category_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
            
            # 主题子类型选择
            ttk.Label(topic_frame, text="主题子类型:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky='w', padx=5, pady=5)
            subtype_var = tk.StringVar(value=topic_subtype)
            subtype_combo = ttk.Combobox(topic_frame, textvariable=subtype_var, values=[], state="readonly", width=40)
            subtype_combo.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
            
            # 标注选择 (status: "", "1", "2", "3")
            ttk.Label(topic_frame, text="标注:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky='w', padx=5, pady=5)
            status_var = tk.StringVar(value=topic_status)
            status_combo = ttk.Combobox(topic_frame, textvariable=status_var, values=("", "1", "2", "3"), state="readonly", width=10)
            status_combo.grid(row=2, column=1, padx=5, pady=5, sticky='w')
            
            # 主题标签输入
            ttk.Label(topic_frame, text="主题标签 (用 | 分隔):", font=("Arial", 10, "bold")).grid(row=3, column=0, sticky='nw', padx=5, pady=5)
            tags_var = tk.StringVar(value=topic_tags)
            tags_entry = ttk.Entry(topic_frame, textvariable=tags_var, width=40)
            tags_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
            
            # 可选标签列表（用于快速选择）
            ttk.Label(topic_frame, text="可选标签:", font=("Arial", 10, "bold")).grid(row=4, column=0, sticky='nw', padx=5, pady=5)
            tags_listbox_frame = ttk.Frame(topic_frame)
            tags_listbox_frame.grid(row=4, column=1, padx=5, pady=5, sticky='nsew')
            
            tags_listbox = tk.Listbox(tags_listbox_frame, selectmode=tk.EXTENDED, height=6)
            tags_listbox_scrollbar = ttk.Scrollbar(tags_listbox_frame, orient=tk.VERTICAL, command=tags_listbox.yview)
            tags_listbox.configure(yscrollcommand=tags_listbox_scrollbar.set)
            tags_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tags_listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
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
                if topic_subtype in subtypes:
                    subtype_var.set(topic_subtype)
                else:
                    subtype_var.set('')
                update_tags()
            
            def update_tags(*args):
                """根据选择的子类型更新标签选项（tags 为字符串数组）"""
                selected_category = category_var.get()
                selected_subtype = subtype_var.get()
                tags = []
                if selected_category and selected_subtype and self.topic_choices:
                    for item in self.topic_choices:
                        if isinstance(item, dict) and item.get('topic_category') == selected_category:
                            for subtype_item in item.get('topic_subtypes', []):
                                if isinstance(subtype_item, dict) and subtype_item.get('topic_subtype') == selected_subtype:
                                    for tag in subtype_item.get('tags', []) or subtype_item.get('problem_tags', []):
                                        if tag not in tags:
                                            tags.append(tag)
                tags_listbox.delete(0, tk.END)
                for tag in tags:
                    tags_listbox.insert(tk.END, tag)
            
            def add_selected_tags():
                """将选中的标签添加到输入框"""
                selected_indices = tags_listbox.curselection()
                if selected_indices:
                    current_tags_text = tags_var.get()
                    selected_tags = [tags_listbox.get(i) for i in selected_indices]
                    new_tags = ','.join(selected_tags)
                    if current_tags_text:
                        tags_var.set(f"{current_tags_text},{new_tags}")
                    else:
                        tags_var.set(new_tags)

            
            def copy_material():
                """拷贝原文"""
                text_content = self.fetch_text_content(video_detail)
                if text_content:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(text_content)
                    self.root.update()
                    messagebox.showinfo("成功", "原文已拷贝到剪贴板", parent=summary_window)
                else:
                    messagebox.showinfo("提示", "原文不存在", parent=summary_window)


            def re_category_tags():
                """重新分类"""
                selected_category = category_var.get()

                text_content = self.fetch_text_content(video_detail)

                category_selected_json = {}
                if selected_category and self.topic_choices:
                    for item in self.topic_choices:
                        if isinstance(item, dict) and item.get('topic_category') == selected_category:
                            category_selected_json = item
                            break

                if not text_content or not selected_category or not category_selected_json:
                    return

                self.prepare_category_for_content(video_detail, text_content, category_selected_json)


            # 绑定事件
            category_combo.bind('<<ComboboxSelected>>', update_subtypes)
            subtype_combo.bind('<<ComboboxSelected>>', update_tags)
            
            # 按钮框架
            button_frame = ttk.Frame(topic_frame)
            button_frame.grid(row=6, column=0, columnspan=2, padx=5, pady=5, sticky='ew')
            
            # 添加标签按钮
            add_tags_btn = ttk.Button(button_frame, text="添加选中标签", command=add_selected_tags)
            add_tags_btn.pack(side=tk.LEFT, padx=5)
            
            re_tag_category_btn = ttk.Button(button_frame, text="重新分类", command=re_category_tags)
            re_tag_category_btn.pack(side=tk.LEFT, padx=5)

            copy_material_btn = ttk.Button(button_frame, text="拷贝原文", command=copy_material)
            copy_material_btn.pack(side=tk.LEFT, padx=5)


            # 保存按钮
            def save_topic_info():
                """保存主题信息"""
                category = category_var.get().strip()
                subtype = subtype_var.get().strip()
                tags_text = tags_var.get().strip()
                st = status_var.get()
                
                # 解析标签（用逗号分隔）
                if tags_text:
                    tags_list = [tag.strip() for tag in tags_text.split(',') if tag.strip()]
                else:
                    tags_list = []
                
                # 更新视频详情
                if category:
                    video_detail['topic_category'] = category
                if subtype:
                    video_detail['topic_subtype'] = subtype
                if tags_list:
                    video_detail['problem_tags'] = tags_list
                if st in ('', '1', '2', '3'):
                    video_detail['status'] = st
                
                # 保存到文件
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                
                # 刷新树视图（如果对话框还存在）
                try:
                    populate_tree()
                except:
                    pass
                
                messagebox.showinfo("成功", "主题信息已保存", parent=summary_window)
            
            save_btn = ttk.Button(button_frame, text="保存主题信息", command=save_topic_info)
            save_btn.pack(side=tk.RIGHT, padx=5)
            
            # 配置网格权重
            topic_frame.columnconfigure(1, weight=1)
            topic_frame.rowconfigure(4, weight=1)  # 标签列表在第4行
            
            # 初始化子类型和标签选项
            if topic_category:
                update_subtypes()  # 这会调用 update_tags()
            
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
            
            # 插入摘要内容
            text_widget.insert(tk.END, summary)
            text_widget.config(state=tk.DISABLED)  # 设置为只读
            # 自动拷贝到剪贴板，便于粘贴到其他应用
            if summary and summary.strip():
                try:
                    summary_window.clipboard_clear()
                    summary_window.clipboard_append(summary.strip())
                    summary_window.update()
                except Exception:
                    pass
            
            # 添加关闭按钮
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X, pady=(10, 0))
            ttk.Button(button_frame, text="关闭", command=summary_window.destroy).pack(side=tk.RIGHT)
            
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


        def summarize_selected(force=False):
            selected_items = tree.selection()
            if not selected_items:
                return

            videos_to_process = []
            for item in selected_items:
                item_tags = tree.item(item, "tags")
                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue
                summary = video_detail.get('summary', '')
                topic_type = video_detail.get('topic_subtype', '')
                topic_category = video_detail.get('topic_category', '')
                tags = video_detail.get('tags', '')
                if not force and summary and summary.strip() and topic_type and topic_type.strip() and topic_category and topic_category.strip() and tags:
                    continue
                videos_to_process.append(video_detail)
            
            if not videos_to_process:
                messagebox.showinfo("提示", "所选视频都已生成摘要", parent=dialog)
                return
            
            # 启动摘要生成任务
            for video_detail in videos_to_process:
                self.update_text_content(video_detail, in_background=True)
            
            messagebox.showinfo("提示", f"已启动 {len(videos_to_process)} 个视频的摘要生成任务，请稍后...", parent=dialog)


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
                messagebox.showerror("错误", "无法获取频道ID，请使用「获取热门视频列表」重新导入频道", parent=dialog)
                return
            channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

            def fetch_task():
                new_videos = self.downloader.fetch_channel_new_videos(channel_url, max_videos=200)
                dialog.after(0, lambda: _show_new_videos_popup(new_videos))

            def _show_new_videos_popup(new_videos):
                if new_videos is None:
                    messagebox.showerror("错误", "抓取视频列表失败", parent=dialog)
                    return
                if not new_videos:
                    messagebox.showinfo("提示", "没有发现新视频", parent=dialog)
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

                video_to_iid = {}
                for i, v in enumerate(new_videos):
                    view_count = v.get('view_count', 0)
                    views_str = f"{view_count:,}" if isinstance(view_count, (int, float)) else str(view_count)
                    duration_str = fmt_duration(v.get('duration', 0))
                    upload_date = v.get('upload_date', '') or '-'
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


        def download_selected():
            selected_items = tree.selection()
            if not selected_items:
                return
            # 获取选中视频的信息
            selected_videos = []
            for item in selected_items:
                item_tags = tree.item(item, "tags")
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
                        print(f"[{idx}/{total}] 下载: {video_detail['title']}")
                        # 使用可重用的方法生成文件名前缀（下载时使用100字符）
                        #file_path = self.downloader.download_video_highest_resolution(video_detail)
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

            # 开始转录（不关闭对话框，转录完成后刷新列表）
            self.downloader._check_and_update_cookies(wait_forever=False)

            target_lang = self.downloader.select_language(videos_to_transcribe[0])

            # 初始化计数器
            success_count = 0
            failed_count = 0

            for idx, video_detail in enumerate(videos_to_transcribe, 1):
                try:
                    downloaded_file = self.downloader.download_captions( video_detail, target_lang )
                    if downloaded_file:
                        print(f"  ✅ 转录成功")
                        self.update_text_content(video_detail, downloaded_file)
                        success_count += 1
                    else:
                        print(f"  ❌ 转录失败：无法下载字幕")
                        failed_count += 1
                        
                except Exception as e:
                    print(f"  ❌ 转录失败: {str(e)}")
                    failed_count += 1
            
            # 保存更新后的视频列表
            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            
            # 显示完成信息
            print(f"\n{'='*50}")
            print(f"转录任务完成！成功: {success_count} 个，失败: {failed_count} 个")
            
            # 刷新列表
            populate_tree()



        def tag_selected():
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            for item in selected_items:
                item_tags = tree.item(item, "tags")
                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue
                self.update_text_content(video_detail, tag_again=True)



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
        ttk.Button(bottom_frame, text="编辑主题", command=edit_selected_topics).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="摘要", command=summarize_selected).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="分类", command=tag_selected).pack(side=tk.RIGHT, padx=5)
        #ttk.Button(bottom_frame, text="重摘", command=re_summarize_selected).pack(side=tk.RIGHT, padx=5)
        #ttk.Button(bottom_frame, text="摘要", command=summarize_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="转录", command=transcribe_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="下载", command=download_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="更新", command=update_video_list).pack(side=tk.RIGHT, padx=5)


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

        def fetch_video_list():
            try:
                new_channel_name = self.downloader.list_hot_videos(
                    channel_url, 
                    max_videos=int(max_videos_var.get()), 
                    min_view_count=int(min_view_count_var.get())
                )
                if not new_channel_name:
                    return

                print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")

            except Exception as e:
                error_msg = str(e)
                print(f"❌ 获取视频列表失败: {error_msg}")
        
        thread = threading.Thread(target=fetch_video_list)
        thread.daemon = True
        thread.start()



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
        video_data = self.downloader.get_video_detail(video_url, channel_name='Unknown')
        if not video_data:
            self.root.after(0, lambda: messagebox.showerror("错误", "获取视频详情失败"))
            return

        channel_name = self.downloader.get_channel_name(video_data)

        if not transcribe:
            self.downloader.download_video_highest_resolution(video_data)
            return
    
        self.downloader.channel_list_json = f"{self.youtube_dir}/list/{channel_name}.json.txt"
        if os.path.exists(self.downloader.channel_list_json):
            self.downloader.channel_videos = json.load(open(self.downloader.channel_list_json, 'r', encoding='utf-8'))
            self.downloader.latest_date = max(
                (
                    datetime.strptime(v["upload_date"], "%Y%m%d")
                    for v in self.downloader.channel_videos
                    if v.get("upload_date")
                ),
                default=None
            )            
        else:
            self.downloader.channel_list_json = None
            self.downloader.channel_videos = []

        if not self.downloader.channel_videos:
            # show all the *.json.txt files in the youtube_dir,  let user to select one
            # if user Not select one, ask user give a new channel name, then create a new file with the new channel name
            # and add the video_data as the first item in the new file (change the channel_name to the new channel name)
            
            # 查找所有热门视频JSON文件
            channel_list_json_files = glob.glob(f"{self.youtube_dir}/list/*.json.txt")
            
            # 使用线程安全的队列来传递结果
            selected_file = None
            if channel_list_json_files:
                # 准备选项列表和文件路径映射
                channel_choices = []
                channel_to_file = {}
                
                for json_file in channel_list_json_files:
                    filename = os.path.basename(json_file)
                    # 提取频道名
                    match = re.match(r'(.+?)\.json\.txt', filename)
                    if match:
                        channel_name = match.group(1)
                        channel_choices.append(channel_name)
                        channel_to_file[channel_name] = json_file
                
                # 在主线程中显示选择对话框
                choice = askchoice("选择视频列表文件", channel_choices, parent=self.root)
                if choice:
                    if choice in channel_to_file:
                        selected_file = channel_to_file[choice]
            
            # 如果用户选择了文件，加载它
            if selected_file:
                self.downloader.channel_list_json = selected_file
                try:
                    with open(self.downloader.channel_list_json, 'r', encoding='utf-8') as f:
                        self.downloader.channel_videos = json.load(f)
                        self.downloader.latest_date = max(
                            (
                                datetime.strptime(v["upload_date"], "%Y%m%d")
                                for v in self.downloader.channel_videos
                                if v.get("upload_date")
                            ),
                            default=None
                        )                
                except Exception as e:
                    print(f"❌ 读取视频列表失败: {e}")
                    self.downloader.channel_videos = []
            
            if not selected_file or not self.downloader.channel_videos:
                self.downloader.channel_list_json = f"{self.youtube_dir}/list/{channel_name}.json.txt"
                self.downloader.channel_videos = []
                print(f"✅ 已创建新的视频列表文件: {self.downloader.channel_list_json}")


        is_new_video = self.downloader.is_video_new(video_data)
        if not is_new_video:
            print(f"✅ 视频已存在，跳过下载...")
            return

        file_path = self.downloader.download_audio_only(video_data)

        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            video_data["audio_path"] = file_path
            video_data["file_size_mb"] = file_size
            video_data["status"] = "success"
        else:
            self.root.after(0, lambda: messagebox.showerror("错误", "视频下载失败"))
            return


        target_lang = self.downloader.select_language(video_url)

        transcribed_file = self.downloader.download_captions( video_data, target_lang )
        if transcribed_file:
            print(f"✅ YouTube视频转录完成！")
            video_data['transcribed_file'] = transcribed_file
            self.root.after(0, lambda: messagebox.showinfo("转录完成", "YouTube视频转录完成！"))
        else:
            print(f"❌ YouTube视频转录失败")
            self.root.after(0, lambda: messagebox.showerror("错误", "YouTube视频转录失败：未生成字幕文件"))
        
        self.downloader.channel_videos.append(video_data)
        this_video_date = datetime.strptime(video_data["upload_date"], "%Y%m%d")
        if this_video_date > self.downloader.latest_date:
            self.downloader.latest_date = this_video_date
        self.update_text_content(video_data)
        
        with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
            json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")