import json
import re
from typing import List, Dict, Optional, Union, Any, Generator
from openai import OpenAI
import time
import os
import httpx
import tkinter as tk
import tkinter.scrolledtext as scrolledtext
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk


OLLAMA = "gemma3:27b-it-qat"
GPT_MINI = "gpt-5-nano"
#GPT_MINI = "gpt-4o-mini"
GEMINI_2_0_FLASH = "gemini-2.0-flash"  # 免费
#GEMINI_2_5_FLASH = "gemini-2.5-pro-preview-06-05"  # 付费
MANUAL = "manual"

MODELS = {
    GPT_MINI : {
        "url": "https://api.openai.com/v1"
    },
    GEMINI_2_0_FLASH : {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/"
    },
    OLLAMA : {
        "url": "http://10.0.0.216:11434/v1"
    },
    MANUAL: {
        "url": "http://10.0.0.238:11434/v1"
    }
}


class LLMApi:

    def __init__(self, model: str = None):
        self.model = model

        self.openai_client = OpenAI(
            api_key = os.getenv("OPENAI_API_KEY", ""),
            base_url = MODELS[GPT_MINI]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(90.0))
        )
        self.google_client = OpenAI(
            api_key = os.getenv("GOOGLE_API_KEY", ""),
            base_url =  MODELS[GPT_MINI]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(90.0))
        )
        self.ollama_client = OpenAI(
            api_key="ollama",
            base_url =  MODELS[OLLAMA]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(90.0))
        )
        self.manal_client = OpenAI(
            api_key="ollama",
            base_url =  MODELS[MANUAL]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(90.0))
        )
    

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
    

    def create_message(self, role: str, content: Union[str, List]) -> Dict[str, Union[str, List]]:
        """创建消息对象，支持文本（字符串）或包含图片的内容（列表）"""
        return {"role": role, "content": content}


    def generate_json_summary(self, system_prompt, user_prompt, output_path=None, expect_list=True) -> Union[Dict, List]:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                content = self.generate_text(system_prompt, user_prompt)
                
                if content and content.strip():
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

                    return self.parse_json( content_string=content_string, expect_list=expect_list )

            except Exception as e:
                print(f"生成JSON摘要失败: {str(e)}")

            if attempt < max_retries - 1:  # 不是最后一次尝试
                print(f"等待 7 秒后重试...")
                time.sleep(7)
            else:
                print("所有重试尝试已用尽")
                return [] if expect_list else {}


    def parse_json(self, content_string: str, expect_list: bool = False) -> Union[Dict, List]:
        """
        解析JSON字符串，支持多种格式和清理操作
        
        Args:
            content_string: 要解析的JSON字符串
            expect_list: 是否期望返回列表格式。如果为True，会将字典自动转换为列表
            
        Returns:
            解析后的JSON对象（Dict或List）
        """
        
        def validate_and_convert_type(parsed_result: Any) -> Union[Dict, List]:
            """根据expect_list参数验证和转换类型"""
            if expect_list:
                if isinstance(parsed_result, list):
                    return parsed_result
                elif isinstance(parsed_result, dict):
                    print(f"警告：返回了 {type(parsed_result)} 而不是期望的列表格式，自动转换为列表")
                    return [parsed_result]
                else:
                    print(f"警告：返回了 {type(parsed_result)} 而不是期望的JSON格式")
                    return []
            else:
                return parsed_result
        
        # Step 1: 移除<think>标签及其内容
        if content_string is None or content_string.strip() == "":
            return [] if expect_list else {}
        
        content_string = re.sub(r'<think>.*?</think>', '', content_string, flags=re.DOTALL)
        
        # Step 2: 移除首尾空白
        content_string = content_string.strip()
        
        # Step 3: 首先尝试从 ```json ... ``` 代码块中提取JSON
        json_pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(json_pattern, content_string, re.DOTALL)
        if matches:
            try:
                json_content = matches[0].strip()
                parsed_result = json.loads(json_content)
                return validate_and_convert_type(parsed_result)
            except json.JSONDecodeError as e:
                print(f"从代码块解析JSON失败: {e}")
                # 继续尝试其他方法
        
        # Step 4: 尝试直接解析整个响应（最常见情况）
        try:
            parsed_result = json.loads(content_string)
            return validate_and_convert_type(parsed_result)
        except json.JSONDecodeError as e:
            print(f"直接解析失败: {e}")
            # 继续尝试其他方法
        
        # Step 5: 尝试提取JSON数组或对象（使用更精确的模式）
        # 查找以 [ 或 { 开头的JSON结构
        json_start = -1
        bracket_count = 0
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i, char in enumerate(content_string):
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
                
            if not in_string:
                if char in '[{':
                    if json_start == -1:
                        json_start = i
                    if char == '[':
                        bracket_count += 1
                    else:
                        brace_count += 1
                elif char in ']}':
                    if char == ']':
                        bracket_count -= 1
                    else:
                        brace_count -= 1
                    
                    # 如果所有括号都匹配了，我们找到了完整的JSON
                    if json_start != -1 and bracket_count == 0 and brace_count == 0:
                        json_str = content_string[json_start:i+1]
                        try:
                            parsed_result = json.loads(json_str)
                            return validate_and_convert_type(parsed_result)
                        except json.JSONDecodeError:
                            # 重置计数器，寻找下一个可能的JSON
                            json_start = -1
                            bracket_count = 0
                            brace_count = 0
        
        # Step 6: 最后的尝试 - 轻量级清理（仅用于明显损坏的JSON）
        try:
            # 移除控制字符（除了换行、回车、制表符）
            cleaned = ''.join(char for char in content_string if ord(char) >= 32 or char in '\n\r\t')
            
            # 移除首尾的引号（如果整个字符串被引号包裹）
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
                # 处理转义的引号
                cleaned = cleaned.replace('\\"', '"')
            
            # 修复多余的逗号（只在明显错误的情况下）
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
            
            parsed_result = json.loads(cleaned)
            return validate_and_convert_type(parsed_result)
        except json.JSONDecodeError as e:
            print(f"轻量级清理后解析失败: {e}")
        
        # Step 7: 如果所有方法都失败，提供详细的错误信息
        preview = content_string[:500] if len(content_string) > 500 else content_string
        print(f"JSON解析失败，字符串预览：\n{preview}")
        raise Exception(f"无法从响应中提取有效的JSON。原始长度: {len(content_string)} 字符")



    def generate_text(self, system_prompt, user_prompt) -> str:
        if user_prompt is None:
            messages=[
                self.create_message("system", system_prompt)
            ]
        else:
            messages=[
                self.create_message("system", system_prompt),
                self.create_message("user", user_prompt)
            ]

        try:
            # popup dialog to ask user choose from GPT_MINI, GEMINI_2_0_FLASH, or MANUAL, return choice as model
            if self.model == MANUAL or self.model is None:
                model = self._show_model_dialog()
            else:
                model = self.model

            # 准备请求参数（在确定模型后设置）
            if model == GPT_MINI:
                
                request_params = {
                    "model": model,  # 使用确定的模型名称
                    "messages": messages,
                    "max_completion_tokens": 64000,
                    "stream": False
                }
                response = self.openai_client.chat.completions.create(**request_params)
                description = self.parse_response(response)
            elif model == GEMINI_2_0_FLASH:
                request_params = {
                    "model": model,  # 使用确定的模型名称
                    "messages": messages,
                    "temperature": 0.5, # Low (0.0–0.3) predictable;  Medium (0.4–0.7) creativity & reliability;  High (0.8–1.0) very creative
                    "top_p": 0.9,
                    "max_tokens": 64000,
                    "stream": False
                }
                response = self.google_client.chat.completions.create(**request_params)
                description = self.parse_response(response)
            elif model == OLLAMA or model == "gemma3:27b-it-qat":
                request_params = {
                    "model": model,  # 使用确定的模型名称
                    "messages": messages,
                    "temperature": 0.5, # Low (0.0–0.3) predictable;  Medium (0.4–0.7) creativity & reliability;  High (0.8–1.0) very creative
                    "top_p": 0.9,
                    "max_tokens": 64000,
                    "stream": False
                }
                # OLLAMA 模型使用实际的模型名称（如 "gemma3:27b-it-qat"）
                try:
                    print(f"🔄 使用 OLLAMA 模型 ({model}) 生成文本...")
                    response = self.ollama_client.chat.completions.create(**request_params)
                    description = self.parse_response(response)
                    print(f"✅ OLLAMA 模型响应成功")
                except Exception as ollama_error:
                    print(f"❌ OLLAMA 模型调用失败: {str(ollama_error)}")
                    print(f"   请求参数: model={request_params.get('model')}, messages数量={len(messages)}")
                    raise ollama_error
            else:
                description = self._show_mock_dialog(system_prompt, user_prompt)

            if description:
                return description
        except Exception as e:
            print(f"生成文本失败: {str(e)}")
            import traceback
            traceback.print_exc()

        print(f"生成文本失败, EMPTY")
        return ""


    def _show_model_dialog(self) -> str:
        """弹出对话框让用户选择模型：GPT_MINI, GEMINI_2_0_FLASH, 或 MANUAL"""
        # 创建根窗口（如果不存在）
        root = None
        try:
            root = tk._default_root
            if root is None:
                root = tk.Tk()
                root.withdraw()  # 隐藏主窗口
        except:
            root = tk.Tk()
            root.withdraw()
        
        # 创建对话框
        dialog = tk.Toplevel(root)
        dialog.title("选择 LLM 模型")
        dialog.geometry("400x250")
        dialog.transient(root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 400) // 2
        y = (dialog.winfo_screenheight() - 200) // 2
        dialog.geometry(f"400x250+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        ttk.Label(main_frame, text="请选择要使用的 LLM 模型：", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 15))
        
        # 用于存储选择的变量
        selected_model = tk.StringVar(value=GPT_MINI)  # 默认选择 GPT_MINI
        
        # 创建单选按钮
        ttk.Radiobutton(main_frame, text=f"GPT Mini ({GPT_MINI})", variable=selected_model, value=GPT_MINI).pack(anchor='w', pady=5)
        ttk.Radiobutton(main_frame, text=f"Gemini 2.0 Flash ({GEMINI_2_0_FLASH})", variable=selected_model, value=GEMINI_2_0_FLASH).pack(anchor='w', pady=5)
        ttk.Radiobutton(main_frame, text=f"Manual ({MANUAL})", variable=selected_model, value=MANUAL).pack(anchor='w', pady=5)
        
        # 用于存储结果
        result = [None]  # 使用列表以便在闭包中修改
        
        def on_ok():
            result[0] = selected_model.get()
            dialog.destroy()
        
        def on_cancel():
            # 取消时保持 result[0] 为 None
            dialog.destroy()
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=5)
        
        # 等待对话框关闭
        dialog.wait_window()
        
        # 如果用户点击取消，返回默认值 GPT_MINI
        # 如果用户点击确定，返回选择的模型
        return result[0] if result[0] is not None else GPT_MINI


    def _show_mock_dialog(self, system_prompt, user_prompt) -> str:
        """在 MOCK 模式下显示对话框，允许用户编辑 system_prompt 并输入 JSON 响应"""
        # 创建根窗口（如果不存在）
        root = None
        try:
            root = tk._default_root
            if root is None:
                root = tk.Tk()
                root.withdraw()  # 隐藏主窗口
        except:
            root = tk.Tk()
            root.withdraw()
        
        # 创建对话框
        dialog = tk.Toplevel(root)
        dialog.title("LLM Mock - 编辑提示词并输入 JSON 响应")
        dialog.geometry("1000x800")
        dialog.transient(root)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 1000) // 2
        y = (dialog.winfo_screenheight() - 800) // 2
        dialog.geometry(f"1000x800+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建 Notebook 来组织标签页
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # System Prompt 标签页
        system_frame = ttk.Frame(notebook, padding=10)
        notebook.add(system_frame, text="Prompt (可编辑)")
        ttk.Label(system_frame, text="提示词 (Prompt):", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        system_text = scrolledtext.ScrolledText(system_frame, wrap=tk.WORD, width=90, height=15)
        system_text.pack(fill=tk.BOTH, expand=True)
        content = system_prompt +" \n\n ----- user-promt ----\n\n" + user_prompt
        system_text.insert('1.0', content)
        # 将内容复制到剪贴板，方便用户粘贴到其他应用/窗口
        dialog.clipboard_clear()
        dialog.clipboard_append(content)
        dialog.update()  # 确保剪贴板操作完成
        
        # JSON Response 标签页
        response_frame = ttk.Frame(notebook, padding=10)
        notebook.add(response_frame, text="Response (输入响应)")
        ttk.Label(response_frame, text="响应 (Response):", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        response_text = scrolledtext.ScrolledText(response_frame, wrap=tk.WORD, width=90, height=15)
        response_text.pack(fill=tk.BOTH, expand=True)
        response_text.insert('1.0', '')
        
        # 用于存储结果
        result = [None]  # 使用列表以便在闭包中修改
        
        def on_ok():
            # 获取响应文本内容
            response_content = response_text.get('1.0', tk.END).strip()
            result[0] = response_content  # 即使为空字符串也保存
            dialog.destroy()
        
        def on_cancel():
            # 取消时保持 result[0] 为 None
            dialog.destroy()
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=5)
        
        # 等待对话框关闭
        dialog.wait_window()
        
        # 如果用户点击取消，result[0] 仍然是 None，返回空字符串
        # 如果用户点击确定，result[0] 包含响应文本（可能为空字符串）
        return result[0] if result[0] is not None else ""

    
