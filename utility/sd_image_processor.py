import json
import base64
import requests
from PIL import Image
from io import BytesIO
from rembg import remove
import os
import config
from pathlib import Path
import threading
# VIDEO_WIDTH and VIDEO_HEIGHT are now obtained from project config via ffmpeg_processor
from typing import Dict, Any
import config_prompt
from . import llm_api
from .file_util import get_file_path, build_scene_media_prefix, safe_copy_overwrite
from project_manager import refresh_scene_media
import subprocess


GEN_CONFIG = {
        #"Story":{"url": "http://10.0.0.179:8188", "model": "banana", "seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":"\\\\10.0.0.179\\wan22\\ComfyUI\\user\\default\\workflows\\nano_banana.json"},
        #"Story":{"url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent", "model": "banana", "seed": 1234567890, "steps": 4, "cfg": 1.0},
        "Story":{"url": "http://10.0.0.x:8188",                        "face": "flux","seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":"\\\\10.0.0.179\\wan22\\ComfyUI\\user\\default\\workflows\\flux_workflow.json"},
        "Host": {"url": "http://10.0.0.x:8188",                        "face": "flux","seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":"\\\\10.0.0.179\\wan22\\ComfyUI\\user\\default\\workflows\\flux_workflow_figure.json"},
        "SD":   {"url": "http://10.0.0.x:7860/sdapi/v1/txt2img",       "face": "sd",  "seed": 1234567890, "steps": 30,"cfg": 7.0},

        "I2V":    {"url": "http://10.0.0.231:9001/wan/image2video",    "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":16, "frame_rate":15, "max_frames":91,  "image_width":704, "image_height":400},
        "2I2V":   {"url": "http://10.0.0.231:9001/wan/imagesss2video", "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":4,  "frame_rate":15, "max_frames":91,  "image_width":704, "image_height":400},

        "HS2V":   {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":196, "image_width":720, "image_height":405},
        "S2V":    {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":226, "image_width":672, "image_height":378},
        "FS2V":   {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":4,  "frame_rate":15, "max_frames":316, "image_width":570, "image_height":321},
        "WS2V":   {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":91,  "image_width":468, "image_height":480},
        #"FS2V": {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "model": "wan", "seed": 1234567890, "steps": 4, "cfg": 1.0, "motion_frame":5,  "frame_rate":15, "max_frames":121, "image_width":683, "image_height":384},
        "AI2V":   {"url": "http://10.0.0.231:9001/wan/action_transfer","face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":121, "image_width":853, "image_height":480},
        "INTP":   {"url": "http://10.0.0.235:9001/interpolate",        "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":60, "max_frames":121, "image_width":853, "image_height":480}
}


class SDProcessor:


    """
    图像处理流水线类，提供图像卡通化、背景移除等功能
    """
    def __init__(self, workflow):
        self.prompt_url = ""
        self.prompt_model = ""


        self.workflow = workflow
        # Get video dimensions from ffmpeg_processor (will be set after workflow initialization)
        # For now, use default values - they will be updated when workflow is created
        
        self.llm_api = llm_api.LLMApi()

        # Set default image dimensions to match video dimensions
        self.wan_vidoe_count = 0
        self.infinite_vidoe_count = 0


    def resize_image(self, image, width, height):
        """调整图像大小并处理EXIF方向"""
        # 首先将base64字符串解码为二进制数据
        if isinstance(image, str):
            # 如果是base64编码的字符串，先解码
            image_data = base64.b64decode(image)
        else:
            image_data = image
            
        # 打开图像
        img = Image.open(BytesIO(image_data))
        
        try:
            exif = img._getexif()
            if exif:
                # EXIF方向标签
                orientation_tag = 274  # 0x0112
                if orientation_tag in exif:
                    orientation = exif[orientation_tag]
                    # 根据不同的方向值旋转图像
                    if orientation == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation == 6:
                        img = img.rotate(270, expand=True)
                    elif orientation == 8:
                        img = img.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError):
            pass
        
        # 转换为RGBA并调整大小
        img = img.convert("RGBA")
        resized_img = img.resize(
            (int(width), int(height)),
            Image.LANCZOS
        )
        return resized_img


    def cartoonizeImage(self, image_b64, image_dimen, description, denoising):
        """将图像卡通化处理"""
        if image_dimen[0] > image_dimen[1]:
            width = 512
            height = 512*image_dimen[1]/image_dimen[0]
        else:
            width = 512*image_dimen[0]/image_dimen[1]
            height = 512

        positive = "pixar art style \n\n---------------\n\n" + description
        negative = "worst quality, low quality, normal quality, lowres, low details, oversaturated, undersaturated, overexposed, underexposed, grayscale, bw, bad photo, bad photography, bad art:1.4), (watermark, signature, text font, username, error, logo, words, letters, digits, autograph, trademark, name)"
        payload = {
            "init_images": [image_b64],
            "prompt": positive,
            "negative_prompt": negative,
            "steps": 30,
            "denoising_strength": denoising,  # 0.3–0.7 is typical
            "cfg_scale": 7.0,
            "width": width,
            "height": height,
            "seed": 1234567890,
            "sampler_name": "Euler a"  #"DPM++ 2M" "DPM++ 2M SDE Heun" 
            #"sd_model_checkpoint": "cartoon_model.ckpt",  # Optional if already loaded
        }

        # Generate curl command for debugging
        self._save_curl_command(GEN_CONFIG['SD']['url'], payload, "img2img")
        
        # Send request to AUTOMATIC1111 API
        response = requests.post(GEN_CONFIG['SD']['url'], json=payload, timeout=60)

        # Get and decode result
        r = response.json()

        resized_img = self.resize_image(r['images'][0], image_dimen[0], image_dimen[1])

        buffer = BytesIO()
        resized_img.save(buffer, format="PNG")
        return buffer.getvalue()


    def text2Image_sd(self, positive, negative, url, cfg, seed, steps, width, height):
        print(f"🖼️ 准备发送到IMAGE服务器{url}的图像尺寸: {width}x{height}")
        
        # 如果 prompt 是字典，转换为 JSON 字符串
        if isinstance(positive, dict):
            import json
            positive = json.dumps(positive, ensure_ascii=False)
        if isinstance(negative, dict):
            import json
            negative = json.dumps(negative, ensure_ascii=False)
        
        payload = {
            "prompt": positive,
            "negative_prompt": negative,
            "cfg_scale": cfg,
            "width": width,
            "height": height,
            "steps": steps,
            "seed": seed,
            "sampler_name": "Euler a"
        }
        # Generate curl command for debugging
        self._save_curl_command(url, payload, "txt2img")

        try:
            response = requests.post(url, json=payload, timeout=90)
            # Get and decode result
            r = response.json()
            image_b64 = r['images'][0]
            # 解码base64图像数据
            print(f"🔍 开始解码base64图像数据，长度: {len(image_b64)}")
            return base64.b64decode(image_b64)
        except Exception as e:
            print(f"❌ 图像缩放失败: {str(e)}")
            return None

    
    def text2Image_banana(self, url, workflow, positive, negative, image_list=None, width=None, height=None, cfg=None, seed=None, steps=None):
        """使用 Banana 模型生成文本到图像
        Returns:
            bytes: 生成的图像数据，失败时返回 None
        """
        pass


    def png_to_base64(self, image_path):
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded_string}"


    def remove_background(self, image_data):
        """去除图像背景"""
        removed = remove(image_data)
        # reduce the size to get ride of empty top bottom left right 
        
        # 转换为PIL图像
        img = Image.open(BytesIO(removed))
        
        # 获取非透明区域的边界
        # 创建图像的alpha通道
        alpha = img.getchannel('A')
        
        # 找到非透明像素的边界
        bbox = alpha.getbbox()
        
        if bbox:
            # 裁剪图像，只保留非透明部分
            cropped_img = img.crop(bbox)
            
            # 将裁剪后的图像保存到内存中
            output = BytesIO()
            cropped_img.save(output, format='PNG')
            output.seek(0)
            
            return output.getvalue()
        
        # 如果没有找到非透明区域，则返回原始图像
        return removed


    def save_image(self, image, filename, format="WEBP"):
        if os.path.exists(filename):
            os.remove(filename)
        # if image instanceof Image, then save it
        if isinstance(image, Image.Image):
            image.save(filename, format=format)
            return filename
        
        img = Image.open(BytesIO(image))
        img.save(filename, format=format)
        return filename


    def read_image(self, image_path):
        with open(image_path, "rb") as input_file:
            return input_file.read()


    def add_image_to_image(self, top_image, background_image, position):
        try:
            from PIL import Image
            from io import BytesIO
            
            # Load both images
            bg_img = Image.open(BytesIO(background_image))
            top_img = Image.open(BytesIO(top_image))
            
            # Get background image dimensions
            bg_width, bg_height = bg_img.size
            
            # Calculate target height for top image (3/4 of background height)
            target_height = int(bg_height * 5 / 6)
            
            # Calculate target width to maintain aspect ratio
            top_original_width, top_original_height = top_img.size
            aspect_ratio = top_original_width / top_original_height
            target_width = int(target_height * aspect_ratio)
            
            # Convert top image to binary data for resize_image method
            top_buffer = BytesIO()
            top_img.save(top_buffer, format='PNG')
            top_buffer.seek(0)
            top_binary = top_buffer.getvalue()
            
            # Resize top image to 3/4 of background height while keeping aspect ratio
            top_img = self.resize_image(top_binary, target_width, target_height)
            
            # Convert background to RGBA if it's not already
            if bg_img.mode != 'RGBA':
                bg_img = bg_img.convert('RGBA')
            
            # Convert top image to RGBA if it's not already
            if top_img.mode != 'RGBA':
                top_img = top_img.convert('RGBA')
            
            # Get dimensions (top_img has already been resized)
            top_width, top_height = top_img.size
            
            # Calculate position
            if position.lower() == "right":
                x = bg_width - top_width - 20  # 20px margin from right edge
                y = (bg_height - top_height)  # Center vertically
            elif position.lower() == "left":
                x = 20  # 20px margin from left edge
                y = (bg_height - top_height)  # Center vertically
            elif position.lower() == "center":
                x = (bg_width - top_width) // 2  # Center horizontally
                y = (bg_height - top_height)  # Center vertically
            else:
                # Default to center if position is not recognized
                x = (bg_width - top_width) // 2
                y = (bg_height - top_height) // 2
            
            # Ensure the top image doesn't go outside the background bounds
            x = max(0, min(x, bg_width - top_width))
            y = max(0, min(y, bg_height - top_height))
            
            # Create a copy of the background image
            result_img = bg_img.copy()
            
            # Paste the top image onto the background
            result_img.paste(top_img, (x, y), top_img)
            
            # Convert to binary data
            output = BytesIO()
            result_img.save(output, format='PNG')
            output.seek(0)
            
            return output.getvalue()
            
        except Exception as e:
            print(f"❌ Error adding image to image: {str(e)}")
            # Return the background image if there's an error
            return background_image


    def _save_curl_command(self, url, payload, api_type):
        """生成并保存curl命令用于调试"""
        try:
            debug_dir = os.path.join(config.get_temp_path(self.workflow.pid), "debug_curls")
            os.makedirs(debug_dir, exist_ok=True)
            
            # 生成时间戳用于文件名
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # 毫秒精度
            
            # 生成curl命令 - 根据API类型选择格式
            if api_type == "txt2img" and isinstance(payload, dict) and "prompt" in payload:
                # flux API使用multipart/form-data格式
                curl_command = f'curl --location "{url}" \\\n'
                for key, value in payload.items():
                    curl_command += f'  --form \'{key}="{value}"\' \\\n'
                curl_command = curl_command.rstrip(' \\\n')  # 移除最后的反斜杠
            else:
                # 其他API使用JSON格式
                curl_command = f'curl -X POST "{url}" \\\n'
                curl_command += '  -H "Content-Type: application/json" \\\n'
                curl_command += f'  -d \'{json.dumps(payload, indent=2, ensure_ascii=False)}\''
            
            # 保存到文件
            filename = f"{api_type}_{timestamp}.txt"
            filepath = os.path.join(debug_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# Stable Diffusion API Debug - {api_type.upper()}\n")
                f.write(f"# Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# URL: {url}\n\n")
                f.write("# CURL Command:\n")
                f.write(curl_command)
                if api_type == "txt2img" and isinstance(payload, dict) and "prompt" in payload:
                    f.write("\n\n# Form Data:\n")
                    for key, value in payload.items():
                        f.write(f"{key}: {value}\n")
                else:
                    f.write("\n\n# Payload JSON (formatted):\n")
                    f.write(json.dumps(payload, indent=2, ensure_ascii=False))
                
            print(f"🔧 调试curl命令已保存到: {filepath}")
            
        except Exception as e:
            print(f"⚠️ 保存curl命令时出错: {str(e)}")


    def open_image_as_base64(self, image_path):
        import base64
        from io import BytesIO
        
        # 打开并转换图片为 base64
        image = Image.open(image_path)
        
        # 如果图片太大，先调整大小以节省 token
        max_size = 1024
        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # 处理 RGBA 模式（PNG 透明度）：合成到白色背景
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])  # 使用 alpha 通道作为 mask
            image = background
        elif image.mode not in ('RGB',):
            # 其他模式转换为 RGB
            image = image.convert('RGB')
        
        # 转换为 base64（JPEG 格式）
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return img_base64


    def describe_image(self, img_input):
        """
        使用 OpenAI/Gemini API 描述图片
        
        Args:
            img_input: 可以是文件路径（str）或 base64 字符串（str）
        
        Returns:
            dict: 图片描述数据，失败时返回 None
        """
        try:
            # 如果输入是文件路径，先转换为 base64
            if isinstance(img_input, str):
                # 检查是否是文件路径（文件存在，或包含路径分隔符）
                if os.path.exists(img_input):
                    # 确认是文件路径，转换为 base64
                    img_base64 = self.open_image_as_base64(img_input)
                elif '/' in img_input or '\\' in img_input:
                    # 包含路径分隔符但文件不存在，尝试作为文件路径处理
                    # 如果失败会在 open_image_as_base64 中抛出异常
                    img_base64 = self.open_image_as_base64(img_input)
                else:
                    # 假设是 base64 字符串
                    img_base64 = img_input
            else:
                raise ValueError("img_input 必须是文件路径（str）或 base64 字符串（str）")
            
            # 清理 base64 字符串（移除可能的换行符、空格和 data URI 前缀）
            img_base64 = img_base64.strip()
            # 如果包含 data URI 前缀，移除它
            if img_base64.startswith('data:image'):
                img_base64 = img_base64.split(',', 1)[1] if ',' in img_base64 else img_base64
            # 移除所有空白字符
            img_base64 = img_base64.replace('\n', '').replace('\r', '').replace(' ', '').replace('\t', '')
            
            system_prompt = config_prompt.IMAGE_DESCRIPTION_SYSTEM_PROMPT
            user_prompt = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_base64}"
                    }
                }
            ]
            return self.llm_api.generate_json(system_prompt, user_prompt, "describe_image_response.txt", False)

        except Exception as e:
            print(f"❌ 图片描述失败: {str(e)}")
            return None


    def two_image_to_video(self, prompt, file_prefix, first_frame, last_frame, sound_path) :
        server_config = GEN_CONFIG["2I2V"]
        num_frames = server_config["frame_rate"] * self.workflow.ffmpeg_audio_processor.get_duration(sound_path) + 1
        if num_frames > server_config["max_frames"]:
            num_frames = server_config["max_frames"]

        # 如果 prompt 是字典，转换为 JSON 字符串
        if isinstance(prompt, dict):
            import json
            prompt = json.dumps(prompt, ensure_ascii=False)

        data = {
            'prompt': prompt,
            "negative_prompt": "",
            'filename_prefix': file_prefix,

            'image_width': server_config["image_width"] if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height else server_config["image_height"],
            'image_height': server_config["image_height"] if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height else server_config["image_width"],

            "cfg_scale": server_config["cfg"],
            "steps": server_config["steps"],
            "seed": server_config["seed"],

            'motion_frame': server_config["motion_frame"],
            'frame_rate': server_config["frame_rate"],
            'num_frames': int(num_frames)
        }

        files = {
            'first_frame': first_frame,
            'last_frame': last_frame
        }
        self.post_multipart(
            data=data,
            files=files,
            full_url=server_config["url"]
        )
        self.wan_vidoe_count += 1


    def action_transfer_video(self, prompt, file_prefix, image_path, sound_path, action_path) :
        duration = self.workflow.ffmpeg_audio_processor.get_duration(sound_path)
        if duration <= 0.0:
            print(f"🔴 音频时长为0")
            return

        if isinstance(prompt, dict):
            import json
            prompt = json.dumps(prompt, ensure_ascii=False)

        server_config = GEN_CONFIG["AI2V"]
        fps = server_config["frame_rate"]

        action_path = self.workflow.ffmpeg_processor.refps_video(action_path, fps)

        num_frames = int(duration * fps)
        max_frames = server_config["max_frames"]
        if num_frames > max_frames:
            num_frames = max_frames

        data = {
            'prompt': prompt,
            "negative_prompt": "",
            'filename_prefix': file_prefix,

            'image_width': server_config["image_width"] if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height else server_config["image_height"],
            'image_height': server_config["image_height"] if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height else server_config["image_width"],

            "cfg_scale": server_config["cfg"],
            "steps": server_config["steps"],
            "seed": server_config["seed"],

            'motion_frame': server_config["motion_frame"],
            'frame_rate': fps,
            'num_frames': int(num_frames)
        }

        files = {
            'image': image_path,
            'action': action_path
        }
        self.post_multipart(
            data=data,
            files=files,
            full_url=server_config["url"]
        )
        self.infinite_vidoe_count += 1


    def sound_to_video(self, prompt, file_prefix, image_path, sound_path, next_sound_path, animate_mode, silence=False) :
        # 如果 prompt 是字典，转换为 JSON 字符串
        if isinstance(prompt, dict):
            import json
            prompt = json.dumps(prompt, ensure_ascii=False)

        server_config = GEN_CONFIG[animate_mode]

        if not silence:
            fps = server_config["frame_rate"]
            max_frames = server_config["max_frames"]
            duration = self.workflow.ffmpeg_audio_processor.get_duration(sound_path)

            if next_sound_path:
                batch_sec = (max_frames-3.0)/fps
                batches = int(duration/batch_sec)
                remind_sec = duration - batches*batch_sec
                add_sec = batch_sec - remind_sec - 0.15
                if add_sec > 0.0:
                    next_sound_path = self.workflow.ffmpeg_audio_processor.audio_cut_fade(next_sound_path, 0, add_sec)
                    sound_path = self.workflow.ffmpeg_audio_processor.concat_audios([sound_path, next_sound_path])
                    duration = self.workflow.ffmpeg_audio_processor.get_duration(sound_path)
            # if int(duration*fps)+1 <= max_frames:
            #    max_frames = int(duration*fps)+1
            #    if max_frames % fps == 0:
            #        max_frames += 1
        else:    
            fps = server_config["frame_rate"]//2
            max_frames = int(server_config["max_frames"]//2)
            if max_frames % 2 == 0:
                max_frames += 1
            duration = self.workflow.ffmpeg_audio_processor.get_duration(sound_path)
            sound_path = self.workflow.ffmpeg_audio_processor.make_silence(duration)

        #num_frames = int(duration * fps)
        #if num_frames % 2 == 0:
        #    num_frames += 1
        #if num_frames > max_frames:
        #    num_frames = max_frames

        data = {
            'prompt': prompt,
            "negative_prompt": "",
            'filename_prefix': file_prefix,

            'image_width': server_config["image_width"] if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height else server_config["image_height"],
            'image_height': server_config["image_height"] if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height else server_config["image_width"],

            "cfg_scale": server_config["cfg"],
            "steps": server_config["steps"],
            "seed": server_config["seed"],

            'motion_frame': server_config["motion_frame"],
            'frame_rate': fps,
            'num_frames': int(max_frames)
        }

        files = {
            'image': image_path,
            'sound': sound_path
        }
        self.post_multipart(
            data=data,
            files=files,
            full_url=server_config["url"]
        )
        self.infinite_vidoe_count += 1


    def image_to_video(self, prompt, file_prefix, image_path, sound_path) :
        server_config = GEN_CONFIG["I2V"]
        num_frames = server_config["frame_rate"] * self.workflow.ffmpeg_audio_processor.get_duration(sound_path) + 1
        if num_frames > server_config["max_frames"]:
            num_frames = server_config["max_frames"]
        
        # 如果 prompt 是字典，转换为 JSON 字符串
        if isinstance(prompt, dict):
            import json
            prompt = json.dumps(prompt, ensure_ascii=False)
        
        data = {
            'prompt': prompt,
            "negative_prompt": "",
            'filename_prefix': file_prefix,

            'image_width': server_config["image_width"] if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height else server_config["image_height"],
            'image_height': server_config["image_height"] if self.workflow.ffmpeg_processor.width > self.workflow.ffmpeg_processor.height else server_config["image_width"],
            
            "cfg_scale": server_config["cfg"],
            "steps": server_config["steps"],
            "seed": server_config["seed"],
            
            'motion_frame': server_config["motion_frame"],
            'frame_rate': server_config["frame_rate"],
            'num_frames': int(num_frames)
        }
        files = {
            'first_frame': image_path
        }

        self.post_multipart(
            data=data,
            files=files,
            full_url=server_config["url"]
        )
        self.wan_vidoe_count += 1


    def enhance_clip(self, pid, scene, track, level:str):
        status = scene.get(track + "_status", "")
        print(f"enhance_clip {track} status: {status}")
        if status == "ENH2":
            return

        fps = scene.get(track + "_fps", 15)
        if fps > 24:
            fps = 15

        animate_mode = scene.get(track + "_animation", "")

        if animate_mode in config_prompt.ANIMATE_WS2V:
            left_input = get_file_path(scene, track + "_left")
            right_input = get_file_path(scene, track + "_right")
            if left_input and right_input:
                left_input = self.workflow.ffmpeg_processor.refps_video(left_input, fps)
                right_input = self.workflow.ffmpeg_processor.refps_video(right_input, fps)
                enhance_left_input = build_scene_media_prefix(pid, scene["id"], track, "ENH", True)
                enhance_left_input = config.get_temp_file(self.pid, "mp4", enhance_left_input + "_" + level + "_")
                safe_copy_overwrite(left_input, enhance_left_input)
                self._enhance_video(enhance_left_input)

                enhance_right_input = build_scene_media_prefix(pid, scene["id"], track, "ENH", True)
                enhance_right_input = config.get_temp_file(self.pid, "mp4", enhance_right_input + "_" + level + "_")
                safe_copy_overwrite(right_input, enhance_right_input)
                self._enhance_video(enhance_right_input)
                scene[track + "_status"] = "ENH1"
        else:
            input = get_file_path(scene, track)
            if input:
                input = self.workflow.ffmpeg_processor.refps_video(input, fps)
                enhance_input = build_scene_media_prefix(pid, scene["id"], track, "ENH", True)
                enhance_input = config.get_temp_file(pid, "mp4", enhance_input+"_"+level+"_")
                safe_copy_overwrite(input, enhance_input)
                self._enhance_video(enhance_input)
                scene[track + "_status"] = "ENH1"

 
    ENHANCE_SERVERS = ["http://10.0.0.210:5000", "http://10.0.0.235:5000", "http://10.0.0.210:5000", "http://10.0.0.235:5000", "http://10.0.0.235:5000",]
    current_enhance_server = 0

    def _enhance_video(self, video_path):
        """调用 REST API 增强单个视频"""
        try: # clip_project_20251208_1710_10708_S2V_13225050_original.mp4
            url = self.ENHANCE_SERVERS[self.current_enhance_server] + "/enhance"
            self.current_enhance_server = (self.current_enhance_server + 1) % len(self.ENHANCE_SERVERS)
            
            with open(video_path, 'rb') as video_file:
                files = {'video': video_file}
                
                print(f"🚀 正在调用视频增强API: {url}")
                response = requests.post(url, files=files, timeout=300)
                
                if response.status_code >= 200 and response.status_code < 300:
                    print("✅ 单视频增强成功")
                    print(f"📄 响应: {response.text}")
                else:
                    print(f"❌ 单视频增强失败，状态码: {response.status_code}")
                    print(f"📄 错误信息: {response.text}")
                    
        except requests.exceptions.RequestException as e:
            print(f"❌ REST API 调用失败: {str(e)}")
        except Exception as e:
            print(f"❌ 增强单视频时出错: {str(e)}")


    def _enhance_image_in_bat(self, image_path, face_weight=0.3):
        # 获取当前脚本所在目录的父目录（项目根目录），然后拼接 Real-ESRGAN 子文件夹
        #project_root = Path("__file__").parent.parent
        enhancer_root = Path("/ImageEnhance")
        realesrgan_python = enhancer_root / "venv" / "Scripts" / "python.exe"

        temp_path = config.get_temp_path(self.workflow.pid)
        face_args = f"--face_enhance --face_enhance_weight {face_weight}"  if face_weight > 0.09 else ""
        # Use explicit Python path to ensure we use the correct version
        batch_content = f"""
cd {enhancer_root}
call venv\\Scripts\\activate.bat
{str(realesrgan_python)} inference_realesrgan.py -n RealESRGAN_x2plus -i {image_path} -o {temp_path} --suffix out  {face_args}
"""
        batch_file = config.get_temp_file(self.workflow.pid, "bat")
        with open(batch_file, 'w', encoding='utf-8') as f:
            f.write(batch_content)

        result = subprocess.run([str(batch_file)], shell=True, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore', cwd=str(enhancer_root))
        print(f"Real-ESRGAN batch script return code: {result.returncode}")

        temp_output = temp_path +"/" + Path(image_path).stem + "_out" + Path(image_path).suffix
        return self.workflow.ffmpeg_processor.resize_image_smart(temp_output)


    def _enhance_image_in_api(self, image_path, face_enhance_weight=0.3):
        output_path = config.get_temp_file(self.workflow.pid, "webp")
        #url = "http://10.0.0.216:5050/enhance"
        url = os.getenv("ENHANCE_API_URL", "")
        
        # 打开图片文件
        with open(image_path, 'rb') as f:
            files = {'image': f}
            data = {
                'face_enhance_weight': face_enhance_weight
            }
            
            # 发送请求
            response = requests.post(url, files=files, data=data)
        
        # 检查响应
        if response.status_code == 200:
            # 保存增强后的图片
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ 图片增强成功！输出: {output_path}")
            return self.workflow.ffmpeg_processor.resize_image_smart(output_path)
        else:
            error_msg = response.json().get('error', 'Unknown error')
            print(f"❌ 错误: {error_msg}")
            return None


    def post_multipart(self, 
                      full_url: str, 
                      data: Dict[str, Any] = None,
                      files: Dict[str, str] = None) -> requests.Response:
        # Prepare form data
        form_data = data.copy() if data else {}
        
        # Prepare files for upload
        files_to_upload = {}
        if files:
            for field_name, file_path in files.items():
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"File not found: {file_path}")
                # Open file and add to upload
                files_to_upload[field_name] = open(file_path, 'rb')
        
        try:
            response = requests.post(
                full_url,
                data=form_data,
                files=files_to_upload,
                timeout=60
            )
            
            return response
            
        finally:
            # Close all opened files
            for file_obj in files_to_upload.values():
                file_obj.close()

