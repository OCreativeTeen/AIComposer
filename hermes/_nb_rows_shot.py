"""Screenshot full NotebookLM window and crop tightly around the 3 infographic
rows so vision can pinpoint the export button pixel precisely.
"""
import uiautomation as auto
import ctypes, win32gui, time
from PIL import Image

u = ctypes.windll.user32
NB_HWND = 0x3098c

def main():
    root = auto.ControlFromHandle(NB_HWND)
    root.SetActive(); time.sleep(1.0)
    rect = win32gui.GetWindowRect(NB_HWND)
    from PIL import ImageGrab
    img = ImageGrab.grab(bbox=rect)
    img.save("hermes/nb_full.png")
    w,h=img.size
    # studio rows roughly mid-right; crop x 1380..3462, y 380..1000
    crop=img.crop((1380, 380, w, 1000))
    crop.save("hermes/nb_rows.png")
    print("full", img.size, "rows crop", crop.size)

if __name__=="__main__":
    main()
