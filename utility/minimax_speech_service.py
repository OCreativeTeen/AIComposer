import requests
import json
import os
from typing import Optional, Dict, List
import hashlib
import re
import time
from .ffmpeg_audio_processor import FfmpegAudioProcessor
from .llm_api import LLMApi
import config
import base64
import binascii


class MinimaxSpeechService:

    def __init__(self, pid: str):
        # Use provided values or fallback to config
        self.pid = pid
        self.access_token = os.getenv("MINIMAX_KEY", "")
        group_id = os.getenv("MINIMAX_GROUP_ID", "")
        self.tts_url = f"https://api.minimaxi.chat/v1/t2a_v2?GroupId={group_id}" 
        
        self.llm_large = LLMApi(model=LLMApi.GEMINI_2_0_FLASH)
        
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)
        print(f"TTS URL: {self.tts_url}")


    def create_ssml(self, text: str, voice: str, mood: str = "calm", speed: float = 1.0, pitch: int = 0, vol: float = 1.0) -> str:
        # Escape special XML characters in text
        import html
        escaped_text = html.escape(text)

        # 使用正则表达式替换换行符和制表符
        escaped_text = re.sub(r'[\n\t]', '<#0.5#>', escaped_text)
        # 使用正则表达式将多个连续空格替换为单个空格
        escaped_text = re.sub(r' {2,}', ' ', escaped_text)
        # 使用正则表达式移除标点符号后的空格
        escaped_text = re.sub(r'([,.!，。？，；：]) ', r'\1', escaped_text)
        
        # 将剩余的空格替换为语音停顿标记
        escaped_text = escaped_text.replace(" ", "<#0.5#>")

        mood = mood.lower()
        if mood not in EXPRESSION_STYLES:
            mood = "calm"

        ssml = f"""
{{
    "model":"speech-2.5-hd-preview",
    "text":"{escaped_text}",
    "stream":false,
    "language_boost":"auto",
    "output_format":"hex",
    "voice_setting":{{
        "voice_id":"{voice}",
        "speed":{speed},
        "vol":{vol},
        "pitch":{pitch},
        "emotion":"{mood}"
    }},
    "audio_setting":{{
        "sample_rate":32000,
        "bitrate":128000,
        "format":"mp3",
        "channel":1
    }}
}}
"""
        return ssml
    

    def synthesize_speech(self, ssml_text: str) :
        audio_path = f"{config.get_project_path(self.pid)}/media/{self.string_to_code(ssml_text)}.mp3"
        if os.path.exists(audio_path):
            return audio_path
        # Clean and validate SSML
        ssml_text = ssml_text.strip()
        
        # Debug: Print SSML being sent
        print(f"Sending SSML: {ssml_text}")
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(self.tts_url, headers=headers, data=ssml_text.encode('utf-8'), timeout=10000)
            
            if response.status_code == 200:
                # 解析JSON响应
                response_data = json.loads(response.content.decode('utf-8'))
                
                # 获取base64编码的音频数据
                audio_hex = response_data['data']['audio']
                
                # 尝试直接解码
                audio_binary = bytes.fromhex(audio_hex)
                # 保存为MP3文件
                with open(audio_path, 'wb') as f:
                    f.write(audio_binary)
                
                return audio_path
            else:
                # Print detailed error information
                print(f"Request headers: {headers}")
                print(f"Request body: {ssml_text}")
                print(f"Response status: {response.status_code}")
                print(f"Response headers: {response.headers}")
                print(f"Response text: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Network error during TTS request: {str(e)}")
            return None


    def string_to_code(self, input_string):
        # Generate MD5 hash of the input string
        input_string = str(input_string)  # Ensure it's a string
        hash_object = hashlib.md5(input_string.encode('utf-8'))

        # Get hexadecimal representation and truncate to desired length
        code = str(hash_object.hexdigest())
        code = re.sub(r'[^a-zA-Z0-9_-]', '', code)
        # Ensure the code is filename-safe by removing/ replacing unsafe characters
        return code


    def get_voice(self, speaker: str, language: str) -> str:
        for voice in VOICES:
            if voice["language"] != language:
                continue
            if voice["name"] == speaker:
                return voice["voice"]
            if voice["voice"] == speaker:
                return voice["voice"]
        return "male-qn-qingse"


# Common Chinese voices and moods
VOICES = [
    {
        'name': 'female-host',
        'language': 'chinese',
        'voice': 'female-chengshu-jingpin' # female-yujie   female-chengshu   presenter_female
    },
    {
        'name': 'male-host',
        'language': 'chinese',
        'voice': 'male-qn-badao-jingpin' #'male-qn-jingying-jingpin' # male-qn-jingying  presenter_male
    },
    {
        'name': 'actress',
        'language': 'chinese',
        'voice': 'female-yujie-jingpin' # female-shaonv  female-tianmei-jingpin
    },
    {
        'name': 'actor',
        'language': 'chinese',
        'voice': 'male-qn-daxuesheng-jingpin'
    },
    {
        'name': 'trump',
        'language': 'english',
        'voice': 'moss_audio_b37dc4b3-9691-11f0-aeab-4aec103046b8'
    },
    {
        'name': 'wwj',
        'language': 'chinese',
        'voice': 'moss_audio_73fe2657-9743-11f0-aeab-4aec103046b8'
    },
    {
        'name': 'qin',
        'language': 'chinese',
        'voice': 'moss_audio_9edd8a0f-9743-11f0-b659-7a84e7f91f54'
    },
    {
        'name': 'male-qingse',
        'language': 'chinese',
        'voice': 'male-qn-qingse'
    },
    {
        'name': 'male-jingying',
        'language': 'chinese',
        'voice': 'male-qn-jingying'
    },
    
    {
        'name': 'male-badao',
        'language': 'chinese',
        'voice': 'male-qn-badao'
    },
    {
        'name': 'female-shaonv',
        'language': 'chinese',
        'voice': 'female-shaonv'
    },
    {
        'name': 'female-tianmei',
        'language': 'chinese',
        'voice': 'female-tianmei'
    },
    {
        'name': 'female-chengshu',
        'language': 'chinese',
        'voice': 'female-chengshu'
    },
    {
        'name': 'female-yujie',
        'language': 'chinese',
        'voice': 'female-yujie'
    },
    
]

EXPRESSION_STYLES = ["happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"]


# template = {
#    "model":"speech-2.5-hd-preview",
#    "text":"真正的危险不是计算机开始像人一样思考，而是人开始像计算机一样思考。计算机只是可以帮我们处理一些简单事务。",
#    "stream":false,
#    "language_boost":"auto",
#    "output_format":"hex",
#    "voice_setting":{
#        "voice_id":"female-chengshu",
#        "speed":1.0,
#        "vol":1.0,
#        "pitch":0,
#        "emotion":"happy"
#    },
#    "pronunciation_dict":{
#        "tone":[
#            "Omg/Oh my god"
#        ]
#    },
#       "audio_setting":{
#        "sample_rate":32000,
#        "bitrate":128000,
#        "format":"mp3",
#        "channel":1
#    },
#    "voice_modify":{
#      "pitch":0,
#      "intensity":0,
#      "timbre":0,
#      "sound_effects":"spacious_echo"
#    }
#}
