# -*- coding: utf-8 -*-
"""t238u: MiniMax H3 no-subtitle rule x3 + polish preserve + negative merge."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"D:\AIComposer")

HELPERS = '''
# t238u: MiniMax H3 — 禁止字幕/台词上屏（正词写三遍；负面词有则并入）
H3_NO_SUBTITLE_RULE = "NEVER add any subtitles, captions or on-screen text of the dialogue!"
H3_NO_SUBTITLE_NEGATIVE = (
    "subtitles, captions, on-screen text, dialogue text on screen, burned-in subtitles, "
    "subtitle bar, caption overlay, karaoke lyrics, lower-third text"
)


def count_h3_no_subtitle_rules(prompt: str) -> int:
    return (prompt or "").count(H3_NO_SUBTITLE_RULE)


def with_h3_no_subtitle_negative(negative: str | None) -> str | None:
    """有负面提示时并入字幕相关禁词；没有负面则原样返回 None。"""
    if negative is None:
        return None
    base = str(negative).strip()
    if not base:
        return H3_NO_SUBTITLE_NEGATIVE
    low = base.lower()
    if "subtitle" in low and "caption" in low:
        return base
    return base.rstrip(", ") + ", " + H3_NO_SUBTITLE_NEGATIVE


def ensure_h3_no_subtitle_rules(prompt: str) -> str:
    """保证禁字幕句出现恰好 3 次：多模态描述开头、对话附近、多模态描述末尾。

    用于 build_h3_prompt 与 Strata 打磨后；若已有 >=3 次则不改；不足则清掉旧的再按位置重插。
    """
    rule = H3_NO_SUBTITLE_RULE
    text = prompt or ""
    if text.count(rule) >= 3:
        return text

    # 去掉已有残缺副本，避免凑不齐或堆在一处
    cleaned = text.replace(rule, "")
    cleaned = re.sub(r"[ \\t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\\n{3,}", "\\n\\n", cleaned)

    # 拆 REFERENCE PICTURES 头（若有）
    head, body = "", cleaned
    if cleaned.startswith("REFERENCE PICTURES:") and "\\n\\n" in cleaned:
        head, body = cleaned.split("\\n\\n", 1)
        head = head + "\\n\\n"

    # 定位 integrated_multimodal_description / overall_soundscape
    marker = "integrated_multimodal_description:"
    sound = "\\n\\noverall_soundscape:"
    if marker in body:
        pre, rest = body.split(marker, 1)
        # rest 以可选空白 + 正文；末尾到 overall_soundscape
        if sound in rest:
            mid, post = rest.split(sound, 1)
            post = sound + post
        else:
            mid, post = rest, ""
        mid = mid.lstrip(" ")
        # top: 紧跟 [Shot 1] 句号后，或描述最前
        top_at = 0
        m = re.search(r"\\[Shot 1\\][^.\\n]*\\.", mid)
        if m:
            top_at = m.end()
        # middle: 对话 <d> 前，或 Speaker map / Lip sync 前
        mid_at = None
        for key in ("<d>", "Speaker map:", "Lip sync:", "On camera:"):
            i = mid.find(key)
            if i >= 0 and (mid_at is None or i < mid_at):
                mid_at = i
        if mid_at is None:
            mid_at = max(top_at, len(mid) // 2)
        # end: 描述末尾（进 sound 之前）
        end_at = len(mid.rstrip())

        def _ins(s: str, at: int, chunk: str) -> str:
            at = max(0, min(at, len(s)))
            left, right = s[:at].rstrip(), s[at:].lstrip()
            return (left + " " + chunk + " " + right).strip()

        # 从后往前插，避免偏移
        pieces = [(end_at, rule), (mid_at, rule), (top_at, rule)]
        # 去重位置过近
        used = []
        for at, chunk in pieces:
            if any(abs(at - u) < 5 for u in used):
                at = max(0, at - 8)
            used.append(at)
        # sort descending
        for at, chunk in sorted(zip(used, [rule, rule, rule]), key=lambda x: -x[0]):
            mid = _ins(mid, at, chunk)
        # 若仍不足 3（极端短文），末尾补
        while mid.count(rule) < 3:
            mid = mid.rstrip() + " " + rule
        body = pre + marker + " " + mid.lstrip() + post
    else:
        # 非标准 H3：头 / 中 / 尾硬插
        lines = body.splitlines() or [body]
        if len(lines) == 1:
            body = f"{rule} {body.strip()} {rule} {rule}"
        else:
            mid_i = max(1, len(lines) // 2)
            lines = [rule, lines[0]] + lines[1:mid_i] + [rule] + lines[mid_i:] + [rule]
            body = "\\n".join(lines)
        while body.count(rule) < 3:
            body = body.rstrip() + " " + rule

    out = head + body
    # 保底
    while out.count(rule) < 3:
        out = out.rstrip() + " " + rule
    return out


'''


def patch_config_prompt():
    path = ROOT / "config_prompt.py"
    text = path.read_text(encoding="utf-8")
    if "H3_NO_SUBTITLE_RULE" in text:
        print("config_prompt helpers already present")
    else:
        # Insert before build_h3_prompt
        anchor = "def build_h3_prompt(scenes, *, frames: str = \"one\", transition=None, style: str = \"\", region: str = \"\", era: str = \"\","
        if anchor not in text:
            raise SystemExit("build_h3_prompt not found")
        # Fix HELPERS: the string was written with double-escaped newlines for the *source file content*
        # We need the helpers as valid Python in config_prompt.py
        helpers = HELPERS
        # Convert intentional \\n in regex/strings that should be real escapes in the .py file
        # In HELPERS triple-quoted string in this patch script:
        # - `\\n` in the patch file source → `\n` in helpers value → correct for writing to config_prompt
        # Wait: HELPERS is a normal ''' string in the patch file. In the patch file we have `\\n` 
        # which becomes `\n` (backslash + n) in the helpers string value - GOOD for writing Python source.
        text = text.replace(anchor, helpers + "\n" + anchor, 1)
        print("inserted H3_NO_SUBTITLE helpers")

    # Inject call at end of build_h3_prompt return
    old_ret = '''    return (first + "\\n\\nintegrated_multimodal_description: " + " ".join(shot)
            + "\\n\\noverall_soundscape: " + sound + "\\n\\nnon_diegetic_music: " + music)
'''
    # Actual file has real newlines in the source as \n escapes
    old_ret = (
        '    return (first + "\\n\\nintegrated_multimodal_description: " + " ".join(shot)\n'
        '            + "\\n\\noverall_soundscape: " + sound + "\\n\\nnon_diegetic_music: " + music)\n'
    )
    new_ret = (
        '    # t238u: 禁字幕句写三遍（头 / 对话旁 / 尾）；打磨后 ensure 会再核对\n'
        '    raw = (first + "\\n\\nintegrated_multimodal_description: " + " ".join(shot)\n'
        '           + "\\n\\noverall_soundscape: " + sound + "\\n\\nnon_diegetic_music: " + music)\n'
        '    return ensure_h3_no_subtitle_rules(raw)\n'
    )
    if "return ensure_h3_no_subtitle_rules(raw)" in text:
        print("build_h3 return already wrapped")
    else:
        if old_ret not in text:
            # show nearby
            idx = text.find('integrated_multimodal_description: " + " ".join(shot)')
            print("NEAR", repr(text[idx-80:idx+200]) if idx >= 0 else "not found")
            raise SystemExit("build_h3 return not found")
        text = text.replace(old_ret, new_ret, 1)
        print("wrapped build_h3_prompt return")

    # Also place explicit mid rule near dialogue in shot list for prominence before ensure
    old_said = '''    if said:
        shot.append(" ".join(said))
'''
    new_said = '''    if said:
        shot.append(H3_NO_SUBTITLE_RULE)  # t238u: 对话旁再强调一次（ensure 会凑满三遍）
        shot.append(" ".join(said))
'''
    if "shot.append(H3_NO_SUBTITLE_RULE)  # t238u" in text:
        print("mid rule already in shot")
    else:
        if old_said not in text:
            raise SystemExit("said append not found")
        text = text.replace(old_said, new_said, 1)
        print("added mid-dialogue rule in shot")

    path.write_text(text, encoding="utf-8")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(raw[3:])
    print("config_prompt written")


def patch_polish():
    path = ROOT / "utility" / "prompt_polish.py"
    text = path.read_text(encoding="utf-8")

    # Update _SYS_H3
    needle = "- Copy the sentence starting \"On camera:\" verbatim."
    add = (
        "- Copy the sentence starting \"On camera:\" verbatim. A person who speaks is seen speaking on camera with moving lips, never as a voice-over: never describe a speaker with a hand on \n"
    )
    # Find a shorter unique line in _SYS_H3
    if "NEVER add any subtitles" not in text:
        old_sys = '- Copy the sentence starting "On camera:" verbatim.'
        # The actual file may have longer On camera line - search
        idx = text.find('Copy the sentence starting "On camera:"')
        if idx < 0:
            raise SystemExit("On camera sys line not found")
        # insert a new bullet after the Actor-is-truth / before Output only
        out_only = "Output only the final prompt: no preface, no notes, no markdown fences."
        if out_only not in text.split("_SYS_H3", 1)[1][:2500]:
            # find within _SYS_H3 only
            pass
        insert = (
            '- Keep EVERY copy of this exact sentence verbatim (there are three): '
            '"NEVER add any subtitles, captions or on-screen text of the dialogue!" '
            "Do not drop, paraphrase, or merge them.\n"
        )
        # Insert before "Output only the final prompt" in _SYS_H3
        marker = "Output only the final prompt: no preface, no notes, no markdown fences.\"\"\""
        # Only first occurrence is _SYS_H3 (general has different text)
        h3_out = "Output only the final prompt: no preface, no notes, no markdown fences.\"\"\""
        # _SYS_H3 ends with that; _SYS_GENERAL ends with similar - check
        parts = text.split(h3_out)
        if len(parts) < 2:
            # try without escaped quotes ending
            marker2 = 'Output only the final prompt: no preface, no notes, no markdown fences."""'
            if marker2 not in text:
                raise SystemExit("sys h3 end not found")
            # find the H3 one: after _SYS_H3
            h3_start = text.find("_SYS_H3")
            gen_start = text.find("_SYS_GENERAL")
            # H3 comes after GENERAL in file - looking at earlier dump, GENERAL is first, H3 second
            pos = text.find(marker2, text.find("_SYS_H3"))
            if pos < 0:
                raise SystemExit("H3 output line not found")
            text = text[:pos] + insert + text[pos:]
            print("added keep-subtitle-rule to _SYS_H3")
        else:
            # ambiguous - use position after _SYS_H3
            pos = text.find(h3_out, text.find("_SYS_H3"))
            text = text[:pos] + insert + text[pos:]
            print("added keep-subtitle-rule to _SYS_H3 (split)")
    else:
        print("_SYS_H3 already mentions NEVER subtitles")

    # After restore locks, ensure rules
    old_block = '''    if str(backend or "").startswith("minimax"):
        out = restore_h3_dialogue(prompt, out)  # t172u: 对话部分一律用原文
        out = restore_h3_locked_lines(prompt, out)  # t150u: 讲话人对应 + 对口型那两句一律用原句
        _first = prompt.strip().splitlines()[0].strip()
'''
    new_block = '''    if str(backend or "").startswith("minimax"):
        out = restore_h3_dialogue(prompt, out)  # t172u: 对话部分一律用原文
        out = restore_h3_locked_lines(prompt, out)  # t150u: 讲话人对应 + 对口型那两句一律用原句
        from config_prompt import ensure_h3_no_subtitle_rules  # t238u

        out = ensure_h3_no_subtitle_rules(out)  # 禁字幕句必须仍有三遍
        _first = prompt.strip().splitlines()[0].strip()
'''
    if "ensure_h3_no_subtitle_rules(out)" in text:
        print("polish ensure already present")
    else:
        if old_block not in text:
            raise SystemExit("polish restore block not found")
        text = text.replace(old_block, new_block, 1)
        print("polish ensures no-subtitle x3 after restore")

    # Also ensure on successful return AND on fallback to original (original should already have 3)
    # When validate fails, returns prompt (original) which has 3 from build - OK
    # When success, out already ensured - OK
    # Extra: ensure right before both returns for minimax
    old_ok = '''    why = f"Strata 精简完成：{len(prompt)} → {len(out)} 字（{secs:.1f} 秒）"
    print(f"[Strata 精简] {why}")
    return out, why
'''
    new_ok = '''    if str(backend or "").startswith("minimax"):
        from config_prompt import ensure_h3_no_subtitle_rules

        out = ensure_h3_no_subtitle_rules(out)  # t238u: 最终再核对三遍
    why = f"Strata 精简完成：{len(prompt)} → {len(out)} 字（{secs:.1f} 秒）"
    print(f"[Strata 精简] {why}")
    return out, why
'''
    if "最终再核对三遍" in text:
        print("final ensure already present")
    else:
        if old_ok not in text:
            raise SystemExit("polish success return not found")
        text = text.replace(old_ok, new_ok, 1)
        print("final ensure on success return")

    path.write_text(text, encoding="utf-8")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(raw[3:])
    print("prompt_polish written")


def patch_sd_and_dual():
    # sd_image_processor: merge negative when provided
    path = ROOT / "utility" / "sd_image_processor.py"
    text = path.read_text(encoding="utf-8")
    old = '''    if negative:
        print("[ComfyUI H3] 没有负面提示词输入，negative 不使用")
'''
    new = '''    if negative is not None:
        try:
            from config_prompt import with_h3_no_subtitle_negative

            negative = with_h3_no_subtitle_negative(negative)  # t238u
        except Exception:  # noqa: BLE001
            pass
        print("[ComfyUI H3] 没有负面提示词输入，negative 不使用（已并入字幕禁词备查）")
'''
    if "with_h3_no_subtitle_negative" in text:
        print("sd negative merge already present")
    else:
        if old not in text:
            print("WARN: i2v negative block not found exact")
        else:
            text = text.replace(old, new, 1)
            print("sd i2v negative merge")

    # Also ensure prompt before submit in generate path
    # find where prompt is used in generate_minimax / run
    gen_marker = "wf = build_minimax_h3_prompt(workflow, image_name=image_name, prompt=prompt, seconds=seconds, width=width,"
    if "ensure_h3_no_subtitle_rules(prompt)" in text:
        print("sd ensure before build already")
    elif gen_marker in text:
        text = text.replace(
            gen_marker,
            "try:\n"
            "        from config_prompt import ensure_h3_no_subtitle_rules, with_h3_no_subtitle_negative\n"
            "        prompt = ensure_h3_no_subtitle_rules(prompt)  # t238u\n"
            "        negative = with_h3_no_subtitle_negative(negative)\n"
            "    except Exception as _e:  # noqa: BLE001\n"
            "        print(f\"[ComfyUI H3] 禁字幕句核对跳过：{_e}\")\n"
            "    " + gen_marker,
            1,
        )
        print("sd ensure before build_minimax_h3_prompt")
    else:
        print("WARN: build_minimax_h3_prompt call not found")

    path.write_text(text, encoding="utf-8")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(raw[3:])

    # dual: ensure before generate
    dpath = ROOT / "utility" / "minimax_dual.py"
    dtext = dpath.read_text(encoding="utf-8")
    if "ensure_h3_no_subtitle_rules" in dtext:
        print("dual already ensures")
    else:
        # find start of minimax_generate body after docstring
        anchor = "def minimax_generate(prompt, image_path, image_paths, extra, dest_dir, backend, status=None, server_key=None) -> str:\n"
        if anchor not in dtext:
            raise SystemExit("minimax_generate not found")
        # insert after first few lines of function - find `key = ` or similar
        idx = dtext.find(anchor) + len(anchor)
        # skip docstring if any
        rest = dtext[idx:]
        insert = (
            "    try:  # t238u: 提交前再保证禁字幕句三遍\n"
            "        from config_prompt import ensure_h3_no_subtitle_rules\n"
            "        prompt = ensure_h3_no_subtitle_rules(prompt)\n"
            "    except Exception as _e:  # noqa: BLE001\n"
            "        print(f\"[MiniMax] 禁字幕句核对跳过：{_e}\")\n"
        )
        # Find a good spot: after docstring
        if rest.lstrip().startswith('"""'):
            end = rest.find('"""', 3) + 3
            dtext = dtext[:idx] + rest[:end] + "\n" + insert + rest[end:]
        else:
            dtext = dtext[:idx] + insert + rest
        dpath.write_text(dtext, encoding="utf-8")
        print("dual ensures before generate")


if __name__ == "__main__":
    patch_config_prompt()
    patch_polish()
    patch_sd_and_dual()
