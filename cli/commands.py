"""CLI command registry for ``story_root`` and ``story_scene``."""

from __future__ import annotations

import os
import time

from cli.bridge import bridge_screen_bound, send_bridge_command
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
    "scene_save": "scnsave",
    "notebooklm": "nbp",
    "open_notebooklm": "nbi",
    "notebooklm_ready": "nbif",
    "whole_story_image": "igp",
    "whole_story_pick": "itc",
    "grok_image": "grv",
    "grok_image_prompt": "gri",
    "grok_download": "gvd",
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


def _wait_screen_ready(screen: str, timeout_s: float = 25.0) -> bool:
    """Wait until the GUI reports a screen finished building."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if bridge_screen_bound(screen, timeout_s=1.0):
            return True
        time.sleep(0.2)
    return False


def _lm_bridge_retry(want: str, *, timeout_s: float = 15.0) -> tuple[bool, str] | None:
    """Retry bridge ``lm`` set while SCENE is still finishing its async UI build."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if bridge_screen_bound(SCREEN_STORY_SCENE, timeout_s=1.0):
            ok, msg = send_bridge_command(
                screen=SCREEN_STORY_SCENE,
                op="set",
                field="lm",
                value=want,
                timeout_s=6.0,
            )
            if ok:
                return True, msg
        time.sleep(0.25)
    return None

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
    "scnsave": "scene_save",
    "ssave": "scene_save",
    "s_save": "scene_save",
    "pst": "scene_save",
    "paste_scene": "scene_save",
    "onb": "open_notebooklm",
    "nbi": "open_notebooklm",
    "nbif": "notebooklm_ready",
    "nbf": "notebooklm_ready",
    "infographic_ready": "notebooklm_ready",
    "notebooklm_ready": "notebooklm_ready",
    "gi": "grok_image",
    "grv": "grok_image",
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
    "gui": "gui_health",
    "health": "gui_health",
    "diag": "gui_health",
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
    "gvd": "grok_download",
    "grvd": "grok_download",
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


def _click_story_root(field: str) -> tuple[bool, str]:
    """Click a STORY toolbar control via GUI bridge (no mouse simulation)."""
    import time

    from cli.win_gui_tasks import find_detail_window, set_foreground

    hwnd = find_detail_window()
    if not hwnd:
        return False, "STORY 窗口未找到（请先从 LIST 打开一条故事）"
    set_foreground(hwnd)
    time.sleep(0.15)

    ok, msg = send_bridge_command(
        screen=SCREEN_STORY_ROOT,
        op="click",
        field=field,
        timeout_s=30.0,
    )
    if not ok:
        label = STORY_ROOT_BUTTONS.get(field, field)
        return False, f"bridge 点击「{label}」失败: {msg}"
    return True, msg or f"clicked {field}"


def cmd_screen() -> tuple[bool, str]:
    info = current_screen_info()
    name = public_screen_name(info.get("screen") or "none")
    title = info.get("title") or ""
    extra = f"  title={title}" if title else ""
    return True, f"{name}{extra}"


def cmd_gui_health() -> tuple[bool, str]:
    """Report whether the GUI is running, responsive, and which screens are bound."""
    from cli.bridge import gui_heartbeat

    beat = gui_heartbeat()
    if beat is None:
        return False, (
            "GUI：没在跑（没有心跳）。\n"
            "请先启动 GUI，再发命令。"
        )

    lines = []
    if beat.get("pump_alive"):
        lines.append(f"GUI：正常（Tk 主线程 {beat.get('pump_age_s')}s 前刚跑过）")
    else:
        lines.append(
            f"GUI：卡住 — Tk 主线程已 {beat.get('pump_age_s')}s 没处理 bridge。\n"
            "多半有窗口在做同步长任务。等一会儿或重启 GUI。"
        )
    ready = beat.get("ready") or []
    building = beat.get("building") or []
    lines.append("已就绪的屏：" + (", ".join(ready) if ready else "（无）"))
    if building:
        lines.append("正在加载：" + ", ".join(building))
    inbox = beat.get("inbox") or 0
    if inbox:
        lines.append(f"待处理 bridge 请求：{inbox}")
    return bool(beat.get("pump_alive")), "\n".join(lines)


def cmd_help() -> tuple[bool, str]:
    screen = current_screen()
    lines = [
        f"win={public_screen_name(screen)}  (story=STORY  scene=SCENE  list=LIST  yt=YT)",
        "sync  — 再同步一次",
        "",
        "SCENE:  lm 4  sty  snp  prf  gem  scnsave  nbp  nbi  nbif  itc  grv  gvd  vc  vp  nbv  gen  cx  sync",
        "STORY:  scn  save  pub  ana  poe  scr  sty  cov  vc  vp  sync",
        "QUEUE:  pick  /  pick next  /  pick N  /  pick exit",
        "",
        "lm 4 = 4 Step Story   grv 1 [1…8] = 开标签+出图+出片+下载(全自动)   nbv = video变体   gvd = 补下载   nbp 1 = 封面单图",
        "长名仍可用（prompt_choice / gemini / scene_save …）",
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
    """Foreground GUI and open SCENE via bridge (calls do_review_scene, no mouse)."""
    import time

    import config
    from cli.win_gui_tasks import find_panel_window, flash_window, set_foreground
    from cli.bridge import gui_heartbeat

    def _bring_scene_front() -> bool:
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            hwnd = find_panel_window()
            if hwnd:
                set_foreground(hwnd)
                flash_window(hwnd)
                return True
            time.sleep(0.12)
        return False

    def _scene_ready() -> bool:
        return bridge_screen_bound(config.SCREEN_STORY_SCENE, timeout_s=1.5)

    def _wait_scene_ready(deadline: float) -> bool:
        while time.monotonic() < deadline:
            hwnd = find_panel_window()
            if hwnd:
                set_foreground(hwnd)
            if _scene_ready():
                return True
            time.sleep(0.2)
        return False

    if _scene_ready():
        config.set_active_screen(SCREEN_STORY_SCENE)
        _bring_scene_front()
        return True, "already on scene — SCENE is in front (bridge ready)"

    if not bridge_screen_bound(SCREEN_STORY_ROOT, timeout_s=2.0):
        return False, (
            "STORY 屏未绑定 CLI bridge。请先从 LIST 打开一条故事，再发 scn。\n"
            "若刚改过代码：关 STORY 再从 LIST 打开一次。"
        )

    # Do not win32-foreground STORY here — it shares the GUI process and can
    # stall Tk while the bridge click is waiting for the pump.
    ok, bridge_msg = send_bridge_command(
        screen=SCREEN_STORY_ROOT,
        op="click",
        field="scene",
        timeout_s=15.0,
    )

    if not ok:
        beat = gui_heartbeat() or {}
        building = beat.get("building") or []
        if config.SCREEN_STORY_SCENE in building and _wait_scene_ready(
            time.monotonic() + 25.0
        ):
            config.set_active_screen(SCREEN_STORY_SCENE)
            _bring_scene_front()
            return True, "opened scene — SCENE is in front (bridge ready)"
        return False, (
            "未能打开 SCENE。\n"
            f"bridge: {bridge_msg}\n"
            "若刚改过代码：关 STORY 再从 LIST 打开一次，然后重发 scn。"
        )

    if _wait_scene_ready(time.monotonic() + 30.0):
        config.set_active_screen(SCREEN_STORY_SCENE)
        _bring_scene_front()
        return True, "opened scene — SCENE is in front (bridge ready)"

    if find_panel_window():
        _bring_scene_front()
        return False, (
            "SCENE 窗口已出现，但编辑器还没加载完（30 秒内未就绪）。\n"
            f"bridge: {bridge_msg}\n"
            "稍等几秒直接发 lm；一直不行就关 SCENE 再发 scn。"
        )
    return False, (
        "未能打开 SCENE。\n"
        f"bridge: {bridge_msg}\n"
        "若刚改过代码：关 STORY 再从 LIST 打开一次，然后重发 scn。"
    )


def _foreground_story_scene() -> None:
    try:
        from cli.win_gui_tasks import find_panel_window, set_foreground

        hwnd = find_panel_window()
        if hwnd:
            set_foreground(hwnd)
    except Exception:
        pass


def _load_gemini_prompt() -> str:
    from cli.browser_tasks import read_windows_clipboard

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

    from cli.browser_tasks import GEMINI_PASTED_MARK, handle_gemini, write_windows_clipboard
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
            "然后发 scnsave 写入 SCENE 并保存到频道列表。"
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
        "下一步发 scnsave，写入 SCENE 并保存到频道列表。"
    )


def cmd_gemini_copy() -> tuple[bool, str]:
    """Copy the already-generated Gemini JSON onto the clipboard. Does not re-send."""
    import json

    from cli.browser_tasks import copy_existing_gemini_json, write_windows_clipboard

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
        "下一步发 scnsave，写入 SCENE 并保存到频道列表。"
    )


def _scene_json_from_clipboard() -> tuple[list | None, str, str]:
    """Return ``(parsed, pretty_json, error_message)`` from Windows clipboard."""
    import json

    from cli.browser_tasks import parse_ready_scene_json, read_windows_clipboard
    from utility.telegram_session import story_scene_count

    expected = story_scene_count()
    try:
        text = read_windows_clipboard()
    except Exception as exc:
        return None, "", f"clipboard empty/unreadable: {exc}"

    parsed = parse_ready_scene_json(text, expected=expected or None)
    if parsed is None:
        try:
            value = json.loads(text)
        except Exception:
            value = None
        if isinstance(value, list) and value:
            if expected >= 1 and len(value) != expected:
                return (
                    None,
                    "",
                    (
                        f"剪贴板有 {len(value)} 场 JSON，但 LM 记录是 {expected} 场。"
                        "请先 lm 选对步数，再 gem / scnsave。"
                    ),
                )
            parsed = value
    if parsed is None:
        hint = f"（LM 记录 {expected} 场）" if expected >= 1 else ""
        return (
            None,
            "",
            (
                f"剪贴板里不是有效的 SCENE JSON{hint}。"
                "请先跑 gem（或 gemini_copy），再发 scnsave。"
            ),
        )
    pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
    return parsed, pretty, ""


def cmd_scene_save() -> tuple[bool, str]:
    """Clipboard JSON → scene_content 文本框 → 写入 video_detail / 频道列表（不关窗）。"""
    parsed, pretty, err = _scene_json_from_clipboard()
    if err:
        return False, err

    if not _wait_screen_ready(SCREEN_STORY_SCENE, timeout_s=25.0):
        return False, "SCENE 窗还没就绪。先发 scn 打开场景编辑窗。"

    _foreground_story_scene()
    set_ok, set_msg = send_bridge_command(
        screen=SCREEN_STORY_SCENE,
        op="set",
        field="content",
        value=pretty,
        timeout_s=8.0,
    )
    if not set_ok:
        return False, f"scnsave failed setting scene_content: {set_msg}"

    persist_ok, persist_msg = send_bridge_command(
        screen=SCREEN_STORY_SCENE,
        op="persist",
        field="content",
        timeout_s=12.0,
    )
    if not persist_ok:
        return False, f"scnsave persist failed: {persist_msg}"

    return True, (
        f"scnsave ok — {len(parsed)} scenes saved to video_detail "
        f"(SCENE window kept open; clipboard unchanged)"
    )


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
    """Bridge-only retry — never click the screen (coords lie, UIA needs COM)."""
    return _lm_bridge_retry(want)


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
    if field in ("lm", "style", "snippet", "notebooklm"):
        if not _wait_screen_ready(SCREEN_STORY_SCENE, timeout_s=25.0):
            return False, (
                f"{shown} 需要 SCENE 已就绪。先发 scn，等窗口出来后再发 {shown} {want}。"
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
            ok, msg = fb
    if ok:
        if public_cmd == "prompt_choice":
            try:
                from utility.telegram_session import save_story_scene_prompt_choice

                label = (msg or "").split("—", 1)[0].strip() or msg
                save_story_scene_prompt_choice(label)
            except Exception:
                pass
            got_ok, got = send_bridge_command(
                screen=SCREEN_STORY_SCENE,
                op="get",
                field="lm",
                timeout_s=4.0,
            )
            if got_ok:
                got_val = (got or "").split("\n", 1)[0].strip()
                want_label = ""
                if want.isdigit():
                    ch_ok, ch_msg = send_bridge_command(
                        screen=SCREEN_STORY_SCENE,
                        op="choices",
                        field="lm",
                        timeout_s=4.0,
                    )
                    if ch_ok:
                        labels = [
                            ln.strip() for ln in (ch_msg or "").splitlines() if ln.strip()
                        ]
                        idx = int(want)
                        if 1 <= idx <= len(labels):
                            want_label = labels[idx - 1]
                if want_label and want_label not in got_val:
                    return False, (
                        f"lm set 回了 ok，但 SCENE 下拉仍是 {got_val!r}，"
                        f"不是 {want_label!r}。请重发 lm {want}。"
                    )
            _foreground_story_scene()
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
    """Pick a Chrome profile, open NotebookLM, click Generate ×3, return immediately."""
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

    from cli.browser_tasks import handle_notebooklm_covers

    try:
        detail = handle_notebooklm_covers(times=3)
    except Exception as exc:
        return False, (
            f"{shown} failed ({selected['label']}): {exc}\n"
            f"可换一个 profile 再发 {shown} N。"
        )

    try:
        from utility.telegram_session import save_notebooklm_last_profile

        save_notebooklm_last_profile(profile=selected.get("label") or "", index=int(want) if want.isdigit() else 0)
    except Exception:
        pass

    nbif = short_cli("notebooklm_ready")
    itc = short_cli("whole_story_pick")
    body = (
        f"{shown} ok — profile={selected['label']}\n{detail}\n"
        f"已点 Generate ×3，不等待结束、不拷图。\n"
        f"请过几分钟发 {nbif} 查询三张新 infographic 是否 ready；"
        f"ready 后再发 {itc} 拷图并发 Telegram 选一张。"
    )
    return True, body


def cmd_notebooklm_ready(value: str = "") -> tuple[bool, str]:
    """Query Studio: three new infographics ready, or still generating."""
    del value
    from cli.browser_tasks import check_notebooklm_infographic_status
    from utility.telegram_session import load_whole_story_image_record

    shown = short_cli("notebooklm_ready")
    itc = short_cli("whole_story_pick")
    rec = load_whole_story_image_record()
    expected = int(rec.get("expected") or rec.get("generate_clicked") or 3) or 3
    try:
        st = check_notebooklm_infographic_status(expected=expected)
    except Exception as exc:
        return False, f"{shown} failed: {exc}"
    if not st.get("ok"):
        return False, f"{shown} — {st.get('error') or '查询失败'}"
    gen_n = int(st.get("generating_count") or 0)
    gen_items = list(st.get("generating_items") or [])
    gen_detail = ""
    if gen_items:
        gen_detail = "\n仍在生成：\n" + "\n".join(
            f"  · {g.get('title', '')}" for g in gen_items[:5]
        )
    if st.get("ready"):
        total = int(st.get("total_items") or 0)
        return True, (
            f"{shown} — 三个新的 infographic 已经 ready。\n"
            f"Studio 右侧列表无 Generating 项"
            f"{f'（共 {total} 个 artifact）' if total else ''}。\n"
            f"下一步发 {itc}：打开这三张、下载到 Windows Downloads，再 Telegram 发给你选一张。"
        )
    if st.get("uncertain"):
        return True, (
            f"{shown} — 还不能判定 ready。\n"
            f"{st.get('error') or '没读到 Studio 列表。'}\n"
            "如果你仍然看见第一项是 Generating infographic，就还没好，请稍后再发 nbif。"
        )
    return True, (
        f"{shown} — 还没有 ready，仍在生成中。\n"
        f"Studio 右侧列表里还有 Generating 项"
        f"{f'（{gen_n} 条）' if gen_n else ''}。"
        f"{gen_detail}\n"
        f"请稍后再发 {shown}。"
    )


def _itc_do_cover_pick(idx: int, shown: str, igp: str) -> tuple[bool, str]:
    from utility.telegram_session import (
        load_whole_story_image_record,
        load_whole_story_images,
        record_whole_story_pick,
    )

    files = load_whole_story_images()
    if not files:
        return False, f"还没有封面图。请先 {shown} 拷图，再 {shown} {idx}。"
    if idx < 1 or idx > len(files):
        return False, (
            f"封面序号要在 1…{len(files)}。"
            f"Telegram 直接回复数字，或发 {shown} 1…{len(files)}。"
        )
    try:
        picked = record_whole_story_pick(idx)
    except ValueError as exc:
        return False, str(exc)
    rec = load_whole_story_image_record()
    path = picked.get("path") or rec.get("selected_path") or ""
    cover_note = ""
    if path:
        cov_ok, cov_msg = install_story_cover_from_image(path)
        if not cov_ok:
            return False, (
                f"{shown} 已选 #{idx}，但写入 STORY 封面失败：{cov_msg}"
            )
        cover_note = f"\n{cov_msg}"
    clip_note = ""
    if path:
        try:
            from cli.browser_tasks import copy_image_file_to_clipboard

            copy_image_file_to_clipboard(path)
            clip_note = "\n已把所选图拷到剪贴板。"
        except Exception as exc:
            clip_note = f"\n拷到剪贴板失败：{exc}"
    return True, (
        f"{shown} ok — 已选 #{idx} {os.path.basename(path)}\n"
        f"记录：selected_path={rec.get('selected_path')}"
        f"{cover_note}"
        f"{clip_note}\n"
        f"下一步发 {igp}（无参）把该图贴进所有 Grok Imagine 标签。"
    )


def install_story_cover_from_image(image_path: str) -> tuple[bool, str]:
    """``itc N`` / Telegram 选封面：无弹窗写入 gen_video/<id>.webp（与拖放共用底层）。"""
    path = (image_path or "").strip()
    if not path or not os.path.isfile(path):
        return False, f"封面文件不存在: {path or image_path}"

    from cli.bridge import bridge_screen_bound, send_bridge_command
    from cli.screens import SCREEN_STORY_ROOT

    if bridge_screen_bound(SCREEN_STORY_ROOT, timeout_s=3.0):
        return send_bridge_command(
            screen=SCREEN_STORY_ROOT,
            op="set",
            field="cover_image",
            value=path,
            timeout_s=120.0,
        )

    from cli.video_choice_queue import (
        apply_queue_item_yt_prefs,
        current_taken_queue_item,
        resolve_video_detail_from_queue_item,
    )
    from gui.downloader import save_cover_image_as_gen_video_webp

    item = current_taken_queue_item()
    vd = resolve_video_detail_from_queue_item(item) if item else None
    if not vd:
        return False, (
            "STORY 窗未打开，且队列无当前条。"
            "请先 pick 打开故事，或保持 STORY 窗在前台。"
        )
    prefs = apply_queue_item_yt_prefs(item) if item else {}
    ch = ""
    if item:
        ch = (item.get("channel_id") or prefs.get("channel") or "").strip()
    lang = (prefs.get("language") or "zh") if prefs else "zh"
    pid = str(vd.get("id") or vd.get("pid") or "yt_img")
    ok, dest, err = save_cover_image_as_gen_video_webp(
        path,
        vd,
        channel=ch,
        pid=pid,
        lang=lang,
    )
    if ok:
        return True, f"封面已保存: {dest}"
    return False, err or "保存封面失败"


def _itc_parse_cover_index(want: str) -> int | None:
    """``itc 2`` / ``itc pick 2`` → cover index; ``None`` if not a pick form."""
    text = (want or "").strip().translate(_FULLWIDTH_DIGITS)
    if not text:
        return None
    first, _, rest = text.partition(" ")
    first_l = first.lower()
    if first_l in ("pick", "sel", "choice", "选"):
        tail = (rest or "").strip()
        return int(tail) if tail.isdigit() else None
    if first.isdigit() and not (rest or "").strip():
        return int(first)
    return None


def _itc_send_covers(files: list[str], shown: str, igp: str) -> tuple[bool, str]:
    from utility.telegram_cli import notify_whole_story_covers_for_pick
    from utility.telegram_session import mark_whole_story_telegram_sent

    if not files:
        return False, f"{shown} 没有拷到 infographic 图。"
    tg_lines = notify_whole_story_covers_for_pick(files)
    mark_whole_story_telegram_sent()
    extra = "\n".join(tg_lines) if tg_lines else ""
    listed = _format_numbered_choices(
        f"已拷 {len(files)} 张封面到 working：",
        [os.path.basename(p) for p in files],
        "封面",
    )
    msg = (
        f"{shown} ok — 已发 Telegram 请选封面。\n{listed}\n"
        f"Telegram 直接回复 1…{len(files)}，或发 {shown} 1…{len(files)} 选定。\n"
        f"（{shown} N 在等选图时表示选第 N 张；窗口已关、还没图时用 nbi N 再 {shown}。）\n"
        f"选定后会记下并拷到剪贴板；再发 {igp} 贴进 Grok。"
    )
    if extra:
        msg += f"\n{extra}"
    return True, msg


def cmd_whole_story_pick(value: str = "") -> tuple[bool, str]:
    """Copy top 3 infographic images, or record which cover the owner chose.

    ``itc`` — use the already-open NotebookLM window, send 3 covers to Telegram.
    ``itc N`` — pick cover #N (when images are waiting, or ``1<=N<=`` file count).
    ``itc N`` — if no covers yet, reopen NotebookLM with Chrome profile N (legacy).
    """
    import config
    from utility.telegram_session import (
        load_whole_story_image_record,
        load_whole_story_images,
        whole_story_pick_pending,
    )

    shown = short_cli("whole_story_pick")
    igp = short_cli("whole_story_image")
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    pick_idx = _itc_parse_cover_index(want)
    files = load_whole_story_images()

    if pick_idx is not None:
        if files and 1 <= pick_idx <= len(files):
            return _itc_do_cover_pick(pick_idx, shown, igp)
        if whole_story_pick_pending():
            return False, (
                f"请选 1…{len(files) or 3}。"
                f"Telegram 直接回复数字，或 {shown} 1…{len(files) or 3}。"
            )
        if not want.isdigit() and pick_idx is not None:
            return False, (
                f"还没有封面图。请先 {shown}，再 {shown} {pick_idx}。"
            )

    rec = load_whole_story_image_record()
    expected = int(rec.get("expected") or rec.get("generate_clicked") or 3) or 3

    if not want:
        from cli.browser_tasks import (
            capture_notebooklm_infographics,
            notebooklm_window_open,
        )

        if not notebooklm_window_open():
            return True, _format_chrome_profile_choices(
                f"{shown} 找不到已打开的 NotebookLM。"
                f"先发 nbi N 打开 notebook，再 {shown}；"
                f"或 legacy：{shown} N 用 Chrome 号 N 重开再拷图",
                shown,
                "notebooklm",
            )
        try:
            files = capture_notebooklm_infographics(times=expected)
        except Exception as exc:
            return False, f"{shown} failed: {exc}"
        return _itc_send_covers(files, shown, igp)

    if want.isdigit():
        try:
            selected = config.set_gemini_chrome_profile(want)
        except ValueError as exc:
            return False, str(exc) + "\n\n" + _format_chrome_profile_choices(
                f"{shown} 选项（Chrome 号，重新打开 notebook 再拷图）：",
                shown,
                "notebooklm",
            )
        _record_chrome_profile("notebooklm", selected)
        from cli.browser_tasks import reopen_notebooklm_and_capture

        try:
            files = reopen_notebooklm_and_capture(times=expected)
        except Exception as exc:
            return False, (
                f"{shown} failed ({selected['label']}): {exc}\n"
                f"可换一个 profile 再发 {shown} N。"
            )
        ok, msg = _itc_send_covers(files, shown, igp)
        if ok:
            msg = f"{shown} ok — 已用 {selected['label']} 重新打开 notebook 并拷图。\n" + msg
        return ok, msg

    return False, (
        f"unknown {shown}: {value}\n"
        f"无参 = 当前已打开的 NotebookLM 拷最上边三张并发 Telegram；\n"
        f"{shown} N = 选第 N 张封面（Telegram 也可直接回 1/2/3）；\n"
        f"还没图时 {shown} N 仍可用 Chrome 号 N 重开 notebook（建议 nbi N 再 {shown}）。"
    )


def _paste_whole_story_image_to_grok(picked: str, picked_idx: int) -> tuple[bool, str]:
    from cli.browser_tasks import copy_image_file_to_clipboard

    shown = short_cli("whole_story_image")
    try:
        copy_image_file_to_clipboard(picked)
    except Exception as exc:
        return False, f"拷贝图片到剪贴板失败：{exc}"
    try:
        from cli.browser_tasks import paste_image_into_all_grok_tabs

        extra = paste_image_into_all_grok_tabs()
    except Exception as exc:
        return True, (
            f"{shown} ok — #{picked_idx} {os.path.basename(picked)} → clipboard\n"
            f"未能贴进 Grok（{exc}）。请先 grv 开标签，再重发 {shown}。"
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
    nbif = short_cli("notebooklm_ready")
    rec = load_whole_story_image_record()
    files = load_whole_story_images()
    if not files:
        return False, (
            f"还没有 whole story image。请先 {nbif} 确认 ready，再 {itc} 拷图选封面。"
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
            f"\n先 Telegram 回复 1…{len(files)}，或发 {itc} N，"
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
    """Pick Chrome profile + optional video prompt variant (1…8), open Grok Imagine tabs."""
    import config
    import config_prompt
    from utility.telegram_session import (
        load_grok_scene_video_nb_index,
        load_story_scene_prompt_choice,
        save_grok_scene_video_nb_index,
    )

    shown = short_cli("grok_image")
    choice = load_story_scene_prompt_choice()
    label = (choice.get("label") or "").strip()
    tabs = int(choice.get("tabs") or 0)
    if not label or tabs < 1:
        return False, (
            "还没有记下 LM。先在 SCENE 发 lm 4。"
        )

    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if want.lower() in ("prep", "prepare", "paste", "ready"):
        from cli.browser_tasks import prepare_open_grok_imagine_tabs

        try:
            detail = prepare_open_grok_imagine_tabs(paste_image=True)
        except Exception as exc:
            return False, f"{shown} prep failed: {exc}"
        return True, f"{shown} prep ok — {detail}"
    parts = [p for p in want.split() if p]
    video_nb_index: int | None = None
    profile_want = ""
    if len(parts) >= 2 and parts[-1].isdigit():
        vi = int(parts[-1])
        n_var = len(config_prompt.GROK_SCENE_VIDEO_NB_VARIANTS) or 8
        if 1 <= vi <= n_var:
            video_nb_index = vi
            profile_want = parts[0]
    elif parts:
        profile_want = parts[0]
    if not profile_want:
        cur_v = load_grok_scene_video_nb_index()
        return True, (
            _format_chrome_profile_choices(
                f"{shown} 先选 Chrome profile（将开 {tabs} 个 Imagine 标签，LM={label}）：",
                shown,
                "grok",
            )
            + "\n\n"
            + config_prompt.format_grok_scene_video_nb_choices()
            + f"\n当前 video 变体：{cur_v}（"
            + config_prompt.grok_scene_video_nb_choice_label(cur_v)
            + "）\n"
            f"例：{shown} 1 {cur_v}  或  {shown} 1 5"
        )
    try:
        selected = config.set_gemini_chrome_profile(profile_want)
    except ValueError as exc:
        return False, str(exc) + "\n\n" + _format_chrome_profile_choices(
            f"{shown} 选项：", shown, "grok"
        )
    _record_chrome_profile("grok", selected)

    if video_nb_index is not None:
        save_grok_scene_video_nb_index(video_nb_index)
    v_idx = video_nb_index if video_nb_index is not None else load_grok_scene_video_nb_index()
    v_label = config_prompt.grok_scene_video_nb_choice_label(v_idx)

    from cli.browser_tasks import handle_grok_imagine_tabs

    try:
        detail = handle_grok_imagine_tabs(video_nb_index=v_idx)
    except Exception as exc:
        return False, f"{shown} failed ({selected['label']}): {exc}"
    return True, (
        f"{shown} ok — profile={selected['label']}  LM={label}  tabs={tabs}  "
        f"video_nb={v_idx} ({v_label})\n{detail}"
    )


def cmd_grok_image_prompt(value: str = "") -> tuple[bool, str]:
    """Deprecated: scene image prompts are applied by ``grv`` automatically."""
    import config_prompt
    from utility.telegram_session import load_story_scene_prompt_choice

    shown = short_cli("grok_image_prompt")
    grv = short_cli("grok_image")
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
    if n < 1:
        active_rows = rows
        lm_note = f"还没记下 LM；先发 lm 再 {grv}。"
    else:
        active_rows = image_rows[:n] + video_rows
        lm_note = f"LM={lm_label} → 场景图已并入 {grv}（{grv} 1 自动贴封面 + Image 1…{n} 提示词）"

    labels = [lbl for lbl, _ in active_rows]
    want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
    if want:
        return False, (
            f"{shown} 已合并到 {grv}：请发 {grv} 1，会自动在每个 Grok 标签贴封面图"
            f"+ 对应场景提示词（Image to Detail-Single-Step-Image 1…{n or 'N'}）。"
            f"\nvideo 提示词由 {grv} 自动按 nbv/grv 变体粘贴并生成。"
        )
    title = f"{shown} 已合并到 {grv}（下列仅供参考；场景图提示词由 {grv} 自动粘贴）："
    if lm_note:
        title += f"\n{lm_note}"
    return True, _format_numbered_choices(title, labels, shown)


def cmd_grok_download(value: str = "") -> tuple[bool, str]:
    """Download all Grok scene mp4 clips into Windows Downloads."""
    _ = value
    try:
        from cli.browser_tasks import download_grok_scene_videos

        files = download_grok_scene_videos()
    except Exception as exc:
        return False, f"gvd failed: {exc}"
    if not files:
        return False, "gvd 没有记下任何 mp4"
    lines = [f"gvd ok — {len(files)} clip(s) → Windows Downloads"]
    for item in files:
        lines.append(
            f"  scene {item.get('scene')}: {os.path.basename(item.get('path') or '')}"
        )
    return True, "\n".join(lines)


def cmd_video_concat(value: str = "") -> tuple[bool, str]:
    """末帧延长 + 水印 + 按场景顺序拼接，写入 publish/gen_video（不做手工裁剪）。"""
    _ = value
    from utility.telegram_session import load_grok_scene_videos

    clips = load_grok_scene_videos()
    if not clips:
        return False, (
            "还没有记录 grok 场景 video。\n"
            "先 grv（已含每场景下载），或各标签出片后 gvd。"
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
        from cli.video_choice_queue import first_pending_story_index, mark_active_item_done

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
    from cli.video_choice_queue import describe_queue_stories

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

    from cli.video_choice_queue import (
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
    if cmd == "gui_health":
        return cmd_gui_health()
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
        return cmd_grok_download(value)
    if cmd == "nbv":
        import config_prompt
        from utility.telegram_session import (
            load_grok_scene_video_nb_index,
            save_grok_scene_video_nb_index,
        )

        want = (value or "").strip().translate(_FULLWIDTH_DIGITS)
        if not want:
            cur = load_grok_scene_video_nb_index()
            return True, (
                config_prompt.format_grok_scene_video_nb_choices()
                + f"\n当前：{cur}（{config_prompt.grok_scene_video_nb_choice_label(cur)}）"
                + f"\n用法：nbv 3  切换变体；grv 1 3  一次指定 profile+变体"
            )
        if want.isdigit():
            idx = int(want)
            try:
                save_grok_scene_video_nb_index(idx)
            except ValueError as exc:
                return False, str(exc)
            return True, (
                f"nbv ok — video 提示词变体 {idx}（"
                f"{config_prompt.grok_scene_video_nb_choice_label(idx)}）"
            )
        return _choice_cli("notebooklm", "notebooklm", want)
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
    if cmd in ("scene_save", "scnsave", "ssave", "s_save", "paste_scene", "pst"):
        return cmd_scene_save()
    if cmd == "open_notebooklm":
        return cmd_open_notebooklm(value)
    if cmd == "notebooklm_ready":
        return cmd_notebooklm_ready(value)
    if cmd == "whole_story_pick":
        return cmd_whole_story_pick(value)
    if cmd == "whole_story_image":
        return cmd_whole_story_image(value)
    if cmd == "grok_image":
        return cmd_grok_image(value)
    if cmd == "grok_image_prompt":
        return cmd_grok_image_prompt(value)
    if cmd == "grok_download":
        return cmd_grok_download(value)
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
        result = _click_story_root(cmd)
        if result[0] and cmd == "scene":
            import config

            config.set_active_screen(SCREEN_STORY_SCENE)
        return result

    return False, f"unknown command: {raw.strip()}\n\n" + cmd_help()[1]
