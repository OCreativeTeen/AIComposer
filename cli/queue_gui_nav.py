"""Queue-driven GUI navigation: retreat to LIST, open next row, close session."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import config


def _default_run_cx() -> tuple[bool, str]:
    from cli.bridge import send_bridge_command

    return send_bridge_command(
        screen=config.SCREEN_STORY_SCENE,
        op="click",
        field="cancel",
        timeout_s=8.0,
    )


def _row_keys_from_item(item: dict) -> list[str]:
    keys: list[str] = []
    for k in (
        item.get("row_key"),
        item.get("row_id"),
        item.get("url"),
        item.get("workflow_pid"),
    ):
        v = (k or "").strip()
        if v and v not in keys:
            keys.append(v)
    return keys


def sync_gui_window_path_from_hwnds() -> str:
    """按当前可见窗口推断层级路径并写入 config。"""
    from cli.win_gui_tasks import find_detail_window, find_panel_window, find_video_list_window

    parts: list[str] = []
    if find_video_list_window():
        parts.append(config.GUI_WINDOW_LEVEL_LIST)
    if find_detail_window():
        parts.append(config.GUI_WINDOW_LEVEL_STORY)
    if find_panel_window():
        parts.append(config.GUI_WINDOW_LEVEL_SCENE)
    return config.set_gui_window_path(parts)


def list_session_alive() -> bool:
    from cli.win_gui_tasks import find_video_list_window

    return bool(find_video_list_window())


def retreat_to_list_window(
    *,
    run_cx: Callable[[], tuple[bool, str]] | None = None,
    timeout_s: float = 25.0,
) -> tuple[bool, str]:
    """关 SCENE/STORY，保留 LIST；更新 ``gui_window_path`` 为 ``list``。"""
    from cli.ensure_gui import gui_windows_open
    from cli.win_gui_tasks import (
        find_detail_window,
        find_panel_window,
        find_video_list_window,
        post_close_window,
        set_foreground,
    )

    if find_panel_window():
        cx_fn = run_cx or _default_run_cx
        try:
            cx_fn()
        except Exception:
            pass
        time.sleep(0.6)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        detail = find_detail_window()
        if detail:
            post_close_window(detail)
        if not gui_windows_open():
            break
        time.sleep(0.45)

    list_hwnd = find_video_list_window()
    if list_hwnd:
        set_foreground(list_hwnd)
        config.set_gui_window_path([config.GUI_WINDOW_LEVEL_LIST])
        return True, f"已退回 LIST（path={config.get_gui_window_path_str()}）"

    if not gui_windows_open():
        config.reset_gui_window_path()
        return True, "STORY/SCENE 已关，未找到 LIST 窗"

    return False, "退回 LIST 失败：STORY/SCENE 可能仍开着"


def open_queue_item_from_list(
    item: dict,
    *,
    timeout_s: float = 75.0,
) -> tuple[bool, str]:
    """在已打开的 LIST 上打开队列条目（不启动第二个 AIComposer）。"""
    from cli.bridge import send_bridge_command
    from cli.ensure_gui import gui_windows_open
    from cli.video_choice_queue import activate_queue_item
    from cli.win_gui_tasks import find_detail_window, find_video_list_window

    if not isinstance(item, dict):
        return False, "无效的 queue item"
    cid = (item.get("choice_id") or "").strip()
    title = (item.get("title") or item.get("row_key") or cid or "?").strip()
    if not cid:
        return False, "队列条目缺少 choice_id"

    list_hwnd = find_video_list_window()
    if not list_hwnd:
        return False, "LIST 窗未打开，无法用同一会话打开下一条"

    row_keys = _row_keys_from_item(item)
    if not row_keys:
        return False, f"队列条目无 row_key：{title}"

    try:
        activate_queue_item(cid)
    except ValueError as exc:
        return False, str(exc)

    ok, msg = send_bridge_command(
        screen=config.SCREEN_VIDEO_LIST,
        op="set",
        field="open_row",
        value=json.dumps(row_keys, ensure_ascii=False),
        timeout_s=min(timeout_s, 12.0),
    )
    if not ok:
        return False, f"LIST open_row 失败：{msg}"

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if gui_windows_open() and find_detail_window():
            parts = [config.GUI_WINDOW_LEVEL_LIST, config.GUI_WINDOW_LEVEL_STORY]
            config.set_gui_window_path(parts)
            return True, (
                f"已从 LIST 打开：{title}\n"
                f"choice_id={cid}\n"
                f"path={config.get_gui_window_path_str()}"
            )
        time.sleep(0.5)

    return False, f"open_row 后 STORY 窗未出现：{title}"


def close_ai_composer_session(
    *,
    run_cx: Callable[[], tuple[bool, str]] | None = None,
    timeout_s: float = 30.0,
) -> tuple[bool, str]:
    """队列全部完成后关闭 STORY/SCENE/LIST。"""
    from cli.ensure_gui import gui_windows_open
    from cli.win_gui_tasks import (
        find_detail_window,
        find_panel_window,
        find_video_list_window,
        post_close_window,
    )

    ok, msg = retreat_to_list_window(run_cx=run_cx, timeout_s=timeout_s * 0.6)
    notes = [msg] if ok else [f"retreat: {msg}"]

    list_hwnd = find_video_list_window()
    if list_hwnd:
        post_close_window(list_hwnd)
        notes.append("已关 LIST")

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if (
            not find_video_list_window()
            and not find_detail_window()
            and not find_panel_window()
            and not gui_windows_open()
        ):
            config.reset_gui_window_path()
            return True, "；".join(notes) + f"；path={config.get_gui_window_path_str() or 'none'}"
        time.sleep(0.4)

    return False, "；".join(notes) + "；仍有窗口未关"
