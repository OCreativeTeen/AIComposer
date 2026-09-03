"""Manual helper: launch Gemini on HermesChromeCDP (same as ``python -m cli scnge``)."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from cli.browser_tasks import GEMINI_URL, resolve_chrome_profile_directory

config.set_gemini_chrome_profile(1)
exe = (config.CHROME_EXE or "").strip()
user_data = (config.CHROME_CDP_USER_DATA_DIR or "").strip()
profile_dir = resolve_chrome_profile_directory(config.GEMINI_CHROME_PROFILE)
port = int(config.CHROME_REMOTE_DEBUGGING_PORT or 9222)

args = [
    exe,
    f"--user-data-dir={user_data}",
    f"--profile-directory={profile_dir}",
    f"--remote-debugging-port={port}",
    "--remote-allow-origins=*",
    "--remote-debugging-address=127.0.0.1",
    "--no-first-run",
    "--no-default-browser-check",
    "--new-window",
    GEMINI_URL,
]
print("launching HermesChromeCDP:", " ".join(args))
subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(7)
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as r:
        print("CDP up:", r.read(200).decode())
except Exception as exc:
    print("CDP not up yet:", exc)
