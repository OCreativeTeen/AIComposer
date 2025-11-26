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


class AzureSpeechService:
    def __init__(self, pid: str, subscription_key: str = None, region: str = None):
        """
        Initialize Azure Speech Service client
        
        Args:
            pid: Project ID
            subscription_key: Azure subscription key (optional, will use config if not provided)
            region: Azure region (optional, will use config if not provided)
        """
        # Use provided values or fallback to config
        self.subscription_key = subscription_key or config.azure_subscription_key
        self.region = region or config.azure_region
        
        # Validate inputs
        if not self.subscription_key or self.subscription_key.startswith('YOUR_'):
            raise ValueError("请提供有效的 Azure 订阅密钥")
        if not self.region or self.region.startswith('YOUR_'):
            raise ValueError("请提供有效的 Azure 区域")
        
        self.llm_large = LLMApi(model=LLMApi.GEMINI_2_0_FLASH)
        
        self.subscription_key = subscription_key
        self.region = region
        self.pid = pid
        
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)

        self.token_url = f"https://{self.region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
        self.tts_url = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        self.access_token = None

        print(f"Initialized Azure Speech Service - Region: {self.region}")
        print(f"Token URL: {self.token_url}")
        print(f"TTS URL: {self.tts_url}")
    
    @property
    def temp_dir(self):
        """动态获取临时目录路径，确保使用最新的 pid"""
        return os.path.abspath(config.get_temp_path(self.pid))

    def get_access_token(self) -> str:
        """Get access token for Azure Speech Service"""
        headers = {
            'Ocp-Apim-Subscription-Key': self.subscription_key
        }
        
        response = requests.post(self.token_url, headers=headers)
        
        if response.status_code == 200:
            self.access_token = response.text
            return self.access_token
        else:
            raise Exception(f"Failed to get access token: {response.status_code} - {response.text}")
    

    def create_ssml(self, text: str, voice: str, mood: str = "general") -> str:
        """
        Create SSML XML from template
        
        Args:
            text: Text to synthesize
            voice: Voice name (e.g., 'zh-CN-XiaoxiaoNeural')
            mood: Expression style (e.g., 'cheerful', 'sad', 'angry', 'friendly')
        
        Returns:
            SSML XML string
        """
        # Escape special XML characters in text
        import html
        escaped_text = html.escape(text)
        
        # Validate voice name format
        if not voice or 'Neural' not in voice:
            print(f"Warning: Voice '{voice}' might not be a valid neural voice")
        
        # Create clean SSML without extra whitespace
        # ssml_template = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="zh-CN"><voice name="{voice}"><mstts:express-as style="{mood}">{escaped_text}</mstts:express-as></voice></speak>'
        ssml_template = self.call_llm_to_ssml(text, voice, mood)
        print("=======================")
        print(ssml_template)
        print("=======================")

        return ssml_template
    

    def split_text_into_segments(self, text: str) -> list:
        """
        将文本分割成更小的段落，便于生成自然的SSML
        """
        # 按句号、感叹号、问号等分割
        segments = re.split(r'([。！？；\n])', text)
        
        # 重新组合，保留标点符号
        result = []
        current_segment = ""
        
        for i in range(len(segments)):
            if i % 2 == 0:  # 文本部分
                current_segment += segments[i]
            else:  # 标点符号
                current_segment += segments[i]
                if current_segment.strip():
                    result.append(current_segment.strip())
                current_segment = ""
        
        # 处理最后一个片段
        if current_segment.strip():
            result.append(current_segment.strip())
        
        # 过滤掉空字符串
        result = [seg for seg in result if seg.strip()]
        
        return result

    # <prosody rate="{speed}">
    def make_ssml(self, break_time: str, voice_data: List[Dict]) -> str:
        sections = []
        for item in voice_data:
            pitch = item.get("pitch", "default")
            speed = item.get("speed", "default")

            speaker = item.get("speaker", "narrator-male")
            speaker = speaker.replace("_", "-").replace(":", "-").replace(" ", "-")
            match speaker:
                case "narrator-male":
                    voice = "zh-CN-Yunyi:DragonHDFlashLatestNeural"
                case "narrator-female":
                    voice = "zh-CN-Xiaochen:DragonHDFlashLatestNeural" #"zh-CN-XiaoqiuNeural"
                case "female-actor-1":
                    voice = "zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural"
                case "female-actor-2":
                    voice = "zh-CN-Xiaochen:DragonHDFlashLatestNeural"
                case "female-actor-3":
                    voice = "zh-CN-XiaorouNeural"
                case "male-actor-1":
                    voice = "zh-CN-Yunxiao:DragonHDFlashLatestNeural"
                case "male-actor-2":
                    voice = "zh-CN-Yunyi:DragonHDFlashLatestNeural"
                case "male-actor-3":
                    voice = "zh-CN-YunjianNeural"

            sections.append(f"""
                            <voice name="{voice}">
                                <mstts:express-as style="{item["mood"]}" styledegree="2.0">
                                    <prosody rate="{speed}" pitch="{pitch}">
                                        {item["content"]}
                                    </prosody>
                                </mstts:express-as>
                            </voice>
                            """)

        all_sections = f'\n\n'.join(sections) #  <break time="{break_time}"/> 

        ssml = f"""
            <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="zh-CN">
                {all_sections}
            </speak>
            """
        return ssml


    def synthesize_speech(self, ssml_text: str, output_format: str = "audio-16khz-128kbitrate-mono-mp3") -> bytes:
        # if not self.access_token:
        self.get_access_token()
        
        # Clean and validate SSML
        ssml_text = ssml_text.strip()
        
        # Debug: Print SSML being sent
        print(f"Sending SSML: {ssml_text}")
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/ssml+xml',
            'X-Microsoft-OutputFormat': output_format,
            'User-Agent': 'PythonTTSClient'
        }
        
        try:
            response = requests.post(self.tts_url, headers=headers, data=ssml_text.encode('utf-8'), timeout=240)
            
            if response.status_code == 200:
                return response.content
            elif response.status_code == 401:
                # Token might be expired, refresh and retry
                print("Token expired, refreshing...")
                self.get_access_token()
                headers['Authorization'] = f'Bearer {self.access_token}'
                response = requests.post(self.tts_url, headers=headers, data=ssml_text.encode('utf-8'), timeout=240)
                
                if response.status_code == 200:
                    return response.content
                else:
                    raise Exception(f"TTS request failed after token refresh: {response.status_code} - {response.text}")
            else:
                # Print detailed error information
                print(f"Request headers: {headers}")
                print(f"Request body: {ssml_text}")
                print(f"Response status: {response.status_code}")
                print(f"Response headers: {response.headers}")
                print(f"Response text: {response.text}")
                raise Exception(f"TTS request failed: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error during TTS request: {str(e)}")
    

    def validate_ssml(self, ssml_text: str) -> bool:
        """
        Validate SSML format
        
        Args:
            ssml_text: SSML XML string to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(ssml_text)
            return True
        except ET.ParseError as e:
            print(f"SSML validation error: {e}")
            return False
        

    def text_to_speech(self, ssml: str):
        audio_path = os.path.abspath(f"{self.temp_dir}/{self.string_to_code(ssml)}.mp3")
        if os.path.exists(audio_path):
            return audio_path
        # Synthesize speech
        audio_data = self.synthesize_speech(ssml)
        # Save to file if specified
        with open(audio_path, 'wb') as f:
            f.write(audio_data)

        return audio_path


    def string_to_code(self, input_string):
        # Generate MD5 hash of the input string
        input_string = str(input_string)  # Ensure it's a string
        hash_object = hashlib.md5(input_string.encode('utf-8'))

        # Get hexadecimal representation and truncate to desired length
        code = str(hash_object.hexdigest())
        code = re.sub(r'[^a-zA-Z0-9_-]', '', code)
        # Ensure the code is filename-safe by removing/ replacing unsafe characters
        return code



# Factory function to create service with validation
def create_azure_speech_service(pid: str, subscription_key: str = None, region: str = None) -> AzureSpeechService:
    """
    Factory function to create AzureSpeechService with validation
    
    Args:
        pid: Project ID
        subscription_key: Azure subscription key (optional, will use config if not provided)
        region: Azure region (optional, will use config if not provided)
        
    Returns:
        AzureSpeechService instance
        
    Raises:
        ValueError: If parameters are invalid
    """
    if not pid or len(pid) < 1:
        raise ValueError("Invalid project ID provided")
    
    if not subscription_key or len(subscription_key) < 10:
        raise ValueError("Invalid subscription key provided")
    
    valid_regions = [
        'eastus', 'eastus2', 'westus', 'westus2', 'westus3', 'centralus', 
        'northcentralus', 'southcentralus', 'westcentralus',
        'canadacentral', 'brazilsouth', 'northeurope', 'westeurope', 
        'uksouth', 'ukwest', 'francecentral', 'germanywestcentral',
        'switzerlandnorth', 'norwayeast', 'southafricanorth',
        'centralindia', 'southindia', 'eastasia', 'southeastasia',
        'japaneast', 'japanwest', 'koreacentral', 'australiaeast'
    ]
    
    if region and region not in valid_regions:
        print(f"Warning: '{region}' might not be a valid Azure region.")
        print(f"Valid regions include: {', '.join(valid_regions[:10])}...")
    
    return AzureSpeechService(pid, subscription_key, region)


# Common Chinese voices and moods
CHINESE_VOICES = {
    'xiaoxiao': 'zh-CN-XiaoxiaoNeural',  # Female, general
    'yunxi': 'zh-CN-YunxiNeural',        # Male, general
    'xiaoyi': 'zh-CN-XiaoyiNeural',      # Female, adult
    'yunjian': 'zh-CN-YunjianNeural',    # Male, elderly
    'xiaomo': 'zh-CN-XiaomoNeural',      # Female, young adult
}

EXPRESSION_STYLES = [
    'general', 'cheerful', 'sad', 'angry', 'fearful', 
    'disgruntled', 'serious', 'affectionate', 'gentle', 
    'embarrassed', 'calm', 'friendly'
]
