"""
AIComposer Windows GUI controller for Hermes (v2 – more robust).

Design goals:
- NEVER launch or kill AIComposer.
- Operate on the AIComposer window already opened by Step 1.
- Uses DPI-aware physical coordinates and keyboard navigation to avoid Tkinter crashes.
- Commands are small and deterministic.
- Prefer UIA name-based lookup; fall back to ratio / keyboard only when necessary.

Usage:
    python -m aiagent.win_gui_tasks click 场景
    python -m aiagent.win_gui_tasks click 保存
    python -m aiagent.win_gui_tasks click 审阅发布
    python -m aiagent.win_gui_tasks select_4step
    python -m aiagent.win_gui_tasks paste_scene
    python -m aiagent.win_gui_tasks status
    python -m aiagent.win_gui_tasks windows
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import sys
import threading
import time
from typing import Any, Callable, Optional, Tuple

try:
    import uiautomation as auto
except Exception:
    auto = None

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import win32gui
    import win32con
    import win32process
except Exception:
    win32gui = None
    win32con = None
    win32process = None

# Ensure DPI Awareness to avoid coordinate drift (critical for Tkinter)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

_COINIT_APARTMENTTHREADED = 0x2
_S_OK = 0
_S_FALSE = 1


def ensure_uia_com() -> None:
    """Initialize COM in *this* thread so UIAutomation can load.

    Telegram job/ui lanes and ``call_with_timeout`` workers are not the process
    main thread. Without CoInitialize, every UIA call prints
    ``CoInitialize has not been called`` / ``Can not load UIAutomationCore.dll``
    and silently fails — which is why ``nbi`` opens the home page then never
    clicks Story Builder.
    """
    t = threading.current_thread()
    if getattr(t, "_aic_uia_com", False):
        return
    hr = -1
    try:
        hr = int(ctypes.windll.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED))
    except Exception:
        try:
            hr = int(ctypes.windll.ole32.CoInitialize(None))
        except Exception:
            hr = -1
    t._aic_uia_com = True
    if hr not in (_S_OK, _S_FALSE) and hr not in (0, 1):
        # RPC_E_CHANGED_MODE (0x80010106): already initialized as MTA. UIA may
        # still work; log once so a remaining failure is diagnosable.
        log(f"CoInitializeEx hr=0x{hr & 0xFFFFFFFF:08X} on {t.name}")


def call_with_timeout(fn: Callable[[], Any], timeout_s: float, default: Any = None) -> Any:
    """Run ``fn`` on a throwaway thread and give up after ``timeout_s``.

    UIAutomation (cross-process COM) and ``AttachThreadInput`` block forever when
    the target app stops pumping messages. Everything the Telegram listener calls
    must be able to give up, otherwise the whole listener goes silent.
    """
    box: list[Any] = [default]
    done = threading.Event()

    def _runner() -> None:
        ensure_uia_com()
        try:
            box[0] = fn()
        except Exception:
            box[0] = default
        finally:
            done.set()

    threading.Thread(target=_runner, daemon=True).start()
    if not done.wait(timeout_s):
        log(f"WARNING: call timed out after {timeout_s}s (GUI may be frozen)")
        return default
    return box[0]


_enum_found: list[tuple[int, str]] = []
_enum_sub = ""
_enum_exclude = ""


def _global_enum_cb(hwnd: int, _: Any) -> int:
    if win32gui and win32gui.IsWindowVisible(hwnd):
        title = win32gui.GetWindowText(hwnd).strip()
        if _enum_sub.lower() in title.lower():
            if not _enum_exclude or _enum_exclude.lower() not in title.lower():
                _enum_found.append((hwnd, title))
    return 1


def enum_windows_safe(sub: str = "", exclude: str = "") -> list[tuple[int, str]]:
    global _enum_found, _enum_sub, _enum_exclude
    _enum_found = []
    _enum_sub = sub
    _enum_exclude = exclude
    if win32gui is not None:
        win32gui.EnumWindows(_global_enum_cb, None)
    return list(_enum_found)


def log(message: str) -> None:
    print(f"[win_gui_tasks] {message}", flush=True)


_SUMMARY_TITLE_SKIP = (
    "热门视频管理",
    "LIST |",
    "分镜 /",
    "SCENE |",
    "YT 工具",
    "审阅成品",
    "转录脚本",
)
_ROW_SUMMARY_TITLE = re.compile(r"^\d+\s*-\s+\S")


_EXISTING_AI_SKIP = (
    "cursor",
    "notepad",
    "visual studio",
    "chrome",
    "firefox",
    "edge",
    "code.exe",
)


def find_existing_ai_window() -> Optional[int]:
    candidates = enum_windows_safe(sub="aicomposer")
    for hwnd, title in candidates:
        low = title.lower()
        if any(mark in low for mark in _EXISTING_AI_SKIP):
            continue
        return hwnd
    return None


def _window_pid(hwnd: int) -> Optional[int]:
    if not hwnd or win32process is None:
        return None
    try:
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        return int(pid)
    except Exception:
        return None


def _is_skipped_summary_title(title: str) -> bool:
    text = (title or "").strip()
    if not text:
        return True
    low = text.lower()
    if "aicomposer" in low:
        return True
    return any(mark in text for mark in _SUMMARY_TITLE_SKIP)


def _window_has_button(hwnd: int, button_name: str) -> bool:
    if auto is None or not hwnd:
        return False

    def _probe() -> bool:
        try:
            root = auto.ControlFromHandle(hwnd)
            if not root:
                return False
            btn = root.ButtonControl(searchDepth=12, Name=button_name)
            return bool(btn.Exists(0.12, 0.04))
        except Exception:
            return False

    # UIA talks COM to the other process; a frozen GUI would hang us forever.
    return bool(call_with_timeout(_probe, 2.0, False))


def _pick_summary_candidate(candidates: list[tuple[int, str]]) -> Optional[int]:
    valid = [(hwnd, title) for hwnd, title in candidates if not _is_skipped_summary_title(title)]
    if not valid:
        return None
    return valid[-1][0]


def find_detail_window() -> Optional[int]:
    """Find the STORY window. New titles start with ``STORY |``; old ones used 摘要/拖入."""
    for marker in ("STORY |", "摘要", "拖入"):
        hwnd = _pick_summary_candidate(enum_windows_safe(sub=marker))
        if hwnd:
            return hwnd

    list_hwnd = find_video_list_window()
    list_pid = _window_pid(list_hwnd) if list_hwnd else None
    numbered: list[tuple[int, str]] = []
    for hwnd, title in enum_windows_safe(sub=""):
        if _is_skipped_summary_title(title):
            continue
        if not _ROW_SUMMARY_TITLE.match(title.strip()):
            continue
        numbered.append((hwnd, title))
        if list_pid and _window_pid(hwnd) == list_pid:
            return hwnd

    for hwnd, _title in reversed(numbered):
        if _window_has_button(hwnd, "场景"):
            return hwnd
    if numbered:
        return numbered[-1][0]
    return None


def foreground_window_hwnd() -> int | None:
    if win32gui is None:
        return None
    try:
        hwnd = int(win32gui.GetForegroundWindow() or 0)
    except Exception:
        return None
    return hwnd or None


def find_panel_window() -> Optional[int]:
    for marker in ("SCENE |", "分镜"):
        candidates = enum_windows_safe(sub=marker)
        if candidates:
            return candidates[0][0]
    for hwnd, title in enum_windows_safe(sub="SCENE"):
        if (title or "").strip().upper().startswith("SCENE"):
            return hwnd
    return None


def find_video_list_window() -> Optional[int]:
    for marker in ("LIST |", "热门视频管理"):
        candidates = enum_windows_safe(sub=marker)
        if candidates:
            return candidates[0][0]
    return None


def find_yt_tools_window() -> Optional[int]:
    candidates = enum_windows_safe(sub="YT 工具")
    if candidates:
        return candidates[0][0]
    return None


def owns_window(hwnd: int) -> bool:
    """True when hwnd belongs to this very process."""
    if not hwnd or win32process is None:
        return False
    try:
        _tid, pid = win32process.GetWindowThreadProcessId(int(hwnd))
    except Exception:
        return False
    return int(pid or 0) == os.getpid()


def set_foreground(hwnd: int) -> None:
    """Bring hwnd in front of Cursor / Telegram, giving up if the target is frozen."""
    if not hwnd or win32gui is None:
        return
    if owns_window(hwnd):
        # Self-deadlock guard: AttachThreadInput / SetForegroundWindow wait for the
        # target window's thread to pump messages. On our own window that thread is
        # the caller (blocked in call_with_timeout), so nobody pumps and the GUI
        # wedges for good. In-process callers must use Tk's lift/focus_force.
        log(f"refusing to win32-foreground our own window hwnd={hwnd}; use Tk lift()")
        return
    # AttachThreadInput blocks indefinitely when the target thread stops pumping.
    call_with_timeout(lambda: _set_foreground_blocking(hwnd), 3.0, None)


def _set_foreground_blocking(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    try:
        if win32con is not None:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.BringWindowToTop(hwnd)
        try:
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP if win32con else 0,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE if win32con else 3,
            )
        except Exception:
            pass

        # Unlock foreground lock (Alt key trick)
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)

        fg = user32.GetForegroundWindow()
        if fg != hwnd and win32process is not None:
            current_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            fg_tid, _ = win32process.GetWindowThreadProcessId(fg)
            target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            user32.AttachThreadInput(current_tid, fg_tid, True)
            user32.AttachThreadInput(current_tid, target_tid, True)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.AttachThreadInput(current_tid, target_tid, False)
            user32.AttachThreadInput(current_tid, fg_tid, False)
        else:
            user32.SetForegroundWindow(hwnd)

        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception as exc:
            log(f"warning: SetForegroundWindow hwnd={hwnd}: {exc}")
        time.sleep(0.25)
    except Exception as exc:
        log(f"warning: could not foreground hwnd={hwnd}: {exc}")


def flash_window(hwnd: int, *, until_foreground: bool = True) -> None:
    """Flash taskbar button so the user notices SCENE/STORY behind other apps."""
    if not hwnd:
        return
    try:
        if win32gui is not None:
            win32gui.FlashWindow(int(hwnd), bool(until_foreground))
    except Exception as exc:
        log(f"warning: FlashWindow hwnd={hwnd}: {exc}")


def get_window_rect(hwnd: int) -> Tuple[int, int, int, int]:
    if win32gui is None:
        raise RuntimeError("pywin32 is required for coordinate calculations")
    return win32gui.GetWindowRect(hwnd)


def _find_named_button(root, button_name: str):
    if auto is None or not root:
        return None
    try:
        btn = root.ButtonControl(searchDepth=20, Name=button_name)
        if btn.Exists(0.4, 0.08):
            return btn
    except Exception:
        pass
    try:
        walker = getattr(auto, "WalkControl", None)
        if walker is None:
            return None
        for ctrl, _depth in walker(root, maxDepth=20):
            try:
                name = ctrl.Name or ""
                ctype = getattr(ctrl, "ControlTypeName", "") or ""
                if button_name not in name:
                    continue
                if ctype in ("ButtonControl", "HyperlinkControl", "TextControl", "PaneControl"):
                    return ctrl
            except Exception:
                continue
    except Exception:
        pass
    return None


def try_uia_click(button_name: str, hwnd: Optional[int]) -> bool:
    """Locate a control named button_name and click its physical center."""
    if auto is None or pyautogui is None:
        return False
    return bool(call_with_timeout(lambda: _try_uia_click_blocking(button_name, hwnd), 8.0, False))


def _try_uia_click_blocking(button_name: str, hwnd: Optional[int]) -> bool:
    try:
        root = auto.ControlFromHandle(hwnd) if hwnd else auto.GetForegroundControl()
        if not root:
            return False
        ctrl = _find_named_button(root, button_name)
        if not ctrl:
            return False
        rect = ctrl.BoundingRectangle
        if not rect or rect.width() <= 0 or rect.height() <= 0:
            return False
        click_x = rect.left + (rect.width() // 2)
        click_y = rect.top + (rect.height() // 2)
        if hwnd:
            set_foreground(hwnd)
        pyautogui.click(click_x, click_y)
        log(f"UIA physical click succeeded: '{button_name}' at ({click_x}, {click_y})")
        return True
    except Exception as exc:
        log(f"UIA lookup failed for '{button_name}': {exc}")
        return False


def click_app_button(button_name: str) -> bool:
    panel_hwnd = find_panel_window()
    detail_hwnd = find_detail_window()
    ai_hwnd = find_existing_ai_window()

    target_hwnd = panel_hwnd or detail_hwnd or ai_hwnd
    if not target_hwnd:
        log("ERROR: existing AIComposer/detail/panel window not found")
        return False

    set_foreground(target_hwnd)
    time.sleep(0.25)

    if try_uia_click(button_name, target_hwnd):
        return True

    # Fallback ratio-based click (only for well-known bottom-row buttons)
    left, top, right, bottom = get_window_rect(target_hwnd)
    width = right - left
    height = bottom - top

    # Summary action row sits above 主角/风格/旁白, not at mid-height.
    # ttk buttons are invisible to UIA, so these ratios are the click fallback.
    button_ratios = {
        "审阅发布": 0.08,
        "保存": 0.20,
        "风格": 0.36,
        "分析": 0.44,
        "场景": 0.52,
        "诗歌": 0.60,
        "脚本": 0.72,
        "封面提示": 0.78,
    }

    if button_name in button_ratios and pyautogui:
        xs = [button_ratios[button_name]]
        ys = (0.76, 0.72, 0.80)
        if button_name == "场景":
            xs = (0.50, 0.54, 0.58)
            ys = (0.74, 0.78, 0.70)
        for x_ratio in xs:
            x = left + int(width * x_ratio)
            for y_ratio in ys:
                y = top + int(height * y_ratio)
                pyautogui.click(x, y)
                time.sleep(0.2)
                log(f"Fallback ratio click attempted: '{button_name}' at ({x}, {y})")
                if button_name == "场景":
                    time.sleep(0.45)
                    if find_panel_window():
                        return True
                    continue
                return True

    log(f"ERROR: could not click '{button_name}'.")
    return False


def open_scene_panel() -> bool:
    """Foreground the 摘要窗 and click 场景 until 分镜 / Scene exists."""
    panel = find_panel_window()
    if panel:
        set_foreground(panel)
        flash_window(panel)
        return True
    hwnd = find_detail_window()
    if not hwnd:
        log("ERROR: 摘要窗 not found — cannot click 场景")
        return False
    set_foreground(hwnd)
    time.sleep(0.3)
    if try_uia_click("场景", hwnd) or click_app_button("场景"):
        time.sleep(0.6)
        panel = find_panel_window()
        if panel:
            set_foreground(panel)
            flash_window(panel)
            log("分镜 window is open")
            return True
    log("ERROR: 场景 click did not open 分镜 window")
    return False


def select_4step_prompt() -> bool:
    """Select '4 Step Story' in the Visual-by / prompt-type combobox and copy the prompt."""
    if pyautogui is None:
        log("ERROR: pyautogui is required to select prompt.")
        return False

    panel_hwnd = find_panel_window() or find_detail_window() or find_existing_ai_window()
    if not panel_hwnd:
        log("ERROR: Panel/Detail window not found.")
        return False

    try:
        set_foreground(panel_hwnd)
        time.sleep(0.35)

        # --- Preferred path: UIA ComboBox ---
        if auto is not None:
            try:
                root = auto.ControlFromHandle(panel_hwnd)
                # Look for any ComboBox that currently shows a story-type value
                combos = root.GetChildren()
                for c in root.GetChildren():
                    try:
                        name = (c.Name or "") + (getattr(c, "Value", "") or "")
                        if any(k in name for k in ("Step Story", "Short Story", "Visual", "提示")):
                            c.Click()
                            time.sleep(0.25)
                            # type the desired item (works even if the list is long)
                            pyautogui.write("4 Step Story", interval=0.03)
                            time.sleep(0.15)
                            pyautogui.press("enter")
                            log("UIA ComboBox path: selected '4 Step Story'")
                            return True
                    except Exception:
                        continue

                # broader search
                cb = root.ComboBoxControl(searchDepth=12)
                if cb.Exists(0.8, 0.2):
                    cb.Click()
                    time.sleep(0.25)
                    pyautogui.write("4 Step Story", interval=0.03)
                    pyautogui.press("enter")
                    log("UIA ComboBoxControl path succeeded")
                    return True
            except Exception as uia_exc:
                log(f"UIA ComboBox attempt failed: {uia_exc}")

        # --- Fallback: geometric click + keyboard navigation ---
        left, top, right, bottom = get_window_rect(panel_hwnd)
        # Approximate location of the first dropdown (Visual by / 提示 type)
        # These offsets are relative to the Scene panel and may need tuning if the layout changes.
        for dx, dy in ((239, 167), (220, 160), (250, 175), (200, 150)):
            combo_x = left + dx
            combo_y = top + dy
            pyautogui.click(combo_x, combo_y)
            time.sleep(0.3)
            # Clear any existing selection and type the target
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            pyautogui.write("4 Step Story", interval=0.025)
            time.sleep(0.1)
            pyautogui.press("enter")
            log(f"Geometric fallback: clicked ({combo_x},{combo_y}) and typed '4 Step Story'")
            return True

        log("ERROR: all select_4step strategies failed")
        return False
    except Exception as exc:
        log(f"ERROR: Failed to select 4 Step Story: {exc}")
        return False


def paste_scene() -> bool:
    """Paste current clipboard content into the anonymous scene_content textarea."""
    if pyautogui is None:
        log("ERROR: pyautogui is required to paste scene data.")
        return False

    target_hwnd = find_panel_window() or find_detail_window() or find_existing_ai_window()
    if not target_hwnd:
        log("ERROR: Could not find window to paste scene data.")
        return False

    try:
        set_foreground(target_hwnd)
        time.sleep(0.35)
        left, top, right, bottom = get_window_rect(target_hwnd)
        width = right - left
        height = bottom - top

        # The large multi-line editor sits roughly in the vertical middle of the Scene panel
        for y_ratio in (0.45, 0.50, 0.40, 0.55):
            click_x = left + (width // 2)
            click_y = top + int(height * y_ratio)
            pyautogui.click(click_x, click_y)
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.08)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.15)
            log(f"Successfully pasted JSON into window at ({click_x}, {click_y})")
            return True
    except Exception as exc:
        log(f"ERROR: Failed to paste scene data: {exc}")
        return False
    return False


def print_windows() -> None:
    for hwnd, title in enum_windows_safe():
        print(f"{hwnd}\t{title}")


def status() -> int:
    ai = find_existing_ai_window()
    detail = find_detail_window()
    panel = find_panel_window()
    print(f"AIComposer={ai or 'NOT_FOUND'}")
    print(f"DetailWindow={detail or 'NOT_FOUND'}")
    print(f"PanelWindow={panel or 'NOT_FOUND'}")
    return 0 if (ai or detail or panel) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    p_click = sub.add_parser("click")
    p_click.add_argument("button")

    sub.add_parser("select_4step")
    sub.add_parser("paste_scene")
    sub.add_parser("status")
    sub.add_parser("windows")

    args = parser.parse_args()

    if args.action == "click":
        return 0 if click_app_button(args.button) else 1
    if args.action == "select_4step":
        return 0 if select_4step_prompt() else 1
    if args.action == "paste_scene":
        return 0 if paste_scene() else 1
    if args.action == "status":
        return status()
    if args.action == "windows":
        print_windows()
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
