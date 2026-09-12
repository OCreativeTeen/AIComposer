"""StoryProducer Telegram 听筒 — 远程发 CLI，进程内执行，无 GUI。"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from storyproducer.engine import StoryEngine


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def run_bot(*, engine: StoryEngine | None = None) -> int:
    from utility.telegram import ROLE_CLI, get_updates, send_message, token_for, warn_if_tokens_overlap
    from utility.telegram_cli import cli_allowed_chat_id

    warn_if_tokens_overlap()
    if not token_for(ROLE_CLI) or not cli_allowed_chat_id():
        print("ERROR: TELEGRAM_CLI_BOT_TOKEN / TELEGRAM_CLI_CHAT_ID missing", flush=True)
        return 1
    chat = cli_allowed_chat_id()
    eng = engine or StoryEngine()
    offset = 0
    print(f"[{_now()}] StoryProducer bot 听筒启动（无 GUI）", flush=True)
    print("不要同时跑 cli\\run_bot.bat / cli\\run_telegram_client.bat（同一 token 会 409）。", flush=True)
    try:
        send_message(
            ROLE_CLI,
            chat,
            "StoryProducer bot 已上线（无 GUI）。\n发 pick / help 开始。",
        )
    except Exception as exc:
        print(f"Telegram hello failed: {exc}", flush=True)
    try:
        while True:
            try:
                updates = get_updates(ROLE_CLI, offset=offset, timeout=25)
            except Exception as exc:
                print(f"[{_now()}] poll: {exc}", flush=True)
                time.sleep(3.0)
                continue
            for upd in updates or []:
                uid = int((upd or {}).get("update_id") or 0)
                if uid:
                    offset = max(offset, uid + 1)
                msg = (upd or {}).get("message") or {}
                cid = str((msg.get("chat") or {}).get("id") or "")
                if chat and cid and cid != str(chat):
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                print(f"[{_now()}] telegram << {text}", flush=True)
                ok, reply = eng.dispatch(text)
                body = (("ok — " if ok else "error — ") + (reply or "")).strip()
                print(f"[{_now()}] {body}", flush=True)
                try:
                    send_message(ROLE_CLI, chat, body[:3500] if len(body) > 3500 else body)
                except Exception as exc:
                    print(f"send failed: {exc}", flush=True)
    except KeyboardInterrupt:
        print(f"[{_now()}] KeyboardInterrupt", flush=True)
        return 0
    return 0
