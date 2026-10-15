import json
import re
import base64
from io import BytesIO
from typing import List, Dict, Union, Any, Generator, Optional, Tuple
from openai import OpenAI
import time
import os
import httpx
import threading
import queue
import config
import tkinter as tk
import tkinter.scrolledtext as scrolledtext
import tkinter.ttk as ttk
from tkinter import messagebox
from PIL import Image, ImageTk
from . import file_util


# 本机 Strata 上已加载的模型。/v1/models 的 id，上下文 65536，只收文字。
STRATA = "qwen3.8-flash-next-iq3_xxs"

GEMINI = "gemini-3.5-flash-lite"

MANUAL = "manual"

# 纯文字、不是手动窗口的调用都走这一台本机 Strata。带图片或附件的仍然先开手动窗口。
TEXT_MODEL = STRATA

# 难度分级：简单 -> Strata，难 -> 手动窗口，最难/带图 -> 手动窗口
MODEL_SIMPLE = STRATA
MODEL_HARD = MANUAL  # 不再用 DeepSeek，难任务也走手动窗口
MODEL_MANUAL = MANUAL
# 生成长度上限。模型总窗口是 65536，提示词也算在里面，所以回答不要占满。
STRATA_MAX_TOKENS = 32768

MODELS = {
    STRATA : {
        "url": "http://192.168.1.185:8080/v1"
    },
    GEMINI : {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/"
    },
}


class LLMApi:

    def __init__(self, model: str = None):
        self.model = model
        # 自动调用（Strata / Gemini）失败时，直接打开手动窗口。
        # 调用方自己有手动兜底时（如 media_transcript 的 ManualBridge）设成 False，避免开两次。
        self.manual_fallback = True
        self._last_source = ""

        self.strata_client = OpenAI(
            api_key = os.getenv("STRATA_API_KEY", ""),
            base_url = MODELS[STRATA]["url"],
            http_client = httpx.Client(timeout=httpx.Timeout(180.0))
        )
        self.google_client = OpenAI(
            api_key = os.getenv("GOOGLE_API_KEY", ""),
            base_url =  MODELS[GEMINI]["url"],
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
    def generate_json(self, system_prompt, user_prompt, output_path=None, expect_list=True, *, images=None, attachment=None) -> Union[Dict, List]:
        max_retries = 1
        for attempt in range(max_retries):
            try:
                content = self.generate_text(system_prompt, user_prompt, images=images, attachment=attachment)
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
                if self._last_source not in ("", MANUAL) and self.manual_fallback:
                    # 模型回答了但不是可用的 JSON：同一个提示词转手动窗口一次
                    failed = self._last_source
                    manual = self._manual_fallback(system_prompt, user_prompt, images, attachment, failed)
                    if isinstance(manual, str) and manual.strip():
                        try:
                            cleaned = re.sub(r'\s+', ' ', manual.strip().replace("```json", "").replace("```", ""))
                            return file_util.parse_json(content_string=cleaned, expect_list=expect_list)
                        except Exception as e2:
                            print(f"手动结果也不是可用的 JSON: {e2}")
                    return [] if expect_list else {}
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


    def _strata_request(self, model: str, messages: List[Dict]) -> Dict:
        """本机 Strata（Qwen）的请求。关掉思考，否则回答会空着、只剩 reasoning。"""
        return {
            "model": model,
            "messages": messages,
            "max_tokens": STRATA_MAX_TOKENS,
            "stream": False,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }

    def _chat_completions(self, model: str, messages: List[Dict]) -> Any:
        if model == STRATA:
            return self.strata_client.chat.completions.create(**self._strata_request(model, messages))
        if model == GEMINI:
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": 0.5,
                "max_tokens": 65536,
                "stream": False,
            }
            return self.google_client.chat.completions.create(**request_params)
        raise ValueError(f"没有这个模型：{model}")


    def show_manual_window(
        self,
        system_prompt,
        user_prompt="",
        *,
        images=None,
        on_image_response=None,
    ):
        """只打开手动窗口，用来复制提示词和图片。不调用模型。

        有返回图时得到内存里的 PIL Image。没有图、文字有内容时得到这段文字。
        两边都空时得到空字符串，和原来没有贴回时一样。

        ``on_image_response`` 是可选回调：``fn(pil_image) -> str | None``。
        当返回图片（PIL Image）时调用，返回保存后的路径或 None。
        """
        _model, response = self._show_model_dialog(
            system_prompt or "", user_prompt or "", image_paths=images
        )
        if response is not None and callable(on_image_response) and hasattr(response, "save"):
            try:
                on_image_response(response)
            except Exception as exc:
                print(f"⚠️ on_image_response 回调失败: {exc}")
        return response

    def show_manual_workflow(
        self,
        steps,
        *,
        title: str = "手动流程",
        on_image_response=None,
    ) -> List[Dict[str, Any]]:
        """一连串的手动窗口（一个小小的提示词流程）。不调用任何模型。

        ``steps`` 是一个列表，每一步是下面两种之一：

        - 字典：``{"title": 步骤名, "system": 提示词, "user": 用户提示词（可省）, "images": [图片路径]（可省）,
          "attachment": PDF/音频/视频路径（可省）}``
        - 函数：``fn(results) -> 上面那种字典，或 None（跳过这一步）``。``results`` 是前面已经做完的各步结果，
          所以后面一步的提示词可以按前面一步的回答现拼。

        这是通用的：每一步的提示词和带的图 / 文件都由调用方一次写好传进来，这里不认识任何具体业务。
        每一步都打开同一个手动窗口（只有手动，没有选模型按钮）：提示词先自动拷到剪贴板；
        有 ``images`` 或 ``attachment`` 才显示；没有就不显示。
        不是最后一步时「确定」写成「下一步」。点「取消」或关窗就停下，后面的步骤不再打开。

        ``on_image_response`` 是可选回调：``fn(step_index, step_title, pil_image) -> str | None``。
        当某一步返回图片（PIL Image）时调用，返回保存后的路径或 None。

        返回已经做完的各步结果，每个是 ``{"title", "response", "cancelled", "saved_path"}``：
        ``response`` 是贴回的文字、贴回的图（PIL Image），或 None。取消的那一步 ``cancelled`` 为 True，是列表最后一个。
        ``saved_path`` 是 ``on_image_response`` 返回的路径（若有图片且回调返回了路径）。
        """
        results: List[Dict[str, Any]] = []
        total = len(steps or [])
        for index, raw in enumerate(steps or []):
            step = raw(results) if callable(raw) else raw
            if not isinstance(step, dict):
                continue
            name = str(step.get("title") or f"步骤 {index + 1}")
            is_last = index == total - 1
            window_title = f"{title} · 第 {index + 1} / {total} 步 · {name}"
            _model, response = self._show_model_dialog(
                step.get("system") or "",
                step.get("user") or "",
                image_paths=step.get("images"),
                attachment=step.get("attachment"),
                title=window_title,
                ok_text="完成" if is_last else "下一步 ▶",
                cancel_text="取消流程",
                manual_only=True,
            )
            cancelled = bool(getattr(self, "_last_dialog_cancelled", False))
            saved_path = None
            if not cancelled and response is not None and callable(on_image_response):
                if hasattr(response, "save"):
                    try:
                        saved_path = on_image_response(index, name, response)
                    except Exception as exc:
                        print(f"⚠️ on_image_response 回调失败: {exc}")
            result_entry = {
                "title": name,
                "response": None if cancelled else response,
                "cancelled": cancelled,
            }
            if saved_path:
                result_entry["saved_path"] = saved_path
            results.append(result_entry)
            if cancelled:
                break
        return results

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


    def generate_text(self, system_prompt, user_prompt, *, images=None, attachment=None, _force_model=None):
        """生成文字。

        - 指定了模型（不是 None、不是 MANUAL）：直接用它。
        - 没指定模型（LLMApi()）：
            * 纯文字（没有图片、没有要手动贴的音频/视频/PDF）：先自动用 TEXT_MODEL（本机 Strata），
              失败（报错或空回答）才打开手动窗口，让人处理。
            * 有图片或附件：直接打开手动窗口，和原来一样。
        - MANUAL：总是打开手动窗口。
        """
        user_prompt = user_prompt or "Continue."
        messages=[
            self.create_message("system", system_prompt),
            self.create_message("user", user_prompt)
        ]
        base_model = _force_model or self.model
        self._last_source = ""

        if base_model is None:
            has_media = bool(self._normalize_image_paths(images)) or bool(attachment)
            base_model = MANUAL if has_media else TEXT_MODEL

        if base_model == MANUAL:
            # 手动窗口（也可以在窗口里点选一个模型）
            model, manual_response = self._show_model_dialog(
                system_prompt, user_prompt, image_paths=images, attachment=attachment
            )
            if model == MANUAL:
                self._last_source = MANUAL
                return manual_response
        else:
            model = base_model

        answer = None
        try:
            answer = self.parse_response(self._chat_completions(model, messages))
        except Exception as e:
            print(f"❌ LLM API 调用失败（{model}）: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        if isinstance(answer, str) and answer.strip():
            self._last_source = model
            return answer

        print(f"⚠️ 自动调用 {model} 没成功。")
        if model == STRATA and not os.getenv("STRATA_API_KEY"):
            print("⚠️ 没有找到 Strata 密钥：请在 .env 里加一行 STRATA_API_KEY=你的密钥。")
        return self._manual_fallback(system_prompt, user_prompt, images, attachment, model)

    def _manual_fallback(self, system_prompt, user_prompt, images, attachment, failed_model):
        """自动调用失败：直接打开手动窗口（只能手动，不再选模型，免得来回绕）。后台线程里会转到主线程。"""
        if not self.manual_fallback:
            return None
        print(f"⚠️ {failed_model} 失败，转到手动窗口。")
        _model, manual_response = self._show_model_dialog(
            system_prompt,
            user_prompt,
            image_paths=images,
            attachment=attachment,
            title=f"{failed_model} 没成功，请手动处理",
            manual_only=True,
        )
        self._last_source = MANUAL
        return manual_response


    @staticmethod
    def _attachment_kind(path: str) -> str:
        ext = os.path.splitext(path or "")[1].lower()
        if ext == ".pdf":
            return "pdf"
        if ext in (".mp3", ".wav", ".wave", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".wma", ".opus", ".aiff", ".aif"):
            return "audio"
        if ext in (".mp4", ".m4v", ".mov", ".mkv", ".webm"):
            return "video"
        return ""

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = max(0, int(round(seconds)))
        return f"{total // 60}:{total % 60:02d}"

    def _probe_media_seconds(self, path: str) -> float:
        import shutil
        import subprocess

        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                out = subprocess.run(
                    [
                        ffprobe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path,
                    ],
                    capture_output=True, text=True, timeout=20,
                )
                return max(0.0, float((out.stdout or "").strip() or 0))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        if self._attachment_kind(path) == "audio":
            try:
                import pygame

                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                return float(pygame.mixer.Sound(path).get_length() or 0)
            except Exception:
                return 0.0
        return 0.0

    def _pdf_preview_image(self, path: str):
        try:
            import fitz
        except ImportError:
            return None, 0
        try:
            doc = fitz.open(path)
        except Exception:
            return None, 0
        try:
            pages = len(doc)
            if pages <= 0:
                return None, 0
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(0.45, 0.45), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            return img, pages
        except Exception:
            return None, 0
        finally:
            try:
                doc.close()
            except Exception:
                pass

    def _video_preview_image(self, path: str):
        import shutil
        import subprocess
        import tempfile

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return None
        fd, out = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            subprocess.run(
                [ffmpeg, "-y", "-ss", "0.5", "-i", path, "-frames:v", "1", out],
                capture_output=True, timeout=30,
            )
            if not os.path.isfile(out) or os.path.getsize(out) <= 0:
                return None
            with Image.open(out) as img:
                img.load()
                return img.copy()
        except (OSError, subprocess.SubprocessError):
            return None
        finally:
            try:
                os.remove(out)
            except OSError:
                pass

    def _copy_path_to_clipboard(self, path: str) -> bool:
        import struct

        abs_path = os.path.normpath(os.path.abspath(path))
        try:
            import win32clipboard  # type: ignore

            payload = (abs_path + "\0\0").encode("utf-16-le")
            data = struct.pack("Iiiii", 20, 0, 0, 0, 1) + payload
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_HDROP, data)
            win32clipboard.CloseClipboard()
            return True
        except Exception as exc:
            print(f"复制文件到剪贴板失败: {exc}")
            return False

    def _show_model_dialog_from_thread(
        self,
        system_prompt,
        user_prompt=None,
        *,
        image_paths=None,
        attachment=None,
        title: str = "",
        ok_text: str = "确定",
        cancel_text: str = "取消",
        manual_only: bool = False,
    ) -> Tuple[str, Optional[str]]:
        """从后台线程安全地调用 _show_model_dialog。

        将对话框调度到主线程执行，并等待结果返回。
        """
        result_queue: queue.Queue = queue.Queue()

        def run_on_main_thread():
            try:
                result = self._show_model_dialog(
                    system_prompt,
                    user_prompt,
                    image_paths=image_paths,
                    attachment=attachment,
                    title=title,
                    ok_text=ok_text,
                    cancel_text=cancel_text,
                    manual_only=manual_only,
                )
                result_queue.put(("ok", result))
            except Exception as exc:
                result_queue.put(("error", exc))

        try:
            root = tk._default_root
            if root is None:
                self._last_dialog_cancelled = True
                return MANUAL, None
            root.after(0, run_on_main_thread)
        except Exception:
            self._last_dialog_cancelled = True
            return MANUAL, None

        try:
            status, value = result_queue.get(timeout=600)
            if status == "error":
                raise value
            return value
        except queue.Empty:
            self._last_dialog_cancelled = True
            return MANUAL, None

    def _show_model_dialog(
        self,
        system_prompt,
        user_prompt=None,
        *,
        image_paths=None,
        attachment=None,
        title: str = "",
        ok_text: str = "确定",
        cancel_text: str = "取消",
        manual_only: bool = False,
    ) -> Tuple[str, Optional[str]]:
        """没有图时右栏是 User Prompt。有图时左栏是提示词和文字贴回，右栏上三分之二是输入图，下三分之一是贴回的图。带了 PDF、音频或视频时，右栏上方改成这个文件。

        ``title`` 改窗口标题；``ok_text`` / ``cancel_text`` 改两个按钮上的字；``manual_only`` 为真时不显示
        Strata / Gemini / Manual 三个选模型按钮，只能走手动（多步手动流程用）。
        关窗后 ``self._last_dialog_cancelled`` 记着这次是不是取消（点取消或直接关窗）。
        """
        if threading.current_thread() is not threading.main_thread():
            return self._show_model_dialog_from_thread(
                system_prompt,
                user_prompt,
                image_paths=image_paths,
                attachment=attachment,
                title=title,
                ok_text=ok_text,
                cancel_text=cancel_text,
                manual_only=manual_only,
            )
        self._last_dialog_cancelled = True
        image_paths = self._normalize_image_paths(image_paths)
        attachment = (attachment or "").strip()
        if attachment and not os.path.isfile(attachment):
            attachment = ""
        file_kind = self._attachment_kind(attachment) if attachment else ""
        is_image_mode = bool(image_paths) or bool(file_kind)
        dialog_w = dialog_h = 1000
        parent = self._get_dialog_parent()
        dialog = tk.Toplevel(parent)
        dialog.title(title or "选择 LLM 模型")
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

        model_frame = ttk.LabelFrame(top_frame, text=(title or "选择 LLM 模型"), padding=8)
        model_frame.grid(row=0, column=0, sticky="ew")
        selected_model = tk.StringVar(value=MANUAL)
        if not manual_only:
            ttk.Label(model_frame, text="点击下方按钮选择模型：", font=("TkDefaultFont", 9)).pack(anchor=tk.W, pady=(0, 4))
        model_btn_row = ttk.Frame(model_frame)
        model_btn_row.pack(fill=tk.X)
        for mid, btn_title in ([] if manual_only else [
            (STRATA, "Strata"),
            (GEMINI, "Gemini"),
            (MANUAL, "Manual"),
        ]):
            ttk.Button(
                model_btn_row,
                text=btn_title,
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
        paste_image_handler = [None]  # 当前窗口「返回的图」区的粘贴函数（附件 / 图片 / 纯文字三种布局都有）

        if file_kind:
            right_col.rowconfigure(0, weight=2)
            right_col.rowconfigure(1, weight=1)
            titles = {"pdf": "PDF", "audio": "音频", "video": "视频"}
            input_box = ttk.LabelFrame(right_col, text=titles.get(file_kind, "文件"), padding=8)
            input_box.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
            name = os.path.basename(attachment)
            seconds = self._probe_media_seconds(attachment) if file_kind in ("audio", "video") else 0
            pages = 0
            preview = None
            if file_kind == "pdf":
                preview, pages = self._pdf_preview_image(attachment)
                detail = f"{name}\n{pages} 页" if pages else name
                hint_text = "单击或双击，把这份 PDF 拷到剪贴板"
            elif file_kind == "audio":
                length = self._format_duration(seconds) if seconds else "时长未知"
                detail = f"音频  {name}\n时长 {length}"
                hint_text = "单击拷贝。双击播放，再双击停止"
            else:
                preview = self._video_preview_image(attachment)
                length = self._format_duration(seconds) if seconds else "时长未知"
                detail = f"视频  {name}\n时长 {length}"
                hint_text = "单击拷贝。双击播放，再双击停止"
            info = ttk.Label(input_box, text=detail, font=("TkDefaultFont", 11, "bold"), justify=tk.LEFT)
            info.pack(anchor=tk.W, pady=(0, 6))
            hint = ttk.Label(input_box, text=hint_text, font=("TkDefaultFont", 9))
            hint.pack(anchor=tk.W, pady=(0, 6))
            photo_ref = []
            if preview is not None:
                preview.thumbnail((460, 280), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(preview)
                photo_ref.append(photo)
                pic = ttk.Label(input_box, image=photo)
                pic.pack(anchor=tk.CENTER, expand=True)
            else:
                pic = ttk.Label(input_box, text="")
            play = {"on": False, "proc": None}

            def _stop_playback():
                play["on"] = False
                proc = play.get("proc")
                if proc is not None and proc.poll() is None:
                    try:
                        proc.kill()
                    except OSError:
                        pass
                play["proc"] = None
                try:
                    import pygame

                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except Exception:
                    pass

            def _stop_attachment(_event=None):
                _stop_playback()
                try:
                    hint.config(text=hint_text)
                except tk.TclError:
                    pass

            def _on_dialog_destroy(event=None):
                if event is not None and getattr(event, "widget", None) is not dialog:
                    return
                _stop_playback()

            def _attachment_playing() -> bool:
                proc = play.get("proc")
                if proc is not None and proc.poll() is None:
                    return True
                try:
                    import pygame

                    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                        return True
                except Exception:
                    pass
                return False

            def _start_attachment():
                if file_kind == "audio":
                    try:
                        import pygame

                        if not pygame.mixer.get_init():
                            pygame.mixer.init()
                        pygame.mixer.music.load(attachment)
                        pygame.mixer.music.play()
                        play["on"] = True
                        hint.config(text="正在播放。再双击停止")
                        return
                    except Exception:
                        pass
                import shutil
                import subprocess

                ffplay = shutil.which("ffplay")
                if not ffplay:
                    hint.config(text="没有找到播放器")
                    return
                cmd = [ffplay, "-autoexit", "-loglevel", "quiet"]
                if file_kind == "audio":
                    cmd.append("-nodisp")
                cmd.append(attachment)
                try:
                    play["proc"] = subprocess.Popen(cmd)
                    play["on"] = True
                    hint.config(text="正在播放。再双击停止")
                except OSError:
                    hint.config(text="没有找到播放器")

            transcript = {"path": "", "running": False}

            def _run_transcribe():
                """后台一段一段转录，再把带时间戳的文字文件放进剪贴板，换掉刚才拷的媒体。"""
                import threading

                import project_manager
                from utility import media_transcript

                engine = str(getattr(config, "TRANSCRIBE_ENGINE", "whisper") or "").strip().lower()
                if engine not in ("whisper", "voicebox"):
                    messagebox.showerror(
                        "转录",
                        f"config.py 里的 TRANSCRIBE_ENGINE 写的是 {engine!r}，只能是 \"whisper\" 或 \"voicebox\"。",
                        parent=dialog,
                    )
                    return
                cfg = project_manager.PROJECT_CONFIG if isinstance(project_manager.PROJECT_CONFIG, dict) else {}
                pid = str(cfg.get("pid") or getattr(project_manager, "pid", "") or "")
                language = str(cfg.get("language") or "zh")
                out_dir = None
                if pid:
                    try:
                        out_dir = config.get_temp_path(pid)
                    except Exception:  # noqa: BLE001
                        out_dir = None
                # 文字稿放在媒体旁边，文件名和媒体一样（只是扩展名 .txt）。媒体所在文件夹写不了才放临时目录。
                media_dir = os.path.dirname(os.path.abspath(attachment))
                if media_dir and os.access(media_dir, os.W_OK):
                    out_dir = media_dir

                state = {"done": False, "cancel": False, "error": "", "path": "", "message": "正在准备转录…",
                         "notes": []}
                # 转录里调用 LLM 失败一次，就转到手动模式：请这里（主线程）打开 LLM 手动窗口。
                bridge = media_transcript.ManualBridge(lambda: state["cancel"])
                prog = tk.Toplevel(dialog)
                prog.title("转录中")
                prog.transient(dialog)
                prog.resizable(False, False)
                body_box = ttk.Frame(prog, padding=14)
                body_box.pack(fill=tk.BOTH, expand=True)
                prog_label = ttk.Label(body_box, text=state["message"], width=44, justify=tk.LEFT)
                prog_label.pack(anchor=tk.W)
                bar = ttk.Progressbar(body_box, length=320, mode="determinate", maximum=1, value=0)
                bar.pack(fill=tk.X, pady=(8, 8))

                def _cancel():
                    state["cancel"] = True
                    prog_label.config(text="正在取消…")

                ttk.Button(body_box, text="取消", command=_cancel).pack(anchor=tk.E)
                prog.protocol("WM_DELETE_WINDOW", _cancel)
                prog.update_idletasks()
                try:
                    px = dialog.winfo_rootx() + (dialog.winfo_width() - prog.winfo_reqwidth()) // 2
                    py = dialog.winfo_rooty() + (dialog.winfo_height() - prog.winfo_reqheight()) // 3
                    prog.geometry(f"+{max(0, px)}+{max(0, py)}")
                except tk.TclError:
                    pass
                prog.grab_set()
                transcript["running"] = True

                def _progress(done: int, total: int, message: str):
                    if message:
                        state["message"] = message
                    state["ratio"] = (done / total) if total else 0.0

                def _work():
                    try:
                        state["path"] = media_transcript.transcribe_media_with_timestamps(
                            attachment,
                            engine=engine,
                            pid=pid,
                            language=language,
                            out_dir=out_dir,
                            progress=_progress,
                            cancelled=lambda: state["cancel"],
                            notes=state["notes"],
                            manual_llm=bridge.call,
                        )
                    except InterruptedError:
                        state["error"] = "cancelled"
                    except Exception as exc:  # noqa: BLE001
                        state["error"] = str(exc) or type(exc).__name__
                    state["done"] = True

                def _finish():
                    transcript["running"] = False
                    try:
                        prog.grab_release()
                        prog.destroy()
                    except tk.TclError:
                        pass
                    try:
                        dialog.grab_set()
                    except tk.TclError:
                        pass
                    if state["error"] == "cancelled":
                        hint.config(text="已取消转录。媒体还在剪贴板里")
                        return
                    if state["error"]:
                        hint.config(text="转录失败。媒体还在剪贴板里")
                        messagebox.showerror("转录", state["error"], parent=dialog)
                        return
                    transcript["path"] = state["path"]
                    if state["notes"]:
                        messagebox.showwarning(
                            "转录：有一部分没做好",
                            "文字稿已经写出来了，但是：\n\n" + "\n".join(state["notes"]),
                            parent=dialog,
                        )
                    if self._copy_path_to_clipboard(state["path"]):
                        hint.config(text=f"转录文字已拷到剪贴板：{os.path.basename(state['path'])}")
                        messagebox.showinfo(
                            "转录",
                            "转好了。剪贴板里现在是带时间戳的文字文件：\n"
                            + os.path.basename(state["path"]),
                            parent=dialog,
                        )
                    else:
                        hint.config(text="转录好了，但文字文件没能拷进剪贴板")

                def _poll():
                    try:
                        if not prog.winfo_exists():
                            return
                        prog_label.config(text=state["message"])
                        bar.config(value=float(state.get("ratio", 0.0)))
                    except tk.TclError:
                        return
                    if bridge.pending():
                        def _before_manual(what):
                            state["message"] = f"自动调用没成功（{what}），请在手动窗口里处理…"
                            try:
                                prog_label.config(text=state["message"])
                                prog.grab_release()
                            except tk.TclError:
                                pass

                        def _after_manual():
                            try:
                                prog.grab_set()
                            except tk.TclError:
                                pass

                        bridge.serve(_before_manual, _after_manual)
                    if state["done"]:
                        _finish()
                        return
                    dialog.after(200, _poll)

                threading.Thread(target=_work, daemon=True).start()
                dialog.after(200, _poll)

            def _offer_transcribe():
                if transcript["running"]:
                    return
                if not messagebox.askyesno(
                    "转录",
                    "媒体已经拷到剪贴板了。\n\n要不要进一步把里面的声音转成文字？\n"
                    "文字每一句前面带时间戳（精确到 0.1 秒）。转好以后，剪贴板里的内容会换成这份文字文件。",
                    parent=dialog,
                ):
                    return
                done_path = transcript.get("path") or ""
                if done_path and os.path.isfile(done_path):
                    if self._copy_path_to_clipboard(done_path):
                        hint.config(text=f"转录文字已拷到剪贴板：{os.path.basename(done_path)}")
                    return
                _run_transcribe()

            def _copy_attachment():
                if file_kind in ("audio", "video"):
                    from utility import media_transcript

                    existing = media_transcript.find_transcript_for_media(attachment)
                    if existing:
                        # 已经有文字稿：让用户选拷媒体还是拷文字稿，不再问要不要转录。
                        choice = media_transcript.ask_copy_choice(
                            dialog, os.path.basename(attachment), os.path.basename(existing)
                        )
                        if not choice:
                            return
                        target = existing if choice == "transcript" else attachment
                        if self._copy_path_to_clipboard(target):
                            what = "文字稿" if choice == "transcript" else "媒体"
                            hint.config(text=f"{what}已拷到剪贴板：{os.path.basename(target)}")
                        else:
                            hint.config(text="拷贝失败")
                        return
                if self._copy_path_to_clipboard(attachment):
                    hint.config(text="已拷到剪贴板。可以粘到别处")
                    if file_kind in ("audio", "video"):
                        dialog.after(30, _offer_transcribe)
                else:
                    hint.config(text="拷贝失败")

            click_wait = {"id": None}

            def _on_attachment_click(_event=None):
                if click_wait["id"] is not None:
                    try:
                        dialog.after_cancel(click_wait["id"])
                    except tk.TclError:
                        pass
                click_wait["id"] = dialog.after(280, _copy_attachment)

            def _on_attachment_double(_event=None):
                if click_wait["id"] is not None:
                    try:
                        dialog.after_cancel(click_wait["id"])
                    except tk.TclError:
                        pass
                    click_wait["id"] = None
                if file_kind == "pdf":
                    _copy_attachment()
                elif _attachment_playing():
                    _stop_attachment()
                else:
                    _start_attachment()
                return "break"

            for widget in (input_box, info, hint, pic):
                widget.bind("<Button-1>", _on_attachment_click)
                widget.bind("<Double-Button-1>", _on_attachment_double)
            dialog.bind("<Destroy>", _on_dialog_destroy, add="+")
            dialog._llm_dialog_photo_ref = photo_ref

            reply_box = ttk.LabelFrame(right_col, text="返回的图（双击从剪贴板粘贴）", padding=8)
            reply_box.grid(row=1, column=0, sticky="nsew")
            reply_hint = ttk.Label(reply_box, text="双击从剪贴板粘贴", font=("TkDefaultFont", 8))
            reply_hint.pack(anchor=tk.W, pady=(0, 4))
            reply_hit = tk.Frame(reply_box, height=160)
            reply_hit.pack(fill=tk.BOTH, expand=True)
            reply_pic = ttk.Label(reply_hit)
            reply_pic.pack(anchor=tk.CENTER, expand=True, fill=tk.BOTH)

            def paste_response_image(_event=None, img=None):
                if img is None:
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
            paste_image_handler[0] = paste_response_image
        elif is_image_mode:
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

            def paste_response_image(_event=None, img=None):
                if img is None:
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
            paste_image_handler[0] = paste_response_image
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

            # 纯文字窗口也能贴回一张图（与图片模式同样的「返回的图」区）。
            right_col.rowconfigure(0, weight=3)
            right_col.rowconfigure(1, weight=1)
            prompt_box.grid_configure(pady=(0, 6))
            photo_ref = []
            reply_box = ttk.LabelFrame(right_col, text="返回的图（双击或 Ctrl+V 从剪贴板粘贴）", padding=8)
            reply_box.grid(row=1, column=0, sticky="nsew")
            reply_hint = ttk.Label(reply_box, text="双击从剪贴板粘贴", font=("TkDefaultFont", 8))
            reply_hint.pack(anchor=tk.W, pady=(0, 4))
            reply_hit = tk.Frame(reply_box, height=120)
            reply_hit.pack(fill=tk.BOTH, expand=True)
            reply_pic = ttk.Label(reply_hit)
            reply_pic.pack(anchor=tk.CENTER, expand=True, fill=tk.BOTH)

            def paste_response_image(_event=None, img=None):
                if img is None:
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
            paste_image_handler[0] = paste_response_image

        def _clipboard_has_text() -> bool:
            try:
                return bool((dialog.clipboard_get() or "").strip())
            except tk.TclError:
                return False

        def on_ctrl_v_image(_event=None):
            """Ctrl+V：剪贴板里是图片（没有文字）时贴到「返回的图」区；有文字时照常贴文字。

            绑定在对话框（toplevel 绑定标签）上，文本框自己的粘贴先执行；剪贴板只有图时那一步什么也不贴。
            """
            handler = paste_image_handler[0]
            if handler is None or _clipboard_has_text():
                return None
            if self._image_from_clipboard() is None:
                return None
            handler()
            return "break"

        dialog.bind("<Control-v>", on_ctrl_v_image, add="+")
        dialog.bind("<Control-V>", on_ctrl_v_image, add="+")

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
            self._last_dialog_cancelled = False
            dialog.destroy()

        def on_cancel():
            self._last_dialog_cancelled = True
            result_model[0] = MANUAL
            result_response[0] = None
            dialog.destroy()

        def on_copy():
            dialog.clipboard_clear()
            dialog.clipboard_append(get_request_copy_content())
            dialog.update()

        # ---- CLI自动：通过 CDP 驱动 Chrome 里的 Grok，自动完成这次手动来回（utility/grok_cdp.py）----
        cli_status = ttk.Label(model_frame, text="", font=("TkDefaultFont", 9), foreground="#1f5fbf")
        cli_status.pack(anchor=tk.W, pady=(2, 0))
        cli_busy = [False]
        cli_btn_ref = [None]

        def _cli_ui(fn):
            """后台线程改界面一律交给主线程（同 _show_model_dialog_from_thread 的做法）。"""
            def _run():
                try:
                    if dialog.winfo_exists():
                        fn()
                except tk.TclError:
                    pass
            try:
                dialog.after(0, _run)
            except Exception:
                pass

        def _cli_set_status(text, color="#1f5fbf"):
            _cli_ui(lambda: cli_status.config(text=text, foreground=color))

        def _cli_done_ui():
            cli_busy[0] = False
            if cli_btn_ref[0] is not None:
                cli_btn_ref[0].state(["!disabled"])

        def on_cli_auto():
            """有图：Grok Imagine 以图生图，结果进「返回的图」。没图：grok.com 对话，结果进「响应」。然后点完成。
            失败时只显示错误，窗口照旧可以手动粘贴。"""
            if cli_busy[0]:
                return
            if file_kind:
                cli_status.config(text="CLI自动 不支持 PDF / 音频 / 视频附件，请手动操作", foreground="#c00000")
                return
            prompt = get_request_copy_content()
            image_path = image_paths[0] if image_paths else ""
            selected_model.set(MANUAL)
            cli_busy[0] = True
            if cli_btn_ref[0] is not None:
                cli_btn_ref[0].state(["disabled"])
            cli_status.config(text="CLI自动 开始 …", foreground="#1f5fbf")

            def _work():
                try:
                    from . import grok_cdp

                    if image_path:
                        img = grok_cdp.make_image(prompt, image_path, status=_cli_set_status)

                        def _apply_image():
                            _cli_done_ui()
                            handler = paste_image_handler[0]
                            if handler is not None:
                                handler(img=img)
                            else:
                                response_image[0] = img
                            cli_status.config(text="CLI自动 完成", foreground="#1f7f1f")
                            on_ok()

                        _cli_ui(_apply_image)
                    else:
                        text = grok_cdp.ask_text(prompt, status=_cli_set_status)
                        if not (text or "").strip():
                            raise RuntimeError("Grok 返回了空回答")

                        def _apply_text():
                            _cli_done_ui()
                            content = file_util.safe_clipboard_json_copy(text) or text
                            response_text.delete("1.0", tk.END)
                            response_text.insert("1.0", content)
                            cli_status.config(text="CLI自动 完成", foreground="#1f7f1f")
                            on_ok()

                        _cli_ui(_apply_text)
                except Exception as exc:
                    msg = f"CLI自动 失败：{exc}（可以继续手动粘贴）"
                    print(f"❌ {msg}")

                    def _fail():
                        _cli_done_ui()
                        cli_status.config(text=msg, foreground="#c00000")

                    _cli_ui(_fail)

            threading.Thread(target=_work, name="grok-cli-auto", daemon=True).start()

        action_box = ttk.Frame(model_btn_row)
        action_box.pack(side=tk.RIGHT)
        ttk.Button(action_box, text=ok_text, command=on_ok).pack(side=tk.RIGHT, padx=(6, 0), pady=2)
        ttk.Button(action_box, text=cancel_text, command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0), pady=2)
        ttk.Button(action_box, text="重新拷贝提示词", command=on_copy).pack(side=tk.RIGHT, pady=2)
        cli_btn = ttk.Button(action_box, text="CLI自动", command=on_cli_auto)
        cli_btn.pack(side=tk.RIGHT, padx=(0, 6), pady=2)
        cli_btn_ref[0] = cli_btn
        ttk.Separator(model_btn_row, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=48, pady=2)

        on_copy()
        dialog.wait_window()
        model = result_model[0] if result_model[0] is not None else GEMINI
        response = result_response[0] if result_response[0] is not None else None
        return model, response


