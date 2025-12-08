#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LLM API 测试程序
测试 utility.llm_api.py 中的所有模型和功能
"""

import os
import time
import json
from typing import Dict, List, Any
from utility.llm_api import LLMApi

# 设置环境变量（如果需要）
# os.environ["OPENAI_API_KEY"] = "你的OpenAI API Key"
# os.environ["GOOGLE_API_KEY"] = "你的Google API Key"

class LLMApiTester:
    """LLM API 测试类"""
    
    def __init__(self):
        """初始化测试器"""
        self.test_results = {}
        self.test_message = [
            {"role": "user", "content": "你好，请简单介绍一下你自己，并回答：1+1等于多少？"}
        ]
        self.json_test_message = [
            {"role": "user", "content": "请以JSON格式返回你的信息，包含name（名字）、version（版本）、features（特性列表）三个字段。"}
        ]
    
    def print_separator(self, title: str):
        """打印分隔线"""
        print("\n" + "="*60)
        print(f" {title} ")
        print("="*60)
    
    def print_test_header(self, test_name: str):
        """打印测试头部"""
        print(f"\n🧪 测试：{test_name}")
        print("-" * 40)
    
    def test_model(self, model_name: str) -> Dict[str, Any]:
        """测试单个模型"""
        self.print_test_header(f"模型 {model_name}")
        
        test_result = {
            "model": model_name,
            "basic_chat": {"success": False, "response": "", "error": ""},
            "json_response": {"success": False, "response": "", "error": ""},
            "stream_response": {"success": False, "response": "", "error": ""},
            "response_time": 0
        }
        
        try:
            # 初始化API客户端
            api = LLMApi(model=model_name)
            print(f"✅ 成功初始化模型：{model_name}")
            
            # 测试1：基础聊天
            print("\n📝 测试基础聊天功能...")
            start_time = time.time()
            
            response_text = api.generate_text(self.test_message, "")
            test_result["response_time"] = time.time() - start_time
            test_result["basic_chat"]["success"] = True
            test_result["basic_chat"]["response"] = response_text[:200] + "..." if len(response_text) > 200 else response_text
            
            print(f"✅ 基础聊天测试成功")
            print(f"📄 响应内容：{test_result['basic_chat']['response']}")
            print(f"⏱️ 响应时间：{test_result['response_time']:.2f}秒")
            
        except Exception as e:
            test_result["basic_chat"]["error"] = str(e)
            print(f"❌ 基础聊天测试失败：{e}")
        
        # 测试2：JSON响应
        try:
            print("\n🔄 测试JSON响应功能...")
            

            
            json_response = self.call_with_json_response(
                messages=self.json_test_message,
                temperature=0.3,
                max_tokens=300
            )
            
            test_result["json_response"]["success"] = True
            test_result["json_response"]["response"] = json_response
            
            print(f"✅ JSON响应测试成功")
            print(f"📄 JSON内容：{json.dumps(json_response, ensure_ascii=False, indent=2)}")
            
        except Exception as e:
            test_result["json_response"]["error"] = str(e)
            print(f"❌ JSON响应测试失败：{e}")
        
        return test_result
    

    def call_with_json_response(self, 
                               messages: List[Dict[str, str]], 
                               extract_json: bool = True,
                               expect_list: bool = False,
                               allow_dict_to_list: bool = True,
                               output_file_path: Optional[str] = None,
                               **kwargs) -> Union[Dict, List, str]:
        response = self.create_completion(messages, **kwargs)
        response_text = self.parse_response(response)
        print("------------ text ------------")
        print(response_text)
        print("--------------------------------")
        if extract_json:
            try:
                json_data = self.parse_and_save_json(
                    response_content=response_text,
                    output_file_path=output_file_path,
                    expect_list=expect_list,
                    allow_dict_to_list=allow_dict_to_list
                )
                print("--------enhanced json parsing------------")
                print(json_data)
                print("--------------------------------")
                return json_data
            except Exception as e:
                print(f"Enhanced JSON parsing failed: {e}")
                print("Falling back to basic extraction...")
                # Fallback to old method if enhanced parsing fails
                json_data = self.extract_json_from_response(response_text)
                print("--------fallback json extraction------------")
                print(json_data)
                print("--------------------------------")
                return json_data if json_data is not None else response_text
        else:
            return response_text

    
    def test_all_models(self):
        """测试所有可用模型"""
        self.print_separator("开始测试所有LLM模型")
        
        model_name = LLMApi.GPT_OSS
        api = LLMApi(model_name)
        
        try:
            result = self.test_model(model_name)
            self.test_results[model_name] = result
        except Exception as e:
            print(f"❌ 模型 {model_name} 测试过程中发生严重错误：{e}")
            self.test_results[model_name] = {
                "model": model_name,
                "basic_chat": {"success": False, "error": str(e)},
                "json_response": {"success": False, "error": str(e)},
                "stream_response": {"success": False, "error": str(e)},
                "response_time": 0
            }


def main():
    """主函数"""
    print("🚀 开始 LLM API 测试程序")
    print("📝 测试内容：utility.llm_api.py 中的所有模型和功能")
    
    tester = LLMApiTester()
    
    try:
        # 测试所有模型
        tester.test_all_models()
        
        # 测试工具函数
        tester.test_utility_functions()
        
        # 生成报告
        tester.generate_report()
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误：{e}")
    
    print("\n🏁 测试完成！")

if __name__ == "__main__":
    main()
