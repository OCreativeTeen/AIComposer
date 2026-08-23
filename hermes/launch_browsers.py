import subprocess, time, sys
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# Grok: 4 tabs in Profile 2 (ocreativeteen@gmail.com)
subprocess.Popen([CHROME, "--profile-directory=Profile 2", "--new-window",
                  "https://grok.com/imagine", "https://grok.com/imagine",
                  "https://grok.com/imagine", "https://grok.com/imagine"])
time.sleep(3)
# NotebookLM Studio in Profile 3 (myhomefun@gmail.com)
subprocess.Popen([CHROME, "--profile-directory=Profile 3", "--new-window",
                  "https://notebooklm.google.com"])
print("LAUNCHED", flush=True)
