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
- FIRST LINE (t321u): if the prompt begins with the line starting "NO SUBTITLES:", copy that whole line verbatim as the very first line of your output, once. It defines subtitles / captions as the speaking content (heard as voice only, never written on screen); it is not about text already in the image. Do not repeat it anywhere else and do not add any other wording about subtitles, captions or on-screen text.
- Exact speech (t336u): if the prompt has the sentence starting "Exact speech:", copy it verbatim, once, in the same place (right before the first dialogue line, or inside the spoken transcript). The speaking text itself is never changed: do not repeat, split, merge, reword, translate, shorten or extend any spoken line, add no words to it, and never write a spoken line a second time anywhere else in the prompt.
- Portraits (t340u): if the prompt has the paragraph starting "Single scene shot:", copy it verbatim, once, where it is. The video is one continuous shot of picture 1 (the scene); never write that it cuts, switches or transitions to a portrait or shows a portrait as a shot. Any portrait picture (<Picture 2>, <Picture 3> ... or reference image 2, 3 ...) only identifies a person in picture 1; keep those mentions as identity references.
- Image keywords (t321u/t369u): if the prompt has the sentence starting "Image keywords:", copy it verbatim, once. It means: lettering already drawn in the start picture (a keyword set into the background) is kept and never erased, and may gently come alive; NO new text is ever added. Never take words from the visual description, the speaking lines or the scene title and put them on screen, and never write any new word, keyword or sign text into the prompt.
- One base shot (t382u): if the prompt has the sentence starting "One base shot:", copy it verbatim, once. The whole video stays in the base scene of picture 1 with the same composition: never write a cut, a shot change, a scene change, or a cut / switch to a portrait, a close-up or a single-person shot of whoever speaks. Each speaker talks where they are in the base scene (lips in sync for spoken lines), the others keep their mouths closed and may make small movements, and any change is slow and local.
- Art style (t369u): if the prompt has the sentence starting "Art style lock:", copy it verbatim, once. The video keeps the start picture's own art style exactly as named there (for example 3D animation / Pixar-style 3D cartoon). Keep that style name wherever the style is mentioned; never rewrite the style as live-action, photorealistic, realistic, real footage, real camera or a film shot.
- The OUTPUT FORMAT line(s) at the very top (right after the NO SUBTITLES line if present), copied verbatim.
- Every dialogue line verbatim (same words and punctuation, same order), each with its speaker's name and that speaker's voice (gender, age, voice name).
- Who is in the clip and the cast lock (exactly these people, nobody else), their look and age.
- Lighting / time of day and the real-time continuity of the moment.
- Camera, visual style, setting region and era, and the sound rule (natural sound of the place, no music).
- The sentence "Clean picture: only the scene fills the frame." copied verbatim once, near the top.
- People's names exactly as written (do not romanize or translate names).
- Speaker identity: <N> and <Ns> are the IDENTICAL actor N (any digits, e.g. <12>=<12s>); the letter s is a speech mode (self-talk / inner thought), not another person, portrait, costume, or voice. Copy any sentence starting "Speaker marks:" verbatim.
- Spoken transcript: copy the block from BEGIN_SPOKEN_TRANSCRIPT through END_SPOKEN_TRANSCRIPT verbatim. Only those lines are spoken. Visual, scene title, actor, reference, FYI and direction text are silent and must never be read, summarized, or turned into narration. Copy any sentence starting "Spoken words:" verbatim.
- Self-talk: copy sentences starting "Self-talk:", "Entire-scene self-talk:", "Audible voices:", "Single audible voice:", and "Speak once:" verbatim. A scene with exactly one speaking turn marked <Ns> is that same actor delivering the exact supplied speaking text off-mouth (lips closed, no lip sync), audible not mute — not narration of actions or setting, not another narrator. Interactive <N> lines still have lip sync. Cast count is not speaker count: unmarked visible people stay silent and never repeat the line.
- Directions inside the scene: when something is turned, shown or handed to a person, name that person as the target and say it turns sideways toward them inside the scene, never toward the camera or viewer. People never address the camera.
- Cast lock: keep the sentences starting "Exactly ... in the whole video" and "Any change of pose or place" verbatim. Never add a person. A change of pose or place is the same person moving there (for example "小偉 himself walks over and sits down on the chair"), never a second copy.
Remove repetition, field names, meta explanations and instructions about how to read the prompt.
Write in positive, concrete phrasing (describe what is seen and heard). Do not write ban lists.
Output only the final prompt text: no preface, no notes, no markdown fences."""

_SYS_H3 = """You are an expert prompt editor for the MiniMax H3 audio-video model.
The user gives a prompt already in the official H3 format. Return an improved prompt in EXACTLY the same structure:
FIRST LINE (t321u): if the prompt begins with the line starting "NO SUBTITLES:", copy that whole line verbatim as the very first line of your output, once. It defines subtitles / captions as the speaking content (heard as voice only, never written on screen); it is not about text already in the image. Do not repeat it anywhere else and do not add any other wording about subtitles, captions or on-screen text.
Exact speech (t336u): if the prompt has the sentence starting "Exact speech:", copy it verbatim, once, in the same place (right before the first dialogue line, or inside the spoken transcript). The speaking text itself is never changed: do not repeat, split, merge, reword, translate, shorten or extend any spoken line, add no words to it, and never write a spoken line a second time anywhere else in the prompt.
Portraits (t340u): if the prompt has the paragraph starting "Single scene shot:", copy it verbatim, once, where it is. The video is one continuous shot of picture 1 (the scene); never write that it cuts, switches or transitions to a portrait or shows a portrait as a shot. Any portrait picture (<Picture 2>, <Picture 3> ... or reference image 2, 3 ...) only identifies a person in picture 1; keep those mentions as identity references.
Image keywords (t321u/t369u): if the prompt has the sentence starting "Image keywords:", copy it verbatim, once. It means: lettering already drawn in the start picture (a keyword set into the background) is kept and never erased, and may gently come alive; NO new text is ever added. Never take words from the visual description, the speaking lines or the scene title and put them on screen, and never write any new word, keyword or sign text into the prompt.
One base shot (t382u): if the prompt has the sentence starting "One base shot:", copy it verbatim, once. The whole video stays in the base scene of picture 1 with the same composition: never write a cut, a shot change, a scene change, or a cut / switch to a portrait, a close-up or a single-person shot of whoever speaks. Each speaker talks where they are in the base scene (lips in sync for spoken lines), the others keep their mouths closed and may make small movements, and any change is slow and local.
Art style (t369u): if the prompt has the sentence starting "Art style lock:", copy it verbatim, once, right after the [Shot 1] style sentence. The video keeps <Picture 1>'s own art style exactly as named there (for example 3D animation / Pixar-style 3D cartoon). Keep the style name in the [Shot 1] opening; never rewrite the style as live-action, photorealistic, realistic, real footage, real camera or a film shot.
1. The first line (the NO SUBTITLES line, or the H3 mode line when there is none) copied verbatim, then one blank line; when the NO SUBTITLES line is first, the H3 mode line follows it unchanged.
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
- Directions inside the scene: when something is turned, shown or handed to a person ("轉向 David", "turns toward David"), write it with that person as the explicit target, turning sideways inside the scene toward them, never toward the camera or viewer. Copy every sentence containing "not toward the camera" or "Everyone stays inside the scene" verbatim. People never address the camera.
- Cast lock: copy the sentences starting "Exactly ... in the whole video" and "Any change of pose or place" verbatim. Never add a person. When the description really changes someone's pose or place (sits down, stands up, walks to...), write it as that same person moving there from where they are, never as a second copy; a person already sitting or standing in <Picture 1> simply stays there, so never invent a move. Do not describe the same move a second time in other words.
- Copy every sentence that contains a <d> block exactly as given, together with the speaker description in front of it (for example "The young man 林浩 with a young male voice (voice Leo) (S2) says:"), including the bracketed description of each person, the times, the "while ... listens with closed lips" part and the "lip movement switches to ..." part. Rewrite only the sentences without <d>.
- Lip sync and speaker mapping are the most important facts of this prompt. Copy the sentence starting "Speaker map:" and the sentence starting "Lip sync:" verbatim, with every bracketed person description. Never drop, shorten, swap or soften the lip-sync emphasis, who speaks, who stays silent with closed lips, the switch of the moving mouth when the speaker changes, or each speaker's seat/side (left/right) and clothing in the brackets. Every (S1)/(S2) id always means the same person as in the Speaker map; never move a speaker to the other person's seat or outfit.
- Self-talk (t241/t250/t283/t284/t285/t286): if the prompt contains the sentence starting "Self-talk:" or "Entire-scene self-talk:" or "Speaker marks:" or "Spoken words:" or "Audible voices:" or "Single audible voice:" or "Speak once:", copy each verbatim. Copy BEGIN_SPOKEN_TRANSCRIPT ... END_SPOKEN_TRANSCRIPT verbatim. Never drop them. <N> and <Ns> are the identical actor N (lowercase s is speech mode, not another person). Self-talk lines marked <Ns> have NO lip sync (mouth closed) and are that actor's exact speaking text, not picture narration; only interactive dialogue has lip sync. Visual / "Silent picture direction" text is never spoken. Cast count is not speaker count: a visible person with no speaking turn never speaks or repeats the line. If the same words appear in a <d> tag and in the transcript, speak them once only.
- Actor-is-truth for positioning (t223): each speaker's left/right/seat comes ONLY from the Speaker map brackets (which come from the actor parenthesis). If "What happens while they talk" (or any action sentence) puts a named person on the opposite side or in the other person's seat, ignore that positioning — do not rewrite, swap, or merge seats from the action text; keep the Speaker map seats. You may keep story actions, gestures and props from the action text.
- Copy the sentence starting "On camera:" verbatim. If that sentence describes closed-mouth / off-mouth delivery of the exact speaking text, keep that meaning: do not rewrite it as visible lip movement and do not invent picture narration. If it describes interactive spoken dialogue, a person who speaks is seen speaking on camera with moving lips, never as a different narrator: never describe an interactive speaker with a hand on the chin or over the mouth, looking down, with the head bowed, turned away or with the face hidden, and never make a speaker walk or change place while talking. When there is interactive dialogue, write the actions as happening while they say their lines and add no silence or quiet wording; this never means more speech: no spoken words are added, repeated or continued.
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


def _repeated_spoken_line(original: str, polished: str) -> str:
    """t336u: Strata 把某句台词（<d> 里的原文）多写了一遍 → 返回那句；没有就 ""。"""
    for m in re.finditer(r"<d>(.*?)</d>", original or "", re.S):
        line = re.sub(r"^\s*\[[^\]]*\]\s*", "", m.group(1)).strip()
        if len(line) >= 2 and (polished or "").count(line) > (original or "").count(line):
            return line
    return ""


def _added_text_words(original: str, polished: str) -> str:
    """t321u: 禁字幕第一行和「Image keywords:」那句不算；Strata 多写了字幕 / 文字类的词（比原文多）就不通过。"""
    try:
        from config_prompt import VIDEO_IMAGE_KEYWORDS_RULE, strip_video_no_subtitle_lines

        def _body(s: str) -> str:
            return strip_video_no_subtitle_lines(s).replace(VIDEO_IMAGE_KEYWORDS_RULE, " ").lower()
    except Exception:  # noqa: BLE001
        def _body(s: str) -> str:
            return (s or "").lower()
    lo, lp = _body(original), _body(polished)
    for w in _TEXT_WORDS:
        if lp.count(w) > lo.count(w):
            return w
    return ""


_DIRECTION_RE = re.compile(
    r"[^.\n]*(?:not toward the camera|Everyone stays inside the scene|in the whole video, |never by a second copy|the same person as in the start picture|Story stage: )[^.\n]*\."
)  # t181u 方向句 + t182u 人数锁


def restore_direction_lines(original: str, polished: str) -> str:
    """t181u: 原文里的方向句（不对镜头、转向某人）打磨后丢了就补回去：H3 放在对话前，其他放在末行前。"""
    out = polished or ""
    missing = [m.group(0).strip() for m in _DIRECTION_RE.finditer(original or "") if m.group(0).strip() not in out]
    # t182u: 换位置那句：Strata 已经为同一个人写了同样的动作（同名开头 + 同一个动作短语）就用原句换掉那一句，不再多补一句
    keep = []
    for x in missing:
        tail = ", the same person as in the start picture"
        if tail in x and " " in x:
            name, rest = x.split(" ", 1)
            move = rest.split(tail, 1)[0]
            if re.search(rf"(?<![^\s.]){re.escape(name)} [^.\n]*the same person as in the start picture", out):
                continue  # Strata 已经写了这个人的换位置句
            pat = re.compile(rf"(?<![^\s.]){re.escape(name)} (?:himself |herself )?{re.escape(move)}[^.\n]*\.")
            m = pat.search(out)
            if m:
                out = out[:m.start()] + m.group(0).rstrip('.') + x.split(name + ' ' + move, 1)[1] + out[m.end():]
                continue
        keep.append(x)
    missing = keep
    if not missing:
        return out
    add = " ".join(missing)
    span = _dialogue_span(out) if "<d>" in out else None
    if span:
        return out[:span[0]] + add + " " + out[span[0]:]
    lines = out.rstrip().splitlines()
    if len(lines) > 1:
        return "\n".join(lines[:-1] + [add, lines[-1]])
    return out.rstrip() + "\n" + add


_H3_LOCKED = ("Speaker map: ", "Lip sync: ", "On camera: ", "Speech pace: ",
              "Speaker marks: ", "Self-talk: ", "Entire-scene self-talk: ",
              "Entire-scene inner monologue: ", "Spoken words: ",
              "Audible voices: ", "Single audible voice: ", "Speak once: ")  # t150u / t283u / t284u / t286u


def _locked_sentence(text: str, prefix: str):
    i = (text or "").find(prefix)
    if i < 0:
        return None
    j = text.find(".", i)
    while j >= 0 and j + 1 < len(text) and not text[j + 1].isspace():
        j = text.find(".", j + 1)  # 跳过 5.7 这种小数点
    j = len(text) if j < 0 else j + 1
    return i, j


def restore_h3_locked_lines(original: str, polished: str) -> str:
    """t150u: 「Speaker map:」「Lip sync:」两句：Strata 改了就换回原句，丢了就补在对话前。"""
    out = polished or ""
    for prefix in _H3_LOCKED:
        a = _locked_sentence(original or "", prefix)
        if not a:
            continue
        want = original[a[0]:a[1]]
        b = _locked_sentence(out, prefix)
        if b:
            out = out[:b[0]] + want + out[b[1]:]
            continue
        span = _dialogue_span(out) if "<d>" in out else None
        if span:
            out = out[:span[0]] + want + " " + out[span[0]:]
        else:
            k = out.find("\n\noverall_soundscape:")
            out = (out[:k].rstrip() + " " + want + out[k:]) if k >= 0 else (out.rstrip() + " " + want)
    return out


def split_reference_block(prompt: str) -> tuple:
    """t150u/t246: 参考图工作流的 REFERENCE PICTURES 段落不交给 Strata 改：(前缀 + 段落 + 空行, H3 正文)。
    
    t246: 正确处理禁字幕行前缀。如果存在，先剥离，找到 REFERENCE PICTURES，然后重新组装。
    返回 (ref_block_with_critical_prefix, body)，其中 ref_block 包含禁字幕行（若有）和 REFERENCE PICTURES。
    """
    text = prompt or ""
    
    # t246: 检查是否以禁字幕行开头
    try:
        from config_prompt import VIDEO_NO_SUBTITLE_CRITICAL_LINE
        critical = VIDEO_NO_SUBTITLE_CRITICAL_LINE
    except ImportError:
        critical = None
    
    critical_prefix = ""
    working_text = text
    
    if critical:
        first_line = text.split('\n', 1)[0].strip() if text else ""
        if first_line == critical.strip():
            # 移除第一行和紧随的空行
            rest = text[len(first_line):].lstrip('\n')
            critical_prefix = critical + "\n\n"
            working_text = rest.strip()
    
    # 现在检查 REFERENCE PICTURES
    if working_text.startswith("REFERENCE PICTURES:") and "\n\n" in working_text:
        head, rest = working_text.split("\n\n", 1)
        return critical_prefix + head + "\n\n", rest
    
    # 没有 REFERENCE PICTURES，返回禁字幕行前缀（若有）作为 head 的一部分
    if critical_prefix:
        return critical_prefix, working_text
    
    return "", text


def validate(original: str, polished: str, backend: str) -> str:
    """返回 '' 表示通过，否则是原因。"""
    h3 = str(backend or "").startswith("minimax")  # t188u/t194u: minimax_5070ti / minimax_5060 / minimax_dual
    if not polished:
        return "Strata 返回空"
    added = _added_text_words(original, polished)
    if added:
        return f"Strata 加了文字相关的词（{added}）"
    try:  # t369u: 非写实画风（三维动画等）时 Strata 写进了写实 / 实拍的词 → 不通过
        from config_prompt import ART_STYLE_LOCK_PREFIX, added_realism_words

        real = added_realism_words(original, polished)
        if real:
            return f"Strata 把画风改成写实（{real}）"
        if ART_STYLE_LOCK_PREFIX in original and ART_STYLE_LOCK_PREFIX not in polished:
            return "画风锁定那句没保留"
        from config_prompt import VIDEO_ONE_SHOT_PREFIX, added_cut_words  # t382u

        cut = added_cut_words(original, polished)
        if cut:
            return f"Strata 加了切镜头 / 切到肖像的说法（{cut}）"
        if VIDEO_ONE_SHOT_PREFIX in original and VIDEO_ONE_SHOT_PREFIX not in polished:
            return "基础画面（不切镜头）那句没保留"
    except ImportError:
        pass
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
        for prefix in _H3_LOCKED:  # t150u
            a = _locked_sentence(original, prefix)
            if a and original[a[0]:a[1]] not in polished:
                return f"「{prefix.strip()}」那句没有原样保留"
        lo, hi = 0.5, 2.0
    else:
        if "Clean picture: only the scene fills the frame." in original and \
                "Clean picture: only the scene fills the frame." not in polished:
            return "画面干净那句没保留"
        head = original.strip().splitlines()[0].strip()
        if head.startswith("OUTPUT FORMAT") and head not in polished:
            return "画面比例那一行没保留"
        lo, hi = 0.15, 1.0
    ratio = len(polished) / max(1, len(original))
    if not (lo <= ratio <= hi):
        return f"长度不对（{len(polished)} / 原 {len(original)} 字）"
    return ""


def _fix_no_subtitle_line(original: str, out: str) -> str:
    """t321u: 原文以禁字幕句开头 → 结果里它恰好一次且在第一行；原文没有（参考图正文另算）→ 结果里一句也不留。"""
    from config_prompt import VIDEO_NO_SUBTITLE_CRITICAL_LINE, ensure_video_no_subtitle_first_line, strip_video_no_subtitle_lines

    first = (original or "").strip().split("\n", 1)[0].strip()
    if first == VIDEO_NO_SUBTITLE_CRITICAL_LINE:
        return ensure_video_no_subtitle_first_line(out)
    return strip_video_no_subtitle_lines(out)


def polish_video_prompt(prompt: str, backend: str, timeout_s: float = POLISH_TIMEOUT_S) -> tuple:
    """(结果, 说明)。失败时结果是原提示词。"""
    ref_head, body = split_reference_block(prompt) if str(backend or "").startswith("minimax") else ("", prompt)
    if ref_head:  # t150u: 参考图说明段不改，只打磨 H3 正文
        out, why = polish_video_prompt(body, backend, timeout_s)
        from config_prompt import restore_portrait_reference_rule  # t340u: 参考图说明段里的那句恰好一次

        return restore_portrait_reference_rule(prompt, ref_head + out), why
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
        system = _SYS_H3 if str(backend or "").startswith("minimax") else _SYS_GENERAL
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
    # t244/t321u: 禁字幕句只说一次：原文第一行有就放回第一行，没有（参考图正文）就清掉 Strata 加的
    try:
        out = _fix_no_subtitle_line(prompt, out)
    except Exception as _e:  # noqa: BLE001
        print(f"[Strata 精简] 禁字幕第一行恢复跳过：{_e}")
    out = restore_direction_lines(prompt, out)  # t181u
    out = restore_h3_locked_lines(prompt, out)  # t150u / t283u: locked speaker/lip-sync/identity sentences
    from config_prompt import (  # t241u / t283u / t284u / t321u
        ensure_h3_monologue_no_lipsync_rules,
        ensure_speaker_semantics_rules,
        restore_exact_speech_rule,
        restore_image_keywords_rule,
        restore_spoken_transcript,
        restore_video_locked_rules,
    )

    out = restore_spoken_transcript(prompt, out)
    out = restore_image_keywords_rule(prompt, out)  # t321u
    out = restore_video_locked_rules(prompt, out)  # t369u: 画风锁定句
    out = restore_exact_speech_rule(prompt, out)  # t336u
    _has_mono = ("Self-talk:" in (prompt or "") or bool(re.search(r"[<＜]\s*\d+\s*s\s*[>＞]", prompt or "")))
    _single_inner = ("Entire-scene self-talk:" in (prompt or "") or "Entire-scene inner monologue:" in (prompt or ""))
    _has_speaking = _has_mono or _single_inner or "Speaker marks:" in (prompt or "") or "BEGIN_SPOKEN_TRANSCRIPT" in (prompt or "")
    if str(backend or "").startswith("minimax"):
        out = restore_h3_dialogue(prompt, out)  # t172u: 对话部分一律用原文
        out = restore_h3_locked_lines(prompt, out)  # after dialogue restore
        out = ensure_h3_monologue_no_lipsync_rules(out, has_monologue=_has_mono)  # t241u
        out = ensure_speaker_semantics_rules(
            out, has_speaking=_has_speaking, has_monologue=_has_mono, single_inner=_single_inner,
        )
        _first = prompt.strip().splitlines()[0].strip()
        _lines = out.strip().splitlines()
        if _lines and _lines[0].strip() != _first and "integrated_multimodal_description:" in out:
            if _lines[0].lstrip().startswith("integrated_multimodal_description:"):  # t181u: 第一行整行漏了：补在前面
                out = "\n".join([_first, ""] + _lines)
            else:
                out = "\n".join([_first] + _lines[1:])  # 固定第一行也用原文
    bad = validate(prompt, out, backend)
    if not bad:
        _rep = _repeated_spoken_line(prompt, out)  # t336u: 台词多写一遍 = 视频里会说两遍
        if _rep:
            bad = f"Strata 把台词「{_rep[:20]}」多写了一遍"
    if bad:
        why = f"{bad}，用原提示词（{secs:.1f} 秒）"
        print(f"[Strata 精简] {why}")
        return prompt, why
    if str(backend or "").startswith("minimax"):
        _has_mono2 = ("Self-talk:" in (prompt or "") or bool(re.search(r"[<＜]\s*\d+\s*s\s*[>＞]", prompt or "")))
        _single_inner2 = ("Entire-scene self-talk:" in (prompt or "") or "Entire-scene inner monologue:" in (prompt or ""))
        out = ensure_h3_monologue_no_lipsync_rules(out, has_monologue=_has_mono2)  # t241u
        out = ensure_speaker_semantics_rules(
            out, has_speaking=_has_speaking or _has_mono2, has_monologue=_has_mono2, single_inner=_single_inner2,
        )
    else:
        out = ensure_speaker_semantics_rules(
            out, has_speaking=_has_speaking, has_monologue=_has_mono, single_inner=_single_inner,
        )
    # t244/t321u: 最后再核对一次：禁字幕句恰好一次（原文有时在第一行）
    try:
        out = _fix_no_subtitle_line(prompt, out)
    except Exception as _e:  # noqa: BLE001
        print(f"[Strata 精简] 最终禁字幕第一行确保跳过：{_e}")
    out = restore_spoken_transcript(prompt, out)
    out = restore_exact_speech_rule(prompt, out)  # t336u: 恰好一句、原位置
    from config_prompt import restore_portrait_reference_rule

    out = restore_portrait_reference_rule(prompt, out)  # t340u: 「Single scene shot:」恰好一句
    out = restore_video_locked_rules(prompt, out)  # t369u: 最后再核对关键字句 + 画风锁定句
    why = f"Strata 精简完成：{len(prompt)} → {len(out)} 字（{secs:.1f} 秒）"
    print(f"[Strata 精简] {why}")
    return out, why


# ---------------------------------------------------------------------------
# t150u: MiniMax：Strata 先看场景图 + 人物肖像，给每个说话人写一句括号描述（衣服、脸、表情、在画面里的位置、特征），
# 再把描述放进提示词（Speaker map 和每个人第一次说话的地方），然后照常打磨。Strata 看不了图就只用文字。

_SYS_DESCRIBE = """You describe the people of ONE video scene so that a video model can tell them apart and move the lips of the right person.
You get: the speaker list (speaker id, name, actor description with an authoritative parenthesis about clothing and seat/side), the scene's visual description, the scene's first frame (Picture 1) and, for some speakers, a portrait.
Actor-is-truth for positioning (t223): the actor parenthesis for each speaker (clothing, hair, seat, left/right) is the ONLY source of who sits/stands where for that (S) id. Match the person in Picture 1 by that clothing and seat. IGNORE visual-text positioning entirely when an actor parenthesis exists — do not use, rewrite, or merge left/right/seat from the visual text into the description.
For EVERY speaker id write one short English description (at most 35 words) with: clothing and colours, hair and face, facial expression, approximate position and pose in Picture 1 (left / right / centre, foreground / background, standing / sitting / lying, near what), and any distinctive feature. Keep the actor's seat (left/right) and clothing. You may merge expression, gesture and action from the visual description for THIS person (never their seat/side). Follow the actor parenthesis + the matching person in Picture 1.
Use the portrait to recognise the person in Picture 1. If a person is not visible in Picture 1, describe them from the portrait and say they are not in view yet. Do not invent other people. Do not use the person's name or any brackets inside the description.
<N> and <Ns> are the same person (s is speech mode, not another character). If the scene is an entire-scene self-talk turn, a natural thinking pose is allowed. Visual text is only for appearance, never spoken words. For interactive spoken dialogue, describe the face as visible: never mention a hand on the chin or over the mouth, looking down, a bowed head, a turned-away or hidden face.
Return only JSON, for example: {"S1": "...", "S2": "..."}"""


def _image_data_url(path: str, side: int = 640) -> str:
    import base64
    import io

    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((side, side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _strata_client(timeout_s: float):
    import os

    import httpx
    from openai import OpenAI

    from utility import llm_api

    return OpenAI(api_key=os.getenv("STRATA_API_KEY", ""), base_url=llm_api.MODELS[llm_api.STRATA]["url"],
                  http_client=httpx.Client(timeout=httpx.Timeout(timeout_s)), max_retries=0)


def describe_speakers(speakers: list, scene_image: str = "", visual: str = "", timeout_s: float = POLISH_TIMEOUT_S,
                      use_images: bool = True) -> tuple:
    """speakers = [(序号, 名字, 身份/actor 文字, 肖像路径或 "", 人物括号或省略)]。
    返回 ({序号: 描述}, 说明, 是否看了图)。
    失败返回 ({}, 原因, False)；图片请求被拒时自动退回只用文字再问一次。"""
    import json
    import os

    if not speakers:
        return {}, "没有说话人", False
    lines = ["Speakers:"]
    try:
        from config_prompt import h3_visual_person_note as _vnote
    except Exception:  # noqa: BLE001
        _vnote = None
    _names = [nm for _n, nm, *_r in speakers]
    for n, name, ident, portrait, *rest in speakers:
        _actor = str(rest[0]).strip() if rest else ""
        _v = _vnote(str(visual or ""), name, _names) if _vnote else ""  # t151u: scene clauses about this person
        try:
            from config_prompt import drop_all_side_clauses as _drop_all
            if _actor and _v:
                _v = _drop_all(_v)  # t223u: ignore visual positioning entirely when actor exists
        except Exception:  # noqa: BLE001
            pass
        lines.append(
            f"- S{n}: {name}"
            + (f", {ident}" if ident else "")
            + (f", actor parenthesis (authoritative clothing/seat): {_actor}" if _actor else "")
            + (", portrait given" if portrait and use_images else "")
            + (f"; visual about this person (expression/action only; IGNORE all left/right/seat — actor is sole position source): {_v}" if _v else "")
        )
    lines.append("")
    lines.append("Visual description of the scene: " + (str(visual or "").strip() or "(none)"))
    content = [{"type": "text", "text": "\n".join(lines)}]
    seen = False
    if use_images:
        try:
            if scene_image and os.path.isfile(scene_image):
                content += [{"type": "text", "text": "Picture 1 (the scene, first frame of the video):"},
                            {"type": "image_url", "image_url": {"url": _image_data_url(scene_image)}}]
                seen = True
            for n, name, _ident, portrait, *_rest in speakers:
                if portrait and os.path.isfile(portrait):
                    content += [{"type": "text", "text": f"Portrait of S{n} {name}:"},
                                {"type": "image_url", "image_url": {"url": _image_data_url(portrait, 512)}}]
                    seen = True
        except Exception as exc:  # noqa: BLE001
            print(f"[Strata 人物描述] 图片没读出来（{exc}），只用文字")
            content, seen = content[:1], False
    started = time.monotonic()
    try:
        from openai import BadRequestError

        from utility import llm_api

        api = llm_api.LLMApi(llm_api.STRATA)
        api.manual_fallback = False
        req = api._strata_request(llm_api.STRATA, [{"role": "system", "content": _SYS_DESCRIBE},
                                                    {"role": "user", "content": content if seen else content[0]["text"]}])
        req["max_tokens"] = 1024
        try:
            resp = _strata_client(timeout_s).chat.completions.create(**req)
        except BadRequestError as exc:
            if not seen:
                raise
            print(f"[Strata 人物描述] 带图请求被拒（{str(exc)[:120]}），只用文字再问")
            return describe_speakers(speakers, "", visual, timeout_s, use_images=False)
        raw = _clean(resp.choices[0].message.content if resp and resp.choices else "")
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0)) if m else {}
    except Exception as exc:  # noqa: BLE001
        why = f"Strata 人物描述失败（{type(exc).__name__}: {str(exc)[:120]}）"
        print(f"[Strata 人物描述] {why}")
        return {}, why, False
    notes = {}
    for k, v in (data.items() if isinstance(data, dict) else []):
        mm = re.match(r"^\s*S?(\d+)\s*$", str(k))
        if mm and str(v or "").strip():
            notes[int(mm.group(1))] = str(v).strip()
    want = {n for n, *_r in speakers}
    notes = {n: v for n, v in notes.items() if n in want}
    why = (f"Strata 人物描述 {len(notes)}/{len(want)} 人（{'看了图' if seen else '只用文字'}，"
           f"{time.monotonic() - started:.1f} 秒）")
    print(f"[Strata 人物描述] {why}")
    return notes, why, seen


def polish_h3_with_people(rebuild, speakers: list, scene_image: str, visual: str, backend: str,
                          timeout_s: float = POLISH_TIMEOUT_S) -> tuple:
    """t150u: rebuild(notes) -> 提示词。先让 Strata 看图写人物描述，用描述重做提示词，再打磨。
    人物描述失败就用 rebuild(None)（画面描述里讲这个人的小句）。返回 (提示词, 说明)。"""
    notes, why1, _seen = describe_speakers(speakers, scene_image, visual, timeout_s) if speakers else ({}, "", False)
    try:
        prompt = rebuild(notes or None)
    except Exception as exc:  # noqa: BLE001
        print(f"[Strata 人物描述] 放进提示词失败（{exc}），不用描述")
        prompt, why1 = rebuild(None), why1 + "；没放进提示词"
    out, why2 = polish_video_prompt(prompt, backend, timeout_s)
    return out, "；".join(x for x in (why1, why2) if x)
