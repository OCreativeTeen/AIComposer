# -*- coding: utf-8 -*-
"""t271: “这个故事有没有有效的场景 JSON”——创建项目 / 打开项目（视频生成）之前的唯一判断。

规则（和视频生成真正用的数据一致）：
- 项目文件夹里已经有 ``scenes.json`` → 视频生成直接读它：必须能解析成 JSON 数组、至少一场、每一场是对象；
- 还没有 ``scenes.json`` → 视频生成从预览窗口存的 ``scene_content`` 建场景：必须是（或能解析成）JSON 数组，
  至少一场，每一场至少有标题（caption / title）、画面（visual / content）、台词（speaking / voiceover / story_content）
  或人物（actor）里的一样非空。

预览窗口的「场景生成」（PDF → 场景 JSON → 自动给每场配图）是唯一生成场景的地方；视频生成窗口不再从 PDF 页建场景。
这个模块不碰 Tk、不碰磁盘上的项目数据（只读 ``scenes.json`` 判断）。
"""
from __future__ import annotations

import json
import os

BLOCK_CREATE_TITLE = "不能创建项目"
BLOCK_OPEN_TITLE = "不能打开项目"

_HEADING_KEYS = ("caption", "title", "Title")
_BODY_KEYS = ("visual", "content")
_SPEECH_KEYS = ("speaking", "story_content", "voiceover")
_ACTOR_KEYS = ("actor",)
_CONTENT_KEYS = _HEADING_KEYS + _BODY_KEYS + _SPEECH_KEYS + _ACTOR_KEYS


class NoValidScenesError(ValueError):
    """这个故事没有有效的场景 JSON，不能建 / 开项目。消息就是给用户看的整段话。"""


def _filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def scene_has_content(item) -> bool:
    return isinstance(item, dict) and any(_filled(item.get(k)) for k in _CONTENT_KEYS)


def parse_scene_value(value):
    """list → 原样；JSON 文本 → 解析出的 list；其他 → None。"""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def scene_content_problem(value) -> str:
    """scene_content（列表或 JSON 文本）有效返回 ""；否则返回一句话原因。"""
    if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and not value):
        return "场景 JSON 是空的（还没有生成场景）"
    scenes = parse_scene_value(value)
    if scenes is None:
        if isinstance(value, str):
            return "场景 JSON 不是合法的 JSON 数组（要以 [ 开头）"
        return "场景 JSON 必须是数组（以 [ 开头）"
    if not scenes:
        return "场景 JSON 是空的（还没有生成场景）"
    for i, item in enumerate(scenes, 1):
        if not isinstance(item, dict):
            return f"第 {i} 个场景不是对象（要写成 {{...}}）"
        if not scene_has_content(item):
            return f"第 {i} 场没有任何内容（标题 caption、画面 visual、台词 speaking / voiceover、人物 actor 都是空的）"
    return ""


def scenes_file_problem(path: str) -> str:
    """已存在的 scenes.json 有效返回 ""；不存在也返回 ""（由调用方再看 scene_content）。"""
    path = str(path or "")
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        return f"项目里的 scenes.json 读不出来（{type(exc).__name__}）：{path}"
    if not isinstance(data, list):
        return f"项目里的 scenes.json 不是 JSON 数组：{path}"
    if not data:
        return f"项目里的 scenes.json 里一场都没有：{path}"
    for i, item in enumerate(data, 1):
        if not isinstance(item, dict):
            return f"项目里的 scenes.json 第 {i} 个场景不是对象：{path}"
    return ""


def create_problem(scene_content) -> str:
    """创建项目前：预览窗口里这个故事的 scene_content。"""
    return scene_content_problem(scene_content)


def open_problem(*configs, scenes_path: str = "") -> str:
    """打开项目前：``configs`` = 项目配置 / 列表行（先后顺序取第一个有 scene_content 的）。

    scenes.json 已存在 → 只看它；否则看 scene_content。有效返回 ""。"""
    if scenes_path and os.path.isfile(scenes_path):
        return scenes_file_problem(scenes_path)
    for cfg in configs:
        if not isinstance(cfg, dict):
            continue
        value = cfg.get("scene_content")
        if value is None or value == "" or value == []:
            continue
        return scene_content_problem(value)
    return scene_content_problem(None)


def create_message(reason: str) -> str:
    return (
        "不能创建项目：这个故事还没有有效的场景 JSON。\n\n"
        f"原因：{reason}\n\n"
        "请先回到预览窗口（STORY），按「场景生成」生成场景（或在「场景」里贴入有效的场景 JSON），保存后再创建项目。"
    )


def open_message(reason: str) -> str:
    return (
        "不能打开项目：这个故事还没有有效的场景 JSON。\n\n"
        f"原因：{reason}\n\n"
        "请先回到预览窗口（STORY），按「场景生成」生成场景，保存后再打开 视频生成。"
    )


def project_open_problem(cfg, row=None, *, pid: str = "") -> str:
    """按项目 id 找 scenes.json（config.get_scenes_path）后调 ``open_problem``。"""
    scenes_path = ""
    if not pid and isinstance(cfg, dict):
        pid = cfg.get("pid") or cfg.get("id") or ""
    pid = str(pid or "").strip()
    if pid:
        try:
            import config

            scenes_path = config.get_scenes_path(pid)
        except Exception:  # noqa: BLE001
            scenes_path = ""
    return open_problem(cfg, row, scenes_path=scenes_path)