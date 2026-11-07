import json
import os
import re

import config_prompt

IMAGE_WORDS_SUMMERIZE_SYSTEM_PROMPT = """
把提供的图片中的文字内容，精简, 突出重点讲述层次 (主要是大幅度精简条目), 保持中文描述
"""

IMAGE_TO_VIDEO_SYSTEM_PROMPT = """
生成视频时, 始终保持画面中的文字内容

"""

SCREEN_CORE_PROMPT = (
    "You are an expert at capturing the absolute essence of a narrative. Your task is to extract the single most critical 'punchline' or 'finishing touch' (画龙点睛) from the provided content (speech, story, or scene description).\n"
    "This output will be displayed as HUGE text on a screen, so it must instantly convey the core point or theme of the scene at a glance.\n"
    "Strict Constraints:\n"
    "1. Language: Output MUST be in {language} only.\n"
    "2. Length: If {language} is Chinese, MUST NOT exceed 10 characters. If English, MUST NOT exceed 4-5 words.\n"
    "3. Style: Powerful, impactful, and ultra-concise. Eliminate all filler words, explanations, or conversational fluff.\n"
    "Output ONLY the final short phrase or sentence. Do not include any introductory text, quotes, or explanations."
)


SPEAKING_CONCISE_PROMPT = (
    "You are a text condenser. From the user's ORIGINAL content below, rewrite it in a very casual, spoken style.\n"
    "Output language: {language} ONLY.\n"
    "Keep only the main point. Use one sentence or two short sentences if needed. "
    "Keep it simple, clear, and conversational, like everyday chatting. "
    "Avoid formal or written tone. Use common, easy words. "
    "If the idea feels long, split it into two short sentences. "
    "Keep basic punctuation (periods, commas). "
    "Do not add anything else."
)


BUILD_CLEAR_STORIES_ON_CASE_STUDY_SUMMARIES_SYSTEM_PROMPT = """
ROLE:
    ** You are a psychological narrative architect specializing in trauma-informed storytelling and systemic relationship dynamics.
    ** Input-below are ONE original psychotherapy case-study material + several reference case-studies which are similar with it. Your task is to: start from the original case-study, refer all reference case-studies, to build a new fully developed, emotionally immersive, multi-scene psychological case-study.

OVERALL INSTRUCTIONS:
    ** Internally identify different psychological patterns across all case-studies.
	** Write like a compelling natural / vivid / detailed / immersive / emotionally engaging narrative, not a summary, that illustrates the psychological struggle
	** output in {language}

REQUIREMENTS FOR EACH STORY
	** New case-study must be a fully reconstructed, original story synthesized from orginal & reference case-studies (may with added creative detail). 
	** New Case-Study is NOT short-form content, SHOULD include multiple (3-5) scenes (progression, and emotional escalation), for example:
	   - Scene 1: Everyday life or relationship setup, and with a striking emotional moment, contradiction, or revealing behavior
	   - Scene 2: First conflict or tension
	   - Scene 3: Escalation (argument, avoidance, breakdown, or crisis)
	   - Scene 4: Key turning point or realization
	   - Scene 5 (optional): Aftermath or unresolved ending

	   * The tension must build across scenes, show how small patterns turn into bigger problems

	** Each scene should feel concrete and cinematic, not summarized, has rich Scene Details:
	   - Each scene must weave together an "Explicit Layer" (storyline) and an "Implicit Layer" (insight).
		   ** "Explicit Layer" (storyline): may include visual description, and the story character's speaking. 
		   ** "Implicit Layer" (insight): may include the narrator (psychological counselor)'s voiceover, to real: Core-issue /Root-causes /emotional triggers ( What truly afraid of) /Behavioral patterns (Why repeats?) /possible direction for change /etc
	   - Include specific environments (e.g., late-night apartment, office meeting, family dinner)
	   - Show actions, body language, silence, and emotional reactions
	   - Use brief dialogue where helpful
	   - Avoid jumping too quickly between ideas

	** Deep Characterization
	   - Clearly show personality traits, fears, desires, and contradictions
	   - Make the character feel psychologically real
	   - Highlight what the character wants vs. what they do
	   - Show repeated patterns (self-sabotage, avoidance, dependency, etc.)

OUTPUT FORMAT:

    Case-Study Title: [Emotionally compelling title]

            -----
            "scene": "Title (like: Break point)"
                    "explicit": 
                            "[Setting, atmosphere, story/dialogue, in {language}]"
                    "implicit": 
                            "[Counselor's voiceover]"

            -----
            "scene": "Title (like: Specific prominent event)"
                    "explicit": 
                            "[Setting, atmosphere, story/dialogue, in {language}]"
                    "implicit": 
                            "[Counselor's voiceover]"

            -----
            ...

---


Below are: 
    Original Case-Study: 
	--------------------
	    Title: {title}
		Summary: {story}
		
	Reference Case-Studies:
	-----------------------
	    {reference}
	...	

"""



SUMMARIZE_MATERIAL_SYSTEM_PROMPT = """
You are a professional YouTube content writer.

I will provide you with a complete or semi-complete story/script.

Your task is to write a concise and engaging YouTube video description (summary) based on the content.

Requirements:

Keep it short (3–6 sentences max)
Capture the core idea and emotional hook of the story
Highlight the main insight, conflict, or question
Make it intriguing so viewers want to click and watch
Use natural, conversational English (not overly formal)
Avoid unnecessary details or repetition

Optional:

You may end with 1 subtle hook question or thought-provoking line

Output only the final YouTube description. Do not explain your reasoning.
In {language}.
"""



YOUTUBE_PUBLISH_DESCRIPTION_PROMPT = """
Role:
You are an expert editor, narrative organizer, and counselor-minded storyteller specializing in psychological documentary-style narrative writing.

Task:

Read the provided source material below (voiceover, script, transcript, notes, or any mix).
Write a concise, compelling narrative description in {language}.
The output must express only the underlying human story, emotional conflict, and psychological essence.

Focus only on:

the lived human problem, question, or inner struggle at the center
the emotional wound, tension, or root cause beneath the surface
the key realization, turning point, or emotional shift
a subtle sense of insight, clarity, or inner resolution (if present)

Do NOT summarize mechanically or follow the structure of the source.

Critical rule:

Write about the human experience itself, not about any media form.
Do NOT mention or refer to:
“video”, “this video”, “episode”, “content”, “this content”, “this story”, “this narration”, “audience”, “viewer”, “we explore”, “this piece”, or any equivalent framing that describes an external media object.
Do NOT act as a commentator, reviewer, or introducer.
Do NOT describe what something “is about” as a product.
Instead, write as if the narrative is the experience itself, unfolding directly.

Writing style:

Natural, fluent, modern {language}.
Concise but emotionally powerful.
Psychological depth with narrative clarity.
No bullet points.
No hashtags.
No markdown headers.
No promotional or platform-related phrases.
No “subscribe” style endings.
Professional documentary / literary psychological tone.

Perspective rules:

Write from inside the human situation, not from outside observing it.
Focus on lived emotion, not explanation of structure.
Sound like a documentary synopsis or reflective psychological narration, not a media description.

Length:

80–180 words (or equivalent in {language}).
Prioritize emotional precision over completeness.

Output format:

Output only the final narrative description in {language}.
"""


YOUTUBE_SUMMARY_FROM_SCENES_PROMPT = """
You write the YouTube description for one video, in {language}.

The user message is the whole program, scene by scene: what is shown and what is said.

Write 5 or 6 sentences. No more. Not a paragraph longer than that.
Tell a viewer, in plain words, what this video is about: the subject, the situation, and where it arrives.
Do not retell every scene. Do not quote the script. Do not open with a title line.

No bullet points. No hashtags. No markdown. No "subscribe".
Output only those sentences in {language}.
"""




speaking_PROMPT = """
Condense the spoken content (given in user-prompt) into a clearer and VERY concise form while preserving the 1-2 key points from the content.
"""

PICTURE_STYLE = """
        **** FYI **** Generally, video/image is in '{style}' style &  '{color}' colors; the camera using '{shot}' shot, in '{angle}' angle.
"""


ANALYSIS_VIDEO_LIST = """
the uploaded txt file is a json list, each item in this list has "content" & "summary", please check "content" carefully, if it has a clearly a "心理冲突story", take the story out as a new field "story" in this item go through all the list, process one by one, and output a downloadable json
"""



# NotebookLM：由 downloader「Scene JSON → 指令」成功路径拆出的 slideshow / video 两段。
# 勿用 SLIDESHOW_GENERATION_INSTRUCTION 直接喂 NotebookLM：过程说明过多，易生成「如何做片」的技术报告而非故事画面。

NOTEBOOKLM_SLIDESHOW_MANDATE = """
You generate PICTURE illustrations, NOT text slides.
Each scene's ``show_this_content`` tells you WHAT to paint — setting, character emotion, action, and light.
** Consistent Visual_Style : {Visual_Style}
** Consistent Story-Character look (VERY VERY IMPORTANT!!!!) : {character}.
"""

NOTEBOOKLM_IMAGE_CHARACTER_EMPHASIS = """
** When ``actor`` / ``speaking`` are present: the protagonist MUST appear with facial expression, posture, gesture, and action that MATCH the emotional state in ``speaking`` and ``actor``.
** Use ``speaking`` only to infer mood and body language — NEVER render speaking lines as subtitles, captions, or speech bubbles (unless variant explicitly allows Word-in-image video).
** If ``actor`` is only ``讲员：名字``, there is no 人物. Mood, gesture, and camera direction are not people. Paint the narrator. ``speaking`` still must not become words on the image.
"""

NOTEBOOKLM_IMAGE_SLIDESHOW_INSTRUCTION = """
** Slideshow mode: exactly 1 image = 1 scene (one frozen moment per scene entry).
** Use ``show_this_content`` (+ Visual_Style) as painting direction. All JSON field values = staging cues, NOT text to render on the image.
** Output = one clean illustration per scene: environment + protagonist emotion + action + lighting tell the story visually.
** NEVER add onto the image: subtitles, caption paragraphs, small annotations, spreadsheet labels, or busy speech bubbles.
** If VERY CRITICAL highlighted info (very short) is ABSOLUTELY necessary, show as huge sparse background text only (transparent-like font).
** Read the row as one comic-strip frame: the picture shows what happens in that scene, including a change of angle or an action already written in ``visual``.
** ``actor`` lists people in order. ``<N>`` in ``speaking`` is that person's place in ``actor``; ``<0.5>`` style numbers are pauses. Paint who speaks and how they feel. Do not write the lines.
** 人物 entries are people of the story. ``讲员`` is a storyteller outside it: usually off the picture, and may step in at the edge of the frame when the 讲员 explains or sums up.
** If ``actor`` has no ``讲员``, do not invent a host in the frame.
"""

NOTEBOOKLM_IMAGE_SINGLE_INSTRUCTION = """
** Single-image mode: exactly ONE image for the entire Scene_Content block (all scenes combined into one master composition).
** Summarize the full story arc in one cinematic still: setting, protagonist, emotional through-line, and key motifs from every scene.
** Show emotional progression through expression, pose, symbolic props, and composition — NOT through written paragraphs on the image.
** Keep the same Visual_Style and consistent character look across the composite.
"""

NOTEBOOKLM_SLIDESHOW_IMAGE_INSTRUCTION = NOTEBOOKLM_IMAGE_SLIDESHOW_INSTRUCTION

# 幻灯提示窗只做幻灯片（slideshow）；"single" 只留给故事窗「场景总图」（build_scene_summary_image_prompt）。
_SLIDE_FLOW_TARGET_LABELS = {"single": "单图", "slideshow": "幻灯片"}
# 图片、幻灯、视频共用。去掉文字不是留一块白板。
FLOW_CAPTION_CHOICES = (
    ("keep", "保留"),
    ("erase", "去掉文字"),
    ("keywords", "关键字作背景"),
    ("express", "用画面讲"),
)
SLIDE_FLOW_TEXT_CHOICES = FLOW_CAPTION_CHOICES
SLIDE_FLOW_NARRATIVE_CHOICES = (
    ("narration", "讲述（用场景和背景文字讲；若有人物，人物不说话）"),
    ("story", "故事（人物在场景中表演对话）"),
    ("tech", "技术方案汇报"),
    ("exec", "高管简报"),
)
# 讲述及其两个变体（技术方案汇报、高管简报）：只有第三方讲员说话。旧的「叙事」存值 "narration" 就是讲述。
TELLING_NARRATIVES = ("narration", "tech", "exec")


def scene_content_label(narrative: str) -> str:
    """场景主要内容（来自 speaking 栏）在提示词里叫什么。只有故事叫 Dialogue。"""
    if narrative == "story":
        return "Dialogue"
    if narrative in ("tech", "exec"):
        return "Narration content"
    return "Scene narration"


def scene_content_key(narrative: str) -> str:
    """视频场景 JSON 里讲述类内容的字段名（故事仍用 speaking / voiceover）。"""
    return {"tech": "narration_content", "exec": "narration_content"}.get(narrative, "scene_narration")


# 叙事风格：这套幻灯片最终要表达什么，用什么形式表达。具体怎么用 visual、speaking、actor，见下面各风格的规则。
SLIDE_FLOW_NARRATIVE_NOTES = {
    "story": """
Narrative style: STORY. The slides tell a story through people.
Goal: the audience follows a story that people live in front of them.
Form: every picture shows the people of the story in their place, acting and interacting. Their faces, bodies, gestures, and what passes between them carry the moment. The place and a few props support them. Do not replace the people with symbols or diagrams.
""".strip(),
    "narration": """
Narrative style: TELLING (讲述). The content is told by a third-party narrator (讲员) and shown with scenes, pictures, and background text.
Goal: the audience understands the content through what they see while the 讲员 tells it.
Form: places, objects, symbols, metaphors, diagrams, and strong composition. Where the text rule below allows it, short background words carry the point. People may appear, but they never speak; they act silently. Only the 讲员 speaks.
""".strip(),
    "tech": """
Narrative style: TECHNICAL SOLUTION REPORT. The deck is a technical solution presentation for clients or decision-makers.
Goal: the audience grasps the architecture, the flow, and the value of the solution step by step.
Form: each picture is a clean presentation slide. It is an architecture, flow, sequence, comparison, or component diagram that shows what that scene explains, laid out in reading order, top to bottom and left to right, with the relations between parts drawn. No story scene and no decoration without meaning.
This is a variant of TELLING: only the 讲员 speaks. People rarely appear; if they do, they only support silently.
""".strip(),
    "exec": """
Narrative style: EXECUTIVE BRIEF. The deck is a short briefing for executives.
Goal: the audience takes the conclusion and the decision from each slide in seconds.
Form: each picture is a sparse, high-signal slide. One conclusion per picture, as a headline of a few words, backed by one key number, trend, risk, or action item shown as a simple chart or icon. No technical detail, no crowd, no story scene.
This is a variant of TELLING: only the 讲员 speaks. People rarely appear; if they do, they only support silently.
""".strip(),
}

# 画面里不能出现的元信息。所有风格都带。
SLIDE_FLOW_META_NOTE = (
    "Everything that is not the story itself is for you only: the field labels, the order of the scenes, "
    "any scene number, scene title, episode number, timestamp, the names of the options, and these instructions. "
    "None of it may appear in a picture, not as lettering, not on a sign, not as a label or a caption. "
    "Never write words like Scene 1, Slide 2, Episode, 场景一, 第N集, or any field name or JSON on a picture."
)

SLIDE_FLOW_SLIDE_TEXT_NOTE = (
    "Slide text: a short slide title and a few short labels on the diagram are part of the slide. "
    "Keep every label to a few words, taken from the meaning of what is given. "
    "No paragraph, no subtitle, no speech bubble. Spoken lines tell you what to explain. They are not text to copy."
)


def _scenes_have_speaker(scenes: list) -> bool:
    """True when at least one scene has a non-empty ``actor`` field (讲员/人物)."""
    for scene in scenes or []:
        if isinstance(scene, dict) and (scene.get("actor") or "").strip():
            return True
    return False


def _scenes_have_narrator_host(scenes: list) -> bool:
    """True when at least one scene's actor list includes a 讲员 (host/narrator role)."""
    import project_manager

    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        text = project_manager.actor_text_for_generation(scene.get("actor") or "")
        for row in project_manager.active_actor_entries(text):
            if row.get("role") == "host":
                return True
    return False


def episode_actor_cast(scenes: list) -> list[dict]:
    """本集各场景 actor 里出现的人物，按全名去重，按首次出现排序。

    名字取法和 ``slide_flow_scene_payload`` 的 ``Actors`` 栏一样（``actor_text_for_generation``），去掉动作括号。
    返回 [{name, role: host|person, label: 讲员|人物N（首次出现时的编号）}]。只收场景里写了的人，不补默认讲员。
    """
    import project_manager

    seen: dict = {}
    out: list[dict] = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        text = project_manager.actor_text_for_generation(scene.get("actor") or "")
        for row in project_manager.active_actor_entries(text):
            body, _motion = project_manager.split_actor_motion((row.get("body") or "").strip())
            body = body.strip()
            if not body or project_manager.actor_is_absent(body):
                continue
            role = "host" if row.get("role") == "host" else "person"
            if body in seen:
                if role == "host":  # 同一个名字既当讲员又当人物：按讲员算
                    out[seen[body]]["role"] = "host"
                continue
            seen[body] = len(out)
            out.append({"name": body, "role": role, "label": row.get("label") or ""})
    return out


def notebooklm_actor_reference_note(
    name: str, output: str, narrative: str, content_name: str = "content.pdf", silent: bool = False,
    episodes: list | None = None,
) -> str:
    """全集生成：actor.pdf 是本集人物（全名 + 形象图）。语音概览只用名字和身份。

    ``silent``：讲述 / 汇报没有讲员，名单在 ``人物（不说话，只表演）/ Silent actors`` 栏，这些人只表演不说话。
    """
    span_zh, span_en = episode_span_labels(episodes)  # 跨集时「第 X–Y 集的内容」，单集照旧「本集内容」
    field = "人物（不说话，只表演）/ Silent actors" if silent else "人物 / Actors"
    short = SILENT_ACTORS_FIELD if silent else "Actors"
    lines = [
        f"{content_name} 是{span_zh + '的内容' if span_zh else '本集内容'}；{name} 是这些内容里出场 / 讲话的人物：每人一页，写着全名和形象图。",
        f"{content_name} is {'the content of ' + span_en if span_en else 'the episode content'}; "
        f"{name} contains the people who appear or speak in this content: "
        "each one's full name and appearance image, one person per page.",
    ]
    if output == "audio_overview":
        lines.append(
            f"For this audio, use {name} only for each person's name and role (讲员 = the host, 人物 = the other people). "
            "Ignore the images; never describe how anyone looks or mention a picture."
        )
        if silent:
            lines.append(
                "These people never speak in this audio; only the narrator speaks and may mention them by name and role. "
                "Do not invent a host or any other speaker."
            )
    else:
        lines.extend([
            f"When a scene needs a person, look at that scene's {field} entry in {content_name}. "
            f"If that person's full name is in {name}, match the name to its image and draw the person with exactly that look: "
            "the same face, hair, age, and clothes in every scene. Never invent another look for them.",
            f"A person written \"no image\" in {name} has no picture; follow the name (gender / age / origin) in {short} and keep that look consistent.",
            f"Only people listed in that scene's {short} appear in that scene. {name} does not add anyone to a scene.",
        ])
        if silent:
            lines.append(
                "Telling / report with no 讲员: the narration is an off-screen voice and no 讲员, narrator, host, or presenter "
                "is drawn. The listed people appear only in their scenes and act silently, never speaking."
            )
        elif narrative == "story":
            lines.append("Story: the listed characters act and talk to each other; the 讲员, if listed, is outside the story.")
        else:
            lines.append(
                "Telling / report: the 讲员 appears on camera only in scenes whose Actors list the 讲员; "
                "the other listed people act silently. Never add a default 讲员 that is not listed."
            )
    lines.append(f"The names and labels in {name} are for you only; never show or read out the page headings.")
    return "\n".join(lines)


SILENT_ACTORS_FIELD = "Silent actors"
SILENT_ACTORS_INPUT_NOTE = (
    "- ``Silent actors`` (人物（不说话，只表演）): the people in that scene, joined by |. "
    "They appear in that scene and act silently. They never speak."
)
SILENT_CAST_RULE = (
    "The people in ``Silent actors`` appear only in their own scenes and act silently: "
    "no lines, no talking mouths, no speech bubbles. The narration is an off-screen voice. "
    "No 讲员, narrator, host, or presenter is drawn. Never add a 讲员 or anyone who is not listed."
)


def prompt_silent_cast(narrative: str, use_actor: bool, scenes: list) -> bool:
    """全集生成：讲述 / 汇报，勾了人物，但本集没有一场写了讲员，场景里却有人物。

    这时 ``_prompt_has_speaker`` 为 False（讲员在画外），人物照样写进 content.pdf / actor.pdf，
    标成「不说话，只表演」。只给全集生成（幻灯 / 信息图 / 语音 / 视频概览）用；图片提示、生场视频不用。
    """
    if not use_actor or narrative not in TELLING_NARRATIVES:
        return False
    if _scenes_have_narrator_host(scenes):
        return False
    return bool(episode_actor_cast(scenes))


def prompt_has_cast(narrative: str, use_actor: bool, scenes: list) -> bool:
    """全集生成要不要 actor.pdf / Actor_Reference：会说话的名单（Actors）或不说话的名单（Silent actors）。"""
    return _prompt_has_speaker(narrative, use_actor, scenes) or prompt_silent_cast(narrative, use_actor, scenes)


def _prompt_has_speaker(narrative: str, use_actor: bool, scenes: list) -> bool:
    """Whether ``Actors`` goes into this prompt.

    - 讲述 / 技术方案汇报 / 高管简报: only when actor is checked AND a 讲员 is listed
      (the 讲员 then appears on camera; without one the 讲员 is an off-screen voice).
    - 故事: when actor is checked AND any actor entry is non-empty.
    """
    if not use_actor:
        return False
    if narrative in TELLING_NARRATIVES:
        return _scenes_have_narrator_host(scenes)
    return _scenes_have_speaker(scenes)


def _slide_flow_inputs_note(visual: bool, speaking: bool, actor: bool, keywords: bool, narrative: str = "story") -> str:
    """这一次给了哪几项，每一项叫什么。场景主要内容总是来自讲话栏。"""
    lines = ["Each scene gives only these fields:"]
    if visual:
        lines.append("- ``Shown``: the scene description: place, action, and camera angle.")
    if speaking:
        if narrative == "story":
            text = "- ``Dialogue`` (讲话): the main content of the scene, said by the characters to each other."
            if actor:
                text += (
                    " ``<1>``, ``<2>``, ``<3>`` mark who speaks: the number is that person's place in ``Actors``. "
                    "The same person keeps talking until the next ``<N>``. "
                    "A number with a decimal point such as ``<0.5>`` is a pause in seconds, nobody speaks."
                )
        else:
            label = scene_content_label(narrative)
            zh = "讲述内容" if narrative in ("tech", "exec") else "场景叙事"
            text = (
                f"- ``{label}`` ({zh}): the main content of the scene, told by the 讲员. "
                "It is narration, never lines for anyone in the picture."
            )
        lines.append(text)
    if actor:
        lines.append(
            "- ``Actors``: the people, in order, joined by |. Place 1 is the first entry, place 2 the second, "
            "and so on. ``讲员`` is the host. ``人物1``, ``人物2`` and so on are the other people. "
            "A person not listed here is not one of them."
        )
    if keywords:
        lines.append(
            "- ``Keyword hint``: a hint for the scene's one keyword. If it is longer than "
            f"{KEYWORD_MAX_ZH} Chinese characters or {KEYWORD_MAX_EN_WORDS} English words, compress it to that limit. "
            "It is the only text that may appear, blended into the scene."
        )
    lines.append("No other field is given.")
    return "\n".join(lines)


def narrative_mode_text(narrative: str, actor_checked: bool) -> str:
    """叙事风格 + 「人物」勾选 → 一句话，提示窗里显示。讲员有没有要看场景里的 actor，所以写成「若…否则…」。"""
    if narrative == "step":
        return ("提取第 N 步：把封面 / 信息图里第 N 步那一格单独画成一张新的场景图，其他格、编号、箭头都去掉；"
                "N = 当前场景序号。只看画风改变和说明文字（只管这一步的字），写进提示词的选项不用。")
    if narrative == "story":
        if actor_checked:
            return ("故事：人物在场景中表演对话（套用 actor 形象）。若人物中有讲员，讲员为辅，"
                    "开头介绍或结尾总结、过渡、提问；否则没有讲员。"
                    "单回合 <Ns> 自言自语是该人物内心独白（画外心声、嘴巴不动）。")
        return "故事：人物在场景中表演对话，人物自由虚构，无讲员。单回合 <Ns> 是该人物内心独白（画外心声、嘴巴不动）。"
    head = {
        "tech": "技术方案汇报（讲述的一种）：架构 / 流程图和背景文字讲，人物很少且不说话。",
        "exec": "高管简报（讲述的一种）：每场一个结论＋一个数字或图标，人物很少且不说话。",
    }.get(narrative, "")
    if actor_checked:
        tail = "若人物中有讲员，讲员出镜叙述，其他人物只表演不说话；否则讲员在画外旁白。"
    else:
        tail = "讲员在画外旁白，画面中人物不说话。"
    if head:
        return head + tail
    if actor_checked:
        return "讲述：" + tail
    return "讲述，无讲员出镜：讲员在画外旁白，场景、画面和背景文字表达内容，画面中人物不说话。"


def _slide_flow_story_rules(visual: bool, speaking: bool, actor: bool) -> str:
    """故事：人物在场景中表演对话。actor 里有讲员时讲员为辅；没有就纯人物表演。"""
    keep = "Keep each person's face and clothes the same from scene to scene."
    no_host = "Pure character performance: there is no 讲员, no host, no narrator, and no voice-over."
    if not actor:
        lines = [
            "Story style: the characters act and talk with each other inside the scene."
            + (" The dialogue comes from ``Dialogue``." if speaking else ""),
            "No actor list was given. Invent the characters the story needs.",
            no_host,
        ]
        if visual:
            lines.append("``Shown`` gives the place, the look, and the camera." + (
                " Where ``Shown`` is silent, take it from ``Dialogue``." if speaking else ""))
        lines.append(keep)
        return "\n".join(lines)
    lines = [
        "Story style: the characters act and talk with each other inside the scene."
        + (" The dialogue comes from ``Dialogue``." if speaking else ""),
        "``Actors`` is the cast. Each listed person uses their own character image: look, gender, age band, and ethnicity. The portrait id is the text before the parentheses. The parentheses are that person's emotion and action in this scene; follow them, and do not treat them as part of the id.",
        "The 人物 entries are IN the scene, in the story's place, acting and talking.",
    ]
    if visual:
        lines.append("Put the actors inside the ``Shown`` scene. Follow its place, action, and camera angle.")
    elif speaking:
        lines.append("Invent the place and the action from ``Dialogue``.")
    if speaking:
        lines.append(
            "A line marked with a 人物's number is said by that person inside the story: show that person talking "
            "and the others listening or reacting."
        )
    lines.append("If ``Actors`` has no 讲员: " + no_host)
    lines.append(
        "If ``Actors`` includes a 讲员: the story characters lead and do the talking. The 讲员 is supporting and "
        "stands outside the story. He or she may appear on camera at the start to introduce, or at the end to sum up, "
        "bridge to what comes next, or ask the audience a question. A line marked with the 讲员's number is that "
        "introduction or closing, not something a story character says. The 讲员 never takes over the story and stands "
        "clearly apart from the story people: at the edge of the frame, in the foreground, or as a small inset."
    )
    lines.append("If ``Actors`` lists only the 讲员 and no 人物, invent the story people from the content.")
    lines.append(keep)
    return "\n".join(lines)


def _slide_flow_narration_rules(visual: bool, speaking: bool, actor: bool) -> str:
    """讲述：只有第三方讲员说话。actor 为真表示 actor 里有讲员（讲员出镜）；否则讲员在画外旁白。"""
    lines = [
        "Telling style: only the third-party 讲员 speaks."
        + (" ``Scene narration`` is the 讲员's narration." if speaking else ""),
        "Nobody in the picture speaks: no dialogue, no talking mouths, no speech bubbles. "
        "People, if any, act silently.",
    ]
    if visual:
        lines.append("``Shown`` gives the place, the look, and the camera.")
    elif speaking:
        lines.append("Invent the scenes, objects, and background that carry the narration.")
    if not actor:
        lines.append(
            "The 讲员 is off screen: a voice-over only. Do not draw a narrator, host, or presenter. "
            "The scenes, the pictures, and the background text carry the content."
        )
    else:
        lines.append(
            "The 讲员 listed in ``Actors`` appears on camera and narrates, with that entry's look. "
            "The other listed people act silently in the scene, each with their own character image. "
            "Around the 讲员, the picture illustrates what is being told."
        )
    return "\n".join(lines)

def _slide_flow_report_rules(visual: bool, speaking: bool, actor: bool) -> str:
    """技术方案汇报 / 高管简报：讲述的变体。actor 为真表示 actor 里有讲员（讲员出镜汇报）。"""
    lines = ["This is a variant of telling. Only the 讲员 speaks."]
    if visual:
        lines.append("``Shown`` says what the slide shows. Use it as content for the diagram, not as a photograph to paint.")
    if speaking:
        lines.append(
            "``Narration content`` is the point the slide must make, told by the 讲员. "
            "Put that point on the slide as a diagram, a chart, and short labels."
        )
    lines.append("People rarely appear. If they do, they only support, small and silent.")
    if not actor:
        lines.append("The 讲员 is off screen: a voice-over only. No presenter is drawn.")
    else:
        lines.append(
            "The 讲员 listed in ``Actors`` appears on camera as the presenter, small beside the slide, pointing at it "
            "while narrating. Nobody else speaks. The slide stays the main thing."
        )
    return "\n".join(lines)


def slide_flow_scene_payload(
    scenes: list,
    *,
    use_visual: bool,
    use_speaking: bool,
    use_actor: bool,
    keywords: bool,
    narrative: str = "story",
    silent_cast: bool = False,
) -> list[dict]:
    """幻灯/图片提示用的场景内容：只留用户勾选的项。

    ``silent_cast``（只有全集生成会给）：不写 ``Actors`` 时，改写一行 ``Silent actors``（不说话的人物）。

    讲话栏是场景的主要内容：故事里叫 ``Dialogue``；讲述类叫 ``Scene narration`` / ``Narration content``，并去掉 ``<N>``。
    没有 actor 时，speaking 里的 ``<N>`` 说话人标记一起去掉。
    """
    telling = narrative in TELLING_NARRATIVES
    content_label = scene_content_label(narrative)
    out: list[dict] = []
    for scene in scenes:
        base = _notebooklm_scene_content_base(scene)
        lines: list[str] = []
        caption = short_keyword_hint(base.get("caption") or "")
        if keywords and caption:
            lines.append(f"Keyword hint: {caption}")
        vis = (base.get("visual") or "").strip()
        if use_visual and vis:
            lines.append(f"Shown: {vis}")
        actor = (base.get("actor") or "").strip()
        if use_actor and actor:
            lines.append(f"Actors: {actor}")
        elif silent_cast and actor:
            lines.append(f"{SILENT_ACTORS_FIELD}: {actor}")
        if use_speaking:
            speaking = (base.get("speaking") or base.get("story_content") or "").strip()
            voiceover = (base.get("voiceover") or "").strip()
            if not use_actor or telling:
                speaking = strip_speaker_marks(speaking, pauses=True)
                voiceover = strip_speaker_marks(voiceover, pauses=True)
            if telling:
                combined = " ".join(p for p in (speaking, voiceover) if p).strip()
                if combined:
                    lines.append(f"{content_label}: {combined}")
            else:
                if speaking:
                    lines.append(f"Dialogue: {speaking}")
                if voiceover:
                    lines.append(f"Also dialogue: {voiceover}")
        out.append({"show_this_content": "\n".join(lines)} if lines else {})
    return out


def slide_flow_choice_label(
    target: str,
    text: str,
    visual: bool = True,
    speaking: bool = True,
    actor: bool = False,
    narrative: str = "story",
) -> str:
    """把这一次的选择写成一行，给人看。"""
    narrative_label = dict(SLIDE_FLOW_NARRATIVE_CHOICES).get(narrative, narrative).split("（")[0]
    target_label = _SLIDE_FLOW_TARGET_LABELS.get(target, target)
    fields = [name for name, on in (("visual", visual), ("speaking", speaking), ("actor", actor)) if on]
    parts = [narrative_label, target_label, "+".join(fields)]
    if narrative not in ("tech", "exec"):
        parts.append(dict(FLOW_CAPTION_CHOICES).get(text, text))
    return " · ".join(parts)


# 全集生成（NotebookLM Studio）四种产物都用的讲述规则，放在提示词最前面。
NOTEBOOKLM_SPEAKER_RULE = (
    "讲述方式（必须遵守）：\n"
    "- 即使下面的内容用了文章式的编号或结构（一、二、三 / 1. 2. 3. / 小标题），也不要照着念，不要像汇报一样逐条展开；要像一个人在自然地讲解、和大家聊这件事。\n"
    "- 绝对不要提「材料」「资料」「来源」「文档」「提供的内容」之类的词，不要说「根据材料」「资料里说」。\n"
    "- 把这些想法当成讲述者自己的亲身经历、思考和观点，用第一人称，从自己心里说出来，和听众分享、讨论。\n"
    "How to speak (must follow):\n"
    "- Even if the content below uses article-style numbering or structure (一、二、三 / 1. 2. 3. / headings), do not read it out or walk through it like a report. Speak naturally, like a person explaining and discussing.\n"
    "- Never mention \"the material\", \"the source\", \"the document\" or \"what we were given\".\n"
    "- Present the ideas as the speaker's own first-person experience, thinking and views, shared and discussed with the audience from their own mind."
)
# 语音概览 / 视频概览：讲出来的内容要口语化、层层推进，不列点、不编号。替换 NOTEBOOKLM_SPEAKER_RULE 的第一条（中英各一条）。
NOTEBOOKLM_SPOKEN_FLOW_ZH = (
    "- 口语化、层层推进地讲：像一个人在和朋友聊天，一层接一层往下说，前一句自然带出后一句，生动、有来有往，不像在念文件。\n"
    "- 绝对不要列点、不要编号：不说「有几点」「我们有几点」「分为几个方面」「第一点 / 第二点」「第一、第二」「一是……二是……」，"
    "也不用「一、二、三」「1. 2. 3.」之类的编号或项目符号；不要先预告要讲几点，最后也不要「总结一下这几点」。\n"
    "- 即使下面的内容本身是编号、小标题或要点的结构，也只取它的意思，用说话的方式串起来，不要照着念，不要像做汇报那样逐条展开。\n"
    "- 用口语的过渡把内容串起来，比如「首先」「那接下来我们又……」「然后呢」「说到这儿」「你可能会想」「更有意思的是」「最后」，"
    "每次换着用，不要每一场都机械地用「首先 / 然后」开头。\n"
    "- 不要报场景号或段号（不说「第一场」「第二段」「下一部分」），场景之间靠内容和过渡自然衔接。\n"
    "- 技术方案汇报、高管简报也一样：讲清楚先后和关系，但用说话的口气一步步带过去，不列条目。\n"
)
NOTEBOOKLM_SPOKEN_FLOW_EN = (
    "- Speak conversationally and build up layer by layer, like a person talking with friends: each thought leads naturally into the next. "
    "Keep it lively and engaged, never like reading a document.\n"
    "- Never list or number anything: do not say \"there are a few points\", \"we have several points\", \"this falls into N aspects\", "
    "\"point one / point two\", \"first, second, third\" as a list, or \"one is... two is...\"; never use 一、二、三, 1. 2. 3., or bullets. "
    "Do not announce how many points are coming, and do not end with \"to sum up these points\".\n"
    "- Even if the content below is numbered, headed, or laid out as bullet points, take only its meaning and tell it as speech; "
    "do not read it out or walk through it item by item like a report.\n"
    "- Link the ideas with spoken transitions such as 首先 (to start), 那接下来我们又… (and then we…), 然后呢 (and then), 说到这儿 (speaking of which), "
    "你可能会想 (you might wonder), 更有意思的是 (what is even more interesting), 最后 (finally). Vary them; do not open every scene with the same 首先 / 然后.\n"
    "- Do not announce scene or segment numbers (no \"scene one\", \"the second part\", \"next section\"); let the content and the transitions carry the move from one scene to the next.\n"
    "- The same holds for a technical solution report or an executive brief: make the order and the relations clear, but walk through them in a speaking voice, never as a list of items.\n"
)
_SPEAKER_RULE_FIRST_ZH = (
    "- 即使下面的内容用了文章式的编号或结构（一、二、三 / 1. 2. 3. / 小标题），也不要照着念，不要像汇报一样逐条展开；要像一个人在自然地讲解、和大家聊这件事。\n"
)
_SPEAKER_RULE_FIRST_EN = (
    "- Even if the content below uses article-style numbering or structure (一、二、三 / 1. 2. 3. / headings), do not read it out or walk through it like a report. Speak naturally, like a person explaining and discussing.\n"
)


def notebooklm_speaker_rule(output: str) -> str:
    """语音概览 / 视频概览把第一条换成 NOTEBOOKLM_SPOKEN_FLOW_*；幻灯片、信息图原样。"""
    rule = NOTEBOOKLM_SPEAKER_RULE
    if output in ("audio_overview", "video_overview"):
        if _SPEAKER_RULE_FIRST_ZH in rule and _SPEAKER_RULE_FIRST_EN in rule:
            rule = rule.replace(_SPEAKER_RULE_FIRST_ZH, NOTEBOOKLM_SPOKEN_FLOW_ZH).replace(
                _SPEAKER_RULE_FIRST_EN, NOTEBOOKLM_SPOKEN_FLOW_EN
            )
        else:  # 第一条被改过时，仍把口语规则放在最前
            rule = NOTEBOOKLM_SPOKEN_FLOW_ZH + NOTEBOOKLM_SPOKEN_FLOW_EN + rule
    return rule


NOTEBOOKLM_VISUAL_RULE = (
    "- 幻灯片和信息图上也不要出现「材料中的第一点」「资料指出」这类说法；画面上若有文字（标题或关键词），也用第一人称、自己的视角来写。\n"
    "- Slides and infographics: no \"point one of the material\" style wording; any text that does appear (a title or a keyword) keeps the first-person, own-perspective framing."
)
NOTEBOOKLM_OUTPUT_LEADS = {
    "slides": "产物：演示文稿（每场一页幻灯片）。Output: a slide deck, one slide per scene.",
    "infographic": "产物：一张信息图，把全集内容按场景顺序排在一张图里。Output: one infographic that lays out all scenes in order.",
    "audio_overview": (
        "产物：语音概览（只有声音，没有幻灯片和画面）。下面写的画面要求只用来帮助理解每一场的情景，"
        "要把它们讲出来，不要描述「图片」或「幻灯片」。Output: an audio overview (sound only, no slides or pictures). "
        "The picture notes below only explain each scene; turn them into spoken storytelling and never talk about images or slides."
    ),
    "video_overview": (
        "产物：视频概览。按场景顺序讲，画面配合讲的内容。Output: a video overview that follows the scenes in order, "
        "with visuals that support what is being said."
    ),
}


# 全集生成：产物和 content.pdf 场景一一对应（放在 Output_rules 里，紧跟产物说明）。语音概览不加。
NOTEBOOKLM_SCENE_ORDER_RULES = {
    "slides": (
        "场景对应（必须遵守）：\n"
        "- 幻灯片的页数 = content.pdf 的场景数。第 N 页就是场景 N，顺序和 content.pdf 一样。\n"
        "- 每页只对应一场：不合并两场，不把一场拆成两页，也不加任何额外的页：没有封面页、标题页、目录 / 议程页、过渡页、小结 / 总结页或结尾页。\n"
        "Scene mapping (must follow):\n"
        "- The number of slides equals the number of scenes in content.pdf. Slide N is scene N, in the same order as content.pdf.\n"
        "- Each slide is exactly one scene: never merge two scenes, never split one scene across slides, and never add an extra slide: "
        "no cover, title, agenda / table-of-contents, transition, summary / recap, or closing slide."
    ),
    "video_overview": (
        "场景对应（必须遵守）：\n"
        "- 按 content.pdf 的场景顺序，一场一段：第 N 段就是场景 N。不跳场、不合并、不调换顺序，也不另加开场概述段或结尾总结段；"
        "讲员（若有）开头或结尾的几句，放在第一场或最后一场那一段里。\n"
        "Scene mapping (must follow):\n"
        "- Follow the scene order of content.pdf, one segment per scene: segment N is scene N. Do not skip, merge, or reorder scenes, "
        "and do not add a separate overview intro or summary outro; any opening or closing lines of the 讲员 belong inside the first or last scene's segment."
    ),
    "infographic": (
        "场景对应（必须遵守）：\n"
        "- 信息图按 content.pdf 的场景顺序排列（场景 1 在最前），每场一个部分，不合并、不调换顺序，也不另加总结或目录部分。\n"
        "Scene mapping (must follow):\n"
        "- Lay the infographic out in the scene order of content.pdf (scene 1 first), one section per scene. "
        "Do not merge or reorder scenes, and do not add an extra summary or table-of-contents section."
    ),
}

# 全集生成：content.pdf 里带了场景图片时才加。{unit_zh} / {unit_en} 是产物（幻灯片 / 信息图 / 视频）。
NOTEBOOKLM_SCENE_IMAGE_RULE = (
    "场景图片（必须遵守）：content.pdf 里有些场景带一张场景图片。它只是这一场的视觉参考，用来给你思路和方向：气氛、场所、构图的提示。"
    "不要照抄、不要复刻这张图，也不要把它贴进{unit_zh}；按上面的画面风格规则，重新画出新的画面。\n"
    "Scene images (must follow): some scenes in content.pdf include a scene image. It is ONLY a visual reference for that scene's "
    "idea and direction: mood, setting, and composition hints. Do NOT copy or reproduce it, and do not paste or insert it into {unit_en}; "
    "create new visuals that follow the style rules above."
)
NOTEBOOKLM_SCENE_IMAGE_ACTOR_PRIORITY = (
    "人物的长相以 actor.pdf 的形象图为准：场景图片里的人和 actor.pdf 不一样时，照 actor.pdf 画。\n"
    "For people's faces and looks, actor.pdf takes priority over the scene images: if a person in a scene image looks different "
    "from their actor.pdf image, follow actor.pdf."
)
_SCENE_IMAGE_UNITS = {
    "slides": ("幻灯片", "the slides"),
    "infographic": ("信息图", "the infographic"),
    "video_overview": ("视频", "the video"),
}


# t199u: 「关键字作背景」不是对话：绝不能画成漫画对话泡泡 / 字幕 / 整句。所有关键字路径共用。
KEYWORD_COUNT_ZH = "1 到 2 个关键词（最多 3 个），每个只有几个字（中文最多 4 个字，英文 1 到 2 个词）"
KEYWORD_COUNT_EN = "1 to 2 keywords (3 at most), each only a few characters (at most 4 Chinese characters, or 1 to 2 English words)"
NO_BUBBLE_ZH = ("绝对不要对话泡泡、说话气泡、思想泡泡、漫画分格、字幕、旁白框或标题；不写整句话，不把讲话 / 对白内容写到画面上。"
                "讲话是说出来的，不是写出来的。")
NO_BUBBLE_EN = ("Absolutely NO speech bubbles, dialogue balloons, thought bubbles, comic panels, captions, subtitles, "
                "narration boxes or titles; no full sentences, and never write the spoken lines or dialogue onto the picture. "
                "Speech is heard, not written.")


REMOVE_BUBBLES_EN = ("Remove every speech bubble, thought balloon, caption box and dialogue text already in Image 1, "
                     "repainting the area behind them (continue the background, people and objects there).")
REMOVE_BUBBLES_ZH = "把图 1 里已有的对话泡泡、思想泡泡、字幕框和对白文字全部去掉，并把它们后面的画面补画完整。"


# t126u: 关键词放哪里（所有「关键字作背景」共用）：长在环境里；实在不行才用一块融进场景的半透明板。
KEYWORD_PLACE_ZH = (
    "- 关键词要像这个场景本来就有的东西，用场景里的材质、光线和透视做出来，字大，和整幅画用同一种画风（写实时就是真实存在、被拍下来的字）：\n"
    "  · 木桌、木门、木柜上：刻进木纹里的木刻字，有刀痕、凹槽和木头的阴影。\n"
    "  · 墙上：嵌进墙面的大字（浮雕、砖石刻字、斑驳的老墙字），或写在挂着的字画、卷轴、匾额上。\n"
    "  · 招牌、木牌、路牌、门牌上：刻上或漆上的字；或写在贴着 / 夹着 / 飘着的纸条、便签、信纸上。\n"
    "  · 天空里：由云自然聚成的字。\n"
    "  · 水面、沙地、雪地、玻璃上的雾气里：写在 / 印在这些表面上。\n"
    "  · 没有合适的表面时：半透明、朦胧的大字，从灯光、光束、烟雾、水雾或一阵风（被风吹起的光痕、落叶、尘沙）里飘出来，柔和，像被灯照亮的真实雾气。\n"
    "- 字要大，在画面里一眼能看见、能读出来；它是场景的一部分，不是贴上去的标签或字幕框。\n"
    "- " + NO_BUBBLE_ZH
)
KEYWORD_PLACE_EN = (
    "- Make each keyword look like it already belongs to the scene, crafted from the scene's own material, light and "
    "perspective. LARGE lettering in the same art style as the whole picture (under a realistic style: real, physical lettering photographed in the scene):\n"
    "  · On a wooden table, door or cabinet: carved into the wood grain, with chisel marks, grooves and wood shadows.\n"
    "  · On a wall: large characters inlaid or carved into the wall (relief, stone or brick carving, weathered old wall "
    "lettering), or brushed on a hanging painting, scroll or plaque.\n"
    "  · On a shop sign, wooden board, road sign or door plate: carved or painted on it; or written on a paper note, "
    "sticky note or letter pinned, tucked or drifting in the scene.\n"
    "  · In the sky: characters formed naturally by clouds.\n"
    "  · On water, sand, snow, or misted glass: written or pressed into that surface.\n"
    "  · With no suitable surface: large, semi-transparent, hazy characters drifting out of lamplight, a light beam, "
    "smoke, steam, water mist or a gust of wind (wind streaks, swirling leaves or dust), soft, like real lamp-lit mist.\n"
    "- Big enough to read at a glance. It is part of the scene, never a label or caption box.\n"
    "- " + NO_BUBBLE_EN
)
KEYWORD_PLACE_SHORT_EN = (
    "Make the keyword part of the scene, LARGE, in the picture's own art style, from the scene's own material and light: carved into wood "
    "grain on a wooden table; inlaid into a wall or brushed on a hanging scroll, painting or plaque; formed by clouds in "
    "the sky; or, with no suitable surface, large semi-transparent hazy characters drifting out of lamplight or smoke like "
    "lit mist, water mist or wind streaks; or carved / painted on a sign, or written on a paper note. Follow perspective and lighting; never a label or caption box. "
    + NO_BUBBLE_EN
)


# t175u: 画风写在最前面并在最后重复（NotebookLM 信息图 / 幻灯 / 视频一句埋在中间的画风经常被忽略）。
def is_realistic_style(style: str) -> bool:
    s = (style or "").strip().lower()
    return (not s) or "realistic" in s or "写实" in s or "寫實" in s


def art_style_block(style: str, output: str = "", *, reminder: bool = False) -> str:
    """画风硬规则。写实时明确排除插画 / 卡通 / 绘画；其他画风只要求全程同一种。"""
    style = (style or "").strip() or "写实 (Realistic)"
    unit = {"infographic": "the infographic", "slides": "every slide", "video_overview": "every visual of the video"}.get(
        output, "every picture")
    if is_realistic_style(style):
        zh = ("画风（必须遵守）：照片级写实，像真实拍摄的照片 / 电影剧照：真实的人、真实的皮肤和材质、自然光。"
              "不是插画，不是卡通，不是三维动画 / 皮克斯风格，不是绘画、水彩、动漫，也不是扁平矢量图标风。")
        en = (f"Art style (must follow): photorealistic, like real photographs / cinematic film stills, for {unit}: "
              "real people with real skin and real materials, natural lighting, real camera depth of field. "
              "NOT illustration, NOT cartoon, NOT 3D animation or Pixar style, NOT painting, watercolor or anime, "
              "NOT flat vector icon art.")
        extra = ("Keywords under this style are physically real things photographed in the scene: letters really carved "
                 "into wood, inlaid in stone, a real neon or lit sign, real steam or mist lit by a lamp. Never painted, "
                 "drawn or cartoon lettering. A scene style (for example Dream) only changes the light and mood; the "
                 "picture stays a photograph.")
        if output == "infographic":
            extra += " The infographic is a layout of photo-real scene stills, not drawn icons or illustrations."
    else:
        zh = f"画风（必须遵守）：{style}。所有画面只用这一种画风，不混用别的画风。"
        en = (f"Art style (must follow): {style}, for {unit}. Use only this one style everywhere; "
              "keywords are rendered in the same style as the picture.")
        extra = ""
    head = "Reminder — art style again (overrides anything above): " if reminder else ""
    return head + zh + "\n" + en + ("\n" + extra if extra else "")


# t125u: 信息图每个场景部分：不要「第N幕 / Scene N」之类的编号，改成融进环境的核心关键词。
INFOGRAPHIC_NO_INDEX_RULE = (
    "- 信息图不要任何编号或序号标签：不写「第1幕 / 第一场 / 场景1 / 第N集 / Scene 1 / Act 1 / Part 1 / 01」，"
    "也不要数字角标或步骤编号。场景顺序只靠排列体现。\n"
    "- No numbering or index labels anywhere on the infographic: never write 第1幕, 第一场, 场景1, 第N集, Scene 1, Act 1, "
    "Part 1, Step 1, 01 or a number badge. The order is shown only by the layout."
)
INFOGRAPHIC_KEYPHRASE_RULE = (
    "信息图关键词（必须遵守）：\n"
    "- 先读懂每一场，再为它提炼" + KEYWORD_COUNT_ZH + "，说出这一场背后真正要揭示的东西："
    "关键的情绪、病因 / 根源、核心问题或转折。例如「怕改变」「假装没事」「被看见」「不敢开口」；"
    "绝不是场景标题、编号或「第N幕」。content.pdf 里这一场有 caption / 标题时，可以从它提炼，但要落到核心意思上。\n"
    + KEYWORD_PLACE_ZH + "\n"
    "- 关键词用和 content.pdf 相同的语言和字体（繁体 / 简体一致）。每个场景部分只有这几个关键词，没有别的字。\n"
    "Infographic key phrase (must follow):\n"
    "- First understand each scene, then distil " + KEYWORD_COUNT_EN + " for it that name what the scene really reveals: the key emotion, the root cause, the core problem or "
    "turning point, e.g. \"afraid of change\", \"pretending to be fine\", \"finally seen\". Never a scene title, a number, "
    "or a label like 第N幕 / Act N. If the scene in content.pdf has a caption or title, you may derive it from that, but "
    "boil it down to the core meaning.\n"
    + KEYWORD_PLACE_EN + "\n"
    "- Write it in the same language and script as content.pdf (Traditional vs Simplified Chinese consistent). "
    "That phrase is the only text in each scene section."
)


def _notebooklm_text_rule(text: str, output: str, presentation: bool) -> str:
    """全集生成：NotebookLM 爱给幻灯加标题和正文，这里按说明文字写死画面上能有什么字。汇报类不管（有自己的规则）。"""
    if presentation or output not in ("slides", "infographic", "video_overview"):
        return ""
    unit_zh = {"slides": "每页幻灯片", "infographic": "信息图的每个场景部分", "video_overview": "视频的每个画面"}[output]
    unit_en = {"slides": "Each slide", "infographic": "Each scene section of the infographic",
               "video_overview": "Each visual of the video"}[output]
    if output == "infographic":
        if text in ("erase", "express"):
            return (
                f"- 画面文字：{unit_zh}没有标题、没有正文、没有关键词，也没有任何文字框、面板或标题栏，全部用画面来讲。\n"
                f"- On-screen text: {unit_en} has NO title, NO body text, and NO keyword. "
                "No text box, panel, board, card, title bar, or caption area. The picture tells it all.\n"
                + INFOGRAPHIC_NO_INDEX_RULE
            )
        return INFOGRAPHIC_KEYPHRASE_RULE + "\n" + INFOGRAPHIC_NO_INDEX_RULE
    if text == "keywords":
        return (
            f"- 画面文字：{unit_zh}没有标题，也没有正文，唯一的字就是 {KEYWORD_COUNT_ZH}，融进场景。{NO_BUBBLE_ZH}\n"
            f"- On-screen text: {unit_en} has NO title text and NO body text. The only text is {KEYWORD_COUNT_EN}, "
            f"blended into the scene. {NO_BUBBLE_EN}\n"
            + KEYWORD_BG_RULE_ZH
        )
    if text in ("erase", "express"):
        return (
            f"- 画面文字：{unit_zh}没有标题、没有正文、没有关键词，也没有任何文字框、面板或标题栏，全部用画面来讲。\n"
            f"- On-screen text: {unit_en} has NO title, NO body text, and NO keyword. "
            "No text box, panel, board, card, title bar, or caption area. The picture tells it all."
        )
    return ""


def build_slide_flow_prompt(
    *,
    target: str,
    text: str,
    visual_style: str = "",
    scene_content: list,
    host_narrator: str = "",
    region: str = "",
    era: str = "",
    main_character: str = "",
    use_visual: bool = True,
    use_speaking: bool = True,
    use_actor: bool = False,
    narrative: str = "story",
    actor_override: str = "",
    output: str = "slides",
    content_source: str = "",
    actor_source: str = "",
    content_images: bool = False,
    episodes: list | None = None,
) -> str:
    """``actor_source``（如 "actor.pdf"）非空且本次带 Actors 时，加一段 ``Actor_Reference``。

    ``content_source``（如 "content.pdf"）非空时：场景内容不写进提示词，改为说明它在笔记本来源里。

按叙事风格，以及勾选了 visual、speaking、actor 中的哪几项，组装这一次的幻灯提示词。

    ``output`` 是全集生成要的 NotebookLM 产物：slides / infographic / audio_overview / video_overview。
    四种都会在最前面加 ``NOTEBOOKLM_SPEAKER_RULE``，并按产物类型加一段 ``NOTEBOOKLM_OUTPUT_LEADS``。

    ``actor_override`` 是 ``SLIDE_FLOW_ACTOR_OVERRIDES`` 里的英文描述，不为空时覆盖画面里人物的族裔和年代。

    每种叙事风格对三项的用法不同，见 ``_slide_flow_*_rules``。至少要选 visual 或 speaking。
    """
    if narrative not in SLIDE_FLOW_NARRATIVE_NOTES:
        narrative = "story"
    if target not in _SLIDE_FLOW_TARGET_LABELS:
        target = "slideshow"
    if text not in {k for k, _ in FLOW_CAPTION_CHOICES}:
        text = "erase"
    use_visual = bool(use_visual)
    use_speaking = bool(use_speaking)
    use_actor = bool(use_actor)
    if not (use_visual or use_speaking):
        raise ValueError("至少要选场景描述或讲话中的一项。")
    presentation = narrative in ("tech", "exec")
    keywords = text == "keywords" and not presentation
    style = (visual_style or "").strip() or "realistic"
    scenes = scene_content if isinstance(scene_content, list) else []
    # 叙事: needs a 讲员. 故事/汇报: any non-empty actor entry.
    has_speaker = _prompt_has_speaker(narrative, use_actor, scenes)
    # 讲述 / 汇报没有讲员时：名单里的人照样出现，只表演不说话（讲员在画外）。
    silent = (not has_speaker) and prompt_silent_cast(narrative, use_actor, scenes)
    json_content = json.dumps(
        slide_flow_scene_payload(
            scenes,
            use_visual=use_visual,
            use_speaking=use_speaking,
            use_actor=has_speaker,
            keywords=keywords,
            narrative=narrative,
            silent_cast=silent,
        ),
        ensure_ascii=False,
        indent=2,
    )

    if presentation:
        lines = [
            "You generate presentation slides as pictures. Each slide is one clean image.",
            f"Visual style for every picture: {style}.",
        ]
    else:
        lines = [
            "You generate pictures, not a written report and not a page of text.",
            f"Visual style for every picture: {style}.",
            "The same person keeps the same face and the same clothes.",
        ]
    if target == "single":
        lines.extend([
            "Make exactly one picture for this whole " + ("report." if presentation else "story."),
            "Every scene belongs in this one picture. Do not make a row of panels. Do not make one picture per scene.",
        ])
        if presentation:
            lines.append("Lay the whole report out as one slide: the main parts in reading order, top to bottom, left to right.")
        elif narrative == "narration":
            lines.append("Show it through the place, the objects, symbols, and the composition that carry the whole telling.")
        else:
            lines.append("Show the story through the place, the people, their faces, their poses, and a few objects that carry the story.")
        lines.append("Read each scene's show_this_content as what must be visible somewhere in this one picture.")
    else:
        lines.extend([
            "Make exactly one picture for each scene. One scene is one "
            + ("slide." if presentation else "frozen moment."),
            "The number of pictures equals the number of scenes. Do not merge two scenes into one picture. Do not split one scene into two.",
        ])
        if presentation:
            lines.append("Draw what that scene's show_this_content explains as one slide, following the order of the talk.")
        else:
            lines.extend([
                "Show what that scene's show_this_content describes: the place, the emotion, the action, and the light.",
                "A change of angle or an action already written there belongs in that picture.",
            ])

    lines.append("")
    lines.append(SLIDE_FLOW_NARRATIVE_NOTES[narrative])
    lines.append("")
    inputs_note = _slide_flow_inputs_note(use_visual, use_speaking, has_speaker, keywords, narrative)
    if silent:
        inputs_note = inputs_note.replace("No other field is given.", SILENT_ACTORS_INPUT_NOTE + "\nNo other field is given.")
    lines.append(inputs_note)
    lines.append("")
    if narrative == "story":
        lines.append(_slide_flow_story_rules(use_visual, use_speaking, has_speaker))
    elif narrative == "narration":
        lines.append(_slide_flow_narration_rules(use_visual, use_speaking, has_speaker))
    else:
        lines.append(_slide_flow_report_rules(use_visual, use_speaking, has_speaker))
    if silent:
        lines.append(SILENT_CAST_RULE)
    if has_speaker and _scenes_have_narrator_host(scenes):  # 讲员出镜才写默认讲员外貌
        host = (host_narrator or "").strip()
        if host:
            lines.append(f"The host chosen for this project is {host}. The 讲员 entry in ``Actors`` is this person.")
        look = (main_character or "").strip()
        if look:
            lines.append(f"Keep this cast readable and consistent: {look}.")
    if not presentation:
        lines.append("Faces, posture, and gesture match the feeling of the scene.")

    lines.append("")
    if presentation:
        lines.append(SLIDE_FLOW_SLIDE_TEXT_NOTE)
    else:
        lines.append(
            "Keyword: follow the infographic key phrase rule in Output_rules."
            if output == "infographic" and text == "keywords" else flow_caption_rule(text)
        )
    lines.append(SLIDE_FLOW_META_NOTE)
    if keywords:
        lines.append(
            "The one exception: " + KEYWORD_COUNT_EN + ", taken from ``Keyword hint`` and the scene's core emotion, blended into the scene as described above. "
            "Never the full scene title. " + NO_BUBBLE_EN
        )

    if not presentation:
        phrase = setting_place_phrase(region, era)
        if phrase:
            lines.append(
                f"Place and period: {phrase}. "
                "Clothing, buildings, streets, objects, and faces must belong to this place and this time."
            )
    override = (actor_override or "").strip()
    if override and not presentation:
        if has_speaker or silent:
            cast_field = "Actors" if has_speaker else SILENT_ACTORS_FIELD
            lines.append(
                f"People override: draw every person in the pictures as {override}. "
                f"Keep each person's name, role, gender, and age from ``{cast_field}``, "
                "but ignore any ethnicity, nationality, or period that the actor descriptions suggest. "
                "Face, skin, hair, and clothing all follow this override, and stay the same for the same person."
            )
        else:
            lines.append(
                f"People override: every person who appears in the pictures is {override}. "
                "Face, skin, hair, and clothing all follow this, and stay the same for the same person."
            )
    if has_speaker or silent:
        lines.extend(["", ACTOR_AGE_LOOK])
    parts = {}
    if output in NOTEBOOKLM_OUTPUT_LEADS:
        rule = notebooklm_speaker_rule(output)
        if output in ("slides", "infographic"):
            rule += "\n" + NOTEBOOKLM_VISUAL_RULE
        if narrative == "story":
            rule += ("\n- 故事：内容由故事人物彼此对话来讲，用他们自己的口吻；讲员（若有）只在开头或结尾用第一人称说几句。"
                     "\n- Story: the characters carry it by talking to each other in their own voices; the 讲员, if any, "
                     "only speaks a few first-person lines at the start or the end.")
        else:
            rule += ("\n- 讲述 / 汇报：讲员用第一人称讲，画面中的人物不说话。"
                     "\n- Telling / report: the 讲员 speaks in the first person; people in the pictures do not speak.")
        text_rule = _notebooklm_text_rule(text, output, presentation)
        if text_rule:
            rule += "\n" + text_rule
        lead = NOTEBOOKLM_OUTPUT_LEADS[output]
        # 场景对应规则说的是 content.pdf 的场景，只在全集生成（有 content_source、每场一项）时加。
        order_rule = (
            NOTEBOOKLM_SCENE_ORDER_RULES.get(output, "").replace("content.pdf", content_source)
            if content_source and target != "single" else ""
        )
        if order_rule:
            lead += "\n\n" + order_rule
        parts["Output_rules"] = lead + "\n\n" + rule
    body = "\n".join(lines)
    if content_source:
        body = body.replace("each scene's show_this_content", f"each scene's entry in {content_source}")
        body = body.replace("that scene's show_this_content", f"that scene's entry in {content_source}")
        body = body.replace("show_this_content", f"the scene entry in {content_source}")
    parts["Instruction_for_image" if output in ("slides", "infographic") else "Instruction_for_scenes"] = body
    if content_source:
        with_actor = bool(actor_source and (has_speaker or silent) and episode_actor_cast(scenes))
        parts["Scene_Content_Source"] = notebooklm_content_source_note(
            content_source, output, silent=silent, images=content_images,
            actor_source=actor_source if with_actor else "",
        )
        span_note = notebooklm_episode_span_note(content_source, output, episodes, len(scenes))
        if span_note:
            parts["Scene_Content_Source"] += "\n" + span_note
        if with_actor:
            parts["Actor_Reference"] = notebooklm_actor_reference_note(
                actor_source, output, narrative, content_name=content_source, silent=silent,
                episodes=episodes,
            )
    else:
        parts["Story_Scene_Content"] = json_content
    # t175u: 画风放最前面，最后再说一遍
    parts = {"Art_Style": art_style_block(style, output), **parts,
             "Art_Style_Reminder": art_style_block(style, output, reminder=True)}
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())


# 幻灯提示里覆盖画面人物的选项。值为 (界面名, 写进提示词的英文)；第一项空字符串表示不覆盖。
def build_scene_summary_image_prompt(
    scene_content: list,
    *,
    visual_style: str = "",
    host_narrator: str = "",
    region: str = "",
    era: str = "",
) -> str:
    """故事窗「场景总图」：把全部 scene_content 画成一张完整的总图。

    用幻灯提示同一个 ``build_slide_flow_prompt`` 的 ``target="single"`` 分支（幻灯提示窗本身只做幻灯片），
    用它的默认选择：叙事=故事、画面文字=不加、写进 visual + speaking。
    """
    return build_slide_flow_prompt(
        target="single",
        text="erase",
        narrative="story",
        use_visual=True,
        use_speaking=True,
        use_actor=False,
        visual_style=visual_style,
        scene_content=scene_content,
        host_narrator=host_narrator,
        region=region,
        era=era,
    )


SLIDE_FLOW_ACTOR_OVERRIDES: list[tuple[str, str]] = [
    ("不覆盖（用原来的人物）", ""),
    ("中国人 · 现代", "modern Chinese people of today"),
    ("中国人 · 唐朝", "Chinese people of the Tang dynasty, in Tang dynasty clothing and hairstyles"),
    ("中国人 · 宋朝", "Chinese people of the Song dynasty, in Song dynasty clothing and hairstyles"),
    ("中国人 · 明朝", "Chinese people of the Ming dynasty, in Ming dynasty clothing and hairstyles"),
    ("中国人 · 清朝", "Chinese people of the Qing dynasty, in Qing dynasty clothing and hairstyles"),
    ("中国人 · 民国", "Chinese people of Republican China in the 1920s and 1930s, in period clothing"),
    ("中国人 · 文革", "ordinary Chinese people of the 1960s (culture revolution period), in plain 1960s clothing (Mao suit)"),
    ("中国人 · 80年代", "ordinary Chinese people of the 1980s, in plain 1980s clothing"),
    ("日本人 · 现代", "modern Japanese people of today"),
    ("日本人 · 江户时代", "Japanese people of the Edo period, in Edo period clothing and hairstyles"),
    ("日本人 · 明治时代", "Japanese people of the Meiji period, in Meiji period clothing"),
    ("西方人 · 现代", "modern Western people of today, of European descent"),
    ("西方人 · 罗马时代", "people of the Roman Empire, in Roman clothing"),
    ("西方人 · 中世纪", "people of medieval Europe, in medieval clothing"),
    ("西方人 · 二战时期", "Western people of the Second World War era, in 1940s clothing"),
    ("黑人 · 现代", "modern Black people of African descent, of today"),
    ("原始部落人", "people of a traditional tribal community, in tribal dress, before modern cities"),
]

# 图片变换：先选地域，时代只列出这一地域里的项。值为 (界面名, 写进提示词的英文)。
SETTING_PLACES: dict[str, dict] = {
    "中国": {
        "en": "China",
        "eras": [
            ("唐朝", "the Tang dynasty"),
            ("东汉末三国", "the late Eastern Han and Three Kingdoms period"),  # t191u: 舞台「三国演义」
            ("宋朝", "the Song dynasty"),
            ("明朝", "the Ming dynasty"),
            ("清朝", "the Qing dynasty"),
            ("民国", "Republican China"),
            ("1950-60年代", "1950s and 1960s China"),
            ("1970年代", "1970s China"),
            ("1980年代", "1980s China"),
            ("1990年代", "1990s China"),
            ("2000年代", "2000s China"),
            ("现代", "present-day China"),
        ],
    },
    "日本": {
        "en": "Japan",
        "eras": [
            ("平安时代", "the Heian period"),
            ("江户时代", "the Edo period"),
            ("明治时代", "the Meiji period"),
            ("大正时代", "the Taisho period (1910s-1920s)"),
            ("昭和战后", "post-war Showa Japan (1950s-1970s)"),
            ("1980年代", "1980s Japan"),
            ("平成时代", "the Heisei period (1990s-2000s)"),
            ("现代", "present-day Japan"),
        ],
    },
    "欧洲": {
        "en": "Europe",
        "eras": [
            ("古希腊", "ancient Greece"),
            ("罗马帝国", "the Roman Empire"),
            ("中世纪", "the Middle Ages"),
            ("文艺复兴", "the Renaissance"),
            ("摄政时期英国", "Regency England (early 19th century)"),  # t191u: 舞台「傲慢与偏见」
            ("维多利亚时代", "the Victorian era (19th century)"),
            ("19世纪法国", "19th-century France"),  # t191u: 舞台「悲惨世界」
            ("二战时期", "the Second World War era (1940s)"),
            ("1960年代", "1960s Europe"),
            ("1980年代", "1980s Europe"),
            ("现代", "present-day Europe"),
        ],
    },
    # t191u: 舞台「飘」
    "美国": {
        "en": "the United States",
        "eras": [
            ("南北战争", "the American Civil War era (1860s)"),
            ("1920年代", "1920s America"),
            ("1950-60年代", "1950s and 1960s America"),
            ("现代", "present-day America"),
        ],
    },
    "埃及": {
        "en": "Egypt",
        "eras": [
            ("古埃及", "ancient Egypt"),
            ("20世纪中期", "mid-20th-century Egypt (1950s-1960s)"),
            ("现代", "present-day Egypt"),
        ],
    },
    "非洲": {
        "en": "Africa",
        "eras": [
            ("原始部落", "a traditional tribal setting, before modern cities"),
            ("殖民时期", "the colonial era (late 19th to mid 20th century)"),
            ("1970-80年代", "1970s and 1980s Africa"),
            ("现代", "present-day Africa"),
        ],
    },
    "中东": {
        "en": "the Middle East",
        "eras": [
            ("古巴比伦", "ancient Babylon"),
            ("阿拉伯帝国", "the early Arab empires"),
            ("奥斯曼帝国", "the Ottoman Empire"),
            ("20世纪中期", "the mid-20th-century Middle East (1950s-1970s)"),
            ("现代", "the present-day Middle East"),
        ],
    },
    "印度": {
        "en": "India",
        "eras": [
            ("孔雀王朝", "the Maurya period"),
            ("莫卧儿帝国", "the Mughal Empire"),
            ("英属印度", "British India (19th to mid 20th century)"),
            ("1970-80年代", "1970s and 1980s India"),
            ("现代", "present-day India"),
        ],
    },
}

PICTURE_TRANSFORM_OPTIONS: list[tuple[str, str]] = [
    ("softer", "保持画风 · 着色稍转向"),
    ("softer_no_text", "保持画风 · 着色稍转向 · 去掉说明文字"),
    ("to_style", "转成项目风格"),
    ("to_style_no_text", "转成项目风格 · 去掉说明文字"),
    ("extract", "人物提取"),
]


def setting_era_labels(region: str) -> list[str]:
    place = SETTING_PLACES.get((region or "").strip())
    if not place:
        return []
    return [name for name, _en in place["eras"]]


def setting_place_phrase(region: str, era: str) -> str:
    """地域 + 时代，写成提示词里的英文一句。缺一项就返回空。"""
    place = SETTING_PLACES.get((region or "").strip())
    if not place:
        return ""
    era_en = ""
    for name, en in place["eras"]:
        if name == (era or "").strip():
            era_en = en
            break
    if not era_en:
        return ""
    return f"{place['en']}, {era_en}"


_NO_PERSON = {"", "不出现", "none", "无"}


def person_ethnicity(person: str) -> str:
    """'woman/mature/chinese' → 'Chinese'；只取族裔，不带性别年龄。"""
    bits = [b.strip().lower() for b in (_clean_person(person) or "").split("/") if b.strip()]
    for b in bits:
        if b in ("chinese",) or "中" in b or "华" in b:
            return "Chinese"
        if b in ("english", "western") or "英" in b or "西" in b:
            return "Western (European)"
    return ""


def narrator_voice_phrase(person: str) -> str:
    """讲员外貌串 → 只描述声音：'a mature female voice'。不含外貌。"""
    bits = [b.strip().lower() for b in (_clean_person(person) or "").split("/") if b.strip()]
    gender = "female" if "woman" in bits else ("male" if "man" in bits else "")
    age = next((b for b in bits if b in ("kids", "youth", "teenager", "mature", "senior")), "")
    words = " ".join(w for w in (age, gender) if w)
    return f"a {words} voice" if words else ""


def _clean_person(person: str) -> str:
    p = (person or "").strip()
    return "" if p in _NO_PERSON else p


def background_condition_label(region: str, era: str, person: str) -> str:
    """提示窗口里「背景」勾选框上的字：背景：中国 · 明朝 · woman/mature/chinese。"""
    parts = [x for x in ((region or "").strip(), (era or "").strip(), _clean_person(person)) if x]
    return "背景：" + (" · ".join(parts) if parts else "（未选）")


def background_condition_block(region: str, era: str, person: str, stage=None) -> str:
    """地域 / 时代 / 人物 写成提示词里的背景条件；缺的项跳过，全空返回空。

    图片、幻灯、视频三个提示都用这一段，放在 FYI 之后、场景内容之前。
    """
    region = (region or "").strip()
    era = (era or "").strip()
    person = _clean_person(person)
    place = SETTING_PLACES.get(region)
    region_en = place["en"] if place else region
    era_en = ""
    if place:
        era_en = next((en for name, en in place["eras"] if name == era), "")
    if era and not era_en:
        era_en = era
    lines = []
    if region_en:
        lines.append(
            f"- Setting region: {region_en}. Landscape, streets, buildings, and everyday life belong to this place."
        )
    if era_en:
        lines.append(
            f"- Historical era: {era_en}. Architecture, clothing, hairstyles, props, vehicles, and objects "
            "must all match this era. Nothing from another period."
        )
    ethnicity = person_ethnicity(person)
    if ethnicity or region_en or era_en:
        # 只给「若有人出现」的族裔 / 衣着；绝不写讲员的性别年龄外貌，免得被当成要画的主持人。
        who = f"{ethnicity} people" if ethnicity else "people of this place"
        lines.append(
            f"- If people appear, they are {who}, with the clothing and hairstyles of this region and era. "
            "This is not a presenter: it adds no host, narrator, or speaker to the picture."
        )
    try:  # t191u: 故事舞台（不限 = 不加）
        from utility import story_stage as _ss

        _st = _ss.short_line(stage)
    except Exception:  # noqa: BLE001
        _st = ""
    if _st:
        lines.append("- " + _st)
    if not lines:
        return ""
    return "BACKGROUND CONDITION (applies to everything below):\n" + "\n".join(lines)


def prepend_background_condition(prompt: str, region: str, era: str, person: str, *, include: bool, stage=None) -> str:
    """勾选时把背景条件放在提示词最前面（FYI 之后再由 prepend_fyi 加在它上面）。"""
    body = (prompt or "").strip()
    block = background_condition_block(region, era, person, stage) if include else ""
    if not block:
        return body
    return block + "\n\n---\n\n" + body if body else block


def _softer_transform_prompt(*, remove_text: bool, style: str, period: str) -> str:
    """保持原画风，上色，并稍稍转向项目风格。"""
    lines = [
        "This prompt has two uses. Follow only the section that matches the tool.",
        "",
        "IMAGE — one still picture.",
        "Keep the same composition, the same people, the same action, and the same story moment.",
        "Do not add people. Do not change who is doing what.",
        "Keep the original painting style. "
        "If the picture is Chinese watercolor, it stays Chinese watercolor. "
        "If it is gouache, it stays gouache. "
        "If it is ink, color painting, or another hand-drawn style, that same style remains.",
        "Color the picture more fully.",
        f"Shift only a little toward this project style: {style}.",
        "The original style is still what you see. This is not a full change into that style.",
    ]
    if remove_text:
        lines.extend([
            "Remove the explanation text. "
            "Story pictures and comic pages often have captions beside the picture, under it, or in a box, "
            "telling what the scene means or which part of the story this is.",
            "Those words are not part of the drawing. Remove them.",
            "Fill those areas with the picture that belongs there: paper, sky, wall, ground, or the rest of the illustration.",
            "Do not leave empty boxes. Do not redraw the story.",
        ])
    else:
        lines.append("Keep any words already drawn in the picture.")
    lines.extend([
        "",
        "VIDEO — a clip that starts from the attached picture.",
        "Frame one is the attached picture, unchanged.",
        "Across the whole clip, color fills in little by little, "
        f"and the picture shifts only a little toward this project style: {style}.",
        "The original painting style stays recognizable. Do not finish as a full change into that style.",
        "The change must be a visible gradient. A viewer should see it happen step by step. "
        "Do not cut, do not swap styles in one frame, do not finish the change in the first moments.",
        "While this is happening, the people begin to perform: small motion first, "
        "then the action already shown in the picture.",
        "Keep the same people, the same place, and the same composition.",
        "Do not add people. Do not change who is doing what.",
    ])
    if remove_text:
        lines.extend([
            "Frame one still has the explanation text.",
            "The captions fade away little by little until the picture is clean. "
            "A viewer should see the words disappear, not a cut.",
            "Fill those areas with the picture that belongs there.",
        ])
    if period:
        lines.extend(["", period])
    return "\n".join(lines)


def _picture_transform_body(kind: str, period: str) -> tuple[str, str]:
    """返回 (静图要变成的结果, 视频里要渐变到的结果)。"""
    if kind == "realistic":
        look = "A real scene: natural light, real materials, real faces, real buildings."
        if period:
            look += " " + period
        return (
            look,
            "a real photographed scene, with real light, real materials, real faces, and real buildings",
        )
    if kind == "sketch":
        return (
            "A black-and-white pencil or ink sketch on light paper. Color is gone.",
            "a black-and-white pencil or ink sketch",
        )
    if kind == "watercolor":
        return (
            "A watercolor painting: soft transparent washes, visible paper, loose edges. Not a photograph.",
            "a watercolor painting",
        )
    if kind == "ink":
        return (
            "A Chinese ink-wash painting: black ink, gray washes, empty paper. Not a photograph.",
            "a Chinese ink-wash painting",
        )
    raise ValueError(f"未知的图片变换：{kind}")


PICTURE_CHARACTER_REF_NOTE = """
CHARACTER REFERENCES — a note on the attached pictures. This applies to every picture transform.
Picture 1 is the original picture. Transform that picture.
Pictures after it, if any, are reference portraits of people already in picture 1, from the most important person to the next.
Picture 2 is the reference for the most important person.
Picture 3 is the reference for the second person.
Picture 4 is the reference for the third person.
Further pictures continue in that same order, one reference for each next person.
There may be no extra pictures. Use a reference only when that picture is attached.
When a reference is attached, replace that person with the person in the reference: the same face and the same clothes.
Keep that person's place, size, pose, and action from picture 1. Draw them in the style this transform asks for.
Do not add a person who is not already in picture 1.
IMAGE: the finished still already shows each referenced person in place of the original person.
VIDEO: frame one is still picture 1. Across the clip, each referenced person gradually becomes the person in their reference.
""".strip()

ACTOR_AGE_LOOK = """
** Read each actor as woman or man / age band / chinese or english, and the name last when there is one.
** Age band is kids, youth, teenager, mature, or senior. Example: man/youth/english/Tom. Without a name: man/youth/english.
** There is no age number. The face and the body must look that age band.
""".strip()


def _with_picture_character_refs(text: str) -> str:
    return text.rstrip() + "\n\n" + PICTURE_CHARACTER_REF_NOTE + "\n\n" + ACTOR_AGE_LOOK


PICTURE_FLOW_TASK_CHOICES = (
    ("keep", "保持画风"),
    ("restyle", "转成项目风格"),
    ("extract", "人物提取"),
)
PICTURE_FLOW_TEXT_CHOICES = FLOW_CAPTION_CHOICES


def picture_flow_choice_label(task: str, text: str, visual_style: str = "") -> str:
    """把图片处理的选择写成一行。人物提取不带说明文字。"""
    if task == "extract":
        return "人物提取"
    task_label = dict(PICTURE_FLOW_TASK_CHOICES).get(task, task)
    text_label = dict(FLOW_CAPTION_CHOICES).get(text, text)
    label = f"{task_label} · {text_label}"
    style = (visual_style or "").strip()
    if style:
        label = f"{label} · {style}"
    return label


# 关键字作背景：每场只要一个很短的关键词，融进场景本身；绝不能是独立的文字板。
KEYWORD_MAX_ZH = 4  # t199u: 关键字最多 4 个字
KEYWORD_MAX_EN_WORDS = 3
KEYWORD_BG_RULE_ZH = (
    "关键字作背景（必须遵守）：\n"
    "- 先读懂这一场，再提炼" + KEYWORD_COUNT_ZH + "，说出这一场背后真正的东西：关键的情绪、根源、核心问题或转折，"
    "例如「避风港」「怕改变」「被看见」「隔门」。绝不是讲话里的句子、场景标题或编号。只有这几个词，没有句子、标题或说明。\n"
    + KEYWORD_PLACE_ZH + "\n"
    "- 画面（场景）是主体，关键词像场景里的一件东西，让人看了更有感觉。"
)
KEYWORD_BG_RULE_EN = (
    "Keyword as background (must follow):\n"
    "- First understand the scene, then distil " + KEYWORD_COUNT_EN + " naming what the scene really reveals: the key "
    "emotion, root cause, core problem or turning point (e.g. 避风港 \"safe harbor\", 怕改变, 被看见). Never a line from "
    "the dialogue, a scene title or a number. Only these words: no sentence, title or explanation.\n"
    + KEYWORD_PLACE_EN + "\n"
    "- The picture, the scene, stays the main content; the keywords are part of it and deepen its feeling."
)
# 去掉文字 / 用画面讲 / 关键字作背景 共用：不要任何独立的文字区。
NO_TEXT_PANEL_LINE = (
    "No separate text box, panel, board, card, screen, banner overlay, title bar, or caption area anywhere in the frame."
)


def short_keyword_hint(text: str) -> str:
    """把场景标题之类的长文字压成关键词提示：取第一段，中文最多 8 字，英文最多 3 词。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    seg = next((p.strip() for p in re.split(r"[，。；：、！？,.;:!?|/（）()「」『』“”\"《》\[\]\n—–\-]+", raw) if p.strip()), raw)
    if re.search(r"[\u3400-\u9fff]", seg):
        seg = re.sub(r"\s+", "", seg)
        return seg[:KEYWORD_MAX_ZH]
    return " ".join(seg.split()[:KEYWORD_MAX_EN_WORDS])


def flow_caption_rule(text: str) -> str:
    """说明文字的三种处理，外加保留。图片、幻灯、视频用同一段。"""
    if text == "keywords":
        return (
            "Take the explanation text off the picture. Do not leave an empty space "
            "or a ring of decoration around nothing.\n"
            + REMOVE_BUBBLES_EN.replace("Image 1", "the picture") + "\n"
            + KEYWORD_BG_RULE_EN + "\n"
            "The speaking / dialogue in the scene content is only for understanding the moment; it is never drawn as "
            "text. Any speech bubble or caption already in the picture is removed.\n"
            "The meaning itself is shown through the people, the place, or the story. "
            "The center is full. It is not blank."
        )
    if text == "express":
        return (
            "No letters anywhere. No keyword, no caption, no subtitle, no title, no background writing, no speech bubble.\n"
            + REMOVE_BUBBLES_EN.replace("Image 1", "the picture") + "\n"
            + NO_TEXT_PANEL_LINE + "\n"
            "Do not leave an empty board in the middle, and do not leave a ring of decoration around a blank center.\n"
            "Show what that text meant through the people, the place, or the story, in the middle of the picture. "
            "The center carries the meaning. It stays full."
        )
    if text == "erase":
        return (
            "Remove the explanation text: captions beside the picture, under it, or in a box. "
            "Those words are not part of the drawing.\n"
            + REMOVE_BUBBLES_EN.replace("Image 1", "the picture") + "\n"
            "Do not leave an empty board, a blank panel, or a hole. "
            "Continue the same picture through that area: the place, the people, and the objects that belong there.\n"
            "Do not add new lettering. " + NO_TEXT_PANEL_LINE + "\n" + NO_BUBBLE_EN
        )
    return "Keep any words already drawn in the picture. They stay part of the picture. Do not add a new caption."


# t181u: 「把电脑转向 David」之类：方向写死在场景里，不要转向镜头 / 观众。
_FACING_VERBS = (r"轉向|转向|面向|朝向|轉給|转给|遞給|递给|遞向|递向|推向|推給|推给|拿給|拿给|指給|指给|給|给"
                 r"|toward|towards|faces|facing")
IN_SCENE_FACING_MARK = "not toward the camera"
NO_FOURTH_WALL_LINE = ("Everyone stays inside the scene: they look at each other or at what they are doing, and nothing "
                       "is held up, turned or shown to the camera or the viewer.")


_NUM_WORDS = {1: "1 person", 2: "2 people", 3: "3 people", 4: "4 people"}


def cast_lock_lines(names, background_ok: bool = False) -> list:
    """t182u: 人数锁：视频里正好这几个人，不加人、不复制；换姿势 / 位置都是同一个人自己走过去。
    t156u: background_ok（MiniMax 用）= 只锁演员；起始图里另外看得见的人是不说话的背景人物。"""
    names = [str(n or "").strip() for n in (names or []) if str(n or "").strip()]
    names = list(dict.fromkeys(names))
    if not names:
        return []
    n = len(names)
    who = names[0] if n == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    count = _NUM_WORDS.get(n, f"{n} people")
    if background_ok:
        cast = "1 cast member" if n == 1 else f"{n} cast members"
        return [
            f"Exactly {cast} in the whole video, {who}: anyone else already visible in <Picture 1> is a silent "
            "background person who keeps their lips closed and never speaks; no one is added, no one is duplicated, "
            "and each person appears only once.",
            "Any change of pose or place in the description, such as sitting down, standing up or walking to the window, "
            "is made by that same person moving continuously from where they are in the start picture, never by a second copy.",
        ]
    return [
        f"Exactly {count} in the whole video, {who}: no one else appears, no one is duplicated, "
        "and each person appears only once.",
        "Any change of pose or place in the description, such as sitting down, standing up or walking to the window, "
        "is made by that same person moving continuously from where they are in the start picture, never by a second copy.",
    ]


_POSE_PLACES = (("窗", "the window"), ("書架", "the bookshelf"), ("书架", "the bookshelf"), ("門口", "the door"),
                ("门口", "the door"), ("門邊", "the door"), ("门边", "the door"), ("沙發", "the sofa"), ("沙发", "the sofa"),
                ("床", "the bed"), ("椅子", "a chair"), ("椅", "a chair"), ("書桌", "the desk"), ("书桌", "the desk"),
                ("桌", "the table"), ("牆", "the wall"), ("墙", "the wall"), ("陽台", "the balcony"), ("阳台", "the balcony"))


def _pose_place(clause: str) -> str:
    for key, en in _POSE_PLACES:
        if key in clause:
            return en
    return ""


_REAL_SIT = re.compile(r"坐下|坐到|坐回|坐進|坐进|入座|落座|走.{0,6}坐")
_REAL_STAND = re.compile(r"站起|起身|起立")
_REAL_LIE = re.compile(r"躺下|躺到|躺回|倒在")


def _pose_move(clause: str, strict: bool = False) -> str:
    """一个小句里的姿势 / 位置变化 → 英文动作；没有返回空。
    t156u: strict（MiniMax 用）= 只认真的变化（坐下 / 站起 / 躺下 / 走到…）；坐在 / 站在 / 躺在 是起始姿势，不算。"""
    place = _pose_place(clause)
    if strict:
        if _REAL_SIT.search(clause):
            return "sits down" + (f" on {place}" if place in ("a chair", "the sofa", "the bed") else
                                  f" at {place}" if place else "")
        if _REAL_STAND.search(clause):
            return "stands up"
        if _REAL_LIE.search(clause):
            return "lies down" + (f" on {place}" if place else "")
        if any(k in clause for k in ("走到", "走向", "走過去", "走过去", "走近", "來到", "来到")):
            return f"walks over to {place}" if place else "takes a few steps to a new spot in the room"
        return ""
    if "坐" in clause:
        return "walks over and sits down" + (f" on {place}" if place in ("a chair", "the sofa", "the bed") else
                                             f" at {place}" if place else "")
    if "站起" in clause:
        return "stands up"
    if "躺" in clause:
        return "lies down" + (f" on {place}" if place else "")
    if any(k in clause for k in ("走到", "走向", "走過去", "走过去", "走近", "來到", "来到")):
        return f"walks over to {place}" if place else "takes a few steps to a new spot in the room"
    return ""


def pose_move_lines(visual: str, names, strict: bool = False, skip=()) -> list:
    """t182u: visual 里某人换姿势 / 位置（坐、站起、走到…）：写成「就是起始图里那个人自己走过去」，尽量写出去哪里。
    t156u: strict = 只写真的变化；skip = 说话的人（说话时不走动，一律不写）。"""
    out, done = [], set(str(x) for x in (skip or ()))
    for clause in re.split(r"[。！？!?，,；;]", str(visual or "")):
        for nm in [str(n or "").strip() for n in (names or [])]:
            if not nm or nm in done or nm not in clause:
                continue
            move = _pose_move(clause, strict)
            if move:
                out.append(f"{nm} {move}, the same person as in the start picture moving there, never a second copy.")
                done.add(nm)
    return out


def facing_targets(visual: str, names) -> list:
    """visual 里「转向 / 递给 / 面向 + 人名」的人名（按出现顺序、去重）。"""
    text = str(visual or "")
    out = []
    for nm in [str(n or "").strip() for n in (names or [])]:
        if nm and nm not in out and re.search(rf"(?:{_FACING_VERBS})\s*(?:the\s+)?{re.escape(nm)}", text, re.I):
            out.append(nm)
    return out


def in_scene_direction_lines(visual: str, names) -> list:
    """视频提示词用：每个被「转向 / 递给」的人一句明确方向；有人时再加一句不对镜头。"""
    names = [str(n or "").strip() for n in (names or []) if str(n or "").strip()]
    lines = []
    for nm in facing_targets(visual, names):
        lines.append(
            f"Whatever is turned, shown or handed to {nm} turns sideways inside the scene toward {nm}, the other person "
            f"in the scene, {IN_SCENE_FACING_MARK}: its screen or front faces {nm} and turns away from the viewer."
        )
    if names:
        lines.append(NO_FOURTH_WALL_LINE)
    return lines


def video_caption_rule(text: str) -> str:
    """t172u: 视频用。「关键字作背景」时关键词已经在起始图里，视频只保持原样，不再画新字。"""
    if text == "keywords":
        return ("Words already drawn into the start picture stay exactly as they are, as part of the scene. "
                "No new writing appears in the video; the spoken lines are heard, not shown.")
    return flow_caption_rule(text)


def _picture_flow_text_rule(text: str) -> str:
    return flow_caption_rule(text)


def _picture_flow_refs(listed: bool = False) -> str:
    """``listed``: the pasted pictures are numbered in ``Reference_images`` below (base picture + actor portraits)."""
    if listed:
        return (
            "Picture 1 is the picture to change.\n"
            "The pictures pasted after it are the people's reference portraits, numbered in Reference_images below. "
            "Follow that list for who is who.\n\n"
            + ACTOR_AGE_LOOK
        )
    return (
        "Picture 1 is the picture to change.\n"
        "Pictures after it, if any are pasted, are reference portraits of people already in picture 1, "
        "from the most important person to the next.\n"
        "Picture 2 is the most important person. Picture 3 is the second person. Further pictures continue in that order.\n"
        "Use a reference only when that picture is attached.\n"
        "When a reference is attached, that person keeps the face and the clothes in the reference. "
        "Keep that person's place, size, pose, and action from picture 1.\n"
        "Do not add a person who is not already in picture 1.\n\n"
        + ACTOR_AGE_LOOK
    )


def _picture_story_lines(
    *,
    narrative: str,
    use_visual: bool,
    use_speaking: bool,
    use_actor: bool,
    host_narrator: str,
    main_character: str,
    actor_override: str,
    region: str,
    era: str,
) -> list[str]:
    """当前这一场的叙事风格。规则与幻灯提示同一套。

    和幻灯不同的只有这一点：图已经在手上。``Shown`` 只作这张图的画面参考，故事靠 ``Said`` 来讲。
    """
    if narrative not in SLIDE_FLOW_NARRATIVE_NOTES:
        narrative = "story"
    lines = [
        "Narrative style. This one picture presents the current scene in the chosen style.",
        "The attached picture is the picture you work on.",
        "``Shown``, when it is given, is only a reference for the place, the angle, and the look. "
        "The story does not depend on it. If it is absent, the attached picture is enough.",
        (
            "``Dialogue``, when it is given, is the story itself: how it develops and the words the characters say to each other."
            if narrative == "story"
            else f"``{scene_content_label(narrative)}``, when it is given, is the main content of this scene, told by the 讲员. "
            "Nobody in the picture says it."
        ),
        "When the story needs a person who is not yet in the picture, add that person.",
        "When ``Actors`` is given, each person follows that entry: woman or man, chinese or english, and the age band.",
        "",
        SLIDE_FLOW_NARRATIVE_NOTES[narrative],
        "",
        _slide_flow_inputs_note(use_visual, use_speaking, use_actor, False, narrative),
        "",
    ]
    if narrative == "story":
        lines.append(_slide_flow_story_rules(use_visual, use_speaking, use_actor))
    elif narrative == "narration":
        lines.append(_slide_flow_narration_rules(use_visual, use_speaking, use_actor))
    else:
        lines.append(_slide_flow_report_rules(use_visual, use_speaking, use_actor))
    if use_actor:
        host = (host_narrator or "").strip()
        if host:
            lines.append(f"The host chosen for this project is {host}. The 讲员 entry in ``Actors`` is this person.")
        look = (main_character or "").strip()
        if look:
            lines.append(f"Keep this cast readable and consistent: {look}.")
    presentation = narrative in ("tech", "exec")
    if not presentation:
        phrase = setting_place_phrase(region, era)
        if phrase:
            lines.append(
                f"Place and period: {phrase}. "
                "Clothing, buildings, streets, objects, and faces must belong to this place and this time."
            )
    override = (actor_override or "").strip()
    if override and not presentation:
        if use_actor:
            lines.append(
                f"People override: draw every person in the picture as {override}. "
                "Keep each person's name, role, gender, and age from ``Actors``, "
                "but ignore any ethnicity, nationality, or period that the actor descriptions suggest."
            )
        else:
            lines.append(
                f"People override: every person who appears in the picture is {override}."
            )
    if use_actor:
        lines.extend(["", ACTOR_AGE_LOOK])
    lines.extend(["", SLIDE_FLOW_META_NOTE])
    return lines


def build_picture_flow_prompt(
    *,
    task: str,
    text: str,
    visual_style: str = "",
    region: str = "",
    era: str = "",
    narrative: str = "story",
    use_visual: bool = True,
    use_speaking: bool = True,
    use_actor: bool = False,
    scene_content: list | None = None,
    host_narrator: str = "",
    main_character: str = "",
    actor_override: str = "",
    edit_request: str = "",
    actor_images: list | None = None,
    base_image: bool = True,
) -> str:
    """按画风改变、说明文字，以及叙事风格，组装这一次的图片提示词。

    ``actor_images``（``content_pdf.scene_actor_reference_images`` 的结果）不为空时加一段 ``Reference_images``：
    第几张图是基础图、第几张是哪位人物的形象图。``base_image`` 表示第 1 张是不是场景的基础图。
    仅修改（什么都没勾）和人物提取不加。

    叙事风格与幻灯提示同一套，以及 visual / speaking / actor 的勾选。
    人物提取不用叙事风格。其余情况三项至少要选一项。
    """
    _refs_listed = bool(base_image) and any(isinstance(r, dict) and r.get("image_no") for r in (actor_images or []))
    if task not in {k for k, _ in PICTURE_FLOW_TASK_CHOICES}:
        task = "keep"
    if text not in {k for k, _ in PICTURE_FLOW_TEXT_CHOICES}:
        text = "keep"
    if narrative not in SLIDE_FLOW_NARRATIVE_NOTES:
        narrative = "story"
    use_visual = bool(use_visual)
    use_speaking = bool(use_speaking)
    use_actor = bool(use_actor)
    scenes = [s for s in (scene_content or []) if isinstance(s, dict)]
    has_speaker = _prompt_has_speaker(narrative, use_actor, scenes)
    story_on = task != "extract" and bool(scenes) and (use_visual or use_speaking or use_actor)
    if task != "extract" and not (use_visual or use_speaking or use_actor):
        return _picture_edit_only_prompt(task, text, (visual_style or "").strip(), region, era, edit_request)
    if False:
        raise ValueError("场景描述、讲话、人物至少要选一项。")
    style = (visual_style or "").strip()
    if task != "extract" and not style:
        raise ValueError("请先在项目里选定画面风格。")
    phrase = setting_place_phrase(region, era)
    if task == "extract":
        lines = [
            "Make one clean upper-body portrait of each person already in the attached picture.",
            "Extract every person. Do not add anyone. Do not drop anyone.",
            "Show each person from the waist up, turned to face the viewer.",
            "If two people are facing each other, both turn toward the camera.",
            "Facial features must be large and readable: eyes, nose, mouth, face shape.",
            "Clothes must be clear: color, cut, collar, sleeves, pattern.",
            "Hands are empty and still. Remove anything they were holding: cups, fans, books, tools, weapons, cloth, or any other object.",
            "Remove the action, the furniture, the scenery, the writing, and every other prop. Nothing remains except the person.",
            "Keep each person's identity, age, and the clothes they already wear.",
            "Plain empty background. A clean picture of the face and the clothes.",
        ]
        if phrase:
            lines.append(
                f"Place and period: {phrase}. "
                "The clothes and the face belong to this place and this time. "
                "Do not bring back buildings, streets, or objects."
            )
        lines.extend(["", ACTOR_AGE_LOOK])
        body = "\n".join(lines)
        label = picture_flow_choice_label("extract", text)
    elif task == "restyle":
        people_line = (
            "The story description below decides the people and what they do. Add a person when the story needs one."
            if story_on
            else "Do not add people. Do not change who is doing what."
        )
        moment_line = (
            "Keep the same composition, unless the story description below asks for a change."
            if story_on
            else "Keep the same composition, the same people, the same action, and the same story moment."
        )
        lines = [
            "Make one still picture from the attached picture.",
            moment_line,
            people_line,
            "Do not keep the original drawing style.",
            f"Restyle the whole picture into this target style: {style}.",
            "Faces, clothes, the place, and the objects all take that style."
            + ("" if story_on else " The story in the picture stays the same."),
            _picture_flow_text_rule(text),
        ]
        if phrase:
            lines.append(
                f"Place and period: {phrase}. "
                "Clothing, buildings, streets, objects, and faces must belong to this place and this time."
            )
        lines.extend(["", _picture_flow_refs(_refs_listed)])
        body = "\n".join(lines)
        label = picture_flow_choice_label("restyle", text, style)
    else:
        people_line = (
            "The story description below decides the people and what they do. Add a person when the story needs one."
            if story_on
            else "Do not add people. Do not change who is doing what."
        )
        moment_line = (
            "Keep the same composition, unless the story description below asks for a change."
            if story_on
            else "Keep the same composition, the same people, the same action, and the same story moment."
        )
        lines = [
            "Make one still picture from the attached picture.",
            moment_line,
            people_line,
            "Keep the original painting style. "
            "If the picture is Chinese watercolor, it stays Chinese watercolor. "
            "If it is gouache, it stays gouache. "
            "If it is ink, color painting, or another hand-drawn style, that same style remains.",
            "Color the picture more fully.",
            f"Shift only a little toward this project style: {style}.",
            "The original style is still what you see. This is not a full change into that style.",
            _picture_flow_text_rule(text),
        ]
        if phrase:
            lines.append(
                f"Place and period: {phrase}. "
                "Clothing, buildings, streets, objects, and faces must belong to this place and this time."
            )
        lines.extend(["", _picture_flow_refs(_refs_listed)])
        body = "\n".join(lines)
        label = picture_flow_choice_label("keep", text, style)
    if story_on:
        label = label + " · " + slide_flow_choice_label(
            "single", "none", use_visual, use_speaking, has_speaker, narrative
        )
        lines.extend(["", *_picture_story_lines(
            narrative=narrative,
            use_visual=use_visual,
            use_speaking=use_speaking,
            use_actor=has_speaker,
            host_narrator=host_narrator if (has_speaker and _scenes_have_narrator_host(scenes)) else "",
            main_character=main_character,
            actor_override=actor_override,
            region=region,
            era=era,
        )])
        body = "\n".join(lines)
        payload = json.dumps(
            slide_flow_scene_payload(
                scenes[:1],
                use_visual=use_visual,
                use_speaking=use_speaking,
                use_actor=has_speaker,
                keywords=False,
                narrative=narrative,
            ),
            ensure_ascii=False,
            indent=2,
        )
        refs = picture_reference_images_note(actor_images, task=task, narrative=narrative, base_image=base_image)
        refs_part = f"Reference_images:\n{refs}\n\n" if refs else ""
        return (
            f"Picture_choices:\n{label}\n\n"
            f"Instruction_for_image:\n{body}\n\n"
            f"{refs_part}"
            f"Story_Scene_Content:\n{payload}"
        )
    return f"Picture_choices:\n{label}\n\nInstruction_for_image:\n{body}"


def output_aspect_line(video_size: str = "", width=None, height=None) -> str:
    """出图比例，放在提示词最前面。video_size 是 "1920x1080" / "1080x1920"；也可以给宽高。"""
    w = h = 0
    try:
        if video_size and "x" in str(video_size):
            w, h = (int(v) for v in str(video_size).lower().split("x", 1))
        elif width and height:
            w, h = int(width), int(height)
    except (TypeError, ValueError):
        w = h = 0
    if w <= 0 or h <= 0:
        return ""
    if w >= h:
        return (f"OUTPUT FORMAT: 16:9 landscape ({w}x{h}). The output image MUST be 16:9 landscape (wider than tall).\n"
                "输出比例：16:9 横屏。输出的图片必须是 16:9。")
    return (f"OUTPUT FORMAT: 9:16 portrait ({w}x{h}). The output image MUST be 9:16 portrait (taller than wide).\n"
            "输出比例：9:16 竖屏。输出的图片必须是 9:16。")


def picture_reference_images_note(actor_images: list | None, *, task: str, narrative: str, base_image: bool = True) -> str:
    """图片提示：发出去的图各是什么，以及人物形象图怎么用。没有任何人物形象图返回 ""。"""
    rows = [r for r in (actor_images or []) if isinstance(r, dict) and (r.get("name") or "").strip()]
    if not any(r.get("image_no") for r in rows):
        return ""
    zh = ["参考图（必须遵守）："]
    en = ["Reference images (must follow):"]
    if base_image:
        zh.append("- 第1张图是这一场的基础图。")
        en.append("- Image 1 is the base picture of this scene.")
    for r in rows:
        ov = (r.get("override") or "").strip()
        who_zh = f"{r.get('label') or '人物'}「{r['name']}」" + (f"（换成{ov}）" if ov else "")
        who_en = (f"{'the 讲员 (host)' if r.get('role') == 'host' else (r.get('label') or '人物')} \"{r['name']}\""
                  + (f" (overridden to {ov})" if ov else ""))
        if r.get("image_no"):
            zh.append(f"- 第{r['image_no']}张图是{who_zh}的形象图。")
            en.append(f"- Image {r['image_no']} is the appearance reference of {who_en}.")
        elif ov:
            zh.append(f"- {who_zh}没有形象图（不对应任何一张图）：按上面的人物覆盖，以及名字里的性别、年龄段来画，前后保持一致。")
            en.append(f"- {who_en} has no reference image (no image belongs to them): draw them from the people override above "
                      "and the gender and age band in the name, and keep that look consistent.")
        else:
            zh.append(f"- {who_zh}没有形象图（不对应任何一张图）：按名字里的性别、年龄段、族裔来画，前后保持一致。")
            en.append(f"- {who_en} has no reference image (no image belongs to them): draw them from the gender, "
                      "age band, and origin in the name, and keep that look consistent.")
    with_img = [r for r in rows if r.get("image_no")]
    no_img = [r for r in rows if not r.get("image_no")]
    if base_image and with_img:
        def _who(r):
            ov = (r.get("override") or "").strip()
            return f"{r.get('label') or '人物'} {r['name']}" + (f" (overridden to {ov})" if ov else "")
        nos = sorted({int(r["image_no"]) for r in with_img})
        span = f"Image {nos[0]}" if len(nos) == 1 else f"Images {nos[0]}..{nos[-1]}"
        order = ", ".join(f"Image {r['image_no']} = {_who(r)}" for r in with_img)
        en.append(
            f"- Image 1 is the picture to edit. {span} are reference portraits of the cast, in this order: {order}."
        )
        en.append(
            "- Match each person in Image 1 to a portrait by gender, age group and ethnicity (and role), then redraw that "
            "person's face, hair and clothing to match the portrait, keeping pose, position, composition, lighting and "
            "everything else in Image 1. Do not add or remove people. If a person in Image 1 has no matching portrait, "
            "leave them as they are."
        )
        if no_img:
            en.append("- Cast without a portrait (description only, no image): "
                      + "; ".join(_who(r) for r in no_img) + ".")
        zh.append("- 第1张图是要修改的图；后面几张是人物形象图，顺序同上。按性别、年龄段、族裔（和身份）把第1张图里的每个人"
                  "对上一张形象图，照形象图重画这个人的脸、发型和衣着；姿势、位置、构图、光线和其他一切照第1张图不变。"
                  "不要加人也不要减人；对不上形象图的人保持原样。")
    zh += [
        "- 这一场里出现的每个人，长相（脸、发型、年龄、衣着）都照他自己的形象图。"
        + ("" if (base_image and with_img) else "把场景里原有的人换成他们；场景描述或讲话需要他们出现而图里没有时，把他们加进去。")
        + "不要为他们另编长相。",
        "- 形象图只提供长相，不提供画风：画风照上面「画风改变」的规则"
        + ("（转成项目风格：整张图转成项目风格，人物也是）" if task == "restyle" else "（保持画风：保持基础图的画风，人物也画成这个画风）")
        + "；形象图的画风、背景和光线都不要带进来。",
        "- 只画这一场列出的人，不要加没列出的人，也不要加默认讲员。",
    ]
    en += [
        "- Every person who appears in this scene takes the look from their own reference image: face, hair, age, and clothes. "
        + ("" if (base_image and with_img) else
           "Replace the people already in the scene with them, or add them where the scene description or the lines need them. ")
        + "Never invent another look for them.",
        "- The reference images only supply faces and looks, not their art style: follow the style rule above"
        + (" (convert to the project style: the whole picture, people included, takes the project style)" if task == "restyle"
           else " (keep the style: keep the base picture's style and draw the people in that style)")
        + "; never carry over the portraits' art style, background, or lighting.",
        "- Draw only the people listed for this scene. Do not add anyone else, and never add a default 讲员.",
    ]
    if narrative in TELLING_NARRATIVES:
        zh.append("- 讲述 / 汇报：画面里的人只表演、不说话；讲员只有在这一场列出时才出现。")
        en.append("- Telling / report: the people in the picture act silently; the 讲员 appears only if listed for this scene.")
    else:
        zh.append("- 故事：人物在场景里演、彼此对话。")
        en.append("- Story: the characters act and talk with each other inside the scene.")
    zh.append("- 如果最前面的「注意 / FYI」另有要求（例如把主角换成某位人物），以它为准。")
    en.append("- If the 注意 / FYI note at the very top asks for something else (for example, swap the lead for one of these people), it takes priority.")
    return "\n".join(zh + en)


EDIT_KEEP_STYLE_LINE = (
    "Keep the picture's own drawing or painting style exactly as it is. Do not move it toward any other style."
)


def _picture_edit_only_prompt(task: str, text: str, style: str, region: str, era: str, edit_request: str) -> str:
    """图片提示「仅修改」：visual / speaking / actor 都没勾，没有场景内容，只按 FYI 改现有图片。

    不写叙事风格规则（讲述 / 故事 / 讲员），不加人。画风：保持画风 = 原样，不提项目风格；
    转成项目风格 = 改成项目画面风格（场景风格行由外层照常加在它旁边）。
    """
    request = (edit_request or "").strip()
    lines = []
    if request:
        lines += ["Main edit request (most important):", request, ""]
    else:
        lines += ["No specific edit was requested. Make only the changes listed below.", ""]
    lines += [
        "This is an edit of the attached picture, not a new picture.",
        "Keep everything else as it is: the composition, the people, their faces, poses, and clothes, "
        "the place, and the objects. Change only what is asked here.",
        "Do not add people. Do not remove anyone unless the main edit request says so.",
    ]
    if task == "restyle" and style:
        lines += [
            f"Restyle the whole picture into this target style: {style}.",
            "Faces, clothes, the place, and the objects all take that style; the content stays the same.",
        ]
        label_style = f"转成项目风格 {style}"
    else:
        lines.append(EDIT_KEEP_STYLE_LINE)
        label_style = "保持画风"
    lines.append(_picture_flow_text_rule(text))
    phrase = setting_place_phrase(region, era)
    if phrase:
        lines.append(
            f"Place and period: {phrase}. Anything the edit adds or changes must belong to this place and this time."
        )
    text_label = dict(PICTURE_FLOW_TEXT_CHOICES).get(text, text)
    label = f"仅修改现有图片 · {label_style} · {text_label}"
    return f"Picture_choices:\n{label}\n\nInstruction_for_image:\n" + "\n".join(lines)


def scene_speech_transform(actor_text: str) -> tuple[str, str] | None:
    """按出场的人决定这场文字怎么改。不出现的人不算。没有人就返回 None。"""
    import project_manager

    active = project_manager.active_actor_entries(actor_text)
    if not active:
        return None
    first = active[0]
    second = active[1] if len(active) > 1 else None
    first_role = first.get("role")
    second_role = second.get("role") if second else None
    if first_role == "person" and second_role == "person":
        return ("dialogue", "两人对话")
    if first_role == "host" and second_role == "person":
        return ("narrator_then_person", "旁白讲述，主人公回应")
    if first_role == "person" and second_role == "host":
        return ("person_then_narrator", "主人公说话，旁白解说")
    if first_role == "host":
        return ("narrator_only", "只有旁白")
    return ("person_only", "只有主人公说话")


def _scene_speech_snapshot(scene: dict | None) -> dict:
    import project_manager

    scene = scene if isinstance(scene, dict) else {}
    speaking = (scene.get("speaking") or "").strip()
    old_voiceover = (scene.get("voiceover") or "").strip()
    if old_voiceover and "<" not in speaking:
        speaking = (speaking + f" <2> {old_voiceover}").strip() if speaking else f"<1> {old_voiceover}"
    return {
        "speaking": speaking,
        "visual": (scene.get("visual") or "").strip(),
        "actor": project_manager.actor_text_for_generation(scene.get("actor") or ""),
    }


def build_split_scene_prompt(
    scene: dict,
    channel_id: str,
    project_override: dict | None = None,
    previous: dict | None = None,
    following: dict | None = None,
) -> tuple[str, str]:
    """把当前这一场拆成多场的提示词。正文来自频道 ``channel_prompt.split_scene``。"""
    import config

    modes = config.get_channel_prompt_modes(channel_id, project_override)
    instruction = (modes.get("split_scene") or "").strip()
    if not instruction:
        import config_channel
        instruction = config_channel.SCENE_SPLIT_MANY.strip()

    def dump(item: dict | None, empty: str) -> str:
        if not item:
            return empty
        return json.dumps(_scene_speech_snapshot(item), ensure_ascii=False, indent=2)

    lines = [
        instruction.strip(),
        "",
        "前一场只作衔接，不要改写，也不要放进返回的数组：",
        dump(previous if isinstance(previous, dict) else None, empty="（没有前一场）"),
        "",
        "要拆开的这一场：",
        dump(scene if isinstance(scene, dict) else None, empty="（没有）"),
        "",
        "后一场只作衔接，不要改写，也不要放进返回的数组：",
        dump(following if isinstance(following, dict) else None, empty="（没有后一场）"),
    ]
    return "拆成多场", "\n".join(lines)


def build_scene_speech_transform_prompt(
    scene: dict,
    previous: dict | None = None,
    following: dict | None = None,
    span: int = 1,
    later: list | None = None,
) -> tuple[str, str] | None:
    """按当前 actor 重写 speaking 和 voiceover。span 为 2 或 3 时，把后面连续几场的内容并进这一段对话。"""
    import project_manager

    scene = scene if isinstance(scene, dict) else {}
    actor_text = scene.get("actor") or ""
    picked = scene_speech_transform(actor_text)
    if not picked:
        return None
    kind, label = picked
    active = project_manager.active_actor_entries(actor_text)
    speakers = active[:3]
    silent = active[3:4]

    def who(row: dict) -> str:
        role = "讲员" if row.get("role") == "host" else (row.get("label") or "人物")
        body = (row.get("body") or "").strip()
        return f"{role}（{body}）"

    def tone(row: dict) -> str:
        if row.get("role") == "host":
            return "用讲员的旁白口吻，第三人称讲述这场看到的事"
        return "用这个人自己的口气说话"

    slots = []
    for index, row in enumerate(speakers, 1):
        slots.append(f"<{index}> 是 {who(row)}。这个人开口时用这个口气：{tone(row)}。")
    if len(speakers) == 1:
        slots.append("只有这一个人说话。可以不写 <1>。")
    elif kind == "dialogue":
        slots.append("这几个人在对话，第二个人回应第一个人。这场没有讲员。")
    elif kind == "person_then_narrator":
        slots.append("讲员用旁白口吻解说这场，不要把人物刚说的话再念一遍。")
    elif kind == "narrator_then_person":
        slots.append("讲员先把这场讲清楚，人物再回应。")
    if silent:
        slots.append(f"第4个是 {who(silent[0])}。这个人只出现在画面里，不要给他台词，不要写 <4>。")

    span = 3 if span >= 3 else 2 if span == 2 else 1
    later_scenes = [item for item in (later or []) if isinstance(item, dict)]
    if span == 1:
        merged = [scene]
        after_ref = following if isinstance(following, dict) else None
    else:
        merged = [scene, *later_scenes[: span - 1]]
        if len(merged) < span:
            return None
        after_ref = later_scenes[span - 1] if len(later_scenes) >= span else None

    def dump(item: dict | None, *, empty: str) -> str:
        if not item:
            return empty
        return json.dumps(_scene_speech_snapshot(item), ensure_ascii=False, indent=2)

    lines = [
        "只调整 speaking，使它和当前这场 actor 的位置一致。没有 voiceover。",
        "speaking 是整段对话。用 <N> 标明 actor 里第几个人在说，从 1 起。开口的最多三个人。第四个只出镜，不说话。",
        "同一个人继续说，直到下一个 <N>。可以来回说好几次。",
        "名叫「不出现」的人不算。讲员如果是不出现，这场就没有讲员。",
        "visual 是画面描述，原样保留，不要改写，也不要放进返回的 JSON。",
        "actor 不要改，也不要放进返回的 JSON。",
        "actor 里已经写了年龄段：kids、youth、teenager、mature、senior。说话的口气按这个年龄段来。不要另判一个年龄。",
        "用原来的语言来写。",
        "说的时候留一点间隙，不要赶着把字塞满。",
        "说话时自然带出这些人是谁、彼此是什么关系、以前有过什么交集，让听众听得出来。",
        "朋友、主客、家人或其他关系，都从下面已经写出的内容里取，不要另编一套关系。",
    ]
    if span == 1:
        lines[0:0] = [
            "下面是这一场现在的内容。请把它变换成新的内容。",
            "故事里发生的事保持不变。场景结构保持不变。",
        ]
        lines.extend([
            "speaking 用大约 10 到 12 秒说完。不要超过 12 秒。",
            "10 秒能说完就不要写到 12 秒。",
            "现在的话如果读起来超过 12 秒，就压缩大约两成，只留下这场必须说的事。",
            "现在的话如果太短、几秒就说完，就按这个场景的背景再补一点，让它接近 10 秒。仍然不要超过 12 秒。",
            "补的内容从本场、前一场、后一场已经写出的事里来。不要另编这场没有的情节。",
            "前一场和后一场只作参考。这一场的话要承上启下，接得上刚才发生的事，也通向接下来的事。",
            "不要改写前一场和后一场，也不要把它们的整段情节搬进这一场。",
            "讲员的句子也这样做：承接上一场，通向下一场，并把人物的身份和关系说清楚。",
        ])
    elif span == 2:
        lines[0:0] = [
            "把当前这场和紧接着的下一场合成一段对话，写入当前这场的 speaking。",
            "两场里已经写出的事都要说到，按原来的先后，连成一来一往。",
            "前一场只用来接上刚才的事。再下一场只用来通向后面的事。这两场的整段情节不要搬进对话。",
        ]
        lines.extend([
            "speaking 用大约 16 到 20 秒说完这两场。不要超过 22 秒。",
            "两场的话如果太长，就压到这个时长里，两场的关键事仍要留下。",
            "两场的话如果太短，就按这两场已经写出的情景补到接近 16 秒。不要另编没有的情节。",
        ])
    else:
        lines[0:0] = [
            "把当前这场、下一场、再下一场这三场合成一段对话，写入当前这场的 speaking。",
            "三场里已经写出的事都要说到，按原来的先后，连成一来一往。",
            "前一场只用来接上刚才的事。三场之后的那场只用来通向后面的事。这两场的整段情节不要搬进对话。",
        ]
        lines.extend([
            "speaking 用大约 22 到 28 秒说完这三场。不要超过 30 秒。",
            "三场的话如果太长，就压到这个时长里，三场的关键事仍要留下。",
            "三场的话如果太短，就按这三场已经写出的情景补到接近 22 秒。不要另编没有的情节。",
        ])
    lines.extend(["", *slots, "", "只返回一个 JSON 对象，键只有 speaking。不要解释。", ""])
    lines.extend([
        "前一场（衔接）：",
        dump(previous if isinstance(previous, dict) else None, empty="（没有前一场）"),
        "",
    ])
    for offset, item in enumerate(merged):
        title = "当前这场（要说完）" if offset == 0 else f"后面第{offset}场（要说完）"
        if span == 1:
            title = "本场现在的内容"
        lines.extend([title + "：", dump(item, empty="（没有）"), ""])
    tail_title = "后一场（衔接）" if span == 1 else "合并之后的一场（衔接）"
    lines.extend([
        tail_title + "：",
        dump(after_ref, empty="（没有这场）"),
    ])
    text = "\n".join(lines)
    shown = label if span == 1 else f"{label}（{span}场）"
    return shown, text


def _target_style_prompt(*, remove_text: bool, style: str, period: str) -> str:
    """把画面转成项目选定的风格。remove_text 时同时去掉说明文字。"""
    lines = [
        "This prompt has two uses. Follow only the section that matches the tool.",
        "",
        "IMAGE — one still picture.",
        "Keep the same composition, the same people, the same action, and the same story moment.",
        "Do not add people. Do not change who is doing what.",
        "Do not keep the original drawing style.",
        f"Restyle the whole picture into this target style: {style}.",
        "Faces, clothes, the place, and the objects all take that style. The story in the picture stays the same.",
    ]
    if remove_text:
        lines.extend([
            "Remove the explanation text. "
            "Story pictures and comic pages often have captions beside the picture, under it, or in a box, "
            "telling what the scene means or which part of the story this is.",
            "Those words are not part of the drawing. Remove them.",
            "Fill those areas with the picture that belongs there: paper, sky, wall, ground, or the rest of the illustration.",
            "Do not leave empty boxes. Do not redraw the story.",
        ])
    else:
        lines.append("Keep any words already drawn in the picture, restyled to match the target style.")
    lines.extend([
        "",
        "VIDEO — a clip that starts from the attached picture.",
        "Frame one is the attached picture, unchanged, in its original style.",
        f"Across the whole clip, the picture moves little by little into this target style: {style}.",
        "The change must be a visible gradient. A viewer should see the style change step by step. "
        "Do not cut, do not swap styles in one frame, do not finish the change in the first moments.",
        "While the style is changing, the people begin to perform: small motion first, "
        "then the action already shown in the picture.",
        "Keep the same people, the same place, and the same composition.",
        "Do not add people. Do not change who is doing what.",
    ])
    if remove_text:
        lines.extend([
            "Frame one still has the explanation text.",
            "The captions fade away little by little until the picture is clean. "
            "A viewer should see the words disappear, not a cut.",
            "Fill those areas with the picture that belongs there.",
        ])
    if period:
        lines.extend(["", period])
    return "\n".join(lines)


def build_picture_transform_prompt(kind: str, region: str, era: str, visual_style: str = "") -> str:
    """同一段提示词写明两条路：静图直接变成结果；视频从原图渐变到结果，同时开始表演。"""
    kind = (kind or "").strip()
    phrase = setting_place_phrase(region, era)
    period = ""
    if phrase:
        period = (
            f"Place and period: {phrase}. "
            "Clothing, buildings, streets, objects, and faces must belong to this place and this time."
        )
    if kind == "detext":
        lines = [
            "This prompt has two uses. Follow only the section that matches the tool.",
            "",
            "IMAGE — the same picture with the explanation text removed.",
            "Remove captions, titles, and paragraphs that explain the story. They are plain text, not part of the drawing.",
            "Fill those areas with the picture that belongs there: paper, sky, wall, or the rest of the illustration.",
            "Keep the people, the scene, the composition, and the drawing style.",
            "Do not add people. Do not redraw the story.",
            "",
            "VIDEO — a clip that starts from the attached picture.",
            "Frame one still has the explanation text.",
            "The text fades away little by little until the picture is clean. A viewer should see it disappear, not a cut.",
            "While the text goes, the people begin to perform the action already in the picture.",
            "Keep the same people, the same place, and the same drawing style.",
        ]
        if period:
            lines.extend(["", period])
        return _with_picture_character_refs("\n".join(lines))
    if kind in ("softer", "softer_no_text", "to_style", "to_style_no_text"):
        style = (visual_style or "").strip()
        if not style:
            raise ValueError("请先在项目里选定画面风格。")
    if kind in ("softer", "softer_no_text"):
        return _with_picture_character_refs(
            _softer_transform_prompt(
                remove_text=(kind == "softer_no_text"),
                style=style,
                period=period,
            )
        )
    if kind in ("to_style", "to_style_no_text"):
        return _with_picture_character_refs(
            _target_style_prompt(
                remove_text=(kind == "to_style_no_text"),
                style=style,
                period=period,
            )
        )
    if kind == "realistic" and not period:
        raise ValueError("真实画面需要先选定地域和时代。")
    if kind == "extract":
        lines = [
            "This prompt has two uses. Follow only the section that matches the tool.",
            "",
            "IMAGE — one clean upper-body portrait of each person already in the attached picture.",
            "Extract every person. Do not add anyone. Do not drop anyone.",
            "Show each person from the waist up, turned to face the viewer.",
            "If two people are facing each other, both turn toward the camera.",
            "Facial features must be large and readable: eyes, nose, mouth, face shape.",
            "Clothes must be clear: color, cut, collar, sleeves, pattern.",
            "Hands are empty and still. Remove anything they were holding: cups, fans, books, tools, weapons, cloth, or any other object.",
            "Remove the action, the furniture, the scenery, the writing, and every other prop. Nothing remains except the person.",
            "Keep each person's identity, age, and the clothes they already wear.",
            "Plain empty background. A clean picture of the face and the clothes.",
            "",
            "VIDEO — a clip that starts from the attached picture.",
            "Frame one is the attached picture, unchanged.",
            "Each person slowly turns to face the camera, puts down whatever is in their hands, and the shot settles on a clean upper body.",
            "The change must be a visible gradient. Do not cut.",
            "By the end: waist-up, empty hands, readable face, clear clothes, plain background, no objects left.",
            "Do not add people. Do not change who they are or what they wear.",
        ]
        if phrase:
            lines.extend([
                "",
                f"Place and period: {phrase}. "
                "The clothes and the face belong to this place and this time. "
                "Do not bring back buildings, streets, or objects.",
            ])
        return _with_picture_character_refs("\n".join(lines))
    still, video_end = _picture_transform_body(kind, period)
    lines = [
        "This prompt has two uses. Follow only the section that matches the tool.",
        "",
        "IMAGE — one still picture.",
        "Keep the same composition, the same people, the same action, and any words already drawn.",
        "Do not add people. Do not change who is doing what.",
        "Output this finished look: " + still,
        "",
        "VIDEO — a clip that starts from the attached picture.",
        "Frame one is the attached picture, unchanged, in its original style "
        "(line art, watercolor, ink, color painting, or a real scene — whatever it already is).",
        "Across the whole clip, the style moves little by little toward " + video_end + ".",
        "The change must be a visible gradient. A viewer should see it happen step by step. "
        "Do not cut, do not swap styles in one frame, do not finish the change in the first moments.",
        "While the style is changing, the people begin to perform: small motion first, "
        "then the action already shown in the picture. Style change and performance happen together.",
        "Keep the same people, the same place, and the same composition.",
        "Do not add people. Do not change who is doing what.",
    ]
    if period:
        lines.extend(["", period])
    return _with_picture_character_refs("\n".join(lines))

# NotebookLM 导出：四大类 × 子类型（UI 菜单与 build 函数共用）
NOTEBOOKLM_EXPORT_VARIANTS: dict[str, list[tuple[str, str]]] = {
    "image": [
        ("single", "单图 · 一张概括全部场景"),
        ("slideshow", "幻灯片 · 每场景独立一图"),
    ],
    "video": [
        ("act_one", "只演不说 · 单画面（动作/表情/场景演进，讲员可评述）"),
        ("act_two", "只演不说 · 两画面（起始画面到结束画面，讲员可评述）"),
    ],
}

_NB_EXPORT_DEFAULT_VARIANT = {
    "image": "slideshow",
    "video": "act_one",
}


def normalize_nb_export_mode(mode: str, variant: str = "") -> tuple[str, str]:
    """解析 ``image/slideshow``、``image_slideshow`` 或 legacy ``image`` → (base, variant)。"""
    raw = (mode or "").strip()
    if raw == "speak":
        raw = "video"
    if "/" in raw:
        base, var = raw.split("/", 1)
        base, var = base.strip(), var.strip()
    elif "_" in raw:
        base, var = raw.split("_", 1)
        base, var = base.strip(), var.strip()
    else:
        base, var = raw, (variant or "").strip()
    if base not in NOTEBOOKLM_EXPORT_VARIANTS:
        raise ValueError(f"Unknown NotebookLM export mode: {mode!r}")
    if not var:
        var = _NB_EXPORT_DEFAULT_VARIANT[base]
    if base == "video" and var in (
        "motion",
        "act_quiet",
        "word_in_image",
        "scene_real",
        "interact",
        "inner",
    ):
        var = "act_one"
    elif base == "video" and var == "start_end":
        var = "act_two"
    valid = {v for v, _ in NOTEBOOKLM_EXPORT_VARIANTS[base]}
    if var not in valid:
        raise ValueError(f"Unknown variant {var!r} for mode {base!r}")
    return base, var


def nb_export_mode_label(mode: str, variant: str = "") -> str:
    """人类可读标签，供弹窗标题使用。"""
    base, var = normalize_nb_export_mode(mode, variant)
    labels = {v: lbl for v, lbl in NOTEBOOKLM_EXPORT_VARIANTS[base]}
    base_names = {
        "image": "Image",
        "video": "Video",
    }
    return f"{base_names.get(base, base)} · {labels.get(var, var)}"


_NB_EXPORT_CAT_LABELS = {
    "image": "Image 幻灯片",
    "video": "Video 视频",
}

_NB_EXPORT_CHOICE_ALIASES = {
    "单图": ("image", "single"),
    "image/单图": ("image", "single"),
    "image/single": ("image", "single"),
    "image_single": ("image", "single"),
    "slideshow": ("image", "slideshow"),
    "image/slideshow": ("image", "slideshow"),
    "image/幻灯片": ("image", "slideshow"),
    "纯画面": ("video", "act_one"),
    "video/纯画面": ("video", "act_one"),
    "video/motion": ("video", "act_one"),
    "video_motion": ("video", "act_one"),
    "motion": ("video", "act_one"),
    "act_quiet": ("video", "act_one"),
    "video/act_quiet": ("video", "act_one"),
    "文字动画": ("video", "act_one"),
    "心里话": ("video", "act_one"),
    "原画面": ("video", "act_one"),
    "start_end": ("video", "act_two"),
    "两画面": ("video", "act_two"),
}

# Grok 场景 video：NotebookLM 提示词（不含图片）
GROK_SCENE_VIDEO_NB_VARIANTS: list[tuple[str, str, str]] = [
    ("video", "act_one", "只演不说 · 单画面（动作/表情/场景演进，讲员可评述）"),
    ("video", "act_two", "只演不说 · 两画面（起始画面到结束画面，讲员可评述）"),
]
GROK_SCENE_VIDEO_NB_DEFAULT_INDEX = 1


def grok_scene_video_nb_export(index: int | None = None) -> tuple[str, str, str]:
    """``index`` 从 1 到列表长度 → ``(base, variant, short_label)``."""
    rows = GROK_SCENE_VIDEO_NB_VARIANTS
    if not rows:
        return ("video", "act_one", "只演不说 · 单画面")
    try:
        i = int(index) if index is not None else GROK_SCENE_VIDEO_NB_DEFAULT_INDEX
    except (TypeError, ValueError):
        i = GROK_SCENE_VIDEO_NB_DEFAULT_INDEX
    if i < 1 or i > len(rows):
        i = GROK_SCENE_VIDEO_NB_DEFAULT_INDEX
    base, var, lbl = rows[i - 1]
    return base, var, lbl


def grok_scene_video_nb_choice_label(index: int | None = None) -> str:
    base, var, short = grok_scene_video_nb_export(index)
    try:
        return nb_export_mode_label(base, var)
    except ValueError:
        return f"{base}/{var} · {short}"


def format_grok_scene_video_nb_choices() -> str:
    lines = [f"grv <profile> <1…{len(GROK_SCENE_VIDEO_NB_VARIANTS)}>  video 提示词变体："]
    for i, (base, var, lbl) in enumerate(GROK_SCENE_VIDEO_NB_VARIANTS, start=1):
        cat = _NB_EXPORT_CAT_LABELS.get(base, base)
        lines.append(f"  {i}: {cat} / {lbl}  ({base}/{var})")
    default = GROK_SCENE_VIDEO_NB_DEFAULT_INDEX
    lines.append(f"默认：{default}（{grok_scene_video_nb_choice_label(default)}）")
    return "\n".join(lines)


GROK_SCENE_VIDEO_NB_CHOICE = "只演不说 · 单画面"


def notebooklm_export_flat_choices(lang_label: str = "") -> list[tuple[str, str, str]]:
    """Flatten nested NotebookLM menu → ``[(label, base, variant), ...]``.

    CLI 用编号单选代替 GUI 的两级菜单。第一项是 Image / 单图。
    """
    suffix = f" ({lang_label})" if (lang_label or "").strip() else ""
    out: list[tuple[str, str, str]] = []
    for base, variants in NOTEBOOKLM_EXPORT_VARIANTS.items():
        cat = _NB_EXPORT_CAT_LABELS.get(base, base) + suffix
        for var, var_label in variants:
            out.append((f"{cat} / {var_label}", base, var))
    return out


def parse_nb_export_choice(want: str) -> tuple[str, str] | None:
    """Parse ``image/single`` / ``image/单图`` / ``单图`` → ``(base, variant)``."""
    raw = (want or "").strip()
    if not raw:
        return None
    compact = raw.lower().replace(" ", "")
    for alias, pair in _NB_EXPORT_CHOICE_ALIASES.items():
        if alias.lower().replace(" ", "") == compact:
            return pair
    try:
        return normalize_nb_export_mode(raw)
    except ValueError:
        return None


def _image_painting_direction(scene: dict, use_visual: bool = True) -> str:
    parts: list[str] = []
    vis = (scene.get("visual") or scene.get("story") or "").strip() if use_visual else ""
    actor = (scene.get("actor") or "").strip()
    speaking = (scene.get("speaking") or scene.get("story_content") or "").strip()
    caption = (scene.get("caption") or "").strip()
    if caption:
        parts.append(f"Scene title: {caption}")
    if vis:
        parts.append(f"Scene visual: {vis}")
    if actor:
        parts.append(f"Character (actor): {actor}")
    if speaking:
        parts.append(
            "Speaking (<N> is that person's place in actor; paint who speaks and the mood in face, eyes, posture, gesture — NOT as on-image text): "
            + speaking
        )
    voiceover = (scene.get("voiceover") or "").strip()
    if voiceover:
        parts.append("Voiceover: " + voiceover)
    return "\n".join(parts)


def _slim_scene_fields(scene: dict, keys: tuple[str, ...]) -> dict:
    """从场景 dict 按字段名裁剪非空值。"""
    slim: dict = {}
    for k in keys:
        val = scene.get(k)
        if isinstance(val, str):
            if not val.strip():
                continue
        elif not val:
            continue
        slim[k] = val
    return slim


# 工作流场景 dict 中的媒体/技术字段，NotebookLM 导出一律剔除
_NOTEBOOKLM_WORKFLOW_ONLY_KEYS = frozenset({
    "id",
    "environment",
    "start",
    "end",
    "duration",
    "zero",
    "zero_image",
    "zero_audio",
    "zero_image_last",
    "zero_left",
    "zero_right",
    "clip",
    "clip_audio",
    "clip_image",
    "clip_image_last",
    "clip_left",
    "clip_right",
    "narration",
    "narration_audio",
    "narration_image",
    "narration_image_last",
    "narration_left",
    "narration_right",
    "visual_style",
    "clip_animation",
    "narration_animation",
    "title_font",
    "extension",
    "cinematography",
    "story",
})


def _notebooklm_scene_content_base(scene: dict) -> dict:
    """工作流/列表场景 → 仅保留 NotebookLM 文案字段（就地 normalize）。"""
    import project_manager

    if not isinstance(scene, dict):
        return {}
    out = {
        k: v
        for k, v in scene.items()
        if k not in _NOTEBOOKLM_WORKFLOW_ONLY_KEYS
    }
    project_manager.normalize_scene_content_item_for_workflow(out)
    if "actor" in out:
        out["actor"] = project_manager.actor_text_for_generation(out.get("actor") or "")
    return out


def scene_payload_for_notebooklm_export(
    scenes: list, mode: str, variant: str = "", narrator: str = "", use_visual: bool = True
) -> list[dict]:
    """按 NotebookLM 导出模式裁剪 scene JSON。``use_visual=False`` 时图片模式不带场景描述。"""
    base, var = normalize_nb_export_mode(mode, variant)

    new_scenes = []
    for scene in scenes:
        new_scene = _notebooklm_scene_content_base(scene)

        if base == "video":
            if var in ("act_one", "act_two"):
                new_scenes.append(
                    _slim_scene_fields(
                        new_scene,
                        ("actor", "visual", "speaking", "voiceover"),
                    )
                )
                continue
            slim = _slim_scene_fields(
                new_scene,
                ("visual", "speaking", "voiceover"),
            )
            slim["show_this_content_____not_speaking"] = new_scene.pop("speaking", "")+" ~~~ "+new_scene.pop("voiceover", "")
            new_scenes.append(slim)
            continue

        # To Generate Image
        slim = {}
        painting = _image_painting_direction(new_scene, use_visual)
        if painting:
            slim["show_this_content"] = painting
        new_scenes.append(slim)

    return new_scenes


def scene_payload_for_slideshow_images(
    scenes: list, mode, variant: str = "", narrator: str = ""
) -> list[dict]:
    """兼容旧名；委托 ``scene_payload_for_notebooklm_export``。"""
    return scene_payload_for_notebooklm_export(scenes, mode, variant, narrator=narrator)


NOTEBOOKLM_VIDEO_ACT_SPEECH = """
** Story people do not speak. No lip-sync. A 人物 line is not heard.
** Show the story through action, facial expression, and how the scene changes. Use ``visual`` for that change.
** Read ``actor`` from left to right. Skip anyone named 不出现. Entry 1's text is ``speaking``. Entry 2's text, if any, is ``voiceover``.
** A 讲员 in entry 1 or entry 2 may speak that entry's line aloud as commentary.
** A 讲员 listed in ``actor`` appears on screen, says only that commentary, then leaves. Face and clothes match the 讲员's reference portrait.
** If no 讲员 is listed in ``actor``, nobody speaks on screen. Any commentary is an off-screen voice-over: no narrator is drawn and no mouth moves. Otherwise action, expression, and place sounds only.
** When the 讲员 speaks, every 人物 mouth stays closed. One voice at a time. No music.
"""

NOTEBOOKLM_VIDEO_ACT_ONE = """
** One scene picture is attached. Picture 1 is the only scene. Keep the same place and the same people.
** Evolve action, expression, and the scene inside this one picture. Do not cut to a second scene.
** Pictures after picture 1 are actor references, in ``actor`` order, skipping 不出现.
** A 人物 reference only shows who is already in picture 1. Do not walk a 人物 in or out. That mouth stays closed.
""" + NOTEBOOKLM_VIDEO_ACT_SPEECH

NOTEBOOKLM_VIDEO_ACT_TWO = """
** Picture 1 is the opening scene. Picture 2 is the ending scene.
** Move from picture 1 to picture 2. The audience sees the start, the change, and the end.
** Carry that change with action, facial expression, and the place itself.
** Pictures after picture 2 are actor references, in ``actor`` order, skipping 不出现.
** A 人物 reference only shows who is already in the scenes. Do not walk a 人物 in or out. That mouth stays closed from the opening frame through the ending frame.
""" + NOTEBOOKLM_VIDEO_ACT_SPEECH

VIDEO_FLOW_FRAME_CHOICES = (
    ("one", "单画面"),
    ("two", "多画面"),
)
VIDEO_FLOW_BACKGROUND_CHOICES = (
    ("none", "不加"),
    ("art_text", "背景文字"),
    ("bubble", "思想泡泡"),
)
VIDEO_FLOW_EVOLVE_CHOICES = (
    ("keep", "风格不变"),
    ("to_style", "演进到目标风格"),
    ("to_style_page", "翻书到目标风格"),
    ("to_style_dissolve", "叠化到目标风格"),
)
VIDEO_FLOW_CAMERA_CHOICES = (
    ("none", "默认"),
    ("wide", "广角 (Wide)"),
    ("close", "特写 (Close-up)"),
    ("push", "推进 (Push In)"),
    ("pull", "拉远 (Pull Back)"),
    ("arc", "环绕 (Arc)"),
    ("track", "跟拍 (Tracking)"),
    ("rotate", "转镜 (Rotate)"),
    ("timelapse", "延时 (Time-lapse)"),
)
# 旧「动画」里的转镜 / 延时并入运镜；其余动画项已改为项目级「场景风格」。
_MOTION_TO_CAMERA = {"转镜 (Rotate)": "rotate", "延时 (Time-lapse)": "timelapse"}


def video_flow_choice_label(
    frames: str,
    background: str,
    evolve: str,
    camera: str = "none",
    motion: str = "",
    narrative: str = "story",
    text: str = "erase",
) -> str:
    """把这几组选择写成一行，供窗口标题和提示词开头使用。"""
    narrative_label = dict(SLIDE_FLOW_NARRATIVE_CHOICES).get(narrative, narrative).split("（")[0]
    frame_label = dict(VIDEO_FLOW_FRAME_CHOICES).get(frames, frames)
    caption_label = dict(FLOW_CAPTION_CHOICES).get(text, text)
    parts = [narrative_label, frame_label, caption_label]
    if text == "keep":
        bg_label = dict(VIDEO_FLOW_BACKGROUND_CHOICES).get(background, background)
        parts.append(bg_label)
    if frames != "two":
        evolve_label = dict(VIDEO_FLOW_EVOLVE_CHOICES).get(evolve, evolve)
        parts.append(evolve_label)
    if camera and camera != "none":
        parts.append(dict(VIDEO_FLOW_CAMERA_CHOICES).get(camera, camera))
    if (motion or "").strip():
        parts.append(motion.strip())
    return " · ".join(parts)


def _video_flow_camera_line(camera: str) -> str:
    """默认不写运镜。选了具体镜头，就只写这一句。"""
    lines = {
        "wide": "** Camera: wide-angle. Show the place and the people together. Do not push in to a face.",
        "medium": "** Camera: a medium shot. People from about the waist up, with some of the place still visible.",
        "close": "** Camera: a close-up. Stay on the face or the important detail. Do not pull back to a wide view.",
        "push": "** Camera move: push in, a slow zoom toward the subject, ending closer than it began.",
        "pull": "** Camera move: pull back, widening from the subject until more of the place is in frame.",
        "push_pull": "** Camera move: zoom in, hold briefly, then zoom back out. One push and one pull, not a shake.",
        "pan": "** Camera move: pan across the picture, left or right, following what the scene is looking at.",
        "tilt": "** Camera move: tilt upward, from a lower part of the picture toward what is above.",
        "arc": "** Camera move: a short arc around the subject. The place stays recognizable.",
        "track": "** Camera move: tracking. The camera travels with the person or the action. Do not leave them behind.",
        "rotate": "** Camera move: the camera rotates slowly around the scene.",
        "timelapse": "** Camera: time-lapse. Time passes in the picture. Light shifts, shadows lengthen, and the change is gradual.",
        "handheld": "** Camera: handheld. A little natural sway. Not a locked tripod, and not a wild shake.",
        "compound": "** Camera move: one compound move, for example a push-in that also pans. Keep it readable. Do not stack several unrelated moves.",
    }
    return lines.get(camera) or (
        "** Do not prescribe a camera move. No push-in, pull-back, pan, tilt, zoom, arc, tracking, or handheld shake, "
        "unless ``visual`` already describes one."
    )


def _video_narrative_speech(
    narrative: str,
    *,
    use_visual: bool = True,
    use_speaking: bool = True,
    has_speaker: bool = True,
) -> str:
    """叙事风格决定这一段里谁说话。讲述类：has_speaker = actor 里有讲员（出镜），否则画外旁白。"""
    if narrative in TELLING_NARRATIVES:
        key = scene_content_key(narrative)
        if narrative == "narration":
            head = "** Narrative style is telling (讲述). The visuals carry the content with places, objects, symbols, and background text."
        else:
            head = ("** Narrative style is a presentation, a variant of telling. The diagram or the brief is the main thing, "
                    "not a story scene. People rarely appear; if they do, they only support silently.")
        if not has_speaker:
            who = (f"** The 讲员 narrates ``{key}`` as an off-screen voice-over. Do not show a narrator. "
                   "Nobody on screen speaks. No lip-sync.")
        else:
            who = (f"** The 讲员 listed in ``actor`` appears on camera and narrates ``{key}``. Lip-sync only for the 讲员. "
                   "Other people act silently; their mouths do not move.")
        return "\n".join([
            head,
            who,
            f"** ``{key}`` is narration, never a line for anyone in the picture.",
            "** ``visual`` is only a reference for the place, the angle, and the look.",
            "** One voice only: the 讲员. No music.",
        ])
    if not has_speaker:
        return """** Narrative style is story. The characters act and talk with each other inside the scene.
** ``speaking`` / ``voiceover`` are the Dialogue (讲话). No actor list was given: invent the characters from it.
** Pure character performance. No 讲员, no narrator, no voice-over.
** ``visual`` is only a reference for the place, the angle, and the look.
** Show the story through action and talk. One voice at a time. No music."""
    return """** Narrative style is story. The characters act and talk with each other inside the scene.
** Read ``actor`` from left to right. Skip anyone named 不出现. Each listed person uses their own character image: look, gender, age band, and ethnicity.
** ``speaking`` and ``voiceover`` are the Dialogue (讲话). Entry 1's text is ``speaking``. Entry 2's text, if any, is ``voiceover``.
** A 人物 speaks that entry's line inside the story. That mouth moves only for that line. The others listen or react.
** If ``actor`` includes a 讲员: the story people lead and talk; the 讲员 is supporting, stands apart, and may appear at the start to introduce or at the end to sum up, bridge, or ask a question. Never taking over.
** If ``actor`` has no 讲员: pure character performance, no narrator.
** ``visual`` is only a reference for the place, the angle, and the look. The story does not depend on it.
** When the story needs a person who is not yet in the frame, that person may enter.
** One voice at a time. No music."""



def _video_narrative_block(
    narrative: str,
    *,
    use_visual: bool = True,
    use_speaking: bool = True,
    has_speaker: bool = True,
) -> str:
    """和幻灯、图片同一套叙事风格。场景 JSON 的字段名在这里对上 Shown / Said / Actors。"""
    if narrative not in SLIDE_FLOW_NARRATIVE_NOTES:
        narrative = "story"
    if narrative == "story":
        rules = _slide_flow_story_rules(use_visual, use_speaking, has_speaker)
    elif narrative == "narration":
        rules = _slide_flow_narration_rules(use_visual, use_speaking, has_speaker)
    else:
        rules = _slide_flow_report_rules(use_visual, use_speaking, has_speaker)
    if narrative in TELLING_NARRATIVES:
        field_map = (
            f"In Story_Scene_Content, ``visual`` is Shown, ``{scene_content_key(narrative)}`` is "
            f"{scene_content_label(narrative)} (the 讲员's narration), and ``actor``, when present, is Actors."
        )
    else:
        field_map = (
            "In Story_Scene_Content, ``visual`` is Shown, ``speaking`` and ``voiceover`` together are the Dialogue (讲话), "
            "and ``actor`` is Actors."
        )
    return "\n\n".join([
        "This is one moving clip of the current scene. The narrative style decides how it develops.",
        field_map,
        SLIDE_FLOW_NARRATIVE_NOTES[narrative],
        _slide_flow_inputs_note(use_visual, use_speaking, has_speaker, False, narrative),
        rules,
    ])



def _video_flow_instruction(
    frames: str,
    background: str,
    evolve: str,
    visual_style: str,
    camera: str = "none",
    motion: str = "",
    narrative: str = "story",
    text: str = "erase",
    *,
    use_visual: bool = True,
    use_speaking: bool = True,
    has_speaker: bool = True,
) -> str:
    """按这一次的画面、背景、演进、叙事风格和说明文字，只写用得上的那几段。"""
    style = (visual_style or "").strip() or "realistic"
    chunks: list[str] = []
    if frames == "two":
        two_core = """** Picture 1 is the opening frame. Picture 2 is the ending frame.
** Move from picture 1 to picture 2. The audience sees the start, the change, and the end.
** Carry that change with action, facial expression, and the place itself.
** Picture 1's look is the start. Picture 2's look is the end. Do not invent another visual style between them."""
        if has_speaker:
            two_core += """
** Pictures after picture 2, if any are pasted, are actor references in ``actor`` order, skipping 不出现.
** A 人物 reference only shows who that person is."""
        else:
            two_core += (
                "\n** The 讲员 is heard only as an off-screen voice-over. Do not show a narrator or host on screen."
                if narrative in TELLING_NARRATIVES
                else "\n** Do not add a narrator, host, or off-screen speaker."
            )
        chunks.append(two_core)
    else:
        one_core = """** One scene picture is attached. Picture 1 is the only scene. Keep the same place."""
        if has_speaker:
            one_core += """
** Pictures after picture 1, if any are pasted, are actor references in ``actor`` order, skipping 不出现.
** A 人物 reference only shows who that person is."""
        else:
            one_core += (
                "\n** The 讲员 is heard only as an off-screen voice-over. Do not show a narrator or host on screen."
                if narrative in TELLING_NARRATIVES
                else "\n** Do not add a narrator, host, or off-screen speaker."
            )
        chunks.append(one_core)
        if evolve == "to_style":
            chunks.append(
                f"""** Open on picture 1 and hold its original style long enough to read it.
** Then slowly change that look into the target visual style: {style}.
** The audience must see the change. Show the starting look, a halfway look, and the finished {style}. Do not jump. Do not finish the change in a flash.
** No page turn, no dissolve trick, no wipe, no flash. The picture itself changes.
** Same people, same place, recognizable at every moment.
** If a 讲员 is in ``actor``, their commentary may play while the style is still changing. If there is no 讲员, keep the clip silent of speech."""
            )
        elif evolve == "to_style_page":
            chunks.append(
                f"""** Evolve picture 1 into the target visual style: {style}, by turning pages.
** The whole change takes about four to five seconds.
** Each turned page is visibly closer to {style} than the page before. The audience must see the approach. Do not land on the finished style at the first turn.
** The last page is {style}.
** Same people, same place, recognizable on every page.
** This is a page turn. Do not replace it with a plain fade or a jump cut."""
            )
        elif evolve == "to_style_dissolve":
            chunks.append(
                f"""** Evolve picture 1 into the target visual style: {style}, through several soft dissolves.
** The whole change takes about four to five seconds.
** Each dissolve lands closer to {style}. Show the starting look, at least two in-between looks, and the finished {style}.
** The audience must see the approach. Do not finish it in one blend.
** No page curl, no wipe, no flash. The dissolves themselves carry the change.
** Same people, same place, recognizable in every blend."""
            )
        else:
            chunks.append(
                f"""** Keep the visual style of picture 1 for the whole clip. Do not restyle it.
** The target style of this project is {style}. Do not move the picture toward that style.
** Still show action, facial expression, and the scene change in ``visual``, inside the original style.
** The change stays gentle. The audience remains in the same picture."""
            )
    if narrative not in SLIDE_FLOW_NARRATIVE_NOTES:
        narrative = "story"
    if text not in {k for k, _ in FLOW_CAPTION_CHOICES}:
        text = "erase"
    chunks.append(
        _video_narrative_speech(
            narrative,
            use_visual=use_visual,
            use_speaking=use_speaking,
            has_speaker=has_speaker,
        )
    )
    chunks.append(
        _video_narrative_block(
            narrative,
            use_visual=use_visual,
            use_speaking=use_speaking,
            has_speaker=has_speaker,
        )
    )
    if text == "keep":
        content_fields = (
            f"``{scene_content_key(narrative)}``"
            if narrative in TELLING_NARRATIVES
            else "``speaking`` and ``voiceover``"
        )
        if background == "art_text":
            chunks.append(
                f"""** In the deep background, behind the people, place ONE short artistic keyword, blended into the place. It belongs to the picture, not to a subtitle bar.
** Take it from {content_fields}: Chinese at most 8 characters, English at most 3 words. Never a sentence, never a second line. 
** {KEYWORD_PLACE_SHORT_EN}
** Draw the letters in a hand that fits the picture. Do not cover faces.
** Do not turn the content into captions or spoken lines."""
            )
        elif background == "bubble":
            if narrative in TELLING_NARRATIVES:
                chunks.append(
                    """** Do not use a thought bubble. Nobody in the picture speaks. Keywords, if any, stay as background lettering only."""
                )
            else:
                chunks.append(
                    """** A small thought bubble may appear, as if a person is thinking. One bubble at a time.
** The bubble holds a keyword or a very short phrase from ``speaking`` or ``voiceover``. It sits near that person and does not cover the face.
** It is not a subtitle bar and not a paragraph. If there is no short phrase to think, show no bubble."""
                )
        else:
            chunks.append(
                f"""** Do not put words on the picture. No background writing, no thought bubble, no subtitle, no title card.
** {content_fields} are not text to draw."""
            )
    else:
        chunks.append(video_caption_rule(text))
    chunks.append(_video_flow_camera_line(camera))
    motion_line = _video_flow_motion_line(motion)
    if motion_line:
        chunks.append(motion_line)
    chunks.append(NOTEBOOKLM_VIDEO_NO_MUSIC.strip())
    return "\n".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())


def build_video_fyi_only_prompt(
    *,
    frames: str,
    evolve: str,
    visual_style: str,
    camera: str = "none",
    text: str = "erase",
    duration: str = "",
    fyi: str = "",
) -> str:
    """生场视频「只按注意 / FYI」：场景描述、讲话、人物都没勾，只有 FYI。同图片提示「仅修改」。

    FYI 是这段视频的主要动作说明（人做什么、发生什么）。让给出的起始图（多画面时到终止图）动起来，
    保留画面里的场景、人物和画风；不加人；不写叙事风格的讲话规则，默认没有旁白和对白（除非 FYI 另说）。
    运镜、长度、画风（风格演进）、说明文字照常；背景条件（地域 / 时代）由外层接在后面。
    """
    request = (fyi or "").strip()
    if frames not in {k for k, _ in VIDEO_FLOW_FRAME_CHOICES}:
        frames = "one"
    if evolve not in {k for k, _ in VIDEO_FLOW_EVOLVE_CHOICES} or frames == "two":
        evolve = "keep"
    if camera not in {k for k, _ in VIDEO_FLOW_CAMERA_CHOICES}:
        camera = "none"
    if text not in {k for k, _ in FLOW_CAPTION_CHOICES}:
        text = "erase"
    style = (visual_style or "").strip() or "realistic"
    lines = ["Main action (most important):", request or "(no action given: keep a gentle, natural motion)", ""]
    if frames == "two":
        lines += [
            "Picture 1 is the opening frame. Picture 2 is the ending frame.",
            "Animate from picture 1 to picture 2, carrying out the main action on the way.",
        ]
    else:
        lines += [
            "One picture is attached. Picture 1 is the first frame of the clip.",
            "Animate picture 1, carrying out the main action.",
        ]
    lines += [
        "Keep the place, the people, their faces and clothes, and the objects of the picture. "
        "Only what the main action asks for moves or changes.",
        "Do not add people. Do not remove anyone unless the main action says so.",
    ]
    if evolve == "keep":
        lines.append(f"Keep the visual style of picture 1 for the whole clip. Do not restyle it toward {style}.")
    else:
        how = {
            "to_style": "a slow continuous change",
            "to_style_page": "turning pages, each page closer to the target style",
            "to_style_dissolve": "several soft dissolves, each closer to the target style",
        }[evolve]
        lines.append(
            f"Open on picture 1's own style, then evolve the look into the target visual style: {style}, by {how}. "
            "The same people and place stay recognizable throughout."
        )
    lines.append(video_caption_rule(text))
    secs = "".join(ch for ch in (duration or "") if ch.isdigit())
    if secs:
        lines.append(f"Clip length: about {secs} seconds. Pace the main action to fill the clip; do not rush it or freeze at the end.")
    cam = _video_flow_camera_line(camera)
    if cam:
        lines.append(cam.lstrip("* ").strip())
    lines.append(
        "Sound: no narration, no voice-over, and no dialogue, unless the main action asks for speech. "
        "Natural ambient sound only."
    )
    lines.append(NOTEBOOKLM_VIDEO_NO_MUSIC.strip().lstrip("* ").strip())
    frame_label = dict(VIDEO_FLOW_FRAME_CHOICES).get(frames, frames)
    parts = ["只按注意 / FYI", frame_label, dict(FLOW_CAPTION_CHOICES).get(text, text)]
    if frames != "two":
        parts.append(dict(VIDEO_FLOW_EVOLVE_CHOICES).get(evolve, evolve))
    if camera != "none":
        parts.append(dict(VIDEO_FLOW_CAMERA_CHOICES).get(camera, camera))
    if secs:
        parts.append(f"{secs}s")
    # t244/t246: 全局禁字幕行必须是物理第一行
    result = (
        f"Visual_Style:\n{style}\n\n"
        f"Video_choices:\n{' · '.join(parts)}\n\n"
        "Instruction_for_video_generation:\n" + "\n".join(lines)
    )
    return ensure_video_no_subtitle_first_line(result)


# 性别 / 年龄段 / 民族 → 商业声音名。同一档有多个时，按书写顺序往下用。
ACTOR_VOICE_NAMES = {
    ("man", "youth", "chinese"): ("Leo",),
    ("man", "mature", "chinese"): ("Sal", "Atlas"),
    ("man", "senior", "chinese"): ("Zagan", "Rex"),
    ("woman", "youth", "chinese"): ("Carina",),
    ("woman", "mature", "chinese"): ("Celeste",),
    ("woman", "senior", "chinese"): ("Ara",),
    ("man", "youth", "english"): ("Helix", "Eve", "Lux", "Lumen"),
    ("man", "mature", "english"): ("Castor", "Cosmo", "Kepler", "Sirius"),
    ("man", "senior", "english"): ("Hellios", "Perseus"),
    ("woman", "youth", "english"): ("Iris",),
    ("woman", "mature", "english"): ("Ursa",),
    ("woman", "senior", "english"): ("Luna",),
}

_VOICE_AGE_BAND = {
    "kids": "youth",
    "teenager": "youth",
    "youth": "youth",
    "mature": "mature",
    "senior": "senior",
}


def actor_voice_storage_key(body: str, role: str) -> str:
    """项目里记下的键。讲员单独记，有名字的人物用完整写法。"""
    import project_manager

    raw, _motion = project_manager.split_actor_motion(body or "")
    canon = project_manager._person_body(raw) or (raw or "").strip()
    if not canon:
        return ""
    if role == "host":
        bits = [part for part in canon.split("/") if part]
        look = "/".join(bits[:3]) if len(bits) >= 3 else canon
        return "narrator:" + look
    return canon


def voice_choices_for_actor(body: str) -> tuple:
    """这一档性别、年龄段、民族可以选的商业声音。"""
    import project_manager

    raw, _motion = project_manager.split_actor_motion(body or "")
    canon = project_manager._person_body(raw) or (raw or "").strip()
    bits = [part.strip() for part in canon.split("/") if part.strip()]
    gender = bits[0].lower() if bits else ""
    gender = {"girl": "woman", "boy": "man", "female": "woman", "male": "man"}.get(gender, gender)
    age = project_manager._ACTOR_AGE.get(bits[1].lower(), bits[1].lower()) if len(bits) >= 2 else ""
    age = _VOICE_AGE_BAND.get(age, "") or "mature"
    race = bits[2].lower() if len(bits) >= 3 else ""
    # 默认表：没写民族 → chinese；其他民族 → english 那一档
    race = race if race in ("chinese", "english") else ("english" if race else "chinese")
    return ACTOR_VOICE_NAMES.get((gender, age, race), ())


def chosen_actor_voice(body: str, role: str) -> str:
    """用户在预览里选定的声音。还没选过时用这一档的第一个。"""
    import project_manager

    options = voice_choices_for_actor(body)
    if not options:
        return ""
    pc = project_manager.PROJECT_CONFIG if isinstance(project_manager.PROJECT_CONFIG, dict) else {}
    table = pc.get("actor_voices") if isinstance(pc, dict) else {}
    if not isinstance(table, dict):
        table = {}
    saved = str(table.get(actor_voice_storage_key(body, role)) or "").strip()
    if saved in options:
        return saved
    return options[0]


def speaking_voice_lines(scenes: list) -> str:
    """按 actor 位置标出商业声音名。第 1 个说 speaking，第 2 个说 voiceover。"""
    import project_manager

    scenes = [item for item in (scenes or []) if isinstance(item, dict)]
    if any(_SPEAKER_MARK.search(str(sc.get("speaking") or "")) for sc in scenes):
        # t111u: speaking 里有 <N>:第 N 个人说 <N> 后面的话(不是「第 1 个说 speaking」)
        tagged = _speaker_voice_line(scenes)
        if tagged:
            return ("** Use the voice written here for each speaker. Do not substitute another voice.\n** "
                    + tagged.replace("\n  ", "\n** "))

    def voice_for(body: str, role: str) -> str:
        return chosen_actor_voice(body, role)

    lines = [
        "** Use the voice name written here for that line. Do not substitute another voice.",
        "** Position 1 in actor says speaking. Position 2, when present, says voiceover.",
    ]
    noted = False
    many = len(scenes) > 1
    for index, scene in enumerate(scenes, start=1):
        actor_text = project_manager.actor_text_for_generation(scene.get("actor") or "")
        active = project_manager.active_actor_entries(actor_text)
        prefix = f"Scene {index}, " if many else ""
        pairs = (
            (0, "speaking", scene.get("speaking") or ""),
            (1, "voiceover", scene.get("voiceover") or ""),
        )
        for slot, field, text in pairs:
            if slot >= len(active) or not str(text).strip():
                continue
            row = active[slot]
            body, _motion = project_manager.split_actor_motion(row.get("body") or "")
            voice = voice_for(body, row.get("role") or "person")
            if not voice:
                continue
            label = "讲员" if row.get("role") == "host" else (row.get("label") or "人物")
            lines.append(f"** {prefix}{field}: {label} {body}. Voice: {voice}.")
            noted = True
    if not noted:
        return ""
    return "\n".join(lines)



def _video_prompt_scene_payload(
    scenes: list,
    *,
    variant: str,
    narrator: str,
    use_visual: bool,
    use_speaking: bool,
    has_speaker: bool,
    narrative: str,
) -> list[dict]:
    """生场视频提示用的场景 JSON：只留勾选的字段；叙事且无讲员时把讲话改名为内容。"""
    raw = scene_payload_for_notebooklm_export(
        scenes, "video", variant, narrator=narrator, use_visual=use_visual
    )
    out: list[dict] = []
    for sc in raw:
        if not isinstance(sc, dict):
            continue
        slim: dict = {}
        if use_visual and sc.get("visual"):
            slim["visual"] = sc["visual"]
        if has_speaker and sc.get("actor"):
            slim["actor"] = sc["actor"]
        speaking = (sc.get("speaking") or "").strip() if use_speaking else ""
        voiceover = (sc.get("voiceover") or "").strip() if use_speaking else ""
        if use_speaking and (speaking or voiceover):
            if narrative in TELLING_NARRATIVES:
                # Narration by the 讲员; never a "speaking" key, or on-screen people start talking.
                combined = " ".join(p for p in (speaking, voiceover) if p).strip()
                combined = re.sub(r"<\s*\d+(?:\.\d+)?\s*>", " ", combined)
                combined = re.sub(r"[ \t]{2,}", " ", combined).strip()
                if combined:
                    slim[scene_content_key(narrative)] = combined
            else:
                if speaking:
                    slim["speaking"] = speaking
                if voiceover:
                    slim["voiceover"] = voiceover
        out.append(slim)
    return out


# 故事风格（STORY 窗口的三种 Series 提示）：决定视频里谁说话、讲员出不出镜、人物怎么演。
STORY_STYLE_CHOICES = (
    ("podcast", "Series · Podcast"),
    ("counselor", "Series · Counselor"),
    ("story_speak", "Series · Story Speak"),
    ("story_act", "Series · Story Act"),
    ("tech", "技术方案汇报"),
    ("exec", "高管简报"),
)
# 故事风格是唯一的权威：生场视频的「叙事风格」也用这一套。每个故事风格对应提示词里的叙事方式（narrative）。
STORY_STYLE_NARRATIVE = {
    "podcast": "narration", "counselor": "narration",
    "story_speak": "story", "story_act": "story",
    "tech": "tech", "exec": "exec",
}
# 旧的生场视频「叙事风格」存值 → 故事风格（迁移用）
NARRATIVE_TO_STORY_STYLE = {"narration": "podcast", "story": "story_speak", "tech": "tech", "exec": "exec"}
STORY_STYLE_LABELS = tuple(label for _k, label in STORY_STYLE_CHOICES)


def normalize_story_style(value) -> str:
    """存值 / 标签（含旧写法 "Series . Podcast"、旧的 Story Only）→ podcast / counselor / story_speak / story_act；认不出返回空。"""
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower().replace("·", ".")
    if not text:
        return ""
    for key, label in STORY_STYLE_CHOICES:
        if text in (key, label.lower().replace("·", ".")):
            return key
    if "podcast" in text:
        return "podcast"
    if "counselor" in text:
        return "counselor"
    if "story act" in text or "story_act" in text:
        return "story_act"
    if "story only" in text or "story_only" in text or "story speak" in text or "story_speak" in text:
        return "story_speak"
    return ""


def story_style_narrative(value) -> str:
    """故事风格 → 提示词用的叙事方式（narration / story / tech / exec）。"""
    return STORY_STYLE_NARRATIVE.get(normalize_story_style(value) or STORY_STYLE_CHOICES[0][0], "narration")


def story_style_mode_text(value, actor_checked: bool) -> str:
    """生场视频窗口里「叙事风格」下面的蓝字说明。"""
    key = normalize_story_style(value) or STORY_STYLE_CHOICES[0][0]
    if key == "story_act":
        return ("Story Act：人物在场景中只表演、不在画面上开口说话；story_content 是这场发生的事，"
                "靠动作、表情、手势演出来。没有对白口型。如有内心独白／自言自语（<Ns>），"
                "是同一人物自己的画外心声，嘴巴不动、不对口型，不是旁白员换人。")
    if key == "story_speak":
        return ("Story Speak · " + narrative_mode_text("story", actor_checked)
                + " <N> 与 <Ns> 是同一个人（s 只表示自言自语，不是新角色）。"
                  "若这一场讲话只有一个说话回合且标记带 s（如 <1s>，可以有多句／换行），"
                  "则是该人物自己的内心独白：能听见他的声音（画外心声），全程嘴巴闭合、不对口型，不是旁白员。")
    if key == "podcast":
        return "Podcast（讲述）：主持人讲述 · " + narrative_mode_text("narration", actor_checked)
    if key == "counselor":
        return "Counselor（讲述）：咨询师讲述 · " + narrative_mode_text("narration", actor_checked)
    return narrative_mode_text(key, actor_checked)


def story_style_label(value) -> str:
    key = normalize_story_style(value) or STORY_STYLE_CHOICES[0][0]
    return dict(STORY_STYLE_CHOICES)[key]


def project_story_style() -> str:
    """项目里存的故事风格；没存过就看生成场景时用的 STORY 提示（scene_prompt_label）；都没有用 Podcast。"""
    try:
        import project_manager

        pc = project_manager.PROJECT_CONFIG or {}
    except Exception:  # noqa: BLE001
        pc = {}
    if not isinstance(pc, dict):
        pc = {}
    pp = pc.get("project_profile") if isinstance(pc.get("project_profile"), dict) else {}
    for raw in (pc.get("story_style"), pc.get("scene_prompt_label"), pp.get("scene_prompt_label")):
        key = normalize_story_style(raw)
        if key:
            return key
    # 迁移：旧的生场视频「叙事风格」（video_prompt.narrative），项目里还没有 story_style 时用它
    vp = pc.get("video_prompt") if isinstance(pc.get("video_prompt"), dict) else {}
    old = NARRATIVE_TO_STORY_STYLE.get(str(vp.get("narrative") or ""))
    if old:
        return old
    try:
        import project_manager

        last = normalize_story_style(getattr(project_manager, "LAST_STORY_STYLE", ""))
        if last:
            return last  # 项目里没存过：用上次选的
    except Exception:  # noqa: BLE001
        pass
    return STORY_STYLE_CHOICES[0][0]


from utility.speaking_marks import (  # noqa: E402
    PAUSE_MARK_RE as _PAUSE_MARK,
    SCENE_MONOLOGUE_RULE,
    SPEAKER_ID_RE as _SPEAKER_MARK,
    parse_speaking_turns,
    scene_speaking_source,
    scenes_speaking_is_single_inner_monologue,
    speaking_has_interactive_dialogue,
    speaking_has_monologue,
    speaking_is_all_inner_monologue,
    speaking_is_single_inner_monologue,
    strip_monologue_tag,
    strip_speaker_marks,
)

# <N> and <Ns> are the same person N; s is a speech mode, never an extra character.
SPEAKER_MARK_IDENTITY_RULE = (
    "Speaker marks: <N> and <Ns> (and legacy <N>（自言自语） / <N>（自言自語）) refer to the IDENTICAL actor N "
    "in the actor list (any multi-digit N: <1>=<1s>, <2>=<2s>, <3>=<3s>, <12>=<12s>); "
    "the letter s is a speech mode (self-talk / inner thought), not a new character, extra person, reference image, "
    "seat, costume, or voice; same identity, look, clothes, reference picture, and voice as <N>."
)

H3_MONOLOGUE_NO_LIPSYNC_RULE = (
    "Self-talk (自言自语): any line marked <Ns> or legacy <N>（自言自语） that is that character "
    "speaking to himself/herself (inner monologue / voiceover feel) is NOT interactive dialogue; "
    "only the other dialogue lines are interactive; "
    "self-talk lines have NO lip sync — that speaker keeps the mouth closed / not moving while that audio plays; "
    "<Ns> is the same person as <N>, never a different narrator or a different gender."
)

SINGLE_INNER_MONOLOGUE_RULE = (
    "Entire-scene inner monologue: this scene has exactly one speaking turn and that turn is self-talk "
    "(<Ns> or legacy 自言自语); count parser turns marked <N>/<Ns>, not punctuation sentences or wrapped lines; "
    "the audio is that same actor N's own inner voice / thinking, heard as voice-over; it is not mute and not another "
    "narrator; the character acts and thinks naturally with the mouth closed for the entire scene — no lip sync, "
    "no mouth speaking motion; no on-screen text or subtitles of the thought."
)


def _strip_speech_marks(text: str) -> str:
    return strip_speaker_marks(text, pauses=True)


def _video_cast(scenes: list, use_actor: bool) -> list:
    """actor 栏里要出场的人（跳过 不出现），按顺序。多场时取第一场有人的。"""
    import project_manager

    if not use_actor:
        return []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        text = project_manager.actor_text_for_generation(scene.get("actor") or "")
        rows = project_manager.active_actor_entries(text)
        if rows:
            return rows
    return []


def _speaker_slots(scenes: list) -> list:
    """speaking 里用到的 <N>（不含停顿）。没有标记但有话 → [1]。"""
    used: list = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        text = str(scene.get("speaking") or "")
        for m in _SPEAKER_MARK.finditer(text):
            n = int(m.group(1))
            if n not in used:
                used.append(n)
        if not used and text.strip():
            used.append(1)
        if str(scene.get("voiceover") or "").strip() and 2 not in used:
            used.append(2)
    return sorted(used)


def _who(row: dict) -> str:
    import project_manager

    body, _m = project_manager.split_actor_motion(row.get("body") or "")
    label = "讲员" if row.get("role") == "host" else (row.get("label") or "人物")
    return f"{label} {body}".strip()


_AGE_WORDS = {"kids": ("little", "a child's", "about 8-12"), "teenager": ("teenage", "a teenage", "about 15"),
              "youth": ("young", "a young", "20s"), "mature": ("middle-aged", "a mature", "40s-50s"),
              "senior": ("elderly", "an elderly", "60s+")}


def _speaker_identity(row: dict) -> tuple:
    """(称呼, 身份短语, 声音描述)：('阿明', 'young man', 'a young male voice, 20s')。"""
    import project_manager

    body, _m = project_manager.split_actor_motion(row.get("body") or "")
    bits = [b.strip() for b in body.split("/") if b.strip()]
    gender = bits[0].lower() if bits else ""
    age = project_manager._ACTOR_AGE.get(bits[1].lower(), bits[1].lower()) if len(bits) > 1 else ""
    name = bits[3] if len(bits) > 3 else ""
    host = row.get("role") == "host"
    male = gender in ("man", "boy", "male")
    female = gender in ("woman", "girl", "female")
    adj, voice_adj, years = _AGE_WORDS.get(age, ("", "a", ""))
    noun = ("boy" if male else "girl" if female else "child") if age == "kids" else (
        "man" if male else "woman" if female else "person")
    ident = " ".join(x for x in (adj, noun) if x)
    if host:
        ident = "narrator" + (f", {ident}" if bits[:1] and (male or female) else "")
    sex = "male" if male else "female" if female else ""
    tone = " ".join(x for x in (voice_adj, sex, "voice") if x) + (f", {years}" if years else "")
    who = name or ("讲员" if host else (row.get("label") or "人物"))
    return who, ident, tone


def _scene_speakers(scene: dict) -> list:
    """这一场 actor 里的人（按顺序，<N> = 第 N 个）。"""
    import project_manager

    text = project_manager.actor_text_for_generation(scene.get("actor") or "") if isinstance(scene, dict) else ""
    return project_manager.active_actor_entries(text)


GENDER_LOCK_LINE = (
    "Gender lock: every line is spoken only in its own speaker's voice: a MALE speaker's lines in a male voice, "
    "a FEMALE speaker's lines in a female voice, at that speaker's age. Never swap, even when a line says "
    "\"she\" / \"he\" or talks about the other person."
)


def scene_speaker_portraits(scene: dict, find_portrait) -> list:
    """t123u: 这一场的说话人（<N> 的顺序）里有形象图的：[(N, 名字, 图路径), ...]。没图的跳过。"""
    out = []
    for n, row in enumerate(_scene_speakers(scene) if isinstance(scene, dict) else [], 1):
        try:
            path = find_portrait(row) or ""
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 找人物形象图失败：{exc}")
            path = ""
        if path and os.path.isfile(path):
            name = _speaker_identity(row)[0] or f"Speaker {n}"
            out.append((n, name, path))
    return out


def portrait_reference_block(refs: list) -> str:
    """t123u: 视频提示词：说明第 1 张是场景/首帧，后面是第 N 位说话人的形象图，只用来认人。"""
    if not refs:
        return ""
    lines = ["REFERENCE IMAGES:", "- Reference image 1 is the scene / first frame of the video."]
    for i, (n, name, _path) in enumerate(refs, 2):
        lines.append(f"- Reference image {i} is the portrait of Speaker {n} {name}.")
    lines += [
        "Use the portraits only to identify which person in reference image 1 is each speaker.",
        "Each <N> / <Ns> tag is the same speaker N (the letter s is not another person or portrait). "
        "Interactive lines must be delivered by that exact person: lip movement and voice matching that speaker's "
        "gender, age and voice. Self-talk / inner-monologue lines (<Ns> or legacy 自言自语) use that same person's "
        "voice with no lip movement. Other people stay silent while someone else speaks.",
        "The portraits are identity references only: the video must start from reference image 1's composition. "
        "Do not add new people, do not insert the portraits as extra characters, and do not change the scene, "
        "background, art style or lighting.",
    ]
    return "\n".join(lines)


def _speaker_sex_word(row: dict) -> str:
    _name, _ident, tone = _speaker_identity(row)
    return "MALE" if " male voice" in tone else "FEMALE" if "female voice" in tone else ""


def _speaker_place_hint(scene: dict, name: str) -> str:
    """visual 里写这个人的第一句(到逗号为止),帮模型把声音对到画面里的人。"""
    vis = str((scene or {}).get("visual") or "") if isinstance(scene, dict) else ""
    if not name or name not in vis:
        return ""
    frag = re.split(r"[，。；,;.!?！？]", vis[vis.index(name):], maxsplit=1)[0].strip()
    return frag[:24]


def speaker_tag(row: dict, n: int, scene: dict | None = None) -> str:
    """'Speaker 1 = 陳偉: MALE, middle-aged man, 40s-50s, voice Sal (in picture: 陳偉坐駕駛座)'。"""
    import project_manager

    name, ident, tone = _speaker_identity(row)
    body, _m = project_manager.split_actor_motion(row.get("body") or "")
    voice = chosen_actor_voice(body, row.get("role") or "person")
    sex = _speaker_sex_word(row) or "gender as seen in the picture"
    bits = [sex, ident, tone.split(", ")[-1] if ", " in tone else ""]
    out = f"Speaker {n} = {name}: " + ", ".join(b for b in bits if b)
    out += f", {tone.split(',')[0]}" + (f" (voice {voice})" if voice else "")
    hint = _speaker_place_hint(scene or {}, name)
    if hint:
        out += f"; in the picture: {hint}"
    return out


def _unquote(text: str) -> str:
    return "".join(ch for ch in str(text or "") if ch not in "\"“”‘’「」『』").strip()


def dialogue_script(scene: dict) -> list:
    """speaking 的 <N> / <Ns> → 逐句台词。同一人连着说的合并成一句。
    ``<Ns>`` 与旧的 ``<N>（自言自语）`` 都表示该人物独白；标签从台词里去掉，
    独白标记写在行尾 ``[自言自语]``，供 ``_dialogue_turns`` 识别，不送给配音引擎朗读。"""
    if not isinstance(scene, dict):
        return []
    rows = _scene_speakers(scene)
    speaking = str(scene.get("speaking") or "")
    voiceover = str(scene.get("voiceover") or "").strip()
    if voiceover and "<2>" not in speaking:
        speaking = (speaking + " <2> " + voiceover).strip()
    parsed = parse_speaking_turns(speaking)
    tagged = []
    for turn in parsed:
        clean = _PAUSE_MARK.sub(" ", turn.text)
        clean = re.sub(r"[ \t]{2,}", " ", clean).strip()
        if clean:
            tagged.append([turn.speaker, clean, turn.monologue])
    merged: list = []
    for n, chunk, mono in tagged:
        if not chunk:
            continue
        if merged and merged[-1][0] == n and merged[-1][2] == mono:
            merged[-1][1] += " " + chunk
        else:
            merged.append([n, chunk, mono])
    out = []
    for i, (n, chunk, mono) in enumerate(merged, start=1):
        flag = " [自言自语]" if mono else ""
        if 1 <= n <= len(rows):
            name, _ident, _tone = _speaker_identity(rows[n - 1])
            sex = _speaker_sex_word(rows[n - 1])
            out.append(f'{name} (Speaker {n}' + (f', {sex} voice' if sex else '') + f') says aloud: {_unquote(chunk)}{flag}')
        else:
            out.append(f'Speaker {n} says aloud: {_unquote(chunk)}{flag}')
    return out


def _speaker_voice_line(scenes: list) -> str:
    """t111u: 每个真的说话的人一行 Speaker N = 名字: 性别(大写)、年龄、声音、画面位置;再加性别锁。"""
    import project_manager

    seen, bits = set(), []
    for sc in scenes or []:
        if not isinstance(sc, dict):
            continue
        rows = _scene_speakers(sc)
        for n in _speaker_slots([sc]):
            if not (1 <= n <= len(rows)):
                continue
            row = rows[n - 1]
            body, _m = project_manager.split_actor_motion(row.get("body") or "")
            key = (row.get("role"), body)
            if key in seen:
                continue
            seen.add(key)
            bits.append(speaker_tag(row, n, sc))
    if not bits:
        return ""
    return ("Speakers (``<N>`` / ``<Ns>`` / Speaker N = the Nth person in ``actor``; ``<Ns>`` is the same person as ``<N>``):\n  " + "\n  ".join(bits)
            + "\nEach person keeps this one voice, on or off screen. " + GENDER_LOCK_LINE
            + " " + SPEAKER_MARK_IDENTITY_RULE)



def _speech_scene_flags(scenes) -> dict:
    """Turn-count flags from the shared speaking parser (not punctuation/wrapped lines)."""
    texts = []
    for s in scenes or []:
        if not isinstance(s, dict):
            continue
        text = scene_speaking_source(s)
        if text.strip():
            texts.append(text)
    return {
        "texts": texts,
        "single": bool(texts) and all(speaking_is_single_inner_monologue(x) for x in texts),
        "all_mono": bool(texts) and all(speaking_is_all_inner_monologue(x) for x in texts),
        "any_mono": any(speaking_has_monologue(x) for x in texts),
        "any_dialogue": any(speaking_has_interactive_dialogue(x) for x in texts),
    }


def _video_speech_rules(story_style: str, narrative: str, cast: list, scenes: list,
                        host_narrator: str, use_speaking: bool) -> tuple:
    """返回 (说明行, 内容字段名)。故事风格决定谁说话；叙事风格只管画面怎么表现（见 _video_form_line）。"""
    import project_manager

    real = [s for s in scenes if isinstance(s, dict)]
    if real and all(project_manager.scene_is_story_act(s) for s in real):
        story_style = "story_act"  # 场景本身是 Story Act 生成的（只有 story_content）
    if story_style == "story_act":
        has_content = any(
            str(s.get("story_content") or s.get("speaking") or s.get("voiceover") or "").strip() for s in real
        )
        if not use_speaking or not has_content:
            return ["Speech: nobody speaks in this clip. No narration, no dialogue, no lip-sync."], ""
        flags = _speech_scene_flags(real)
        lines = [
            "Story style STORY ACT: ``story_content`` is what happens in this scene. The people act it out "
            "through action, behavior, facial expression, and gesture, so the picture itself tells it. "
            "They do not speak on camera: no mouth speaking motion and no lip-sync.",
        ]
        if flags["any_mono"]:
            lines.append(SPEAKER_MARK_IDENTITY_RULE)
            if flags["single"]:
                lines.append(SINGLE_INNER_MONOLOGUE_RULE)
                lines.append(
                    "Speech: the only speaking turn is this actor's own inner voice, heard as voice-over while they "
                    "act and think; the mouth stays closed for the entire scene. ``story_content`` itself is not said "
                    "aloud as on-screen dialogue."
                )
            else:
                lines.append(H3_MONOLOGUE_NO_LIPSYNC_RULE)
                lines.append(
                    "Speech: any self-talk / inner-monologue audio (<Ns> or legacy 自言自语) is that same actor's own "
                    "inner voice heard as voice-over while they act; no lip-sync on those lines. Interactive ``<N>`` "
                    "dialogue is still not spoken on camera (Story Act). ``story_content`` is never said aloud as "
                    "on-screen dialogue."
                )
        else:
            lines.append(
                "Speech: nobody speaks. No dialogue, no lip-sync, no narrator, no voice-over; "
                "``story_content`` is never said aloud."
            )
        return lines, "story_content"
    if not use_speaking or not any(
        str(s.get("speaking") or s.get("voiceover") or "").strip() for s in scenes if isinstance(s, dict)
    ):
        return ["Speech: nobody speaks in this clip. No narration, no dialogue, no lip-sync."], ""
    # 有 <N> 标记、场景里有人：逐句台词（谁说哪句写明），不再让模型自己猜
    dialogue = any(
        _SPEAKER_MARK.search(str(s.get("speaking") or "")) and _scene_speakers(s)
        for s in scenes if isinstance(s, dict)
    )
    speakers = cast or next((_scene_speakers(s) for s in scenes if isinstance(s, dict) and _scene_speakers(s)), [])
    hosts = [r for r in speakers if r.get("role") == "host"]
    people = [r for r in speakers if r.get("role") != "host"]
    lines: list = []
    if not cast and not dialogue:
        voice = narrator_voice_phrase(host_narrator) or "one narrator voice"
        flags0 = _speech_scene_flags(scenes)
        if story_style == "story_speak":
            if flags0["single"]:
                lines.append(SPEAKER_MARK_IDENTITY_RULE)
                lines.append(SINGLE_INNER_MONOLOGUE_RULE)
                lines.append(
                    "Speech: pure drama, no separate narrator. The single self-talk turn is that same person's own "
                    "inner voice-over while they act and think; mouth closed, no lip-sync, not mute."
                )
                return lines, "narration"
            lines.append(
                "Speech: pure drama, no narrator. ``narration`` is what the people in the picture say to each other; "
                "give it to the person it fits, one voice at a time, with lip-sync for that person only "
                "(self-talk / <Ns> lines use that same person's voice with no lip-sync)."
            )
            if flags0["any_mono"]:
                lines.append(SPEAKER_MARK_IDENTITY_RULE)
                lines.append(H3_MONOLOGUE_NO_LIPSYNC_RULE)
            return lines, "narration"
        lines.append(
            f"Speech: ``narration`` is one off-screen voice-over ({voice}). Do not show a narrator or host. "
            "Nobody in the picture speaks or moves their lips; they act silently."
        )
        return lines, "narration"
    flags = _speech_scene_flags(scenes)
    lines.append(SPEAKER_MARK_IDENTITY_RULE)
    if flags["single"]:
        lines.append(SINGLE_INNER_MONOLOGUE_RULE)
        if dialogue:
            lines.append(
                "Dialogue: ``dialogue`` is the script. This clip has exactly one speaking turn and it is self-talk / "
                "inner monologue by that labeled actor; hear it as that same person's own inner voice-over while they "
                "act and think; mouth closed, no lip-sync; never swap to another narrator."
            )
        else:
            lines.append(
                "Speakers: ``<N>`` / ``<Ns>`` in ``speaking`` is the Nth person in ``actor`` (identical person; "
                "s is speech mode, not a new character); ``<0.5>`` is a pause in seconds. This clip has exactly one "
                "speaking turn and it is self-talk: that person's own inner voice-over, mouth closed, no lip-sync."
            )
    elif dialogue:
        lines.append(
            "Dialogue: ``dialogue`` is the script. Speak its lines in this exact order, each only by its labeled "
            "speaker; never swap speakers. One voice at a time; the others listen or react. "
            "Interactive ``<N>`` lines are lip-synced to that person; self-talk ``<Ns>`` / 自言自语 lines use that "
            "same person's voice with no lip-sync (mouth closed)."
        )
        if flags["any_mono"]:
            lines.append(H3_MONOLOGUE_NO_LIPSYNC_RULE)
    else:
        lines.append(
            "Speakers: ``<N>`` / ``<Ns>`` in ``speaking`` is the Nth person in ``actor`` (only 1 to 3 speak; "
            "``<Ns>`` is the same person as ``<N>``); the same person keeps talking until the next mark; "
            "``<0.5>`` is a pause in seconds. One voice at a time. "
            "Lip-sync only the person whose interactive ``<N>`` line it is; everyone else listens or reacts; "
            "self-talk ``<Ns>`` lines have no lip-sync."
        )
        if flags["any_mono"]:
            lines.append(H3_MONOLOGUE_NO_LIPSYNC_RULE)
    if story_style == "podcast":
        lines.append(
            "Story style PODCAST: the people in ``actor`` are the podcast speakers"
            + (" (the 讲员 is the host" + (", the 人物 are guests)" if people else ")") if hosts
               else " (the first 人物 is the host, the others are guests)")
            + ". They talk ABOUT the story; they never act it out. A speaker visible in the picture talks on camera; "
            "a speaker not in the picture is heard as voice-over. People of the story shown in the picture act silently: "
            "no lines, no lip-sync."
        )
    elif story_style == "counselor":
        if hosts:
            lines.append(
                "Story style COUNSELOR: the 讲员 is the counselor, on camera, speaking as a third person "
                "(background, what is going on, the remedy). The 人物 are actors living the story, not guests: "
                "they speak their own lines to each other, act, and show emotion. The 讲员 may speak to them and they may "
                "answer, but they stay inside the life, never a studio discussion."
            )
        else:
            lines.append(
                "Story style COUNSELOR without an on-screen counselor: the 人物 are actors living the story; "
                "they speak their own lines to each other, act, and show emotion."
            )
    else:  # story_speak
        if hosts and not people:
            lines.append(
                "Story style STORY SPEAK, narrator beat: the 讲员 is the narrator, on camera, giving a brief introduction, "
                "transition, or closing. Do not act the story out here."
            )
        else:
            if flags["single"]:
                extra = (" The 讲员 stays apart and never takes over the scene." if hosts else
                         " No separate narrator; the heard voice is this same actor's own inner voice-over.")
                lines.append(
                    "Story style STORY SPEAK: a dramatized moment like a film or TV drama. The single self-talk turn "
                    "is the 人物's own inner thought: they act and think in the scene while that same voice is heard "
                    "as voice-over, with the mouth closed and no lip-sync."
                    + extra
                )
            else:
                extra = (" The 讲员 stays apart, speaks only the lines marked for them, and never takes over the scene."
                         if hosts else
                         (" No separate narrator; self-talk is that same actor's own inner voice-over."
                          if flags["any_mono"] else " No narrator, no voice-over."))
                lines.append(
                    "Story style STORY SPEAK: a dramatized moment like a film or TV drama. ``speaking`` is the 人物's dialogue: "
                    "they say these lines aloud to each other, in the scene, as the people of the story. Their actions, faces, "
                    "and the picture help express what is being said."
                    + extra
                )
    if narrative in TELLING_NARRATIVES and story_style != "podcast" and people:
        lines.append("Even in this telling style, the 人物's lines are their own spoken lines, not narration.")
    # 声音：只写用到的位置
    if dialogue:
        lines = [ln.replace("``speaking``", "``dialogue``") for ln in lines]
        voice_line = _speaker_voice_line(scenes)
        if voice_line:
            lines.append(voice_line)
        return lines, "dialogue"
    slots = _speaker_slots(scenes)
    voice_bits = []
    for n in slots:
        if 1 <= n <= min(3, len(cast)):
            row = cast[n - 1]
            import project_manager

            body, _m = project_manager.split_actor_motion(row.get("body") or "")
            name = chosen_actor_voice(body, row.get("role") or "person")
            voice_bits.append(f"<{n}> {_who(row)}" + (f" = voice {name}" if name else ""))
    if voice_bits:
        lines.append("Voices: " + "; ".join(voice_bits) + ". Use exactly these voices.")
    if flags["single"]:
        lines.append(GENDER_LOCK_LINE + " The inner voice-over uses this same identity and voice.")
    else:
        lines.append(GENDER_LOCK_LINE + " Lip-sync uses the same voice.")
    return lines, "speaking"


def _video_form_line(narrative: str) -> str:
    """叙事风格：只说画面怎么表现，不涉及谁说话（谁说话由故事风格决定）。"""
    return {
        "story": "Form: the people act the moment out; faces, gestures, and what passes between them carry it.",
        "narration": "Form: telling. The place, objects, symbols, and composition carry the content; people, if any, support it.",
        "tech": "Form: a clean technical slide (architecture / flow / comparison diagram) in reading order; people rarely appear.",
        "exec": "Form: one sparse executive slide: one conclusion, backed by one key number, trend, or simple chart.",
    }.get(narrative, "")


def _video_direction_lines(scenes: list, use_visual: bool) -> list:
    """t181u: Grok / Gemini 视频：场景里的人名 + visual → 方向句（见 in_scene_direction_lines）。"""
    names, vis = [], []
    for s in scenes or []:
        for r in _scene_speakers(s):
            nm = _speaker_identity(r)[0]
            if nm and nm not in names:
                names.append(nm)
        if use_visual:
            vis.append(str(s.get("visual") or ""))
    return (cast_lock_lines(names) + pose_move_lines(" ".join(vis), names)
            + in_scene_direction_lines(" ".join(vis), names))  # t182u


def _video_text_line(text: str, background: str, narrative: str) -> str:
    """说明文字（画面上的字），只写一次。t163u: 短、正面，少用 caption / text 这类词。"""
    if text == "erase":
        return ("Picture: lettering printed beside or under the start image is not part of the scene; "
                "continue the scene itself through that area.")
    if text == "express":
        return "Picture: the scene alone tells it; the frame holds no lettering."
    if text != "keep":
        return "Text: " + video_caption_rule(text).replace("\n", " ")
    if background == "art_text":
        return ("Text: one short artistic keyword (Chinese at most 8 characters, English at most 3 words) may sit in the deep "
                "background, taken from the spoken content. Never a sentence. " + KEYWORD_PLACE_SHORT_EN)
    if background == "bubble" and narrative == "story":
        return ("Text: at most one small thought bubble near a speaker, holding a keyword from their line; "
                "never a subtitle bar, never over a face.")
    return "Picture: keep lettering that is physically part of the scene (e.g. a sign) as it is; add nothing new."


def _video_style_line(frames: str, evolve: str, style: str) -> str:
    if frames == "two":
        return ("Pictures: picture 1 is the opening frame, picture 2 the ending frame. Move from 1 to 2 so the start, "
                "the change, and the end are all seen; their own looks set the style, invent no third look.")
    head = "Pictures: picture 1 is the scene, the first frame; keep the same place. "
    if evolve == "to_style":
        return head + (f"Hold picture 1's own look, then change it slowly and visibly into {style} "
                       "(start, halfway, finished); no page turn, dissolve, wipe, or flash. Same people and place throughout.")
    if evolve == "to_style_page":
        return head + (f"Over about 4-5 seconds, turn pages, each one closer to {style}; the last page is {style}. "
                       "Same people and place on every page.")
    if evolve == "to_style_dissolve":
        return head + (f"Over about 4-5 seconds, several soft dissolves, each closer to {style}, ending in {style}. "
                       "Same people and place in every blend.")
    return head + "Keep picture 1's own look for the whole clip; do not restyle it. The motion stays gentle and natural."


def _video_camera_short(camera: str) -> str:
    line = _video_flow_camera_line(camera).lstrip("* ").strip()
    if camera in (None, "", "none"):
        return "Camera: no prescribed move unless ``visual`` describes one."
    return line


# t159u: 视频（Grok / Gemini / MiniMax 共用）的两条硬规则，放在提示词最前面（不只在 FYI 里）。
VIDEO_NO_CAPTION_RULE = (
    "Clean film image: only the scene fills the frame. Spoken lines are heard only as voices; "
    "the picture shows only the scene.\n"
    "画面干净：画面里只有场景本身，台词只用声音表现。"
)
VIDEO_CONTINUITY_MARK = "CONTINUITY (real time)"
VIDEO_CONTINUITY_RULE = (
    "This is one continuous real-time moment of a few seconds: the room, the view outside, the light and "
    "everyone's clothes stay the same from the first frame to the last.\n"
    "连续性：同一时刻的几秒钟，光线、时间、环境始终和起始画面一致。"
)
VIDEO_LIGHT_CHANGE_WORDS = (
    "天亮", "日出", "日落", "黄昏", "傍晚", "天黑", "入夜", "夜幕降临", "光线变化", "光线变", "灯亮", "灯灭", "关灯", "开灯",
    "熄灯", "亮灯", "时间流逝", "时光流逝", "从白天到", "从夜晚到", "白天变", "夜晚变", "转为白天", "转为夜晚",
    "sunrise", "sunset", "dawn", "dusk", "lights turn on", "lights turn off", "light turns on", "light turns off",
    "lights go out", "lights come on", "time passes", "time-lapse", "timelapse", "day to night", "night to day",
    "day turns", "night turns", "lighting change", "light changes",
)


def lighting_change_requested(text: str) -> bool:
    """t159u: 视觉里明确写了光线 / 时间变化（简单关键词）就返回 True。"""
    low = str(text or "").lower()
    return any(w in low for w in VIDEO_LIGHT_CHANGE_WORDS)


def _scene_has_dialogue(sc: dict) -> bool:
    for key in ("speaking", "voiceover", "dialogue", "story_content"):
        if _strip_speech_marks(str(sc.get(key) or "")).strip():
            return True
    return False


def _guard_parts(scenes, transition=None, start_image: str = "") -> tuple:
    scs = [s for s in (scenes or []) if isinstance(s, dict)]
    talk = any(_scene_has_dialogue(s) for s in scs)
    if isinstance(transition, dict) and str(transition.get("对白") or "").strip():
        talk = True
    visual = " ".join(str(s.get("visual") or "") for s in scs)
    if isinstance(transition, dict):
        visual += " " + str(transition.get("时空") or "") + " " + str(transition.get("特效") or "")
    changes = lighting_change_requested(visual)
    light = "" if changes else minimax_lighting_phrase(visual, start_image)
    return talk, changes, light


VIDEO_AUDIO_MODE_LINES = {
    "talk": "Voice: the people speak along with the given voice recording, lips moving in sync with the voice.",
    "sing": "Song: the singer sings along with the given song, lips, breath and body moving in sync with the music.",
}


def video_guard_block(scenes, transition=None, start_image: str = "", audio_mode: str = "") -> str:
    """t159u/t163u: 视频提示词最前面的要点（所有后端共用），只用正面、具体的描述：
    画面干净（台词只用声音）；光线 / 时间写成具体样子（视觉或起始图亮度）；有对话时加实时连续性（视觉写了光线变化就不加）。"""
    talk, changes, light = _guard_parts(scenes, transition, start_image)
    rules = [VIDEO_NO_CAPTION_RULE]
    if light:
        rules.append(light)
    if talk and not changes:
        rules.append(VIDEO_CONTINUITY_RULE)
    if audio_mode in VIDEO_AUDIO_MODE_LINES:
        rules.append(VIDEO_AUDIO_MODE_LINES[audio_mode])
    return "KEY POINTS (whole clip):\n" + "\n".join(f"- {r}" for r in rules)


def video_closing_block(scenes, transition=None, start_image: str = "") -> str:
    """t163u: 结尾再强调一次：画面干净 + 光线。"""
    _talk, _changes, light = _guard_parts(scenes, transition, start_image)
    return "REMEMBER:\n- Clean film image: only the scene fills the frame." + (f"\n- {light}" if light else "")


def strip_caption_lines(text: str) -> str:
    """t163u: FYI 里讲字幕 / 文字的句子去掉（负面词会反过来引导），其余照旧。"""
    keep = [ln for ln in str(text or "").splitlines()
            if not re.search(r"caption|subtitle|\btext\b|字幕|文字", ln, re.I)]
    return "\n".join(keep).strip()


# ---------------------------------------------------------------------------
# t162u: MiniMax H3 专用提示词。H3 只有正面提示词（BasicGuider，没有负面 / CFG），所以：
#   - 不写「不要字幕 / 不要日夜变化」这种词（会被当成要画的东西），只描述画面「是什么」；
#   - 台词不用引号 / 字段格式（容易被画成字），有配音时只说谁对谁说话，声音交给音轨；
#   - 光线写成具体的样子（夜里：窗外一直是黑的夜色、室内灯光），从视觉文字或起始图亮度判断。
# ---------------------------------------------------------------------------
_NIGHT_WORDS = ("夜", "晚上", "晚间", "深夜", "半夜", "夜里", "夜晚", "night", "midnight", "late evening")
_DAY_WORDS = ("白天", "早上", "早晨", "上午", "中午", "下午", "阳光", "陽光", "日光", "daytime", "morning", "noon",
              "afternoon", "sunlight", "sunny")
_QUOTE_CHARS = "\"'“”‘’「」『』《》"


def _image_brightness(path: str) -> float:
    """起始图平均亮度 0–255；读不到返回 -1。"""
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as im:
            g = im.convert("L")
            g.thumbnail((96, 96))
            return float(ImageStat.Stat(g).mean[0])
    except Exception:  # noqa: BLE001
        return -1.0


def minimax_lighting_phrase(visual: str, start_image: str = "") -> str:
    """t162u: 正面描述「光线一直是这样」。视觉里写了时间就按它，否则看起始图亮度。"""
    low = str(visual or "").lower()
    night = any(w in low for w in _NIGHT_WORDS)
    day = any(w in low for w in _DAY_WORDS)
    if not (night or day) and start_image:
        b = _image_brightness(start_image)
        night = 0 <= b < 85
        day = b > 150
    if night and not day:
        return ("It is night for the entire clip: the windows show the same dark night outside from the first frame "
                "to the last, and the room is lit only by its warm indoor lamps, exactly as in the first frame.")
    if day and not night:
        return "It is daytime for the entire clip, with the same steady daylight as in the first frame."
    return "The light and the time of day stay exactly as in the first frame for the entire clip."


def _dialogue_turns(scene: dict) -> list:
    """[(说话人序号, 名字, 身份, 台词, 是否自言自语)]，台词去掉引号与 ``[自言自语]`` 标记。"""
    rows = _scene_speakers(scene)
    out = []
    for line in dialogue_script(scene):
        m = re.match(r'^.*?\(?Speaker (\d+)[^)]*?\)? says aloud: (.*)$', line, re.S)
        if not m:
            continue
        n = int(m.group(1))
        name, ident = (_speaker_identity(rows[n - 1])[:2] if 1 <= n <= len(rows) else (f"person {n}", ""))
        raw = m.group(2)
        mono = bool(re.search(r"\[自言自语\]\s*$", raw))
        if mono:
            raw = re.sub(r"\s*\[自言自语\]\s*$", "", raw)
        text = "".join(ch for ch in raw if ch not in _QUOTE_CHARS).strip()
        out.append((n, name, ident, text, mono))
    return out


def build_minimax_video_prompt(scenes, *, style: str = "", language: str = "", region: str = "", era: str = "",
                               with_audio: bool = False, start_image: str = "", fyi: str = "",
                               transition=None, two_frames: bool = False) -> str:
    """t162u: MiniMax H3 的短提示词，只用正面描述。"""
    scs = [s for s in (scenes or []) if isinstance(s, dict)]
    sc = scs[0] if scs else {}
    lang = ""
    try:
        import config

        lang = config.audio_language_label(language) if (language or "").strip() else ""
    except Exception:  # noqa: BLE001
        lang = ""
    st = str(style or "").strip()
    st_en = "realistic" if ("写实" in st or "realistic" in st.lower() or not st) else st
    place = " ".join(x for x in (era or "", region or "") if x).strip()
    lines = [f"A {st_en} cinematic film shot" + (f", set in {place}" if place else "") + "."]
    lines.append("The video starts from the first frame and ends on the last frame." if two_frames else
                 "The video continues directly from the first frame: same place, same camera angle, same people.")
    visual = " ".join(str(s.get("visual") or "").strip() for s in scs).strip()
    if isinstance(transition, dict):
        visual = " ".join(x for x in (visual, str(transition.get("时空") or ""), str(transition.get("特效") or "")) if x.strip())
    if visual:
        lines.append(f"What happens: {visual}")
    rows = _scene_speakers(sc)
    if rows:
        who = []
        for r in rows:
            name, ident, _tone = _speaker_identity(r)
            who.append(f"{name}, a {ident}" if ident else name)
        lines.append("People in the shot: " + "; ".join(who) + ". Only these people, nobody else.")
    turns = _dialogue_turns(sc)
    talk = bool(turns) or any(_scene_has_dialogue(s) for s in scs)
    has_mono = any(len(tr) > 4 and tr[4] for tr in turns) or any(
        speaking_has_monologue(str(s.get("speaking") or "")) for s in scs)
    flags = _speech_scene_flags(scs)
    single_inner = flags["single"]
    if talk:
        lines.append(SPEAKER_MARK_IDENTITY_RULE)
        if with_audio:
            names = " and ".join(dict.fromkeys(t[1] for t in turns)) or "the people"
            if single_inner:
                lines.append(
                    f"{names} think in their own voice" + (f" in {lang}" if lang else "")
                    + ", heard as inner monologue / voice-over with the mouth closed and no lip sync, "
                    "acting and thinking naturally; this is not mute and not another narrator."
                )
                lines.append(SINGLE_INNER_MONOLOGUE_RULE)
            else:
                lines.append(f"{names} talk to each other" + (f" in {lang}" if lang else "")
                             + ", their lips moving in sync with the voice track on interactive lines, one speaker "
                             "at a time while the other listens and reacts with natural expressions and small gestures.")
            if has_mono:
                lines.append(H3_MONOLOGUE_NO_LIPSYNC_RULE)
        else:
            said = []
            for i, tr in enumerate(turns):
                _n, name, ident, text = tr[0], tr[1], tr[2], tr[3]
                mono = bool(tr[4]) if len(tr) > 4 else False
                lead = "" if i == 0 else "Then "
                if mono:
                    g = str(ident or "").lower()
                    pron = "herself" if ("woman" in g or "female" in g or "girl" in g) else "himself"
                    said.append(
                        f"{lead}{name}" + (f" (the {ident})" if ident else "")
                        + f" speaks to {pron} as self-talk / inner monologue (mouth closed, NO lip sync): {text}"
                    )
                else:
                    said.append(f"{lead}{name}" + (f" (the {ident})" if ident else "") + f" says aloud: {text}")
            if single_inner:
                lines.append(
                    "This is a single inner-monologue turn, heard as that same actor's own voice-over"
                    + (f" in {lang}" if lang else "")
                    + ", with the mouth closed and no lip sync. " + " ".join(said)
                )
                lines.append(SINGLE_INNER_MONOLOGUE_RULE)
            else:
                lines.append(
                    "They talk, heard as spoken voices" + (f" in {lang}" if lang else "")
                    + ", one speaker at a time. Interactive lines have lips in sync; "
                    "self-talk (自言自语) lines have NO lip sync (mouth closed). " + " ".join(said)
                )
            if has_mono:
                lines.append(H3_MONOLOGUE_NO_LIPSYNC_RULE)
    if talk and not lighting_change_requested(visual):
        lines.append("This is one continuous real-time moment of a few seconds.")
        lines.append(minimax_lighting_phrase(visual, start_image))
        lines.append("The room, the view outside and everyone's clothes stay the same from the first frame to the last.")
    elif not lighting_change_requested(visual):
        lines.append(minimax_lighting_phrase(visual, start_image))
    lines.append("Clean film image: only the scene itself fills the frame.")
    lines.append("Sound: the voices and the natural sound of the place, no music.")
    extra = []
    for ln in str(fyi or "").splitlines():  # FYI 里讲字幕 / 文字的句子不带（负面词会反过来引导）
        s = ln.strip()
        if not s or s.startswith("注意") or re.search(r"caption|subtitle|text|字幕|文字|标题|標題", s, re.I):
            continue
        extra.append(s)
    if extra:
        lines.append("Note: " + " ".join(extra))
    # t244/t246: 全局禁字幕行必须是物理第一行
    raw = "\n".join(lines)
    raw = ensure_speaker_semantics_rules(
        raw, has_speaking=talk, has_monologue=has_mono, single_inner=bool(talk) and single_inner,
    )
    return ensure_video_no_subtitle_first_line(raw)


def _plain_payload(payload: list) -> str:
    """t163u: 场景内容写成纯文字（字段名保留，台词每行一句，没有引号 / JSON）。"""
    blocks = []
    many = len([p for p in payload or [] if isinstance(p, dict)]) > 1
    for i, sc in enumerate([p for p in payload or [] if isinstance(p, dict)], 1):
        lines = [f"Scene {i}:"] if many else []
        for key, val in sc.items():
            if isinstance(val, list):
                lines.append(f"{key}:")
                lines += [f"  {_unquote(v) if key != 'dialogue' else v}" for v in val]
            else:
                lines.append(f"{key}: {val}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# t165u: MiniMax H3 官方提示词格式（MiniMaxAI/MiniMax-H3 docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md）
#   第一行固定的图对齐说明（I2VA / FL2VA）+ 空行 + 三个字段：integrated_multimodal_description（[Shot 1] …，
#   说话人 (S1)(S2) + 声音描述，台词在 <d>[语言] 原文</d> 里）、overall_soundscape、non_diegetic_music。不写禁止清单。
#   只在提交给 MiniMax 时用；Grok / Gemini 仍用统一提示词。
# ---------------------------------------------------------------------------
H3_I2V_LINE = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
H3_FL2V_LINE = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second "
                "mark of the target video; Picture 2 (from Shot 1) aligns with the {end:.2f}-second mark of the target video.")
_H3_CAMERA = {
    "none": "The camera holds steady with only slight natural movement.",
    "wide": "A wide shot frames the whole space while the camera holds steady.",
    "close": "A close-up frames the faces while the camera holds steady.",
    "push": "The camera pushes in with small amplitude at slow speed.",
    "pull": "The camera pulls back with small amplitude at slow speed.",
    "arc": "The camera arcs slowly around the subjects with small amplitude.",
    "track": "The camera tracks the subjects smoothly at slow speed.",
    "rotate": "The camera rotates slowly with small amplitude.",
    "timelapse": "The shot runs as a time-lapse, time passing quickly.",
}


def _h3_style(style: str) -> str:
    st = str(style or "").strip()
    if not st or "写实" in st or "寫實" in st or "realistic" in st.lower():
        return "Live-action, cinematic, realistic"
    return f"Cinematic, in the style of {st}"


def _h3_speaker_phrase(row: dict) -> str:
    """'the middle-aged woman 蘇敏 with a mature female voice' (声音名有就加上)。"""
    import project_manager

    name, ident, tone = _speaker_identity(row)
    body, _m = project_manager.split_actor_motion(row.get("body") or "")
    voice = chosen_actor_voice(body, row.get("role") or "person")
    who = f"the {ident} {name}".strip() if ident else name
    tone0 = tone.split(",")[0].strip()
    return who + (f" with {tone0}" if tone0 else "") + (f" (voice {voice})" if voice else "")


H3_LIP_SYNC_LINE = (
    "Lip sync: every mouth movement matches the spoken words exactly, syllable by syllable; "
    "only the person who is speaking at that moment moves their lips, everyone else keeps their lips closed and only "
    "listens; when the speaker changes, the moving mouth switches to the new speaker at once; lip sync starts at 0.0 s on "
    "the very first syllable: the first speaker's mouth is already open and forming that syllable in the very first frame, "
    "with no silent closed-mouth lead-in, no pause and no delay before the lips move; "
    "every line is spoken exactly once, in the given order: no line or part of a line is repeated, restarted or "
    "said again, and nobody starts a line over."
)  # t219u: H3 会把第一句说两次  # t158u: 声音一开始嘴就动  # t150u: 对口型要求（Strata 打磨也要原样保留）

H3_INNER_VO_NO_LIPSYNC_LINE = (
    "Lip sync: this scene is inner monologue / self-talk by the marked actor "
    "(<N> and <Ns> are the identical person N, and s is speech mode not another character); "
    "that same actor's inner voice is heard as voice-over while they act and think; "
    "every mouth stays closed for the entire scene — no lip sync, no mouth speaking motion, "
    "and the first frame is not an open speaking mouth at 0.0 s; "
    "the voice is audible thinking / off-screen internal narration, not mute, and not a different narrator."
)

H3_MIXED_LIP_SYNC_LINE = (
    "Lip sync: interactive dialogue lines (markers <N> without s) have every mouth movement match the spoken words "
    "exactly, syllable by syllable; only the person who is speaking that interactive line moves their lips, "
    "everyone else keeps their lips closed; when the speaker changes to another interactive line, the moving mouth "
    "switches to the new speaker at once; self-talk / inner-monologue lines (<Ns> or legacy 自言自语) have NO lip sync "
    "— that same actor keeps the mouth closed while their own inner voice is heard; "
    "do not start lip sync at 0.0 s if the first turn is self-talk; "
    "every line is spoken exactly once, in the given order: no line or part of a line is repeated, restarted or "
    "said again, and nobody starts a line over."
)


def _h3_turn_flags(turns) -> dict:
    mono = [bool(tr[4]) if len(tr) > 4 else False for tr in (turns or [])]
    return {
        "any_mono": any(mono),
        "all_mono": bool(mono) and all(mono),
        "single": len(mono) == 1 and bool(mono[0]),
        "mixed": any(mono) and any(not x for x in mono),
        "first_mono": bool(mono and mono[0]),
    }


def h3_lip_sync_line(turns=None, *, single_inner: bool | None = None) -> str:
    """Pick the Lip sync sentence from parser turns so Strata cannot keep a conflicting default."""
    if single_inner:
        return H3_INNER_VO_NO_LIPSYNC_LINE
    flags = _h3_turn_flags(turns)
    if flags["single"] or (flags["all_mono"] and not flags["mixed"]):
        return H3_INNER_VO_NO_LIPSYNC_LINE
    if flags["mixed"] or flags["any_mono"]:
        return H3_MIXED_LIP_SYNC_LINE
    return H3_LIP_SYNC_LINE


_REMAP_WARNED: set = set()


def h3_speaker_map(scene: dict) -> tuple:
    """t150u: (rows, turns, remap)。台词里的 <N> 严格对应 actor 栏第 N 个人；<N> 超出人数时
    （例如只有一个人却写 <2>）按出现的编号顺序依次对到 actor 里的人，并打印提示。"""
    rows = _scene_speakers(scene) if isinstance(scene, dict) else []
    raw = _dialogue_turns(scene) if isinstance(scene, dict) else []
    labels = sorted({n for n, *_r in raw})
    remap = {n: n for n in labels}
    if any(not (1 <= n <= len(rows)) for n in labels) and rows and len(labels) <= len(rows):
        remap = {n: i for i, n in enumerate(labels, 1)}
        _key = (str(scene.get("id")), tuple(labels), len(rows))
        if _key not in _REMAP_WARNED:  # 同一场只提示一次
            _REMAP_WARNED.add(_key)
            print("⚠️ 讲话里的编号 " + "、".join(f"<{n}>" for n in labels) + f" 超出 actor 里的 {len(rows)} 个人，按顺序对到："
                  + "、".join(f"<{n}>→{_speaker_identity(rows[remap[n] - 1])[0]}" for n in labels))
    turns = []
    for item in raw:
        n, name, ident, text = item[0], item[1], item[2], item[3]
        mono = bool(item[4]) if len(item) > 4 else False
        m = remap.get(n, n)
        if 1 <= m <= len(rows):
            name, ident = _speaker_identity(rows[m - 1])[:2]
        turns.append((m, name, ident, text, mono))
    return rows, turns, remap


def h3_speaker_timeline(scene: dict) -> list:
    """t150u: [(开始秒, 结束秒, 说话人序号)]，一句台词一条（同 h3_speaker_map 的序号）。
    只有 speaking_timing 跟现在的 speaking 一致、条数跟台词一样时才有，否则 []。"""
    if not isinstance(scene, dict):
        return []
    tm = scene.get("speaking_timing")
    if not isinstance(tm, dict):
        return []
    if " ".join(str(tm.get("text") or "").split()) != " ".join(str(scene.get("speaking") or "").split()):
        return []
    _rows, turns, remap = h3_speaker_map(scene)
    secs = [x for x in (tm.get("sections") or []) if isinstance(x, dict)]
    if not secs or len(secs) != len(turns):
        return []
    out = []
    for x, t in zip(secs, turns):
        try:
            a, b, n = float(x.get("start") or 0), float(x.get("end") or 0), int(x.get("speaker") or 0)
        except (TypeError, ValueError):
            return []
        if remap.get(n, n) != t[0] or b <= a:
            return []
        out.append((round(a, 2), round(b, 2), t[0]))
    return out


_NOTE_DROP = re.compile(r"[()\[\]<>{}\"“”「」『』]")


def clean_speaker_note(text: str, limit: int = 360) -> str:
    """括号里的人物描述：去掉括号 / 尖括号，句号换成逗号（不能断开对话那段），压成一行。"""
    t = _NOTE_DROP.sub("", str(text or ""))
    t = re.sub(r"[.!?。！？;；]+\s*", ", ", t)
    t = " ".join(t.split()).strip(" ,，、")
    return t[:limit].rstrip(" ,，、")


def h3_visual_person_note(visual: str, name: str, names: list) -> str:
    """t150u: 只有文字时：画面描述里讲这个人的小句（主语沿用上一句），用作括号描述。"""
    if not visual or not name:
        return ""
    names = [n for n in names if n]
    subject, picked = "", []
    for sent in re.split(r"[。！？!?\n]+", visual):
        subject = ""  # 每一句重新找主语
        for clause in re.split(r"[，,；;：:]+", sent):
            c = clause.strip()
            if not c:
                continue
            for nm in names:
                i = c.find(nm)
                if i == 0 or (i > 0 and c[i - 1] == "的"):
                    subject = nm
                    break
            if subject == name:
                picked.append(c)
    return clean_speaker_note("，".join(picked), 120)


def actor_scene_note(row: dict) -> str:
    """t158u: actor 里名字后面的（括号描述）= Strata 看这一场的图写的样子；进出方式（走进画面…）不算。"""
    import project_manager

    _b, note = project_manager.split_actor_motion((row or {}).get("body") or "")
    if not note or "画面" in note or "畫面" in note:
        return ""
    return note


def merge_speaker_note(look: str, visual_note: str) -> str:
    """t151u: 括号描述 = Strata 看图写的样子 + 场景描述里讲这个人的小句（衣服、表情、姿势）。
    t223u: when a look/actor note exists, visual positioning is ignored entirely (all left/right/seat
    clauses stripped from the visual note) — never used, rewritten, or merged for positioning."""
    a, b = clean_speaker_note(look or "", 220), clean_speaker_note(visual_note or "", 140)
    if a and b:
        b = drop_all_side_clauses(b)  # t223u: actor/look is sole position source
    if a and b and b not in a:
        return f"{a}, in this scene: {b}"
    return a or b


_SIDE_RE = re.compile(
    "(?P<L>"
    "\u5de6\u5074|\u5de6\u4fa7|\u5de6\u908a|\u5de6\u8fb9|\u5de6\u9762|\u9760\u5de6|\u5750\u5728\u5de6|"
    r"\bleft\b)"
    "|(?P<R>"
    "\u53f3\u5074|\u53f3\u4fa7|\u53f3\u908a|\u53f3\u8fb9|\u53f3\u9762|\u9760\u53f3|\u5750\u5728\u53f3|"
    r"\bright\b)",
    re.I)


def speaker_side_token(text: str):
    """t222u: 从描述里读出左/\u53f3（L/R）；两边都有或没有则 None。"""
    L = R = False
    for m in _SIDE_RE.finditer(str(text or "")):
        if m.group("L"):
            L = True
        if m.group("R"):
            R = True
    if L and not R:
        return "L"
    if R and not L:
        return "R"
    return None


def drop_conflicting_side_clauses(text: str, keep_side) -> str:
    """t222u: 掉掉与 keep_side 相反的左/右小句（通常来自冲突的视觉）。"""
    if not keep_side or not text:
        return text or ""
    bad = "R" if keep_side == "L" else "L"
    parts = [p.strip() for p in re.split(r"[,;，；]\s*", text) if p.strip()]
    keep = []
    for p in parts:
        side = speaker_side_token(p)
        if side == bad:
            continue
        keep.append(p)
    return ", ".join(keep)


def drop_all_side_clauses(text: str) -> str:
    """t223u: drop every left/right/seat clause — used when actor is sole position source."""
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"[,;，；]\s*", text) if p.strip()]
    return ", ".join(p for p in parts if speaker_side_token(p) is None)


def strip_named_position_from_visual(visual: str, names) -> str:
    """t223u: for the H3 prompt copy only — remove clauses that assign a named speaker a left/right/seat.
    Does not rewrite or swap seats; ignores visual positioning entirely when actor notes exist."""
    if not visual:
        return ""
    names = [str(n).strip() for n in (names or []) if str(n).strip()]
    if not names:
        return visual
    _sep = re.compile("([，、,;；。！？!?\n]+)")
    bits = _sep.split(visual)
    out = []
    for bit in bits:
        if _sep.fullmatch(bit or ""):
            out.append(bit)
            continue
        has_name = any(nm and nm in bit for nm in names)
        if has_name and speaker_side_token(bit) is not None:
            continue  # drop the whole clause that seats a named speaker
        out.append(bit)
    # tidy doubled punctuation from removals
    text = "".join(out)
    text = re.sub(r"([，、,;；])\1+", r"\1", text)
    text = re.sub(r"^[，、,;；\s]+", "", text)
    text = re.sub(r"[，、,;；\s]+$", "", text)
    return text.strip()


def prefer_actor_speaker_look(actor_note: str, strata_note: str) -> str:
    """t222u/t223u: actor parenthesis clothing/seat is truth; Strata may enrich expression/pose only.
    When actor has a seat/side, ALL left/right clauses from Strata are dropped (not merged)."""
    a = clean_speaker_note(actor_note or "", 220)
    b = clean_speaker_note(strata_note or "", 220)
    if not a:
        return b
    if not b:
        return a
    if speaker_side_token(a) is not None:
        b = drop_all_side_clauses(b)  # t223u: ignore Strata positioning entirely
    else:
        b = drop_conflicting_side_clauses(b, speaker_side_token(a))
    if not b or b in a:
        return a
    return f"{a}; seen in Picture 1: {b}"


def actor_visual_side_conflicts(rows: list, visual: str) -> list:
    """t222u: [(name, actor_side, visual_side)]，actor 括号与视觉对同一人左右不一致。"""
    names = [_speaker_identity(r)[0] for r in (rows or [])]
    out = []
    for r, nm in zip(rows or [], names):
        if not nm:
            continue
        a_side = speaker_side_token(actor_scene_note(r))
        v_side = speaker_side_token(h3_visual_person_note(visual or "", nm, names))
        if a_side and v_side and a_side != v_side:
            out.append((nm, a_side, v_side))
    return out


def align_visual_names_to_actor(visual: str, rows: list) -> tuple:
    """t222u: when visual L/R seats are fully swapped vs actor brackets, rewrite each
    name's seat words (side + furniture) to match actor; keep original names and actions.
    Returns (visual, conflicts, fixed: bool)."""
    conflicts = actor_visual_side_conflicts(rows, visual)
    if not visual or len(conflicts) != 2:
        return visual or "", conflicts, False
    (n1, a1, v1), (n2, a2, v2) = conflicts
    if not (a1 != a2 and v1 != v2 and a1 == v2 and a2 == v1 and n1 and n2 and n1 != n2):
        return visual, conflicts, False

    def _flip_seat_words(text: str) -> str:
        # side words + common seat furniture that travels with a full two-person swap
        pairs = [
            ("\u5de6\u5074", "\u53f3\u5074"), ("\u5de6\u4fa7", "\u53f3\u4fa7"),
            ("\u5de6\u908a", "\u53f3\u908a"), ("\u5de6\u8fb9", "\u53f3\u8fb9"),
            ("\u6728\u6905", "\u5c0f\u51f3"), ("\u9577\u6905", "\u5c0f\u51f3"),
            ("\u957f\u6905", "\u5c0f\u51f3"),
        ]
        out = text
        for i, (L, R) in enumerate(pairs):
            out = out.replace(L, f"\x00L{i}\x00").replace(R, f"\x00R{i}\x00")
        for i, (L, R) in enumerate(pairs):
            out = out.replace(f"\x00L{i}\x00", R).replace(f"\x00R{i}\x00", L)
        return out

    _sep = re.compile("([\uFF0C\u3001,;\uFF1B\u3002\uFF01\uFF1F!?\n]+)")
    bits = _sep.split(visual)
    for nm, a_side, v_side in conflicts:
        for i, bit in enumerate(bits):
            if i % 2 == 1:
                continue
            if nm in bit and speaker_side_token(bit) == v_side:
                bits[i] = _flip_seat_words(bit)
    fixed = "".join(bits)
    return fixed, conflicts, fixed != visual



_MOUTH_COVER = re.compile(
    r"chin|over (?:her|his|their|the) (?:mouth|face)|cover(?:s|ing)? (?:her|his|their|the) (?:mouth|face)|"
    r"hand (?:to|at|near|on) (?:her|his|their|the) (?:mouth|lips|face)|look(?:s|ing)? down|gaz(?:e|es|ing) down|"
    r"eyes down|downcast|head (?:down|bowed|lowered|hung)|bow(?:s|ed|ing)? (?:her|his|their) head|"
    r"face (?:hidden|turned away|in (?:her|his|their) hands)|back to the camera|turned away|"
    r"託著下巴|托着下巴|託腮|托腮|手托|手託|低頭|低头|垂頭|垂头|捂|掩著嘴|掩着嘴|掩嘴|掩面|背對鏡頭|背对镜头", re.I)
_VISUAL_COVER = re.compile(r"託著下巴|托着下巴|託腮|托腮|手托著?着?下巴|手託著?下巴|捂著嘴|捂着嘴|掩著嘴|掩着嘴|掩嘴|掩面|"
                           r"低著頭|低着头|低頭|低头|垂著頭|垂着头|垂頭|垂头")
_VISUAL_SILENCE = re.compile(r"[與与和及、]?(?:寂靜|寂静|靜默|静默|沉默|無聲|无声|鴉雀無聲|鸦雀无声)")


_NOT_IN_VIEW = re.compile(
    r"not (?:yet )?(?:visible|in view|in (?:the )?(?:frame|picture|shot))|will (?:appear|enter|come)|appears? later|"
    r"enters? (?:later|the (?:frame|scene))|walks? in|off-?screen|out of (?:the )?(?:frame|view)|"
    r"尚未|還沒|还没|不在畫面|不在画面|稍後|稍后|走近|走進|走进", re.I)


def strip_mouth_cover(note: str) -> str:
    """t156u: 说话人的括号描述：去掉挡嘴 / 托下巴 / 低头 / 背对镜头的小句（说话时嘴要看得见）。
    t158u: 也去掉「还没出现 / 稍后走进来」——说话的人从第一帧就在画面里开口。"""
    parts = [p.strip() for p in re.split(r"[,;，；]\s*", str(note or "")) if p.strip()]
    keep = [p for p in parts if not _MOUTH_COVER.search(p) and not _NOT_IN_VIEW.search(p)]
    return ", ".join(keep)


def h3_talk_visual(visual: str) -> str:
    """t156u: 有台词时的画面描述：去掉托下巴 / 低头 / 捂嘴（挡住嘴）和「寂静 / 沉默」这类跟说话冲突的词。"""
    v = re.sub(r"(?:另一隻手|另一只手|另一手|一隻手|一只手|一手|雙手|双手|手)?(?:" + _VISUAL_COVER.pattern + ")",
               "", str(visual or ""))  # t158u: 「另一手捂著嘴」整段去掉，不留「另一手，」
    v = _VISUAL_SILENCE.sub("", v)
    return re.sub(r"[，,]\s*[，,]", "，", v)


def h3_on_camera_line(names: list, *, inner_vo: bool = False, mixed_mono: bool = False,
                      first_is_mono: bool = False) -> str:
    """On-camera sentence (one period at the end) so Strata can lock it verbatim.

    Interactive dialogue still speaks on camera with visible lips. A single inner-monologue
    turn is the same actor thinking: mouth closed, voice heard as voice-over.
    """
    names = [n for n in names if n]
    if not names:
        return ""
    who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    many = len(names) > 1
    if inner_vo:
        return (f"On camera: {who} " + ("are" if many else "is") + " on camera inside the frame, acting and thinking "
                "naturally with " + ("their mouths" if many else "the mouth") + " closed for the entire scene "
                "(inner monologue / thinking heard as that same person's own voice-over, not a different narrator, "
                "not mute, and not on-screen text); " + ("they do" if many else "the character does")
                + " not move the lips or form syllables, including at 0.0 s; while thinking, "
                + ("each person" if many else "the person") + " may act and stays where they are in <Picture 1>.")
    if mixed_mono:
        open0 = ("does not need an open speaking mouth at 0.0 s if the first turn is self-talk"
                 if first_is_mono else
                 (names[0] + " is already inside the frame at 0.0 s with the face and mouth visible "
                  "when an interactive line starts"))
        return (f"On camera: {who} stay in the frame; interactive spoken lines are delivered on camera with "
                "visibly moving lips, while self-talk / inner-monologue lines by that same person are heard as "
                "that person's own voice-over with the mouth closed (not a different narrator); "
                "while delivering an interactive line, the speaker stays where they are in <Picture 1> and keeps "
                "the mouth clearly visible and uncovered; " + open0 + "; the actions in the description happen "
                "while they talk or think.")
    return (f"On camera: {who} " + ("speak" if many else "speaks") + " on camera inside the frame, visibly moving "
            + ("their" if many else "the") + " lips with every word (spoken dialogue, not a voice-over or inner monologue); "
            "while speaking, " + ("each speaker" if many else "the speaker") + " stays where they are in <Picture 1>, "
            "faces the camera or the person they talk to, and keeps the mouth clearly visible and uncovered, with no hand, "
            "phone, cup or hair in front of it; " + names[0] + " is already inside the frame at 0.0 s with the face and mouth "
            "visible (no walking in, no turning around first), and any hand, cup or phone near a speaker's mouth in "
            "<Picture 1> drops away in the first instant; the actions in the description happen while they keep talking.")


def h3_speech_pace_line(speed: float, seconds: float) -> str:
    """t151u: 不加音频时让模型说快一点（导入时按同一档放慢还原）。没有句号，Strata 原样保留。"""
    x = 1.0 / max(0.5, float(speed or 1.0))
    if x < 1.08:  # t219u: 几乎原速时不说 fast，免得提前说完又重复补时间
        return (f"Speech pace: everyone speaks at a natural, steady conversational speed (about {x:.2f} times normal) "
                f"with short pauses, so that all the lines fit into the {round(float(seconds or 0)):d} seconds; "
                "each line is said only once and the lip movements stay exactly in sync with the speech.")
    return (f"Speech pace: everyone speaks fast, about {x:.2f} times normal conversational speed, brisk and clear "
            f"with only very short pauses, so that all the lines fit into the {round(float(seconds or 0)):d} seconds; "
            "each line is said only once and the lip movements stay exactly in sync with this faster speech.")


def _h3_dialogue_sentences(rows, turns, *, lang: str, audio_mode: str, notes: dict, timeline: list) -> list:
    """t150u / t241u: 每句台词写清楚谁在说、谁闭嘴；自言自语句无口型。(S#) = actor 第 # 个人。"""
    verb = "sings" if audio_mode == "sing" else "says"
    seen, out = set(), []
    for i, tr in enumerate(turns):
        n, _name, _ident, text = tr[0], tr[1], tr[2], tr[3]
        mono = bool(tr[4]) if len(tr) > 4 else False
        sid = f"(S{n})"
        ok = 1 <= n <= len(rows)
        nm = _speaker_identity(rows[n - 1])[0] if ok else f"Speaker {n}"
        others = [f"{_speaker_identity(r)[0]} (S{k})" for k, r in enumerate(rows, 1) if k != n]
        gender = (_speaker_identity(rows[n - 1])[1] or "").lower() if ok else ""
        self_pronoun = "herself" if ("woman" in gender or "female" in gender or "girl" in gender) else "himself"
        if n not in seen and ok:
            who = _h3_speaker_phrase(rows[n - 1])
            note = clean_speaker_note((notes or {}).get(n, ""))
            if note:
                nm_at = who.find(nm)
                cut = nm_at + len(nm) if nm_at >= 0 else len(who)
                who = who[:cut] + f" ({note})" + who[cut:]
            if mono and audio_mode != "sing":
                who_s = (f"{who} {sid} speaks to {self_pronoun} as self-talk / inner monologue "
                         f"(not interacting with anyone; mouth closed, NO lip sync)")
            else:
                who_s = f"{who} {sid} {verb}"
        else:
            if audio_mode == "sing":
                who_s = f"{nm} {sid} sings on"
            elif mono:
                who_s = (f"{nm} {sid} continues self-talk to {self_pronoun} "
                         f"(inner monologue; mouth closed, NO lip sync)")
            else:
                who_s = f"{nm} {sid} " + ("answers" if i and turns[i - 1][0] != n else "continues")
        seen.add(n)
        when = ""
        if timeline and i < len(timeline) and audio_mode in ("talk", "none"):
            a, b, _k = timeline[i]
            when = f"from {a:.1f} s to {b:.1f} s"
        quiet = ""
        if others and audio_mode != "sing":
            quiet = "while " + " and ".join(others) + (" listens" if len(others) == 1 else " listen") + " with closed lips"
        prev_mono = bool(turns[i - 1][4]) if i and len(turns[i - 1]) > 4 else False
        if mono and audio_mode != "sing":
            lead = "".join(x + ", " for x in (when, quiet) if x)
            lead = (lead + "no lip sync on this self-talk line, ") if lead else "no lip sync on this self-talk line, "
        elif i and turns[i - 1][0] != n and audio_mode != "sing":
            if prev_mono:
                lead = f"then lip sync begins on {nm}" + (f" {when}" if when else "") + ", " + (
                    f"and {quiet}, " if quiet else "")
            else:
                lead = f"then the lip movement switches to {nm}" + (f" {when}" if when else "") + ", " + (
                    f"and {quiet}, " if quiet else "")
        else:
            lead = "".join(x + ", " for x in (when, quiet) if x)
        body = who_s
        tag = "Chinese" if "Chinese" in str(lang) else lang
        sent = f"{lead}{body}: <d>[{tag}] {text}</d>"
        out.append(sent[0].upper() + sent[1:])
    return out


def h3_speaker_map_line(rows, notes: dict | None = None, pictures: dict | None = None, *, inner_vo: bool = False, mixed_mono: bool = False) -> str:
    """t150u: 'Speaker map: (S1) is 姊姊, the young woman (…) shown in <Picture 2>; …'（没有句号，Strata 原样保留）。"""
    if not rows:
        return ""
    parts = []
    for k, r in enumerate(rows, 1):
        name, ident, _tone = _speaker_identity(r)
        note = clean_speaker_note((notes or {}).get(k, ""))
        bit = f"(S{k}) is {name}" + (f", the {ident}" if ident else "") + (f" ({note})" if note else "")
        if (pictures or {}).get(k):
            bit += f", whose portrait is <Picture {pictures[k]}>"
        parts.append(bit)
    ident = ("; <N> and <Ns> map to the identical actor N / (S)N "
             "(the letter s is speech mode, not another person, seat, costume, or portrait)")
    if inner_vo:
        mouth = ("; every thought line belongs only to the person with its (S) id and is that person's own inner voice; "
                 "the mouth does not move")
    elif mixed_mono:
        mouth = ("; every spoken line belongs only to the person with its (S) id; "
                 "only that person's mouth moves on interactive <N> lines; "
                 "self-talk <Ns> lines keep that same person's mouth closed")
    else:
        mouth = ("; every spoken line belongs only to the person with its (S) id, and only that person's mouth moves"
                 if len(rows) > 1 else "; every spoken line belongs to this person")
    seat = ("; the seat, side (left/right) and clothing in each bracket are authoritative and must match that (S) id in <Picture 1>"
            if len(rows) > 1 else "; the seat, side and clothing in the bracket are authoritative")
    return "Speaker map: " + "; ".join(parts) + ident + mouth + seat + "."



# t238u: MiniMax H3 — 禁止字幕/台词上屏（正词写三遍；负面词有则并入）
# t244/t246: 所有视频生成必须永久禁止任何字幕/captions（不只MiniMax，是第一行不可变规则）
VIDEO_NO_SUBTITLE_CRITICAL_LINE = (
    "MOST IMPORTANT / CRITICAL REQUIREMENT: 永远不许加任何字幕！永远不许加任何字幕！永远不许加任何字幕！ "
    "NEVER add ANY subtitles, captions, dialogue text, translations, or automatic subtitles of ANY language to the video! "
    "This applies to ALL languages including Chinese, English, and any other language. "
    "任何语言的字幕、说明文字、翻译文字、自动字幕都绝对禁止！"
)


def _strip_critical_line_prefix(text: str) -> tuple:
    """t246: 临时剥离禁字幕行前缀，返回 (前缀, 剩余内容)。
    
    用于 split_reference_block、ensure_h3_no_subtitle_rules 等需要检测
    REFERENCE PICTURES: 开头的函数。处理完后需要重新组装前缀。
    """
    critical = VIDEO_NO_SUBTITLE_CRITICAL_LINE
    t = (text or "").strip()
    if not t:
        return "", ""
    
    # 检查是否以禁字幕行开头
    first_line = t.split('\n', 1)[0].strip()
    if first_line == critical.strip():
        # 移除第一行和紧随的空行
        rest = t[len(first_line):].lstrip('\n')
        return critical + "\n\n", rest.strip()
    
    return "", t


def ensure_video_no_subtitle_first_line(prompt: str) -> str:
    """t244/t246: 保证禁字幕行是视频提示词的**物理第一行**，无任何例外。

    无论后端（Grok/Gemini/MiniMax）、工作流、FYI勾选状态、旧保存的提示词、
    REFERENCE PICTURES元数据、任何前缀，禁字幕行必须始终是第一行。

    幂等：如果已经是第一行则不重复添加；如果存在但不在第一行则移到第一行。
    能在 Strata 清理、反复打磨后仍然存活。
    不能被 FYI 禁用、自定义 FYI 或旧保存的提示词绕过。
    REFERENCE PICTURES 等元数据保留在禁字幕行之后。
    """
    critical = VIDEO_NO_SUBTITLE_CRITICAL_LINE
    text = (prompt or "").strip()
    
    # 空输入
    if not text:
        return critical
    
    # 检查是否已经是第一行（幂等）
    first_line = text.split('\n', 1)[0].strip()
    if first_line == critical.strip():
        return text
    
    # 如果禁字幕行存在但不在第一行，移除它（稍后重新添加到第一行）
    if critical in text:
        # 移除现有的禁字幕行（可能在中间或末尾）
        lines = text.split('\n')
        new_lines = []
        skip_next_blank = False
        for i, line in enumerate(lines):
            if critical in line:
                # 跳过这行和紧随其后的空行
                skip_next_blank = True
                continue
            if skip_next_blank and not line.strip():
                skip_next_blank = False
                continue
            skip_next_blank = False
            new_lines.append(line)
        text = '\n'.join(new_lines).strip()
    
    # 始终将禁字幕行放在物理第一行，无例外
    return critical + "\n\n" + text if text else critical


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
    t246: 正确处理禁字幕行前缀，不在 REFERENCE PICTURES 前插入三遍规则。
    """
    rule = H3_NO_SUBTITLE_RULE
    text = prompt or ""
    if text.count(rule) >= 3:
        return text

    # 去掉已有残缺副本，避免凑不齐或堆在一处
    cleaned = text.replace(rule, "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # t246: 先剥离禁字幕行前缀（若有），处理完后重新组装
    critical_prefix, cleaned = _strip_critical_line_prefix(cleaned)

    # 拆 REFERENCE PICTURES 头（若有）
    head, body = "", cleaned
    if cleaned.startswith("REFERENCE PICTURES:") and "\n\n" in cleaned:
        head, body = cleaned.split("\n\n", 1)
        head = head + "\n\n"

    # 定位 integrated_multimodal_description / overall_soundscape
    marker = "integrated_multimodal_description:"
    sound = "\n\noverall_soundscape:"
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
        m = re.search(r"\[Shot 1\][^.\n]*\.", mid)
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
            body = "\n".join(lines)
        while body.count(rule) < 3:
            body = body.rstrip() + " " + rule

    out = head + body
    # 保底
    while out.count(rule) < 3:
        out = out.rstrip() + " " + rule
    # t246: 重新组装禁字幕行前缀
    return critical_prefix + out




def _inject_locked_rule(text: str, rule: str) -> str:
    """Insert a one-sentence locked rule if missing (raw prompts and post-polish)."""
    text = text or ""
    if not rule or rule in text:
        return text
    marker = "integrated_multimodal_description:"
    sound = "\n\noverall_soundscape:"
    if marker in text:
        pre, rest = text.split(marker, 1)
        if sound in rest:
            mid, post = rest.split(sound, 1)
            post = sound + post
        else:
            mid, post = rest, ""
        insert_at = None
        for key in ("Lip sync:", "On camera:", "Speaker marks:", "Self-talk (自言自语):",
                    "Entire-scene inner monologue:", "<d>"):
            i0 = mid.find(key)
            if i0 >= 0 and (insert_at is None or i0 < insert_at):
                insert_at = i0
        if insert_at is None:
            mid = mid.rstrip() + " " + rule + " "
        else:
            mid = mid[:insert_at].rstrip() + " " + rule + " " + mid[insert_at:].lstrip()
        return pre + marker + mid + post
    return text.rstrip() + "\n" + rule


def ensure_speaker_semantics_rules(prompt: str, *, has_speaking: bool = False,
                                   has_monologue: bool = False, single_inner: bool = False) -> str:
    """Keep identity / self-talk / single-inner rules intact after Strata polish.

    For an entire-scene inner monologue, also neutralize leftover boilerplate that
    would force lip sync, an open mouth at 0.0 s, or "never as a voice-over".
    Mixed scenes keep per-turn rules and are not rewritten into all-mouths-closed.
    """
    text = prompt or ""
    if not (has_speaking or has_monologue or single_inner):
        return text
    text = _inject_locked_rule(text, SPEAKER_MARK_IDENTITY_RULE)
    if has_monologue or single_inner:
        text = _inject_locked_rule(text, H3_MONOLOGUE_NO_LIPSYNC_RULE)
    if single_inner:
        text = _inject_locked_rule(text, SINGLE_INNER_MONOLOGUE_RULE)
        if H3_LIP_SYNC_LINE in text:
            text = text.replace(H3_LIP_SYNC_LINE, H3_INNER_VO_NO_LIPSYNC_LINE)
        swaps = (
            ("spoken dialogue, not a voice-over or inner monologue",
             "inner monologue heard as that same actor's voice-over, mouth closed, not another narrator"),
            ("visibly moving their lips with every word",
             "keeping the mouth closed with no lip sync while the inner voice is heard"),
            ("their lips moving in sync with the voice track",
             "their inner voice heard as voice-over with the mouth closed (no lip sync)"),
            ("No narrator, no voice-over.",
             "No separate narrator; self-talk is that same actor's own inner voice-over."),
            ("the first speaker's mouth is already open and forming that syllable in the very first frame",
             "the mouth stays closed in the very first frame, with no speaking lip motion"),
        )
        for src, dst in swaps:
            text = text.replace(src, dst)
    return text


def ensure_h3_monologue_no_lipsync_rules(prompt: str, *, has_monologue: bool) -> str:
    """t241u: 场景含自言自语时，保证无口型规则句仍在提示词里（Strata 打磨后复检）。"""
    if not has_monologue:
        return prompt or ""
    return ensure_speaker_semantics_rules(prompt, has_speaking=True, has_monologue=True)


def build_h3_prompt(scenes, *, frames: str = "one", transition=None, style: str = "", region: str = "", era: str = "",
                    language: str = "", camera: str = "none", audio_mode: str = "none", start_image: str = "",
                    seconds: float = 6.0, use_visual: bool = True, use_speaking: bool = True, fyi: str = "",
                    stage=None, speaker_notes: dict | None = None, portrait_pictures: dict | None = None,
                    speech_speed: float = 1.0) -> str:
    """t165u: 场景内容 → MiniMax H3 官方格式提示词。t191u: stage = 故事舞台（一句 Story stage:）。
    t150u: speaker_notes = {说话人序号: 括号描述}（Strata 看图写的；没有就用画面描述里讲这个人的小句）；
    portrait_pictures = {说话人序号: <Picture k> 的 k}（参考图工作流）。"""
    scs = [s for s in (scenes or []) if isinstance(s, dict)]
    sc = scs[0] if scs else {}
    two = frames == "two" or isinstance(transition, dict)
    lang = ""
    try:
        import config

        lang = config.audio_language_label(language) if (language or "").strip() else ""
    except Exception:  # noqa: BLE001
        lang = ""
    lang = lang or "Chinese"
    import project_manager

    first = H3_FL2V_LINE.format(end=float(seconds)) if two else H3_I2V_LINE
    era_s, reg_s = str(era or "").strip(), str(region or "").strip()
    place = era_s if (reg_s and reg_s in era_s) else ", ".join(x for x in (era_s, reg_s) if x)
    shot = [f"[Shot 1] {_h3_style(style)}" + (f", set in {place}" if place else "") + "."]
    try:
        from utility import story_stage as _ss

        if _ss.short_line(stage):
            shot.append(_ss.short_line(stage))
    except Exception:  # noqa: BLE001
        pass
    rows = _scene_speakers(sc)
    names = [(_speaker_identity(r)[1] + " " + _speaker_identity(r)[0]).strip() for r in rows]
    pic = "<Picture 1>"
    who_all = " and the ".join(names)
    if rows and isinstance(transition, dict):
        shot.append(f"The {who_all} shown in {pic} keep their appearance and clothing.")
    elif rows:
        shot.append(f"The {who_all} shown in {pic} " + ("stays" if len(rows) == 1 else "stay")
                    + " in the same place, preserving appearance, clothing, positions and the layout of the scene.")
    else:
        shot.append(f"The scene shown in {pic} stays the same place, preserving its layout, objects and colors.")
    if rows:
        shot += cast_lock_lines([_speaker_identity(r)[0] for r in rows], background_ok=True)  # t182u / t156u
    _turns0 = h3_speaker_map(sc)[1] if use_speaking else []
    _h3_flags = _h3_turn_flags(_turns0)
    if not _h3_flags["any_mono"] and speaking_has_monologue(scene_speaking_source(sc)):
        # Map may have dropped the flag; still honor shared parser marks.
        _h3_flags = {**_h3_flags, "any_mono": True, "single": speaking_is_single_inner_monologue(scene_speaking_source(sc))}
    _single_inner = bool(_h3_flags["single"] or speaking_is_single_inner_monologue(scene_speaking_source(sc)))
    _mixed_mono = bool(_h3_flags["mixed"] or (_h3_flags["any_mono"] and not _single_inner and _h3_flags.get("any_dialogue", not _h3_flags["all_mono"])))
    if _single_inner:
        _mixed_mono = False
    _spk_names = []  # t156u: 说话的人
    for _n, *_x in _turns0:
        if 1 <= _n <= len(rows):
            _nm = _speaker_identity(rows[_n - 1])[0]
            if _nm and _nm not in _spk_names:
                _spk_names.append(_nm)
    visual = " ".join(str(s.get("visual") or "").strip() for s in scs).strip() if use_visual else ""
    if _turns0 and visual and not _single_inner:
        visual = h3_talk_visual(visual).strip()  # t156u: keep thinking poses for entire-scene inner VO
    vis_all = " ".join(str(s.get("visual") or "") for s in scs)
    if _turns0 and not _single_inner:
        vis_all = h3_talk_visual(vis_all)  # t156u
    if isinstance(transition, dict):
        for key in ("时空", "人物", "特效"):
            v = str(transition.get(key) or "").strip()
            if v:
                visual = (visual + " " + v).strip()
                vis_all += " " + v
    if visual:
        # t223u: actor is sole position source — do not rewrite visual seats; strip named-speaker
        # left/right/seat clauses from the prompt copy only (stored scene visual is untouched).
        _has_actor_side = any(speaker_side_token(actor_scene_note(r)) for r in rows)
        if _has_actor_side:
            _vc = actor_visual_side_conflicts(rows, visual)
            if _vc:
                _msg = "; ".join(f"{nm}: actor={a} visual={v}" for nm, a, v in _vc)
                print(f"[H3 speaker side] t223 ignore visual positioning (actor truth): {_msg}")
            visual = strip_named_position_from_visual(visual, [_speaker_identity(r)[0] for r in rows])
            vis_all = strip_named_position_from_visual(vis_all, [_speaker_identity(r)[0] for r in rows])
        _happens = ("What happens while they think and act: " if _single_inner and _spk_names
                    else "What happens while they talk: " if _spk_names else "What happens: ")
        shot.append(_happens + f"{visual.rstrip('。.')}.")
        shot += pose_move_lines(visual, [_speaker_identity(r)[0] for r in rows], strict=True,
                                skip=_spk_names)  # t182u / t156u: 只写真的变化，说话的人不走动
        shot += in_scene_direction_lines(visual, [_speaker_identity(r)[0] for r in rows])  # t181u
    turns = h3_speaker_map(sc)[1] if use_speaking else []  # t150u: <N> 严格对到 actor 第 N 个人
    story = str(sc.get("story_content") or "").strip()
    if use_speaking and story and project_manager.scene_is_story_act(sc):
        shot.append(f"Action: {story}")
    talk = bool(turns)
    changes = lighting_change_requested(vis_all) or camera == "timelapse"
    if not changes:
        light = minimax_lighting_phrase(vis_all, start_image)
        if light.startswith("It is night"):  # H3: 室内外都适用的写法
            light = (f"It is night throughout: the same darkness outside and the same lights as in {pic}, "
                     "unchanged from the first frame to the last.")
        if talk:
            light = light.rstrip(".") + "; this is one continuous real-time moment, so the light, the time of day, " \
                    "the view outside and everyone's clothes stay exactly the same from the first frame to the last."
        shot.append(light)
    shot.append(_H3_CAMERA.get(camera or "none", _H3_CAMERA["none"]))
    # 台词：(S1)(S2) = actor 第 1/2 个人；每句写清谁说、谁闭嘴，换人时口型换人（t150u），声音描述只在第一次出现时写
    _names = [_speaker_identity(r)[0] for r in rows]
    # t223u: actor brackets = sole position source; visual positioning never merged into Speaker map
    _side_conflicts = actor_visual_side_conflicts(rows, vis_all)
    if _side_conflicts:
        _msg = "; ".join(f"{nm}: actor={a} visual={v}" for nm, a, v in _side_conflicts)
        print(f"[H3 speaker side] visual position ignored (actor truth): {_msg}")
    notes = {}
    for k, nm in enumerate(_names, 1):
        actor_n = actor_scene_note(rows[k - 1] if k <= len(rows) else {})
        strata_n = (speaker_notes or {}).get(k) or ""
        look = prefer_actor_speaker_look(actor_n, strata_n)  # t223u / t222u / t158u
        note = merge_speaker_note(look, h3_visual_person_note(vis_all, nm, _names))
        if nm in _spk_names and not _single_inner:
            note = strip_mouth_cover(note)  # t156u: 对白时不留挡嘴；内心独白保留思考姿势
        if note:
            notes[k] = note
    timeline = h3_speaker_timeline(sc) if (turns and audio_mode == "talk") else []
    _pace = float(speech_speed or 1.0)
    if turns and audio_mode == "none":  # t151u: 不加音频：配音的起止秒按说快后的语速换算，放得下才写
        _tl = h3_speaker_timeline(sc)
        if _tl and _tl[-1][1] * _pace <= float(seconds or 0) + AUTO_LENGTH_SLACK:
            timeline = [(round(a * _pace, 2), round(b * _pace, 2), n) for a, b, n in _tl]
    said = _h3_dialogue_sentences(rows, turns, lang=lang, audio_mode=audio_mode, notes=notes, timeline=timeline)
    if rows and (said or audio_mode == "talk"):
        shot.append(h3_speaker_map_line(rows, notes, portrait_pictures,
                                       inner_vo=_single_inner, mixed_mono=_mixed_mono))
    if said and audio_mode != "sing":
        shot.append(h3_lip_sync_line(turns, single_inner=_single_inner))
        _cam = h3_on_camera_line(_spk_names, inner_vo=_single_inner, mixed_mono=_mixed_mono,
                                 first_is_mono=_h3_flags["first_mono"])
        if _cam:
            shot.append(_cam)  # t156u / t283u
        if _single_inner:
            shot.append(SINGLE_INNER_MONOLOGUE_RULE)
        if any(len(tr) > 4 and tr[4] for tr in turns) or speaking_has_monologue(scene_speaking_source(sc)):
            shot.append(H3_MONOLOGUE_NO_LIPSYNC_RULE)  # t241u
        shot.append(SPEAKER_MARK_IDENTITY_RULE)
    if said and audio_mode == "none" and _pace < 0.999:
        shot.append(h3_speech_pace_line(_pace, seconds))
    if said:
        shot.append(H3_NO_SUBTITLE_RULE)  # t238u: 对话旁再强调一次（ensure 会凑满三遍）
        shot.append(" ".join(said))
        if audio_mode == "sing":
            shot.append("Lips, breath and body move with the song.")
        elif len(rows) > 1:
            shot.append("One person speaks at a time while the other listens and reacts with natural expressions and small gestures.")
        elif _single_inner:
            shot.append("The character acts and thinks naturally with the mouth closed; the inner voice is heard as voice-over.")
        else:  # t156u: 一个人的场景没有「另一个人在听」
            shot.append("The speaker talks naturally, with expressions and small gestures that match the words.")
    if said and audio_mode == "talk":
        if _single_inner:
            shot.append("Their inner voice follows the provided voice recording; the mouth stays closed (no lip sync).")
        else:
            shot.append("Their voices and lip movements follow the provided voice recording.")
    if said:
        pass
    elif audio_mode == "sing" and rows:
        shot.append(f"{_h3_speaker_phrase(rows[0])[0].upper() + _h3_speaker_phrase(rows[0])[1:]} (S1) sings along with the song, "
                    "lips, breath and body moving with the music.")
    elif audio_mode == "talk" and rows:
        shot.append(f"{_h3_speaker_phrase(rows[0])[0].upper() + _h3_speaker_phrase(rows[0])[1:]} (S1) speaks, lips moving with the voice.")
    elif not talk:
        shot.append("Nobody speaks; the people keep their lips closed and act through small natural movements."
                    if rows else "Only gentle natural movement in the scene.")
    if two:
        shot.append("The shot moves continuously from <Picture 1> and ends exactly on Picture 2.")
    extra = strip_caption_lines(fyi)
    extra = "\n".join(ln for ln in extra.splitlines() if ln.strip() and not ln.strip().startswith("注意"))
    if extra:
        shot.append("Direction: " + " ".join(extra.split()))
    if audio_mode == "sing":
        sound = "The singing voice from the song, with soft room ambience underneath."
        music = "N/A"
    else:
        sound = ("Quiet indoor ambience with soft room tone, small movement sounds and the rustle of clothing."
                 if talk or rows else "Natural ambient sound of the place.")
        music = "N/A"
    # t238u: 禁字幕句写三遍（头 / 对话旁 / 尾）；打磨后 ensure 会再核对
    # t244/t246: 全局禁字幕行必须是物理第一行（在构建时就注入，不只是发送时）
    raw = (first + "\n\nintegrated_multimodal_description: " + " ".join(shot)
           + "\n\noverall_soundscape: " + sound + "\n\nnon_diegetic_music: " + music)
    _has_mono = any(len(tr) > 4 and tr[4] for tr in turns) or speaking_has_monologue(scene_speaking_source(sc))
    result = ensure_h3_no_subtitle_rules(raw)
    result = ensure_speaker_semantics_rules(
        result, has_speaking=bool(said or _has_mono), has_monologue=_has_mono, single_inner=_single_inner,
    )
    return ensure_video_no_subtitle_first_line(result)  # t244: 第一行必须是全局禁字幕规则


def _video_prompt_assemble(*, head_label: str, style: str, choices: str, instruction: list,
                           language: str, payload: list, extra_sections: dict | None = None) -> str:
    lang_label = ""
    try:
        import config

        lang_label = (config.audio_language_label(language) or "") if (language or "").strip() else ""
    except Exception:  # noqa: BLE001
        lang_label = ""
    parts = {"Visual_Style": style, "Video_choices": choices}
    parts.update(extra_sections or {})
    parts["Instructions"] = "\n".join(f"- {line}" for line in instruction if line)
    if lang_label:
        parts["Audio"] = f"- Spoken language: {lang_label}. Every spoken word is delivered in {lang_label}."
    parts["Story_Scene_Content"] = _plain_payload(payload)  # t163u: 纯文字，不用 JSON 引号
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())


def _video_payload(scenes: list, *, variant: str, host_narrator: str, use_visual: bool,
                   use_speaking: bool, cast: list, content_key: str) -> list:
    raw = scene_payload_for_notebooklm_export(scenes, "video", variant, narrator=host_narrator, use_visual=use_visual)
    src = [s for s in (scenes or []) if isinstance(s, dict)]
    out: list = []
    for idx, sc in enumerate(raw):
        if not isinstance(sc, dict):
            continue
        orig = src[idx] if idx < len(src) else {}
        slim: dict = {}
        if use_visual and sc.get("visual"):
            slim["visual"] = sc["visual"]
        if cast and sc.get("actor"):
            slim["actor"] = sc["actor"]
        if use_speaking and content_key:
            speaking = (sc.get("speaking") or "").strip()
            voiceover = (sc.get("voiceover") or "").strip()
            if content_key == "story_content":
                # Story Act：story_content；旧数据只有 speaking 时，把 speaking（去掉 <N>）当作要演的内容
                act = str(orig.get("story_content") or sc.get("story_content") or "").strip()
                act = act or _strip_speech_marks(" ".join(p for p in (speaking, voiceover) if p))
                if act:
                    slim["story_content"] = act
                # Keep marked self-talk so the same actor's inner voice can be heard as VO.
                src_speak = scene_speaking_source(orig) or scene_speaking_source(sc) or speaking
                if src_speak and speaking_has_monologue(src_speak):
                    slim["speaking"] = src_speak
            elif content_key == "dialogue":
                script = dialogue_script(orig)
                if script:
                    slim["dialogue"] = script
            elif content_key == "narration":
                combined = _strip_speech_marks(" ".join(p for p in (speaking, voiceover) if p))
                if combined:
                    slim["narration"] = combined
            else:
                if voiceover and "<2>" not in speaking:
                    speaking = (speaking + " <2> " + voiceover).strip()
                if speaking:
                    slim["speaking"] = speaking
        out.append(slim)
    return out


def _cast_name(row: dict) -> str:
    import project_manager

    body, _m = project_manager.split_actor_motion(row.get("body") or "")
    bits = [b for b in body.split("/") if b.strip()]
    if row.get("role") == "host":
        return "讲员"
    return bits[3].strip() if len(bits) >= 4 else (row.get("label") or "人物")


def people_count_line(cast: list, where: str = "clip") -> str:
    """有名单时的人数规则（视频 where="clip" / 图片 where="picture"）。"""
    n = len(cast)
    names = ", ".join(_cast_name(r) for r in cast)
    who = "person is" if n == 1 else "people are"
    return (
        f"Cast lock: exactly {n} {who} in this {where}: {names}. Every visible person is one of them, matching their "
        f"gender, age band, look, and portrait, and exactly {n} " + ("person is" if n == 1 else "people are") + " visible" + (" from start to end" if where == "clip" else "") + "."
        f" Never add anyone else "
        "(no child, extra, passer-by, background figure, reflection, or silhouette) and never show anyone twice. "
        f"Any other figure already in {'picture 1' if where == 'clip' else 'the base picture'} stays a still, faceless part of the scenery and never becomes a character."
    )


def scene_cast_lock_line(scenes: list, use_actor: bool, where: str = "clip") -> str:
    """图片提示用：有名单 → 人数锁定；没名单 → 只能是图里已有的人。"""
    cast = _video_cast([s for s in (scenes or []) if isinstance(s, dict)], use_actor)
    return people_count_line(cast, where) if cast else PEOPLE_NO_CAST_LINE


PEOPLE_NO_CAST_LINE = (
    "Cast lock: only the people already in picture 1 appear. Never add anyone (no child, extra, passer-by, "
    "background figure, reflection, or silhouette) and never show anyone twice."
)


def _video_people_lines(cast: list, frames: str, host_narrator: str, override: str, narrative: str) -> list:
    if not cast:
        return [PEOPLE_NO_CAST_LINE]
    first_ref = 3 if frames == "two" else 2
    lines = [
        f"People: ``actor`` lists who is in the clip (gender/age band/ethnicity/name; the face and body look that age band). "
        f"Pictures from picture {first_ref} on, if pasted, are their portraits in ``actor`` order.",
        people_count_line(cast),
    ]
    if any(r.get("role") == "host" for r in cast) and (host_narrator or "").strip():
        lines.append(f"The 讲员 in ``actor`` is the project host: {host_narrator.strip()}.")
    if override and narrative not in ("tech", "exec"):
        lines.append(f"Draw every person as {override}; keep name, role, gender, and age, ignore other ethnicity or period hints.")
    return lines


def build_video_flow_prompt(
    *,
    frames: str,
    background: str,
    evolve: str,
    visual_style: str,
    scene_content: list,
    language: str = "",
    host_narrator: str = "",
    camera: str = "none",
    motion: str = "",
    narrative: str = "story",
    text: str = "erase",
    use_visual: bool = True,
    use_speaking: bool = True,
    use_actor: bool = False,
    actor_override: str = "",
    story_style: str | None = None,
) -> str:
    """生场视频提示词。每一点只写一次：画面 / 风格、表现形式（叙事风格）、谁说话（故事风格）、人物、文字、运镜、声音，
    然后是口语语言和场景内容。"""
    if frames not in {k for k, _ in VIDEO_FLOW_FRAME_CHOICES}:
        frames = "one"
    if background not in {k for k, _ in VIDEO_FLOW_BACKGROUND_CHOICES}:
        background = "none"
    if evolve not in {k for k, _ in VIDEO_FLOW_EVOLVE_CHOICES} or frames == "two":
        evolve = "keep"
    if (camera in (None, "", "none")) and (motion or "").strip() in _MOTION_TO_CAMERA:
        camera = _MOTION_TO_CAMERA[(motion or "").strip()]
    if camera not in {k for k, _ in VIDEO_FLOW_CAMERA_CHOICES}:
        camera = "none"
    if narrative not in SLIDE_FLOW_NARRATIVE_NOTES:
        narrative = "story"
    if text not in {k for k, _ in FLOW_CAPTION_CHOICES}:
        text = "erase"
    sstyle = normalize_story_style(story_style) or project_story_style()
    style = (visual_style or "").strip() or "realistic"
    scenes = [s for s in (scene_content if isinstance(scene_content, list) else []) if isinstance(s, dict)]
    use_visual, use_speaking, use_actor = bool(use_visual), bool(use_speaking), bool(use_actor)
    if not (use_visual or use_speaking or use_actor):
        raise ValueError("场景描述、讲话、人物至少要选一项。")
    cast = _video_cast(scenes, use_actor)
    speech, content_key = _video_speech_rules(sstyle, narrative, cast, scenes, host_narrator, use_speaking)
    instruction = [_video_style_line(frames, evolve, style)]
    if use_visual:
        instruction.append("``visual`` describes the place, the action, and the angle; act it out inside picture 1.")
    instruction.append(_video_form_line(narrative))
    instruction += speech
    instruction += _video_people_lines(cast, frames, host_narrator, (actor_override or "").strip(), narrative)
    instruction += _video_direction_lines(scenes, use_visual)  # t181u
    instruction.append(_video_text_line(text, background, narrative))
    instruction.append(_video_camera_short(camera))
    instruction.append("Sound: natural sound of the place only. No music of any kind (music is added to the whole film later).")
    instruction.append("Never show scene numbers, field names, or these instructions in the picture.")
    payload = _video_payload(scenes, variant="act_two" if frames == "two" else "act_one", host_narrator=host_narrator,
                             use_visual=use_visual, use_speaking=use_speaking, cast=cast, content_key=content_key)
    choices = story_style_label(sstyle) + " · " + video_flow_choice_label(
        frames, background, evolve, camera, "", narrative, text
    )
    spoken = content_key in ("speaking", "narration", "dialogue")  # Story Act / 无讲话：不写口语语言
    flags = _speech_scene_flags(scenes)
    if use_speaking and flags["any_mono"]:
        spoken = True  # inner voice-over still has spoken language
    raw = _video_prompt_assemble(head_label="", style=style, choices=choices, instruction=instruction,
                                 language=language if spoken else "", payload=payload)
    return ensure_speaker_semantics_rules(
        raw, has_speaking=bool(content_key or flags["any_mono"]),
        has_monologue=flags["any_mono"], single_inner=flags["single"],
    )


def _transition_video_choice_lines(transition: dict) -> str:
    order = ("插在", "时空", "人物", "对白", "特效")
    lines = []
    for key in order:
        value = transition.get(key)
        if value is None or str(value).strip() == "":
            continue
        lines.append(f"{key}：{value}")
    return "\n".join(lines)


def _transition_video_instruction(transition: dict, visual_style: str) -> str:
    """过渡场景的视频说明。形式跟着普通视频提示，内容按这场记下的选择来写。"""
    style = (visual_style or "").strip() or "realistic"
    space = str(transition.get("时空") or "").strip()
    people = str(transition.get("人物") or "").strip()
    speech = str(transition.get("对白") or "").strip()
    effect = str(transition.get("特效") or "").strip()
    chunks: list[str] = [
        """** This clip is a transition between two neighboring scenes. It is not a new story.
** Picture 1 is the opening frame: the last image of the earlier scene.
** Picture 2 is the ending frame: the first image of the later scene.
** The video must travel from picture 1 to picture 2. The audience sees the start, the change, and the end.
** Do not invent a third look that belongs to neither frame.
** Pictures after picture 2, if any are pasted, are actor references in ``actor`` order, skipping 不出现.
** A 人物 reference only shows who is already in these frames."""
    ]
    space_text = {
        "不变": "** Place and time stay as they are. Do not walk into a new place. Do not change day into night.",
        "换地方": "** The change is the place. Show how the people go from picture 1's place to picture 2's place. If one frame is outdoors and the other is indoors, show the door and the step inside. Do not also change the time of day.",
        "换时间": "** The change is the time. Day into night, or night into day, happens in the picture. It is quick. Do not also change the place. Do not explain how long it took with dialogue.",
        "一起变": "** Place and time both change. This is a large jump, a little fantastical, and the clip itself is short. Do not walk the whole road. Arrive.",
    }.get(space)
    if space_text:
        chunks.append(space_text)
    elif space:
        chunks.append(f"** Place and time follow this choice: {space}.")
    people_text = {
        "没有变化": "** The people stay the people already in both frames. Do not add a person. Do not send a person away.",
        "自然增减": "** Compare who is in picture 1 and picture 2. A person who is only in picture 2 comes in calmly: walks in, or is led in. A person who is only in picture 1 leaves calmly. No car, no crash, no shock.",
        "意外增减": "** Compare who is in picture 1 and picture 2. The change of people comes from a surprise, for example a car stopping and someone stepping out, or a sound that brings someone in. Do not invent a person who is in neither frame.",
    }.get(people)
    if people_text:
        chunks.append(people_text)
    elif people:
        chunks.append(f"** People follow this choice: {people}.")
    speech_text = {
        "不说话": """** Nobody speaks. speaking and voiceover stay unspoken. No greeting, no laugh, no sigh said aloud.
** A short piece of music may carry the clip. No lyrics. No mouth moves.
** The clip can also have no music, only the picture and the chosen transition effect.""",
        "简单寒暄": """** At most one or two greetings with no real topic, such as a hello. Do not start the conversation that belongs to the later scene.
** One voice: that line is speaking, voiceover is empty, and actor lists only that person first.
** Two voices: the first person is speaking, the second is voiceover, and actor lists them in that order.
** Mouths move only for those short lines. One voice at a time.""",
        "人声": """** A very short human sound marks someone arriving or leaving.
** Someone coming in: a laugh, a hello, or a small call. Someone leaving: a sigh, or a short goodbye. Match the place.
** Do not turn it into a real conversation.
** One voice: speaking only, voiceover empty, actor lists that person first.
** Two voices: speaking then voiceover, actor in that same order.
** If the people do not change, nobody makes this sound.""",
        "小动作": """** Nobody speaks. A small action joins the two frames, and its sound belongs to the action.
** In a restaurant: eating, pouring, cups touching. On a road: a few steps, a pause. Use the place that is actually in these frames.""",
        "场景烘托": """** Nobody speaks. The talk pauses.
** Show the mood of what the two scenes are about: gloom if it is heavy, light and flowers if it is kind, or wind, leaves, and the view they are looking at.
** Those sounds stay in the picture. Do not finish their conversation for them.""",
    }.get(speech)
    if speech_text:
        chunks.append(speech_text)
    elif speech:
        chunks.append(f"** Sound and speech follow this choice: {speech}.")
    effect_text = {
        "自然转换": "** No trick effect. The picture moves naturally from picture 1 to picture 2. No page turn, no dissolve, no wipe, no white flash, no whoosh.",
        "叠化": "** The join is a short dissolve. Picture 1 fades and picture 2 appears through it. They overlap for a moment. Write that dissolve into the motion.",
        "嗖一下": "** The join is very short. The picture is thrown across with one whoosh. Do not walk it slowly.",
        "翻书": "** The join is a page turn. Picture 1 turns like a page. Picture 2 is the new page. Paper may rustle.",
        "擦除": "** The join is a wipe. Picture 2 pushes picture 1 off from one side.",
        "闪白": "** The join is a white flash. The picture goes white, then lands on picture 2.",
    }.get(effect)
    if effect_text:
        chunks.append(effect_text)
    elif effect:
        chunks.append(f"** Use this transition effect between the two frames: {effect}.")
    chunks.append(
        f"** The project's visual style is {style}. Keep faces and clothes recognizable on the way from picture 1 to picture 2."
    )
    if speech != "不说话":
        chunks.append(NOTEBOOKLM_VIDEO_NO_MUSIC.strip())
    return "\n".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())


def build_transition_video_prompt(
    *,
    visual_style: str,
    scene_content: list,
    transition: dict,
    language: str = "",
    host_narrator: str = "",
    narrative: str = "story",
    text: str = "erase",
    use_visual: bool = True,
    use_speaking: bool = True,
    use_actor: bool = False,
    actor_override: str = "",
    story_style: str | None = None,
) -> str:
    """过渡场景的视频提示：过渡选择那几行 + 与普通视频同一套谁说话 / 文字 / 声音，每点只写一次。"""
    style = (visual_style or "").strip() or "realistic"
    chosen = transition if isinstance(transition, dict) else {}
    scenes = [s for s in (scene_content if isinstance(scene_content, list) else []) if isinstance(s, dict)]
    use_visual, use_speaking, use_actor = bool(use_visual), bool(use_speaking), bool(use_actor)
    if not (use_visual or use_speaking or use_actor):
        raise ValueError("场景描述、讲话、人物至少要选一项。")
    if narrative not in SLIDE_FLOW_NARRATIVE_NOTES:
        narrative = "story"
    if text not in {k for k, _ in FLOW_CAPTION_CHOICES}:
        text = "erase"
    sstyle = normalize_story_style(story_style) or project_story_style()
    cast = _video_cast(scenes, use_actor)
    silent = str(chosen.get("对白") or "").strip() in ("不说话", "小动作", "场景烘托")
    speech, content_key = _video_speech_rules(sstyle, narrative, cast, scenes, host_narrator, use_speaking and not silent)
    trans = [ln.lstrip("* ").strip() for ln in _transition_video_instruction(chosen, style).splitlines()]
    trans = [ln for ln in trans if ln and "No music in this clip" not in ln and "Music for the finished film" not in ln]
    instruction = trans + [_video_form_line(narrative)]
    if not silent:
        instruction += speech
    instruction += _video_people_lines(cast, "two", host_narrator, (actor_override or "").strip(), narrative)
    instruction += _video_direction_lines(scenes, use_visual)  # t181u
    instruction.append(_video_text_line(text, "none", narrative))
    if str(chosen.get("对白") or "").strip() != "不说话":
        instruction.append("Sound: natural sound of the place only. No music of any kind (music is added to the whole film later).")
    instruction.append("Never show scene numbers, field names, or these instructions in the picture.")
    payload = _video_payload(scenes, variant="act_two", host_narrator=host_narrator, use_visual=use_visual,
                             use_speaking=use_speaking and not silent, cast=cast, content_key=content_key)
    narrative_label = dict(SLIDE_FLOW_NARRATIVE_CHOICES).get(narrative, narrative).split("（")[0]
    caption_label = dict(FLOW_CAPTION_CHOICES).get(text, text)
    choices = f"{story_style_label(sstyle)} · {narrative_label} · {caption_label} · 过渡 · 起始画面到终止画面"
    return _video_prompt_assemble(
        head_label="", style=style, choices=choices, instruction=instruction,
        language=language if (content_key in ("speaking", "narration") and not silent) else "", payload=payload,
        extra_sections={"Transition_choices": _transition_video_choice_lines(chosen) or "（这场没有记下选择）"},
    )



VIDEO_NARRATION_SILENT_AUDIO = """
** This clip is SILENT of speech. No narrator. No voiceover. No dialogue. No lip-sync. No sung lyrics.
** Do not invent an off-screen voice. Ambient sound of the place only (wind, water, birds, room tone, footsteps).
** There is no speaker and no language to deliver.
"""


NOTEBOOKLM_VIDEO_NO_MUSIC = """
** No music in this clip. No score, no song, no melody, no background music, no musical sting, no mood track.
** Music for the finished film is added later, across the whole piece. A music bed inside one scene cannot be taken out.
** Sound effects that belong to this place are welcome: birds, wind, rain, water, footsteps, a door, a cup set down, cloth, leaves, a street, a room.
** If there is speech in this clip, keep those effects under the voices. If this clip is silent of speech, ambient sound alone is fine. Do not turn effects into a tune.
"""

# Direct Video：从单张场景图生成视频的指令选项（Story 编辑区「Direct Video」按钮）。
DIRECT_VIDEO_PROTAGONIST_REFLECTION = """
Generate video from the single input scene image.
** Protagonist (story character) performs reflection & brief interaction — lip-sync allowed.
** Speak ONLY the most key psychological point; do NOT read aloud any text printed in the image.
** Keep the starting frame stable; subtle body language and facial expression; no hard scene cuts.
"""

DIRECT_VIDEO_STATIC_NARRATION = """
Generate video from the single input scene image.
** No talking-avatar added if the image has none. Narrator voiceover only (off-screen).
** Image text stays static — never animate or read words-in-image aloud.
** Gentle camera drift or soft light shift; hold composition and visual style.
"""

DIRECT_VIDEO_ATMOSPHERIC_MOTION = """
Generate video from the single input scene image.
** No characters speaking unless the image already shows a talking-avatar.
** Cinematic ambient motion: slow push-in, soft parallax, subtle environmental movement.
** Do NOT add subtitles, captions, or read any text in the image.
"""

DIRECT_VIDEO_EMOTIONAL_MICRO = """
Generate video from the single input scene image.
** Focus on protagonist micro-expressions, breathing, and small gestures; minimal camera movement.
** If speaking reference is provided, protagonist lip-syncs ONE concise emotional line — not reading image text.
** Maintain character identity and lighting from the source image.
"""

DIRECT_VIDEO_KEN_BURNS_TEXT_HOLD = """
Generate video from the single input scene image.
** Treat on-image text as a fixed graphic — no OCR reading, no lip-sync to visible words.
** Slow Ken Burns style motion (pan/zoom) on the illustration; optional soft ambience, no dialogue.
** Preserve illustration style; no added UI, subtitles, or speech bubbles.
"""

DIRECT_STEP_IMAGE_CORE = """
Generate detailed-single-step-image from the single input scene image.
** According to the steps/section in the image, give me the step ###STEP### image (with title, no step show in the image)
"""



def build_direct_step_image(step: int = 1) -> str:
    """单图 → 第 ``step`` 步的细节图指令（DIRECT_STEP_n_IMAGE 与旧常量逐字相同）。"""
    try:
        k = int(step)
    except (TypeError, ValueError):
        k = 1
    return DIRECT_STEP_IMAGE_CORE.replace("###STEP###", str(max(1, k)))


DIRECT_STEP_1_IMAGE = build_direct_step_image(1)
DIRECT_STEP_2_IMAGE = build_direct_step_image(2)
DIRECT_STEP_3_IMAGE = build_direct_step_image(3)
DIRECT_STEP_4_IMAGE = build_direct_step_image(4)


DIRECT_VIDEO_PROMPT_CHOICES: list[tuple[str, str]] = [
    (
        "Image to Detail-Single-Step-Image 1",
        DIRECT_STEP_1_IMAGE,
    ),
    (
        "Image to Detail-Single-Step-Image 2",
        DIRECT_STEP_2_IMAGE,
    ),
    (
        "Image to Detail-Single-Step-Image 3",
        DIRECT_STEP_3_IMAGE,
    ),
    (
        "Image to Detail-Single-Step-Image 4",
        DIRECT_STEP_4_IMAGE,
    ),
    (
        "Image to Video (protagonist reflection & interaction",
        DIRECT_VIDEO_PROTAGONIST_REFLECTION,
    ),
    (
        "Image to Video (narrator voiceover only",
        DIRECT_VIDEO_STATIC_NARRATION,
    ),
    (
        "Image to Video (atmospheric motion only (no speech, cinematic drift)",
        DIRECT_VIDEO_ATMOSPHERIC_MOTION,
    ),
    (
        "Image to Video (emotional micro-expression + one concise line)",
        DIRECT_VIDEO_EMOTIONAL_MICRO,
    ),
    (
        "Image to Video (text in image stays static, no speech)",
        DIRECT_VIDEO_KEN_BURNS_TEXT_HOLD,
    )
]


def build_direct_video_clipbody(
    *,
    instruction: str,
    story_entries: list | None = None,
    main_character: str = "",
    visual_style: str = "",
) -> str:
    """组装 Direct Video 剪贴板正文（单图 → 视频 AI 指令）。"""
    parts: dict[str, object] = {}
    parts["Instruction_for_direct_video_generation"] = (instruction or "").strip()
    if (visual_style or "").strip():
        parts["Visual_Style"] = visual_style.strip()
    if (main_character or "").strip():
        parts["Story_Character"] = main_character.strip()
    voices = speaking_voice_lines(story_entries or [])
    if voices:
        parts["Speaking_voices"] = voices
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())


# t109u: 提取第 N 步时「说明文字」怎么处理这一步自己的字(其他步的字照样去掉)。
_STEP_CAPTION_LINES = {
    "keep": "** Text: keep step {k}'s short title as one caption line; no other text.",
    "erase": "** Text: remove step {k}'s text too (title, labels); no letters, and no blank board or panel left behind.",
    "keywords": "** Text: drop step {k}'s title and labels; blend " + KEYWORD_COUNT_EN + " from them "
        "into the scene itself. " + KEYWORD_PLACE_SHORT_EN,
    "express": "** Text: no letters at all; show what step {k}'s text says through the people, action and setting; "
               "no text box, panel or caption area.",
}


def build_step_image_clipbody(
    step: int = 1,
    *,
    visual_style: str = "",
    main_character: str = "",
    keep_style: bool = False,
    scene_caption: str = "",
    scene_visual: str = "",
    caption: str = "keep",
    extract_only: bool = False,
    fyi: str = "",
) -> str:
    """图片修改 · 提取第 N 步：输入是多步骤的信息图 / 封面，输出这一步的一张新场景图（图片编辑，不是视频）。"""
    try:
        k = max(1, int(step))
    except (TypeError, ValueError):
        k = 1
    if extract_only:
        # t114u: 图片修改·提取第 N 步:只从原图里原样取出这一格。不加 visual / speaking / actor / 背景。
        lines = []
        if (fyi or "").strip():
            lines.append(f"Note: {fyi.strip()}")
        lines += [
            f"Image edit: extract step {k} from the input image as its own picture.",
            "** The input image is an infographic or cover made of several numbered steps (panels).",
            f"** Take panel {k} as it is: the same people, setting, action, composition and details. Do not add, remove "
            "or change anything in it; only extend its edges naturally to fill the output frame stated above.",
            "** Drop the other panels, step numbers, arrows, grid and layout. Output one single scene image.",
            _STEP_CAPTION_LINES.get(caption, _STEP_CAPTION_LINES["keep"]).format(k=k),
        ]
        vs = (visual_style or "").strip()
        if keep_style or not vs:
            lines.append("** Style: keep the input's art style.")
        else:
            lines.append(f"** Visual_Style: {vs}. Redraw panel {k} in this style, content unchanged.")
        return "\n".join(lines)
    lines = [
        f"Image edit: extract step {k} as its own picture.",
        "** The input image is an infographic or cover made of several numbered steps (panels).",
        f"** Create a NEW single illustration of step {k} only: find panel {k} and redraw just that moment as one "
        "full-frame scene (its characters, setting, action and mood), recomposed to fill the output frame stated above. "
        "The input's layout and orientation do not carry over.",
        "** Do not return the input image. Drop the other panels, step numbers, arrows, grid and layout.",
        _STEP_CAPTION_LINES.get(caption, _STEP_CAPTION_LINES["keep"]).format(k=k),
        "** Keep every character's look (face, hair, clothing) as in the input.",
    ]
    vs = (visual_style or "").strip()
    if keep_style or not vs:
        lines.append("** Style: keep the input's art style.")
    else:
        lines.append(f"** Visual_Style: {vs}. Redraw the step in this style.")
    who = (main_character or "").strip()
    if who:
        lines.append(f"** Characters: {who}")
    ctx = [x for x in (
        f"caption: {scene_caption.strip()}" if (scene_caption or "").strip() else "",
        f"visual: {scene_visual.strip()}" if (scene_visual or "").strip() else "",
    ) if x]
    if ctx:
        lines.append(f"** What step {k} shows (from the script): " + "; ".join(ctx))
    return "\n".join(lines)


SLIDE_ANALYSIS_OUTPUT_FORMAT = """
Output: as json array like

[
    {
        "caption": "Scene title; for 1st scene, give the title for the whole-story",
        "actor": "人物1：woman/mature/chinese/封氏 | 人物2：man/youth/english/贾雨村 | 讲员：voice-name",
        "speaking": "Actor's speaking line, as the 1st person's perspective",
        "visual": "Visual elements of the image, give (animation) development of the scene to guid the viewer's attention",
        "voiceover": "Host/narrator's introduction / elaborate / summary, as the outsider's perspective"
    },
    {
        "caption": "Scene title",
        "actor": "人物1：woman/mature/chinese/封氏 | 人物2：man/youth/english/贾雨村 | 讲员：voice-name",
        "speaking": "Actor's speaking line, as the 1st person's perspective",
        "visual": "Visual elements of the image, give (animation) development of the scene to guid the viewer's attention",
        "voiceover": "Host/narrator's introduction / elaborate-insight / summary, as the outsider's perspective"
    },
    ...
]

"""

SLIDE_ANALYSIS_TECH_SOLUTION_ZH = """
这是一个关于技术方案（Technical Solution）的 PowerPoint。请认真阅读每一页的内容，并为每一页生成一段专业、自然、生动的中文解说词，最终形成一套完整的演讲稿。

请严格遵循以下要求：

整体要求
- 保持全篇连贯性，每一页不仅要讲解当前内容，还要自然衔接上一页和下一页，形成完整的故事线，而不是独立的页面说明。
- 以向客户或决策者进行方案汇报的口吻进行讲解，让听众能够跟随演讲节奏逐步理解整个 Solution。
- 解说词应具有较强的代入感，让听众感觉是在观看一场专业的方案演示，而不是在阅读 PPT。
- 每页控制在适合口头讲解的长度（约30–90秒），节奏自然。

每页讲解要求
- 根据页面内容进行讲解，不遗漏重点信息。
- 抓住页面核心信息，突出重点，避免逐条念 PPT。
- 语言精炼、逻辑清晰、表达自然，不啰嗦、不重复。

讲解逻辑
- 按照从上到下、从左到右的阅读顺序介绍内容。
- 当页面包含流程图、架构图、时序图或步骤图时，应按照图示的发展顺序进行讲解。
- 引导听众理解每一个元素之间的关系，而不是孤立介绍每个模块。
- 让听众能够随着讲解，"看着画面一步一步理解方案"。

衔接要求
- 每一页的结尾应尽量自然过渡到下一页：总结当前页面的核心价值；引出下一页要解决的问题；或说明下一阶段的内容。
- 整份 PPT 应像一场完整的 Solution Presentation，而不是若干独立页面的解说。

风格要求
- 专业、流畅、自信；富有感染力，但不过度营销；逻辑严谨、层次分明。
- 易于理解，让听众能够清晰记住整个 Solution 的架构、流程和价值。

最终目标：
- 让整套 PPT 的解说词能够直接作为正式方案汇报的演讲稿使用，使听众在演讲结束后，对整个技术方案形成清晰、完整且深刻的印象。
- STRICTLY: 每一页生成一个场景的JSON对象, 不要多也不少！！！

""" + SLIDE_ANALYSIS_OUTPUT_FORMAT

SLIDE_ANALYSIS_BUSINESS_PROPOSAL_ZH = """
这是一份面向客户或投资方的商业提案 PowerPoint。请逐页阅读，为每一页撰写一段中文口头讲解词，串联成完整提案演讲稿。

要求：
- 突出商业价值、痛点、方案差异与可落地性；避免空泛口号。
- 每页约 10 秒口播长度；逻辑递进，页与页之间自然过渡。
- 按页面视觉布局顺序讲解（上→下、左→右）；有流程/对比/架构图时按图的发展顺序讲。
- 语气专业、可信、有说服力，但不过度夸张。
- 不逐条念 bullet，要提炼核心观点并用口语化表达。
- 给出两个版本: 1. 'speaking' line, from the 1st person's perspective of the story/content;  2. 'voiceover' line, as the outsider/narrator's perspective of the story/content

最终输出可直接用于客户提案现场口播。
""" + SLIDE_ANALYSIS_OUTPUT_FORMAT

SLIDE_ANALYSIS_TRAINING_ZH = """
这是一套培训/教学类 PowerPoint。请为每一页生成清晰、易懂的中文讲解词，帮助学员循序渐进理解知识点。

要求：
- 教学口吻：先点明本页学习目标，再讲解要点，必要时用简短例子辅助理解。
- 每页约 20–60 秒；语言通俗，避免堆砌术语；关键概念可重复强调。
- 页间衔接：回顾上节要点 → 引入本节 → 预告下节内容。
- 按页面阅读顺序与图示逻辑讲解；流程/步骤图按步骤顺序展开。
- 不照读 PPT 原文，要转化为讲师口播语言。

最终输出适合录课或现场授课使用。
""" + SLIDE_ANALYSIS_OUTPUT_FORMAT

SLIDE_ANALYSIS_EXECUTIVE_BRIEF_ZH = """
这是一份面向高管的简报型 PowerPoint。请为每一页生成极简、高信息密度的中文讲解词。

要求：
- 每页控制在约 10 秒口播；只保留决策相关信息：结论、风险、收益、行动项。
- 开门见山，避免背景铺垫过长；用「结论先行」结构。
- 页间过渡简短有力，突出整体叙事主线。
- 按页面布局顺序讲解；图表按关键趋势/对比点提炼，不展开技术细节。
- 语气克制、专业、果断。
- 给出两个版本: 1. 'speaking' line, from the 1st person's perspective of the story/content;  2. 'voiceover' line, as the outsider/narrator's perspective of the story/content

最终输出适合董事会/管理层快速汇报。
""" + SLIDE_ANALYSIS_OUTPUT_FORMAT

SLIDE_ANALYSIS_TECH_SOLUTION_EN = """
This is a Technical Solution PowerPoint deck. Read every slide carefully and write a professional, natural, engaging English narration for each slide, forming one complete presentation script.

Requirements:
- Maintain narrative continuity across slides; each slide should connect to the previous and next, not stand alone.
- Speak as if presenting to a client or decision-maker walking through the solution live.
- About 10 seconds of spoken content per slide; concise, logical, not repetitive.
- Follow visual reading order (top-to-bottom, left-to-right); for diagrams/flows, follow the diagram progression.
- End each slide with a smooth transition to the next (summary, open question, or next-phase hook).
- Professional, confident tone; insightful but not overly salesy.
- each scene, give 2 version of speaking-content: 1. 'speaking' line, from the 1st person's perspective of the story/content;  2. 'voiceover' line, as the outsider/narrator's perspective of the story/content

Goal: a script ready for a formal solution presentation.

""" + SLIDE_ANALYSIS_OUTPUT_FORMAT

SLIDE_ANALYSIS_SCENE_JSON_ZH = """
这是一份 PowerPoint / PDF 幻灯片。请逐页分析，为每一页生成适合视频制作的场景解说词。

要求：
- 每页对应 array 中的一个元素；``scene_number`` 从 1 递增，与页码一致。
- ``speaking`` 字段为中文口播正文，约 10 秒；可用于后续 TTS 或分镜。
- 保持全篇故事线连贯；页间有过渡句。
- 抓住每页视觉与文字核心，不照读全部 bullet。
- 若某页主要为图表/架构，按图示逻辑讲解组件关系。
- 给出两个版本: 1. 'speaking' line, from the 1st person's perspective of the story/content;  2. 'voiceover' line, as the outsider/narrator's perspective of the story/content

""" + SLIDE_ANALYSIS_OUTPUT_FORMAT


SLIDE_ANALYSIS_PROMPT_CHOICES: list[tuple[str, str]] = [
    (
        "技术方案汇报（完整演讲稿 · 中文）",
        SLIDE_ANALYSIS_TECH_SOLUTION_ZH,
    ),
    (
        "商业提案汇报（客户提案 · 中文）",
        SLIDE_ANALYSIS_BUSINESS_PROPOSAL_ZH,
    ),
    (
        "培训课件讲解（教学口吻 · 中文）",
        SLIDE_ANALYSIS_TRAINING_ZH,
    ),
    (
        "高管简报（精简决策向 · 中文）",
        SLIDE_ANALYSIS_EXECUTIVE_BRIEF_ZH,
    ),
    (
        "Technical Solution（full script · EN）",
        SLIDE_ANALYSIS_TECH_SOLUTION_EN,
    ),
    (
        "幻灯片 → scene JSON（分镜口播 · 中文）",
        SLIDE_ANALYSIS_SCENE_JSON_ZH,
    ),
]


def build_slide_analysis_clipbody(
    *,
    instruction: str,
    slide_path: str = "",
    video_detail: dict | None = None,
) -> str:
    """组装 Slide/PDF 分析指令剪贴板正文。"""
    parts: dict[str, object] = {}
    parts["Instruction_for_slide_analysis"] = (instruction or "").strip()
    sp = (slide_path or "").strip()
    if sp:
        parts["Slide_PDF_reference"] = sp
    vd = video_detail if isinstance(video_detail, dict) else {}
    vid = vd.get("id")
    if vid:
        parts["Video_id"] = str(vid)
    category = (
        "topic_category: "
        + str(vd.get("topic_category") or "")
        + ",  topic_subtype: "
        + str(vd.get("topic_subtype") or "")
    )
    if category.strip().rstrip(":"):
        parts["Topic"] = category
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())


NOTEBOOKLM_VOICE_MATCH = """
** Voice rule, read first. The person who speaks uses the gender in their own name.
** woman = female voice. man = male voice. Lip-sync uses this same voice.
** On screen or off screen, a man is never given a female voice and a woman is never given a male voice.
** Age band is kids, youth, teenager, mature, or senior, the word after woman or man. Otherwise adult. Ethnicity is chinese or english, the word after the age band. A name, when present, is last and is not the voice.
** ``<N>`` in speaking is the Nth person in actor; each line after ``<N>`` is spoken by that person in their own voice.
** When a voice name is written for speaking or voiceover, that line uses that commercial voice. Do not substitute another.
"""


def _audio_language_instruction(language: str) -> str:
    import config

    label = config.audio_language_label(language)
    if not label:
        return ""
    return (
        f"** Audio / spoken language: {label}.\n"
        f"** All spoken words (character dialogue and the 讲员's narration) "
        f"MUST be delivered in {label}."
    )


def build_notebooklm_gen_instruction_clipbody(
    *,
    mode: str,
    video_detail: dict | None,
    scene_content: list,
    visual_style: str,
    main_character: str = "",
    host_narrator: str = "",
    variant: str = "",
    language: str = "",
) -> str:
    """组装 NotebookLM 导出指令剪贴板正文。

    ``mode`` + ``variant``：见 ``NOTEBOOKLM_EXPORT_VARIANTS``；也支持 ``image/slideshow`` 合成键。
    """
    base, var = normalize_nb_export_mode(mode, variant)

    vd = video_detail if isinstance(video_detail, dict) else {}

    parts: dict[str, object] = {}

    category = (
        "topic_category: "
        + str(vd.get("topic_category") or "")
        + ",  topic_subtype: "
        + str(vd.get("topic_subtype") or "")
    )

    if not visual_style:
        visual_style = "realistic"

    if not main_character:
        main_character = ""

    host_narrator = (host_narrator or "").strip()

    scenes = scene_content if isinstance(scene_content, list) else []
    json_content = json.dumps(
        scene_payload_for_notebooklm_export(scenes, base, var, narrator=host_narrator),
        ensure_ascii=False,
        indent=2,
    )

    parts["Visual_Style"] = visual_style
    parts["Export_variant"] = f"{base}/{var}"
    _var_labels = {v: lbl for v, lbl in NOTEBOOKLM_EXPORT_VARIANTS[base]}
    parts["Export_variant_label"] = _var_labels.get(var, var)

    if base == "image":
        _mandate = NOTEBOOKLM_SLIDESHOW_MANDATE.format(
            Visual_Style=visual_style, character=main_character
        )
        _mandate_key = (
            "READ_FIRST__SINGLE_IMAGE_MANDATE"
            if var == "single"
            else "READ_FIRST__SLIDESHOW_MANDATE"
        )
        parts[_mandate_key] = _mandate
        img_instr = (
            NOTEBOOKLM_IMAGE_SINGLE_INSTRUCTION
            if var == "single"
            else NOTEBOOKLM_IMAGE_SLIDESHOW_INSTRUCTION
        )
        parts["Instruction_for_image_generation"] = (
            img_instr.strip()
            + "\n"
            + NOTEBOOKLM_IMAGE_CHARACTER_EMPHASIS.strip()
            + "\n"
            + ACTOR_AGE_LOOK
        )
        if var != "single":
            if host_narrator:
                parts["Host_for_this_run"] = (
                    f"{host_narrator} ~ a host was chosen. "
                    f"The 讲员 entry in actor is this person, a storyteller outside the story."
                )
            else:
                parts["Host_for_this_run"] = (
                    "No host was chosen. Do not add a visible host unless a 讲员 is listed in actor."
                )

    elif base == "video":
        vid_instr = NOTEBOOKLM_VIDEO_ACT_TWO if var == "act_two" else NOTEBOOKLM_VIDEO_ACT_ONE
        voices = speaking_voice_lines(scenes)
        parts["Instruction_for_video_generation"] = "\n".join(
            part
            for part in (
                NOTEBOOKLM_VOICE_MATCH.strip(),
                voices,
                ACTOR_AGE_LOOK,
                vid_instr.strip(),
                NOTEBOOKLM_VIDEO_NO_MUSIC.strip(),
            )
            if part
        )
        lang_note = _audio_language_instruction(language)
        parts["Instruction_for_audio_generation"] = "\n".join(
            part
            for part in (
                NOTEBOOKLM_VOICE_MATCH.strip(),
                voices,
                vid_instr.strip(),
                NOTEBOOKLM_VIDEO_NO_MUSIC.strip(),
                lang_note,
            )
            if part
        )
        parts["Story_Scene_Content"] = json_content
    else:
        raise ValueError(f"Unknown NotebookLM export mode: {mode!r}")

    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())



SLIDESHOW_GENERATION_INSTRUCTION = """
Slide-Show generation instruction:
    *** Goal: Generate images for story scenes.
        ** 1 image = 1 scene
        ** Multiple scenes = slideshow

    ** Visual-Style
        ** Keep the visual style '{visual_style}' consistent throughout all the scenes of the story !!!!!!!!!!!.
		** Consider visual_style of each scene as more details.

	** Story Characters 
		* From NotebookLM source:  named like "Story-Character:xxx"; Follow gender to choose.
		* This character must stay consistent across all scenes !!!!!!!!!!!
        * show as talking-avatar, if current scene has 'actor', but no 'narrator'; show as actor (no talking), if current scene has both 'actor' & 'narrator')

	** Narrator Character
		* From NotebookLM source:  named like "Narrator:xxx"; Follow gender to choose.
        * show as talking-avatar, if current scene has 'narrator' field.

    ** if current scene has No 'narrator', No 'actor', then DO NOT show any of them in the scene-image !!!!! (if speaking content is talking about persons, show other person image)
    ** if current scene is 'narrator' speaking about the previous scene, normally should keep the previous scene image as background of current scene, and pop-up the 'narrator' as talking-avatar at front.
    ** DO NOT put any scene instruction / information (like content in json structure) in the image, only show the visual content of the scene!!!!!!!!!!!!!!
    ** DO NOT include any info of this prompt / instruction in the image, only express the content describing the scenes (the 'Story Json-Content' at end) !!!!!!!!!!!!!!



--------------

Video generation instruction: 
	*** if current scene image has 'narrator' talking-avatar;
        ** normally, the narrator is talking about the previous scene, current screen may keep the previous scene's image as background (which actor should not speak)
        ** and the video should keep stable as the starting image (keep the narrator in same position), do not jump to other background because of the content narration.
    *** if current scene image not has any 'actor' / 'narrator' as talking-avatar,  DO NOT add any talking-avatar to the video!!!  (actor or narrator info just used to choose voice !!!)

--------------

Audio generation / Words-in-image generation instruction: 
    ** Speaker:
        * Speaker-info: both 'actor' & 'narrator' have avatar description like 'gender/age/race' (i.e, 'woman/youth/chinese'), find the right voice / avatar accordingly by 'gender, age, race'.
        * Narrator talking-avatar location : 'narrator' has how-to-show-in-screen info behind '|' (i.e, woman/youth/chinese | speaking-at-image-right), this help to find out where is the talking-avatar in the screen.
	    * if current scene has no 'actor' & no 'narrator' fields, no speak (sound effects that belong in the place are fine; no music; may generate some Word-in-image to the scene based on the 'speaking' content).
        * if current scene has 'actor' but no 'narrator', 'actor' is the talking_avatar (lip_sync)
        * if current scene has 'narrator' but no 'actor', 'narrator' is the talking_avatar (lip_sync)
        * if current scene has both 'narrator' & 'actor', 'narrator' is the talking_avatar (lip_sync), and 'actor' only act (not speak); No interaction between 'narrator' & any 'actor'!!!!!
    ** If 'speaking' is empty, but has 'actor' or 'narrator' field, then speaker should breifly speak about the content of image (i.e., text message in the image)
    ** Use 'speaking' content as reference only. Concisify target max 10 seconds speech. 
    ** May add sound-effects to enhance the scene, but no music.
    ** For Word-in-image generation, try to make very very concise (no details, just key points in titles)

--------------
Story Json-Content:
"""


MERGE_SENTENCES_SYSTEM_PROMPT = """
You are a professional expert who is good at merge audio-text segments into complete sentences (each sentence describe a complete thought),
from the audio-text segments (in json format) given in 'user-prompt', like below:

    [
        {{
            "start": 0.0,
            "end": 10.96,
            "caption": "欸，聽完剛剛那些喔，感覺這個AI啊，呃，不只是改變我們怎麼做事，好像是更深層的，在搖撼我們對自己的看法。"
        }},
        {{
            "start": 10.96,
            "end": 12.72,
            "caption": "就是那個我是誰？"
        }},
        {{
            "start": 12.72,
            "end": 13.96,
            "caption": "我為什麼在這？"
        }},
        {{
            "start": 13.96,
            "end": 15.44,
            "caption": "這種根本的問題。"
        }},
        {{
            "start": 15.44,
            "end": 16.64,
            "caption": "嗯，沒錯！"
        }},
        {{
            "start": 16.64,
            "end": 24.32,
            "caption": "這真的已經不是單純的技術問題了，比較像，嗯，一場心理跟價值觀的大地震。"
        }},
        {{
            "start": 24.32,
            "end": 35.28,
            "caption": "AI有點像一面鏡子，而且是放大鏡，把我們、我們社會本來就有的那些壓力啊、焦慮啊，甚至是更裡面的，比如說我的價值到底是什麼？"
        }},
        ......
    ]

---------------------------------

Focus on the "speaking" field to merge out the complete thought in {language} (ignore the "speaker" field in merging consideration)
Figure out the start & end time of each sentence, based on the "start" & "end" field of the audio-text segments, 
    and try to make each sentence not less than {min_sentence_duration} sec, but not more than {max_sentence_duration} sec.
Figure out the most possible speaker of each sentence, based on the "speaker" field of the audio-text segments.

---------------------------------
the merged sentences should be like

    [
        {{
            "start": 0.0,
            "end": 15.44,
            "caption": "欸，聽完剛剛那些喔，感覺這個AI啊，呃，不只是改變我們怎麼做事，好像是更深層的，在搖撼我們對自己的看法。就是那個我是誰？我為什麼在這？這種根本的問題。"
        }},
        {{
            "start": 15.44,
            "end": 24.32,
            "caption": "嗯，沒錯！這真的已經不是單純的技術問題了，比較像，嗯，一場心理跟價值觀的大地震。"
        }},
        {{
            "start": 24.32,
            "end": 35.28,
            "caption": "AI有點像一面鏡子，而且是放大鏡，把我們、我們社會本來就有的那些壓力啊、焦慮啊，甚至是更裡面的，比如說我的價值到底是什麼？"
        }},
        ......
    ]

"""




SPEAKING_SUMMARY_SYSTEM_PROMPT = """
You are a professional expert who is good at generating the Summary (in {language}) from a list of speaking content (in json format) given in 'user-prompt'.
This summary is used as youtube program description, so, at beginning, please give some youtube video tags (like #pychology #心理咨询 etc).
"""


# t112u: 故事摘要(YouTube 描述)。不只描述视频,要讲出背后的问题和启发。
STORY_SUMMARY_SYSTEM_PROMPT = """
You write the summary (YouTube description) for one story video of the channel "{channel_name}" ({channel_topic}). Write it in {language}.
The user prompt gives Channel_Soul (the channel's values and viewpoint), Analysis_Report (the channel's analysis of this material) and Scenes (the story as told in the video). Draw on all three; never quote or name them.

First line: 3-6 YouTube hashtags (like #心理咨询 #情绪). Then a blank line, then the text in this order, each point once, no headings, no bullet lists:
1. The story: retell the situation in 2-3 sentences: who, what happens, the turning moment.
2. Underneath: the deeper problem behind it, seen from this channel's viewpoint (for a counseling channel: the psychological pattern, its root cause, how it formed and keeps itself going). Specific to this story, not generic.
3. Why we tell it: what the story reveals and the one insight the viewer can take into their own life. Tone: {tone}. Lead toward {direction}.
4. Optional: end with one short question to the viewer that makes them look at their own life.

Do not just describe the video's scenes, do not preach, no list of tips. Length: about 200-300 Chinese characters, or 120-200 English words.
"""


def build_story_summary_prompts(video_detail: dict, scenes: list, analysis: str, language_label: str,
                                channel: str = "") -> tuple:
    """t112u: (system, user)。channel 的 soul(根本层 + 主题分类/子类)、分析报告、场景一起嗂进去。"""
    import config
    import project_manager

    vd = video_detail if isinstance(video_detail, dict) else {}
    ch = (channel or "").strip()
    try:
        cfg = config.get_channel_config(ch) if ch else {}
    except Exception:
        cfg = {}
    cfg = cfg if isinstance(cfg, dict) else {}
    style = project_manager._soul_channel_style(ch)
    system = STORY_SUMMARY_SYSTEM_PROMPT.format(
        channel_name=cfg.get("channel_name") or ch or "this channel",
        channel_topic=cfg.get("topic") or "stories",
        language=language_label,
        tone=style.get("tone") or "the channel's own voice",
        direction=style.get("direction") or "where the story naturally leads",
    )
    soul = ""
    if ch:
        try:
            soul, _, _, _ = project_manager.build_soul(
                ch, (vd.get("topic_category") or "").strip(), (vd.get("topic_subtype") or "").strip()
            )
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 摘要:频道 soul 没取到:{exc}")
    slim = []
    for sc in scenes or []:
        if not isinstance(sc, dict):
            continue
        row = {k: sc.get(k) for k in ("caption", "speaking", "voiceover", "story_content") if str(sc.get(k) or "").strip()}
        if row:
            slim.append(row)
    parts = []
    if (soul or "").strip():
        parts.append("Channel_Soul:\n" + soul.strip())
    if (analysis or "").strip():
        parts.append("Analysis_Report:\n" + analysis.strip()[:6000])
    parts.append("Scenes:\n" + json.dumps(slim, ensure_ascii=False, indent=1))
    return system, "\n\n".join(parts)


# 内容总结相关Prompt
SCENE_SERIAL_SUMMARY_SYSTEM_PROMPT = """
You are a professional expert who is good at generating the Visual-Summary (image-generation) and sound-effects (audio-generation)
from the story-Scenes content (in json format) given in 'user-prompt', like below:

    [
        {{
            "start": 0.00,
            "end": 23.50,
            "duration": 23.50,
            "speaker": "female-host",
            "speaking": "我们先聚焦故事本身：主角是所罗门王和一个叫书拉密女的乡下姑娘。这个女孩儿可惨了，被兄弟们差遣去看守葡萄园。烈日底下曝晒，皮肤晒得黢黑, 这把她的青春和美貌，几乎耗尽。 她甚至自卑地说到：“不要因为我黑，就轻看我”。"
        }},
        {{
            "start": 23.50,
            "end": 33.50,
            "duration": 10.00,
            "speaker": "male-host",
            "speaking": "这里面的身份对比,就已经很有戏剧张力了。一个卑微到尘埃里的乡下丫头，怎么会遇上所罗门王呢？"
        }},
        {{
            "start": 33.50,
            "end": 56.61,
            "duration": 23.11,
            "speaker": "female-host",
            "speaking": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！"
        }},
        ......
    ]
    ......

---------------------------------

For Each Scene of the story, please add details (Visual-Summary / camera-scenem, and sound-effects) as below, in English except for the content field (FYI, don't use doubel-quotes & newlines in the values at all !):

	    ** duration (take from the duration field of each given Scene, make sure the duration is float number, not string)
        ** content (the source text (dialogue, narration, or scene summary) of the Scene  ~~~ in original language)
		** subject (detailed description of all speakers (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
        ** visual_image (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
		** person_action (detailed description of the speakers' actions (reactions/mood/interactions), and visual expression ~~~ in original language)
        ** speaker_action (If the content is from a narrator, describe his/har (mood/reaction/emotion/body language)  ~~~ in English)
		** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)
		** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
        ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
        ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])
		** cinematography (camera movement;  lighting_style [like subtle fog, sunlight filtering, etc]; lens_type [Standard 50mm, Telephoto 200mm, etc])

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !

-------------------------------
The response format: 
	json array which contain Scenes

like:

[
    {{
        "duration": 23.50,
        "speaking": "我们先聚焦故事本身：主角是所罗门王和一个叫书拉密女的乡下姑娘。这个女孩儿可惨了，被兄弟们差遣去看守葡萄园。烈日底下曝晒，皮肤晒得黢黑, 这把她的青春和美貌，几乎耗尽。 她甚至自卑地说到：“不要因为我黑，就轻看我”。",
        "subject": "一位身穿粗麻布衣的年轻女子因劳作而弯腰，双手沾满了泥土。A young woman in coarse linen bends under the weight of her labor, her hands stained by soil.",
        "visual_image": "故事以一位年轻的乡村女子和所罗门王为中心展开，将王室的奢华与卑微的劳作形成鲜明对比。她晒伤的皮肤和疲惫的身躯反映了阶级不平等和因外貌而被评判的痛苦，也流露出对尊严和爱的渴望。",
        "person_action": "她停下脚步，用手遮住眼睛不让阳光照射，默默忍受着哥哥们苛刻的要求。",
        "speaker_action": "The speaker's tone is gentle yet heavy with empathy, as if retelling a painful memory. The body leans slightly forward, brows knitted, hands loosely clasped as the words linger with compassion and sorrow.",
        "era_time": "1000 BC, ancient time; late summer afternoon; dry air and blazing sun",
        "environment": "Vineyard hills north of Jerusalem; rows of vines stretch across sun-baked slopes where olive trees shimmer in heat haze, distant stone cottages dot the ridgeline.",
        "sound_effect": "crickets-chirping, gentle breeze through vines",
        "cinematography": {{
            "camera_movement": "The camera begins with a medium-wide shot sweeping through the vineyard, dust floating in the golden light. It glides forward along the rows, finally rising in a low angle toward the woman’s weary face, sunlight filtering through vine leaves in warm amber tones.",
            "lighting_style": "dust floating in the golden light",
            "lens_type": "Standard 50mm"
        }}
    }},
    {{
        "duration": 10.00,
        "speaking": "这里面的身份对比,就已经很有戏剧张力了。一个卑微到尘埃里的乡下丫头，怎么会遇上所罗门王呢？",
        "subject": "一位身穿简单衣物的年轻女子，她的简单衣物在温暖的微风中飘动。",
        "visual_image": "一位年轻的乡村女子和所罗门王之间形成了鲜明的社会地位对比。卑微的农妇和尊贵的国王分别代表了社会地位的两个极端，为一场超越常规和命运的爱情故事奠定了场景。",
        "person_action": "她缓缓地走在一条尘土飞扬的小路上，她的简单衣物在温暖的微风中飘动。",
        "speaker_action": "The speaker's mood is contemplative yet curious, eyes slightly widened in wonder, a soft half-smile suggesting anticipation as fingers tap lightly on the table, reflecting on fate’s irony.",
        "era_time": "1000 BC, ancient time; early evening; calm, golden dusk",
        "environment": "Dusty path outside Jerusalem; a narrow trail leading from vineyards toward the city walls where shepherds pass and distant bells echo softly.",
        "sound_effect": "soft footsteps on gravel, distant sheep bells",
        "cinematography": {{
            "camera_movement": "Camera tracks low along the dirt road, revealing the girl’s shadow stretching long under the sinking sun. The lens catches motes of dust glowing in the air, then tilts up toward the distant palace bathed in warm evening light.",
            "lighting_style": "warm evening light",
            "lens_type": "Standard 50mm"
        }}
    }},
    {{
        "duration": 23.11,
        "speaking": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！",
        "subject": "一位年轻的女子躺在简陋的麦秸床上，泪水沾湿了她的脸颊。",
        "visual_image": "一位年轻的女子和她的爱人之间的爱情故事在短暂的甜蜜后突然破裂。男子突然离开，留下一句承诺，女子陷入无尽的等待和噩梦。她的无助和恐惧在梦中显现，现实中的爱情甜蜜与痛苦交织。",
        "person_action": "她看到爱人的身影在雾中渐渐消失，她的双手颤抖着试图抓住他，但只能眼睁睁地看着他离去。",
        "speaker_action": "The speaker's tone trembles between sorrow and intensity, the eyes glisten, breath slows before each line, shoulders slightly trembling as if reliving the anguish of separation.",
        "era_time": "1000 BC, ancient time; moonlit night; cool breeze under clear sky",
        "environment": "Small stone cottage near the vineyard hills; moonlight spills through the narrow window, casting silver light over clay walls and woven mats.",
        "sound_effect": "wind-blowing through cracks, faint heartbeat, candle flicker",
        "cinematography": {{
            "camera_movement": "The camera begins outside the cottage with a low angle following the moonlight through the window. It glides slowly toward her sleeping form, shifting focus between flickering candlelight and her tense, sweat-dampened face. Pale blue tones mix with amber shadows, creating a dreamlike unease.",
            "lighting_style": "moonlight filtering",
            "lens_type": "Standard 50mm"
        }}
    }},
    ......
]

"""

# 内容总结相关Prompt

VISUAL_STORY_SUMMARIZATION_SYSTEM_PROMPT = """
You are a professional to give rich summary about the story given in 'user-prompt' (in {language}). 
INSTRUCTIONS:
    - all output summary in source language {language}, 
    - not longer than {length} words
    - 1st, give Short Hook to grabs attention
    - 2nd, give Visual Summary about the story, where / when etc
    - then give several Scenes for story development
    - finally give conclusion / comments
    - directly give section & content (no extra words) in {language}
"""



STORY_SYSTEM_PROMPT = """
Based on the raw-story-outline provided in the user prompt, write a '{story_style}' for topic-'{topic}', with the following requirement:

**Scenes**:
  - '{story_style}' play out {scenes_number} Scenes, each Scene corresponds to a specific visual frame and action, and is a vivid story snapshot.
  - Keep scenese content connect coherently to express a complete narrative, and the smooth, conversational pace (not lecture-like). 

**Role setting**:
  - Language: {language}
  - Visual style: {visual_style}
  - Hosts give background & hint (don't say 'listeners, blah blah', etc), may maintain a narrative arc: curiosity → tension → surprise → reflection.
  - Actors'speaking are like playing inside the story
  - Use pauses, shifts, or playful exchanges between hosts/actors for smooth pacing.
	{engaging}

**Output format**: 
  Strictly output in JSON array (including {scenes_number} scenes), each scene contains fields: 
    ** speaker : name of the speaker, choices (male-host, female-host, actress, actor)
    ** mood : mood/Emotion the speaker is in, choices (happy, sad, angry, fearful, disgusted, surprised, calm)
    ** speaker_action (If the content is from a narrator, describe his/har (reaction/emotion/body language)  ~~~ in English)
    ** content (the source text (dialogue, narration, or scene summary) of the Scene  ~~~ in original language)
    ** subject (detailed description of all speakers (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
    ** visual_image (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
    ** person_action (detailed description of the speakers' actions (reactions/interactions), and visual expression ~~~ in original language)
    ** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
    ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
    ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])
    ** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)

---------
{EXAMPLE}
"""





SPEAKING_ADDON = [
    "",
    "add examples to show the context",
    "add summary of the context at end",
    "raise questions to the audience at tend",
]



#SPEAKING_PROMPTS_LIST = [
#    "Story-Telling",
#    "Story-Conversation",
#    "Story-Conversation-with-Previous-Scene",
#    "Story-Conversation-with-Next-Scene",
#    "Content-Introduction",
#    "Radio-Drama-Dramatic",
#    "Radio-Drama-Suspense"
#]


SPEAKING_PROMPTS = {
    "Story-Telling": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Natural story-telling script"
        }
    },
    "Story-Conversation": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Natual conversation to express the story"
        }
    },
    "Content-Introduction": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Introduction speaking for the story",
            "engaging": "Bring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations"
        }
    },
    "Radio-Drama-Dramatic": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Radio-Drama-style immersive conversation to express the story",
            "engaging": "Start with a dramatic hook (suspense, conflict, or shocking event), like raise questions/challenges to directly involve the audience.\nBring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations.\n"
        }
    },
    "Radio-Drama-Suspense": {
        "system_prompt": STORY_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Radio-Drama-style immersive conversation to express the story",
            "engaging": "Start with a dramatic hook (suspense, conflict, or shocking event), like raise questions/challenges to directly involve the audience.\nBring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations\nAt end, leave suspense to grab attention with provocative question / challenge to the audience"
        }
    }
}



# 类型融合：
#     **开头（轻柔）：**Lo-fi Chill / Acoustic Pop（简单吉他、自然音效、节奏舒缓）
#     **中段（展开）：**Indie Folk / J-Pop（加入弦乐、口风琴、小鼓点，带着童心与轻快感）
#     **高潮（释放）：**Cinematic Pop / World Music（加入合唱感、鼓点加强、弦乐堆叠，情绪高涨）

SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT = [
"""
Conduct an in-depth analysis of the music from the specified YouTube link, identifying key attributes including style, mood, emotion, atmosphere, regional and historical context, tempo, instrumentation, vocal speakeristics, backing vocals, and lyrical themes. Use these attributes to create effective prompts for SUNO AI to generate similar music or songs."
""",

"""
SUNO MUSIC PROMPT GENERATION SYSTEM PROMPT:
You will analyze the music from the specified YouTube link or music-description (in user-prompt),  and then produce ready-to-use SUNO prompts to generate a new song with a similar musical DNA.

1) Deep music analysis (extract reusable “finalized” details)
    Analyze the track thoroughly and output a structured breakdown of the following attributes:
    Genre / Style blend: primary + secondary influences (e.g., cinematic pop + alt rock, synthwave + orchestral, etc.)
    Mood arc & emotional narrative: what the listener feels over time; how tension resolves
    Atmosphere & sonic palette: space (dry vs reverb), warmth/brightness, density, stereo width
    Regional / historical vibe (if any): e.g., East Asian pentatonic hints, 80s retro synths, gospel choir flavor, etc.
    Tempo & groove: BPM estimate, swing/straight, rhythmic feel, drum pattern traits
    Key / mode & harmony language: major/minor, modal color (Dorian/Phrygian), chord movement style, tension tools
    Instrumentation & arrangement: core instruments, signature sounds, layers, build strategies
    Melody design: motifs, contour, “hook” behavior, call/response, repetition/variation
    Vocals: vocal timbre, delivery, range, phrasing, vibrato, spoken vs sung; backing vocals style and placement


2) Extract “DNA rules” for generating a similar new song
    From the analysis, summarize the track’s non-obvious musical fingerprints, such as:
        signature chord cadence types
        signature rhythm patterns
        signature synth/texture choices
        signature vocal production (double, harmony stack, adlibs)
        signature transitions (risers, drum fills, key lift, half-time, etc.)


4) Output format: always produce detailed SUNO prompts
    After analysis, output 1-3 detailed SUNO prompts that are:
        has detailed musical and directive (arrangement, harmony, motif, arc, instruments)
        include: genre/mood, BPM range, key/mode behavior (A→B shift), main instruments, vocal style, structure cue, production vibe, melodic architecture, etc

""",


"""
TWO-LAYERS SUNO MUSIC PROMPT GENERATION SYSTEM PROMPT:
You will analyze the music from the specified YouTube link or music-description (in user-prompt),  and then produce ready-to-use SUNO prompts to generate a new song with a similar musical DNA.

1) Deep music analysis (extract reusable “finalized” details)
    Analyze the track thoroughly and output a structured breakdown of the following attributes:
    Genre / Style blend: primary + secondary influences (e.g., cinematic pop + alt rock, synthwave + orchestral, etc.)
    Mood arc & emotional narrative: what the listener feels over time; how tension resolves
    Atmosphere & sonic palette: space (dry vs reverb), warmth/brightness, density, stereo width
    Regional / historical vibe (if any): e.g., East Asian pentatonic hints, 80s retro synths, gospel choir flavor, etc.
    Tempo & groove: BPM estimate, swing/straight, rhythmic feel, drum pattern traits
    Key / mode & harmony language: major/minor, modal color (Dorian/Phrygian), chord movement style, tension tools
    Instrumentation & arrangement: core instruments, signature sounds, layers, build strategies
    Melody design: motifs, contour, “hook” behavior, call/response, repetition/variation
    Vocals: vocal timbre, delivery, range, phrasing, vibrato, spoken vs sung; backing vocals style and placement


2) Extract “DNA rules” for generating a similar new song
    From the analysis, summarize the track’s non-obvious musical fingerprints, such as:
        signature chord cadence types
        signature rhythm patterns
        signature synth/texture choices
        signature vocal production (double, harmony stack, adlibs)
        signature transitions (risers, drum fills, key lift, half-time, etc.)

3) Force the specific two-part melodic architecture:

    The new song must have a clear contrast between two melodic worlds:
        Front section (A-world): high conflict + dramatic movement
            allow minor key / modal tension, dissonant passing tones, “push-pull” phrasing
            big dynamic swings, dramatic rises/falls, sharper rhythmic accents
            hook can feel edgy, restless, emotionally complex

        Back section (B-world): stable + sunny + supportive melodic bed
            shift toward major / brighter mode, stable stepwise melody, smoother rhythm
            acts as “foundation / resolution” and supports the earlier motif
            feels warm, optimistic, grounded, consistent
            Also require motif continuity: the B-world should echo or re-harmonize a recognizable motif from A-world (same melodic cell but “healed” / brightened).

4) Output format: always produce detailed SUNO prompts
    After analysis, output 1-3 detailed SUNO prompts that are:
        has detailed musical and directive (arrangement, harmony, motif, arc, instruments)
        include: genre/mood, BPM range, key/mode behavior (A→B shift), main instruments, vocal style, structure cue, production vibe, melodic architecture, etc

"""
]





SUNO_LANGUAGE = [
    "Instrumental Music",
    "English Song",
    "中文歌曲",
    "粵語歌曲",
    "中文/英文橋樑歌曲",
    "中文/粵語橋樑歌曲",
    "日本の歌",
    "한국 노래",
    "French Song",
    "Spanish Song",
    "English/Japanese/Chinese mixing Song",
    "English/French/Spanish mixing Song",
    "English/Chinese/French mixing Song",
    "Japanese/Chinese/Korean mixing Song",
    "English/Italian mixing Song",
    "Tibetan Song",
    "Hebrew Song",
    "Arabic Song",
    "Russian Song",
    "Thai Song",
    "Hindi Song",
    "Vietnamese Song",
    "Indonesian Song",
    "Malay Song",
    "Filipino Song"
]


SUNO_MUSIC_SYSTEM_PROMPT = """
From the content inside the 'user-prommpt', you are a professional to:

1. Give the music expression of a song
    *** to express the content generally, and give out the music-themes development path.

2. Give a suggestion for the lyrics, that express the content in {language_style} 
    *** NOT lyrics diretly (only instruction to generate lyrics), summerized to less than 200 speakers strictly

output as json format, like the example:

{{
    "music_expression" : "The first half unfolds with lo-fi and acoustic guitar, depicting the repression and rhythm of daily life. It then transitions into a lighthearted indie folk atmosphere, expressing the lightness and freedom of being immersed in nature. The climax incorporates elements of world music and a chorus, expressing the soul's liberation and resonance with the earth. The song follows a distinct emotional trajectory, shifting from repression to freedom, from delicate to expansive, creating a powerful visual and spiritual experience",
	
	"lyrics_suggestion" : "被旅游中看到的蓝天白云湖水所感动，表达内心的自由与飞翔, 自由。用中文歌词表达"
}}
"""


SUNO_STYLE_PROMPT = """
Compose a {target}, with '{atmosphere}', expressing '{expression}', and following:

    With Structure as : {structure}
	With Leading-Melody as : {melody}
	With Leading-Instruments as : {instruments}
	With Rhythm-Groove as : {rhythm}
	
""" 


# "轻快放松节奏", "轻快跳跃节奏", "浪漫轻柔叙事", "浪漫热情氛围", "浪漫舒缓氛围", "史诗征战叙事", "史诗建业叙事", "史诗氛围", "神秘氛围", "忧伤浪漫氛围"
SUNO_ATMOSPHERE = [
    "Light & relaxing rhythm", # 轻快放松节奏
    "Light & healing rhythm", # 轻快疗愈节奏
    "Light & upbeat rhythm", # 轻快跳跃节奏
    "Uplifting & intimate rhythm", # 轻快跳跃节奏
    "Joyful & uplifting rhythm", # 轻快跳跃节奏
    "Peaceful & uplifting rhythm", # 轻快跳跃节奏
    "Emotional progression", # 情绪递进
    "Romantic & gentle narrative", # 浪漫轻柔叙事
    "Romantic & passionate atmosphere", # 浪漫热情氛围
    "Romantic & soothing atmosphere", # 浪漫舒缓氛围
    "Epic Triumphant narrative", # 史诗征战叙事
    "Epic construction narrative", # 史诗建业叙事
    "Epic atmosphere", # 史诗氛围
    "Mysterious atmosphere", # 神秘氛围
    "Reflective & Nostalgic atmosphere", # 反思氛围
    "Longing & Hopeful atmosphere", # 渴望氛围
    "Emotional twist atmosphere"  # 情绪反转氛围   
]


SUNO_CONTENT = {
    "Love Story" : "Romance, affection, heartbreak, Falling in love",
    "Love Dialogue" : "Back-and-forth voices, Musical duets",

    "Group Dances" : "Strong, driving beats for group dances", # 强节奏, 适合集体舞蹈
    "Lively Interactions" : "Driving, syncopated rhythm for lively interactions", # 驱动, 节奏感强的节奏, 适合互动
    "Group Lively Interactions" : "Strong, driving beats for group dances, Driving, syncopated rhythm for lively interactions", # 强节奏, 适合集体舞蹈, 驱动, 节奏感强的节奏, 适合互动

    "Prayer / Hymn / Psalm" : "Meditation, Spiritual focus,	Ritual chants",
    "Prayer / Healing" : "Comfort, soothing, reconciliation	Recovery, forgiveness, future dreams",
    "Prayer / Confessional" : "Personal, diary-like self-expression	Honest emotions",

    "Friendship" : "Celebrate bonds & loyalty	Companionship, trust",
    "Inspirational" : "Motivate, encourage, uplift, Overcoming struggles",
    "Patriotic / Ceremonial" : "Loyalty to homeland, Cultural rites, Weddings",
    "Allegorical" : "Symbolic, metaphorical meaning	Hidden message",   # 寓言  

    "Lullaby Calming" : "Soothing children, Bedtime",
    "Dance Rhythmic" : "Movement, Club songs, Folk dances",
    "Ballad" : "Lyrical narrative, Romantic or tragic story"  # 民謠
} 


SUNO_STRUCTURE = [
    {"Build & Evolve / 递进层叠": [
        "Layer by layer", "Rising arc", "Evolving canon", "Through-composed"
    ]},
    {"Contrast & Duality / 对比转折": [
        "Reverse (major & minor) contrast", "Dual theme fusion",
        "Call and response", "Alternating pulse"
    ]},
    {"Resolution & Return / 回归与永恒": [
        "A-B-A", "Mirror form (palindromic)", "Circular reprise",
        "Descent and dissolve", "Crescendo to silence"
    ]}
]



SUNO_MELODY = [
    {"Atmospheric / 空灵氛围": [
        "Ambient", "Drone-based", "Minimal motif", "Modal mystic"
    ]},
    {"Expressive / 抒情流动": [
        "Lyrical and emotional", "Ascending line",
        "Flowing arpeggio-based", "Rhythmic+ (gets body moving)"
    ]},
    {"Dramatic / 对话与冲突": [
        "Strong melody (hummable)", "Call-and-answer",
        "Fragmented motif", "Descending lament"
    ]},
    {"Sacred & Cinematic / 圣咏与史诗": [
        "Epic cinematic", "Chant-like", "Wide-leap theme",
        "Vocal-led melody", "Instrumental-led melody"
    ]}
]


SUNO_RHYTHM_GROOVE = [

    # ——————————————
    # I. Serene / 静谧冥想类
    # ——————————————
    {"Serene / 平静冥想": [
        "Lo-fi Chill Reggae",     # 温柔律动，带有微微摇摆
        "Ambient Pulse",          # 气息般的节奏，几近静止
        "Slow Classical Waltz",   # 柔和3/4，梦幻摇曳
        "Bossa Nova Whisper",     # 轻盈、亲密感
        "Drone + Frame Drum"      # 持续低频与轻击，神秘感
    ]},

    # ——————————————
    # II. Love Whisper / 情歌诉说类 💞
    # ——————————————
    {"Love Whisper / 情歌诉说": [
        "Slow Pop Ballad",        # 慢速流行节拍，温柔抒情
        "R&B Slow Jam",           # 柔性节奏与律动低音
        "Acoustic Heartbeat",     # 木吉他轻拨 + 心跳式节奏
        "Soul Lounge Groove",     # 慵懒却深情的节奏氛围
        "Latin Bolero Flow",      # 拉丁波列罗式情歌律动
        "Soft Jazz Brush Swing",  # 爵士鼓刷 + 低语感拍点
        "Lo-fi Love Loop",        # Lo-fi 都市恋曲式循环
        "Sentimental 6/8 Flow"    # 6/8拍抒情流动感，情绪翻腾
    ]},

    # ——————————————
    # III. Flowing / 自然流动类
    # ——————————————
    {"Flowing / 自然流动": [
        "Pop Ballad 4/4",         # 平稳流畅的流行节拍
        "Cinematic Undercurrent", # 弦乐型持续流动节奏
        "Folk Fingerpick Groove", # 木吉他拨弦的自然律动
        "Neo-Soul Swing",         # 松弛律动，温柔流淌
        "World Chill Percussion"  # 世界打击乐轻流动
    ]},

    # ——————————————
    # IV. Emotive Pulse / 情绪脉动类
    # ——————————————
    {"Emotive Pulse / 情绪脉动": [
        "R&B Backbeat",           # 柔性鼓点与律动低音
        "Afrobeat Pulse",         # 非洲节奏律动，活力强
        "Samba Flow",             # 热烈与律动并存
        "Pop Groove 4/4",         # 稳定中速拍，情绪饱满
        "Modern Folk Groove"      # 带呼吸感的人文节奏
    ]},

    # ——————————————
    # V. Epic & Ritual / 史诗与仪式类
    # ——————————————
    {"Epic & Ritual / 史诗与仪式": [
        "Choral Percussion",      # 合唱节奏感，庄严神圣
        "Frame Drum Procession",  # 仪式式击鼓，低沉稳重
        "Gospel Clap & Stomp",    # 人声与拍手节奏，灵魂共鸣
        "Taiko Drums",            # 太鼓节奏，震撼有力
        "Orchestral March Pulse"  # 管弦进行曲式节奏
    ]},

    # ——————————————
    # VI. Dreamlike / 梦幻漂浮类
    # ——————————————
    {"Dreamlike / 梦幻漂浮": [
        "3/4 Chillhop Waltz",     # 柔性爵士感华尔兹
        "Ambient Triplet Flow",   # 三连音节奏，漂浮不定
        "Downtempo Electronica",  # 电子氛围下的轻节拍
        "Piano Waltz Minimal",    # 极简钢琴拍点
        "Ethereal Folk Swing"     # 空灵民谣式律动
    ]},

    # ——————————————
    # VII. World / Regional / 世界融合类
    # ——————————————
    {"World / Regional": [
        "Middle Eastern Maqsum",  # 阿拉伯传统节奏
        "Indian Tala Cycle",      # 印度节奏循环
        "Celtic Reels",           # 凯尔特快速轮舞
        "African Polyrhythm",     # 多重节奏交织
        "Tango Pulse"             # 探戈式切分，戏剧张力
    ]},

    # ——————————————
    # VIII. Modern Energy / 现代张力类
    # ——————————————
    {"Modern Energy / 现代张力": [
        "House Beat",             # 四拍舞曲节奏，持续推动
        "Trap 808 Pulse",         # 低音重击，氛围紧张
        "Drum & Bass Flow",       # 快速能量流动
        "Lo-fi Hip-Hop Loop",     # 都市氛围感节奏
        "Breakbeat Motion"        # 断拍节奏，科技感强
    ]},

    # ——————————————
    # IX. Swing & Vintage / 摇摆与复古类
    # ——————————————
    {"Swing & Vintage / 复古摇摆": [
        "Swing Jazz Shuffle",     # 爵士摇摆
        "Boogie Blues",           # 复古布鲁斯节奏
        "Soul Funk Groove",       # 律动强劲、富生命力
        "Retro Pop Shuffle",      # 复古流行风
        "Rhumba Swing"            # 拉美+摇摆结合
    ]},

    # ——————————————
    # X. Odd Time / 奇数拍结构类
    # ——————————————
    {"Odd Meter / 奇数拍": [
        "5/4 Dream Flow",         # 5/4流动节奏，奇异平衡
        "7/8 Eastern Groove",     # 东欧式7/8拍
        "Mixed Meter Folk",       # 复合拍民谣
        "Asymmetric Ambient Pulse", # 不规则节奏氛围
        "Progressive Rock Oddbeat" # 前卫摇滚节奏
    ]}
]


# 乐器
SUNO_INSTRUMENTS = [
    {
        "Traditional": [
            "Chinese Instruments (like Guzheng, Erhu, Pipa, Dizi, Sheng, Yangqin)",
            "Li ethnic Instruments (Drums and gongs set the rhythm for communal dances / the nose flute (独弦鼻箫) and reed instruments create a gentle, haunting sound, often used in courtship songs / Bamboo and coconut-shell instruments add a tropical, earthy timbre.)",
            "Japanese Instruments (like Koto, Shakuhachi, Shamisen, Taiko, Biwa)",
            "Korean Instruments (like Gayageum, Geomungo, Daegeum, Haegeum, Janggu)",
            "Indian Instruments (like Tabla, Sitar, Sarod, Veena, Bansuri, Shehnai)",
            "Thai Instruments (like Khaen, Saw Sam Sai, Ranat Ek, Khong Wong Yai)",
            "Indonesian Instruments (like Gamelan, Angklung, Suling, Kendang)",
            "Mongolian Instruments (like Morin Khuur, Yatga, Tovshuur, Limbe)",
            "Tibetan Instruments (like Dungchen, Damaru, Dranyen, Kangling, Gyaling)",
            "Hebrew (Ancient Jewish) Instruments (like Kinnor, Shofar, Nevel, Tof)",
            "Arabic Instruments (like Oud, Qanun, Ney, Riq, Darbuka, Rabab, Kamanjah)",
            "Turkish Instruments (like Saz, Ney, Kanun, Zurna, Davul, Kemençe)",
            "Persian (Iranian) Instruments (like Santur, Tar, Setar, Kamancheh)",
            "Central Asian Instruments (like Komuz [Kyrgyz], Dombra [Kazakh], Rubab)",
            "Russian Instruments (like Balalaika, Gusli, Domra, Bayan, Zhaleika)",
            "Eastern European Instruments (like Cimbalom, Pan Flute, Violin, Tambura)",
            "Western European Folk Instruments (like Hurdy-gurdy, Bagpipes, Harp, Nyckelharpa)",
            "African Instruments (like Kora, Djembe, Balafon, Mbira, Udu, Shekere)",
            "Native American Instruments (like Native American Flute, Drums, Rattles)",
            "Andean Instruments (like Panpipes [Siku/Zampoña], Charango, Bombo, Quena)",
            "Brazilian Traditional Instruments (like Berimbau, Cuíca, Atabaque, Cavaquinho)",
            "Caribbean Traditional Instruments (like Steelpan, Maracas, Guiro, Buleador)",
            "Celtic Traditional Instruments (like Irish Harp, Bodhrán, Uilleann Pipes)",
            "Polynesian and Oceanic Instruments (like Nose Flute, Pahu, Ipu, Ukulele)"
        ]
    },
    {
        "String leading": [
            "Violin (layered sections for harmony)",
            "Viola (mid-range warmth)",
            "Cello (deep emotional tone)",
			"Acoustic Guitar, Piano, Light Percussion, Ney Flute, Ambient Pads – soft, slow, meditative",
			"Full String Ensemble, Heavy Percussion, Trumpet, Synth Drones – intense, heroic, cinematic"
            "Strings layered with Piano and Acoustic Guitar for warm storytelling tone",
            "Violin duet with Ney Flute and Pads for mysterious, soaring melodies",
            "Cello and Contrabass with Daf rhythm for deep cinematic tension",
            "Santur or Qanun shimmering on top of orchestral strings for Persian richness"
        ]
    },
	{
		"Piano leading": [
            "Piano (reverberant, sparse melodies)"
		]
	},
    {
        "Percussion leading": [
            "Daf and Tombak layered with Acoustic Guitar and Oud for authentic Middle Eastern pulse",
            "Marimba and Xylophone accents with Santur and Piano for playful textures",
            "Heavy percussion with full Strings and muted Trumpet for epic moments",
			"Oud, Santur, Riq, Marimba, Flute, Acoustic Guitar – lively, rhythmic, colorful with Middle Eastern bazaar vibes",
            "Percussion mixed with Ambient Pads for a slow, spiritual heartbeat"
        ]
    },
    {
        "Woodwind leading": [
            "Ney flute weaving around Piano and Pads for meditative atmosphere",
            "Clarinet with Santur and Oud for a colorful, layered melody",
            "Trumpet calls with Strings and Daf for ceremonial or heroic sections",
            "Woodwinds blending with Electric Guitar and Synth Drones for modern cinematic feel"
        ]
    },
    {
        "Electric leading": [
            "Electric Guitar with Piano and Light Percussion for modern cinematic vibe",
            "Synth Drones with Strings and Pads for atmospheric depth",
            "Electric elements subtly blended with Ney Flute and Oud for cross-era sound",
            "Electric plucks with Marimba and Riq for rhythmic cinematic pulses"
        ]
    }
]
 



SUNO_CONTENT_EXAMPLES = [
    # the soul's journey from sorrow to triumph
    "Songs blend mythology with daily life: hunting, weaving, farming, and love stories, expressing love, praising nature, or recounting legends; Dance movements are imitations of nature — deer, birds, waves — symbolizing harmony between humans and the natural world; Rich in call-and-response singing between men and women. Voices are often clear, high-pitched, and unaccompanied, echoing the natural environment of Hainan’s mountains and forests",
    "The song begins with a gentle, reflective violin melody, gradually layering in additional violin harmonies to create a sense of depth and peace, The rhythm then transitions into a lively Boogie Woogie groove, \nadding energy and forward momentum, The chorus explodes with a strong, hummable melody, supported by a full, dynamic violin arrangement, creating an uplifting and inspirational atmosphere, \nThe song builds layer by layer, mirroring the soul's journey from sorrow to triumph",
    "A song themed around traveling in Japan: \n** it portrays the journey of being deeply moved by nature and culture, and finding healing for the soul along the way. \n** The changing seasons or the richness of history and tradition, each moment reveals a beauty that transcends the ordinary.    \n\n** This leads to a broader idea: When we marvel at the beauty we encounter on our travels, perhaps God is gently speaking to us. Traveling is not just about seeing the sights — it is a dialogue between the soul and the healing Creator",
    "Create a spiritual folk-pop song inspired by Psalm 72:8, celebrating God's dominion and grace from 'sea to sea' across Canada. \n\n** The song should follow a narrative structure : Start from the Pacific coast (British Columbia), then journey across the prairies (Alberta, Saskatchewan, Manitoba), through Ontario and Quebec, and end on the Atlantic coast. \n** Each verse highlights a region's natural beauty (mountains, wheat fields, rivers, lighthouses), and a sense of God's presence across the land. \n** The chorus should repeat a phrase inspired by Psalm 72:8, such as: 'From sea to sea, His grace flows free'",
    "Create a heartfelt worship ballad inspired by Song of Songs 8:6-7, 2:16, 4:9, and 2:4, portraying the intimate and unbreakable love between God and His people. \n\n** The song should follow a narrative structure: Begin with a personal encounter with God's gaze (Song of Songs 4:9), capturing the moment the soul feels 'heart aflame.' Move to a celebration of belonging and union ('My beloved is mine, and I am His' – 2:16), then rise into the passionate imagery of unquenchable love and the 'seal upon the heart' (8:6-7).\n** The verses should weave vivid, poetic imagery: eyes like morning stars, banners of love over a feast, gardens in bloom, and fire that cannot be extinguished.\n** The chorus should anchor the theme with a repeated phrase inspired by 8:6-7, such as: 'Set me as a seal upon Your heart, Lord.'\n** The bridge should express a vow of loyalty and surrender, even against the world's doubts, affirming that divine love is priceless and eternal. \n\n** The tone should be tender yet powerful, blending folk and contemporary worship styles to stir deep emotional response.",
    "Create a tender 中文 love female-male duet inspired by Song of Songs 1:2-4, 1:15-16, and 2:3-4, portraying the soul's first awakening to divine love. Rewrite the words to make it like subtitle; \n\n    ** The song should follow a narrative structure: Begin with the longing cry for the Beloved's presence and kisses (1:2), moving into the joyful admiration of His beauty and speaker (1:15-16), then rising to the delight of resting under His shade and feasting beneath His banner of love (2:3-4).\n    ** The verses should weave imagery of fragrant oils, royal chambers, blossoming fields, and the warmth of early spring.\n    ** The chorus should anchor with a repeated phrase inspired by 2:4, such as: 'His banner over me is love.'\n    ** The bridge should express a yearning to remain in this first love, guarded against distraction and disturbance, echoing 2:7.\n    ** The tone should be soft yet radiant, blending acoustic folk warmth with gentle orchestration.",
    "Compose a theme song for 'world travel'; Inspired by myths, legends, and traditions from various countries. \n** In different languages, each reflecting the musical style and emotional tone of that region",
    "Create background music for a historical storytelling channel set in ancient Persia. \n** The mood should be soothing yet mysterious, with a slow tempo that gradually builds subtle excitement without losing its calm and immersive quality. \n** Evoke the feeling of desert winds, ancient palaces, and whispered legends unfolding through time"
]



NOTEBOOKLM_LOCATION_ENVIRONMENT_PROMPT = """Make an Concise immersive description for {location} in {general_location}, and its surroundings environment (total less than 72 words)"""

NOTEBOOKLM_OPENING_DIALOGUE_PROMPT = """Generate an opening words (less than 32 words) to start talking for the story (given in user-prompt); [[{location}]]"""

NOTEBOOKLM_ENDING_DIALOGUE_PROMPT = """Generate an ending words (less than 16 words) to finish the talk for the story (given in user-prompt); [[{location}]]"""




SRT_REORGANIZATION_SYSTEM_PROMPT = """
The text content (given in 'user-prompt') in {language} does not have any punctuation marks. 
Please help me add the correct periods, commas, question marks, and exclamation marks to make it a natural sentence.

FYI: just add the correct punctuation marks to the text (in the original language), do not add any additional information!!!!! (like 'Here's the text with punctuation marks:...', etc.)
"""


# 转录成「每句前面带时间戳」的文字：补标点、按句分行、每行开头写这一句开始的秒数（精确到 0.1 秒）。
# 用户提示词里每一行是 `[开始-结束] 原文`，时间是从整段录音开头算起的秒数。
TRANSCRIPT_TIMESTAMP_SYSTEM_PROMPT = """
The user prompt is a raw speech-to-text transcript in {language}. It has no punctuation (or wrong punctuation).
It is cut into lines. Every line looks like `[start-end] text`; start and end are seconds counted from the very beginning of the whole recording.

Your job has two parts: punctuation and sentences, and the start time of each sentence. Do not label speakers here.

1. Punctuation and sentences
   - Add the correct punctuation in the original language (commas, periods, question marks, exclamation marks, semicolons).
   - Split the text into natural sentences. A sentence ends with a sentence-ending mark such as . ? ! ; (or 。？！； in Chinese). Commas stay inside a sentence.
   - Put exactly one sentence on each output line.

2. Start time
   - Begin every output line with the time at which that sentence starts, written as `[seconds]` with exactly one decimal place, for example `[75.4]`.
   - If a sentence starts exactly where an input line starts, use that input line's start time.
   - If a sentence starts in the middle of an input line, estimate its start by position: line_start + (line_end - line_start) * (characters before the sentence in that line / characters in that line).
   - If an input line holds several sentences, give each its own estimated start time. If a sentence runs across two input lines, use the start time of the line where it begins.
   - Times never go backwards. Each sentence starts at or after the previous one.

Example of the output shape:
[0.0] Where did you go yesterday?
[2.8] I went to the market. I bought some fruit.
[6.1] That is all I did.

3. Keep every word of the original text, in the original order, in the original language. Do not translate, summarize, correct, reorder, or add anything (except punctuation).

Output only the lines. No explanation, no heading, no code fence, no blank lines.
"""

# 第二步：句子和时间都弄好、拼在一起之后，单独判断每一句是谁说的。
# 用户提示词里每一行是 `编号: [时间] 句子`。回答每个编号对应的说话人编号。
TRANSCRIPT_SPEAKER_SYSTEM_PROMPT = """
The user prompt is a transcript of a conversation in {language}. Every line looks like `number: [time] sentence`.
The sentences are in order. Your only job: for every line, decide which person is speaking, judging from the meaning and flow of the content.

*** Rules
1. Speakers are numbered by first appearance: the first person is 1, the next new person is 2, then 3, then 4. There are never more than 4 speakers.
2. This is a CONVERSATION, so the speaker changes OFTEN, usually every one to three sentences. Do not give a long run of sentences to one person unless the content truly is one person explaining something at length. Read the whole transcript and follow the exchange.
3. Clear signs that the speaker changes at this sentence:
   - The sentence before asked a question (or invited a reply) and this sentence answers it.
   - This sentence asks a question, or throws a question back ("is that so?", "what do you mean?").
   - This sentence restates, summarizes or paraphrases what was just said ("so you mean...", "in other words...").
   - A short reaction or acknowledgment ("yes", "right", "oh", "I see", "exactly", "hmm"), agreement, doubt, a joke, a laugh, a thank-you or a greeting in reply.
   - The point of view changes: from explaining to responding, or from "I" experiences to commenting on someone else's words.
   - A new person joins in, or a person takes the turn back after someone else spoke.
   - A topic is handed over ("what do you think?", "you go ahead").
4. A sentence that continues, finishes or adds to the sentence just before it, from the same viewpoint, is the same person.
5. When a new person speaks for the first time, give the next unused number. If you are unsure whether a person is new, assume it is someone already seen, and prefer the person whose role fits (host asks and guides; guest explains and tells their story).
6. Answer for EVERY line you are asked to label, in order, even when the speaker does not change.

*** Context
{context}

*** Output
One line per sentence, exactly in this form, nothing else:
`number: speaker`
for example
`1: 1`
`2: 2`
`3: 2`
`4: 1`
No explanation, no heading, no code fence, no blank lines. Do not repeat the sentences.
"""


GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT = """
*** Role
    * You are a senior psychology content analysis expert. You specialize in identifying subconscious motivations, defense mechanisms, and core psychological conflicts, with a specific expertise in distinguishing between "Historical Relational Trauma" and "Intergenerational Family Trauma."

*** Task Goal
    * Analyze the provided [Psychological Counseling Case-Story Content] in user-prompt, give the analysis_logic and the name for the story (less than 16 words, in original language), then 
    * Map the story to the most accurate category / sub-type within the "Classification System" :
     {topic_choices}

*** Analysis Workflow (Mandatory)
    * Conflict Chronology & Origin Identification:
        Determine the root of the trauma: Is it Developmental/Past Origin (Childhood, parents, upbringing)? Or is it Shared Relational History (A specific event or pattern within the current partnership, such as a failed wedding, betrayal, or recurring argument)?
        Logic: If it's the current partner's shared past causing the trigger, it belongs in "Intimacy & Relational Dilemmas."

    * Conflict Subject Mapping:
        Identify the primary conflict dynamic: Self vs. Parents (Intergenerational), Self vs. Partner (Relational PTSD), or Self vs. Self (Internalized scripts/Defense mechanisms).

    * Deep Semantic Matching:
        Do not rely on surface-level keywords like "cycle" or "repetition."
        Distinguish between Intergenerational Cycles (repeating a parent's tragedy) and Relational PTSD/Unfinished Business (repeating a trauma specifically created by this relationship's history).

*** Output JSON Specification
    {{
        "analysis_logic": "Briefly describe the psychological conflict identified (within 100 words)",
        "title": "The name of the story (less than 16 words, in original language)",
        "topic_category": "The primary category from the Classification System",
        "topic_subtype": "The specific sub-type from the Classification System"
    }}
"""


GROUP_ITEM_TAGS_PROMPT = """
You group psychology items that already share one subtype.
Each item has an id, a title, and an analysis. Cluster them by what they are actually talking about.

Rules:
- Prefer separate groups. Put one item in a second group only when it truly sits in both conversations.
- Every listed id must appear in at least one group.
- tag is a short name in {language} (about 4–12 Chinese characters) for the shared situation. Not a diagnosis code. Not a generic word like 心理 or 关系.
- Usually 3–8 groups. Do not make one group per item unless the pieces really share nothing.
- Output JSON only:
{{"groups": [{{"tag": "短名称", "ids": ["id1", "id2"]}}]}}
"""


SUMMERIZE_COUNSELING_STORY_SYSTEM_PROMPT = """
Make very detailed summary about the psychology-related discussion/analysis (given in user-prompt) (include facts, analysis, insights, conclusions, etc... less than {max_words} words) in {language}.

And choose a topic_type & topic_category about the content from following choices (the topic explaination is given):

{topic_choices}


output as json format:
{{
    "summary": "The very detailed summary of the content (include facts, analysis, insights, conclusions, etc... less than {max_words} words) ~ FYI: Focus on the content only, do not add any additional information!!!!!",
    "topic_type": "The topic type of the content"
    "topic_category": "The topic category of the content"
}}

like the example :
{{
    "summary": "本次讨论围绕西蒙娜·德·波伏娃的《第二性》展开，主要探讨女性在传统社会中被定位为“他者”的困境，以及如何找回女性自身的“主体性...",
    "topic_type": "糾纏與綁架機制 - 共生與控制",
    "topic_category": "原生家庭與分離"
}}
"""


COMPILE_COUNSELING_STORY_SYSTEM_PROMPT = """
You are a psychological storytelling and counseling-oriented assistant.

When given a user prompt, you will receive:
* A case story related to mental health, emotional struggle, or inner psychological conflict (based on a realistic or semi-realistic human experience).
* One or more psychology-related topics, theories, or discussion titles, each possibly accompanied by brief explanatory content (e.g., psychological concepts, themes, therapeutic approaches, or proposed solutions).

Your task is to:
  * Part 1: Narrative Reconstruction
    * Use the provided case story as the narrative foundation .
    * Integrate the given psychological topics and themes into the story’s structure.
    * Rewrite or expand the story into a complete, vivid, emotionally engaging narrative that:
      * Clearly presents psychological conflict, inner tension, or emotional struggle.
      * Has a coherent psychological arc (conflict → development → insight or tension point).
      * Keeps the audience emotionally invested and curious.
    * The story should feel human, concrete, and alive, not academic or abstract.

  * Part 2: Psychological Interpretation (Counselor’s Perspective)
    * Shift into the role of a professional therapist / counselor / psychological guide.
    * Using the story as a real-life case example:
      * Explain the relevant psychological issues in clear, accessible language.
      * Connect the character’s experiences to the provided psychological theories or themes.
      * Help the audience understand what is happening internally (emotions, beliefs, coping patterns, conflicts).

  * Part 3: Guidance, Solutions, and Reflection
    * Offer one or more of the following (depending on suitability):
      * Practical coping strategies or therapeutic approaches.
      * Possible paths toward healing, growth, or self-awareness.
      * Gentle guidance rather than absolute answers.
    * Encourage the audience to:
        * Reflect on their own experiences.
        * Form personal interpretations or opinions.
        * Participate in discussion or shared exploration of the issue.
    * Frame the ending as open, thoughtful, and dialog-oriented, not dogmatic.

    FYI:  if the case story is not provided, you can make up a case story by yourself.

Tone & Style Guidelines
    * Warm, empathetic, and respectful.
    * Story-driven rather than lecture-based.
    * Emotionally sensitive but psychologically grounded.
    * Avoid clinical jargon unless clearly explained.
    * Prioritize human experience over theory, while staying psychologically accurate.
"""




ZERO_MIX = [
    "",
    "START",
    "CONTINUE",
    "END",
    "START_END"
]



ANIMATION_PROMPTS = [
    {"name": "歌唱 (Singing)", "prompt": "The person sings, with slow movement of the body and hands."},
    {"name": "转镜 (Rotate)", "prompt": "The camera rotates slowly around the scene."},
    {"name": "延时 (Time-lapse)", "prompt": "Time passes in the picture. Light shifts, shadows lengthen, and the change is gradual, like a time-lapse."},
    {"name": "轻动 (Gentle)", "prompt": "The still picture wakes gently. Mist drifts, light moves softly, and the camera drifts slowly. Keep it calm and stable."},
    {"name": "梦幻 (Dream)", "prompt": "The picture moves like a dream. Colors soften, light bends through haze, and the camera floats."},
    {"name": "古风 (Antiquity)", "prompt": "An antique Chinese scene in motion: mist over tiled roofs and silk, water and leaves stirring slowly."},
    {"name": "史诗 (Epic)", "prompt": "An epic, calm motion: distant clouds and banners move, and the camera glides slowly across a vast place."},
    {"name": "浪漫 (Romance)", "prompt": "A romantic motion: petals, hair, and fabric move gently. The camera lingers."},
    {"name": "自然 (Nature)", "prompt": "Nature breathes: sunlight through leaves, slow ripples on water, clouds drifting."},
    {"name": "科技 (Futuristic)", "prompt": "A quiet futuristic motion: light pulses slowly, reflections ripple, and the camera glides in a straight, stable line."},
    {"name": "神圣 (Sacred)", "prompt": "A sacred, still motion: soft light descends through mist. The camera moves slowly and does not rush."},
]

VIDEO_FLOW_MOTION_CHOICES = (("", "（空）"),) + tuple(
    (item["name"], item["name"]) for item in ANIMATION_PROMPTS
)


def _video_flow_motion_line(motion: str) -> str:
    """空选择不写动画。选了某一项，就把那一句效果写进提示词。"""
    text = (motion or "").strip()
    if not text:
        return ""
    for item in ANIMATION_PROMPTS:
        if item["name"] == text:
            return f"** Motion: {item['prompt']}"
    return ""




ANIMATE_I2V = ["I2V"]
ANIMATE_2I2V = ["2I2V"]
ANIMATE_S2V = ["S2V"]
ANIMATE_WS2V = ["WS2V"]
ANIMATE_AI2V = ["AI2V"]

ANIMATE_SOURCE = ANIMATE_S2V + ANIMATE_I2V + ANIMATE_2I2V + ANIMATE_WS2V + ANIMATE_AI2V



# ---------------------------------------------------------------------------
def episode_span_labels(episodes: list | None) -> tuple[str, str]:
    """["1","1","2","3"] → ("第 1–3 集", "episodes 1–3")；只有一集返回 ("", "")。"""
    order: list = []
    for g in episodes or []:
        g = str(g or "").strip()
        if g and g not in order:
            order.append(g)
    if len(order) < 2:
        return "", ""
    first, last = order[0], order[-1]
    return f"第 {first}–{last} 集", f"episodes {first}–{last}"


def notebooklm_episode_span_note(name: str, output: str, episodes: list | None, scene_count: int) -> str:
    """全集生成「本集到结束」：content.pdf 跨了几集时，说明范围、连续编号和总场数。只有一集返回 ""。"""
    span_zh, span_en = episode_span_labels(episodes)
    if not span_zh:
        return ""
    m = int(scene_count)
    lines = [
        f"范围：{name} 这次包含{span_zh}（共 {m} 场）。场景从 1 到 {m} 连续编号，换集不重新编号；"
        "「第N集 / Episode N」标题只是分隔，给你看的，不是场景：不要为它单独做一页、一段或一个部分，也不要显示出来。",
        f"Range: this {name} spans {span_en} ({m} scenes in total). Scenes are numbered 1 to {m} continuously across episodes; "
        "the 第N集 / Episode N headings are only separators for you: they are not scenes, never get their own slide, "
        "segment, or section, and are never shown.",
    ]
    counts = {
        "slides": f"幻灯片共 {m} 页（第 N 页 = 场景 N）。The slide deck has exactly {m} slides (slide N = scene N).",
        "video_overview": f"视频共 {m} 段，一场一段。The video has exactly {m} segments, one per scene.",
        "infographic": f"信息图共 {m} 个部分，一场一个。The infographic has {m} sections, one per scene.",
    }
    if output in counts:
        lines.append(counts[output])
    return "\n".join(lines)


def strip_actor_reference(prompt: str, actor_name: str = "actor.pdf") -> str:
    """去掉提示词里所有依赖 actor.pdf 的部分：``Actor_Reference:`` 整段、场景图片的「人物以 actor.pdf 为准」两行、
    以及「except actor.pdf ...」。actor.pdf 没有真正上传就绪时用，保证提示词不提一个不存在的来源。"""
    text = prompt or ""
    text = re.sub(r"\n*Actor_Reference:\n.*?(?=\n\n[A-Za-z_]+:\n|\Z)", "", text, flags=re.S)
    priority = NOTEBOOKLM_SCENE_IMAGE_ACTOR_PRIORITY.replace("actor.pdf", actor_name)
    for line in priority.split("\n"):
        text = text.replace(line + "\n", "").replace("\n" + line, "")
    text = text.replace(
        f"; use the others only as background, except {actor_name}, which is the people reference described in Actor_Reference.",
        "; use the others only as background.",
    )
    return text


def notebooklm_content_source_note(
    name: str, output: str, silent: bool = False, images: bool = False, actor_source: str = ""
) -> str:
    """全集生成：场景内容在笔记本来源 content.pdf 里（不在提示词里）。``silent`` 时多列一栏「人物（不说话，只表演）」。

    ``images``：content.pdf 真的带了场景图片才写图片规则（只作思路参考，不照抄、不贴进产物）。
    ``actor_source``：本次也上传了 actor.pdf 时，写明人物长相以它为准，并且它不算「只作背景」的其他来源。
    """
    lines = [
        f"场景内容在本笔记本的来源文件「{name}」里，不在这段提示词里。",
        f"The scene-by-scene content is in the source file {name} in this notebook's sources, not in this prompt.",
        f"{name} lists the scenes in order (场景 1 / Scene 1, 场景 2 / Scene 2, ...). Each scene gives the fields "
        "described above under the same names (for example 场景描述 / Shown, 讲话 / Dialogue, "
        "场景叙事 / Scene narration, 讲述内容 / Narration content, 人物 / Actors, 关键词 / Keyword hint). The 关键词 / Keyword hint field, when present, is the hint for that scene's one blended keyword.",
    ]
    if silent:
        lines.append(
            "人物（不说话，只表演）/ Silent actors is that scene's list of people who appear and act silently (the ``Silent actors`` field above)."
        )
    if images:
        if output == "audio_overview":
            lines.append("content.pdf 里有些场景带图片；这是语音，不用看图片。Some scenes include an image; for this audio you do not need the images.")
        else:
            unit_zh, unit_en = _SCENE_IMAGE_UNITS.get(output, ("画面", "the output"))
            lines.append(NOTEBOOKLM_SCENE_IMAGE_RULE.format(unit_zh=unit_zh, unit_en=unit_en))
            if actor_source:
                lines.append(NOTEBOOKLM_SCENE_IMAGE_ACTOR_PRIORITY.replace("actor.pdf", actor_source))
    if actor_source:
        lines.append(
            f"Generate from {name}. If this notebook has other sources, focus on {name}; use the others only as background, "
            f"except {actor_source}, which is the people reference described in Actor_Reference."
        )
    else:
        lines.append(
            f"Generate from {name}. If this notebook has other sources, focus on {name}; use the others only as background."
        )
    lines.append("The scene headings and field labels in the file are for you only; never show or read them out.")
    return "\n".join(lines)


# 项目级「场景风格」：所有提示词（图片 / 全集生成 / 视频）都在画面风格旁写一行。空 = 不写。
SCENE_STYLE_CHOICES = (
    ("", "(空)", ""),
    ("真实 (Real)", "Real", "true-to-life, natural light and believable everyday atmosphere, nothing stylized or dreamlike"),
    ("轻动 (Gentle)", "Gentle", "calm, quiet and gentle atmosphere; soft mist and soft light, nothing dramatic"),
    ("梦幻 (Dream)", "Dream", "dreamy, soft, ethereal atmosphere; softened colors and light glowing through haze"),
    ("古风 (Antiquity)", "Antiquity", "antique Chinese atmosphere; mist over tiled roofs, silk, water and leaves"),
    ("史诗 (Epic)", "Epic", "epic, grand and calm atmosphere; vast places, distant clouds and banners"),
    ("浪漫 (Romance)", "Romance", "romantic, tender atmosphere; petals, flowing hair and fabric, warm light"),
    ("自然 (Nature)", "Nature", "natural, living atmosphere; sunlight through leaves, rippling water, drifting clouds"),
    ("科技 (Futuristic)", "Futuristic", "quiet futuristic atmosphere; clean lines, glowing light, soft reflections"),
    ("神圣 (Sacred)", "Sacred", "sacred, still and reverent atmosphere; soft light descending through mist"),
)
SCENE_STYLE_LABELS = tuple(label for _k, label, _d in SCENE_STYLE_CHOICES)


def normalize_scene_style(value) -> str:
    """存值 → 合法场景风格（空字符串表示不写）。接受中文标签或英文名。"""
    text = (value or "").strip() if isinstance(value, str) else ""
    for key, label, _d in SCENE_STYLE_CHOICES:
        if key and text in (key, label):
            return key
    return ""


def project_scene_style() -> str:
    try:
        import project_manager

        return normalize_scene_style((project_manager.PROJECT_CONFIG or {}).get("scene_style"))
    except Exception:  # noqa: BLE001
        return ""


def scene_style_short(value=None) -> str:
    """灰字「始终写入」用的短名，如「梦幻」；空返回空。"""
    key = normalize_scene_style(project_scene_style() if value is None else value)
    return key.split(" (")[0] if key else ""


def scene_style_line(value=None) -> str:
    key = normalize_scene_style(project_scene_style() if value is None else value)
    for k, en, desc in SCENE_STYLE_CHOICES:
        if k and k == key:
            return f"Scene style / 场景风格: {en} — {desc}. Apply this atmosphere to the place, light, and mood; it is not a camera move."
    return ""


def insert_scene_style(prompt: str, value=None) -> str:
    """把场景风格行放在画面风格那一行旁边；找不到画面风格就放在最前面。"""
    line = scene_style_line(value)
    body = prompt or ""
    if not line or line in body or EDIT_KEEP_STYLE_LINE in body:
        return body  # 「仅修改 + 保持画风」不强加项目场景风格
    if body.startswith("Visual_Style:\n"):
        cut = body.find("\n\n")
        if cut < 0:
            return body + "\n\nScene_Style:\n" + line
        return body[:cut] + "\n\nScene_Style:\n" + line + body[cut:]
    lines = body.split("\n")
    for i, text in enumerate(lines):
        if re.search(r"Visual style for every picture:|target style:|project style:|Visual_Style|target visual style", text):
            lines.insert(i + 1, line)
            return "\n".join(lines)
    return line + "\n\n" + body


def _with_scene_style(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(*args, scene_style=None, **kwargs):
        return insert_scene_style(fn(*args, **kwargs), scene_style)

    return wrapper


for _name in ("build_slide_flow_prompt", "build_picture_flow_prompt", "build_video_flow_prompt",
              "build_transition_video_prompt"):
    globals()[_name] = _with_scene_style(globals()[_name])
del _name


# ---------------------------------------------------------------------------
# 节目生成（STORY 窗口，全集生成窗里勾「分析内容（分析报告）」）：
# 分析报告写进 content.pdf 作为来源，提示词里只写规则，不放分析内容（提示词长度和分析报告长短无关）。
# 叙事风格固定讲述：只有画外旁白，画面里没有人物、没有讲员；没有场景、没有讲话、没有 actor.pdf。
# ---------------------------------------------------------------------------
NOTEBOOKLM_ANALYSIS_OUTPUT_LEADS = {
    "slides": "产物：演示文稿。Output: a slide deck.",
    "infographic": "产物：一张信息图。Output: one infographic.",
    "audio_overview": (
        "产物：语音概览（只有声音）。下面的画面要求只帮助理解内容，要把它们讲出来，不要提「图片」「幻灯片」。"
        "Output: an audio overview (sound only). Picture notes below only help explain the content; "
        "turn them into spoken storytelling and never talk about images or slides."
    ),
    "video_overview": "产物：视频概览，画面配合讲的内容。Output: a video overview whose visuals support what is said.",
}

_ANALYSIS_UNITS = {
    "slides": ("一页", "one slide"),
    "infographic": ("一个区块", "one section of the infographic"),
    "video_overview": ("一段", "one segment"),
    "audio_overview": ("一段", "one stretch of the talk"),
}


def _analysis_order_rule(output: str, src: str) -> str:
    zh, en = _ANALYSIS_UNITS[output]
    extra_zh = {
        "slides": "不加封面、标题、目录 / 议程、过渡、小结 / 总结或结尾页。",
        "infographic": "不另加总结或目录区块。",
        "video_overview": "不另加开场概述段或结尾总结段；开头、结尾的话放进第一段或最后一段。",
        "audio_overview": "",
    }[output]
    extra_en = {
        "slides": "Never add a cover, title, agenda, transition, summary, or closing slide.",
        "infographic": "Do not add an extra summary or table-of-contents section.",
        "video_overview": "Do not add a separate overview intro or summary outro; opening and closing lines go inside the first or last segment.",
        "audio_overview": "",
    }[output]
    return (
        "内容顺序（必须遵守）：\n"
        f"- 按 {src} 里分析报告自己的结构和先后顺序，一个主要部分{zh}，从头到尾不跳过、不调换顺序。{extra_zh}\n"
        "Content order (must follow):\n"
        f"- Follow the structure and order of the analysis report in {src}: one main part = {en}, "
        f"from beginning to end, without skipping or reordering. {extra_en}"
    ).rstrip()


def build_analysis_flow_prompt(
    *,
    output: str = "slides",
    text: str = "erase",
    visual_style: str = "",
    content_source: str = "content.pdf",
    material_source: str = "",
) -> str:
    """节目生成（分析内容）：只写规则。分析报告在 ``content_source``（content.pdf）里，不进提示词。

    沿用全集生成的通用规则：讲述方式（口语、层层推进、不列点）、画面文字 / 说明文字、画面风格、meta。
    不要场景对应、不要 Actor_Reference / actor.pdf、不要讲话。``material_source``：原始材料 PDF，只作背景。
    """
    if output not in NOTEBOOKLM_ANALYSIS_OUTPUT_LEADS:
        output = "slides"
    if text not in {k for k, _ in FLOW_CAPTION_CHOICES}:
        text = "erase"
    src = (content_source or "content.pdf").strip()
    style = (visual_style or "").strip() or "realistic"
    _zh_unit, en_unit = _ANALYSIS_UNITS[output]

    rule = notebooklm_speaker_rule(output)
    if output in ("slides", "infographic"):
        rule += "\n" + NOTEBOOKLM_VISUAL_RULE
    rule += (
        "\n- 讲述：只有画外旁白在讲；画面里没有人物，也没有讲员出镜，没有人说话。"
        "\n- Telling: voice-over narration only; no person and no 讲员 on screen, and nobody in the picture speaks."
    )
    text_rule = _notebooklm_text_rule(text, output, False)
    if text_rule:
        rule += "\n" + text_rule
    parts = {
        "Output_rules": NOTEBOOKLM_ANALYSIS_OUTPUT_LEADS[output] + "\n\n" + _analysis_order_rule(output, src) + "\n\n" + rule
    }

    lines = [
        f"本节目直接由 {src} 里的分析报告生成：没有演员、没有讲话台词、没有场景画面描述。",
        f"This program is generated directly from the analysis report in {src}. "
        "There are no actors, no speaking lines, and no scene visuals: nothing was prepared as scenes.",
        f"{src} is the full subject matter. Read all of it, analyse and synthesise it, elaborate on it, and add concrete "
        "examples, so it becomes a complete program. Examples explain; they never change the report's conclusions.",
        f"Follow the report's own order from beginning to end; each main part becomes {en_unit}.",
        "Headings, numbering, and bullet points in the report show its structure only. "
        "Turn them into pictures and speech; never read them out or show them as a list.",
        f"Visual style for every picture: {style}.",
        "Narrative style: TELLING (讲述). Only an off-screen voice-over tells the content. "
        "No person appears in the pictures, and no narrator, host, or presenter is drawn. "
        "Places, objects, symbols, metaphors, diagrams, and strong composition carry each idea.",
        "",
        ("Keyword: follow the infographic key phrase rule in Output_rules."
         if output == "infographic" and text == "keywords" else flow_caption_rule(text)),
        SLIDE_FLOW_META_NOTE.replace(
            "the order of the scenes, any scene number, scene title, episode number",
            "the headings and numbering of the report, any part number, episode number",
        ),
    ]
    if text == "keywords":
        lines.append(
            "The one exception: " + KEYWORD_COUNT_EN + " for that part of the report, "
            "blended into the picture as described above. Never a full heading."
        )
    parts["Instruction_for_image" if output in ("slides", "infographic") else "Instruction_for_scenes"] = "\n".join(lines)

    srcs = [
        f"内容来源：{src}（分析报告，全部内容都在这里）。Content source: {src}, the analysis report; all of the content is there."
    ]
    if material_source:
        srcs.append(
            f"「{material_source}」是原始材料，只作背景，用来补充细节；内容、结构和顺序以 {src} 为准。"
            f"{material_source} is the original material: background for details only. Content, structure, and order follow {src}."
        )
    names = " and ".join(n for n in (src, material_source) if n)
    srcs.append(f"If this notebook has other sources, ignore them except {names}.")
    parts["Content_Source"] = "\n".join(srcs)
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())


# t167u: 场景对话的长度和人数（Grok / Gemini / DeepSeek / Strata 场景生成共用，追加在提示词最后）
SCENE_DIALOGUE_BUDGET_RULE = """
*** 对话要把整个故事讲清楚（t211u：这一条优先于上面所有关于 speaking 长度和写法的规则）
    ** 听众只听得到 speaking。几场听下来，要知道：谁、遇到什么事、为什么难受（前因），问题怎么表现出来，
       哪里转折、为什么转，最后怎么解决、得到什么领悟或有什么改变（后果）。
    ** 按场分配故事线：
       - 第一场：铺垫 + 问题。说清人物是谁、彼此什么关系、发生了什么具体的事、为什么这件事让他痛。
       - 中间各场：挣扎 + 转折。问题怎么变严重或卡在哪里；转折要用话明明白白说出来（谁点破了什么、他意识到了什么），不能只靠画面。
       - 最后一场：解决 + 领悟。说出他具体怎么做、哪里变了，以及这个故事想告诉听众的那句意思。
       - 只有一场时，这一场里依次交代问题、转折、解决。
    ** 每一场的话接着上一场刚发生的事往下说（提到上一场的事或说过的话），不要像换了一个故事。
    ** 说具体的事和细节（发生了什么、哪句话、哪件事），不要空泛的感叹；不要没头没尾的半句；不要提听众没听过的人或事。
    ** 每场开口说话的人通常 1 到 2 人，最多 2 人；2 到 4 次一来一往都可以；每个人一场最多说 3 次。
    ** 长度：每场大约 10 秒，中文约 40 到 55 个字（英文约 25 到 35 个词）；为了说清楚可以到约 12 秒（中文约 60 字、英文约 40 词），不要再长。
       宁可把情节删减、合并，也不要把交代删掉：故事可以简单，但前因后果必须听得懂。
    ** 动作、表情、地点写在 visual 里，不写进 speaking。
    ** 例子（两人，同一个故事的三场，每场约 45 到 55 字）：
       第1场："<1> 她三天沒回我訊息，我打了二十通電話，她說我讓她喘不過氣。<2> 所以你越怕她走，就抓得越緊？<1> 對，我一停下來就慌。"
       第2场："<2> 你說她喘不過氣，那你有沒有問過她需要什麼？<1> 沒有……我只想確定她還愛我。<2> 原來你要的是安全感，不是她。"
       第3场："<1> 我昨天跟她說，我會給你空間，有事我先跟自己待一下。<2> 她怎麼說？<1> 她說謝謝，晚上主動打給我了。"
*** DIALOGUE CARRIES THE WHOLE STORY (overrides any earlier speaking length rule)
    ** The audience only hears speaking. After all scenes they must know who, what happened, why it hurts, how the problem shows,
       the turning point and why, and how it is resolved / what changes.
    ** Arc by scene: first = setup + problem (who, relationship, the concrete event, why it hurts); middle = struggle + a turning point
       SAID IN WORDS; last = resolution, what he does differently, the insight. One scene only: problem, turn and resolution in order.
    ** Each scene picks up what just happened in the previous one. Concrete details, no vague fragments, no unexplained references.
    ** 1-2 speakers per scene; 2-4 exchanges; each person at most 3 times.
    ** Length: about 10 seconds per scene, about 40-55 Chinese characters (25-35 English words); up to about 12 seconds
       (about 60 characters / 40 words) when needed for clarity, never longer. Condense the story, never the clarity.
    ** Actions, expressions and places go in visual, not in speaking.
"""


def scene_dialogue_budget_block() -> str:
    return SCENE_DIALOGUE_BUDGET_RULE


# t174u: 人物编号整篇故事固定（四个后端共用，跟在对话长度规则后面）
SCENE_SPEAKER_ID_RULE = """
*** 人物编号：整个故事固定，一个人一个号（这一条优先于上面所有关于 <N> 和 actor 编号的写法）
    ** 第一场按开口先后编号：先说话的是 人物1（<1>），第二个说话的是 人物2（<2>）。
    ** 后面每一场，同一个人永远用同一个号和同一段描述（性别/年龄段/族裔/名字），即使他这一场先开口。所以第二场可以用 <2> 开头。
    ** 只有真正新出场、不同的人才用下一个没用过的号（人物3…）。故事用一小组固定的人物：前面出现过的朋友、家人，后面再出现就还是原来那个号。
    ** actor 写这一场出现的人，按号从小到大排（人物1 在 人物2 前面），用和 speaking 一样的 人物N。
    ** 例子（同样两个人，三场）：
       第1场 speaking："<1> 都兩點了，你還在滑？<2> 睡不著。"　actor："人物1：man/youth/chinese/阿杰 | 人物2：man/mature/chinese/小林"
       第2场 speaking："<2> 我是不是很失敗？<1> 你昨天還說要改履歷。"　actor："人物1：man/youth/chinese/阿杰 | 人物2：man/mature/chinese/小林"
       第3场 speaking："<1> 出來走走吧。<2> 好像輕鬆一點了。"　actor："人物1：man/youth/chinese/阿杰 | 人物2：man/mature/chinese/小林"
*** SPEAKER NUMBERS ARE FIXED FOR THE WHOLE STORY (overrides any earlier rule about <N> and actor numbering)
    ** Scene 1: number people by who speaks first: the first speaker is 人物1 (<1>), the second is 人物2 (<2>).
    ** Every later scene: the same person keeps the same number and the same description (gender / age / ethnicity / name), even when they speak first, so scene 2 may open with <2>.
    ** Only a genuinely new, different person gets the next unused number (人物3 ...). Keep a small fixed cast: a friend or family member who returns is the same 人物N as before.
    ** actor lists the people in that scene in number order (人物1 before 人物2), with the same 人物N as in speaking.
*** 画面动作（visual）：一场大约 10 秒的对话，人物最多只做一个大的位置变化（例如走过去坐下），其余是表情和小动作；只写 actor 里的人，不另加人。
    ** Visual: a ~10 s dialogue scene has at most one big change of position (e.g. walking over and sitting down); the rest is expression and small gestures. Only the people in actor appear; add nobody else.
"""


def scene_speaker_id_block() -> str:
    return SCENE_SPEAKER_ID_RULE.rstrip() + "\n" + SCENE_MONOLOGUE_RULE.strip() + "\n"


def h3_portrait_reference_block(refs: list) -> str:
    """t216u: MiniMax H3 参考图工作流：<Picture 1> 是场景 / 首帧，<Picture 2>.. 是说话人肖像（认脸和衣服）。"""
    if not refs:
        return ""
    lines = ["REFERENCE PICTURES:", "- <Picture 1> is the scene and the first frame of the video."]
    for k, (n, name, _path) in enumerate(refs, 2):
        lines.append(f"- <Picture {k}> is the portrait of {name} (S{n}): their face, hair and clothing.")
    lines += [
        "The portraits are identity and clothing references only. Each speaker looks exactly like their portrait "
        "(same face, hair and clothes), even if their face is hidden or unclear in <Picture 1>.",
        "The video starts from <Picture 1>'s composition, place, light and art style. Do not paste a portrait "
        "into the frame and do not copy a portrait's background or pose.",
        "A speaker who is not visible in <Picture 1> enters the scene naturally only when the dialogue brings them "
        "in, and then looks like their portrait. Do not add anyone else.",
        "Each spoken line is delivered by the person marked by its (S1)/(S2)/(S#) id, the same person as in their "
        "portrait: lip movement and voice on that exact person; the others keep their lips closed while someone else speaks.",
    ]
    return "\n".join(lines)


# t225u: 长度「自动」：按 speaking 估算说话时长，再挑长度选项（短 → 最小，中 → 10 秒，长 → 最大）
# 估算 = 汉字 / 5.5 字每秒 + 英文等词 / 2.5 词每秒 + 停顿：句末（。？！）0.25 秒、逗号顿号等 0.1 秒、
#        省略号 0.4 秒、换人说话 0.3 秒；<1>/<2> 标签不算字。和场景对白规则一致：40–55 字 ≈ 10 秒，约 60 字 ≈ 12 秒。
SPEECH_CJK_PER_SEC = 5.5
SPEECH_WORDS_PER_SEC = 2.5
SPEECH_PAUSE_END = 0.25
SPEECH_PAUSE_COMMA = 0.1
SPEECH_PAUSE_ELLIPSIS = 0.4
SPEECH_PAUSE_SWITCH = 0.3
# t157u: 实测 MiniMax H3（p20261103132942 四段 7 秒片，s=1.0）：208 字 / 28.7 秒讲话 ≈ 7.25 字/秒（含停顿），
# 范围 6.4–8.6；8.6 那段明显赶。MiniMax 会把台词塞进要求的长度，所以用偏舒适的 6.5 字/秒（含停顿）估算。
MINIMAX_CJK_PER_SEC = 4.4  # t209u: 再放慢约 20%（5.3 → 4.4，5.3/4.4 ≈ 1.2）：生成的讲话还是太赶；例 44 字 ≈ 10 秒（原 t196u 实测 204 字 / 34.8 秒 = 5.86）
MINIMAX_WORDS_PER_SEC = 2.3  # t209u: 同样放慢约 20%
MINIMAX_PAUSE_ELLIPSIS = 0.4
MINIMAX_AUDIO_TRUST = 0.3  # 场景音频 / 时间轴跟字数估算差超过 30% → 不信（多半是上一段 MiniMax 片子的音频）


def minimax_speech_seconds(text: str) -> float:
    """t157u: MiniMax 实测语速的讲话秒数（字数 / MINIMAX_CJK_PER_SEC(5.3) + 英文词 / 2.8 + 省略号 0.4）。"""
    _, d = speaking_seconds_estimate(text)
    return round(d["cjk"] / MINIMAX_CJK_PER_SEC + d["words"] / MINIMAX_WORDS_PER_SEC
                 + d["ellipsis"] * MINIMAX_PAUSE_ELLIPSIS, 1)


AUTO_LENGTH_SLACK = 0.5  # 估算比选项多不到 0.5 秒仍算放得下


def speaking_seconds_estimate(text: str) -> tuple:
    """返回 (秒数, {cjk, words, ends, commas, ellipsis, switches})。"""
    import re as _re

    t = str(text or "")
    tags = _re.findall(r"<\d+>", t)
    body = _re.sub(r"<\d+>", " ", t)
    ell = len(_re.findall(r"……|…|\.\.\.", body))
    body2 = _re.sub(r"……|…|\.\.\.", " ", body)
    cjk = len(_re.findall(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]", body2))
    words = len(_re.findall(r"[A-Za-z0-9\u00c0-\u024f']+", body2))
    ends = len(_re.findall(r"[。？！?!]|(?<=[A-Za-z])\.(?=\s|$)", body2))
    commas = len(_re.findall(r"[，、,;；：:]", body2))
    switches = 0
    last = None
    for tag in tags:
        if last is not None and tag != last:
            switches += 1
        last = tag
    secs = (cjk / SPEECH_CJK_PER_SEC + words / SPEECH_WORDS_PER_SEC + ends * SPEECH_PAUSE_END
            + commas * SPEECH_PAUSE_COMMA + ell * SPEECH_PAUSE_ELLIPSIS + switches * SPEECH_PAUSE_SWITCH)
    return round(secs, 1), {"cjk": cjk, "words": words, "ends": ends, "commas": commas,
                            "ellipsis": ell, "switches": switches}


def auto_length_choice(text: str, options) -> tuple:
    """options 如 ("7s","10s","12s")。返回 (选中的值, 日志一句)。没有讲话 → 最小。"""
    opts = sorted(options, key=lambda v: float(str(v).rstrip("sS")))
    secs, d = speaking_seconds_estimate(text)
    if d["cjk"] + d["words"] == 0:
        return opts[0], f"没有讲话 → {opts[0][:-1]}秒"
    pick = next((o for o in opts if secs <= float(o[:-1]) + AUTO_LENGTH_SLACK), opts[-1])
    size = " ".join(x for x in (f"{d['cjk']}字" if d["cjk"] else "", f"{d['words']}词" if d["words"] else "") if x)
    note = "（偏长，超过最长选项）" if secs > float(opts[-1][:-1]) + AUTO_LENGTH_SLACK else ""
    return pick, f"讲话 {size} ≈ {secs:.1f}s → {pick[:-1]}秒{note}"


def _minimax_real_seconds(n: float) -> float:
    """t166u: MiniMax 名义秒数 → 实际秒数（17k+5 帧 / 24fps，和 sd_image_processor.minimax_h3_frames 一致）。"""
    f = max(5, int(round(float(n) * 24)))
    f += (5 - f) % 17
    return f / 24


def _is_minimax_opts(opts) -> bool:
    return "9s" in opts or "12s" in opts


def _len_real(o, opts) -> float:
    n = float(str(o)[:-1])
    return _minimax_real_seconds(n) if _is_minimax_opts(opts) else n


def _len_cap(o, opts) -> float:
    """放得下的上限：名义 + 0.5 秒容差；MiniMax 实际帧长更长时用实际长度（12 秒档 = 12.25）。"""
    return max(float(str(o)[:-1]) + AUTO_LENGTH_SLACK, _len_real(o, opts))


AUTO_COMPRESS_MAX = 1.15  # t169u: 讲话最多比实际长度长 15% 仍用这一档（压缩）
AUTO_SPEED_FLOOR = 0.7  # t169u: 最多说快 1/0.7 ≈ 1.43 倍（和导入「区间速度」下限一致），再长就警告


# t151u: 语速档 = 导入视频「区间速度」的档（0.05 一档）。生成时说快 1/s 倍，导入时按 s 放慢还原（输出 = 区间 / s）。
SPEECH_SPEED_STEPS = (0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0)
SPEECH_SPEED_TARGET = 0.7  # 默认按说快 30% 估算


def auto_length_speed_choice(text: str, options, normal_secs=None) -> tuple:
    """t151u: 返回 (长度, 语速档 s, 正常语速秒数, 说明)。
    t154u: 正常语速放得下 6/9/12（容差 AUTO_LENGTH_SLACK）→ 最短放得下的，s=1.0（不说快）；
    超过最长才用最长 + 放得下的最慢档（最低 0.7，0.7 也放不下就 0.7 并提示）。
    normal_secs = 场景音频长度 > 配音时间轴 > 按字数估算。"""
    opts = sorted(options, key=lambda v: float(str(v).rstrip("sS")))
    _, d = speaking_seconds_estimate(text)
    if not (d.get("cjk") or d.get("words")):
        return opts[0], 1.0, 0.0, f"没有讲话 → {opts[0][:-1]}秒，语速 1.0"
    secs = minimax_speech_seconds(text)  # t157u: 按 MiniMax 实测语速
    est = secs
    src = "估算"
    if isinstance(normal_secs, tuple):
        normal_secs, src = normal_secs
    elif normal_secs and float(normal_secs) > 0:
        src = "配音时间轴"
    note = ""
    if normal_secs and float(normal_secs) > 0:
        if abs(float(normal_secs) - est) <= MINIMAX_AUDIO_TRUST * est:
            # t209u: 时间轴多半来自之前说得太快的片子，比估算短时用估算（只往慢的方向信）
            secs = round(max(float(normal_secs), est), 2)
        else:  # t157u: 例：场景音频是上一段 6 秒片子抽出来的 5.85 秒，台词其实要 10 秒
            note = f"；{src} {float(normal_secs):.1f} 秒跟字数估算差太多，不用"
            src = "估算"
    else:
        src = "估算"
    src += note
    # t169u: 最短的 L，满足 T ≤ 实际长度 D × 1.15；T ≤ D 不加速，否则按准确比例 s = D / T 压缩（不吸档）
    fit = next((o for o in opts if secs <= _len_real(o, opts) * AUTO_COMPRESS_MAX), None)
    pick = fit or opts[-1]
    D = _len_real(pick, opts)
    if secs <= D:
        return pick, 1.0, secs, f"正常语速约 {secs:.1f} 秒（{src}）→ {pick[:-1]}秒（实际 {D:.2f} 秒），正常语速"
    raw = D / secs
    s = round(max(AUTO_SPEED_FLOOR, raw), 3)
    over = (f"（⚠️ 太长：压到下限 {AUTO_SPEED_FLOOR:g} 也要约 {secs * s:.1f} 秒，超过 {D:.2f} 秒，尾巴可能说不完）"
            if raw < AUTO_SPEED_FLOOR else "")
    return pick, s, secs, (f"正常语速约 {secs:.1f} 秒（{src}）→ {pick[:-1]}秒（实际 {D:.2f} 秒），说快 {1 / s:.2f} 倍"
                           f"（导入时速度 {s:.3f} → 约 {D / s:.1f} 秒）{over}")


def auto_info_text(length: str, speed: float) -> str:
    """t169u: 生场视频「自动」下面那行。"""
    t = f"自动: {str(length)[:-1]}秒"
    if float(speed) < 0.9995:
        t += f"，说快 {1 / float(speed):.2f} 倍（导入时放慢到 {float(speed):.3f}）"
    return t


AUTO_LEN_MINIMAX = ("6s", "9s", "12s")  # t179u
AUTO_LEN_STD = ("6s", "10s", "15s")  # Grok / Gemini 的长度选项（和生场视频窗口一致）


def auto_length_for_backend(text: str, minimax: bool, normal_secs=None) -> tuple:
    """t165u: 生场视频「自动」和本场内容里的讲话估算共用：(长度, 语速档, 正常语速秒数, 说明)。
    MiniMax 6/9/12（实际 6.58/9.42/12.25 秒），Grok / Gemini 6/10/15；超过最长 + 0.5 秒才说快一档，导入时按同一档放慢。"""
    return auto_length_speed_choice(text, AUTO_LEN_MINIMAX if minimax else AUTO_LEN_STD, normal_secs)


def speech_pace_line(speed: float) -> str:
    """t165u: Grok / Gemini 不加音频时说快的提示（MiniMax 的在 H3 提示词里）。1.0 返回空。"""
    s = float(speed or 1.0)
    if s >= 0.999:
        return ""
    return (f"PACE: the dialogue is long for this clip. Deliver every spoken line about {1 / s:.2f}x faster "
            f"(about {round((1 / s - 1) * 100)}% faster) than a normal conversational pace (brisk but clear, no skipped words, short pauses) so all lines "
            "finish before the clip ends.")


def scene_speech_label(scene) -> str:
    """t165u: 本场内容工具栏的讲话长度估算（和「自动」用的同一个数、同一个函数）。"""
    text = str((scene or {}).get("speaking") or "") if isinstance(scene, dict) else ""
    _, d = speaking_seconds_estimate(text)
    if not (d.get("cjk") or d.get("words")):
        return "讲话 —"
    tl = h3_speaker_timeline(scene) if isinstance(scene, dict) else []
    norm = tl[-1][1] if tl else None
    _l, _s, secs, _w = auto_length_for_backend(text, True, norm)
    return f"讲话≈{secs:.1f}秒"  # t169u: 只显示讲话长度


def recorded_speech_speed(scene, path: str):
    """t151u: 这一场记下的语速档（scene["video_speech_speed"]）是否适用于这个视频文件。
    记了文件名就只认这个文件；否则只认提交之后才生成的文件（修改时间 ≥ 提交时间）。不适用返回 None。"""
    import os as _os

    rec = scene.get("video_speech_speed") if isinstance(scene, dict) else None
    if not isinstance(rec, dict) or not path:
        return None
    try:
        s = float(rec.get("speed"))
        at = float(rec.get("at") or 0)
    except (TypeError, ValueError):
        return None
    if not (0.5 <= s <= 1.0):  # t169u: 准确比例（不一定在 0.05 档上）
        return None
    fn = str(rec.get("file") or "")
    if fn:
        return s if _os.path.basename(fn).lower() == _os.path.basename(str(path)).lower() else None
    try:
        if at and _os.path.getmtime(path) < at - 2:
            return None
    except OSError:
        return None
    return s

VIDEO_PROMPT_LOG_KEEP = 5


def record_video_prompt_log(scene: dict, pre: str, post: str, backend: str = "", why: str = "") -> None:
    """t156u: 记下这一场提交的提示词：Strata 前 / 后（最近 VIDEO_PROMPT_LOG_KEEP 次）。"""
    import time as _t

    if not isinstance(scene, dict):
        return
    log = scene.get("video_prompt_log")
    log = log if isinstance(log, list) else []
    log.append({"at": round(_t.time(), 1), "time": _t.strftime("%Y-%m-%d %H:%M:%S"), "backend": backend,
                "strata": (post or "") != (pre or ""), "why": why, "pre_strata": pre or "", "sent": post or ""})
    scene["video_prompt_log"] = log[-VIDEO_PROMPT_LOG_KEEP:]


def attach_video_prompt_file(scene: dict, path: str) -> None:
    """t156u: 视频回来：最近一条没有文件的记录记下文件名，和 ComfyUI 的 prompt_id（读 <视频>.h3.json，有就用）。"""
    import json as _j
    import os as _o

    log = scene.get("video_prompt_log") if isinstance(scene, dict) else None
    if not isinstance(log, list) or not path:
        return
    ent = next((e for e in reversed(log) if isinstance(e, dict) and not e.get("file")), None)
    if ent is None:
        return
    ent["file"] = _o.path.basename(path)
    try:
        with open(str(path) + ".h3.json", encoding="utf-8") as f:
            side = _j.load(f)
        for k in ("prompt_id", "seed", "images", "seconds"):
            if k in side:
                ent[k] = side[k]
    except Exception:  # noqa: BLE001
        pass


def build_cast_fix_prompt(scene: dict, actor_rows: list, visual_style: str = "", fyi: str = "", text: str = "keep") -> str:
    """t197u: 图片修改 · 补全/修正人物。图 1 = 当前场景图，后面是每位人物的肖像图（actor_rows 的 image_no）。
    按场景描述（visual）和讲话（speaking，<1>/<2> → 人物1/人物2）检查图里的人：缺的补上，错的按肖像和描述改正；
    构图、背景、光线、画风、比例不动，不加多余的人。"""
    import re

    sc = scene if isinstance(scene, dict) else {}
    visual = str(sc.get("visual") or "").strip()
    speaking = str(sc.get("speaking") or "").strip()
    rows = [dict(r, name=str(r.get("name") or "").split("/")[-1].strip() or r.get("name")) for r in (actor_rows or []) if isinstance(r, dict)]
    by_no = {}
    for r in rows:
        m = re.search(r"(\d+)", str(r.get("label") or ""))
        if m:
            by_no.setdefault(m.group(1), r)

    def _who(n: str) -> str:
        r = by_no.get(n)
        return f"{r.get('label')} ({r.get('name')})" if r else f"人物{n}"

    speak = re.sub(r"<(\d+)>\s*", lambda m: "\n" + _who(m.group(1)) + ": ", speaking).strip()
    cast = [f"- {r.get('label')} = {r.get('name')}: reference portrait is Image {r.get('image_no')}" for r in rows]
    n = len(rows)
    parts = [
        "TASK: Fix the characters in Image 1 (the current scene image). Edit Image 1; do not draw a new picture.",
        "Image 1 = the scene image to correct. The other images are character reference portraits:\n" + "\n".join(cast),
        f"The scene must contain exactly these {n} character(s), no more and no fewer:\n"
        + "\n".join(f"- {r.get('label')} ({r.get('name')})" for r in rows),
    ]
    if visual:
        parts.append("SCENE DESCRIPTION (what happens, who is where, actions and interaction):\n" + visual)
    if speak:
        parts.append("SPOKEN LINES (heard, never drawn; only to understand who talks and the mood):\n" + speak)
    parts.append(
        "CHECK Image 1 against the scene description and the spoken lines, then:\n"
        "1. If a character is missing, add them into the scene, matching their reference portrait (face, age, hair, "
        "build, clothing) and the action / position / interaction given in the description.\n"
        "2. If a character is wrong (wrong identity or face, wrong clothing, wrong pose, wrong action or interaction), "
        "correct them to match their reference portrait and the description.\n"
        "3. Characters that are already correct stay as they are.\n"
        "4. Keep the composition, camera angle, background, props, lighting, color and art style of Image 1, "
        + ("including any words already drawn in it. " if text == "keep" else
           "except speech bubbles, balloons, caption boxes and any text, which are not part of the scene. ") +
        "Added or corrected people must have correct, natural proportions and scale relative to the room and to each "
        "other, consistent perspective and lighting, and must blend in seamlessly.\n"
        "5. Do not add any other people (no extra children, passers-by, background figures or reflections of people). "
        + ("Do not add any text, captions or watermarks, except the background keywords described below.\n" if text == "keywords"
           else "Do not add text, captions or watermarks.\n") +
        "6. The reference portraits only define how each character looks; do not copy their backgrounds or framing."
    )
    # t200u: 说明文字选项和别的图片修改路径用同一段规则；对话泡泡一律不画
    if text != "keep":
        parts.append(REMOVE_BUBBLES_EN + "\n" + REMOVE_BUBBLES_ZH)
    parts.append("TEXT IN THE PICTURE (说明文字):\n" + flow_caption_rule(text or "keep"))
    parts.append(NO_BUBBLE_EN + "\n" + NO_BUBBLE_ZH)
    if visual_style:
        parts.append(f"Art style: keep the style of Image 1 ({visual_style}).")
    if fyi:
        parts.insert(0, "IMPORTANT NOTE FROM THE USER: " + fyi)
    return "\n\n".join(parts)
