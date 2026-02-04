import requests
import json
import os
from typing import Optional, Dict, List
import hashlib
import re
import time
from .ffmpeg_audio_processor import FfmpegAudioProcessor
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
        
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)
        print(f"TTS URL: {self.tts_url}")


    def create_ssml(self, text: str, voice: str, actions: str, language: str, speed: float = 1.0, pitch: int = 0, vol: float = 1.0) -> str:
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
        if language == "chinese":
            escaped_text = escaped_text.replace(" ", "<#0.5#>")

        actions = actions.lower()
        mood = None
        for style in EXPRESSION_STYLES:
            if style in actions:
                mood = style
                break
        if not mood:
            mood = "auto"

        ssml = f"""
{{
    "model":"speech-2.8-hd",
    "text":"{escaped_text}",
    "stream":false,
    "language_boost":"auto",
    "output_format":"hex",
    "voice_setting":{{
        "voice_id":"{voice}",
        "speed":{speed},
        "vol":{vol},
        "pitch":{pitch}
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
        audio_path = f"{config.get_project_path(self.pid)}/temp/{self.string_to_code(ssml_text)}.mp3"
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
            if voice["name"].lower() in speaker.lower():
                return voice["voice"]
            if voice["voice"].lower() in speaker.lower():
                return voice["voice"]
        return "male-qn-qingse"

# man_mature/woman_mature/man_young/woman_young/man_old/woman_old/teen_boy/teen_girl/boy/girl
# Common Chinese voices and moods
VOICES = [
    {
        'name': 'woman_mature',
        'language': 'chinese',
        'voice': 'moss_audio_9edd8a0f-9743-11f0-b659-7a84e7f91f54' #'Chinese (Mandarin)_Kind-hearted_Antie' # female-yujie   female-chengshu   presenter_female
    },
    {
        'name': 'man_mature',
        'language': 'chinese',
        'voice': 'Chinese (Mandarin)_Stubborn_Friend' #moss_audio_9c223de9-7ce1-11f0-9b9f-463feaa3106a  moss_audio_ce44fc67-7ce3-11f0-8de5-96e35d26fb85    'male-qn-jingying-jingpin' # male-qn-jingying  presenter_male
    },
    {
        'name': 'man_mature',
        'language': 'english',
        'voice': 'moss_audio_b37dc4b3-9691-11f0-aeab-4aec103046b8' #'Chinese (Mandarin)_Stubborn_Friend' #moss_audio_9c223de9-7ce1-11f0-9b9f-463feaa3106a  moss_audio_ce44fc67-7ce3-11f0-8de5-96e35d26fb85    'male-qn-jingying-jingpin' # male-qn-jingying  presenter_male
    },
    {
        'name': 'woman_young',
        'language': 'chinese',
        'voice': 'Chinese (Mandarin)_Warm_Bestie' # female-shaonv  female-tianmei-jingpin
    },
    {
        'name': 'man_young',
        'language': 'chinese',
        'voice': 'moss_audio_ce44fc67-7ce3-11f0-8de5-96e35d26fb85'
    },

    {
        'name': 'girl',
        'language': 'chinese',
        'voice': 'Chinese (Mandarin)_Warm_Girl' #Chinese (Mandarin)_Cute_Spirit' 'BritishChild_female_1_v1'
    },
    {
        'name': 'boy',
        'language': 'chinese',
        'voice': 'Chinese (Mandarin)_Straightforward_Boy'
    },

    {
        'name': 'teen_boy',
        'language': 'chinese',
        'voice': 'Chinese (Mandarin)_Southern_man_young'  
    },
    {
        'name': 'teen_girl',
        'language': 'chinese',
        'voice': 'moss_audio_ad5baf92-735f-11f0-8263-fe5a2fe98ec8'  #'Chinese (Mandarin)_Warm_Girl'
    },

    {
        'name': 'man_old',
        'language': 'chinese',
        'voice': 'Chinese (Mandarin)_Humorous_Elder'
    },
    {
        'name': 'woman_old',
        'language': 'chinese',
        'voice': 'Chinese (Mandarin)_Kind-hearted_Elder'
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
    }
]



EXPRESSION_STYLES = ["happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"]




MOODS_AZURE = [
    'general', 'chat', 'hopeful', 'sad', 'affectionate', 'empathetic', 'disgruntled', 'gentle', 'cheerful', 'fearful', 'angry', 'calm', 
    'excited', 'unfriendly', 'friendly', 'serious', 'dramatic', 'whisper', 'customerservice', 'narration-casual'
] 


#   https://learn.microsoft.com/nb-no/azure/ai-services/speech-service/language-support?tabs=tts#voice-styles-and-roles
VOICES_11_LAB = [
    "zh-CN-Yunyi:DragonHDFlashLatestNeural",
    "zh-CN-Yunfan:DragonHDLatestNeural",
    "zh-CN-Yunxiao:DragonHDFlashLatestNeural",
    "zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural",
    "zh-CN-Xiaochen:DragonHDFlashLatestNeural",
    "zh-CN-XiaoqiuNeural",
    "tw_m",
    "tw_f"
]




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
