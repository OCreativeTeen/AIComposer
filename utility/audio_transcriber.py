import os
import json
from typing import Any, Dict, List, Optional

from . import llm_api
import config_prompt
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
import requests
import config


VOICE_TEMP_PATH = "/AI_MEDIA/voice"
if not os.path.exists(VOICE_TEMP_PATH):
    os.makedirs(VOICE_TEMP_PATH)


def remove_transcribe_cache_for_audio_path(audio_path: str) -> None:
    """删除与音频同名的 .srt.json 缓存，便于强制重新转写。"""
    if not audio_path:
        return
    if audio_path.endswith(".mp3"):
        cache_file = audio_path.replace(".mp3", ".srt.json")
    elif audio_path.endswith(".wav"):
        cache_file = audio_path.replace(".wav", ".srt.json")
    else:
        return
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
        except OSError:
            pass


class AudioTranscriber:

    def __init__(self, pid, model_size, device):
        self.pid = pid
        self.model_size = model_size
        self.device = device
        self.api_url = "http://10.0.0.231:9001/transcribe"
        self.llm_api = llm_api.LLMApi(llm_api.GPT_MINI)
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)
        self._whisperx_engine: Optional[Any] = None

    def _ensure_whisperx(self):
        if self._whisperx_engine is None:
            from utility.audio_transcriber_x import AudioTranscriberX

            dev = str(self.device or "cuda").lower()
            ct = "float16" if dev.startswith("cuda") else "int8"
            self._whisperx_engine = AudioTranscriberX(
                model_size=self.model_size,
                device=self.device,
                compute_type=ct,
            )
        return self._whisperx_engine

    def transcribe_with_whisper(self, audio_path, language, min_duration, max_duration) -> List[Dict[str, Any]]:
        """
        优先使用本地 WhisperX（``utility/audio_transcriber_x.AudioTranscriberX.transcribe``：
        对齐、可选 diarization（默认 2 人）、NLP 重切后再合并）。
        失败时回退到原有 HTTP API。
        """
        print(f"🔍 开始转录：{audio_path}")

        lang = language
        if lang == "zh-CN" or lang == "tw":
            lang = "zh"

        if audio_path.endswith(".mp3"):
            transcribe_file = audio_path.replace(".mp3", ".srt.json")
        elif audio_path.endswith(".wav"):
            transcribe_file = audio_path.replace(".wav", ".srt.json")
        else:
            print(f"❌ 音频文件格式不支持: {audio_path}")
            return []

        if os.path.exists(transcribe_file):
            with open(transcribe_file, "r", encoding="utf-8") as f:
                segments = json.load(f)
            return segments

        total_duration = self.ffmpeg_audio_processor.get_duration(audio_path)
        print(f"📝 音频总时长: {total_duration:.1f}s ({total_duration / 60:.1f} 分钟)")

        try:
            wx = self._ensure_whisperx()
            segments, _out_path = wx.transcribe(
                audio_path,
                lang,
                diarize=True,
                min_speakers=2,
                max_speakers=2,
                min_duration=float(min_duration),
                max_duration=float(max_duration),
                nlp_resplit=True,
            )
            if segments:
                print(f"✅ WhisperX 转录完成，共 {len(segments)} 个片段")
                return segments
        except Exception as e:
            print(f"⚠️ WhisperX 转录失败，回退 HTTP API：{type(e).__name__}: {e}")

        print(f"📝 开始调用API转录 (language={lang})...")
        try:
            with open(audio_path, "rb") as f:
                files = {"audio_file": f}
                data = {"language": lang, "min_duration": min_duration, "max_duration": max_duration}
                response = requests.post(self.api_url, files=files, data=data, timeout=600)

            if response.status_code == 200:
                srt_segments = response.json()
                if srt_segments:
                    print(f"✅ API 转录完成，共 {len(srt_segments)} 个片段")
                    with open(transcribe_file, "w", encoding="utf-8") as f:
                        json.dump(srt_segments, f, ensure_ascii=False, indent=2)
                    return srt_segments

            print(f"❌ API调用失败: HTTP {response.status_code} - {response.text}")

        except Exception as e:
            print(f"❌ API调用失败: {str(e)}")

        return []

    def translate_text(self, text, source_language, target_language):
        if source_language == target_language:
            return config.chinese_convert(text, target_language)

        if (source_language == "zh" or source_language == "tw") and (
            target_language == "zh" or target_language == "tw"
        ):
            return config.chinese_convert(text, target_language)

        system_prompt = config_prompt.TRANSLATION_SYSTEM_PROMPT.format(
            source_language=config.LANGUAGES[source_language],
            target_language=config.LANGUAGES[target_language],
        )
        prompt = config_prompt.TRANSLATION_USER_PROMPT.format(
            source_language=config.LANGUAGES[source_language],
            target_language=config.LANGUAGES[target_language],
            text=text,
        )

        content = self.llm_api.generate_text(system_prompt, prompt)
        if content:
            return content.strip()
        return text