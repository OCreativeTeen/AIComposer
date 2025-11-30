import json
import base64
import requests
from PIL import Image
from io import BytesIO
from rembg import remove
import os
import config
# VIDEO_WIDTH and VIDEO_HEIGHT are now obtained from project config via ffmpeg_processor
from typing import Dict, Any
import time
import random
from pathlib import Path
from .file_util import safe_file
from .llm_api import LLMApi



class SDProcessor:

    """
    图像处理流水线类，提供图像卡通化、背景移除等功能
    """
    def __init__(self, workflow):
        self.prompt_url = ""
        self.prompt_model = ""

        self.gen_config = {
                #"Story":{"url": "http://10.0.0.179:8188", "model": "banana", "seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":"\\\\10.0.0.179\\wan22\\ComfyUI\\user\\default\\workflows\\nano_banana.json"},
                #"Story":{"url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent", "model": "banana", "seed": 1234567890, "steps": 4, "cfg": 1.0},
                "Story":{"url": "http://10.0.0.x:8188", "model": "flux", "seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":"\\\\10.0.0.179\\wan22\\ComfyUI\\user\\default\\workflows\\flux_workflow.json"},
                "Host": {"url": "http://10.0.0.x:8188", "model": "flux1", "seed": 1234567890, "steps": 4, "cfg": 1.0, "workflow":"\\\\10.0.0.179\\wan22\\ComfyUI\\user\\default\\workflows\\flux_workflow_figure.json"},
                "SD":   {"url": "http://10.0.0.x:7860/sdapi/v1/txt2img",   "model": "sd",  "seed": 1234567890, "steps": 30, "cfg": 7.0},

                "I2V": {"url": "http://10.0.0.210:9001/wan/image2video",    "model": "wan", "seed": 1234567890, "steps": 4, "cfg": 1.0, "motion_frame":16, "frame_rate":15, "max_frames":121, "image_width":832, "image_height":480},
                "2I2V": {"url": "http://10.0.0.210:9001/wan/imagesss2video", "model": "wan", "seed": 1234567890, "steps": 4, "cfg": 1.0, "motion_frame":4,  "frame_rate":15, "max_frames":121, "image_width":832, "image_height":480},

                "S2V":  {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "model": "wan", "seed": 1234567890, "steps": 4, "cfg": 1.0, "motion_frame":5,  "frame_rate":15, "max_frames":81,  "image_width":832, "image_height":480},
                "FS2V": {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "model": "wan", "seed": 1234567890, "steps": 4, "cfg": 1.0, "motion_frame":5,  "frame_rate":15, "max_frames":121, "image_width":683, "image_height":384},
                "WS2V": {"url": "http://10.0.0.222:9001/wan/infinite_s2v",   "model": "wan", "seed": 1234567890, "steps": 4, "cfg": 1.0, "motion_frame":5,  "frame_rate":15, "max_frames":121, "image_width":432, "image_height":480},

                "AI2V": {"url": "http://10.0.0.231:9001/wan/action_transfer","model": "wan", "seed": 1234567890, "steps": 4, "cfg": 1.0, "motion_frame":5,  "frame_rate":15, "max_frames":121, "image_width":853, "image_height":480}
        }

        self.workflow = workflow
        # Get video dimensions from ffmpeg_processor (will be set after workflow initialization)
        # For now, use default values - they will be updated when workflow is created
        
        self.llm = LLMApi(model=LLMApi.GEMINI_2_0_FLASH)

        self.temp_dir = config.get_temp_path(self.workflow.pid)
        
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
        self._save_curl_command(self.gen_config['SD']['url'], payload, "img2img")
        
        # Send request to AUTOMATIC1111 API
        response = requests.post(self.gen_config['SD']['url'], json=payload, timeout=60)

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


    # 1. if image_list is empty, go pure Text to Image mode like below:
    #
    #  curl -s -X POST
    #"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent" \
    #-H "x-goog-api-key: $GEMINI_API_KEY" \
    #-H "Content-Type: application/json" \
    #-d '{
    #    "contents": [{
    #    "parts": [
    #        {"text": "Create a picture of a nano banana dish in a fancy restaurant with a Gemini theme"}
    #        ]
    #        }]
    #}' \
    #| grep -o '"data": "[^"]*"' \
    #| cut -d'"' -f4 \
    #| base64 --decode > gemini-native-image.png
    #


    # 2. if image_list is not empty, go Image to Image mode like below:
    #
    #IMG_PATH=/path/to/cat_image.jpeg
    #
    #if [[ "$(base64 --version 2>&1)" = *"FreeBSD"* ]]; then
    #    B64FLAGS="--input"
    #else
    #    B64FLAGS="-w0"
    #fi

    #IMG_BASE64=$(base64 "$B64FLAGS" "$IMG_PATH" 2>&1)

    #else
    #    B64FLAGS="-w0"
    #fi

    #IMG_BASE64=$(base64 "$B64FLAGS" "$IMG_PATH" 2>&1)

    #B64FLAGS="-w0"
    #fi

    #IMG_BASE64=$(base64 "$B64FLAGS" "$IMG_PATH" 2>&1)

    #curl -X POST \
    #"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent" \
    #    -H "x-goog-api-key: $GEMINI_API_KEY" \
    #    -H 'Content-Type: application/json' \
    #    -d "{
    #    \"contents\": [{
    #        \"parts\":[
    #            {\"text\": \"'Create a picture of my cat eating a nano-banana in a fancy restaurant under the Gemini constellation\"},
    #            {
    #            \"inline_data\": {
    #                \"mime_type\":\"image/jpeg\",
    #                \"data\": \"$IMG_BASE64\"
    #            }
    #            }
    #        ]
    #    }]
    #    }"  \
    #| grep -o '"data": "[^"]*"' \
    #| cut -d'"' -f4 \
    #| base64 --decode > gemini-edited-image.png    
    
    def text2Image_banana(self, url, workflow, positive, negative, image_list=None, width=None, height=None, cfg=None, seed=None, steps=None):
        """使用 Banana 模型生成文本到图像
        Returns:
            bytes: 生成的图像数据，失败时返回 None
        """
        if not image_list:
            image_list = []

        # 如果 prompt 是字典，转换为 JSON 字符串
        if isinstance(positive, dict):
            import json
            positive = json.dumps(positive, ensure_ascii=False)
        if isinstance(negative, dict):
            import json
            negative = json.dumps(negative, ensure_ascii=False)

        text = positive + "...... And negative prompt is :" + negative
        aspect_ratio = "16:9"
        if width and height:
            if width > height:
                aspect_ratio = "16:9"
                if len(image_list) > 0:
                    image_list.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "media", "16_9.png"))
            else:
                aspect_ratio = "9:16"
                if len(image_list) > 0:
                    image_list.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "media", "9_16.png"))

        try:
            # 加载和准备工作流
            api_workflow = self._load_workflow(workflow)
            if not api_workflow:
                return None
            
            # 上传所有图像（最多4个）
            uploaded_image_names = []
            if image_list and len(image_list) > 0:
                max_images = min(len(image_list), 4)  # 最多4个图像
                
                for i in range(max_images):
                    image_path = safe_file(image_list[i])
                    if image_path:
                        # 读取图像文件
                        with open(image_path, 'rb') as f:
                            image_data = f.read()
                        
                        print(f"🖼️ 读取图像 {i+1}: {image_path}, 大小: {len(image_data)} bytes")
                        
                        # 生成唯一的图像名称
                        base_name = os.path.basename(image_path)
                        if i > 0:
                            name, ext = os.path.splitext(base_name)
                            unique_name = f"{name}_{i+1}{ext}"
                        else:
                            unique_name = base_name
                        
                        # 上传图像到 ComfyUI 服务器
                        uploaded_name = self._upload_image_to_comfyui(url, image_data, unique_name)
                        if uploaded_name:
                            uploaded_image_names.append(uploaded_name)
                            print(f"✅ 图像 {i+1} 上传成功: {uploaded_name}")
                        else:
                            print(f"❌ 图像 {i+1} 上传失败")
                            return None
                    else:
                        print(f"❌ 图像文件不存在: {image_list[i]}")
                        return None
            
            # 更新工作流参数
            # clean & update widgets_values ~ text & aspect ratio (widgets_values aspect_ratio)
            self._update_banana_text_prompts(api_workflow, text, aspect_ratio)

            # clean & update LoadImage nodes' widgets_values ~ image & upload
            if uploaded_image_names:
                self._update_banana_load_image_nodes(api_workflow, uploaded_image_names)
            
            # 提交工作流并获取结果
            return self._submit_comfyui_workflow(url, api_workflow)
            
        except Exception as e:
            print(f"❌ Flux 图像生成失败: {str(e)}")
            return None


    def text2Image_banana_raw(self, url, text, image_list=None, width=None, height=None, cfg=None, seed=None, steps=None):
        """使用 Banana 模型生成文本到图像
        Returns:
            bytes: 生成的图像数据，失败时返回 None
        """
        if not image_list:
            image_list = []

        if width and height:
            if width > height:
                text = text + " (in 16:9 image format; don't show any text in the image)"
                image_list.append(os.path.join(os.path.dirname(__file__), "media", "16_9.png"))
            else:
                text = text + " (in 9:16 image format; don't show any text in the image)"
                image_list.append(os.path.join(os.path.dirname(__file__), "media", "9_16.png"))

        try:
            # 获取 Google API Key
            api_key = os.getenv("GOOGLE_API_KEY", "")
            if not api_key:
                print("❌ 未找到 GOOGLE_API_KEY 环境变量")
                return None
            
            # 构建请求头
            headers = {
                "x-goog-api-key": api_key,
                "Content-Type": "application/json"
            }
            
            # 1. 纯文本到图像模式
            if not image_list or len(image_list) == 0:
                print(f"🎨 使用 Banana 模型进行纯文本到图像生成")
                print(f"📝 提示词: {text}")
                
                # 构建请求体
                request_body = {
                    "contents": [{
                        "parts": [
                            {"text": text}
                        ]
                    }]
                }
                
            # 2. 图像到图像模式  
            else:
                print(f"🎨 使用 Banana 模型进行图像到图像生成")
                print(f"📝 提示词: {text}")
                print(f"🖼️ 输入图像数量: {len(image_list)}")
                
                # 准备内容部分
                parts = [{"text": text}]
                
                # 处理输入图像
                for i, image_path in enumerate(image_list):
                    image_path = safe_file(image_path)
                    if not image_path:
                        print(f"⚠️ 图像文件不存在: {image_path}")
                        continue
                        
                    try:
                        # 读取图像文件
                        with open(image_path, "rb") as f:
                            image_data = f.read()
                        
                        # 编码为 base64
                        import base64
                        img_base64 = base64.b64encode(image_data).decode('utf-8')
                        
                        # 根据文件扩展名确定 MIME 类型
                        mime_type = "image/jpeg"
                        if image_path.lower().endswith('.png'):
                            mime_type = "image/png"
                        elif image_path.lower().endswith('.webp'):
                            mime_type = "image/webp"
                        
                        # 添加到 parts
                        parts.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": img_base64
                            }
                        })
                        
                        print(f"✅ 已处理图像 {i+1}: {image_path} ({len(image_data)} bytes)")
                        
                    except Exception as e:
                        print(f"❌ 处理图像失败 {image_path}: {str(e)}")
                        continue
                
                # 构建请求体
                request_body = {
                    "contents": [{
                        "parts": parts
                    }]
                }
            
            # 发送请求到 Gemini API
            print(f"🌐 发送请求到: {url}")
            response = requests.post(url, headers=headers, json=request_body, timeout=90)
            
            if response.status_code != 200:
                print(f"❌ API 请求失败: HTTP {response.status_code}")
                print(f"响应内容: {response.text}")
                return None
            
            # 解析响应
            response_data = response.json()
            
            # 查找图像数据
            try:
                # Gemini API 返回的图像数据通常在 candidates[0].content.parts[0].inline_data.data
                candidates = response_data.get('candidates', [])
                if not candidates:
                    print("❌ 响应中未找到候选结果")
                    return None
                
                content = candidates[0].get('content', {})
                parts = content.get('parts', [])
                
                for part in parts:
                    if 'inlineData' in part:
                        image_base64 = part['inlineData'].get('data', '')
                        if image_base64:
                            # 解码 base64 图像数据
                            import base64
                            image_bytes = base64.b64decode(image_base64)
                            print(f"✅ 成功生成图像，大小: {len(image_bytes)} bytes")
                            return image_bytes
                
                print("❌ 响应中未找到图像数据")
                print(f"响应结构: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
                return None
                
            except Exception as e:
                print(f"❌ 解析响应失败: {str(e)}")
                print(f"响应内容: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Banana 图像生成失败: {str(e)}")
            return None


    def text2Image_flux(self, positive, negative, url, workflow, cfg, seed, steps, width, height):
        """使用 Flux 模型生成文本到图像"""
        try:
            # 加载和准备工作流
            api_workflow = self._load_workflow(workflow)
            if not api_workflow:
                return None
            
            # 更新工作流参数
            self._update_text_prompts(api_workflow, positive, negative)
            self._update_latent_image_size(api_workflow, width, height)
            self._update_sampler_params(api_workflow, steps, seed, cfg, denoise=1.0)
            
            # 提交工作流并获取结果
            return self._submit_comfyui_workflow(url, api_workflow)
            
        except Exception as e:
            print(f"❌ Flux 图像生成失败: {str(e)}")
            return None


    def image2Image_flux(self, positive, negative, url, workflow, figure_image_file, cfg, seed, steps, width, height, denoise=1.0):
        """使用 Flux 模型进行图像到图像的生成，支持参考图像"""
        try:
            api_workflow = self._load_workflow(workflow)
            if not api_workflow:
                return None
            
            # load figure_image_file to figure_image_data
            print(f"🖼️ 开始Flux图像到图像生成，参考图像文件: {figure_image_file}")
            if not os.path.exists(figure_image_file):
                print(f"❌ 参考图像文件不存在: {figure_image_file}")
                return None
                
            with open(figure_image_file, "rb") as f:
                figure_image_data = f.read()
            
            print(f"🖼️ 参考图像大小: {len(figure_image_data)} bytes")
            
            # 上传参考图像到 ComfyUI 服务器
            uploaded_image_name = self._upload_image_to_comfyui(url, figure_image_data, "figure_reference.png")
            if not uploaded_image_name:
                print("❌ 参考图像上传失败")
                return None
            
            # 更新工作流参数
            self._update_text_prompts(api_workflow, positive, negative)
            self._update_latent_image_size(api_workflow, width, height) 
            self._update_sampler_params(api_workflow, steps, seed, cfg, denoise=denoise)
            
            # 为GGUF节点设置默认参数
            self._update_gguf_nodes(api_workflow)
            
            # 更新图像缩放节点 (如果存在)
            self._update_image_scale_node(api_workflow, width, height)
            
            # 更新参考图像加载节点
            figure_node = self._update_load_image_node(api_workflow, uploaded_image_name, "Load Image")
            if not figure_node:
                print("⚠️ 未找到 'Load Image' 节点，尝试查找其他LoadImage节点")
                # 尝试查找任何 LoadImage 节点
                for node_id, node in api_workflow.items():
                    if node.get("class_type") == "LoadImage":
                        node["inputs"]["image"] = uploaded_image_name
                        print(f"🔍 使用LoadImage节点 {node_id}: {uploaded_image_name}")
                        break
            
            # 验证工作流的关键节点
            if not self._validate_workflow(api_workflow):
                print("❌ 工作流验证失败")
                return None
            
            # 提交工作流并获取结果
            result = self._submit_comfyui_workflow(url, api_workflow)
            
            if result:
                print(f"✅ Flux图像到图像生成成功，结果大小: {len(result)} bytes")
                return result
            else:
                print("❌ Flux图像到图像生成失败，返回 None")
                return None
            
        except Exception as e:
            print(f"❌ Flux 图像到图像生成失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


    def _load_workflow(self, workflow_path):
        """加载并转换工作流文件"""
        try:
            workflow_path = Path(workflow_path)
            if not workflow_path.exists():
                print(f"❌ 工作流文件不存在: {workflow_path}")
                return None
            
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow_template = json.load(f)
            
            # 转换 ComfyUI 工作流格式为 API 格式
            return self._convert_comfyui_workflow(workflow_template)
        except Exception as e:
            print(f"❌ 加载工作流失败: {str(e)}")
            return None

    def _update_text_prompts(self, api_workflow, positive, negative):
        """更新工作流中的文本提示词"""
        positive_node, negative_node = self._find_text_encode_nodes(api_workflow)
        print(f"🔍 找到文本编码节点 - 正面: {positive_node}, 负面: {negative_node}")
        
        # 如果 prompt 是字典，转换为 JSON 字符串
        if isinstance(positive, dict):
            import json
            positive = json.dumps(positive, ensure_ascii=False)
        if isinstance(negative, dict):
            import json
            negative = json.dumps(negative, ensure_ascii=False)
        
        if positive_node:
            api_workflow[positive_node]["inputs"]["text"] = positive
        if negative_node:
            api_workflow[negative_node]["inputs"]["text"] = negative or ""
        
        return positive_node, negative_node

    def _update_latent_image_size(self, api_workflow, width, height):
        """更新工作流中的潜在图像尺寸"""
        latent_node = self._find_latent_image_node(api_workflow)
        if latent_node:
            api_workflow[latent_node]["inputs"]["width"] = width
            api_workflow[latent_node]["inputs"]["height"] = height
            print(f"🔍 更新潜在图像尺寸节点 {latent_node}: {width}x{height}")
        return latent_node

    def _update_sampler_params(self, api_workflow, steps, seed, cfg, denoise=0.8):
        """更新工作流中的采样器参数"""
        sampler_node = self._find_sampler_node(api_workflow)
        if sampler_node:
            api_workflow[sampler_node]["inputs"]["steps"] = steps
            api_workflow[sampler_node]["inputs"]["seed"] = seed if seed != -1 else random.randint(0, 2**32 - 1)
            api_workflow[sampler_node]["inputs"]["cfg"] = cfg
            api_workflow[sampler_node]["inputs"]["sampler_name"] = "euler"
            api_workflow[sampler_node]["inputs"]["scheduler"] = "simple"
            api_workflow[sampler_node]["inputs"]["denoise"] = denoise
            
            if "control_after_generate" not in api_workflow[sampler_node]["inputs"]:
                api_workflow[sampler_node]["inputs"]["control_after_generate"] = "randomize"
            
            print(f"🔍 更新采样器节点 {sampler_node}: steps={steps}, cfg={cfg}, denoise={denoise}")
        return sampler_node

    def _upload_image_to_comfyui(self, url, image_data, image_name="input_image.png"):
        """上传图像到 ComfyUI 服务器"""
        try:
            upload_endpoint = f"{url}/upload/image"
            

            # 准备文件数据
            files = {
                'image': (image_name, BytesIO(image_data), 'image/png')
            }
            
            response = requests.post(upload_endpoint, files=files, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            uploaded_name = result.get('name', image_name)
            print(f"✅ 图像上传成功: {uploaded_name}")
            return uploaded_name
            
        except Exception as e:
            print(f"❌ 图像上传失败: {str(e)}")
            return None

    def _update_load_image_node(self, api_workflow, image_name, node_title="Load Image"):
        """更新工作流中的加载图像节点"""
        for node_id, node in api_workflow.items():
            if node.get("class_type") == "LoadImage":
                title = node.get("title", "")
                print(f"🔍 发现LoadImage节点 {node_id}, 标题: '{title}'")
                if title == node_title:
                    node["inputs"]["image"] = image_name
                    print(f"🔍 更新图像加载节点 {node_id}: {image_name}")
                    return node_id
        
        # 如果没有找到带有指定标题的节点，查找第二个LoadImage节点（通常是figure节点）
        load_image_nodes = []
        for node_id, node in api_workflow.items():
            if node.get("class_type") == "LoadImage":
                load_image_nodes.append(node_id)
        
        if len(load_image_nodes) >= 2:
            # 使用第二个LoadImage节点（按照ID排序）
            load_image_nodes.sort()
            figure_node_id = load_image_nodes[1]  # 第二个节点
            api_workflow[figure_node_id]["inputs"]["image"] = image_name
            print(f"🔍 使用第二个LoadImage节点 {figure_node_id}: {image_name}")
            return figure_node_id
            
        return None

    def _find_image_scale_node(self, api_workflow):
        """查找图像缩放节点"""
        for node_id, node in api_workflow.items():
            if node.get("class_type") == "ImageScale":
                return node_id
        return None

    def _update_image_scale_node(self, api_workflow, width, height, upscale_method="nearest-exact", crop="center"):
        """更新工作流中的图像缩放节点"""
        scale_node = self._find_image_scale_node(api_workflow)
        if scale_node:
            api_workflow[scale_node]["inputs"]["width"] = width
            api_workflow[scale_node]["inputs"]["height"] = height
            api_workflow[scale_node]["inputs"]["upscale_method"] = upscale_method
            api_workflow[scale_node]["inputs"]["crop"] = crop
            print(f"🔍 更新图像缩放节点 {scale_node}: {width}x{height}, 方法={upscale_method}, 裁剪={crop}")
        return scale_node

    def _update_banana_text_prompts(self, api_workflow, text, aspect_ratio):
        """更新 Banana 工作流中的文本提示词和宽高比参数"""
        try:
            # 查找 ComfyUI_NanoBanana 节点
            banana_node_id = None
            for node_id, node in api_workflow.items():
                if node.get("class_type") == "ComfyUI_NanoBanana":
                    banana_node_id = node_id
                    break
            
            if not banana_node_id:
                print("❌ 未找到 ComfyUI_NanoBanana 节点")
                return None
                
            # 更新 widgets_values 中的参数
            # widgets_values 格式: [prompt, operation, api_key, batch_count, temperature, quality, aspect_ratio, character_consistency, enable_safety]
            widgets_values = api_workflow[banana_node_id].get("widgets_values", [])
            
            # 确保 widgets_values 有足够的元素，使用默认值
            default_values = [
                text,           # prompt
                "edit",         # operation
                "",             # api_key (will be set from environment)
                1,              # batch_count
                0.7,            # temperature
                "high",         # quality
                aspect_ratio,   # aspect_ratio
                True,           # character_consistency
                False           # enable_safety
            ]
            
            # 如果 widgets_values 长度不够，用默认值填充
            for i in range(len(default_values)):
                if i >= len(widgets_values):
                    widgets_values.append(default_values[i])
                elif i == 0:  # prompt
                    widgets_values[i] = text
                elif i == 6:  # aspect_ratio
                    widgets_values[i] = aspect_ratio
            
            # 确保有 Google API Key
            import os
            api_key = os.getenv("GOOGLE_API_KEY", "")
            if api_key and len(widgets_values) > 2:
                widgets_values[2] = api_key
            
            # 更新 inputs 字段（对于有 widget 的输入）
            if "inputs" not in api_workflow[banana_node_id]:
                api_workflow[banana_node_id]["inputs"] = {}
            
            # 设置必需的输入参数
            api_workflow[banana_node_id]["inputs"]["prompt"] = text
            api_workflow[banana_node_id]["inputs"]["operation"] = "edit"
            api_workflow[banana_node_id]["inputs"]["aspect_ratio"] = aspect_ratio
            
            if api_key:
                api_workflow[banana_node_id]["inputs"]["api_key"] = api_key
            
            # 更新工作流
            api_workflow[banana_node_id]["widgets_values"] = widgets_values
            
            print(f"🔍 更新 Banana 节点 {banana_node_id}: 提示词='{text[:50]}...', 宽高比={aspect_ratio}")
            return banana_node_id
            
        except Exception as e:
            print(f"❌ 更新 Banana 文本提示词失败: {str(e)}")
            return None

    def _update_banana_load_image_node(self, api_workflow, image_name):
        """更新 Banana 工作流中的 LoadImage 节点"""
        try:
            # 查找 LoadImage 节点
            load_image_node_id = None
            for node_id, node in api_workflow.items():
                if node.get("class_type") == "LoadImage":
                    load_image_node_id = node_id
                    break
            
            if not load_image_node_id:
                print("❌ 未找到 LoadImage 节点")
                return None
            
            # 更新 widgets_values 中的图像参数
            # widgets_values 格式: [image_name, upload_type]
            widgets_values = api_workflow[load_image_node_id].get("widgets_values", [])
            
            # 确保 widgets_values 有足够的元素
            while len(widgets_values) < 2:
                widgets_values.append(None)
            
            # 更新图像名称 (索引 0)
            widgets_values[0] = image_name
            
            # 设置上传类型为 "image" (索引 1)
            widgets_values[1] = "image"
            
            # 更新 inputs 字段
            if "inputs" not in api_workflow[load_image_node_id]:
                api_workflow[load_image_node_id]["inputs"] = {}
            
            # 设置图像输入参数
            api_workflow[load_image_node_id]["inputs"]["image"] = image_name
            api_workflow[load_image_node_id]["inputs"]["upload"] = "image"
            
            # 更新工作流
            api_workflow[load_image_node_id]["widgets_values"] = widgets_values
            
            print(f"🔍 更新 LoadImage 节点 {load_image_node_id}: 图像={image_name}")
            return load_image_node_id
            
        except Exception as e:
            print(f"❌ 更新 Banana LoadImage 节点失败: {str(e)}")
            return None

    def _update_banana_load_image_nodes(self, api_workflow, image_names):
        """更新 Banana 工作流中的多个 LoadImage 节点"""
        try:
            # 查找所有 LoadImage 节点，按标题排序
            load_image_nodes = []
            
            # 定义节点标题映射
            node_titles = [None, "Load Image 2", "Load Image 3", "Load Image 4"]
            
            for title in node_titles:
                found_node = None
                for node_id, node in api_workflow.items():
                    if node.get("class_type") == "LoadImage":
                        node_title = node.get("title")
                        if node_title == title:
                            found_node = (node_id, title or "Load Image")
                            break
                
                if found_node:
                    load_image_nodes.append(found_node)
            
            if not load_image_nodes:
                print("❌ 未找到任何 LoadImage 节点")
                return []
            
            updated_nodes = []
            
            # 更新每个图像到对应的节点
            for i, image_name in enumerate(image_names):
                if i < len(load_image_nodes):
                    node_id, node_title = load_image_nodes[i]
                    
                    # 更新 widgets_values 中的图像参数
                    widgets_values = api_workflow[node_id].get("widgets_values", [])
                    
                    # 确保 widgets_values 有足够的元素
                    while len(widgets_values) < 2:
                        widgets_values.append(None)
                    
                    # 更新图像名称 (索引 0)
                    widgets_values[0] = image_name
                    
                    # 设置上传类型为 "image" (索引 1)
                    widgets_values[1] = "image"
                    
                    # 更新 inputs 字段
                    if "inputs" not in api_workflow[node_id]:
                        api_workflow[node_id]["inputs"] = {}
                    
                    # 设置图像输入参数
                    api_workflow[node_id]["inputs"]["image"] = image_name
                    api_workflow[node_id]["inputs"]["upload"] = "image"
                    
                    # 更新工作流
                    api_workflow[node_id]["widgets_values"] = widgets_values
                    
                    print(f"🔍 更新 {node_title} 节点 {node_id}: 图像={image_name}")
                    updated_nodes.append(node_id)
                else:
                    print(f"⚠️ 图像 {i+1} 超出可用节点数量")
            
            return updated_nodes
            
        except Exception as e:
            print(f"❌ 更新多个 Banana LoadImage 节点失败: {str(e)}")
            return []


    def _update_gguf_nodes(self, api_workflow):
        """为GGUF节点设置默认参数（基于服务器错误信息中的可用模型）"""
        try:
            # 基于ComfyUI服务器反馈的可用模型列表设置默认值
            available_unet_models = [
                "flux1-schnell-Q4_K.gguf",
                "flux1-schnell-Q6_K.gguf", 
                "flux1-schnell-Q8_0.gguf"
            ]
            
            for node_id, node in api_workflow.items():
                class_type = node.get("class_type")
                inputs = node.get("inputs", {})
                
                if class_type == "UnetLoaderGGUF":
                    if "unet_name" not in inputs or not inputs.get("unet_name"):
                        # 使用服务器上第一个可用的flux模型
                        inputs["unet_name"] = available_unet_models[0]
                        print(f"🔧 设置UnetLoaderGGUF节点 {node_id} 默认unet_name: {inputs['unet_name']}")
                        print(f"   (服务器可用模型: {available_unet_models})")
                
                elif class_type == "VAELoader":
                    if "vae_name" not in inputs or not inputs.get("vae_name"):
                        inputs["vae_name"] = "ae.safetensors"  # 默认VAE模型
                        print(f"🔧 设置VAELoader节点 {node_id} 默认vae_name: {inputs['vae_name']}")
                
                elif class_type == "DualCLIPLoaderGGUF":
                    if "type" not in inputs or not inputs.get("type"):
                        inputs["type"] = "flux"
                        print(f"🔧 设置DualCLIPLoaderGGUF节点 {node_id} 默认type: {inputs['type']}")
                    if "clip_name1" not in inputs or not inputs.get("clip_name1"):
                        inputs["clip_name1"] = "t5xxl_fp8_e4m3fn.safetensors"
                        print(f"🔧 设置DualCLIPLoaderGGUF节点 {node_id} 默认clip_name1: {inputs['clip_name1']}")
                    if "clip_name2" not in inputs or not inputs.get("clip_name2"):
                        inputs["clip_name2"] = "clip_l.safetensors"
                        print(f"🔧 设置DualCLIPLoaderGGUF节点 {node_id} 默认clip_name2: {inputs['clip_name2']}")
                        
        except Exception as e:
            print(f"⚠️ 更新GGUF节点时出错: {str(e)}")

    def _submit_comfyui_workflow(self, url, api_workflow):
        """提交工作流到 ComfyUI 并获取结果"""
        try:
            prompt_endpoint = f"{url}/prompt"
            history_endpoint = f"{url}/history"
            view_endpoint = f"{url}/view"
            
            # 调试：保存工作流到文件
            self._save_workflow_debug(api_workflow)
            
            # 提交到 ComfyUI
            print(f"📤 提交工作流到 ComfyUI...")
            response = requests.post(prompt_endpoint, json={"prompt": api_workflow}, timeout=120)
            
            if response.status_code != 200:
                print(f"❌ HTTP 错误 {response.status_code}: {response.text}")
                return None
                
            response.raise_for_status()
            
            result = response.json()
            prompt_id = result.get("prompt_id")
            if not prompt_id:
                print("❌ 未能获取 prompt ID")
                return None
            
            print(f"✅ 工作流已提交，prompt ID: {prompt_id}")
            
            # 等待完成
            max_wait_time = 300  # 5分钟超时
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                try:
                    # 检查历史记录
                    history_response = requests.get(f"{history_endpoint}/{prompt_id}", timeout=120)
                    if history_response.status_code == 200:
                        history = history_response.json()
                        if prompt_id in history:
                            outputs = history[prompt_id].get("outputs", {})
                            if outputs:
                                print(f"✅ 图像生成完成")
                                break
                except Exception as e:
                    print(f"⚠️ 检查历史记录失败: {e}")
                
                time.sleep(2)
            else:
                print("❌ 图像生成超时")
                return None
            
            # 获取生成的图像
            images = self._get_generated_images(prompt_id, history_endpoint)
            if not images:
                print("❌ 未找到生成的图像")
                return None
            
            # 下载第一张图像
            img_info = images[0]
            params = {
                "filename": img_info["filename"],
                "type": img_info["type"]
            }
            if img_info.get("subfolder"):
                params["subfolder"] = img_info["subfolder"]
            
            print(f"📥 下载图像: {img_info['filename']}")
            img_response = requests.get(view_endpoint, params=params, timeout=120)
            img_response.raise_for_status()
            
            return img_response.content
            
        except Exception as e:
            print(f"❌ ComfyUI 工作流提交失败: {str(e)}")
            return None

    def _convert_comfyui_workflow(self, comfyui_workflow):
        """将 ComfyUI 节点格式转换为 API 格式"""
        api_workflow = {}
        
        nodes = comfyui_workflow.get("nodes", [])
        links = comfyui_workflow.get("links", [])
        
        # 过滤掉不可执行的节点类型
        non_executable_nodes = {"Note", "Reroute"}
        
        # 创建链接映射
        link_map = {}
        for link in links:
            link_id, output_node, output_slot, input_node, input_slot, data_type = link
            link_map[link_id] = {
                "output_node": output_node,
                "output_slot": output_slot,
                "input_node": input_node,
                "input_slot": input_slot
            }
        
        # 转换节点
        for node in nodes:
            node_id = str(node["id"])
            node_type = node["type"]
            
            # 跳过不可执行的节点
            if node_type in non_executable_nodes:
                continue
            
            api_node = {
                "class_type": node_type,
                "inputs": {}
            }
            
            # 保留节点标题用于识别
            if "title" in node:
                api_node["title"] = node["title"]
            
            # 添加小部件值作为输入
            if "widgets_values" in node and node["widgets_values"]:
                widget_values = node["widgets_values"]
                
                # 根据节点类型映射小部件值
                if node_type == "CLIPTextEncode" and len(widget_values) > 0:
                    api_node["inputs"]["text"] = widget_values[0]
                elif node_type == "KSampler" and len(widget_values) >= 7:
                    api_node["inputs"].update({
                        "seed": widget_values[0],
                        "control_after_generate": widget_values[1] if len(widget_values) > 1 else "randomize",
                        "steps": widget_values[2] if len(widget_values) > 2 else 4,
                        "cfg": widget_values[3] if len(widget_values) > 3 else 1.0,
                        "sampler_name": widget_values[4] if len(widget_values) > 4 else "euler",
                        "scheduler": widget_values[5] if len(widget_values) > 5 else "simple",
                        "denoise": widget_values[6] if len(widget_values) > 6 else 1.0
                    })
                elif node_type == "EmptySD3LatentImage" and len(widget_values) >= 3:
                    api_node["inputs"].update({
                        "width": widget_values[0],
                        "height": widget_values[1],
                        "batch_size": widget_values[2]
                    })
                elif node_type == "CheckpointLoaderSimple" and len(widget_values) > 0:
                    api_node["inputs"]["ckpt_name"] = widget_values[0]
                elif node_type == "SaveImage" and len(widget_values) > 0:
                    api_node["inputs"]["filename_prefix"] = widget_values[0]
                elif node_type == "ImageScale" and len(widget_values) >= 4:
                    api_node["inputs"].update({
                        "upscale_method": widget_values[0],
                        "width": widget_values[1],
                        "height": widget_values[2],
                        "crop": widget_values[3]
                    })
                elif node_type == "LoadImage" and len(widget_values) >= 2:
                    api_node["inputs"].update({
                        "image": widget_values[0],
                        "upload": widget_values[1] if len(widget_values) > 1 else "image"
                    })
                elif node_type == "IPAdapterFluxLoader" and len(widget_values) >= 3:
                    api_node["inputs"].update({
                        "ipadapter": widget_values[0],
                        "clip_vision": widget_values[1],
                        "provider": widget_values[2]
                    })
                elif node_type == "ApplyIPAdapterFlux" and len(widget_values) >= 3:
                    api_node["inputs"].update({
                        "weight": widget_values[0],
                        "start_percent": widget_values[1],
                        "end_percent": widget_values[2]
                    })
                elif node_type == "VAELoader" and len(widget_values) > 0:
                    api_node["inputs"]["vae_name"] = widget_values[0]
                elif node_type == "UnetLoaderGGUF" and len(widget_values) > 0:
                    api_node["inputs"]["unet_name"] = widget_values[0]
                elif node_type == "DualCLIPLoaderGGUF" and len(widget_values) >= 3:
                    api_node["inputs"].update({
                        "clip_name1": widget_values[0],
                        "clip_name2": widget_values[1],
                        "type": widget_values[2]
                    })
            
            # 添加输入连接
            if "inputs" in node:
                for input_info in node["inputs"]:
                    if "link" in input_info and input_info["link"] is not None:
                        link_id = input_info["link"]
                        if link_id in link_map:
                            link_info = link_map[link_id]
                            input_name = input_info["name"]
                            api_node["inputs"][input_name] = [str(link_info["output_node"]), link_info["output_slot"]]
            
            api_workflow[node_id] = api_node
        
        return api_workflow

    def _find_text_encode_nodes(self, workflow):
        """在工作流中查找正面和负面文本编码节点"""
        positive_node = None
        negative_node = None
        
        for node_id, node in workflow.items():
            if node.get("class_type") == "CLIPTextEncode":
                # 首先检查节点标题（最可靠）
                title = node.get("title", "")
                if "Positive" in title:
                    positive_node = node_id
                elif "Negative" in title:
                    negative_node = node_id
                else:
                    # 备用方案：检查文本长度 - 较长的文本可能是正面提示
                    text_input = node.get("inputs", {}).get("text", "")
                    if len(text_input) > 10:  # 假设较长的文本是正面的
                        if positive_node is None:
                            positive_node = node_id
                    elif text_input == "":  # 空文本可能是负面的
                        if negative_node is None:
                            negative_node = node_id
        
        return positive_node, negative_node

    def _find_latent_image_node(self, workflow):
        """查找潜在图像生成节点"""
        for node_id, node in workflow.items():
            if node.get("class_type") in ["EmptyLatentImage", "EmptySD3LatentImage"]:
                return node_id
        return None

    def _find_sampler_node(self, workflow):
        """查找采样器/调度器节点"""
        for node_id, node in workflow.items():
            if node.get("class_type") in ["KSampler", "KSamplerAdvanced"]:
                return node_id
        return None

    def _get_generated_images(self, prompt_id, HISTORY_ENDPOINT):
        """从 ComfyUI 历史记录中获取生成的图像"""
        try:
            import requests
            
            print(f"🔍 获取 prompt ID 的历史记录: {prompt_id}")
            response = requests.get(f"{HISTORY_ENDPOINT}/{prompt_id}", timeout=120)
            response.raise_for_status()
            history = response.json()
            
            if prompt_id in history:
                prompt_data = history[prompt_id]
                outputs = prompt_data.get("outputs", {})
                
                images = []
                for node_id, output in outputs.items():
                    if "images" in output:
                        for img_info in output["images"]:
                            images.append({
                                "filename": img_info["filename"],
                                "subfolder": img_info.get("subfolder", ""),
                                "type": img_info.get("type", "output")
                            })
                
                return images
            else:
                print(f"❌ 在历史记录中未找到 prompt ID {prompt_id}")
                
        except Exception as e:
            print(f"❌ 获取图像失败: {e}")
            import traceback
            traceback.print_exc()
            
        return []


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
            # 创建调试目录
            debug_dir = os.path.join(self.temp_dir, "debug_curls")
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

    def _save_workflow_debug(self, api_workflow):
        """保存工作流到调试文件"""
        try:
            # 创建调试目录
            debug_dir = os.path.join(self.temp_dir, "debug_workflows")
            os.makedirs(debug_dir, exist_ok=True)
            
            # 生成时间戳用于文件名
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            
            # 保存工作流
            filename = f"workflow_{timestamp}.json"
            filepath = os.path.join(debug_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(api_workflow, f, indent=2, ensure_ascii=False)
            
            print(f"🔧 调试工作流已保存到: {filepath}")
            
        except Exception as e:
            print(f"⚠️ 保存调试工作流时出错: {str(e)}")

    def _validate_workflow(self, api_workflow):
        """验证工作流的关键节点和连接"""
        try:
            # 检查必需的节点类型 - 支持两种模式
            # 模式1: CheckpointLoaderSimple (旧版)
            # 模式2: UnetLoader + LoadVAE + DualClipLoader (新版)
            
            found_nodes = {}
            for node_id, node in api_workflow.items():
                class_type = node.get("class_type")
                if class_type not in found_nodes:
                    found_nodes[class_type] = []
                found_nodes[class_type].append(node_id)
            
            print(f"🔍 发现的节点类型: {list(found_nodes.keys())}")
            
            # 检查基本必需节点
            essential_nodes = ["CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage"]
            missing_essential = [node for node in essential_nodes if node not in found_nodes]
            if missing_essential:
                print(f"❌ 工作流验证失败，缺少基本必需节点: {missing_essential}")
                return False
            
            # 检查模型加载节点 - 支持多种模式
            has_checkpoint = "CheckpointLoaderSimple" in found_nodes
            has_unet_combo = ("UnetLoader" in found_nodes and 
                             "LoadVAE" in found_nodes and 
                             "DualClipLoader" in found_nodes)
            has_gguf_combo = ("UnetLoaderGGUF" in found_nodes and 
                             "VAELoader" in found_nodes and 
                             "DualCLIPLoaderGGUF" in found_nodes)
            
            if not has_checkpoint and not has_unet_combo and not has_gguf_combo:
                print("❌ 工作流验证失败，缺少模型加载节点")
                print("   需要以下之一:")
                print("   - CheckpointLoaderSimple")
                print("   - UnetLoader + LoadVAE + DualClipLoader") 
                print("   - UnetLoaderGGUF + VAELoader + DualCLIPLoaderGGUF")
                return False
            
            if has_checkpoint:
                print("✅ 使用 CheckpointLoaderSimple 模式")
            elif has_unet_combo:
                print("✅ 使用 UnetLoader + LoadVAE + DualClipLoader 模式")
            else:
                print("✅ 使用 UnetLoaderGGUF + VAELoader + DualCLIPLoaderGGUF 模式")
            
            # 检查节点的基本输入
            for node_id, node in api_workflow.items():
                class_type = node.get("class_type")
                inputs = node.get("inputs", {})
                
                # 验证特定节点的必需输入
                if class_type == "CLIPTextEncode":
                    if "text" not in inputs:
                        print(f"❌ CLIPTextEncode 节点 {node_id} 缺少 text 输入")
                        return False
                
                elif class_type == "KSampler":
                    required_inputs = ["model", "positive", "negative", "latent_image"]
                    for req_input in required_inputs:
                        if req_input not in inputs:
                            print(f"❌ KSampler 节点 {node_id} 缺少 {req_input} 输入")
                            return False
                
                elif class_type == "ImageScale":
                    required_scale_inputs = ["width", "height", "upscale_method", "crop"]
                    for req_input in required_scale_inputs:
                        if req_input not in inputs:
                            print(f"❌ ImageScale 节点 {node_id} 缺少 {req_input} 输入")
                            return False
                
                elif class_type == "IPAdapterFluxLoader":
                    required_ipadapter_inputs = ["ipadapter", "clip_vision", "provider"]
                    for req_input in required_ipadapter_inputs:
                        if req_input not in inputs:
                            print(f"❌ IPAdapterFluxLoader 节点 {node_id} 缺少 {req_input} 输入")
                            return False
                
                elif class_type == "ApplyIPAdapterFlux":
                    required_apply_inputs = ["model", "ipadapter_flux", "image", "weight", "start_percent", "end_percent"]
                    for req_input in required_apply_inputs:
                        if req_input not in inputs:
                            print(f"❌ ApplyIPAdapterFlux 节点 {node_id} 缺少 {req_input} 输入")
                            return False
                
                # 新节点类型验证
                elif class_type == "UnetLoader":
                    if "unet_name" not in inputs:
                        print(f"❌ UnetLoader 节点 {node_id} 缺少 unet_name 输入")
                        return False
                
                elif class_type == "LoadVAE":
                    if "vae_name" not in inputs:
                        print(f"❌ LoadVAE 节点 {node_id} 缺少 vae_name 输入")
                        return False
                
                elif class_type == "DualClipLoader":
                    required_clip_inputs = ["clip_name1", "clip_name2"]
                    for req_input in required_clip_inputs:
                        if req_input not in inputs:
                            print(f"❌ DualClipLoader 节点 {node_id} 缺少 {req_input} 输入")
                            return False
                
                # GGUF版本节点验证
                elif class_type == "UnetLoaderGGUF":
                    unet_input_names = ["unet_name", "model_name", "unet"]
                    has_unet_input = any(param in inputs for param in unet_input_names)
                    if not has_unet_input and inputs:
                        print(f"⚠️ UnetLoaderGGUF 节点 {node_id} 可能使用非标准输入参数")
                        print(f"   检查的标准参数: {unet_input_names}")
                        print(f"   实际输入: {list(inputs.keys())}")
                    elif not inputs:
                        print(f"ℹ️ UnetLoaderGGUF 节点 {node_id} 使用默认配置")
                
                elif class_type == "VAELoader":
                    # VAELoader可能使用不同的输入参数名，或者使用默认配置
                    vae_input_names = ["vae_name", "vae", "model_name"]
                    has_vae_input = any(param in inputs for param in vae_input_names)
                    if not has_vae_input and inputs:
                        print(f"⚠️ VAELoader 节点 {node_id} 可能使用非标准输入参数")
                        print(f"   检查的标准参数: {vae_input_names}")
                        print(f"   实际输入: {list(inputs.keys())}")
                    elif not inputs:
                        print(f"ℹ️ VAELoader 节点 {node_id} 使用默认配置（无输入参数）")
                
                elif class_type == "DualCLIPLoaderGGUF":
                    clip_input_names = ["clip_name1", "clip_name2", "model_name1", "model_name2"]
                    has_clip_input = any(param in inputs for param in clip_input_names)
                    if not has_clip_input and inputs:
                        print(f"⚠️ DualCLIPLoaderGGUF 节点 {node_id} 可能使用非标准输入参数")
                        print(f"   检查的标准参数: {clip_input_names}")
                        print(f"   实际输入: {list(inputs.keys())}")
                    elif not inputs:
                        print(f"ℹ️ DualCLIPLoaderGGUF 节点 {node_id} 使用默认配置")
            
            print("✅ 工作流验证通过")
            return True
            
        except Exception as e:
            print(f"❌ 工作流验证时出错: {str(e)}")
            return False


    def describe_image_openai(self, image_path):
        """使用 OpenAI/Gemini API 描述图片"""
        import base64
        from io import BytesIO
        
        # 打开并转换图片为 base64
        image = Image.open(image_path)
        
        # 如果图片太大，先调整大小以节省 token
        max_size = 1024
        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # 转换为 RGB 模式（如果不是）
        if image.mode not in ('RGB', 'RGBA'):
            image = image.convert('RGB')
        
        # 转换为 base64
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # 构建符合 OpenAI 格式的消息
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe this image in detail briefly (no more than 64 words). Include key visual elements, mood, and any notable features."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    }
                ]
            }
        ]
        
        response = self.llm.openai_completion(messages=messages)
        
        content = self.llm.parse_response(response)
        if not content:
            raise Exception("描述图像API返回了空内容")
        return content.strip()


    def describe_image(self, image_b64):
        """使用Ollama模型描述图像"""
        try:
            prompt = "The uploaded image is a portrait; then fill the following form to describe this portrait... \nGender:??\nAge:??\nRace:??\nGlasses:??\nFacial-Features:??\nOccupation-Guess:??\nPersonality-Guess(MBTI):??"
            # Prepare API request
            payload = {
                "model": self.prompt_model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 500
                }
            }
            
            # Send request to Ollama
            response = requests.post(f"{self.prompt_url}/api/generate", json=payload, timeout=60)
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "No response received")
            else:
                return f"Error: API returned status code {response.status_code}"
        
        except Exception as e:
            return f"Error processing image: {str(e)}" 


    def two_image_to_video(self, prompt, file_prefix, first_frame, last_frame, sound_path) :
        server_config = self.gen_config["2I2V"]
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
            'filename_prefix': file_prefix + "_2I2V_",

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


    def action_transfer_video(self, prompt, file_prefix, image_path, sound_path, action_path, key) :
        duration = self.workflow.ffmpeg_audio_processor.get_duration(sound_path)
        if duration <= 0.0:
            print(f"🔴 音频时长为0")
            return

        if isinstance(prompt, dict):
            import json
            prompt = json.dumps(prompt, ensure_ascii=False)

        server_config = self.gen_config[key]
        fps = server_config["frame_rate"]

        action_path = self.workflow.ffmpeg_processor.refps_video(action_path, str(fps))

        num_frames = int(duration * fps)
        max_frames = server_config["max_frames"]
        if num_frames > max_frames:
            num_frames = max_frames

        data = {
            'prompt': prompt,
            "negative_prompt": "",
            'filename_prefix': file_prefix + "_" + key + "_",

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


    def sound_to_video(self, prompt, file_prefix, image_path, sound_path, key, silence=False) :
        duration = self.workflow.ffmpeg_audio_processor.get_duration(sound_path)
        if duration <= 0.0:
            print(f"🔴 音频时长为0")
            return
            
        if silence:
            sound_path = self.workflow.ffmpeg_audio_processor.make_silence(duration)

        # 如果 prompt 是字典，转换为 JSON 字符串
        if isinstance(prompt, dict):
            import json
            prompt = json.dumps(prompt, ensure_ascii=False)

        server_config = self.gen_config[key]
        fps = server_config["frame_rate"]//2 if silence else server_config["frame_rate"]
        num_frames = int(duration * fps)
        max_frames = server_config["max_frames"]//2 + 2 if silence else server_config["max_frames"]
        if num_frames > max_frames:
            num_frames = max_frames

        data = {
            'prompt': prompt,
            "negative_prompt": "",
            'filename_prefix': file_prefix + "_" + key + "_",

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
            'sound': sound_path
        }
        self.post_multipart(
            data=data,
            files=files,
            full_url=server_config["url"]
        )
        self.infinite_vidoe_count += 1


    def image_to_video(self, prompt, file_prefix, image_path, sound_path, animate_mode) :
        server_config = self.gen_config[animate_mode]
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
            'filename_prefix': file_prefix + "_I2V_",

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

