"""Detect / report the current AIComposer GUI screen."""

from __future__ import annotations

from typing import Optional

import config

SCREEN_NONE = config.SCREEN_NONE
SCREEN_STORY_ROOT = config.SCREEN_STORY_ROOT
SCREEN_STORY_SCENE = config.SCREEN_STORY_SCENE
SCREEN_VIDEO_LIST = getattr(config, "SCREEN_VIDEO_LIST", "video_list")
SCREEN_YT_TOOLS = getattr(config, "SCREEN_YT_TOOLS", "yt_tools")

# Telegram / Hermes 看到的短窗名（内部仍用 story_root / story_scene 绑 bridge）
SCREEN_PUBLIC = {
    SCREEN_STORY_ROOT: "story",
    SCREEN_STORY_SCENE: "scene",
    SCREEN_VIDEO_LIST: "list",
    SCREEN_YT_TOOLS: "yt",
    SCREEN_NONE: "none",
}


def public_screen_name(screen: str = "") -> str:
    key = (screen or SCREEN_NONE).strip() or SCREEN_NONE
    return SCREEN_PUBLIC.get(key, key)


def _hwnd_title(hwnd: Optional[int]) -> str:
    if not hwnd:
        return ""
    try:
        from cli.win_gui_tasks import win32gui

        if win32gui is None:
            return ""
        return (win32gui.GetWindowText(hwnd) or "").strip()
    except Exception:
        return ""


def current_screen() -> str:
    """Use real windows first; prefer the foreground STORY/SCENE when both exist."""
    from cli.win_gui_tasks import (
        find_detail_window,
        find_panel_window,
        find_video_list_window,
        find_yt_tools_window,
        foreground_window_hwnd,
    )

    panel = find_panel_window()
    detail = find_detail_window()
    fg = foreground_window_hwnd()
    if fg and panel and fg == panel:
        return config.set_active_screen(SCREEN_STORY_SCENE)
    if fg and detail and fg == detail:
        return config.set_active_screen(SCREEN_STORY_ROOT)
    if panel:
        return config.set_active_screen(SCREEN_STORY_SCENE)
    if detail:
        return config.set_active_screen(SCREEN_STORY_ROOT)
    if find_video_list_window():
        return SCREEN_VIDEO_LIST
    if find_yt_tools_window():
        return SCREEN_YT_TOOLS
    persisted = config.get_active_screen()
    if persisted in (SCREEN_STORY_ROOT, SCREEN_STORY_SCENE):
        return SCREEN_NONE
    return SCREEN_NONE


def current_screen_info() -> dict:
    from cli.win_gui_tasks import (
        find_detail_window,
        find_existing_ai_window,
        find_panel_window,
        find_video_list_window,
        find_yt_tools_window,
    )

    name = current_screen()
    detail = find_detail_window()
    panel = find_panel_window()
    video_list = find_video_list_window()
    yt_tools = find_yt_tools_window()
    if name == SCREEN_STORY_SCENE:
        title = _hwnd_title(panel)
    elif name == SCREEN_STORY_ROOT:
        title = _hwnd_title(detail)
    elif name == SCREEN_VIDEO_LIST:
        title = _hwnd_title(video_list)
    elif name == SCREEN_YT_TOOLS:
        title = _hwnd_title(yt_tools)
    else:
        title = ""
    return {
        "screen": name,
        "win": public_screen_name(name),
        "title": title,
        "detail_hwnd": detail or None,
        "panel_hwnd": panel or None,
        "video_list_hwnd": video_list or None,
        "yt_tools_hwnd": yt_tools or None,
        "app_hwnd": find_existing_ai_window() or None,
        "active_screen": config.get_active_screen(),
    }
