from faster_whisper import WhisperModel
from datetime import datetime
import re
import os
import json
import zhconv
from . import llm_api
import config_prompt
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from difflib import SequenceMatcher
from typing import List, Dict, Any
from utility.file_util import safe_file, read_json, write_json, clean_memory, safe_remove, read_text, write_text
import gc
import math
import torch
import requests


LANGUAGES = {
    "zh": "Chinese",
    "tw": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
}



VOICE_TEMP_PATH = "/AI_MEDIA/voice"
if not os.path.exists(VOICE_TEMP_PATH):
    os.makedirs(VOICE_TEMP_PATH)



class AudioTranscriber:

    def __init__(self, pid, model_size, device):
        self.pid = pid
        self.model_size = model_size
        self.device = device
        self.api_url = "http://10.0.0.222:9001/transcribe"
        self.llm_api = llm_api.LLMApi(llm_api.OLLAMA)
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)


    def fetch_text_from_json(self, script_path, output_path=None):
        """
        从JSON字幕文件中提取文本内容
        
        Args:
            script_path: JSON字幕文件路径
            output_path: 可选，输出文本文件路径。如果提供，将保存到文件；否则只返回文本
            
        Returns:
            str: 提取的文本内容
        """
        with open(script_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
        text_content = "\n".join([segment["caption"] for segment in segments])
        
        # 如果提供了输出路径，保存到文件
        if output_path:
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(text_content)
                print(f"✅ 文本已保存: {output_path}")
            except Exception as e:
                print(f"⚠️ 保存文本文件失败: {str(e)}")
        
        return text_content


    def transcribe_with_whisper(self, audio_path, language) -> List[Dict[str, Any]]:
        """
        api call to do transcribe audio, curl like:
        curl -X POST "http://10.0.0.231:9001/transcribe" -F "audio_file=@/path/to/your/audio.mp3" -F "language=en"
        """
        print(f"🔍 开始转录：{audio_path}")
        import sys
        
        lang = language
        if lang == "zh-CN" or lang == "tw":
            lang = "zh"

        # 检查缓存文件
        if audio_path.endswith('.mp3'):
            transcribe_file = audio_path.replace(".mp3", ".srt.json")        
        elif audio_path.endswith('.wav'):
            transcribe_file = audio_path.replace(".wav", ".srt.json")
        else:
            print(f"❌ 音频文件格式不支持: {audio_path}")
            return []

        if os.path.exists(transcribe_file):
            with open(transcribe_file, "r", encoding="utf-8") as f:
                segments = json.load(f)
            return segments

        # 获取音频总时长
        total_duration = self.ffmpeg_audio_processor.get_duration(audio_path)
        print(f"📝 音频总时长: {total_duration:.1f}s ({total_duration/60:.1f} 分钟)")
        
        # 音频不超过5分钟，直接调用API转录
        print(f"📝 开始调用API转录 (language={lang})...")
        try:
            with open(audio_path, 'rb') as f:
                files = {'audio_file': f}
                data = {'language': lang}
                response = requests.post(self.api_url, files=files, data=data, timeout=600)
            
            if response.status_code == 200:
                srt_segments = response.json()
                if srt_segments:
                    print(f"✅ 转录完成，共 {len(srt_segments)} 个片段")
                    with open(transcribe_file, "w", encoding="utf-8") as f:
                        json.dump(srt_segments, f, ensure_ascii=False, indent=2)
                    return srt_segments

            else:
                print(f"❌ API调用失败: HTTP {response.status_code} - {response.text}")

        except Exception as e:
            print(f"❌ API调用失败: {str(e)}")
        
        return []



    def chinese_convert(self, text, language):
        if language == "zh":
            # Convert to simplified Chinese
            return zhconv.convert(text, 'zh-cn')
        elif language == "tw":
            # Convert to traditional Chinese
            return zhconv.convert(text, 'zh-tw')
        else:
            return text


    def translate_text(self, text, source_language, target_language):
        if source_language == target_language:
            return self.chinese_convert(text, target_language)
        
        if (source_language == "zh" or source_language == "tw") and (target_language == "zh" or target_language == "tw"):
            return self.chinese_convert(text, target_language)
        
        system_prompt = config_prompt.TRANSLATION_SYSTEM_PROMPT.format(
            source_language=LANGUAGES[source_language],
            target_language=LANGUAGES[target_language]
        )
        prompt = config_prompt.TRANSLATION_USER_PROMPT.format(
            source_language=LANGUAGES[source_language],
            target_language=LANGUAGES[target_language],
            text=text
        )

        content = self.llm_api.generate_text(system_prompt, prompt)
        if content:
            content.strip()
        else:
            return text

