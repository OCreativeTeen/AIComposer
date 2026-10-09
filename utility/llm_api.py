import json
import re
import base64
from io import BytesIO
from typing import List, Dict, Union, Any, Generator, Optional, Tuple
from openai import OpenAI
import time
import os
import httpx
import config
import tkinter as tk
import tkinter.scrolledtext as scrolledtext
import tkinter.ttk as ttk
from PIL import Image, ImageTk
from . import file_util


LM_STUDIO = "qwen/qwen3.5-9b"
#OLLAMA = "qwen3.5:9b"
OLLAMA = "gemma4:26b"

GPT_MINI = "deepseek-flash"

GEMINI = "gemini-3.5-flash-lite"

MANUAL = "manual"

MODELS = {
    GPT_MINI : {
        "url": "https://api.deepseek.com/v1" #"https://api.openai.com/v1"
    },
    GEMINI : {
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
            base_url =  MODELS[GEMINI]["url"],
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
    def generate_json(self, system_prompt, user_prompt, output_path=None, expect_list=True, *, images=None) -> Union[Dict, List]:
        max_retries = 1
        for attempt in range(max_retries):
            try:
                content = self.generate_text(system_prompt, user_prompt, images=images)
                if not isinstance(content, str) or not content.strip():
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
                print(f"生成JSON失败: {str(e)}")
                # write content_string to file
                failed_file = config.get_temp_file("debug", "txt", "llm_api_generate_json_failed_content_string")
                with open(failed_file, "w", encoding="utf-8") as f:
                    f.write(content_string)

            if attempt < max_retries - 1:  # 不是最后一次尝试
                print(f"等待 7 秒后重试...")
                time.sleep(2)
            else:
                print("所有重试尝试已用尽")
                return [] if expect_list else {}

   
    def _get_dialog_parent(self):
        """选择一个可见的父窗口作为 Toplevel parent。"""
        parent = None
        try:
            parent = tk._default_root
        except Exception:
            parent = None
        try:
            if parent is not None:
                w = parent.focus_get()
                if w is not None:
                    parent = w.winfo_toplevel()
        except Exception:
            pass
        if parent is None:
            parent = tk.Tk()
            parent.withdraw()
        return parent


    def _image_path_to_data_url(self, image_path: str) -> str:
        image = Image.open(image_path)
        max_size = 1024
        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        elif image.mode not in ('RGB',):
            image = image.convert('RGB')
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{img_base64}"


    def _create_vision_messages(
        self, system_prompt: str, image_path: str, user_prompt: str = ""
    ) -> List[Dict]:
        """旧的看图请求。手动窗口现在只展示图片供复制，模型调用走文字。"""
        data_url = self._image_path_to_data_url(image_path)
        user_content: list[dict] = [
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            }
        ]
        ut = (user_prompt or "").strip()
        if ut:
            user_content.append({"type": "text", "text": ut})
        return [
            self.create_message("system", system_prompt),
            self.create_message("user", user_content),
        ]


    @staticmethod
    def _image_from_clipboard():
        """从剪贴板取出一张图，返回独立的一份内存图像。剪贴板里没有图时返回 None。"""
        try:
            from PIL import ImageGrab
        except ImportError:
            return None
        try:
            clip = ImageGrab.grabclipboard()
        except Exception:
            return None
        if clip is None:
            return None
        try:
            if isinstance(clip, list):
                src = next((p for p in clip if isinstance(p, str) and p and os.path.isfile(p)), "")
                if not src:
                    return None
                with Image.open(src) as opened:
                    opened.load()
                    return opened.copy()
            if not hasattr(clip, "copy"):
                return None
            clip.load()
            return clip.copy()
        except Exception:
            return None

    @staticmethod
    def _copy_image_to_clipboard(image_path: str) -> bool:
        try:
            import win32clipboard  # type: ignore

            img = Image.open(image_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            output = BytesIO()
            img.save(output, 'BMP')
            data = output.getvalue()[14:]
            output.close()
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()
            print(f"✅ 已复制图像到剪贴板: {os.path.basename(image_path)}")
            return True
        except ImportError:
            print("⚠️ 需要安装 pywin32 才能复制图像到剪贴板: pip install pywin32")
            return False
        except Exception as e:
            print(f"❌ 复制图像到剪贴板失败: {e}")
            return False


    def _chat_completions(self, model: str, messages: List[Dict]) -> Any:
        if model == GPT_MINI:
            request_params = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": 131072,
                "stream": False,
            }
            return self.openai_client.chat.completions.create(**request_params)
        if model == GEMINI:
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": 0.5,
                "max_tokens": 65536,
                "stream": False,
            }
            return self.google_client.chat.completions.create(**request_params)
        if model == LM_STUDIO:
            request_params = {
                "model": model,
                "messages": messages,
                "max_tokens": 262144,
                "stream": False,
            }
            print(f"🔄 使用 LM Studio 模型 ({model}) 分析图片...")
            return self.lm_studio_client.chat.completions.create(**request_params)
        request_params = {
            "model": model,
            "messages": messages,
            "max_tokens": 262144,
            "stream": False,
        }
        print(f"🔄 使用 OLLAMA 模型 ({model}) 分析图片...")
        return self.ollama_client.chat.completions.create(**request_params)


    def show_manual_window(self, system_prompt, user_prompt="", *, images=None):
        """只打开手动窗口，用来复制提示词和图片。不调用模型。

        有返回图时得到内存里的 PIL Image。没有图、文字有内容时得到这段文字。
        两边都空时得到空字符串，和原来没有贴回时一样。
        """
        _model, response = self._show_model_dialog(system_prompt or "", user_prompt or "", image_paths=images)
        return response

    def analyze_image(
        self, analyze_prompt, image_path, user_prompt: str = ""
    ) -> Optional[str]:
        """最多 3 张图只在手动窗口里供双击复制。发给模型的仍是文字。"""
        user_text = (user_prompt or "").strip() or "Continue."
        return self.generate_text(analyze_prompt or "", user_text, images=image_path)


    def analyze_image_json(
        self,
        analyze_prompt,
        image_path,
        output_path=None,
        expect_list=False,
        user_prompt: str = "",
    ) -> Union[Dict, List]:
        """分析图片并解析为 JSON（与 generate_json 相同的清洗/解析流程）。"""
        content = self.analyze_image(analyze_prompt, image_path, user_prompt=user_prompt)
        if not isinstance(content, str) or not content.strip():
            return [] if expect_list else {}

        content_string = str(content).strip()
        content_string = content_string.replace("```json", "").replace("```", "")
        content_string = re.sub(r'\s+', ' ', content_string)
        content_string = content_string.replace("\r\n", " ")
        content_string = content_string.replace("\n", " ")
        content_string = content_string.replace("\r", " ")
        content_string = " ".join(content_string.splitlines())

        if output_path:
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content_string)
            except Exception as e:
                print(f"警告：无法保存 JSON 文件到 {output_path}: {e}")

        return file_util.parse_json(content_string=content_string, expect_list=expect_list)


    @staticmethod
    def _normalize_image_paths(images) -> list:
        """一张路径或一个列表，最多留 3 张存在的图。"""
        if not images:
            return []
        if isinstance(images, str):
            images = [images]
        kept = []
        for raw in images:
            path = (raw or "").strip() if isinstance(raw, str) else ""
            if not path or not os.path.isfile(path) or path in kept:
                continue
            kept.append(path)
            if len(kept) >= 3:
                break
        return kept


    def generate_text(self, system_prompt, user_prompt, *, images=None):
        user_prompt = user_prompt or "Continue."
        messages=[
            self.create_message("system", system_prompt),
            self.create_message("user", user_prompt)
        ]

        try:
            # popup dialog to ask user choose from GPT_MINI, GEMINI, or MANUAL, return choice as model
            if self.model == MANUAL or self.model is None:
                model, manual_response = self._show_model_dialog(
                    system_prompt, user_prompt, image_paths=images
                )
                if model == MANUAL:
                    return manual_response
            else:
                model = self.model

            # 准备请求参数（在确定模型后设置）
            if model == GPT_MINI:
                
                request_params = {
                    "model": model,  # 使用确定的模型名称
                    "messages": messages,
                    "max_completion_tokens": 131072,
                    "stream": False
                }
                response = self.openai_client.chat.completions.create(**request_params)
                return self.parse_response(response)

            elif model == GEMINI:

                request_params = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.5,
                    "max_tokens": 65536,
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


    def _show_model_dialog(
        self,
        system_prompt,
        user_prompt=None,
        *,
        image_paths=None,
    ) -> Tuple[str, Optional[str]]:
        """没有图时右栏是 User Prompt。有图时左栏是提示词和文字贴回，右栏上三分之二是输入图，下三分之一是贴回的图。"""
        image_paths = self._normalize_image_paths(image_paths)
        is_image_mode = bool(image_paths)
        dialog_w = dialog_h = 1000
        parent = self._get_dialog_parent()
        dialog = tk.Toplevel(parent)
        dialog.title("选择 LLM 模型")
        dialog.geometry(f"{dialog_w}x{dialog_h}")
        dialog.minsize(900, 900)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog_w) // 2
        y = (dialog.winfo_screenheight() - dialog_h) // 2
        dialog.geometry(f"{dialog_w}x{dialog_h}+{x}+{y}")
        try:
            dialog.lift()
            dialog.focus_force()
        except Exception:
            pass

        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        top_frame = ttk.Frame(main_frame)
        top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top_frame.columnconfigure(0, weight=1)

        model_frame = ttk.LabelFrame(top_frame, text="选择 LLM 模型", padding=8)
        model_frame.grid(row=0, column=0, sticky="ew")
        selected_model = tk.StringVar(value=MANUAL)
        ttk.Label(model_frame, text="点击下方按钮选择模型：", font=("TkDefaultFont", 9)).pack(anchor=tk.W, pady=(0, 4))
        model_btn_row = ttk.Frame(model_frame)
        model_btn_row.pack(fill=tk.X)
        for mid, title in [
            (GPT_MINI, f"GPT"),
            (GEMINI, "Gemini"),
            (OLLAMA, f"OLLAMA"),
            (MANUAL, f"Manual"),
        ]:
            ttk.Button(
                model_btn_row,
                text=title,
                command=lambda m=mid: selected_model.set(m),
            ).pack(side=tk.LEFT, padx=(0, 6), pady=2)
        model_status = ttk.Label(model_frame, text="", font=("TkDefaultFont", 9), foreground="gray30")
        model_status.pack(anchor=tk.W, pady=(6, 0))

        body = ttk.Frame(main_frame)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=2, uniform="cols")
        body.columnconfigure(1, weight=3, uniform="cols")
        body.rowconfigure(0, weight=1)

        left_col = ttk.Frame(body, padding=(0, 4))
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_col.columnconfigure(0, weight=1)
        response_row = 2 if is_image_mode else 1
        left_col.rowconfigure(0, weight=1)
        if is_image_mode:
            left_col.rowconfigure(1, weight=1)
        left_col.rowconfigure(response_row, weight=1)

        system_frame = ttk.LabelFrame(left_col, text="System Prompt", padding=8)
        system_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        system_frame.rowconfigure(0, weight=1)
        system_frame.columnconfigure(0, weight=1)
        system_text = scrolledtext.ScrolledText(system_frame, wrap=tk.WORD, height=8)
        system_text.grid(row=0, column=0, sticky="nsew")
        if isinstance(system_prompt, str):
            system_text.insert("1.0", system_prompt)

        user_text = None
        if is_image_mode:
            user_frame = ttk.LabelFrame(left_col, text="User Prompt", padding=8)
            user_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
            user_frame.rowconfigure(0, weight=1)
            user_frame.columnconfigure(0, weight=1)
            user_text = scrolledtext.ScrolledText(user_frame, wrap=tk.WORD, height=8)
            user_text.grid(row=0, column=0, sticky="nsew")
            if isinstance(user_prompt, str):
                user_text.insert("1.0", user_prompt)

        response_frame = ttk.LabelFrame(left_col, text="响应 (Response) - 仅 Manual", padding=8)
        response_frame.grid(row=response_row, column=0, sticky="nsew")
        response_frame.rowconfigure(1, weight=1)
        response_frame.columnconfigure(0, weight=1)
        ttk.Label(response_frame, text="双击从剪贴板粘贴", font=("TkDefaultFont", 8)).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        response_text = scrolledtext.ScrolledText(response_frame, wrap=tk.WORD, height=8)
        response_text.grid(row=1, column=0, sticky="nsew")

        right_col = ttk.Frame(body)
        right_col.grid(row=0, column=1, sticky="nsew")
        right_col.columnconfigure(0, weight=1)
        response_image = [None]

        if is_image_mode:
            right_col.rowconfigure(0, weight=2)
            right_col.rowconfigure(1, weight=1)
            input_box = ttk.LabelFrame(right_col, text="图片（双击复制这一张）", padding=8)
            input_box.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
            input_box.columnconfigure(0, weight=1)
            photo_ref = []
            thumb_h = {1: 420, 2: 200, 3: 130}[len(image_paths)]
            for index, path in enumerate(image_paths):
                input_box.rowconfigure(index, weight=1)
                slot = ttk.Frame(input_box)
                slot.grid(row=index, column=0, sticky="nsew", pady=4)
                ttk.Label(slot, text=os.path.basename(path), font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
                try:
                    pil_img = Image.open(path)
                    pil_img.thumbnail((400, thumb_h), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(pil_img)
                    photo_ref.append(photo)
                    image_label = ttk.Label(slot, image=photo)
                    image_label.pack(anchor=tk.CENTER, expand=True)
                    image_label.bind(
                        "<Double-Button-1>",
                        lambda _e, one=path: self._copy_image_to_clipboard(one),
                    )
                except Exception as exc:
                    ttk.Label(slot, text=f"无法加载图片: {exc}").pack(anchor=tk.W)

            reply_box = ttk.LabelFrame(right_col, text="返回的图（双击从剪贴板粘贴）", padding=8)
            reply_box.grid(row=1, column=0, sticky="nsew")
            reply_hint = ttk.Label(reply_box, text="双击从剪贴板粘贴", font=("TkDefaultFont", 8))
            reply_hint.pack(anchor=tk.W, pady=(0, 4))
            reply_hit = tk.Frame(reply_box, height=160)
            reply_hit.pack(fill=tk.BOTH, expand=True)
            reply_pic = ttk.Label(reply_hit)
            reply_pic.pack(anchor=tk.CENTER, expand=True, fill=tk.BOTH)

            def paste_response_image(_event=None):
                img = self._image_from_clipboard()
                if img is None:
                    reply_hint.config(text="剪贴板里没有图片")
                    return "break"
                response_image[0] = img
                thumb = img.copy()
                thumb.thumbnail((400, 220), Image.Resampling.LANCZOS)
                if thumb.mode not in ("RGB", "RGBA"):
                    thumb = thumb.convert("RGBA")
                photo = ImageTk.PhotoImage(thumb)
                photo_ref.append(photo)
                reply_pic.configure(image=photo)
                reply_hint.config(text="已贴上返回的图")
                return "break"

            for widget in (reply_box, reply_hint, reply_hit, reply_pic):
                widget.bind("<Double-Button-1>", paste_response_image)
            dialog._llm_dialog_photo_ref = photo_ref
        else:
            prompt_box = ttk.LabelFrame(right_col, text="User Prompt", padding=8)
            prompt_box.grid(row=0, column=0, sticky="nsew")
            right_col.rowconfigure(0, weight=1)
            prompt_box.columnconfigure(0, weight=1)
            prompt_box.rowconfigure(1, weight=1)
            ttk.Label(prompt_box, text="User Prompt:", font=("TkDefaultFont", 9, "bold")).grid(
                row=0, column=0, sticky="w", pady=(0, 4)
            )
            user_text = scrolledtext.ScrolledText(prompt_box, wrap=tk.WORD, height=20)
            user_text.grid(row=1, column=0, sticky="nsew")
            if isinstance(user_prompt, str):
                user_text.insert("1.0", user_prompt)

        def on_response_double_click_paste(_event):
            try:
                clipboard_content = file_util.safe_clipboard_json_copy(dialog.clipboard_get())
                if clipboard_content:
                    try:
                        sel_start = response_text.index(tk.SEL_FIRST)
                        sel_end = response_text.index(tk.SEL_LAST)
                        response_text.delete(sel_start, sel_end)
                        response_text.insert(sel_start, clipboard_content)
                    except tk.TclError:
                        response_text.insert(response_text.index(tk.INSERT), clipboard_content)
            except tk.TclError:
                pass

        response_text.bind('<Double-Button-1>', on_response_double_click_paste)

        result_model = [None]
        result_response = [None]

        def get_request_copy_content() -> str:
            content = system_text.get('1.0', tk.END).strip()
            if is_image_mode and user_text is not None:
                ut = user_text.get("1.0", tk.END).strip()
                if ut:
                    content += "\n\n----- user-prompt ----\n\n" + ut
            elif not is_image_mode and user_text is not None:
                content += " \n\n ----- user-promt ----\n\n" + user_text.get('1.0', tk.END).strip()
            return content

        def update_response_visibility():
            if selected_model.get() == MANUAL:
                response_frame.grid(row=response_row, column=0, sticky="nsew", pady=(0, 6))
            else:
                response_frame.grid_remove()

        def sync_model_status(*_):
            model_status.config(text=f"当前模型: {selected_model.get()}")

        def on_model_changed(*_):
            update_response_visibility()
            sync_model_status()

        selected_model.trace("w", on_model_changed)
        on_model_changed()

        def on_ok():
            model = selected_model.get()
            result_model[0] = model
            if model == MANUAL:
                text = response_text.get("1.0", tk.END).strip()
                if response_image[0] is not None:
                    result_response[0] = response_image[0]
                else:
                    result_response[0] = text
                dialog.clipboard_clear()
                dialog.clipboard_append(get_request_copy_content())
                dialog.update()
            else:
                result_response[0] = None
            dialog.destroy()

        def on_cancel():
            result_model[0] = MANUAL
            result_response[0] = None
            dialog.destroy()

        def on_copy():
            dialog.clipboard_clear()
            dialog.clipboard_append(get_request_copy_content())
            dialog.update()

        action_box = ttk.Frame(model_btn_row)
        action_box.pack(side=tk.RIGHT)
        ttk.Button(action_box, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=(6, 0), pady=2)
        ttk.Button(action_box, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0), pady=2)
        ttk.Button(action_box, text="重新拷贝提示词", command=on_copy).pack(side=tk.RIGHT, pady=2)
        ttk.Separator(model_btn_row, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=48, pady=2)

        on_copy()
        dialog.wait_window()
        model = result_model[0] if result_model[0] is not None else GEMINI
        response = result_response[0] if result_response[0] is not None else None
        return model, response


