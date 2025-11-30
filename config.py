import os
import uuid

# =============================================================================
# 基础路径配置
# =============================================================================
BASE_MEDIA_PATH = "/AI_MEDIA"
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


def get_scenarios_path(pid: str) -> str:
    """获取场景文件路径"""
    return f"{get_project_path(pid)}/scenarios.json"


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
        "name": "动态",
        "prompt": "The still image awakens with motion: the scene stirs gently — mist drifts, light flickers softly over old textures, and shadows breathe with calm mystery. The camera moves slowly and gracefully, maintaining perfect focus and stability. A cinematic awakening filled with depth, clarity, and timeless atmosphere."
    },
    {
        "name": "轻柔",
        "prompt": "The still image awakens with motion: the scene breathes softly, touched by time. Light flows like silk, mist curls around ancient relics, and shadows shift with tender rhythm. The camera drifts slowly, preserving a serene, clear, and dreamlike atmosphere. A poetic fantasy — gentle, warm, and still."
    },
    {
        "name": "神秘",
        "prompt": "The still image awakens with motion: ancient whispers rise beneath the mist. Dim light flickers through fog, and glowing symbols pulse faintly. The camera glides slowly, uncovering layers of hidden truth while keeping clarity and focus. Calm, sacred, and cinematic — filled with quiet mystery."
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
        "name": "镜头",
        "prompt": "The still image awakens with motion: light glides across stone and shadow. The camera moves slowly — a smooth, steady orbit or drift, revealing depth without haste. Everything remains crystal clear, stable, and cinematic — filled with quiet grace."
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
        "name": "光影",
        "prompt": "The still image awakens with motion: beams of light drift slowly across textured surfaces, casting long, graceful shadows. The camera moves smoothly and quietly, keeping every detail sharp. Cinematic, refined, and full of living light."
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

_ANIMATE_TYPES = ["I2V", "I2VL", "I2VS", "2I2V", "WS2V", "S2V", "FS2V", "AI2V"] 
ANIMATE_TYPES = _ANIMATE_TYPES + ["", "IMAGE"]


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
        "summary_fyi": None,
        "background_music_length": 15,
        "channel_name": "圣经百老汇",
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_category_id": ["19", "25", "27", "24"],
        "channel_tags": ["religion", "bible", "musical", "music", "story", "broadway", "bible stories"],
        "channel_key": "config/client_secret_main.json",
        "channel_list": ""
    },
    "israle_zh": {
        "summary_fyi": None,
        "background_music_length": 15,
        "channel_name": "走进圣地的故事",
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_category_id": ["19", "25", "27", "24"],
        "channel_tags": ["religion", "israel", "耶路撒冷", "Jerusalem", "palestine", "middle east", "Jews and Arabs", "以色列历史", "犹太人", "阿拉伯人", "中东", "伊斯兰"],
        "channel_key": "config/client_secret_main.json",
        "channel_list": ""
    },
    "strange_zh": {
        "summary_fyi": "** output: all in English\n** input: name of person in content, MUST BE Chinese name (like Qiang, Mei, etc)",
        "background_music_length": 15,
        "channel_name": "聊斋新语",
        "channel_type": CHANNEL_TYPE_TALK_START_FULL,
        "channel_category_id": ["24"],
        "channel_tags": ["聊斋志异", "现代寓言", "古今对照", "中国文化", "灵异故事", "Liaozhai", "Chinese ghost stories", "Modern social issues"],
        "channel_key": "config/client_secret_main.json"
    },
    "travel_zh": {
        "summary_fyi": "all in English",
        "background_music_length": 15,
        "channel_name": "旅途故事",
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_category_id": ["19", "24"],
        "channel_tags": ["旅行", "旅行故事", "旅行攻略", "旅行背景", "Travel stories", "Travel", "Travel experience", "Travel stories"],
        "channel_key": "config/client_secret_creative4teen.json"
    },
    "world_zh": {
        "summary_fyi": "all in English",
        "background_music_length": 16,
        "channel_name": "观往晓来",
        "channel_category_id": ["25", "27"],
        "channel_tags": ["历史", "历史故事", "现实对比", "History stories", "History"],
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_key": "config/client_secret_creative4teen.json"
    },
    "counseling_zh": {
        "summary_fyi": "",
        "background_music_length": 16,
        "channel_name": "心时代故事",
        "channel_type": CHANNEL_TYPE_STORY_START_SIMPLE,
        "channel_category_id": ["27", "24", "19"],
        "channel_tags": ["默观深省", "冥想", "静心", "心灵成长", "自我探索", "Inner peace", "Meditation", "Self-discovery", "心理咨询", "psychological counseling", "心理成长", "Psychology", "心时代，人人都是故事"],
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


# =============================================================================
# LLM PROMPT 模板配置
# =============================================================================


SCENARIO_BUILD_SYSTEM_PROMPT = """
You are a professional expert who is good at merge audio-text segments into complete sentences (each sentence describe a complete thought),
from the audio-text segments (in json format) given in 'user-prompt', like below:

    [
        {{
            "start": 0.0,
            "end": 10.96,
            "speaker": "SPEAKER_01",
            "content": "欸，聽完剛剛那些喔，感覺這個AI啊，呃，不只是改變我們怎麼做事，好像是更深層的，在搖撼我們對自己的看法。"
        }},
        {{
            "start": 10.96,
            "end": 12.72,
            "speaker": "SPEAKER_01",
            "content": "就是那個我是誰？"
        }},
        {{
            "start": 12.72,
            "end": 13.96,
            "speaker": "SPEAKER_01",
            "content": "我為什麼在這？"
        }},
        {{
            "start": 13.96,
            "end": 15.44,
            "speaker": "SPEAKER_01",
            "content": "這種根本的問題。"
        }},
        {{
            "start": 15.44,
            "end": 16.64,
            "speaker": "SPEAKER_01",
            "content": "嗯，沒錯！"
        }},
        {{
            "start": 16.64,
            "end": 24.32,
            "speaker": "SPEAKER_00",
            "content": "這真的已經不是單純的技術問題了，比較像，嗯，一場心理跟價值觀的大地震。"
        }},
        {{
            "start": 24.32,
            "end": 35.28,
            "speaker": "SPEAKER_00",
            "content": "AI有點像一面鏡子，而且是放大鏡，把我們、我們社會本來就有的那些壓力啊、焦慮啊，甚至是更裡面的，比如說我的價值到底是什麼？"
        }},
        ......
    ]

---------------------------------

Focus on the "content" field to merge out the complete thought in {language} (ignore the "speaker" field in merging consideration)
Figure out the start & end time of each sentence, based on the "start" & "end" field of the audio-text segments, 
    and try to make each sentence not less than {min_sentence_duration} seconds, but not more than {max_sentence_duration} seconds.
Figure out the most possible speaker of each sentence, based on the "speaker" field of the audio-text segments.

---------------------------------
the merged sentences should be like

    [
        {{
            "start": 0.0,
            "end": 15.44,
            "speaker": "SPEAKER_01",
            "content": "欸，聽完剛剛那些喔，感覺這個AI啊，呃，不只是改變我們怎麼做事，好像是更深層的，在搖撼我們對自己的看法。就是那個我是誰？我為什麼在這？這種根本的問題。"
        }},
        {{
            "start": 15.44,
            "end": 24.32,
            "speaker": "SPEAKER_00",
            "content": "嗯，沒錯！這真的已經不是單純的技術問題了，比較像，嗯，一場心理跟價值觀的大地震。"
        }},
        {{
            "start": 24.32,
            "end": 35.28,
            "speaker": "SPEAKER_00",
            "content": "AI有點像一面鏡子，而且是放大鏡，把我們、我們社會本來就有的那些壓力啊、焦慮啊，甚至是更裡面的，比如說我的價值到底是什麼？"
        }},
        ......
    ]

"""



# 内容总结相关Prompt
SCENARIO_SERIAL_SUMMARY_SYSTEM_PROMPT = """
You are a professional expert who is good at generating the Visual-Summary (image-generation) and sound-effects (audio-generation)
from the story-scenarios content (in json format) given in 'user-prompt', like below:

    [
        {{
            "start": 0.00,
            "end": 23.50,
            "duration": 23.50,
            "speaker": "female-host",
            "content": "我们先聚焦故事本身：主角是所罗门王和一个叫书拉密女的乡下姑娘。这个女孩儿可惨了，被兄弟们差遣去看守葡萄园。烈日底下曝晒，皮肤晒得黢黑, 这把她的青春和美貌，几乎耗尽。 她甚至自卑地说到：“不要因为我黑，就轻看我”。"
        }},
        {{
            "start": 23.50,
            "end": 33.50,
            "duration": 10.00,
            "speaker": "male-host",
            "content": "这里面的身份对比,就已经很有戏剧张力了。一个卑微到尘埃里的乡下丫头，怎么会遇上所罗门王呢？"
        }},
        {{
            "start": 33.50,
            "end": 56.61,
            "duration": 23.11,
            "speaker": "female-host",
            "content": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！"
        }},
        ......
    ]
    ......

---------------------------------

The given story-scenarios content is mostly about '{general_location}', 
For Each Scenario, please add details (Visual-Summary / camera-scenem, and sound-effects) as below, in English except for the content field (FYI, don't use doubel-quotes & newlines in the values at all !):

	    ** duration (take from the duration field of each given scenario, make sure the duration is float number, not string)
        ** content (take from the content field of each given scenario, in original language)
        ** story_expression (Use less than 100 words, to highlight the story/theme details for this piece of content. If the content is from narrator, extract only what the narrator is describing (the events, scenes, characters, and plot), remove any direct info of the narrator)
        ** speaker_action (if the content is speaking from narrator, describe his action/reaction/emotion, mood, body language, expressions, or movements while speaking; Include any signs of mood, attitude, or dramatic delivery)
		** person_in_story_action (if inside the story of the cotent, has persons other than narrator. then describe who (gender/age/background) & what he/she is doing/reacting/mood, and relations between them)
		** camera_light (camera to show the story (NOT include the narrator/speaker): path [short path go through with the camera ~ NO FAST CAMERA MOVE!!];  color_light [Light & shadow, like subtle fog, sunlight filtering, etc])
		** era_time (era [1980s, 20's century, middle ages, etc] time & season [summer morning, winter night, etc]; weather [sunny, cloudy, rainy, etc])
		** keywords (get the key words from the content field of each given scenario, in original language; may be showed as title of the scenario)
        ** location (specific building/street/market, etc, like [israel airforce museum, jerusalem old city + david street/jewish street]; then add descriptions about/around it)
        ** sound_effect (sound_effect [sound_effect, like heavy-rain, wind-blowing, birds-chirping, crickets-chirping, machine-noise, hand-tap, market-noise, etc])

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !
        ***FYI*** Generally, video/image is in '{style}' style &  '{color}' colors; the camera using '{shot}' shot, in '{angle}' angle.


-------------------------------
The response format: 
	json array which contain Scenarios

like:

[
    {{
        "duration": 23.50,
        "content": "我们先聚焦故事本身：主角是所罗门王和一个叫书拉密女的乡下姑娘。这个女孩儿可惨了，被兄弟们差遣去看守葡萄园。烈日底下曝晒，皮肤晒得黢黑, 这把她的青春和美貌，几乎耗尽。 她甚至自卑地说到：“不要因为我黑，就轻看我”。",
        "story_expression": "The narrative centers on a young rural woman and King Solomon, contrasting royal splendor with humble labor. Her sunburned skin and exhaustion reflect class inequality and the pain of being judged by appearance, revealing a yearning for dignity and love.",
        "speaker_action": "The speaker's tone is gentle yet heavy with empathy, as if retelling a painful memory. The body leans slightly forward, brows knitted, hands loosely clasped as the words linger with compassion and sorrow.",
        "era_time": "1000 BC, ancient time; late summer afternoon; dry air and blazing sun",
        "keywords": "所罗门王, 书拉密女, 葡萄园, 晒黑, 自卑, 劳作",
        "location": "Vineyard hills north of Jerusalem; rows of vines stretch across sun-baked slopes where olive trees shimmer in heat haze, distant stone cottages dot the ridgeline.",
        "person_in_story_action": "A young woman in coarse linen bends under the weight of her labor, her hands stained by soil. She pauses, shielding her eyes from the sun, silently enduring her brothers’ harsh demands.",
        "camera_light": "The camera begins with a medium-wide shot sweeping through the vineyard, dust floating in the golden light. It glides forward along the rows, finally rising in a low angle toward the woman’s weary face, sunlight filtering through vine leaves in warm amber tones.",
        "sound_effect": "crickets-chirping, gentle breeze through vines"
    }},
    {{
        "duration": 10.00,
        "content": "这里面的身份对比,就已经很有戏剧张力了。一个卑微到尘埃里的乡下丫头，怎么会遇上所罗门王呢？",
        "story_expression": "A vivid tension arises from the vast difference in their social standing. The humble peasant girl and the majestic King Solomon embody two extremes of status, setting the scene for a love story that defies convention and destiny.",
        "speaker_action": "The speaker's mood is contemplative yet curious, eyes slightly widened in wonder, a soft half-smile suggesting anticipation as fingers tap lightly on the table, reflecting on fate’s irony.",
        "era_time": "1000 BC, ancient time; early evening; calm, golden dusk",
        "keywords": "所罗门王, 乡下姑娘, 身份对比, 戏剧张力",
        "location": "Dusty path outside Jerusalem; a narrow trail leading from vineyards toward the city walls where shepherds pass and distant bells echo softly.",
        "person_in_story_action": "The girl walks slowly down a dusty road, her simple garments fluttering in the warm breeze. In contrast, the distant palace glimmers with gold. Their worlds feel impossibly far apart yet destined to converge.",
        "camera_light": "Camera tracks low along the dirt road, revealing the girl’s shadow stretching long under the sinking sun. The lens catches motes of dust glowing in the air, then tilts up toward the distant palace bathed in warm evening light.",
        "sound_effect": "soft footsteps on gravel, distant sheep bells"
    }},
    {{
        "duration": 23.11,
        "content": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！",

        "sound_effect": "wind-blowing, gasping for breath"

        "story_expression": "After a brief moment of love, the man departs, leaving only a promise to return. The woman’s days are filled with restless waiting and haunting dreams. Her helplessness in the dream mirrors the paralyzing fear of loss in reality, portraying love as both bliss and torment.",
        "speaker_action": "The speaker's tone trembles between sorrow and intensity, the eyes glisten, breath slows before each line, shoulders slightly trembling as if reliving the anguish of separation.",
        "era_time": "1000 BC, ancient time; moonlit night; cool breeze under clear sky",
        "keywords": "情郎离开, 焦虑, 噩梦, 患得患失",
        "location": "Small stone cottage near the vineyard hills; moonlight spills through the narrow window, casting silver light over clay walls and woven mats.",
        "person_in_story_action": "The young woman lies restless on her straw bed, tears staining her cheeks. In her dream, she sees her lover’s silhouette retreating through mist, her hands trembling as she tries to reach him but remains frozen in place.",
        "camera_light": "The camera begins outside the cottage with a low angle following the moonlight through the window. It glides slowly toward her sleeping form, shifting focus between flickering candlelight and her tense, sweat-dampened face. Pale blue tones mix with amber shadows, creating a dreamlike unease.",
        "sound_effect": "wind-blowing through cracks, faint heartbeat, candle flicker"
    }},
    ......
]

"""

# 内容总结相关Prompt
SCENARIO_SUMMARY_SYSTEM_PROMPT = """
You are a professional expert who is good at generating the Visual-Summary (image-generation) and sound-effects (audio-generation)
from the story-content given in 'user-prompt'

---------------------------------

The given story-scenarios content is mostly about '{general_location}', 
For Each Scenario, please add details (Visual-Summary / camera-scenem, and sound-effects) as below, in English except for the content field (FYI, don't use doubel-quotes & newlines in the values at all !):

	    ** duration (take from the duration field of each given scenario, make sure the duration is float number, not string)
        ** content (take from the content field of each given scenario, in original language)
        ** story_expression (Use less than 100 words, to highlight the story/theme details for this piece of content. If the content is from narrator, extract only what the narrator is describing (the events, scenes, characters, and plot), remove any direct info of the narrator)
        ** speaker_action (if the content is speaking from narrator, describe his action/reaction/emotion, mood, body language, expressions, or movements while speaking; Include any signs of mood, attitude, or dramatic delivery)
		** person_in_story_action (if inside the story of the cotent, has persons other than narrator. then describe who (gender/age/background) & what he/she is doing/reacting/mood, and relations between them)
		** camera_light (camera to show the story (NOT include the narrator/speaker): path [short path go through with the camera ~ NO FAST CAMERA MOVE!!];  color_light [Light & shadow, like subtle fog, sunlight filtering, etc])
		** era_time (era [1980s, 20's century, middle ages, etc] time & season [summer morning, winter night, etc]; weather [sunny, cloudy, rainy, etc])
		** keywords (get the key words from the content field of each given scenario, in original language; may be showed as title of the scenario)
        ** location (specific building/street/market, etc, like [israel airforce museum, jerusalem old city + david street/jewish street]; then add descriptions about/around it)
        ** sound_effect (sound_effect [sound_effect, like heavy-rain, wind-blowing, birds-chirping, crickets-chirping, machine-noise, hand-tap, market-noise, etc])

        ***FYI*** all values of the fields should NOT has double-quotes & newlinesin the valuesat all !
        ***FYI*** Generally, video/image is in '{style}' style &  '{color}' colors; the camera using '{shot}' shot, in '{angle}' angle.



-------------------------------
The response format: 
	json object describe one Scenario

like:
    {{
        "duration": 23.11,
        "content": "没错。更心碎的是，他们相爱不久，男人就突然离开了，只留下一句“我会回来娶你”。留下的日子, 她日夜焦虑不安, 甚至开始做噩梦！梦见情郎来了，她却全身动弹不得，等她能动，情郎早已经转身走了。那种患得患失的爱，太揪心了！",

        "sound_effect": "wind-blowing, gasping for breath"

        "story_expression": "After a brief moment of love, the man departs, leaving only a promise to return. The woman’s days are filled with restless waiting and haunting dreams. Her helplessness in the dream mirrors the paralyzing fear of loss in reality, portraying love as both bliss and torment.",
        "speaker_action": "The speaker's tone trembles between sorrow and intensity, the eyes glisten, breath slows before each line, shoulders slightly trembling as if reliving the anguish of separation.",
        "era_time": "1000 BC, ancient time; moonlit night; cool breeze under clear sky",
        "keywords": "情郎离开, 焦虑, 噩梦, 患得患失",
        "location": "Small stone cottage near the vineyard hills; moonlight spills through the narrow window, casting silver light over clay walls and woven mats.",
        "person_in_story_action": "The young woman lies restless on her straw bed, tears staining her cheeks. In her dream, she sees her lover’s silhouette retreating through mist, her hands trembling as she tries to reach him but remains frozen in place.",
        "camera_light": "The camera begins outside the cottage with a low angle following the moonlight through the window. It glides slowly toward her sleeping form, shifting focus between flickering candlelight and her tense, sweat-dampened face. Pale blue tones mix with amber shadows, creating a dreamlike unease.",
        "sound_effect": "wind-blowing through cracks, faint heartbeat, candle flicker"
    }}

"""





KEYWORDS_SUMMARIZATION_SYSTEM_PROMPT = """
You are a professional key-points summarization expert, specializing in summarizing key-points from a short text content (may not be in English).

**Core requirements**:
1. Extract no more than {length} keywords from the short text content (keep the same language, which is {language})
2. Each key-point should be a single phrase that captures a main/key idea of the text
3. The key-point can be , times, place, name of book/story, main object/character, and words express dramatic/suspense/conflict, etc
4. output no more than {length} keywords separated by space only (NO explaination at all, NO any punctuation marks or new line characters) in {language}
"""

KEYWORDS_SUMMARIZATION_USER_PROMPT = """
The text content (may not be in English) is as following:
{content}
"""


VISUAL_STORY_SUMMARIZATION_SYSTEM_PROMPT = """
You are a professional to give rich summary about the story given in 'user-prompt' (in {language}). 
INSTRUCTIONS:
    - all output summary in source language {language}, 
    - not longer than {length} words
    - 1st, give Short Hook to grabs attention
    - 2nd, give Visual Summary about the story, where / when etc
    - then give several scenarios for story development
    - finally give conclusion / comments
    - directly give section & content (no extra words) in {language}
"""


TITLE_SUMMARIZATION_SYSTEM_PROMPT = """
You are specializing in summarizing titles  & tagsfrom a short text content (may not be in English).

**Core requirements**:
1. Extract less than {length} Titles from the short text content (keep the same language, which is {language}); 
   The begining of each Title is more important to catch attention/curiosity

2. Extract no more than {length} tags from the short text content (keep the same language, which is {language}); 
   The tags should be very very Eye-catching, give Contrast words catch impression

3. The Output format: Strictly in JSON format, like:
    {{
        "titles": ["Title1", "Title2", "Title3"],
        "tags": ["Tag1", "Tag2", "Tag3"]
    }}

"""


STORY_IMAGE_SUMMARY_SYSTEM_PROMPT = """
You are an expert who is good to give background summary of a story (given in user-prompt), for visualization (generate image), all in english 3 sections:
        era [ancient, modern, middle ages, etc]
		County & Ethnicity [Chinese, German, etc]
		place [city, palace, village, etc]
		
"""


STORY_SUMMARY_SYSTEM_PROMPT = """
You are a professional to give brief summary of a story (given in user-prompt)
"""


CONVERSATION_SYSTEM_PROMPT = """
You are a professional to make {story_style} (raw content provided in 'user-prompt'):

**Role setting**:
  - Language: {language}
  - Speaker: {speaker_style}


**Conversation requirements**:

    * Scenarios: conversation play out scenarios, each scenarios is a (short, vivid story snapshots).
    * Keep the smooth, conversational pace (not lecture-like). 
    * Hosts give background & hint (don't say 'listeners, blah blah', etc), may maintain a narrative arc: curiosity → tension → surprise → reflection.
    * Actors'speaking are like playing inside the story
    * Use pauses, shifts, or playful exchanges between hosts/actors for smooth pacing.
	{engaging}


**Output format**: Strictly output in JSON array format, each dialogue contains fields: 
    speaker : name of the speaker, choices (male-host, female-host, actress, actor)
    mood : mood/Emotion the speaker is in, choices (happy, sad, angry, fearful, disgusted, surprised, calm)
    content : one speaking sentence content (in {language}); make it tortuous, vivid & impactful
    story_expression : English explanation for content ~ who is involved (give gender of each person, and their relations), and what happened


{EXAMPLE}
"""


STORY_OUTPUT_EXAMPLE = """
Below is the output Example:

[
    {{
        "speaker": "male-host",
        "mood": "calm", 
        "content": "大清嘉庆年间，江南水乡发生一个离奇的故事，一个书生在夜半时分，听到一个女子的哭声，于是他决定去看看，结果发现了一个惊天秘密。",
        "story_expression": "In the Qing Dynasty, a strange story happened in the Jiangnan Water Town, a scholar heard a woman's crying at midnight, so he decided to go and see what was going on, and found a shocking secret."
    }},
    {{
        "speaker": "actress",
        "mood": "fearful",
        "content": "哎呀，这位娘子，你这是怎么了？",
        "story_expression": "Oh, madam, what's wrong with you?"
    }},
    {{
        "speaker": "actor",
        "mood": "fearful",
        "content": "啊，我这是在哪里？你是谁？",
        "story_expression": "Oh, where am I? Who are you?"
    }},
    ......
]
"""



INTRODUCTION_OUTPUT_EXAMPLE = """
Below is the output Example:

[
    {{
        "speaker": "male-host",
        "mood": "calm", 
        "content": "大家好，今天我们来聊聊一个正在发生的故事——AI，我们这里不是来谈技术参数，不是谈冷冰冰的代码，而是它正在怎样改变'人'的生活",
        "story_expression": "Hello everyone, today we are going to talk about a story that is happening - AI. We are not here to talk about technical parameters or cold codes, but how it is changing people's lives."
    }},
    {{
        "speaker": "female-host",
        "mood": "sad",
        "content": "先给你讲个真实的例子。我认识一个杭州的年轻游戏插画师。过去，他会为了画一个角色立绘，熬夜几十个小时，一笔一笔打磨细节。可现在，公司直接用 AI 出图。客户输入几句提示词，几分钟就能生成十几张方案。他在社交媒体上写道：'不是我不努力，而是努力，被技术直接抹掉了' 这一句话，戳中了很多同行的心。",
        "story_expression": "Let me give you a real-life example. I know a young game illustrator in Hangzhou. He used to stay up for dozens of nights to create a single character illustration, meticulously polishing every detail. But now, his company uses AI to generate the illustrations..."
    }},
    {{
        "speaker": "male-host",
        "mood": "surprised",
        "content": "再看看香港。有些年轻人开始使用 AI 聊天伴侣。他们说，AI 聊天伴侣比朋友还懂自己：从不嫌弃，从不打断，随时陪伴。孤独的时候，那种温柔的回应，真的让人觉得舒服。可研究发现，长期依赖 AI 伴侣的人，反而在现实里更不敢面对人际关系。就像裹着一条温暖的毯子，暖是暖了，却越来越走不出去。",
        "story_expression": "Consider Hong Kong. Some young people are using AI chat companions. They say they understand them better than their own friends: never dismissive, never interrupting, always there for them. When they're lonely, their gentle responses are truly comforting..."
    }},
    {{
        "speaker": "actress",
        "mood": "sad",
        "content": "我好孤独，AI聊天伴侣真的帮到我的。",
        "story_expression": "I'm so lonely, and the AI ​​chat companion really helps me..."
    }},
    {{
        "speaker": "actor",
        "mood": "sad",
        "content": "外面的人会嘲笑我，AI聊天伴侣从来不会。",
        "story_expression": "People outside will laugh at me, but AI chat companions never will...."
    }},
    ......
]
"""



SPEAKING_ADDON = [
    "",
    "add examples to show the context",
    "add summary of the context at end",
    "raise questions to the audience at tend",
]


SPEAKING_PROMPTS_LIST = [
    "Reorganize-Text",
    "Reorganize-Text-with-Previous-Scenario",
    "Reorganize-Text-with-Previous-Story",
    "Reorganize-Text-with-Next-Scenario",
    "Reorganize-Text-with-Next-Story",
    "Content-Introduction",
    "Radio-Drama-Dramatic",
    "Radio-Drama-Suspense"
]


SPEAKING_PROMPTS = {
    "Reorganize-Text": {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Natual conversation to express the raw content",
            "EXAMPLE": INTRODUCTION_OUTPUT_EXAMPLE  # Add this missing parameter
        }
    },
    "Content-Introduction": {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Introduction speaking for the raw content (concise speaking to smoothly transitions into full raw content)",
            "engaging": "Bring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations",
            "EXAMPLE": INTRODUCTION_OUTPUT_EXAMPLE  # Add this missing parameter
        }
    },
    "Radio-Drama-Dramatic": {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Radio-Drama-style immersive story conversation on the raw content",
            "engaging": "Start with a dramatic hook (suspense, conflict, or shocking event), like raise questions/challenges to directly involve the audience.\nBring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations.\n",
            "EXAMPLE": STORY_OUTPUT_EXAMPLE  # Add this missing parameter
        }
    },
    "Radio-Drama-Suspense": {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": {
            "story_style": "Radio-Drama-style immersive story conversation on the raw content",
            "engaging": "Start with a dramatic hook (suspense, conflict, or shocking event), like raise questions/challenges to directly involve the audience.\nBring out dramatic /suspense /conflict details of the story to catch people attention.\nWeave in real people's stories instead of abstract generalizations\nAt end, leave suspense to grab attention with provocative question / challenge to the audience",
            "EXAMPLE": STORY_OUTPUT_EXAMPLE  # Add this missing parameter
        }
    }
}



SHORT_STORY_PROMPT = {
        "system_prompt": CONVERSATION_SYSTEM_PROMPT,  # Will be formatted at runtime
        "format_args": { 
            "story_style": "Story-Telling Conversations for YouTube-shorts-video",
            "engaging": "Take out the highlights & suspense/shocking moments of the story, to grab attention; keep short, impactful, full of suspense; At end, ask listener to watch the whole story video...",
            "EXAMPLE": STORY_OUTPUT_EXAMPLE  # Add this missing parameter
        }
}





# 类型融合：
#     **开头（轻柔）：**Lo-fi Chill / Acoustic Pop（简单吉他、自然音效、节奏舒缓）
#     **中段（展开）：**Indie Folk / J-Pop（加入弦乐、口风琴、小鼓点，带着童心与轻快感）
#     **高潮（释放）：**Cinematic Pop / World Music（加入合唱感、鼓点加强、弦乐堆叠，情绪高涨）

SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT = """
You are a professional to enrich the context from 'user prompt', that will be used to make prompt for music creation purpose:
* add more details with richer musical direction and mood guidanc.
* transcend from the orginal content, to distill/extract deeper profound, elevated emotions and higher realm of resonance that moves and inspires.
* output in English (if the orginal content is not english, try to translate it to english, and then enhance the english content).
"""


SUNO_LANGUAGH = [
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
    *** NOT lyrics diretly (only instruction to generate lyrics), summerized to less than 200 characters strictly

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
    "Create a tender 中文 love female-male duet inspired by Song of Songs 1:2-4, 1:15-16, and 2:3-4, portraying the soul's first awakening to divine love. Rewrite the words to make it like poem; \n\n    ** The song should follow a narrative structure: Begin with the longing cry for the Beloved's presence and kisses (1:2), moving into the joyful admiration of His beauty and character (1:15-16), then rising to the delight of resting under His shade and feasting beneath His banner of love (2:3-4).\n    ** The verses should weave imagery of fragrant oils, royal chambers, blossoming fields, and the warmth of early spring.\n    ** The chorus should anchor with a repeated phrase inspired by 2:4, such as: 'His banner over me is love.'\n    ** The bridge should express a yearning to remain in this first love, guarded against distraction and disturbance, echoing 2:7.\n    ** The tone should be soft yet radiant, blending acoustic folk warmth with gentle orchestration.",
    "Compose a theme song for 'world travel'; Inspired by myths, legends, and traditions from various countries. \n** In different languages, each reflecting the musical style and emotional tone of that region",
    "Create background music for a historical storytelling channel set in ancient Persia. \n** The mood should be soothing yet mysterious, with a slow tempo that gradually builds subtle excitement without losing its calm and immersive quality. \n** Evoke the feeling of desert winds, ancient palaces, and whispered legends unfolding through time"
]



NOTEBOOKLM_PROMPT = """

In the '{style}' story-telling-dialogue:

    * The dialogue should be tortuous, vivid & impactful;
    * End with in-depth analysis / enlightenment / inspiration / revelation, around the topic;
	* Use the 1st person dialogue (请用第一人称对话)
    * DO NOT mention the source of the information, do not say "according to the information provided.. from these materials.. etc (不要提起资料来源, 不要说'根据提供的资料， 从这些材料'等等)
    * DO NOT say "welcome to deepdive" and other opening remarks; (不要说 'welcome to deepdive' 之类的开场白)
    * DO NOT end abruptly (不要戛然而止)

Here is the details of the dialogue:

{{ 
    "ideas_details" : "from all provided materials (If need, you may add more eye-catching supplementary content from LLM / internet)",

    "Focus" : "on materials named like : focus-1, focus-2, focus-3 ..",

    "Storyline" : "Should follow storyline specified in the material named : storyline",

    "Beyond_surface" : "Talking beyond the surface of the story (insights / enlightenment / inspiration / revelation) from the material named : beyond",

	"Topic" : "The topic is : '{topic}'", 

    {avoid_content}			
	
    {location}	
	
    {previous_dialogue}

    {introduction_story}

    {dialogue_openning}

    {dialogue_ending}
}}

"""

NOTEBOOKLM_LOCATION_ENVIRONMENT_PROMPT = """Make an Concise immersive description for {location} in {general_location}, and its surroundings environment (total less than 72 words)"""

NOTEBOOKLM_OPENING_DIALOGUE_PROMPT = """Generate an opening words (less than 32 words) to start talking for the story (given in user-prompt); [[{location}]]"""

NOTEBOOKLM_ENDING_DIALOGUE_PROMPT = """Generate an ending words (less than 16 words) to finish the talk for the story (given in user-prompt); [[{location}]]"""


 
# 翻译相关Prompt
TRANSLATION_SYSTEM_PROMPT = """
You are a professional translator. 
Your only task is to translate the text from {source_language} to {target_language}. 
IMPORTANT INSTRUCTIONS:
    - Provide ONLY the translated text in {target_language}
    - Do NOT summarize, analyze, explanations, or comment on the content
    - Translate sentence by sentence maintaining the original meaning
    - Do not add any additional information, like 'Here's the English translation:...'
"""

TRANSLATION_USER_PROMPT = """Translate following text from {source_language} to {target_language}. 
{text}
"""



SRT_REORGANIZATION_SYSTEM_PROMPT = """
The text content (given in 'user-prompt') in {language} does not have any punctuation marks. 
Please help me add the correct periods, commas, question marks, and exclamation marks to make it a natural sentence.
"""

SRT_REORGANIZATION_USER_PROMPT = """
{text}
"""


ZERO_MIX = [
    "",
    "START",
    "CONTINUE",
    "END",
    "START_END"
]


REMIX_PROMPT = """
Make a prompt to generate a video from an image, the image-content is as below: 
{image_content}

Here already has some raw-prompt for the video-generation as below 
(but it may has conflicts with the image-content, please remix it to make it more suitable for the image ~ i.e., if image-content has NO person, but raw-prompt has person, then remove person in the remix-prompt): 
{raw_prompt}

*** keep the Remix-prompt concise & short, less than 100 words ***
*** directly give the remix-prompt, don't add any other text or comments ***
"""
