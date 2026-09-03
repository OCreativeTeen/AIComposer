"""How the current AIComposer GUI was started: queue pickup vs GUI_pm by hand."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import config

SOURCE_MANUAL = getattr(config, "GUI_LAUNCH_MANUAL", "manual")
SOURCE_QUEUE = getattr(config, "GUI_LAUNCH_QUEUE", "queue")


def _path() -> str:
    return getattr(config, "GUI_LAUNCH_SOURCE_JSON", "") or ""


def set_gui_launch_source(source: str) -> str:
    key = (source or "").strip().lower()
    if key not in (SOURCE_MANUAL, SOURCE_QUEUE, ""):
        key = ""
    path = _path()
    payload = {
        "source": key,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if path:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass
    return key


def clear_gui_launch_source() -> None:
    set_gui_launch_source("")


def read_gui_launch_source() -> str:
    path = _path()
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    key = (data.get("source") or "").strip().lower()
    if key in (SOURCE_MANUAL, SOURCE_QUEUE):
        return key
    return ""


def gui_session_open() -> bool:
    """Any AIComposer YT 工具会话窗（含列表 / 欢迎），不只是摘要/分镜。"""
    from cli.win_gui_tasks import (
        find_detail_window,
        find_panel_window,
        find_video_list_window,
        find_yt_tools_window,
    )

    return bool(
        find_detail_window()
        or find_panel_window()
        or find_video_list_window()
        or find_yt_tools_window()
    )


def is_manual_gui_session() -> bool:
    """手工开的会话还在：故事已在界面里选好，story_pickup 应关掉。

    明确标了 queue 的才算队列会话。窗已开但没标来源（例如 GUI_pm 旧进程）也当成手工。
    """
    if not gui_session_open():
        return False
    return read_gui_launch_source() != SOURCE_QUEUE


def is_queue_gui_session() -> bool:
    return read_gui_launch_source() == SOURCE_QUEUE and gui_session_open()


def listen_clis_for_screen(screen: str) -> list[str]:
    """听筒主动同步时，这一屏可以发的 CLI 短名。"""
    name = (screen or "none").strip() or "none"
    if name == "story_scene":
        return [
            "lm",
            "sty",
            "snp",
            "prf",
            "scnge",
            "scnsave",
            "nb",
            "nbp",
            "onb",
            "nbi",
            "nbif",
            "itc",
            "igp",
            "grv",
            "gri",
            "gvd",
            "nbv",
            "vc",
            "vp",
            "sync",
        ]
    if name == "story_root":
        return [
            "scn",
            "save",
            "pub",
            "ana",
            "poe",
            "scr",
            "sty",
            "cov",
            "vc",
            "vp",
            "sync",
        ]
    if name == "video_list":
        return ["sync"]
    if name == "yt_tools":
        return ["sync"]
    return ["sync"]


def format_listen_sync(info: dict) -> str:
    """听筒主动同步文案：进了哪个窗 + 能发哪些 CLI。"""
    screen = (info.get("screen") or "none").strip() or "none"
    title = (info.get("title") or "").strip()
    labels = {
        "story_scene": "SCENE",
        "story_root": "STORY",
        "video_list": "LIST",
        "yt_tools": "YT",
        "none": "none",
    }
    lines = ["【听筒同步】" + labels.get(screen, screen)]
    if title:
        lines.append(title)
    names = listen_clis_for_screen(screen)
    if (not is_manual_gui_session()) and screen == "none":
        names = ["pick"] + [n for n in names if n != "pick"]
        try:
            from cli.video_choice_queue import describe_queue_stories

            rows = (describe_queue_stories().get("rows") or [])
            names = [f"pick {row['index']}" for row in rows] + ["pick"]
        except Exception:
            pass
    if names:
        lines.append("可发：" + "  ".join(names))
        lines.append("发其中一个即可。")
    if screen == "video_list":
        lines.append("先在界面打开一条 STORY，再发 scn。")
    elif screen == "yt_tools":
        lines.append("继续开到 LIST 或 STORY 后我会再同步。")
    elif screen == "story_scene":
        lines.append("choice 先发 scnlm / scnvs 看选项，再发 scnlm 4 / scnvs 2。")
    if is_manual_gui_session():
        lines.append("手工会话：pick 已关掉。")
    elif is_queue_gui_session():
        lines.append("队列会话：做完一条可再 pick。")
    return "\n".join(lines)
