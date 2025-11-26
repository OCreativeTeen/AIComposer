import os
import yt_dlp
import subprocess
import config

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from urllib.parse import urlparse, parse_qs
from datetime import datetime
from io import BytesIO

from flask import Flask, request, jsonify, send_file



class YoutubeDownloader:

    def __init__(self, pid):
        print("YoutubeDownloader init...")
        self.pid = pid
        self.project_path = config.get_project_path(pid)


    def has_subtitles(self, video_url):
        """检查视频是否存在字幕语言"""
        try:
            ydl_opts = {'quiet': True, 'skip_download': True}
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
            ydl_opts = {'quiet': True, 'skip_download': True}
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


    def download_captions(self, video_url, lang, download_prefix):
        try:
            # 首先获取视频信息，检查可用的字幕语言
            ydl_opts = {'quiet': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                subtitles = info.get('subtitles', {})
                auto_captions = info.get('automatic_captions', {})
            
            # 检查是否有任何字幕
            if not subtitles and not auto_captions:
                print(f"❌ 视频没有任何字幕")
                return None
                
            # 确定要下载的语言
            target_lang = None
            available_langs = list(subtitles.keys()) + list(auto_captions.keys())
            
            # 首先检查是否有指定语言
            if lang in subtitles or lang in auto_captions:
                target_lang = lang
                print(f"✅ 找到目标语言字幕: {lang}")
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
                
            # 下载字幕
            ydl_opts = {
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': [target_lang],
                'subtitlesformat': 'srt',
                'outtmpl': download_prefix,
                'quiet': False,
            }
            
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

    def download_video_highest_resolution(self, video_url):
        """下载视频的最高分辨率版本"""
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  # 优先选择最高质量的MP4
            'outtmpl': os.path.join(f"{self.project_path}/Youtbue_download", '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': False,
            'progress_hooks': [self._progress_hook],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            # 返回下载的文件路径
            return os.path.abspath(f"{self.project_path}/Youtbue_download/{info['title']}.mp4")


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




