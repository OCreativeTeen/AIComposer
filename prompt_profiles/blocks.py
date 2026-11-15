"""t426u: 档位共用的英文句子（不带中文括号，不提说话 / 声音 / 文字以外的禁区，只写正面描述）。

锁定句保留原来的开头（Art style lock: / One base shot: / Objects lock: / Faithful animation: / No new people: /
Image keywords:），这样 restore_video_locked_rules 和原来的核对照样认得。"""
from __future__ import annotations

import re

PIC = "<Picture 1>"


def en_only(text: str) -> str:
    """去掉中文括号说明（……）和其余汉字，合并空白。"""
    s = re.sub(r"（[^）]*）", " ", str(text or ""))
    s = re.sub(r"[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]+", " ", s)
    s = re.sub(r"\(\s*\)", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" +([,.;:])", r"\1", s)
    return s.strip()


def style_en(style: str) -> str:
    import config_prompt as cp

    return en_only(cp.video_art_style_en(style)[0]) or "the style of the picture"


def art_style_lock(style: str) -> str:
    import config_prompt as cp

    return en_only(cp.video_art_style_lock_rule(style, pic=PIC))


def one_base_shot() -> str:
    import config_prompt as cp

    return (f"{cp.VIDEO_ONE_SHOT_PREFIX} the whole video stays inside the base scene of {PIC} from the first frame to "
            f"the last: the same place, background and anyone already in it stay in view, each at about the size and "
            f"place they have in {PIC}. The camera may move slowly (pan, turn, drift or reposition a little within this "
            f"same place) and the light may shift softly without changing the time of day. The video stays one continuous "
            f"shot of this same place from start to end: it never cuts, never switches shots or scenes, and never zooms "
            f"in to one face, a portrait or a single-person shot. Anyone already in {PIC} keeps a calm, relaxed "
            f"expression and makes only small natural movements (a nod, a glance, a gesture). Any change is slow, small "
            f"and local (faces, hands, hair, cloth, light), never the whole scene.")


def objects_lock() -> str:
    import config_prompt as cp

    return en_only(cp.video_props_lock_rule(PIC))


def faithful() -> str:
    import config_prompt as cp

    return en_only(cp.video_faithful_rule(PIC))


def no_new_people() -> str:
    """t429u: 没勾人物时：只有图里本来就有的人和动物；不加人，也不加动物、宠物或任何角色 / 生物。
    开头仍是「No new people:」（锁定句核对认它）。"""
    import config_prompt as cp

    return (f"{cp.VIDEO_NO_NEW_PEOPLE_PREFIX} only the people and animals already shown in {PIC} appear, exactly as "
            f"many as in {PIC} (none if it shows none). Every living thing in the video is one already drawn in {PIC}: "
            "no protagonist, extra, crowd, passer-by, child, background figure, reflection or silhouette, and no "
            "animal, pet, cat, dog, bird, creature, mascot or cartoon character is added; nobody and nothing alive "
            "enters the frame or is shown twice.")


# t429u: 没勾人物时，场景的内容只靠图里已有的东西 + 镜头 + 光线 + 环境的动 + 关键词讲出来
STORY_THROUGH_SCENE = (
    f"The story of this moment is told only through what {PIC} already shows: the camera, the light, the "
    "environment moving softly (light, shadow, air, cloth, leaves, smoke, water) and the picture's keywords, together "
    f"with small movements of any figure already drawn in {PIC}."
)


def caption(text: str) -> str:
    """说明文字四种：保留 / 关键字作背景 → Image keywords 句（不提讲话）；去掉文字 / 用画面讲 → 原来那句。"""
    import config_prompt as cp

    if text in cp.IMAGE_TEXT_KEEP_CHOICES:
        return (f"{cp.VIDEO_IMAGE_KEYWORDS_PREFIX} the keywords only describe lettering already drawn in the start "
                "picture (for example a keyword already set into the background); keep those as they are and they are "
                "never erased; they may gently come alive with the scene (a soft glow, shimmer, sway or light moving "
                "across it) while keeping the same characters in the same place. Anything in the keywords that is not "
                "already visible in the start picture is not added. Nothing new appears and no new lettering is added; "
                "if the start picture has no lettering, the video has none.")
    return en_only(cp.video_caption_rule(text if text in {k for k, _ in cp.FLOW_CAPTION_CHOICES} else "erase"))


def light(visual: str, start_image: str) -> str:
    import config_prompt as cp

    text = cp.minimax_lighting_phrase(visual or "", start_image or "")
    if text.startswith("It is night"):
        text = (f"It is night throughout: the same darkness outside and the same lights as in {PIC}, unchanged from "
                "the first frame to the last.")
    return en_only(text)


def camera(camera: str) -> str:
    import config_prompt as cp

    return cp._H3_CAMERA.get(camera or "none", cp._H3_CAMERA["none"])


# 声音：明确只有安静的环境声（Pixaroma Act 模板的做法），音乐字段也写死。
# t429u: 不再举「远处的鸟」（会被画成鸟）：只写空气、微风和这个地方本身的安静声音
SOUNDSCAPE = ("Only quiet natural ambient sound of the place, steady from the first frame to the last, such as soft air, "
              "a light breeze and the quiet room tone of the place itself. No speech, no singing, no music.")
MUSIC = "None. No music is generated."
