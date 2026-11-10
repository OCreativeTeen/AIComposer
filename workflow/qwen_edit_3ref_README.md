# Qwen-Image-Edit-2509 三图 API 工作流

API 格式：`qwen_edit_3ref_api.json`（扁平图，无 subgraph、无 ComfySwitchNode）。
客户端：`qwen_edit_api_client.py`。

## 默认采样（Lightning turbo）

- 加载 Lightning 4-step LoRA：`Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors`（`LoraLoaderModelOnly`，`strength_model=1.0`）
- 接线：UNETLoader (`30`) → LoraLoaderModelOnly (`31`) → ModelSamplingAuraFlow (`66`, `shift=3`) → CFGNorm (`75`, `strength=1.0`) → KSampler (`37`)
- `steps=4`, `cfg=1.0`, `euler` / `simple`, `denoise=1.0`, 默认 seed `42`（客户端可覆盖）
- 底图经原生 `FluxKontextImageScale`，再 VAEEncode 作为 latent
- `TextEncodeQwenImageEditPlus` 内部会把参考图缩到约 384²（视觉）和约 1MP（VAE latent），因此工作流里不再额外缩放 ref；多图接线不变

官方对照（来自 Comfy 模板备注）：

| 参数 | Qwen Team | Comfy Original | 4-step Lightning LoRA（本默认） |
|------|-----------|----------------|--------------------------------|
| Steps | 50 | 20 | 4 |
| CFG | 4.0 | 2.5 | 1.0 |

质量路径（可选）：去掉节点 `31` 并把 KSampler 改回 `steps=20` `cfg=2.5`（UNET 直接接到 ModelSamplingAuraFlow）。客户端可用 `--steps` / `--cfg` 覆盖采样参数，但默认图已接入 Lightning LoRA。

## 模型路径（Comfy-Org + lightx2v Lightning）

放到 `D:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\models\...`：

- `diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors` (~19.03 GB)
  https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors
- `text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` (~8.74 GB)
  https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
- `vae/qwen_image_vae.safetensors` (~242 MB)
  https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors
- Lightning LoRA（默认已接入）：`loras/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors` (~850 MB)
  https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors

## 提示词写法

编码器会把图标成 Picture 1 / Picture 2 / Picture 3（底图=1，ref 依次=2、3）。用英文写清身份与场景，例如：把 Picture 2 / Picture 3 的人放进 Picture 1，并保留五官、发型、种族和衣服颜色。

## CLI

```
python qwen_edit_api_client.py --base scene.png --refs person_a.png person_b.png --prompt "Place the person from Picture 2 and the person from Picture 3 into the living room of Picture 1. Keep each person's face, hair, ethnicity and clothing exactly as in their reference. Keep Picture 1's room, lighting and composition unchanged." --out D:\AI_MEDIA\working\qwen_edit_result.png --seed 42
```

1 张底图即可；参考图 0–2 张。默认服务器 `http://192.168.1.x:8188`。默认 Lightning：4 步 / CFG 1.0。
