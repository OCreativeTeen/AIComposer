import json
import os
import time
from openai import OpenAI
from pathlib import Path
from .llm_api import LLMApi
import config
from typing import List, Dict, Optional, Union, Any, Generator
import re


class TalkSummarizer:
    
    def __init__(self, pid, language, model: str = LLMApi.GEMINI_2_0_FLASH, model_2: str = LLMApi.GPT_OSS, model_small: str = LLMApi.GPT_4O_MINI):
        """
        初始化谈话摘要器
        
        Args:
            api_key: OpenAI API密钥
            model: 使用的GPT模型
        """ 
        self.pid = pid
        self.language = language

        self.llm = LLMApi(model=model)
        self.llm_2 = LLMApi(model=model_2)
        self.llm_small = LLMApi(model=model_small)
        
        self.short_conversation_path = f"{config.get_project_path(pid)}/{pid}_{language}_short_1.json"
        self.short_conversation_path_2 = f"{config.get_project_path(pid)}/{pid}_{language}_short_2.json"


    #            content=config.fetch_script_content(self.pid, self.language),
    #            description=config.fetch_text_content(self.pid, self.language),
    def generate_json_summary(self, system_prompt, user_prompt, output_path=None, expect_list=True, model_number=1) -> Union[Dict, List]:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.llm.openai_completion(
                    messages= [
                        self.llm.create_message("system", system_prompt),
                        self.llm.create_message("user", user_prompt)
                    ],
                    temperature=0.7,
                    max_tokens=65530
                )
                
                content = self.llm.parse_response(response)
                
                if content:
                    # Step 1: Clean the response content
                    content_string = content.strip()
                    content_string = content_string.replace("```json", "").replace("```", "")
                    # 方法1：使用正则表达式一次性处理所有换行符
                    content_string = re.sub(r'\s+', ' ', content_string)  # 将所有连续空白字符替换为单个空格

                    # 方法2：处理所有类型的换行符
                    content_string = content_string.replace("\r\n", " ")  # 先处理Windows换行符
                    content_string = content_string.replace("\n", " ")    # 再处理Unix换行符
                    content_string = content_string.replace("\r", " ")    # 最后处理Mac换行符

                    # 方法3：使用字符串的splitlines()和join()方法
                    content_string = " ".join(content_string.splitlines())
                    # Step 2: Save cleaned content to file if path provided
                    if output_path:
                        try:
                            with open(output_path, "w", encoding="utf-8") as f:
                                f.write(content_string)
                        except Exception as e:
                            print(f"警告：无法保存JSON文件到 {output_path}: {e}")

                    return self.parse_json(
                        content_string=content_string,
                        expect_list=expect_list
                    )

            except Exception as e:
                print(f"生成JSON摘要失败: {str(e)}")

            if attempt < max_retries - 1:  # 不是最后一次尝试
                print(f"等待 7 秒后重试...")
                time.sleep(7)
            else:
                print("所有重试尝试已用尽")
                return []


    def parse_json(self, content_string: str, expect_list: bool = False) -> Union[Dict, List]:
        # Step 3: Try direct JSON parsing first
        try:
            parsed_result = json.loads(content_string)
            # Type validation and conversion
            if expect_list:
                if isinstance(parsed_result, list):
                    return parsed_result
                elif isinstance(parsed_result, dict):
                    print(f"警告：LLM返回了 {type(parsed_result)} 而不是期望的列表格式，自动转换为列表")
                    return [parsed_result]
                else:
                    print(f"警告：LLM返回了 {type(parsed_result)} 而不是期望的JSON格式")
                    return []
            else:
                return parsed_result
                
        except json.JSONDecodeError:
            try:
                parsed_result = self.llm.parse_json_response(content_string)
                # Type validation and conversion for parsed result
                if expect_list:
                    if isinstance(parsed_result, list):
                        return parsed_result
                    elif isinstance(parsed_result, dict):
                        print(f"警告：解析的JSON是 {type(parsed_result)} 而不是期望的列表格式，自动转换为列表")
                        return [parsed_result]
                    else:
                        print(f"警告：解析的JSON是 {type(parsed_result)} 而不是期望的JSON格式")
                        return []
                else:
                    return parsed_result
                    
            except (ValueError, Exception):
                raise Exception("无法从响应中提取有效的JSON")


    def generate_text_summary(self, system_prompt, user_prompt, model_number) -> str:
        messages=[
            self.llm.create_message("system", system_prompt),
            self.llm.create_message("user", user_prompt)
        ]

        try:
            if model_number == 1:
                response = self.llm.openai_completion(
                messages=messages,
                temperature=0.1,
                max_tokens=8000,
                top_p=0.9,
                stream=False
                )
            elif model_number == 2:
                response = self.llm_2.openai_completion(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=8000,
                    top_p=0.9,
                    stream=False
                )
            else:
                response = self.llm_small.openai_completion(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=8000,
                    top_p=0.9,
                    stream=False
                )

            description = self.llm.parse_response(response)
            if not description:
                print("Summary API返回了空内容")
                return ""
               
            return description
        except Exception as e:
            return ""



    def generate_simple_text_summary(self,user_prompt, model_number) -> str:
        try:
            messages = [
                self.llm.create_message("user", user_prompt)
            ]

            if model_number == 1:
                response = self.llm.openai_completion(
                messages=messages,
                temperature=0.1,
                max_tokens=8000,
                top_p=0.9,
                stream=False
                )
            elif model_number == 2:
                response = self.llm_2.openai_completion(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=8000,
                    top_p=0.9,
                    stream=False
                )
            else:
                response = self.llm_small.openai_completion(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=8000,
                    top_p=0.9,
                    stream=False
                )

            description = self.llm.parse_response(response)
            if not description:
                print("Summary API返回了空内容")
                return ""
               
            return description
        except Exception as e:
            return ""

    

if __name__ == "__main__":
    #file_path = "data/paragraphs.json"
    #with open(file_path, 'w', encoding='utf-8') as f:
    #    json.dump([asdict(p) for p in paragraphs], f, ensure_ascii=False, indent=2)
    pass
