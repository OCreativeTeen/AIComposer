import json
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
** If only the narrator speaks, ``actor`` is exactly ``讲员：名字`` and there is no 人物. Mood, gesture, and camera direction are not people. Paint the narrator. ``speaking`` still must not become words on the image.
"""

NOTEBOOKLM_IMAGE_SLIDESHOW_INSTRUCTION = """
** Slideshow mode: exactly 1 image = 1 scene (one frozen moment per scene entry).
** Use ``show_this_content`` (+ Visual_Style) as painting direction. All JSON field values = staging cues, NOT text to render on the image.
** Output = one clean illustration per scene: environment + protagonist emotion + action + lighting tell the story visually.
** NEVER add onto the image: subtitles, caption paragraphs, small annotations, spreadsheet labels, or busy speech bubbles.
** If VERY CRITICAL highlighted info (very short) is ABSOLUTELY necessary, show as huge sparse background text only (transparent-like font).
** Read the row as one comic-strip frame: the picture shows what happens in that scene, including a change of angle or an action already written in ``visual``.
** Two or more story people and no ``讲员``: no host. First person is ``speaking``, second person is ``voiceover``. Sketch both. Do not write the lines.
** One story person and ``讲员：look``: paint that host while ``voiceover`` plays. Do not write ``speaking``.
** If the line is only the story person, do not invent a host in the frame.
** ``actor`` is only ``讲员：look``: the frame is the host. No second voice.
"""

NOTEBOOKLM_IMAGE_SINGLE_INSTRUCTION = """
** Single-image mode: exactly ONE image for the entire Scene_Content block (all scenes combined into one master composition).
** Summarize the full story arc in one cinematic still: setting, protagonist, emotional through-line, and key motifs from every scene.
** Show emotional progression through expression, pose, symbolic props, and composition — NOT through written paragraphs on the image.
** Keep the same Visual_Style and consistent character look across the composite.
"""

NOTEBOOKLM_SLIDESHOW_IMAGE_INSTRUCTION = NOTEBOOKLM_IMAGE_SLIDESHOW_INSTRUCTION

SLIDE_FLOW_TARGET_CHOICES = (
    ("single", "单图"),
    ("slideshow", "幻灯片"),
)
SLIDE_FLOW_TEXT_CHOICES = (
    ("none", "不加"),
    ("keywords", "背景关键字"),
)


def slide_flow_choice_label(target: str, text: str) -> str:
    """把幻灯目标和对画面文字的选择写成一行。"""
    target_label = dict(SLIDE_FLOW_TARGET_CHOICES).get(target, target)
    text_label = "背景关键字" if text == "keywords" else "不加文字"
    return f"{target_label} · {text_label}"


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
) -> str:
    """按单图或幻灯片、以及画面上的字，组装这一次的幻灯提示词。"""
    if target not in {k for k, _ in SLIDE_FLOW_TARGET_CHOICES}:
        target = "slideshow"
    if text not in {k for k, _ in SLIDE_FLOW_TEXT_CHOICES}:
        text = "none"
    style = (visual_style or "").strip() or "realistic"
    variant = "single" if target == "single" else "slideshow"
    scenes = scene_content if isinstance(scene_content, list) else []
    json_content = json.dumps(
        scene_payload_for_notebooklm_export(scenes, "image", variant),
        ensure_ascii=False,
        indent=2,
    )
    lines = [
        "You generate pictures, not a written report and not a page of text.",
        f"Visual style for every picture: {style}.",
        "The same person keeps the same face and the same clothes.",
    ]
    if target == "single":
        lines.extend([
            "Make exactly one picture for this whole story.",
            "Every scene belongs in this one picture. Do not make a row of panels. Do not make one picture per scene.",
            "Show the story through the place, the people, their faces, their poses, and a few objects that carry the story.",
            "Read each scene's show_this_content as what must be visible somewhere in this one picture.",
        ])
    else:
        lines.extend([
            "Make exactly one picture for each scene. One scene is one frozen moment.",
            "The number of pictures equals the number of scenes. Do not merge two scenes into one picture. Do not split one scene into two.",
            "Paint what that scene's show_this_content describes: the place, the emotion, the action, and the light.",
            "A change of angle or an action already written there belongs in that picture.",
            "Two or more story people and no 讲员: draw those people. Do not add a host.",
            "One story person and a 讲员: paint that host with them.",
            "Only a story person: do not invent a host.",
            "Only a 讲员: the picture is that host.",
        ])
    host = (host_narrator or "").strip()
    if host:
        lines.append(
            f"A host was chosen: {host}. When a scene has only this host, show this host. Do not add another person for that scene."
        )
    else:
        lines.append("No host was chosen. Do not add a visible host.")
    look = (main_character or "").strip()
    if look:
        lines.append(f"Keep this cast readable and consistent: {look}.")
    lines.append("Faces, posture, and gesture match the feeling of the scene.")
    if text == "keywords":
        lines.extend([
            "Do not add captions, subtitles, or speech bubbles.",
            "If one very short phrase is essential, place it as large sparse lettering in the background, behind the people.",
            "One word or a few words. Never a sentence. Never a paragraph.",
        ])
    else:
        lines.extend([
            "Do not put words on the picture. No subtitle, no caption, no annotation, no speech bubble, no background writing.",
            "Spoken lines tell you the mood and the body. They are not text to draw.",
        ])
    phrase = setting_place_phrase(region, era)
    if phrase:
        lines.append(
            f"Place and period: {phrase}. "
            "Clothing, buildings, streets, objects, and faces must belong to this place and this time."
        )
    lines.extend(["", ACTOR_AGE_LOOK])
    parts = {
        "Visual_Style": style,
        "Slide_choices": slide_flow_choice_label(target, text),
        "Instruction_for_image": "\n".join(lines),
        "Story_Scene_Content": json_content,
    }
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())

# 图片变换：先选地域，时代只列出这一地域里的项。值为 (界面名, 写进提示词的英文)。
SETTING_PLACES: dict[str, dict] = {
    "中国": {
        "en": "China",
        "eras": [
            ("唐朝", "the Tang dynasty"),
            ("宋朝", "the Song dynasty"),
            ("明朝", "the Ming dynasty"),
            ("清朝", "the Qing dynasty"),
            ("民国", "Republican China"),
        ],
    },
    "日本": {
        "en": "Japan",
        "eras": [
            ("平安时代", "the Heian period"),
            ("江户时代", "the Edo period"),
            ("明治时代", "the Meiji period"),
        ],
    },
    "欧洲": {
        "en": "Europe",
        "eras": [
            ("古希腊", "ancient Greece"),
            ("罗马帝国", "the Roman Empire"),
            ("中世纪", "the Middle Ages"),
            ("文艺复兴", "the Renaissance"),
        ],
    },
    "埃及": {
        "en": "Egypt",
        "eras": [("古埃及", "ancient Egypt")],
    },
    "非洲": {
        "en": "Africa",
        "eras": [("原始部落", "a traditional tribal setting, before modern cities")],
    },
    "中东": {
        "en": "the Middle East",
        "eras": [
            ("古巴比伦", "ancient Babylon"),
            ("阿拉伯帝国", "the early Arab empires"),
        ],
    },
    "印度": {
        "en": "India",
        "eras": [
            ("孔雀王朝", "the Maurya period"),
            ("莫卧儿帝国", "the Mughal Empire"),
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
** Age band is kids, youth, teenager, mature, or senior. Example: woman/mature/chinese/封氏. Without a name: woman/mature/chinese.
** There is no age number. The face and the body must look that age band.
""".strip()


def _with_picture_character_refs(text: str) -> str:
    return text.rstrip() + "\n\n" + PICTURE_CHARACTER_REF_NOTE + "\n\n" + ACTOR_AGE_LOOK


PICTURE_FLOW_TASK_CHOICES = (
    ("keep", "保持画风"),
    ("restyle", "转成项目风格"),
    ("extract", "人物提取"),
)
PICTURE_FLOW_TEXT_CHOICES = (
    ("keep", "保留"),
    ("remove", "去掉"),
)


def picture_flow_choice_label(task: str, text: str, visual_style: str = "") -> str:
    """把图片处理的选择写成一行。人物提取不带说明文字。"""
    if task == "extract":
        return "人物提取"
    task_label = dict(PICTURE_FLOW_TASK_CHOICES).get(task, task)
    text_label = "去掉说明文字" if text == "remove" else "保留说明文字"
    label = f"{task_label} · {text_label}"
    style = (visual_style or "").strip()
    if style:
        label = f"{label} · {style}"
    return label


def _picture_flow_text_rule(remove_text: bool) -> str:
    if remove_text:
        return (
            "Remove the explanation text. "
            "Story pictures and comic pages often have captions beside the picture, under it, or in a box, "
            "telling what the scene means or which part of the story this is. "
            "Those words are not part of the drawing. Remove them. "
            "Fill those areas with the picture that belongs there: paper, sky, wall, ground, or the rest of the illustration. "
            "Do not leave empty boxes. Do not redraw the story."
        )
    return "Keep any words already drawn in the picture. They stay part of the picture."


def _picture_flow_refs() -> str:
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


def build_picture_flow_prompt(
    *,
    task: str,
    text: str,
    visual_style: str = "",
    region: str = "",
    era: str = "",
) -> str:
    """按画风处理和说明文字，组装这一次的图片提示词。人物提取用固定提示。"""
    if task not in {k for k, _ in PICTURE_FLOW_TASK_CHOICES}:
        task = "keep"
    if text not in {k for k, _ in PICTURE_FLOW_TEXT_CHOICES}:
        text = "keep"
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
        lines = [
            "Make one still picture from the attached picture.",
            "Keep the same composition, the same people, the same action, and the same story moment.",
            "Do not add people. Do not change who is doing what.",
            "Do not keep the original drawing style.",
            f"Restyle the whole picture into this target style: {style}.",
            "Faces, clothes, the place, and the objects all take that style. The story in the picture stays the same.",
            _picture_flow_text_rule(text == "remove"),
        ]
        if phrase:
            lines.append(
                f"Place and period: {phrase}. "
                "Clothing, buildings, streets, objects, and faces must belong to this place and this time."
            )
        lines.extend(["", _picture_flow_refs()])
        body = "\n".join(lines)
        label = picture_flow_choice_label("restyle", text, style)
    else:
        lines = [
            "Make one still picture from the attached picture.",
            "Keep the same composition, the same people, the same action, and the same story moment.",
            "Do not add people. Do not change who is doing what.",
            "Keep the original painting style. "
            "If the picture is Chinese watercolor, it stays Chinese watercolor. "
            "If it is gouache, it stays gouache. "
            "If it is ink, color painting, or another hand-drawn style, that same style remains.",
            "Color the picture more fully.",
            f"Shift only a little toward this project style: {style}.",
            "The original style is still what you see. This is not a full change into that style.",
            _picture_flow_text_rule(text == "remove"),
        ]
        if phrase:
            lines.append(
                f"Place and period: {phrase}. "
                "Clothing, buildings, streets, objects, and faces must belong to this place and this time."
            )
        lines.extend(["", _picture_flow_refs()])
        body = "\n".join(lines)
        label = picture_flow_choice_label("keep", text, style)
    return f"Picture_choices:\n{label}\n\nInstruction_for_image:\n{body}"


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
    return {
        "speaking": (scene.get("speaking") or "").strip(),
        "voiceover": (scene.get("voiceover") or "").strip(),
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
    first = active[0]
    second = active[1] if len(active) > 1 else None

    def who(row: dict) -> str:
        role = "讲员" if row.get("role") == "host" else (row.get("label") or "人物")
        body = (row.get("body") or "").strip()
        return f"{role}（{body}）"

    def tone(row: dict) -> str:
        if row.get("role") == "host":
            return "用讲员的旁白口吻，第三人称讲述这场看到的事"
        return "用这个人自己的口气说话"

    slots = [f"第1个是 {who(first)}。speaking 由这个人说，{tone(first)}。"]
    if second:
        slots.append(f"第2个是 {who(second)}。voiceover 由这个人说，{tone(second)}。")
        if kind == "dialogue":
            slots.append("这两个人在对话：第二个人回应第一个人。这场没有讲员。")
        elif kind == "person_then_narrator":
            slots.append("voiceover 是旁白，解说这场，不要把 speaking 里的话再念一遍。")
        elif kind == "narrator_then_person":
            slots.append("speaking 先把这场讲清楚，voiceover 里的人再回应。")
    else:
        slots.append("只有这一个人。voiceover 写成空字符串。")

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
        "只调整 speaking 和 voiceover，使它们和当前这场 actor 的位置一致。",
        "第1个出场的人说 speaking。有第2个人时，第2个说 voiceover。没有第2个人时，voiceover 为空。",
        "仍然只有这两句。可以一来一往，把要说的事都放进这两句里。",
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
            "speaking 和 voiceover 加在一起，用大约 10 到 12 秒说完。不要超过 12 秒。",
            "10 秒能说完就不要写到 12 秒。",
            "现在的话如果读起来超过 12 秒，就压缩大约两成，只留下这场必须说的事。",
            "现在的话如果太短、几秒就说完，就按这个场景的背景再补一点，让它接近 10 秒。仍然不要超过 12 秒。",
            "补的内容从本场、前一场、后一场已经写出的事里来。不要另编这场没有的情节。",
            "前一场和后一场只作参考。这一场的话要承上启下，接得上刚才发生的事，也通向接下来的事。",
            "不要改写前一场和后一场，也不要把它们的整段情节搬进这一场。",
            "旁白也这样做：承接上一场，通向下一场，并把人物的身份和关系说清楚。",
        ])
    elif span == 2:
        lines[0:0] = [
            "把当前这场和紧接着的下一场合成一段对话，写入当前这场的 speaking 和 voiceover。",
            "两场里已经写出的事都要说到，按原来的先后，连成一来一往。",
            "前一场只用来接上刚才的事。再下一场只用来通向后面的事。这两场的整段情节不要搬进对话。",
        ]
        lines.extend([
            "speaking 和 voiceover 加在一起，用大约 16 到 20 秒说完这两场。不要超过 22 秒。",
            "两场的话如果太长，就压到这个时长里，两场的关键事仍要留下。",
            "两场的话如果太短，就按这两场已经写出的情景补到接近 16 秒。不要另编没有的情节。",
        ])
    else:
        lines[0:0] = [
            "把当前这场、下一场、再下一场这三场合成一段对话，写入当前这场的 speaking 和 voiceover。",
            "三场里已经写出的事都要说到，按原来的先后，连成一来一往。",
            "前一场只用来接上刚才的事。三场之后的那场只用来通向后面的事。这两场的整段情节不要搬进对话。",
        ]
        lines.extend([
            "speaking 和 voiceover 加在一起，用大约 22 到 28 秒说完这三场。不要超过 30 秒。",
            "三场的话如果太长，就压到这个时长里，三场的关键事仍要留下。",
            "三场的话如果太短，就按这三场已经写出的情景补到接近 22 秒。不要另编没有的情节。",
        ])
    lines.extend(["", *slots, "", "只返回一个 JSON 对象，键只有 speaking 和 voiceover。不要解释。", ""])
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


def _image_painting_direction(scene: dict) -> str:
    parts: list[str] = []
    vis = (scene.get("visual") or scene.get("story") or "").strip()
    actor = (scene.get("actor") or "").strip()
    speaking = (scene.get("speaking") or "").strip()
    caption = (scene.get("caption") or "").strip()
    if caption:
        parts.append(f"Scene title: {caption}")
    if vis:
        parts.append(f"Scene visual: {vis}")
    if actor:
        parts.append(f"Character (actor): {actor}")
    if speaking:
        parts.append(
            "Emotion/subtext from speaking (paint in face, eyes, posture, gesture — NOT as on-image text): "
            + speaking
        )
    voiceover = (scene.get("voiceover") or "").strip()
    if voiceover:
        parts.append(
            "Voiceover (second person if actor lists two or more; "
            "if only one actor, inner thought or the host — see the slideshow instruction): "
            + voiceover
        )
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
    scenes: list, mode: str, variant: str = "", narrator: str = ""
) -> list[dict]:
    """按 NotebookLM 导出模式裁剪 scene JSON。"""
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
        painting = _image_painting_direction(new_scene)
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
** A 讲员 with a plain white picture stays off screen. No mouth in the scene moves for that commentary.
** A 讲员 with a real portrait enters, says only that commentary, then leaves. Face and clothes match the portrait.
** If neither entry is 讲员, nobody speaks. Action, expression, and place sounds only.
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


def video_flow_choice_label(frames: str, background: str, evolve: str) -> str:
    """把三组选择写成一行，供窗口标题和提示词开头使用。"""
    frame_label = dict(VIDEO_FLOW_FRAME_CHOICES).get(frames, frames)
    bg_label = dict(VIDEO_FLOW_BACKGROUND_CHOICES).get(background, background)
    parts = [frame_label, bg_label]
    if frames != "two":
        evolve_label = dict(VIDEO_FLOW_EVOLVE_CHOICES).get(evolve, evolve)
        parts.append(evolve_label)
    return " · ".join(parts)


def _video_flow_instruction(frames: str, background: str, evolve: str, visual_style: str) -> str:
    """按这一次的画面、背景、演进选择，只写用得上的那几段。"""
    style = (visual_style or "").strip() or "realistic"
    chunks: list[str] = []
    if frames == "two":
        chunks.append(
            """** Picture 1 is the opening frame. Picture 2 is the ending frame.
** Move from picture 1 to picture 2. The audience sees the start, the change, and the end.
** Carry that change with action, facial expression, and the place itself.
** Picture 1's look is the start. Picture 2's look is the end. Do not invent another visual style between them.
** Pictures after picture 2, if any are pasted, are actor references in ``actor`` order, skipping 不出现.
** A 人物 reference only shows who is already in these frames. Do not walk a 人物 in or out."""
        )
    else:
        chunks.append(
            """** One scene picture is attached. Picture 1 is the only scene. Keep the same place and the same people.
** Pictures after picture 1, if any are pasted, are actor references in ``actor`` order, skipping 不出现.
** A 人物 reference only shows who is already in picture 1. Do not walk a 人物 in or out."""
        )
        if evolve == "to_style":
            chunks.append(
                f"""** Open on picture 1 and hold its original style long enough to read it.
** Then slowly change that look into the target visual style: {style}.
** The audience must see the change. Show the starting look, a halfway look, and the finished {style}. Do not jump. Do not finish the change in a flash.
** No page turn, no dissolve trick, no wipe, no flash. The picture itself changes.
** Same people, same place, recognizable at every moment.
** A 讲员 commentary may play while the style is still changing."""
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
    chunks.append(NOTEBOOKLM_VIDEO_ACT_SPEECH.strip())
    if background == "art_text":
        chunks.append(
            """** In the deep background, behind the people, place a few artistic words. They belong to the picture, not to a subtitle bar.
** Take only the shortest keywords from ``speaking`` and ``voiceover``. A word or a short phrase. Never a sentence. Never a paragraph.
** Draw the letters in a hand that fits the picture. Do not cover faces.
** Do not turn the spoken lines into captions."""
        )
    elif background == "bubble":
        chunks.append(
            """** A small thought bubble may appear, as if a person is thinking. One bubble at a time.
** The bubble holds a keyword or a very short phrase from ``speaking`` or ``voiceover``. It sits near that person and does not cover the face.
** It is not a subtitle bar and not a paragraph. If there is no short phrase to think, show no bubble."""
        )
    else:
        chunks.append(
            """** Do not put words on the picture. No background writing, no thought bubble, no subtitle, no title card.
** ``speaking`` and ``voiceover`` are not text to draw."""
        )
    chunks.append(NOTEBOOKLM_VIDEO_NO_MUSIC.strip())
    return "\n".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())


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
    age = project_manager._ACTOR_AGE.get(bits[1].lower(), bits[1].lower()) if len(bits) >= 2 else ""
    age = _VOICE_AGE_BAND.get(age, "")
    race = bits[2].lower() if len(bits) >= 3 else ""
    if race not in ("chinese", "english"):
        race = ""
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


def build_video_flow_prompt(
    *,
    frames: str,
    background: str,
    evolve: str,
    visual_style: str,
    scene_content: list,
    language: str = "",
    host_narrator: str = "",
) -> str:
    """按画面数量、背景文字、单画面演进，组装这一次的视频提示词。"""
    if frames not in {k for k, _ in VIDEO_FLOW_FRAME_CHOICES}:
        frames = "one"
    if background not in {k for k, _ in VIDEO_FLOW_BACKGROUND_CHOICES}:
        background = "none"
    if evolve not in {k for k, _ in VIDEO_FLOW_EVOLVE_CHOICES}:
        evolve = "keep"
    if frames == "two":
        evolve = "keep"
    style = (visual_style or "").strip() or "realistic"
    variant = "act_two" if frames == "two" else "act_one"
    scenes = scene_content if isinstance(scene_content, list) else []
    json_content = json.dumps(
        scene_payload_for_notebooklm_export(scenes, "video", variant, narrator=host_narrator),
        ensure_ascii=False,
        indent=2,
    )
    instruction = _video_flow_instruction(frames, background, evolve, style)
    voices = speaking_voice_lines(scenes)
    lang_note = _audio_language_instruction(language)
    audio = "\n".join(
        part
        for part in (NOTEBOOKLM_VOICE_MATCH.strip(), voices, instruction, lang_note)
        if part
    )
    video = "\n".join(
        part
        for part in (NOTEBOOKLM_VOICE_MATCH.strip(), voices, ACTOR_AGE_LOOK.strip(), instruction)
        if part
    )
    parts = {
        "Visual_Style": style,
        "Video_choices": video_flow_choice_label(frames, background, evolve),
        "Instruction_for_video_generation": video,
        "Instruction_for_audio_generation": audio,
        "Story_Scene_Content": json_content,
    }
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())


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
) -> str:
    """过渡场景的视频提示。普通场景仍用 ``build_video_flow_prompt``。"""
    style = (visual_style or "").strip() or "realistic"
    chosen = transition if isinstance(transition, dict) else {}
    scenes = scene_content if isinstance(scene_content, list) else []
    json_content = json.dumps(
        scene_payload_for_notebooklm_export(scenes, "video", "act_two", narrator=host_narrator),
        ensure_ascii=False,
        indent=2,
    )
    instruction = _transition_video_instruction(chosen, style)
    voices = speaking_voice_lines(scenes)
    lang_note = _audio_language_instruction(language)
    audio = "\n".join(
        part
        for part in (NOTEBOOKLM_VOICE_MATCH.strip(), voices, instruction, lang_note)
        if part
    )
    video = "\n".join(
        part
        for part in (NOTEBOOKLM_VOICE_MATCH.strip(), voices, ACTOR_AGE_LOOK.strip(), instruction)
        if part
    )
    choice_lines = _transition_video_choice_lines(chosen)
    parts = {
        "Visual_Style": style,
        "Video_choices": "过渡 · 起始画面到终止画面",
        "Transition_choices": choice_lines or "（这场没有记下选择）",
        "Instruction_for_video_generation": video,
        "Instruction_for_audio_generation": audio,
        "Story_Scene_Content": json_content,
    }
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())


NOTEBOOKLM_VIDEO_NO_MUSIC = """
** No music in this clip. No score, no song, no melody, no background music, no musical sting, no mood track.
** Music for the finished film is added later, across the whole piece. A music bed inside one scene cannot be taken out.
** Sound effects that belong to this place are welcome: birds, wind, rain, water, footsteps, a door, a cup set down, cloth, leaves, a street, a room.
** Keep those effects under the voices. Do not turn them into a tune.
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

DIRECT_STEP_1_IMAGE = DIRECT_STEP_IMAGE_CORE.replace("###STEP###", "1")
DIRECT_STEP_2_IMAGE = DIRECT_STEP_IMAGE_CORE.replace("###STEP###", "2")
DIRECT_STEP_3_IMAGE = DIRECT_STEP_IMAGE_CORE.replace("###STEP###", "3")
DIRECT_STEP_4_IMAGE = DIRECT_STEP_IMAGE_CORE.replace("###STEP###", "4")


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
** On screen or off screen, a woman is never given a male voice.
** Age band is kids, youth, teenager, mature, or senior, the word after woman or man. Otherwise adult. Ethnicity is chinese or english, the word after the age band. A name, when present, is last and is not the voice.
** When a voice name is written for speaking or voiceover, that line uses that commercial voice. Do not substitute another.
"""


def _audio_language_instruction(language: str) -> str:
    import config

    label = config.audio_language_label(language)
    if not label:
        return ""
    return (
        f"** Audio / spoken language: {label}.\n"
        f"** All lip-sync dialogue, protagonist ``speaking`` lines, and "
        f"narrator/host ``voiceover`` MUST be delivered in {label}."
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
                    f"In a one-actor scene, show this host speaking the voiceover."
                )
            else:
                parts["Host_for_this_run"] = (
                    "No host was chosen. Do not add a visible host. "
                    "A one-actor voiceover is that person's inner thought."
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
        * Speaker-info: both 'actor' & 'narrator' have avatar description like 'gender/age/race' (i.e, 'woman/young/chinese'), find the right voice / avatar accordingly by 'gender, age, race'.
        * Narrator talking-avatar location : 'narrator' has how-to-show-in-screen info behind '|' (i.e, woman/young/chinese | speaking-at-image-right), this help to find out where is the talking-avatar in the screen.
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


IMAGE_DESCRIPTION_SYSTEM_PROMPT = """
You are a professional expert who is good at analyzing & describing the image (attached in the user-prompt) as a Scene, in English.

Please give details (Visual-Summary / camera-scene, and sound-effects) as below (FYI, don't use doubel-quotes & newlines in the values at all !):

		** subject (detailed description of all speakers (gender/age/background/key features)  ~~ not including any narrator  ~~~ in original language)
        ** visual_image (The dense, detailed text description of the scene's visual content ~~ Excluding any narrator info  ~~~ in original language)
		** person_action (detailed description of the speakers' actions (reactions/mood/interactions), and visual expression ~~~ in original language)
		** era_time (the time setting, including the historical era, season, time of day, and weather conditions  ~~~ in English)
        ** environment (detailed description of the setting, including architecture, terrain, specific buildings, streets, market.   ~~~ in English)
        ** sound_effect (Specific ambient sounds, sound effects, music cues for the scene [like heavy-rain, wind-blowing, birds-chirping, hand-tap, market-noise, etc. ~~~ in English])
		** cinematography (Detailed directorial cues covering camera motion, shot scale, lighting, and lens choices. (NOT for the narrator!)  ~~~ in English)

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !

-------------------------------
The response format: json dictionary
like:

    {{
        "subject": "白蛇：身长五十尺，鳞片泛着珍珠般的光泽，眼神忧郁。徐明州：浑身湿透，满脸泥泞，一副惊恐万分的样子。",
        "visual_image": "史诗级灾难场景：洪水摧毁城市，夜幕降临，一条巨大的白色巨蛇从水中升起，鳞片闪闪发光，一个矮小的男子蜷缩在屋顶上，暴雨倾盆。",
        "person_action": "巨蟒用鼻子轻轻地把明州推到屋顶上。明州惊恐地向后爬去，发出尖叫。",
        "era_time": "1000 BC, ancient time; late summer afternoon; dry air and blazing sun",
        "environment": "Vineyard hills north of Jerusalem; rows of vines stretch across sun-baked slopes where olive trees shimmer in heat haze, distant stone cottages dot the ridgeline.",
        "sound_effect": "crickets-chirping, gentle breeze through vines",
        "cinematography": {{
            "camera_movement": "The camera begins with a medium-wide shot sweeping through the vineyard. It glides forward along the rows, finally rising in a low angle toward the woman’s weary face, sunlight filtering through vine leaves in warm amber tones.",
            "lighting_style": "dust floating in the golden light",
            "lens_type": "Standard 50mm"
        }}
    }}
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



COMBO_ANALYZE_SURVEY_PROMPT = """
You are a senior psychological counselor writing ONE finished analysis in {language}.
The user prompt numbers several source notes. The report must read as one continuous piece about one matter. It must also stay thick: the scenes, relationships, and analytical detail in those notes are the body of the piece, not raw material to be shortened.

Write as a counselor opening a case discussion, not as a literary essay and not as notes stitched together.
The first sentences name the psychological problem in professional, ordinary language: what keeps happening, in what kind of relationship or life, and why it matters. Do not open inside a scene. Do not open with a contrast such as "这不是某一次争吵，也不是谁变了心".
Then take the problem apart step by step: how it starts, what maintains it, what it costs.
Only after that, show it in the concrete lives from the notes. Those lives illustrate the problem. They are not separate chapters pasted in order.
End as a counselor would close: what this problem asks for, and how a response can begin. The ending belongs to the problem, not to the last scene.

Do not say "case 1", "the second source", "another facet", or "a different story". Do not number the situations.

Keep the life in the notes:
- Carry over concrete people, rooms, dialogues, repeated behaviors, and the specific observations already made. A situation that took a page in the note should still be felt on the page here, not reduced to one sentence of "in this situation, the person does X".
- Do not compress. Length should follow the useful detail you kept. Cutting duplicate sentences is allowed. Cutting a scene, a turn in a relationship, or an insight down to a label is not.
- Where the notes share a thread, state it once and let the detailed situations show it. Where they differ, write the difference as another fully described moment of the same matter, not as a new essay that starts over.
- Keep every source. Do not drop one because it fits loosely. Do not invent one hidden cause just to glue them. If a shared problem is really there, name it once in ordinary professional language, then let the situations carry it.
- You may add sensory and behavioral detail that makes an existing scene clearer, as long as it stays inside what that note already showed. Do not invent a new person or a new event.
- End with one closing for the whole piece: what this matter comes to, and what kind of response fits. The close is not a recap of each note.
- Do not add a diagnosis none of the notes stated.
- Do not write scene scripts. Do not mention that the text was combined.
- In title and analyzed_content, never use the words 根, 根儿, 病根, or "root". Say the basic problem, the repeating pattern, or the core conflict in words a reader already uses. Do not repeat that phrase in every paragraph.

Output JSON only. Source numbers appear only in kept_indexes, never inside analyzed_content.
{{
  "title": "a short title in {language} for the one matter",
  "analyzed_content": "the full report in {language}: one essay, with the original situations still told in detail",
  "kept_indexes": [1, 2, 3],
  "ignored": []
}}
"""


COMBO_ANALYZE_ROOT_PROMPT = """
You are a senior psychological counselor writing ONE finished analysis in {language}.
The user prompt numbers several cases. Decide whether most of them are driven by the same basic problem: one repeating pattern or core conflict, not a shared headline.

Use only the cases that share that problem. Leave out cases that sit too far away. Do not pull them in to look complete. If only a minority share it, write about that minority. If they do not share one problem, say so in analyzed_content and leave kept_indexes empty. Do not invent one.

Write as a counselor presenting one common psychological problem, then taking it apart. Not as a literary opening, and not as several stories placed side by side.
Open by naming the problem the way you would begin a case seminar: what this difficulty is, where it usually appears, and what is actually going on. The first sentences must not drop the reader into a marriage scene, and must not start with "不是某一次争吵，也不是谁变了心" or any similar contrast.
Then unpack it in order: how the pattern gets started, what keeps it going, what it costs the person and the relationship.
Then show that problem inside the concrete lives from the kept notes. Each life is evidence and illustration, told with its original detail, still inside the same discussion.
Close by saying how to work with this problem, step by step, including how the work looks different in those different lives. The close is the counselor's conclusion, not a last anecdote.

Do not turn each situation into "this condition produces that result".

The reader must feel each situation, more fully than a summary:
- For every kept case, write how this problem is actually lived: the people, the room, what is said and avoided, the repeated move, and the cost. Keep the detail and the analysis already in that note.
- You may add detail that makes those existing scenes sharper and more visible, when it follows from what the note already showed. Do not invent a new person or a new event.
- Do not compress a case into "under this condition, it appears as X". If the note dwelt on a marriage, a parent, a night, a work habit, those beats stay, and may be written more fully.
- Do not say "case 1", "source 3", or "another client". One situation follows another as further life of the same problem, inside one account.
- Then say what would actually change it. The response may look different in each situation, and those differences should be as concrete as the situations.
- Close on that response for the whole piece. Do not end by summarizing each case in a sentence.
- Do not add a diagnosis none of the kept cases stated.
- Do not write scene scripts. Do not mention that cases were selected or discarded.
- In title and analyzed_content, never use 根, 根儿, 病根, or "root". Do not repeat one keyword in every paragraph.

Output JSON only. Indexes stay in kept_indexes and ignored. They must not appear in title or analyzed_content.
{{
  "title": "a short title in {language} that names the one matter, without the word 根",
  "analyzed_content": "the report in {language}: the basic problem named once, each situation told in full detail, then what addresses it",
  "kept_indexes": [1, 3, 4],
  "ignored": [{{"index": 2, "reason": "why this case does not share the problem, in {language}"}}]
}}
"""


# (按钮文字, 系统提示词)。合成项目时弹出选择，以后在这里加一项即可。
COMBO_ANALYZE_CHOICES = [
    ("综合报告", COMBO_ANALYZE_SURVEY_PROMPT),
    ("找共同病根", COMBO_ANALYZE_ROOT_PROMPT),
]


SPEAKING_SUMMARY_SYSTEM_PROMPT = """
You are a professional expert who is good at generating the Summary (in {language}) from a list of speaking content (in json format) given in 'user-prompt'.
This summary is used as youtube program description, so, at beginning, please give some youtube video tags (like #pychology #心理咨询 etc).
"""


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
    {
        "name": "歌唱",
        "prompt": "Singing with slowly body/hand movements."
    },
    {
        "name": "转镜",
        "prompt": "Camera rotates slowly."
    },
    {
        "name": "渐变",
        "prompt": "Time-lapse / change gradually along long period."
    },
    {
        "name": "动态",
        "prompt": "The still image awakens with motion: the scene stirs gently — mist drifts, light flickers softly over old textures, and shadows breathe with calm mystery. The camera moves slowly and gracefully, maintaining perfect focus and stability. A cinematic awakening filled with depth, clarity, and timeless atmosphere."
    },
    {
        "name": "轻柔",
        "prompt": "The still image awakens with motion: the scene breathes softly, touched by time. Light flows like silk, mist curls around ancient relics, and shadows shift with tender rhythm. The camera drifts slowly, preserving a serene, clear, and dreamlike atmosphere. A poetic fantasy — gentle, warm, and still."
    },
    {
        "name": "梦幻",
        "prompt": "The still image awakens with motion: colors melt like memory, and sparkles drift in slow rhythm. Light bends through haze, reflections ripple softly. The camera floats gently as if in a dream — everything clear, smooth, and luminous. A slow, poetic vision of beauty and wonder."
    },
    {
        "name": "古风",
        "prompt": "The still image awakens with motion: sunlight filters through soft mist over tiled roofs and silk curtains. Water ripples faintly, leaves stir in a slow breeze. The camera moves with calm precision, preserving clarity and fine detail. Serene, elegant, and timeless — a cinematic memory of antiquity."
    },
    {
        "name": "史诗",
        "prompt": "The still image awakens with motion: distant clouds move slowly, banners wave softly in the wind. Light shifts gently across vast landscapes. The camera glides with slow majesty, revealing grandeur in stillness. Epic yet calm — sharp, stable, and full of reverence."
    },
    {
        "name": "浪漫",
        "prompt": "The still image awakens with motion: petals drift in soft golden air, hair and fabric move gently. The camera lingers slowly between glances and reflections, every movement tender and smooth. Warm, cinematic, and crystal clear — filled with timeless love."
    },
    {
        "name": "自然",
        "prompt": "The still image awakens with motion: sunlight filters through leaves, ripples widen slowly across water, clouds drift in quiet rhythm. The camera follows gently, holding clarity and focus. Calm, organic, and cinematic — nature breathing in slow motion."
    },
    {
        "name": "科技",
        "prompt": "The still image awakens with motion: neon pulses slowly, holographic reflections ripple with light. The camera glides in controlled, slow precision — smooth and stable. A futuristic calm filled with depth, clarity, and quiet energy."
    },
    {
        "name": "灵性",
        "prompt": "The still image awakens with motion: divine light descends softly, mist stirs with sacred calm. The camera moves slowly and reverently, unveiling stillness and grace. Ethereal and luminous — a meditative vision of transcendent peace."
    },
    {
        "name": "时间流逝",
        "prompt": "The still image awakens with motion: light changes gently, shadows lengthen, and clouds drift slowly. The camera moves subtly, preserving clarity as moments flow by. A serene unfolding of time — smooth, stable, and poetic."
    },
    {
        "name": "神圣",
        "prompt": "The still image awakens with motion: golden rays descend through the mist, touching sacred symbols. The camera ascends slowly, as if carried by gentle divine wind. A clear, majestic, and tranquil revelation — cinematic holiness in stillness."
    }
]




ANIMATE_I2V = ["I2V"]
ANIMATE_2I2V = ["2I2V"]
ANIMATE_S2V = ["S2V"]
ANIMATE_WS2V = ["WS2V"]
ANIMATE_AI2V = ["AI2V"]

ANIMATE_SOURCE = ANIMATE_S2V + ANIMATE_I2V + ANIMATE_2I2V + ANIMATE_WS2V + ANIMATE_AI2V
