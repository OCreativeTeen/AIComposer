"""
Voicebox TTS / ASR 客户端：与 MinimaxSpeechService 相同入口（create_ssml / synthesize_speech / get_voice），
便于在 GUI 中替换导入。

环境变量（可选）：
  VOICEBOX_BASE_URL   默认 http://10.0.0.231:17493
  VOICEBOX_PROFILE_ID 默认示例 UUID（可被 VOICES 中 voice 覆盖）
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests

import config
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.file_util import safe_copy_overwrite

# 与 minimax_speech_service 一致，供 GUI import EXPRESSION_STYLES
EXPRESSION_STYLES = ["happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"]

# 仓库根目录下 ``media/voices.json``（非各视频项目目录）
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _repo_media_voices_json_path() -> str:
    return os.path.join(_REPO_ROOT, "media", "voices.json")


DEFAULT_BASE_URL = "http://10.0.0.231:17493"
DEFAULT_PROFILE_ID = "5c3b89e6-7eab-4809-8145-ba1c995e8abe"


def _transcribe_result_json(text: str, duration: Any = None) -> str:
    """统一为 JSON 字符串，含 ``text`` 与 ``duration``（无则 ``null``）。"""
    payload: Dict[str, Any] = {"text": text}
    if duration is not None:
        try:
            payload["duration"] = float(duration)
        except (TypeError, ValueError):
            payload["duration"] = duration
    else:
        payload["duration"] = None
    return json.dumps(payload, ensure_ascii=False)


def _vb_normalize_gender(token: str) -> str:
    t = (token or "").strip().lower()
    if t in ("man", "male", "boy", "guy"):
        return "man"
    return "woman"


def _vb_age_number_to_category(n: int) -> str:
    if n < 13:
        return "kids"
    if n < 20:
        return "teen"
    if n < 30:
        return "young"
    if n <= 60:
        return "mature"
    return "old"


def _vb_age_token_to_category(token: str) -> str:
    t = (token or "").strip().lower()
    if t.isdigit():
        return _vb_age_number_to_category(int(t))
    aliases = {
        "kid": "kids",
        "child": "kids",
        "children": "kids",
        "teenager": "teen",
        "middle": "mature",
        "middle-aged": "mature",
        "middle_aged": "mature",
        "senior": "old",
    }
    if t in aliases:
        return aliases[t]
    if t in ("kids", "teen", "young", "mature", "old", "narrator"):
        return t
    return "mature"


def _vb_normalize_race(token: str, language: str) -> str:
    t = (token or "").strip().lower()
    if t in ("chinese", "zh", "tw", "mandarin", "cn"):
        return "chinese"
    if t in ("english", "en", "eng"):
        return "english"
    if language in ("zh", "tw", "chinese"):
        return "chinese"
    return "english"


# 半角标点 → 中文常用全角（TTS 断句更自然）；`;` 按产品习惯映射为 `，`
_VB_ASCII_PUNCT_TO_FULL = str.maketrans(
    {
        ",": "，",
        ";": "，",
        ":": "：",
        "!": "！",
        "?": "？",
        "(": "（",
        ")": "）",
        "[": "【",
        "]": "】",
        "{": "｛",
        "}": "｝",
        '"': "\uff02",
        "'": "\uff07",
        "@": "＠",
        "#": "＃",
        "%": "％",
        "&": "＆",
        "*": "＊",
        "+": "＋",
        "=": "＝",
        "<": "＜",
        ">": "＞",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "~": "～",
        "^": "＾",
    }
)


def _vb_normalize_ascii_punctuation_to_cjk(s: str) -> str:
    """将常见英文半角标点换成中文全角；句号 `.` 在非小数处改为 `。`。"""
    if not s:
        return s
    s = s.translate(_VB_ASCII_PUNCT_TO_FULL)
    return re.sub(r"(?<!\d)\.(?!\d)", "。", s)


# 逐句 TTS 后拼接时，句间静音（秒）；来自 noise.wav 裁切，见 FfmpegAudioProcessor.make_silence
_VB_SEGMENT_GAP_SEC = 0.125


def _split_voicebox_segments(text: str) -> List[str]:
    """按中文句读标点拆句（作用于与 _normalize_for_voicebox 相同语义的文本）。"""
    text = (text or "").strip()
    if not text:
        return []
    text = re.sub(r" +", " ", text)
    chunks = re.split(r"(?<=[。！？])", text)
    parts = [c.strip() for c in chunks if c.strip()]
    return parts if parts else [text]


class VoiceboxService:
    """Voicebox：POST /generate + GET /audio/{id}；POST /transcribe（multipart file）。"""

    def __init__(self, pid: str, base_url: Optional[str] = None):
        self.pid = pid
        raw = (base_url or os.getenv("VOICEBOX_BASE_URL") or DEFAULT_BASE_URL).strip()
        self.base_url = raw.rstrip("/")
        self.default_profile_id = os.getenv("VOICEBOX_PROFILE_ID") or DEFAULT_PROFILE_ID
        print(f"Voicebox TTS base: {self.base_url}")
        _ensure_voices_for_project(self.pid)
        self._ffmpeg_audio = FfmpegAudioProcessor(pid)

    def _normalize_for_voicebox(self, text: str) -> str:
        """与 create_ssml 中一致：省略号/破折号、全角化、繁简转换（在 html.escape 之前）。"""
        text = text or ""
        text = re.sub(r"…", "。\n", text)
        text = re.sub(r"\.{3,}", "。\n", text)
        text = text.replace("——", "。\n")
        text = _vb_normalize_ascii_punctuation_to_cjk(text)
        text = re.sub(r"[\t\r]+", " ", text)
        text = config.chinese_convert(text, "zh")
        return text

    def _generate_url(self) -> str:
        return f"{self.base_url}/generate"

    def _audio_url(self, job_id: str) -> str:
        return f"{self.base_url}/audio/{job_id}"

    def _transcribe_url(self) -> str:
        return f"{self.base_url}/transcribe"

    def create_ssml(self, text: str, voice: Dict[str, Any], actions: str, language: str) -> str:
        """返回 JSON 字符串；synthesize_speech 解析后 POST /generate。"""
        norm = self._normalize_for_voicebox(text or "")
        escaped_text = html.escape(norm)
        profile_id = voice.get("voice") or voice.get("profile_id") or self.default_profile_id
        payload = {
            "profile_id": profile_id,
            "text": escaped_text,
        }
        return json.dumps(payload, ensure_ascii=False)

    def _post_generate_and_save_mp3(self, profile_id: str, text_for_api: str, out_mp3_path: str) -> bool:
        """POST /generate，轮询下载音频，写入 out_mp3_path。"""
        body = {"profile_id": profile_id, "text": text_for_api}
        try:
            r = requests.post(
                self._generate_url(),
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=600,
            )
            if r.status_code != 200:
                print(f"Voicebox /generate HTTP {r.status_code}: {r.text[:800]}")
                return False
            data = r.json()
        except requests.RequestException as e:
            print(f"Voicebox /generate request error: {e}")
            return False

        job_id = data.get("id")
        if not job_id:
            print(f"Voicebox: no id in response: {data!r}")
            return False

        raw = self._download_audio_bytes(job_id)
        if raw is None:
            return False

        os.makedirs(os.path.dirname(out_mp3_path) or ".", exist_ok=True)
        with open(out_mp3_path, "wb") as f:
            f.write(raw)
        return True

    def synthesize_speech(self, ssml_text: str) -> Optional[str]:
        """解析 create_ssml 的 JSON（或兼容仅含 text 字段），生成音频并保存为文件。
        多句时按标点拆句逐段生成，句间用 make_silence 静音拼接（concat_audios）。"""
        ssml_text = (ssml_text or "").strip()
        audio_path = f"{config.get_project_path(self.pid)}/temp/{self.string_to_code(ssml_text)}.mp3"
        if os.path.exists(audio_path):
            return audio_path

        try:
            payload = json.loads(ssml_text)
        except json.JSONDecodeError:
            payload = {"text": ssml_text, "profile_id": self.default_profile_id}

        text = payload.get("text")
        profile_id = payload.get("profile_id") or self.default_profile_id
        if not text:
            print("Voicebox: empty text")
            return None

        base = html.unescape(text)
        segments = _split_voicebox_segments(base)
        if len(segments) <= 1:
            if not self._post_generate_and_save_mp3(profile_id, text, audio_path):
                return None
            return audio_path

        print(
            f"Voicebox: 拆句 TTS 共 {len(segments)} 段，句间静音 {_VB_SEGMENT_GAP_SEC}s（noise.wav / concat）"
        )
        gap = self._ffmpeg_audio.make_silence(_VB_SEGMENT_GAP_SEC)
        if not gap:
            print("⚠️ Voicebox: make_silence 失败，句间无静音直接拼接")
        mp3_parts: List[str] = []
        for i, seg in enumerate(segments):
            esc = html.escape(seg)
            part_path = config.get_temp_file(self.pid, "mp3")
            if not self._post_generate_and_save_mp3(profile_id, esc, part_path):
                return None
            mp3_parts.append(part_path)

        chain: List[str] = []
        for i, p in enumerate(mp3_parts):
            chain.append(p)
            chain.append(gap)

        wav = self._ffmpeg_audio.concat_audios(chain)
        if not wav:
            return None
        mp3_out = self._ffmpeg_audio.to_mp3(wav)
        if not mp3_out:
            return None
        os.makedirs(os.path.dirname(audio_path) or ".", exist_ok=True)
        safe_copy_overwrite(mp3_out, audio_path)
        return audio_path

    def synthesize_speaker_text_to_wav(self, speaker: str, text: str, language_key: str) -> Optional[str]:
        """
        与 GUI.apply_tts_audio_to_scene_track 中 SSML→TTS→to_wav 段一致，供主界面与成品审阅复用。
        language_key: 与 workflow.language 相同，如 zh / tw / en。
        成功返回 wav 路径，失败返回 None。
        """
        text = (text or "").strip()
        if not text:
            return None
        lk = (language_key or "zh").lower().split("-")[0]
        if lk not in config.LANGUAGES:
            lk = "zh"
        lang = config.LANGUAGES[lk]
        voice = self.get_voice(speaker, lang)
        if not voice:
            print("Voicebox: get_voice 无匹配 voice")
            return None
        ssml = self.create_ssml(text=text, voice=voice, actions="", language=lang)
        audio_file = self.synthesize_speech(ssml)
        if not audio_file:
            return None
        return self._ffmpeg_audio.to_wav(audio_file)

    def _download_audio_bytes(self, job_id: str, max_wait_sec: float = 300.0) -> Optional[bytes]:
        """GET /audio/{id}，轮询直到拿到非空字节或超时。"""
        deadline = time.time() + max_wait_sec
        url = self._audio_url(job_id)
        last_err = None
        while time.time() < deadline:
            try:
                gr = requests.get(url, timeout=120)
                if gr.status_code == 200 and gr.content:
                    return gr.content
                if gr.status_code not in (200, 202, 404):
                    last_err = f"HTTP {gr.status_code} {gr.text[:200]}"
                time.sleep(0.4)
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(0.5)
        print(f"Voicebox: timeout downloading audio for id={job_id}: {last_err}")
        return None

    def transcribe(self, file_path: str) -> Optional[str]:
        """
        POST /transcribe，multipart 字段名 ``file``。

        典型 JSON 响应（与 Content-Type 是否含 application/json 无关时也会解析正文）::

            {"text": "…", "duration": 10.05425}

        成功时返回 **JSON 字符串**，形如上述对象（含 ``text`` 与 ``duration``；无时长则为 ``null``）。
        """
        if not file_path or not os.path.isfile(file_path):
            print(f"Voicebox transcribe: file not found: {file_path}")
            return None
        try:
            with open(file_path, "rb") as f:
                r = requests.post(
                    self._transcribe_url(),
                    files={"file": (os.path.basename(file_path), f)},
                    timeout=600,
                )
        except requests.RequestException as e:
            print(f"Voicebox /transcribe error: {e}")
            return None

        if r.status_code != 200:
            print(f"Voicebox /transcribe HTTP {r.status_code}: {r.text[:800]}")
            return None

        raw = (r.text or "").strip()
        if not raw:
            return None

        data: Any = None
        try:
            data = r.json()
        except json.JSONDecodeError:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return _transcribe_result_json(raw, None)

        if isinstance(data, str):
            t = data.strip()
            return _transcribe_result_json(t, None) if t else None
        if not isinstance(data, dict):
            t = str(data).strip()
            return _transcribe_result_json(t, None) if t else None

        if data.get("duration") is not None:
            try:
                print(f"Voicebox transcribe duration: {float(data['duration']):.3f}s")
            except (TypeError, ValueError):
                pass

        for key in ("text", "transcript", "result", "transcription", "content"):
            if key in data and data[key] is not None:
                return _transcribe_result_json(str(data[key]).strip(), data.get("duration"))
        return json.dumps(data, ensure_ascii=False)

    def string_to_code(self, input_string: str) -> str:
        input_string = str(input_string)
        hash_object = hashlib.md5(input_string.encode("utf-8"))
        code = str(hash_object.hexdigest())
        code = re.sub(r"[^a-zA-Z0-9_-]", "", code)
        return code

    def get_voice(self, speaker: str, language: str) -> dict:
        for v in VOICES:
            if v["name"].lower().strip() in speaker.lower().strip().lower():
                if v["language"].lower().strip() == language.lower().strip():
                    return v
                else:
                    return None

        return _voicebox_resolve_voice(speaker, language)


# profile_id 与 Minimax 的 voice 字段用法一致：存 UUID，可按项目改
VOICES: List[Dict[str, Any]] = [
    {
        "name": "woman/mature/chinese",
        "language": "chinese",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "e42ef432-b8f4-4c8f-8b40-4f75fb9f0b6d",
    },
    {
        "name": "man/mature/chinese",
        "language": "chinese",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "5f69a089-1fc5-4ba6-9dd8-60c809c25103",
    },
    {
        "name": "woman/mature/english",
        "language": "english",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "24437748-b794-470d-a536-81c1e32ab64b",
    },
    {
        "name": "man/mature/english",
        "language": "english",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "9f308b2c-d55b-4434-b15e-9a83dbdb35b1",
    },
    {
        "name": "woman/young/chinese",
        "language": "chinese",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "2cd0b3ec-b944-49f2-a621-fb60987aaa09",
    },
    {
        "name": "man/young/chinese",
        "language": "chinese",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "e01a9dad-d841-4c49-852b-fd0e161f7a37",
    },
    {
        "name": "woman/young/english",
        "language": "english",
        "volume": 1.0,  
        "speed": 1.0,
        "pitch": 0,
        "voice": "8085c594-6931-43d0-bf07-6dc0dbba8bd1",
    },
    {
        "name": "man/young/english",
        "language": "english",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "8ad21674-7919-49b4-9a3d-01171e9f47bd",
    },


    {
        "name": "man/narrator/chinese",
        "language": "chinese",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "3919d1ad-7d41-45a8-ae92-d7cec3584757"
    },
    {
        "name": "woman/qin/chinese",
        "language": "chinese",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "5c3b89e6-7eab-4809-8145-ba1c995e8abe"
    },
    {
        "name": "woman/qin-fast/chinese",
        "language": "chinese",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "3773bc54-ee3c-4a11-91c4-5890ef8a37ea"
    },
    {
        "name": "man/wj/chinese",
        "language": "chinese",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "f27d05a1-71eb-4e8c-876d-bc590fac200f"
    },
    {
        "name": "man/elon/english",
        "language": "english",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "99a43f1a-3e8f-4823-841a-1cf7d5a79000"
    },
    {
        "name": "man/trump/english",
        "language": "english",
        "volume": 1.0,
        "speed": 1.0,
        "pitch": 0,
        "voice": "904466f6-b170-49d8-94a4-f828e4cbdcbe"
    }
]

_VOICES_DEFAULT_SNAPSHOT: Optional[List[Dict[str, Any]]] = None
_voice_json_applied_pid: Optional[str] = None


def _normalize_voice_json_language(lang: Any) -> str:
    """voices.json 中的 language 统一为 ``chinese`` 或 ``english``。"""
    s = str(lang or "").strip().lower()
    if s in ("zh", "tw", "chinese", "mandarin", "cn", "c", "中文"):
        return "chinese"
    return "english"


def _voice_entries_from_json_payload(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        items = data.get("voices")
        if items is None:
            items = data.get("items")
        if items is None:
            return []
    elif isinstance(data, list):
        items = data
    else:
        return []
    out: List[Dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        vid = row.get("id") if row.get("id") is not None else row.get("voice")
        if vid is None:
            vid = row.get("profile_id")
        name = row.get("name")
        if vid is None or name is None or str(name).strip() == "":
            continue
        try:
            vol = float(row.get("volume", 1.0))
        except (TypeError, ValueError):
            vol = 1.0
        try:
            spd = float(row.get("speed", 1.0))
        except (TypeError, ValueError):
            spd = 1.0
        try:
            pitch = int(float(row.get("pitch", 0)))
        except (TypeError, ValueError):
            pitch = 0
        out.append(
            {
                "voice": str(vid).strip(),
                "name": str(name).strip(),
                "language": _normalize_voice_json_language(row.get("language")),
                "volume": vol,
                "speed": spd,
                "pitch": pitch,
            }
        )
    return out


def _ensure_voices_for_project(pid: str) -> None:
    """
    从本仓库 ``media/voices.json`` 加载音色时**整表替换** ``VOICES``（与内置默认字段一致）。
    同一 ``pid`` 只应用一次；切换项目时重新从默认快照还原再读文件。
    JSON：每项含 ``id``（或 ``voice`` / ``profile_id``）、``name``、``language``；可选 ``volume`` / ``speed`` / ``pitch``。
    """
    global VOICES, _VOICES_DEFAULT_SNAPSHOT, _voice_json_applied_pid
    if _VOICES_DEFAULT_SNAPSHOT is None:
        _VOICES_DEFAULT_SNAPSHOT = copy.deepcopy(VOICES)
    if _voice_json_applied_pid == pid:
        return
    VOICES = copy.deepcopy(_VOICES_DEFAULT_SNAPSHOT)
    path = _repo_media_voices_json_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, UnicodeError, json.JSONDecodeError) as e:
            print(f"Voicebox: 无法读取 {path}: {e}")
            _voice_json_applied_pid = pid
            return
        merged = _voice_entries_from_json_payload(data)
        if merged:
            VOICES = merged
    _voice_json_applied_pid = pid
    # 与 config.CHARACTER_PERSON_OPTIONS 同源（media/voices.json 的 name），切换项目时刷新下拉
    try:
        config.reload_character_person_options()
    except Exception:
        pass


def _voicebox_resolve_voice(speaker: str, language: str) -> dict:
    """
    按 ``VOICES`` 条目的 ``name`` 解析 speaker。

    speaker 形如 ``gender/age/race``（与 ``name`` 一致），例如 ``woman/mature/chinese``。
    gender：``woman`` | ``man``；race：``chinese`` | ``english``（缺省时由 ``language`` 推断）。

    age 可为词（``kids`` / ``teen`` / ``young`` / ``mature`` / ``old`` / ``narrator``）或**年龄数字**：
    <13 kids，<20 teen，20–29 young，30–60 mature，>60 old。
    """
    raw = (speaker or "").strip().replace("\\", "/")
    lang_pref = "chinese" if language in ("zh", "tw", "chinese") else "english"

    def _fallback() -> dict:
        for v in VOICES:
            if v["language"] == lang_pref:
                return v
        return VOICES[0]

    if not raw:
        return _fallback()

    for v in VOICES:
        if v["name"].lower() == raw.lower():
            return v

    parts = [p.strip() for p in raw.split("/") if p.strip()]
    if len(parts) >= 3:
        gender = _vb_normalize_gender(parts[0])
        age = _vb_age_token_to_category(parts[1])
        race = _vb_normalize_race(parts[2], language)
    elif len(parts) == 2:
        gender = _vb_normalize_gender(parts[0])
        age = _vb_age_token_to_category(parts[1])
        race = _vb_normalize_race("", language)
    elif len(parts) == 1:
        p = parts[0]
        if p.isdigit():
            gender = "woman"
            age = _vb_age_token_to_category(p)
            race = _vb_normalize_race("", language)
        else:
            gender = _vb_normalize_gender(p)
            age = "mature"
            race = _vb_normalize_race("", language)
    else:
        return _fallback()

    key = f"{gender}/{age}/{race}"
    for v in VOICES:
        if v["name"] == key:
            return v

    for v in VOICES:
        if v["language"] == lang_pref and v["name"].startswith(f"{gender}/") and v["name"].endswith(f"/{race}"):
            return v
    return _fallback()
