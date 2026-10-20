"""NotebookLM / scene prompt text builders (moved verbatim from gui/downloader.py)."""
import os
import string
import config
import config_channel
from utility.tags_text import parse_tags_list
import project_manager
from utility.file_util import _media_kind_for_path
from utility.media_probe import _media_duration_seconds
from gui.dl.youtube_dl import _youtube_row_display_title
from gui.dl.gen_video_files import _find_gen_video_webp_for_row, _item_transcript_text


def _format_nb_prompt_template(template: str, **kwargs) -> str:
    """对模板中 ``{name}`` 占位符填入 kwargs（``content`` / ``story`` / ``instruction`` 等）。"""
    names = set()
    for _, field_name, _, _ in string.Formatter().parse(template):
        if not field_name:
            continue
        names.add(field_name.split("!")[0].split(":")[0].strip())
    safe = {k: kwargs.get(k, "") for k in names}
    return template.format(**safe)


def _prompt_choice_entries(channel_key: str) -> list[tuple[str, str]]:
    cfg = config.get_channel_config(channel_key) or {}
    entries: list[tuple[str, str]] = []
    for item in cfg.get("scenes_prompt_choices") or []:
        if not item or len(item) < 2:
            continue
        lbl, tpl = item[0], item[1]
        if (tpl or "").strip():
            entries.append(((lbl or "").strip(), tpl))
    return entries


def _resolve_combined_prompt_template(
    channel_key: str,
    *,
    label: str | None = None,
    index: int = 0,
) -> tuple[str, str, int]:
    """在 ``scenes_prompt_choices`` 合并列表中解析 (label, template, index)。"""
    choices = _prompt_choice_entries(channel_key)
    if not choices:
        return ("", "", 0)
    if label:
        want = label.strip()
        for i, (lbl, tpl) in enumerate(choices):
            if (lbl or "").strip() == want:
                return (lbl, tpl, i)
    idx = max(0, min(index, len(choices) - 1))
    lbl, tpl = choices[idx]
    return lbl, tpl, idx


def _scene_entry_heading(entry: dict) -> str:
    """Scene 条目标题：``caption``。"""
    return project_manager.caption_from_scene_content_item(entry)


def _notebooklm_row_topic_fields(video_detail: dict) -> tuple[str, str, str]:
    """从列表行 / ``project_profile`` 取主题分类、子类型与 ``topic`` 字符串。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    cat = (vd.get("topic_category") or "").strip()
    sub = (vd.get("topic_subtype") or "").strip()
    prof = vd.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict):
        if not cat:
            cat = (prof.get("topic_category") or "").strip()
        if not sub:
            sub = (prof.get("topic_subtype") or "").strip()
    topic = f"{cat}-{sub}" if cat or sub else ""
    return cat, sub, topic


def _notebooklm_row_tags_text(video_detail: dict) -> str:
    vd = video_detail if isinstance(video_detail, dict) else {}
    tags_raw = vd.get("tags", "")
    if isinstance(tags_raw, list):
        return ", ".join(str(x) for x in tags_raw if str(x).strip())
    return ", ".join(parse_tags_list(str(tags_raw or "")))


def _story_cast_text(video_detail: dict):
    """STORY 窗人物栏的名单（场景 actor 同一格式）。从来没设过返回 None（走旧的讲员逻辑）。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    cast = vd.get("story_actors")
    if not isinstance(cast, str):
        prof = vd.get(project_manager.PROJECT_PROFILE_KEY)
        cast = prof.get("story_actors") if isinstance(prof, dict) else None
    return cast if isinstance(cast, str) else None


def build_cast_block(actor_text) -> str:
    """把人物栏名单写成提示词里的 CAST 段：讲员有没有、几个人物、各自的样子，按人物栏顺序。"""
    if actor_text is None:
        return "(No cast was chosen in the Story window. Use the host rules written above.)"
    rows = []
    for row in project_manager.actor_entries(actor_text or ""):
        body = (row.get("body") or "").strip()
        if not body or project_manager.actor_is_absent(body):
            continue
        rows.append(row)
    host = next((r for r in rows if r.get("role") == "host"), None)
    persons = [r for r in rows if r.get("role") != "host"]
    lines = [
        f"Narrator (讲员) present: {'YES' if host else 'NO'}",
        f"Number of characters (人物): {len(persons)}",
    ]
    if not rows:
        lines.append("Cast list: EMPTY. Nobody is chosen.")
    else:
        lines.append("Cast list, in the order the user arranged it (gender/age band/ethnicity/name):")
        n = 0
        for r in rows:
            body = project_manager.split_actor_motion(r.get("body") or "")[0]
            if r.get("role") == "host":
                lines.append(f"  - 讲员：{body}")
            else:
                n += 1
                lines.append(f"  - 人物{n}：{body}")
    lines.append(
        "Use exactly these people with exactly these looks in ``actor``. Do not invent another 讲员. "
        "Do not change anyone's gender, age band, or ethnicity. Extra minor people from the story may appear "
        "only when the material requires them, and they never replace a listed person."
    )
    return "\n    ".join(lines)


def _scene_prompt_narrator(video_detail: dict) -> str:
    """本轮已选的主持人。没选则空字符串，提示词里主持人只出声、不进画面。

    STORY 窗人物栏设过名单时只看名单：名单里没有讲员 = 空（不再退回上次的讲员）。
    """
    vd = video_detail if isinstance(video_detail, dict) else {}
    cast = _story_cast_text(vd)
    if cast is not None:
        return (project_manager.actor_host_name(cast) or "").strip()
    named = (vd.get("narrator") or "").strip()
    if named:
        return named
    return (getattr(project_manager, "LAST_NARRATOR", None) or "").strip()


def _notebooklm_prompt_context_from_video_detail(
    mgr,
    video_detail: dict,
    *,
    instruction: str = "",
) -> dict:
    """场景智能生成等共用的 NotebookLM 占位符数据源。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    cat, sub, topic = _notebooklm_row_topic_fields(vd)
    content = vd.get("analyzed_content")
    return {
        "topic": topic,
        "tags": _notebooklm_row_tags_text(vd),
        "story_title": _youtube_row_display_title(vd),
        "content": content,
        "link": (vd.get("url") or "").strip(),
        "instruction": (instruction or "").strip(),
        "language": config.llm_language_label(getattr(mgr, "language", "")),
        "category": cat,
        "subtype": sub,
        "narrator": _scene_prompt_narrator(vd),
        "cast": build_cast_block(_story_cast_text(vd)),
    }


def _build_notebooklm_prompt_for_row(
    mgr,
    video_detail: dict,
    template: str,
    *,
    instruction: str = "",
    sections: int = 1,
    topic: str = "",
    tags: str = "",
    topic_category: str = "",
    topic_subtype: str = "",
    content_override: str | None = None,
    dialogue_mode: str = "",
    visual_style: str = "",
) -> str:
    """按频道模板 + 列表行数据拼 NotebookLM / LLM 提示词（``{content}`` = analyzed_content）。

    ``visual_style``：故事窗所选画面风格（config.VISUAL_STYLE_OPTIONS），非空时写进提示词。
    """
    ctx = _notebooklm_prompt_context_from_video_detail(
        mgr, video_detail, instruction=instruction
    )
    if content_override is not None:
        ctx["content"] = (content_override or "").strip()
    if topic:
        ctx["topic"] = topic
    if tags:
        ctx["tags"] = tags
    cat = (topic_category or ctx.get("category") or "").strip()
    sub = (topic_subtype or ctx.get("subtype") or "").strip()
    prompt = _format_nb_prompt_template(
        template,
        topic=ctx.get("topic", ""),
        tags=ctx.get("tags", ""),
        language=ctx.get("language", ""),
        story_title=ctx.get("story_title", ""),
        content=ctx.get("content", ""),
        link=ctx.get("link", ""),
        instruction=ctx.get("instruction", ""),
        sections=sections,
        narrator=ctx.get("narrator", ""),
        cast=ctx.get("cast", ""),
    )
    talk = config.dialogue_mode_instruction(dialogue_mode) if dialogue_mode else ""
    if talk:
        prompt = (prompt or "").rstrip() + "\n\n" + talk + "\n"
    style_block = config_channel.visual_style_prompt_block(visual_style)
    if style_block and (visual_style or "").strip().lower() not in (prompt or "").lower():
        prompt = (prompt or "").rstrip() + "\n\n" + style_block + "\n"
    # 频道 soul：放在故事内容与模板规则之后，作为幕后视角（无 soul 目录的频道为空）
    soul_block = project_manager.build_soul_prompt_block(
        getattr(mgr, "channel", None) or mgr._channel_config_key(),
        cat,
        sub,
        language=ctx.get("language", ""),
        story_chars=len((ctx.get("content") or "").strip()),
    )
    if soul_block:
        prompt = (prompt or "").rstrip() + "\n\n\n" + soul_block + "\n"
    return prompt


def _media_length_line(path: str) -> str:
    seconds = _media_duration_seconds(path)
    if seconds <= 0:
        return ""
    n = f"{seconds:.2f}"
    return (
        f"Recording length: {n} seconds. N = {n}. "
        f"This audio or video ends at {n}. "
        f"Every start and every end must be from 0.00 to {n}, two decimal places. "
        f"The largest number in the whole array is {n}, and it is only the last scene's end. "
        f"Any start or end above {n} is wrong. Every scene needs start < end. "
        f"One scene's end is the next scene's start."
    )


def _media_source_blurb(path: str) -> str:
    kind = _media_kind_for_path(path)
    name = os.path.basename(path)
    length = _media_length_line(path)
    tail = f"\n{length}" if length else ""
    if kind == "audio":
        return (
            f"Audio file: {name}\n"
            "The content of this item is the speech in this audio file. "
            "Use what is spoken. Do not treat this as a written article or a PDF."
            + tail
        )
    if kind == "video":
        return (
            f"Video file: {name}\n"
            "The content of this item is the spoken words in this video. "
            "Use the speech. Do not use the pictures as the script."
            + tail
        )
    return ""


def _transcript_source_blurb(media_path: str, transcript_text: str) -> str:
    """有文字稿时，{content} 直接放文字稿，不再附上媒体。"""
    kind = _media_kind_for_path(media_path)
    word = "video" if kind == "video" else "audio"
    length = _media_length_line(media_path)
    tail = f"\n{length}" if length else ""
    return (
        f"{word.capitalize()} file: {os.path.basename(media_path)}\n"
        f"Below is the written transcript of the speech in this {word}. "
        "The recording itself is not attached; work from this transcript."
        + tail
        + "\n\n"
        + transcript_text
    )


def _media_material_override(video: dict, media_path: str) -> str:
    """选了媒体：有文字稿就用文字稿，没有再用媒体本身。"""
    _tpath, text = _item_transcript_text(video)
    if text:
        return _transcript_source_blurb(media_path, text)
    return _media_source_blurb(media_path)


_MEDIA_SCENE_LENGTH_NOTE = (
    "Scene size for a recording: about 30 seconds, never shorter than 15 seconds and never longer than 50 seconds. "
    "Most scenes land between 20 and 40 seconds. So a recording of N seconds has about N divided by 30 scenes: "
    "a 10-minute recording has about 20 scenes, a 20-minute recording about 40. "
    "Do not write a handful of long scenes. A podcast or a long talk is many scenes. "
    "A scene starts at the start time of its first sentence. Its end is the start time of the first sentence "
    "of the next scene, and the last scene ends at N. Its length is end minus start. "
    "Work this subtraction for every scene before you answer. A scene under 15 seconds must be joined to the "
    "neighbour whose matter is closest. A scene over 50 seconds must be split at a sentence end. "
    "Then check the scene count against N divided by 30. "
    "Never cut in the middle of a sentence. Inside the 15 to 50 second window, cut where a small point is finished, "
    "where a question has been answered, or where the matter turns. "
    "If one single sentence runs longer than 50 seconds by itself, it stays whole as its own scene. "
    "Scenes need not be equal and the ends follow the sentence times, so do not repeat round numbers "
    "such as 30.00 or 60.00 as ends. "
    "Do not mix two matters in one scene, and keep the order of the speech, "
    "so the story or the levels stay clear from one scene to the next. "
    "A recording shorter than 15 seconds is one scene. "
    "Many scenes means several episodes: the episode rules of the prompt group them, 5 to 15 scenes per episode."
)


_MEDIA_SCENE_TIMING_NOTE = (
    _MEDIA_SCENE_LENGTH_NOTE + " "
    "When this run splits the recording into more than one scene, every scene object "
    "must include \"start\" and \"end\": seconds on that file, two decimal places. "
    "0.00 is the first moment of the file. N is the Recording length of this file. "
    "Write the scenes from 0.00 up to N. Every scene needs start < end. "
    "The next scene's start equals this scene's end. The last scene's end is exactly N. "
    "Before you return the JSON, read every start and every end. "
    "If any number is greater than N, that timeline is wrong. Write it again so every "
    "number sits inside 0.00 to N. Do not put N only on the last end while earlier "
    "scenes run past N. A start of 709.00 with an end of 485.48 is wrong."
)


def _prompt_text_for_material(prompt: str, material: str) -> str:
    """按这次选中的材料，说明内容来自文字、PDF、音频里的话，还是视频里的话。"""
    if not prompt:
        return prompt
    kind = (material or "analyzed").strip().lower()
    notes = {
        "analyzed": (
            "Content source for this run: analyzed_content, the written text in Reference Content. "
            "An item may instead supply a PDF, an audio file, or a video file. "
            "If the source is audio, the content is the speech in that recording. "
            "If the source is video, the content is the spoken words in that video, not the pictures. "
            "This run uses the written analysis."
        ),
        "pdf": (
            "Content source for this run: a PDF file. Read the PDF for the pictures and any text. "
            "An item may instead supply written analyzed_content, an audio file, or a video file. "
            "If the source is audio, use the speech in the recording. "
            "If the source is video, use the spoken words, not the pictures. "
            "This run uses the PDF."
        ),
        "audio": (
            "Content source for this run: an audio file. The material is the speech in that recording. "
            "Use what is spoken. Do not treat it as a written article or a PDF. "
            "An item may instead supply written analyzed_content, a PDF, or a video whose content is its spoken words. "
            "This run uses the audio.\n"
            + _MEDIA_SCENE_TIMING_NOTE
        ),
        "video": (
            "Content source for this run: a video file. The material is the speech in that video. "
            "Use the spoken words. Do not use the pictures as the script. "
            "An item may instead supply written analyzed_content, a PDF, or an audio recording. "
            "This run uses the video.\n"
            + _MEDIA_SCENE_TIMING_NOTE
        ),
        "transcript": (
            "Content source for this run: the written transcript of an audio or video recording, "
            "given in Reference Content. The recording itself is not attached. "
            "Every media item is worked from its transcript.\n"
            "How to read the transcript:\n"
            "- Every line is one sentence. It starts with its start time [hh:mm:ss.s] "
            "(hours:minutes:seconds.tenths) on the recording.\n"
            "- A speaker mark such as <1> or <2> comes right after the time, only on the sentence where "
            "the speaker changes. A sentence without a mark is spoken by the same person as the sentence before it. "
            "The first line is always <1>. There are at most 4 speakers.\n"
            "Scenes from the transcript:\n"
            "- Group whole sentences into scenes. A scene never cuts a sentence. Every scene is about 30 seconds, "
            "never under 15 and never over 50 seconds; a recording of N seconds has about N divided by 30 scenes.\n"
            "- You know the exact start time of every sentence, so you can measure. Walk down the transcript from the "
            "start of a scene and find the sentence start that is closest to 30 seconds later, preferring a sentence end "
            "where a small point is finished or a question has been answered, inside the 15 to 50 second window. "
            "That sentence start is the next scene's start. Compute end minus start for every scene, convert times to "
            "seconds first, and fix any scene outside 15 to 50 seconds before you answer.\n"
            "- A scene's \"start\" is the start time of its first sentence. Its \"end\" is the start time of the "
            "first sentence of the next scene, so each scene's end equals the next scene's start. "
            "The first scene starts at 0.00. The last scene ends at N, the Recording length.\n"
            "- Write start and end in seconds with two decimal places: convert [hh:mm:ss.s] to seconds "
            "(for example [00:01:15.4] is 75.40). Take these numbers from the transcript times. Do not guess them.\n"
            "Speakers in the scenes:\n"
            "- Put the speaker marks into each scene's \"speaking\" using the same <N> format as this prompt's "
            "speaking field. Use the transcript's own numbers: transcript speaker <N> is written as <N>, "
            "and the same person keeps the same number in every scene.\n"
            "- Write a mark at the start of every scene's speaking for the person who says its first sentence, "
            "even when the transcript line has no mark there. Then write a new mark only where the speaker changes, "
            "at the same sentence as in the transcript.\n"
            "- The actor list of each scene follows the numbers used in that scene's speaking. "
            "Place N in the actor list is the person marked <N>: <1> is the first entry, <2> the second, "
            "<3> the third, and so on. Look at the highest number used in the scene's speaking; "
            "the actor list must have that many entries, in order, so every <N> that appears points to the right person. "
            "If a scene uses only <2>, the actor list still has place 1 (the person who is <1> in the transcript) "
            "and place 2. Name each person by this prompt's own actor rules (for example the host and the guests), "
            "and a person keeps the same place in every scene.\n"
            "The episode rules of this prompt are not changed by any of this. "
            "This run uses the transcript.\n"
            + _MEDIA_SCENE_TIMING_NOTE
        ),
    }
    names = {
        "transcript": "the transcript",
        "pdf": "the PDF",
        "audio": "the audio recording",
        "video": "the video",
    }
    notes["image"] = (
        "Content source for this run: one attached image (the item's cover image). "
        "Read the picture for the people, the place, any text and the steps or sections it shows. "
        "This run uses the image."
    )
    note = notes.get(kind) or notes["analyzed"]
    if kind in names:
        prompt = prompt.replace("analyzed_content", names[kind])
    return prompt.rstrip() + "\n\n" + note + "\n"


def _image_material_override(video_detail: dict) -> str:
    """材料选「封面图片」时 ``{content}`` 的说明（图片本身作为附件发给 LLM）。"""
    img = _find_gen_video_webp_for_row(video_detail) if isinstance(video_detail, dict) else ""
    name = os.path.basename(img) if img else "(none)"
    return (
        f"The content is the attached image ({name}). Read the picture itself: its people, place, "
        "any text and the steps or sections it shows. Build the scenes from what the image shows."
    )


def _pdf_scene_generation_instruction(prompt_label: str, page_count: int, mode: str) -> str:
    """选 PDF 时加在每一条场景提示词上，只说页数和场数，不逐页罗列。"""
    label = (prompt_label or "").strip()
    n = max(0, int(page_count))
    line = (
        f"The PDF has {n} pages. It may contain pictures and a little text. "
        "Read the PDF for the content. Use this prompt's scene JSON fields. "
        "When you write actor, take the name from the picture or the words, "
        "and take the age band from how the person looks: kids, youth, teenager, mature, or senior. "
        "Do not write an age number. The same person keeps one age band."
    )
    line += (
        f" One scene per page, in page order: exactly {n} scenes. "
        "Do not merge two pages, do not split one page, do not add a scene, do not drop one. "
        "The scene count equals the page count."
    )
    if "series" in label.lower():
        line += (
            " The program frame (the host's or counselor's opening and closing, the remedy) "
            "is carried inside the scenes of the pages it belongs to. It does not get extra scenes."
        )
    return line
