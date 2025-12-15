import os
import uuid
import random
import glob



# self.channel is like israle_zh,  need to get the 'isreale' part out
def fetch_resource_prefix(prefix, keywords):
    if keywords and len(keywords) > 0:
        if prefix != "":
            prefix = keywords[0] + "/" + prefix
        else:
            prefix = keywords[0]

        if len(keywords) > 1:
            keywords = keywords[1:]
        else:
            keywords = []
    return prefix, keywords



def find_matched_files(folder, prefix, post, keywords=None):
    if keywords is None:
        keywords = []
    
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
    
    if not keywords:
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
        for keyword in keywords:
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



def find_matched_file(folder, prefix, post, keywords=None, used_files=None):
    best_matches = find_matched_files(folder, prefix, post, keywords)
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
INPUT_MEDIA_PATH = f"{BASE_MEDIA_PATH}/input_mp4"
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
def get_temp_file(pid: str, ext: str) -> str:
    """获取临时文件路径"""
    filename = f"{uuid.uuid4()}.{ext}"
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

def get_main_summary_path(pid: str, language: str) -> str:
    """获取长文本文件路径"""
    return f"{get_project_path(pid)}/main_summary.txt"

def get_titles_path(pid: str, language: str) -> str:
    """获取长文本文件路径"""
    return f"{get_project_path(pid)}/titles_choices.json"

def get_story_summary_path(pid: str, language: str) -> str:
    """获取沉浸故事文件路径"""
    return f"{get_project_path(pid)}/story_summary.txt"

def get_promote_srt_path(pid: str) -> str:
    """获取沉浸故事文件路径"""
    return f"{get_project_path(pid)}/promote.srt"

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
FONT_0 = { "id":"FONT_0", "name": "华文简体", "path": BASE_MEDIA_PATH+"/font/0_zh.ttf" }
FONT_1 = { "id":"FONT_1", "name": "华文行楷", "path": BASE_MEDIA_PATH+"/font/1_zh.ttf" }
FONT_2 = { "id":"FONT_2", "name": "漢王行楷", "path": BASE_MEDIA_PATH+"/font/2_tw.ttf" }
FONT_4 = { "id":"FONT_4", "name": "方正美黑_GBK", "path": BASE_MEDIA_PATH+"/font/4_zh.ttf" }
FONT_6 = { "id":"FONT_6", "name": "书体坊郭小语钢笔楷体", "path": BASE_MEDIA_PATH+"/font/6_zh.ttf" }
FONT_7 = { "id":"FONT_7", "name": "方正姚体简体", "path": BASE_MEDIA_PATH+"/font/7_zh.ttf" }
FONT_8 = { "id":"FONT_8", "name": "漢王鏤空", "path": BASE_MEDIA_PATH+"/font/8_tw.ttf" }
FONT_9 = { "id":"FONT_9", "name": "繁體正楷", "path": BASE_MEDIA_PATH+"/font/9_tw.ttf" }
FONT_10= { "id":"FONT_10","name": "猫啃什锦", "path": BASE_MEDIA_PATH+"/font/10_tw.ttf" }

FONT_11 = { "id":"FONT_11", "name": "JAPANESE_0", "path": BASE_MEDIA_PATH+"/font/japanese_1.ttf" }
FONT_12 = { "id":"FONT_12", "name": "JAPANESE_2", "path": BASE_MEDIA_PATH+"/font/japanese_2.ttf" }

FONT_13 = { "id":"FONT_13", "name": "ARABIC_0", "path": BASE_MEDIA_PATH+"/font/NotoSansArabic.ttf" } 

FONT_14 = { "id":"FONT_14", "name": "THAI_1", "path": BASE_MEDIA_PATH+"/font/NotoSansThai.ttf" }

FONT_15 = { "id":"FONT_15", "name": "ENGLISH_0", "path": BASE_MEDIA_PATH+"/font/general_0.ttf" }

FONT_15_1 = { "id":"FONT_15_1", "name": "ENGLISH_1", "path": BASE_MEDIA_PATH+"/font/general_1.ttf" }

FONT_16 = { "id":"FONT_16", "name": "TIBETAN_0", "path": BASE_MEDIA_PATH+"/font/NotoSerifTibetan.ttf" }

FONT_17 = { "id":"FONT_17", "name": "MONGOLIAN_0", "path": BASE_MEDIA_PATH+"/font/NotoSansMongolian.ttf" }

FONT_20 = { "id":"FONT_20", "name": "KOREAN_0", "path": BASE_MEDIA_PATH+"/font/NotoSansKR.ttf" }

FONTS_BY_LANGUAGE = {
    "zh": [FONT_0, FONT_1, FONT_4, FONT_6, FONT_7],
    "tw": [FONT_10,FONT_9, FONT_2, FONT_8],
    "general": [FONT_15, FONT_15_1],
    "jp": [FONT_11, FONT_12],
    "kr": [FONT_20],
    "ar": [FONT_13],
    "th": [FONT_14],
    "tib": [FONT_16],
    "mn": [FONT_17]
}

FONT_LIST = {
    "zh": FONT_0,
    "tw": FONT_10,
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

# =============================================================================
# FFmpeg配置
# =============================================================================
ffmpeg_path = "ffmpeg" 
ffprobe_path = "ffprobe"

# =============================================================================
# 语音配置
# =============================================================================

ROLES = [
    "",
    "female-host",
    "male-host",
    "actress",
    "actor",
    "female-host, male-host",
    "actor, actress"
]

SPEAKER_POSITIONS = [
    "left",
    "right"
]

HOSTS = [
    "1 female-host",
    "1 male-host",
    "1 female-host & 1 male-host",
    ""
]


ACTORS = [
    "",
    "1 actress & 1 actor",
    "1 actor",
    "1 actress"
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


VOICES_11_LAB = [
    "zh-CN-Yunyi:DragonHDFlashLatestNeural",
    "zh-CN-Yunfan:DragonHDLatestNeural",
    "zh-CN-Yunxiao:DragonHDFlashLatestNeural",
    "zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural",
    "zh-CN-Xiaochen:DragonHDFlashLatestNeural",
    "zh-CN-XiaoqiuNeural",
    "tw_m",
    "tw_f"
]


MOODS_11_LAB = [
    'general', 'cheerful', 'sad', 'angry', 'calm', 
    'excited', 'friendly', 'serious', 'dramatic', 'whisper'
] 

#   https://learn.microsoft.com/nb-no/azure/ai-services/speech-service/language-support?tabs=tts#voice-styles-and-roles
MOODS_AZURE = [
    'general', 'chat', 'hopeful', 'chat', 'affectionate', 'empathetic', 'disgruntled', 'gentle', 'cheerful', 'fearful', 'angry', 'calm', 
    'excited', 'unfriendly', 'friendly', 'serious', 'dramatic', 'whisper', 'customerservice', 'narration-casual'
] 


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


TRANSITION_EFFECTS = ["fade", "circleopen", "radial", "dissolve", "diagtl", "circleclose"]


# =============================================================================
# 图像生成配置
# =============================================================================
# 图像生成默认风格配置

ANIMATE_TARGET = ["I2V", "2I2V", "S2V", "FS2V", "WS2V", "AI2V"]
ANIMATE_I2V = ["I2V"]
ANIMATE_2I2V = ["2I2V"]
ANIMATE_S2V = ["S2V", "FS2V"]
ANIMATE_WS2V = ["WS2V"]
ANIMATE_AI2V = ["AI2V"]
ANIMATE_SOURCE = [""] + ANIMATE_I2V + ANIMATE_2I2V + ANIMATE_S2V + ANIMATE_WS2V + ANIMATE_AI2V

FACE_ENHANCE = ["0", "15", "30", "60"]


ANIMATE_TYPE_PATTERNS = [
    (r"_I2V(_\d{8})?\.mp4$", "_I2V"),
    (r"_2I2V(_\d{8})?\.mp4$", "_2I2V"),
    (r"_L_WS2V(_\d{8})?\.mp4$", "_L_WS2V"),
    (r"_R_WS2V(_\d{8})?\.mp4$", "_R_WS2V"),
    (r"_S2V(_\d{8})?\.mp4$", "_S2V"), # clip_project_20251208_1710_10708_S2V_13231028_60_.mp4
    (r"_FS2V(_\d{8})?\.mp4$", "_FS2V"),
    (r"_AI2V(_\d{8})?\.mp4$", "_AI2V")
]

ANIMATE_WITH_AUDIO = ["_L_WS2V", "_R_WS2V", "_S2V", "_FS2V"]


HOST_FIGURE_ACTIONS = [
    "Standing",
    "Walking",
    "Running",
    "Jumping",
    "Crying",
    "Laughing",
    "Praying"
]

SPECIAL_EFFECTS = [
    "still",
    "left",
    "right",
    "zoom in",
    "zoom out"
]


def get_next_special_effect():
    return SPECIAL_EFFECTS[0]




# =============================================================================
# 频道配置
# =============================================================================
CHANNEL_TYPE_TALK_START_FULL = "talk_start_full"
CHANNEL_TYPE_TALK_START_SIMPLE = "talk_start_simple"
CHANNEL_TYPE_STORY_START_SIMPLE = "story_start_simple"




# tubebuddy
channel_config = {
    "broadway_zh": {
        "topic": "Musical myths and legends",
        "background_music_length": 15,
        "channel_name": "圣经百老汇",
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_category_id": ["19", "25", "27", "24"],
        "channel_tags": ["religion", "bible", "musical", "music", "story", "broadway", "bible stories"],
        "channel_key": "config/client_secret_main.json",
        "channel_list": ""
    },
    "counseling_zh": {
        "topic": "Case Analysis of Psychological Counseling, Life Reflections",
        "background_music_length": 16,
        "channel_name": "心理龙门阵",
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_category_id": ["27", "24", "19"],
        "channel_tags": ["默观深省", "冥想", "静心", "心灵成长", "自我探索", "Inner peace", "Meditation", "Self-discovery", "心理咨询", "psychological counseling", "心理成长", "Psychology", "心时代，人人都是故事"],
        "channel_key": "config/client_secret_creative4teen.json"
    },
    "israle_zh": {
        "topic": "stories about Israel and the Bible",
        "background_music_length": 15,
        "channel_name": "走进圣地的故事",
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_category_id": ["19", "25", "27", "24"],
        "channel_tags": ["religion", "israel", "耶路撒冷", "Jerusalem", "palestine", "middle east", "Jews and Arabs", "以色列历史", "犹太人", "阿拉伯人", "中东", "伊斯兰"],
        "channel_key": "config/client_secret_main.json",
        "channel_list": ""
    },
    "strange_zh": {
        "topic": "** output: all in English\n** input: name of person in content, MUST BE Chinese name (like Qiang, Mei, etc)",
        "background_music_length": 15,
        "channel_name": "聊斋新语",
        "channel_type": CHANNEL_TYPE_TALK_START_FULL,
        "channel_category_id": ["24"],
        "channel_tags": ["聊斋志异", "现代寓言", "古今对照", "中国文化", "灵异故事", "Liaozhai", "Chinese ghost stories", "Modern social issues"],
        "channel_key": "config/client_secret_main.json"
    },
    "travel_zh": {
        "topic": "stories about travel",
        "background_music_length": 15,
        "channel_name": "旅途故事",
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_category_id": ["19", "24"],
        "channel_tags": ["旅行", "旅行故事", "旅行攻略", "旅行背景", "Travel stories", "Travel", "Travel experience", "Travel stories"],
        "channel_key": "config/client_secret_creative4teen.json"
    },
    "world_zh": {
        "topic": "stories about history",
        "background_music_length": 16,
        "channel_name": "观往晓来",
        "channel_category_id": ["25", "27"],
        "channel_tags": ["历史", "历史故事", "现实对比", "History stories", "History"],
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_key": "config/client_secret_creative4teen.json"
    }

}



YOUTUBE_CATEGORY_ID = [
  { "id": "1", "name_en": "Film & Animation", "name_zh": "電影與動畫" },
  { "id": "2", "name_en": "Autos & Vehicles", "name_zh": "汽車與車輛" },
  { "id": "10", "name_en": "Music", "name_zh": "音樂" },
  { "id": "15", "name_en": "Pets & Animals", "name_zh": "寵物與動物" },
  { "id": "17", "name_en": "Sports", "name_zh": "運動" },
  { "id": "18", "name_en": "Short Movies", "name_zh": "短片" },
  { "id": "19", "name_en": "Travel & Events", "name_zh": "旅遊與活動" },
  { "id": "20", "name_en": "Gaming", "name_zh": "遊戲" },
  { "id": "21", "name_en": "Videoblogging", "name_zh": "影片部落格" },
  { "id": "22", "name_en": "People & Blogs", "name_zh": "人物與部落格" },
  { "id": "23", "name_en": "Comedy", "name_zh": "喜劇" },
  { "id": "24", "name_en": "Entertainment", "name_zh": "娛樂" },
  { "id": "25", "name_en": "News & Politics", "name_zh": "新聞與政治" },
  { "id": "26", "name_en": "Howto & Style", "name_zh": "教學與風格" },
  { "id": "27", "name_en": "Education", "name_zh": "教育" },
  { "id": "28", "name_en": "Science & Technology", "name_zh": "科學與科技" },
  { "id": "29", "name_en": "Nonprofits & Activism", "name_zh": "非營利與社會運動" },
  { "id": "30", "name_en": "Movies", "name_zh": "電影" },
  { "id": "31", "name_en": "Anime/Animation", "name_zh": "動漫／動畫" },
  { "id": "32", "name_en": "Action/Adventure", "name_zh": "動作／冒險" },
  { "id": "33", "name_en": "Classics", "name_zh": "經典" },
  { "id": "34", "name_en": "Comedy", "name_zh": "喜劇（影片分類）" },
  { "id": "35", "name_en": "Documentary", "name_zh": "紀錄片" },
  { "id": "36", "name_en": "Drama", "name_zh": "戲劇" },
  { "id": "37", "name_en": "Family", "name_zh": "家庭" },
  { "id": "38", "name_en": "Foreign", "name_zh": "外語" },
  { "id": "39", "name_en": "Horror", "name_zh": "恐怖" },
  { "id": "40", "name_en": "Sci-Fi/Fantasy", "name_zh": "科幻／奇幻" },
  { "id": "41", "name_en": "Thriller", "name_zh": "驚悚" },
  { "id": "42", "name_en": "Shorts", "name_zh": "短片（影片分類）" },
  { "id": "43", "name_en": "Shows", "name_zh": "節目" },
  { "id": "44", "name_en": "Trailers", "name_zh": "預告片" }
]
