import json
from utility.zh_convert import to_simplified as _to_simplified  # t210u
import base64
import requests
from PIL import Image
from datetime import datetime
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
import subprocess


# DEPRECATED: I2V / 2I2V / S2V / WS2V / AI2V / INTP 和下面的 enhance_clip 已不从界面调用。
# 代码留在这里，免得以后想接回主动画、次动画、增主轨时找不到。
# 地址都来自 config「服务地址」段（.env 可改）；10.0.0.x 是不可达的占位地址。
GEN_CONFIG = {
        #"Story":{"url": "http://10.0.0.179:8188", "model": "banana", "seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":"\\\\10.0.0.179\\wan22\\ComfyUI\\user\\default\\workflows\\nano_banana.json"},
        #"Story":{"url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent", "model": "banana", "seed": 1234567890, "steps": 4, "cfg": 1.0},
        "Story":{"url": config.COMFYUI_URL,                        "face": "flux","seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":os.path.join(config.COMFYUI_WORKFLOW_DIR, "flux_workflow.json")},
        "Host": {"url": config.COMFYUI_URL,                        "face": "flux","seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":os.path.join(config.COMFYUI_WORKFLOW_DIR, "flux_workflow_figure.json")},
        "SD":   {"url": config.SD_WEBUI_URL + "/sdapi/v1/txt2img",       "face": "sd",  "seed": 1234567890, "steps": 30,"cfg": 7.0},

        "I2V":    {"url": config.WAN_I2V_URL + "/wan/image2video",    "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":16, "frame_rate":15, "max_frames":91,  "image_width":704, "image_height":400},
        "2I2V":   {"url": config.WAN_I2V_URL + "/wan/imagesss2video", "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":4,  "frame_rate":15, "max_frames":91,  "image_width":704, "image_height":400},

        #"HS2V":   {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":120, "image_width":922, "image_height":518},
        "HS2V":   {"url": config.WAN_S2V_URL + "/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":196, "image_width":720, "image_height":405},
        "S2V":    {"url": config.WAN_S2V_URL + "/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":226, "image_width":672, "image_height":378},
        "FS2V":   {"url": config.WAN_S2V_URL + "/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":4,  "frame_rate":15, "max_frames":335, "image_width":550, "image_height":310},
        "WS2V":   {"url": config.WAN_S2V_URL + "/wan/infinite_s2v",   "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":91,  "image_width":468, "image_height":480},
        #"FS2V": {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "model": "wan", "seed": 1234567890, "steps": 4, "cfg": 1.0, "motion_frame":5,  "frame_rate":15, "max_frames":121, "image_width":683, "image_height":384},
        "AI2V":   {"url": config.WAN_I2V_URL + "/wan/action_transfer","face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":15, "max_frames":121, "image_width":853, "image_height":480},
        "INTP":   {"url": config.INTERP_URL + "/interpolate",        "face": "66", "seed": 1234567890, "steps": 4, "cfg": 0.5, "motion_frame":5,  "frame_rate":60, "max_frames":121, "image_width":853, "image_height":480}
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


    def two_image_to_video(self, prompt, file_prefix, first_frame, last_frame, sound_path) :
        prompt = _to_simplified(prompt)  # t210u: 送出前转简体
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
        prompt = _to_simplified(prompt)  # t210u: 送出前转简体
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
        prompt = _to_simplified(prompt)  # t210u: 送出前转简体
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
        prompt = _to_simplified(prompt)  # t210u: 送出前转简体
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
        """DEPRECATED: 界面上的增主轨已拿掉。这段增强代码留着。"""
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

 
    ENHANCE_SERVERS = list(config.ENHANCE_SERVERS) or ["http://10.0.0.235:5000"]
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
        
        # Prepare files for upload (keep file paths for curl dump)
        files_to_upload = {}
        file_paths_for_curl = {}  # field_name -> file_path
        if files:
            for field_name, file_path in files.items():
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"File not found: {file_path}")
                file_paths_for_curl[field_name] = file_path
                files_to_upload[field_name] = open(file_path, 'rb')

        # Write equivalent curl command to project temp folder for debugging
        try:
            temp_dir = config.get_temp_path(self.workflow.pid)
            curl_filename = datetime.now().strftime("%Y%m%d%H%M%S") + ".txt"
            curl_path = os.path.join(temp_dir, curl_filename)
            curl_parts = ["curl", "-X", "POST", "--timeout", "60"]
            for k, v in form_data.items():
                curl_parts.append("-F")
                v_esc = str(v).replace('\\', '\\\\').replace('"', '\\"')
                curl_parts.append(f'"{k}={v_esc}"')
            for field_name, path in file_paths_for_curl.items():
                curl_parts.append("-F")
                curl_parts.append(f'"{field_name}=@{path}"')
            curl_parts.append(f'"{full_url}"')
            with open(curl_path, "w", encoding="utf-8") as cf:
                cf.write(" ".join(curl_parts))
        except Exception as e:
            pass  # ignore curl dump errors

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


# ---------------------------------------------------------------------------
# t148u: ComfyUI HTTP API — MiniMax H3 图生视频（workflow/MiniMax_H3_api.json）
# ---------------------------------------------------------------------------
# API 格式的工作流来自 ComfyUI 里一次成功运行（/history），节点按 class_type 找，不靠写死的 id：
#   MiniMaxH3ImageToVideo : prompt / width / height / first_frame（新加的 LoadImage 接进来）
#   PrimitiveFloat        : 秒数（ComfyMathExpression 换算帧数：24fps，至少 5 帧，向上取到 17n+5）
#   RandomNoise           : noise_seed
#   CreateVideo           : fps（帧数公式按 24fps 写死，改 fps 只改播放速度和时长）
#   SaveVideo             : filename_prefix；结果从 /history 的 outputs 里取，/view 下载
# t155u: 可选 last_frame（结束图，新加 LoadImage）；可选配音：LoadAudio → PixaromaH3AudioSync（插在模型/latent 和
#   采样之间，用工作流里的音频 VAE），把真实录音放进 H3 的声音部分、画面跟着对口型；CreateVideo 用它输出的音轨。
MINIMAX_H3_API_WORKFLOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "workflow", "MiniMax_H3_api_5070.json")  # t188u: 默认 5070；按选项传 workflow_path
MINIMAX_H3_FPS = 24


def _align_h3_frames(n: int) -> int:
    """Next legal MiniMax H3 length: 17n+5, at least 5 frames (workflow ComfyMathExpression)."""
    n = max(5, int(n))
    return n + (5 - n % 17) % 17


def minimax_h3_frames(seconds: float, fps: int = MINIMAX_H3_FPS) -> int:
    """和工作流里 ComfyMathExpression 一样：max(5, round(s*fps)) 再向上取到 17n+5（模型要求的帧数）。"""
    return _align_h3_frames(max(5, int(round(float(seconds) * fps))))


def _find_nodes(prompt: Dict[str, Any], class_type: str) -> list:
    return [k for k, v in prompt.items() if v.get("class_type") == class_type]


def _one_node(prompt: Dict[str, Any], class_type: str) -> str:
    ids = _find_nodes(prompt, class_type)
    if len(ids) != 1:
        raise ValueError(f"MiniMax H3 工作流里 {class_type} 节点应有 1 个，实际 {len(ids)} 个")
    return ids[0]


def build_minimax_h3_prompt(workflow: Dict[str, Any], *, image_name: str, prompt: str, seconds: float,
                            width: int, height: int, seed: int, fps=None, filename_prefix: str = "video/MiniMax_H3",
                            negative=None, last_image_name=None, audio_name=None,
                            ref_image_names=None) -> Dict[str, Any]:
    """把 API 格式工作流复制一份并填入参数（纯函数，可离线测）。image_name 是 /upload/image 返回的文件名。
    t216u: 工作流里是 MiniMaxH3ReferenceToVideo（R2V）时：场景图 = ref_image_0（<Picture 1>），
    ref_image_names（人物肖像）依次接 ref_image_1..（<Picture 2>..），最多共 9 张；
    再用 MiniMaxH3AddGuide 把场景图钉在第 0 帧（有结束图就钉在最后一帧）。"""
    import copy

    wf = copy.deepcopy(workflow)
    if width % 32 or height % 32:
        raise ValueError(f"MiniMax H3 的宽高必须是 32 的倍数（给的是 {width}x{height}）")
    if _find_nodes(wf, "MiniMaxH3ReferenceToVideo"):
        return _build_minimax_h3_r2v(wf, image_name=image_name, prompt=prompt, seconds=seconds, width=width,
                                     height=height, seed=seed, fps=fps, filename_prefix=filename_prefix,
                                     last_image_name=last_image_name, audio_name=audio_name,
                                     ref_image_names=list(ref_image_names or []))
    i2v = _one_node(wf, "MiniMaxH3ImageToVideo")
    text = (prompt or "").strip()
    # t162u: H3 只有正面条件（BasicGuider，没有负面 / CFG），「Avoid: 字幕, 日夜变化」写进去反而会被画出来，所以不加
    if negative is not None:
        try:
            from config_prompt import with_h3_no_subtitle_negative

            negative = with_h3_no_subtitle_negative(negative)  # t238u
        except Exception:  # noqa: BLE001
            pass
        print("[ComfyUI H3] 没有负面提示词输入，negative 不使用（已并入字幕禁词备查）")
    # t165u: H3 首尾帧对齐行里的结束秒数按实际帧数改准（17n+5 帧 / 24fps）
    import re as _re

    _end = minimax_h3_frames(seconds) / float(MINIMAX_H3_FPS)
    text = _re.sub(r"(Picture 2 \(from Shot \d+\) aligns with the )[0-9.]+(-second mark)", lambda m: f"{m.group(1)}{_end:.2f}{m.group(2)}", text)
    wf[i2v]["inputs"].update({"prompt": text, "width": int(width), "height": int(height)})
    load_id = str(max(int(k) for k in wf if str(k).isdigit()) + 1)
    wf[load_id] = {"class_type": "LoadImage", "inputs": {"image": image_name}, "_meta": {"title": "first_frame"}}
    wf[i2v]["inputs"]["first_frame"] = [load_id, 0]
    wf[i2v]["inputs"].pop("last_frame", None)
    if last_image_name:  # t155u: 结束图接到 MiniMaxH3ImageToVideo 的可选 last_frame
        last_id = str(int(load_id) + 1)
        wf[last_id] = {"class_type": "LoadImage", "inputs": {"image": last_image_name}, "_meta": {"title": "last_frame"}}
        wf[i2v]["inputs"]["last_frame"] = [last_id, 0]
    if audio_name:  # t155u: 配音对口型
        audio_vae = wf[_one_node(wf, "VAEDecodeAudio")]["inputs"]["vae"]
        guider = _one_node(wf, "BasicGuider")
        sampler = _one_node(wf, "SamplerCustomAdvanced")
        nid = max(int(k) for k in wf if str(k).isdigit())
        la_id, sync_id = str(nid + 1), str(nid + 2)
        wf[la_id] = {"class_type": "LoadAudio", "inputs": {"audio": audio_name}, "_meta": {"title": "scene_audio"}}
        wf[sync_id] = {"class_type": "PixaromaH3AudioSync",
                       "inputs": {"model": wf[guider]["inputs"]["model"], "latent": [i2v, 1],
                                  "audio_vae": audio_vae, "track": [la_id, 0]},
                       "_meta": {"title": "lip sync"}}
        wf[guider]["inputs"]["model"] = [sync_id, 0]
        wf[sampler]["inputs"]["latent_image"] = [sync_id, 1]
        wf[_one_node(wf, "CreateVideo")]["inputs"]["audio"] = [sync_id, 2]
    wf[_one_node(wf, "PrimitiveFloat")]["inputs"]["value"] = float(seconds)
    wf[_one_node(wf, "RandomNoise")]["inputs"]["noise_seed"] = int(seed)
    if fps:
        wf[_one_node(wf, "CreateVideo")]["inputs"]["fps"] = float(fps)
    wf[_one_node(wf, "SaveVideo")]["inputs"]["filename_prefix"] = filename_prefix
    return wf


def video_size_for(orientation: str, long_side: int = 1024) -> tuple:
    """t152u: 方向 → (宽, 高)：长边 long_side，短边按 16:9 / 9:16 算再取 32 的倍数。portrait → 576x1024。"""
    short = max(32, int(round(long_side * 9 / 16 / 32.0)) * 32)
    return (short, long_side) if str(orientation or "").lower() == "portrait" else (long_side, short)


def _parse_size(text: str, fallback: tuple) -> tuple:
    try:
        a, b = (int(x) for x in str(text).lower().replace("×", "x").split("x"))
        a, b = max(a, b), min(a, b)
        if a % 32 or b % 32 or b < 32:
            raise ValueError
        return a, b
    except Exception:  # noqa: BLE001
        print(f"[ComfyUI H3] 分辨率设置不对（{text}），用 {fallback[0]}x{fallback[1]}")
        return fallback


MINIMAX_LENGTHS = (6, 9, 12)  # 旧 UI 三档名义秒；分辨率门槛仍按 158 / 226 / 294 帧
MINIMAX_MIN_NOMINAL = 5  # 工作流 PrimitiveFloat 默认 5.0 秒（不是产品里发明的更短下限）
MINIMAX_MAX_NOMINAL = 12


def minimax_exact_seconds(seconds) -> float:
    """名义秒数 → 实际生成的秒数（17k+5 帧 / 24fps）：5→5.167，6→6.583，9→9.417，12→12.25。"""
    return minimax_h3_frames(float(seconds)) / MINIMAX_H3_FPS


MINIMAX_MIN_FRAMES = minimax_h3_frames(MINIMAX_MIN_NOMINAL)  # 124 帧 = 5.167 秒
MINIMAX_MAX_FRAMES = minimax_h3_frames(MINIMAX_MAX_NOMINAL)  # 294 帧 = 12.25 秒
MINIMAX_MIN_SECONDS = minimax_exact_seconds(MINIMAX_MIN_NOMINAL)
MINIMAX_MAX_SECONDS = minimax_exact_seconds(MINIMAX_MAX_NOMINAL)  # 294 帧 = 12.25 秒
MINIMAX_AUDIO_MIN_SECONDS = 4.0  # 带场景音频时的现有下限（不是无声自动的 5 秒）
MINIMAX_AUDIO_MIN_FRAMES = minimax_h3_frames(MINIMAX_AUDIO_MIN_SECONDS)  # 107 帧 = 4.458 秒


def minimax_frames_for_speech(speech_seconds: float, fps: int = MINIMAX_H3_FPS,
                             min_frames: int | None = None, max_frames: int | None = None) -> int:
    """台词/目标秒数 → 提交帧数：ceil(s×fps)+1 安全帧，再向上对齐 17n+5。

    默认夹在无声自动的 124–294（5.17–12.25 秒）。带场景音频时传入 min_frames=107（4 秒档）。
    """
    import math

    lo = MINIMAX_MIN_FRAMES if min_frames is None else int(min_frames)
    hi = MINIMAX_MAX_FRAMES if max_frames is None else int(max_frames)
    s = float(speech_seconds or 0)
    if s <= 0:
        return lo
    raw = math.ceil(s * float(fps) - 1e-9) + 1
    return max(lo, min(hi, _align_h3_frames(raw)))


def minimax_seconds_from_frames(frames: int) -> float:
    return int(frames) / float(MINIMAX_H3_FPS)


def minimax_submit_seconds(duration) -> float:
    """Parse extra['duration'] into PrimitiveFloat seconds (legal frames / 24).

    Does **not** snap to 6/9/12. Legacy bucket strings ('6s'/'9s'/'12s', plus
    old 7/10/15 mappings) become that bucket's exact frame length. Numeric
    values (including already-aligned 7.2916…) are aligned via 17n+5 and
    clamped to 124–294 frames so a later builder cannot round them back.
    """
    raw = str(duration or "").strip()
    key = raw.lower()
    if key in ("6s", "7s", "9s", "10s", "12s", "15s"):
        return minimax_exact_seconds(minimax_snap_seconds(key))
    try:
        s = float(key.rstrip("s") or 0)
    except Exception:  # noqa: BLE001
        s = float(MINIMAX_MIN_NOMINAL)
    frames = max(MINIMAX_MIN_FRAMES, min(MINIMAX_MAX_FRAMES, minimax_h3_frames(s)))
    return minimax_seconds_from_frames(frames)


def minimax_snap_seconds(seconds) -> int:
    """t200u/t178u: 任意秒数（含 Grok 的 6 / 10 / 15）→ 最近的 6 / 9 / 12：旧 7→6，10→9，15→12（t179u）。

    只留给旧三档字符串的兼容；动态长度请用 minimax_submit_seconds / minimax_frames_for_speech。
    """
    try:
        s = float(str(seconds).strip().rstrip("sS") or 10)
    except Exception:  # noqa: BLE001
        s = 10.0
    return min(MINIMAX_LENGTHS, key=lambda x: (abs(x - s), x))


def minimax_audio_video_seconds(audio_seconds) -> float:
    """有音频时的视频长度：跟音频走（至少 4 秒），ceil×24 +1 再对齐 17n+5，最长 12.25 秒（294 帧）。"""
    a = float(audio_seconds or 0)
    if a <= 0 or a > MINIMAX_MAX_SECONDS:
        return MINIMAX_MAX_SECONDS
    a = max(MINIMAX_AUDIO_MIN_SECONDS, a)
    frames = minimax_frames_for_speech(
        a, min_frames=MINIMAX_AUDIO_MIN_FRAMES, max_frames=MINIMAX_MAX_FRAMES,
    )
    return minimax_seconds_from_frames(frames)


MINIMAX_6S_MAX_SECONDS = minimax_exact_seconds(6)  # 158 帧 = 6.583 秒，到这为止用 1312x736
MINIMAX_HIRES_MAX_SECONDS = minimax_exact_seconds(9)  # t178u: 9 秒档 226 帧 = 9.417 秒，到这为止用 1280x704


def minimax_size_for(orientation: str, seconds: float, has_audio: bool, audio_seconds=None) -> tuple:
    """返回 (宽, 高, 说明)。t178u: 按实际视频长度挑分辨率：≤ 6.583 秒（6 秒档）1312x736（竖屏 736x1312），≤ 9.417 秒（9 秒档）1280x704（竖屏 704x1280），
    更长（12 秒档）1120x640（竖屏 640x1120）。有音频时长度 = 音频（最长 12.25）。"""
    if has_audio:
        a = float(audio_seconds or 0)
        what = f"音频 {a:.1f} 秒" if a > 0 else "音频时长读不到"
        if a <= 0 or a > MINIMAX_MAX_SECONDS:
            what += f"，按 {MINIMAX_MAX_SECONDS:.2f} 秒"
        real = minimax_audio_video_seconds(a)
    else:
        what = f"{int(round(float(seconds or 0)))}秒"
        real = minimax_exact_seconds(seconds or 0)
    if real <= MINIMAX_6S_MAX_SECONDS + 1e-6:
        long_e, short_e = _parse_size(getattr(config, "MINIMAX_SIZE_6S", "1312x736"), (1312, 736))
    elif real <= MINIMAX_HIRES_MAX_SECONDS + 1e-6:
        long_e, short_e = _parse_size(getattr(config, "MINIMAX_SIZE_XLARGE", "1280x704"), (1280, 704))
    else:
        long_e, short_e = _parse_size(getattr(config, "MINIMAX_SIZE_LARGE", "1120x640"), (1120, 640))  # t252u
    why = what + f"（{minimax_h3_frames(real)} 帧），{long_e}x{short_e}"
    w, h = (short_e, long_e) if str(orientation or "").lower() == "portrait" else (long_e, short_e)
    return w, h, why


def crop_to_aspect(image_path: str, width: int, height: int, out_path: str) -> str:
    """t152u: 居中裁到 width:height 的比例再缩到 width x height（不拉伸），存成 PNG。返回 out_path。"""
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        want = width / float(height)
        if w / float(h) > want:  # 太宽：裁左右
            nw = int(round(h * want))
            box = ((w - nw) // 2, 0, (w - nw) // 2 + nw, h)
        else:  # 太高：裁上下
            nh = int(round(w / want))
            box = (0, (h - nh) // 2, w, (h - nh) // 2 + nh)
        im.crop(box).resize((int(width), int(height)), Image.LANCZOS).save(out_path, "PNG")
    return out_path


def generate_video_comfy(image_path: str, prompt: str, seconds: float, width: int, height: int,
                         negative=None, seed=None, fps=None, output_path=None, server=None,
                         timeout_s: float = 3600.0, status=None, crop: bool = True,
                         audio_path=None, last_image_path=None, workflow_path=None, ref_image_paths=None) -> str:
    """ComfyUI（MiniMax H3）图生视频：上传起始图 → POST /prompt → 轮询 /history → /view 下载 mp4。返回本地路径。
    server 默认 config.COMFYUI_VIDEO_URL；宽高要是 32 的倍数；seed 不给就随机。"""
    try:  # t244: 最重要的禁字幕行必须是第一行（发送前最后一道保障）
        from config_prompt import ensure_video_no_subtitle_first_line
        prompt = ensure_video_no_subtitle_first_line(prompt)
    except Exception as _e:  # noqa: BLE001
        print(f"[ComfyUI H3] 禁字幕第一行注入跳过：{_e}")
    prompt = _to_simplified(prompt)  # t210u: 送出前转简体
    import random
    import time
    import uuid

    def say(msg):
        print(f"[ComfyUI H3] {msg}")
        if callable(status):
            try:
                status(msg)
            except Exception:
                pass

    base = (server or getattr(config, "COMFYUI_VIDEO_URL", "") or "").rstrip("/")
    if not base:
        raise RuntimeError("没有设置 ComfyUI 地址（config.COMFYUI_VIDEO_URL）")
    if not (image_path and os.path.isfile(image_path)):
        raise FileNotFoundError(f"起始图不存在：{image_path}")
    wf_file = workflow_path or MINIMAX_H3_API_WORKFLOW
    say(f"ComfyUI {base} · 工作流 {os.path.basename(wf_file)}")
    with open(wf_file, encoding="utf-8-sig") as f:
        workflow = json.load(f)
    seed = int(seed) if seed is not None else random.randint(1, 2**31 - 1)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    is_r2v = bool(_find_nodes(workflow, "MiniMaxH3ReferenceToVideo"))
    if is_r2v:  # t216u: 先确认这台机器有 Ref2VA 权重，没有就说清楚，不提交
        check_comfy_unet_available(base, workflow)

    upload_path = image_path
    if crop:  # t152u: 居中裁到目标比例并缩小，避免拉伸、减小上传
        import tempfile

        upload_path = crop_to_aspect(image_path, width, height,
                                     os.path.join(tempfile.gettempdir(), f"h3_{stamp}_first_frame.png"))
    def upload(path, name):
        # ComfyUI 的 /upload/image 只是把文件存进 input 目录，音频也能这样传（LoadAudio 从 input 目录选）
        with open(path, "rb") as f:
            r = requests.post(f"{base}/upload/image", files={"image": (name, f)},
                              data={"type": "input", "overwrite": "true"}, timeout=300)
        r.raise_for_status()
        up = r.json()
        return (up.get("subfolder") + "/" if up.get("subfolder") else "") + up["name"]

    import tempfile

    # t155u: 有场景音频时，视频长度跟音频走（夹在 4–12.25 秒），音频按这个长度截好转 wav 再上传
    audio_local = None
    if audio_path and os.path.isfile(audio_path):
        dur = h3_audio_seconds(audio_path)
        seconds = minimax_audio_video_seconds(dur)  # t200u: 跟音频（至少 4 秒），最长 12.25 秒（294 帧）
        if dur > MINIMAX_MAX_SECONDS:
            say(f"场景音频 {dur:.1f} 秒，超过 {MINIMAX_MAX_SECONDS:.2f} 秒，只用前 {MINIMAX_MAX_SECONDS:.2f} 秒")
        audio_local = os.path.join(tempfile.gettempdir(), f"h3_{stamp}_audio.wav")
        # apad + -t：音频不够长就补静音，正好和视频一样长（后面换音轨用 -shortest 不会截掉画面）
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", audio_path, "-af", "apad", "-t", f"{float(seconds):.3f}",
                        "-ac", "2", "-ar", "48000", audio_local], check=True)
    elif audio_path:
        say(f"场景音频不存在，按无声处理：{audio_path}")

    say(f"上传起始图 {os.path.basename(image_path)} → {base}")
    image_name = upload(upload_path, f"h3_{stamp}_{os.path.basename(image_path)}")
    last_image_name = None
    if not last_image_path and getattr(config, "MINIMAX_LOCK_LAST_FRAME", False):
        last_image_path = image_path  # t162u: 单画面时把起始图也当结束图，锁住环境 / 光线（动作可能变少）
        say("结束图用起始图（MINIMAX_LOCK_LAST_FRAME）")
    if last_image_path and os.path.isfile(last_image_path):
        last_up = last_image_path
        if crop:
            last_up = crop_to_aspect(last_image_path, width, height,
                                     os.path.join(tempfile.gettempdir(), f"h3_{stamp}_last_frame.png"))
        say(f"上传结束图 {os.path.basename(last_image_path)}")
        last_image_name = upload(last_up, f"h3_{stamp}_last_{os.path.basename(last_image_path)}")
    ref_image_names = []
    if is_r2v:
        refs = [p for p in (ref_image_paths or []) if p and os.path.isfile(p)][:R2V_MAX_REFS - 1]
        for k, rp in enumerate(refs, 2):
            say(f"上传人物肖像 <Picture {k}> {os.path.basename(rp)}")
            ref_image_names.append(upload(rp, f"h3_{stamp}_ref{k}_{os.path.basename(rp)}"))
    elif ref_image_paths:
        say("原工作流没有参考图输入，人物肖像不使用")
    audio_name = None
    if audio_local:
        say(f"上传场景音频 {os.path.basename(audio_path)}（{float(seconds):.1f} 秒，对口型）")
        audio_name = upload(audio_local, f"h3_{stamp}_audio.wav")

    try:
        from config_prompt import ensure_video_no_subtitle_first_line, with_h3_no_subtitle_negative
        prompt = ensure_video_no_subtitle_first_line(prompt)  # t321u: 禁字幕只一句、在第一行（不再三遍）
        negative = with_h3_no_subtitle_negative(negative)
    except Exception as _e:  # noqa: BLE001
        print(f"[ComfyUI H3] 禁字幕句核对跳过：{_e}")
    wf = build_minimax_h3_prompt(workflow, image_name=image_name, prompt=prompt, seconds=seconds, width=width,
                                 height=height, seed=seed, fps=fps, filename_prefix=f"video/H3_{stamp}",
                                 negative=negative, last_image_name=last_image_name, audio_name=audio_name,
                                 ref_image_names=ref_image_names)
    client_id = str(uuid.uuid4())
    r = requests.post(f"{base}/prompt", json={"prompt": wf, "client_id": client_id}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI /prompt HTTP {r.status_code}: {r.text[:800]}")
    prompt_id = r.json()["prompt_id"]
    say(f"已提交 prompt_id={prompt_id}（{seconds}s → {minimax_h3_frames(seconds)} 帧，{width}x{height}，seed={seed}）")

    started = time.monotonic()
    last_say = 0.0
    entry = None
    while time.monotonic() - started < timeout_s:
        try:
            h = requests.get(f"{base}/history/{prompt_id}", timeout=30).json()
        except requests.RequestException as e:
            h = {}
            print(f"[ComfyUI H3] /history 读取失败：{e}")
        entry = h.get(prompt_id)
        if entry and (entry.get("status") or {}).get("completed") is not None:
            st = entry.get("status") or {}
            if st.get("status_str") == "error":
                err = next((m[1] for m in st.get("messages", []) if m and m[0] == "execution_error"), {})
                raise RuntimeError(f"ComfyUI 运行出错（{err.get('node_type')}）：{str(err.get('exception_message'))[:500]}")
            if entry.get("outputs"):
                break
        elapsed = time.monotonic() - started
        if elapsed - last_say >= 30:
            say(f"生成中 … {int(elapsed)} 秒")
            last_say = elapsed
        time.sleep(3.0)
    else:
        raise RuntimeError(f"等了 {int(timeout_s)} 秒，ComfyUI 还没生成完（prompt_id={prompt_id}）")

    files = []
    for out in (entry.get("outputs") or {}).values():
        for key in ("images", "videos", "gifs"):
            files += [x for x in out.get(key) or [] if str(x.get("filename", "")).lower().endswith((".mp4", ".webm", ".mov", ".mkv"))]
    if not files:
        raise RuntimeError(f"ComfyUI 完成了但没有视频输出：{json.dumps(entry.get('outputs'), ensure_ascii=False)[:300]}")
    v = files[0]
    if not output_path:
        output_path = os.path.join(os.path.dirname(os.path.abspath(image_path)), v["filename"])
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    say(f"下载 {v['filename']} → {output_path}")
    with requests.get(f"{base}/view", params={"filename": v["filename"], "subfolder": v.get("subfolder", ""),
                                              "type": v.get("type", "output")}, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    try:  # t156u: 旁边记一份 prompt_id / 提示词 / 送进去的图（顺序 = Picture 1, 2, …）
        with open(output_path + ".h3.json", "w", encoding="utf-8") as f:
            json.dump({"prompt_id": prompt_id, "seed": seed, "seconds": seconds,
                       "images": [image_name] + list(ref_image_names or []), "prompt": prompt},
                      f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        print(f"[ComfyUI H3] prompt_id 记录没写成：{e}")
    if audio_local:
        # t155u: 保险起见把原始场景音频（同样截好的）换进 mp4，画面不重编码；失败就保留 ComfyUI 的输出
        muxed = output_path + ".mux.mp4"
        try:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", output_path, "-i", audio_local, "-map", "0:v:0",
                            "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", muxed],
                           check=True)
            os.replace(muxed, output_path)
        except Exception as e:  # noqa: BLE001
            print(f"[ComfyUI H3] 换原始音轨失败，保留 ComfyUI 的音轨：{e}")
    return output_path


def h3_audio_seconds(path: str) -> float:
    """t155u: ffprobe 读音频时长（秒），读不到返回 0。"""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                              "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True, timeout=60)
        return float((out.stdout or "").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


# ---------------------------------------------------------------------------
# t216u: MiniMax H3 参考图工作流（R2V，Ref2VA 权重）
R2V_MAX_REFS = 9  # MiniMaxH3ReferenceToVideo 的 ref_images 最多 9 张（场景图 + 8 张肖像）
MINIMAX_H3_R2V_WORKFLOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "workflow", "MiniMax_H3_R2V_5070.json")
# t228u: FastH3 OmniRef（FastVideo 8 步蒸馏的 Ref2VA，euler / simple，SigmaShift 12/3），参考图接法和 R2V 一样
MINIMAX_H3_FAST8_WORKFLOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                         "workflow", "MiniMax_H3_FastH3_8step_5070.json")
# Pika H3 Flex Ref2VA LoRA:6 步 lcm + ManualSigmas(基于 R2V 工作流)
MINIMAX_H3_PIKA6_WORKFLOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                         "workflow", "MiniMax_H3_R2V_Pika6_5070.json")
MINIMAX_MODEL_SOURCE_HINT = {  # 缺模型时提示：从 5070Ti（.36）这个位置拷
    "fasth3_omniref_qad_nvfp4_comfy.safetensors":
        r"D:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\models\diffusion_models\fasth3_omniref_qad_nvfp4_comfy.safetensors",
    "MiniMax-H3_Ref2VA-NVFP4.safetensors":
        r"D:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\models\diffusion_models\MiniMax-H3_Ref2VA-NVFP4.safetensors",
}


def minimax_workflow_for(choice: str) -> str:
    """t228u: h3_workflow 选项 → 工作流文件（i2v 返回空 = 用服务器选项里的原工作流）。"""
    return {"r2v": MINIMAX_H3_R2V_WORKFLOW, "r2v_fast8": MINIMAX_H3_FAST8_WORKFLOW,
            "r2v_pika6": MINIMAX_H3_PIKA6_WORKFLOW}.get(str(choice or ""), "")


def _build_minimax_h3_r2v(wf, *, image_name, prompt, seconds, width, height, seed, fps, filename_prefix,
                          last_image_name, audio_name, ref_image_names):
    r2v = _one_node(wf, "MiniMaxH3ReferenceToVideo")
    vae = wf[r2v]["inputs"].get("vae") or wf[_one_node(wf, "VAEDecode")]["inputs"]["vae"]
    wf[r2v]["inputs"].update({"prompt": (prompt or "").strip(), "width": int(width), "height": int(height)})
    for k in [k for k in wf[r2v]["inputs"] if k.startswith("ref_images.")]:
        wf[r2v]["inputs"].pop(k)
    nid = [max(int(k) for k in wf if str(k).isdigit())]

    def new(node):
        nid[0] += 1
        wf[str(nid[0])] = node
        return str(nid[0])

    names = [image_name] + list(ref_image_names or [])
    if len(names) > R2V_MAX_REFS:
        print(f"[ComfyUI H3] 参考图 {len(names)} 张，只用前 {R2V_MAX_REFS} 张")
        names = names[:R2V_MAX_REFS]
    first_id = None
    for i, nm in enumerate(names):
        lid = new({"class_type": "LoadImage", "inputs": {"image": nm},
                   "_meta": {"title": "scene (first frame)" if i == 0 else f"portrait <Picture {i + 1}>"}})
        if i == 0:
            first_id = lid
        wf[r2v]["inputs"][f"ref_images.ref_image_{i}"] = [lid, 0]
    # 场景图钉在第 0 帧（MiniMaxH3AddGuide 只改 positive，latent 照旧）
    pos = new({"class_type": "MiniMaxH3AddGuide",
               "inputs": {"positive": [r2v, 0], "latent": [r2v, 1], "frame_idx": 0, "vae": vae,
                          "image": [first_id, 0]}, "_meta": {"title": "anchor first frame"}})
    if last_image_name:
        last_id = new({"class_type": "LoadImage", "inputs": {"image": last_image_name}, "_meta": {"title": "last_frame"}})
        pos = new({"class_type": "MiniMaxH3AddGuide",
                   "inputs": {"positive": [pos, 0], "latent": [r2v, 1], "frame_idx": -1, "vae": vae,
                              "image": [last_id, 0]}, "_meta": {"title": "anchor last frame"}})
    guider = _one_node(wf, "BasicGuider")
    # t221u: 工作流里有 purge_before_sampling 节点时，条件先经过它（文字编码器 / VAE 编码完、采样前清显存）
    purge = next((k for k, v in wf.items() if isinstance(v, dict) and (v.get("_meta") or {}).get("title") == "purge_before_sampling"), None)
    if purge:
        wf[purge]["inputs"]["anything"] = [pos, 0]
        pos = purge
    wf[guider]["inputs"]["conditioning"] = [pos, 0]
    if audio_name:  # 和原工作流一样：PixaromaH3AudioSync 插在模型 / latent 和采样之间
        audio_vae = wf[_one_node(wf, "VAEDecodeAudio")]["inputs"]["vae"]
        sampler = _one_node(wf, "SamplerCustomAdvanced")
        la_id = new({"class_type": "LoadAudio", "inputs": {"audio": audio_name}, "_meta": {"title": "scene_audio"}})
        sync_id = new({"class_type": "PixaromaH3AudioSync",
                       "inputs": {"model": wf[guider]["inputs"]["model"], "latent": [r2v, 1],
                                  "audio_vae": audio_vae, "track": [la_id, 0]}, "_meta": {"title": "lip sync"}})
        wf[guider]["inputs"]["model"] = [sync_id, 0]
        wf[sampler]["inputs"]["latent_image"] = [sync_id, 1]
        wf[_one_node(wf, "CreateVideo")]["inputs"]["audio"] = [sync_id, 2]
    wf[_one_node(wf, "PrimitiveFloat")]["inputs"]["value"] = float(seconds)
    wf[_one_node(wf, "RandomNoise")]["inputs"]["noise_seed"] = int(seed)
    if fps:
        wf[_one_node(wf, "CreateVideo")]["inputs"]["fps"] = float(fps)
    wf[_one_node(wf, "SaveVideo")]["inputs"]["filename_prefix"] = filename_prefix
    return wf


def workflow_unet_names(workflow) -> list:
    return [str(v["inputs"].get("unet_name")) for v in workflow.values()
            if isinstance(v, dict) and v.get("class_type") == "UNETLoader" and v.get("inputs", {}).get("unet_name")]


def check_comfy_unet_available(base: str, workflow, get=None) -> None:
    """t216u: GET /object_info/UNETLoader（只读），工作流要的模型这台没有就抛出清楚的错误。"""
    get = get or (lambda url: requests.get(url, timeout=30).json())
    try:
        info = get(f"{base}/object_info/UNETLoader")
        spec = info["UNETLoader"]["input"]["required"]["unet_name"]
        opts = spec[0] if isinstance(spec[0], list) else (spec[1] or {}).get("options", [])
    except Exception as e:  # noqa: BLE001
        print(f"[ComfyUI H3] 读不到 {base} 的模型列表，照常提交：{e}")
        return
    missing = [n for n in workflow_unet_names(workflow) if n not in opts]
    if missing:
        src = "；".join(f"{n}（5070Ti 上在 {MINIMAX_MODEL_SOURCE_HINT[n]}）" for n in missing if n in MINIMAX_MODEL_SOURCE_HINT)
        raise RuntimeError(
            f"这台 ComfyUI（{base}）没有这个工作流要的模型：{', '.join(missing)}。\n"
            "请把这个文件拷到这台服务器的 ComfyUI\\models\\diffusion_models\\ 文件夹（拷完在 ComfyUI 里刷新或重启）"
            + (f"。来源：{src}" if src else "")
            + "；或者在生场视频窗口选「原工作流（无参考图）」/ 另一台机器。")

# ---------------------------------------------------------------------------
# t229u / t231u: MOSS 图片编辑（ComfyUI · workflow/moss_edit_3ref_api.json）
# ---------------------------------------------------------------------------
# API 工作流：LoadImage base（→ ImageScale 1.0MP）+ 可选 ref1..3（→ 0.3MP）
# → TextEncodeMOSSImageEdit（正面 / 负面；images 槽位可增减，最少 1 张）→ KSampler → SaveImage
# t231u: 没有参考图时只接底图一张——以前用底图垫满 4 路，封面提取会把同一张多格图喂 4 次，
# 模型容易画出嵌套/堆叠分镜。节点 images 是 growable（min1 max10），可以只留 image_0。
MOSS_EDIT_API_WORKFLOW = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "workflow", "moss_edit_3ref_api.json",
)
MOSS_EDIT_MAX_REFS = 3  # 最多再加 3 张参考（人物肖像等）；不够就不要垫底图
MOSS_EXTRACT_NEGATIVE = (
    "nsfw, worst quality, bad anatomy, watermark, jpeg artifact, "
    "multi-panel, collage, comic strip, storyboard, nested panels, stacked panels, "
    "grid layout, picture-in-picture, infographic layout, smaller frames inside the image"
)


def _moss_image_load_ids(workflow: Dict[str, Any]) -> list:
    """按正面 TextEncodeMOSSImageEdit 的 images.image_0.. 追到 LoadImage 节点 id。"""
    ks = _one_node(workflow, "KSampler")
    pos_id = str(workflow[ks]["inputs"]["positive"][0])
    enc = workflow[pos_id]["inputs"]
    out = []
    for i in range(1 + MOSS_EDIT_MAX_REFS):
        key = f"images.image_{i}"
        if key not in enc:
            if i == 0:
                raise ValueError(f"MOSS 工作流正面编码器没有 {key}")
            break
        scale_id = str(enc[key][0])
        load_id = str(workflow[scale_id]["inputs"]["image"][0])
        if workflow.get(load_id, {}).get("class_type") != "LoadImage":
            raise ValueError(f"MOSS 工作流 images.image_{i} 不是 LoadImage（{load_id}）")
        out.append(load_id)
    return out


def _moss_scale_ids_for_loads(workflow: Dict[str, Any], load_ids: list) -> list:
    """每个 LoadImage 对应的 ImageScaleToTotalPixels 节点 id（与 load_ids 对齐）。"""
    ks = _one_node(workflow, "KSampler")
    pos_id = str(workflow[ks]["inputs"]["positive"][0])
    enc = workflow[pos_id]["inputs"]
    out = []
    for i, _lid in enumerate(load_ids):
        key = f"images.image_{i}"
        out.append(str(enc[key][0]))
    return out


def adapt_prompt_for_moss_edit(prompt: str) -> tuple:
    """把 Grok 向的图片提示改成 MOSS-Image-Edit 口吻。返回 (prompt, negative_or_None)。

    封面/分镜「extract step N」：明确只要第 N 格铺满全画幅，禁止嵌套堆叠多格。
    其他提示原样返回（negative=None → 工作流默认负面）。
    """
    import re

    text = (prompt or "").strip()
    m = re.search(r"extract\s+step\s+(\d+)", text, flags=re.I)
    if not m:
        return text, None
    k = max(1, int(m.group(1)))
    aspect_lines, keep_lines = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("output format") or s.startswith("输出比例"):
            aspect_lines.append(s)
        elif s.startswith("Note:") or s.startswith("** Text:") or s.startswith("** Style:") \
                or s.startswith("** Visual_Style:") or s.startswith("Text:") or s.startswith("Style:") \
                or s.startswith("Visual_Style:"):
            keep_lines.append(s)
    where = "topmost / first" if k == 1 else f"number {k} counting from the top"
    moss_body = [
        f"Replace the entire image with ONLY panel/step {k} from the input "
        f"(the {where} step panel in the multi-panel cover/infographic).",
        f"Crop out that one panel alone and expand it to fill the full output frame as a single "
        f"standalone scene. The result must be one full-bleed picture of panel {k} only.",
        "Remove every other panel, step numbers, arrows, grid and the multi-panel collage layout.",
        "Do not nest panels inside panels. Do not stack or tile multiple panels. "
        "Do not return a smaller collage or picture-in-picture.",
        f"Keep panel {k}'s people, setting, action, composition details and art style; "
        f"only reframe that panel to fill the canvas.",
    ]
    parts = aspect_lines + [""] + moss_body
    if keep_lines:
        parts += [""] + keep_lines
    return "\n".join(parts).strip(), MOSS_EXTRACT_NEGATIVE


def _moss_latent_size_from_prompt(prompt: str):
    """从 OUTPUT FORMAT / 输出比例 行读 9:16 或 16:9 → 约 1MP、16 倍数的宽高；读不到返回 None。"""
    t = prompt or ""
    if "9:16" in t:
        return 768, 1360
    if "16:9" in t:
        return 1360, 768
    return None


def build_moss_edit_prompt(workflow: Dict[str, Any], *, base_name: str, ref_names: list,
                           prompt: str, seed: int,
                           filename_prefix: str = "moss_edit_3ref",
                           negative=None, width=None, height=None) -> Dict[str, Any]:
    """把 API 格式 MOSS 编辑工作流复制一份并填入参数（纯函数，可离线测）。

    base_name / ref_names：/upload/image 返回的文件名。只用「底图 + 真实参考图」，
    不再用底图垫满空槽；多余的 images.image_N 与对应 LoadImage/Scale 节点会删掉。
    prompt → 正面 TextEncodeMOSSImageEdit；negative 不给则保留工作流原负面词。
    width/height 若给，则 EmptyFlux2LatentImage 用固定尺寸（不再跟底图像素走）。
    """
    import copy

    wf = copy.deepcopy(workflow)
    load_ids = _moss_image_load_ids(wf)
    scale_ids = _moss_scale_ids_for_loads(wf, load_ids)
    refs = [n for n in list(ref_names or []) if n][:MOSS_EDIT_MAX_REFS]
    names = [base_name] + refs  # t231u: 不垫底图
    n_use = len(names)
    for i, name in enumerate(names):
        wf[load_ids[i]]["inputs"]["image"] = name

    # 丢掉未用的 image 槽，并删掉对应 LoadImage / Scale，避免 Comfy 仍去跑它们
    for enc_id in _find_nodes(wf, "TextEncodeMOSSImageEdit"):
        inp = wf[enc_id]["inputs"]
        for i in range(n_use, len(load_ids)):
            inp.pop(f"images.image_{i}", None)
    for i in range(n_use, len(load_ids)):
        wf.pop(load_ids[i], None)
        wf.pop(scale_ids[i], None)

    ks = _one_node(wf, "KSampler")
    pos_id = str(wf[ks]["inputs"]["positive"][0])
    neg_id = str(wf[ks]["inputs"]["negative"][0])
    wf[pos_id]["inputs"]["prompt"] = (prompt or "").strip()
    if negative is not None:
        wf[neg_id]["inputs"]["prompt"] = (negative or "").strip()
    wf[ks]["inputs"]["seed"] = int(seed)
    if width and height:
        w, h = int(width), int(height)
        if w % 16 or h % 16:
            raise ValueError(f"MOSS 宽高必须是 16 的倍数（给的是 {w}x{h}）")
        latent_id = _one_node(wf, "EmptyFlux2LatentImage")
        wf[latent_id]["inputs"]["width"] = w
        wf[latent_id]["inputs"]["height"] = h
    save_ids = _find_nodes(wf, "SaveImage")
    if save_ids:
        wf[save_ids[0]]["inputs"]["filename_prefix"] = filename_prefix
    return wf


def generate_image_moss_edit(prompt: str, images, *, server=None, seed=None,
                             workflow_path=None, timeout_s: float = 1800.0,
                             status=None, negative=None):
    """ComfyUI 跑 MOSS 图片编辑。images[0]=底图，images[1:]=参考图（最多 3，可无）。

    返回 PIL.Image。server 默认 config.COMFYUI_MOSS_URL（192.168.1.x:8188，asus2060）。
    t231u: 送出前把「extract step」类提示改成 MOSS 口吻；无参考时只传 1 张底图。
    """
    prompt = _to_simplified(prompt)  # t210u: 送出前转简体
    adapted, adapt_neg = adapt_prompt_for_moss_edit(prompt)
    prompt = adapted
    if negative is None and adapt_neg:
        negative = adapt_neg
    import io
    import random
    import time
    import uuid

    def say(msg):
        print(f"[ComfyUI MOSS] {msg}")
        if callable(status):
            try:
                status(msg)
            except Exception:
                pass

    paths = [p for p in list(images or []) if p and os.path.isfile(p)]
    if not paths:
        raise FileNotFoundError("MOSS 编辑需要至少一张底图")
    base = (server or getattr(config, "COMFYUI_MOSS_URL", "") or "").rstrip("/")
    if not base:
        raise RuntimeError("没有设置 ComfyUI 地址（config.COMFYUI_MOSS_URL）")
    wf_file = workflow_path or MOSS_EDIT_API_WORKFLOW
    if not os.path.isfile(wf_file):
        raise FileNotFoundError(f"MOSS 工作流不存在：{wf_file}")
    say(f"ComfyUI {base} · 工作流 {os.path.basename(wf_file)}")
    with open(wf_file, encoding="utf-8-sig") as f:
        workflow = json.load(f)
    seed = int(seed) if seed is not None else random.randint(1, 2**31 - 1)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    size = _moss_latent_size_from_prompt(prompt)

    def upload(path, name):
        with open(path, "rb") as f:
            r = requests.post(
                f"{base}/upload/image",
                files={"image": (name, f)},
                data={"type": "input", "overwrite": "true"},
                timeout=300,
            )
        r.raise_for_status()
        up = r.json()
        return (up.get("subfolder") + "/" if up.get("subfolder") else "") + up["name"]

    say(f"上传底图 {os.path.basename(paths[0])}")
    base_name = upload(paths[0], f"moss_{stamp}_base_{os.path.basename(paths[0])}")
    ref_names = []
    for i, rp in enumerate(paths[1:1 + MOSS_EDIT_MAX_REFS], 1):
        say(f"上传参考图 {i} {os.path.basename(rp)}")
        ref_names.append(upload(rp, f"moss_{stamp}_ref{i}_{os.path.basename(rp)}"))
    if len(paths) - 1 > MOSS_EDIT_MAX_REFS:
        say(f"参考图超过 {MOSS_EDIT_MAX_REFS} 张，只用前 {MOSS_EDIT_MAX_REFS} 张")
    say(f"图像槽位：底图 + {len(ref_names)} 张参考（不垫空槽）")
    if size:
        say(f"输出画布固定 {size[0]}x{size[1]}（按提示词比例）")

    wf = build_moss_edit_prompt(
        workflow, base_name=base_name, ref_names=ref_names, prompt=prompt, seed=seed,
        filename_prefix=f"moss_edit_3ref_{stamp}", negative=negative,
        width=(size[0] if size else None), height=(size[1] if size else None),
    )
    # 日志：实际进正面编码器的图槽
    ks = _one_node(wf, "KSampler")
    pos_id = str(wf[ks]["inputs"]["positive"][0])
    slot_keys = sorted(k for k in wf[pos_id]["inputs"] if k.startswith("images.image_"))
    say(f"正面提示词 {len(prompt)} 字；image slots={slot_keys}")
    print("[ComfyUI MOSS] positive prompt:\n" + prompt[:1200])

    client_id = str(uuid.uuid4())
    r = requests.post(f"{base}/prompt", json={"prompt": wf, "client_id": client_id}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI /prompt HTTP {r.status_code}: {r.text[:800]}")
    prompt_id = r.json()["prompt_id"]
    say(f"已提交 prompt_id={prompt_id}（seed={seed}，底图 + {len(ref_names)} 参考）")

    started = time.monotonic()
    last_say = 0.0
    entry = None
    while time.monotonic() - started < timeout_s:
        try:
            h = requests.get(f"{base}/history/{prompt_id}", timeout=30).json()
        except requests.RequestException as e:
            h = {}
            print(f"[ComfyUI MOSS] /history 读取失败：{e}")
        entry = h.get(prompt_id)
        if entry and (entry.get("status") or {}).get("completed") is not None:
            st = entry.get("status") or {}
            if st.get("status_str") == "error":
                err = next((m[1] for m in st.get("messages", []) if m and m[0] == "execution_error"), {})
                raise RuntimeError(
                    f"ComfyUI 运行出错（{err.get('node_type')}）：{str(err.get('exception_message'))[:500]}"
                )
            if entry.get("outputs"):
                break
        elapsed = time.monotonic() - started
        if elapsed - last_say >= 15:
            say(f"生成中 … {int(elapsed)} 秒")
            last_say = elapsed
        time.sleep(2.0)
    else:
        raise RuntimeError(f"等了 {int(timeout_s)} 秒，ComfyUI 还没生成完（prompt_id={prompt_id}）")

    imgs = []
    for out in (entry.get("outputs") or {}).values():
        imgs += [x for x in (out.get("images") or []) if x.get("filename")]
    if not imgs:
        raise RuntimeError(f"ComfyUI 完成了但没有图片输出：{json.dumps(entry.get('outputs'), ensure_ascii=False)[:300]}")
    v = imgs[0]
    say(f"下载 {v['filename']}")
    with requests.get(
        f"{base}/view",
        params={"filename": v["filename"], "subfolder": v.get("subfolder", ""), "type": v.get("type", "output")},
        timeout=600,
    ) as resp:
        resp.raise_for_status()
        data = resp.content
    return Image.open(io.BytesIO(data)).convert("RGB")


# ---------------------------------------------------------------------------
# t234u: Qwen(QN) 图片编辑（ComfyUI · workflow/qwen_edit_3ref_api.json）
# ---------------------------------------------------------------------------
# 与 MOSS 同机（默认 COMFYUI_QN_URL = COMFYUI_MOSS_URL = 192.168.1.x:8188）。
# API 工作流：LoadImage base(8) → FluxKontextImageScale(117)
#   → TextEncodeQwenImageEditPlus 正面(39)/负面(36)：image1=缩放底图，image2/3=可选参考
#   → VAEEncode(88) → KSampler(37) → VAEDecode → SaveImage(9)
# image2/image3 为 optional：无参考时删掉槽位与 LoadImage，绝不拿底图垫参考（同 t231 教训）。
QN_EDIT_API_WORKFLOW = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "workflow", "qwen_edit_3ref_api.json",
)
QN_EDIT_MAX_REFS = 2  # 工作流只有 image2 / image3 两个参考槽


def _qwen_follow_to_loadimage(workflow: Dict[str, Any], start_id) -> str:
    """从编码器的 imageN 链路追到 LoadImage 节点 id。"""
    nid = str(start_id)
    seen = set()
    while nid and nid not in seen:
        seen.add(nid)
        node = workflow.get(nid) or {}
        if node.get("class_type") == "LoadImage":
            return nid
        img = (node.get("inputs") or {}).get("image")
        if isinstance(img, (list, tuple)) and img:
            nid = str(img[0])
            continue
        break
    raise ValueError(f"QN 工作流无法从节点 {start_id} 追到 LoadImage")


def _qwen_slot_load_ids(workflow: Dict[str, Any]) -> dict:
    """返回 {"image1": load_id, "image2": load_id|None, "image3": load_id|None}（按正面编码器）。"""
    ks = _one_node(workflow, "KSampler")
    pos_id = str(workflow[ks]["inputs"]["positive"][0])
    enc = workflow[pos_id]["inputs"]
    if "image1" not in enc:
        raise ValueError("QN 工作流正面编码器没有 image1（底图）")
    out = {"image1": _qwen_follow_to_loadimage(workflow, enc["image1"][0])}
    for key in ("image2", "image3"):
        if key in enc and isinstance(enc[key], (list, tuple)) and enc[key]:
            out[key] = _qwen_follow_to_loadimage(workflow, enc[key][0])
        else:
            out[key] = None
    return out


def adapt_prompt_for_qwen_edit(prompt: str) -> tuple:
    """封面 extract-step：复用 MOSS 口吻（同属本地图编辑，避免多格嵌套）。"""
    return adapt_prompt_for_moss_edit(prompt)


def build_qwen_edit_prompt(workflow: Dict[str, Any], *, base_name: str, ref_names: list,
                           prompt: str, seed: int,
                           filename_prefix: str = "qwen_edit",
                           negative=None) -> Dict[str, Any]:
    """填 qwen_edit_3ref_api：底图 + 最多 2 张真实参考；空参考槽删除（不垫底图）。"""
    import copy

    wf = copy.deepcopy(workflow)
    slots = _qwen_slot_load_ids(wf)
    refs = [n for n in list(ref_names or []) if n][:QN_EDIT_MAX_REFS]
    wf[slots["image1"]]["inputs"]["image"] = base_name
    ref_keys = ["image2", "image3"]
    used_keys = []
    for i, name in enumerate(refs):
        key = ref_keys[i]
        lid = slots.get(key)
        if not lid:
            raise ValueError(f"QN 工作流缺少 {key} 对应的 LoadImage")
        wf[lid]["inputs"]["image"] = name
        used_keys.append(key)

    # 未用参考：从正/负编码器去掉 imageN，并删除对应 LoadImage
    drop_keys = [k for k in ref_keys if k not in used_keys]
    for enc_id in _find_nodes(wf, "TextEncodeQwenImageEditPlus"):
        inp = wf[enc_id]["inputs"]
        for k in drop_keys:
            inp.pop(k, None)
    for k in drop_keys:
        lid = slots.get(k)
        if lid:
            wf.pop(lid, None)

    ks = _one_node(wf, "KSampler")
    pos_id = str(wf[ks]["inputs"]["positive"][0])
    neg_id = str(wf[ks]["inputs"]["negative"][0])
    wf[pos_id]["inputs"]["prompt"] = (prompt or "").strip()
    if negative is not None:
        wf[neg_id]["inputs"]["prompt"] = (negative or "").strip()
    wf[ks]["inputs"]["seed"] = int(seed)
    save_ids = _find_nodes(wf, "SaveImage")
    if save_ids:
        wf[save_ids[0]]["inputs"]["filename_prefix"] = filename_prefix
    return wf


def generate_image_qwen_edit(prompt: str, images, *, server=None, seed=None,
                             workflow_path=None, timeout_s: float = 1800.0,
                             status=None, negative=None):
    """ComfyUI 跑 Qwen(QN) 图片编辑。images[0]=底图，images[1:]=参考（最多 2，可无）。

    返回 PIL.Image。server 默认 config.COMFYUI_QN_URL（与 MOSS 同机）。
    extract-step 提示走 adapt_prompt_for_qwen_edit（同 MOSS 防嵌套）。
    """
    prompt = _to_simplified(prompt)
    adapted, adapt_neg = adapt_prompt_for_qwen_edit(prompt)
    prompt = adapted
    if negative is None and adapt_neg:
        negative = adapt_neg
    import io
    import random
    import time
    import uuid

    def say(msg):
        print(f"[ComfyUI QN] {msg}")
        if callable(status):
            try:
                status(msg)
            except Exception:
                pass

    paths = [p for p in list(images or []) if p and os.path.isfile(p)]
    if not paths:
        raise FileNotFoundError("QN 编辑需要至少一张底图")
    base = (server or getattr(config, "COMFYUI_QN_URL", "")
            or getattr(config, "COMFYUI_MOSS_URL", "") or "").rstrip("/")
    if not base:
        raise RuntimeError("没有设置 ComfyUI 地址（config.COMFYUI_QN_URL）")
    wf_file = workflow_path or QN_EDIT_API_WORKFLOW
    if not os.path.isfile(wf_file):
        raise FileNotFoundError(f"QN 工作流不存在：{wf_file}")
    say(f"ComfyUI {base} · 工作流 {os.path.basename(wf_file)}")
    with open(wf_file, encoding="utf-8-sig") as f:
        workflow = json.load(f)
    seed = int(seed) if seed is not None else random.randint(1, 2**31 - 1)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def upload(path, name):
        with open(path, "rb") as f:
            r = requests.post(
                f"{base}/upload/image",
                files={"image": (name, f)},
                data={"type": "input", "overwrite": "true"},
                timeout=300,
            )
        r.raise_for_status()
        up = r.json()
        return (up.get("subfolder") + "/" if up.get("subfolder") else "") + up["name"]

    say(f"上传底图 {os.path.basename(paths[0])}")
    base_name = upload(paths[0], f"qn_{stamp}_base_{os.path.basename(paths[0])}")
    ref_names = []
    for i, rp in enumerate(paths[1:1 + QN_EDIT_MAX_REFS], 1):
        say(f"上传参考图 {i} {os.path.basename(rp)}")
        ref_names.append(upload(rp, f"qn_{stamp}_ref{i}_{os.path.basename(rp)}"))
    if len(paths) - 1 > QN_EDIT_MAX_REFS:
        say(f"参考图超过 {QN_EDIT_MAX_REFS} 张，只用前 {QN_EDIT_MAX_REFS} 张")
    say(f"图像槽位：底图 + {len(ref_names)} 张参考（不垫空槽）")

    wf = build_qwen_edit_prompt(
        workflow, base_name=base_name, ref_names=ref_names, prompt=prompt, seed=seed,
        filename_prefix=f"qwen_edit_{stamp}", negative=negative,
    )
    ks = _one_node(wf, "KSampler")
    pos_id = str(wf[ks]["inputs"]["positive"][0])
    slot_keys = sorted(k for k in wf[pos_id]["inputs"] if k.startswith("image"))
    say(f"正面提示词 {len(prompt)} 字；image slots={slot_keys}")
    print("[ComfyUI QN] positive prompt:\n" + prompt[:1200])

    client_id = str(uuid.uuid4())
    r = requests.post(f"{base}/prompt", json={"prompt": wf, "client_id": client_id}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI /prompt HTTP {r.status_code}: {r.text[:800]}")
    prompt_id = r.json()["prompt_id"]
    say(f"已提交 prompt_id={prompt_id}（seed={seed}，底图 + {len(ref_names)} 参考）")

    started = time.monotonic()
    last_say = 0.0
    entry = None
    while time.monotonic() - started < timeout_s:
        try:
            h = requests.get(f"{base}/history/{prompt_id}", timeout=30).json()
        except requests.RequestException as e:
            h = {}
            print(f"[ComfyUI QN] /history 读取失败：{e}")
        entry = h.get(prompt_id)
        if entry and (entry.get("status") or {}).get("completed") is not None:
            st = entry.get("status") or {}
            if st.get("status_str") == "error":
                err = next((m[1] for m in st.get("messages", []) if m and m[0] == "execution_error"), {})
                raise RuntimeError(
                    f"ComfyUI 运行出错（{err.get('node_type')}）：{str(err.get('exception_message'))[:500]}"
                )
            if entry.get("outputs"):
                break
        elapsed = time.monotonic() - started
        if elapsed - last_say >= 15:
            say(f"生成中 … {int(elapsed)} 秒")
            last_say = elapsed
        time.sleep(2.0)
    else:
        raise RuntimeError(f"等了 {int(timeout_s)} 秒，ComfyUI 还没生成完（prompt_id={prompt_id}）")

    imgs = []
    for out in (entry.get("outputs") or {}).values():
        imgs += [x for x in (out.get("images") or []) if x.get("filename")]
    if not imgs:
        raise RuntimeError(f"ComfyUI 完成了但没有图片输出：{json.dumps(entry.get('outputs'), ensure_ascii=False)[:300]}")
    v = imgs[0]
    say(f"下载 {v['filename']}")
    with requests.get(
        f"{base}/view",
        params={"filename": v["filename"], "subfolder": v.get("subfolder", ""), "type": v.get("type", "output")},
        timeout=600,
    ) as resp:
        resp.raise_for_status()
        data = resp.content
    return Image.open(io.BytesIO(data)).convert("RGB")
