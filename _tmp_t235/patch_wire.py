# -*- coding: utf-8 -*-
"""t235u: wire apply_look + fix clone look pass-through."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"D:\AIComposer")


def patch_wf():
    path = ROOT / "gui" / "workflow" / "wf_prompt_flows.py"
    text = path.read_text(encoding="utf-8")
    if "def apply_look(" in text and "t235u" in text:
        print("wf apply_look already present")
    else:
        anchor = '''        def on_story_style(key: str) -> None:
            """生场视频里选了叙事风格：写 project story_style，同步主窗口「故事风格」，记为上次选择。"""
'''
        if anchor not in text:
            raise SystemExit("on_story_style anchor not found")
        inject = '''        def apply_look(look: dict) -> None:
            """t235u: 提交确认里改过的全场内容写回主窗口（画面风格 / 场景风格 / 讲员 / 地域 · 时代）。"""
            look = dict(look or {})
            vs = config.match_visual_style(look.get("visual_style") or "")
            if vs and hasattr(self, "scene_visual_style"):
                try:
                    self.scene_visual_style.set(vs)
                except Exception:  # noqa: BLE001
                    pass
            ss = config_prompt.normalize_scene_style(look.get("scene_style"))
            if hasattr(self, "scene_style"):
                try:
                    self.scene_style.set(ss or config_prompt.SCENE_STYLE_LABELS[0])
                except Exception:  # noqa: BLE001
                    pass
            region = (look.get("region") or "").strip()
            era = (look.get("era") or "").strip()
            if region not in config_prompt.SETTING_PLACES:
                region, era = "", ""
            eras = config_prompt.setting_era_labels(region)
            if era not in eras:
                era = eras[0] if eras else ""
            if hasattr(self, "setting_region"):
                try:
                    self.setting_region.set(region)
                    if hasattr(self, "setting_era"):
                        self.setting_era["values"] = eras
                        self.setting_era.set(era)
                except Exception:  # noqa: BLE001
                    pass
            nar = (look.get("narrator") or "").strip()
            pc = project_manager.PROJECT_CONFIG
            if isinstance(pc, dict):
                if pc.get("narrator") != nar:
                    pc["narrator"] = nar
                project_manager.LAST_NARRATOR = nar
            if callable(getattr(self, "_refresh_narrator_button", None)):
                try:
                    self._refresh_narrator_button(nar)
                except Exception:  # noqa: BLE001
                    pass
            try:
                project_manager.remember_setting_place(region, era)
            except Exception:  # noqa: BLE001
                pass
            try:
                project_manager.remember_scene_style(ss)
            except Exception:  # noqa: BLE001
                pass
            if vs:
                try:
                    project_manager.LAST_VISUAL_STYLE = vs
                except Exception:  # noqa: BLE001
                    pass
            if callable(getattr(self, "_save_project_look", None)):
                try:
                    self._save_project_look()
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 全场内容写回项目失败：{exc}")

        def on_story_style(key: str) -> None:
            """生场视频里选了叙事风格：写 project story_style，同步主窗口「故事风格」，记为上次选择。"""
'''
        text = text.replace(anchor, inject, 1)
        print("added apply_look")

    call = '''        open_video_prompt_dialog(
            self.root,
            self._nb_story_video_btn,
            get_scenes=lambda: [s for s in [current_scene()] if isinstance(s, dict)],
            get_style=get_style,
            copy_text=copy_text,
            language=getattr(self.workflow, "language", "") or "",
            host_narrator=project_manager.project_narrator(),
            get_place=lambda: (
                (self.setting_region.get() or "").strip(),
                (self.setting_era.get() or "").strip(),
            ),
'''
    if "apply_look=apply_look" in text:
        print("apply_look already passed")
    else:
        if call not in text:
            raise SystemExit("open_video_prompt_dialog call not found")
        # insert apply_look= near on_story_style=
        if "on_story_style=on_story_style," not in text:
            raise SystemExit("on_story_style= kw not found")
        text = text.replace(
            "on_story_style=on_story_style,",
            "on_story_style=on_story_style,\n            apply_look=apply_look,",
            1,
        )
        print("passed apply_look to open_video_prompt_dialog")

    raw = text.encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    path.write_bytes(raw)
    print("wf_prompt_flows written")


def patch_clone():
    path = ROOT / "gui" / "dl" / "channel_videos_dialog.py"
    text = path.read_text(encoding="utf-8")
    old = '''                        if _action == "clone":
                            ac = cfg.get("analyzed_content") or vd.get("analyzed_content")
                            sc = cfg.get("scene_content") or vd.get("scene_content")
                            _look_vs, _look_talk, _look_nar = _project_look_from_row(vd, cfg)
                            _create_new_project_from_raw(
                                ac,
                                sc,
                                narrator=_look_nar,
                                visual_style=_look_vs,
                                language=cfg.get("language"),
                                topic_category_kw=_topic_category_val(cfg),
                                topic_subtype_kw=_topic_subtype_val(cfg),
                                topic_tags_kw=_topic_tags_val(cfg),
                                superseded_pid=cfg_pid,
                                dialogue_mode=_look_talk,
                                title=(cfg.get("video_title") or "").strip() or None,
                            )
                            return
'''
    new = '''                        if _action == "clone":
                            ac = cfg.get("analyzed_content") or vd.get("analyzed_content")
                            sc = cfg.get("scene_content") or vd.get("scene_content")
                            _look_vs, _look_talk, _look_nar = _project_look_from_row(vd, cfg)
                            # t235u: 参照已有项目新建时，地域 / 时代 / 场景风格 / 故事风格也从 cfg∪vd 带上（勿丢）
                            _clone_region = (
                                (cfg.get("setting_region") or vd.get("setting_region") or "").strip() or None
                            )
                            _clone_era = (
                                (cfg.get("setting_era") or vd.get("setting_era") or "").strip() or None
                            )
                            _clone_ss = cfg.get("scene_style")
                            if _clone_ss is None:
                                _clone_ss = vd.get("scene_style")
                            if isinstance(cfg, dict) and (cfg.get("story_style") or "").strip():
                                vd["story_style"] = (cfg.get("story_style") or "").strip()
                            _create_new_project_from_raw(
                                ac,
                                sc,
                                narrator=_look_nar,
                                visual_style=_look_vs,
                                language=cfg.get("language"),
                                topic_category_kw=_topic_category_val(cfg),
                                topic_subtype_kw=_topic_subtype_val(cfg),
                                topic_tags_kw=_topic_tags_val(cfg),
                                superseded_pid=cfg_pid,
                                dialogue_mode=_look_talk,
                                setting_region=_clone_region,
                                setting_era=_clone_era,
                                scene_style=_clone_ss,
                                title=(cfg.get("video_title") or "").strip() or None,
                            )
                            return
'''
    if "t235u: 参照已有项目新建时" in text:
        print("clone path already patched")
    else:
        if old not in text:
            raise SystemExit("clone block not found")
        text = text.replace(old, new, 1)
        print("patched clone look pass-through")

    # Also strengthen _create_new_project_from_raw fallbacks for story_style from cfg-like vd
    # and ensure visual_style/narrator/dialogue from look aren't overwritten by LAST when empty string from look is wrong.
    # Improve: when visual_style arg is None use look from vd first (already does via caller).
    # Strengthen story_style fallback:
    old_ss = '''                    story_style=(vd.get("story_style") or "").strip() or None,
                    # t110u: 项目名 = 选定/手改的名称;没有才用首场 caption
                    title=(title or vd.get(project_manager.PENDING_PROJECT_TITLE_KEY) or "").strip() or None,
'''
    # Also pull setting from vd more carefully when scene_style is "" (empty is valid)
    # Current:
    #   if scene_style is None and vd.get("scene_style") is not None:
    #       scene_style = vd.get("scene_style")
    # That's correct for empty string.
    # For story_style, also check project_profile:
    new_ss = '''                    story_style=(
                        (vd.get("story_style") or "").strip()
                        or (
                            (vd.get(project_manager.PROJECT_PROFILE_KEY) or {}).get("story_style") or ""
                            if isinstance(vd.get(project_manager.PROJECT_PROFILE_KEY), dict) else ""
                        ).strip()
                        or None
                    ),
                    # t110u: 项目名 = 选定/手改的名称;没有才用首场 caption
                    title=(title or vd.get(project_manager.PENDING_PROJECT_TITLE_KEY) or "").strip() or None,
'''
    if "PROJECT_PROFILE_KEY) or {}).get(\"story_style\")" in text or "PROJECT_PROFILE_KEY) or {}).get('story_style')" in text:
        print("story_style profile fallback already present")
    else:
        if old_ss not in text:
            print("WARN story_style line not exact; skip profile fallback")
        else:
            text = text.replace(old_ss, new_ss, 1)
            print("strengthened story_style from project_profile")

    # When visual_style/narrator passed as None, prefer vd look over LAST_*
    old_create_call = '''                result, selected_config = create_project_with_initial_raw(
                    parent=self.root,
                    channel=ch,
                    language=lang,
                    narrator=narrator if narrator is not None else LAST_NARRATOR,
                    visual_style=visual_style if visual_style is not None else LAST_VISUAL_STYLE,
'''
    new_create_call = '''                # t235u: 没显式传入时优先用这一条 / profile 上的全场内容，避免落回全局 LAST_*
                if narrator is None or visual_style is None or dialogue_mode is None:
                    _lv, _lt, _ln = _project_look_from_row(vd)
                    if narrator is None:
                        narrator = _ln
                    if visual_style is None:
                        visual_style = _lv
                    if dialogue_mode is None:
                        dialogue_mode = _lt
                result, selected_config = create_project_with_initial_raw(
                    parent=self.root,
                    channel=ch,
                    language=lang,
                    narrator=narrator if narrator is not None else LAST_NARRATOR,
                    visual_style=visual_style if visual_style is not None else LAST_VISUAL_STYLE,
'''
    if "没显式传入时优先用这一条" in text:
        print("create fallback already present")
    else:
        if old_create_call not in text:
            raise SystemExit("create_project_with_initial_raw call not found")
        text = text.replace(old_create_call, new_create_call, 1)
        print("strengthened create fallback to _project_look_from_row")

    raw = text.encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    path.write_bytes(raw)
    print("channel_videos_dialog written")


if __name__ == "__main__":
    patch_wf()
    patch_clone()
