"""t214u: 确认分类搬了分类之后，让 GUI_topic / GUI_pm 从头开始（重新弹「选择频道 / 主题列表」）。

原因：独立入口（project_manager 的 _poll_standalone_exit）在根窗下没有 Toplevel 时 quit() 结束 mainloop，
所以关掉预览 + 列表后整个程序就退出了。这里改成：退出当前进程，进程结束时（atexit）用同样的
python 和脚本参数重新启动一次，新进程走正常的启动流程。
"""
from __future__ import annotations

import atexit
import os
import subprocess
import sys

_ARMED = False


def restart_command() -> list:
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    return [sys.executable, script] + list(sys.argv[1:]) if script else []


def _spawn(cmd: list, cwd: str) -> None:
    try:
        subprocess.Popen(cmd, cwd=cwd, close_fds=True)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 重新启动失败: {e}\n请手动运行: {' '.join(cmd)}")


def restart_app(root, spawn=None) -> list:
    """退出 mainloop（不走各窗口的关闭保存），进程退出时重启。返回重启命令（测试用）。"""
    global _ARMED
    cmd = restart_command()
    if cmd and not _ARMED:
        _ARMED = True
        cwd = os.path.dirname(cmd[1]) or os.getcwd()
        atexit.register(spawn or _spawn, cmd, cwd)
        print("🔄 确认分类：程序重新启动，回到开始选择主题列表")
    try:
        root.after(100, root.quit)
    except Exception:  # noqa: BLE001
        pass
    return cmd