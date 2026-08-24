"""Start the story GUI from the video-choice queue when it is not already open."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import config

_gui_proc: subprocess.Popen | None = None


def gui_windows_open() -> bool:
    from aiagent.win_gui_tasks import find_detail_window, find_panel_window

    return bool(find_detail_window() or find_panel_window())


def _queue_preview() -> dict | None:
    from aiagent.video_choice_queue import first_pending_story_index, queue_item_at

    idx = first_pending_story_index()
    if not idx:
        return None
    try:
        return queue_item_at(idx)
    except ValueError:
        return None


def _wait_for_gui(proc: subprocess.Popen, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if gui_windows_open():
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.5)
    return gui_windows_open()


def _log_tail(log_path: Path, n: int = 12) -> str:
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if not lines:
        return ""
    return "\n".join(lines[-n:])


def _spawn_pick_video_choice(
    args: list[str],
    *,
    title: str,
    choice_id: str,
    log_name: str,
    timeout_s: float,
) -> tuple[bool, str]:
    global _gui_proc

    root = Path(__file__).resolve().parents[1]
    py = root / "venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = root / ".venv" / "Scripts" / "python.exe"
    python_exe = str(py) if py.is_file() else sys.executable

    log_dir = Path(config.BASE_PROGRAM_PATH)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_name
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")

    cmd = [python_exe, "-X", "utf8", "-m", "aiagent.pick_video_choice", *args]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    kwargs: dict = {
        "cwd": str(root),
        "stdout": log_fh,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE
        )

    print(f"[cli] GUI missing — starting: {' '.join(cmd)}", flush=True)
    print(f"[cli] queue item: {choice_id} {title}", flush=True)
    try:
        _gui_proc = subprocess.Popen(cmd, **kwargs)
    except Exception as exc:
        log_fh.close()
        return False, f"无法启动 pick_video_choice：{exc}"

    if _wait_for_gui(_gui_proc, timeout_s):
        return True, f"已从队列打开摘要：{title}" + (
            f"\nchoice_id={choice_id}" if choice_id else ""
        )

    code = _gui_proc.poll()
    extra = f" 退出码 {code}。" if code is not None else f" 进程仍在跑 pid={_gui_proc.pid}。"
    tail = _log_tail(log_path)
    detail = f"\n\n日志末尾：\n{tail}" if tail else f"\n日志：{log_path}"
    return False, (
        f"已执行 python -m aiagent.pick_video_choice {' '.join(args)}，"
        f"但摘要窗没有出现。{extra}{detail}"
    )


def ensure_gui_from_queue(*, timeout_s: float = 75.0) -> tuple[bool, str]:
    """If 摘要/分镜 is missing, run pick_video_choice next --with-detail --json."""
    global _gui_proc

    from cli.gui_session import gui_session_open, is_manual_gui_session

    if is_manual_gui_session():
        return False, (
            "当前是 GUI_pm 手工会话，不会从队列再开一条。"
            "请在界面里继续；听筒会跟着窗口同步。"
        )
    if gui_windows_open():
        return True, "GUI already open (摘要 / 分镜)"
    if gui_session_open():
        return False, (
            "电脑上已有 AIComposer（列表/欢迎窗）。不要开第二个。"
            "手工开到 STORY 后听筒会同步；队列选故事请先关掉这个 GUI 再 pick。"
        )

    if _gui_proc is not None and _gui_proc.poll() is None:
        if _wait_for_gui(_gui_proc, timeout_s):
            return True, "GUI started from queue (already launching)"
        return False, (
            f"队列 GUI 进程还在跑 (pid={_gui_proc.pid})，但摘要窗还没出现。"
            "发 sync 再等一次。"
        )

    from aiagent.video_choice_queue import list_queue_items

    preview = _queue_preview()
    if preview:
        title = (preview.get("title") or preview.get("row_key") or preview.get("choice_id") or "?").strip()
        choice_id = (preview.get("choice_id") or "").strip()
        return _spawn_pick_video_choice(
            ["next", "--with-detail", "--json"],
            title=title,
            choice_id=choice_id,
            log_name="cli_pick_next.log",
            timeout_s=timeout_s,
        )

    from cli.commands import _format_story_pickup_list

    if list_queue_items():
        return True, (
            "没有未处理的故事了，但队列里还有条目，已完成的也可以再选。\n"
            "不要发 pick next。请看列表，发 pick 1 / pick 2 / …\n\n"
            + _format_story_pickup_list()
        )
    return False, "队列里一条都没有。请先在 LIST 里导出选择队列。"


def ensure_gui_for_queue_item(item: dict, *, timeout_s: float = 75.0) -> tuple[bool, str]:
    """打开指定队列故事。GUI 已开时不启动第二个 AIComposer。"""
    from aiagent.video_choice_queue import (
        activate_queue_item,
        current_taken_queue_item,
    )

    if not isinstance(item, dict):
        return False, "无效的 queue item"
    cid = (item.get("choice_id") or "").strip()
    title = (item.get("title") or item.get("row_key") or cid or "?").strip()
    if not cid:
        return False, "队列条目缺少 choice_id"

    from cli.gui_session import is_manual_gui_session

    if is_manual_gui_session():
        return False, (
            "pick 已关掉：当前是 GUI_pm 手工会话，故事已在界面里选好。"
        )

    prev = current_taken_queue_item()
    prev_cid = ((prev.get("choice_id") or "").strip() if prev else "")

    if gui_windows_open():
        if prev_cid == cid:
            try:
                activate_queue_item(cid)
            except ValueError as exc:
                return False, str(exc)
            return True, (
                f"GUI already open — 当前就是这一条：{title}\n"
                f"choice_id={cid}\n"
                "直接发 scene 继续。"
            )
        return False, (
            "摘要/分镜还开着另一条故事。不要开第二个 AIComposer。\n"
            f"当前 GUI 对应：{prev_cid or '未知'}\n"
            f"想打开：{cid}  {title}\n"
            "请先关掉 SCENE 和 STORY（SCENE 可发 cx），等 win=none，再发一次 pick N。"
        )

    try:
        activate_queue_item(cid)
    except ValueError as exc:
        return False, str(exc)

    return _spawn_pick_video_choice(
        ["open", cid, "--with-detail", "--json"],
        title=title,
        choice_id=cid,
        log_name="cli_story_pickup.log",
        timeout_s=timeout_s,
    )
