"""YouTube download / upload (MediaDownloader) (moved verbatim from gui/downloader.py)."""
import os
import time
import yt_dlp
import subprocess
import shutil
import json
import re
import config
from datetime import datetime, timedelta, timezone
import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.audio_transcriber import AudioTranscriber
from utility.file_util import write_json, safe_copy_overwrite, safe_remove, make_safe_file_name
import project_manager
import tkinter.messagebox as messagebox
from utility.media_probe import _ffprobe_video_height
from utility.time_util import _should_update_upload_date
from gui.dl.list_store import _GENERIC_PROJECT_VIDEO_TITLES, _channel_list_dir_for_media_downloader, _downloader_aux_dir, _infer_channel_list_item_media_dir, _normalize_channel_list_item_for_storage, _normalize_channel_videos_for_storage, _sync_project_video_title_on_list_row, _write_channel_list_json_file, _youtube_row_display_title, _youtube_row_project_title, _youtube_row_source_title  # re-export
from gui.dl.row_keys import _video_youtube_id  # re-export


def _normalize_youtube_watch_url(url: str) -> str:
    """单视频 watch URL；去掉 list / start_radio 等，避免 yt-dlp 按播放列表解析。"""
    url = (url or "").strip()
    if not url:
        return url
    m = re.search(
        r"(?:[?&]v=|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})",
        url,
    )
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


def _iter_node_executable_candidates():
    """常见 Node.js 路径（含 PATH 与 Windows 默认安装目录）。"""
    seen: set[str] = set()
    w = shutil.which("node")
    if w:
        ap = os.path.normcase(os.path.abspath(w))
        seen.add(ap)
        yield w
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    for p in (
        os.path.join(pf, "nodejs", "node.exe"),
        os.path.join(pf86, "nodejs", "node.exe"),
        os.path.join(local, "Programs", "nodejs", "node.exe"),
        os.path.join(
            local,
            "Programs",
            "cursor",
            "resources",
            "app",
            "resources",
            "helpers",
            "node.exe",
        ),
    ):
        if not p:
            continue
        ap = os.path.normcase(os.path.abspath(p))
        if ap in seen or not os.path.isfile(p):
            continue
        seen.add(ap)
        yield p


def _verify_node_executable(node_path: str) -> bool:
    try:
        r = subprocess.run(
            [node_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _youtube_format_error_message(raw_error: str, *, cookies_invalid: bool = False) -> str:
    msg = (raw_error or "").strip()
    hints = [
        "YouTube 无法获取音视频格式。常见原因与处理：",
        "1) Node.js — 需已安装并在 PATH 中（重启程序后应看到「检测到 JavaScript 运行时」）",
    ]
    if cookies_invalid:
        hints.append(
            "2) cookies 已过期（日志出现 no longer valid）— 请重新登录 YouTube 并导出 "
            "www.youtube.com_cookies.txt 到「下载」文件夹，然后重启本程序"
        )
        hints.append("   导出说明: https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies")
    else:
        hints.append(
            "2) cookies 过期 — 将新的 www.youtube.com_cookies.txt 放入「下载」文件夹"
        )
    hints.append("3) yt-dlp 过旧 — 在 venv 中执行: pip install -U yt-dlp")
    if msg:
        hints.append("")
        hints.append(f"原始错误: {msg}")
    return "\n".join(hints)


def _youtube_best_video_ydl_opts() -> dict:
    """yt-dlp：最高分辨率 + 最高帧率（先 ``bestvideo*`` 再合并为 mp4）。"""
    return {
        "format": "bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "prefer_free_formats": False,
        "format_sort": ["res:9999", "fps:9999", "size", "br", "asr"],
        "format_sort_force": True,
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
    }


YOUTUBE_VIDEO_FORMAT_FALLBACKS = (
    "bestvideo*+bestaudio/best",
    "bv*+ba/b",
    "bestvideo+bestaudio/best",
    "bestvideo*+bestaudio",
    "best",
)


YOUTUBE_VIDEO_MIN_HEIGHT_TO_SKIP_REDOWNLOAD = 1080


def _log_yt_downloaded_format_info(info: dict | None) -> None:
    if not isinstance(info, dict):
        return
    parts: list[str] = []
    for key in ("requested_formats", "requested_downloads"):
        for fmt in info.get(key) or []:
            if not isinstance(fmt, dict):
                continue
            if fmt.get("vcodec") == "none":
                continue
            h = fmt.get("height")
            fps = fmt.get("fps")
            ext = fmt.get("ext")
            if h or fps or ext:
                parts.append(f"{h or '?'}p {fps or '?'}fps {ext or '?'}")
    fp = (info.get("filepath") or "").strip()
    if parts:
        print(f"📺 已选画质: {', '.join(parts)}")
    if fp:
        print(f"📁 输出: {fp}")


YOUTUBE_AUDIO_FORMAT_FALLBACKS = (
    "bestaudio/best",
    "bestaudio",
    "ba/b",
    "best",
)


_YT_DOWNLOAD_PREFS_JSON = "_yt_download_prefs.json"


























class MediaDownloader:

    def __init__(self, pid, youtube_path, language):
        print("YoutubeDownloader init...")
        self.pid = pid
        self.youtube_dir = youtube_path
        self.channel_list_dir = _channel_list_dir_for_media_downloader(youtube_path)
        os.makedirs(self.channel_list_dir, exist_ok=True)
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
        self._cookies_session_disabled = False
        # 批量转录时由首个视频探测：None | {"mode":"caption","lang":...} | {"mode":"audio"}
        self._batch_transcribe_strategy = None
        # 按频道记住成功的 yt-dlp 音频下载策略（player_client / format / cookies）
        self._yt_download_pref = None


    def _find_cookies_file(self):
        cookies_filename = "www.youtube.com_cookies.txt"
        download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        download_cookies = os.path.join(download_folder, cookies_filename)
        
        if os.path.exists(download_cookies):
            print(f"✅ 在下载文件夹找到 cookies 文件: {download_cookies}")
            # 移动到项目路径
            project_cookies = os.path.join(_downloader_aux_dir(self.youtube_dir), cookies_filename)
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
        project_cookies = os.path.join(_downloader_aux_dir(self.youtube_dir), cookies_filename)
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
        while True:
            if os.path.exists(download_cookies):
                print(f"🔄 在下载文件夹发现新的 cookies 文件: {download_cookies}")
                
                # 移动到项目路径
                project_cookies = os.path.join(_downloader_aux_dir(self.youtube_dir), cookies_filename)
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
        for node_path in _iter_node_executable_candidates():
            if not _verify_node_executable(node_path):
                continue
            try:
                result = subprocess.run(
                    [node_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    version = (result.stdout or "").strip().split("\n")[0]
                    print(
                        f"✅ 检测到 JavaScript 运行时: Node.js {version} ({node_path})"
                    )
                    return ("node", node_path)
            except Exception:
                continue

        deno_path = shutil.which("deno")
        if deno_path:
            try:
                result = subprocess.run(
                    ["deno", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split("\n")[0]
                    print(f"✅ 检测到 JavaScript 运行时: Deno {version}")
                    return ("deno", deno_path)
            except Exception:
                pass

        print("⚠️ 未检测到 JavaScript 运行时（Node.js 或 Deno）")
        print("   这可能导致某些 YouTube 视频无法下载或格式缺失")
        print("   建议安装 Node.js: https://nodejs.org/")
        return (None, None)


    def _get_ydl_opts_base(self, **kwargs):
        """
        获取基础的 yt-dlp 选项，包含 cookies 支持
        
        Args:
            **kwargs: 额外的选项参数（quiet, skip_download 等）；``use_cookies=False`` 可禁用 cookies。
            
        Returns:
            dict: yt-dlp 选项字典
        """
        use_cookies = kwargs.pop("use_cookies", True)
        if getattr(self, "_cookies_session_disabled", False):
            use_cookies = False
        opts = {}

        if (
            use_cookies
            and self.cookie_file
            and os.path.exists(self.cookie_file)
            and os.path.getsize(self.cookie_file) > 0
        ):
            opts["cookiefile"] = self.cookie_file
            if not hasattr(self, "_cookies_logged"):
                print(f"🍪 使用 cookies 文件: {self.cookie_file}")
                self._cookies_logged = True

        if "sleep_interval" not in kwargs:
            opts["sleep_interval"] = 2
        if "sleep_interval_requests" not in kwargs:
            opts["sleep_interval_requests"] = 5

        if self.js_runtime[0] and "js_runtimes" not in kwargs:
            runtime_name, runtime_path = self.js_runtime
            runtime_config = {}
            if runtime_path:
                runtime_config["path"] = runtime_path
            opts["js_runtimes"] = {runtime_name: runtime_config}

        if "remote_components" not in kwargs:
            opts["remote_components"] = ["ejs:github"]

        if "noplaylist" not in kwargs:
            opts["noplaylist"] = True

        opts.update(kwargs)

        ea = dict(opts.get("extractor_args") or {})
        yt = dict(ea.get("youtube") or {})
        if "player_client" not in yt:
            if self.js_runtime[0]:
                yt["player_client"] = ["mweb", "web", "android", "tv_embedded"]
            else:
                yt["player_client"] = ["android", "mweb", "web"]
        ea["youtube"] = yt
        opts["extractor_args"] = ea

        return opts


    def _extract_youtube_info(self, video_url, *, use_cookies=True, **extra_opts):
        """``extract_info``；URL 规范为单视频 watch 链接。"""
        url = _normalize_youtube_watch_url(video_url)
        opts = self._get_ydl_opts_base(
            use_cookies=use_cookies,
            quiet=True,
            skip_download=True,
            **extra_opts,
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False), url


    def _disable_cookies_for_session(self, reason: str = "") -> None:
        if getattr(self, "_cookies_session_disabled", False):
            return
        self._cookies_session_disabled = True
        why = (reason or "").strip()
        print("🍪 本次会话将跳过 cookies（可能已过期）" + (f"：{why}" if why else ""))
        print("   请重新导出 www.youtube.com_cookies.txt 到「下载」文件夹后重启程序。")


    def _yt_download_pref_key(self) -> str:
        """用于记住下载策略的频道键（YouTube 列表名或 list JSON 基名）。"""
        name = (self.channel_name or "").strip()
        if name:
            return name
        path = (self.channel_list_json or "").strip()
        if path:
            base = os.path.basename(path)
            if base.lower().endswith(".json"):
                base = base[:-5]
            if base:
                return base
        return ""


    def _yt_download_prefs_file(self) -> str:
        return os.path.join(self.channel_list_dir, _YT_DOWNLOAD_PREFS_JSON)


    def _default_youtube_player_clients(self) -> list[str]:
        if self.js_runtime[0]:
            return ["mweb", "web", "android", "tv_embedded"]
        return ["android", "mweb", "web"]

    def _default_youtube_video_player_clients(self) -> list[str]:
        """视频最高画质：优先 web（android 常只有 360p/720p；tv_embedded 已弃用）。"""
        if self.js_runtime[0]:
            return ["web", "tv", "mweb"]
        return ["web", "mweb", "tv"]


    def _load_yt_download_pref(self) -> dict | None:
        key = self._yt_download_pref_key()
        if not key:
            return None
        cached = getattr(self, "_yt_download_pref", None)
        if isinstance(cached, dict) and cached.get("_key") == key:
            return cached.get("data")
        pref = None
        path = self._yt_download_prefs_file()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    ent = data.get(key)
                    if isinstance(ent, dict) and ent.get("format"):
                        pref = ent
            except Exception:
                pass
        self._yt_download_pref = {"_key": key, "data": pref}
        return pref


    def _save_yt_download_pref(self, pref: dict) -> None:
        key = self._yt_download_pref_key()
        if not key or not isinstance(pref, dict) or not pref.get("format"):
            return
        path = self._yt_download_prefs_file()
        data: dict = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                pass
        data[key] = {
            "use_cookies": bool(pref.get("use_cookies", True)),
            "format": str(pref["format"]),
            "player_client": str(pref.get("player_client") or ""),
        }
        write_json(path, data)
        self._yt_download_pref = {"_key": key, "data": data[key]}
        print(
            f"📌 已记住频道下载策略: cookies={data[key]['use_cookies']}, "
            f"client={data[key]['player_client']}, format={data[key]['format']}"
        )


    def _yt_merge_player_client_args(self, extra_opts: dict, player_client: str | None) -> dict:
        if not player_client:
            return extra_opts
        kw = dict(extra_opts)
        ea = dict(kw.get("extractor_args") or {})
        yt = dict(ea.get("youtube") or {})
        yt["player_client"] = [player_client]
        ea["youtube"] = yt
        kw["extractor_args"] = ea
        return kw


    def _yt_is_format_or_cookie_error(self, err: Exception | str) -> bool:
        msg = str(err or "").lower()
        return (
            "format" in msg
            or "no video formats" in msg
            or "cookies are no longer valid" in msg
            or "only images are available" in msg
        )


    def _yt_extract_download(
        self,
        video_url: str,
        *,
        use_cookies: bool = True,
        download: bool = True,
        format_string: str | None = None,
        **extra_opts,
    ):
        url = _normalize_youtube_watch_url(video_url)
        opts = self._get_ydl_opts_base(
            use_cookies=use_cookies,
            quiet=extra_opts.pop("quiet", True),
            **extra_opts,
        )
        if format_string:
            opts["format"] = format_string
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=download), url


    def _yt_download_pref_video_key(self) -> str:
        base = self._yt_download_pref_key()
        return f"{base}::video" if base else ""

    def _load_yt_download_video_pref(self) -> dict | None:
        key = self._yt_download_pref_video_key()
        if not key:
            return None
        path = self._yt_download_prefs_file()
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        ent = data.get(key)
        return ent if isinstance(ent, dict) else None

    def _save_yt_download_video_pref(self, pref: dict) -> None:
        key = self._yt_download_pref_video_key()
        if not key or not isinstance(pref, dict) or not pref.get("format"):
            return
        path = self._yt_download_prefs_file()
        data: dict = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                pass
        data[key] = {
            "use_cookies": bool(pref.get("use_cookies", True)),
            "format": str(pref["format"]),
            "player_client": str(pref.get("player_client") or ""),
        }
        write_json(path, data)
        print(
            f"📌 已记住频道视频下载策略: cookies={data[key]['use_cookies']}, "
            f"client={data[key]['player_client']}, format={data[key]['format']}"
        )

    def _yt_download_video_with_fallbacks(self, video_url: str, **extra_opts):
        """视频最高画质下载：web 客户端 + 多 format 回退（与音频策略分开记忆）。"""
        last_err = ""
        base_opts = {**_youtube_best_video_ydl_opts(), **extra_opts}

        saved = self._load_yt_download_video_pref()
        if saved and (saved.get("player_client") or "").strip().lower() in (
            "android",
            "ios",
        ):
            print("⚠️ 忽略旧的 android/ios 视频策略，改用 web 客户端…")
            saved = None
        if saved:
            fmt = saved.get("format")
            client = (saved.get("player_client") or "").strip() or None
            use_ck = bool(saved.get("use_cookies", True))
            if fmt:
                try:
                    kw = self._yt_merge_player_client_args(base_opts, client)
                    print(
                        f"📌 复用频道视频下载策略: cookies={use_ck}, "
                        f"client={client or 'default'}, format={fmt}"
                    )
                    return self._yt_extract_download(
                        video_url,
                        use_cookies=use_ck,
                        download=True,
                        format_string=fmt,
                        **kw,
                    )
                except yt_dlp.utils.DownloadError as e:
                    last_err = str(e)
                    if "cookies are no longer valid" in last_err.lower() and use_ck:
                        self._disable_cookies_for_session("YouTube 报告 cookies 无效")
                    if not self._yt_is_format_or_cookie_error(e):
                        raise
                    print("⚠️ 已保存的视频下载策略失效，重新探测…")

        cookie_phases = (True, False) if self.cookie_file else (False,)
        for use_ck in cookie_phases:
            if use_ck and getattr(self, "_cookies_session_disabled", False):
                continue
            for client in self._default_youtube_video_player_clients():
                for fmt in YOUTUBE_VIDEO_FORMAT_FALLBACKS:
                    try:
                        kw = self._yt_merge_player_client_args(base_opts, client)
                        result = self._yt_extract_download(
                            video_url,
                            use_cookies=use_ck,
                            download=True,
                            format_string=fmt,
                            **kw,
                        )
                        self._save_yt_download_video_pref(
                            {
                                "use_cookies": use_ck,
                                "format": fmt,
                                "player_client": client,
                            }
                        )
                        return result
                    except yt_dlp.utils.DownloadError as e:
                        last_err = str(e)
                        if "cookies are no longer valid" in last_err.lower() and use_ck:
                            self._disable_cookies_for_session("YouTube 报告 cookies 无效")
                            break
                        if not self._yt_is_format_or_cookie_error(e):
                            raise
                        print(
                            f"⚠️ 视频下载失败 (cookies={use_ck}, client={client}, "
                            f"format={fmt})，尝试下一方案…"
                        )
                        continue
                    except Exception:
                        raise
        cookies_bad = "cookies are no longer valid" in last_err.lower()
        raise Exception(
            _youtube_format_error_message(last_err, cookies_invalid=cookies_bad)
        )

    def _yt_download_with_fallbacks(
        self,
        video_url: str,
        *,
        format_candidates: tuple[str, ...] = YOUTUBE_AUDIO_FORMAT_FALLBACKS,
        **extra_opts,
    ):
        """先复用频道已记住的策略；失效则逐个 client/format 探测并写入记忆。"""
        last_err = ""

        saved = self._load_yt_download_pref()
        if saved:
            fmt = saved.get("format")
            client = (saved.get("player_client") or "").strip() or None
            use_ck = bool(saved.get("use_cookies", True))
            if fmt:
                try:
                    kw = self._yt_merge_player_client_args(extra_opts, client)
                    print(
                        f"📌 复用频道下载策略: cookies={use_ck}, "
                        f"client={client or 'default'}, format={fmt}"
                    )
                    return self._yt_extract_download(
                        video_url,
                        use_cookies=use_ck,
                        download=True,
                        format_string=fmt,
                        **kw,
                    )
                except yt_dlp.utils.DownloadError as e:
                    last_err = str(e)
                    if "cookies are no longer valid" in last_err.lower() and use_ck:
                        self._disable_cookies_for_session("YouTube 报告 cookies 无效")
                    if not self._yt_is_format_or_cookie_error(e):
                        raise
                    print("⚠️ 已保存的下载策略失效，重新探测…")
                except Exception:
                    raise

        cookie_phases = (True, False) if self.cookie_file else (False,)
        for use_ck in cookie_phases:
            if use_ck and getattr(self, "_cookies_session_disabled", False):
                continue
            for client in self._default_youtube_player_clients():
                for fmt in format_candidates:
                    try:
                        kw = self._yt_merge_player_client_args(extra_opts, client)
                        result = self._yt_extract_download(
                            video_url,
                            use_cookies=use_ck,
                            download=True,
                            format_string=fmt,
                            **kw,
                        )
                        self._save_yt_download_pref(
                            {
                                "use_cookies": use_ck,
                                "format": fmt,
                                "player_client": client,
                            }
                        )
                        return result
                    except yt_dlp.utils.DownloadError as e:
                        last_err = str(e)
                        if "cookies are no longer valid" in last_err.lower() and use_ck:
                            self._disable_cookies_for_session("YouTube 报告 cookies 无效")
                            break
                        if not self._yt_is_format_or_cookie_error(e):
                            raise
                        print(
                            f"⚠️ 下载失败 (cookies={use_ck}, client={client}, "
                            f"format={fmt})，尝试下一方案…"
                        )
                        continue
                    except Exception:
                        raise
        cookies_bad = "cookies are no longer valid" in last_err.lower()
        raise Exception(
            _youtube_format_error_message(last_err, cookies_invalid=cookies_bad)
        )




    def _find_caption_srt(self, download_prefix, target_lang):
        """查找 yt-dlp 下载的字幕文件（语言码可能与请求不完全一致）。"""
        expected = f"{download_prefix}.{target_lang}.srt"
        if os.path.exists(expected):
            return expected
        media_dir = os.path.dirname(download_prefix)
        base = os.path.basename(download_prefix)
        if not os.path.isdir(media_dir):
            return None
        for filename in os.listdir(media_dir):
            if filename.startswith(base) and filename.endswith(".srt"):
                return os.path.join(media_dir, filename)
        return None

    def _transcribe_audio_to_json(self, video_detail, target_lang, audio_path):
        """用 Whisper 转录音频并写入 JSON，成功返回路径。"""
        if not audio_path or not os.path.exists(audio_path):
            return None
        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        src_path = f"{download_prefix}.{target_lang}.json"
        if os.path.exists(src_path):
            return src_path
        cfg = project_manager.PROJECT_CONFIG or {}
        scene_min_length = cfg.get("scene_min_length", 9)
        script_json = self.transcriber.transcribe_with_whisper(
            audio_path,
            target_lang,
            False,
            False,
            False,
            scene_min_length,
            int(scene_min_length * 1.5),
        )
        if script_json:
            write_json(src_path, script_json)
            return src_path
        return None

    def _ensure_audio_path(self, video_detail):
        """返回已有或可解析的音频路径；不存在则返回空字符串。"""
        audio_path = (video_detail.get("audio_path") or "").strip()
        if audio_path and os.path.exists(audio_path):
            return audio_path
        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        for ext in ("mp3", "m4a", "webm", "opus", "wav"):
            candidate = f"{download_prefix}.{ext}"
            if os.path.exists(candidate):
                video_detail["audio_path"] = candidate
                return candidate
        video_path = f"{download_prefix}.mp4"
        if os.path.exists(video_path):
            audio_path = self.ffmpeg_audio_processor.extract_audio_from_video(video_path, "mp3")
            mp3_path = f"{download_prefix}.mp3"
            safe_copy_overwrite(audio_path, mp3_path)
            video_detail["audio_path"] = mp3_path
            return mp3_path
        return ""

    def download_captions(self, video_detail, target_lang, *, allow_audio_fallback=None):
        if not target_lang:
            return None

        video_url = video_detail.get('url', '')
        if not video_url:
            return None

        if allow_audio_fallback is None:
            allow_audio_fallback = config.TRANSCRIBE_FALLBACK_TO_AUDIO

        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        
        video_url = _normalize_youtube_watch_url(video_url)
        caption_opts = dict(
            skip_download=True,
            writesubtitles=True,
            writeautomaticsub=True,
            subtitleslangs=[target_lang],
            subtitlesformat="srt",
            outtmpl=download_prefix,
            quiet=True,
            no_warnings=True,
            format="bestaudio/best",
        )
        for use_ck in (True, False):
            if use_ck and (
                not self.cookie_file
                or getattr(self, "_cookies_session_disabled", False)
            ):
                continue
            try:
                info, _ = self._yt_extract_download(
                    video_url,
                    use_cookies=use_ck,
                    download=True,
                    **caption_opts,
                )
                if info and "upload_date" in info:
                    upload_date = info.get("upload_date", "")
                    if upload_date:
                        upload_date = str(upload_date).strip()
                        if upload_date:
                            if len(upload_date) == 10:
                                upload_date = upload_date.replace("-", "")
                            if _should_update_upload_date(video_detail):
                                video_detail["upload_date"] = upload_date[:8]
                                print(f"✅ 已更新 upload_date: {upload_date[:8]}")
                src_path = self._find_caption_srt(download_prefix, target_lang)
                if src_path:
                    print(f"✅ 已下载字幕：语言 {target_lang}")
                    return src_path
            except yt_dlp.utils.DownloadError as e:
                err = str(e)
                if "cookies are no longer valid" in err.lower() and use_ck:
                    self._disable_cookies_for_session("YouTube 报告 cookies 无效")
                    continue
                if self._yt_is_format_or_cookie_error(e) and use_ck:
                    print("⚠️ 带 cookies 下载字幕失败，尝试无 cookies…")
                    continue
            except Exception:
                break

        if not allow_audio_fallback:
            return None

        print(f"❌ 下载字幕失败，尝试音频转录...")
        src_path = f"{download_prefix}.{target_lang}.json"
        if os.path.exists(src_path):
            return src_path

        audio_path = self._ensure_audio_path(video_detail)
        if not audio_path:
            print(f"❌ 音频文件不存在")
            return None

        return self._transcribe_audio_to_json(video_detail, target_lang, audio_path)

    def reset_batch_transcribe_strategy(self):
        """重置批量转录策略（新批次开始时调用，首个视频会重新探测）。"""
        self._batch_transcribe_strategy = None

    def _get_caption_lang_priority(self):
        """按当前频道语言只尝试一种字幕（en 频道试 en，其余一律试 zh）。"""
        if (self.language or "zh").lower().startswith("en"):
            return ["en"]
        return ["zh"]

    def _transcribe_via_audio(self, video_detail, target_lang, *, direct_audio=False):
        """下载音频（若本地无）并用 Whisper 转录。"""
        audio_path = self._ensure_audio_path(video_detail)
        if not audio_path:
            if direct_audio:
                print("📥 正在下载音频…")
            else:
                print("📥 字幕不可用，正在下载音频…")
            audio_path = self.download_audio_only(video_detail)
        if not audio_path:
            print("❌ 音频下载失败，无法转录")
            return None
        return self._transcribe_audio_to_json(video_detail, target_lang, audio_path)

    def transcribe_video_detail(self, video_detail, target_lang=None, *, batch_mode=False):
        """优先下载字幕；失败时按 config 决定是否下载音频并 Whisper 转录。

        batch_mode=True 时，首个视频探测字幕语言/音频 fallback，后续视频复用同一策略。
        """
        target_lang = target_lang or self.language or "zh"
        strategy = self._batch_transcribe_strategy if batch_mode else None

        if strategy and strategy.get("mode") == "caption":
            return self.download_captions(
                video_detail, strategy["lang"], allow_audio_fallback=False
            )

        if strategy and strategy.get("mode") == "audio":
            if not config.TRANSCRIBE_FALLBACK_TO_AUDIO:
                return None
            return self._transcribe_via_audio(video_detail, target_lang, direct_audio=True)

        # 首个视频或非批量：按语言优先级探测字幕
        for lang in self._get_caption_lang_priority():
            transcribed_file = self.download_captions(
                video_detail, lang, allow_audio_fallback=False
            )
            if transcribed_file:
                if batch_mode:
                    self._batch_transcribe_strategy = {"mode": "caption", "lang": lang}
                    print(f"📌 批量策略：后续使用字幕 ({lang})")
                return transcribed_file

        if batch_mode:
            self._batch_transcribe_strategy = {"mode": "audio"}
            print("📌 批量策略：字幕不可用，后续直接下载音频转录")

        if not config.TRANSCRIBE_FALLBACK_TO_AUDIO:
            return None
        return self._transcribe_via_audio(video_detail, target_lang)

    def transcribe_audio_detail(self, video_detail, target_lang=None):
        """仅用本地/已下载音频 Whisper 转录，不尝试下载字幕。"""
        target_lang = target_lang or self.language or "zh"
        audio_path = self._ensure_audio_path(video_detail)
        if not audio_path:
            print("❌ 音频文件不存在，无法转录")
            return None
        return self._transcribe_audio_to_json(video_detail, target_lang, audio_path)


    def try_download_caption_with_priority(self, video_detail):
        """按用户选择的语言优先尝试下载字幕，成功返回路径，失败返回 None"""
        if not self.cookie_file:
            return None
        for lang in self._get_caption_lang_priority():
            path = self.download_captions(video_detail, lang, allow_audio_fallback=False)
            if path:
                return path
        return None


    def download_audio_only(self, video_detail, sleep_interval=2):
        video_url = _normalize_youtube_watch_url(video_detail.get("url", ""))
        if video_url:
            video_detail["url"] = video_url
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
        ydl_extra = {
            "outtmpl": outtmpl,
            "quiet": False,
            "progress_hooks": [self._progress_hook],
            "skip_download": False,
            "ignoreerrors": False,
        }
        if sleep_interval is not None:
            ydl_extra["sleep_interval"] = sleep_interval

        try:
            info, _ = self._yt_download_with_fallbacks(
                video_url,
                **ydl_extra,
            )

            if info and "upload_date" in info:
                upload_date = info.get("upload_date", "")
                if upload_date:
                    if len(upload_date) == 10:
                        upload_date = upload_date.replace("-", "")
                    if _should_update_upload_date(video_detail):
                        video_detail["upload_date"] = upload_date
                        print(f"✅ 已更新 upload_date: {upload_date}")

            for ext in audio_extensions:
                expected_path = os.path.abspath(f"{video_prefix}.{ext}")
                if os.path.exists(expected_path):
                    print(f"✅ 找到下载的音频文件: {expected_path}")
                    if not expected_path.endswith(".mp3"):
                        a = self.ffmpeg_audio_processor.to_mp3(expected_path)
                        expected_path = video_prefix + ".mp3"
                        safe_copy_overwrite(a, expected_path)
                    video_detail["audio_path"] = expected_path
                    return expected_path

            if info and info.get("requested_downloads"):
                actual_path = info["requested_downloads"][0].get("filepath")
                if actual_path and os.path.exists(actual_path):
                    expected_path = os.path.abspath(actual_path)
                    if not expected_path.endswith(".mp3"):
                        a = self.ffmpeg_audio_processor.to_mp3(expected_path)
                        safe_remove(expected_path)
                        expected_path = video_prefix + ".mp3"
                        safe_copy_overwrite(a, expected_path)
                    video_detail["audio_path"] = expected_path
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
            existing_h = _ffprobe_video_height(target_video_path)
            if (
                existing_h is not None
                and existing_h >= YOUTUBE_VIDEO_MIN_HEIGHT_TO_SKIP_REDOWNLOAD
            ):
                if video_detail.get('video_path', '') == target_video_path:
                    return video_detail['video_path']
                video_detail['video_path'] = target_video_path
                audio_path = video_detail.get('audio_path', '')
                if not audio_path or audio_path != target_audio_path:
                    a = self.ffmpeg_audio_processor.extract_audio_from_video(
                        target_video_path, "mp3"
                    )
                    safe_copy_overwrite(a, target_audio_path)
                    video_detail['audio_path'] = target_audio_path
                print(
                    f"✅ 已有高清视频（{existing_h}p），跳过下载: "
                    f"{os.path.basename(target_video_path)}"
                )
                return video_detail['video_path']
            if existing_h:
                print(
                    f"⚠️ 已有视频仅 {existing_h}p（<{YOUTUBE_VIDEO_MIN_HEIGHT_TO_SKIP_REDOWNLOAD}p），"
                    "将重新下载更高画质…"
                )
            for ext in ("mp4", "webm", "mkv"):
                p = video_prefix + f".{ext}"
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

        outtmpl = video_prefix + ".%(ext)s"
        ydl_opts_kwargs = {
            "outtmpl": outtmpl,
            "quiet": False,
            "progress_hooks": [self._progress_hook],
            "skip_download": False,
            "ignoreerrors": False,
        }
        if sleep_interval is not None:
            ydl_opts_kwargs["sleep_interval"] = sleep_interval

        self._check_and_update_cookies()
        try:
            info, _ = self._yt_download_video_with_fallbacks(
                video_url,
                **ydl_opts_kwargs,
            )
            _log_yt_downloaded_format_info(info)
            if not os.path.exists(target_video_path):
                base_path = target_video_path.rsplit('.', 1)[0]
                for ext in ['webm', 'mkv', 'mp4']:
                    alt_path = f"{base_path}.{ext}"
                    if os.path.exists(alt_path):
                        print(f"✅ 找到下载文件: {alt_path}")
                        target_video_path = alt_path
                        break
                fp = ""
                if isinstance(info, dict):
                    fp = (info.get("filepath") or "").strip()
                if fp and os.path.isfile(fp):
                    target_video_path = os.path.abspath(fp)

            if not os.path.exists(target_video_path):
                print("❌ 视频下载完成但未找到输出文件")
                return None

            safe_copy_overwrite(
                self.ffmpeg_audio_processor.extract_audio_from_video(
                    target_video_path, "mp3"
                ),
                target_audio_path,
            )
            video_detail['audio_path'] = target_audio_path
            video_detail['video_path'] = target_video_path
            out_h = _ffprobe_video_height(target_video_path)
            if out_h:
                print(f"✅ 视频已保存: {out_h}p → {target_video_path}")
            return target_video_path

        except Exception as e:
            print(f"❌ 下载视频失败: {e}")
            return None




    def get_video_detail(self, video_url, channel_name='Unknown'):
        video_url = _normalize_youtube_watch_url(video_url)
        video_detail = None
        resolved_url = video_url
        last_error = ""

        try:
            video_detail, resolved_url = self._extract_youtube_info(
                video_url, use_cookies=True
            )
        except yt_dlp.utils.DownloadError as e:
            last_error = str(e)
            if "cookies are no longer valid" in last_error.lower():
                self._disable_cookies_for_session("YouTube 报告 cookies 无效")
            fmt_fail = (
                "format" in last_error.lower()
                or "No video formats" in last_error
                or "only images are available" in last_error.lower()
            )
            if (fmt_fail or getattr(self, "_cookies_session_disabled", False)) and self.cookie_file:
                try:
                    print("⚠️ 带 cookies 拉取失败，尝试无 cookies / android 客户端…")
                    video_detail, resolved_url = self._extract_youtube_info(
                        video_url, use_cookies=False
                    )
                    last_error = ""
                except Exception as retry_e:
                    last_error = str(retry_e)

            if video_detail is None:
                if "403" in last_error or "Forbidden" in last_error:
                    raise Exception(
                        f"HTTP 403 Forbidden - YouTube 访问被拒绝，可能需要更新 cookies 或等待: {video_url}"
                    )
                if "challenge" in last_error.lower():
                    raise Exception(f"YouTube 挑战验证失败: {video_url}")
                if fmt_fail or "format" in last_error.lower():
                    cookies_bad = "cookies are no longer valid" in last_error.lower()
                    raise Exception(
                        _youtube_format_error_message(
                            last_error, cookies_invalid=cookies_bad
                        )
                    )
                raise Exception(f"下载错误: {last_error}")

        if not video_detail:
            raise Exception(f"无法获取视频信息: {video_url}")

        uploader = video_detail.get("uploader") or video_detail.get("channel") or channel_name
        chan = video_detail.get("channel") or video_detail.get("uploader") or channel_name
        return {
            "title": video_detail.get("title", "Unknown Title"),
            "url": resolved_url or video_url,
            "id": video_detail.get("id", ""),
            "duration": video_detail.get("duration", 0),
            "view_count": video_detail.get("view_count", 0),
            "uploader": uploader,
            "channel": chan,
            "channel_id": video_detail.get("channel_id", ""),
            "upload_date": video_detail.get("upload_date", ""),
            "thumbnail": video_detail.get("thumbnail", ""),
            "description": video_detail.get("description", "")[:200]
            if video_detail.get("description")
            else "",
        }


    def generate_video_prefix(self, video_detail, title_length=15):
        # 格式: {view_count:010d}_{upload_date}_{title}.{ext}
        view_count = video_detail.get('view_count', 0)
        upload_date = video_detail.get('upload_date', "20260101")
        title = _youtube_row_display_title(video_detail)

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
        new_title = _youtube_row_display_title(video_data).lower()
        if not new_title:
            return True
        for existing_video in self.channel_videos:
            existing_title = _youtube_row_display_title(existing_video).lower()
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

            info_path = os.path.join(_downloader_aux_dir(self.youtube_dir), f"info_{channel_name}.json")
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
        
            if not info or 'entries' not in info:
                return None

            self.channel_list_json = os.path.join(self.channel_list_dir, f"{channel_name}.json")
            if os.path.exists(self.channel_list_json):
                with open(self.channel_list_json, 'r', encoding='utf-8') as f:
                    self.channel_videos = json.load(f)
                    _normalize_channel_videos_for_storage(self.channel_videos)
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
                        _disp = (video_data.get('title') or '')[:50]
                        print(f"✓ {count} -- {_disp} -- {video_data['view_count']:,} 观看" + (f" ({ud[:8]})" if ud else "") + " (使用列表信息)")
                    else:
                        # entry 中信息不足，尝试获取详细信息
                        try:
                            video_data = self.get_video_detail(video_url, channel_name)
                            _disp = (video_data.get('title') or '')[:50]
                            print(f"✓ {count} -- {_disp} -- {video_data['view_count']:,} 观看")
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

            _normalize_channel_videos_for_storage(self.channel_videos)
            _write_channel_list_json_file(self.channel_list_json, self.channel_videos)

            return channel_name
            
        except Exception as e:
            print(f"❌ 获取视频列表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # YouTube 元数据字段：更新列表时从抓取结果覆盖，不覆盖用户添加的 audio_path/status/topic_* 等
    YOUTUBE_META_FIELDS = (
        'title',
        'url',
        'duration',
        'view_count',
        'uploader',
        'channel',
        'channel_id',
        'upload_date',
        'thumbnail',
        'description',
    )

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
                    _disp = (video_data.get('title') or '')[:50]
                    print(f"✓ {count} -- {_disp} -- {video_data['view_count']:,} 观看" + (f" ({video_data.get('upload_date', '')[:8]})" if video_data.get('upload_date') else ""))
                else:
                    try:
                        video_data = self.get_video_detail(video_url, channel_name)
                        if video_data and video_data.get('upload_date'):
                            ud = video_data['upload_date']
                            if isinstance(ud, str) and len(ud) == 10 and '-' in ud:
                                video_data['upload_date'] = ud.replace('-', '')[:8]
                        _disp = (video_data.get('title') or '')[:50]
                        print(f"✓ {count} -- {_disp} -- {video_data['view_count']:,} 观看")
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



    def upload_video(
        self,
        file_path,
        thumbnail_path,
        title,
        description,
        language,
        script_path,
        secret_key,
        channel_id,
        categoryId,
        tags,
        privacy="unlisted",
        publish_at=None,
    ):
        """
        publish_at: 若为 datetime，则定时公开（YouTube 要求 privacy 为 private，并设置 status.publishAt，UTC RFC3339）。
        若为 None，则按 privacy 立即上传（如 unlisted）。
        """
        scopes = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]

        # 区分不同频道的 token 文件
        token_file = config.get_channel_path(channel_id) + f"/token_{channel_id}.json"
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

        status_block = {
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        }
        if publish_at is not None:
            # API：仅当 privacyStatus 为 private 且从未发布过时，可设置 publishAt
            if not isinstance(publish_at, datetime):
                raise TypeError("publish_at 须为 datetime 或 None")
            local_tz = datetime.now().astimezone().tzinfo
            dt_utc = publish_at if publish_at.tzinfo else publish_at.replace(tzinfo=local_tz)
            dt_utc = dt_utc.astimezone(timezone.utc)
            publish_at_str = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            status_block["privacyStatus"] = "private"
            status_block["publishAt"] = publish_at_str
            print(f"📅 定时发布（UTC）: {publish_at_str}")
        else:
            status_block["privacyStatus"] = privacy

        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": categoryId,
                "defaultLanguage": youtube_language,  # Video language
                "defaultAudioLanguage": youtube_language  # Audio language
            },
            "status": status_block,
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
        snippet = response.get("snippet") or {}
        published_at_iso = (
            snippet.get("publishedAt")
            or snippet.get("published_at")
            or ""
        )
        print("✅ Upload successful! Video ID:", video_id)
        print(f"📝 Video settings applied:")
        print(f"   - Privacy: {request_body['status'].get('privacyStatus')}")
        if request_body["status"].get("publishAt"):
            print(f"   - publishAt: {request_body['status']['publishAt']}")
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

        return video_id, (published_at_iso or "").strip()


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
