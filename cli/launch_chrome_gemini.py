import subprocess, time, urllib.request, os

exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
args = [
    exe,
    "--user-data-dir=C:\\Users\\wenju\\AppData\\Local\\HermesChromeCDP",
    "--profile-directory=Profile 2",
    "--remote-debugging-port=9222",
    "--remote-allow-origins=*",
    "--new-window",
    "https://gemini.google.com/",
]
print("launching:", " ".join(args))
p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(7)
try:
    with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3) as r:
        print("CDP up:", r.read(200).decode())
except Exception as e:
    print("CDP not up yet:", e)
procs = sum(1 for l in os.popen("tasklist.exe").read().splitlines() if "chrome.exe" in l.lower())
print("chrome procs:", procs)
