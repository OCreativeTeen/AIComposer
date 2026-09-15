"""Headless command engine — in-process, no GUI pump."""

from __future__ import annotations

import json
import os
from typing import Callable

from storyproducer.prompts import (
    build_gemini_prompt,
    build_notebooklm_clipbody,
    lm_choices,
    match_choice,
    narrator_choices,
    visual_style_choices,
)
from storyproducer.session import StorySession
from storyproducer import workflow as wfstore

_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")

_ALIASES = {
    "nbp": "notebooklm",
    "nblm": "notebooklm",
    "nbi": "open_notebooklm",
    "onb": "open_notebooklm",
    "nbif": "notebooklm_ready",
    "nbf": "notebooklm_ready",
    "itc": "whole_story_pick",
    "itcs": "whole_story_pick_skip",
    "grv": "grok_image",
    "gvd": "grok_download",
    "grvc": "grok_continue",
    "continue": "grok_continue",
    "scnlm": "scene_lm",
    "scnvs": "scene_visual_style",
    "sty": "style",
    "scnge": "gemini",
    "scnsave": "scene_save",
    "ssave": "scene_save",
    "nbv": "nbv",
    "pick": "story_pickup",
    "help": "help",
    "commands": "help",
    "start": "help",
    "status": "status",
    "sync": "status",
    "win": "status",
    "nar": "narrator",
    "narrator": "narrator",
}


class StoryEngine:
    """Operate on one in-memory story; persist to the channel list JSON."""

    def __init__(self) -> None:
        self.session = StorySession()

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    # ------------------------------------------------------------------ dispatch

    def dispatch(self, raw: str) -> tuple[bool, str]:
        text = (raw or "").strip()
        if not text:
            return False, "empty command"
        cmd, _, rest = text.partition(" ")
        cmd = cmd.strip().lower()
        value = rest.strip()
        name = _ALIASES.get(cmd, cmd)
        fn: Callable[[str], tuple[bool, str]] | None = getattr(self, f"cmd_{name}", None)
        if fn is None:
            return False, (
                f"unknown command: {cmd}\n"
                "可用：pick scnlm scnvs nar scnge scnsave nbp nbi nbif itc itcs grv gvd status help"
            )
        return fn(value)

    def cmd_help(self, _value: str = "") -> tuple[bool, str]:
        return True, (
            "storyproducer（无 GUI）\n"
            "pick / pick next / pick N\n"
            "scnlm [N]   选 LM 提示（生成 scene_content 用）\n"
            "scnvs [N]   选 Visual Style\n"
            "nar [N]     选 narrator（画外旁白声线）\n"
            "scnge       Gemini ×3；有已有数据时问 1=重生成 2=用已有\n"
            "scnge force / scnge use / scnge pick N\n"
            "scnsave     把选定 Gemini JSON 写入 video_detail.scene_content\n"
            "nbp 1       组 NotebookLM 封面提示词到剪贴板\n"
            "nbi N       开 NotebookLM，Generate ×3\n"
            "nbif        查 infographic 是否 ready\n"
            "itc / itcs  下载或跳过，发 Telegram 选封面\n"
            "itc N       选定封面并写入 cover_image / gen_video webp\n"
            "grv [profile] [variant]   Grok 出图+逐场景 video（失败留标签待 review）\n"
            "grvc / continue  review 后下载各标签 clip → scene_content\n"
            "gvd         补下载 mp4（同 grvc）\n"
            "status      当前故事与 workflow.stage"
        )

    def cmd_status(self, _value: str = "") -> tuple[bool, str]:
        s = self.session
        if not s.is_loaded():
            return True, "storyproducer：尚未 pick 故事。先发 pick。"
        sc = s.scene_count()
        wf = self.workflow() if s.is_loaded() else {}
        return True, (
            f"storyproducer（无 GUI）\n"
            f"title: {s.title()}\n"
            f"channel: {s.channel_id() or '?'}\n"
            f"workflow.stage: {wfstore.infer_stage(s.video_detail)}\n"
            f"infographic_status: {wf.get('infographic_status') or 'NONE'}\n"
            f"workflow.step: {wf.get('step') or '—'}\n"
            f"lm: {s.lm_label or '（未选）'}\n"
            f"visual_style: {s.visual_style or '（未选）'}\n"
            f"narrator: {s.narrator or '（未选）'}\n"
            f"scene_content: {sc} 场\n"
            f"cover_image: {os.path.basename(str((s.video_detail or {}).get('cover_image') or s.cover_path or '')) or '（未选）'}\n"
            f"nbi: {wf.get('nbi_index') or s.nbi_index or '—'}\n"
            f"grv variant: {wf.get('grv_variant') or s.grv_variant}"
        )

    def _need_story(self) -> tuple[bool, str] | None:
        if not self.session.is_loaded():
            return False, "还没有当前故事。先发 pick next 或 pick N。"
        return None

    def _reload_video_detail(self) -> None:
        from cli.video_choice_queue import (
            current_taken_queue_item,
            resolve_video_detail_from_queue_item,
        )

        item = current_taken_queue_item() or self.session.queue_item
        if not item:
            return
        vd = resolve_video_detail_from_queue_item(item)
        if isinstance(vd, dict):
            self.session.queue_item = item
            self.session.video_detail = vd

    def _persist_field(self, field: str, value) -> tuple[bool, str]:
        from cli.video_choice_queue import persist_active_video_detail_field

        ok, msg = persist_active_video_detail_field(field, value)
        if ok and isinstance(self.session.video_detail, dict):
            self.session.video_detail[field] = value
        return ok, msg

    def _patch_wf(self, patch: dict) -> dict:
        return wfstore.persist_workflow(self.session.video_detail, patch)

    def workflow(self) -> dict:
        return wfstore.get_workflow(self.session.video_detail)

    def mark_stage(self, stage: str, **extra) -> dict:
        patch = {"stage": stage}
        patch.update(extra)
        return self._patch_wf(patch)

    def inferred_stage(self) -> str:
        return wfstore.infer_stage(self.session.video_detail)

    def _load_scene_json_for_save(
        self, *, prefer_session: bool = False
    ) -> tuple[list | None, str]:
        """Gemini pick 文件优先，其次内存 ``scene_content``。返回 ``(parsed, source)``。"""
        from pathlib import Path

        if prefer_session:
            sc = self.session.scene_content()
            if sc:
                return sc, "session"

        gem = self.workflow()
        gemini_path = str(gem.get("gemini_picked_path") or "").strip()
        if not gemini_path:
            picked = int(gem.get("gemini_picked") or 0)
            files = [str(p) for p in (gem.get("gemini_files") or []) if str(p).strip()]
            if picked and 1 <= picked <= len(files):
                gemini_path = files[picked - 1]
        if gemini_path and os.path.isfile(gemini_path):
            try:
                value = json.loads(Path(gemini_path).read_text(encoding="utf-8"))
            except Exception as exc:
                return None, f"读取 {gemini_path} 失败：{exc}"
            if isinstance(value, list) and value:
                return value, f"disk:{os.path.basename(gemini_path)}"
        sc = self.session.scene_content()
        if sc:
            return sc, "session"
        return None, ""

    def _persist_scene_content_from_picked(
        self, *, prefer_session: bool = False
    ) -> tuple[bool, str]:
        """把已选 Gemini JSON 写入当前故事的 ``video_detail.scene_content``。"""
        parsed, source = self._load_scene_json_for_save(prefer_session=prefer_session)
        if not parsed:
            return False, "没有可保存的 scene JSON。请先 scnge 并 pick 1/2/3。"
        parsed = wfstore.normalize_scene_content(parsed)
        ok, msg = self._persist_field("scene_content", parsed)
        if not ok:
            return False, f"scnsave failed: {msg}"
        self._reload_video_detail()
        self._patch_wf(
            {
                "step": "scnsave",
                "stage": wfstore.STAGE_GEMINI_DONE,
            }
        )
        return True, f"scnsave ok — {len(parsed)} scenes saved ({source})"

    # ------------------------------------------------------------------ pick

    def cmd_story_pickup(self, value: str = "") -> tuple[bool, str]:
        from cli.video_choice_queue import (
            activate_queue_item,
            apply_queue_item_yt_prefs,
            describe_queue_stories,
            first_pending_story_index,
            list_queue_items,
            queue_item_at,
            resolve_video_detail_from_queue_item,
        )

        want = (value or "").strip().translate(_FULLWIDTH)
        low = want.lower().replace(" ", "")
        if low in ("exit", "finish", "stop", "quit", "结束", "停"):
            return True, "pick exit — 本轮结束。"
        info = describe_queue_stories()
        rows = info.get("rows") or []
        if not want:
            if not rows:
                return True, "pick：队列是空的。请先在原 GUI 热门列表导出选择队列。"
            lines = ["pick："]
            for row in rows:
                mark = " ←当前" if row.get("current") else ""
                title = (row.get("title") or "")[:80]
                status = row.get("status_zh") or ""
                lines.append(f"pick {row['index']}: ([{status}] {title}{mark})")
            lines.append(
                f"共 {info.get('total')} 条；未处理 {info.get('pending')}；"
                f"已完成 {info.get('done')}。"
            )
            suggest = info.get("suggest")
            if suggest:
                lines.append(f"建议：pick {suggest} 或 pick next")
            return True, "\n".join(lines)

        item = None
        if low in ("next", "n", "下一个", "下一条"):
            suggest = first_pending_story_index()
            if not suggest:
                return True, "没有未处理的了。发 pick 看列表，或 pick N 重做。"
            item = queue_item_at(suggest)
        elif want.isdigit():
            item = queue_item_at(int(want))
        else:
            for it in list_queue_items():
                cid = (it.get("choice_id") or "").strip()
                title = (it.get("title") or "").strip()
                if cid == want or (title and want.lower() in title.lower()):
                    item = it
                    break
            if not item:
                return False, f"unknown pick: {value}"

        chosen = activate_queue_item(item.get("choice_id") or "")
        apply_queue_item_yt_prefs(chosen)
        vd = resolve_video_detail_from_queue_item(chosen)
        if not isinstance(vd, dict):
            return False, "队列条没有对应的频道 list 行（video_detail）。"
        self.session = StorySession(
            queue_item=chosen,
            video_detail=vd,
            visual_style=(chosen.get("visual_style") or vd.get("visual_style") or "").strip(),
            narrator=(chosen.get("narrator") or vd.get("narrator") or "").strip(),
            grv_variant=self.session.grv_variant,
        )
        wfstore.restore_session_fields(self.session)
        stage = wfstore.infer_stage(self.session.video_detail)
        self._patch_wf({"step": "picked", "stage": stage})
        sc = self.session.scene_count()
        wf_note = ""
        wf = self.workflow()
        if wf.get("lm_label") or wf.get("step") or stage:
            wf_note = (
                f"\nworkflow: stage={stage}  "
                f"infographic={wf.get('infographic_status') or 'NONE'}  "
                f"step={wf.get('step') or '—'}  "
                f"lm={self.session.lm_label or '—'}  "
                f"style={self.session.visual_style or '—'}  "
                f"nar={self.session.narrator or '—'}"
            )
        return True, (
            f"pick ok — {self.session.title()}\n"
            f"channel={self.session.channel_id() or '?'}  "
            f"scene_content={sc} 场  analyzed="
            f"{'yes' if (vd.get('analyzed_content') or '').strip() else 'no'}"
            f"{wf_note}"
        )

    # ------------------------------------------------------------------ choices

    def _list_or_set(
        self,
        labels: list[str],
        cmd: str,
        value: str,
        *,
        setter,
        empty_msg: str,
    ) -> tuple[bool, str]:
        if not labels:
            return False, empty_msg
        want = (value or "").strip()
        if not want:
            lines = [f"{cmd}："]
            for i, lab in enumerate(labels, 1):
                lines.append(f"{cmd} {i}: ({lab})")
            return True, "\n".join(lines)
        matched = match_choice(want, labels)
        if not matched:
            return False, f"unknown {cmd}: {want}\nchoices: " + " | ".join(labels)
        return setter(matched)

    def cmd_scene_lm(self, value: str = "") -> tuple[bool, str]:
        miss = self._need_story()
        if miss:
            return miss
        labels = [lbl for lbl, _ in lm_choices(self.session.channel_id())]
        if not labels:
            labels = [
                "Short Story",
                "2 Step Story",
                "3 Step Story",
                "4 Step Story",
                "Mini Story",
                "Long Story",
            ]

        def _set(lab: str) -> tuple[bool, str]:
            self.session.lm_label = lab
            self._patch_wf({"step": "scnlm", "lm_label": lab})
            return True, f"scnlm ok — {lab}"

        return self._list_or_set(
            labels, "scnlm", value, setter=_set, empty_msg="没有 LM 提示词选项。"
        )

    def cmd_scene_visual_style(self, value: str = "") -> tuple[bool, str]:
        miss = self._need_story()
        if miss:
            return miss
        labels = visual_style_choices()

        def _set(lab: str) -> tuple[bool, str]:
            import project_manager

            self.session.visual_style = lab
            project_manager.LAST_VISUAL_STYLE = lab
            self._persist_field("visual_style", lab)
            self._patch_wf({"step": "scnvs", "visual_style": lab})
            return True, f"scnvs ok — {lab}"

        return self._list_or_set(
            labels, "scnvs", value, setter=_set, empty_msg="没有 Visual Style 选项。"
        )

    cmd_style = cmd_scene_visual_style

    def cmd_narrator(self, value: str = "") -> tuple[bool, str]:
        miss = self._need_story()
        if miss:
            return miss
        labels = narrator_choices()

        def _set(lab: str) -> tuple[bool, str]:
            import project_manager

            self.session.narrator = lab
            if hasattr(project_manager, "LAST_NARRATOR"):
                project_manager.LAST_NARRATOR = lab
            self._persist_field("narrator", lab)
            self._patch_wf({"step": "nar", "narrator": lab})
            return True, f"nar ok — {lab}"

        return self._list_or_set(
            labels, "nar", value, setter=_set, empty_msg="没有 narrator 选项。"
        )

    # ------------------------------------------------------------------ gemini / save

    def cmd_gemini(self, value: str = "") -> tuple[bool, str]:
        miss = self._need_story()
        if miss:
            return miss

        want = (value or "").strip().translate(_FULLWIDTH).lower()
        wf = self.workflow()
        if want.startswith("pick"):
            parts = want.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return self.cmd_gemini_pick(parts[1])
            return False, "用法：scnge pick 1"
        if want.isdigit() and wf.get("gemini_pending_pick"):
            return self.cmd_gemini_pick(want)
        if want in ("use", "copy", "existing", "skip", "reuse", "已有"):
            return self._use_existing_scenes()
        if want in ("force", "regen", "generate", "new", "生成", "重新"):
            return self._run_gemini()
        existing = self.session.scene_content()
        if existing:
            self._patch_wf(
                {
                    "step": "scnge_choice",
                    "gemini_pending_regen_choice": True,
                    "gemini_regen_or_reuse": "",
                }
            )
            return True, (
                f"已有 {len(existing)} 场 scene_content。\n"
                "1 = 用 Gemini 重新生成 ×3（scnge force）\n"
                "2 = 用已有数据（scnge use）\n"
                "请 Telegram 回复 1 或 2。"
            )
        return self._run_gemini()

    def _use_existing_scenes(self) -> tuple[bool, str]:
        sc = self.session.scene_content()
        if not sc:
            return False, "还没有 scene_content。请先 scnge 生成。"
        self._patch_wf(
            {
                "step": "scnge_use",
                "stage": wfstore.STAGE_GEMINI_DONE,
                "gemini_pending_regen_choice": False,
                "gemini_pending_pick": False,
                "gemini_regen_or_reuse": "use",
            }
        )
        ok_save, msg_save = self._persist_scene_content_from_picked(
            prefer_session=True
        )
        if ok_save:
            return True, (
                f"scnge ok — 已用已有 {len(sc)} 场 scene_content。\n{msg_save}"
            )
        return True, (
            f"scnge ok — 已用已有 {len(sc)} 场 scene_content。\n"
            f"警告：写入频道列表失败：{msg_save}\n请手动发 scnsave。"
        )

    def _run_gemini(self) -> tuple[bool, str]:
        from cli.browser_tasks import generate_gemini_scene_variants

        if not self.session.lm_label:
            return False, "请先 scnlm 选 LM 提示（如 4 Step Story），再 scnge。"
        prompt = build_gemini_prompt(
            self.session.video_detail,
            channel_id=self.session.channel_id(),
            lm_label=self.session.lm_label,
            visual_style=self.session.visual_style,
            instruction=self.session.instruction,
            language=self.session.language(),
        )
        if len(prompt) < 400:
            return False, (
                "Gemini prompt 太短。请确认本条有 analyzed_content，并已 scnlm。"
            )
        try:
            paths = generate_gemini_scene_variants(prompt)
        except Exception as exc:
            return False, f"gemini failed: {exc}"
        self.session.gemini_paths = list(paths)
        self._patch_wf(
            {
                "step": "scnge_pick",
                "gemini_pending_regen_choice": False,
                "gemini_pending_pick": True,
                "gemini_files": list(paths),
                "gemini_picked": 0,
                "gemini_picked_path": "",
                "gemini_regen_or_reuse": "force",
            }
        )
        lines = "\n".join(f"  {i}. {p}" for i, p in enumerate(paths, 1))
        return True, (
            f"scnge ok — 已生成 {len(paths)} 份场景 JSON：\n{lines}\n"
            "请打开对比后，在 Telegram 回复 1 / 2 / 3（或 scnge pick N）。\n"
            "选定后会自动 scnsave 写入频道列表。"
        )

    def cmd_gemini_pick(self, value: str = "") -> tuple[bool, str]:
        want = (value or "").strip().translate(_FULLWIDTH)
        if not want.isdigit():
            return False, "用法：scnge pick 1"
        index = int(want)
        gem = self.workflow()
        files = [str(p) for p in (gem.get("gemini_files") or []) if str(p).strip()]
        if not gem.get("gemini_pending_pick") and int(gem.get("gemini_picked") or 0) == index:
            path = str(gem.get("gemini_picked_path") or "")
            if path:
                ok_save, msg_save = self._persist_scene_content_from_picked()
                if ok_save:
                    return True, (
                        f"scnge pick ok — 已选 {os.path.basename(path)}。\n{msg_save}"
                    )
                return True, (
                    f"scnge pick ok — 已选 {os.path.basename(path)}。\n"
                    f"警告：自动 scnsave 失败：{msg_save}\n请手动发 scnsave。"
                )
        if not files:
            return False, "当前没有待选的场景 JSON（先发 scnge）。"
        if index < 1 or index > len(files):
            return False, f"请选 1…{len(files)}。"
        path = files[index - 1]
        if not os.path.isfile(path):
            return False, f"文件不存在：{path}"
        self.session.gemini_pick = index
        self._patch_wf(
            {
                "step": "scnge_picked",
                "gemini_pending_pick": False,
                "gemini_picked": index,
                "gemini_picked_path": path,
            }
        )
        n = "?"
        try:
            with open(path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            n = len(parsed) if isinstance(parsed, list) else "?"
        except Exception:
            pass
        ok_save, msg_save = self._persist_scene_content_from_picked()
        base = (
            f"scnge pick ok — #{index}（{os.path.basename(path)}） — {n} scenes。"
        )
        if ok_save:
            return True, f"{base}\n{msg_save}"
        return True, (
            f"{base}\n"
            f"警告：自动 scnsave 失败：{msg_save}\n"
            "请手动发 scnsave。"
        )

    def cmd_scene_save(self, _value: str = "") -> tuple[bool, str]:
        miss = self._need_story()
        if miss:
            return miss
        ok, msg = self._persist_scene_content_from_picked()
        if not ok:
            return False, msg
        return True, msg

    # ------------------------------------------------------------------ notebooklm / covers

    def cmd_notebooklm(self, value: str = "") -> tuple[bool, str]:
        miss = self._need_story()
        if miss:
            return miss
        import config_prompt
        from cli.browser_tasks import write_windows_clipboard

        lang = ""
        try:
            import config

            lang = config.llm_language_label(self.session.language())
        except Exception:
            pass
        rows = config_prompt.notebooklm_export_flat_choices(lang)
        labels = [row[0] for row in rows]
        want = (value or "").strip()
        if not want:
            lines = ["nbp："]
            for i, lab in enumerate(labels, 1):
                lines.append(f"nbp {i}: ({lab})")
            return True, "\n".join(lines)
        matched = match_choice(want, labels)
        base = var = ""
        if matched:
            for lab, b, v in rows:
                if lab == matched:
                    base, var = b, v
                    break
        else:
            parsed = config_prompt.parse_nb_export_choice(want)
            if parsed:
                base, var = parsed
                try:
                    matched = next(lab for lab, b, v in rows if b == base and v == var)
                except StopIteration:
                    matched = config_prompt.nb_export_mode_label(base, var)
        if not base:
            return False, "unknown NotebookLM export: " + want + "\nchoices: " + " | ".join(labels)
        actor = self.session.actor_for_scene(0)
        try:
            body = build_notebooklm_clipbody(
                self.session.video_detail,
                mode=base,
                variant=var,
                visual_style=self.session.visual_style,
                main_character=actor,
                host_narrator=self.session.narrator,
                scene_index=-1,
                language=self.session.language(),
            )
        except Exception as exc:
            return False, f"nbp failed: {exc}"
        try:
            write_windows_clipboard(body)
        except Exception as exc:
            return False, f"写入剪贴板失败：{exc}"
        self._patch_wf(
            {
                "step": "nbp",
                "nbp_mode": base,
                "nbp_variant": var,
                "nbp_label": matched,
            }
        )
        return True, f"nbp ok — copied {matched} ({base}/{var}) to clipboard"

    def cmd_open_notebooklm(self, value: str = "") -> tuple[bool, str]:
        import config
        from cli.browser_tasks import handle_notebooklm_covers

        want = (value or "").strip().translate(_FULLWIDTH)
        if not want:
            profiles = config.list_gemini_chrome_profiles() or []
            lines = ["nbi："]
            for i, p in enumerate(profiles, 1):
                lines.append(f"nbi {i}: ({p.get('label') or '?'})")
            return True, "\n".join(lines)
        try:
            selected = config.set_gemini_chrome_profile(want)
        except ValueError as exc:
            return False, str(exc)
        try:
            detail = handle_notebooklm_covers(
                times=3, language=self.session.language()
            )
        except Exception as exc:
            return False, f"nbi failed: {exc}"
        idx = int(want) if want.isdigit() else 0
        self.session.nbi_index = idx
        self._patch_wf(
            {
                "step": "nbi",
                "stage": wfstore.STAGE_INFOGRAPHIC_PENDING,
                "infographic_status": wfstore.INFO_SUBMITTED,
                "nbi_index": idx,
                "nbi_profile": selected.get("label") or "",
                "cover_expected": 3,
            }
        )
        return True, f"nbi ok — {selected.get('label')}\n{detail}"

    def cmd_notebooklm_ready(self, _value: str = "") -> tuple[bool, str]:
        from cli.browser_tasks import check_notebooklm_infographic_status

        expected = int(self.workflow().get("cover_expected") or 3) or 3
        try:
            st = check_notebooklm_infographic_status(expected=expected)
        except Exception as exc:
            return False, f"nbif failed: {exc}"
        if not isinstance(st, dict) or not st.get("ok"):
            return False, f"nbif — {(st or {}).get('error') or '查询失败'}"
        gen_n = int(st.get("generating_count") or 0)
        if st.get("ready"):
            self._patch_wf(
                {
                    "step": "nbif_ready",
                    "stage": wfstore.STAGE_INFOGRAPHIC_PENDING,
                    "infographic_status": wfstore.INFO_SUBMITTED,
                }
            )
            return True, "nbif — 三个新的 infographic 已经 ready。"
        if st.get("uncertain"):
            return True, f"nbif — 还不能判定 ready。{st.get('error') or ''}"
        return True, f"nbif — 还没有 ready，仍在生成中（{gen_n} 条 Generating）。"

    def _send_cover_files(self, files: list[str], *, from_disk: bool = False) -> tuple[bool, str]:
        from utility.telegram_cli import notify_whole_story_covers_for_pick

        paths = [p for p in (files or []) if p and os.path.isfile(p)]
        if not paths:
            return False, "itc 没有封面图。"
        self._patch_wf(
            {
                "step": "itc_wait_pick",
                "cover_pending_pick": True,
                "cover_files": paths,
                "cover_picked": 0,
                "cover_selected_path": "",
                "cover_expected": len(paths),
            }
        )
        tg_lines = notify_whole_story_covers_for_pick(paths)
        extra = "\n".join(tg_lines) if tg_lines else ""
        src = "已有 Infographic" if from_disk else "NotebookLM 下载"
        return True, (
            f"itc ok — {src} {len(paths)} 张，已发 Telegram 请选 1…{len(paths)}。\n"
            f"{extra}"
        ).strip()

    def cmd_whole_story_pick(self, value: str = "") -> tuple[bool, str]:
        from cli.commands import install_story_cover_from_image

        want = (value or "").strip().translate(_FULLWIDTH)
        pick_idx = None
        if want.isdigit():
            pick_idx = int(want)
        elif want.lower().startswith("pick"):
            parts = want.split()
            if len(parts) >= 2 and parts[1].isdigit():
                pick_idx = int(parts[1])
        cover = self.workflow()
        files = [str(p) for p in (cover.get("cover_files") or []) if str(p).strip()]
        if pick_idx is not None:
            if files and 1 <= pick_idx <= len(files):
                path = files[pick_idx - 1]
                self.session.cover_path = path
                ok, msg = install_story_cover_from_image(path)
                note = msg if ok else f"封面写入失败：{msg}"
                try:
                    from cli.browser_tasks import copy_image_file_to_clipboard

                    copy_image_file_to_clipboard(path)
                except Exception:
                    pass
                dest = _cover_dest_from_install_msg(msg) if ok else ""
                cover_image = dest or path
                if ok and cover_image:
                    self._persist_field("cover_image", cover_image)
                    if isinstance(self.session.video_detail, dict):
                        self.session.video_detail["cover_image"] = cover_image
                self.session.cover_path = (cover_image if ok else path) or path
                wf_patch = {
                    "step": "cover_picked",
                    "cover_pending_pick": False,
                    "cover_pending_gen_choice": False,
                    "cover_picked": pick_idx,
                    "cover_selected_path": cover_image if ok else path,
                    "selected_infographic_image": path,
                }
                if ok:
                    wf_patch["stage"] = wfstore.STAGE_INFOGRAPHIC_DONE
                    wf_patch["infographic_status"] = wfstore.INFO_COMPLETED
                self._patch_wf(wf_patch)
                return True, (
                    f"itc ok — 封面已记录 #{pick_idx} {os.path.basename(path)}\n{note}"
                )
            if cover.get("cover_pending_pick"):
                return False, f"请选 1…{len(files) or 3}。"
            return False, "还没有封面图。请先 itc 或 itcs。"
        if want:
            return False, "用法：itc   或  itc 1"
        from cli.browser_tasks import capture_notebooklm_infographics

        expected = int(cover.get("cover_expected") or 3) or 3
        try:
            files = capture_notebooklm_infographics(
                times=expected, require_ready=True, attach_only=False
            )
        except Exception as exc:
            return False, f"itc failed: {exc}"
        return self._send_cover_files(list(files or []))

    def cmd_whole_story_pick_skip(self, _value: str = "") -> tuple[bool, str]:
        import config

        expected = int(getattr(config, "INFOGRAPHIC_COVER_COUNT", 3) or 3)
        files = config.infographic_slot_files_for_pick(expected)
        if len(files) < expected:
            missing = []
            for i in range(1, expected + 1):
                p = config.resolve_infographic_cover_path(i)
                if not os.path.isfile(p):
                    missing.append(os.path.basename(config.infographic_cover_path(i)))
            base = os.path.dirname(config.infographic_cover_path(1)) or "aiagent"
            return False, (
                f"itcs 需要 {expected} 张封面，当前只有 {len(files)} 张。\n"
                f"缺少：{', '.join(missing) or '?'}\n"
                f"请把图放到 {base}\\Infographic_1…{expected}。"
            )
        return self._send_cover_files(files, from_disk=True)

    # ------------------------------------------------------------------ grok

    def cmd_nbv(self, value: str = "") -> tuple[bool, str]:
        import config_prompt

        want = (value or "").strip().translate(_FULLWIDTH)
        cur = int(self.workflow().get("grv_variant") or self.session.grv_variant or 3)
        if not want:
            return True, (
                config_prompt.format_grok_scene_video_nb_choices()
                + f"\n当前：{cur}（{config_prompt.grok_scene_video_nb_choice_label(cur)}）"
            )
        if not want.isdigit():
            return False, "用法：nbv 3"
        idx = int(want)
        self.session.grv_variant = idx
        self._patch_wf({"step": "nbv", "grv_variant": idx})
        return True, (
            f"nbv ok — video 提示词变体 {idx}（"
            f"{config_prompt.grok_scene_video_nb_choice_label(idx)}）"
        )

    def cmd_grok_image(self, value: str = "") -> tuple[bool, str]:
        miss = self._need_story()
        if miss:
            return miss
        import config
        import config_prompt
        from storyproducer.grok import run_grok_imagine

        n = self.session.scene_count()
        if n < 1:
            self._reload_video_detail()
            n = self.session.scene_count()
        if n < 1:
            ok_save, msg_save = self._persist_scene_content_from_picked()
            if ok_save:
                n = self.session.scene_count()
            elif msg_save:
                self.log(f"grv: auto scnsave before grok — {msg_save}")
        if n < 1:
            return False, "还没有 scene_content。请先 scnge → scnsave。"
        want = (value or "").strip().translate(_FULLWIDTH)
        parts = [p for p in want.split() if p]
        video_nb_index: int | None = None
        profile_override: int | None = None
        if len(parts) >= 2 and parts[-1].isdigit():
            vi = int(parts[-1])
            n_var = len(config_prompt.GROK_SCENE_VIDEO_NB_VARIANTS) or 8
            if 1 <= vi <= n_var:
                video_nb_index = vi
                if parts[0].isdigit():
                    profile_override = int(parts[0])
        elif parts and parts[0].isdigit():
            profile_override = int(parts[0])
        from cli.browser_tasks import prepare_grok_imagine_session

        try:
            grv_idx, grv_label, selected, grok_port = prepare_grok_imagine_session(
                profile_override=profile_override
            )
        except ValueError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"grv Chrome failed: {exc}"
        if video_nb_index is not None:
            self.session.grv_variant = video_nb_index
        v_idx = video_nb_index if video_nb_index is not None else int(
            self.workflow().get("grv_variant") or self.session.grv_variant or 3
        )
        self._patch_wf(
            {
                "step": "grv",
                "grv_variant": v_idx,
                "grv_profile_index": grv_idx,
                "grv_profile": selected.get("label") or "",
            }
        )
        try:
            detail, video_results = run_grok_imagine(
                self.session.video_detail,
                n,
                video_nb_index=v_idx,
                visual_style=self.session.visual_style,
                host_narrator=self.session.narrator,
                language=self.session.language(),
                cdp_port=grok_port,
            )
        except Exception as exc:
            return False, f"grv failed ({selected.get('label')}): {exc}"
        self._patch_wf(
            {
                "step": "grv_review",
                "grv_review_pending": True,
                "grok_video_results": list(video_results or []),
                "grv_variant": v_idx,
                "grv_profile_index": grv_idx,
                "grv_profile": selected.get("label") or "",
            }
        )
        return True, (
            f"grv ok — profile #{grv_idx} {selected.get('label')}  scenes={n}  "
            f"video_nb={v_idx}\n{detail}"
        )

    def cmd_grok_continue(self, _value: str = "") -> tuple[bool, str]:
        return self._grok_download_after_review(step="grvc")

    def cmd_grok_download(self, _value: str = "") -> tuple[bool, str]:
        return self._grok_download_after_review(step="gvd")

    def _grok_download_after_review(self, *, step: str) -> tuple[bool, str]:
        try:
            from cli.browser_tasks import download_grok_scene_videos

            files = download_grok_scene_videos(continue_on_error=True)
        except Exception as exc:
            return False, f"{step} failed: {exc}"
        ok_files = [f for f in (files or []) if f.get("path")]
        if not ok_files:
            failed = [f for f in (files or []) if f.get("status") != "ok"]
            hint = ""
            if failed:
                hint = "\n".join(
                    f"  场景 {f.get('scene')}: {f.get('error', '')[:100]}"
                    for f in failed
                )
            return False, (
                f"{step} 没有成功下载任何 mp4。"
                "请确认各 Grok 标签已出片后再发 continue。\n" + hint
            ).strip()
        wfstore.persist_scene_clips(ok_files)
        self._reload_video_detail()
        vd = self.session.video_detail if isinstance(self.session.video_detail, dict) else {}
        sc = self.session.scene_content() or []
        patch: dict = {
            "step": step,
            "grv_review_pending": False,
        }
        if sc and wfstore.story_has_all_clips(vd):
            patch["stage"] = wfstore.STAGE_COMPLETED
        self._patch_wf(patch)
        failed = [f for f in (files or []) if f.get("status") != "ok"]
        lines = [f"{step} ok — 已下载 {len(ok_files)} clip(s)，写入 grok_video_results"]
        for item in ok_files:
            lines.append(
                f"  scene {item.get('scene')}: {os.path.basename(item.get('path') or '')}"
            )
        if failed:
            lines.append(f"仍有 {len(failed)} 个场景下载失败（可修好后再发 gvd）：")
            for item in failed:
                lines.append(
                    f"  scene {item.get('scene')}: {str(item.get('error') or '')[:100]}"
                )
        else:
            lines.append("全部 clip 已记录 — ready")
        return True, "\n".join(lines)

    def start_cover_gen_choice(self, *, existing_count: int, expected: int) -> None:
        self._patch_wf(
            {
                "step": "cover_gen_choice",
                "cover_pending_gen_choice": True,
                "cover_gen_choice": "",
                "cover_expected": expected,
                "cover_existing_count": existing_count,
            }
        )

    def record_cover_gen_choice(self, raw: str) -> str:
        choice = wfstore.normalize_cover_gen_choice(raw)
        if not choice:
            raise ValueError("请回复 1=生成新封面，或 2=跳过")
        cover = self.workflow()
        if not cover.get("cover_pending_gen_choice"):
            raise ValueError("当前不在等待封面生成选择")
        self._patch_wf(
            {
                "cover_pending_gen_choice": False,
                "cover_gen_choice": choice,
            }
        )
        return choice

    def take_cover_gen_choice(self) -> str:
        cover = self.workflow()
        choice = str(cover.get("cover_gen_choice") or "").strip()
        if choice and not cover.get("cover_pending_gen_choice"):
            return choice
        return ""

    def next_nbi_start(self, *, override: int | None = None) -> tuple[int, str]:
        import config

        profiles = config.list_gemini_chrome_profiles() or []
        n = max(1, len(profiles))
        idx = wfstore.next_nbi_index(
            wfstore.list_path_from_session(self.session), n, override=override
        )
        label = ""
        if 1 <= idx <= len(profiles):
            label = str(profiles[idx - 1].get("label") or "")
        return idx, label


def _cover_dest_from_install_msg(msg: str) -> str:
    for line in (msg or "").splitlines():
        if "封面已保存" in line and ":" in line:
            return line.split(":", 1)[-1].strip()
    return ""
