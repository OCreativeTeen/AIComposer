import os
import re
import uuid
import random
import glob
import json
import copy
import unicodedata
import zhconv

try:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from utility.file_util import safe_clipboard_json_copy
import config_channel


LANGUAGES = {
    "zh": "chinese",
    "tw": "chinese",
    "zh-cn": "chinese",
    "zh-tw": "chinese",
    "zh-hk": "chinese",
    "zh-mo": "chinese",
    "zh-sg": "chinese",
    "zh-my": "chinese",
    "zh-ph": "chinese",
    "zh-th": "chinese",
    "zh-vn": "chinese",
    "en": "english",
    "ja": "japanese",
    "ko": "korean",
    "fr": "french",
    "de": "german",
    "es": "spanish",
}


_BILINGUAL_RAW_KEYS = frozenset(("english", "chinese"))


def bilingual_branch_for_ui_language(ui_language_key: str) -> str:
    """NotebookLM / Case-Study RAW 的双语分支名（仅 english | chinese）。"""
    br = LANGUAGES.get(str(ui_language_key or "tw").strip().lower(), "chinese")
    return br if br in _BILINGUAL_RAW_KEYS else "chinese"


def scene_story_language_key_for_ui(ui_language_key: str) -> str:
    """UI 语种码 → ``scene_content`` 顶层分支名，规则与 ``magic_workflow.load_scenes`` 中
    ``config.LANGUAGES[self.language]`` 一致（tw/zh → chinese；en → english；…）。

    若参数本身已是 ``english`` / ``chinese``（部分旧数据），则原样返回。
    """
    k = str(ui_language_key or "tw").strip().lower()
    if k in _BILINGUAL_RAW_KEYS:
        return k
    return LANGUAGES.get(k, "chinese")


def merge_analyzed_content_bilingual(existing, rewritten, ui_language_key: str) -> dict:
    """将 LLM 返回的 analyzed_content 合并进 ``{english: {...}, chinese: {...}}``，保留另一语种。

    ``rewritten`` 若为带 english/chinese 键的对象则按分支整体替换；否则只更新当前 UI 语种分支。
    """
    existing = existing if isinstance(existing, dict) else {}
    rewritten = rewritten if isinstance(rewritten, dict) else {}
    out: dict = {}
    if _BILINGUAL_RAW_KEYS.intersection(existing.keys()):
        for k in _BILINGUAL_RAW_KEYS:
            v = existing.get(k)
            out[k] = copy.deepcopy(v) if isinstance(v, dict) else {}
    else:
        branch0 = bilingual_branch_for_ui_language(ui_language_key)
        out = {"english": {}, "chinese": {}}
        out[branch0] = copy.deepcopy(existing)

    if _BILINGUAL_RAW_KEYS.intersection(rewritten.keys()):
        for k in _BILINGUAL_RAW_KEYS:
            if k not in rewritten:
                continue
            sub = rewritten[k]
            if isinstance(sub, dict):
                out[k] = copy.deepcopy(sub)
        return out

    branch = bilingual_branch_for_ui_language(ui_language_key)
    out.setdefault("english", {})
    out.setdefault("chinese", {})
    if not isinstance(out["english"], dict):
        out["english"] = {}
    if not isinstance(out["chinese"], dict):
        out["chinese"] = {}
    out[branch] = copy.deepcopy(rewritten)
    return out


def merge_scene_content_bilingual(existing, rewritten, ui_language_key: str) -> dict:
    """将内容合并进 ``{english: [scenes], chinese: [scenes]}``；``rewritten`` 可为 list 或双语 dict。"""
    existing = existing if isinstance(existing, dict) else {}
    bi = _BILINGUAL_RAW_KEYS
    out: dict = {}
    if bi.intersection(existing.keys()):
        for k in bi:
            v = existing.get(k)
            if isinstance(v, list):
                out[k] = copy.deepcopy(v)
            elif isinstance(v, dict):
                out[k] = [copy.deepcopy(v)]
            elif v is None:
                out[k] = []
            else:
                out[k] = []
    else:
        branch0 = bilingual_branch_for_ui_language(ui_language_key)
        out = {"english": [], "chinese": []}
        if isinstance(existing, list):
            out[branch0] = copy.deepcopy(existing)
        elif isinstance(existing, dict):
            out[branch0] = [copy.deepcopy(existing)]
        else:
            out[branch0] = []

    if isinstance(rewritten, list):
        branch = bilingual_branch_for_ui_language(ui_language_key)
        out.setdefault("english", [])
        out.setdefault("chinese", [])
        out[branch] = copy.deepcopy(rewritten)
        return out

    if isinstance(rewritten, dict):
        if bi.intersection(rewritten.keys()):
            for k in bi:
                if k not in rewritten:
                    continue
                v = rewritten[k]
                if isinstance(v, list):
                    out[k] = copy.deepcopy(v)
                elif isinstance(v, dict):
                    out[k] = [copy.deepcopy(v)]
                elif v is None:
                    out[k] = []
            return out
        branch = bilingual_branch_for_ui_language(ui_language_key)
        out.setdefault("english", [])
        out.setdefault("chinese", [])
        out[branch] = [copy.deepcopy(rewritten)]
        return out

    return out



def chinese_convert(text, language):
    if language == "zh":
        # Convert to simplified Chinese
        return zhconv.convert(text, 'zh-cn')
    elif language == "tw":
        # Convert to traditional Chinese
        return zhconv.convert(text, 'zh-tw')
    else:
        return text




# =============================================================================
# Speaker/Host 角色与风格定义 - 供 GUI、downloader 等模块共享
# 格式: gender/age/race | style（如 man/mature/chinese | realistic）
# 旁白/人物下拉：默认从仓库根 media/voices.json 各条目的 name 动态加载（与 Voicebox 同源），
# 仅当文件缺失或解析失败时使用下方回退列表。
# =============================================================================
VISUAL_STYLE_OPTIONS = [
    "pixar-art cartoon + realistic",
    "pixar-art cartoon",
    "realistic",
    "cartoon",
]

_CHARACTER_PERSON_OPTIONS_FALLBACK = [
    "",
    "woman/mature/chinese",
    "man/mature/chinese",
    "woman/young/chinese",
    "man/young/chinese",
    "woman/mature/english",
    "man/mature/english",
    "woman/young/english",
    "man/young/english",
    "woman/grok/chinese",
    "man/grok/chinese",
    "woman/grok/english",
    "man/grok/english",
    "man/teen/chinese",
    "man/narrator/chinese",
    "woman/qin/chinese",
    "woman/qin-fast/chinese",
    "man/wj/chinese",
    "man/elon/english",
    "man/trump/english",
]


def load_character_person_options():
    """
    从 ``media/voices.json`` 读取每条 ``name``（兼容 ``voice``），去重保序；
    首项固定为 ``""`` 供下拉留空。失败则返回 ``_CHARACTER_PERSON_OPTIONS_FALLBACK``。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media", "voices.json")
    if not os.path.isfile(path):
        return list(_CHARACTER_PERSON_OPTIONS_FALLBACK)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return list(_CHARACTER_PERSON_OPTIONS_FALLBACK)
    if not isinstance(data, list):
        return list(_CHARACTER_PERSON_OPTIONS_FALLBACK)
    names = []
    for item in data:
        if not isinstance(item, dict):
            continue
        n = (item.get("name") or item.get("voice") or "").strip()
        if n:
            names.append(n)
    seen = set()
    uniq = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    if not uniq:
        return list(_CHARACTER_PERSON_OPTIONS_FALLBACK)
    return [""] + uniq


def reload_character_person_options():
    """重新从 ``voices.json`` 加载并写回 ``CHARACTER_PERSON_OPTIONS``（例如 JSON 更新后调用）。"""
    global CHARACTER_PERSON_OPTIONS
    CHARACTER_PERSON_OPTIONS = load_character_person_options()
    return CHARACTER_PERSON_OPTIONS


CHARACTER_PERSON_OPTIONS = load_character_person_options()



#
IMAGE_STYLES = [
    "ultra-realistic, cinematic lighting, dramatic shading",

    "watercolor painting",
    "watercolor painting with postcard border",
    "watercolor painting with golden ornate photo frame",
    "watercolor painting with Rococo picture frame",
    "watercolor painting with vintage photo frame",

    "ukiyo-e style",
    "ukiyo-e with vintage photo frame",
    "ukiyo-e with postcard border",
    "ukiyo-e with golden ornate photo frame",
    "ukiyo-e with Rococo picture frame"
]

IMAGE_STYLES_2 = [
    #"ultra-realistic, cinematic lighting, dramatic shading",
    { "style": "vintage postcard look", "frame": "vintage photo frame" },
    { "style": "vintage postcard look", "frame": "postcard border" },
    { "style": "vintage postcard look", "frame": "golden ornate photo frame" },
    { "style": "vintage postcard look", "frame": "baroque frame" },
    { "style": "vintage postcard look", "frame": "Rococo picture frame" },
    { "style": "graphite drawing", "frame": "vintage photo frame" },
    { "style": "graphite drawing", "frame": "postcard border" },
    { "style": "graphite drawing", "frame": "golden ornate photo frame" },
    { "style": "graphite drawing", "frame": "baroque frame" },
    { "style": "graphite drawing", "frame": "Rococo picture frame" },
    { "style": "watercolor painting", "frame": "gallery frame" },
    { "style": "watercolor painting", "frame": "postcard border" },
    { "style": "watercolor painting", "frame": "golden ornate photo frame" },
    { "style": "watercolor painting", "frame": "baroque frame" },
    { "style": "watercolor painting", "frame": "Rococo picture frame" },
    { "style": "rococo painting (baroque art)", "frame": "baroque frame" },
    { "style": "rococo painting (baroque art)", "frame": "postcard border" },
    { "style": "rococo painting (baroque art)", "frame": "golden ornate photo frame" },
    { "style": "rococo painting (baroque art)", "frame": "Rococo picture frame" },
    { "style": "ukiyo-e style", "frame": "ukiyo-e frame" },
    { "style": "ukiyo-e style", "frame": "postcard border" },
    { "style": "ukiyo-e style", "frame": "golden ornate photo frame" },
    { "style": "ukiyo-e style", "frame": "baroque frame" },
    { "style": "ukiyo-e style", "frame": "Rococo picture frame" },
    { "style": "crayon art (pastel drawing)", "frame": "postcard border" },
    { "style": "crayon art (pastel drawing)", "frame": "golden ornate photo frame" },
    { "style": "crayon art (pastel drawing)", "frame": "baroque frame" },
    { "style": "crayon art (pastel drawing)", "frame": "Rococo picture frame" }
]

# 图像提示词预设选项
IMAGE_PROMPT_OPTIONS = [
    "",
    "Ancient Middle-Eastern (story, clothing/head-coverings, tent)",
    "Chinese person (black hair) with traditional chinese dressing, Song-dynasty traditional chinese culture/architecture",
    "Modern Chinese person in business suit, contemporary urban cityscape background",
    "Japanese person in traditional kimono, traditional Japanese temple and garden",
    "Modern Japanese person in casual street fashion, Tokyo neon lights background",
    "Korean person in traditional hanbok, ancient Korean palace architecture",
    "Modern Korean person in K-pop style fashion, Seoul city skyline",
    "European person in medieval clothing, Gothic cathedral and castle",
    "Modern European person in elegant fashion, Paris street café scene",
    "American person in western cowboy attire, wild west desert landscape",
    "Modern American person in casual wear, New York skyscrapers background",
    "Indian person in traditional sari/kurta, Taj Mahal and traditional architecture",
    "Modern Indian person in contemporary dress, Mumbai modern cityscape",
    "Middle Eastern person in traditional robes, ancient desert city architecture",
    "Modern Middle Eastern person in business attire, Dubai futuristic skyline",
    "African person in traditional tribal clothing, savanna and acacia trees",
    "Modern African person in stylish fashion, Lagos or Cape Town cityscape",
    "Russian person in traditional folk costume, Red Square and onion domes",
    "Modern Russian person in winter fashion, Moscow snowy streets",
    "Brazilian person in carnival costume, Rio de Janeiro beach and mountains",
    "Modern Brazilian person in beach wear, São Paulo urban landscape",
    "cozy warm tones, calm atmosphere, subtle textures, psychological wellness, emotional warmth, a heartwarming lifestyle"    
]


# 负面提示词预设选项
NEGATIVE_PROMPT_OPTIONS = [
    "words explaination in the image, low quality, distorted, overly cartoonish, text, watermark, deformed, ugly, duplicate faces",
    "modern clothing/t-shirt, glasses/watches, guns/rifles/pistols/tactical-outfit, cars, phones, neon-lights",
    "drawing, painting, sketch, illustration",
    "nsfw, nude, sexual, adult content, violence, gore, blood",
    "extra limbs, extra fingers, extra arms, extra legs, missing limbs"
    "crowd, too many people"
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

    text = safe_clipboard_json_copy(text)
    if not text.strip():
        return None

    text = text.strip()

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



def load_topics(channel: str) -> tuple[list, list, dict]:
    channel_path = get_channel_path(config_channel.get_channel_id(channel)) if channel else None

    topics_file = os.path.join(channel_path, 'topics.json')
    tags_file = os.path.join(channel_path, 'tags.json')
    topic_choices = []
    topic_categories = []
    tag_features_map: dict = {}
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
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    if not isinstance(k, str) or not k.strip():
                        continue
                    if isinstance(v, list):
                        tag_features_map[k.strip()] = [
                            str(x).strip() for x in v if x is not None and str(x).strip()
                        ]
        except (json.JSONDecodeError, OSError):
            pass
    return topic_choices, topic_categories, tag_features_map


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
# 成片/拖放加水印输出目录（Youtube 摘要窗等处写入）
INPUT_MEDIA_GEN_VIDEO_PATH = f"{INPUT_MEDIA_PATH}/gen_video"
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


def channel_list_json_dir_abs(channel_path: str) -> str:
    """频道下所有热门/主题 list JSON 根目录：``program/<channel_id>/list``（与 ``Download`` 等媒体子目录并列）。"""
    return os.path.join(channel_path, "list")


def ensure_channel_list_json_dir(channel_path: str) -> str:
    d = channel_list_json_dir_abs(channel_path)
    os.makedirs(d, exist_ok=True)
    return d


def normalize_topic_category_list_key(topic_category):
    """规范主题分类字符串，使同一逻辑栏目只对应一个 list 文件（strip、压缩空白、Unicode NFC）。"""
    s = (topic_category or "").strip()
    if not s:
        return "_uncategorized"
    s = unicodedata.normalize("NFC", s)
    s = " ".join(s.split())
    return s


def topic_category_list_file_basename(topic_category) -> str:
    """``list/<可读安全名>.json``（相对频道目录），无哈希后缀。

    分类唯一性由用户在确定 ``topic_category`` 时保证；非法路径字符与长度由 ``make_safe_file_name`` 处理。
    """
    from utility.file_util import make_safe_file_name

    key = normalize_topic_category_list_key(topic_category)
    safe = make_safe_file_name(key, title_length=200)
    return f"{safe}.json"


def topic_category_list_json_abspath(channel_field: str, topic_category: str) -> str:
    """``program/<channel>/list/<basename>``，与 ``gui.downloader`` 主题列表一致。"""
    ch_key = (channel_field or "").strip()
    ch_id = config_channel.get_channel_id(ch_key) if ch_key else None
    if not ch_id:
        keys = list(config_channel.CHANNEL_CONFIG.keys())
        ch_id = ch_key or (keys[0] if keys else "default")
    base = get_channel_path(ch_id)
    d = ensure_channel_list_json_dir(base)
    return os.path.join(d, topic_category_list_file_basename(topic_category))


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

def parse_speaker_host_for_voice(s):
    """从 speaker/host 字符串解析出 gender/age/race 部分（用于语音匹配）。支持新旧格式：
    新格式: woman/middle-aged/chinese | realistic  -> woman/middle-aged/chinese
    旧格式: realistic-style | woman/middle-aged/chinese -> woman/middle-aged/chinese"""
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


def get_fallback_background_image(channel, width, height):
    """当 extract_frame 失败时，从当前 channel 的 background_image 目录取一张图作为备用。
    参考 make_backgroud_medias 的选图逻辑，按横竖屏选 169_ 或 916_。"""
    if not channel:
        return None
    prefix, kernel = fetch_resource_prefix("", [])
    image_dir = get_channel_path(channel) + "/image"
    if not os.path.isdir(image_dir):
        return None
    if width > height:
        img = find_matched_file(image_dir, prefix + "/169_", "png", kernel)
    else:
        img = find_matched_file(image_dir, prefix + "/916_", "png", kernel)
    return img


def make_backgroud_medias(pid, channel, ffmpeg_processor, ffmpeg_audio_processor):
    prefix, kernel = fetch_resource_prefix("", [])
    image_dir = get_channel_path(channel) + "/clip_image"
    music_dir = get_channel_path(channel) + "/zero"
    video_dir = get_channel_path(channel) + "/clip"

    # 1. 获取 background_image（按横竖屏选 169_ 或 916_）
    if ffmpeg_processor.width > ffmpeg_processor.height:
        background_image = find_matched_file(image_dir, prefix + "/169_", "png", kernel)
        background_video= find_matched_file(video_dir, prefix + "/169_", "mp4", kernel)
        background_music= find_matched_file(music_dir, prefix + "/169_", "mp4", kernel)
    else:
        background_image = find_matched_file(image_dir, prefix + "/916_", "png", kernel)
        background_video= find_matched_file(video_dir, prefix + "/916_", "mp4", kernel)
        background_music= find_matched_file(music_dir, prefix + "/916_", "mp4", kernel)

    return background_image, background_video, background_music
    
    
def get_scenes_path(pid: str) -> str:
    """获取场景文件路径"""
    return f"{get_project_path(pid)}/scenes.json"




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
# Telegram：发布成片到 YouTube 成功后可选推送到私信/群组/频道（Bot API）
# =============================================================================
#
# 【一次性设置概要】
# 1) Telegram 搜索 @BotFather → /newbot → 按提示起名 → 拿到 ``bot_token``（形如 ``123456:AAH...``）。
# 2) 目标为「自己与 Bot 的对话」：先对 Bot 点 Start；浏览器打开（把 <TOKEN> 换成 token）：
#    ``https://api.telegram.org/bot<TOKEN>/getUpdates``
#    在结果里找 ``message.chat.id`` 即为 ``chat_id``（可写成字符串）。
# 3) 群组：把 Bot 拉进群后发一条消息，再刷 ``getUpdates``，使用该群的 ``chat.id``。
# 4) 频道：把 Bot 加为频道管理员（需发消息权限）；``chat_id`` 可用 ``@频道公开名`` 或数字 ID（常为 -100…）。
# 5) 在仓库根目录 ``.env`` 中设置（勿提交 Git；``.gitignore`` 已忽略 ``.env``）：
#
#      TELEGRAM_BOT_TOKEN=你的_bot_token
#
#    单个接收方::
#
#      TELEGRAM_CHAT_ID=单个_chat_id
#
#    或多个接收方（**同一 Bot 会向列表中每个会话各发一遍相同内容**），逗号 / 分号 / 竖线分隔均可::
#
#      TELEGRAM_CHAT_IDS=111111111,222222222,-100xxxxxxxxxx,@your_channel
#
#    若同时设置了 ``TELEGRAM_CHAT_IDS``（非空），则 **忽略** ``TELEGRAM_CHAT_ID``。
#
#    ``config.py`` 中的 ``enabled`` 等开关仍可在此文件填写。
# 6) Bot 单文件上限约 50MB；超过 ``max_video_mb`` 时跳过视频文件，仍会发送标题/链接及 YouTube 描述文案（与上传时 ``summary`` 一致）。
#

def _telegram_publish_chat_ids_from_env():
    """从环境变量解析 Telegram 接收方列表（去重保序）。"""
    raw = (os.environ.get("TELEGRAM_CHAT_IDS") or "").strip()
    out = []
    if raw:
        for segment in re.split(r"[,|;]+", raw):
            for tok in segment.split():
                t = tok.strip()
                if t:
                    out.append(t)
    else:
        one = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
        if one:
            out.append(one)
    seen = set()
    dedup = []
    for x in out:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    return dedup


TELEGRAM_PUBLISH = {
    "enabled": True,
    "bot_token": (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip(),
    "chat_ids": _telegram_publish_chat_ids_from_env(),
    "max_video_mb": 48,
}

# =============================================================================
# 图像生成配置
# =============================================================================
# 图像生成默认风格配置





