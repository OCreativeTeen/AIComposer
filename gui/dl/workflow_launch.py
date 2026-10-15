"""launch / focus GUI_wf processes (moved verbatim from gui/downloader.py)."""
import os
import sys
import time
import subprocess
import json
import threading
from utility.file_util import show_auto_close_popup
from gui.dl.list_store import _video_detail_project_pid


_workflow_launch_guard: dict[str, float] = {}


_workflow_launch_guard_lock = threading.Lock()


def _focus_open_workflow(pid: str = "") -> bool:
    """项目窗口已经在，就把它拿到前面，不再另开一个。"""
    from gui.raise_window import find_workflow_window, raise_window

    hwnd = find_workflow_window(pid)
    if not hwnd:
        return False
    raise_window(hwnd)
    return True


def _begin_workflow_launch(pid: str, parent=None) -> bool:
    """窗口已经在，或这一条正在启动，就不再另开。返回 True 时调用方才去启动进程。

    第一次打开要从媒体切场景、合成视频，窗口要等几分钟才出来，这段时间一直算在启动中，
    直到窗口出现或那个进程退出。"""
    pid = (pid or "").strip()
    if not pid:
        return False
    if _focus_open_workflow(pid):
        with _workflow_launch_guard_lock:
            _workflow_launch_guard.pop(pid, None)
        return False
    with _workflow_launch_guard_lock:
        busy = pid in _workflow_launch_guard
        if not busy:
            _workflow_launch_guard[pid] = float("inf")
    if busy:
        if parent is not None:
            try:
                show_auto_close_popup(
                    parent,
                    "魔法工作流",
                    "这个项目正在打开。第一次要切场景、合成视频，要等几分钟，窗口出来前请不要再点。",
                )
            except Exception:
                pass
        return False
    return True


def _release_workflow_launch(pid: str) -> None:
    with _workflow_launch_guard_lock:
        _workflow_launch_guard.pop((pid or "").strip(), None)


def _watch_workflow_launch(pid: str, proc=None) -> None:
    """窗口一出来就放开，关掉以后可以马上再开。进程退出了也放开。"""
    pid = (pid or "").strip()
    while True:
        time.sleep(0.5)
        if proc is not None and proc.poll() is not None:
            break
        if _focus_open_workflow(pid):
            break
    _release_workflow_launch(pid)


def _launch_gui_wf_open_pid(pid: str, *, parent=None) -> bool:
    """另起进程启动 ``GUI_wf.py --open-pid``，与在主窗口用 ``--open-pid`` /「选择项目→打开」后的加载逻辑一致。"""
    pid = (pid or "").strip()
    if not pid:
        return False
    if not _begin_workflow_launch(pid, parent):
        return True
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(repo_root, "GUI_wf.py")
    if not os.path.isfile(script):
        _release_workflow_launch(pid)
        show_auto_close_popup(parent, "无法启动魔法工作流", f"找不到工作流脚本：\n{script}", kind="error")
        return False
    cmd = [sys.executable, script, "--open-pid", pid]
    try:
        proc = subprocess.Popen(cmd, cwd=repo_root)
    except Exception as e:
        _release_workflow_launch(pid)
        show_auto_close_popup(parent, "无法启动魔法工作流", str(e), kind="error")
        return False
    threading.Thread(target=_watch_workflow_launch, args=(pid, proc), daemon=True).start()
    return True


def _launch_gui_wf_from_list_json(list_json_path: str, index: int, *, parent=None) -> bool:
    """启动 ``GUI_wf.py --open-from-list-json``，从频道热门列表 JSON 的一行载入完整 ``project_profile``。"""
    list_json_path = (list_json_path or "").strip()
    if not list_json_path or not os.path.isfile(list_json_path):
        return False
    try:
        with open(list_json_path, "r", encoding="utf-8") as f:
            rows = json.load(f)
        row = rows[int(index)] if isinstance(rows, list) and 0 <= int(index) < len(rows) else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError, IndexError):
        row = None
    open_pid = _video_detail_project_pid(row) if isinstance(row, dict) else ""
    if open_pid and not _begin_workflow_launch(open_pid, parent):
        return True
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(repo_root, "GUI_wf.py")
    if not os.path.isfile(script):
        _release_workflow_launch(open_pid)
        show_auto_close_popup(parent, "无法启动魔法工作流", f"找不到工作流脚本：\n{script}", kind="error")
        return False
    cmd = [sys.executable, script, "--open-from-list-json", os.path.normpath(list_json_path), str(int(index))]
    try:
        proc = subprocess.Popen(cmd, cwd=repo_root)
    except Exception as e:
        _release_workflow_launch(open_pid)
        show_auto_close_popup(parent, "无法启动魔法工作流", str(e), kind="error")
        return False
    if open_pid:
        threading.Thread(target=_watch_workflow_launch, args=(open_pid, proc), daemon=True).start()
    return True
