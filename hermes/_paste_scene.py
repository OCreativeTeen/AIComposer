"""Paste clipboard JSON into the 分镜 scene_content field, then click 保存.
Physical coords relative to the 分镜 panel UIA origin."""
import uiautomation as auto
import win32gui, time, ctypes, sys

USER32 = ctypes.windll.user32
VK_CONTROL = 0x11
VK_A = 0x41
VK_V = 0x56

def find_toplevel(sub):
    res=[]
    def cb(h,_):
        if win32gui.IsWindowVisible(h) and sub in win32gui.GetWindowText(h):
            res.append(h)
        return 1
    win32gui.EnumWindows(cb,None)
    return res

def key(hi, lo):  # press+release a virtual key
    USER32.keybd_event(hi, lo, 0, 0); time.sleep(0.03)
    USER32.keybd_event(hi, lo, 2, 0); time.sleep(0.03)

def ctrl_key(vk):
    USER32.keybd_event(VK_CONTROL, 0, 0, 0); time.sleep(0.03)
    USER32.keybd_event(vk, 0, 0, 0); time.sleep(0.04)
    USER32.keybd_event(vk, 0, 2, 0); time.sleep(0.03)
    USER32.keybd_event(VK_CONTROL, 0, 2, 0); time.sleep(0.05)

def safe_click(hwnd, x, y, pre=0.9, hold=0.09, post=0.4):
    ctl = auto.ControlFromHandle(hwnd); ctl.SetActive(); time.sleep(pre)
    r = ctl.BoundingRectangle
    ax, ay = r.left + x, r.top + y
    USER32.SetCursorPos(ax, ay); time.sleep(0.3)
    USER32.mouse_event(0x0002,0,0,0,0); time.sleep(hold); USER32.mouse_event(0x0004,0,0,0,0)
    time.sleep(post)
    return ax, ay

def paste_into_field(hwnd, rel_x, rel_y):
    ax, ay = safe_click(hwnd, rel_x, rel_y)
    time.sleep(0.2)
    USER32.SetCursorPos(ax, ay); time.sleep(0.1)
    ctrl_key(VK_A)         # select all existing
    time.sleep(0.15)
    ctrl_key(VK_V)         # paste
    time.sleep(0.7)
    return True

def click_button(hwnd, rel_x, rel_y, pre=0.9):
    safe_click(hwnd, rel_x, rel_y, pre=pre)
    return True

if __name__ == "__main__":
    panel = find_toplevel("分镜")[0]
    # field upper-left
    paste_into_field(panel, 465, 800)
    print("pasted into scene_content field")
