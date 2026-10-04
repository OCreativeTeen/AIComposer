from urllib.parse import urlparse, parse_qs

from utility.audio_transcriber import AudioTranscriber
from gui.downloader import MediaDownloader
from utility import sd_image_processor
from utility.sd_image_processor import SDProcessor
from utility.ffmpeg_processor import FfmpegProcessor
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
import os
import copy
import json
import shutil
import re
import time

# 连环画页面图和再合成的 PDF 都用这份 JPEG。质量压低一些，避免 PNG 把文件撑得太大。
_PAGE_JPEG_QUALITY = 60
_PAGE_WEBP_QUALITY = 80
from datetime import datetime
from pathlib import Path
import config
import tkinter.messagebox as messagebox
import config_prompt
from io import BytesIO
from utility.file_util import get_file_path, safe_remove, build_scene_media_prefix, write_json, ending_punctuation, safe_copy_overwrite
from utility.llm_api import LLMApi
import project_manager
from project_manager import refresh_scene_media, save_project_config
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
        self.downloader = MediaDownloader(self.pid, config.get_project_path(self.pid), language)
        self.llm_api = LLMApi()
        self.transcriber = AudioTranscriber(self.pid, model_size="small", device="cuda")

        config.create_project_path(pid)

        # Create project paths
        self.publish_path = config.PUBLISH_PATH + "/"
        self.project_path = config.get_project_path(pid)
        self.channel_path = config.get_channel_path(config.get_channel_id(channel))
        self.effect_path = config.get_effect_path()

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
        self.background_video = None

        # load_scenes() 之前若有代码路径调用 save_scenes_to_json，需有默认列表（GUI 启动顺序已保证先 load）
        self.scenes: list = []

    def post_init(self, title):
        if title:
            self.title = config.chinese_convert(title, self.language)


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

            clip_audio = get_file_path(scene, "clip_audio")
            if clip_audio:
                valid_media_files.append(clip_audio)
            clip_video = get_file_path(scene, "clip")
            if clip_video:
                valid_media_files.append(clip_video)

            narration = get_file_path(scene, "narration")
            if narration:
                valid_media_files.append(narration)
            narration_audio = get_file_path(scene, "narration_audio")
            if narration_audio:
                valid_media_files.append(narration_audio)


            zero_left = get_file_path(scene, "zero_left")
            if zero_left:
                valid_media_files.append(zero_left)
            zero_right = get_file_path(scene, "zero_right")
            if zero_right:
                valid_media_files.append(zero_right)

            clip_left = get_file_path(scene, "clip_left")
            if clip_left:
                valid_media_files.append(clip_left)
            clip_right = get_file_path(scene, "clip_right")
            if clip_right:
                valid_media_files.append(clip_right)

            narration_left = get_file_path(scene, "narration_left")
            if narration_left:
                valid_media_files.append(narration_left)
            narration_right = get_file_path(scene, "narration_right")
            if narration_right:
                valid_media_files.append(narration_right)


            back_video = get_file_path(scene, "back")
            if back_video:
                backs = back_video.split(',')
                for back in backs:
                    if back and os.path.exists(back):
                        valid_media_files.append(back)

            speaker_audio = get_file_path(scene, "speaker_audio")
            if speaker_audio:
                valid_media_files.append(speaker_audio)
            actor_audio = get_file_path(scene, "actor_audio")
            if actor_audio:
                valid_media_files.append(actor_audio)
            narrator_audio = get_file_path(scene, "narrator_audio")
            if narrator_audio:
                valid_media_files.append(narrator_audio)


            zero_image = get_file_path(scene, "zero_image")
            if zero_image:
                valid_media_files.append(zero_image)
            zero_image_last = get_file_path(scene, "zero_image_last")
            if zero_image_last:
                valid_media_files.append(zero_image_last)

            clip_image = get_file_path(scene, "clip_image")
            if clip_image:
                valid_media_files.append(clip_image)
            clip_image_last = get_file_path(scene, "clip_image_last")
            if clip_image_last:
                valid_media_files.append(clip_image_last)

            narration_image = get_file_path(scene, "narration_image")
            if narration_image:
                valid_media_files.append(narration_image)
            narration_image_last = get_file_path(scene, "narration_image_last")
            if narration_image_last:
                valid_media_files.append(narration_image_last)


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
        actor = scene_data.get("actor", "")
        speaking = scene_data.get("speaking", "")
        visual = scene_data.get("visual", "")

        narrator = project_manager.project_narrator()
        voiceover = scene_data.get("voiceover", "")

        if "narration" in track:
            if voiceover:
                if narrator:
                    prompt_dict["NARRATION"] = voiceover
                    if narrator.endswith("left"):
                        prompt_dict["NARRATOR"] = f"the left-side person ({narrator}), {actions}."
                        if av_type == "WS2V":
                            prompt_dict["NARRATOR"] = prompt_dict["NARRATOR"] + "... while the right-side person is listening."
                    elif narrator.endswith("right"):
                        prompt_dict["NARRATOR"] = f"the right-side person ({narrator}), {actions}."
                        if av_type == "WS2V":
                            prompt_dict["NARRATOR"] = prompt_dict["NARRATOR"] + "... while the left-side person is listening."
                    else:
                        prompt_dict["NARRATOR"] = f"the person ({narrator}), {actions}."
                elif speaking:
                    prompt_dict["SPEAKER"] = f"the person ({actor}), {actions}."
                    prompt_dict["SPEAKING"] = speaking

        if "clip" in track or "zero" in track:
            person_lower = actor
            if person_lower:
                has_negative_pattern = (
                    re.search(r'\bno\b.*\bpersons?\b', person_lower) or  # matches "no person", "no persons", "no specific person"
                    re.search(r'\bno\b.*\bspeakers?\b', person_lower) or  # matches "no speaker", "no speakers", "no other speaker"
                    re.search(r'\bno\b.*\bcharacters?\b', person_lower) or  # matches "no character", "no characters", "no other character"                    
                    re.search(r'\bn/a\b', person_lower) or  # matches "n/a"
                    re.search(r'\bnone\b', person_lower)  # matches "none"
                )
                if not has_negative_pattern:
                    prompt_dict["SPEAKER"] = f"the speaker ({actor}), {actions}."
                    prompt_dict["SPEAKING"] = speaking

        prompt_dict["visual"] = visual

        #if "cinematography" in scene_data:
        #    prompt_dict["CINEMATOGRAPHY"] = scene_data['cinematography']
        if extra:
            prompt_dict["CINEMATOGRAPHY"] = extra

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


    def merge_scene(self, from_index, to_index):
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

        speaking = from_scene.get("speaking", "")
        caption = from_scene.get("caption", "")
        voiceover = from_scene.get("voiceover", "")
        from_scene["speaking"] = speaking + "  " + to_scene.get("speaking", "") if ending_punctuation(speaking) else speaking + "... " + to_scene.get("speaking", "")
        from_scene["caption"] = caption + "  " + to_scene.get("caption", "") if ending_punctuation(caption) else caption + "... " + to_scene.get("caption", "")
        from_scene["voiceover"] = voiceover + "  " + to_scene.get("voiceover", "") if ending_punctuation(voiceover) else voiceover + "... " + to_scene.get("voiceover", "")
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

        self.release_scene_page_png(to_scene)
        del self.scenes[to_index]
        self.compact_episode_pages(self.scene_group(from_scene))
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
        self.touch_episode_media(self.scene_group(self.scenes[current_index]))


    def replace_scene(self, current_index, new_scene=None):
        if current_index >= len(self.scenes):
            return None

        old_scene = self.scenes[current_index]
        ss = self.scenes_in_story(old_scene)

        if new_scene:
            self.scenes[current_index] = new_scene
        else:
            episode = self.scene_group(old_scene)
            self.release_scene_page_png(old_scene)
            del self.scenes[current_index]
            self.compact_episode_pages(episode)

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


    def split_smart_scene(self, current_scene) -> list:
        """将场景按照指定时长分割成多个部分"""
        current_index = None
        for i, scene in enumerate(self.scenes):
            if scene is current_scene:
                current_index = i
                break

        original_audio_clip = get_file_path(current_scene, "clip_audio")
        original_video_clip = get_file_path(current_scene, "clip")
        original_duration = self.find_clip_duration(current_scene)
        if original_duration <= 0 or not original_audio_clip or not original_video_clip:
            return None

        s2v_config = None
        for config in [sd_image_processor.GEN_CONFIG["HS2V"], sd_image_processor.GEN_CONFIG["S2V"], sd_image_processor.GEN_CONFIG["FS2V"]]:
            s2v_config = config.copy()
            s2v_config["section_duration"] = (s2v_config["max_frames"]-4) * 1.0 / s2v_config["frame_rate"]
            if original_duration - s2v_config["section_duration"] <= 0.0:
                current_scene["clip_animation"] = "S2V"
                return [current_scene]

        ss = int(original_duration / s2v_config["section_duration"])
        remain = original_duration - ss * s2v_config["section_duration"]
        if remain > 0.05:
            ss += 1
        
        section_def = []
        for i in range(ss):
            section_def.append(s2v_config.copy())

        if remain > 0.05:
            section_def[-1]["section_duration"] = remain
        else:
            if remain > 0.0:
                section_def[-1]["section_duration"] = section_def[-1]["section_duration"] + remain

        # 获取当前场景的section ID，用于生成新的场景ID
        max_section_id = current_scene["id"]
        current_section = current_scene["id"] // 100
        for s in self.scenes:
            if s["id"] // 100 == current_section and s["id"] > max_section_id:
                max_section_id = s["id"]
        
        # 创建所有新场景的列表
        new_scenes = []
        start_time = 0.0
        for i, sdef in enumerate(section_def):
            if i == 0:
                new_scene = current_scene
            else:
                new_scene = copy.deepcopy(current_scene)

            new_scene["id"] = max_section_id + i + 1
            new_scenes.append(new_scene)

            trimmed_audio = self.ffmpeg_audio_processor.audio_cut_fade(
                original_audio_clip, start_time, sdef["section_duration"], 0, 0, 1.0
            )
            refresh_scene_media(new_scene, "clip_audio", ".wav", trimmed_audio)
            
            trimmed_video = self.ffmpeg_processor.trim_video(
                original_video_clip, start_time=start_time, end_time=start_time + sdef["section_duration"]
            )
            refresh_scene_media(new_scene, "clip", ".mp4", trimmed_video)
            
            start_time += sdef["section_duration"]
        
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

        # 须用深拷贝：浅拷贝会使两半场景共享嵌套 dict/list，后续任一侧原地修改会污染另一侧，
        # 表现为「别的镜」或后半段 speaking / 其它字段错乱。
        next_scene = copy.deepcopy(current_scene)

        self.replace_scene_with_others(n, [current_scene, next_scene])

        f1st, s2nd = self.ffmpeg_audio_processor.split_audio(original_audio_clip, position)
        refresh_scene_media(current_scene, "clip_audio", ".wav", f1st)
        refresh_scene_media(next_scene, "clip_audio", ".wav", s2nd)

        f1st, s2nd = self.ffmpeg_processor.split_video(original_video_clip, position)
        refresh_scene_media(current_scene, "clip", ".mp4", f1st)
        refresh_scene_media(next_scene, "clip", ".mp4", s2nd)

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

        self.save_scenes_to_json()
        return True




    def trim_scene_at_position(self, n, position, trim_audio):
        """分离当前场景"""
        if n<0  or n >= len(self.scenes):
            return False

        current_scene = self.scenes[n]

        original_duration = self.find_clip_duration(current_scene)
        if position<=0 or position >= original_duration:
            return False

        original_audio_clip = get_file_path(current_scene, "clip_audio")
        original_video_clip = get_file_path(current_scene, "clip")

        if trim_audio:
            f1st, s2nd = self.ffmpeg_audio_processor.split_audio(original_audio_clip, position)
            olda, original_audio_clip = refresh_scene_media(current_scene, "clip_audio", ".wav", f1st)
            refresh_scene_media(current_scene, "clip", ".mp4", self.ffmpeg_processor.add_audio_to_video(original_video_clip, original_audio_clip))
        else:
            f1st, s2nd = self.ffmpeg_processor.split_video(original_video_clip, position)
            refresh_scene_media(current_scene, "clip", ".mp4", self.ffmpeg_processor.add_audio_to_video(f1st, original_audio_clip, True, "trim"))

        self.save_scenes_to_json()
        return True



    def shift_scene(self, n, m, position, only_audio):
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

        f1sta, s2nda = self.ffmpeg_audio_processor.split_audio(original_audio_clip, position)

        if not only_audio:
            f1st, s2nd = self.ffmpeg_processor.split_video(original_video_clip, position)

        if n < m: 
            refresh_scene_media(current_scene, "clip_audio", ".wav", f1sta)
            mergeda = self.ffmpeg_audio_processor.concat_audios([s2nda, get_file_path(next_scene, "clip_audio")])
            refresh_scene_media(next_scene, "clip_audio", ".wav", mergeda)
            # video
            if not only_audio:
                refresh_scene_media(current_scene, "clip", ".mp4", f1st)
                mergedv = self.ffmpeg_processor.concat_videos([s2nd, get_file_path(next_scene, "clip")], True)
                refresh_scene_media(next_scene, "clip", ".mp4", mergedv)
            else:
                current_video = self.ffmpeg_processor.add_audio_to_video(original_video_clip, current_scene["clip_audio"])
                refresh_scene_media(current_scene, "clip", ".mp4", current_video)

                next_video = self.ffmpeg_processor.add_audio_to_video(get_file_path(next_scene, "clip"), next_scene["clip_audio"])  
                refresh_scene_media(next_scene, "clip", ".mp4", next_video)
        else:
            refresh_scene_media(current_scene, "clip_audio", ".wav", s2nda)
            mergeda = self.ffmpeg_audio_processor.concat_audios([get_file_path(next_scene, "clip_audio"), f1sta])
            refresh_scene_media(next_scene, "clip_audio", ".wav", mergeda)
            # video
            if not only_audio:
                refresh_scene_media(current_scene, "clip", ".mp4", s2nd)
                mergedv = self.ffmpeg_processor.concat_videos([get_file_path(next_scene, "clip"), f1st], True)
                refresh_scene_media(next_scene, "clip", ".mp4", mergedv)
            else:
                current_video = self.ffmpeg_processor.add_audio_to_video(original_video_clip, current_scene["clip_audio"])
                refresh_scene_media(current_scene, "clip", ".mp4", current_video)

                next_video = self.ffmpeg_processor.add_audio_to_video(get_file_path(next_scene, "clip"), next_scene["clip_audio"])  
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


    def _defaults_from_project_config(self):
        """欢迎屏 / 新建项目写入 PROJECT_CONFIG 的 narrator、visual_style，用于场景缺省补全。"""
        narr = config.CHARACTER_PERSON_OPTIONS[0]
        visual_style = config.VISUAL_STYLE_OPTIONS[0]
        try:
            pc = project_manager.PROJECT_CONFIG
            if pc:
                n = pc.get("narrator")
                if n:
                    narr = n
                v = pc.get("visual_style")
                if v:
                    visual_style = v
        except Exception:
            pass
        return narr, visual_style


    def load_scenes(self):
        scenes_file = config.get_scenes_path(self.pid)
        if os.path.exists(scenes_file):
            # 先读取文件到局部变量再赋值，避免先清空 self.scenes 导致在 make_backgroud_medias 期间若触发 save 会覆盖成空列表
            loaded_scenes = []
            try:
                with open(scenes_file, "r", encoding="utf-8") as f:
                    loaded_scenes = json.load(f)
            except json.JSONDecodeError as e:
                bad_copy = scenes_file + f".broken.{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                try:
                    shutil.copy2(scenes_file, bad_copy)
                    print(
                        f"❌ scenes.json 不是合法 JSON（line {e.lineno} col {e.colno}）：{e.msg}\n"
                        f"   已备份损坏文件到: {bad_copy}\n"
                        f"   请用编辑器打开原文件对照行号修复，或从备份恢复后再启动。"
                    )
                except OSError as copy_err:
                    print(f"❌ scenes.json JSON 解析失败且无法备份: {copy_err}\n   原错误: {e}")
                loaded_scenes = []
            if not isinstance(loaded_scenes, list):
                loaded_scenes = []
            self.scenes = loaded_scenes

            changed = False
            for story_scene in self.scenes:
                if not isinstance(story_scene, dict):
                    continue
                if story_scene.pop("visual_style", None) is not None:
                    changed = True
                if story_scene.pop("title_font", None) is not None:
                    changed = True
                if story_scene.pop("narrator", None) is not None:
                    changed = True
                if not story_scene.get("caption"):
                    story_scene["caption"] = config.get_channel_config(self.channel)["channel_name"]
                    changed = True
            if changed:
                self.save_scenes_to_json()
            return

        self.scenes = []

        channel = project_manager.PROJECT_CONFIG.get('channel', 'default')

        self.title = config.get_channel_config(self.channel)["channel_name"]

        scene_content = project_manager.PROJECT_CONFIG.get('scene_content') or []
        scene_list = scene_content if isinstance(scene_content, list) else []
        if scene_list:
            if isinstance(scene_list[0], dict):
                self.title = project_manager.caption_from_scene_content_item(scene_list[0])
            for scene_index, scene_item in enumerate(scene_list):
                if isinstance(scene_item, dict):
                    project_manager.normalize_scene_content_item_for_workflow(scene_item)
                self.add_story_scene(scene_index, scene_item, False, is_append=False)
        #else:
        #    stories_template = project_manager.PROJECT_CONFIG.get('channel_template', [])
        #     for story_index, element in enumerate(stories_template):
        #          element["caption"] = config.get_channel_config(channel)["channel_name"]
        #          self.add_story_scene(story_index, element, True, is_append=False)
        for story_scene in self.scenes:
            if not isinstance(story_scene, dict):
                continue
            story_scene.pop("visual_style", None)
            story_scene.pop("title_font", None)
            story_scene.pop("narrator", None)
            if not story_scene.get("caption"):
                story_scene["caption"] = config.get_channel_config(self.channel)["channel_name"]

        # 从 PROJECT_CONFIG 封面媒体填充 clip_image，并按首图宽高比设定横/竖屏尺寸
        self._apply_cover_media_to_scenes(scene_list)

        self.save_scenes_to_json()


    def _project_size_from_image_dims(self, width: int, height: int) -> tuple[int, int]:
        """宽>=高（约 16:9）→ 1920x1080；否则 → 1080x1920。"""
        try:
            w, h = int(width), int(height)
        except (TypeError, ValueError):
            return 1920, 1080
        if w <= 0 or h <= 0:
            return 1920, 1080
        if w >= h:
            return 1920, 1080
        return 1080, 1920

    def _image_dims(self, image_path: str) -> tuple[int, int]:
        from PIL import Image

        with Image.open(image_path) as im:
            return int(im.width), int(im.height)

    def _pdf_pages_to_images(self, pdf_path: str, out_dir: str | None = None) -> list[str]:
        """用 PyMuPDF 将 PDF 每页渲成 WebP，返回按页序的绝对路径列表。"""
        import fitz  # PyMuPDF
        import tempfile
        from PIL import Image

        pdf_path = (pdf_path or "").strip()
        if not pdf_path or not os.path.isfile(pdf_path):
            return []
        media_dir = config.get_media_path(self.pid)
        os.makedirs(media_dir, exist_ok=True)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            dest_dir = out_dir
        else:
            dest_dir = tempfile.mkdtemp(prefix="slide_pdf_", dir=media_dir)
        paths: list[str] = []
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"❌ 打开 PDF 失败: {pdf_path} — {e}")
            return []
        try:
            zoom = fitz.Matrix(2, 2)
            for i in range(len(doc)):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=zoom, alpha=False)
                out_path = os.path.join(dest_dir, f"{i + 1}.webp")
                mode = "RGB" if pix.n >= 3 else "L"
                Image.frombytes(mode, (pix.width, pix.height), pix.samples).save(
                    out_path, "WEBP", quality=_PAGE_WEBP_QUALITY, method=4
                )
                paths.append(os.path.abspath(out_path))
        finally:
            doc.close()
        return paths

    def _episode_number(self, name: str) -> int | None:
        name = (name or "").strip()
        if name.isdigit():
            return int(name)
        match = re.fullmatch(r"group(\d+)", name, re.I)
        if match:
            return int(match.group(1))
        return None

    def scene_group(self, scene) -> str:
        """场景所属 episode。没写 episode 的场景算第 1 集。"""
        if not isinstance(scene, dict):
            return ""
        name = str(scene.get("episode") or "").strip()
        if name:
            num = self._episode_number(name)
            return str(num) if num is not None else name
        legacy = str(scene.get("group") or "").strip()
        num = self._episode_number(legacy)
        if num is not None:
            return str(num)
        return "1"

    def _used_group_numbers(self) -> set[int]:
        used: set[int] = set()
        bare = False
        for scene in self.scenes or []:
            if not isinstance(scene, dict):
                continue
            episode = str(scene.get("episode") or "").strip()
            legacy = str(scene.get("group") or "").strip()
            if not episode and not legacy:
                bare = True
                continue
            num = self._episode_number(episode or legacy)
            if num is not None:
                used.add(num)
        if bare:
            used.add(1)
        media_dir = config.get_media_path(self.pid)
        if os.path.isdir(media_dir):
            for name in os.listdir(media_dir):
                if not os.path.isdir(os.path.join(media_dir, name)):
                    continue
                num = self._episode_number(name)
                if num is not None:
                    used.add(num)
        return used

    def next_group_name(self) -> str:
        used = self._used_group_numbers()
        n = 1
        while n in used:
            n += 1
        return str(n)

    def group_scene_indices(self, group_name: str) -> list[int]:
        group_name = (group_name or "").strip() or "1"
        return [
            i
            for i, scene in enumerate(self.scenes or [])
            if isinstance(scene, dict) and self.scene_group(scene) == group_name
        ]

    def next_scene_id(self) -> int:
        highest = 0
        for scene in self.scenes or []:
            if not isinstance(scene, dict):
                continue
            try:
                highest = max(highest, int(scene.get("id") or 0))
            except (TypeError, ValueError):
                continue
        return highest + 1

    def export_pdf_pages_to_group(self, pdf_path: str, group_name: str) -> tuple[str, list[str]]:
        """把 PDF 每一页渲成 1.webp、2.webp…，放进项目 media/<episode>/。"""
        group_name = (group_name or "").strip() or "1"
        folder = os.path.join(config.get_media_path(self.pid), group_name)
        os.makedirs(folder, exist_ok=True)
        for name in os.listdir(folder):
            stem, ext = os.path.splitext(name)
            if stem.isdigit() and ext.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass
        pages = self._pdf_pages_to_images(pdf_path, out_dir=folder)
        return folder, pages

    def _copy_slide_pdf_into_episode(self, slide_pdf: str, episode: str) -> str:
        """把 slide PDF 拷成 media/<集号>/<集号>.pdf，保留原文件时间。"""
        episode = (episode or "").strip() or "1"
        dest = self.episode_pdf_path(episode)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        src = os.path.abspath(slide_pdf)
        if os.path.abspath(dest) != src:
            shutil.copy2(src, dest)
        return dest

    def _stamp_episode_folder_to_pdf(self, episode: str) -> None:
        """拆页之后，把这一集文件夹的时间改成 PDF 的时间。"""
        pdf_path = self.episode_pdf_path(episode)
        folder = self.episode_media_dir(episode)
        if not os.path.isfile(pdf_path) or not os.path.isdir(folder):
            return
        codec_path = self._episode_pdf_codec_path(episode)
        with open(codec_path, "w", encoding="utf-8") as f:
            f.write(f"jpeg{_PAGE_JPEG_QUALITY}")
        stamp = os.path.getmtime(pdf_path)
        os.utime(folder, (stamp, stamp))

    def fit_group_to_page_count(self, group_name: str, page_count: int, mode: str) -> tuple[int, int]:
        """按选定页数调整这个 group 的场景数。extend 复制最后一场；trim 删掉多出来的场。"""
        added = 0
        removed = 0
        page_count = max(0, int(page_count))
        if mode in ("extend", "match"):
            while len(self.group_scene_indices(group_name)) < page_count:
                indices = self.group_scene_indices(group_name)
                if not indices:
                    break
                last_i = indices[-1]
                dup = copy.deepcopy(self.scenes[last_i])
                dup["id"] = self.next_scene_id()
                dup.pop("episode_page", None)
                dup.pop("group_page", None)
                self.scenes.insert(last_i + 1, dup)
                added += 1
        if mode in ("trim", "match") and page_count >= 1:
            while len(self.group_scene_indices(group_name)) > page_count:
                indices = self.group_scene_indices(group_name)
                del self.scenes[indices[-1]]
                removed += 1
        return added, removed

    def _episode_png_paths(self, episode: str) -> list[str]:
        """这一集里按页码排好的页面图。同一页有 webp 时用 webp，否则用 jpg。"""
        folder = os.path.join(config.get_media_path(self.pid), episode)
        if not os.path.isdir(folder):
            return []
        rank = {".webp": 0, ".jpg": 1, ".jpeg": 1, ".png": 2}
        best: dict[int, tuple[int, str]] = {}
        for name in os.listdir(folder):
            stem, ext = os.path.splitext(name)
            ext = ext.lower()
            if ext not in rank or not stem.isdigit():
                continue
            n = int(stem)
            path = os.path.join(folder, name)
            prev = best.get(n)
            if prev is None or rank[ext] < prev[0]:
                best[n] = (rank[ext], path)
        return [best[n][1] for n in sorted(best)]

    def episode_media_dir(self, episode: str) -> str:
        return os.path.join(config.get_media_path(self.pid), (episode or "").strip() or "1")

    def touch_episode_media(self, episode: str) -> None:
        """改这一集页面文件夹的修改时间。拷集用它和 PDF 的时间判断要不要重做。"""
        folder = self.episode_media_dir(episode)
        if not os.path.isdir(folder):
            return
        now = time.time()
        os.utime(folder, (now, now))

    def write_scene_page_png(self, scene: dict, image_path: str, *, force_new_page: bool = False) -> None:
        """把这张图写成这一集文件夹里对应页的 webp，并改文件夹时间。页码可以不连续。"""
        from PIL import Image

        if not isinstance(scene, dict) or not image_path or not os.path.isfile(image_path):
            return
        episode = self.scene_group(scene)
        folder = self.episode_media_dir(episode)
        os.makedirs(folder, exist_ok=True)
        page = None
        if not force_new_page:
            try:
                page = int(scene.get("episode_page") or 0)
            except (TypeError, ValueError):
                page = None
            if page is not None and page <= 0:
                page = None
        if page is None:
            used: set[int] = set()
            for path in self._episode_png_paths(episode):
                used.add(int(os.path.splitext(os.path.basename(path))[0]))
            for other in self.scenes:
                if not isinstance(other, dict) or self.scene_group(other) != episode:
                    continue
                try:
                    n = int(other.get("episode_page") or 0)
                except (TypeError, ValueError):
                    n = 0
                if n > 0:
                    used.add(n)
            page = (max(used) if used else 0) + 1
            scene["episode_page"] = page
        dest = os.path.join(folder, f"{page}.webp")
        if os.path.splitext(image_path)[1].lower() == ".webp":
            if os.path.abspath(image_path) != os.path.abspath(dest):
                shutil.copy2(image_path, dest)
        else:
            with Image.open(image_path) as im:
                rgb = im.convert("RGB")
                rgb.save(dest, "WEBP", quality=_PAGE_WEBP_QUALITY, method=4)
        for old_ext in (".png", ".jpg", ".jpeg"):
            old = os.path.join(folder, f"{page}{old_ext}")
            if os.path.isfile(old) and os.path.abspath(old) != os.path.abspath(dest):
                try:
                    os.remove(old)
                except OSError:
                    pass
        scene["episode"] = episode
        scene["episode_pdf"] = f"{episode}.pdf"
        self.touch_episode_media(episode)

    def release_scene_page_png(self, scene: dict) -> None:
        """删场景时去掉它对应的那一页 png。同一页还被别的场景用着就留下。"""
        if not isinstance(scene, dict):
            return
        episode = self.scene_group(scene)
        try:
            page = int(scene.get("episode_page") or 0)
        except (TypeError, ValueError):
            page = 0
        if page > 0:
            still_used = False
            for other in self.scenes:
                if other is scene or not isinstance(other, dict):
                    continue
                if self.scene_group(other) != episode:
                    continue
                try:
                    other_page = int(other.get("episode_page") or 0)
                except (TypeError, ValueError):
                    other_page = 0
                if other_page == page:
                    still_used = True
                    break
            if not still_used:
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    path = os.path.join(self.episode_media_dir(episode), f"{page}{ext}")
                    if os.path.isfile(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
        self.touch_episode_media(episode)

    def compact_episode_pages(self, episode: str) -> None:
        """删掉场景留下的页码空洞补上。剩下的场景按顺序改成第 1、2、3 页，页面文件一起改名。"""
        episode = (episode or "").strip() or "1"
        scenes = [
            s for s in self.scenes or []
            if isinstance(s, dict) and self.scene_group(s) == episode
        ]
        order: list[int] = []
        for scene in scenes:
            try:
                page = int(scene.get("episode_page") or 0)
            except (TypeError, ValueError):
                page = 0
            if page > 0 and page not in order:
                order.append(page)
        if not order:
            return
        folder = self.episode_media_dir(episode)
        file_nums: list[int] = []
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                stem, ext = os.path.splitext(name)
                if ext.lower() in (".webp", ".jpg", ".jpeg", ".png") and stem.isdigit():
                    file_nums.append(int(stem))
        file_nums = sorted(set(file_nums))
        dense = file_nums == list(range(1, len(file_nums) + 1))
        if dense and all(old == new for new, old in enumerate(order, start=1)):
            return
        mapping = {old: new for new, old in enumerate(order, start=1)}
        if all(old == new for old, new in mapping.items()):
            return
        pending: list[tuple[str, str]] = []
        for old, new in mapping.items():
            if old == new:
                continue
            for ext in (".webp", ".jpg", ".jpeg", ".png"):
                src = os.path.join(folder, f"{old}{ext}")
                if not os.path.isfile(src):
                    continue
                tmp = os.path.join(folder, f".renum_{old}{ext}")
                os.replace(src, tmp)
                pending.append((tmp, os.path.join(folder, f"{new}{ext}")))
        for tmp, dest in pending:
            if os.path.isfile(dest):
                try:
                    os.remove(dest)
                except OSError:
                    pass
            os.replace(tmp, dest)
        changed = False
        for scene in scenes:
            try:
                page = int(scene.get("episode_page") or 0)
            except (TypeError, ValueError):
                continue
            new = mapping.get(page)
            if new and new != page:
                scene["episode_page"] = new
                changed = True
        if changed:
            self.save_scenes_to_json()
        self.touch_episode_media(episode)

    def insert_copied_episode_page(self, source: dict, dup: dict) -> None:
        """拷贝场景后，副本占用下一页，后面的页码和页面文件都顺延，并复制这一页的图。"""
        if not isinstance(source, dict) or not isinstance(dup, dict):
            return
        episode = self.scene_group(source)
        try:
            page = int(source.get("episode_page") or 0)
        except (TypeError, ValueError):
            page = 0
        if page <= 0:
            dup.pop("episode_page", None)
            return
        new_page = page + 1
        folder = self.episode_media_dir(episode)
        highest = page
        for scene in self.scenes or []:
            if scene is dup or not isinstance(scene, dict) or self.scene_group(scene) != episode:
                continue
            try:
                n = int(scene.get("episode_page") or 0)
            except (TypeError, ValueError):
                n = 0
            if n > highest:
                highest = n
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                stem, ext = os.path.splitext(name)
                if ext.lower() in (".webp", ".jpg", ".jpeg", ".png") and stem.isdigit():
                    highest = max(highest, int(stem))
        for scene in self.scenes or []:
            if scene is dup or not isinstance(scene, dict) or self.scene_group(scene) != episode:
                continue
            try:
                n = int(scene.get("episode_page") or 0)
            except (TypeError, ValueError):
                continue
            if n >= new_page:
                scene["episode_page"] = n + 1
        dup["episode"] = episode
        dup["episode_page"] = new_page
        dup["episode_pdf"] = source.get("episode_pdf") or f"{episode}.pdf"
        for n in range(highest, new_page - 1, -1):
            for ext in (".webp", ".jpg", ".jpeg", ".png"):
                src = os.path.join(folder, f"{n}{ext}")
                if os.path.isfile(src):
                    os.replace(src, os.path.join(folder, f"{n + 1}{ext}"))
        for ext in (".webp", ".jpg", ".jpeg", ".png"):
            src = os.path.join(folder, f"{page}{ext}")
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(folder, f"{new_page}{ext}"))
        self.touch_episode_media(episode)

    def episode_pdf_path(self, episode: str) -> str:
        episode = (episode or "").strip() or "1"
        return os.path.join(self.episode_media_dir(episode), f"{episode}.pdf")

    def _episode_pdf_codec_path(self, episode: str) -> str:
        episode = (episode or "").strip() or "1"
        return os.path.join(self.episode_media_dir(episode), f".{episode}.codec")

    def episode_pdf_is_current(self, episode: str) -> bool:
        """这一集的 PDF 和页面文件夹修改时间一致，而且是按当前 JPEG 质量生成的。"""
        folder = self.episode_media_dir(episode)
        pdf_path = self.episode_pdf_path(episode)
        codec_path = self._episode_pdf_codec_path(episode)
        if not os.path.isdir(folder) or not os.path.isfile(pdf_path) or not os.path.isfile(codec_path):
            return False
        try:
            with open(codec_path, "r", encoding="utf-8") as f:
                codec = f.read().strip()
        except OSError:
            return False
        if codec != f"jpeg{_PAGE_JPEG_QUALITY}":
            return False
        return abs(os.path.getmtime(folder) - os.path.getmtime(pdf_path)) < 1.0

    def build_episode_pdf(self, episode: str) -> str:
        """按页码顺序把现有页面图合成 PDF。页图是 WebP 时先解开，PDF 里仍写入 JPEG。"""
        pngs = self._episode_png_paths(episode)
        if not pngs:
            return ""
        pdf_path = self._assemble_episode_pdf(episode, pngs)
        if not pdf_path:
            return ""
        codec_path = self._episode_pdf_codec_path(episode)
        with open(codec_path, "w", encoding="utf-8") as f:
            f.write(f"jpeg{_PAGE_JPEG_QUALITY}")
        stamp = time.time()
        os.utime(pdf_path, (stamp, stamp))
        os.utime(self.episode_media_dir(episode), (stamp, stamp))
        return pdf_path

    def _assemble_episode_pdf(self, episode: str, pngs: list[str]) -> str:
        """把这一集的页面图合成 media/<episode>/<episode>.pdf。WebP 由 PIL 解开后再写入 JPEG。"""
        import fitz
        from io import BytesIO
        from PIL import Image

        if not pngs:
            return ""
        folder = os.path.join(config.get_media_path(self.pid), episode)
        os.makedirs(folder, exist_ok=True)
        pdf_path = os.path.join(folder, f"{episode}.pdf")
        doc = fitz.open()
        try:
            for src in pngs:
                with Image.open(src) as im:
                    rgb = im.convert("RGB")
                    width, height = rgb.size
                    buf = BytesIO()
                    rgb.save(buf, "JPEG", quality=_PAGE_JPEG_QUALITY, optimize=True)
                page = doc.new_page(width=width, height=height)
                page.insert_image(page.rect, stream=buf.getvalue())
            doc.save(pdf_path, deflate=True, garbage=4)
        finally:
            doc.close()
        return os.path.abspath(pdf_path)

    def split_group_at(self, index: int) -> str:
        """从当前场景起划成新的一集。页面图跟着挪过去，保留原来的页码，不在这里合成 PDF。"""
        if not self.scenes or index < 0 or index >= len(self.scenes):
            return ""
        old_name = self.scene_group(self.scenes[index])
        episode_indices = self.group_scene_indices(old_name)
        stay_indices = [i for i in episode_indices if i < index]
        move_indices: list[int] = []
        i = index
        while i < len(self.scenes) and self.scene_group(self.scenes[i]) == old_name:
            move_indices.append(i)
            i += 1
        if not move_indices:
            return ""
        new_name = self.next_group_name()
        pages = self._episode_png_paths(old_name)
        move_pages = pages[len(stay_indices) :]
        if move_pages:
            new_folder = self.episode_media_dir(new_name)
            os.makedirs(new_folder, exist_ok=True)
            for src in move_pages:
                dest = os.path.join(new_folder, os.path.basename(src))
                if os.path.abspath(src) != os.path.abspath(dest):
                    shutil.move(src, dest)
        for scene_i, png in zip(move_indices, move_pages):
            scene = self.scenes[scene_i]
            if isinstance(scene, dict):
                scene["episode_page"] = int(os.path.splitext(os.path.basename(png))[0])
        for scene_i in move_indices:
            scene = self.scenes[scene_i]
            scene["episode"] = new_name
            if move_pages:
                scene["episode_pdf"] = f"{new_name}.pdf"
            scene.pop("group", None)
            scene.pop("group_page", None)
            scene.pop("group_pdf", None)
        if pages[: len(stay_indices)]:
            for scene_i in stay_indices:
                scene = self.scenes[scene_i]
                if isinstance(scene, dict):
                    scene["episode_pdf"] = f"{old_name}.pdf"
        self.touch_episode_media(old_name)
        self.touch_episode_media(new_name)
        for scene in self.scenes:
            if isinstance(scene, dict) and not str(scene.get("episode") or "").strip():
                scene["episode"] = "1"
                scene.pop("group", None)
        return new_name

    def _apply_project_video_size(self, width: int, height: int) -> None:
        """更新 PROJECT_CONFIG 与 ffmpeg 输出尺寸；尺寸变化时重绑模板底稿。"""
        nw, nh = int(width), int(height)
        pc = project_manager.PROJECT_CONFIG
        cur_w = int((pc or {}).get("video_width") or self.ffmpeg_processor.width or 1920)
        cur_h = int((pc or {}).get("video_height") or self.ffmpeg_processor.height or 1080)
        if pc is not None:
            pc["video_width"] = nw
            pc["video_height"] = nh
            try:
                save_project_config()
            except Exception as e:
                print(f"⚠️ 保存 video_width/height 失败: {e}")
        if (cur_w, cur_h) != (nw, nh):
            print(f"📐 项目尺寸按封面媒体设为 {nw}x{nh}")
            try:
                self.reapply_all_scenes_template_medias(nw, nh)
            except Exception as e:
                print(f"⚠️ 按新尺寸重绑模板失败（仍继续设置 clip_image）: {e}")
                self.ffmpeg_processor = FfmpegProcessor(self.pid, self.language, nw, nh)
        else:
            self.ffmpeg_processor.width = nw
            self.ffmpeg_processor.height = nh


    def _apply_cover_media_to_scenes(self, scene_list: list) -> None:
        """scene_content 多场景 → PDF 页对 clip_image；单场景 → 封面图作 clip_image。"""
        pc = project_manager.PROJECT_CONFIG
        if not isinstance(pc, dict):
            return
        if not (pc.get("cover_image") or pc.get("slide") or pc.get("cover_video")):
            project_manager.hydrate_config_cover_media(pc)

        n_scenes = len(self.scenes)
        if n_scenes <= 0:
            return

        # 多场景：用幻灯片 PDF 逐页对应 clip_image
        if isinstance(scene_list, list) and len(scene_list) > 1:
            slide_pdf = (pc.get("slide") or "").strip()
            if not slide_pdf or not os.path.isfile(slide_pdf):
                print("⚠️ 多场景但 PROJECT_CONFIG 无可用 slide PDF，跳过封面导入")
                return
            group_name = "1"
            for scene in self.scenes:
                if isinstance(scene, dict) and str(scene.get("episode") or "").strip():
                    group_name = self.scene_group(scene)
                    break
            pdf_path = self._copy_slide_pdf_into_episode(slide_pdf, group_name)
            pdf_name = os.path.basename(pdf_path)
            _folder, page_images = self.export_pdf_pages_to_group(pdf_path, group_name)
            if not page_images:
                print(f"⚠️ PDF 未能渲出页面图: {pdf_path}")
                return
            self._stamp_episode_folder_to_pdf(group_name)
            try:
                iw, ih = self._image_dims(page_images[0])
            except Exception as e:
                print(f"⚠️ 读取 PDF 首页尺寸失败: {e}")
                return
            nw, nh = self._project_size_from_image_dims(iw, ih)
            self._apply_project_video_size(nw, nh)
            for scene in self.scenes:
                if isinstance(scene, dict) and not str(scene.get("episode") or "").strip():
                    scene["episode"] = group_name
                    scene.pop("group", None)
            self.fit_group_to_page_count(group_name, len(page_images), "extend")
            written = 0
            for i, scene_i in enumerate(self.group_scene_indices(group_name)):
                if i >= len(page_images):
                    break
                scene = self.scenes[scene_i]
                try:
                    page_path = page_images[i]
                    if os.path.splitext(page_path)[1].lower() == ".webp":
                        refresh_scene_media(scene, "clip_image", ".webp", page_path, True)
                    else:
                        file_path = self.ffmpeg_processor.resize_image_smart(page_path)
                        refresh_scene_media(scene, "clip_image", ".webp", file_path, True)
                except Exception as e:
                    print(f"⚠️ 场景 {scene_i} 设置 clip_image 失败: {e}")
                    continue
                scene["episode"] = group_name
                scene["episode_page"] = i + 1
                scene["episode_pdf"] = pdf_name
                scene.pop("group", None)
                scene.pop("group_page", None)
                scene.pop("group_pdf", None)
                written += 1
            print(f"✅ 已从 slide PDF 为第 {group_name} 集的 {written} 个场景设置 clip_image")
            return

        # 单场景：封面图 → clip_image；封面成片 → clip
        if n_scenes == 1:
            scene = self.scenes[0]
            cover = (pc.get("cover_image") or "").strip()
            cover_video = (pc.get("cover_video") or "").strip()
            if cover and os.path.isfile(cover):
                try:
                    iw, ih = self._image_dims(cover)
                    nw, nh = self._project_size_from_image_dims(iw, ih)
                    self._apply_project_video_size(nw, nh)
                    ext = os.path.splitext(cover)[1].lower() or ".webp"
                    if ext not in (".webp", ".png", ".jpg", ".jpeg"):
                        ext = ".webp"
                    refresh_scene_media(scene, "clip_image", ext, cover, make_replacement_copy=True)
                    print(f"✅ 已将封面图设为单场景 clip_image，尺寸 {nw}x{nh}")
                except Exception as e:
                    print(f"⚠️ 设置封面 clip_image 失败: {e}")
            elif not cover_video or not os.path.isfile(cover_video):
                print("⚠️ 单场景但 PROJECT_CONFIG 无可用 cover_image / cover_video，跳过封面导入")
                return
            if cover_video and os.path.isfile(cover_video):
                try:
                    refresh_scene_media(scene, "clip", ".mp4", cover_video, make_replacement_copy=True)
                    print(f"✅ 已将封面成片设为单场景 clip: {cover_video}")
                except Exception as e:
                    print(f"⚠️ 设置封面 clip 失败: {e}")

    def remix_conversation(self, current_scene, mode, _content, selected_prompt):
        refresh_conversation = "content:\n" + _content + "\n\n\nAnd the core-insight ('soul') is: \n" + project_manager.resolve_soul_for_config(project_manager.PROJECT_CONFIG or {})
        new_scenes = self.llm_api.generate_json(
            system_prompt=selected_prompt,
            user_prompt=refresh_conversation,
            expect_list=True
        )
        if not new_scenes or len(new_scenes) == 0:
            return

        start_id = current_scene.get("id", 0)
        for i, scene in enumerate(new_scenes):
            scene["id"] = start_id + 1
            start_id = scene["id"]
        return new_scenes


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

        return config.chinese_convert('\n'.join(content), self.language)


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

            scenes_path = config.get_scenes_path(self.pid)
            if os.path.exists(scenes_path):
                # check if the content of the file is same as the normalized_scenes
                with open(scenes_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if content != json.dumps(normalized_scenes, ensure_ascii=False, indent=2):
                    ts = datetime.now().strftime("%Y%m%d_%H%M")
                    backup_path = f"{scenes_path}.{ts}.bak"
                    # overwrite the backup file, if exists
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    shutil.copy2(scenes_path, backup_path)

            with open(scenes_path, "w", encoding="utf-8") as f:
                json.dump(normalized_scenes, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ 保存scenes到JSON失败: {str(e)}")
            return False


    def scenes_in_story(self, scene):
        """同一 episode 的场景，按列表顺序。集数写在场景的 episode 上。"""
        if not self.scenes or not isinstance(scene, dict):
            return []
        name = self.scene_group(scene)
        if not name:
            return []
        return [
            s for s in self.scenes
            if isinstance(s, dict) and self.scene_group(s) == name
        ]


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

    def get_scene_by_index(self, index):
        if not self.scenes or index < 0 or index >= len(self.scenes):
            return None
        return self.scenes[index]

    def get_previous_scene(self, index):
        if not self.scenes or index <= 0 or index >= len(self.scenes):
            return None
        return self.scenes[index - 1]

    def get_next_scene(self, index):
        if not self.scenes or index < 0 or index >= len(self.scenes) - 1:
            return None
        return self.scenes[index + 1]

    def get_previous_story_last_scene(self, index):
        if not self.scenes or index <= 0 or index >= len(self.scenes):
            return None
        current_group = self.scene_group(self.scenes[index])
        for i in range(index - 1, -1, -1):
            if self.scene_group(self.scenes[i]) != current_group:
                return self.scenes[i]
        return None

        
 
    def replace_scene_narration(self, current_scene, source_video_path, source_audio_path):
        oldv, narrationv = refresh_scene_media(current_scene, "narration", ".mp4", source_video_path)
        olda, narrationa = refresh_scene_media(current_scene, "narration_audio", ".wav", source_audio_path)

        for s in self.scenes_in_story(current_scene):
            s["narration"] = narrationv
            s["narration_audio"] = narrationa

        self.save_scenes_to_json()


    def is_last_scene(self, scene, scenes):
        if len(scenes) <= 1 or scene is scenes[-1]:
            return True
        try:
            next_scene = scenes[scenes.index(scene) + 1]
            return next_scene["main_audio"] != scene["main_audio"]
        except:
            return True


    def replace_scene_image(self, current_scene, source_image_path, vertical_line_position, target_field):
        oldi, image_path = refresh_scene_media(current_scene, target_field, ".webp", source_image_path)
        if target_field == "clip_image" and image_path:
            self.write_scene_page_png(current_scene, image_path)

        current_scene[target_field + "_split"] = vertical_line_position
        clip_image_last = get_file_path(current_scene, target_field + "_last")
        if not clip_image_last:
            current_scene[target_field + "_last"] = image_path

        #self.ask_replace_scene_info_from_image(current_scene, image_path)
        self.save_scenes_to_json()


    def upload_video(
        self,
        youtube_title,
        publish_at=None,
        description=None,
        *,
        telegram_title: str | None = None,
    ):
        """
        publish_at: None 表示立即按 privacy 上传（默认不公开列出）。
        若为 datetime（建议带本地时区），则使用 YouTube 定时公开（API 要求先 private + publishAt）。
        description: YouTube 描述；未提供时回退为首场景 voiceover（旧行为）。
        telegram_title: Telegram 通知用展示标题；默认与 youtube_title 相同。

        返回 Telegram 旁路状态行列表（与 downloader 发布一致）。
        """
        final_video_path = config.publish_final_video_path(self.pid)
        if not os.path.isfile(final_video_path):
            raise FileNotFoundError(
                f"未找到成片：{final_video_path}\n请先使用「Video生成」导出。"
            )
        if description is not None:
            summary = config.chinese_convert(description, self.language)
        else:
            sc = project_manager.PROJECT_CONFIG.get("scene_content", [{"voiceover": ""}])
            if isinstance(sc, dict):
                summary = sc.get("voiceover", "")
            elif isinstance(sc, list) and sc:
                first = sc[0] if isinstance(sc[0], dict) else {}
                summary = first.get("voiceover", "")
            else:
                summary = ""
            summary = config.chinese_convert(summary, self.language)

        # thumbnail_path = f"{config.get_project_path(self.pid)}/thumbnail.png"
        thumbnail_path = None

        video_id, _published_iso = self.downloader.upload_video(
            final_video_path,
            thumbnail_path,
            title=youtube_title,
            description=summary,
            language=self.language,
            script_path=None,
            secret_key=config.get_channel_config(self.channel)["channel_key"],
            channel_id=self.channel,
            categoryId=config.get_channel_config(self.channel)["channel_category_id"],
            tags=[],
            privacy="unlisted",
            publish_at=publish_at,
        )
        # 仅用 published_youtube_video_id 记录 YouTube 成片 id；不写入 pid / 列表行 id / project_profile.pid
        pc = project_manager.PROJECT_CONFIG
        if pc is not None:
            if video_id:
                pc["published_youtube_video_id"] = video_id
            else:
                pc.pop("published_youtube_video_id", None)
            pc.pop("video_id", None)
            if publish_at is not None:
                try:
                    pc["youtube_scheduled_publish_at"] = publish_at.isoformat()
                except Exception:
                    pc["youtube_scheduled_publish_at"] = str(publish_at)
            else:
                pc.pop("youtube_scheduled_publish_at", None)
            save_project_config()
            print(f"✅ Published YouTube video id saved to project config: {video_id}")
        else:
            print("⚠️ project_manager.PROJECT_CONFIG 未加载，无法将 published_youtube_video_id 写入项目配置")

        watch = ""
        vid_s = str(video_id).strip() if video_id is not None else ""
        if vid_s:
            watch = f"https://www.youtube.com/watch?v={vid_s}"

        tg_lines: list[str] = []
        try:
            from utility.telegram_notify import notify_youtube_publish_extras

            tg_lines = notify_youtube_publish_extras(
                mp4_path=final_video_path,
                watch_url=watch,
                title_line=(telegram_title or youtube_title or "").strip(),
                summary=summary,
            )
        except Exception as e:
            tg_lines = [f"Telegram（旁路异常）: {e}"]
        for line in tg_lines:
            print(line)
        return tg_lines


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
            self.sd_processor.two_image_to_video( prompt=wan_prompt, file_prefix=file_prefix, f1st_frame=image_path, last_frame=image_last_path, sound_path=sound_path )

        elif animate_mode in config_prompt.ANIMATE_S2V:
            file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "S2V", False)

            s2v_mode = "FS2V"
            for config in ["HS2V", "S2V", "FS2V"]:
                s2v_config = sd_image_processor.GEN_CONFIG[config].copy()
                original_duration = self.find_clip_duration(scene)
                section_duration = (s2v_config["max_frames"]-4) * 1.0 / s2v_config["frame_rate"]
                if original_duration - section_duration <= 0.0:
                    s2v_mode = config
                    break
            self.sd_processor.sound_to_video( 
                                  prompt=wan_prompt, file_prefix=file_prefix, image_path=image_path, 
                                  sound_path=sound_path, next_sound_path=next_sound_path, animate_mode=s2v_mode, silence=False 
                              )

        elif animate_mode in config_prompt.ANIMATE_AI2V:
            if not action_path:
                action_path = f"{config.DEFAULT_MEDIA_PATH}/default_action.mp4"
            file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "AI2V", False)
            self.sd_processor.action_transfer_video(prompt=wan_prompt, file_prefix=file_prefix, image_path=image_path, sound_path=sound_path, action_path=action_path)

        elif animate_mode in config_prompt.ANIMATE_WS2V:
            vertical_line_position = scene.get("clip_image_split", 0)
            if vertical_line_position == 0:
                return

            narrator = project_manager.project_narrator()
            narrator_position = scene.get("narrator_position", "")
            if not narrator or not narrator_position:
                return

            left_image, right_image = self.ffmpeg_processor.split_image(image_path, vertical_line_position)
            
            left_prompt = wan_prompt.copy()
            right_prompt = wan_prompt.copy()

            left_file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "WS2VL", False)
            right_file_prefix = build_scene_media_prefix(self.pid, scene["id"], video_type, "WS2VR", False)

            if narrator_position == "left":
                left_prompt.pop("LISTENING", None)
                right_prompt.pop("SPEAKING", None)
                self.sd_processor.sound_to_video(prompt=left_prompt, file_prefix=left_file_prefix, image_path=left_image, sound_path=sound_path, animate_mode=animate_mode, silence=False)
                self.sd_processor.sound_to_video(prompt=right_prompt, file_prefix=right_file_prefix, image_path=right_image, sound_path=sound_path, animate_mode=animate_mode, silence=True)
            elif narrator_position == "right":
                left_prompt.pop("SPEAKING", None)
                right_prompt.pop("LISTENING", None)
                self.sd_processor.sound_to_video(prompt=left_prompt, file_prefix=left_file_prefix, image_path=left_image, sound_path=sound_path, animate_mode=animate_mode, silence=True)
                self.sd_processor.sound_to_video(prompt=right_prompt, file_prefix=right_file_prefix, image_path=right_image, sound_path=sound_path, animate_mode=animate_mode, silence=False)


    def finalize_video(self, with_transitions, replace_final_audio_with_zero=False, scene_start=None, scene_end=None):
        scenes = self.scenes
        n_all = len(scenes)
        if scene_start is not None and scene_end is not None and n_all:
            a = max(0, min(int(scene_start), n_all - 1))
            b = max(0, min(int(scene_end), n_all - 1))
            if a > b:
                a, b = b, a
            scenes = scenes[a:b + 1]
        video_segments = []
        for s in scenes:
            #valid_narrator = None
            #if add_narration and "narration" in s and "narrator" in s and s["narration"] and s["narrator"]:
            #    valid_narrator = s["narrator"]

            ext = float(s.get("extension", 0) or 0)

            #if valid_narrator and ("left" in valid_narrator):
            #    video_segments.append({"path":s["narration"], "transition":"fade", "duration":1.0, "extend":ext})
            #    #v = self.ffmpeg_processor.add_audio_to_video(s["narration"], s["narration_audio"], True)
            #    #video_segments.append({"path":v, "transition":"fade", "duration":1.0, "extend":ext})

            v = self.ffmpeg_processor.add_audio_to_video(s["clip"], s["clip_audio"], True)
            #video_segments.append({"path":s["clip"], "transition":"fade", "duration":1.0, "extend":ext})
            video_segments.append({"path":v, "transition":"fade", "duration":1.0, "extend":ext})

            #if valid_narrator and (not "left" in valid_narrator):
            #    video_segments.append({"path":s["narration"], "transition":"fade", "duration":1.0, "extend":ext})
            #    #v = self.ffmpeg_processor.add_audio_to_video(s["narration"], s["narration_audio"], True)
            #    #video_segments.append({"path":v, "transition":"fade", "duration":1.0, "extend":0})

        final_video_dir = f"{self.publish_path}/{self.pid}"
        if not os.path.exists(final_video_dir):
            os.makedirs(final_video_dir)
        for file in os.listdir(final_video_dir):
            os.remove(os.path.join(final_video_dir, file))

        for i, v in enumerate(video_segments):
            video_path = f"{final_video_dir}/{i:04d}.mp4"
            if v["extend"] > 0.0 and with_transitions:
                # create new function to extend the clip (simple extend last frame (if extend > 0.0))
                v_temp = self.ffmpeg_processor.extend_video(v["path"], v["extend"])
            else:
                v_temp = v["path"]
            safe_copy_overwrite(v_temp, video_path)
            video_segments[i]["path"] = video_path

        #video_temp = self.ffmpeg_processor._concat_videos_with_transitions(video_segments, frames_deduct=5.95, keep_audio_if_has=True)


        if with_transitions:
            video_temp = self.ffmpeg_processor.concat_videos_with_transitions(video_segments, keep_audio_if_has=True)
        else:
            video_temp = self.ffmpeg_processor.concat_videos([seg["path"] for seg in video_segments], keep_audio=True)

        if replace_final_audio_with_zero:
            # 按时间线、连续同一 story（id 同一万档）分段。
            # 首场景有 zero_audio：用其铺满本 story 成片总时长（必要时裁切或循环）。
            # 否则：按场景顺序拼接本 story 内所有 clip_audio，再裁切/静音补齐到与本 story 成片总时长一致。
            # 最后再按 story 顺序 concat 成整条成片音轨。
            per_story_audios = []
            n = len(scenes)
            idx = 0
            aud = self.ffmpeg_audio_processor
            while idx < n:
                scene0 = scenes[idx]
                root_id = int(scene0.get("id", 0) / 10000)
                story_dur = 0.0
                j = idx
                while j < n and int(scenes[j].get("id", 0) / 10000) == root_id:
                    seg_path = video_segments[j]["path"]
                    story_dur += self.ffmpeg_processor.get_duration(seg_path)
                    j += 1

                za = get_file_path(scene0, "zero_audio")
                if za and os.path.isfile(za):
                    tiled = aud.audio_trim_or_loop_to_duration(za, story_dur)
                else:
                    clip_paths = []
                    for k in range(idx, j):
                        ca = get_file_path(scenes[k], "clip_audio")
                        if ca and os.path.isfile(ca):
                            clip_paths.append(ca)
                    if not clip_paths:
                        tiled = aud.make_silence(story_dur)
                    else:
                        merged = aud.concat_audios(clip_paths)
                        if not merged:
                            tiled = aud.make_silence(story_dur)
                        else:
                            tiled = aud.extend_audio(merged, 0.0, story_dur)
                            if not tiled:
                                tiled = aud.make_silence(story_dur)

                if not tiled:
                    tiled = aud.make_silence(story_dur)
                per_story_audios.append(tiled)

                idx = j

            full_story_audio = aud.concat_audios(per_story_audios) if per_story_audios else None
            if full_story_audio:
                video_temp = self.ffmpeg_processor.add_audio_to_video(video_temp, full_story_audio)

        final_video_path = config.publish_final_video_path(self.pid)
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
        if hasattr(current_scene, "id"):
            same_story_scenes = self.scenes_in_story(current_scene)
        elif isinstance(current_scene, dict) and current_scene.get("id", 0):
            same_story_scenes = self.scenes_in_story(current_scene)
        else:
            same_story_scenes = self.scenes

        if same_story_scenes is None or len(same_story_scenes) == 0:
            return 0

        max_id = 0
        for s in same_story_scenes:
            id = s.get("id", 0)
            if id > max_id:
                max_id = id
        return max_id



    def add_story_scene(self, story_index, story, story_level, is_append):
        self.background_image, self.background_video, background_music = config.make_backgroud_medias(self.pid, self.channel, self.ffmpeg_processor, self.ffmpeg_audio_processor)
        if not self.background_image or not self.background_video:
            raise FileNotFoundError(
                f"频道 {self.channel} 没有画面模板。请在 program/{self.channel}/clip 放入静帧和 MP4。"
            )

        if story_level:
            next_root_id = (int(self.max_id(story)/10000) + 1)*10000
        else:
            next_root_id = (int(self.max_id(story)/100) + 1)*100
            if next_root_id < 10000:
                next_root_id = 10000

        story = story.copy()
        story.pop("narrator", None)
        story["id"] = next_root_id
        story["environment"] = ""
        if story_level:
            story["episode"] = self.next_group_name()
            story.pop("group", None)
            story.pop("episode_page", None)
            story.pop("episode_pdf", None)
            story.pop("group_page", None)
            story.pop("group_pdf", None)
        elif not str(story.get("episode") or "").strip():
            story["episode"] = "1"
            story.pop("group", None)

        oldv, zero = refresh_scene_media(story, "zero", ".mp4", self.background_video, True)
        oldi, zero_image = refresh_scene_media(story, "zero_image", ".webp", self.background_image, True)
        zero_audio = self.ffmpeg_audio_processor.extract_audio_from_video(background_music)
        olda, zero_audio = refresh_scene_media(story, "zero_audio", ".wav", zero_audio, True)

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


    def reapply_all_scenes_template_medias(self, video_width: int, video_height: int):
        """切换输出分辨率（横/竖屏）后，按 ``add_story_scene`` 同源逻辑批量重绑各场景的模板底稿。

        - 重建 ``ffmpeg_processor`` 以使 ``make_backgroud_medias`` 按宽高选择 169_ / 916_ 模板；
        - 对每个场景重写 zero / zero_image / zero_audio / clip / clip_audio / clip_image；
        - 结束时 ``save_scenes_to_json()``（无场景时仅更新处理器与模板路径缓存）。"""
        vw, vh = int(video_width), int(video_height)
        self.ffmpeg_processor = FfmpegProcessor(self.pid, self.language, vw, vh)

        self.background_image, self.background_video, background_music = config.make_backgroud_medias(
            self.pid, self.channel, self.ffmpeg_processor, self.ffmpeg_audio_processor
        )
        if not self.background_video or not self.background_image:
            raise FileNotFoundError(
                f"未找到与 {vw}×{vh} 匹配的频道模板（clip/ 下的 169_ 或 916_ 静帧与 MP4），channel={self.channel}"
            )

        zero_audio_extracted = self.ffmpeg_audio_processor.extract_audio_from_video(background_music)
        if background_music and zero_audio_extracted is None:
            print("⚠️ clip 模板 MP4 未提取音轨成功，zero_audio / clip_audio 仍按既有流程写入路径")

        for story in self.scenes:
            oldv, zero = refresh_scene_media(story, "zero", ".mp4", self.background_video, True)
            oldi, zero_image = refresh_scene_media(story, "zero_image", ".webp", self.background_image, True)
            olda, zero_audio = refresh_scene_media(story, "zero_audio", ".wav", zero_audio_extracted, True)
            refresh_scene_media(story, "clip", ".mp4", zero, True)
            refresh_scene_media(story, "clip_audio", ".wav", zero_audio, True)
            refresh_scene_media(story, "clip_image", ".webp", zero_image, True)

        self.save_scenes_to_json()
