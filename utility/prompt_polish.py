# -*- coding: utf-8 -*-
"""t166u: 提交视频前用本机 Strata 把提示词打磨得更短、更准（Grok / Gemini / MiniMax 都用）。

polish_video_prompt(prompt, backend) -> (新提示词, 说明)。任何失败（超时、缺台词、缺标记、长度不对）都退回原提示词，说明里写原因。
"""
import re
import time

POLISH_TIMEOUT_S = 60.0

_SYS_GENERAL = """You are an expert prompt editor for AI video generation (Grok Imagine / Google Veo).
Rewrite the user's video prompt into ONE concise, precise video-generation prompt in English.
Keep ALL hard facts:
- The OUTPUT FORMAT line(s) at the very top, copied verbatim as the first lines.
- Every dialogue line verbatim (same words and punctuation, same order), each with its speaker's name and that speaker's voice (gender, age, voice name).
- Who is in the clip and the cast lock (exactly these people, nobody else), their look and age.
- Lighting / time of day and the real-time continuity of the moment.
- Camera, visual style, setting region and era, and the sound rule (natural sound of the place, no music).
- The sentence "Clean film image: only the scene fills the frame." copied verbatim near the top AND again as the last line.
- People's names exactly as written (do not romanize or translate names).
Remove repetition, field names, meta explanations and instructions about how to read the prompt.
Write in positive, concrete phrasing (describe what is seen and heard). Do not write ban lists.
Output only the final prompt text: no preface, no notes, no markdown fences."""

_SYS_H3 = """You are an expert prompt editor for the MiniMax H3 audio-video model.
The user gives a prompt already in the official H3 format. Return an improved prompt in EXACTLY the same structure:
1. The first line copied verbatim, then one blank line.
2. Then exactly these three fields, each starting on its own line, in this order:
integrated_multimodal_description: [Shot 1] ...
overall_soundscape: ...
non_diegetic_music: ...
Rules:
- Keep every <d>[Language] ...</d> block exactly verbatim (do not translate or change anything inside <d>...</d>), in the same order.
- Keep the speaker ids (S1), (S2)... and the <Picture N> / Picture N references.
- Translate any Chinese text OUTSIDE the <d> blocks into natural English, but keep people's names exactly as written (do not romanize them).
- Make the visual, action, expression and voice descriptions vivid, concrete and concise, in English, positive phrasing only. No ban lists.
- Keep the lighting / time-of-day continuity and the camera instruction.
- Copy every sentence that contains a <d> block exactly as given, together with the speaker description in front of it (for example "The young man 林浩 with a young male voice (voice Leo) (S2) says:"). Rewrite only the sentences without <d>.
Output only the final prompt: no preface, no notes, no markdown fences."""


def _clean(text: str) -> str:
    t = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S | re.I)
    t = re.sub(r"^\s*```[a-zA-Z]*\s*\n", "", t.strip())
    t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


def _dialogue_lines(prompt: str, h3: bool) -> list:
    if h3:
        return re.findall(r"<d>.*?</d>", prompt, flags=re.S)
    return [m.strip() for m in re.findall(r"says aloud:\s*(.+)$", prompt, flags=re.M) if m.strip()]


_TEXT_WORDS = ("subtitle", "caption", "on-screen text", "onscreen text", "text overlay", "lettering", "字幕", "台词字")


def _dialogue_span(text: str):
    """H3：从第一句带 <d> 的句子开头（说话人描述）到最后一个 </d>。没有就 None。"""
    first = text.find("<d>")
    last = text.rfind("</d>")
    if first < 0 or last < first:
        return None
    head = text[:first]
    start = 0
    for m in re.finditer(r"[.!?。！？](?=\s)|\[Shot \d+\]", head):
        start = m.end()
    while start < first and head[start:start + 1].isspace():
        start += 1
    return start, last + len("</d>")


def restore_h3_dialogue(original: str, polished: str) -> str:
    """t172u: Strata 打磨后，把整段对话（说话人句 + <d>…</d>）换回原文，一字不改。"""
    a = _dialogue_span(original)
    b = _dialogue_span(polished or "")
    if not a or not b:
        return polished
    return polished[:b[0]] + original[a[0]:a[1]] + polished[b[1]:]


def _added_text_words(original: str, polished: str) -> str:
    lo, lp = original.lower(), polished.lower()
    for w in _TEXT_WORDS:
        if w in lp and w not in lo:
            return w
    return ""


def validate(original: str, polished: str, backend: str) -> str:
    """返回 '' 表示通过，否则是原因。"""
    h3 = backend == "minimax"
    if not polished:
        return "Strata 返回空"
    added = _added_text_words(original, polished)
    if added:
        return f"Strata 加了文字相关的词（{added}）"
    for line in _dialogue_lines(original, h3):
        if line not in polished:
            return f"台词没有原样保留：{line[:40]}"
    if h3:
        first = original.strip().splitlines()[0].strip()
        if polished.strip().splitlines()[0].strip() != first:
            return "H3 第一行变了"
        for field in ("integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:"):
            if field not in polished:
                return f"缺少字段 {field}"
        if not polished.split("integrated_multimodal_description:", 1)[1].lstrip().startswith("[Shot 1]"):
            return "缺少 [Shot 1]"
        for sid in set(re.findall(r"\(S\d+(?:,S\d+)*\)", original)):
            if sid not in polished:
                return f"说话人编号 {sid} 丢了"
        if "<Picture 1>" in original and "Picture 1" not in polished:
            return "Picture 1 引用丢了"
        lo, hi = 0.5, 2.0
    else:
        if "Clean film image: only the scene fills the frame." in original and \
                "Clean film image: only the scene fills the frame." not in polished:
            return "画面干净那句没保留"
        head = original.strip().splitlines()[0].strip()
        if head.startswith("OUTPUT FORMAT") and head not in polished:
            return "画面比例那一行没保留"
        lo, hi = 0.15, 1.0
    ratio = len(polished) / max(1, len(original))
    if not (lo <= ratio <= hi):
        return f"长度不对（{len(polished)} / 原 {len(original)} 字）"
    return ""


def polish_video_prompt(prompt: str, backend: str, timeout_s: float = POLISH_TIMEOUT_S) -> tuple:
    """(结果, 说明)。失败时结果是原提示词。"""
    started = time.monotonic()
    try:
        from utility import llm_api

        api = llm_api.LLMApi(llm_api.STRATA)
        api.manual_fallback = False
        import os

        import httpx
        from openai import OpenAI

        # 自己的短超时客户端（LLMApi 里的客户端是 180 秒，且 with_options 不能换自带的 http_client）
        client = OpenAI(api_key=os.getenv("STRATA_API_KEY", ""), base_url=llm_api.MODELS[llm_api.STRATA]["url"],
                        http_client=httpx.Client(timeout=httpx.Timeout(timeout_s)), max_retries=0)
        system = _SYS_H3 if backend == "minimax" else _SYS_GENERAL
        req = api._strata_request(llm_api.STRATA, [{"role": "system", "content": system},
                                                    {"role": "user", "content": prompt}])
        req["max_tokens"] = 4096
        resp = client.chat.completions.create(**req)
        out = _clean(resp.choices[0].message.content if resp and resp.choices else "")
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        why = f"Strata 调用失败（{type(exc).__name__}: {str(exc)[:120]}），用原提示词"
        print(f"[Strata 精简] {why}")
        return prompt, why
    secs = time.monotonic() - started
    if backend == "minimax":
        out = restore_h3_dialogue(prompt, out)  # t172u: 对话部分一律用原文
        _first = prompt.strip().splitlines()[0].strip()
        _lines = out.strip().splitlines()
        if _lines and _lines[0].strip() != _first and "integrated_multimodal_description:" in out:
            out = "\n".join([_first] + _lines[1:])  # 固定第一行也用原文
    bad = validate(prompt, out, backend)
    if bad:
        why = f"{bad}，用原提示词（{secs:.1f} 秒）"
        print(f"[Strata 精简] {why}")
        return prompt, why
    why = f"Strata 精简完成：{len(prompt)} → {len(out)} 字（{secs:.1f} 秒）"
    print(f"[Strata 精简] {why}")
    return out, why
