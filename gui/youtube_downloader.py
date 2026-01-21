import os
import time
import yt_dlp
import subprocess
import shutil
import json
import re
import config_prompt

import google_auth_oauthlib.flow
import googleapiclient.discovery

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from utility.llm_api import LLMApi, OLLAMA



class YoutubeDownloader:

    def __init__(self, project_path):
        print("YoutubeDownloader init...")
        self.project_path = project_path
        self.youtube_dir = f"{self.project_path}/Youtbue_download"
        
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
                    os.remove(download_cookies)

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


    def has_subtitles(self, video_url):
        """检查视频是否存在字幕语言"""
        try:
            ydl_opts = self._get_ydl_opts_base(quiet=True, skip_download=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                subtitles = info.get('subtitles', {})
                auto_captions = info.get('automatic_captions', {})

                # 检查是否有目标语言字幕
                if len(subtitles) > 0:
                    return list(subtitles.keys())[0]
                elif len(auto_captions) > 0:
                    return list(auto_captions.keys())[0]
                return None
        except Exception as e:
            print(f"❌ 检查字幕失败: {e}")
            return None
    

    def get_available_subtitles(self, video_url):
        """获取视频所有可用的字幕语言列表"""
        try:
            ydl_opts = self._get_ydl_opts_base(quiet=True, skip_download=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                subtitles = info.get('subtitles', {})
                auto_captions = info.get('automatic_captions', {})
                
                result = {
                    'manual_subtitles': list(subtitles.keys()),
                    'auto_captions': list(auto_captions.keys()),
                    'all_languages': list(set(list(subtitles.keys()) + list(auto_captions.keys())))
                }
                
                print(f"📝 可用字幕语言: 手动={len(result['manual_subtitles'])}, 自动={len(result['auto_captions'])}")
                return result
        except Exception as e:
            print(f"❌ 获取字幕语言列表失败: {e}")
            return {'manual_subtitles': [], 'auto_captions': [], 'all_languages': []}


    def download_captions(self, video_url, lang, download_prefix, format):
        try:
            # 优化：直接尝试下载指定语言的字幕，避免两次提取
            # 如果失败，再检查可用语言
            target_lang = lang
            
            # 第一次尝试：直接下载指定语言的字幕
            ydl_opts = self._get_ydl_opts_base(
                skip_download=True,
                writesubtitles=True,
                writeautomaticsub=True,
                subtitleslangs=[target_lang],
                subtitlesformat=format,
                outtmpl=download_prefix,
                quiet=True,  # 使用 quiet 模式减少输出
                no_warnings=True,  # 禁用警告
            )
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
                
                # 检查文件是否真的下载了
                expected_file = f"{download_prefix}.{target_lang}.{format}"
                if os.path.exists(expected_file):
                    print(f"✅ 已下载字幕：语言 {target_lang}")
                    return target_lang
                else:
                    # 文件不存在，可能下载失败但没报错
                    raise Exception("字幕文件未生成")
                    
            except Exception as direct_error:
                # 直接下载失败，检查可用语言
                # 只进行一次提取来检查可用语言
                check_opts = self._get_ydl_opts_base(quiet=True, skip_download=True)
                with yt_dlp.YoutubeDL(check_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    subtitles = info.get('subtitles', {})
                    auto_captions = info.get('automatic_captions', {})
                
                # 检查是否有任何字幕
                if not subtitles and not auto_captions:
                    print(f"❌ 视频没有任何字幕")
                    return None
                
                # 确定要下载的语言
                target_lang = None
                
                # 首先检查是否有指定语言
                if lang in subtitles or lang in auto_captions:
                    target_lang = lang
                    print(f"✅ 找到目标语言字幕: {lang}")
                    # 语言存在但下载失败，可能是网络问题，再次尝试
                    ydl_opts = self._get_ydl_opts_base(
                        skip_download=True,
                        writesubtitles=True,
                        writeautomaticsub=True,
                        subtitleslangs=[target_lang],
                        subtitlesformat=format,
                        outtmpl=download_prefix,
                        quiet=True,
                        no_warnings=True,
                    )
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([video_url])
                    print(f"✅ 已下载字幕：语言 {target_lang}")
                    return target_lang
                else:
                    # 没有指定语言，选择第一个可用语言
                    if subtitles:
                        target_lang = list(subtitles.keys())[0]
                        print(f"⚠️ 未找到语言 {lang}，使用手动字幕: {target_lang}")
                    elif auto_captions:
                        target_lang = list(auto_captions.keys())[0]
                        print(f"⚠️ 未找到语言 {lang}，使用自动字幕: {target_lang}")
                    
                    if not target_lang:
                        return None
                    
                    # 下载找到的语言
                    ydl_opts = self._get_ydl_opts_base(
                        skip_download=True,
                        writesubtitles=True,
                        writeautomaticsub=True,
                        subtitleslangs=[target_lang],
                        subtitlesformat=format,
                        outtmpl=download_prefix,
                        quiet=True,
                        no_warnings=True,
                    )
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([video_url])
                    print(f"✅ 已下载字幕：语言 {target_lang}")
                    return target_lang
                
        except Exception as e:
            print(f"❌ 下载字幕失败: {e}")
            return None 


    def download_audio(self, video_url):
        """
        下载音频文件（同时保留视频文件）
        
        这个方法会：
        1. 下载视频文件（优先mp4格式）
        2. 从视频中提取音频为mp3格式
        3. 保留原始视频文件
        
        Returns:
            str: mp3音频文件的路径，失败则返回None
        """
        try:
            # 先下载最佳视频格式
            video_ydl_opts = {
                'format': 'best[ext=mp4]/best',  # 优先下载mp4格式
                'outtmpl': os.path.join(f"{self.project_path}/Youtbue_download", '%(id)s.%(ext)s'),
                'quiet': False,
            }
            
            # 下载视频并提取音频
            audio_ydl_opts = {
                'format': 'best[ext=mp4]/best',  # 从视频文件提取音频
                'outtmpl': os.path.join(f"{self.project_path}/Youtbue_download", '%(id)s.%(ext)s'),
                'keepvideo': True,  # 保留原始视频文件
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': False,
            }
            
            with yt_dlp.YoutubeDL(audio_ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info['id']
                
                # 返回音频文件路径
                mp3_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{video_id}.mp3")
                
                # 检查视频文件是否存在
                possible_video_exts = ['mp4', 'webm', 'mkv', 'avi']
                video_path = None
                for ext in possible_video_exts:
                    potential_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{video_id}.{ext}")
                    if os.path.exists(potential_path):
                        video_path = potential_path
                        break
                
                print(f"✅ 已下载视频: {video_path}")
                print(f"✅ 已提取音频: {mp3_path}")
                
                return mp3_path
                
        except Exception as e:
            print(f"❌ 下载失败: {e}")
            return None

    def get_downloaded_video_path(self, video_url):
        """获取已下载视频的文件路径"""
        try:
            # 先获取视频ID
            ydl_opts = {'quiet': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                video_id = info['id']
            
            # 查找视频文件
            possible_video_exts = ['mp4', 'webm', 'mkv', 'avi', 'mov']
            for ext in possible_video_exts:
                video_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{video_id}.{ext}")
                if os.path.exists(video_path):
                    return video_path
            
            return None
        except Exception as e:
            print(f"❌ 获取视频路径失败: {e}")
            return None

    def download_video_only(self, video_url):
        """仅下载视频文件（不提取音频）"""
        try:
            ydl_opts = {
                'format': 'best[ext=mp4]/best',  # 优先下载mp4格式
                'outtmpl': os.path.join(f"{self.project_path}/Youtbue_download", '%(id)s.%(ext)s'),
                'quiet': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info['id']
                
                # 查找下载的视频文件
                possible_video_exts = ['mp4', 'webm', 'mkv', 'avi', 'mov']
                for ext in possible_video_exts:
                    video_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{video_id}.{ext}")
                    if os.path.exists(video_path):
                        print(f"✅ 已下载视频: {video_path}")
                        return video_path
                
                print(f"❌ 未找到下载的视频文件")
                return None
                
        except Exception as e:
            print(f"❌ 下载视频失败: {e}")
            return None


    def download_video_highest_resolution(self, video_url, video_prefix, sleep_interval=2):
        outtmpl = os.path.join(f"{self.project_path}/Youtbue_download", f'{video_prefix}.%(ext)s')
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
                
                if video_prefix:
                    expected_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{video_prefix}.mp4")
                else:
                    expected_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{info['title']}.mp4")
                
                # 验证文件是否存在
                if not os.path.exists(expected_path):
                    # 尝试查找其他扩展名
                    base_path = expected_path.rsplit('.', 1)[0]
                    for ext in ['webm', 'mkv', 'mp4']:
                        alt_path = f"{base_path}.{ext}"
                        if os.path.exists(alt_path):
                            print(f"✅ 找到下载文件: {alt_path}")
                            return alt_path
                    raise Exception(f"下载的文件不存在: {expected_path}")
                
                return expected_path
        except Exception as e:
            error_msg = str(e)
            
            # 检查是否是 cookies 无效的错误
            if self._check_cookie_invalid(error_msg):
                print("❌ 检测到 cookies 可能已失效")
                self.cookie_valid = False
            
            if "Requested format is not available" in error_msg or "HTTP Error 403" in error_msg:
                print(f"⚠️ 格式不可用,尝试使用最基础的格式...")
                # 最后的备用方案: 只下载最佳可用格式
                ydl_opts = self._get_ydl_opts_base(
                    format='best',
                    outtmpl=outtmpl,
                    quiet=False,
                    progress_hooks=[self._progress_hook],
                    skip_download=False,
                )
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video_url, download=True)
                        
                        if video_prefix:
                            expected_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{video_prefix}.mp4")
                        else:
                            expected_path = os.path.abspath(f"{self.project_path}/Youtbue_download/{info['title']}.mp4")
                        
                        return expected_path
                except Exception as retry_error:
                    retry_error_msg = str(retry_error)
                    if self._check_cookie_invalid(retry_error_msg):
                        print("❌ 备用方案也失败，cookies 可能已失效")
                        self.cookie_valid = False
                    print(f"❌ 备用方案也失败: {retry_error}")
                    raise
            else:
                raise


    def download_playlist_highest_resolution(self, playlist_url, max_videos=None):
        """下载播放列表中的所有视频，最高分辨率"""
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(f"{self.project_path}/Youtbue_download", '%(playlist_index)s-%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': False,
            'progress_hooks': [self._progress_hook],
            'ignoreerrors': True,  # 忽略单个视频的错误，继续下载其他视频
        }
        
        # 如果设置了最大视频数量限制
        if max_videos:
            ydl_opts['playlist_items'] = f'1-{max_videos}'
        
        downloaded_files = []
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(playlist_url, download=True)
                
                # 收集下载的文件信息
                if 'entries' in info:
                    for entry in info['entries']:
                        if entry and 'title' in entry:
                            expected_filename = f"{entry.get('playlist_index', 'unknown')}-{entry['title']}.mp4"
                            expected_path = os.path.join(f"{self.project_path}/Youtbue_download", expected_filename)
                            if os.path.exists(expected_path):
                                downloaded_files.append({
                                    'title': entry['title'],
                                    'url': entry.get('webpage_url', ''),
                                    'file_path': expected_path,
                                    'duration': entry.get('duration', 0),
                                    'view_count': entry.get('view_count', 0)
                                })
                
                print(f"✅ 播放列表下载完成，共下载 {len(downloaded_files)} 个视频")
                return downloaded_files
                
            except Exception as e:
                print(f"❌ 播放列表下载失败: {str(e)}")
                return downloaded_files


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


    def generate_video_prefix(self, video_detail, title_length=50):
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
            print(f"🔍 获取频道视频列表: {channel_url}")
            print(f"📊 参数: 最大视频数={max_videos}, 最小观看次数={min_view_count:,}")
            
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
        
            video_list_json_path = os.path.join(self.youtube_dir, f"_{channel_name}_hotvideos.json")
            if os.path.exists(video_list_json_path):
                return json.load(open(video_list_json_path, 'r', encoding='utf-8'))

            videos = []

            if 'entries' in info:
                # 记录循环开始时间，用于每10分钟检查一次 cookies
                loop_start_time = time.time()
                cookie_check_interval = 600  # 10分钟 = 600秒
                
                for count, entry in enumerate(info['entries']):
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
            
            # 限制返回数量
            videos = videos[:max_videos]
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
class YoutubeGUIManager:
    """YouTube GUI管理器 - 处理所有YouTube相关的GUI对话框"""
    
    def __init__(self, root, project_path, get_pid_func, tasks, log_to_output_func, download_output):
        self.root = root
        self.project_path = project_path
        self.youtube_dir = f"{self.project_path}/Youtbue_download"
        # 在导入模块之前先导入os，避免局部变量错误
        import os
        os.makedirs(self.youtube_dir, exist_ok=True)

        self.get_pid = get_pid_func
        self.tasks = tasks
        self.log_to_output = log_to_output_func
        self.download_output = download_output
        
        self.llm_api = LLMApi(OLLAMA)

        # 创建YoutubeDownloader实例
        self.downloader = YoutubeDownloader(project_path)
        
        # 导入所需模块
        import tkinter as tk
        import tkinter.ttk as ttk
        import tkinter.messagebox as messagebox
        import tkinter.filedialog as filedialog
        import tkinter.scrolledtext as scrolledtext
        import tkinter.simpledialog as simpledialog
        import threading
        import uuid
        from datetime import datetime
        import os
        import re
        import json
        import config
        
        # 存储到实例属性中以便方法使用
        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.filedialog = filedialog
        self.simpledialog = simpledialog
        self.scrolledtext = scrolledtext
        self.threading = threading
        self.uuid = uuid
        self.datetime = datetime
        self.os = os
        self.re = re
        self.json = json
        self.config = config


    def manage_hot_videos(self):
        """管理热门视频列表 - 选择频道、下载或转录"""
        import glob
        
        # 扫描所有 *_hotvideos.json 文件
        youtube_dir = f"{self.project_path}/Youtbue_download"
        if not self.os.path.exists(youtube_dir):
            self.messagebox.showwarning("提示", "YouTube下载文件夹不存在")
            return
        
        # 查找所有热门视频JSON文件
        pattern = self.os.path.join(youtube_dir, "*_hotvideos.json")
        json_files = glob.glob(pattern)
        
        if not json_files:
            self.messagebox.showinfo("提示", "未找到任何热门视频列表文件\n\n请先使用 '获取热门视频' 功能获取频道视频列表")
            return
        
        # 提取频道名称
        channel_data = []
        for json_file in json_files:
            filename = self.os.path.basename(json_file)
            # 从文件名中提取频道名：_频道名_hotvideos.json -> 频道名
            match = self.re.match(r'_(.+?)_hotvideos\.json', filename)
            if match:
                channel_name = match.group(1)
                # 读取文件获取视频数量
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        videos = self.json.load(f)
                        video_count = len(videos) if isinstance(videos, list) else 0
                except:
                    video_count = 0
                
                channel_data.append({
                    'name': channel_name,
                    'file': json_file,
                    'video_count': video_count
                })
        
        if not channel_data:
            self.messagebox.showwarning("提示", "未找到有效的频道视频列表")
            return
        
        # 显示频道选择对话框
        channel_dialog = self.tk.Toplevel(self.root)
        channel_dialog.title("选择频道")
        channel_dialog.geometry("600x400")
        channel_dialog.transient(self.root)
        channel_dialog.grab_set()
        
        # 顶部提示
        top_frame = self.ttk.Frame(channel_dialog)
        top_frame.pack(fill=self.tk.X, padx=10, pady=10)
        self.ttk.Label(top_frame, text="请选择要管理的频道：", 
                  font=("Arial", 12, "bold")).pack(side=self.tk.LEFT)
        
        # 创建频道列表
        list_frame = self.ttk.Frame(channel_dialog)
        list_frame.pack(fill=self.tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = self.ttk.Scrollbar(list_frame)
        scrollbar.pack(side=self.tk.RIGHT, fill=self.tk.Y)
        
        listbox = self.tk.Listbox(list_frame, yscrollcommand=scrollbar.set, 
                            font=("Arial", 11), selectmode=self.tk.SINGLE)
        listbox.pack(side=self.tk.LEFT, fill=self.tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # 填充频道列表
        for channel in channel_data:
            listbox.insert(self.tk.END, f"{channel['name']} ({channel['video_count']} 个视频)")
        
        # 默认选择第一个
        if channel_data:
            listbox.selection_set(0)
        
        # 底部按钮
        bottom_frame = self.ttk.Frame(channel_dialog)
        bottom_frame.pack(fill=self.tk.X, padx=10, pady=10)
        
        def on_confirm():
            selected = listbox.curselection()
            if not selected:
                self.messagebox.showwarning("提示", "请选择一个频道", parent=channel_dialog)
                return
            
            channel = channel_data[selected[0]]
            channel_dialog.destroy()
            
            # 显示该频道的视频管理对话框
            self._show_channel_videos_dialog(channel['name'], channel['file'])
        
        self.ttk.Button(bottom_frame, text="确定", command=on_confirm).pack(side=self.tk.RIGHT, padx=5)
        self.ttk.Button(bottom_frame, text="取消", command=channel_dialog.destroy).pack(side=self.tk.RIGHT, padx=5)


    def fetch_text_content(self, srt_file):
        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用正则表达式匹配SRT格式
        # SRT格式：序号\n时间戳\n文本内容\n\n
        # 匹配模式：数字开头，然后是时间戳行（包含-->），然后是文本内容
        pattern = r'^\d+\s*\n\s*\d{2}:\d{2}:\d{2}[,\d]+\s*-->\s*\d{2}:\d{2}:\d{2}[,\d]+\s*\n(.*?)(?=\n\d+\s*\n|\Z)'
        matches = self.re.findall(pattern, content, self.re.MULTILINE | self.re.DOTALL)
        
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


    def _show_channel_videos_dialog(self, channel_name, channel_vidoe_json_file):
        """显示频道视频管理对话框"""
        with open(channel_vidoe_json_file, 'r', encoding='utf-8') as f:
            channel_videos = self.json.load(f)
        if not channel_videos:
            self.messagebox.showwarning("提示", "视频列表为空")
            return
        
        # 创建视频管理对话框
        dialog = self.tk.Toplevel(self.root)
        dialog.title(f"热门视频管理 - {channel_name}")
        dialog.geometry("1100x650")
        dialog.transient(self.root)
        
        # 顶部信息和控制栏
        top_frame = self.ttk.Frame(dialog)
        top_frame.pack(fill=self.tk.X, padx=10, pady=5)
        
        # 第一行：信息标签和刷新按钮
        info_frame = self.ttk.Frame(top_frame)
        info_frame.pack(fill=self.tk.X, pady=(0, 5))
        
        info_text = f"频道: {channel_name} | 共 {len(channel_videos)} 个视频"
        info_label = self.ttk.Label(info_frame, text=info_text, font=("Arial", 12, "bold"))
        info_label.pack(side=self.tk.LEFT)
        
        # 添加刷新按钮
        self.ttk.Button(info_frame, text="🔄 刷新", command=lambda: refresh_video_list()).pack(side=self.tk.RIGHT, padx=5)
        
        # 第二行：过滤和排序控制
        control_frame = self.ttk.Frame(top_frame)
        control_frame.pack(fill=self.tk.X)
        
        # 最小观看次数过滤
        self.ttk.Label(control_frame, text="最小观看次数:").pack(side=self.tk.LEFT, padx=(0, 5))
        min_view_var = self.tk.StringVar(value="0")
        min_view_entry = self.ttk.Entry(control_frame, textvariable=min_view_var, width=15)
        min_view_entry.pack(side=self.tk.LEFT, padx=(0, 10))
        
        # 排序方式
        sort_mode_var = self.tk.StringVar(value="view_count")  # 默认按观看次数排序
        
        def toggle_sort():
            """切换排序方式"""
            if sort_mode_var.get() == "view_count":
                sort_mode_var.set("upload_date")
                sort_button.config(text="排序: 上传日期 ↓")
            else:
                sort_mode_var.set("view_count")
                sort_button.config(text="排序: 观看次数 ↓")
            refresh_video_list()
        
        sort_button = self.ttk.Button(control_frame, text="排序: 观看次数 ↓", command=toggle_sort)
        sort_button.pack(side=self.tk.LEFT, padx=5)
        
        # 应用过滤函数
        def apply_filter():
            refresh_video_list()
        
        # 绑定回车键自动应用过滤
        min_view_entry.bind('<Return>', lambda e: apply_filter())
        
        # 应用过滤按钮
        self.ttk.Button(control_frame, text="应用过滤", command=apply_filter).pack(side=self.tk.LEFT, padx=5)
        
        # Smart Select 功能
        self.ttk.Label(control_frame, text="智能选择:").pack(side=self.tk.LEFT, padx=(10, 5))
        smart_select_var = self.tk.StringVar()
        smart_select_entry = self.ttk.Entry(control_frame, textvariable=smart_select_var, width=20)
        smart_select_entry.pack(side=self.tk.LEFT, padx=(0, 5))
        
        def smart_select():
            """根据输入文本智能选择匹配的视频"""
            search_text = smart_select_var.get().strip().lower()
            if not search_text:
                return
            
            # 清空当前选择
            tree.selection_remove(*tree.selection())
            
            # 搜索并选择匹配的视频
            matched_count = 0
            for item in tree.get_children():
                item_tags = tree.item(item, "tags")
                if item_tags and len(item_tags) > 5:
                    video_title = item_tags[5] if len(item_tags) > 5 else ''
                    # 不区分大小写匹配
                    if search_text in video_title.lower():
                        tree.selection_add(item)
                        matched_count += 1
            
            # 更新选择计数（直接更新stats_label，因为update_selection_count在后面定义）
            selected = tree.selection()
            stats_label.config(text=f"已选择: {len(selected)} 个视频")
            
            # 滚动到第一个匹配项
            if matched_count > 0:
                first_matched = None
                for item in tree.get_children():
                    if item in tree.selection():
                        first_matched = item
                        break
                if first_matched:
                    tree.see(first_matched)
                    tree.focus(first_matched)
            
            # 显示结果提示
            if matched_count > 0:
                print(f"✅ 智能选择: 找到 {matched_count} 个匹配的视频")
            else:
                print(f"⚠️ 智能选择: 未找到匹配的视频")
        
        # 绑定回车键
        smart_select_entry.bind('<Return>', lambda e: smart_select())
        
        # 创建Treeview显示视频列表
        columns = ("title", "views", "duration", "upload_date", "status")
        tree_frame = self.ttk.Frame(dialog)
        tree_frame.pack(fill=self.tk.BOTH, expand=True, padx=10, pady=5)
        
        # 添加滚动条
        scrollbar = self.ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=self.tk.RIGHT, fill=self.tk.Y)
        
        tree = self.ttk.Treeview(tree_frame, columns=columns, show="tree headings", 
                            yscrollcommand=scrollbar.set, selectmode="extended")
        tree.pack(side=self.tk.LEFT, fill=self.tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        
        # 设置列标题和宽度
        tree.heading("#0", text="序号")
        tree.heading("title", text="标题")
        tree.heading("views", text="观看次数")
        tree.heading("duration", text="时长")
        tree.heading("upload_date", text="上传日期")
        tree.heading("status", text="状态")
        
        tree.column("#0", width=50, anchor="center")
        tree.column("title", width=450, anchor="w")
        tree.column("views", width=120, anchor="e")
        tree.column("duration", width=80, anchor="center")
        tree.column("upload_date", width=100, anchor="center")
        tree.column("status", width=150, anchor="center")
        

        def check_video_status(video_detail, youtube_dir):
            """检查单个视频的下载和转录状态"""
            status_parts = []
            video_file = None
            
            # 使用可重用的方法生成文件名前缀（用于匹配，使用50字符）
            filename_prefix = self.downloader.generate_video_prefix( video_detail, title_length=15 )
            
            # 检查是否已下载 - 只扫描 .mp4 文件
            if self.os.path.exists(youtube_dir):
                for filename in self.os.listdir(youtube_dir):
                    # 只检查 .mp4 文件
                    if not filename.lower().endswith('.mp4'):
                        continue
                    if filename.startswith(filename_prefix):
                        video_file = self.os.path.join(youtube_dir, filename)
                        video_detail['video_path'] = video_file
                        break
            
            if video_file:
                status_parts.append("✅ 已下载")
            else:
                status_parts.append("⬜ 未下载")
            
            # 检查是否已转录 - 检查 .srt 文件（转录生成的字幕文件）
            if video_file:
                # 查找所有以 __{filename_prefix} 开头且以 .srt 结尾的文件
                has_transcript = False
                if self.os.path.exists(youtube_dir):
                    prefix = f"__{filename_prefix}"
                    for filename in self.os.listdir(youtube_dir):
                        if filename.startswith(prefix) and filename.endswith('.srt'):
                            has_transcript = True
                            break
                if has_transcript:
                    status_parts.append("✅ 已转录")
                else:
                    status_parts.append("⬜ 未转录")
            else:
                status_parts.append("⬜ 未转录")
            
            return " ".join(status_parts), video_file
        

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
            for video in channel_videos:
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
            youtube_dir = self.os.path.dirname(channel_vidoe_json_file)
            downloaded_count = 0
            transcribed_count = 0
            
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
                status_str, video_file = check_video_status(video, youtube_dir)
                
                # 统计
                if "✅ 已下载" in status_str:
                    downloaded_count += 1
                if "✅ 已转录" in status_str:
                    transcribed_count += 1
                
                tree.insert("", self.tk.END, text=str(idx), 
                           values=(
                               video.get('title', 'Unknown')[:60],
                               view_str,
                               duration_str,
                               upload_date_str,
                               status_str
                           ),
                           tags=(video.get('url', ''), video_file or '', str(view_count), 
                                 video.get('upload_date', ''), str(duration_sec), 
                                 video.get('title', 'Unknown'), channel_name, video.get('id', '')))
            
            with open(channel_vidoe_json_file, 'w', encoding='utf-8') as f:
                self.json.dump(channel_videos, f, ensure_ascii=False, indent=2)
                print(f"✅ 已保存更新后的视频列表到: {channel_vidoe_json_file}")

            # 更新顶部信息标签
            info_text = f"频道: {channel_name} | 共 {len(filtered_videos)}/{len(channel_videos)} 个视频 | 已下载: {downloaded_count} | 已转录: {transcribed_count}"
            info_label.config(text=info_text)
        

        def refresh_video_list():
            """刷新视频列表"""
            print("🔄 刷新视频列表...")
            populate_tree()
            print("✅ 刷新完成")
        
        # 初始填充树视图
        populate_tree()
        
        # 选择统计标签
        stats_label = self.ttk.Label(dialog, text="已选择: 0 个视频", font=("Arial", 10))
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
            if not self.messagebox.askyesno("确认删除", 
                                           f"确定要删除 {len(selected_items)} 个视频吗？\n\n这将从列表中移除并删除相关的文件（mp4、srt、txt）。",
                                           parent=dialog):
                return
            
            youtube_dir = self.os.path.dirname(channel_vidoe_json_file)
            deleted_count = 0
            failed_count = 0
            
            # 收集要删除的视频ID和文件
            videos_to_remove = []
            files_to_delete = []
            
            for item in selected_items:
                item_tags = tree.item(item, "tags")
                if not item_tags or len(item_tags) < 8:
                    continue
                
                video_url = item_tags[0]
                video_file = item_tags[1]
                video_id = item_tags[7] if len(item_tags) > 7 else ''
                
                # 找到对应的视频数据
                video_to_remove = None
                for video in channel_videos:
                    if video.get('url') == video_url or video.get('id') == video_id:
                        video_to_remove = video
                        break
                
                if video_to_remove:
                    videos_to_remove.append(video_to_remove)
                    
                    # 收集要删除的文件
                    if video_file and self.os.path.exists(video_file):
                        files_to_delete.append(video_file)
                    
                    # 查找并收集SRT和TXT文件
                    video_detail = {
                        'title': video_to_remove.get('title', 'Unknown'),
                        'view_count': video_to_remove.get('view_count', 0),
                        'upload_date': video_to_remove.get('upload_date', ''),
                        'duration': video_to_remove.get('duration', 0),
                        'url': video_url,
                        'id': video_id
                    }
                    
                    filename_prefix = self.downloader.generate_video_prefix(video_detail, title_length=15)
                    prefix = f"__{filename_prefix}"
                    
                    if self.os.path.exists(youtube_dir):
                        for filename in self.os.listdir(youtube_dir):
                            if filename.startswith(prefix):
                                file_path = self.os.path.join(youtube_dir, filename)
                                # 收集SRT和TXT文件
                                if filename.endswith('.srt') or filename.endswith('.txt'):
                                    files_to_delete.append(file_path)
            
            # 删除文件
            for file_path in files_to_delete:
                try:
                    if self.os.path.exists(file_path):
                        self.os.remove(file_path)
                        print(f"✅ 已删除文件: {self.os.path.basename(file_path)}")
                except Exception as e:
                    print(f"❌ 删除文件失败 {self.os.path.basename(file_path)}: {str(e)}")
                    failed_count += 1
            
            # 从videos列表中移除
            for video_to_remove in videos_to_remove:
                if video_to_remove in channel_videos:
                    channel_videos.remove(video_to_remove)
                    deleted_count += 1
            
            # 保存回JSON文件
            try:
                with open(channel_vidoe_json_file, 'w', encoding='utf-8') as f:
                    self.json.dump(channel_videos, f, ensure_ascii=False, indent=2)
                print(f"✅ 已保存更新后的视频列表到: {channel_vidoe_json_file}")
            except Exception as e:
                print(f"❌ 保存视频列表失败: {str(e)}")
                self.messagebox.showerror("错误", f"保存视频列表失败: {str(e)}", parent=dialog)
                return
            
            # 刷新列表
            refresh_video_list()
            
            # 显示结果
            if failed_count > 0:
                self.messagebox.showwarning("删除完成", 
                                          f"已删除 {deleted_count} 个视频\n\n{failed_count} 个文件删除失败",
                                          parent=dialog)
            else:
                self.messagebox.showinfo("删除完成", 
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

        def get_video_detail(video_url):
            video_detail = None
            for video in channel_videos:
                if video.get('url') == video_url:
                    video_detail = video
                    break
            return video_detail

        def update_text_content(video_url):
            if not video_url:
                return
            video_detail = get_video_detail(video_url)
            if not video_detail or not video_detail.get('transcribed_file', ''):
                return

            changed = False
            if not video_detail.get('text_content', ''):
                text_content = self.fetch_text_content(video_detail.get('transcribed_file', ''))
                video_detail['text_content'] = text_content
                changed = True
            if not video_detail.get('summary', ''):
                summary = self.llm_api.generate_text(config_prompt.SUMMERIZE_COUNSELING_STORY_SYSTEM_PROMPT.format(language='Chinese'), video_detail['text_content'])
                video_detail['summary'] = summary
                video_detail.pop('description', None)
                changed = True
            if changed: 
                with open(channel_vidoe_json_file, 'w', encoding='utf-8') as f:
                    self.json.dump(channel_videos, f, ensure_ascii=False, indent=2)
                    print(f"✅ 已保存更新后的视频列表到: {channel_vidoe_json_file}")

        def on_double_click(event):
            """双击事件处理：提取SRT内容并显示"""
            # 获取被双击的项目
            item = tree.identify_row(event.y)
            if not item:
                return
            
            # 选中该项目（如果还没有选中）
            if item not in tree.selection():
                tree.selection_set(item)
            
            item_tags = tree.item(item, "tags")
            if not item_tags or len(item_tags) < 2:
                return
            
            # get the video item from channel_videos
            video_detail = None
            for video in channel_videos:
                if video.get('url') == item_tags[0]:
                    video_detail = video
                    break
            if not video_detail or not video_detail.get('transcribed_file', ''):
                return

            update_text_content(video_detail)
            
            # 弹出窗口显示内容
            content_dialog = self.tk.Toplevel(dialog)
            content_dialog.title(f"转录内容 - {video_detail['title'][:50]}")
            content_dialog.geometry("800x600")
            content_dialog.transient(dialog)
            
            # 顶部信息
            info_frame = self.ttk.Frame(content_dialog)
            info_frame.pack(fill=self.tk.X, padx=10, pady=5)
            self.ttk.Label(info_frame, text=f"文件内容已复制到剪贴板", 
                          font=("Arial", 10, "bold")).pack(side=self.tk.LEFT)
            
            # 文本显示区域（带滚动条）
            text_frame = self.ttk.Frame(content_dialog)
            text_frame.pack(fill=self.tk.BOTH, expand=True, padx=10, pady=5)
            
            scrollbar = self.ttk.Scrollbar(text_frame)
            scrollbar.pack(side=self.tk.RIGHT, fill=self.tk.Y)
            
            text_widget = self.tk.Text(text_frame, wrap=self.tk.WORD, yscrollcommand=scrollbar.set, font=("Arial", 11))
            text_widget.pack(side=self.tk.LEFT, fill=self.tk.BOTH, expand=True)
            scrollbar.config(command=text_widget.yview)
            
            # 插入文本内容
            text_widget.insert("1.0", text_content)
            text_widget.config(state=self.tk.DISABLED)  # 只读
            
            # 底部按钮
            button_frame = self.ttk.Frame(content_dialog)
            button_frame.pack(fill=self.tk.X, padx=10, pady=10)
            self.ttk.Button(button_frame, text="关闭", command=content_dialog.destroy).pack(side=self.tk.RIGHT, padx=5)
        
        # 绑定双击事件
        tree.bind("<Double-1>", on_double_click)
        
        # 底部按钮
        bottom_frame = self.ttk.Frame(dialog)
        bottom_frame.pack(fill=self.tk.X, padx=10, pady=10)
        
        
        def select_all():
            for item in tree.get_children():
                tree.selection_add(item)
            update_selection_count()
        

        def deselect_all():
            tree.selection_remove(*tree.get_children())
            update_selection_count()
        

        def download_selected():
            selected_items = tree.selection()
            if not selected_items:
                self.messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            
            # 获取选中视频的信息
            selected_videos = []
            for item in selected_items:
                item_tags = tree.item(item, "tags")
                video_detail = get_video_detail(item_tags[0])
                selected_videos.append(video_detail)
            
            if not selected_videos:
                self.messagebox.showwarning("提示", "无法获取视频信息", parent=dialog)
                return
            
            # 确认下载
            if not self.messagebox.askyesno("确认下载", 
                                       f"确定要下载 {len(selected_videos)} 个视频吗？\n\n视频将保存到项目的 Youtbue_download 文件夹中。",
                                       parent=dialog):
                return
            
            # 开始下载（不关闭对话框，下载完成后刷新列表）
            self._download_videos_batch(selected_videos, on_complete=lambda: refresh_video_list())
            with open(channel_vidoe_json_file, 'w', encoding='utf-8') as f:
                self.json.dump(channel_videos, f, ensure_ascii=False, indent=2)
                print(f"✅ 已保存更新后的视频列表到: {channel_vidoe_json_file}")


        def compile_selected():
            selected_items = tree.selection()
            if not selected_items:
                self.messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            user_prompt = "case story: \n"  # 暂时为空，等待实现用户输入对话框
            # popup dialog to ask user to input the case story
            case_story = self.simpledialog.askstring("输入案例故事", "请输入案例故事", parent=dialog)
            if case_story:
                user_prompt += case_story
            else:
                return

            for item in selected_items:
                item_tags = tree.item(item, "tags")

                video_detail = get_video_detail(item_tags[0])
                text_content = self.fetch_text_content(video_detail.get('transcribed_file', ''))
                user_prompt += "Title: " + video_detail['title'] + "\n" + "Content: " + text_content + "\n----------------------------\n"

            system_prompt = config_prompt.COMPILE_COUNSELING_STORY_SYSTEM_PROMPT
            response = self.llm_api.generate_text(system_prompt, user_prompt)
            
            # popup dialog to show response
            response_dialog = self.tk.Toplevel(dialog)
            response_dialog.title("编撰结果")
            response_dialog.geometry("700x500")
            response_dialog.transient(dialog)
            response_dialog.grab_set()
            
            # 创建可滚动的文本框来显示响应内容
            text_frame = self.ttk.Frame(response_dialog)
            text_frame.pack(fill=self.tk.BOTH, expand=True, padx=10, pady=10)
            
            response_text = self.scrolledtext.ScrolledText(text_frame, wrap=self.tk.WORD, width=80, height=25)
            response_text.pack(fill=self.tk.BOTH, expand=True)
            response_text.insert(self.tk.END, response)
            response_text.config(state=self.tk.DISABLED)  # 设置为只读
            
            # 自动复制到剪贴板
            response_dialog.clipboard_clear()
            response_dialog.clipboard_append(response)
            
            # 按钮框架
            button_frame = self.ttk.Frame(response_dialog)
            button_frame.pack(side=self.tk.BOTTOM, fill=self.tk.X, padx=10, pady=5)
            
            self.ttk.Button(button_frame, text="关闭", command=response_dialog.destroy).pack(side=self.tk.RIGHT, padx=5)


        def transcribe_selected():
            selected_items = tree.selection()
            if not selected_items:
                self.messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            
            # 检查选中的视频：已下载且没有SRT文件的视频
            videos_to_transcribe = []
            videos_already_transcribed = []
            videos_not_downloaded = []
            
            for item in selected_items:
                item_tags = tree.item(item, "tags")

                video_detail = None
                for video in channel_videos:
                    if video.get('url') == item_tags[0]:
                        video_detail = video
                        break
                if not video_detail:
                    continue

                video_file = video_detail.get('video_path', '')
                if not video_file:
                    prefix = self.downloader.generate_video_prefix(video_detail, title_length=15)
                    if os.path.exists(os.path.join(self.youtube_dir, f"__{prefix}.mp4")):
                        video_file = os.path.join(self.youtube_dir, f"__{prefix}.mp4")
                        video_detail['video_path'] = video_file
                
                if not video_file or not self.os.path.exists(video_file):
                    videos_not_downloaded.append(video_detail)
                    continue

                # 检查是否已有SRT文件
                filename_no_ext = self.os.path.splitext(self.os.path.basename(video_file))[0]
                possible_transcript_files = [
                    self.os.path.join(self.youtube_dir, f"__{filename_no_ext}.zh.srt"),
                    self.os.path.join(self.youtube_dir, f"__{filename_no_ext}.en.srt"),
                    self.os.path.join(self.youtube_dir, f"__{filename_no_ext}.srt")
                ]
                transcribed_file = None
                for f in possible_transcript_files:
                    if self.os.path.exists(f):
                        transcribed_file = f
                        break
                
                if transcribed_file:
                    video_detail['transcribed_file'] = transcribed_file
                    videos_already_transcribed.append(video_detail)
                else:
                    videos_to_transcribe.append(video_detail)

            # 如果没有可转录的视频，显示提示
            if not videos_to_transcribe:
                self.messagebox.showwarning("提示", "选中的视频都未下载，请先下载。", parent=dialog)
                return
            
            message = f"将转录 {len(videos_to_transcribe)} 个视频\n\n是否继续？"
            if not self.messagebox.askyesno("确认转录", message, parent=dialog):
                return

            if videos_already_transcribed:
                for video_detail in videos_already_transcribed:
                    update_text_content(video_detail.get('url', ''))

            if videos_not_downloaded:
                for video_detail in videos_not_downloaded:
                    self.messagebox.showwarning("提示", "选中的视频都未下载，请先下载。", parent=dialog)
                    return

            # 弹出语言选择对话框
            lang_dialog = self.tk.Toplevel(dialog)
            lang_dialog.title("选择转录语言")
            lang_dialog.geometry("400x150")
            lang_dialog.transient(dialog)
            lang_dialog.grab_set()
            
            lang_frame = self.ttk.Frame(lang_dialog)
            lang_frame.pack(fill=self.tk.X, padx=20, pady=20)
            
            self.ttk.Label(lang_frame, text="语言:").pack(side=self.tk.LEFT, padx=(20, 0))
            target_lang_var = self.tk.StringVar(value="zh")
            self.ttk.Combobox(lang_frame, textvariable=target_lang_var, 
                        values=["zh", "en", "ja", "ko", "es", "fr", "de"], 
                        width=10, state="readonly").pack(side=self.tk.LEFT, padx=5)
            
            result_var = self.tk.StringVar(value="cancel")
            
            def on_confirm():
                result_var.set("confirm")
                lang_dialog.destroy()
            
            def on_cancel():
                result_var.set("cancel")
                lang_dialog.destroy()
            
            button_frame = self.ttk.Frame(lang_dialog)
            button_frame.pack(fill=self.tk.X, padx=20, pady=10)
            self.ttk.Button(button_frame, text="确定", command=on_confirm).pack(side=self.tk.LEFT, padx=5)
            self.ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=self.tk.LEFT, padx=5)
            self.root.wait_window(lang_dialog)
            if result_var.get() == "cancel":
                return
            
            target_lang = target_lang_var.get()
            
            # 开始转录（不关闭对话框，转录完成后刷新列表）
            _transcribe_videos_batch(videos_to_transcribe, target_lang, on_complete=lambda: refresh_video_list())
        
        self.ttk.Button(bottom_frame, text="全选", command=select_all).pack(side=self.tk.LEFT, padx=5)
        self.ttk.Button(bottom_frame, text="不选", command=deselect_all).pack(side=self.tk.LEFT, padx=5)

        self.ttk.Button(bottom_frame, text="取消", command=dialog.destroy).pack(side=self.tk.RIGHT, padx=5)
        self.ttk.Button(bottom_frame, text="编撰", command=compile_selected).pack(side=self.tk.RIGHT, padx=5)
        self.ttk.Button(bottom_frame, text="转录", command=transcribe_selected).pack(side=self.tk.RIGHT, padx=5)
        self.ttk.Button(bottom_frame, text="下载", command=download_selected).pack(side=self.tk.RIGHT, padx=5)


        def _transcribe_videos_batch(videos, target_lang, on_complete=None):
            total = len(videos)
            
            progress_dialog = self.tk.Toplevel(self.root)
            progress_dialog.title("批量转录进度")
            progress_dialog.geometry("600x300")
            progress_dialog.transient(self.root)
            progress_dialog.grab_set()
            
            info_label = self.ttk.Label(progress_dialog, text=f"准备转录 {total} 个视频...", font=("Arial", 12, "bold"))
            info_label.pack(pady=10)
            
            progress_var = self.tk.DoubleVar()
            progress_bar = self.ttk.Progressbar(progress_dialog, variable=progress_var, maximum=100)
            progress_bar.pack(fill=self.tk.X, padx=20, pady=10)
            
            status_label = self.ttk.Label(progress_dialog, text="", font=("Arial", 10))
            status_label.pack(pady=5)
            
            log_frame = self.ttk.Frame(progress_dialog)
            log_frame.pack(fill=self.tk.BOTH, expand=True, padx=20, pady=10)
            
            log_scrollbar = self.ttk.Scrollbar(log_frame)
            log_scrollbar.pack(side=self.tk.RIGHT, fill=self.tk.Y)
            
            log_text = self.tk.Text(log_frame, height=10, yscrollcommand=log_scrollbar.set)
            log_text.pack(side=self.tk.LEFT, fill=self.tk.BOTH, expand=True)
            log_scrollbar.config(command=log_text.yview)
            
            def safe_update_ui(func):
                """安全地更新UI组件，如果对话框已关闭则跳过"""
                try:
                    if progress_dialog.winfo_exists():
                        func()
                        progress_dialog.update()
                except (self.tk.TclError, AttributeError):
                    # 组件已被销毁，忽略错误
                    pass

            def transcribe_task():
                success_count = 0
                failed_count = 0
                
                for idx, video_detail in enumerate(videos, 1):
                    file_path = video_detail.get('file_path', '')
                    video_url = video_detail.get('url', '')
                    title = video_detail.get('title', 'Unknown')
                    
                    # 更新状态
                    def update_status():
                        status_label.config(text=f"正在转录 ({idx}/{total}): {title[:50]}...")
                    safe_update_ui(update_status)
                    
                    if idx % 20 == 0:
                        self.downloader._check_and_update_cookies()

                    try:
                        filename_no_ext = self.os.path.splitext(self.os.path.basename(file_path))[0]
                        download_prefix = self.os.path.join(self.os.path.dirname(file_path), f"__{filename_no_ext}")
                        
                        lang = self.downloader.download_captions(
                            video_url,
                            target_lang,
                            download_prefix,
                            "srt"
                        )
                        
                        if lang:
                            print(f"  ✅ 转录成功")
                            update_text_content(video_url)
                            success_count += 1
                        else:
                            print(f"  ❌ 转录失败：无法下载字幕")
                            failed_count += 1
                            
                    except Exception as e:
                        print(f"  ❌ 转录失败: {str(e)}")
                        failed_count += 1
                    
                    # 更新进度条
                    def update_progress():
                        progress_var.set((idx / total) * 100)
                    safe_update_ui(update_progress)

                # save the video_detail to channel_videos
                with open(channel_vidoe_json_file, 'w', encoding='utf-8') as f:
                    self.json.dump(channel_videos, f, ensure_ascii=False, indent=2)


                def update_completion():
                    info_label.config(text=f"转录完成！成功: {success_count}, 失败: {failed_count}")
                    status_label.config(text="")
                safe_update_ui(update_completion)

                print(f"\n{'='*50}")
                print(f"转录任务完成！")
                print(f"成功: {success_count} 个")
                print(f"失败: {failed_count} 个")
                
                # 调用完成回调（刷新视频列表）
                if on_complete:
                    try:
                        on_complete()
                        print("✅ 已刷新视频列表")
                    except Exception as e:
                        print(f"⚠️ 刷新列表失败: {str(e)}")
                
                # 添加关闭按钮
                def close_dialog():
                    progress_dialog.destroy()
                
                def add_close_button():
                    self.ttk.Button(progress_dialog, text="关闭", command=close_dialog).pack(pady=10)
                safe_update_ui(add_close_button)
            
            # 在后台线程中转录
            thread = self.threading.Thread(target=transcribe_task)
            thread.daemon = True
            thread.start()


    def fetch_hot_videos(self):
        """获取频道热门视频列表，保存到JSON文件"""
        # 第一步：输入URL和参数
        url_dialog = self.tk.Toplevel(self.root)
        url_dialog.title("获取热门视频列表")
        url_dialog.geometry("600x200")
        url_dialog.transient(self.root)
        url_dialog.grab_set()
        
        # URL输入框
        url_frame = self.ttk.Frame(url_dialog)
        url_frame.pack(fill=self.tk.X, padx=20, pady=20)
        self.ttk.Label(url_frame, text="频道或播放列表URL:").pack(side=self.tk.LEFT)
        channel_url_var = self.tk.StringVar()
        url_entry = self.ttk.Entry(url_frame, textvariable=channel_url_var, width=50)
        url_entry.pack(side=self.tk.LEFT, padx=5, fill=self.tk.X, expand=True)
        
        # 参数输入
        param_frame = self.ttk.Frame(url_dialog)
        param_frame.pack(fill=self.tk.X, padx=20, pady=5)
        
        self.ttk.Label(param_frame, text="最大视频数量:").pack(side=self.tk.LEFT, padx=5)
        max_videos_var = self.tk.StringVar(value="200")
        max_videos_entry = self.ttk.Entry(param_frame, textvariable=max_videos_var, width=10)
        max_videos_entry.pack(side=self.tk.LEFT, padx=5)
        
        self.ttk.Label(param_frame, text="最小观看次数:").pack(side=self.tk.LEFT, padx=5)
        min_view_count_var = self.tk.StringVar(value="200")
        min_view_count_entry = self.ttk.Entry(param_frame, textvariable=min_view_count_var, width=10)
        min_view_count_entry.pack(side=self.tk.LEFT, padx=5)
        
        result_var = self.tk.StringVar(value="cancel")
        
        def on_url_confirm():
            url = channel_url_var.get().strip()
            if not url:
                self.messagebox.showerror("错误", "请输入URL", parent=url_dialog)
                return
            result_var.set("confirm")
            url_dialog.destroy()
        
        def on_url_cancel():
            result_var.set("cancel")
            url_dialog.destroy()

        # 按钮
        button_frame = self.ttk.Frame(url_dialog)
        button_frame.pack(fill=self.tk.X, padx=20, pady=10)
        self.ttk.Button(button_frame, text="确认", command=on_url_confirm).pack(side=self.tk.LEFT, padx=5)
        self.ttk.Button(button_frame, text="取消", command=on_url_cancel).pack(side=self.tk.LEFT, padx=5)
        
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
        loading_dialog = self.tk.Toplevel(self.root)
        loading_dialog.title("获取视频列表中")
        loading_dialog.geometry("300x100")
        loading_dialog.transient(self.root)
        loading_dialog.grab_set()
        self.ttk.Label(loading_dialog, text="正在获取视频列表，请稍候...", font=("Arial", 12)).pack(pady=30)
        self.root.update()
        
        # 在后台线程中获取视频列表
        hot_videos = []
        error_msg = None
        fetch_complete = [False]  # 用于跟踪是否完成

        def fetch_videos():
            nonlocal hot_videos, error_msg
            try:
                hot_videos = self.downloader.list_hot_videos(
                    channel_url, 
                    max_videos=int(max_videos_var.get()), 
                    min_view_count=int(min_view_count_var.get())
                )
            except Exception as e:
                error_msg = str(e)
            finally:
                fetch_complete[0] = True
        
        thread = self.threading.Thread(target=fetch_videos)
        thread.daemon = True
        thread.start()
        
        # 使用轮询方式等待完成，而不是 join()
        def check_completion():
            if fetch_complete[0]:
                loading_dialog.destroy()
                
                if error_msg:
                    self.messagebox.showerror("错误", f"获取视频列表失败: {error_msg}")
                    return
                
                if not hot_videos:
                    self.messagebox.showwarning("提示", "未找到符合条件的视频")
                    return
            else:
                # 继续检查，每100ms检查一次
                self.root.after(100, check_completion)
        
        # 开始检查
        self.root.after(100, check_completion)


    def _download_videos_batch(self, video_detail_list, on_complete=None):
        """批量下载视频"""
        if not video_detail_list or len(video_detail_list) == 0:
            return
        
        total = len(video_detail_list)
        
        # 获取当前日期和频道名
        current_date = self.datetime.now().strftime("%Y%m%d")
        
        # 从第一个视频获取频道名 - 尝试多个字段
        if video_detail_list:
            first_video = video_detail_list[0]
            channel_name = first_video.get('channel', 'Unknown')
            if channel_name.lower() == 'unknown':
                channel_name = first_video.get('uploader', 'Unknown')
            if channel_name.lower() == 'unknown':
                channel_name = first_video.get('channel_id', 'Unknown')
            print(f"📺 频道名称: {channel_name}")
            print(f"🔍 调试信息 - channel: {first_video.get('channel')}, uploader: {first_video.get('uploader')}, channel_id: {first_video.get('channel_id')}")
        else:
            channel_name = 'Unknown'
        
        # 清理频道名中的非法字符
        channel_name = re.sub(r'[<>:"/\\|?*]', '_', channel_name)
        
        # 创建进度对话框
        progress_dialog = self.tk.Toplevel(self.root)
        progress_dialog.title("批量下载中")
        progress_dialog.geometry("500x200")
        progress_dialog.transient(self.root)
        progress_dialog.grab_set()
        
        # 当前下载信息
        current_label = self.ttk.Label(progress_dialog, text="准备下载...", font=("Arial", 10))
        current_label.pack(pady=10)
        
        # 进度条
        progress = self.ttk.Progressbar(progress_dialog, length=400, mode='determinate', maximum=total)
        progress.pack(pady=10)
        
        # 统计信息
        stats_label = self.ttk.Label(progress_dialog, text=f"总计: 0 / {total}", font=("Arial", 10))
        stats_label.pack(pady=5)
        
        # 下载日志
        log_frame = self.ttk.Frame(progress_dialog)
        log_frame.pack(fill=self.tk.BOTH, expand=True, padx=10, pady=5)
        log_text = self.scrolledtext.ScrolledText(log_frame, height=6, state='disabled')
        log_text.pack(fill=self.tk.BOTH, expand=True)
        
        def log(message):
            log_text.config(state='normal')
            log_text.insert(self.tk.END, message + "\n")
            log_text.see(self.tk.END)
            log_text.config(state='disabled')
            progress_dialog.update()
        
        completed = [0]
        failed = [0]
        download_results = []
        

        def download_task():
            for idx, video_detail in enumerate(video_detail_list, 1):
                try:
                    current_label.config(text=f"正在下载: {video_detail['title'][:50]}...")
                    progress_dialog.update()
                    
                    log(f"[{idx}/{total}] 下载: {video_detail['title']}")
                    
                    if idx % 10 == 0:
                        self.downloader._check_and_update_cookies()

                    # 使用可重用的方法生成文件名前缀（下载时使用100字符）
                    video_prefix = self.downloader.generate_video_prefix( video_detail, title_length=50 )
                    file_path = self.downloader.download_video_highest_resolution(video_detail['url'], video_prefix=video_prefix)
                    video_detail['video_path'] = file_path
                    
                    if file_path and self.os.path.exists(file_path):
                        file_size = self.os.path.getsize(file_path) / (1024 * 1024)  # MB
                        log(f"✅ 完成: {self.os.path.basename(file_path)} ({file_size:.1f} MB)")
                        
                        # 记录下载结果
                        download_results.append({
                            'filename': self.os.path.basename(file_path),
                            'file_path': file_path,
                            'url': video_detail['url'],
                            'title': video_detail['title'],
                            'view_count': video_detail.get('view_count', 0),
                            'duration': video_detail.get('duration', 0),
                            'uploader': video_detail.get('uploader', ''),
                            'upload_date': video_detail.get('upload_date', "20260101"),
                            'download_date': self.datetime.now().strftime("%Y%m%d_%H%M%S"),
                            'file_size_mb': file_size,
                            'status': 'success'
                        })
                        
                        completed[0] += 1
                    else:
                        log(f"❌ 失败: {video_detail['title']}")
                        download_results.append({
                            'url': video_detail['url'],
                            'title': video_detail['title'],
                            'view_count': 0,
                            'status': 'failed',
                            'error': 'File not found after download'
                        })
                        failed[0] += 1
                    
                except Exception as e:
                    log(f"❌ 错误: {video_detail['title']} - {str(e)}")
                    download_results.append({
                        'url': video_detail.get('url', ''),
                        'title': video_detail.get('title', 'Unknown'),
                        'view_count': 0,
                        'status': 'failed',
                        'error': str(e)
                    })
                    failed[0] += 1
                
                progress['value'] = idx
                stats_label.config(text=f"完成: {completed[0]} | 失败: {failed[0]} | 总计: {idx} / {total}")
                progress_dialog.update()
            
            # 保存下载列表到JSON文件
            json_filename = f"{current_date}_{channel_name}_downloads.json"
            json_path = self.os.path.join(f"{self.config.get_project_path(self.get_pid())}/Youtbue_download", json_filename)
            
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    self.json.dump({
                        'channel_name': channel_name,
                        'download_date': self.datetime.now().strftime("%Y%m%d_%H%M%S"),
                        'total_videos': total,
                        'successful': completed[0],
                        'failed': failed[0],
                        'videos': download_results
                    }, f, ensure_ascii=False, indent=2)
                log(f"📄 下载列表已保存: {json_filename}")
            except Exception as e:
                log(f"⚠️ 保存JSON失败: {str(e)}")
            
            # 下载完成
            current_label.config(text="下载完成！")
            log(f"\n{'='*50}")
            log(f"批量下载完成！")
            log(f"成功: {completed[0]} 个")
            log(f"失败: {failed[0]} 个")
            
            # 调用完成回调（刷新视频列表）
            if on_complete:
                try:
                    on_complete()
                    log("✅ 已刷新视频列表")
                except Exception as e:
                    log(f"⚠️ 刷新列表失败: {str(e)}")
            
            # 添加关闭按钮
            def close_dialog():
                progress_dialog.destroy()
            
            self.ttk.Button(progress_dialog, text="关闭", command=close_dialog).pack(pady=10)
        
        # 在后台线程中下载
        thread = self.threading.Thread(target=download_task)
        thread.daemon = True
        thread.start()


    def review_download_list(self):
        """审阅下载列表并可以选择转录"""
        import json
        from tkinter import filedialog
        
        # 选择JSON文件
        download_folder = self.os.path.join(self.config.get_project_path(self.get_pid()), "Youtbue_download")
        if not self.os.path.exists(download_folder):
            self.messagebox.showwarning("提示", "下载文件夹不存在")
            return
        
        json_file = self.filedialog.askopenfilename(
            title="选择下载列表JSON文件",
            initialdir=download_folder,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not json_file:
            return
        
        # 读取JSON文件
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                download_data = self.json.load(f)
        except Exception as e:
            self.messagebox.showerror("错误", f"读取JSON文件失败: {str(e)}")
            return
        
        videos = download_data.get('videos', [])
        if not videos:
            self.messagebox.showwarning("提示", "下载列表为空")
            return
        
        # 只显示成功下载的视频
        successful_videos = [v for v in videos if v.get('status') == 'success']
        
        if not successful_videos:
            self.messagebox.showwarning("提示", "没有成功下载的视频")
            return
        
        # 创建审阅对话框
        dialog = self.tk.Toplevel(self.root)
        dialog.title(f"下载列表审阅 - {download_data.get('channel_name', 'Unknown')}")
        dialog.geometry("1000x600")
        dialog.transient(self.root)
        
        # 顶部信息
        info_frame = self.ttk.Frame(dialog)
        info_frame.pack(fill=self.tk.X, padx=10, pady=5)
        
        info_text = (f"频道: {download_data.get('channel_name', 'Unknown')} | "
                    f"下载日期: {download_data.get('download_date', 'Unknown')} | "
                    f"成功: {download_data.get('successful', 0)} | "
                    f"失败: {download_data.get('failed', 0)}")
        self.ttk.Label(info_frame, text=info_text, font=("Arial", 10, "bold")).pack(side=self.tk.LEFT)
        
        # 创建Treeview显示视频列表
        columns = ("filename", "title", "views", "duration", "size", "transcript")
        tree_frame = self.ttk.Frame(dialog)
        tree_frame.pack(fill=self.tk.BOTH, expand=True, padx=10, pady=5)
        
        # 添加滚动条
        scrollbar = self.ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=self.tk.RIGHT, fill=self.tk.Y)
        
        tree = self.ttk.Treeview(tree_frame, columns=columns, show="tree headings", 
                            yscrollcommand=scrollbar.set, selectmode="browse")
        tree.pack(side=self.tk.LEFT, fill=self.tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        
        # 设置列标题和宽度
        tree.heading("#0", text="序号")
        tree.heading("filename", text="文件名")
        tree.heading("title", text="标题")
        tree.heading("views", text="观看次数")
        tree.heading("duration", text="时长")
        tree.heading("size", text="大小(MB)")
        tree.heading("transcript", text="转录状态")
        
        tree.column("#0", width=50, anchor="center")
        tree.column("filename", width=200, anchor="w")
        tree.column("title", width=250, anchor="w")
        tree.column("views", width=100, anchor="e")
        tree.column("duration", width=80, anchor="center")
        tree.column("size", width=80, anchor="e")
        tree.column("transcript", width=100, anchor="center")
        
        # 填充数据
        for idx, video in enumerate(successful_videos, 1):
            # 格式化时长
            duration_sec = video.get('duration', 0)
            duration_str = f"{duration_sec // 60}:{duration_sec % 60:02d}" if duration_sec else "N/A"
            
            # 格式化观看次数
            view_count = video.get('view_count', 0)
            view_str = f"{view_count:,}" if view_count else "N/A"
            
            # 检查是否已有转录文件
            file_path = video.get('file_path', '')
            filename_no_ext = self.os.path.splitext(self.os.path.basename(file_path))[0] if file_path else ''
            
            # 检查多种可能的转录文件
            transcript_status = "❌ 未转录"
            if file_path:
                base_path = self.os.path.dirname(file_path)
                possible_transcript_files = [
                    self.os.path.join(base_path, f"__{filename_no_ext}.zh.srt"),
                    self.os.path.join(base_path, f"__{filename_no_ext}.en.srt"),
                    self.os.path.join(base_path, f"__{filename_no_ext}.srt"),
                ]
                for trans_file in possible_transcript_files:
                    if self.os.path.exists(trans_file):
                        transcript_status = "✅ 已转录"
                        break
            
            tree.insert("", self.tk.END, text=str(idx), 
                       values=(
                           video.get('filename', 'N/A')[:40],
                           video.get('title', 'Unknown')[:50],
                           view_str,
                           duration_str,
                           f"{video.get('file_size_mb', 0):.1f}",
                           transcript_status
                       ),
                       tags=(video.get('url', ''), video.get('file_path', '')))
        
        # 底部按钮
        bottom_frame = self.ttk.Frame(dialog)
        bottom_frame.pack(fill=self.tk.X, padx=10, pady=10)


    def download_youtube(self, transcribe):
        """下载YouTube视频并转录"""
        # 弹出对话框让用户输入URL
        dialog = self.tk.Toplevel(self.root)
        dialog.title("YouTube下载")
        dialog.geometry("600x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # YouTube URL输入
        url_frame = self.ttk.Frame(dialog)
        url_frame.pack(fill=self.tk.X, padx=20, pady=10)
        self.ttk.Label(url_frame, text="YouTube链接:").pack(side=self.tk.LEFT)
        url_var = self.tk.StringVar()
        url_entry = self.ttk.Entry(url_frame, textvariable=url_var, width=50)
        url_entry.pack(side=self.tk.LEFT, padx=5, fill=self.tk.X, expand=True)
        
        # 语言选择
        lang_frame = self.ttk.Frame(dialog)
        self.ttk.Label(lang_frame, text="语言:").pack(side=self.tk.LEFT, padx=(20, 0))
        target_lang_var = self.tk.StringVar(value="zh")
        target_lang_combo = self.ttk.Combobox(lang_frame, textvariable=target_lang_var, 
                                          values=["zh", "en", "ja", "ko", "es", "fr", "de"], 
                                          width=10, state="readonly")
        target_lang_combo.pack(side=self.tk.LEFT, padx=5)
        
        result_var = self.tk.StringVar(value="cancel")
        
        def on_confirm():
            url = url_var.get().strip()
            if not url:
                self.messagebox.showerror("错误", "请输入YouTube链接", parent=dialog)
                return
            result_var.set("confirm")
            dialog.destroy()
        
        def on_cancel():
            result_var.set("cancel")
            dialog.destroy()
        
        # 按钮
        button_frame = self.ttk.Frame(dialog)
        button_frame.pack(fill=self.tk.X, padx=20, pady=20)
        self.ttk.Button(button_frame, text="确认", command=on_confirm).pack(side=self.tk.LEFT, padx=5)
        self.ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=self.tk.LEFT, padx=5)
        
        # 等待对话框关闭
        self.root.wait_window(dialog)
        
        if result_var.get() == "cancel":
            return
        
        # 在对话框关闭后，通过 StringVar 获取值（它们仍然存在）
        video_url = url_var.get().strip()
        target_lang = target_lang_var.get()
        
        # 确认下载
        if not self.messagebox.askyesno("确认下载", f"确定要下载并转录这个视频吗？\n\nURL: {video_url}\n目标语言: {target_lang}\n\n转录结果将保存到项目的 Youtbue_download 文件夹中。"):
            return
        
        task_id = str(self.uuid.uuid4())
        self.tasks[task_id] = {
            "type": "download_youtube",
            "status": "运行中",
            "start_time": self.datetime.now(),
            "pid": self.get_pid()
        }
        
        def run_task():
            try:
                print(f"📥 开始下载YouTube视频并转录...")
                print(f"URL: {video_url}")
                print(f"语言: {target_lang}")

                video_data = self.downloader.get_video_detail(video_url, channel_name='Unknown')
                if not video_data:
                    self.log_to_output(self.download_output, f"❌ 获取视频详情失败")
                    self.root.after(0, lambda: self.messagebox.showerror("错误", "获取视频详情失败"))
                    return

                channel_name = video_data.get('channel', 'Unknown')
                if channel_name.lower() == 'unknown':
                    channel_name = video_data.get('uploader', 'Unknown')
                if channel_name.lower() == 'unknown':
                    channel_name = video_data.get('channel_id', 'Unknown')
            
                video_list_json_path = os.path.join(self.youtube_dir, f"_{channel_name}_hotvideos.json")
                if os.path.exists(video_list_json_path):
                    video_list_json = json.load(open(video_list_json_path, 'r', encoding='utf-8'))

                if not video_list_json:
                    self.log_to_output(self.download_output, f"❌ 获取视频列表失败")
                    self.root.after(0, lambda: self.messagebox.showerror("错误", "获取视频列表失败"))
                    return

                # add video_data to video_list_json
                video_list_json.append(video_data)
                with open(video_list_json_path, 'w', encoding='utf-8') as f:
                    json.dump(video_list_json, f, ensure_ascii=False, indent=2)

                video_prefix = self.downloader.generate_video_prefix(video_data, title_length=50)
                file_path = self.downloader.download_video_highest_resolution(video_url, video_prefix=video_prefix)

                if file_path and self.os.path.exists(file_path):
                    file_size = self.os.path.getsize(file_path) / (1024 * 1024)  # MB
                    self.log_to_output(self.download_output, f"✅ 视频下载完成！")
                    self.log_to_output(self.download_output, f"文件: {self.os.path.basename(file_path)}")
                    self.log_to_output(self.download_output, f"大小: {file_size:.1f} MB")
                    self.log_to_output(self.download_output, f"路径: {file_path}")
                else:
                    self.log_to_output(self.download_output, f"❌ 视频下载失败")
                    self.root.after(0, lambda: self.messagebox.showerror("错误", "视频下载失败"))
                    return

                download_prefix = self.os.path.join(self.os.path.dirname(file_path), f"__{video_prefix}")
                
                lang = self.downloader.download_captions(
                    video_url,
                    target_lang,
                    download_prefix,
                    "srt"
                )

                if lang:
                    print(f"✅ YouTube视频转录完成！")
                    
                    self.tasks[task_id]["status"] = "完成"
                    self.tasks[task_id]["result"] = lang
                    
                    # 显示成功消息，包含更多详情
                    success_msg = (
                        f"YouTube视频转录完成！"
                    )
                    
                    self.root.after(0, lambda: self.messagebox.showinfo("转录完成", success_msg))
                else:
                    print(f"❌ YouTube视频转录失败")
                    self.tasks[task_id]["status"] = "失败"
                    self.tasks[task_id]["error"] = "转录失败，未生成字幕文件"
                    
                    self.root.after(0, lambda: self.messagebox.showerror("错误", "YouTube视频转录失败：未生成字幕文件"))
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ YouTube视频转录失败: {error_msg}")
                import traceback
                traceback.print_exc()
                
                self.tasks[task_id]["status"] = "失败"
                self.tasks[task_id]["error"] = error_msg
                
                # 提供更详细的错误信息和解决方案
                detailed_error = (
                    f"YouTube视频转录失败\n\n"
                    f"错误信息:\n{error_msg}\n\n"
                    f"可能的解决方案:\n"
                    f"1. 检查视频链接是否正确\n"
                    f"2. 更新 yt-dlp: pip install -U yt-dlp\n"
                    f"3. 安装 Node.js (JavaScript 运行时)\n"
                    f"4. 检查视频是否有地区限制\n"
                    f"5. 确认视频状态（未删除/非私密）"
                )
                
                self.root.after(0, lambda: self.messagebox.showerror("转录失败", detailed_error))
        
        # 在独立线程中运行任务
        thread = self.threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
