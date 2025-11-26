import requests
import json
import os
from typing import Optional, Dict, List
import hashlib
import re
import time
from .ffmeg_audio_processor import FfmpegAudioProcessor
from .llm_api import LLMApi
import config


class ElevenLabsSpeechService:
    def __init__(self, pid: str, api_key: str = None):
        """
        Initialize ElevenLabs Speech Service client
        
        Args:
            pid: Project ID
            api_key: ElevenLabs API key (optional, will use config if not provided)
        """

        # Use provided API key or fallback to config
        self.api_key = api_key or config.elevenlabs_api_key
        
        # Validate inputs
        if not self.api_key or self.api_key.startswith('YOUR_'):
            raise ValueError("请提供有效的 ElevenLabs API 密钥")
        
        self.llm_large = LLMApi(model=LLMApi.GEMINI_2_0_FLASH)
        
        self.base_url = config.elevenlabs_base_url
        self.pid = pid
        
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)
        
        # ElevenLabs 特定配置
        self.default_model_id = "eleven_multilingual_v2"  # 支持中文的模型
        self.available_voices = {}
        
        print(f"初始化 ElevenLabs 语音服务")
        print(f"API URL: {self.base_url}")
        
        # 获取可用语音列表
        self._load_available_voices()
    
    @property
    def temp_dir(self):
        """动态获取临时目录路径，确保使用最新的 pid"""
        return os.path.abspath(config.get_temp_path(self.pid))
    
    def _load_available_voices(self):
        """获取 ElevenLabs 可用的语音列表"""
        try:
            headers = {
                'xi-api-key': self.api_key
            }
            
            response = requests.get(f"{self.base_url}/voices", headers=headers)
            
            if response.status_code == 200:
                voices_data = response.json()
                for voice in voices_data.get('voices', []):
                    self.available_voices[voice['name']] = {
                        'voice_id': voice['voice_id'],
                        'name': voice['name'],
                        'description': voice.get('description', ''),
                        'category': voice.get('category', ''),
                        'labels': voice.get('labels', {})
                    }
                print(f"加载了 {len(self.available_voices)} 个可用语音")
            else:
                print(f"获取语音列表失败: {response.status_code} - {response.text}")
                # 使用默认语音
                self._set_default_voices()
                
        except Exception as e:
            print(f"加载语音列表时出错: {str(e)}")
            self._set_default_voices()
    
    def _set_default_voices(self):
        """设置默认语音（如果无法获取语音列表）"""
        self.available_voices = {
            'Rachel': {'voice_id': '21m00Tcm4TlvDq8ikWAM', 'name': 'Rachel', 'description': 'Young American Female'},
            'Drew': {'voice_id': '29vD33N1CtxCmqQRPOHJ', 'name': 'Drew', 'description': 'Young American Male'},
            'Clyde': {'voice_id': '2EiwWnXFnvU5JabPnv8n', 'name': 'Clyde', 'description': 'Middle-aged American Male'},
            'Paul': {'voice_id': '5Q0t7uMcjvnagumLfvZi', 'name': 'Paul', 'description': 'Middle-aged American Male'},
        }
    
    def get_voice_id(self, voice_name: str) -> str:
        """
        根据语音名称获取语音ID
        
        Args:
            voice_name: 语音名称
            
        Returns:
            语音ID
        """
        if voice_name in self.available_voices:
            return self.available_voices[voice_name]['voice_id']
        
        # 如果找不到精确匹配，尝试模糊匹配
        for name, voice_data in self.available_voices.items():
            if voice_name.lower() in name.lower():
                return voice_data['voice_id']
        
        # 如果都找不到，返回默认语音
        if self.available_voices:
            default_voice = list(self.available_voices.values())[0]
            print(f"警告: 未找到语音 '{voice_name}'，使用默认语音 '{default_voice['name']}'")
            return default_voice['voice_id']
        
        raise ValueError(f"找不到语音: {voice_name}")
    
    def create_voice_settings(self, mood: str = "general") -> Dict:
        """
        根据情绪创建语音设置
        
        Args:
            mood: 情绪风格
            
        Returns:
            语音设置字典
        """
        # 根据不同情绪调整语音参数
        mood_settings = {
            'general': {'stability': 0.5, 'similarity_boost': 0.75, 'style': 0.0, 'use_speaker_boost': True},
            'cheerful': {'stability': 0.3, 'similarity_boost': 0.8, 'style': 0.2, 'use_speaker_boost': True},
            'sad': {'stability': 0.7, 'similarity_boost': 0.6, 'style': 0.1, 'use_speaker_boost': False},
            'angry': {'stability': 0.2, 'similarity_boost': 0.9, 'style': 0.3, 'use_speaker_boost': True},
            'calm': {'stability': 0.8, 'similarity_boost': 0.5, 'style': 0.0, 'use_speaker_boost': False},
            'excited': {'stability': 0.2, 'similarity_boost': 0.8, 'style': 0.4, 'use_speaker_boost': True},
            'friendly': {'stability': 0.4, 'similarity_boost': 0.7, 'style': 0.1, 'use_speaker_boost': True},
            'serious': {'stability': 0.9, 'similarity_boost': 0.6, 'style': 0.0, 'use_speaker_boost': False}
        }
        
        return mood_settings.get(mood, mood_settings['general'])
    
    def split_text_into_segments(self, text: str) -> List[str]:
        """
        将文本分割成更小的段落，便于生成自然的语音
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
    
    def enhance_text_with_llm(self, text: str, voice: str, mood: str) -> str:
        """
        使用 LLM 优化文本以提高语音表现力
        
        Args:
            text: 原始文本
            voice: 语音名称
            mood: 情绪风格
            
        Returns:
            优化后的文本
        """
        # 分割文本
        text_segments = self.split_text_into_segments(text)
        
        system_prompt = config.ELEVENLABS_TEXT_ENHANCEMENT_SYSTEM_PROMPT.format(mood=mood)

        # 构建包含所有片段的用户提示
        segments_text = "\n".join([f"{i+1}. {segment}" for i, segment in enumerate(text_segments)])
        
        user_prompt = config.ELEVENLABS_TEXT_ENHANCEMENT_USER_PROMPT.format(
            segments_text=segments_text,
            voice=voice,
            mood=mood
        )

        response = self.llm_large.openai_completion(
            messages=[
                self.llm_large.create_message("system", system_prompt),
                self.llm_large.create_message("user", user_prompt)
            ],
            temperature=0.3,
            max_tokens=8000,
            top_p=0.9,
            stream=False
        )
        
        # 提取LLM返回的优化文本
        enhanced_text = self.llm_large.parse_response(response)
        
        return enhanced_text
    

    def synthesize_speech(self, text: str, voice_id: str, voice_settings: Dict, 
                         model_id: str = None) -> bytes:
        """
        使用 ElevenLabs API 合成语音
        
        Args:
            text: 要合成的文本
            voice_id: 语音ID
            voice_settings: 语音设置
            model_id: 模型ID
            
        Returns:
            音频数据（bytes）
        """
        if not model_id:
            model_id = self.default_model_id
        
        headers = {
            'Accept': 'audio/mpeg',
            'Content-Type': 'application/json',
            'xi-api-key': self.api_key
        }
        
        data = {
            'text': text,
            'model_id': model_id,
            'voice_settings': voice_settings
        }
        
        url = f"{self.base_url}/text-to-speech/{voice_id}"
        
        try:
            print(f"发送文本到 ElevenLabs: {text[:100]}...")
            
            response = requests.post(url, json=data, headers=headers, timeout=240)
            
            if response.status_code == 200:
                return response.content
            else:
                print(f"请求详情: {data}")
                print(f"响应状态: {response.status_code}")
                print(f"响应内容: {response.text}")
                raise Exception(f"ElevenLabs TTS 请求失败: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"ElevenLabs TTS 网络错误: {str(e)}")
    

    def text_to_speech(self, text: str, voice: str, mood: str = "general", 
                      output_file: str = None) -> str:
        """
        文本转语音主方法
        
        Args:
            text: 要转换的文本
            voice: 语音名称
            mood: 情绪风格
            output_file: 输出文件路径（可选）
            
        Returns:
            生成的音频文件路径
        """
        # 使用 LLM 优化文本
        enhanced_text = text #self.enhance_text_with_llm(text, voice, mood)
        print("=======================")
        print("优化后的文本:")
        print(enhanced_text)
        print("=======================")
        
        # 获取语音ID和设置
        voice_id = self.get_voice_id(voice)
        voice_settings = self.create_voice_settings(mood)
        
        # 合成语音
        audio_data = self.synthesize_speech(enhanced_text, voice_id, voice_settings)
        
        # 确定输出路径
        if not output_file:
            text_hash = self.string_to_code(f"{text}_{voice}_{mood}")
            audio_path = os.path.abspath(f"{self.temp_dir}/{text_hash}.mp3")
        else:
            audio_path = output_file
        
        # 保存音频文件
        with open(audio_path, 'wb') as f:
            f.write(audio_data)
        print(f"音频已保存至: {audio_path}")
        return audio_path

    
    def string_to_code(self, input_string: str) -> str:
        """
        将字符串转换为安全的文件名代码
        
        Args:
            input_string: 输入字符串
            
        Returns:
            安全的文件名代码
        """
        # 生成 MD5 哈希
        input_string = str(input_string)  # 确保是字符串
        hash_object = hashlib.md5(input_string.encode('utf-8'))
        
        # 获取十六进制表示并截断到所需长度
        code = str(hash_object.hexdigest())
        code = re.sub(r'[^a-zA-Z0-9_-]', '', code)
        
        return code
    

    def generate_voice_from_json(self, output_path: str, voice_data: List[Dict], delay: int = 0, wait: int = 0) -> str:
        half_second_path = os.path.abspath(f"{config.BASE_MEDIA_PATH}/effect/half.wav")
        
        # 生成唯一标识符
        json_string = json.dumps(voice_data, ensure_ascii=False)
        
        audio_path_list = []
        
        # 添加开始延迟
        if delay > 0:
            for i in range(delay):
                audio_path_list.append(half_second_path)
        
        # 处理每个语音片段
        for item in voice_data:
            voice = item["voice"]
            mood = item["mood"]
            content = item["content"]
            
            print(f"生成语音片段: {content[:50]}...")
            
            # 生成语音
            segment_audio = self.text_to_speech(content, voice, mood)
            audio_path_list.append(segment_audio)
        
        # 添加结束等待
        if wait > 0:
            for i in range(wait):
                audio_path_list.append(half_second_path)
        
        # 合并所有音频
        self.ffmpeg_audio_processor.concat_audios(output_path, audio_path_list)
    

    def make_transition_conversation(self, conversation_prompt, prev_story_section, next_story_section, system_prompt_const, user_prompt_const) :
        """
        2 speakers :   1 is m (male) /  2 is f (female)
        have comment converstation to about a story, in the middle of the story (between prev_story_section & next_story_section)

        use self.llm_large, to generate a conversation between these 2, express content is [current_content]
        this conversation is following the prev_story_section, and will connect the next_story_section 
        
        the conversation should be natural (connect prev_story_section and next_story_section): 
       
        and the output should be json array like:
        [
            {
                "voice": "m",
                "speaker_name": "主持人A",
                "mood": "cheerful",
                "content": "大家好，我是 佳伟, 欢迎来到我们的 聊斋新语 节目"
            },
            {
                "voice": "f",
                "speaker_name": "主持人B",
                "mood": "cheerful",
                "content": "我是 莹莹, 让我们一起来说说新的聊斋故事吧？记得点赞关注哦！"
            }
        ]

        self.llm_large has method 'extract_json_from_response', you can use it to extract the json array from the response
        """
        names = conversation_prompt["speaker_name"].split("|")
        name1 = names[0]
        name2 = names[1]
        voices = conversation_prompt["voice"].split("|")
        voice1 = voices[0]
        voice2 = voices[1]
        sex1 = "male" if voice1 == "m" else "female"
        sex2 = "male" if voice2 == "m" else "female"

        system_prompt = system_prompt_const.format(
            sex1=sex1,
            sex2=sex2,
            name1=name1,
            name2=name2,
            voice1=voice1,
            voice2=voice2
        )


        # 构建上下文信息
        prevv_context_info = ""
        if prev_story_section:
            #sex = "male" if prev_story_section['voice'] == "m" else "female"
            prevv_context_info = f"Just watched/listened story section ending with : ... {prev_story_section['content']}\n"
        
        next_context_info = ""
        if next_story_section:
            #sex = "male" if next_story_section['voice'] == "m" else "female"
            next_context_info = f"And will continue watched/listened Next story section, starting with :  {next_story_section['content']}\n"

        user_prompt = user_prompt_const.format(
            conversation_prompt=conversation_prompt["content"],
            prevv_context_info=prevv_context_info,
            next_context_info=next_context_info
        )

        try:
            response = self.llm_large.openai_completion(
                messages=[
                    self.llm_large.create_message("system", system_prompt),
                    self.llm_large.create_message("user", user_prompt)
                ],
                temperature=0.7,
                max_tokens=2000,
                top_p=0.9,
                stream=False
            )
            
            # 获取完整响应文本
            response_text = self.llm_large.parse_response(response)
            
            # 提取JSON数组
            conversation_json = self.llm_large.parse_json_response(response_text)
            
            if not conversation_json:
                raise ValueError("无法从LLM响应中提取有效的JSON格式")
            
            print(f"生成的对话片段：")
            
            return conversation_json
            
        except Exception as e:
            print(f"生成对话时出错: {str(e)}")
            return None


    def get_available_voices(self) -> Dict:
        """
        获取可用语音列表
        
        Returns:
            可用语音字典
        """
        return self.available_voices
    

    def print_available_voices(self):
        """打印所有可用语音"""
        print("可用的 ElevenLabs 语音:")
        print("-" * 50)
        for name, voice_data in self.available_voices.items():
            print(f"名称: {name}")
            print(f"ID: {voice_data['voice_id']}")
            print(f"描述: {voice_data.get('description', '无描述')}")
            print(f"类别: {voice_data.get('category', '未知')}")
            print("-" * 30)


