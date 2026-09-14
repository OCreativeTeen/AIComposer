"""StoryProducer Telegram pipeline — in-process engine, no GUI."""

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

from storyproducer.engine import StoryEngine
from storyproducer import workflow as wfstore

_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")
_STOP_WORDS = frozenset({"stop", "exit", "quit", "结束", "停", "halt", "abort"})
_COVER_WAIT_REMIND_S = 180.0
_NBIF_INTERVAL_S = 60.0
_NBIF_MIN_DURATION_S = 300.0
_NBIF_MAX_DURATION_S = 2400.0
NBI_ACCOUNTS = {
    1: "ocreativeteen",
    2: "creative4teen",
    3: "triumphdt777",
    4: "myhomefun",
    5: "mindstoryroom",
    6: "bjtombj2023",
}


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


class PipelineError(RuntimeError):
    pass


class NbifTimeoutError(PipelineError):
    def __init__(self, message: str, *, polls_done: int = 0, elapsed_s: float = 0.0) -> None:
        super().__init__(message)
        self.polls_done = int(polls_done)
        self.elapsed_s = float(elapsed_s)


class StoryProducerClient:
    """Same story-video steps as Hermes, talking to StoryEngine in-process."""

    def __init__(
        self,
        *,
        pick: str = "next",
        once: bool = False,
        nbi: int | None = None,
        grv_variant: int = 3,
        telegram: bool = True,
        telegram_inbox: bool = True,
        engine: StoryEngine | None = None,
        target_stage: str = "",
    ) -> None:
        self.pick_arg = (pick or "next").strip() or "next"
        self.once = bool(once)
        self.nbi_override = int(nbi) if nbi is not None else None
        self.grv_variant = max(1, int(grv_variant))
        self.telegram_enabled = bool(telegram)
        self.telegram_inbox = bool(telegram_inbox)
        self.engine = engine or StoryEngine()
        self.engine.session.grv_variant = self.grv_variant
        self.target_stage = wfstore.parse_target_stage(target_stage) or ""
        self._deferred_ids: set[str] = set()

        self._stop = threading.Event()
        self._stop_requested = False
        self._tg_offset = 0
        self._last_tg = 0.0
        self._inbox_thread: threading.Thread | None = None
        self._choice_lock = threading.Lock()
        self._choice_kind = ""
        self._choice_max = 0
        self._choice_digit = 0
        self._choice_event = threading.Event()
        self._cover_gen_pending = False
        self._cover_gen_event = threading.Event()
        self._scene_gen_pending = False
        self._batch_setup_done = False
        self._batch_vs_idx: int | None = None
        self._batch_lm_idx: int | None = None
        self._batch_nar_idx: int | None = None
        self._batch_prefs_from_queue = False
        self._grv_review_pending = False
        self._grv_continue_event = threading.Event()

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
        cmd = (raw or "").strip()
        self.log(f">>> {cmd}")
        ok, msg = self.engine.dispatch(cmd)
        shown = (msg or "").strip()
        self.log(("ok" if ok else "error") + " — " + shown)
        return ok, shown

    def cli_ok(self, raw: str, *, contain: str = "", tries: int = 1, pause_s: float = 2.0) -> str:
        last = ""
        for i in range(max(1, tries)):
            ok, msg = self.cli(raw)
            last = msg
            if ok and (not contain or contain.lower() in (msg or "").lower()):
                return msg
            if i + 1 < tries:
                time.sleep(pause_s)
        raise PipelineError(f"`{raw}` failed: {last}")

    # ------------------------------------------------------------------ telegram inbox

    def _start_telegram_inbox(self) -> None:
        if not self.telegram_enabled or not self.telegram_inbox:
            return
        t = threading.Thread(target=self._inbox_loop, name="sp-tg-inbox", daemon=True)
        self._inbox_thread = t
        t.start()

    def _inbox_loop(self) -> None:
        from utility.telegram import ROLE_CLI, get_updates
        from utility.telegram_cli import cli_allowed_chat_id

        chat = cli_allowed_chat_id()
        while not self._stop.is_set():
            try:
                updates = get_updates(
                    ROLE_CLI, offset=self._tg_offset, timeout=25
                )
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
        low = raw.lower().translate(_FULLWIDTH)
        self.log(f"telegram << {raw}")
        if low in _STOP_WORDS:
            self._stop_requested = True
            self._choice_event.set()
            self._cover_gen_event.set()
            return
        digit = None
        if raw.translate(_FULLWIDTH).isdigit():
            digit = int(raw.translate(_FULLWIDTH))
        with self._choice_lock:
            kind = self._choice_kind
            mx = self._choice_max
        if digit is not None and kind and 1 <= digit <= mx:
            with self._choice_lock:
                self._choice_digit = digit
            self._choice_event.set()
            return
        if self._cover_gen_pending and (digit in (1, 2) or low in ("生成", "跳过", "itcs", "nbp")):
            try:
                self.engine.record_cover_gen_choice(raw)
            except ValueError:
                return
            self._cover_gen_event.set()
            return
        if self._scene_gen_pending and digit in (1, 2):
            with self._choice_lock:
                self._choice_kind = "scene_gen"
                self._choice_digit = digit
            self._choice_event.set()
            return
        if self._grv_review_pending and low in (
            "continue",
            "grvc",
            "继续",
            "ok",
            "ready",
        ):
            self._grv_continue_event.set()
            return
        # Free-form CLI while idle
        if kind:
            return
        ok, msg = self.engine.dispatch(raw)
        self.log(("ok" if ok else "error") + " — " + (msg or ""), telegram=True)

    def _wait_digit(self, kind: str, maximum: int, prompt: str, remind_s: float = 180.0) -> int:
        with self._choice_lock:
            self._choice_kind = kind
            self._choice_max = maximum
            self._choice_digit = 0
        self._choice_event.clear()
        self.log(prompt, telegram=True)
        last = time.monotonic()
        try:
            while not self._stop.is_set() and not self._stop_requested:
                if self._choice_event.wait(timeout=1.0):
                    self._choice_event.clear()
                    with self._choice_lock:
                        d = int(self._choice_digit or 0)
                    if 1 <= d <= maximum:
                        return d
                if time.monotonic() - last >= remind_s:
                    last = time.monotonic()
                    self.log(f"仍在等 {kind}：请回 1…{maximum}。", telegram=True)
        finally:
            with self._choice_lock:
                self._choice_kind = ""
                self._choice_max = 0
        raise PipelineError("stopped")

    # ------------------------------------------------------------------ steps

    def _pick_story(self, index: int | None = None) -> bool:
        arg = str(index) if index else self.pick_arg
        ok, msg = self.cli(f"pick {arg}")
        if not ok:
            raise PipelineError(f"pick failed: {msg}")
        if "没有未处理" in msg or "队列是空的" in msg:
            self.log(msg, telegram=True)
            return False
        self.log(msg, telegram=True)
        return self.engine.session.is_loaded()

    def _interactive_scene_setup(self) -> None:
        """Per-story setup (legacy). Prefer batch setup + apply."""
        self._ensure_batch_scene_setup()
        self._apply_batch_scene_setup()

    def _ensure_batch_scene_setup(self) -> None:
        """Ask visual style / narrator / LM once per client run (after target)."""
        if self._batch_setup_done:
            return
        idx = self._next_story_index(first=True)
        if not idx:
            self._batch_setup_done = True
            return
        if not self._pick_story(idx):
            self._batch_setup_done = True
            return

        needs_lm = wfstore.any_unfinished_needs_gemini(
            self.target_stage or wfstore.TARGET_FULL,
            skip_ids=self._deferred_ids,
        )
        item = self.engine.session.queue_item if isinstance(
            self.engine.session.queue_item, dict
        ) else {}
        q_vs = (item.get("visual_style") or self.engine.session.visual_style or "").strip()
        q_nar = (item.get("narrator") or self.engine.session.narrator or "").strip()
        q_lang = (
            item.get("yt_language") or item.get("language") or self.engine.session.language()
        )
        self._batch_prefs_from_queue = bool(q_vs or q_nar)
        if q_lang:
            self.log(
                f"场景生成语言：{q_lang} → {self._language_label(q_lang)} "
                f"(tw=Traditional Chinese, zh=Simplified Chinese, en=English)",
                telegram=True,
            )
        if self._batch_prefs_from_queue:
            self.log(
                "本批队列已含 visual_style / narrator，跳过手动选择。",
                telegram=True,
            )
            if q_vs:
                ok, msg = self.engine.cmd_scene_visual_style(q_vs)
                self.log(msg, telegram=True)
                if not ok:
                    raise PipelineError(f"队列 visual_style 无效: {msg}")
            if q_nar:
                ok, msg = self.engine.cmd_narrator(q_nar)
                self.log(msg, telegram=True)
                if not ok:
                    raise PipelineError(f"队列 narrator 无效: {msg}")
        else:
            self.log(
                "本批队列统一选项（整轮只问一次，后续故事复用）：",
                telegram=True,
            )

        if not q_vs:
            ok, msg = self.cli("scnvs")
            self.log(msg, telegram=True)
            n = _count_cmd_lines(msg, "scnvs")
            if n < 1:
                raise PipelineError("scnvs 没有选项")
            self._batch_vs_idx = self._wait_digit(
                "scnvs",
                n,
                "请选 Visual Style（本批所有故事共用）。",
            )
            self.cli_ok(f"scnvs {self._batch_vs_idx}", contain="scnvs ok")

        if needs_lm:
            ok, msg = self.cli("scnlm")
            self.log(msg, telegram=True)
            n = _count_cmd_lines(msg, "scnlm")
            if n < 1:
                raise PipelineError("scnlm 没有选项")
            self._batch_lm_idx = self._wait_digit(
                "scnlm",
                n,
                "请选 LM 提示（本批需生成场景的故事共用）。",
            )
            self.cli_ok(f"scnlm {self._batch_lm_idx}", contain="scnlm ok")
        else:
            self.log(
                "本批没有处于 INIT 的故事，跳过 LM 提示选择。",
                telegram=True,
            )

        if not q_nar:
            ok, msg = self.cli("nar")
            if ok and ("nar：" in msg or msg.startswith("nar")):
                n = _count_cmd_lines(msg, "nar")
                if n >= 1:
                    self.log(msg, telegram=True)
                    self._batch_nar_idx = self._wait_digit(
                        "nar",
                        n,
                        "请选 narrator（画外旁白，本批共用）。",
                    )
                    self.cli_ok(f"nar {self._batch_nar_idx}", contain="nar ok")

        self._batch_setup_done = True
        vs = self.engine.session.visual_style or "?"
        nar = self.engine.session.narrator or "?"
        lm = self.engine.session.lm_label or "（未选）"
        self.log(
            f"本批已锁定：style={vs}  narrator={nar}  lm={lm}",
            telegram=True,
        )

    @staticmethod
    def _language_label(lang_key: str) -> str:
        try:
            import config

            return config.llm_language_label(lang_key)
        except Exception:
            return str(lang_key or "tw")

    def _apply_batch_scene_setup(self) -> None:
        """Write batch choices onto the current story without re-prompting."""
        if not self._batch_setup_done:
            self._ensure_batch_scene_setup()
        item = self.engine.session.queue_item if isinstance(
            self.engine.session.queue_item, dict
        ) else {}
        q_vs = (item.get("visual_style") or "").strip()
        q_nar = (item.get("narrator") or "").strip()
        if q_vs:
            self.engine.cmd_scene_visual_style(q_vs)
        elif self._batch_vs_idx is not None:
            self.cli_ok(f"scnvs {self._batch_vs_idx}", contain="scnvs ok")
        if self._batch_lm_idx is not None:
            self.cli_ok(f"scnlm {self._batch_lm_idx}", contain="scnlm ok")
        if q_nar:
            self.engine.cmd_narrator(q_nar)
        elif self._batch_nar_idx is not None:
            self.cli_ok(f"nar {self._batch_nar_idx}", contain="nar ok")

    def _generate_scenes(self) -> None:
        ok, msg = self.cli("scnge")
        self.log(msg, telegram=True)
        if "1 = 用 Gemini" in msg or "已有" in msg:
            self._scene_gen_pending = True
            try:
                choice = self._wait_digit(
                    "scene_gen", 2, "本 client 轮询 Telegram，请直接回 1 或 2。"
                )
            finally:
                self._scene_gen_pending = False
            if choice == 2:
                self.cli_ok("scnge use")
                return
            ok, msg = self.cli("scnge force")
            self.log(msg, telegram=True)
        if not ok:
            raise PipelineError(f"scnge failed: {msg}")
        if "已生成" in msg:
            self._announce_gemini_files()
            n = _count_numbered_files(msg)
            pick = self._wait_digit(
                "scnge_json",
                max(n, 3),
                "【人工选场景 JSON】请对比上面三套 caption，在 Telegram 回复 1 / 2 / 3。",
            )
            self.cli_ok(f"scnge pick {pick}", contain="scnge pick ok")

    def _announce_gemini_files(self) -> None:
        files = [
            str(p)
            for p in (self.engine.workflow().get("gemini_files") or [])
            if str(p).strip()
        ]
        if not files:
            return
        blocks = ["【三套场景描述】请选 1 / 2 / 3："]
        for i, path in enumerate(files, 1):
            preview = wfstore.preview_scene_json(path)
            blocks.append(f"方案 {i}  {os.path.basename(path)}\n{preview}")
        self.log("\n\n".join(blocks), telegram=True)

    def _wait_cover_generation_choice(self) -> bool:
        """True = skip (itcs). False = generate (nbp…)."""
        import config

        expected = int(getattr(config, "INFOGRAPHIC_COVER_COUNT", 3) or 3)
        existing = config.existing_infographic_cover_paths(expected)
        have_all = len(existing) >= expected
        base = os.path.dirname(config.infographic_cover_path(1)) or "aiagent"
        self.engine.start_cover_gen_choice(
            existing_count=len(existing), expected=expected
        )
        self._cover_gen_pending = True
        self._cover_gen_event.clear()
        names = ", ".join(os.path.basename(p) for p in existing) if existing else ""
        lines = [
            "【封面生成】scnsave 完成。要为当前分镜生成新的 NotebookLM 封面图吗？",
            f"磁盘已有 {len(existing)}/{expected} 张" + (f"：{names}" if names else "。"),
            f"路径：{base}\\Infographic_1…{expected}",
            "",
            "1 = 生成新封面（nbp → nbi → nbif → itc）",
            "2 = 跳过生成，用已有图选封面（itcs）",
            "",
            "请回复 1 或 2。",
        ]
        self.log("\n".join(lines), telegram=True)
        last = time.monotonic()
        try:
            while not self._stop.is_set() and not self._stop_requested:
                choice = self.engine.take_cover_gen_choice()
                if choice == "generate":
                    self.log("继续：生成新 NotebookLM 封面。", telegram=True)
                    return False
                if choice == "skip":
                    if not have_all:
                        self.log(
                            f"itcs 需要 {expected} 张，当前 {len(existing)} 张。请回 1 或先放好图再回 2。",
                            telegram=True,
                        )
                        self.engine.start_cover_gen_choice(
                            existing_count=len(existing), expected=expected
                        )
                    else:
                        self.log("跳过 NotebookLM 封面生成，改用已有 Infographic。", telegram=True)
                        return True
                self._cover_gen_event.wait(timeout=1.0)
                self._cover_gen_event.clear()
                if time.monotonic() - last >= _COVER_WAIT_REMIND_S:
                    last = time.monotonic()
                    self.log("仍在等封面生成选择：回 1=生成  2=跳过（itcs）。", telegram=True)
        finally:
            self._cover_gen_pending = False
        raise PipelineError("stopped")

    def _trigger_notebooklm(self) -> int:
        override = self.nbi_override
        self.nbi_override = None
        idx, label = self.engine.next_nbi_start(override=override)
        last_i = int(self.engine.workflow().get("nbi_index") or 0)
        if last_i:
            self.log(
                f"nbi 本条上次 {last_i} → 本次从 {idx} ({label}) 起轮换",
                telegram=True,
            )
        n = 6
        try:
            import config

            n = max(1, len(config.list_gemini_chrome_profiles() or []))
        except Exception:
            pass
        order = list(range(idx, n + 1)) + list(range(1, idx))
        last_msg = ""
        for acc in order:
            lab = NBI_ACCOUNTS.get(acc) or label
            self.log(f"nbi {acc} ({lab})", telegram=True)
            ok, msg = self.cli(f"nbi {acc}")
            last_msg = msg
            if ok and "nbi ok" in msg.lower():
                return acc
            brief = (msg or "").strip().split("\n")[0][:160]
            self.log(f"nbi {acc} 失败，换下一个号：{brief}", telegram=True)
        raise PipelineError(f"nbi 全部失败: {last_msg}")

    def _poll_notebooklm_ready(self) -> None:
        start = time.monotonic()
        poll_n = 0
        while time.monotonic() - start < _NBIF_MAX_DURATION_S:
            if self._stop_requested:
                raise PipelineError("stopped during nbif")
            poll_n += 1
            ok, msg = self.cli("nbif")
            if ok and "已经 ready" in msg:
                return
            elapsed = time.monotonic() - start
            self.log(f"nbif poll {poll_n} — 已 {elapsed / 60:.1f} 分钟")
            time.sleep(_NBIF_INTERVAL_S)
        elapsed = time.monotonic() - start
        if elapsed < _NBIF_MIN_DURATION_S:
            time.sleep(_NBIF_INTERVAL_S)
            ok, msg = self.cli("nbif")
            if ok and "已经 ready" in msg:
                return
        raise NbifTimeoutError(
            f"nbif 超时（轮询 {poll_n} 次，约 {elapsed / 60:.1f} 分钟）",
            polls_done=poll_n,
            elapsed_s=elapsed,
        )

    def _wait_cover_pick(self) -> str:
        cover = self.engine.workflow()
        files = [str(p) for p in (cover.get("cover_files") or []) if str(p).strip()]
        n = max(len(files), 3)
        self.log("步骤 10 等待人工选封面", telegram=True)
        pick = self._wait_digit(
            "cover", n, "【人工选封面】请在 Telegram 回复 1 / 2 / 3。Agent 不会代选。"
        )
        ok, msg = self.cli(f"itc {pick}")
        if not ok:
            raise PipelineError(f"itc pick failed: {msg}")
        self.log(msg, telegram=True)
        path = (
            self.engine.workflow().get("cover_selected_path")
            or self.engine.session.cover_path
            or (files[pick - 1] if files and 1 <= pick <= len(files) else "")
        )
        if not path:
            raise PipelineError("封面路径为空")
        return path

    def _queue_has_unfinished(self) -> bool:
        return wfstore.find_next_unfinished_index(
            self.target_stage or wfstore.TARGET_FULL,
            skip_ids=self._deferred_ids,
        ) is not None

    def _active_choice_id(self) -> str:
        item = self.engine.session.queue_item or {}
        return str(item.get("choice_id") or "").strip()

    def _ask_target_stage(self) -> str:
        if self.target_stage in wfstore.TARGETS:
            return self.target_stage
        if not self.telegram_enabled:
            self.target_stage = wfstore.TARGET_FULL
            return self.target_stage
        n = self._wait_digit(
            "target",
            3,
            "本次启动请选目标阶段：\n"
            "1 = 仅阶段一（Gemini 场景描述）GEMINI_ONLY\n"
            "2 = 到阶段二（Infographic 封面选定）INFOGRAPHIC_ONLY\n"
            "3 = 全程到阶段三（Grok 场景图 + Video Clip）FULL_PROCESS",
        )
        mapping = {
            1: wfstore.TARGET_GEMINI_ONLY,
            2: wfstore.TARGET_INFOGRAPHIC_ONLY,
            3: wfstore.TARGET_FULL,
        }
        self.target_stage = mapping[n]
        return self.target_stage

    def _run_stage_gemini(self) -> None:
        self.log("阶段一：Gemini 场景描述", telegram=True)
        self._apply_batch_scene_setup()
        self._generate_scenes()
        self.log("scnsave", telegram=True)
        self.cli_ok("scnsave", contain="scnsave ok")

    def _run_stage_infographic(self, *, force_generate: bool = False) -> None:
        from cli.video_choice_queue import mark_active_item_workflow_step

        if force_generate:
            skip_cover = False
        else:
            skip_cover = self._wait_cover_generation_choice()
        if skip_cover:
            self.log("itcs（用已有 Infographic 选封面）", telegram=True)
            ok, msg = self.cli("itcs")
            if not ok:
                raise PipelineError(f"itcs failed: {msg}")
            self.log(msg, telegram=True)
            mark_active_item_workflow_step(workflow_step="itc")
        else:
            self.log("nbp 1 → nbi（提交封面生成）", telegram=True)
            self.cli_ok("nbp 1", contain="nbp ok", tries=2, pause_s=1.0)
            nbi_acc = self._trigger_notebooklm()
            mark_active_item_workflow_step(
                workflow_step="nbif_poll", nbi_profile_index=nbi_acc
            )
            self.log("nbif 轮询（未完成可跳过本条去下一条）", telegram=True)
            self._poll_notebooklm_ready()
            self.log("itc 下载封面", telegram=True)
            ok, msg = self.cli("itc")
            if not ok:
                raise PipelineError(f"itc failed: {msg}")
            self.log(msg)
        cover_path = self._wait_cover_pick()
        self.log(f"封面已记录 {os.path.basename(cover_path)} → cover_image", telegram=True)

    def _check_pending_infographic(self) -> None:
        self.log("尝试检查并下载上次提交的 Infographic", telegram=True)
        self._poll_notebooklm_ready()
        ok, msg = self.cli("itc")
        if not ok:
            raise PipelineError(f"itc failed: {msg}")
        self.log(msg)
        cover_path = self._wait_cover_pick()
        self.log(f"封面已记录 {os.path.basename(cover_path)} → cover_image", telegram=True)

    def _wait_grv_continue(self) -> None:
        self._grv_review_pending = True
        self._grv_continue_event.clear()
        self.log(
            "请在浏览器逐标签 review Grok video clip。\n"
            "不满意可手动重新 Submit；失败的场景标签保持不动。\n"
            "确认后回复 continue 或 grvc 开始下载。",
            telegram=True,
        )
        try:
            while not self._stop.is_set() and not self._stop_requested:
                if self._grv_continue_event.wait(timeout=1.0):
                    self._grv_continue_event.clear()
                    return
        finally:
            self._grv_review_pending = False
        raise PipelineError("stopped")

    def _run_stage_grok(self) -> None:
        from cli.video_choice_queue import mark_active_item_done

        self.log(
            f"阶段三：Grok 场景图 + Video Clip（变体 {self.grv_variant}）",
            telegram=True,
        )
        self.cli(f"nbv {self.grv_variant}")
        ok, msg = self.cli("grv")
        if not ok:
            raise PipelineError(f"grv failed: {msg}")
        self.log(msg, telegram=True)
        self._wait_grv_continue()
        ok, msg = self.cli("grvc")
        if not ok:
            raise PipelineError(f"grvc failed: {msg}")
        self.log(msg, telegram=True)
        try:
            marked = mark_active_item_done()
        except Exception as exc:
            self.log(
                f"队列标 done 失败（可能导致重复处理）：{exc}",
                telegram=True,
            )
            marked = None
        if marked:
            self.log("本条已标为队列已完成。", telegram=True)
        else:
            self.log(
                "警告：未能将本条标为 done，若循环重复处理请检查 video_choice_queue.json。",
                telegram=True,
            )
        self.log("clip 已下载并写入 workflow.grok_video_results", telegram=True)

    def _next_story_index(self, *, first: bool = False) -> int | None:
        want = (self.pick_arg or "").strip()
        if first and want.isdigit():
            return int(want)
        return wfstore.find_next_unfinished_index(
            self.target_stage or wfstore.TARGET_FULL,
            skip_ids=self._deferred_ids,
        )

    def run_one_story(self, index: int) -> str:
        """Process one queue item. Returns ok / skip / defer / empty."""
        if not self._pick_story(index):
            return "empty"

        stage = self.engine.inferred_stage()
        target = self.target_stage or wfstore.TARGET_FULL
        title = self.engine.session.title()
        self.log(
            f"当前故事：{title}\nstage={stage}  target={target}",
            telegram=True,
        )

        if wfstore.meets_target(stage, target):
            self.log("已达目标阶段，跳过本条。", telegram=True)
            return "skip"

        pending_action = ""
        if stage == wfstore.STAGE_INFOGRAPHIC_PENDING:
            choice = self._wait_digit(
                "pending_ig",
                3,
                "该故事上次已发送封面生成指令但未确认完成。\n"
                "1 = 尝试直接检查并下载结果\n"
                "2 = 重新生成\n"
                "3 = 跳过该 Story",
            )
            if choice == 3:
                cid = self._active_choice_id()
                if cid:
                    self._deferred_ids.add(cid)
                self.log("已跳过本条（保持 INFOGRAPHIC_PENDING），处理下一条。", telegram=True)
                return "defer"
            pending_action = "check" if choice == 1 else "regen"

        run_gemini = False
        force_cover_generate = pending_action == "regen"
        if pending_action:
            run_gemini = False
        elif stage == wfstore.STAGE_INIT:
            run_gemini = True
        elif stage == wfstore.STAGE_GEMINI_DONE and target != wfstore.TARGET_GEMINI_ONLY:
            choice = self._wait_digit(
                "skip_gemini",
                2,
                "检测到该故事已有场景描述。\n"
                "1 = 跳过阶段一，直接进入阶段二\n"
                "2 = 重新生成场景描述",
            )
            run_gemini = choice == 2
            if choice == 2:
                force_cover_generate = True

        if run_gemini:
            self._run_stage_gemini()
            stage = wfstore.STAGE_GEMINI_DONE
            force_cover_generate = True

        if target == wfstore.TARGET_GEMINI_ONLY:
            self.log("目标 GEMINI_ONLY：本条停在阶段一。", telegram=True)
            return "ok"

        if stage not in (wfstore.STAGE_INFOGRAPHIC_DONE, wfstore.STAGE_COMPLETED):
            try:
                if pending_action == "check":
                    self._check_pending_infographic()
                else:
                    if force_cover_generate:
                        self.log(
                            "场景已重新生成，自动进入 NotebookLM 封面生成"
                            "（nbp → nbi → nbif → itc）。",
                            telegram=True,
                        )
                    self._run_stage_infographic(force_generate=force_cover_generate)
            except NbifTimeoutError as exc:
                self.engine.mark_stage(
                    wfstore.STAGE_INFOGRAPHIC_PENDING,
                    infographic_status=wfstore.INFO_SUBMITTED,
                    step="nbif_timeout",
                )
                cid = self._active_choice_id()
                if cid:
                    self._deferred_ids.add(cid)
                self.log(
                    f"{exc}\n本条保持 INFOGRAPHIC_PENDING，先处理队列里下一条。",
                    telegram=True,
                )
                return "defer"
            except PipelineError as exc:
                if "nbi 全部失败" in str(exc):
                    self.engine.mark_stage(
                        wfstore.STAGE_GEMINI_DONE,
                        infographic_status=wfstore.INFO_FAILED,
                        step="nbi_failed",
                    )
                raise
            stage = wfstore.STAGE_INFOGRAPHIC_DONE

        if target == wfstore.TARGET_INFOGRAPHIC_ONLY:
            self.log("目标 INFOGRAPHIC_ONLY：本条停在阶段二。", telegram=True)
            return "ok"

        if stage != wfstore.STAGE_COMPLETED:
            self._run_stage_grok()
        return "ok"

    def run(self) -> int:
        from utility.telegram import ROLE_CLI, token_for, warn_if_tokens_overlap
        from utility.telegram_cli import cli_allowed_chat_id

        warn_if_tokens_overlap()
        if self.telegram_enabled:
            if not token_for(ROLE_CLI) or not cli_allowed_chat_id():
                print("ERROR: TELEGRAM_CLI_BOT_TOKEN / TELEGRAM_CLI_CHAT_ID missing", flush=True)
                return 1
        self._start_telegram_inbox()
        try:
            target = self._ask_target_stage()
        except PipelineError:
            self._stop.set()
            self.log("启动时未选定目标阶段，退出。", telegram=True)
            return 1
        self.log(
            "StoryProducer 启动（无 GUI）\n"
            f"target={target}  pick={self.pick_arg}  grv 变体 {self.grv_variant}\n"
            "选 target 后统一选一次 Visual Style / Narrator / LM（整批共用）。\n"
            "Queue 里各 Story 进度可以不同；封面生成中的条目可暂存后处理下一条。\n"
            "不要同时跑 cli\\run_bot.bat 或 cli\\run_telegram_client.bat（同一 token 会 409）。\n"
            + wfstore.format_queue_progress(target),
            telegram=True,
        )
        try:
            self._ensure_batch_scene_setup()
        except PipelineError as exc:
            self._stop.set()
            self.log(f"批量选项设置失败：{exc}", telegram=True)
            return 1
        stories = 0
        first = True
        try:
            while not self._stop.is_set() and not self._stop_requested:
                idx = self._next_story_index(first=first)
                first = False
                if not idx:
                    if self._deferred_ids:
                        self.log(
                            "其余条目都在等 Infographic 或已达目标，本轮结束。",
                            telegram=True,
                        )
                    else:
                        self.log("队列没有未达目标的故事，结束。", telegram=True)
                    break
                try:
                    ran = self.run_one_story(idx)
                except NbifTimeoutError as exc:
                    cid = self._active_choice_id()
                    if cid:
                        self._deferred_ids.add(cid)
                    self.log(str(exc), telegram=True)
                    if self.once:
                        return 2
                    continue
                except PipelineError as exc:
                    self.log(f"本条失败：{exc}", telegram=True)
                    if self.once:
                        return 1
                    cid = self._active_choice_id()
                    if cid:
                        self._deferred_ids.add(cid)
                    continue
                if ran == "empty":
                    break
                if ran == "ok":
                    stories += 1
                if self.once or self._stop_requested:
                    break
                self.pick_arg = "next"
                if not self._queue_has_unfinished():
                    self.log("队列没有未达目标的故事，结束。", telegram=True)
                    break
        except KeyboardInterrupt:
            self.log("KeyboardInterrupt — 停止", telegram=True)
        finally:
            self._stop.set()
        self.log(f"StoryProducer 退出（完成 {stories} 条）。", telegram=True)
        return 0


def _count_cmd_lines(msg: str, cmd: str) -> int:
    head = f"{(cmd or '').strip()} "
    n = 0
    for line in (msg or "").splitlines():
        s = line.strip()
        if s.startswith(head) and ":" in s:
            n += 1
    return n


def _count_numbered_files(msg: str) -> int:
    n = 0
    for line in (msg or "").splitlines():
        s = line.strip()
        if s[:1].isdigit() and ".json" in s.lower():
            n += 1
    return n or 3


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="storyproducer")
    p.add_argument("--pick", default="next")
    p.add_argument("--once", action="store_true")
    p.add_argument("--nbi", type=int, default=None)
    p.add_argument("--grv-variant", type=int, default=3)
    p.add_argument(
        "--target",
        default="",
        help="GEMINI_ONLY / INFOGRAPHIC_ONLY / FULL_PROCESS（不填则 Telegram 询问）",
    )
    p.add_argument("--no-telegram", action="store_true")
    args = p.parse_args(argv)
    client = StoryProducerClient(
        pick=args.pick,
        once=args.once,
        nbi=args.nbi,
        grv_variant=args.grv_variant,
        telegram=not args.no_telegram,
        telegram_inbox=not args.no_telegram,
        target_stage=args.target,
    )
    return client.run()
