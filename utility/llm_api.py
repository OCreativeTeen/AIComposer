import json
import re
from typing import List, Dict, Union, Any, Generator
from openai import OpenAI
import time
import os
import httpx
import tkinter as tk
import tkinter.scrolledtext as scrolledtext
import tkinter.ttk as ttk


OLLAMA = "gemma3:12b-it-qat"
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
            http_client = httpx.Client(timeout=httpx.Timeout(180.0))
        )
        self.google_client = OpenAI(
            api_key = os.getenv("GOOGLE_API_KEY", ""),
            base_url =  MODELS[GPT_MINI]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(180.0))
        )
        self.ollama_client = OpenAI(
            api_key="ollama",
            base_url =  MODELS[OLLAMA]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(180.0))
        )
        self.manal_client = OpenAI(
            api_key="ollama",
            base_url =  MODELS[MANUAL]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(180.0))
        )
    

    def parse_response(self, response: Any) -> str:
        try:
            return response.choices[0].message.content
        except (AttributeError, IndexError) as e:
            return None
    

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
                if not content:
                    return [] if expect_list else {}

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
                time.sleep(2)
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
                model, manual_response = self._show_model_dialog(system_prompt, user_prompt)
                if model == MANUAL:
                    return manual_response
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
                return self.parse_response(response)

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
                return self.parse_response(response)

            else: # model == OLLAMA or model == "gemma3:27b-it-qat":

                request_params = {
                    "model": model,  # 使用确定的模型名称
                    "messages": messages,
                    "max_tokens": 256000,
                    "stream": False
                }
                # OLLAMA 模型使用实际的模型名称（如 "gemma3:27b-it-qat"）
                with open("ollama_request_params.json", "w", encoding="utf-8") as f:
                    json.dump(request_params, f, ensure_ascii=False, indent=2)

                print(f"🔄 使用 OLLAMA 模型 ({model}) 生成文本...")
                response = self.ollama_client.chat.completions.create(**request_params)
                return self.parse_response(response)

        except Exception as e:
            return None


    def _show_model_dialog(self, system_prompt, user_prompt) -> tuple:
        """弹出对话框让用户选择模型并查看/编辑请求和响应"""
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
        
        # 模型选择区域
        model_frame = ttk.LabelFrame(main_frame, text="选择 LLM 模型", padding=10)
        model_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 用于存储选择的变量
        selected_model = tk.StringVar(value=MANUAL)  # 默认选择 GPT_MINI
        
        # 创建单选按钮
        ttk.Radiobutton(model_frame, text=f"GPT Mini ({GPT_MINI})", variable=selected_model, value=GPT_MINI).pack(anchor='w', pady=2)
        ttk.Radiobutton(model_frame, text=f"Gemini 2.0 Flash ({GEMINI_2_0_FLASH})", variable=selected_model, value=GEMINI_2_0_FLASH).pack(anchor='w', pady=2)
        ttk.Radiobutton(model_frame, text=f"OLLAMA ({OLLAMA})", variable=selected_model, value=OLLAMA).pack(anchor='w', pady=2)
        ttk.Radiobutton(model_frame, text=f"Manual ({MANUAL})", variable=selected_model, value=MANUAL).pack(anchor='w', pady=2)
        
        # 请求内容区域（分成两部分）
        request_frame = ttk.LabelFrame(main_frame, text="请求内容 (Request)", padding=10)
        request_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 上部：System Prompt
        ttk.Label(request_frame, text="System Prompt:", font=('TkDefaultFont', 9, 'bold')).pack(anchor='w', pady=(0, 5))
        system_text = scrolledtext.ScrolledText(request_frame, wrap=tk.WORD, height=8)
        system_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        if isinstance(system_prompt, str):
            system_text.insert('1.0', system_prompt)
        
        # 分隔线
        separator = ttk.Separator(request_frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=5)
        
        # 下部：User Prompt
        ttk.Label(request_frame, text="User Prompt:", font=('TkDefaultFont', 9, 'bold')).pack(anchor='w', pady=(5, 5))
        user_text = scrolledtext.ScrolledText(request_frame, wrap=tk.WORD, height=8)
        user_text.pack(fill=tk.BOTH, expand=True)
        if isinstance(user_prompt, str):
            user_text.insert('1.0', user_prompt)
        
        # 响应内容区域（只在 Manual 模式时显示）
        response_frame = ttk.LabelFrame(main_frame, text="响应内容 (Response) - 仅 Manual 模式", padding=10)
        ttk.Label(response_frame, text="响应 (Response):", font=('TkDefaultFont', 9, 'bold')).pack(anchor='w', pady=(0, 5))
        response_text = scrolledtext.ScrolledText(response_frame, wrap=tk.WORD, height=8)
        response_text.pack(fill=tk.BOTH, expand=True)
        response_text.insert('1.0', '')
        
        # 用于存储结果
        result_model = [None]
        result_response = [None]

        def update_response_visibility():
            """根据选择的模型显示/隐藏响应区域"""
            if selected_model.get() == MANUAL:
                response_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            else:
                response_frame.pack_forget()
        
        # 绑定模型选择变化事件
        selected_model.trace('w', lambda *args: update_response_visibility())
        update_response_visibility()  # 初始更新（默认选择 GPT_MINI，所以响应区域会被隐藏）
        

        def on_ok():
            model = selected_model.get()
            result_model[0] = model
            
            # 只有在 Manual 模式时才获取响应内容
            if model == MANUAL:
                response_content = response_text.get('1.0', tk.END).strip()
                result_response[0] = response_content
                
                # 只有在 Manual 模式时才合并并复制到剪贴板
                content = ""
                if isinstance(system_prompt, str):
                    content = content + system_prompt
                if isinstance(user_prompt, str):
                    content = content + " \n\n ----- user-promt ----\n\n" + user_prompt
                dialog.clipboard_clear()
                dialog.clipboard_append(content)
                dialog.update()
            else:
                result_response[0] = None
            
            dialog.destroy()
        

        def on_cancel():
            # 取消时返回 MANUAL 和 None
            result_model[0] = MANUAL
            result_response[0] = None
            dialog.destroy()


        def on_copy():
            content = system_text.get('1.0', tk.END).strip() + " \n\n ----- user-promt ----\n\n" + user_text.get('1.0', tk.END).strip()
            dialog.clipboard_clear()
            dialog.clipboard_append(content)
            dialog.update()


        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=5)

        on_copy()

        # 等待对话框关闭
        dialog.wait_window()
        
        # 返回模型和响应（如果选择的是 Manual）
        model = result_model[0] if result_model[0] is not None else GPT_MINI
        response = result_response[0] if result_response[0] is not None else None
        return model, response


