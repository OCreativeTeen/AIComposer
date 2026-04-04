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
from . import file_util


LM_STUDIO = "qwen/qwen3.5-9b"
#OLLAMA = "qwen3.5:9b"
OLLAMA = "gemma4"

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
    LM_STUDIO : {
        "url": "http://10.0.0.216:1234/v1"
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
        self.lm_studio_client = OpenAI(
            api_key="ollama",
            base_url =  MODELS[LM_STUDIO]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(180.0))
        )
        #self.ollama_client_2 = OpenAI(
        #    api_key="ollama",
        #    base_url =  MODELS[OLLAMA2]["url"],
        #    http_client = httpx.Client(timeout=httpx.Timeout(180.0))
        #)
        self.manal_client = OpenAI(
            api_key="ollama",
            base_url =  MODELS[MANUAL]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(180.0))
        )
    

    def parse_response(self, response: Any) -> str:
        try:
            if not response or not getattr(response, 'choices', None):
                print("⚠️ LLM 响应无 choices 字段")
                return None
            if not response.choices:
                print("⚠️ LLM 响应 choices 为空")
                return None
            content = response.choices[0].message.content
            if content is None or (isinstance(content, str) and not content.strip()):
                print("⚠️ LLM 响应 content 为空")
            return content
        except (AttributeError, IndexError) as e:
            print(f"⚠️ 解析 LLM 响应失败: {e}")
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


    # { "topic_category": "心智成长与存在焦虑", "topic_subtype": "觉醒期与意义崩塌", "tags": "我开始怀疑以前相信的一切, 努力好像不一定 有回报, 我看清规则却更迷茫" }
    def generate_json(self, system_prompt, user_prompt, output_path=None, expect_list=True) -> Union[Dict, List]:
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

                    return file_util.parse_json( content_string=content_string, expect_list=expect_list )

            except Exception as e:
                print(f"生成JSON摘要失败: {str(e)}")

            if attempt < max_retries - 1:  # 不是最后一次尝试
                print(f"等待 7 秒后重试...")
                time.sleep(2)
            else:
                print("所有重试尝试已用尽")
                return [] if expect_list else {}



    def generate_text(self, system_prompt, user_prompt) -> str:
        user_prompt = user_prompt or "Continue."
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
                    "max_completion_tokens": 262144,
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
                    "max_tokens": 262144,
                    "stream": False
                }
                response = self.google_client.chat.completions.create(**request_params)
                return self.parse_response(response)

            elif model == LM_STUDIO:

                request_params = {
                    "model": model,  # 使用确定的模型名称
                    "messages": messages,
                    "max_tokens": 262144,
                    "stream": False
                }
                # OLLAMA 模型使用实际的模型名称（如 "gemma3:27b-it-qat"）
                #with open("ollama_request_params.json", "w", encoding="utf-8") as f:
                #    json.dump(request_params, f, ensure_ascii=False, indent=2)

                print(f"🔄 使用 LM Studio 模型 ({model}) 生成文本...")
                #if model == OLLAMA2:
                #    response = self.ollama_client_2.chat.completions.create(**request_params)
                #else:
                response = self.lm_studio_client.chat.completions.create(**request_params)
                return self.parse_response(response)

            else: # model == OLLAMA or model == "gemma3:27b-it-qat":

                request_params = {
                    "model": model,  # 使用确定的模型名称
                    "messages": messages,
                    "max_tokens": 262144,
                    "stream": False
                }
                # OLLAMA 模型使用实际的模型名称（如 "gemma3:27b-it-qat"）
                #with open("ollama_request_params.json", "w", encoding="utf-8") as f:
                #    json.dump(request_params, f, ensure_ascii=False, indent=2)

                print(f"🔄 使用 OLLAMA 模型 ({model}) 生成文本...")
                #if model == OLLAMA2:
                #    response = self.ollama_client_2.chat.completions.create(**request_params)
                #else:
                response = self.ollama_client.chat.completions.create(**request_params)
                return self.parse_response(response)

        except Exception as e:
            print(f"❌ LLM API 调用失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None


    def _show_model_dialog(self, system_prompt, user_prompt) -> tuple:
        """弹出对话框让用户选择模型并查看/编辑请求和响应"""
        # 选择一个“可见的父窗口”作为 parent，避免对话框挂到 withdraw 的 root 上导致不显示/跑到后台
        parent = None
        try:
            parent = tk._default_root
        except Exception:
            parent = None

        # 优先使用当前焦点所在的顶层窗口作为父窗口（最符合用户预期）
        try:
            if parent is not None:
                w = parent.focus_get()
                if w is not None:
                    parent = w.winfo_toplevel()
        except Exception:
            pass

        # 如果还没有 root，则创建一个隐藏 root 兜底（CLI/无 GUI 场景）
        if parent is None:
            parent = tk.Tk()
            parent.withdraw()

        # 创建对话框
        dialog = tk.Toplevel(parent)
        dialog.title("选择 LLM 模型")
        dialog.geometry("1000x800")
        dialog.transient(parent)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 1000) // 2
        y = (dialog.winfo_screenheight() - 800) // 2
        dialog.geometry(f"1000x800+{x}+{y}")
        # 置顶/聚焦，避免被其它 Toplevel 压住看不到
        try:
            dialog.lift()
            dialog.focus_force()
        except Exception:
            pass
        
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
        
        # 绑定双击事件：双击时自动从剪贴板粘贴内容
        def on_double_click_paste(event):
            """双击时从剪贴板粘贴内容到当前光标位置"""
            try:
                # 获取剪贴板内容
                clipboard_content = dialog.clipboard_get()
                if clipboard_content:
                    # 检查是否有选中的文本，如果有则先删除
                    try:
                        sel_start = response_text.index(tk.SEL_FIRST)
                        sel_end = response_text.index(tk.SEL_LAST)
                        # 删除选中的文本
                        response_text.delete(sel_start, sel_end)
                        # 在删除位置插入剪贴板内容
                        response_text.insert(sel_start, clipboard_content)
                    except tk.TclError:
                        # 没有选中文本，在光标位置插入
                        cursor_pos = response_text.index(tk.INSERT)
                        response_text.insert(cursor_pos, clipboard_content)
            except tk.TclError:
                # 剪贴板为空或无法访问时忽略错误
                pass
        
        response_text.bind('<Double-Button-1>', on_double_click_paste)
        
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


