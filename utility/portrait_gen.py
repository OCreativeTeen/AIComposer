"""t280: 生成肖像（STORY 人物预览窗 和 魔法工作流人物预览窗 共用）。

流程：
1. ``collect_descriptions``：从所有场景里收集这一位的描述（actor 里的括号说明 + 场景文字里提到名字的句子）。
2. ``build_prompt_request``：给 Strata 的系统 / 用户提示词，请它写一段英文文生图提示词，
   必须写进 地域 / 时代 / 舞台（``setting``）和画面风格；肖像规则：头肩像、一个人、素背景、不要任何文字。
3. ``write_portrait_prompt``：调 Strata（``LLMApi.generate_text``；失败时它自己开手动窗口）；
   回答空 → 用本地模板。最后一律补上肖像规则（``PORTRAIT_RULES``），不靠模型记得。
4. ``request_image``：打开 LLM 手动窗口（``cli_kind="text_image"``）：显示提示词；「自动 CLI」开着时
   自动用 Grok Imagine 文生图，成功就关窗；失败 / 不自动时人可以把图贴进「返回的图」再按确定。
5. ``save_portrait``：存成这一位的肖像（``apply_portrait_choice``：原来的先改名 .bak 备份）。

纯函数 + 可注入的 ``llm``，测试里用假的，不碰网络和 Chrome。
"""
from __future__ import annotations

import os
import re
import tempfile

from utility import actor_format

MAX_DESCRIPTIONS = 12
MAX_DESC_CHARS = 200
SCENE_TEXT_FIELDS = ("visual", "content", "story_content", "caption")

PORTRAIT_RULES = (
    "Portrait rules (must follow): a head-and-shoulders portrait of this ONE person only, facing the viewer, "
    "clear face, plain simple background in the same art style. No other people, no scenery, no props. "
    "No text of any kind anywhere in the picture: no caption, no name, no label, no title, no watermark, "
    "no signature, no border or frame."
)

SYSTEM_PROMPT = (
    "You write ONE English text-to-image prompt for a character portrait.\n"
    "Output only the prompt itself: no quotes, no headings, no explanations, no lists. At most 120 words.\n"
    "The prompt must describe:\n"
    "- the person's gender, age band and ethnicity exactly as given;\n"
    "- face, hair, clothing and accessories that fit the person's descriptions AND the story setting "
    "(region, era and story stage given below) — clothing and hair must belong to that place and time;\n"
    "- the art style given below (say it plainly in the prompt);\n"
    "- a head-and-shoulders portrait, one person only, plain simple background.\n"
    "Never ask for any text in the picture: no caption, no name, no label, no watermark. "
    "Do not write the person's name as something to draw."
)


def _clean(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def person_key(body: str) -> str:
    """同一个人：性别/年龄段/族裔/名字（去掉括号，大小写不分）。"""
    from utility.cast_consolidate import clean_body

    return clean_body(str(body or "")).strip().lower()


def person_name(body: str) -> str:
    from utility.cast_merge import split_id

    return (split_id(actor_format.split_label(str(body or ""))[1]).get("name") or "").strip()


def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[。！？!?；;.\n])", str(text or "")) if s.strip()]


def collect_descriptions(scenes, body: str) -> list:
    """所有场景里这一位的描述：``[{"scene": n, "note": 括号说明, "text": 提到名字的句子}]``（场景 1 起）。"""
    key = person_key(body)
    name = person_name(body)
    out, seen = [], set()
    if not key:
        return out
    for n, sc in enumerate(scenes or [], 1):
        if not isinstance(sc, dict):
            continue
        note, present = "", False
        for seg in actor_format.segments(sc.get("actor")):
            role, ent = actor_format.split_label(seg)
            if role == "host":
                continue
            if person_key(ent) != key:
                continue
            present = True
            m = re.search(r"[（(]([^（()）]*)[）)]\s*$", ent)
            note = (m.group(1).strip() if m else "") or note
        texts = []
        if name and len(name) >= 1:
            for field in SCENE_TEXT_FIELDS:
                for s in _sentences(sc.get(field)):
                    if name in s and s not in texts:
                        texts.append(s)
        if not present and not texts:
            continue
        text = _clean(" ".join(texts))[:MAX_DESC_CHARS]
        sig = (note, text)
        if sig in seen or not (note or text):
            continue
        seen.add(sig)
        out.append({"scene": n, "note": note, "text": text})
        if len(out) >= MAX_DESCRIPTIONS:
            break
    return out


def style_line(style: str) -> str:
    style = (style or "").strip()
    try:
        import config_prompt

        realistic = config_prompt.is_realistic_style(style) if style else True
    except Exception:  # noqa: BLE001
        realistic = not style
    if realistic:
        return ("Art style: photorealistic portrait photograph, real skin and real materials, natural light; "
                "not illustration, not cartoon, not anime, not painting.")
    return f"Art style: {style}. Use only this one art style."


def ratio_line(ratio) -> str:
    """t281: 画面比例：``"1080x1920"`` / ``(1080, 1920)`` / ``"9:16"`` → 一句英文；认不出返回 ""。"""
    w = h = 0
    if isinstance(ratio, (tuple, list)) and len(ratio) == 2:
        w, h = ratio
    else:
        m = re.match(r"\s*(\d+)\s*[x×:*]\s*(\d+)\s*$", str(ratio or ""))
        if m:
            w, h = m.group(1), m.group(2)
    try:
        w, h = int(w), int(h)
    except (TypeError, ValueError):
        return ""
    if w <= 0 or h <= 0:
        return ""
    if w == h:
        shape = "1:1 square"
    elif w > h:
        shape = "16:9 landscape"
    else:
        shape = "9:16 portrait"
    size = f" ({w}x{h})" if max(w, h) > 32 else ""
    return (f"Aspect ratio: {shape}{size}. Compose the head-and-shoulders portrait for this frame shape, "
            "the person centered, plain background filling the rest.")


def build_prompt_request(body: str, descriptions, *, setting: str = "", style: str = "", ratio="") -> tuple:
    """给 Strata 的 (system, user)。"""
    look = person_key(body)
    lines = [f"Person (gender/age band/ethnicity/name): {actor_format.split_label(str(body or ''))[1].strip()}"]
    if look:
        bits = look.split("/")
        lines.append("Gender: " + (bits[0] if bits else "") + "; age band: " + (bits[1] if len(bits) > 1 else "")
                     + "; ethnicity: " + (bits[2] if len(bits) > 2 else ""))
    if descriptions:
        lines.append("Descriptions of this person in the story scenes:")
        for d in descriptions:
            bit = "; ".join(x for x in (d.get("note"), d.get("text")) if x)
            lines.append(f"- scene {d.get('scene')}: {bit}")
    else:
        lines.append("Descriptions of this person in the story scenes: (none)")
    lines.append("Story setting (region / era / story stage): " + (
        _clean(setting) or "(not set — infer a plausible region and era from the descriptions; if unclear keep it neutral)"))
    lines.append(style_line(style))
    if ratio_line(ratio):
        lines.append(ratio_line(ratio))
    return SYSTEM_PROMPT, "\n".join(lines)


def fallback_prompt(body: str, descriptions, *, setting: str = "", style: str = "") -> str:
    """Strata 没给回答时的本地模板。"""
    bits = (person_key(body).split("/") + ["", "", ""])[:3]
    who = " ".join(b for b in (bits[1], bits[2], bits[0]) if b) or "person"
    notes = "; ".join(d.get("note") for d in (descriptions or []) if d.get("note"))
    parts = [f"Head-and-shoulders portrait of a {who}."]
    if notes:
        parts.append(f"Look: {notes}.")
    if _clean(setting):
        parts.append(_clean(setting) + " Clothing and hair fit this place and time.")
    return " ".join(parts)


def finalize_prompt(text: str, *, setting: str = "", style: str = "", ratio="") -> str:
    """模型写的提示词 + 必须的 风格 / 地域时代舞台 / 肖像规则（缺什么补什么，规则一律附上）。"""
    text = _clean(text).strip('"“”')
    out = [text]
    if _clean(setting) and _clean(setting) not in text:
        out.append("Setting: " + _clean(setting))
    out.append(style_line(style))
    out.append(ratio_line(ratio))
    out.append(PORTRAIT_RULES)
    return "\n".join(x for x in out if x)


def write_portrait_prompt(body: str, scenes, *, setting: str = "", style: str = "", ratio="", llm=None) -> dict:
    """返回 {"prompt", "source": "strata"/"template", "descriptions", "system", "user"}。"""
    descriptions = collect_descriptions(scenes, body)
    system, user = build_prompt_request(body, descriptions, setting=setting, style=style, ratio=ratio)
    reply, source = "", "template"
    if llm is None:
        from utility.llm_api import LLMApi, STRATA

        llm = LLMApi(STRATA)
    try:
        reply = llm.generate_text(system, user) or ""
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 肖像提示词：Strata 失败 {exc}")
        reply = ""
    if not isinstance(reply, str):
        reply = ""
    if reply.strip():
        source = "strata"
    else:
        reply = fallback_prompt(body, descriptions, setting=setting, style=style)
    return {"prompt": finalize_prompt(reply, setting=setting, style=style, ratio=ratio), "source": source,
            "descriptions": descriptions, "system": system, "user": user}


def request_image(prompt: str, *, llm=None, account: str = ""):
    """LLM 手动窗口（文生图）：自动 CLI 用 Grok Imagine 出图；不行就人贴图。返回 PIL Image 或 None。"""
    if llm is None:
        from utility.llm_api import LLMApi

        llm = LLMApi()
    from utility.llm_api import TEXT_IMAGE_CLI_KIND

    extra = {"image_backend": "grok"}
    if account:
        extra["chrome_account"] = account
    resp = llm.show_manual_window(prompt, "", cli_kind=TEXT_IMAGE_CLI_KIND, extra=extra)
    return resp if resp is not None and hasattr(resp, "save") else None


def save_portrait(img, dest: str) -> str:
    """存成这一位的肖像 dest（.png）；原来的先改名 .bak 备份。返回写好的路径。"""
    if img is None or not dest:
        return ""
    from utility.portrait_candidates import apply_portrait_choice

    handle, tmp = tempfile.mkstemp(prefix="portrait_gen_", suffix=".png")
    os.close(handle)
    try:
        pic = img if getattr(img, "mode", "RGB") in ("RGB", "RGBA") else img.convert("RGBA")
        pic.save(tmp, "PNG")
        return apply_portrait_choice(tmp, dest)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def generate_portrait(body: str, scenes, dest: str, *, setting: str = "", style: str = "", ratio="",
                      llm=None, image_llm=None, status=None) -> dict:
    """整个流程。返回 {"ok", "path", "prompt", "source", "error"}。在后台线程里跑也可以（手动窗口会转到主线程）。"""
    def say(msg):
        if callable(status):
            try:
                status(msg)
            except Exception:  # noqa: BLE001
                pass

    out = {"ok": False, "path": "", "prompt": "", "source": "", "error": ""}
    if not person_key(body) or not dest:
        out["error"] = "先填好这一位的 性别/年龄/族裔/名字。"
        return out
    say("Strata 写肖像提示词 …")
    req = write_portrait_prompt(body, scenes, setting=setting, style=style, ratio=ratio, llm=llm)
    out["prompt"], out["source"] = req["prompt"], req["source"]
    say("Grok 生成肖像 …")
    try:
        img = request_image(req["prompt"], llm=image_llm)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"生成图片失败：{exc}"
        return out
    if img is None:
        out["error"] = "没有拿到图片（取消了，或没有贴图）。"
        return out
    try:
        out["path"] = save_portrait(img, dest)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"保存肖像失败：{exc}"
        return out
    out["ok"] = bool(out["path"])
    return out


def run_in_background(widget, job, on_done, poll_ms: int = 150) -> None:
    """后台线程跑 ``job()``，完了在主线程调 ``on_done(result)``（主线程定时看队列，后台线程不碰 Tk）。"""
    import queue
    import threading

    q: queue.Queue = queue.Queue()

    def work():
        try:
            q.put(job())
        except Exception as exc:  # noqa: BLE001
            q.put({"ok": False, "path": "", "error": str(exc)})

    def poll():
        try:
            res = q.get_nowait()
        except queue.Empty:
            try:
                widget.after(poll_ms, poll)
            except Exception:  # noqa: BLE001
                pass
            return
        on_done(res)

    threading.Thread(target=work, name="portrait-gen", daemon=True).start()
    widget.after(poll_ms, poll)
