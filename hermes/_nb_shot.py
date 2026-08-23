"""Screenshot the NotebookLM window to see Studio rows + export affordances."""
import uiautomation as auto
import ctypes, win32gui, time
from PIL import ImageGrab

u = ctypes.windll.user32
NB_HWND = 0x3098c
OUT = "hermes/nb_studio.png"

def main():
    root = auto.ControlFromHandle(NB_HWND)
    root.SetActive(); time.sleep(1.0)
    rect = win32gui.GetWindowRect(NB_HWND)
    img = ImageGrab.grab(bbox=rect)
    img.save(OUT)
    print("saved", OUT, img.size)

if __name__=="__main__":
    main()
