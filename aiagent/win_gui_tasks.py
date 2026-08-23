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
import sys
import time
from typing import Any, Optional, Tuple

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
except Exception:
    win32gui = None
    win32con = None

# Ensure DPI Awareness to avoid coordinate drift (critical for Tkinter)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

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


def find_existing_ai_window() -> Optional[int]:
    candidates = enum_windows_safe(sub="aicomposer")
    if candidates:
        return candidates[0][0]
    return None


def find_detail_window() -> Optional[int]:
    candidates = enum_windows_safe(sub="摘要")
    if not candidates:
        candidates = enum_windows_safe(sub="拖入")
    valid = [c for c in candidates if "aicomposer" not in c[1].lower()]
    if valid:
        return valid[-1][0]
    return None


def find_panel_window() -> Optional[int]:
    candidates = enum_windows_safe(sub="分镜")
    if candidates:
        return candidates[0][0]
    # also try English-ish title just in case
    candidates = enum_windows_safe(sub="Scene")
    if candidates:
        return candidates[0][0]
    return None


def set_foreground(hwnd: int) -> None:
    if win32gui is None:
        return
    try:
        if win32gui.IsIconic(hwnd) and win32con is not None:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    except Exception as exc:
        log(f"warning: could not foreground hwnd={hwnd}: {exc}")


def get_window_rect(hwnd: int) -> Tuple[int, int, int, int]:
    if win32gui is None:
        raise RuntimeError("pywin32 is required for coordinate calculations")
    return win32gui.GetWindowRect(hwnd)


def try_uia_click(button_name: str, hwnd: Optional[int]) -> bool:
    """Try to locate any clickable control whose Name contains button_name."""
    if auto is None or pyautogui is None:
        return False
    try:
        if hwnd:
            root = auto.ControlFromHandle(hwnd)
        else:
            root = auto.GetForegroundControl()
        if not root:
            return False

        # Prefer exact Button first, then any control that looks clickable
        for ctrl_type in (
            auto.ButtonControl,
            auto.HyperlinkControl,
            auto.TextControl,
            auto.PaneControl,
        ):
            try:
                ctrl = root.Control(
                    searchDepth=15,
                    Name=button_name,
                    ControlType=ctrl_type().ControlType if hasattr(ctrl_type(), "ControlType") else None,
                )
                # simpler fallback search
                ctrl = root.ButtonControl(searchDepth=15, Name=button_name)
                if not ctrl.Exists(0.5, 0.1):
                    # try partial / contains
                    for c in root.GetChildren():
                        try:
                            if button_name in (c.Name or ""):
                                ctrl = c
                                break
                        except Exception:
                            continue
                if ctrl and ctrl.Exists(0.3, 0.1):
                    rect = ctrl.BoundingRectangle
                    if rect and rect.width() > 0 and rect.height() > 0:
                        click_x = rect.left + (rect.width() // 2)
                        click_y = rect.top + (rect.height() // 2)
                        set_foreground(hwnd or win32gui.GetForegroundWindow())
                        pyautogui.click(click_x, click_y)
                        log(f"UIA physical click succeeded: '{button_name}' at ({click_x}, {click_y})")
                        return True
            except Exception:
                continue
        return False
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

    # These ratios are relative to the Detail Editor / Scene panel client area.
    # They are only a last resort; UIA should succeed most of the time.
    button_ratios = {
        "审阅发布": 0.07,
        "保存": 0.18,
        "风格": 0.28,
        "分析": 0.36,
        "场景": 0.44,
        "诗歌": 0.52,
        "脚本": 0.63,
        "封面提示": 0.75,  # approximate; may need adjustment
    }

    if button_name in button_ratios and pyautogui:
        x = left + int(width * button_ratios[button_name])
        # bottom action row is roughly 58-65 % of height depending on whether extra buttons are present
        for y_ratio in (0.61, 0.58, 0.64, 0.55):
            y = top + int(height * y_ratio)
            pyautogui.click(x, y)
            time.sleep(0.15)
            log(f"Fallback ratio click attempted: '{button_name}' at ({x}, {y})")
            # we cannot easily verify success, so assume the first reasonable hit works
            return True

    log(f"ERROR: could not click '{button_name}'.")
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
