"""CLI-bot only: long-poll commands from ``TELEGRAM_CLI_*``.

Uses ``ROLE_CLI``. Never reads ``TELEGRAM_BOT_TOKEN`` / publish chat ids.
The bot is always the 听筒: sync windows, run the command just heard.
"""

from __future__ import annotations

import ctypes
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable

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
from cli.commands import split_command
from utility.telegram_session import TelegramCliSession, welcome_text

# 秒回：不阻塞 getUpdates 长轮询
_FAST_INLINE_CMDS = frozenset(
    {
        "sync",
        "where",
        "here",
        "win",
        "screen",
        "status",
        "help",
        "commands",
        "start",
        "busy",
        "queue",
        "gui_health",
    }
)

# 只跟 GUI bridge 打交道的命令：几秒内返回，走独立「界面车道」，
# 这样 scnlm / scnvs 不会排在 nbi / scnge 这种十几分钟的浏览器任务后面。
_UI_LANE_CMDS = frozenset(
    {
        "scene",
        "scene_choices",
        "scene_lm",
        "scene_visual_style",
        "prompt_choice",
        "style",
        "instruction",
        "snippet",
        "content",
        "notebooklm",
        "save",
        "cancel",
        "generate",
        "publish",
        "analyze",
        "poem",
        "script",
        "cover",
        "cover_copy",
        "folder",
        "clips",
        "project",
        "profile",
        "scene_save",
        "scnsave",
        "ssave",
        "s_save",
    }
)

_UI_LANE = "ui"
_JOB_LANE = "job"

# 超过这个秒数还没结束就主动播报，避免 Telegram 完全静默
_UI_LANE_WARN_S = 45.0
_JOB_LANE_WARN_S = 300.0
# 界面命令超过这个秒数就放弃等待，免得一条卡死的命令永久占住界面车道
_UI_LANE_ABANDON_S = 90.0


def _lane_for(cmd: str) -> str:
    return _UI_LANE if cmd in _UI_LANE_CMDS else _JOB_LANE


class _OutboundMessenger:
    """Send Telegram replies on a background thread so long CLI jobs never block acks."""

    def __init__(self, role: str, chat_id: str) -> None:
        self._role = role
        self._chat_id = chat_id
        self._q: queue.Queue[str | None] = queue.Queue()
        threading.Thread(
            target=self._loop, daemon=True, name="cli-telegram-outbound"
        ).start()

    def send(self, text: str) -> None:
        body = (text or "").strip()
        if body:
            self._q.put(body)

    def _loop(self) -> None:
        while True:
            text = self._q.get()
            if text is None:
                return
            try:
                send_message(self._role, self._chat_id, text, timeout=30)
            except Exception as exc:
                print(f"[cli] outbound send failed: {exc}", flush=True)


class _AsyncCliWorker:
    """后台执行 CLI；Telegram 立刻 ack，完成后再发 ok/error。

    两条独立车道：

    * ``ui``  — 只跟 GUI bridge 打交道（scnlm / scnvs / save …），秒级返回。
    * ``job`` — 浏览器自动化（scnge / nbi / grv …），可能跑十几分钟。

    分开跑，长任务就不会堵住界面命令。
    """

    _LANE_LABELS = {_UI_LANE: "界面", _JOB_LANE: "长任务"}

    def __init__(
        self,
        session: TelegramCliSession,
        notify: Callable[[str], None],
    ) -> None:
        self._session = session
        self._notify = notify
        self._lock = threading.Lock()
        self._current: dict[str, str] = {_UI_LANE: "", _JOB_LANE: ""}
        self._current_id: dict[str, str] = {_UI_LANE: "", _JOB_LANE: ""}
        self._q: dict[str, queue.Queue[tuple[str, str]]] = {
            _UI_LANE: queue.Queue(),
            _JOB_LANE: queue.Queue(),
        }
        for lane in (_UI_LANE, _JOB_LANE):
            threading.Thread(
                target=self._loop,
                args=(lane,),
                daemon=True,
                name=f"cli-telegram-{lane}",
            ).start()

    def _pending(self, lane: str) -> list[str]:
        try:
            return [item[1] for item in list(self._q[lane].queue)]
        except Exception:
            return []

    def format_busy(self) -> str:
        lines = ["听筒任务队列（界面 / 长任务 分开跑）："]
        with self._lock:
            for lane in (_UI_LANE, _JOB_LANE):
                label = self._LANE_LABELS[lane]
                cur = self._current[lane]
                if cur:
                    lines.append(f"[{label}] ▶ 执行中 [{self._current_id[lane]}] {cur}")
                else:
                    lines.append(f"[{label}] ▶ 空闲")
                for i, item in enumerate(self._pending(lane), 1):
                    lines.append(f"    {i}. {item}")
        lines.append("界面命令（scnlm / scnvs / save …）不会排在长任务后面。")
        return "\n".join(lines)

    def submit(self, text: str) -> tuple[bool, str]:
        raw = (text or "").strip()
        if not raw:
            return False, "empty command"
        from utility.telegram_session import scene_choice_pick_pending, whole_story_pick_pending

        if scene_choice_pick_pending():
            digit = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            if digit.isdigit() and " " not in raw and len(digit) <= 2:
                return self._session.handle(raw)
        if whole_story_pick_pending():
            digit = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            if digit.isdigit() and " " not in raw and len(digit) <= 2:
                return self._session.handle(raw)

        cmd, _ = split_command(raw)
        if cmd in _FAST_INLINE_CMDS:
            if cmd in ("busy", "queue"):
                return True, self.format_busy()
            return self._session.handle(raw)

        lane = _lane_for(cmd)
        label = self._LANE_LABELS[lane]
        job_id = uuid.uuid4().hex[:6]

        with self._lock:
            current = self._current[lane]
            pending = self._pending(lane)
            # 重复提交同一条命令只会互相干扰（例如连发两次 scn）。
            if raw.lower() == current.lower():
                return False, (
                    f"[{label}] 这条命令正在跑：[{self._current_id[lane]}] {current}\n"
                    "等它回 ok/error，或发 busy 看队列。"
                )
            if any(raw.lower() == p.lower() for p in pending):
                return False, f"[{label}] 这条命令已在队列里，不重复排队。"
            position = (1 if current else 0) + len(pending) + 1
            self._q[lane].put((job_id, raw))

        if position == 1:
            return True, (
                f"⏳ [{label}] 已开始 [{job_id}] {raw}\n"
                "听筒继续收消息；完成后另发 ok/error。"
            )
        return True, (
            f"⏳ [{label}] 已排队 #{position} [{job_id}] {raw}\n"
            + (f"当前：{current}\n" if current else "")
            + "发 busy 可看队列。"
        )

    def _watchdog(self, lane: str, job_id: str, text: str, done: threading.Event) -> None:
        """Never let Telegram go silent: report a command that overruns its lane."""
        warn_after = _UI_LANE_WARN_S if lane == _UI_LANE else _JOB_LANE_WARN_S
        waited = 0.0
        while not done.wait(warn_after):
            waited += warn_after
            self._notify(
                f"⚠️ [{job_id}] {text} 已经跑了 {waited:.0f} 秒还没结束。\n"
                + (
                    "界面命令通常几秒就好，多半是 GUI 卡住了。发 gui 看诊断。"
                    if lane == _UI_LANE
                    else "长任务还在跑，发 busy 看队列。"
                )
            )
            warn_after = max(warn_after, 120.0)

    def _loop(self, lane: str) -> None:
        from cli.win_gui_tasks import ensure_uia_com

        ensure_uia_com()
        label = self._LANE_LABELS[lane]
        while True:
            job_id, text = self._q[lane].get()
            with self._lock:
                self._current[lane] = text
                self._current_id[lane] = job_id
            started = time.monotonic()
            done = threading.Event()
            threading.Thread(
                target=self._watchdog,
                args=(lane, job_id, text, done),
                daemon=True,
                name=f"cli-watchdog-{job_id}",
            ).start()
            try:
                if lane == _UI_LANE:
                    # A wedged Win32/UIA call must not own the UI lane forever.
                    from cli.win_gui_tasks import call_with_timeout

                    result = call_with_timeout(
                        lambda t=text: self._session.handle(t), _UI_LANE_ABANDON_S, None
                    )
                    if result is None:
                        raise TimeoutError(
                            f"界面命令 {_UI_LANE_ABANDON_S:.0f} 秒没返回，已放弃等待。\n"
                            "GUI 多半卡住了 — 发 gui 看诊断，必要时重启 GUI。"
                        )
                    ok, reply = result
                else:
                    ok, reply = self._session.handle(text)
                prefix = "ok" if ok else "error"
                took = time.monotonic() - started
                suffix = f"\n（{label}，用时 {took:.0f}s）" if took >= 20 else ""
                # Echo the command: ids alone are impossible to correlate once
                # several lanes report out of order.
                self._notify(f"{prefix} [{job_id}] {text}\n{reply}{suffix}")
            except Exception as exc:
                took = time.monotonic() - started
                self._notify(
                    f"error [{job_id}] {text}\n{exc}\n（{label}，用时 {took:.0f}s）"
                )
            finally:
                done.set()
                with self._lock:
                    self._current[lane] = ""
                    self._current_id[lane] = ""
                self._q[lane].task_done()


_CLI_BOT_MUTEX_NAME = "Local\\AIComposerCliTelegramListener"
_CLI_BOT_MUTEX_HANDLE = None
_ERROR_ALREADY_EXISTS = 183
_ERROR_FILE_NOT_FOUND = 2
_ERROR_ACCESS_DENIED = 5
_SYNCHRONIZE = 0x00100000


def _enable_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def cli_bot_mutex_held() -> bool:
    """True if the Telegram 听筒 mutex is already held (instant, no PowerShell)."""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_mutex = kernel32.OpenMutexW
        open_mutex.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
        open_mutex.restype = ctypes.c_void_p
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_bool

        handle = open_mutex(_SYNCHRONIZE, False, _CLI_BOT_MUTEX_NAME)
        err = ctypes.get_last_error()
    except Exception:
        return False
    if handle:
        try:
            close_handle(handle)
        except Exception:
            pass
        return True
    return err == _ERROR_ACCESS_DENIED


def _cli_bot_process_running() -> bool:
    """Slow fallback: scan for ``python -m cli bot``. Prefer ``cli_bot_mutex_held``."""
    return bool(_telegram_poll_holder_pids(cli_bot_only=True))


def _telegram_poll_holder_pids(*, cli_bot_only: bool = False) -> list[int]:
    """Local python processes that may hold Telegram getUpdates."""
    flag = (
        "$_.CommandLine -like '*-m cli bot*'"
        if cli_bot_only
        else (
            "($_.CommandLine -like '*-m cli bot*' -or "
            "$_.CommandLine -like '*telegram_bot_client*')"
        )
    )
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                f"Where-Object {{ $_.CommandLine -and {flag} }} | "
                "ForEach-Object { $_.ProcessId }",
            ],
            capture_output=True,
            text=True,
            timeout=6,
        )
    except Exception:
        return []
    out: list[int] = []
    for line in (completed.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            out.append(int(line))
    return out


def list_telegram_poll_holder_pids(*, exclude_pid: int | None = None) -> list[int]:
    """PIDs for local cli bot / Hermes client (may compete for getUpdates)."""
    skip = exclude_pid if exclude_pid is not None else os.getpid()
    return [pid for pid in _telegram_poll_holder_pids() if pid != skip]


def spawn_cli_bot_detached() -> bool:
    """Start ``python -m cli bot`` in a new console when the 听筒 is not running."""
    if cli_bot_already_running():
        return False
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    try:
        subprocess.Popen(
            [sys.executable, "-X", "utf8", "-m", "cli", "bot"],
            cwd=repo,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return True
    except Exception:
        return False


def cli_bot_already_running() -> bool:
    """True if a live 听筒 is polling Telegram."""
    if cli_bot_mutex_held():
        return True
    return _cli_bot_process_running()


def _acquire_cli_bot_mutex() -> bool:
    """Only one getUpdates listener per machine. A second copy causes Telegram 409.

    ``ctypes.windll.kernel32.GetLastError()`` does not reliably report the error
    of the preceding call, and a default ``restype`` truncates the 64-bit HANDLE.
    Both must be set explicitly or this guard silently lets duplicates through.
    """
    global _CLI_BOT_MUTEX_HANDLE
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        create_mutex.restype = ctypes.c_void_p

        handle = create_mutex(None, False, _CLI_BOT_MUTEX_NAME)
        err = ctypes.get_last_error()
    except Exception:
        return True

    if not handle:
        return True
    _CLI_BOT_MUTEX_HANDLE = handle
    return err != _ERROR_ALREADY_EXISTS


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
    outbound = _OutboundMessenger(ROLE_CLI, allowed_chat)

    def notify(text: str) -> None:
        outbound.send(text)

    worker = _AsyncCliWorker(session, notify=notify)

    try:
        outbound.send(welcome_text())
        from cli.ensure_gui import ensure_gui_from_queue, gui_windows_open
        from cli.gui_session import is_manual_gui_session

        if is_manual_gui_session():
            outbound.send(
                "电脑上已是 GUI_pm 手工会话，不会从队列自动 next。"
                "听筒跟着窗口同步；pick 已关掉。"
            )
        elif not gui_windows_open():
            ok_gui, gui_msg = ensure_gui_from_queue()
            if ok_gui and "已从队列打开" in gui_msg:
                outbound.send(
                    "电脑上还没有 STORY/SCENE，已从队列打开下一条未处理。"
                )
                outbound.send("ok\n" + gui_msg)
            elif ok_gui:
                outbound.send(
                    "电脑上还没有 STORY/SCENE。队列里没有未处理的了，"
                    "但已选过的都可以再选。请发 pick 1 / pick 2 / …",
                )
                outbound.send(gui_msg)
            else:
                outbound.send("error\n" + gui_msg)
        outbound.send(session.announce_sync())
    except Exception as exc:
        print(f"[cli] welcome/sync failed: {exc}", flush=True)

    stop_watch = threading.Event()

    def _watch_screens() -> None:
        from cli.win_gui_tasks import call_with_timeout

        while not stop_watch.wait(2.0):
            try:
                # Window probing can block on a frozen GUI; never stall the watcher.
                now_screen = call_with_timeout(current_screen, 5.0, None)
                if now_screen and now_screen != session.last_announced_screen:
                    notify(session.announce_sync())
            except Exception as exc:
                print(f"[cli] screen watch: {exc}", flush=True)

    threading.Thread(target=_watch_screens, name="cli-screen-watch", daemon=True).start()

    offset = 0
    conflict_streak = 0
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
            conflict_streak = 0
        except KeyboardInterrupt:
            stop_watch.set()
            print("[cli] stopped", flush=True)
            return 0
        except Exception as exc:
            msg = _safe_updates_error(exc)
            if "409" in msg:
                conflict_streak += 1
                print(f"[cli] getUpdates error: {msg}", flush=True)
                if conflict_streak >= 3:
                    print(
                        "[cli] 连续 409 — 已有 Hermes client 或其它听筒在轮询。"
                        "请只留一个窗口（run_bot 或 run_telegram_client，不要两个）。",
                        flush=True,
                    )
                    return 4
                time.sleep(2.0)
                continue
            print(f"[cli] getUpdates error: {msg}", flush=True)
            time.sleep(1.5)
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
            ok, reply = worker.submit(text)
            prefix = "ok" if ok else "error"
            outbound.send(f"{prefix}\n{reply}")
    return 0
