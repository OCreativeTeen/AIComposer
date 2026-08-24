"""CLI-bot only: long-poll commands from ``TELEGRAM_CLI_*``.

Uses ``ROLE_CLI``. Never reads ``TELEGRAM_BOT_TOKEN`` / publish chat ids.
The bot is always the 听筒: sync windows, run the command just heard.
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import threading
import time

import config
from utility.telegram import (
    ROLE_CLI,
    get_updates,
    send_message,
    send_photo,
    token_for,
    warn_if_tokens_overlap,
)
from cli.screens import current_screen
from utility.telegram_session import TelegramCliSession, welcome_text

_CLI_BOT_MUTEX_NAME = "Local\\AIComposerCliTelegramListener"
_CLI_BOT_MUTEX_HANDLE = None
_ERROR_ALREADY_EXISTS = 183
_SYNCHRONIZE = 0x00100000


def _enable_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _cli_bot_process_running() -> bool:
    """True only if a live ``python -m cli bot`` process exists."""
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -and $_.CommandLine -like '*-m cli bot*' } | "
                "Measure-Object | Select-Object -ExpandProperty Count",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    try:
        return int((completed.stdout or "0").strip() or "0") > 0
    except ValueError:
        return False


def cli_bot_already_running() -> bool:
    """True if a live 听筒 process is polling Telegram. Mutex alone is not enough."""
    return _cli_bot_process_running()


def _acquire_cli_bot_mutex() -> bool:
    """Only one getUpdates listener per machine. A second copy causes Telegram 409."""
    global _CLI_BOT_MUTEX_HANDLE
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, _CLI_BOT_MUTEX_NAME)
    if not handle:
        return True
    _CLI_BOT_MUTEX_HANDLE = handle
    if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        return False
    return True


def _safe_updates_error(exc: BaseException) -> str:
    text = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot<token>", str(exc))
    if "409" in text or "Conflict" in text:
        return (
            "409 Conflict：已经有另一个听筒在跟 Telegram 要消息。"
            "请关掉多余的「AIComposer CLI bot」窗口，只留一个。"
        )
    return text


def cli_bot_name() -> str:
    box = getattr(config, "TELEGRAM_CLI", None)
    if not isinstance(box, dict):
        return ""
    return (box.get("bot_name") or "").strip()


def cli_allowed_chat_id() -> str:
    box = getattr(config, "TELEGRAM_CLI", None)
    if not isinstance(box, dict):
        return ""
    return str(box.get("chat_id") or "").strip()


def notify_whole_story_covers_for_pick(files: list[str]) -> list[str]:
    """把 nbi 下载的封面图发到 CLI Telegram，请用户选 1/2/3（下一步 ``igp``）。"""
    lines: list[str] = []
    paths = [p for p in (files or []) if p and os.path.isfile(p)]
    if not paths:
        lines.append("Telegram：没有可发的封面图")
        return lines
    chat_id = cli_allowed_chat_id()
    if not token_for(ROLE_CLI) or not chat_id:
        lines.append("Telegram：未配置 CLI bot，跳过封面核验")
        return lines
    sent = 0
    errs: list[str] = []
    for i, path in enumerate(paths, 1):
        cap = f"NotebookLM 封面 {i}/{len(paths)}\n{os.path.basename(path)}"
        try:
            send_photo(ROLE_CLI, chat_id, path, cap)
            sent += 1
        except Exception as exc:
            errs.append(f"{i}: {exc}")
    if sent:
        lines.append(f"Telegram：已发 {sent}/{len(paths)} 张封面图")
        try:
            send_message(
                ROLE_CLI,
                chat_id,
                "请选一张整篇故事封面：回复 1 / 2 / 3"
                + (f"（共 {len(paths)} 张）" if len(paths) <= 3 else "")
                + "。\n选定后听筒会记下；再发 igp 把该图贴进所有 Grok 标签。",
            )
        except Exception as exc:
            lines.append(f"Telegram：封面选择说明发送失败 — {exc}")
    if errs:
        lines.append(
            "Telegram：部分封面发送失败 — "
            + "; ".join(errs[:3])
            + ("…" if len(errs) > 3 else "")
        )
    return lines


def run_cli_bot(handle_text=None, mode: str | None = None) -> int:
    """Poll the CLI 听筒. Stays up until the window is closed."""
    del handle_text
    from cli.mode import get_mode, set_mode

    _enable_utf8_stdio()
    if mode:
        set_mode(mode)
    warn_if_tokens_overlap()
    token = token_for(ROLE_CLI)
    allowed_chat = cli_allowed_chat_id()
    if not token:
        print("ERROR: TELEGRAM_CLI_BOT_TOKEN missing in .env", flush=True)
        return 1
    if not allowed_chat:
        print("ERROR: TELEGRAM_CLI_CHAT_ID missing in .env", flush=True)
        return 1

    if not _acquire_cli_bot_mutex():
        print("听筒已经在跑。这个窗口可以关掉，沿用原来的那一个。", flush=True)
        return 3

    print("Telegram CLI 听筒（人 / Hermes）", flush=True)
    print("没有 STORY/SCENE 时会从队列打开一条，然后可用 pick", flush=True)
    print("纯手工请只开 GUI_pm.py，不必开本窗口。", flush=True)
    print("关掉本窗口 = 停止远程控制。", flush=True)

    label = cli_bot_name() or "@cli-bot"
    print(f"[cli] Telegram CLI 听筒 as {label} (chat_id={allowed_chat})", flush=True)
    print(f"[cli] mode={get_mode()}", flush=True)

    session = TelegramCliSession()

    def notify(text: str) -> None:
        try:
            send_message(ROLE_CLI, allowed_chat, text)
        except Exception as exc:
            print(f"[cli] notify failed: {exc}", flush=True)

    try:
        send_message(ROLE_CLI, allowed_chat, welcome_text())
        from cli.ensure_gui import ensure_gui_from_queue, gui_windows_open
        from cli.gui_session import is_manual_gui_session

        if is_manual_gui_session():
            send_message(
                ROLE_CLI,
                allowed_chat,
                "电脑上已是 GUI_pm 手工会话，不会从队列自动 next。"
                "听筒跟着窗口同步；pick 已关掉。",
            )
        elif not gui_windows_open():
            ok_gui, gui_msg = ensure_gui_from_queue()
            if ok_gui and "已从队列打开" in gui_msg:
                send_message(
                    ROLE_CLI,
                    allowed_chat,
                    "电脑上还没有 STORY/SCENE，已从队列打开下一条未处理。",
                )
                send_message(ROLE_CLI, allowed_chat, "ok\n" + gui_msg)
            elif ok_gui:
                send_message(
                    ROLE_CLI,
                    allowed_chat,
                    "电脑上还没有 STORY/SCENE。队列里没有未处理的了，"
                    "但已选过的都可以再选。请发 pick 1 / pick 2 / …",
                )
                send_message(ROLE_CLI, allowed_chat, gui_msg)
            else:
                send_message(ROLE_CLI, allowed_chat, "error\n" + gui_msg)
        send_message(ROLE_CLI, allowed_chat, session.announce_sync())
    except Exception as exc:
        print(f"[cli] welcome/sync failed: {exc}", flush=True)

    stop_watch = threading.Event()

    def _watch_screens() -> None:
        while not stop_watch.wait(1.2):
            try:
                now_screen = current_screen()
                if now_screen != session.last_announced_screen:
                    notify(session.announce_sync())
            except Exception as exc:
                print(f"[cli] screen watch: {exc}", flush=True)

    threading.Thread(target=_watch_screens, name="cli-screen-watch", daemon=True).start()

    offset = 0
    try:
        for upd in get_updates(ROLE_CLI, offset=0, timeout=0, request_timeout=30):
            uid = upd.get("update_id")
            if isinstance(uid, int) and uid >= offset:
                offset = uid + 1
    except Exception as exc:
        print(f"[cli] warning: could not drain updates: {_safe_updates_error(exc)}", flush=True)

    while True:
        try:
            updates = get_updates(
                ROLE_CLI,
                offset=offset,
                timeout=25,
                request_timeout=45,
            )
        except KeyboardInterrupt:
            stop_watch.set()
            print("[cli] stopped", flush=True)
            return 0
        except Exception as exc:
            msg = _safe_updates_error(exc)
            print(f"[cli] getUpdates error: {msg}", flush=True)
            time.sleep(8 if "409" in msg else 2)
            continue

        for upd in updates:
            uid = upd.get("update_id")
            if isinstance(uid, int):
                offset = uid + 1
            msg = upd.get("message") or upd.get("edited_message") or {}
            if not msg:
                continue
            chat = msg.get("chat") or {}
            chat_id = str(chat.get("id") or "").strip()
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            if chat_id != allowed_chat:
                print(f"[cli] ignore chat_id={chat_id}", flush=True)
                continue
            print(f"[cli] << {text}", flush=True)
            ok, reply = session.handle(text, notify=notify)
            prefix = "ok" if ok else "error"
            try:
                send_message(ROLE_CLI, chat_id, f"{prefix}\n{reply}")
            except Exception as exc:
                print(f"[cli] sendMessage failed: {exc}", flush=True)
    return 0
