"""Open/activate NotebookLM Studio in the myhomefun (Profile 3) Chrome window.
NotebookLM is opened in a separate Chrome process on a different profile than
the Gemini/Grok window, so we drive it via its own top-level Chrome window.
"""
import subprocess, time, sys

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def main():
    # open notebooklm in Profile 3 as a new window
    subprocess.Popen([CHROME, "--profile-directory=Profile 3", "--new-window",
                     "https://notebooklm.google.com/"])
    print("LAUNCHED notebooklm in Profile 3")
    time.sleep(4)
    print("done")

if __name__ == "__main__":
    main()
