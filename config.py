import os
import re
import uuid
import random
import glob
import json
import shutil



LANGUAGES = {
    "zh": "Chinese",
    "tw": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
}

# =============================================================================
# Speaker/Host 角色与风格定义 - 供 GUI、downloader 等模块共享
# 格式: gender/age/race | style（如 woman/middle-aged/chinese | realistic）
# =============================================================================
VISUAL_STYLE_OPTIONS = [
    ("pixar-art cartoon + realistic", "真实卡通(皮克斯)"),
    ("pixar-art cartoon", "卡通(皮克斯)"),
    ("realistic", "真实形象"),
    ("cartoon", "卡通(普通)"),
]
# 人物选项 (value: gender/age/race, label: 中文显示) - 与 GUI HOST_OPTIONS_DATA 一致
CHARACTER_PERSON_OPTIONS = [
    ("woman/young/chinese", "中国青年女性"),
    ("woman/middle-aged/chinese", "中国中年女性"),
    ("man/young/chinese", "中国青年男性"),
    ("man/middle-aged/chinese", "中国中年男性"),
    ("girl/chinese", "中国女孩"),
    ("boy/chinese", "中国男孩"),
    ("woman/senior/chinese", "中国老年女性"),
    ("man/senior/chinese", "中国老年男性"),
    ("woman/young/caucasian", "白人青年女性"),
    ("man/young/caucasian", "白人青年男性"),
    ("woman/middle-aged/caucasian", "白人中年女性"),
    ("man/middle-aged/caucasian", "白人中年男性"),
    ("girl/caucasian", "白人女孩"),
    ("boy/caucasian", "白人男孩"),
    ("woman/senior/caucasian", "白人老年女性"),
    ("man/senior/caucasian", "白人老年男性"),
]


def _build_describe_host_options():
    """场景描述 Host 组合选项：(value, label)。由 CHARACTER_PERSON_OPTIONS + SPEAKER_STYLE_OPTIONS 生成"""
    opts = [("", "不包含 Host")]
    for style_val, style_lbl in VISUAL_STYLE_OPTIONS:
        for char_val, char_lbl in CHARACTER_PERSON_OPTIONS:
            if char_val in ("woman/middle-aged/chinese", "man/middle-aged/chinese"):
                from config import build_speaker_host_string  # 避免循环
                combined = build_speaker_host_string(char_val, style_val)
                short = char_lbl.replace("中国", "")
                opts.append((combined, f"{style_lbl}-{short}"))
    return opts


DESCRIBE_HOST_OPTIONS = None  # 延迟初始化，见下


def get_describe_host_options():
    """获取场景描述 Host 选项列表"""
    global DESCRIBE_HOST_OPTIONS
    if DESCRIBE_HOST_OPTIONS is None:
        DESCRIBE_HOST_OPTIONS = _build_describe_host_options()
    return DESCRIBE_HOST_OPTIONS


# =============================================================================
# Host 显示方式 - 供 downloader、GUI 等模块共享
# 旁白（Host）在画面中的出现方式：无/仅声音/有声音有图像（多种布局）
# =============================================================================
HOST_DISPLAY_OPTIONS_DOWNLOADER = [
    ("无 Host", "no-host"),           # 无 Host：无声音无图像，主角表演陈述
    ("有声音无图像", "voice-only"),    # 有声音无图像：画面以 Host 旁白为主，主角为辅
    ("有声音有图像-左下角小图", "voice-image-bottom-left"),
    ("有声音有图像-右下角小图", "voice-image-bottom-right"),
    ("有声音有图像-左大右小", "voice-image-left-large-right-small"),
    ("有声音有图像-右大左小", "voice-image-right-large-left-small"),
]




def fetch_text_from_json(script_path, output_path=None):
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
        text_content = "\n".join([segment["caption"] for segment in segments])
    except Exception as e:
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                text_content = f.read()
        except Exception as e:
            return ""

    c = extract_text_from_srt_content(text_content)
    if c:
        text_content = c

    # 如果提供了输出路径，保存到文件
    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text_content)
            print(f"✅ 文本已保存: {output_path}")
        except Exception as e:
            print(f"⚠️ 保存文本文件失败: {str(e)}")
    
    return text_content



def extract_text_from_srt_content(content):
    """
    从 SRT 字幕内容中提取纯文本（去掉序号、时间戳等）。
    可被 downloader、project_manager 等模块复用。

    Args:
        content: SRT 文件内容字符串

    Returns:
        提取的文本行用换行符拼接；若非 SRT 格式则原样返回输入；空输入返回 None。
    """
    if not content or not content.strip():
        return None

    # 使用正则表达式匹配 SRT 格式：序号\n时间戳\n文本内容\n\n
    pattern = r'^\d+\s*\n\s*\d{2}:\d{2}:\d{2}[,\d]+\s*-->\s*\d{2}:\d{2}:\d{2}[,\d]+\s*\n(.*?)(?=\n\d+\s*\n|\Z)'
    matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)

    text_lines = []
    for match in matches:
        text_block = match.strip()
        if text_block:
            lines = [line.strip() for line in text_block.split('\n') if line.strip()]
            text_lines.extend(lines)

    # 如果没有匹配到，使用备用方法：逐行解析
    if not text_lines:
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.isdigit():
                i += 1
                if i < len(lines) and '-->' in lines[i]:
                    i += 1
                while i < len(lines):
                    text_line = lines[i].strip()
                    if not text_line:
                        break
                    if text_line.isdigit():
                        break
                    text_lines.append(text_line)
                    i += 1
            else:
                i += 1

    # 若未识别为 SRT 格式（如纯文本、转录稿），原样返回输入
    return '\n'.join(text_lines) if text_lines else content


def parse_json_from_text(text):
    """从文本中解析 JSON，处理可能的引号包裹问题"""
    if not text:
        return None
    
    text = text.strip()
    if not text:
        return None
    
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 处理被引号包裹的情况：去除外层引号（可能是单引号或双引号）
    # 处理类似 "'[ ..." 或 '"[...' 的情况
    cleaned_text = text
    
    # 去除外层单引号
    if cleaned_text.startswith("'") and cleaned_text.endswith("'"):
        cleaned_text = cleaned_text[1:-1].strip()
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass
    
    # 去除外层双引号
    if cleaned_text.startswith('"') and cleaned_text.endswith('"'):
        cleaned_text = cleaned_text[1:-1].strip()
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass
    
    # 处理双重引号包裹的情况（如 "'[...'" 或 '"\'[...\'"')
    # 先去除外层单引号，再去除内层双引号
    if text.startswith("'\"") and text.endswith("\"'"):
        cleaned_text = text[2:-2].strip()
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass
    
    # 处理转义字符的情况
    # 尝试使用 ast.literal_eval 作为备选方案（仅当字符串看起来像 Python 字面量时）
    try:
        import ast
        # 如果字符串看起来像 Python 字符串字面量，尝试解析
        if (text.startswith('"') or text.startswith("'")) and (text.endswith('"') or text.endswith("'")):
            evaluated = ast.literal_eval(text)
            if isinstance(evaluated, str):
                return json.loads(evaluated)
            elif isinstance(evaluated, (list, dict)):
                return evaluated
    except (ValueError, SyntaxError):
        pass
    
    return None


def load_topics(channel_path: str) -> tuple[list, list, list]:
    """
    从频道目录下的 topics.json 和 tags.json 加载 topic_choices、topic_categories 和 tag_choices。
    可被 downloader、project_manager 等模块复用。

    Args:
        channel_path: 频道目录路径（可用 config.get_channel_path(channel) 获取）

    Returns:
        (topic_choices, topic_categories, tag_choices): 主题列表、去重后的分类列表、tag 类型及选项列表
    """
    topics_file = os.path.join(channel_path, 'topics.json')
    tags_file = os.path.join(channel_path, 'tags.json')
    topic_choices = []
    topic_categories = []
    tag_choices = []
    if os.path.exists(topics_file):
        try:
            with open(topics_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                topic_choices = loaded
            elif isinstance(loaded, dict):
                topic_choices = [loaded]
            for item in topic_choices:
                if isinstance(item, dict):
                    category = item.get('topic_category') or item.get('category')
                    if category and category not in topic_categories:
                        topic_categories.append(category)
        except (json.JSONDecodeError, OSError):
            pass
    if os.path.exists(tags_file):
        try:
            with open(tags_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                tag_choices = loaded
            elif isinstance(loaded, dict):
                tag_choices = [loaded]
        except (json.JSONDecodeError, OSError):
            pass
    return topic_choices, topic_categories, tag_choices


# self.channel is like israle_zh,  need to get the 'isreale' part out
def fetch_resource_prefix(prefix, kernel):
    if kernel and len(kernel) > 0:
        if prefix != "":
            prefix = kernel[0] + "/" + prefix
        else:
            prefix = kernel[0]

        if len(kernel) > 1:
            kernel = kernel[1:]
        else:
            kernel = []
    return prefix, kernel



def find_matched_files(folder, prefix, post, kernel=None):
    if kernel is None:
        kernel = []
    
    # 查找所有匹配模式的文件
    pattern = f"{folder}/{prefix}*.{post}"
    matched_files = glob.glob(pattern)
    
    if not matched_files:
        if "/" in prefix:
            pattern = f"{folder}/*/*.{post}"
            matched_files = glob.glob(pattern)
            if not matched_files:
                prefix = prefix.split("/")[0]
                matched_files = glob.glob(pattern)
        else:
            pattern = f"{folder}/*.{post}"
            matched_files = glob.glob(pattern)

    if not matched_files:
        return None
    
    if not kernel:
        return matched_files
    
    # 计算每个文件的匹配度
    best_matches = []
    max_match_count = 0
    
    for file_path in matched_files:
        # 从文件名中提取关键词部分
        filename = os.path.basename(file_path)
        # 移除扩展名和前缀
        name_without_ext = filename.replace(f'.{post}', '')
        parts = name_without_ext.split('_')[1:]  # 跳过前缀部分
        
        # 移除最后的数字部分（如果存在）
        if parts and parts[-1].isdigit():
            parts = parts[:-1]
        
        # 计算匹配的关键词数量
        match_count = 0
        for keyword in kernel:
            if keyword.lower() in [part.lower() for part in parts]:
                match_count += 1
        
        print(f"📋 文件 {filename} 匹配到 {match_count} 个关键词: {parts}")
        
        # 更新最佳匹配
        if match_count > max_match_count:
            max_match_count = match_count
            best_matches = [file_path]
        elif match_count == max_match_count:
            best_matches.append(file_path)

    print(f"🎯 最佳匹配 ({max_match_count} 个关键词): {best_matches}")
    return best_matches



def find_matched_file(folder, prefix, post, kernel=None, used_files=None):
    best_matches = find_matched_files(folder, prefix, post, kernel) 
    if not best_matches or len(best_matches) == 0:
        return None
    
    if not used_files:
        return random.choice(best_matches)
    
    for i in range(len(best_matches)):
        choice = random.choice(best_matches)
        if not choice in used_files:
            return choice
        
    return choice







# =============================================================================
# 基础路径配置
# =============================================================================
BASE_MEDIA_PATH = "/AI_MEDIA"
INPUT_MEDIA_PATH = f"{BASE_MEDIA_PATH}/input"
DEFAULT_MEDIA_PATH = f"{BASE_MEDIA_PATH}/default"
BASE_PROGRAM_PATH = f"{BASE_MEDIA_PATH}/program"
PROJECT_DATA_PATH = f"{BASE_MEDIA_PATH}/project"
PUBLISH_PATH = f"{BASE_MEDIA_PATH}/publish"
TEMP_PATH_BASE = PROJECT_DATA_PATH  # temp 目录在各个项目下

def create_project_path(pid: str):
    os.makedirs(PUBLISH_PATH, exist_ok=True)


def get_channel_path(channel: str) -> str:
    path = f"{BASE_PROGRAM_PATH}/{channel}"
    os.makedirs(path, exist_ok=True)
    return path

def get_project_path(pid: str) -> str:
    path = f"{PROJECT_DATA_PATH}/{pid}"
    os.makedirs(path, exist_ok=True)
    return path

def get_temp_path(pid: str) -> str:
    path = f"{PROJECT_DATA_PATH}/{pid}/temp"
    os.makedirs(path, exist_ok=True)
    return path


tmp_file_list = []
def get_temp_file(pid: str, ext: str, filename: str = None) -> str:
    """获取临时文件路径"""
    if not filename:
        filename = f"{uuid.uuid4()}.{ext}"
    else:
        filename = filename + "." + ext
    temp_dir = f"{PROJECT_DATA_PATH}/{pid}/temp"
    # 确保临时目录存在
    os.makedirs(temp_dir, exist_ok=True)
    temp_file = f"{temp_dir}/{filename}" 
    tmp_file_list.append(temp_file)
    return temp_file


def clear_temp_files():
    for file in tmp_file_list:
        if os.path.exists(file):
            os.remove(file)
    tmp_file_list.clear()


def get_media_path(pid: str) -> str:
    """获取视频文件路径"""
    path = f"{PROJECT_DATA_PATH}/{pid}/media"
    os.makedirs(path, exist_ok=True)
    return path

def get_effect_path() -> str:
    """获取视频文件路径"""
    path = f"{BASE_MEDIA_PATH}/effect"
    os.makedirs(path, exist_ok=True)
    return path

def get_background_video_path() -> str:
    """获取视频文件路径"""
    return f"{BASE_PROGRAM_PATH}/background_video"

def get_background_music_path() -> str:
    """获取音乐文件路径"""
    return f"{BASE_PROGRAM_PATH}/background_music"

def get_background_image_path() -> str:
    """获取背景文件路径"""
    return f"{BASE_PROGRAM_PATH}/background_image"


def format_gender_age_race_slash(s):
    """将 gender_age_race（下划线分隔）转为 gender/age/race（斜杠分隔），便于 AI 区分。"""
    if not s or not isinstance(s, str):
        return s or ""
    s = s.strip()
    if s in ("voice-only", "not-in-scene", "no-host"):
        return s
    return "/".join(s.split("_"))


def parse_speaker_host_for_voice(s):
    """从 speaker/host 字符串解析出 gender/age/race 部分（用于语音匹配）。支持新旧格式：
    新格式: woman/middle-aged/chinese | realistic  -> woman/middle-aged/chinese
    旧格式: realistic-style | woman_middle-aged_chinese -> woman_middle-aged_chinese"""
    if not s or not isinstance(s, str):
        return ""
    s = s.strip()
    if " | " not in s:
        return s
    before, after = s.split(" | ", 1)
    before, after = before.strip(), after.strip()
    if before.endswith("-style"):
        return after
    return before


def parse_speaker_host_parts(s):
    """从 speaker/host 字符串解析出 (person_part, style_part)。person 为斜杠格式；style 为 realistic/cartoon/pixar-art cartoon。
    支持新旧格式：新格式 person | style；旧格式 style-prefix | person。"""
    if not s or not isinstance(s, str):
        return "", "realistic"
    s = s.strip()
    if " | " not in s:
        return s, "realistic"
    before, after = s.split(" | ", 1)
    before, after = before.strip(), after.strip()
    if before.endswith("-style"):
        person_raw = after
        style_raw = before
        if style_raw == "realistic-style":
            st = "realistic"
        elif style_raw == "cartoon-style":
            st = "cartoon"
        elif style_raw == "pixar-art-cartoon-style":
            st = "pixar-art cartoon"
        else:
            st = "realistic"
        p = format_gender_age_race_slash(person_raw) if "_" in person_raw and "/" not in person_raw else person_raw
        return p, st
    person_part = before
    style_map = {"realistic": "realistic", "cartoon": "cartoon", "pixar-art cartoon": "pixar-art cartoon", "pixar-art cartoon": "pixar-art cartoon"}
    st = style_map.get(after, "realistic") if after in style_map else (after if after in ("realistic", "cartoon") else "realistic")
    return person_part, st


def build_speaker_host_string(gender_age_race, style):
    """按新格式构建: gender/age/race | style。gender_age_race 可为下划线或斜杠格式。"""
    g = format_gender_age_race_slash(gender_age_race) if "/" not in str(gender_age_race or "") else (gender_age_race or "")
    style = (style or "").strip()
    if not g:
        return style or ""
    if not style:
        return g
    return f"{g} | {style}"


# 场景描述对话框的 Host 选项（中年中国男女 x 三风格）- 由共享定义生成
DESCRIBE_HOST_OPTIONS = [("", "不包含 Host")] + [
    (build_speaker_host_string(cv, sv), f"{sl}-{cl.replace('中国', '')}")
    for sv, sl in VISUAL_STYLE_OPTIONS
    for cv, cl in CHARACTER_PERSON_OPTIONS
    if cv in ("woman/middle-aged/chinese", "man/middle-aged/chinese")
]


def get_fallback_background_image(channel, width, height):
    """当 extract_frame 失败时，从当前 channel 的 background_image 目录取一张图作为备用。
    参考 make_backgroud_medias 的选图逻辑，按横竖屏选 169_ 或 916_。"""
    if not channel:
        return None
    prefix, kernel = fetch_resource_prefix("", [])
    image_dir = get_background_image_path() + "/" + channel
    if not os.path.isdir(image_dir):
        return None
    if width > height:
        img = find_matched_file(image_dir, prefix + "/169_", "png", kernel)
    else:
        img = find_matched_file(image_dir, prefix + "/916_", "png", kernel)
    return img


def make_backgroud_medias(pid, channel, ffmpeg_processor, ffmpeg_audio_processor):
    """获取背景图、背景音乐，并用图+音乐合成背景视频，返回 (background_image, background_video, background_music)。"""
    prefix, kernel = fetch_resource_prefix("", [])
    image_dir = get_background_image_path() + "/" + channel
    music_dir = get_background_music_path() + "/" + channel
    video_dir = get_background_video_path() + "/" + channel

    # 1. 获取 background_image（按横竖屏选 169_ 或 916_）
    if ffmpeg_processor.width > ffmpeg_processor.height:
        background_image = find_matched_file(image_dir, prefix + "/169_", "png", kernel)
    else:
        background_image = find_matched_file(image_dir, prefix + "/916_", "png", kernel)
    if background_image:
        img_stem = os.path.splitext(os.path.basename(background_image))[0]
        background_image = ffmpeg_processor.to_webp(background_image)

    # 2. 获取 background_music（转成 wav）
    background_music = find_matched_file(music_dir, prefix + "/", "mp3", kernel)
    if background_music:
        music_stem = os.path.splitext(os.path.basename(background_music))[0]
        background_music = ffmpeg_audio_processor.to_wav(background_music)

    # 3. 用 图 + 音乐 合成 background_video
    background_video = None
    if background_image and background_music:
        video_path = video_dir + "/" + img_stem + "_" + music_stem + ".mp4"
        os.makedirs(video_dir, exist_ok=True)  # 确保目标目录存在
        if os.path.exists(video_path):
            background_video = video_path
        else:
            background_video = ffmpeg_processor.image_audio_to_video(background_image, background_music, 1) 
            shutil.move(background_video, video_path)
            background_video = video_path

    return background_image, background_video, background_music
    

def get_main_summary_path(pid: str, language: str) -> str:
    """获取长文本文件路径"""
    return f"{get_project_path(pid)}/main_summary.txt"


def get_main_audio_path(pid: str) -> str:
    """获取主音频文件路径"""
    return f"{get_media_path(pid)}/main.wav"


def get_main_video_path(pid: str) -> str:
    """获取主视频文件路径"""
    return f"{get_media_path(pid)}/main.mp4"


def get_selected_music_path(pid: str) -> str:
    """获取背景音乐文件路径"""
    return f"{get_media_path(pid)}/selected_music.wav"


def get_starting_video_path(pid: str) -> str:
    """获取开始视频文件路径"""
    return f"{get_media_path(pid)}/starting.mp4"


def get_ending_video_path(pid: str) -> str:
    """获取结束视频文件路径"""
    return f"{get_media_path(pid)}/ending.mp4"


def get_pre_video_path(pid: str) -> str:
    """获取预视频文件路径"""
    return f"{get_media_path(pid)}/pre.mp4"


def get_story_audio_path(pid: str) -> str:
    """获取沉浸故事音频文件路径"""
    return f"{get_media_path(pid)}/story.wav"


def get_story_video_path(pid: str) -> str:
    """获取沉浸故事视频文件路径"""
    return f"{get_media_path(pid)}/story.mp4"


def get_story_json_path(pid: str) -> str:
    """获取沉浸故事JSON文件路径"""
    return f"{get_project_path(pid)}/story.json"


def get_story_extract_text_path(pid: str) -> str:
    """获取沉浸故事提取文本文件路径"""
    return f"{get_project_path(pid)}/story_extract_text.txt"


def get_short_audio_path(pid: str) -> str:
    """获取短视频对话音频文件路径"""
    return f"{get_media_path(pid)}/short.wav"


def get_scenes_path(pid: str) -> str:
    """获取场景文件路径"""
    return f"{get_project_path(pid)}/scenes.json"


main_summary_content = None
def fetch_main_summary_content(pid: str, language: str):
    global main_summary_content
    sum_long_path = get_main_summary_path(pid, language)
    if not main_summary_content and os.path.exists(sum_long_path):
        with open(sum_long_path, "r", encoding='utf-8') as f:
            main_summary_content = f.read()
    return main_summary_content

def write_main_summary_content(pid: str, language: str):
    global main_summary_content
    with open(get_main_summary_path(pid, language), "w", encoding='utf-8') as f:
        f.write(main_summary_content)



story_extract_text_content = None
def fetch_story_extract_text_content(pid: str, language: str):
    global story_extract_text_content
    story_extract_text_path = get_story_extract_text_path(pid)
    if not story_extract_text_content and os.path.exists(story_extract_text_path):
        with open(story_extract_text_path, "r", encoding='utf-8') as f:
            story_extract_text_content = f.read()
    return story_extract_text_content






# =============================================================================
# 视频配置
# =============================================================================
# VIDEO_WIDTH and VIDEO_HEIGHT are now stored in project config files
# Default values: 1920x1080 (can be changed to 1080x1920 when creating project)

VIDEO_DURATION_DEFAULT = 59.0


# =============================================================================
# 字体配置
# =============================================================================
FONT_0 = { "id":"FONT_0", "name": "简体太极", "path": BASE_MEDIA_PATH+"/font/0_zh.ttf" }
FONT_1 = { "id":"FONT_1", "name": "简体行楷", "path": BASE_MEDIA_PATH+"/font/1_zh.ttf" }
FONT_3 = { "id":"FONT_3", "name": "简体钢笔", "path": BASE_MEDIA_PATH+"/font/3_zh.ttf" }
FONT_4 = { "id":"FONT_4", "name": "简体黑体", "path": BASE_MEDIA_PATH+"/font/4_zh.ttf" }

FONT_7 = { "id":"FONT_7", "name": "繁体行书", "path": BASE_MEDIA_PATH+"/font/7_tw.ttf" }
FONT_8 = { "id":"FONT_8", "name": "繁体鏤空", "path": BASE_MEDIA_PATH+"/font/8_tw.ttf" }

FONT_11 = { "id":"FONT_11", "name": "JAPANESE_0", "path": BASE_MEDIA_PATH+"/font/japanese_1.ttf" }
FONT_12 = { "id":"FONT_12", "name": "JAPANESE_2", "path": BASE_MEDIA_PATH+"/font/japanese_2.ttf" }

FONT_13 = { "id":"FONT_13", "name": "ARABIC_0", "path": BASE_MEDIA_PATH+"/font/NotoSansArabic.ttf" } 

FONT_14 = { "id":"FONT_14", "name": "THAI_1", "path": BASE_MEDIA_PATH+"/font/NotoSansThai.ttf" }

FONT_15 = { "id":"FONT_15", "name": "ENGLISH_0", "path": BASE_MEDIA_PATH+"/font/general_0.ttf" }

FONT_15_1 = { "id":"FONT_15_1", "name": "ENGLISH_1", "path": BASE_MEDIA_PATH+"/font/general_1.ttf" }

FONT_16 = { "id":"FONT_16", "name": "TIBETAN_0", "path": BASE_MEDIA_PATH+"/font/NotoSerifTibetan.ttf" }

FONT_17 = { "id":"FONT_17", "name": "MONGOLIAN_0", "path": BASE_MEDIA_PATH+"/font/NotoSansMongolian.ttf" }

FONT_20 = { "id":"FONT_20", "name": "KOREAN_0", "path": BASE_MEDIA_PATH+"/font/NotoSansKR.ttf" }

FONT_LIST = {
    "zh": FONT_0,
    "zh2": FONT_1,
    "tw": FONT_7,
    "tw2": FONT_8,
    "general": FONT_15,
    "jp": FONT_11,
    "kr": FONT_20,
    "ar": FONT_13,
    "th": FONT_14,
    "tib": FONT_16,
    "mn": FONT_17
}



# =============================================================================
# API密钥配置
# =============================================================================
# Azure 语音服务配置
azure_subscription_key = ""
azure_region = "eastus"

# ElevenLabs 配置
elevenlabs_api_key = ""
elevenlabs_base_url = "https://api.elevenlabs.io/v1"



TRANSITION_EFFECTS = ["fade", "circleopen", "radial", "dissolve", "diagtl", "circleclose"]


# =============================================================================
# 图像生成配置
# =============================================================================
# 图像生成默认风格配置





