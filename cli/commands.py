"""CLI command registry for ``story_root`` and ``story_scene``."""

from __future__ import annotations

import os

from cli.bridge import send_bridge_command
from cli.screens import (
    SCREEN_STORY_ROOT,
    SCREEN_STORY_SCENE,
    current_screen,
    current_screen_info,
    public_screen_name,
)

STORY_ROOT_BUTTONS: dict[str, str] = {
    "publish": "审阅发布",
    "save": "保存",
    "style": "风格",
    "analyze": "分析",
    "scene": "场景",
    "poem": "诗歌",
    "script": "脚本",
    "folder": "打开成片文件夹",
    "clips": "编辑成片片段",
    "cover_copy": "封面复制",
    "cover": "封面提示",
    "project": "打开项目",
}

STORY_SCENE_FIELDS: dict[str, str] = {
    "lm": "选LM提示",
    "style": "Visual Style",
    "instruction": "导向说明",
    "snippet": "插入片段",
    "content": "scene_content",
    "notebooklm": "NotebookLM",
}

STORY_SCENE_CLICKS: dict[str, str] = {
    "save": "保存",
    "cancel": "取消",
    "generate": "智能生成",
}

# Public CLI name → GUI bridge field (None = handled locally, e.g. profile).
CHOICE_CLIS: dict[str, str | None] = {
    "prompt_choice": "lm",
    "style": "style",
    "snippet": "snippet",
    "notebooklm": "notebooklm",
    "profile": None,
}

# Telegram / Hermes 对外短名（长名仍可用）
_SHORT_CLI: dict[str, str] = {
    "prompt_choice": "lm",
    "style": "sty",
    "snippet": "snp",
    "profile": "prf",
    "gemini": "gem",
    "paste_scene": "pst",
    "notebooklm": "nbp",
    "open_notebooklm": "nbi",
    "whole_story_image": "igp",
    "whole_story_pick": "itc",
    "grok_image": "gr",
    "grok_image_prompt": "gri",
    "scene_choice": "sc",
    "grok_video": "grv",
    "video_concat": "vc",
    "video_publish": "vp",
    "story_pickup": "pick",
    "publish": "pub",
    "analyze": "ana",
    "poem": "poe",
    "script": "scr",
    "cover": "cov",
    "generate": "gen",
    "cancel": "cx",
    "scene": "scn",
    "screen": "win",
}


def short_cli(name: str) -> str:
    return _SHORT_CLI.get((name or "").strip(), name)

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")

_ALIASES: dict[str, str] = {
    "审阅发布": "publish",
    "保存": "save",
    "风格": "style",
    "分析": "analyze",
    "场景": "scene",
    "诗歌": "poem",
    "脚本": "script",
    "打开成片文件夹": "folder",
    "编辑成片片段": "clips",
    "封面复制": "cover_copy",
    "封面提示": "cover",
    "打开项目": "project",
    "analysis": "analyze",
    "poetry": "poem",
    "review": "publish",
    "cover_prompt": "cover",
    "lm": "prompt_choice",
    "pc": "prompt_choice",
    "prompt": "prompt_choice",
    "promptchoice": "prompt_choice",
    "prompts": "prompt_choice",
    "选lm提示": "prompt_choice",
    "选LM提示": "prompt_choice",
    "sty": "style",
    "snp": "snippet",
    "prf": "profile",
    "gem": "gemini",
    "pst": "paste_scene",
    "onb": "open_notebooklm",
    "nbi": "open_notebooklm",
    "gi": "grok_image",
    "gr": "grok_image",
    "sc": "scene_choice",
    "vc": "video_concat",
    "vp": "video_publish",
    "pick": "story_pickup",
    "pub": "publish",
    "ana": "analyze",
    "poe": "poem",
    "scr": "script",
    "cov": "cover",
    "scn": "scene",
    "gen": "generate",
    "cx": "cancel",
    "win": "screen",
    "visual": "style",
    "visual_style": "style",
    "guide": "instruction",
    "导向说明": "instruction",
    "向导说明": "instruction",
    "insert": "snippet",
    "插入片段": "snippet",
    "scene_content": "content",
    "json": "content",
    "智能生成": "generate",
    "取消": "cancel",
    "nb": "notebooklm",
    "nbp": "notebooklm",
    "nblm": "notebooklm",
    "nb_export": "notebooklm",
    "notebook": "notebooklm",
    "notebooklm_open": "open_notebooklm",
    "nb_open": "open_notebooklm",
    "open_nb": "open_notebooklm",
    "nblm_open": "open_notebooklm",
    "whole_story_image": "whole_story_image",
    "whole_story": "whole_story_image",
    "whole_image": "whole_story_image",
    "story_image": "whole_story_image",
    "igp": "whole_story_image",
    "image_grok_paste": "whole_story_image",
    "wsi": "whole_story_image",
    "itc": "whole_story_pick",
    "image_telegram_choosing": "whole_story_pick",
    "wsp": "whole_story_pick",
    "cover_pick": "whole_story_pick",
    "grok_image": "grok_image",
    "gork_image": "grok_image",
    "grok": "grok_image",
    "grok_imagine": "grok_image",
    "grok_image_prompt": "grok_image_prompt",
    "grok_prompt": "grok_image_prompt",
    "gip": "grok_image_prompt",
    "gri": "grok_image_prompt",
    "scenechoice": "scene_choice",
    "scene_index": "scene_choice",
    "sceneidx": "scene_choice",
    "场景选择": "scene_choice",
    "gork_video": "grok_video",
    "grok_clip": "grok_video",
    "gv": "grok_video",
    "grv": "grok_video",
    "grvd": "grok_video",
    "videoconcat": "video_concat",
    "video_join": "video_concat",
    "concat_video": "video_concat",
    "拼接": "video_concat",
    "videopublish": "video_publish",
    "yt_publish": "video_publish",
    "youtube_publish": "video_publish",
    "发布youtube": "video_publish",
    "pick": "story_pickup",
    "story_pickup": "story_pickup",
    "storypickup": "story_pickup",
    "story_pick": "story_pickup",
    "story_pick_up": "story_pickup",
    "pickup": "story_pickup",
    "pick_story": "story_pickup",
}

_TWO_WORD_COMMANDS: dict[tuple[str, str], str] = {
    ("story", "pickup"): "story_pickup",
    ("story", "pick"): "story_pickup",
    ("story", "pick_up"): "story_pickup",
}


def split_command(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if text.startswith("/"):
        text = text[1:].strip()
    if not text:
        return "", ""
    first, _, rest = text.partition(" ")
    if "@" in first:
        first = first.split("@", 1)[0]
    key = first.strip()
    if key.isascii():
        key = key.lower()
    alias = _ALIASES.get(key) or _ALIASES.get(key.lower())
    if alias:
        key = alias
    second, _, rest2 = rest.partition(" ")
    combo = _TWO_WORD_COMMANDS.get((key.lower(), second.lower())) if second else None
    if combo:
        key = combo
        rest = rest2.strip()
    return key, rest.strip()


def _click_story_root(button_name: str) -> tuple[bool, str]:
    from aiagent.win_gui_tasks import (
        click_app_button,
        find_detail_window,
        find_existing_ai_window,
        open_scene_panel,
        set_foreground,
        try_uia_click,
    )

    if button_name == "场景":
        if open_scene_panel():
            return True, "clicked 场景 — SCENE is open"
        return False, "failed to open SCENE (could not switch to GUI / click 场景)"

    hwnd = find_detail_window() or find_existing_ai_window()
    if not hwnd:
        return False, "STORY window not found (open a story first)"
    set_foreground(hwnd)
    if try_uia_click(button_name, hwnd):
        return True, f"clicked {button_name}"
    if click_app_button(button_name):
        return True, f"clicked {button_name} (fallback)"
    return False, f"failed to click {button_name}"


def cmd_screen() -> tuple[bool, str]:
    info = current_screen_info()
    name = public_screen_name(info.get("screen") or "none")
    title = info.get("title") or ""
    extra = f"  title={title}" if title else ""
    return True, f"{name}{extra}"


def cmd_help() -> tuple[bool, str]:
    screen = current_screen()
    lines = [
        f"win={public_screen_name(screen)}  (story=STORY  scene=SCENE  list=LIST  yt=YT)",
        "sync  — 再同步一次",
        "",
        "SCENE:  lm 4  sty  snp  prf  gem  pst  save  nbp  nbi  itc  igp  gr  gri  sc  grv  gvd  vc  vp  nbv  gen  cx  sync",
        "STORY:  scn  save  pub  ana  poe  scr  sty  cov  vc  vp  sync",
        "QUEUE:  pick  /  pick next  /  pick N  /  pick exit",
        "",
        "lm 4 = 4 Step Story   sc 1 = 场景1+video提示词   grv 1 = 出片   gvd = 下载   nbp 1 = 封面单图",
        "长名仍可用（prompt_choice / gemini / paste_scene …）",
        "",
        "bot:  python -m cli bot",
    ]
    return True, "\n".join(lines)


def cmd_status() -> tuple[bool, str]:
    info = current_screen_info()
    lines = [f"{k}={v}" for k, v in info.items()]
    return True, "\n".join(lines)


def cmd_profile(value: str = "") -> tuple[bool, str]:
    """List or select the Gemini Chrome profile."""
    import config

    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if not want:
        return True, _format_chrome_profile_choices(
            "profile 选项（Gemini Chrome；建议选本轮还没用过的号）：",
            "profile",
            "gemini",
        )
    try:
        selected = config.set_gemini_chrome_profile(want)
    except ValueError as exc:
        return False, str(exc) + "\n\n" + _format_chrome_profile_choices(
            "profile 选项：", "profile", "gemini"
        )
    _record_chrome_profile("gemini", selected)
    return True, f"profile ok — {selected['label']}"


def cmd_go() -> tuple[bool, str]:
    """Foreground GUI and open 分镜 if needed. Succeed only when SCENE bridge is live."""
    import time

    import config
    from aiagent.win_gui_tasks import (
        find_detail_window,
        find_panel_window,
        open_scene_panel,
        set_foreground,
    )
    from gui.cli_bridge import is_screen_bound

    def _scene_ready() -> bool:
        hwnd = find_panel_window()
        return bool(
            hwnd
            and is_screen_bound(config.SCREEN_STORY_SCENE)
        )

    panel = find_panel_window()
    if panel and _scene_ready():
        config.set_active_screen(SCREEN_STORY_SCENE)
        set_foreground(panel)
        return True, "already on scene — SCENE is in front (bridge ready)"

    story = find_detail_window()
    if story:
        set_foreground(story)
        time.sleep(0.25)

    ok, bridge_msg = send_bridge_command(
        screen=SCREEN_STORY_ROOT,
        op="click",
        field="scene",
        timeout_s=20.0,
    )
    if not ok and story:
        ok, bridge_msg = send_bridge_command(
            screen=SCREEN_STORY_ROOT,
            op="click",
            field="scene",
            timeout_s=20.0,
        )

    deadline = time.monotonic() + 25.0
    while time.monotonic() < deadline:
        panel = find_panel_window()
        if panel and _scene_ready():
            config.set_active_screen(SCREEN_STORY_SCENE)
            set_foreground(panel)
            return True, "opened scene — SCENE is in front (bridge ready)"
        time.sleep(0.12)

    if not ok:
        if open_scene_panel():
            deadline = time.monotonic() + 12.0
            while time.monotonic() < deadline:
                panel = find_panel_window()
                if panel and _scene_ready():
                    config.set_active_screen(SCREEN_STORY_SCENE)
                    set_foreground(panel)
                    return True, "opened scene via 场景 click — bridge ready"
                time.sleep(0.12)

    panel = find_panel_window()
    if panel:
        set_foreground(panel)
        if _scene_ready():
            config.set_active_screen(SCREEN_STORY_SCENE)
            return True, "SCENE is open (bridge ready)"
        return False, (
            "SCENE 窗口已出现，但 CLI bridge 未绑定（lm/gem 会 timeout）。\n"
            f"bridge: {bridge_msg}\n"
            "请关 SCENE 再发 scn；仍不行就重启 GUI + 听筒。"
        )
    return False, (
        "未能打开 SCENE。请确认 STORY 窗还在，不要把 Cursor 最大化挡住 GUI。\n"
        f"bridge: {bridge_msg}\n"
        "若刚改过代码：关 STORY 再从 LIST 打开一次，然后重发 scn。"
    )


def _foreground_story_scene() -> None:
    try:
        from aiagent.win_gui_tasks import find_panel_window, set_foreground

        hwnd = find_panel_window()
        if hwnd:
            set_foreground(hwnd)
    except Exception:
        pass


def _load_gemini_prompt() -> str:
    from aiagent.browser_tasks import read_windows_clipboard

    try:
        prompt = read_windows_clipboard()
    except Exception:
        prompt = ""
    if len((prompt or "").strip()) >= 400:
        return prompt.strip()

    ok, preview = send_bridge_command(
        screen=SCREEN_STORY_SCENE,
        op="get",
        field="prompt",
        timeout_s=6.0,
    )
    if ok and len((preview or "").strip()) >= 400:
        return preview.strip()
    return (prompt or "").strip()


def cmd_gemini() -> tuple[bool, str]:
    """Clipboard prompt → Gemini chat → wait → copy finished JSON back to clipboard."""
    import json

    from aiagent.browser_tasks import GEMINI_PASTED_MARK, handle_gemini, write_windows_clipboard
    from utility.telegram_session import story_scene_count

    prompt = _load_gemini_prompt()
    expected = story_scene_count(prompt_text=prompt)
    if len(prompt) < 400:
        return False, (
            "Gemini prompt is missing or too short. "
            "On SCENE run `lm` first (e.g. lm 4), then `gem`."
        )
    if expected < 1:
        return False, (
            "还不知道要生成几个场景。先在 SCENE 发 lm（如 lm 4），再 gem。"
        )

    try:
        raw = handle_gemini(prompt)
    except Exception as exc:
        return False, f"gemini failed: {exc}"

    if raw == GEMINI_PASTED_MARK:
        return True, (
            "已粘贴提示词并回车。等生成结束后再发 gemini_copy，把 JSON 拷回剪贴板；"
            "然后发 pst 写入 SCENE。"
        )

    try:
        parsed = json.loads(raw)
        pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
        n = len(parsed) if isinstance(parsed, list) else "?"
        if isinstance(parsed, list) and len(parsed) != expected:
            return False, (
                f"gem 返回 {len(parsed)} 场，但 LM 记录是 {expected} 场。"
                "请检查 SCENE「选LM提示」是否与 gem 一致。"
            )
    except Exception:
        pretty = raw
        n = "?"
    try:
        write_windows_clipboard(pretty)
    except Exception:
        pass
    return True, (
        f"gem ok — {n} scenes on clipboard (LM={expected}).\n"
        "下一步发 pst，写入 SCENE。"
    )


def cmd_gemini_copy() -> tuple[bool, str]:
    """Copy the already-generated Gemini JSON onto the clipboard. Does not re-send."""
    import json

    from aiagent.browser_tasks import copy_existing_gemini_json, write_windows_clipboard

    try:
        raw = copy_existing_gemini_json()
    except Exception as exc:
        return False, f"gemini_copy failed: {exc}"
    try:
        parsed = json.loads(raw)
        pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
        n = len(parsed) if isinstance(parsed, list) else "?"
    except Exception:
        pretty = raw
        n = "?"
    try:
        write_windows_clipboard(pretty)
    except Exception:
        pass
    return True, (
        f"gemini_copy ok — {n} scenes on clipboard.\n"
        "下一步发 pst，写入 SCENE。"
    )


def cmd_paste_scene() -> tuple[bool, str]:
    """Clipboard JSON → 分镜窗 scene_content text field."""
    import json

    from aiagent.browser_tasks import parse_ready_scene_json, read_windows_clipboard
    from utility.telegram_session import story_scene_count

    expected = story_scene_count()
    try:
        text = read_windows_clipboard()
    except Exception as exc:
        return False, f"clipboard empty/unreadable: {exc}"

    parsed = parse_ready_scene_json(text, expected=expected or None)
    if parsed is None:
        try:
            value = json.loads(text)
        except Exception:
            value = None
        if isinstance(value, list) and value:
            if expected >= 1 and len(value) != expected:
                return False, (
                    f"剪贴板有 {len(value)} 场 JSON，但 LM 记录是 {expected} 场。"
                    "请先 lm 选对步数，再 gem / pst。"
                )
            parsed = value
    if parsed is None:
        hint = f"（LM 记录 {expected} 场）" if expected >= 1 else ""
        return False, (
            f"剪贴板里不是有效的 SCENE JSON{hint}。"
            "请先跑 gem（或 gemini_copy），再发 pst。"
        )

    pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
    _foreground_story_scene()
    set_ok, set_msg = send_bridge_command(
        screen=SCREEN_STORY_SCENE,
        op="set",
        field="content",
        value=pretty,
        timeout_s=8.0,
    )
    if set_ok:
        return True, f"pst ok — {len(parsed)} scenes written to scene_content"

    try:
        from aiagent.browser_tasks import write_windows_clipboard
        from aiagent.win_gui_tasks import paste_scene

        write_windows_clipboard(pretty)
        if paste_scene():
            return True, (
                f"pst ok via GUI paste — {len(parsed)} scenes "
                f"(bridge failed: {set_msg})"
            )
    except Exception as exc:
        return False, f"could not paste into scene_content: {set_msg}; fallback: {exc}"
    return False, f"could not paste into scene_content: {set_msg}"


def _format_numbered_choices(title: str, labels: list[str], cmd: str) -> str:
    """One section: ``cmd N: (label)`` per line."""
    head = (title or "").strip().rstrip("：").rstrip(":")
    if head:
        lines = [f"{head}："]
    else:
        lines = [f"{cmd}："]
    for i, label in enumerate(labels, 1):
        lines.append(f"{cmd} {i}: ({label})")
    return "\n".join(lines)


def _format_chrome_profile_choices(title: str, cmd: str, kind: str) -> str:
    from utility.telegram_session import chrome_profile_choice_labels

    labels, suggest = chrome_profile_choice_labels(kind)
    text = _format_numbered_choices(title, labels, cmd)
    if suggest:
        text += f"\n建议：{cmd} {suggest}"
    return text


def _record_chrome_profile(kind: str, selected: dict) -> None:
    try:
        from utility.telegram_session import record_chrome_profile_used

        record_chrome_profile_used(kind, (selected or {}).get("label") or "")
    except Exception:
        pass


def _lm_gui_fallback(want: str) -> tuple[bool, str] | None:
    """Bridge 超时时，直接前台 SCENE 用 UIA 选 LM 下拉。"""
    from aiagent.win_gui_tasks import find_panel_window, select_4step_prompt, set_foreground

    raw = (want or "").strip().translate(_FULLWIDTH_DIGITS)
    if not raw:
        return None
    hwnd = find_panel_window()
    if not hwnd:
        return None
    set_foreground(hwnd)
    if raw in ("4", "4step", "4stepstory") or raw.lower() in (
        "4 step story",
        "4step story",
    ):
        if select_4step_prompt():
            try:
                from utility.telegram_session import save_story_scene_prompt_choice

                save_story_scene_prompt_choice("4 Step Story")
            except Exception:
                pass
            return True, (
                "4 Step Story — 选LM提示下拉已切换（GUI 直连回退）。"
                "请看 SCENE 是否已变；提示词预览应变长。"
            )
    return None


def _choice_cli(public_cmd: str, field: str, value: str) -> tuple[bool, str]:
    """List numbered options, or set by index / name. Used by lm / sty / snp / nb."""
    shown = short_cli(public_cmd)
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if not want:
        ok, msg = send_bridge_command(
            screen=SCREEN_STORY_SCENE,
            op="choices",
            field=field,
            timeout_s=20.0,
        )
        if not ok:
            if public_cmd == "notebooklm":
                import config_prompt

                labels = [
                    row[0]
                    for row in config_prompt.notebooklm_export_flat_choices("Chinese")
                ]
                listed = _format_numbered_choices(
                    f"{shown} 选项（默认菜单；选中仍需 SCENE）：",
                    labels,
                    shown,
                )
                return True, listed + f"\n\n（SCENE 未绑定：{msg}。请打开 SCENE 并重启 GUI 后再 {shown} 1。）"
            return False, (
                f"{shown} 需要 SCENE。先发 scn，再发 {shown}。\n{msg}"
            )
        labels = [ln.strip() for ln in (msg or "").splitlines() if ln.strip()]
        if not labels:
            return False, f"{shown} 没有可选项（SCENE 未绑定？先打开 SCENE 再试）"
        return True, _format_numbered_choices(
            f"{shown} 选项（当前 SCENE）：", labels, shown
        )
    ok, msg = send_bridge_command(
        screen=SCREEN_STORY_SCENE,
        op="set",
        field=field,
        value=want,
        timeout_s=20.0,
    )
    if not ok and public_cmd == "prompt_choice" and want:
        fb = _lm_gui_fallback(want)
        if fb:
            return fb
    if ok:
        if public_cmd == "prompt_choice":
            try:
                from utility.telegram_session import save_story_scene_prompt_choice

                label = (msg or "").split("—", 1)[0].strip() or msg
                save_story_scene_prompt_choice(label)
            except Exception:
                pass
            return True, (
                f"{shown} ok — {msg}\n"
                "请看 SCENE「选LM提示」：必须已变成这一项，"
                "「提示词预览」应变长。没变就是没选上，不要发 gem。"
            )
        return True, f"{shown} ok — {msg}"
    return False, (
        f"{msg}\n"
        f"{shown} {want} 没有作用到 SCENE（下拉不会变、剪贴板也不会换）。"
        "先 scn 打开 SCENE 并等 bridge ready，再重发。"
        "不要发 gem。"
    )


def cmd_open_notebooklm(value: str = "") -> tuple[bool, str]:
    """Pick a Chrome profile, open NotebookLM, generate 3 Portrait/Concise infographics."""
    import config

    shown = short_cli("open_notebooklm")
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if not want:
        return True, _format_chrome_profile_choices(
            f"{shown} 先选 Chrome profile（额度用完就换号；建议选本轮还没用过的）：",
            shown,
            "notebooklm",
        )
    try:
        selected = config.set_gemini_chrome_profile(want)
    except ValueError as exc:
        return False, str(exc) + "\n\n" + _format_chrome_profile_choices(
            f"{shown} 选项：", shown, "notebooklm"
        )
    _record_chrome_profile("notebooklm", selected)

    from aiagent.browser_tasks import handle_notebooklm_covers

    try:
        detail = handle_notebooklm_covers(times=3)
    except Exception as exc:
        return False, (
            f"{shown} failed ({selected['label']}): {exc}\n"
            f"可换一个 profile 再发 {shown} N。"
        )

    from utility.telegram_session import load_whole_story_images

    files = load_whole_story_images()
    if not files:
        return False, (
            f"{shown} 已点 Generate，但没有成功下载封面到 Downloads。\n{detail}"
        )
    itc = short_cli("whole_story_pick")
    igp = short_cli("whole_story_image")
    body = (
        f"{shown} ok — profile={selected['label']}\n{detail}\n"
        f"已自动生成并下载 {len(files)} 张 → whole_story_images.json\n"
        f"（一条 {shown} = Generate×3 + Studio⋮Download×3）\n"
        f"下一步发 {itc}（Telegram 发图选封面），选定后再发 {igp} 贴进 Grok。"
    )
    return True, body


def cmd_whole_story_pick(value: str = "") -> tuple[bool, str]:
    """Send nbi cover JPGs to Telegram for pick, or record choice 1/2/3 (no paste)."""
    from utility.telegram_cli import notify_whole_story_covers_for_pick
    from utility.telegram_session import (
        load_whole_story_image_record,
        load_whole_story_images,
        mark_whole_story_telegram_sent,
        record_whole_story_pick,
    )

    shown = short_cli("whole_story_pick")
    igp = short_cli("whole_story_image")
    files = load_whole_story_images()
    if not files:
        return False, (
            "还没有封面图。请先 nbi（Generate ×3 并下载到 Downloads）。"
        )
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if not want:
        tg_lines = notify_whole_story_covers_for_pick(files)
        mark_whole_story_telegram_sent()
        extra = "\n".join(tg_lines) if tg_lines else ""
        listed = _format_numbered_choices(
            f"已记录 {len(files)} 张封面（Downloads）：",
            [os.path.basename(p) for p in files],
            shown,
        )
        msg = (
            f"{shown} ok — 已发 Telegram 请选封面。\n{listed}\n"
            f"Telegram 回复 1…{len(files)}，或 CLI 发 {shown} N。\n"
            f"选定后再发 {igp} 贴进所有 Grok 标签。"
        )
        if extra:
            msg += f"\n{extra}"
        return True, msg
    if not want.isdigit():
        return False, f"unknown {shown}: {value}（无参=发 Telegram；或 {shown} 1…{len(files)}）"
    idx = int(want)
    try:
        picked = record_whole_story_pick(idx)
    except ValueError as exc:
        return False, str(exc)
    rec = load_whole_story_image_record()
    igp = short_cli("whole_story_image")
    return True, (
        f"{shown} ok — 已选 #{idx} {os.path.basename(picked['path'])}\n"
        f"记录：selected_path={rec.get('selected_path')}\n"
        f"下一步发 {igp}（无参）把该图贴进所有 Grok Imagine 标签。"
    )


def _paste_whole_story_image_to_grok(picked: str, picked_idx: int) -> tuple[bool, str]:
    from aiagent.browser_tasks import copy_image_file_to_clipboard

    shown = short_cli("whole_story_image")
    try:
        copy_image_file_to_clipboard(picked)
    except Exception as exc:
        return False, f"拷贝图片到剪贴板失败：{exc}"
    try:
        from aiagent.browser_tasks import paste_image_into_all_grok_tabs

        extra = paste_image_into_all_grok_tabs()
    except Exception as exc:
        return True, (
            f"{shown} ok — #{picked_idx} {os.path.basename(picked)} → clipboard\n"
            f"未能贴进 Grok（{exc}）。请先 gr 开标签，再重发 {shown}。"
        )
    return True, (
        f"{shown} ok — #{picked_idx} {os.path.basename(picked)} → clipboard; {extra}"
    )


def cmd_whole_story_image(value: str = "") -> tuple[bool, str]:
    """Paste the picked whole-story cover into every Grok Imagine tab."""
    from utility.telegram_session import (
        load_whole_story_image_record,
        load_whole_story_images,
        record_whole_story_pick,
        selected_whole_story_image_path,
    )

    shown = short_cli("whole_story_image")
    itc = short_cli("whole_story_pick")
    rec = load_whole_story_image_record()
    files = load_whole_story_images()
    if not files:
        return False, (
            f"还没有 whole story image。请先 nbi，再 {itc} 选封面。"
        )
    labels = [os.path.basename(p) for p in files]
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)

    if not want:
        selected = int(rec.get("selected") or 0)
        picked = selected_whole_story_image_path()
        if picked and selected >= 1:
            return _paste_whole_story_image_to_grok(picked, selected)
        listed = _format_numbered_choices(
            f"{shown} 共 {len(files)} 张；尚未选定封面：",
            labels,
            shown,
        )
        listed += (
            f"\n先 {itc}（Telegram 选图）或 {itc} 1…{len(files)}，"
            f"再发 {shown} 贴进 Grok。\n"
            f"或一步：{shown} N 直接选第 N 张并贴进 Grok。"
        )
        if rec.get("pending_pick"):
            listed += f"\n（等待选封面：Telegram 回复 1…{len(files)}）"
        return True, listed

    picked = ""
    picked_idx = 0
    if want.isdigit():
        idx = int(want)
        if 1 <= idx <= len(files):
            picked = files[idx - 1]
            picked_idx = idx
    if not picked:
        low = want.lower()
        for i, (path, name) in enumerate(zip(files, labels), 1):
            if name.lower() == low or low in name.lower():
                picked = path
                picked_idx = i
                break
    if not picked:
        return False, (
            f"unknown {shown}: {value}\n\n"
            + _format_numbered_choices(f"{shown} 选项：", labels, shown)
        )
    try:
        record_whole_story_pick(picked_idx)
    except ValueError as exc:
        return False, str(exc)
    return _paste_whole_story_image_to_grok(picked, picked_idx)


def cmd_grok_image(value: str = "") -> tuple[bool, str]:
    """Pick a Chrome profile, open N grok.com/imagine tabs from story_scene_prompt_choice."""
    import config
    from utility.telegram_session import load_story_scene_prompt_choice

    shown = short_cli("grok_image")
    choice = load_story_scene_prompt_choice()
    label = (choice.get("label") or "").strip()
    tabs = int(choice.get("tabs") or 0)
    if not label or tabs < 1:
        return False, (
            "还没有记下 LM。先在 SCENE 发 lm 4。"
        )

    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if not want:
        return True, _format_chrome_profile_choices(
            f"{shown} 先选 Chrome profile（将开 {tabs} 个 Imagine 标签，LM={label}；建议选本轮还没用过的）：",
            shown,
            "grok",
        )
    try:
        selected = config.set_gemini_chrome_profile(want)
    except ValueError as exc:
        return False, str(exc) + "\n\n" + _format_chrome_profile_choices(
            f"{shown} 选项：", shown, "grok"
        )
    _record_chrome_profile("grok", selected)

    from aiagent.browser_tasks import handle_grok_imagine_tabs

    try:
        detail = handle_grok_imagine_tabs()
    except Exception as exc:
        return False, f"{shown} failed ({selected['label']}): {exc}"
    return True, (
        f"{shown} ok — profile={selected['label']}  LM={label}  tabs={tabs}\n{detail}"
    )


def cmd_grok_image_prompt(value: str = "") -> tuple[bool, str]:
    """List Direct Video / step-image prompts, or copy one (apply to Grok tab 1–N)."""
    import config_prompt
    from utility.telegram_session import load_story_scene_prompt_choice

    shown = short_cli("grok_image_prompt")
    rows = [
        (str(lbl).strip(), str(tpl or ""))
        for lbl, tpl in (config_prompt.DIRECT_VIDEO_PROMPT_CHOICES or [])
        if str(lbl or "").strip()
    ]
    if not rows:
        return False, "DIRECT_VIDEO_PROMPT_CHOICES 为空"

    rec = load_story_scene_prompt_choice()
    n = int(rec.get("tabs") or rec.get("scenes") or 0)
    lm_label = (rec.get("label") or "").strip()
    image_rows = rows[:4]
    video_rows = rows[4:]
    gr = short_cli("grok_image")
    if n < 1:
        active_rows = rows
        lm_note = f"还没记下 LM；{shown} 1…4 按四场景列出。先发 lm 再 {gr}。"
    else:
        active_rows = image_rows[:n] + video_rows
        lm_note = f"LM={lm_label} → 场景图 {shown} 1…{n}（共 {n} 个 Grok 标签）"

    labels = [lbl for lbl, _ in active_rows]
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if not want:
        title = f"{shown} 选项（Image to Detail / Image to Video）："
        if lm_note:
            title += f"\n{lm_note}"
        return True, _format_numbered_choices(title, labels, shown)

    picked_tpl = ""
    picked_label = ""
    picked_idx = 0
    if want.isdigit():
        idx = int(want)
        if 1 <= idx <= len(active_rows):
            picked_label, picked_tpl = active_rows[idx - 1]
            picked_idx = idx
    if not picked_tpl:
        low = want.lower()
        for i, (lbl, tpl) in enumerate(active_rows, 1):
            if lbl.lower() == low or low in lbl.lower():
                picked_label, picked_tpl = lbl, tpl
                picked_idx = i
                break
    if not picked_tpl:
        return False, (
            f"unknown {shown}: {value}\n\n"
            + _format_numbered_choices(f"{shown} 选项：", labels, shown)
            + (f"\n{lm_note}" if lm_note else "")
        )

    from aiagent.browser_tasks import write_windows_clipboard

    write_windows_clipboard(picked_tpl)
    apply_note = f"copied {picked_label} to clipboard"
    is_scene_image = picked_idx >= 1 and picked_idx <= min(n, len(image_rows)) if n >= 1 else (
        picked_idx >= 1 and picked_idx <= len(image_rows)
    )
    if is_scene_image:
        tab_index = picked_idx
        if n >= 1 and tab_index > n:
            return False, (
                f"{shown} {picked_idx} 超出 LM 记录的 {n} 个场景（{lm_label or '?'}）。"
                f"只发 {shown} 1…{n}。"
            )
        try:
            from aiagent.browser_tasks import apply_grok_image_prompt_to_tab

            apply_note = apply_grok_image_prompt_to_tab(tab_index, picked_tpl)
        except Exception as exc:
            apply_note = (
                f"copied {picked_label} to clipboard; "
                f"未能应用到 Grok 标签 {tab_index}：{exc}"
            )
            return True, f"{shown} ok — {apply_note}"
    return True, f"{shown} ok — {apply_note}"


def _format_scene_choice_list(labels: list[str], current: str, lm_note: str) -> str:
    """Values match the GUI button (all / 1 / 2), not 1-based list where 1=All."""
    lines = ["sc："]
    for lab in labels:
        key = "all" if lab.lower() == "all" else lab
        if key == "all":
            hint = "所有场景（只改按钮，不拷 video 提示词）"
        else:
            hint = f"场景 {lab} + Video/纯画面 → 剪贴板（等同点场景按钮再选 NotebookLM）"
        lines.append(f"sc {key}: ({hint})")
    if lm_note:
        lines.append(lm_note)
    if current:
        lines.append(f"当前：{current}")
    return "\n".join(lines)


def cmd_scene_choice(value: str = "") -> tuple[bool, str]:
    """Set 分镜底栏场景索引；选 1/2/3… 时同时拷 Video/纯画面 到剪贴板（等同场景按钮 + NotebookLM）。"""
    from utility.telegram_session import load_story_scene_prompt_choice

    rec = load_story_scene_prompt_choice()
    recorded_n = int(rec.get("tabs") or rec.get("scenes") or 0)
    lm_label = (rec.get("label") or "").strip()
    lm_note = ""
    if lm_label:
        lm_note = f"记下的 LM：{lm_label} → {recorded_n} 个场景"
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)

    ok_ch, msg_ch = send_bridge_command(
        screen=SCREEN_STORY_SCENE,
        op="choices",
        field="scene_choice",
    )
    labels: list[str] = []
    if ok_ch:
        labels = [ln.strip() for ln in (msg_ch or "").splitlines() if ln.strip()]
    if not labels:
        n = recorded_n or 1
        labels = ["All"] + [str(i) for i in range(1, n + 1)]

    ok_cur, msg_cur = send_bridge_command(
        screen=SCREEN_STORY_SCENE,
        op="get",
        field="scene_choice",
    )
    current = ""
    if ok_cur:
        current = (msg_cur or "").splitlines()[0].strip() if msg_cur else ""

    if not want:
        listed = _format_scene_choice_list(labels, current, lm_note)
        if not ok_ch:
            listed += (
                f"\n\n（SCENE 未绑定：{msg_ch}。选中仍需打开 SCENE 并重启 GUI 后再 sc 1。）"
            )
        return True, listed

    ok, msg = send_bridge_command(
        screen=SCREEN_STORY_SCENE,
        op="set",
        field="scene_choice",
        value=want,
    )
    if ok:
        return True, f"sc ok — {msg}"
    return False, (
        f"sc 需要 SCENE。先发 scn，再发 sc {want}。\n{msg}"
    )


def cmd_grok_video(value: str = "") -> tuple[bool, str]:
    """Generate on tab i, or ``download`` all scene clips into Windows Downloads."""
    from utility.telegram_session import load_story_scene_prompt_choice

    shown = short_cli("grok_video")
    rec = load_story_scene_prompt_choice()
    n = int(rec.get("tabs") or rec.get("scenes") or 0)
    lm_label = (rec.get("label") or "").strip()
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if n < 1:
        return False, (
            "还没有记下 LM，不知道有几个场景。\n"
            "先在 SCENE 发 lm 4，再 grv。"
        )
    if not want:
        labels = [f"场景 {i} → Grok Imagine 标签 {i}" for i in range(1, n + 1)]
        extra = f"（LM={lm_label} → {n} 个）" if lm_label else f"（{n} 个场景）"
        listed = _format_numbered_choices(
            f"{shown} 选项{extra}；剪贴板须已是该场景提示词",
            labels,
            shown,
        )
        return True, listed + "\ngvd: (全部下载到 Downloads)"
    low = want.lower().replace(" ", "")
    if low in ("download", "dl", "下载"):
        try:
            from aiagent.browser_tasks import download_grok_scene_videos

            files = download_grok_scene_videos()
        except Exception as exc:
            return False, f"gvd failed: {exc}"
        if not files:
            return False, "gvd 没有记下任何 mp4"
        lines = [
            f"gvd ok — {len(files)} clip(s) → Windows Downloads"
        ]
        for item in files:
            lines.append(
                f"  scene {item.get('scene')}: {os.path.basename(item.get('path') or '')}"
            )
        return True, "\n".join(lines)
    if not want.isdigit():
        return False, (
            f"unknown {shown}: {value}（用 1…{n} 生成，或 gvd）\n\n"
            + _format_numbered_choices(
                f"{shown} 选项：",
                [f"场景 {i}" for i in range(1, n + 1)],
                shown,
            )
        )
    idx = int(want)
    if idx < 1 or idx > n:
        return False, f"没有第 {idx} 个场景（当前记录 {n} 个，LM={lm_label or '?'}）"
    try:
        from aiagent.browser_tasks import apply_grok_video_prompt_to_tab

        note = apply_grok_video_prompt_to_tab(idx)
    except Exception as exc:
        return False, f"{shown} failed: {exc}"
    return True, f"{shown} ok — {note}"


def cmd_video_concat(value: str = "") -> tuple[bool, str]:
    """末帧延长 + 水印 + 按场景顺序拼接，写入 publish/gen_video（不做手工裁剪）。"""
    _ = value
    from utility.telegram_session import load_grok_scene_videos

    clips = load_grok_scene_videos()
    if not clips:
        return False, (
            "还没有记录 grok 场景 video。\n"
            "等各标签出完片后先发 gvd。"
        )
    preview = "\n".join(
        f"  {item.get('scene')}: {os.path.basename(item.get('path') or '')}"
        for item in clips
    )
    try:
        from gui.story_video_concat import concat_recorded_scene_clips

        dest = concat_recorded_scene_clips(clips)
    except Exception as exc:
        return False, f"vc failed: {exc}\n已记录的 clip：\n{preview}"
    return True, (
        f"vc ok — {len(clips)} clip(s) → {dest}\n{preview}"
    )


def cmd_video_publish(value: str = "") -> tuple[bool, str]:
    """List YouTube description sources, or upload immediately (no schedule dialog)."""
    from gui.story_video_publish import (
        default_publish_source_key,
        list_publish_description_choices,
        publish_current_story,
        resolve_current_publish_context,
    )

    try:
        ctx = resolve_current_publish_context()
        rows = list_publish_description_choices(ctx)
    except Exception as exc:
        return False, f"vp 还不能发：{exc}"
    if not rows:
        return False, "当前故事没有任何可用的描述素材（分析 / 场景 / voiceover 都空）。"

    labels = [label for _, label in rows]
    default_key = default_publish_source_key(ctx)
    default_label = next((lbl for key, lbl in rows if key == default_key), labels[0])
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if not want:
        listed = _format_numbered_choices(
            "vp 选项（YouTube 描述来源；立即 unlisted）",
            labels,
            "vp",
        )
        return True, listed + f"\nvp default: (默认 — {default_label})"

    source_key = ""
    low = want.lower().replace(" ", "")
    if low in ("default", "d", "默认"):
        source_key = default_key
    elif want.isdigit():
        idx = int(want)
        if 1 <= idx <= len(rows):
            source_key = rows[idx - 1][0]
    if not source_key:
        low = want.lower()
        for key, label in rows:
            if low == key.lower() or low in label.lower():
                source_key = key
                break
    if not source_key:
        return False, (
            f"unknown vp: {value}\n\n"
            + _format_numbered_choices(
                "vp 选项：", labels, "vp"
            )
        )

    picked_label = next((lbl for key, lbl in rows if key == source_key), source_key)
    try:
        result = publish_current_story(source_key=source_key)
    except Exception as exc:
        return False, f"vp failed（{picked_label}）：{exc}"

    lines = [
        f"vp ok — {picked_label}",
        f"title: {result.get('title') or ''}",
        f"mp4: {result.get('mp4_path') or ''}",
    ]
    if result.get("watch_url"):
        lines.append(result["watch_url"])
    elif result.get("video_id"):
        lines.append(f"YouTube id: {result['video_id']}")
    if result.get("archive"):
        lines.append(str(result["archive"]))
    tg = result.get("telegram") or []
    if tg:
        lines.append("Telegram: " + " | ".join(str(x) for x in tg))
    try:
        from aiagent.video_choice_queue import first_pending_story_index, mark_active_item_done

        done = mark_active_item_done()
        if done:
            title = (done.get("title") or done.get("choice_id") or "").strip()
            lines.append(f"本条已标为已完成：{title}")
        suggest = first_pending_story_index()
        lines.append("")
        if suggest:
            lines.append(
                f"队列里还有未处理的故事。发 pick 看全部；"
                f"建议下一步 pick {suggest}。"
            )
            lines.append("要停就发 pick exit。换下一条前先关掉当前 STORY/SCENE。")
        else:
            lines.append("没有未处理的了，但都可以再选。发 pick 看 1/2/3…，不要发 pick next。")
    except Exception as exc:
        lines.append(f"队列状态未更新：{exc}")
    return True, "\n".join(lines)


def _format_story_pickup_list() -> str:
    from aiagent.video_choice_queue import describe_queue_stories

    info = describe_queue_stories()
    rows = info.get("rows") or []
    if not rows:
        return (
            "pick：队列是空的。请先在 GUI 热门视频列表里导出选择队列。"
        )
    lines = ["pick："]
    for row in rows:
        mark = " ←当前" if row.get("current") else ""
        title = (row.get("title") or "")[:80]
        status = row.get("status_zh") or ""
        lines.append(f"pick {row['index']}: ([{status}] {title}{mark})")
    lines.append(
        f"共 {info.get('total')} 条；"
        f"未处理 {info.get('pending')}；"
        f"已完成 {info.get('done')}。"
    )
    suggest = info.get("suggest")
    if suggest:
        lines.append(f"建议：pick {suggest} 或 pick next")
    else:
        lines.append("无未处理；直接 pick 1/2/… 重做。停：pick exit")
    return "\n".join(lines)


def cmd_story_pickup(value: str = "") -> tuple[bool, str]:
    """列出队列全部故事，或按序号 / next / exit 取用一条。"""
    from cli.gui_session import is_manual_gui_session

    if is_manual_gui_session():
        return False, (
            "pick 已关掉：当前 AIComposer 是 GUI_pm 手工启动的，故事已在界面里选好。\n"
            "听筒会跟着你进的窗口同步，并告诉你这一屏能发哪些 CLI。\n"
            "要用队列选故事，请先关掉这个 GUI，再发 pick。"
        )

    from aiagent.video_choice_queue import (
        first_pending_story_index,
        list_queue_items,
        queue_item_at,
    )

    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    low = want.lower().replace(" ", "")
    if low in ("exit", "finish", "stop", "quit", "结束", "停"):
        return True, (
            "pick exit — 本轮结束，不再打开下一条。"
            "之后要再做，重新发 pick。"
        )
    if not want:
        return True, _format_story_pickup_list()

    item = None
    if low in ("next", "n", "下一个", "下一条"):
        suggest = first_pending_story_index()
        if not suggest:
            return True, (
                "没有未处理的了，不要发 pick next。下面都可以再选：\n\n"
                + _format_story_pickup_list()
            )
        try:
            item = queue_item_at(suggest)
        except ValueError as exc:
            return False, str(exc) + "\n\n" + _format_story_pickup_list()
    elif want.isdigit():
        try:
            item = queue_item_at(int(want))
        except ValueError as exc:
            return False, str(exc) + "\n\n" + _format_story_pickup_list()
    else:
        cid = want
        found = None
        for it in list_queue_items():
            if (it.get("choice_id") or "").strip() == cid:
                found = it
                break
            title = (it.get("title") or "").strip()
            if title and (cid.lower() == title.lower() or cid.lower() in title.lower()):
                found = it
                break
        if not found:
            return False, f"unknown pick: {value}\n\n" + _format_story_pickup_list()
        item = found

    from cli.ensure_gui import ensure_gui_for_queue_item

    ok, msg = ensure_gui_for_queue_item(item)
    extra = "\n本条做完后发 pick 再看处理情况；下一个未处理的可以继续，已完成的也可以重做。要停发 pick exit。"
    return ok, msg + extra


def _scene_field(field: str, value: str) -> tuple[bool, str]:
    if field in ("lm", "style", "snippet", "notebooklm"):
        public = "prompt_choice" if field == "lm" else field
        return _choice_cli(public, field, value)
    if value:
        return send_bridge_command(
            screen=SCREEN_STORY_SCENE,
            op="set",
            field=field,
            value=value,
        )
    return send_bridge_command(screen=SCREEN_STORY_SCENE, op="get", field=field)


def dispatch(raw: str) -> tuple[bool, str]:
    cmd, value = split_command(raw)
    if not cmd:
        return False, "empty command"

    if cmd in ("help", "commands", "start"):
        return cmd_help()
    if cmd == "screen":
        return cmd_screen()
    if cmd in ("sync", "where", "here"):
        from cli.mode import get_mode
        from utility.telegram_session import TelegramCliSession

        return True, TelegramCliSession(mode=get_mode()).announce_sync()
    if cmd == "status":
        return cmd_status()
    if cmd in ("story_pickup",):
        return cmd_story_pickup(value)
    if cmd in ("go", "flow", "scn", "scene"):
        return cmd_go()
    if cmd == "story":
        return True, "story 是窗名（STORY），不是命令。打开 SCENE 发 scn。看当前窗发 win。"
    if cmd in ("gvd", "grvd"):
        return cmd_grok_video("download")
    if cmd == "nbv":
        return _choice_cli("notebooklm", "notebooklm", "纯画面")
    if cmd in ("next", "queue_next"):
        from cli.gui_session import is_manual_gui_session

        if is_manual_gui_session():
            return False, (
                "next 已关掉：当前是 GUI_pm 手工会话，不会从队列再开一条。\n"
                "听筒会跟着你的窗口同步。要用队列请先关掉这个 GUI，再发 pick。"
            )
        from cli.ensure_gui import ensure_gui_from_queue

        return ensure_gui_from_queue()
    if cmd in CHOICE_CLIS:
        field = CHOICE_CLIS[cmd]
        if field is None:
            return cmd_profile(value)
        return _choice_cli(cmd, field, value)
    if cmd == "gemini":
        return cmd_gemini()
    if cmd in ("gemini_copy", "copyjson", "fetch"):
        return cmd_gemini_copy()
    if cmd in ("paste_scene", "scene_json", "paste_json"):
        return cmd_paste_scene()
    if cmd == "open_notebooklm":
        return cmd_open_notebooklm(value)
    if cmd == "whole_story_pick":
        return cmd_whole_story_pick(value)
    if cmd == "whole_story_image":
        return cmd_whole_story_image(value)
    if cmd == "grok_image":
        return cmd_grok_image(value)
    if cmd == "grok_image_prompt":
        return cmd_grok_image_prompt(value)
    if cmd == "scene_choice":
        return cmd_scene_choice(value)
    if cmd == "grok_video":
        return cmd_grok_video(value)
    if cmd == "video_concat":
        return cmd_video_concat(value)
    if cmd == "video_publish":
        return cmd_video_publish(value)

    screen = current_screen()

    if screen == SCREEN_STORY_SCENE:
        if cmd in STORY_SCENE_FIELDS:
            return _scene_field(cmd, value)
        if cmd in STORY_SCENE_CLICKS:
            return send_bridge_command(
                screen=SCREEN_STORY_SCENE,
                op="click",
                field=cmd,
            )
        if cmd == "scene":
            return True, "already on scene"

    if cmd in STORY_ROOT_BUTTONS:
        if screen not in (SCREEN_STORY_ROOT, "none"):
            return False, f"{cmd} is a STORY button; current win={public_screen_name(screen)}"
        result = _click_story_root(STORY_ROOT_BUTTONS[cmd])
        if result[0] and cmd == "scene":
            import config

            config.set_active_screen(SCREEN_STORY_SCENE)
        return result

    return False, f"unknown command: {raw.strip()}\n\n" + cmd_help()[1]
