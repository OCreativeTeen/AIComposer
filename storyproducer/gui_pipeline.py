"""StoryProducer GUI phase — open STORY + vc review for stories with scene clips."""

from __future__ import annotations

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

from storyproducer import workflow as wfstore

_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")
_STOP_WORDS = frozenset({"stop", "exit", "quit", "结束", "停", "halt", "abort"})
_NEXT_WORDS = frozenset(
    {
        "n",
        "next",
        "continue",
        "ok",
        "ready",
        "下一条",
        "下一个",
        "继续",
        "好了",
        "完成",
    }
)
_LIST_WORDS = frozenset({"list", "ls", "菜单", "刷新"})


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


class GuiPipelineError(RuntimeError):
    pass


class StoryProducerGuiClient:
    """After run_client: user picks story → GUI vc review → mark → pick again."""

    def __init__(
        self,
        *,
        pick: str = "",
        once: bool = False,
        require_all_clips: bool = False,
        skip_published: bool = False,
        telegram: bool = True,
        telegram_inbox: bool = True,
    ) -> None:
        want = (pick or "").strip().lower()
        self._first_pick = want if want.isdigit() else ""
        self.once = bool(once)
        self.require_all_clips = bool(require_all_clips)  # 仅影响提示文案
        self.skip_published = bool(skip_published)
        self.telegram_enabled = bool(telegram)
        self.telegram_inbox = bool(telegram_inbox)
        self._gui_reviewed_ids: set[str] = set()
        self._stop = threading.Event()
        self._stop_requested = False
        self._tg_offset = 0
        self._last_tg = 0.0
        self._inbox_thread: threading.Thread | None = None
        self._waiting_next = False
        self._next_event = threading.Event()
        self._waiting_pick = False
        self._pick_event = threading.Event()
        self._pick_digit = 0
        self._pick_max = 0
        self._choice_lock = threading.Lock()
        self._gui_opened = False

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

    def cli(self, raw: str) -> tuple[bool, str]:
        from cli.commands import dispatch

        cmd = (raw or "").strip()
        self.log(f">>> {cmd}")
        ok, msg = dispatch(cmd)
        shown = (msg or "").strip()
        self.log(("ok" if ok else "error") + " — " + shown)
        return ok, shown

    def _pick_menu_text(self) -> str:
        return wfstore.format_gui_pick_menu(
            session_reviewed=self._gui_reviewed_ids,
            require_all=self.require_all_clips,
        )

    def _start_telegram_inbox(self) -> None:
        if not self.telegram_enabled or not self.telegram_inbox:
            return
        t = threading.Thread(target=self._inbox_loop, name="sp-gui-tg", daemon=True)
        self._inbox_thread = t
        t.start()

    def _inbox_loop(self) -> None:
        from utility.telegram import ROLE_CLI, get_updates
        from utility.telegram_cli import cli_allowed_chat_id

        chat = cli_allowed_chat_id()
        while not self._stop.is_set():
            try:
                updates = get_updates(ROLE_CLI, offset=self._tg_offset, timeout=25)
            except Exception as exc:
                self.log(f"telegram poll: {exc}")
                time.sleep(3.0)
                continue
            for upd in updates or []:
                uid = int((upd or {}).get("update_id") or 0)
                if uid:
                    self._tg_offset = max(self._tg_offset, uid + 1)
                msg = (upd or {}).get("message") or {}
                cid = str((msg.get("chat") or {}).get("id") or "")
                if chat and cid and cid != str(chat):
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                self._on_telegram_text(text)

    def _on_telegram_text(self, text: str) -> None:
        raw = (text or "").strip()
        low = raw.lower().translate(_FULLWIDTH).replace(" ", "")
        self.log(f"telegram << {raw}")
        if low in _STOP_WORDS:
            self._stop_requested = True
            self._next_event.set()
            self._pick_event.set()
            return
        if self._waiting_pick:
            if low in _LIST_WORDS:
                self.log(self._pick_menu_text(), telegram=True)
                return
            digit = None
            if raw.translate(_FULLWIDTH).isdigit():
                digit = int(raw.translate(_FULLWIDTH))
            if digit is not None and 1 <= digit <= self._pick_max:
                with self._choice_lock:
                    self._pick_digit = digit
                self._pick_event.set()
                return
            return
        if self._waiting_next and low in _NEXT_WORDS:
            self._next_event.set()
            return
        ok, msg = self.cli(raw)
        self.log(("ok" if ok else "error") + " — " + (msg or ""), telegram=True)

    def _public_win(self) -> str:
        from cli.screens import current_screen, public_screen_name

        return public_screen_name(current_screen())

    def _queue_item_at(self, index: int) -> dict:
        from cli.video_choice_queue import queue_item_at

        item = queue_item_at(index)
        if not isinstance(item, dict):
            raise GuiPipelineError(f"队列第 {index} 条无效")
        return item

    def _queue_count(self) -> int:
        from cli.video_choice_queue import list_queue_items

        return len(list_queue_items())

    def _wait_story_pick(self, *, first: bool = False) -> int | None:
        n = self._queue_count()
        if n < 1:
            self.log("队列是空的。", telegram=True)
            return None
        if first and self._first_pick:
            idx = int(self._first_pick)
            self._first_pick = ""
            if 1 <= idx <= n:
                return idx
            self.log(f"无效的 --pick {idx}，改为交互选择。", telegram=True)

        self._pick_max = n
        self._waiting_pick = True
        self._pick_event.clear()
        with self._choice_lock:
            self._pick_digit = 0
        self.log(self._pick_menu_text(), telegram=True)

        try:
            if not self.telegram_enabled or not self.telegram_inbox:
                while not self._stop.is_set() and not self._stop_requested:
                    try:
                        raw = input("选故事序号（list=刷新 exit=结束）> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        return None
                    if not raw:
                        continue
                    low = raw.lower()
                    if low in _STOP_WORDS:
                        return None
                    if low in _LIST_WORDS:
                        print(self._pick_menu_text(), flush=True)
                        continue
                    if raw.isdigit():
                        d = int(raw)
                        if 1 <= d <= n:
                            return d
                    print(f"请输入 1…{n}，或 list / exit。", flush=True)
                return None

            while not self._stop.is_set() and not self._stop_requested:
                if self._pick_event.wait(timeout=1.0):
                    self._pick_event.clear()
                    with self._choice_lock:
                        d = int(self._pick_digit or 0)
                    if 1 <= d <= n:
                        return d
        finally:
            self._waiting_pick = False
        return None

    def _wait_gui_idle(self, timeout_s: float = 45.0) -> None:
        from cli.bridge import gui_heartbeat, wait_bridge_pump_alive

        beat = gui_heartbeat()
        if beat is None or beat.get("pump_alive"):
            return
        self.log(
            f"等待 GUI 完成当前任务（pump 已 {beat.get('pump_age_s')}s 未响应）…",
            telegram=True,
        )

        def _on_wait(age: float, waited: float) -> None:
            self.log(f"仍在等待 GUI… pump={age:.0f}s 已等 {waited:.0f}s", telegram=True)

        if not wait_bridge_pump_alive(timeout_s=timeout_s, on_wait=_on_wait):
            self.log("GUI 仍繁忙，将强制关闭。", telegram=True)

    def _shutdown_gui_session(self) -> None:
        from cli.ensure_gui import shutdown_queue_gui_session
        from cli.gui_session import gui_session_open

        if not self._gui_opened and not gui_session_open():
            return
        self.log("关闭当前 GUI 会话", telegram=True)
        self._wait_gui_idle(timeout_s=30.0)
        ok, msg = shutdown_queue_gui_session(
            run_cx=lambda: self.cli("cx"),
            wait_pump_s=20.0,
            timeout_s=45.0,
        )
        self.log(msg, telegram=True)
        if not ok:
            self.log("警告：GUI 可能未完全退出。", telegram=True)
        self._gui_opened = False
        time.sleep(1.5)

    def _pick_story_gui(self, index: int) -> None:
        from cli.ensure_gui import ensure_gui_for_queue_item, gui_windows_open
        from cli.gui_session import gui_session_open

        if self._gui_opened or gui_session_open():
            self._shutdown_gui_session()

        item = self._queue_item_at(index)
        last_err = ""
        for attempt in range(1, 4):
            ok, msg = ensure_gui_for_queue_item(item)
            if ok:
                self.log(msg, telegram=True)
                self._gui_opened = True
                deadline = time.monotonic() + 90.0
                while time.monotonic() < deadline:
                    if self._public_win() in ("story", "scene") or gui_windows_open():
                        self._wait_story_bridge_ready(timeout_s=120.0)
                        return
                    time.sleep(0.8)
                raise GuiPipelineError(f"打开 #{index} 后 STORY 窗未出现")
            last_err = msg or "unknown"
            stuck = any(
                k in last_err
                for k in ("pump", "卡住", "bridge", "无响应", "open_row")
            )
            self.log(f"打开 #{index} 失败（{attempt}/3）：{last_err}", telegram=True)
            if stuck and attempt < 3:
                self._shutdown_gui_session()
                time.sleep(2.0)
                continue
            break
        raise GuiPipelineError(f"pick {index} failed: {last_err}")

    def _wait_story_bridge_ready(self, timeout_s: float = 120.0) -> None:
        from cli.bridge import gui_heartbeat, wait_bridge_pump_alive
        from cli.commands import _wait_screen_ready
        from cli.screens import SCREEN_STORY_ROOT

        self.log("等待 STORY 界面与 bridge 就绪…", telegram=True)
        if not _wait_screen_ready(SCREEN_STORY_ROOT, timeout_s=min(timeout_s, 90.0)):
            raise GuiPipelineError("STORY 屏未就绪（仍在加载或 bridge 未绑定）")

        def _on_wait(age: float, waited: float) -> None:
            self.log(
                f"等待 Tk 主线程处理 bridge… pump={age:.0f}s 已等 {waited:.0f}s",
                telegram=True,
            )

        if not wait_bridge_pump_alive(
            timeout_s=timeout_s, on_wait=_on_wait, poll_s=0.35
        ):
            beat = gui_heartbeat() or {}
            raise GuiPipelineError(
                "GUI Tk 主线程超时未就绪，无法打开审阅窗。"
                f"（pump={beat.get('pump_age_s')}s）"
            )
        time.sleep(0.8)

    def _ensure_story_for_vc(self) -> None:
        from cli.queue_gui_nav import sync_gui_window_path_from_hwnds
        from cli.screens import SCREEN_STORY_ROOT

        win = self._public_win()
        if win == "scene":
            self.log("关闭 SCENE，回到 STORY 以打开审阅窗", telegram=True)
            ok, msg = self.cli("cx")
            if not ok:
                raise GuiPipelineError(f"cx failed: {msg}")
            time.sleep(0.8)

        self._wait_story_bridge_ready(timeout_s=120.0)
        sync_gui_window_path_from_hwnds()
        from cli.bridge import bridge_screen_bound

        if not bridge_screen_bound(SCREEN_STORY_ROOT, timeout_s=3.0):
            raise GuiPipelineError(
                "STORY 详情窗未打开（bridge 未绑定）。"
                "请确认 GUI 已打开该故事。"
            )

    def _open_vc_review(self, clip_segments: list[dict]) -> None:
        import json

        from cli.bridge import send_bridge_command, wait_bridge_pump_alive
        from cli.screens import SCREEN_STORY_ROOT

        preview = "\n".join(
            f"  场景 {i}. {os.path.basename(str(seg.get('path') or ''))}"
            for i, seg in enumerate(clip_segments, 1)
        )
        self.log(
            f"打开审阅窗（{len(clip_segments)} 段，scene_content 场景顺序）\n{preview}",
            telegram=True,
        )
        payload = json.dumps(clip_segments, ensure_ascii=False)
        deadline = time.monotonic() + 120.0
        last = ""
        while time.monotonic() < deadline:
            wait_bridge_pump_alive(timeout_s=min(20.0, deadline - time.monotonic()))
            ok, msg = send_bridge_command(
                screen=SCREEN_STORY_ROOT,
                op="set",
                field="clip_review",
                value=payload,
                timeout_s=25.0,
            )
            if ok:
                self.log(
                    msg
                    or (
                        f"vc ok — 已打开审阅窗（{len(clip_segments)} 段）。"
                        "请在窗口内裁剪/排序后点确认生成成片。"
                    ),
                    telegram=True,
                )
                return
            last = msg or "unknown"
            retry = any(
                k in last
                for k in ("仍在加载", "pump", "卡住", "无响应", "not bound", "busy")
            )
            if not retry:
                break
            self.log(f"审阅窗尚未就绪，2s 后重试… ({last[:120]})", telegram=True)
            time.sleep(2.0)
        raise GuiPipelineError(f"vc failed: {last}\n已准备的 clip：\n{preview}")

    def _wait_user_next(self, title: str) -> None:
        self._waiting_next = True
        self._next_event.clear()
        self.log(
            f"【人工审阅】{title}\n"
            "审阅窗已打开，各场景 clip 已按顺序载入。\n"
            "请在 GUI 内裁剪/排序 → 确认生成成片；可发 vp 发布。\n"
            "完成后发 n — 将关闭 GUI 并回到选单。",
            telegram=True,
        )
        try:
            while not self._stop.is_set() and not self._stop_requested:
                if self._next_event.wait(timeout=1.0):
                    self._next_event.clear()
                    return
        finally:
            self._waiting_next = False
        raise GuiPipelineError("stopped")

    def _mark_gui_review_done(self, index: int, cid: str, title: str) -> None:
        if cid:
            self._gui_reviewed_ids.add(cid)
            try:
                from cli.video_choice_queue import mark_gui_review_done

                mark_gui_review_done(cid)
            except Exception as exc:
                self.log(f"队列标记 GUI 审阅失败：{exc}", telegram=True)
        self.log(
            f"#{index}「{title[:40]}」已标为 GUI 审阅完成。\n"
            "请再选下一条（可重复选已完成的）。",
            telegram=True,
        )

    def run_one_story(self, index: int) -> str:
        from cli.video_choice_queue import resolve_video_detail_from_queue_item
        from utility.grok_video_results import grok_clip_segments_from_video_detail

        item = self._queue_item_at(index)
        cid = (item.get("choice_id") or "").strip()
        title = (item.get("title") or item.get("row_key") or cid or "?").strip()
        vd = resolve_video_detail_from_queue_item(item)
        row = vd if isinstance(vd, dict) else {}

        if self.skip_published and (
            str(row.get("video") or "").strip()
            or str(row.get("publish") or "").strip()
        ):
            self.log(f"跳过 #{index} {title}：已有成片（--skip-published）。", telegram=True)
            return "skip"

        clip_segments = grok_clip_segments_from_video_detail(row)
        scenes = row.get("scene_content")
        n_sc = len(scenes) if isinstance(scenes, list) else 0

        if not clip_segments:
            self.log(
                f"#{index} {title}：没有 clip 路径，无法打开审阅窗。\n"
                "请先对该故事跑 run_client（grv + grvc）生成 workflow.grok_video_results。",
                telegram=True,
            )
            return "skip"

        partial = not wfstore.story_has_all_clips(row)
        if partial:
            if self.require_all_clips:
                self.log(
                    f"#{index} {title}：clip 未齐全（{len(clip_segments)}/{n_sc} 场），"
                    "仍将打开 STORY 并载入已有片段。\n"
                    "缺 clip 的场景需回 run_client 补 grv/grvc，或加 --partial 默认允许。",
                    telegram=True,
                )
            else:
                self.log(
                    f"#{index} {title}：部分 clip（{len(clip_segments)}/{n_sc} 场），"
                    "载入已有片段。",
                    telegram=True,
                )

        self.log(
            f"当前故事 #{index}：{title}\n"
            f"clip {len(clip_segments)} 段"
            + (f" / 场景 {n_sc} 场" if n_sc else ""),
            telegram=True,
        )

        try:
            self._pick_story_gui(index)
            self._ensure_story_for_vc()
            self._open_vc_review(clip_segments)
            self._wait_user_next(title)
            self._mark_gui_review_done(index, cid, title)
            return "ok"
        finally:
            self._shutdown_gui_session()

    def run(self) -> int:
        from utility.telegram import ROLE_CLI, token_for, warn_if_tokens_overlap
        from utility.telegram_cli import cli_allowed_chat_id

        warn_if_tokens_overlap()
        if self.telegram_enabled:
            if not token_for(ROLE_CLI) or not cli_allowed_chat_id():
                print("ERROR: TELEGRAM_CLI_BOT_TOKEN / TELEGRAM_CLI_CHAT_ID missing", flush=True)
                return 1

        self._start_telegram_inbox()
        clip_mode = (
            "缺 clip 时仍打开已有片段"
            if not self.require_all_clips
            else "缺 clip 时仍打开已有片段（加 --require-all-clips 可改为必须齐全）"
        )
        self.log(
            "StoryProducer GUI 审阅启动（交互选故事）\n"
            f"clip 策略={clip_mode}  once={self.once}\n"
            "流程：选序号 → 打开 STORY + clip 审阅窗 → 成片/发布 → n → 关 GUI → 再选\n"
            "Telegram：回复 1/2/3 选故事；list 刷新；exit 结束。可重复选。\n"
            "审阅中可发 vc / vp / cx 等 CLI。\n"
            "不要同时跑 cli\\run_telegram_client.bat（同一 token 会 409）。",
            telegram=True,
        )

        stories = 0
        first = True
        try:
            while not self._stop.is_set() and not self._stop_requested:
                idx = self._wait_story_pick(first=first)
                first = False
                if not idx:
                    self.log("结束 GUI 审阅。", telegram=True)
                    break
                try:
                    ran = self.run_one_story(idx)
                except GuiPipelineError as exc:
                    self.log(f"#{idx} 失败：{exc}", telegram=True)
                    self._shutdown_gui_session()
                    if self.once:
                        return 1
                    continue
                if ran == "skip":
                    if self.once:
                        return 2
                    continue
                if ran == "ok":
                    stories += 1
                if self.once or self._stop_requested:
                    break
        except KeyboardInterrupt:
            self.log("KeyboardInterrupt — 停止", telegram=True)
        finally:
            self._stop.set()
            self._shutdown_gui_session()
        self.log(f"StoryProducer GUI 退出（完成 {stories} 条审阅）。", telegram=True)
        return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="storyproducer gui",
        description="交互选故事，打开 GUI 载入 scene clip 审阅窗（vc）。",
    )
    p.add_argument(
        "--pick",
        default="",
        help="仅首次直接打开队列序号如 3，之后仍交互选",
    )
    p.add_argument("--once", action="store_true", help="只处理一条后退出")
    p.add_argument(
        "--require-all-clips",
        action="store_true",
        help="clip 未齐全时仅提示警告（默认仍会打开已有片段）；"
        "与旧版不同，不再直接拒绝打开 GUI",
    )
    p.add_argument(
        "--skip-published",
        action="store_true",
        help="跳过已有 video 成片字段的故事",
    )
    p.add_argument("--no-telegram", action="store_true")
    p.add_argument(
        "--telegram-inbox",
        action="store_true",
        default=True,
        help="Telegram 收选单/n 等（默认开）",
    )
    args = p.parse_args(argv)
    client = StoryProducerGuiClient(
        pick=args.pick,
        once=args.once,
        require_all_clips=bool(args.require_all_clips),
        skip_published=args.skip_published,
        telegram=not args.no_telegram,
        telegram_inbox=not args.no_telegram and args.telegram_inbox,
    )
    return client.run()


if __name__ == "__main__":
    raise SystemExit(main())
