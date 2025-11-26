import json
import re
from typing import List, Dict, Optional, Union, Any, Generator
from openai import OpenAI
import requests
import os
import httpx


class LLMApi:
    """
    LLM API 基础类
    
    提供底层的 API 调用、响应解析和 JSON 处理功能。
    支持 OpenAI 兼容的消息格式。
    
    """
    
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_OSS = "gpt-oss:20b"
    GEMINI_2_0_FLASH = "gemini-2.0-flash"  # 免费
    #GEMINI_2_0_FLASH = "gpt-4o-mini"
    GEMINI_2_5_FLASH = "gemini-2.5-pro-preview-06-05"  # 付费\
    GEMINI_2_5_FLASH_IMAGE = "gemini-2.5-flash-image-preview"  # 付费
    
    models = {
        GPT_OSS : {
            "url": "http://10.0.0.238:11434/v1", 
            "type": "ollama"
        },
        GPT_4O_MINI : {
            "url": "https://api.openai.com/v1", 
            "type": "openai"
        },
        GEMINI_2_0_FLASH : {
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/", 
            "type": "gemini"
        },
        GEMINI_2_5_FLASH : {
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/", 
            "type": "gemini"
        },
        GEMINI_2_5_FLASH_IMAGE : {
            "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent", 
            "type": "gemini"
        }
    }


    def __init__(self, model):
        """
        初始化 LLM API 客户端
        
        Args:
            model (str): 要使用的模型名称
        """
        self.model = model
        self.model_type = self.models[model]["type"]
        self.base_url = self.models[model]["url"]

        # 创建带超时的 httpx 客户端
        timeout = httpx.Timeout(90.0)  # 90秒超时
        http_client = httpx.Client(timeout=timeout)

        if self.model_type == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
            self.client = OpenAI(
                api_key=api_key,
                base_url=self.base_url,
                http_client=http_client
            )
        elif self.model_type == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY", "")
            self.client = OpenAI(
                api_key=api_key,
                base_url=self.base_url,
                http_client=http_client
            )
        elif self.model_type == "ollama":
            self.client = OpenAI(
                api_key="ollama",
                base_url=self.base_url,
                http_client=http_client
            )
    
   
    def set_model(self, model: str) -> None:
        self.model = model
        self.model_type = self.models[model]["type"]
        self.base_url = self.models[model]["url"]


    def openai_completion(self, 
                         messages: List[Dict[str, str]], 
                         model: Optional[str] = None,
                         temperature: float = 0.7,
                         max_tokens: Optional[int] = None,
                         top_p: float = 0.95,
                         stream: bool = False,
                         reasoning_effort: Optional[str] = None,
                         **kwargs) -> Any:
        use_model = model if model is not None else self.model
        current_model_type = self.models.get(use_model, {}).get("type", "unknown")
        
        # 准备请求参数
        request_params = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
            **kwargs
        }
        
        # 添加可选参数
        if max_tokens:
            request_params["max_tokens"] = max_tokens
        
        # reasoning_effort 只对 Gemini 模型有效
        if reasoning_effort and current_model_type == "gemini":
            request_params["reasoning_effort"] = reasoning_effort
        
        try:
            # 发送请求
            response = self.client.chat.completions.create(**request_params)
            return response
        except Exception as e:
            # 根据模型类型提供更准确的错误信息
            model_type_name = {
                "openai": "OpenAI",
                "gemini": "Gemini", 
                "ollama": "Ollama"
            }.get(current_model_type, "LLM")
            
            raise Exception(f"调用 {model_type_name} API 时发生错误: {str(e)}")


    def parse_response(self, response: Any, stream: bool = False) -> Union[str, Generator]:
        if stream:
            return self._parse_stream_response(response)
        else:
            return self._parse_normal_response(response)
    

    def _parse_normal_response(self, response: Any) -> str:
        try:
            return response.choices[0].message.content
        except (AttributeError, IndexError) as e:
            raise Exception(f"解析响应时发生错误: {str(e)}")
    

    def _parse_stream_response(self, response: Any) -> Generator[str, None, None]:
        try:
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except (AttributeError, IndexError) as e:
            raise Exception(f"解析流式响应时发生错误: {str(e)}")
    

    def parse_json_response(self, response_text: str) -> Union[Dict, List, Any]:
        def clean_json_string(text: str) -> str:
            """清理JSON字符串"""
            # 移除控制字符
            text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
            # 移除首尾的引号
            text = text.strip("'\"")
            # 修复错误的双引号
            text = re.sub(r'"{2,}(\w+)"{1,}', r'"\1"', text)
            # 修复键值对中的引号问题
            text = re.sub(r'([{,]\s*)"([^"]+)"\s*:\s*([^",\{\[\]\}]+)([,\}\]])', r'\1"\2":"\3"\4', text)
            # 修复没有引号的值
            text = re.sub(r':\s*([^",\{\[\]\}\s][^",\{\[\]\}]*[^",\{\[\]\}\s])([,\}\]])', r':"\1"\2', text)
            # 修复多余的逗号
            text = re.sub(r',(\s*[}\]])', r'\1', text)
            # 移除多余的转义字符
            text = text.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ')
            return text

        try:
            # 移除<think>标签及其内容
            response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
            
            # 清理响应文本
            response_text = clean_json_string(response_text)
            
            # 首先尝试从 ```json ... ``` 代码块中提取JSON
            json_pattern = r'```json\s*(.*?)\s*```'
            matches = re.findall(json_pattern, response_text, re.DOTALL)
            if matches:
                # 取第一个匹配的JSON内容
                json_content = clean_json_string(matches[0].strip())
                return json.loads(json_content)
            
            # 尝试直接解析整个响应
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                # 如果直接解析失败，尝试提取JSON数组或对象
                json_pattern = r'(\[\s*\{.*\}\s*\]|\{\s*".*"\s*:\s*.*\s*\})'
                matches = re.findall(json_pattern, response_text, re.DOTALL)
                if matches:
                    # 清理提取的JSON字符串
                    json_str = clean_json_string(matches[0])
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        # 如果还是失败，尝试更激进的修复
                        # 移除所有空白字符后重试
                        json_str = re.sub(r'\s+', '', json_str)
                        return json.loads(json_str)
                
                raise ValueError("无法从响应中提取有效的JSON内容")

        except json.JSONDecodeError as e:
            # 如果解析失败，打印出处理后的JSON字符串以便调试
            print(f"JSON解析失败，处理后的字符串：\n{response_text}")
            raise ValueError(f"JSON解析失败: {str(e)}")
    


    def get_json_element(self, json_data: Union[Dict, List], 
                        path: str, 
                        default: Any = None) -> Any:
        """
        从JSON数据中获取指定路径的元素
        """
        try:
            current = json_data
            
            # 分割路径
            path_parts = path.split('.')
            
            for part in path_parts:
                if isinstance(current, dict):
                    current = current[part]
                elif isinstance(current, list):
                    # 尝试将路径部分转换为索引
                    try:
                        index = int(part)
                        current = current[index]
                    except (ValueError, IndexError):
                        return default
                else:
                    return default
            
            return current
            
        except (KeyError, TypeError, IndexError):
            return default
    
    

    def create_message(self, role: str, content: str) -> Dict[str, str]:
        return {"role": role, "content": content}

