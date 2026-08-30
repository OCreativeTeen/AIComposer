"""Hermes Telegram bot client — wrap the story-video harness in one process.

Follows ``D:\\Hermes\\AIComposer_Workflow_Prompt_v2.md``:

- Drive AIComposer with local CLI (``cli.commands.dispatch``), not Telegram commands.
- Telegram is for status + the **human** cover pick (1/2/3). Never auto-pick.
- Do **not** long-poll getUpdates while ``python -m cli bot`` is running
  (one bot token = one poller; a second poller causes 409 and slow replies).

Run::

    python -m cli.telegram_bot_client
    python -m cli client
    cli\\run_telegram_client.bat
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

NBI_ACCOUNTS = {
    1: "ocreativeteen",
    2: "triumphdt777",
    3: "myhomefun",
    4: "creative4teen",
    5: "mindstoryroom",
}

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_STOP_WORDS = frozenset(
    {"stop", "exit", "quit", "结束", "停", "halt", "abort"}
)
_SKIP_WORDS = frozenset({"skip", "跳过", "next"})
_COVER_WAIT_REMIND_S = 180.0
_NBIF_INTERVAL_S = 60.0
_NBIF_MIN_DURATION_S = 300.0  # 至少轮询 5 分钟才允许因超时而退出
_NBIF_MAX_DURATION_S = 2400.0  # 上限约 40 分钟
_GRV_DOWNLOAD_WAIT_S = 120.0
_HEARTBEAT_STUCK_S = 150.0


def _enable_utf8_stdio() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


class PipelineError(RuntimeError):
    """A step failed after retries; abort this story (or the whole run)."""


class NbifTimeoutError(PipelineError):
    """nbif 轮询超时：写入队列后退出，不关 Chrome，等人工 resume。"""

    def __init__(
        self,
        message: str,
        *,
        polls_done: int = 0,
        elapsed_s: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.polls_done = int(polls_done)
        self.elapsed_s = float(elapsed_s)


class HermesTelegramClient:
    """Local harness: CLI state machine + Telegram cover-pick inbox."""

    def __init__(
        self,
        *,
        pick: str = "next",
        once: bool = False,
        lm: str = "4",
        nbi: int | None = None,
        grv_profile: int = 1,
        grv_variant: int = 3,
        telegram: bool = True,
        telegram_inbox: bool = False,
        resume_nbif: bool = False,
    ) -> None:
        self.pick_arg = (pick or "next").strip() or "next"
        self.once = bool(once)
        self.lm = (lm or "4").strip() or "4"
        self.nbi_override = int(nbi) if nbi is not None else None
        self.grv_profile = max(1, int(grv_profile))
        self.grv_variant = max(1, int(grv_variant))
        self.telegram_enabled = bool(telegram)
        self.telegram_inbox = bool(telegram_inbox)
        self.resume_nbif = bool(resume_nbif)

        self._stop = threading.Event()
        self._stop_requested = False
        self._skip_requested = False
        self._tg_offset = 0
        self._tg_thread: threading.Thread | None = None
        self._listener_owns_inbox = True
        self._nbi_used = 0
        self._cover_lock = threading.Lock()
        self._cover_tg_offset = 0
        self._last_tg = 0.0

    # ------------------------------------------------------------------ logging

    def log(self, msg: str, *, telegram: bool = False) -> None:
        text = (msg or "").rstrip()
        print(f"[{_now()}] {text}", flush=True)
        if telegram:
            self._tg_send(text)

    def _tg_send(self, msg: str) -> None:
        if not self.telegram_enabled:
            return
        now = time.monotonic()
        if now - self._last_tg < 0.4:
            time.sleep(0.4)
        self._last_tg = time.monotonic()
        try:
            from utility.telegram import ROLE_CLI, send_message
            from utility.telegram_cli import cli_allowed_chat_id

            chat = cli_allowed_chat_id()
            if not chat:
                return
            body = (msg or "").strip()
            if len(body) > 3500:
                body = body[:3500] + "\n…"
            send_message(ROLE_CLI, chat, body)
        except Exception as exc:
            print(f"[{_now()}] Telegram send failed: {exc}", flush=True)

    # ------------------------------------------------------------------ CLI

    def cli(self, raw: str) -> tuple[bool, str]:
        from cli.commands import dispatch

        cmd = (raw or "").strip()
        self.log(f">>> {cmd}")
        ok, msg = dispatch(cmd)
        shown = (msg or "").strip()
        prefix = "ok" if ok else "error"
        self.log(f"{prefix} — {shown}")
        return ok, shown

    def cli_ok(self, raw: str, *, contain: str = "", tries: int = 1, pause_s: float = 2.0) -> str:
        last = ""
        for i in range(max(1, tries)):
            self._wait_gui_if_stuck()
            ok, msg = self.cli(raw)
            last = msg
            if ok and (not contain or contain.lower() in (msg or "").lower()):
                return msg
            if i + 1 < tries:
                time.sleep(pause_s)
        raise PipelineError(f"`{raw}` failed: {last}")

    # ------------------------------------------------------------------ windows / heartbeat

    def _story_scene_windows(self) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
        from cli.win_gui_tasks import enum_windows_safe

        stories = [
            (h, t) for h, t in enum_windows_safe(sub="STORY |") if (t or "").upper().startswith("STORY")
        ]
        scenes = [
            (h, t) for h, t in enum_windows_safe(sub="SCENE |") if (t or "").upper().startswith("SCENE")
        ]
        if not stories:
            stories = enum_windows_safe(sub="STORY |")
        if not scenes:
            scenes = enum_windows_safe(sub="SCENE |")
        return stories, scenes

    def _public_win(self) -> str:
        from cli.screens import current_screen, public_screen_name

        return public_screen_name(current_screen())

    def _wait_gui_if_stuck(self) -> None:
        from cli.bridge import gui_heartbeat

        start = time.monotonic()
        while not self._stop.is_set():
            beat = gui_heartbeat()
            if beat is None:
                return
            if beat.get("pump_alive"):
                return
            age = float(beat.get("pump_age_s") or 0)
            waited = time.monotonic() - start
            self.log(f"GUI pump_alive=false (age={age:.0f}s) — wait {waited:.0f}s")
            if waited > _HEARTBEAT_STUCK_S:
                self.log(
                    f"GUI still stuck after {waited:.0f}s; continuing anyway",
                    telegram=True,
                )
                return
            time.sleep(15.0)

    def _ensure_single_instance(self) -> None:
        stories, scenes = self._story_scene_windows()
        extra = stories[1:] + scenes[1:]
        if len(stories) <= 1 and len(scenes) <= 1:
            return
        self.log(
            f"extra windows: STORY×{len(stories)} SCENE×{len(scenes)} — closing extras",
            telegram=True,
        )
        for hwnd, title in extra:
            self.log(f"WM_CLOSE extra: {title}")
            self._close_hwnd(hwnd)
        time.sleep(1.5)

    def _close_hwnd(self, hwnd: int) -> None:
        try:
            import win32con
            import win32gui
        except Exception:
            return
        if not hwnd:
            return
        try:
            if not win32gui.IsWindow(hwnd):
                return
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            return
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            try:
                if not win32gui.IsWindow(hwnd):
                    return
            except Exception:
                return
            self._dismisscnsave_prompt()
            time.sleep(0.35)

    def _dismisscnsave_prompt(self) -> None:
        try:
            import uiautomation as auto
        except Exception:
            return
        for name in ("否", "不保存", "No", "&No", "Don't Save"):
            try:
                btn = auto.ButtonControl(searchDepth=10, Name=name)
                if btn.Exists(0.15, 0.04):
                    btn.Click()
                    return
            except Exception:
                continue

    def _close_current_story(self) -> None:
        win = self._public_win()
        if win == "scene":
            try:
                self.cli("cx")
            except Exception:
                pass
            time.sleep(0.6)
        stories, scenes = self._story_scene_windows()
        for hwnd, title in scenes + stories:
            self.log(f"close {title}")
            self._close_hwnd(hwnd)
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            if self._public_win() == "none" and not self._story_scene_windows()[0]:
                self.log("win=none")
                return
            time.sleep(0.5)
            stories, scenes = self._story_scene_windows()
            for hwnd, _title in scenes + stories:
                self._close_hwnd(hwnd)
        self.log("windows still open after close attempt", telegram=True)

    # ------------------------------------------------------------------ Telegram inbox

    def _listener_running(self) -> bool:
        try:
            from utility.telegram_cli import cli_bot_already_running

            return bool(cli_bot_already_running())
        except Exception:
            return False

    def _start_telegram_inbox(self) -> None:
        """Outbound status is always OK. Never steal getUpdates from the 听筒.

        Telegram allows only one getUpdates poller per bot. This client used to
        long-poll as well, which caused 409 Conflict and made ``python -m cli bot``
        sit idle for seconds between retries.
        """
        self._listener_owns_inbox = True
        if not self.telegram_enabled:
            return
        if not self.telegram_inbox:
            self.log(
                "Telegram：只发进度，不轮询。封面 1/2/3 由听筒 (cli bot) 接收。",
            )
            return
        if self._listener_running():
            self.log(
                "听筒已在跑：本 client 不抢 getUpdates，封面选图走 JSON。",
                telegram=True,
            )
            self.log(
                "⚠️ 听筒与 client 共用同一 GUI bridge：跑 client 时不要在 Telegram "
                "发 gem / lm / scn / nbi 等命令（只回封面 1/2/3），否则会出现 "
                "GUI stuck / lm 假失败。",
                telegram=True,
            )
            return
        self._listener_owns_inbox = False
        self._tg_thread = threading.Thread(
            target=self._telegram_loop, name="hermes-tg", daemon=True
        )
        self._tg_thread.start()

    def _telegram_loop(self) -> None:
        from utility.telegram import ROLE_CLI, get_updates
        from utility.telegram_cli import cli_allowed_chat_id

        allowed = cli_allowed_chat_id()
        while not self._stop.wait(0.2):
            try:
                updates = get_updates(
                    ROLE_CLI,
                    offset=self._tg_offset,
                    timeout=25,
                    request_timeout=45,
                )
            except KeyboardInterrupt:
                return
            except Exception as exc:
                msg = str(exc)
                self.log(f"getUpdates: {msg}")
                if "409" in msg:
                    self._listener_owns_inbox = True
                    self.log("409：改由听筒收消息，本 client 不再轮询。", telegram=True)
                    return
                time.sleep(4.0)
                continue
            for upd in updates:
                uid = upd.get("update_id")
                if isinstance(uid, int):
                    self._tg_offset = uid + 1
                msg = upd.get("message") or upd.get("edited_message") or {}
                text = (msg.get("text") or "").strip()
                chat = msg.get("chat") or {}
                chat_id = str(chat.get("id") or "").strip()
                if not text:
                    continue
                if allowed and chat_id and chat_id != allowed:
                    continue
                self.log(f"telegram << {text}")
                self._on_telegram_text(text)

    def _on_telegram_text(self, raw: str) -> None:
        text = (raw or "").strip()
        if not text:
            return
        low = text.lower()
        if low in _STOP_WORDS or text in _STOP_WORDS:
            self._stop_requested = True
            self.log("收到 stop — 本条做完后结束。", telegram=True)
            return
        if low in _SKIP_WORDS or text in _SKIP_WORDS:
            self._skip_requested = True
            self.log("收到 skip。", telegram=True)
            return
        from utility.telegram_session import whole_story_pick_pending

        if not whole_story_pick_pending():
            return
        digit = text.translate(_FULLWIDTH_DIGITS)
        if digit.isdigit() and " " not in text and 1 <= int(digit) <= 9:
            self._apply_cover_pick(int(digit))
            return
        compact = text.translate(_FULLWIDTH_DIGITS).lower()
        if compact.startswith("itc "):
            parts = compact.split()
            if len(parts) == 2 and parts[1].isdigit():
                self._apply_cover_pick(int(parts[1]))
                return
            if len(parts) >= 3 and parts[1] == "pick" and parts[2].isdigit():
                self._apply_cover_pick(int(parts[2]))
                return

    def _apply_cover_pick(self, index: int) -> None:
        with self._cover_lock:
            ok, msg = self.cli(f"itc {index}")
        if ok:
            self.log(f"封面已选 #{index}\n{msg}", telegram=True)
        else:
            self.log(f"封面选择失败 #{index}\n{msg}", telegram=True)

    def _sync_cover_telegram_offset(self) -> None:
        """Ignore Telegram messages sent before itc posted the 3 covers."""
        if not self.telegram_enabled or self._listener_running():
            return
        from utility.telegram import ROLE_CLI, get_updates

        try:
            for upd in get_updates(
                ROLE_CLI,
                offset=self._cover_tg_offset,
                timeout=0,
                request_timeout=20,
            ):
                uid = upd.get("update_id")
                if isinstance(uid, int):
                    self._cover_tg_offset = max(self._cover_tg_offset, uid + 1)
        except Exception as exc:
            self.log(f"封面选图：同步 Telegram offset 失败：{exc}")

    def _poll_telegram_cover_replies(self) -> None:
        """When 听筒 is off, client polls 1/2/3 itself (outbound-only mode)."""
        if not self.telegram_enabled or self._listener_running():
            return
        from utility.telegram import ROLE_CLI, get_updates
        from utility.telegram_cli import cli_allowed_chat_id

        allowed = cli_allowed_chat_id()
        try:
            updates = get_updates(
                ROLE_CLI,
                offset=self._cover_tg_offset,
                timeout=8,
                request_timeout=20,
            )
        except Exception as exc:
            msg = str(exc)
            if "409" in msg:
                self.log(
                    "封面选图：听筒也在轮询 Telegram，本 client 改读 JSON。"
                    "若 1/2/3 无反应请只留 run_bot 或只留 client。",
                    telegram=True,
                )
                self._listener_owns_inbox = True
            return
        for upd in updates:
            uid = upd.get("update_id")
            if isinstance(uid, int):
                self._cover_tg_offset = uid + 1
            msg = upd.get("message") or upd.get("edited_message") or {}
            text = (msg.get("text") or "").strip()
            chat = msg.get("chat") or {}
            chat_id = str(chat.get("id") or "").strip()
            if not text:
                continue
            if allowed and chat_id and chat_id != allowed:
                continue
            self.log(f"telegram << {text}")
            self._on_telegram_text(text)

    # ------------------------------------------------------------------ steps

    def _pick_story(self) -> bool:
        from cli.ensure_gui import gui_windows_open
        from cli.gui_session import is_manual_gui_session
        from cli.video_choice_queue import first_pending_story_index, resolve_story_pick_index

        self._ensure_single_instance()
        win = self._public_win()
        if win in ("story", "scene") or gui_windows_open():
            ok, sync = self.cli("sync")
            self.log(f"已有故事窗 win={win}，不再 pick。\n{sync}", telegram=True)
            return True
        if is_manual_gui_session():
            self.log("GUI_pm 手工会话且没有 STORY/SCENE，无法 pick。", telegram=True)
            return False

        idx = resolve_story_pick_index(self.pick_arg)
        if idx is None:
            raw = (self.pick_arg or "").strip()
            if not raw:
                self.log("队列没有故事可选。", telegram=True)
                return False
            cmd = f"pick {raw}"
        else:
            want = (self.pick_arg or "").strip().lower().replace(" ", "")
            if want in ("next", "n", "下一个", "下一条", "") and not first_pending_story_index():
                self.log(
                    f"队列无未处理条，自动 pick {idx} 重做。",
                    telegram=True,
                )
            cmd = f"pick {idx}"

        try:
            msg = self.cli_ok(cmd, tries=2, pause_s=4.0)
        except PipelineError as exc:
            self.log(str(exc), telegram=True)
            return False
        if "没有未处理" in msg and "不要发 pick next" in msg:
            self.log(msg, telegram=True)
            return False
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            if self._public_win() in ("story", "scene") or gui_windows_open():
                self._ensure_single_instance()
                self.cli("win")
                self.cli("sync")
                return True
            time.sleep(1.0)
        self.log("pick 后 STORY 窗没有出现。", telegram=True)
        return False

    def _open_scene(self) -> None:
        win = self._public_win()
        if win == "scene":
            self.log("already on SCENE")
            return
        last_err = ""
        for _ in range(3):
            self._wait_gui_if_stuck()
            ok, msg = self.cli("scn")
            last_err = msg
            if ok and ("SCENE is in front" in msg or "already on scene" in msg.lower()):
                time.sleep(1.0)
                if self._public_win() == "scene":
                    return
            if "STORY 屏未绑定" in msg:
                raise PipelineError(msg)
            time.sleep(3.0)
        raise PipelineError(f"scn failed: {last_err}")

    def _lm_dropdown_is_4step(self, set_msg: str = "") -> bool:
        blob = (set_msg or "").lower()
        raw = set_msg or ""

        # commands.py 失败文案（勿用宽泛子串如「没变」——成功 ok 里也含「没变就是没选上」）
        if "没有作用到 scene" in blob:
            return False
        if "lm set 回了 ok，但" in raw or "下拉仍是" in raw:
            return False

        # 成功：lm ok — 4 Step Story …
        if "lm ok" in blob and "4 step" in blob:
            return True

        try:
            from cli.bridge import send_bridge_command
            from cli.screens import SCREEN_STORY_SCENE

            got_ok, got = send_bridge_command(
                screen=SCREEN_STORY_SCENE,
                op="get",
                field="lm",
                timeout_s=4.0,
            )
            if got_ok and "4 step" in (got or "").lower():
                return True
        except Exception:
            pass

        try:
            from utility.telegram_session import load_story_scene_prompt_choice

            label = (load_story_scene_prompt_choice().get("label") or "").strip()
            if self.lm == "4" and "4 step" in label.lower():
                self.log(f"lm 已确认（session 记录）：{label}", telegram=True)
                return True
        except Exception:
            pass
        return False

    def _select_lm(self) -> None:
        last = ""
        for _ in range(4):
            self._wait_gui_if_stuck()
            ok, msg = self.cli(f"lm {self.lm}")
            last = msg
            if ok and self._lm_dropdown_is_4step(msg):
                return
            time.sleep(2.5)
        raise PipelineError(f"lm {self.lm} 下拉未切到 4 Step Story: {last}")

    def _generate_scenes(self) -> None:
        last = ""
        for attempt in range(3):
            self._wait_gui_if_stuck()
            ok, msg = self.cli("gem")
            last = msg
            if ok and "scenes on clipboard" in msg.lower():
                return
            if ok and "已粘贴提示词" in msg:
                self.log("gem 已粘贴，等待生成后 fetch")
                time.sleep(25.0)
                for _ in range(8):
                    fok, fmsg = self.cli("fetch")
                    last = fmsg
                    if fok and "scenes on clipboard" in fmsg.lower():
                        return
                    time.sleep(15.0)
                continue
            if "prompt too short" in msg.lower() or "too short" in msg.lower():
                self.log("gem prompt too short — 重做 lm", telegram=True)
                self._select_lm()
                continue
            if not ok and attempt < 2:
                time.sleep(5.0)
                continue
        raise PipelineError(f"gem failed: {last}")

    def _scnsave_ok(self, msg: str) -> bool:
        low = (msg or "").lower()
        return (
            "scnsave ok" in low
            or "s_save ok" in low
            or "scenes saved to video_detail" in low
        )

    def _scene_save(self) -> None:
        last = ""
        for attempt in range(3):
            self._wait_gui_if_stuck()
            ok, msg = self.cli("scnsave")
            last = msg
            if ok and self._scnsave_ok(msg):
                return
            if "不是 JSON" in msg or "不是有效的 SCENE JSON" in msg:
                self.log("scnsave 不是 JSON — 重做 gem", telegram=True)
                self._generate_scenes()
                continue
            if "unknown command" in (msg or "").lower() and "scnsave" in (msg or "").lower():
                raise PipelineError(
                    "scnsave 命令未注册 — 请更新 AIComposer 并重启 GUI / client。"
                )
            if attempt < 2:
                time.sleep(2.0)
        raise PipelineError(f"scnsave failed: {last}")

    def _nbp_preset(self) -> None:
        self.cli_ok("nbp 1", contain="nbp ok", tries=3, pause_s=2.0)

    def _nbi_ring_size(self) -> int:
        try:
            import config

            return max(1, len(config.list_gemini_chrome_profiles() or []))
        except Exception:
            return max(1, len(NBI_ACCOUNTS))

    def _choose_nbi_start(self) -> tuple[int, str]:
        from utility.telegram_session import (
            load_notebooklm_last_profile,
            next_notebooklm_profile_index,
        )

        override = self.nbi_override
        self.nbi_override = None
        idx, label = next_notebooklm_profile_index(override=override)
        last = load_notebooklm_last_profile()
        if override is not None:
            self.log(
                f"nbi 本次指定 {idx} ({label or NBI_ACCOUNTS.get(idx, '?')})",
                telegram=True,
            )
        elif last.get("index"):
            self.log(
                f"nbi 上次 {last.get('index')} ({last.get('profile') or '?'}) → 本次切到 {idx} ({label})",
                telegram=True,
            )
        else:
            self.log(f"nbi 无上次记录，从 {idx} ({label}) 开始", telegram=True)
        return idx, label

    def _trigger_notebooklm(self) -> int:
        start, _label = self._choose_nbi_start()
        n = self._nbi_ring_size()
        order = list(range(start, n + 1)) + list(range(1, start))
        last = ""
        for acc in order:
            label = NBI_ACCOUNTS.get(acc) or ""
            try:
                import config

                profiles = config.list_gemini_chrome_profiles() or []
                if 1 <= acc <= len(profiles):
                    label = profiles[acc - 1].get("label") or label
            except Exception:
                pass
            self.log(f"nbi {acc} ({label or '?'})", telegram=True)
            ok, msg = self.cli(f"nbi {acc}")
            last = msg
            if ok and "nbi ok" in msg.lower():
                self._nbi_used = acc
                return acc
            if "Customize Infographic dialog did not open" in msg:
                self.log(f"nbi {acc} dialog 没开 — 同号重试一次", telegram=True)
                time.sleep(4.0)
                ok, msg = self.cli(f"nbi {acc}")
                last = msg
                if ok and "nbi ok" in msg.lower():
                    self._nbi_used = acc
                    return acc
            brief = (msg or "").strip().split("\n")[0][:160]
            self.log(f"nbi {acc} 失败，立即换下一个号：{brief}", telegram=True)
        raise PipelineError(f"nbi 全部 {n} 个账号都失败: {last}")

    def _poll_notebooklm_ready(self) -> None:
        start = time.monotonic()
        poll_n = 0
        while time.monotonic() - start < _NBIF_MAX_DURATION_S:
            if self._stop_requested:
                raise PipelineError("stopped during nbif")
            poll_n += 1
            ok, msg = self.cli("nbif")
            low = (msg or "").lower()
            if ok and ("已经 ready" in msg or "infographic 已经 ready" in msg):
                return
            elapsed = time.monotonic() - start
            if "仍在生成" in msg or "generating" in low or "还没有 ready" in msg:
                self.log(
                    f"nbif poll {poll_n} — 已 {elapsed / 60:.1f} 分钟，"
                    f"等 {_NBIF_INTERVAL_S:.0f}s"
                )
                time.sleep(_NBIF_INTERVAL_S)
                continue
            if "还不能判定" in msg or "uncertain" in low:
                time.sleep(_NBIF_INTERVAL_S)
                continue
            if not ok:
                self.log(f"nbif error, retry: {msg}")
                time.sleep(_NBIF_INTERVAL_S)
                continue
            time.sleep(_NBIF_INTERVAL_S)
        elapsed = time.monotonic() - start
        if elapsed < _NBIF_MIN_DURATION_S:
            self.log(
                f"nbif 已达上限但未满 {_NBIF_MIN_DURATION_S / 60:.0f} 分钟，"
                f"再等 {_NBIF_INTERVAL_S:.0f}s 后重试",
                telegram=True,
            )
            time.sleep(_NBIF_INTERVAL_S)
            ok, msg = self.cli("nbif")
            if ok and ("已经 ready" in msg or "infographic 已经 ready" in msg):
                return
            elapsed = time.monotonic() - start
        raise NbifTimeoutError(
            f"nbif 超时：infographic 仍未 ready"
            f"（轮询 {poll_n} 次，约 {elapsed / 60:.1f} 分钟）",
            polls_done=poll_n,
            elapsed_s=elapsed,
        )

    def _mark_nbif_timeout(self, exc: NbifTimeoutError, *, nbi_acc: int) -> None:
        try:
            from cli.video_choice_queue import mark_active_item_nbif_timeout

            item = mark_active_item_nbif_timeout(
                error_msg=str(exc),
                nbi_profile_index=int(nbi_acc or 0),
                polls_done=int(exc.polls_done),
                elapsed_s=float(exc.elapsed_s),
            )
            if item:
                title = (item.get("title") or item.get("choice_id") or "?").strip()
                self.log(
                    f"队列已记录 nbif 超时：{title}\n"
                    f"choice_id={item.get('choice_id')}\n"
                    "未关闭 Chrome（请人工打开 NotebookLM 查看）。\n"
                    "确认可继续后运行：cli\\run_telegram_client_resume.bat",
                    telegram=True,
                )
        except Exception as mark_exc:
            self.log(f"队列写入 nbif 超时失败：{mark_exc}", telegram=True)

    def _ensure_nbi_chrome_profile(self, nbi_acc: int) -> None:
        """Resume: log recorded nbi index only — do not switch Chrome profile."""
        if nbi_acc <= 0:
            return
        self.log(
            f"resume：使用你已手动打开的 Chrome（不验证/切换 profile；"
            f"队列记录 nbi={nbi_acc}）",
            telegram=True,
        )

    def _prepare_resume_nbif(self) -> tuple[dict, int]:
        from cli.ensure_gui import ensure_gui_for_queue_item, gui_windows_open
        from cli.video_choice_queue import (
            activate_queue_item,
            find_nbif_timeout_resume_item,
        )

        item = find_nbif_timeout_resume_item()
        if not item:
            raise PipelineError(
                "队列里没有 nbif 轮询超时的条目。"
                "请先跑完 nbi，或检查 video_choice_queue.json。"
            )
        cid = (item.get("choice_id") or "").strip()
        title = (item.get("title") or item.get("row_key") or cid or "?").strip()
        nbi_acc = int(item.get("nbi_profile_index") or 0)
        self.log(
            f"resume：从 nbif 继续 — {title}\n"
            f"choice_id={cid}  nbi_profile={nbi_acc or '?'}",
            telegram=True,
        )
        try:
            activate_queue_item(cid)
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc

        if not gui_windows_open():
            ok, msg = ensure_gui_for_queue_item(item)
            if not ok:
                raise PipelineError(f"resume 打开 GUI 失败：{msg}")
            self.log(msg, telegram=True)
            deadline = time.monotonic() + 90.0
            while time.monotonic() < deadline:
                if self._public_win() in ("story", "scene") or gui_windows_open():
                    break
                time.sleep(1.0)
        else:
            self.cli("sync")
            self.log("GUI 已开 — 已 sync，从 nbif 继续轮询", telegram=True)

        if nbi_acc <= 0:
            try:
                from utility.telegram_session import load_notebooklm_last_profile

                nbi_acc = int(load_notebooklm_last_profile().get("index") or 0)
            except Exception:
                nbi_acc = 0
        self._ensure_nbi_chrome_profile(nbi_acc)
        return item, nbi_acc

    def _download_covers(self, nbi_acc: int, *, attach_only: bool = False) -> None:
        from cli.commands import download_notebooklm_covers_and_notify

        ok, msg = download_notebooklm_covers_and_notify(
            attach_only=attach_only,
            require_ready=not attach_only,
            close_chrome=False,
        )
        if ok and "已发 Telegram" in msg:
            self.log(msg)
            return
        if attach_only:
            raise PipelineError(f"itc failed (attach-only): {msg}")
        ok, msg = self.cli("itc")
        if ok and "已发 Telegram" in msg:
            return
        if "找不到已打开的 NotebookLM" in msg or (ok and "发 itc N" in msg):
            raise PipelineError(
                f"itc failed: {msg}\n"
                "resume 模式不会重开 Chrome。请保持 NotebookLM 窗口打开后再试。"
            )
        raise PipelineError(f"itc failed: {msg}")

    def _wait_human_cover_pick(self) -> str:
        from utility.telegram_session import (
            load_whole_story_image_record,
            selected_whole_story_image_path,
            whole_story_pick_pending,
        )

        self._sync_cover_telegram_offset()
        if self.telegram_enabled and not self._listener_running():
            self.log(
                "听筒未运行：本 client 会直接收 Telegram 的 1 / 2 / 3。",
                telegram=True,
            )
        elif self.telegram_enabled and self._listener_running():
            self.log(
                "听筒在跑：请在 Telegram 回 1/2/3（听筒写入 JSON，client 自动继续）。",
                telegram=True,
            )

        self.log(
            "【人工选封面】请在 Telegram 回复 1 / 2 / 3。Agent 不会代选。",
            telegram=True,
        )
        last_remind = time.monotonic()
        while not self._stop.is_set():
            self._poll_telegram_cover_replies()
            rec = load_whole_story_image_record()
            path = selected_whole_story_image_path()
            selected = int(rec.get("selected") or 0)
            if path and selected >= 1 and not rec.get("pending_pick"):
                self.log(f"封面已记录 selected={selected} path={path}", telegram=True)
                return path
            if self._stop_requested:
                raise PipelineError("stopped while waiting for cover pick")
            if self._skip_requested:
                self._skip_requested = False
                raise PipelineError("skip while waiting for cover pick")
            if time.monotonic() - last_remind >= _COVER_WAIT_REMIND_S:
                last_remind = time.monotonic()
                files = list(rec.get("files") or [])
                pending = whole_story_pick_pending()
                self.log(
                    f"仍在等选封面（共 {len(files)} 张；pending={pending}）。"
                    "请回 1 / 2 / 3。",
                    telegram=True,
                )
            time.sleep(2.0)
        raise PipelineError("stopped")

    def _ensure_story_scene_for_grv(self) -> None:
        """``grv`` 需要 SCENE 窗口已绑定；没有则 ``scn``，全无则从队列重开 GUI。"""
        from cli.ensure_gui import gui_windows_open
        from cli.video_choice_queue import (
            current_taken_queue_item,
            find_nbif_timeout_resume_item,
        )

        win = self._public_win()
        if win == "scene":
            self.log("SCENE 已在前台，继续 grv")
            return
        if win == "story":
            self.log("STORY 已开 — 执行 scn 打开 SCENE", telegram=True)
            self._open_scene()
            return
        if gui_windows_open():
            self.log("GUI 在但 SCENE 未绑定 — 执行 scn", telegram=True)
            self._open_scene()
            return

        item = current_taken_queue_item() or find_nbif_timeout_resume_item()
        if item:
            from cli.ensure_gui import ensure_gui_for_queue_item

            title = (item.get("title") or item.get("choice_id") or "?").strip()
            self.log(f"STORY/SCENE 已关 — 从队列重开：{title}", telegram=True)
            ok, msg = ensure_gui_for_queue_item(item)
            if not ok:
                raise PipelineError(f"重开 STORY 失败：{msg}")
            self.log(msg)
            deadline = time.monotonic() + 90.0
            while time.monotonic() < deadline:
                if self._public_win() in ("story", "scene") or gui_windows_open():
                    break
                time.sleep(1.0)
            self._ensure_single_instance()
            self.cli("sync")
            self._open_scene()
            return

        raise PipelineError(
            "STORY/SCENE 未打开，无法 grv。请先 pick 故事并 scn 打开 SCENE。"
        )

    def _grok_video(self) -> None:
        from utility.telegram_session import load_grok_scene_videos, story_scene_count

        self._ensure_story_scene_for_grv()
        cmd = f"grv {self.grv_profile} {self.grv_variant}"
        self.log(f"开始 {cmd}（可能 5–15 分钟）", telegram=True)
        ok, msg = self.cli(cmd)
        if not ok:
            if "没有封面" in msg:
                raise PipelineError(f"grv 没有封面图: {msg}")
            raise PipelineError(f"grv failed: {msg}")
        expected = story_scene_count() or 4
        deadline = time.monotonic() + _GRV_DOWNLOAD_WAIT_S
        while time.monotonic() < deadline:
            clips = load_grok_scene_videos()
            if len(clips) >= expected:
                self.log(f"grok clips ready: {len(clips)}/{expected}", telegram=True)
                return
            downloads = Path.home() / "Downloads"
            files = sorted(downloads.glob("grok_scene_*.mp4"))
            if len(files) >= expected:
                self.log(f"Downloads grok_scene_*.mp4 ×{len(files)}", telegram=True)
                return
            time.sleep(5.0)
        clips = load_grok_scene_videos()
        if clips:
            self.log(f"grv 结束，已有 {len(clips)} 个 clip（期望 {expected}）", telegram=True)
            return
        self.log("grv ok 但还没看到 mp4，试 gvd", telegram=True)
        self.cli("gvd")

    def _queue_has_pending(self) -> bool:
        from cli.video_choice_queue import first_pending_story_index

        return bool(first_pending_story_index())

    def run_one_story(self, *, resume_from_nbif: bool = False) -> bool:
        from cli.gui_session import is_manual_gui_session
        from cli.video_choice_queue import mark_active_item_workflow_step

        nbi_acc = 0
        skip_close_on_exit = False
        resume_choice_id = ""
        try:
            if resume_from_nbif:
                _item, nbi_acc = self._prepare_resume_nbif()
                resume_choice_id = (_item.get("choice_id") or "").strip()
                self.log(
                    "步骤 8 resume：直连已开 Chrome，下载三张 infographic（不重开 Chrome）",
                    telegram=True,
                )
                self._download_covers(nbi_acc, attach_only=True)
                from cli.video_choice_queue import mark_nbif_resume_succeeded

                mark_nbif_resume_succeeded(resume_choice_id)
            else:
                if not self._pick_story():
                    return False
                self._ensure_single_instance()
                self.log("步骤 2 scn", telegram=True)
                self._open_scene()
                self.log(f"步骤 3 lm {self.lm}", telegram=True)
                self._select_lm()
                self.log("步骤 4 gem", telegram=True)
                self._generate_scenes()
                self.log("步骤 5 scnsave", telegram=True)
                self._scene_save()
                self.log("步骤 6 nbp 1", telegram=True)
                self._nbp_preset()
                self.log("步骤 7 nbi", telegram=True)
                nbi_acc = self._trigger_notebooklm()
                mark_active_item_workflow_step(
                    workflow_step="nbif_poll",
                    nbi_profile_index=nbi_acc,
                )
                self.log("步骤 8 nbif 轮询", telegram=True)
                self._poll_notebooklm_ready()
                self.log("步骤 9 itc", telegram=True)
                self._download_covers(nbi_acc, attach_only=False)
            self.log("步骤 10 等待人工选封面", telegram=True)
            self._wait_human_cover_pick()
            self.log(
                f"步骤 11 确认 SCENE + grv {self.grv_profile} {self.grv_variant}",
                telegram=True,
            )
            self._grok_video()
            self.log("本条故事流水线完成。", telegram=True)
        except NbifTimeoutError as exc:
            skip_close_on_exit = True
            self._mark_nbif_timeout(exc, nbi_acc=nbi_acc)
            self.log(f"本条失败：{exc}", telegram=True)
            self.log(
                "已退出等待人工审核 NotebookLM。"
                "确认三张图 ready 后运行 cli\\run_telegram_client_resume.bat 继续 nbif。",
                telegram=True,
            )
            raise
        except PipelineError as exc:
            self.log(f"本条失败：{exc}", telegram=True)
            if resume_from_nbif:
                skip_close_on_exit = True
            raise
        finally:
            if not is_manual_gui_session() and not skip_close_on_exit:
                self.log("关闭当前 STORY/SCENE", telegram=True)
                try:
                    self._close_current_story()
                except Exception as exc:
                    self.log(f"关窗失败: {exc}")
        return True

    def run_resume_nbif(self) -> int:
        """从队列里上次 nbif 超时的条目继续轮询。"""
        from cli.win_gui_tasks import ensure_uia_com
        from utility.telegram import token_for, ROLE_CLI, warn_if_tokens_overlap
        from utility.telegram_cli import cli_allowed_chat_id

        _enable_utf8_stdio()
        ensure_uia_com()
        warn_if_tokens_overlap()

        if self.telegram_enabled:
            if not token_for(ROLE_CLI) or not cli_allowed_chat_id():
                print("ERROR: TELEGRAM_CLI_BOT_TOKEN / TELEGRAM_CLI_CHAT_ID missing", flush=True)
                return 1

        self._start_telegram_inbox()
        self.log(
            "Hermes resume：直连已开 Chrome 下载封面（不重开/关闭 Chrome）",
            telegram=True,
        )
        try:
            self.run_one_story(resume_from_nbif=True)
        except NbifTimeoutError:
            return 2
        except PipelineError:
            return 1
        return 0

    def run(self) -> int:
        from cli.win_gui_tasks import ensure_uia_com
        from utility.telegram import token_for, ROLE_CLI, warn_if_tokens_overlap
        from utility.telegram_cli import cli_allowed_chat_id

        _enable_utf8_stdio()
        ensure_uia_com()
        warn_if_tokens_overlap()

        if self.telegram_enabled:
            if not token_for(ROLE_CLI) or not cli_allowed_chat_id():
                print("ERROR: TELEGRAM_CLI_BOT_TOKEN / TELEGRAM_CLI_CHAT_ID missing", flush=True)
                return 1

        self._start_telegram_inbox()
        from utility.telegram_session import (
            load_notebooklm_last_profile,
            next_notebooklm_profile_index,
        )

        nbi_idx, nbi_label = next_notebooklm_profile_index(override=self.nbi_override)
        last_nbi = load_notebooklm_last_profile()
        last_note = (
            f"上次 nbi {last_nbi.get('index')} ({last_nbi.get('profile')})"
            if last_nbi.get("index")
            else "上次 nbi 无记录"
        )
        self.log(
            "Hermes Telegram client 启动\n"
            f"pick={self.pick_arg}  lm={self.lm}  "
            f"{last_note} → 本次 nbi {nbi_idx} ({nbi_label or '?'})  "
            f"grv {self.grv_profile} {self.grv_variant}\n"
            "封面必须由你在 Telegram 回 1/2/3。发 stop 可在本条结束后停。",
            telegram=True,
        )
        if self._listener_running():
            self.log(
                "⚠️ 检测到 run_bot 听筒也在跑：流水线由本 client 自动驱动，"
                "Telegram 上请勿再发 gem/lm/scn/nbi（只回 1/2/3 选封面）。",
                telegram=True,
            )

        stories = 0
        try:
            while not self._stop.is_set() and not self._stop_requested:
                try:
                    ran = self.run_one_story()
                except NbifTimeoutError:
                    return 2
                except PipelineError:
                    if self.once:
                        return 1
                    if self._stop_requested:
                        break
                    self.pick_arg = "next"
                    if not self._queue_has_pending() and self._public_win() == "none":
                        break
                    continue
                if not ran:
                    break
                stories += 1
                if self.once:
                    break
                if self._stop_requested:
                    break
                self.pick_arg = "next"
                if not self._queue_has_pending():
                    self.log("队列没有未处理故事，结束。", telegram=True)
                    break
        except KeyboardInterrupt:
            self.log("KeyboardInterrupt — 停止", telegram=True)
        finally:
            self._stop.set()

        self.log(f"Hermes client 退出（完成 {stories} 条）。", telegram=True)
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m cli.telegram_bot_client",
        description="Hermes：本机跑完整故事视频流水线；Telegram 只用于选封面。",
    )
    p.add_argument(
        "--pick",
        default="next",
        help="next（默认：下一条未处理；无未处理时自动 pick 1 重做）或队列序号如 1。已有 STORY/SCENE 时忽略。",
    )
    p.add_argument("--once", action="store_true", help="只做当前/下一条，做完退出")
    p.add_argument("--lm", default="4", help="LM 提示序号，默认 4 = 4 Step Story")
    p.add_argument(
        "--nbi",
        type=int,
        default=None,
        help="强制本次 nbi Chrome 号；默认读 aiagent/notebooklm_last_profile.json 后切到下一个",
    )
    p.add_argument("--grv-profile", type=int, default=1, dest="grv_profile", help="grv Chrome 号，默认 1")
    p.add_argument(
        "--grv-variant",
        type=int,
        default=3,
        dest="grv_variant",
        help="grv video 变体 1–8，默认 3（念 speaking）",
    )
    p.add_argument(
        "--no-telegram",
        action="store_true",
        help="不发 Telegram 状态；封面仍写 JSON，需另开听筒才能在 Telegram 选图",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="从 video_choice_queue 里上次 nbif 轮询超时的条目继续（不关 Chrome）",
    )
    p.add_argument(
        "--telegram-inbox",
        action="store_true",
        dest="telegram_inbox",
        help="本进程轮询 1/2/3（不要和 python -m cli bot 同时开，会 409 变慢）",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _enable_utf8_stdio()
    args = parse_args(argv)
    client = HermesTelegramClient(
        pick=args.pick,
        once=args.once,
        lm=str(args.lm),
        nbi=args.nbi,
        grv_profile=int(args.grv_profile),
        grv_variant=int(args.grv_variant),
        telegram=not args.no_telegram,
        telegram_inbox=bool(args.telegram_inbox),
        resume_nbif=bool(args.resume),
    )
    if args.resume:
        return client.run_resume_nbif()
    return client.run()


if __name__ == "__main__":
    raise SystemExit(main())
