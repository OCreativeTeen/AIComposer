from urllib.parse import urlparse, parse_qs

from utility.audio_transcriber import AudioTranscriber
from utility.youtube_downloader import YoutubeDownloader
from utility.sd_image_processor import SDProcessor
from utility.ffmpeg_processor import FfmpegProcessor
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
import os
import json
import shutil
import re
from pathlib import Path
import config
import config_prompt
import config_channel
from io import BytesIO
from utility.file_util import get_file_path, safe_remove, refresh_scene_media, build_scene_media_prefix
from utility.minimax_speech_service import MinimaxSpeechService
from gui.image_prompts_review_dialog import IMAGE_PROMPT_OPTIONS, NEGATIVE_PROMPT_OPTIONS
from utility.llm_api import LLMApi
import project_manager
import tkinter as tk



class MagicWorkflow:

    def __init__(self, pid, language, channel, video_width=None, video_height=None):
        self.pid = pid
        self.language = language
        self.channel = channel
        
        # 全局线程管理
        self.background_threads = []

        # Get video dimensions from parameters or load from project config
        if video_width is None or video_height is None:
            # Try to load from project config
            try:
                from project_manager import ProjectConfigManager
                config_manager = ProjectConfigManager(pid)
                if project_manager.PROJECT_CONFIG:
                    video_width = project_manager.PROJECT_CONFIG.get('video_width')
                    video_height = project_manager.PROJECT_CONFIG.get('video_height')
            except Exception as e:
                print(f"⚠️  Could not load video dimensions from project config: {e}")
        
        self.ffmpeg_processor = FfmpegProcessor(pid, language, video_width, video_height)
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)
        self.sd_processor = SDProcessor(self)
        self.downloader = YoutubeDownloader(pid)
        self.llm_api = LLMApi()
        self.speech_service = MinimaxSpeechService(self.pid)
        self.transcriber = AudioTranscriber(self, model_size="small", device="cuda")

        config.create_project_path(pid)

        # Create project paths
        self.publish_path = config.PUBLISH_PATH + "/"
        self.project_path = config.get_project_path(pid)
        self.channel_path = config.get_channel_path(channel)
        self.effect_path = config.get_effect_path()

        self.negative_prompt = NEGATIVE_PROMPT_OPTIONS[0]

        self.font_size = 14
        self.language = language
        if language == "tw":
            self.font_video = config.FONT_7
            self.font_title = config.FONT_8
        elif language == 'jp':
            self.font_video = config.FONT_11
            self.font_title = config.FONT_12
        elif language == 'kr':
            self.font_video = config.FONT_20
            self.font_title = config.FONT_20
        elif language == 'ar':
            self.font_video = config.FONT_13
            self.font_title = config.FONT_13
        elif language == 'th':
            self.font_video = config.FONT_14
            self.font_title = config.FONT_14
        elif language == 'ti':
            self.font_video = config.FONT_16
            self.font_title = config.FONT_16
        elif language == 'mo':
            self.font_video = config.FONT_17
            self.font_title = config.FONT_17
        else:
            self.font_video = config.FONT_4
            self.font_title = config.FONT_0

        self.title = ""

        self.background_image = None
        self.background_music = None
        self.background_video = None

 
    def post_init(self, title):
        if title:
            self.title = self.transcriber.translate_text(title, self.language, self.language)


    def project_169_mode(self):
        return self.ffmpeg_processor.width > self.ffmpeg_processor.height


    def clean_folder(self, folder_name):
        folder = Path(folder_name)
        # Check if original folder exists
        if not folder.exists():
            return
        subdirs = [d for d in folder.iterdir() if d.is_dir()]
        if not subdirs:
            return

        for subdir in subdirs:
            shutil.rmtree(subdir)


    def clean_media(self):
        """媒体清理"""
        valid_media_files = []
        for scene in self.scenes:
            zero = get_file_path(scene, "zero")
            if zero:
                valid_media_files.append(zero)
            zero_audio = get_file_path(scene, "zero_audio")
            if zero_audio:
                valid_media_files.append(zero_audio)

            second = get_file_path(scene, "second")
            if second:
                valid_media_files.append(second)
            second_audio = get_file_path(scene, "second_audio")
            if second_audio:
                valid_media_files.append(second_audio)

            clip_audio = get_file_path(scene, "clip_audio")
            if clip_audio:
                valid_media_files.append(clip_audio)
            clip_video = get_file_path(scene, "clip")
            if clip_video:
                valid_media_files.append(clip_video)

            clip_left = get_file_path(scene, "clip_left")
            if clip_left:
                valid_media_files.append(clip_left)
            clip_right = get_file_path(scene, "clip_right")
            if clip_right:
                valid_media_files.append(clip_right)

            second_left = get_file_path(scene, "second_left")
            if second_left:
                valid_media_files.append(second_left)
            second_right = get_file_path(scene, "second_right")
            if second_right:
                valid_media_files.append(second_right)

            zero_left = get_file_path(scene, "zero_left")
            if zero_left:
                valid_media_files.append(zero_left)
            zero_right = get_file_path(scene, "zero_right")
            if zero_right:
                valid_media_files.append(zero_right)

            back_video = get_file_path(scene, "back")
            if back_video:
                backs = back_video.split(',')
                for back in backs:
                    if back and os.path.exists(back):
                        valid_media_files.append(back)

            clip_image = get_file_path(scene, "clip_image")
            if clip_image:
                valid_media_files.append(clip_image)
            clip_image_last = get_file_path(scene, "clip_image_last")
            if clip_image_last:
                valid_media_files.append(clip_image_last)

            second_image = get_file_path(scene, "second_image")
            if second_image:
                valid_media_files.append(second_image)
            second_image_last = get_file_path(scene, "second_image_last")
            if second_image_last:
                valid_media_files.append(second_image_last)

            zero_image = get_file_path(scene, "zero_image")
            if zero_image:
                valid_media_files.append(zero_image)
            zero_image_last = get_file_path(scene, "zero_image_last")
            if zero_image_last:
                valid_media_files.append(zero_image_last)

            speak_audio = get_file_path(scene, "speak_audio")
            if speak_audio:
                valid_media_files.append(speak_audio)
            main_audio = get_file_path(scene, "main_audio")
            if main_audio:
                valid_media_files.append(main_audio)
            main_video = get_file_path(scene, "main_video")
            if main_video:
                valid_media_files.append(main_video)

        # list all files inside the project_path/media folder
        all_media_files = []
        for file in os.listdir(config.get_media_path(self.pid)):
            all_media_files.append(config.get_media_path(self.pid) + "/" + file)

        # list all temp files inside the project_path/temp folder
        for file in os.listdir(config.get_temp_path(self.pid)):
            all_media_files.append(config.get_temp_path(self.pid) + "/" + file)
            #safe_remove(config.get_temp_path(self.pid) + "/" + file)

        # try to remove all files in all_media_files that are not in valid_media_files
        for file in all_media_files:
            if file not in valid_media_files:
                safe_remove(file)



    def build_prompt(self, scene_data, extra, track, av_type):
        prompt_dict = {}

        # 提取当前场景的关键信息
        character = scene_data.get("character", "")
        speaking = scene_data.get("speaking", "")
        actions = scene_data.get("actions", "")
        visual = scene_data.get("visual", "")

        speaker = scene_data.get("speaker", "")
        voiceover = scene_data.get("voiceover", "")

        if "second" in track:
            if "speaking" in scene_data:
                if speaker:
                    if speaker.endswith("left"):
                        prompt_dict["SPEAKING"] = f"the left-side person says: ({speaking}), while {actions}."
                        if av_type == "WS2V":
                            prompt_dict["LISTENING"] = f"the right-side person is listening, while engaging face &  hands reactions."
                    elif speaker.endswith("right"):
                        prompt_dict["SPEAKING"] = f"the right-side person says: ({speaking}),  while {actions}."
                        if av_type == "WS2V":
                            prompt_dict["LISTENING"] = f"the left-side person is listening, while engaging face & hands reactions."
                    else:
                        prompt_dict["SPEAKING"] = f"the person say: ({speaking}),  while {actions}."
                else:
                    prompt_dict["SPEAKING"] = f"{speaking}, while {actions}."

        if "clip" in track or "zero" in track:
            person_lower = character
            if person_lower:
                has_negative_pattern = (
                    re.search(r'\bno\b.*\bpersons?\b', person_lower) or  # matches "no person", "no persons", "no specific person"
                    re.search(r'\bno\b.*\bcharacters?\b', person_lower) or  # matches "no character", "no characters", "no other character"
                    re.search(r'\bn/a\b', person_lower) or  # matches "n/a"
                    re.search(r'\bnone\b', person_lower)  # matches "none"
                )
                if not has_negative_pattern:
                    prompt_dict["character"] = character + ", while " + actions + "."


        prompt_dict["visual"] = visual

        prompt_dict["content"] = speaking
        prompt_dict["voiceover"] = voiceover
        #if "cinematography" in scene_data:
        #    prompt_dict["CINEMATOGRAPHY"] = scene_data['cinematography']
        if extra:
            prompt_dict["FYI"] = extra

        return prompt_dict


    def create_story_audio(self, story_json_path, audio_path, video_duration):
        """创建沉浸式故事音频"""
        try:
            print(f"🎭 开始创建沉浸式故事音频...")
            with open(story_json_path, 'r', encoding='utf-8') as f:
                immersive_story_json = json.load(f)
            
            if not immersive_story_json:
                print(f"❌ 沉浸故事内容为空")
                return None
            
            print(f"📝 沉浸故事包含 {len(immersive_story_json)} 个对话片段")
            
            speed_percentage = self.calculate_speed_percentage(7.0, video_duration)

            # 为每个对话片段设置速度和音调
            for item in immersive_story_json:
                item["speed"] = speed_percentage  # 正常速度
                item["pitch"] = speed_percentage  # 正常音调
            
            # 生成SSML并转换为语音
            # ssml = self.tts_service.make_ssml("250ms", immersive_story_json)
            #print(f"🎵 沉浸故事SSML:\n {ssml}")
            
            # 生成音频文件
            temp_audio_path = self.tts_service.generate_audio(immersive_story_json, audio_path)
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.replace(temp_audio_path, audio_path)
                print(f"🎵 沉浸故事音频文件已生成: {audio_path}")
            else:
                print(f"❌ 沉浸故事音频生成失败")
            
        except Exception as e:
            print(f"❌ 创建沉浸式故事音频时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()

        return audio_path


    # style: choices of  '1 male & 1 female) hosts', '1 male host', '1 female host', '1 host & 2 actors', '2 hosts & 2 actors'
    # topic: the topic of the dialogue (text field)
    # avoid_content: the content to avoid in the dialogue (text field)
    # location: the location of the dialogue (text field)
    # general_location: the name of the large site (from existing 故事场地 field)
    # dialogue_openning: the opening of the dialogue (text field)
    # dialogue_ending: the ending of the dialogue (text field)
    # previous_dialogue: the previous dialogue (drag/drop mp3 or txt file, to the image area [media/wave_sound.png]) in left side 
    # introducation_story: the introducation story (drag/drop mp3 or txt file, to the image area [media/wave_sound.png]) in right side 
    def prepare_notebooklm_for_project(self, style, topic, avoid_content, location, previous_dialogue, introduction_story, introduction_type):
        if avoid_content and avoid_content.strip() != "":
            avoid_content = f"""
            "Avoid_Content" : "Try to avoid content like '{avoid_content}'",
            """
        else:
            avoid_content = ""
            
        if introduction_story and introduction_story.strip() != "":
            if introduction_story.endswith(".mp3") or introduction_story.endswith(".wav"):
                introduction_story = self.transcriber.transcribe_to_file(introduction_story, "zh", 10, 26)
            if not introduction_story:
                return None

            user_prompt = self.transcriber.fetch_text_from_json(introduction_story)
            
            introduction_story = self.llm_api.generate_text(config_prompt.NOTEBOOKLM_SUMMARY_SYSTEM_PROMPT, user_prompt)
            if not introduction_story:
                return None

            introduction_story = f"""
            "Introducation_story" : "The hosts start the dialogue just after they {introduction_type}, that talks about : '{introduction_story}'.     (the dialogue is carried out immediately after this talk)",
            """
        else:
            introduction_story = ""

        if previous_dialogue and previous_dialogue.strip() != "":
            if previous_dialogue.endswith(".mp3") or previous_dialogue.endswith(".wav"):
                previous_dialogue = self.transcriber.transcribe_to_file(previous_dialogue, "zh", 10, 26)
            if not previous_dialogue:
                return None

            user_prompt = self.transcriber.fetch_text_from_json(previous_dialogue)

            previous_dialogue = self.llm_api.generate_text(config_prompt.NOTEBOOKLM_SUMMARY_SYSTEM_PROMPT, user_prompt)
            if not previous_dialogue:
                return None

            previous_dialogue = f"""
                "Previous_Dialogue" : "This dialogue follows the previous story-telling-dialogue, talking about : '{previous_dialogue}'.    !!! This dialogue may mention the previous content quickly, but DO NOT talking the details again !!!",
            """
        else:
            previous_dialogue = ""

        user_prompt = config.fetch_story_extract_text_content(self.pid, self.language)


        dialogue_opening = ""
        dialogue_ending = ""
        location = ""


        return config_prompt.NOTEBOOKLM_PROMPT.format(
            style=style,
            topic=topic,
            avoid_content=avoid_content,
            location=location,
            previous_dialogue=previous_dialogue,
            introduction_story=introduction_story,
            dialogue_openning=dialogue_opening,
            dialogue_ending=dialogue_ending
        )
 
 

    def find_clip_duration(self, current_scene):
        clip_audio = get_file_path(current_scene, "clip_audio")
        duration = None
        if clip_audio:
            duration = self.ffmpeg_audio_processor.get_duration(clip_audio)

        if not duration:
            clip_video = get_file_path(current_scene, "clip")
            duration = self.ffmpeg_processor.get_duration(clip_video)

        current_scene["duration"] = duration
        return duration


    def get_scene_detail(self, scene):
        indx = -1
        for i in range(len(self.scenes)):
            if self.scenes[i] is scene:
                indx = i
                break

        if indx < 0:
            return 0.0, 0.0, 0.0, -1, 0, False # not found

        clip_duration = self.find_clip_duration(scene)

        ss = self.scenes_in_story(scene)
        story_duration = 0.0
        for s in ss:
            story_duration += self.find_clip_duration(s)
        start_time_in_story = 0.0
        for s in ss:
            if s == scene:
                break
            start_time_in_story += self.find_clip_duration(s)

        return start_time_in_story, clip_duration, story_duration, indx, len(ss), s == ss[-1]


    def merge_scene(self, from_index, to_index, keep_current=False):
        if not (from_index-to_index==1 or from_index-to_index==-1):
            return False
        if from_index > len(self.scenes) - 1 or from_index < 0:
            return False
        if to_index > len(self.scenes) - 1 or to_index < 0:
            return False

        from_scene = self.scenes[from_index]
        same_main_scenes = self.scenes_in_story(from_scene)
        if len(same_main_scenes) <= 1:
            return False

        to_scene = self.scenes[to_index]

        if not keep_current:
            from_scene["speaking"] = to_scene["speaking"]
        # merged_duration = self.find_duration(from_scene) + self.find_duration(to_scene)
        if from_index > to_index:
            audio_list = [get_file_path(to_scene, "clip_audio"), get_file_path(from_scene, "clip_audio")]
            video_list = [get_file_path(to_scene, "clip"), get_file_path(from_scene, "clip")]
        else:
            audio_list = [get_file_path(from_scene, "clip_audio"), get_file_path(to_scene, "clip_audio")]
            video_list = [get_file_path(from_scene, "clip"), get_file_path(to_scene, "clip")]

        same_main_scenes = self.scenes_in_story(from_scene)
        refresh_scene_media(from_scene, "clip_audio", ".wav",  self.ffmpeg_audio_processor.concat_audios(audio_list))
        refresh_scene_media(from_scene, "clip", ".mp4",  self.ffmpeg_processor.concat_videos(video_list, True))

        del self.scenes[to_index]

        # self.refresh_scene_visual(from_scene)

        #self._generate_video_from_image(from_scene)
        return True


    def clone_scene(self, current_index, is_append=False):
        if current_index < 0 or current_index >= len(self.scenes):
            return False

        if is_append:
            new_scenes = [self.scenes[current_index], self.scenes[current_index].copy()]
            self.replace_scene_with_others(current_index+1, new_scenes)
        else:
            new_scenes = [self.scenes[current_index].copy(), self.scenes[current_index]]
            self.replace_scene_with_others(current_index, new_scenes)


    def replace_scene(self, current_index, new_scene=None):
        if current_index >= len(self.scenes):
            return None

        old_scene = self.scenes[current_index]
        ss = self.scenes_in_story(old_scene)
        
        if new_scene:
            self.scenes[current_index] = new_scene
        else:
            del self.scenes[current_index]

        if len(ss) == 1:
            return None

        # delete old_scene from ss
        ss.remove(old_scene)
        return ss


    def replace_scene_with_others(self, current_index, new_scenes):
        if current_index < 0 or current_index >= len(self.scenes):
            return False  # invalid index

        # Replace the single item with the list of new scenes
        self.scenes = (
            self.scenes[:current_index] +
            new_scenes +
            self.scenes[current_index + 1:]
        )
        self.save_scenes_to_json()
        return True



    def split_smart_scene(self, current_scene, sections) -> list:
        """将场景按照指定时长分割成多个部分"""
        # 找到当前场景的索引
        current_index = None
        for i, scene in enumerate(self.scenes):
            if scene is current_scene:
                current_index = i
                break
        
        original_duration = self.find_clip_duration(current_scene)
        
        original_audio_clip = get_file_path(current_scene, "clip_audio")
        original_video_clip = get_file_path(current_scene, "clip")
        
        # 获取当前场景的section ID，用于生成新的场景ID
        max_section_id = current_scene["id"]
        current_section = current_scene["id"] // 100
        for s in self.scenes:
            if s["id"] // 100 == current_section and s["id"] > max_section_id:
                max_section_id = s["id"]
        
        # 创建所有新场景的列表
        new_scenes = []
        start_time = 0.0
        part_duration = original_duration / sections
        for i in range(sections):
            # 创建新场景
            if i == 0:
                # 第一个场景使用原场景
                new_scene = current_scene
            else:
                new_scene = current_scene.copy()
            
            # 分割音频：从 start_time 开始，提取 part_duration 长度
            if original_audio_clip:
                trimmed_audio = self.ffmpeg_audio_processor.audio_cut_fade(
                    original_audio_clip, start_time, part_duration, 0, 0, 1.0
                )
                refresh_scene_media(new_scene, "clip_audio", ".wav", trimmed_audio)
            
            # 分割视频：从 start_time 开始，提取到 start_time + part_duration
            if original_video_clip:
                trimmed_video = self.ffmpeg_processor.trim_video(
                    original_video_clip, start_time=start_time, end_time=start_time + part_duration
                )
                refresh_scene_media(new_scene, "clip", ".mp4", trimmed_video)
            
            # 更新场景ID和内容
            new_scene["id"] = max_section_id + i + 1
            
            new_scenes.append(new_scene)
            start_time += part_duration
        
        # 使用 replace_scene_with_others 一次性替换原场景
        self.replace_scene_with_others(current_index, new_scenes)
        return new_scenes



    def split_scene_at_position(self, n, position):
        """分离当前场景"""
        if n<0  or n >= len(self.scenes):
            return False

        current_scene = self.scenes[n]

        original_duration = self.find_clip_duration(current_scene)
        if position<=0 or position >= original_duration:
            return False

        original_content = current_scene.get("speaking", "")
        original_audio_clip = get_file_path(current_scene, "clip_audio")
        original_video_clip = get_file_path(current_scene, "clip")

        next_scene = current_scene.copy()

        self.replace_scene_with_others(n, [current_scene, next_scene])

        current_ratio = position / original_duration

        first, second = self.ffmpeg_audio_processor.split_audio(original_audio_clip, position)
        refresh_scene_media(current_scene, "clip_audio", ".wav", first)
        refresh_scene_media(next_scene, "clip_audio", ".wav", second)

        first, second = self.ffmpeg_processor.split_video(original_video_clip, position)
        refresh_scene_media(current_scene, "clip", ".mp4", first)
        refresh_scene_media(next_scene, "clip", ".mp4", second)

        # max section id -->  raw_id = int((raw_scene["id"]/100)*100)
        # every 100 is a section of id, so we need to find the max section id out of same section
        max_section_id = current_scene["id"]
        current_section = current_scene["id"] // 100
        for s in self.scenes:
            # 检查是否在同一section
            if s["id"] // 100 != current_section:
                continue
            # 在同一section内，找最大的id
            if s["id"] > max_section_id:
                max_section_id = s["id"]

        current_scene["speaking"] = original_content  #original_content[:int(len(original_content)*current_ratio)]
        current_scene["id"] = max_section_id + 1
        next_scene["speaking"] = original_content     #original_content[int(len(original_content)*(1.0-current_ratio)):]
        next_scene["id"] = max_section_id + 2

        #self._generate_video_from_image(current_scene)
        #self._generate_video_from_image(next_scene)

        #self.refresh_scene(current_scene)
        #self.refresh_scene(next_scene)

        self.save_scenes_to_json()

        return True


    def shift_scene(self, n, m, position):
        """分离为n张图片"""
        if n<0  or n > len(self.scenes) or m<0  or m > len(self.scenes):
            return False

        if abs(n-m) != 1:
            return False
        
        current_scene = self.scenes[n]
        next_scene = self.scenes[m]

        original_audio_clip = get_file_path(current_scene, "clip_audio")
        original_video_clip = get_file_path(current_scene, "clip")     
        original_duration = self.ffmpeg_audio_processor.get_duration(original_audio_clip)
        if position<=0 or position >= original_duration:
            return False

        firsta, seconda = self.ffmpeg_audio_processor.split_audio(original_audio_clip, position)

        if n < m: 
            refresh_scene_media(current_scene, "clip_audio", ".wav", firsta)
            mergeda = self.ffmpeg_audio_processor.concat_audios([seconda, get_file_path(next_scene, "clip_audio")])
            refresh_scene_media(next_scene, "clip_audio", ".wav", mergeda)
        else:
            refresh_scene_media(current_scene, "clip_audio", ".wav", seconda)
            mergeda = self.ffmpeg_audio_processor.concat_audios([get_file_path(next_scene, "clip_audio"), firsta])
            refresh_scene_media(next_scene, "clip_audio", ".wav", mergeda)

        current_video = get_file_path(current_scene, "clip")
        current_video = self.ffmpeg_processor.add_audio_to_video(current_video, current_scene["clip_audio"])
        refresh_scene_media(current_scene, "clip", ".mp4", current_video)

        next_video = get_file_path(next_scene, "clip")
        next_video = self.ffmpeg_processor.add_audio_to_video(next_video, next_scene["clip_audio"])  
        refresh_scene_media(next_scene, "clip", ".mp4", next_video)

        self.save_scenes_to_json()

        return True


    def _create_image(self, sd_config, new_image_path, figures, positive, negative, seed):
        if self.ffmpeg_processor.width >= self.ffmpeg_processor.height:
            sd_width, sd_height = 1920, 1080
        else:
            sd_width, sd_height = 1080, 1920

        if sd_config["model"] == "sd":
            image = self.sd_processor.text2Image_sd(
                positive,
                negative, 
                sd_config["url"], 
                sd_config["cfg"], 
                seed or sd_config["seed"], 
                sd_config["steps"], 
                sd_width, 
                sd_height
            )
        elif sd_config["model"] == "banana":
            image = self.sd_processor.text2Image_banana(
                url = sd_config["url"], 
                workflow = sd_config["workflow"],
                positive = positive,
                negative = negative,
                image_list = [figures] if figures else [],
                width = sd_width,
                height = sd_height,
                cfg = sd_config["cfg"],
                seed = seed or sd_config["seed"],
                steps = sd_config["steps"],
            )
            
        # 检查图像生成是否成功
        if image is None:
            print("❌ 图像生成失败，返回 None")
            return
            
        print(f"🔄 缩放图像从 {sd_width}x{sd_height} 到HD尺寸 {self.ffmpeg_processor.width}x{self.ffmpeg_processor.height}")
        hd_image = self.sd_processor.resize_image(image, self.ffmpeg_processor.width, self.ffmpeg_processor.height)
        # Convert back to binary format
        buffer = BytesIO()
        hd_image.save(buffer, format="PNG")
        hd_image_data = buffer.getvalue()

        self.sd_processor.save_image(hd_image_data, new_image_path)



    def load_scenes(self):
        self.scenes = []
        scenes_file = config.get_scenes_path(self.pid)
        if os.path.exists(scenes_file):
            with open(scenes_file, "r", encoding="utf-8") as f:
                self.scenes = json.load(f)
            return

        channel = project_manager.PROJECT_CONFIG.get('channel', 'default')
        channel_topic = config_channel.CHANNEL_CONFIG[channel]["topic"]
        story_script = project_manager.PROJECT_CONFIG.get('story', "{}")
        stories_json = json.loads(story_script)
        stories_template = config_channel.CHANNEL_CONFIG[channel]["channel_template"]

        for i, element in enumerate(stories_template):
            if element.get("name") == "program":
                stories_template[i:i+1] = stories_json
                break

        # popup dialog to select the story level
        story_level = tk.messagebox.askyesno("Story Level", "Do you want to create every scence as seperated story?")
        if story_level:
            story_level = True
        else:
            story_level = False

        for story_index, story in enumerate(stories_template):
            self.add_story_scene(story_index, story, story_level, is_append=False)

        self.save_scenes_to_json()

    

    def get_image_main_scenes(self):
        """获取所有标记为IMAGE_MAIN的场景，用于制作缩略图"""
        image_main_scenes = []
        for i, scene in enumerate(self.scenes):
            if scene.get("clip_animation", "") == "IMAGE_MAIN":
                image_main_scenes.append({
                    "index": i,
                    "scene": scene,
                    "image_path": scene.get("clip_image", "")
                })
        return image_main_scenes


    def make_conversation_srt(self, conversation_json, duration):
        content = []
        addup = 2
        for i, item in enumerate(conversation_json):
            #if (i+1) * duration + addup > video_duration:
            #    break
            addup = addup + 1

            content.append(str(i+1))

            start = i * duration + addup
            end = (i+1) * duration + addup
            content.append(f"{start} --> {end}")

            content.append(item["kernel"])
            content.append("\n")

        return self.transcriber.chinese_convert('\n'.join(content), self.language)


    def calculate_speed_percentage(self, default_duration, actual_duration):
        if default_duration <= 0:
            return "+0%"
        
        # Calculate percentage: (default - actual) / default * 100
        percentage = ((default_duration - actual_duration) / default_duration) * 100
        
        # Round to nearest integer
        percentage = int(round(percentage))
        
        # Format as string with + or - sign
        if percentage > 0:
            return f"+{percentage}%"
        elif percentage < 0:
            return f"{percentage}%"  # negative sign is already included
        else:
            return "+0%"


    def prepare_srt(self, subtitle, start_duration, audio_duration):
        #if subtitle is json file, load it, then for each json item, get the 'speaking' field, concat them by \n, as srt_content
        script_lines = []

        try:
            json_content = json.loads(subtitle)
            srt_content = ""
            for item in json_content:
                script_lines.append(item["speaking"])
        except Exception as e: 
            for line in subtitle.split('\n'):
                line = line.strip()
                # Skip empty lines (even with spaces)
                if not line:
                    continue
                # Skip lines starting with [ or (
                if line.startswith('[') or line.startswith('('):
                    continue
                # Skip lines with very few characters (under 5)
                if len(line) < 5:
                    continue
                # Skip timestamp lines (format: HH:MM:SS.mmm --> HH:MM:SS.mmm)
                if '-->' in line and ':' in line:
                    # Check if it looks like a timestamp
                    parts = line.split('-->')
                    if len(parts) == 2:
                        left = parts[0].strip()
                        right = parts[1].strip()
                        # Check if both parts contain colons (time format)
                        if ':' in left and ':' in right:
                            continue
                script_lines.append(line)
        
        # Create SRT content
        start_seconds = start_duration
        line_duration = audio_duration / len(script_lines) if script_lines else 0
        srt_content = ""
        
        for i, line in enumerate(script_lines):
            end_seconds = start_seconds + line_duration
            start_seconds_str = start_seconds
            end_seconds_str = end_seconds
            srt_content += f"{i+1}\n{start_seconds_str} --> {end_seconds_str}\n{line}\n\n"
            start_seconds = end_seconds
        
        # Convert content using transcriber
        return self.transcriber.chinese_convert(srt_content, self.language)


    def _normalize_json_string_field(self, value):
        """规范化可能是字符串形式JSON的字段值，避免转义累积
        
        处理三种情况：
        1. 已经是字典/列表对象 -> 直接返回
        2. 是字符串形式的JSON -> 解析为对象
        3. 是多层转义的JSON字符串 -> 逐层解析直到得到对象
        """
        # 如果已经是字典或列表，直接返回
        if isinstance(value, (dict, list)):
            return value
        
        # 如果不是字符串，直接返回
        if not isinstance(value, str):
            return value
        
        # 如果是空字符串，直接返回
        if not value.strip():
            return value
        
        value_stripped = value.strip()
        
        # 如果字符串不像 JSON（不以 { 或 [ 或 " 开头），直接返回
        if not ((value_stripped.startswith('{') and value_stripped.endswith('}')) or 
                (value_stripped.startswith('[') and value_stripped.endswith(']')) or
                (value_stripped.startswith('"') and value_stripped.endswith('"'))):
            return value
        
        # 尝试逐层解析 JSON 字符串
        current_value = value_stripped
        max_iterations = 20  # 增加到20次，处理更深层的嵌套
        
        for iteration in range(max_iterations):
            try:
                # 尝试解析当前值
                parsed = json.loads(current_value)
                
                # 如果解析结果是字典或列表，返回它
                if isinstance(parsed, (dict, list)):
                    return parsed
                
                # 如果解析结果是字符串，检查它是否还是 JSON 格式
                if isinstance(parsed, str):
                    parsed_stripped = parsed.strip()
                    if ((parsed_stripped.startswith('{') and parsed_stripped.endswith('}')) or
                        (parsed_stripped.startswith('[') and parsed_stripped.endswith(']'))):
                        # 继续下一轮解析
                        current_value = parsed_stripped
                        continue
                    else:
                        # 不再是 JSON 格式的字符串，返回它
                        return parsed
                
                # 其他类型（数字、布尔等），返回它
                return parsed
                
            except json.JSONDecodeError as e:
                # 解析失败，尝试清理转义字符
                old_value = current_value
                
                # 先尝试移除最外层的引号对（如果有）
                if current_value.startswith('"""') and current_value.endswith('"""'):
                    current_value = current_value[3:-3]
                elif current_value.startswith('""') and current_value.endswith('""'):
                    current_value = current_value[2:-2]
                elif current_value.startswith('"') and current_value.endswith('"') and len(current_value) > 2:
                    current_value = current_value[1:-1]
                
                # 检查是否有转义引号或反斜杠
                if '\\"' in current_value:
                    # 移除转义引号
                    current_value = current_value.replace('\\"', '"')
                
                if '\\\\' in current_value:
                    # 移除转义反斜杠
                    current_value = current_value.replace('\\\\', '\\')
                
                # 如果清理后有变化，继续尝试
                if current_value != old_value:
                    continue
                
                # 无法继续清理，返回当前值
                return current_value
        
        # 达到最大迭代次数，返回当前值
        return current_value


    def save_scenes_to_json(self):
        # config.clear_temp_files()
        try:
            # 在保存之前规范化可能包含JSON字符串的字段
            normalized_scenes = []
            json_string_fields = []  # 可能需要规范化的字段列表
            
            for scene in self.scenes:
                normalized_scene = scene.copy()
                for field in json_string_fields:
                    if field in normalized_scene:
                        normalized_scene[field] = self._normalize_json_string_field(normalized_scene[field])
                normalized_scenes.append(normalized_scene)
            
            with open(config.get_scenes_path(self.pid), "w", encoding="utf-8") as f:
                json.dump(normalized_scenes, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ 保存scenes到JSON失败: {str(e)}")
            return False


    def scenes_in_story(self, scene):
        this_id = scene.get("id", 0)
        if len(self.scenes) == 0 or scene is None or this_id == 0:
            return []

        root_id = int(this_id/10000)
        scenes = []
        for s in self.scenes:
            if int(s["id"]/10000) == root_id:
                scenes.append(s)

        #scenes.sort(key=lambda x: x["id"])
        return scenes


    def next_scene_of_story(self, scene):
        ss = self.scenes_in_story(scene)
        if len(ss) < 2:
            return None
        # get the index of scene in ss
        index = ss.index(scene)
        if index == len(ss) - 1:
            return None
        return ss[index + 1]


    def first_scene_of_story(self, scene):
        ss = self.scenes_in_story(scene)
        if len(ss) == 0:
            return True
        return ss[0] == scene


    def last_scene_of_story(self, scene):
        ss = self.scenes_in_story(scene)
        if len(ss) == 0:
            return True
        return ss[-1] == scene

        
 
    def replace_scene_second(self, current_scene, source_video_path, source_audio_path):
        oldv, secondv = refresh_scene_media(current_scene, "second", ".mp4", source_video_path)
        olda, seconda = refresh_scene_media(current_scene, "second_audio", ".wav", source_audio_path)

        for s in self.scenes_in_story(current_scene):
            s["second"] = secondv
            s["second_audio"] = seconda

        self.save_scenes_to_json()


    def is_last_scene(self, scene, scenes):
        if len(scenes) <= 1 or scene is scenes[-1]:
            return True
        try:
            next_scene = scenes[scenes.index(scene) + 1]
            return next_scene["main_audio"] != scene["main_audio"]
        except:
            return True
        
    def ask_replace_scene_info_from_image(self, current_scene, image_path):
        """询问用户是否要分析图像并更新场景数据"""
        import tkinter.messagebox as messagebox

        dialog_result = messagebox.askyesno(
            "分析图像", 
            f"是否要分析图像并更新场景数据？\n图像路径: {image_path}"
        )
        if not dialog_result:
            return
        
        print(f"🔄 正在分析图像: {image_path}")
        scene_data = self.sd_processor.describe_image(image_path)
        if not scene_data:
            messagebox.showerror("错误", "图像分析失败，无法获取场景数据")
            return
        
        # 更新场景数据
        self.try_update_scene_visual_fields(current_scene, scene_data)


    def replace_scene_image(self, current_scene, source_image_path, vertical_line_position, target_field):
        oldi, image_path = refresh_scene_media(current_scene, target_field, ".webp", source_image_path)

        current_scene[target_field + "_split"] = vertical_line_position
        clip_image_last = get_file_path(current_scene, target_field + "_last")
        if not clip_image_last:
            current_scene[target_field + "_last"] = image_path

        self.ask_replace_scene_info_from_image(current_scene, image_path)
        #target_image = get_file_path(current_scene, target_field)
        #target_image_last = get_file_path(current_scene, target_field + "_last")
         
        #ss = self.scenes_in_story(current_scene)
        #for scene in ss:
        #    if scene == current_scene:
        #        continue
        #    image = get_file_path(scene, target_field)
        #    if not image and target_image:
        #        refresh_scene_media(scene, target_field, ".webp", target_image, True)
        #    image_last = get_file_path(scene, target_field + "_last")
        #    if not image_last and target_image_last:
        #        refresh_scene_media(scene, target_field + "_last", ".webp", target_image_last, True)
        self.save_scenes_to_json()


    def upload_video(self, title):
        title_cvt = self.transcriber.chinese_convert(title, self.language)
        title_used = title_cvt.replace("_", " ")
        title_used = title_used.replace("\n", " ")
        self.title = title_used

        for scene in self.scenes:
            if scene.get("clip_animation", "") == "IMAGE_MAIN":
                image_main_scene = scene
                break

        if not image_main_scene:
            for scene in self.scenes:
                clip_animation = scene.get("clip_animation", "")
                if clip_animation == "VIDEO" or clip_animation == "IMAGE" or clip_animation == "IMAGE_MAIN":
                    image_main_scene = scene
                    break

        if not image_main_scene:
            print(f"❌ 没有找到IMAGE_MAIN场景")
            return

        thumbnail_path = f"{config.get_project_path(self.pid)}/thumbnail.png"
        final_video_path = f"{self.publish_path}/{self.title.replace(' ', '_')}_final.mp4"

        sums = config.fetch_main_summary_content(self.pid, self.language)
        if not sums:
            sums = "《"+config_channel.CHANNEL_CONFIG[self.channel]["channel_name"]+"》 "+self.title
        sums = self.transcriber.chinese_convert(sums, self.language)

        final_srt_path = f"{self.publish_path}/{self.title.replace(' ', '_')}_final.srt"

        video_id = self.downloader.upload_video(final_video_path, 
                                     thumbnail_path, 
                                     title=title, 
                                     description=sums, 
                                     language=self.language, 
                                     script_path=final_srt_path, 
                                     secret_key=config_channel.CHANNEL_CONFIG[self.channel]["channel_key"],
                                     channel_id=self.channel,
                                     categoryId=config_channel.CHANNEL_CONFIG[self.channel]["channel_category_id"][0], 
                                     tags=config_channel.CHANNEL_CONFIG[self.channel]["channel_tags"], 
                                     privacy="unlisted")
        # save video_id to the project_manager.PROJECT_CONFIG
        try:
            from project_manager import ProjectConfigManager
            config_manager = ProjectConfigManager(self.pid)
            # Load existing config or create new one
            existing_config = config_manager.load_config(self.pid) or {}
            # Add video_id to config
            existing_config["video_id"] = video_id
            # Save the updated config
            ProjectConfigManager.set_global_config(existing_config)
            config_manager.save_project_config(existing_config)
            print(f"✅ Video ID saved to project config: {video_id}")
        except Exception as e:
            print(f"❌ Failed to save video_id to project config: {e}")



    def upload_promo_video(self, title, description):
        # need to get video_id from the project_manager.PROJECT_CONFIG
        try:
            from project_manager import ProjectConfigManager
            config_manager = ProjectConfigManager(self.pid)
            existing_config = config_manager.load_config(self.pid) or {}
            video_id = existing_config.get("video_id", None)
        except Exception as e:
            print(f"❌ Failed to get video_id from project config: {e}")

        promo_video_path = f"{self.publish_path}/{title.replace(' ', '_')}_promo.mp4"
        if os.path.exists(promo_video_path):
            channel_name = self.transcriber.chinese_convert(config_channel.CHANNEL_CONFIG[self.channel]["channel_name"], self.language)
            self.downloader.upload_video(promo_video_path, 
                            None, 
                            title=f"《{channel_name}》：{title}", 
                            description=channel_name,
                            language=self.language, 
                            script_path=None, 
                            secret_key=config_channel.CHANNEL_CONFIG[self.channel]["channel_key"],
                            channel_id=self.channel,
                            categoryId=config_channel.CHANNEL_CONFIG[self.channel]["channel_category_id"][0],
                            tags=config_channel.CHANNEL_CONFIG[self.channel]["channel_tags"], 
                            privacy="unlisted")
        return promo_video_path



    def transcript_youtube_video(self, url, source_lang, translated_language):
        try:
            query = urlparse(url).query
            params = parse_qs(query)
            vid = params.get("v", [None])[0]
            if not vid:
                raise ValueError("Invalid YouTube URL, could not find video ID.")
            print(f"🔍 解析链接：{url} - {vid}")

            script_prefix = f"{config.get_project_path(self.pid)}/Youtbue_download/__script_{vid}"

            script_lang = self.downloader.download_captions(url, translated_language, script_prefix)
            if not script_lang:
                mp3_path = self.downloader.download_audio(url)
                print("开始转录音频...")
                script_path = self.transcriber.transcribe_to_file(mp3_path, source_lang, 10, 26)
                if not script_path:
                    return None
                text_path = f"{config.get_project_path(self.pid)}/Youtbue_download/__text_{vid}.{source_lang}.txt"
                self.transcriber.fetch_text_from_json(script_path)
            else:
                script_path = f"{script_prefix}.{script_lang}.srt"
                text_path = f"{config.get_project_path(self.pid)}/Youtbue_download/__text_{vid}.{script_lang}.txt"
                self.transcriber.src_to_text(script_path, text_path)

            if translated_language != source_lang:
                translated_srt_path = f"{config.get_project_path(self.pid)}/Youtbue_download/__script_{vid}.{translated_language}.srt.json"
                self.transcriber.translate_srt_file(script_path, source_lang, translated_language, translated_srt_path)

            return script_path
        except Exception as e:
            print(f"获取字幕失败: {str(e)}")
            return None



    def prepare_final_script(self, base_seconds, final_script_path):
        content = []
        i = 0
        subtitle_index = 1
        
        while i < len(self.scenes):
            current_scene = self.scenes[i]
            current_story = current_scene.get("visual", "")
            
            # Find all consecutive scenes with the same story content
            start_index = i
            end_index = i
            
            start_formatted = base_seconds
            scene_duration = self.get_scene_duration(current_scene)
            base_seconds += scene_duration
            # Look ahead to find consecutive scenes with same story
            while (end_index + 1 < len(self.scenes) and 
                   self.scenes[end_index + 1].get("visual", "") == current_story and
                   current_story.strip() != ""):  # Only combine non-empty content
                end_index += 1
                current_scene = self.scenes[end_index]
                base_seconds += scene_duration

            end_formatted = base_seconds

            # Add to content (only if story content is not empty)
            if current_story.strip():
                content.append(str(subtitle_index))
                content.append(f"{start_formatted} --> {end_formatted}")
                content.append(current_story)
                content.append("\n")
                subtitle_index += 1
                
                # Log the combination for debugging
                if end_index > start_index:
                    print(f"📝 Combined scenes {start_index+1}-{end_index+1} with same content: '{current_story[:50]}{'...' if len(current_story) > 50 else ''}'")
            
            # Move to next unique content
            i = end_index + 1

        with open(final_script_path, "w", encoding="utf-8") as f:
            f.write('\n'.join(content))
            
        print(f"📋 Final script created with {subtitle_index-1} subtitle entries (combined duplicates): {final_script_path}")


    def wait_for_background_threads(self, timeout=300):
        """等待所有后台线程完成"""
        if not self.background_threads:
            return
            
        print(f"⏳ 等待 {len(self.background_threads)} 个后台线程完成...")
        
        for i, thread in enumerate(self.background_threads):
            if thread.is_alive():
                print(f"⏳ 等待线程 {i+1}/{len(self.background_threads)} 完成...")
                thread.join(timeout=timeout//len(self.background_threads))
                
        # 清理已完成的线程
        alive_threads = [t for t in self.background_threads if t.is_alive()]
        completed = len(self.background_threads) - len(alive_threads)
        
        print(f"✅ {completed} 个后台线程完成，{len(alive_threads)} 个仍在运行")
        self.background_threads = alive_threads



    def regenerate_audio(self, fresh_json, language):
        lang = "chinese" if language == "zh" or language == "tw" else "english"
        for json_item in fresh_json:
            self.regenerate_audio_item(json_item, language)
            json_item["caption"] = json_item["speaking"]

        return fresh_json, self.ffmpeg_audio_processor.concat_audios([json_item["speak_audio"] for json_item in fresh_json])


    def regenerate_audio_item(self, json_item, language):
        lang = "chinese" if language == "zh" or language == "tw" else "english"

        speaker = json_item["character"]
        content = json_item["speaking"]
        mood = json_item["mood"]

        ss = speaker.split("/")
        if len(ss) > 1:
            speaker = ss[0]

        try:
            voice = self.speech_service.get_voice(speaker, lang)
            ssml = self.speech_service.create_ssml(text=content, voice=voice, mood=mood)
            audio_file = self.speech_service.synthesize_speech(ssml)
            if audio_file:  # 只添加成功生成的音频文件
                json_item["speak_audio"] = audio_file
                json_item["duration"] = self.ffmpeg_audio_processor.get_duration(json_item["speak_audio"])
            else:
                json_item["speak_audio"] = None
                json_item["duration"] = 0.0
                print(f"⚠️ 说话人 '{s}' 的语音合成失败")
        except Exception as e:
            print(f"❌ 说话人 '{s}' 的语音合成错误: {str(e)}")

        return json_item["duration"], json_item["speak_audio"]



    def rebuild_scene_video(self, scene, video_type, animate_mode, image_path, image_last_path, sound_path, next_sound_path, action_path, wan_prompt):
        if not sound_path or not image_path:
            return
        if not image_last_path:
            image_last_path = image_path

        #if animate_mode == "IMAGE":
        #    v = self.ffmpeg_processor.image_audio_to_video(image_path, sound_path, 1)
        #    refresh_scene_media(scene, video_type, ".mp4", v, True)

        if animate_mode in config_prompt.ANIMATE_I2V:
            file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "I2V", False)
            self.sd_processor.image_to_video( prompt=wan_prompt, file_prefix=file_prefix, image_path=image_path, sound_path=sound_path )

        elif animate_mode in config_prompt.ANIMATE_2I2V:
            file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "2I2V", False)
            self.sd_processor.two_image_to_video( prompt=wan_prompt, file_prefix=file_prefix, first_frame=image_path, last_frame=image_last_path, sound_path=sound_path )

        elif animate_mode in config_prompt.ANIMATE_S2V:
            file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "S2V", False)
            self.sd_processor.sound_to_video(prompt=wan_prompt, file_prefix=file_prefix, image_path=image_path, sound_path=sound_path, next_sound_path=next_sound_path, animate_mode=animate_mode, silence=False)

        elif animate_mode in config_prompt.ANIMATE_AI2V:
            if not action_path:
                action_path = f"{config.DEFAULT_MEDIA_PATH}/default_action.mp4"
            file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "AI2V", False)
            self.sd_processor.action_transfer_video(prompt=wan_prompt, file_prefix=file_prefix, image_path=image_path, sound_path=sound_path, action_path=action_path)

        elif animate_mode in config_prompt.ANIMATE_WS2V:
            vertical_line_position = scene.get("clip_image_split", 0)
            if vertical_line_position == 0:
                return

            speaker = scene.get("speaker", "")
            speaker_position = scene.get("speaker_position", "")
            if not speaker or not speaker_position:
                return

            left_image, right_image = self.ffmpeg_processor.split_image(image_path, vertical_line_position)
            
            left_prompt = wan_prompt.copy()
            right_prompt = wan_prompt.copy()

            left_file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "WS2VL", False)
            right_file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "WS2VR", False)

            if speaker_position == "left":
                left_prompt.pop("LISTENING", None)
                right_prompt.pop("SPEAKING", None)
                self.sd_processor.sound_to_video(prompt=left_prompt, file_prefix=left_file_prefix, image_path=left_image, sound_path=sound_path, animate_mode=animate_mode, silence=False)
                self.sd_processor.sound_to_video(prompt=right_prompt, file_prefix=right_file_prefix, image_path=right_image, sound_path=sound_path, animate_mode=animate_mode, silence=True)
            elif speaker_position == "right":
                left_prompt.pop("SPEAKING", None)
                right_prompt.pop("LISTENING", None)
                self.sd_processor.sound_to_video(prompt=left_prompt, file_prefix=left_file_prefix, image_path=left_image, sound_path=sound_path, animate_mode=animate_mode, silence=True)
                self.sd_processor.sound_to_video(prompt=right_prompt, file_prefix=right_file_prefix, image_path=right_image, sound_path=sound_path, animate_mode=animate_mode, silence=False)


    def replace_scene_audio(self, scene, audio_path, audio_start_time, audio_duration):
        extended_audio = self.ffmpeg_audio_processor.extend_audio(audio_path, audio_start_time, audio_duration)
        olda, newa = refresh_scene_media(scene, "clip_audio", ".wav", extended_audio)
        newv = self.ffmpeg_processor.add_audio_to_video(scene["clip"], newa)
        refresh_scene_media(scene, "clip", ".mp4", newv)


    def promotion_video(self, title):
        self.post_init(title)

        promotion_scenes = []
        for s in self.scenes:
            promotion = s.get("promotion", None)
            if promotion and len(promotion) > 0:
                promotion_scenes.append(s)
        
        if len(promotion_scenes) == 0:
            return

        video_segments = []
        zero_audio = None
        zero_offset = None
        for s in promotion_scenes:
            promotion = s.get("promotion", "")
            clip = s.get("clip", None)
            if zero_offset is None:
                zero_offset, clip_duration, story_duration, indx, count, is_story_last_clip = self.get_scene_detail(s)
            if zero_audio is None:
                zero_audio = get_file_path(s, "zero_audio")

            clip_lang = s.get("content_language", "")
            if not clip_lang or clip_lang not in config.FONT_LIST:
                font = self.font_video
            else:
                font = config.FONT_LIST[clip_lang]
        
            promotion = "hl_" + self.transcriber.translate_text(promotion, self.language, self.language)
            clip_temp = self.ffmpeg_processor.add_script_to_video(clip, promotion, font)
            video_segments.append({"path":clip_temp, "transition":"fade", "duration":1.0})

        video_temp = self.ffmpeg_processor._concat_videos_with_transitions(video_segments, frames_deduct=5.95, keep_audio_if_has=True)
        if zero_audio is not None and zero_offset is not None:
            audio_zero = self.ffmpeg_audio_processor.audio_cut_fade(zero_audio, zero_offset, self.ffmpeg_processor.get_duration(video_temp))
            video_temp = self.ffmpeg_processor.add_audio_to_video(video_temp, audio_zero)
            
        promotion_video_path = f"{self.publish_path}/{self.title.replace(' ', '_')}_promotion.mp4"
        os.replace(video_temp, promotion_video_path)

        config.clear_temp_files()
        print(f"✅ Promotion video created: {promotion_video_path}")


    def finalize_video(self, title, zero_audio:bool):
        self.post_init(title)
        
        #start = 0.0
        #if self.video_prepares["starting"]["video_path"] and os.path.exists(self.video_prepares["starting"]["video_path"]):
        #    video_segments.append({"path":self.video_prepares["starting"]["video_path"], "transition":"fade", "duration":1.0})
        #    start = start + self.ffmpeg_processor.get_duration(self.video_prepares["starting"]["video_path"])

        #if self.video_prepares["pre_video"]["video_path"] and os.path.exists(self.video_prepares["pre_video"]["video_path"]):
        #    video_segments.append({"path":self.video_prepares["pre_video"]["video_path"], "transition":"fade", "duration":1.0})
        #    start = start + self.ffmpeg_processor.get_duration(self.video_prepares["pre_video"]["video_path"])

        video_segments = []
        for s in self.scenes:
            clip= s["clip"]
            video_segments.append({"path":clip, "transition":"fade", "duration":1.0})
            #audio_segments.append(s["clip_audio"])

        video_temp = self.ffmpeg_processor._concat_videos_with_transitions(video_segments, frames_deduct=5.95, keep_audio_if_has=True)

        current_zero = None
        audio_segments = []
        for s in self.scenes:
            if not current_zero or current_zero != s["zero_audio"]:
                current_zero = s["zero_audio"]
                audio_segments.append(current_zero)
        if audio_segments and len(audio_segments) > 0:
            audio_temp = self.ffmpeg_audio_processor.concat_audios(audio_segments)
            video_temp = self.ffmpeg_processor.add_audio_to_video(video_temp, audio_temp, False)

        final_video_path = f"{self.publish_path}/{self.title.replace(' ', '_')}_final.mp4"
        os.replace(video_temp, final_video_path)

        config.clear_temp_files()

        # prepare final srt file
        #final_srt_path = f"{self.publish_path}/{title.replace(' ', '_')}_final.srt"
        #self.prepare_final_script(start, final_srt_path)
 
        # add subtitle to the final video
        # self.ffmpeg_processor.add_subtitle(final_video_path, mp4_path, final_srt_path)
        print(f"✅ Final video with audio created: {final_video_path}")


    def make_background_audio(self):
        audio_segments = []
        started = None
        last_end = 0.0
        for s in self.scenes:
            duration = self.find_clip_duration(s)

            zero = get_file_path(s, "zero")
            zero_clip_position = s.get("zero_clip_position", -1.0)
            zero_volume = s.get("zero_clip_volume", None)
            zero_ending = s.get("zero_ending", False)
            zero_end = s.get("zero_end", None)

            if not zero_end or not zero_volume or zero_clip_position < 0.0 or zero_clip_position >= duration-0.1:
                audio_segments.append( self.ffmpeg_audio_processor.make_silence(duration) )
                continue

            if not started:
                started = s.get("zero_start", None)
                if zero_clip_position > 0.0:
                    audio_segments.append( self.ffmpeg_audio_processor.make_silence(zero_clip_position) )

            if started:
                if zero_ending:
                    audio_segments.append( self.ffmpeg_audio_processor.audio_cut_fade(zero, started, zero_end-started, 1.0, 1.0, zero_volume) )
                    started = None

            if not zero_end:
                last_end = 0.0
            else:
                last_end = zero_end

        audio_temp = self.ffmpeg_audio_processor.concat_audios(audio_segments)
        return audio_temp


    def copy_scene(self, scene, audio_scene):
        preserved_fields = {field: audio_scene[field] for field in ["start", "end", "duration", "speaker", "speaking", "character", "actions", "visual", "caption", "voiceover"] if field in audio_scene}
        scene.update(preserved_fields)
        return scene
 


    def prepare_scenes_from_json(self, raw_scene, audio_json):
        # keep raw_id as integer    
        raw_id = int((raw_scene["id"]/100)*100)
        audio = self.ffmpeg_audio_processor.to_wav(raw_scene["clip_audio"])
        video = self.ffmpeg_processor.resize_video(raw_scene["clip"], None, None) 

        start_time = 0.0
        for audio_scene in audio_json:
            raw_id += 100
            update_fields = {
                "id": raw_id,
                "clip_animation": ""
            }
            audio_scene.update(update_fields)

            # self.refresh_scene_visual(audio_scene)
            clip_wav = self.ffmpeg_audio_processor.audio_cut_fade(audio, start_time, audio_scene["duration"])
            olda, clip_audio = refresh_scene_media(audio_scene, "clip_audio", ".wav", clip_wav)
            end_time = start_time + audio_scene["duration"]
            v = self.ffmpeg_processor.trim_video(video, start_time, end_time)
            v = self.ffmpeg_processor.add_audio_to_video(v, clip_audio)
            refresh_scene_media(audio_scene, "clip", ".mp4", v)
            start_time = end_time

        return audio_json


    def swap_scene(self, current_index, next_index):
        if current_index < 0 or current_index >= len(self.scenes):
            return False
        if next_index < 0 or next_index >= len(self.scenes):
            return False
        self.scenes[current_index], self.scenes[next_index] = self.scenes[next_index], self.scenes[current_index]
        temp = self.scenes[current_index]["id"]
        self.scenes[current_index]["id"] = self.scenes[next_index]["id"]
        self.scenes[next_index]["id"] = temp
        self.save_scenes_to_json()
        return True



    def max_id(self, current_scene):
        same_story_scenes = self.scenes_in_story(current_scene)
        if same_story_scenes is None or len(same_story_scenes) == 0:
            return 0

        max_id = 0
        for s in same_story_scenes:
            id = s.get("id", 0)
            if id > max_id:
                max_id = id
        return max_id



    def add_story_scene(self, story_index, story, story_level, is_append):
        prefix, kernel = config.fetch_resource_prefix("", ["default"])

        if not self.background_image:
            if self.ffmpeg_processor.width > self.ffmpeg_processor.height:
                self.background_image = config.find_matched_file(config.get_background_image_path()+"/"+self.channel, prefix+"/169_", "png", kernel)
            else:
                self.background_image = config.find_matched_file(config.get_background_image_path()+"/"+self.channel, prefix+"/916_", "png", kernel)

            self.background_image = self.ffmpeg_processor.to_webp(self.background_image) 

        if not self.background_video:
            if self.ffmpeg_processor.width > self.ffmpeg_processor.height:
                self.background_video = config.find_matched_file(config.get_background_video_path()+"/"+self.channel, prefix+"/169_", "mp4", kernel)
            else:
                self.background_video = config.find_matched_file(config.get_background_video_path()+"/"+self.channel, prefix+"/916_", "mp4", kernel)
            self.background_music = self.ffmpeg_audio_processor.extract_audio_from_video(self.background_video)

        if not self.background_music:
            self.background_music = config.find_matched_file(config.get_background_music_path()+"/"+self.channel, prefix+"/", "wav", kernel)
            self.background_music = self.ffmpeg_audio_processor.to_wav(self.background_music)
            self.background_video = self.ffmpeg_processor.image_audio_to_video(self.background_image, self.background_music, 1)


        if story_level:
            next_root_id = (int(self.max_id(story)/10000) + 1)*10000
        else:
            next_root_id = (int(self.max_id(story)/100) + 1)*100
            if next_root_id < 10000:
                next_root_id = 10000

        story["id"] = next_root_id
        story["environment"] = ""

        oldv, zero = refresh_scene_media(story, "zero", ".mp4", self.background_video, True)
        olda, zero_audio = refresh_scene_media(story, "zero_audio", ".wav", self.background_music, True)
        oldi, zero_image = refresh_scene_media(story, "zero_image", ".webp", self.background_image, True)

        refresh_scene_media(story, "clip", ".mp4", zero, True)
        refresh_scene_media(story, "clip_audio", ".wav", zero_audio, True)
        refresh_scene_media(story, "clip_image", ".webp", zero_image, True)


        if not self.scenes:
            self.scenes = [story]
        else:
            if is_append:
                self.scenes.insert(story_index+1, story)
            else:
                self.scenes.insert(story_index, story) 


