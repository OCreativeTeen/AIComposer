from hashlib import new
from urllib.parse import urlparse, parse_qs

from torch._inductor.ir import NoneAsConstantBuffer
from utility.audio_transcriber import AudioTranscriber
from utility.youtube_downloader import YoutubeDownloader
from utility.talk_summerizer import TalkSummarizer
from utility.sd_image_processor import SDProcessor
from utility.ffmpeg_processor import FfmpegProcessor
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
import os, time
import json
import shutil
import threading
import requests
import glob
import re
from pathlib import Path
from config import azure_subscription_key, azure_region
import config
from typing import List, Dict, Optional, Union, Any, Generator
import random
from datetime import datetime
from io import BytesIO
from PIL import Image
from utility.file_util import get_file_path, safe_remove, copy_file
from utility.minimax_speech_service import MinimaxSpeechService
from gui.image_prompts_review_dialog import IMAGE_PROMPT_OPTIONS, NEGATIVE_PROMPT_OPTIONS
from utility.llm_api import LLMApi


class MagicWorkflow:

    def __init__(self, pid, language, channel, story_site, video_width=None, video_height=None):
        self.pid = pid
        self.language = language
        self.channel = channel
        self.story_site = story_site
        self.media_count = 0
        
        # 全局线程管理
        self.background_threads = []

        # Get video dimensions from parameters or load from project config
        if video_width is None or video_height is None:
            # Try to load from project config
            try:
                from project_manager import ProjectConfigManager
                config_manager = ProjectConfigManager(pid)
                if config_manager.project_config:
                    video_width = config_manager.project_config.get('video_width')
                    video_height = config_manager.project_config.get('video_height')
            except Exception as e:
                print(f"⚠️  Could not load video dimensions from project config: {e}")
        
        self.ffmpeg_processor = FfmpegProcessor(pid, language, video_width, video_height)
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)
        self.sd_processor = SDProcessor(self)
        self.downloader = YoutubeDownloader(pid)
        self.summarizer = TalkSummarizer(pid, language)
        self.speech_service = MinimaxSpeechService(self.pid)
        self.transcriber = AudioTranscriber(self, model_size="small", device="cuda")

        self.llm = LLMApi(model=LLMApi.GEMINI_2_0_FLASH)

        config.create_project_path(pid)

        # Create project paths
        self.publish_path = config.PUBLISH_PATH + "/"
        self.project_path = config.get_project_path(pid)
        self.channel_path = config.get_channel_path(channel)
        self.effect_path = config.get_effect_path()

        self.short_conversation_path = f"{self.project_path}/{self.pid}_{self.language}_short_1.json"
        if os.path.exists(self.short_conversation_path):
            with open(self.short_conversation_path, "r", encoding="utf-8") as f:
                self.short_conversation = f.read()
        else:
            self.short_conversation = ""

        self.negative_prompt = NEGATIVE_PROMPT_OPTIONS[0]

        self.font_size = 14
        self.language = language
        if language == "tw":
            self.font_video = config.FONT_9
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
        self.program_keywords = None

        self.load_scenarios()

 
    # self.channel is like israle_zh,  need to get the 'isreale' part out
    def fetch_resource_prefix(self, prefix, keywords):
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


    def post_init(self, title, keywords):
        if title:
            self.title = self.transcriber.translate_text(title, self.language, self.language)

        keywords_list = keywords.split(',') if keywords else []
        self.program_keywords = [kw.strip() for kw in keywords_list if kw.strip()]


    def project_169_mode(self):
        return self.ffmpeg_processor.width > self.ffmpeg_processor.height


    def find_default_background_video(self):
        prefix, keywords = self.fetch_resource_prefix("", ["default"])
        return self.find_matched_file(config.get_background_video_path()+"/"+self.channel, prefix+"/", "mp4", keywords)
        

    def find_default_background_music(self):
        prefix, keywords = self.fetch_resource_prefix("", ["default"])
        mp3 = self.find_matched_file(config.get_background_music_path()+"/"+self.channel, prefix+"/", "mp3", keywords)
        return self.ffmpeg_audio_processor.to_wav(mp3)
    

    def find_default_background_image(self):
        prefix, keywords = self.fetch_resource_prefix("", ["default"])
        png = self.find_matched_file(config.get_background_image_path()+"/"+self.channel, prefix+"/", "png", keywords)
        return self.ffmpeg_processor.to_webp(png)


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
        for scenario in self.scenarios:
            zero = get_file_path(scenario, "zero")
            if zero:
                valid_media_files.append(zero)
            zero_audio = get_file_path(scenario, "zero_audio")
            if zero_audio:
                valid_media_files.append(zero_audio)

            second = get_file_path(scenario, "second")
            if second:
                valid_media_files.append(second)
            second_audio = get_file_path(scenario, "second_audio")
            if second_audio:
                valid_media_files.append(second_audio)

            clip_audio = get_file_path(scenario, "clip_audio")
            if clip_audio:
                valid_media_files.append(clip_audio)
            clip_video = get_file_path(scenario, "clip")
            if clip_video:
                valid_media_files.append(clip_video)

            clip_left = get_file_path(scenario, "clip_left")
            if clip_left:
                valid_media_files.append(clip_left)
            clip_right = get_file_path(scenario, "clip_right")
            if clip_right:
                valid_media_files.append(clip_right)

            second_left = get_file_path(scenario, "second_left")
            if second_left:
                valid_media_files.append(second_left)
            second_right = get_file_path(scenario, "second_right")
            if second_right:
                valid_media_files.append(second_right)

            zero_left = get_file_path(scenario, "zero_left")
            if zero_left:
                valid_media_files.append(zero_left)
            zero_right = get_file_path(scenario, "zero_right")
            if zero_right:
                valid_media_files.append(zero_right)

            back_video = get_file_path(scenario, "back")
            if back_video:
                valid_media_files.append(back_video)

            clip_image = get_file_path(scenario, "clip_image")
            if clip_image:
                valid_media_files.append(clip_image)
            clip_image_last = get_file_path(scenario, "clip_image_last")
            if clip_image_last:
                valid_media_files.append(clip_image_last)

            second_image = get_file_path(scenario, "second_image")
            if second_image:
                valid_media_files.append(second_image)
            second_image_last = get_file_path(scenario, "second_image_last")
            if second_image_last:
                valid_media_files.append(second_image_last)

            zero_image = get_file_path(scenario, "zero_image")
            if zero_image:
                valid_media_files.append(zero_image)
            zero_image_last = get_file_path(scenario, "zero_image_last")
            if zero_image_last:
                valid_media_files.append(zero_image_last)

            speak_audio = get_file_path(scenario, "speak_audio")
            if speak_audio:
                valid_media_files.append(speak_audio)
            main_audio = get_file_path(scenario, "main_audio")
            if main_audio:
                valid_media_files.append(main_audio)
            main_video = get_file_path(scenario, "main_video")
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


    # av_type: image_generation, IMAGE, WS2V, FS2V, S2V, I2V, 2I2V, AI2V
    def build_prompt(self, scenario_data, style, extra, track, av_type):
        prompt_dict = {}
        # 提取当前场景的关键信息
        speaker = scenario_data.get("speaker", "")
        speaker_position = scenario_data.get("speaker_position", "")
        speaker_mood = scenario_data.get("mood", "calm")

        if ("clip" in track or "zero" in track) and "IMAGE" in av_type:
            if style:
                prompt_dict["IMAGE_STYLE"] = style

        if "second" in track or "zero" in track:
            if "content" in scenario_data:
                content = scenario_data['content']
                if speaker:
                    if speaker_position and speaker_position == "left":
                        prompt_dict["SPEAKING"] = f"the person on left-side is in {speaker_mood} mood to say ({content}),  while acting like ({scenario_data['speaker_action']})"
                        if av_type == "WS2V":
                            prompt_dict["LISTENING"] = f"the person on right-side is listening this content : {content}, while engaging with lots of reactions, expressions, and hand movements."
                    elif speaker_position and speaker_position == "right":
                        prompt_dict["SPEAKING"] = f"the person on right-side is in {speaker_mood} mood to say ({content}),  while acting like ({scenario_data['speaker_action']})"
                        if av_type == "WS2V":
                            prompt_dict["LISTENING"] = f"the person on left-side is listening this content : ({content}), while engaging with lots of reactions, expressions, and hand movements."
                    else:
                        prompt_dict["SPEAKING"] = f"the person is in {speaker_mood} mood to say ({content}),  while acting like ({scenario_data['speaker_action']})"
                else:
                    prompt_dict["SPEAKING"] = content

        if "clip" in track or "zero" in track:
            if "person_in_story_action" in scenario_data:
                person_in_story_action = scenario_data['person_in_story_action']
                # if person_in_story_action has words like ["no xx person", "no xx character", "none"], then don't add it to the content
                person_lower = person_in_story_action.lower()
                # Check for patterns like: "no person", "no specific person", "no other character", "none", etc.
                has_negative_pattern = (
                    re.search(r'\bno\b.*\bpersons?\b', person_lower) or  # matches "no person", "no persons", "no specific person"
                    re.search(r'\bno\b.*\bcharacters?\b', person_lower) or  # matches "no character", "no characters", "no other character"
                    re.search(r'\bn/a\b', person_lower) or  # matches "n/a"
                    re.search(r'\bnone\b', person_lower)  # matches "none"
                )
                if not has_negative_pattern:
                    prompt_dict["PERSON_RELATION"] = person_in_story_action
            if "camera_light" in scenario_data:
                prompt_dict["CAMERA_LIGHTING"] = scenario_data['camera_light']

        if "story_expression" in scenario_data:
            prompt_dict["SUMMARY"] = scenario_data['story_expression']
        if "era_time" in scenario_data and "location" in scenario_data:
            prompt_dict["BACKGROUND"] = f"ERA: {scenario_data['era_time']}; LOCATION: {scenario_data['location']}"

        if extra:
            prompt_dict["FYI"] = extra

        return prompt_dict


    def prompt_dict_to_string(self, prompt_dict):
        """将提示词字典转换为字符串格式（用于显示或旧版接口）"""
        if isinstance(prompt_dict, str):
            return prompt_dict  # 如果已经是字符串，直接返回
        if isinstance(prompt_dict, dict):
            # 转换为 JSON 格式字符串
            import json
            return json.dumps(prompt_dict, ensure_ascii=False, indent=2)
        return str(prompt_dict)


    def create_story_images(self, story_json_content, image_style, extra_description, negative, image_folder):
        """创建故事图像"""
        print(f"🎭 开始创建沉浸式故事音频...")
        # 读取沉浸故事JSON
        story_json = json.loads(story_json_content)
        
        if not story_json:
            print(f"❌ 沉浸故事内容为空")
            return None
        
        print(f"📝 沉浸故事包含 {len(story_json)} 个对话片段")

        for i,conversation in enumerate(story_json):
            scenario = {}
            scenario["clip_image"] = f"{config.get_project_path(self.pid)}/{image_folder}/{i}.png"
            scenario["summary"] = conversation["english_explanation"],

            self._create_image(   self.workflow.sd_processor.gen_config["Story"], 
                                                scenario, 
                                                "clip",
                                                image_style, 
                                                extra_description, 
                                                negative,
                                                int(time.time())    )
        return  True 


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
    def prepare_notebooklm_for_project(self, style, topic, avoid_content, location, general_location, previous_dialogue, introduction_story, introduction_type):
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
            
            introduction_story = self.summarizer.generate_text_summary(config.STORY_SUMMARY_SYSTEM_PROMPT, user_prompt, 1)

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

            previous_dialogue = self.summarizer.generate_text_summary(config.STORY_SUMMARY_SYSTEM_PROMPT, user_prompt, 1)

            previous_dialogue = f"""
                "Previous_Dialogue" : "This dialogue follows the previous story-telling-dialogue, talking about : '{previous_dialogue}'.    !!! This dialogue may mention the previous content quickly, but DO NOT talking the details again !!!",
            """
        else:
            previous_dialogue = ""

        user_prompt = config.fetch_story_extract_text_content(self.pid, self.language)


        if general_location:
            dialogue_opening = self.summarizer.generate_text_summary(config.NOTEBOOKLM_OPENING_DIALOGUE_PROMPT.format(location=location), user_prompt, 1)
            dialogue_opening = f"""
                "Dialogue_Openning" : "The dialogue should open with Immersive-Narrative like : '{dialogue_opening}'.  (Don't directly use, please re-organize / re-phrase the content in more infectious way)",
                """
    
            dialogue_ending = self.summarizer.generate_text_summary(config.NOTEBOOKLM_ENDING_DIALOGUE_PROMPT.format(location=location), user_prompt, 1)
            dialogue_ending = f"""
                "Dialogue_Ending" : "The dialogue should end like : '{dialogue_ending}'.     (Don't directly use, please re-organize / re-phrase the content in more infectious way)",
                """

            immersive_env_scene = self.summarizer.generate_simple_text_summary(config.NOTEBOOKLM_LOCATION_ENVIRONMENT_PROMPT.format(location=location, general_location=general_location), 1)
            # replace all new line characters with space
            immersive_env_scene = immersive_env_scene.replace("\n", " ").replace("\r", " ")
            location = f"""
                "Location" : "the dialogue happens at: '{location}'; The enviroment is like '{immersive_env_scene}'",
                """
        else:
            dialogue_opening = ""
            dialogue_ending = ""
            location = ""


        return config.NOTEBOOKLM_PROMPT.format(
            style=style,
            topic=topic,
            avoid_content=avoid_content,
            location=location,
            previous_dialogue=previous_dialogue,
            introduction_story=introduction_story,
            dialogue_openning=dialogue_opening,
            dialogue_ending=dialogue_ending
        )
 
 
    def create_titles_and_tags(self):
        system_prompt = config.TITLE_SUMMARIZATION_SYSTEM_PROMPT.format(
            language=config.LANGUAGES[self.language],
            length=5
        )
        user_prompt = self.transcriber.fetch_text_from_json(config.get_project_path(self.pid)+"/main.srt.json")
        
        title_json_path = config.get_titles_path(self.pid, self.language)
        return self.summarizer.generate_json_summary(system_prompt, user_prompt, title_json_path)


    def prepare_suno_music(self, suno_lang, content, atmosphere, expression, structure, 
                                leading_melody, instruments, rhythm_groove):
        
        content = self.summarizer.generate_text_summary(config.SUNO_CONTENT_ENHANCE_SYSTEM_PROMPT, content, 1)
        suno_style_prompt = config.SUNO_STYLE_PROMPT.format(
            target=suno_lang,
            atmosphere=atmosphere,
            expression=expression+" ("+config.SUNO_CONTENT[expression]+")",
            structure=structure,
            melody=leading_melody,
            instruments=instruments,
            rhythm=rhythm_groove
        )
        # Build enhanced system prompt with new parameters
        music_prompt = self.summarizer.generate_json_summary(config.SUNO_MUSIC_SYSTEM_PROMPT.format(language_style=suno_lang), content)

        if music_prompt and len(music_prompt) > 0:
            content += "\n*** " + music_prompt[0]["music_expression"]
            content += "\n\n\n***" + suno_style_prompt
            content += "\n\n\n[LYRICS]\n" + music_prompt[0]["lyrics_suggestion"]

        suno_prompt_path = config.get_project_path(self.pid) + "/suno_prompt.txt"
        with open(suno_prompt_path, "w", encoding="utf-8") as f:
            f.write(content)
        return content



    def prepare_veo_prompts_for_project(self, general_location, scene_number, host_choice, title, ending_words, program_keywords):
        self.post_init(title, program_keywords)

        system_prompt = config.SCENARIO_SERIAL_SUMMARY_SYSTEM_PROMPT.format(
            general_location=general_location,
            scene_number=scene_number,
            host_choice=host_choice
        )

        user_prompt = config.fetch_story_extract_text_content(self.pid, self.language)

        veo_json_path = config.get_project_path(self.pid) + "/veo_prompts.json"
        return self.summarizer.generate_json_summary(system_prompt, user_prompt, veo_json_path)


    def find_clip_duration(self, current_scenario):
        clip_audio = get_file_path(current_scenario, "clip_audio")
        duration = None
        if clip_audio:
            duration = self.ffmpeg_audio_processor.get_duration(clip_audio)

        if not duration:
            clip_video = get_file_path(current_scenario, "clip")
            duration = self.ffmpeg_processor.get_duration(clip_video)

        current_scenario["duration"] = duration
        return duration


    def get_scenario_detail(self, scenario):
        indx = -1
        for i in range(len(self.scenarios)):
            if self.scenarios[i] is scenario:
                indx = i
                break

        if indx < 0:
            return 0.0, 0.0, 0.0, -1, 0, False # not found

        clip_duration = self.find_clip_duration(scenario)

        ss = self.scenarios_in_story(scenario)
        story_duration = 0.0
        for s in ss:
            story_duration += self.find_clip_duration(s)
        start_time_in_story = 0.0
        for s in ss:
            if s == scenario:
                break
            start_time_in_story += self.find_clip_duration(s)

        return start_time_in_story, clip_duration, story_duration, indx, len(ss), s == ss[-1]


    def merge_scenario(self, from_index, to_index):
        if not (from_index-to_index==1 or from_index-to_index==-1):
            return False
        if from_index > len(self.scenarios) - 1 or from_index < 0:
            return False
        if to_index > len(self.scenarios) - 1 or to_index < 0:
            return False

        from_scenario = self.scenarios[from_index]
        to_scenario = self.scenarios[to_index]

        # merged_duration = self.find_duration(from_scenario) + self.find_duration(to_scenario)
        if from_index > to_index:
            from_scenario["content"] = to_scenario["content"] + from_scenario["content"]
            audio_list = [get_file_path(to_scenario, "clip_audio"), get_file_path(from_scenario, "clip_audio")]
            video_list = [get_file_path(to_scenario, "clip"), get_file_path(from_scenario, "clip")]
        else:
            from_scenario["content"] = from_scenario["content"] + to_scenario["content"]
            audio_list = [get_file_path(from_scenario, "clip_audio"), get_file_path(to_scenario, "clip_audio")]
            video_list = [get_file_path(from_scenario, "clip"), get_file_path(to_scenario, "clip")]

        same_main_scenarios = self.scenarios_in_story(from_scenario)
        if len(same_main_scenarios) > 1:
            self.refresh_scenario_media(from_scenario, "clip_audio", ".wav",  self.ffmpeg_audio_processor.concat_audios(audio_list))
            self.refresh_scenario_media(from_scenario, "clip", ".mp4",  self.ffmpeg_processor.concat_videos(video_list, True))
        else:
            self.refresh_scenario_media(from_scenario, "clip_audio", ".wav", get_file_path(from_scenario, "main_audio"), True)
            self.refresh_scenario_media(from_scenario, "clip", ".mp4", get_file_path(from_scenario, "main_video"), True)

        del self.scenarios[to_index]

        self.refresh_scenario(from_scenario)

        #self._generate_video_from_image(from_scenario)
        return True


    def clone_scenario(self, current_index, is_append=False):
        if current_index < 0 or current_index >= len(self.scenarios):
            return False

        if is_append:
            new_scenarios = [self.scenarios[current_index], self.scenarios[current_index].copy()]
            self.replace_scenario_with_others(current_index+1, new_scenarios)
        else:
            new_scenarios = [self.scenarios[current_index].copy(), self.scenarios[current_index]]
            self.replace_scenario_with_others(current_index, new_scenarios)


    def replace_scenario(self, current_index, new_scenario=None):
        if current_index >= len(self.scenarios):
            return None

        old_scenario = self.scenarios[current_index]
        ss = self.scenarios_in_story(old_scenario)
        
        if new_scenario:
            self.scenarios[current_index] = new_scenario
        else:
            del self.scenarios[current_index]

        if len(ss) == 1:
            return None

        # delete old_scenario from ss
        ss.remove(old_scenario)
        return ss


    def replace_scenario_with_others(self, current_index, new_scenarios):
        if current_index < 0 or current_index >= len(self.scenarios):
            return False  # invalid index

        # Replace the single item with the list of new scenarios
        self.scenarios = (
            self.scenarios[:current_index] +
            new_scenarios +
            self.scenarios[current_index + 1:]
        )
        self.save_scenarios_to_json()
        return True


    def split_scenario_at_position(self, n, position):
        """分离当前场景"""
        if n<0  or n >= len(self.scenarios):
            return False

        current_scenario = self.scenarios[n]

        original_duration = self.find_clip_duration(current_scenario)
        if position<=0 or position >= original_duration:
            return False

        original_content = current_scenario.get("content", "")
        original_audio_clip = get_file_path(current_scenario, "clip_audio")
        original_video_clip = get_file_path(current_scenario, "clip")

        next_scenario = current_scenario.copy()

        self.replace_scenario_with_others(n, [current_scenario, next_scenario])

        current_ratio = position / original_duration

        first, second = self.ffmpeg_audio_processor.split_audio(original_audio_clip, position)
        self.refresh_scenario_media(current_scenario, "clip_audio", ".wav", first)
        self.refresh_scenario_media(next_scenario, "clip_audio", ".wav", second)

        first, second = self.ffmpeg_processor.split_video(original_video_clip, position)
        self.refresh_scenario_media(current_scenario, "clip", ".mp4", first)
        self.refresh_scenario_media(next_scenario, "clip", ".mp4", second)

        current_scenario["content"] = original_content[:int(len(original_content)*current_ratio)]
        current_scenario["id"] = current_scenario["id"] + 1
        next_scenario["content"] = original_content[int(len(original_content)*(1.0-current_ratio)):]
        next_scenario["id"] = next_scenario["id"] + 2

        #self._generate_video_from_image(current_scenario)
        #self._generate_video_from_image(next_scenario)

        #self.refresh_scenario(current_scenario)
        #self.refresh_scenario(next_scenario)

        self.save_scenarios_to_json()

        return True


    def shift_scenario(self, n, m, position):
        """分离为n张图片"""
        if n<=0  or n > len(self.scenarios) or m<=0  or m > len(self.scenarios):
            return False

        if abs(n-m) != 1:
            return False
        
        current_scenario = self.scenarios[n]
        next_scenario = self.scenarios[m]

        original_audio_clip = get_file_path(current_scenario, "clip_audio")
        original_video_clip = get_file_path(current_scenario, "clip")     
        original_duration = self.ffmpeg_audio_processor.get_duration(original_audio_clip)
        if position<=0 or position >= original_duration:
            return False

        firsta, seconda = self.ffmpeg_audio_processor.split_audio(original_audio_clip, position)

        if n < m: 
            self.refresh_scenario_media(current_scenario, "clip_audio", ".wav", firsta)
            mergeda = self.ffmpeg_audio_processor.concat_audios([seconda, get_file_path(next_scenario, "clip_audio")])
            self.refresh_scenario_media(next_scenario, "clip_audio", ".wav", mergeda)
        else:
            self.refresh_scenario_media(current_scenario, "clip_audio", ".wav", seconda)
            mergeda = self.ffmpeg_audio_processor.concat_audios([get_file_path(next_scenario, "clip_audio"), firsta])
            self.refresh_scenario_media(next_scenario, "clip_audio", ".wav", mergeda)

        current_video = get_file_path(current_scenario, "clip")
        current_video = self.ffmpeg_processor.add_audio_to_video(current_video, current_scenario["clip_audio"])
        self.refresh_scenario_media(current_scenario, "clip", ".mp4", current_video)

        next_video = get_file_path(next_scenario, "clip")
        next_video = self.ffmpeg_processor.add_audio_to_video(next_video, next_scenario["clip_audio"])  
        self.refresh_scenario_media(next_scenario, "clip", ".mp4", next_video)

        self.save_scenarios_to_json()

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
        elif sd_config["model"] == "flux":
            image = self.sd_processor.text2Image_flux(
                positive,
                negative, 
                sd_config["url"], 
                sd_config["workflow"],
                sd_config["cfg"], 
                seed or sd_config["seed"], 
                sd_config["steps"], 
                sd_width, 
                sd_height
            )
        elif sd_config["model"] == "flux1":
            image = self.sd_processor.image2Image_flux(
                positive,
                negative, 
                sd_config["url"], 
                sd_config["workflow"],
                figures,
                sd_config["cfg"], 
                seed or sd_config["seed"], 
                sd_config["steps"], 
                sd_width, 
                sd_height
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


    def load_scenarios(self):
        self.scenarios = []
        scenarios_file = config.get_scenarios_path(self.pid)
        if not os.path.exists(scenarios_file):
            return

        with open(scenarios_file, "r", encoding="utf-8") as f:
            self.scenarios = json.load(f)

        if len(self.scenarios) == 0:
            background_image = self.find_default_background_image()
            background_music = self.find_default_background_music()
            background_video = self.find_default_background_video()
            self.add_root_scenario(0, self.story_site, background_image, background_music, background_video, False)
            self.save_scenarios_to_json()
            return
            

        changed = False    
        for scenario in self.scenarios:
            zero_video = get_file_path(scenario, "zero")
            zero_audio = get_file_path(scenario, "zero_audio")
            zero_image = get_file_path(scenario, "zero_image")

            if not zero_audio:
                if zero_video:
                    oldv, zero_audio = self.refresh_scenario_media(scenario, "zero_audio", ".wav", self.ffmpeg_audio_processor.extract_audio_from_video(zero_video))
                else:
                    olda, zero_audio = self.refresh_scenario_media(scenario, "zero_audio", ".wav", self.find_default_background_music())
                ss = self.scenarios_in_story(scenario)
                for s in ss:
                    s["zero_audio"] = zero_audio
                changed = True
            if not zero_image:
                zero_image = self.find_default_background_image()
                oldi, zero_image = self.refresh_scenario_media(scenario, "zero_image", ".webp", zero_image)
                ss = self.scenarios_in_story(scenario)
                for s in ss:
                    s["zero_image"] = zero_image
                changed = True
            if not zero_video:
                zero_video = self.ffmpeg_processor.image_audio_to_video(zero_image, zero_audio, 1)
                oldv, zero_video = self.refresh_scenario_media(scenario, "zero", ".mp4", zero_video)
                ss = self.scenarios_in_story(scenario)
                for s in ss:
                    s["zero"] = zero_video
                changed = True


        for scenario in self.scenarios:
            clip_audio = get_file_path(scenario, "clip_audio")
            clip_video = get_file_path(scenario, "clip")
            clip_image = get_file_path(scenario, "clip_image")
            if not clip_audio:
                if clip_video:
                    olda, clip_audio = self.refresh_scenario_media(scenario, "clip_audio", ".wav", self.ffmpeg_audio_processor.extract_audio_from_video(clip_video))
                else:
                    olda, clip_audio = self.refresh_scenario_media(scenario, "clip_audio", ".wav", self.find_default_background_music())
                changed = True
            if not clip_image:
                oldi, clip_image = self.refresh_scenario_media(scenario, "clip_image", ".webp", self.find_default_background_image())
                changed = True
            if not clip_video:
                clip_video = self.ffmpeg_processor.image_audio_to_video(clip_image, clip_audio, 1)
                oldv, clip_video = self.refresh_scenario_media(scenario, "clip", ".mp4", clip_video)
                changed = True

            second_audio = get_file_path(scenario, "second_audio")
            second_image = get_file_path(scenario, "second_image")
            second_video = get_file_path(scenario, "second")
            if not second_audio:
                if second_video:
                    olda, second_audio = self.refresh_scenario_media(scenario, "second_audio", ".wav", self.ffmpeg_audio_processor.extract_audio_from_video(second_video))
                else:
                    olda, second_audio = self.refresh_scenario_media(scenario, "second_audio", ".wav", self.find_default_background_music())
                changed = True
            if not second_image:
                oldi, second_image = self.refresh_scenario_media(scenario, "second_image", ".webp", self.find_default_background_image())
                changed = True
            if not second_video:
                second_video = self.ffmpeg_processor.image_audio_to_video(second_image, second_audio, 1)
                oldv, second_video = self.refresh_scenario_media(scenario, "second", ".mp4", second_video)
                changed = True

        for scenario in self.scenarios:
            start_time_in_story, clip_duration, story_duration, indx, count, is_story_last_clip = self.get_scenario_detail(scenario)
            if is_story_last_clip:
                zero_audio = get_file_path(scenario, "zero_audio")
                clip_video = get_file_path(scenario, "clip")
                clip_audio = get_file_path(scenario, "clip_audio")
                if zero_audio:
                    zero_audio_duration = self.ffmpeg_audio_processor.get_duration(zero_audio)
                    if zero_audio_duration > start_time_in_story + clip_duration + 0.1: # need to fix
                        a = self.ffmpeg_audio_processor.extend_audio(clip_audio, zero_audio_duration-start_time_in_story)
                        olda, a = self.refresh_scenario_media(scenario, "clip_audio", ".wav", a)
                        v = self.ffmpeg_processor.add_audio_to_video(clip_video, a)
                        self.refresh_scenario_media(scenario, "clip", ".mp4", v)

        if changed:
            self.save_scenarios_to_json()


    def get_image_main_scenarios(self):
        """获取所有标记为IMAGE_MAIN的场景，用于制作缩略图"""
        image_main_scenarios = []
        for i, scenario in enumerate(self.scenarios):
            if scenario.get("clip_animation", "") == "IMAGE_MAIN":
                image_main_scenarios.append({
                    "index": i,
                    "scenario": scenario,
                    "image_path": scenario.get("clip_image", "")
                })
        return image_main_scenarios


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

            content.append(item["keywords"])
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
        #if subtitle is json file, load it, then for each json item, get the 'content' field, concat them by \n, as srt_content
        script_lines = []

        try:
            json_content = json.loads(subtitle)
            srt_content = ""
            for item in json_content:
                script_lines.append(item["content"])
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


    def save_scenarios_to_json(self):
        # config.clear_temp_files()
        try:
            with open(config.get_scenarios_path(self.pid), "w", encoding="utf-8") as f:
                json.dump(self.scenarios, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ 保存scenarios到JSON失败: {str(e)}")
            return False


    def scenarios_in_story(self, scenario):
        if len(self.scenarios) == 0 or scenario is None:
            return []

        root_id = int(scenario["id"]/10000)
        scenarios = []
        for s in self.scenarios:
            if int(s["id"]/10000) == root_id:
                scenarios.append(s)

        scenarios.sort(key=lambda x: x["id"])
        return scenarios


    def next_scenario_of_story(self, scenario):
        ss = self.scenarios_in_story(scenario)
        if len(ss) < 2:
            return None
        # get the index of scenario in ss
        index = ss.index(scenario)
        if index == len(ss) - 1:
            return None
        return ss[index + 1]


    def first_scenario_of_story(self, scenario):
        ss = self.scenarios_in_story(scenario)
        if len(ss) == 0:
            return True
        return ss[0] == scenario


    def last_scenario_of_story(self, scenario):
        ss = self.scenarios_in_story(scenario)
        if len(ss) == 0:
            return True
        return ss[-1] == scenario

        
 
    def replace_scenario_second(self, current_scenario, source_video_path, source_audio_path):
        oldv, secondv = self.refresh_scenario_media(current_scenario, "second", ".mp4", source_video_path)
        olda, seconda = self.refresh_scenario_media(current_scenario, "second_audio", ".wav", source_audio_path)

        for s in self.scenarios_in_story(current_scenario):
            s["second"] = secondv
            s["second_audio"] = seconda

        self.save_scenarios_to_json()


    def is_last_scenario(self, scenario, scenarios):
        if len(scenarios) <= 1 or scenario is scenarios[-1]:
            return True
        try:
            next_scenario = scenarios[scenarios.index(scenario) + 1]
            return next_scenario["main_audio"] != scenario["main_audio"]
        except:
            return True
        

    def sync_scenario_audio(self, scenario, force=False):
        #clip_image = get_file_path(scenario, "clip_image")
        # second = scenario.get("second")
        zero = get_file_path(scenario, "zero")
        if not zero:
            print(f"❌ 没有找到zero视频")
            return None

        zero_audio = get_file_path(scenario, "zero_audio")
        if not zero_audio:
            print(f"❌ 没有找到zero音频")
            return None

        zero_image = get_file_path(scenario, "zero_image")
        if not zero_image:
            print(f"❌ 没有找到zero图片")
            return None

        clip_video = get_file_path(scenario, "clip")
        if not clip_video or force:
            oldv, clip_video = self.refresh_scenario_media(scenario, "clip", ".mp4", zero, True)

        clip_audio = get_file_path(scenario, "clip_audio")
        if not clip_audio or force:
            olda, clip_audio = self.refresh_scenario_media(scenario, "clip_audio", ".wav", zero_audio, True)

        clip_image = get_file_path(scenario, "clip_image")
        if not clip_image or force:
            oldi, clip_image = self.refresh_scenario_media(scenario, "clip_image", ".webp", zero_image, True)

        return clip_audio


    def refresh_scenario_media(self, scenario, media_type, media_postfix, replacement=None, make_replacement_copy=False):
        new_media_stem = media_type + "_" + str(int(datetime.now().timestamp()*100 + self.media_count%100))
        self.media_count = (self.media_count + 1) % 100

        old_media_path = scenario.get(media_type, None)
        scenario[media_type] = config.get_media_path(self.pid) + "/" + new_media_stem + media_postfix

        if replacement:
            copy_file(replacement, scenario[media_type])
            if not make_replacement_copy:
                safe_remove(replacement)
        return old_media_path, scenario[media_type]

            
    def replace_scenario_image(self, current_scenario, source_image_path, vertical_line_position, target_field):
        oldi, image_path = self.refresh_scenario_media(current_scenario, target_field, ".webp")

        with Image.open(source_image_path) as img:
            # 转换为RGB模式（如果是RGBA或其他模式）
            if img.mode in ('RGBA', 'LA'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])  # 使用alpha通道作为mask
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # resize image to 1920*1080
            img = img.resize((self.ffmpeg_processor.width, self.ffmpeg_processor.height))
            img.save(image_path, 'WEBP', quality=90, method=6)

        description = self.sd_processor.describe_image_openai(image_path)
        current_scenario[target_field + "_extra"] = description

        current_scenario[target_field + "_split"] = vertical_line_position
        clip_image_last = get_file_path(current_scenario, target_field + "_last")
        if not clip_image_last:
            current_scenario[target_field + "_last"] = image_path

        target_image = get_file_path(current_scenario, target_field)
        target_image_last = get_file_path(current_scenario, target_field + "_last")
         
        ss = self.scenarios_in_story(current_scenario)
        for scenario in ss:
            if scenario == current_scenario:
                continue

            image = get_file_path(scenario, target_field)
            if not image and target_image:
                self.refresh_scenario_media(scenario, target_field, ".webp", target_image, True)
                scenario[target_field + "_extra"] = description

            image_last = get_file_path(scenario, target_field + "_last")
            if not image_last and target_image_last:
                self.refresh_scenario_media(scenario, target_field + "_last", ".webp", target_image_last, True)

        self.save_scenarios_to_json()


    def upload_video(self, title):
        title_cvt = self.transcriber.chinese_convert(title, self.language)
        title_used = title_cvt.replace("_", " ")
        title_used = title_used.replace("\n", " ")
        self.title = title_used

        for scenario in self.scenarios:
            if scenario.get("clip_animation", "") == "IMAGE_MAIN":
                image_main_scenario = scenario
                break

        if not image_main_scenario:
            for scenario in self.scenarios:
                clip_animation = scenario.get("clip_animation", "")
                if clip_animation == "VIDEO" or clip_animation == "IMAGE" or clip_animation == "IMAGE_MAIN":
                    image_main_scenario = scenario
                    break

        if not image_main_scenario:
            print(f"❌ 没有找到IMAGE_MAIN场景")
            return

        thumbnail_path = f"{config.get_project_path(self.pid)}/thumbnail.png"
        final_video_path = f"{self.publish_path}/{self.title.replace(' ', '_')}_final.mp4"

        sums = config.fetch_main_summary_content(self.pid, self.language)
        if not sums:
            sums = "《"+config.channel_config[self.channel]["channel_name"]+"》 "+self.title
        sums = self.transcriber.chinese_convert(sums, self.language)

        final_srt_path = f"{self.publish_path}/{self.title.replace(' ', '_')}_final.srt"

        video_id = self.downloader.upload_video(final_video_path, 
                                     thumbnail_path, 
                                     title=title, 
                                     description=sums, 
                                     language=self.language, 
                                     script_path=final_srt_path, 
                                     secret_key=config.channel_config[self.channel]["channel_key"],
                                     channel_id=self.channel,
                                     categoryId=config.channel_config[self.channel]["channel_category_id"][0], 
                                     tags=config.channel_config[self.channel]["channel_tags"], 
                                     privacy="unlisted")
        # save video_id to the project_config
        try:
            from project_manager import ProjectConfigManager
            config_manager = ProjectConfigManager(self.pid)
            # Load existing config or create new one
            existing_config = config_manager.load_config(self.pid) or {}
            # Add video_id to config
            existing_config["video_id"] = video_id
            # Save the updated config
            config_manager.project_config = existing_config
            config_manager.save_project_config(existing_config)
            print(f"✅ Video ID saved to project config: {video_id}")
        except Exception as e:
            print(f"❌ Failed to save video_id to project config: {e}")



    def upload_promo_video(self, title, description):
        # need to get video_id from the project_config
        try:
            from project_manager import ProjectConfigManager
            config_manager = ProjectConfigManager(self.pid)
            existing_config = config_manager.load_config(self.pid) or {}
            video_id = existing_config.get("video_id", None)
        except Exception as e:
            print(f"❌ Failed to get video_id from project config: {e}")

        promo_video_path = f"{self.publish_path}/{title.replace(' ', '_')}_promo.mp4"
        if os.path.exists(promo_video_path):
            channel_name = self.transcriber.chinese_convert(config.channel_config[self.channel]["channel_name"], self.language)
            self.downloader.upload_video(promo_video_path, 
                            None, 
                            title=f"《{channel_name}》：{title}", 
                            description=channel_name,
                            language=self.language, 
                            script_path=None, 
                            secret_key=config.channel_config[self.channel]["channel_key"],
                            channel_id=self.channel,
                            categoryId=config.channel_config[self.channel]["channel_category_id"][0],
                            tags=config.channel_config[self.channel]["channel_tags"], 
                            privacy="unlisted")
        return promo_video_path


    def build_single_mv(self, background_music_mp3, background_images):
        whole_duration = self.ffmpeg_audio_processor.get_duration(background_music_mp3)
        duration_count = 0
        video_list = [] 

        for repeat in range(1, 10):
            if whole_duration and duration_count > whole_duration:
                break
            for background_image_path in background_images:
                background_video_path = f"{self.channel_path}/{Path(background_image_path).stem}.mp4"
                if self.project_169_mode():
                    duration = 30
                else:
                    duration = 60

                if not os.path.exists(background_video_path):
                    if self.project_169_mode():
                        v = self.ffmpeg_processor.create_scroll_background_video_169(background_image_path, duration, duration)
                    else:
                        v = self.ffmpeg_processor.create_scroll_background_video_916(background_image_path, duration, duration)
                    os.replace(v, background_video_path)

                video_list.append( {"path":background_video_path, "transition":"fade", "duration":1.0} )
                duration_count += duration
                if duration_count > whole_duration:
                    break

        vv = self.ffmpeg_processor.concat_videos_demuxer(video_list)
        vv = self.ffmpeg_processor.add_audio_to_video(vv, background_music_mp3)
        project_background_video = f"{config.get_media_path(self.pid)}/background_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
        os.replace(vv, project_background_video)

        return project_background_video


    def build_full_music_video(self, mv_name, item_list, rebuild=False):
        mv_list = []
        for i, item in enumerate(item_list):
            mv_temp = self.build_single_mv(item)
            mv_list.append( {"path":mv_temp, "transition":"fade", "duration":1.0} )

        whole_video_path = f"{self.publish_path}/full_music_video_{mv_name}.mp4"
        vv = self.ffmpeg_processor.concat_videos_demuxer(mv_list, True)
        os.replace(vv, whole_video_path)  
        config.clear_temp_files()


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
        
        while i < len(self.scenarios):
            current_scenario = self.scenarios[i]
            current_story = current_scenario.get("story_expression", "")
            
            # Find all consecutive scenarios with the same story content
            start_index = i
            end_index = i
            
            start_formatted = base_seconds
            scenario_duration = self.get_scenario_duration(current_scenario)
            base_seconds += scenario_duration
            # Look ahead to find consecutive scenarios with same story
            while (end_index + 1 < len(self.scenarios) and 
                   self.scenarios[end_index + 1].get("story_expression", "") == current_story and
                   current_story.strip() != ""):  # Only combine non-empty content
                end_index += 1
                current_scenario = self.scenarios[end_index]
                base_seconds += scenario_duration

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
                    print(f"📝 Combined scenarios {start_index+1}-{end_index+1} with same content: '{current_story[:50]}{'...' if len(current_story) > 50 else ''}'")
            
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


    def find_matched_file(self, folder, prefix, post, keywords=None, used_files=None):
        best_matches = self.find_matched_files(folder, prefix, post, keywords)
        if not best_matches or len(best_matches) == 0:
            return None
        
        if not used_files:
            return random.choice(best_matches)
        
        for i in range(len(best_matches)):
            choice = random.choice(best_matches)
            if not choice in used_files:
                return choice
            
        return choice


    def find_matched_files(self, folder, prefix, post, keywords=None):
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


    def regenerate_audio(self, fresh_json, language):
        lang = "chinese" if language == "zh" or language == "tw" else "english"

        start_time = 0.0
        for json_item in fresh_json:
            start_time, json_item["speak_audio"] = self.regenerate_audio_item(json_item, start_time, language)

        return fresh_json, self.ffmpeg_audio_processor.concat_audios([json_item["speak_audio"] for json_item in fresh_json])


    def regenerate_audio_item(self, json_item, start_time, language):
        lang = "chinese" if language == "zh" or language == "tw" else "english"

        speaker = json_item["speaker"]
        content = json_item["content"]
        mood = json_item["mood"]

        ss = speaker.split(",")
        if len(ss) > 1:
            print(f"🎤 检测到多说话人模式: {len(ss)} 个说话人 - {', '.join([s.strip() for s in ss if s.strip()])}")

        voices = []
        for s in ss:
            s = s.strip()  # 去除可能的空格
            if not s:  # 跳过空字符串
                continue
            try:
                voice = self.speech_service.get_voice(s, lang)
                ssml = self.speech_service.create_ssml(text=content, voice=voice, mood=mood)
                audio_file = self.speech_service.synthesize_speech(ssml)
                if audio_file:  # 只添加成功生成的音频文件
                    voices.append(audio_file)
                else:
                    print(f"⚠️ 说话人 '{s}' 的语音合成失败")
            except Exception as e:
                print(f"❌ 说话人 '{s}' 的语音合成错误: {str(e)}")

        json_item["speak_audio"] = self.ffmpeg_audio_processor.audio_list_mix(voices)

        json_item["start"] = start_time
        json_item["duration"] = self.ffmpeg_audio_processor.get_duration(json_item["speak_audio"])
        json_item["end"] = start_time + json_item["duration"]

        return json_item["end"], json_item["speak_audio"]


    def make_scenario_name(self, scenario, av_type, postfix):
        if not scenario:
            return av_type + "_" + self.pid + "_" + "0000" + postfix
        return av_type + "_" + self.pid + "_" + str(scenario.get("id", "")) + postfix


    def check_generated_clip_video(self, scenario, video_type, audio_type):
        clip_animation = scenario.get("clip_animation", "")
        second_animation = scenario.get("second_animation", "")
        if clip_animation not in config._ANIMATE_TYPES and second_animation not in config._ANIMATE_TYPES:
            return None

        output_mp4_folder = "Z:/output_mp4"

        # 生成基础文件名前缀（不包括类型后缀）
        # 格式: av_type + "_" + pid + "_" + scenario_id
        base_name = self.make_scenario_name(scenario, video_type, "")
        
        # 定义文件类型模式列表，匹配格式: base_name + type_suffix + _timestamp.mp4
        # timestamp格式为 %d%H%M%S (8位数字: 日期+小时+分钟+秒)
        type_patterns = [
            (r"_I2V_\d{8}\.mp4$", "_I2V"),
            (r"_2I2V_\d{8}\.mp4$", "_2I2V"),
            (r"_L_WS2V_\d{8}\.mp4$", "_L_WS2V"),
            (r"_R_WS2V_\d{8}\.mp4$", "_R_WS2V"),
            (r"_S2V_\d{8}\.mp4$", "_S2V"),
            (r"_FS2V_\d{8}\.mp4$", "_FS2V"),
            (r"_AI2V_\d{8}\.mp4$", "_AI2V")
        ]
        
        files = []
        for file in os.listdir(output_mp4_folder):
            # 检查文件是否以基础名称开头
            if file.startswith(base_name):
                # 检查是否匹配任何一个类型模式
                for pattern, type_suffix in type_patterns:
                    if re.search(pattern, file):
                        files.append(file)
                        break

        if len(files) == 0:
            return None

        choose_file_stem = Path(files[0]).stem
        has_audio = True if "_L_WS2V" in choose_file_stem or "_R_WS2V" in choose_file_stem or "_S2V" in choose_file_stem or "_FS2V" in choose_file_stem   else False

        enhanced_video = output_mp4_folder + "/" + choose_file_stem + ".mp4"
        if not os.path.exists(enhanced_video):
            print(f"⚠️ 文件已经处理过，跳过: {enhanced_video}")
            return
        os.replace(enhanced_video, enhanced_video + ".bak.mp4")
        enhanced_video = enhanced_video + ".bak.mp4"

        audio = get_file_path(scenario, audio_type)
        if audio:
            if not has_audio:
                enhanced_video = self.ffmpeg_processor.add_audio_to_video(enhanced_video, audio)
        elif has_audio:
            audio = self.ffmpeg_audio_processor.extract_audio_from_video(enhanced_video)
            olda, audio = self.refresh_scenario_media(scenario, audio_type, ".wav", audio)

        if "_L_WS2V" in choose_file_stem:
            self.refresh_scenario_media(scenario, video_type+"_left", ".mp4", enhanced_video, True)
            #if scenario[video_type+"_left"] and scenario[video_type+"_right"]:
            #    scenario["clip_animation"] = ""
        elif "_R_WS2V" in choose_file_stem:
            self.refresh_scenario_media(scenario, video_type+"_right", ".mp4", enhanced_video, True)
            #if scenario[video_type+"_left"] and scenario[video_type+"_right"]:
            #    scenario["clip_animation"] = ""
        else:
            oldv, enhanced_video = self.refresh_scenario_media(scenario, video_type, ".mp4", enhanced_video, True)
            #scenario["clip_animation"] = ""

        self.save_scenarios_to_json()


    def rebuild_scenario_video(self, scenario, video_type, animate_mode, image_path, image_last_path, sound_path, action_path, wan_prompt):
        if not sound_path or not image_path:
            return
        if not image_last_path:
            image_last_path = image_path

        file_prefix = video_type + "_" + self.pid + "_" + str(scenario.get("id", ""))
        
        if animate_mode == "IMAGE":
            v = self.ffmpeg_processor.image_audio_to_video(image_path, sound_path, 1)
            self.refresh_scenario_media(scenario, video_type, ".mp4", v, True)

        elif animate_mode == "I2V":
            self.sd_processor.image_to_video( prompt=wan_prompt, file_prefix=file_prefix, image_path=image_path, sound_path=sound_path, animate_mode=animate_mode )

        elif animate_mode == "2I2V":
            self.sd_processor.two_image_to_video( prompt=wan_prompt, file_prefix=file_prefix, first_frame=image_path, last_frame=image_last_path, sound_path=sound_path )

        elif animate_mode == "S2V" or animate_mode == "FS2V":
            self.sd_processor.sound_to_video(prompt=wan_prompt, file_prefix=file_prefix, image_path=image_path, sound_path=sound_path, key=animate_mode, silence=False)

        elif animate_mode == "AI2V":
            if not action_path:
                action_path = f"{config.DEFAULT_MEDIA_PATH}/default_action.mp4"
            self.sd_processor.action_transfer_video(prompt=wan_prompt, file_prefix=file_prefix, image_path=image_path, sound_path=sound_path, action_path=action_path, key=animate_mode)

        elif animate_mode == "WS2V":
            vertical_line_position = scenario.get("clip_image_split", 0)
            if vertical_line_position == 0:
                return

            speaker = scenario.get("speaker", "")
            speaker_position = scenario.get("speaker_position", "")
            if not speaker or not speaker_position:
                return

            left_image, right_image = self.ffmpeg_processor.split_image(image_path, vertical_line_position)
            
            left_prompt = wan_prompt.copy()
            right_prompt = wan_prompt.copy()
            if speaker_position == "left":
                left_prompt.pop("LISTENING", None)
                right_prompt.pop("SPEAKING", None)
                self.sd_processor.sound_to_video(prompt=left_prompt, file_prefix=file_prefix+"_L", image_path=left_image, sound_path=sound_path, key="WS2V", silence=False)
                self.sd_processor.sound_to_video(prompt=right_prompt, file_prefix=file_prefix+"_R", image_path=right_image, sound_path=sound_path, key="WS2V", silence=True)
            elif speaker_position == "right":
                left_prompt.pop("SPEAKING", None)
                right_prompt.pop("LISTENING", None)
                self.sd_processor.sound_to_video(prompt=left_prompt, file_prefix=file_prefix+"_L", image_path=left_image, sound_path=sound_path, key="WS2V", silence=True)
                self.sd_processor.sound_to_video(prompt=right_prompt, file_prefix=file_prefix+"_R", image_path=right_image, sound_path=sound_path, key="WS2V", silence=False)


    def _process_single_files(self, scenario, found_files):
        """处理 S2V 模式的单个视频文件"""
        try:
            # 等待30秒确保文件完全生成
            print("⏳ 等待30秒确保文件生成完成...")
            time.sleep(30)
            
            for new_mp4 in found_files:
                print(f"📹 处理 S2V 视频文件: {os.path.basename(new_mp4)}")
                
                # 移动文件到项目媒体文件夹
                oldv, clip_raw_video = self.refresh_scenario_media(scenario, "clip_raw_video", ".mp4", new_mp4)

                temp_video =  config.get_temp_path(self.pid) + "/" + self.make_scenario_name(scenario, "clip", ".mp4")
                copy_file(clip_raw_video, temp_video)
                
                print(f"✅ 文件已移动到: {clip_raw_video}")
                
                # 调用 REST API 增强视频
                self._enhance_single_video(temp_video)
            
        except Exception as e:
            print(f"❌ 处理 S2V 文件时出错: {str(e)}")


    def _process_dual_files(self, scenario, found_files):
        """处理 WS2V 模式的双视频文件"""
        try:
            # 等待30秒确保文件完全生成
            print("⏳ 等待60秒确保文件生成完成...")
            time.sleep(60)
            
            temp_video =  config.get_temp_path(self.pid) + "/" + self.make_scenario_name(scenario, "clip", ".mp4")
            # 假设前两个文件分别是左右视频
            left_mp4 = found_files[0]
            right_mp4 = found_files[1]
            
            print(f"📹 处理 WS2V 左视频: {os.path.basename(left_mp4)}")
            print(f"📹 处理 WS2V 右视频: {os.path.basename(right_mp4)}")
            
            # 移动文件到项目媒体文件夹
            oldv1, clip_raw_video = self.refresh_scenario_media(scenario, "clip_raw_video", ".mp4", left_mp4)
            copy_file(clip_raw_video, temp_video)
            
            oldv2, clip_raw_video2 = self.refresh_scenario_media(scenario, "clip_raw_video2", ".mp4", right_mp4)
            
            print(f"✅ 左视频已移动到: {clip_raw_video}")
            print(f"✅ 右视频已移动到: {clip_raw_video2}")
            
            # 调用 REST API 增强双视频
            self._enhance_dual_video(temp_video, clip_raw_video2)
            
        except Exception as e:
            print(f"❌ 处理 WS2V 文件时出错: {str(e)}")
    

    def _enhance_single_video(self, video_path):
        """调用 REST API 增强单个视频"""
        try:
            url = "http://10.0.0.179:5000/process/single"
            
            with open(video_path, 'rb') as video_file:
                files = {'video': video_file}
                
                print(f"🚀 正在调用视频增强API: {url}")
                response = requests.post(url, files=files, timeout=300)
                
                if response.status_code >= 200 and response.status_code < 300:
                    print("✅ 单视频增强成功")
                    print(f"📄 响应: {response.text}")
                else:
                    print(f"❌ 单视频增强失败，状态码: {response.status_code}")
                    print(f"📄 错误信息: {response.text}")
                    
        except requests.exceptions.RequestException as e:
            print(f"❌ REST API 调用失败: {str(e)}")
        except Exception as e:
            print(f"❌ 增强单视频时出错: {str(e)}")
    

    def _enhance_dual_video(self, left_video_path, right_video_path):
        """调用 REST API 增强双视频"""
        try:
            url = "http://10.0.0.179:5000/process/dual"
            
            with open(left_video_path, 'rb') as left_file, open(right_video_path, 'rb') as right_file:
                files = {
                    'left_video': left_file,
                    'right_video': right_file
                }
                
                print(f"🚀 正在调用双视频增强API: {url}")
                response = requests.post(url, files=files, timeout=300)
                
                if response.status_code >= 200 and response.status_code < 300:
                    print("✅ 双视频增强成功")
                    print(f"📄 响应: {response.text}")
                else:
                    print(f"❌ 双视频增强失败，状态码: {response.status_code}")
                    print(f"📄 错误信息: {response.text}")
                    
        except requests.exceptions.RequestException as e:
            print(f"❌ REST API 调用失败: {str(e)}")
        except Exception as e:
            print(f"❌ 增强双视频时出错: {str(e)}")


    def finalize_video(self, title, program_keywords, zero_audio_only):
        self.post_init(title, program_keywords)
        
        #start = 0.0
        
        #if self.video_prepares["starting"]["video_path"] and os.path.exists(self.video_prepares["starting"]["video_path"]):
        #    video_segments.append({"path":self.video_prepares["starting"]["video_path"], "transition":"fade", "duration":1.0})
        #    start = start + self.ffmpeg_processor.get_duration(self.video_prepares["starting"]["video_path"])

        #if self.video_prepares["pre_video"]["video_path"] and os.path.exists(self.video_prepares["pre_video"]["video_path"]):
        #    video_segments.append({"path":self.video_prepares["pre_video"]["video_path"], "transition":"fade", "duration":1.0})
        #    start = start + self.ffmpeg_processor.get_duration(self.video_prepares["pre_video"]["video_path"])

        video_segments = []
        for s in self.scenarios:
            clip= s["clip"]
            video_segments.append({"path":clip, "transition":"fade", "duration":1.0})

        video_temp = self.ffmpeg_processor._concat_videos_with_transitions(video_segments, self.ffmpeg_processor.width, self.ffmpeg_processor.height, keep_audio_if_has=True)

        if zero_audio_only:
            audio_segments = []
            current_zero = None
            for s in self.scenarios:
                if not current_zero or current_zero != s["zero"]:
                    current_zero = s["zero"]
                    audio_segments.append(current_zero)

            audio_temp = self.ffmpeg_audio_processor.concat_audios(audio_segments)
            video_temp = self.ffmpeg_processor.add_audio_to_video(video_temp, audio_temp, False)
        else:
            audio_segments = []
            started = None
            last_end = 0.0
            for s in self.scenarios:
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
            video_temp = self.ffmpeg_processor.video_audio_mix(video_temp, audio_temp)

        final_video_path = f"{self.publish_path}/{self.title.replace(' ', '_')}_final.mp4"
        os.replace(video_temp, final_video_path)

        config.clear_temp_files()

        # prepare final srt file
        #final_srt_path = f"{self.publish_path}/{title.replace(' ', '_')}_final.srt"
        #self.prepare_final_script(start, final_srt_path)
 
        # add subtitle to the final video
        # self.ffmpeg_processor.add_subtitle(final_video_path, mp4_path, final_srt_path)
        print(f"✅ Final video with audio created: {final_video_path}")


    def prepare_scenarios_from_json(self, raw_scenario, raw_index, audio_json, style, shot, angle, color):
        # keep raw_id as integer    
        raw_id = int((raw_scenario["id"]/100)*100)

        system_prompt = config.VISUAL_STORY_SUMMARIZATION_SYSTEM_PROMPT.format(
            language=config.LANGUAGES[self.language],
            length=512
        )
        text_summary = self.summarizer.generate_text_summary(
                            system_prompt, 
                            "\n".join([segment["content"] for segment in audio_json]),
                            1 
                        )
        text_summary = text_summary + "\nThe story end like ... " + audio_json[-1]["content"]

        start_time = 0.0
        for audio_scenario in audio_json:
            raw_id += 100
            # 保存 audio_scenario 中需要保留的字段
            preserved_fields = {}
            for field in ["start", "end", "duration", "speaker", "content"]:
                if field in audio_scenario:
                    preserved_fields[field] = audio_scenario[field]
            
            # 克隆 raw_scenario 的所有字段到 audio_scenario
            audio_scenario.update(raw_scenario.copy())
            
            # 恢复保留的字段（覆盖从 raw_scenario 复制的值）
            audio_scenario.update(preserved_fields)
            
            # 更新特定字段
            audio_scenario.update({
                "id": raw_id,
                "wan_style": style,
                "wan_shot": shot,
                "wan_angle": angle,
                "wan_color": color,
                "clip_animation": "",
                "story_summary": text_summary
            })
            self.refresh_scenario(audio_scenario)

            clip_wav = self.ffmpeg_audio_processor.audio_cut_fade(audio_scenario["clip_audio"], audio_scenario["start"], audio_scenario["duration"])
            olda, clip_audio = self.refresh_scenario_media(audio_scenario, "clip_audio", ".wav", clip_wav)

            v = self.ffmpeg_processor.resize_video(raw_scenario["clip"], None, audio_scenario["start"], audio_scenario["end"])
            #v = self.ffmpeg_processor.add_audio_to_video(v, clip_audio)
            self.refresh_scenario_media(audio_scenario, "clip", ".mp4", v)

        self.replace_scenario_with_others(raw_index, audio_json)

        return audio_json


    def visualize_scenarios(self, audio_path, audio_json, general_location, style, shot, angle, color):
        system_prompt = config.VISUAL_STORY_SUMMARIZATION_SYSTEM_PROMPT.format(
            language=config.LANGUAGES[self.language],
            length=512
        )

        text_summary = self.summarizer.generate_text_summary(
                            system_prompt, 
                            "\n".join([segment["content"] for segment in audio_json]),
                            1 
                        )
        text_summary = text_summary + "\nThe story end like ... " + audio_json[-1]["content"]

        raw_json_path = f"{config.get_project_path(self.pid)}/{Path(audio_path).stem}.json"
        system_prompt = config.SCENARIO_SERIAL_SUMMARY_SYSTEM_PROMPT.format(
                                general_location=general_location,
                                style=style,
                                shot=shot,
                                angle=angle,
                                color=color
                            )
        user_prompt = json.dumps(audio_json, ensure_ascii=False, indent=2)

        raw_scenarios = self.summarizer.generate_json_summary(system_prompt, user_prompt, raw_json_path)

        for i, scenario_data in enumerate(raw_scenarios):
            scenario_data.update({
                # "effect": config.get_next_special_effect(),
                # "raw_scenario_index": f"{audio_stem}_raw_{i}",
                "clip_animation": "",
                "second_animation": "",
                "main_audio": audio_path,
                "story_summary": text_summary
            })

        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_scenarios, f, ensure_ascii=False, indent=2)

        print(f"raw scenarios summary done for {audio_path}...")
        return raw_scenarios, raw_json_path
		

    def extend_scenario(self, current_index, offset):
        if current_index < 0 or current_index >= len(self.scenarios):
            return False
        clip_audio = get_file_path(self.scenarios[current_index], "clip_audio")
        clip_video = get_file_path(self.scenarios[current_index], "clip")
        if not clip_audio or not clip_video:
            return False

        a = self.ffmpeg_audio_processor.audio_change(audio_path=clip_audio, fade_in_length=0.0, fade_out_length=0.0, volume=1.0, extend_length=offset)
        v = self.ffmpeg_processor.extend_video(clip_video, offset)
        self.refresh_scenario_media(self.scenarios[current_index], "clip_audio", ".wav", a)
        self.refresh_scenario_media(self.scenarios[current_index], "clip", ".mp4", v)
        self.save_scenarios_to_json()
        return True


    def swap_scenario(self, current_index, next_index):
        if current_index < 0 or current_index >= len(self.scenarios):
            return False
        if next_index < 0 or next_index >= len(self.scenarios):
            return False
        self.scenarios[current_index], self.scenarios[next_index] = self.scenarios[next_index], self.scenarios[current_index]
        temp = self.scenarios[current_index]["id"]
        self.scenarios[current_index]["id"] = self.scenarios[next_index]["id"]
        self.scenarios[next_index]["id"] = temp
        self.save_scenarios_to_json()
        return True



    def refresh_scenario(self, scenario, script_content=None):
        if script_content:
            scenario["content"] = script_content
        else:
            script_content = scenario.get("content", "")
 
        if not script_content or script_content == "":
            scenario["content"] = ""
            self.save_scenarios_to_json()
            return

        system_prompt = config.SCENARIO_SUMMARY_SYSTEM_PROMPT.format(
                                general_location=scenario.get("location",""), 
                                style=scenario["wan_style"], 
                                shot=scenario["wan_shot"], 
                                angle=scenario["wan_angle"], 
                                color=scenario["wan_color"]
                            )
        new_scenario = self.summarizer.generate_json_summary(system_prompt, script_content, None, False)
        if isinstance(new_scenario, list):
            if len(new_scenario) == 0:
                return
            new_scenario = new_scenario[0]

        scenario["story_expression"] = new_scenario.get("story_expression", scenario.get("story_expression", ""))
        scenario["person_in_story_action"] = new_scenario.get("person_in_story_action", scenario.get("person_in_story_action", ""))
        scenario["era_time"] = new_scenario.get("era_time", scenario.get("era_time", ""))
        scenario["location"] = new_scenario.get("location", scenario.get("location", ""))
        scenario["sound_effect"] = new_scenario.get("sound_effect", scenario.get("sound_effect", ""))
        scenario["speaker_action"] = new_scenario.get("speaker_action", scenario.get("speaker_action", ""))
        scenario["camera_light"] = new_scenario.get("camera_light", scenario.get("camera_light", ""))
        
        # sleep 3 seconds
        time.sleep(3)
        self.save_scenarios_to_json()


    def max_id(self):
        max_id = 0
        for s in self.scenarios:
            if s["id"] > max_id:
                max_id = s["id"]
        return max_id


    def add_root_scenario(self, scenario_index, site, background_image, background_music, background_video, is_append=False):
        print(f"🎭 开始创建场景...")
        video_as_scenario = False

        if not background_video:
            #background_video = self.build_single_mv(background_music, background_images)
            background_video = self.ffmpeg_processor.image_audio_to_video(background_image, background_music, 1)
        #else:
        #    v = f"{self.project_path}/media/background_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
        #    copy_file(background_video, v)
        #    background_video = v
        #    video_as_scenario = True

        next_root_id = (int(self.max_id()/10000) + 1)*10000
        scenario = {
                "id": next_root_id,
                "general_location": site,
                #"speaker": "",
                #"story_expression": "",
                #"content": "",
                #"era_time": "",
                #"person_in_story_action": "",
                #"speaker_action": "",
                #"camera_light": "",
                
                "clip_animation": "ADS" if video_as_scenario else "",
            }

        if not self.scenarios:
            self.scenarios = [scenario]
        else:
            if is_append:
                self.scenarios.insert(scenario_index+1, scenario)
            else:
                self.scenarios.insert(scenario_index, scenario) 

        self.refresh_scenario_media(scenario, "zero", ".mp4", background_video)
        self.refresh_scenario_media(scenario, "zero_audio", ".wav", background_music)
        self.refresh_scenario_media(scenario, "zero_image", ".webp", background_image)
        self.sync_scenario_audio(scenario, True)

        self.save_scenarios_to_json()