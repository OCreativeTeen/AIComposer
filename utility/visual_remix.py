# -*- coding: utf-8 -*-
"""t187u: 审阅文案 — 视觉：Remix 时把这一场的起始图（clip_image）一起交给本机 Strata（Qwen，支持看图），
让 visual 不和画面冲突。看图失败 / 没有图时由调用方退回纯文字 Remix。
"""
import base64
import io
import os

VISUAL_IMAGE_REMIX_SYSTEM = """你是视频分镜编辑。用户给你一张起始画面（这一场视频的第一帧）和这一场的「视觉」描述。
把视觉描述改写成和这张图不冲突的版本：
- 以图为准：图里有几个人、谁站谁坐、在什么位置、穿什么、手里拿什么，视频一开始就是这样。描述里和图矛盾的部分要改掉或删掉
  （例如图里他已经坐在桌边，就不要写他进门、在玄关换鞋；图里她已经端着碗，就不要再写她从灶台盛汤）。
- 动作从图里的状态接着往下发生；整场大约 10 秒，最多一个大的位置变化，其余是表情和小动作。不要加新的人。
- 保留场景的地点、时间、气氛和情绪重点，以及人物的名字（名字原样照抄）。
- 简短：2 到 4 句。用和原文相同的语言和字体（原文是繁体就用繁体，简体就用简体）。
- 只输出改写后的视觉描述，不要解释，不要标题。
You are a storyboard editor. Rewrite the scene's visual description so it matches the start picture (the first frame):
people, positions, poses, clothing and props as shown; drop or change actions that contradict it; continue from that state;
about 10 seconds, at most one big change of position; no new people; keep names, place, time and mood; 2-4 sentences,
same language and script as the original. Output only the rewritten description."""


def _image_data_url(path: str, side: int = 768) -> str:
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def remix_visual_with_image(visual: str, image_path: str, *, names=(), language_label: str = "") -> str:
    """返回改写后的 visual；图不在、Strata 不能看图或返回空时抛异常（调用方退回纯文字）。"""
    if not image_path or not os.path.isfile(image_path):
        raise FileNotFoundError("没有起始图")
    from utility import llm_api

    api = llm_api.LLMApi(llm_api.STRATA)
    api.manual_fallback = False
    note = ""
    if names:
        note += "这一场的人物：" + "、".join(str(n) for n in names if n) + "。\n"
    if language_label:
        note += f"输出语言：{language_label}。\n"
    user = [
        {"type": "text", "text": note + "视觉描述原文：\n" + (visual or "").strip()},
        {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
    ]
    resp = api._chat_completions(llm_api.STRATA, [
        {"role": "system", "content": VISUAL_IMAGE_REMIX_SYSTEM},
        {"role": "user", "content": user},
    ])
    out = (resp.choices[0].message.content or "").strip() if resp and resp.choices else ""
    if not out:
        raise RuntimeError("Strata 看图改写返回空")
    return out
