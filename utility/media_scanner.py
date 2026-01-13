
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from collections import defaultdict
import re
import os
import time
from utility.file_util import safe_copy_overwrite, get_file_path, build_scene_media_prefix
from project_manager import refresh_scene_media
import threading
import config


ANIMATE_TYPE_PATTERNS = [
    (r"_I2V(_\d{8})?\.mp4$", "_I2V"),
    (r"_2I2V(_\d{8})?\.mp4$", "_2I2V"),
    (r"_WS2VL(_\d{8})?\.mp4$", "_WS2VL"),
    (r"_WS2VR(_\d{8})?\.mp4$", "_WS2VR"),
    (r"_S2V(_\d{8})?\.mp4$", "_S2V"), # clip_project_20251208_1710_10708_S2V_13231028_60_.mp4
    (r"_INT(_\d{8})?\.mp4$", "_INT"),
    (r"_ENH(_\d{8})?\.mp4$", "_ENH"),
    (r"_FS2V(_\d{8})?\.mp4$", "_FS2V"),
    (r"_AI2V(_\d{8})?\.mp4$", "_AI2V")
]


ANIMATE_WITH_AUDIO = ["_WS2VL", "_WS2VR", "_S2V", "_FS2V"]



@dataclass
class VideoFileInfo:
    """Information extracted from video filename"""
    file_path: str
    image_path: str
    filename: str
    video_type: str  # 'clip', "narration", 'zero'
    pid: str
    scenario_id: str
    video_mode: str
    side: Optional[str] = None  # 'L' or 'R' for WS2V
    timestamp: float = 0.0
    
    def get_pair_key(self) -> str:
        """Get key for pairing WS2V videos"""
        return f"{self.pid}_{self.scenario_id}_WS2V"
    
    def get_output_name(self) -> str:
        """Get output filename without side indicator"""
        return build_scene_media_prefix(self.pid, self.scenario_id, self.video_type, self.video_mode, True) + ".mp4"



class VideoPairManager:

    def __init__(self):
        self.pairs = defaultdict(dict)  # {pair_key: {'L': VideoFileInfo, 'R': VideoFileInfo}}
        self.processed_pairs = set()  # Track already processed pairs
    
    def add_video(self, video_info: VideoFileInfo) -> Optional[tuple]:
        """
        Add a video to the pair manager
        Returns: (left_video, right_video) tuple if pair is complete, None otherwise
        """
        if video_info.video_mode != "WS2V":
            return None
        
        pair_key = video_info.get_pair_key()
        
        # Check if this pair was already processed
        if pair_key in self.processed_pairs:
            print(f"Pair {pair_key} already processed, skipping")
            return None
        
        # Add to pairs dict
        self.pairs[pair_key][video_info.side] = video_info
        
        # Check if pair is complete
        if 'L' in self.pairs[pair_key] and 'R' in self.pairs[pair_key]:
            left_video = self.pairs[pair_key]['L']
            right_video = self.pairs[pair_key]['R']
            
            # Mark as processed
            self.processed_pairs.add(pair_key)
            
            print(f"WS2V pair complete: {pair_key}")
            return (left_video, right_video)
        else:
            missing_side = 'R' if 'L' in self.pairs[pair_key] else 'L'
            print(f"WS2V pair incomplete: {pair_key}, waiting for {missing_side} video")
            return None
    
    def get_incomplete_pairs(self) -> List[str]:
        """Get list of incomplete pair keys"""
        incomplete = []
        for pair_key, videos in self.pairs.items():
            if pair_key not in self.processed_pairs and len(videos) < 2:
                incomplete.append(pair_key)
        return incomplete



class MediaScanner:


    def __init__(self, workflow, stability_duration: int):
        self.workflow = workflow
        self.ffmpeg_processor = workflow.ffmpeg_processor
        self.stability_duration = stability_duration


    def scanning(self, watch_path: str):
        pair_manager = VideoPairManager()
        mp4_files = sorted(Path(watch_path).glob("*.mp4"))
        if not mp4_files:
            return
            
        # Try to find a valid video to process
        for file_path in mp4_files:
            video_info = self.parse_video_filename(self.workflow.pid, file_path.name)
            if not video_info:
                continue
            
            # Wait for file to be stable (fully uploaded/copied)
            if not self._wait_for_file_stability(file_path):
                continue
            
            video_info.file_path = str(file_path)
            if "_ENH" in file_path.stem:
                image_path_obj = file_path.parent / file_path.stem
                if image_path_obj.exists() and image_path_obj.is_dir():
                    png_files = sorted(image_path_obj.glob("*.png"))
                    if png_files:
                        video_info.image_path = str(png_files[-1])
                    else:
                        video_info.image_path = ""
                else:
                    video_info.image_path = ""

            # Handle WS2V pairing
            #if video_info.video_mode == "WS2V": # deprecated !!!!
            #    pair_result = pair_manager.add_video(video_info)
            #    if pair_result:
            #        # Found a complete pair
            #        left_video, right_video = pair_result
            #        print(f"Found WS2V pair: {left_video.filename} + {right_video.filename}")
            #        self._process_video_pair(left_video, right_video, gen_folder)

            # Single video mode - process immediately
            print(f"Found video to process: {video_info.filename} (mode: {video_info.video_mode})")
            # self._process_single_video(video_info, gen_folder)
            copy_to = config.BASE_MEDIA_PATH+"/input_mp4" + "/" + video_info.get_output_name()
            safe_copy_overwrite(video_info.file_path, copy_to)
            bak_path = str(Path(video_info.file_path).with_suffix('.bak.mp4'))
            os.replace(video_info.file_path, bak_path)
            print(f"Processing completed successfully: {video_info.filename}")

            target_scene = None
            for scene in self.workflow.scenes:
                if str(scene["id"]) == str(video_info.scenario_id):
                    target_scene = scene
                    break
            if not target_scene:
                return

            if "_ENH" in copy_to:
                status = "EN2"
            elif "_INT" in copy_to:
                status = "IN2"
            else:
                status = "ORI"
            target_scene[video_info.video_type + "_status"] = status
            if status=="ORI":
                fps = self.ffmpeg_processor.get_video_fps(copy_to)
                target_scene[video_info.video_type + "_fps"] = fps
            if video_info.image_path:
                target_scene[video_info.video_type + "_image_last"] = video_info.image_path

            for pattern, type_suffix in ANIMATE_TYPE_PATTERNS:
                if re.search(pattern, copy_to):
                    self.take_gen_video(copy_to, video_info.video_type, type_suffix, target_scene)
        
    
    def _wait_for_file_stability(self, file_path: Path) -> bool:
        """
        Wait for a file to become stable (size not changing)
        
        Args:
            file_path: Path to the file to monitor
            stability_duration: How long the file size must remain constant (sec)
            check_interval: How often to check file size (sec)
        
        Returns:
            True if file is stable, False if file disappeared or error occurred
        """
        if not file_path.exists():
            return False
        
        print(f"Waiting for file to stabilize: {file_path.name}")
        
        last_size = -1
        stable_time = 0
        check_interval = 2
        
        while stable_time < self.stability_duration:
            if not file_path.exists():
                print(f"File disappeared during stability check: {file_path.name}")
                return False
            
            try:
                current_size = file_path.stat().st_size
                
                if current_size == last_size:
                    stable_time += check_interval
                    print(f"File size stable for {stable_time}s: {file_path.name} ({current_size} bytes)")
                else:
                    stable_time = 0
                    print(f"File size changed: {file_path.name} ({last_size} -> {current_size} bytes)")
                    last_size = current_size
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"Error checking file stability: {e}")
                return False
        
        print(f"File is stable: {file_path.name} (size: {last_size} bytes)")
        return True
    


    def parse_video_filename(self, pid: str, filename: str) -> Optional[VideoFileInfo]:
        # Skip backup files
        if filename.endswith('.bak.mp4'):
            return None
        
        # Unified pattern for I2V, 2I2V, INT, ENH - handle all video types
        unified_pattern = r'^(clip|narration|zero)_(.+)_([^_]+)_(I2V|2I2V|INT|ENH)_(.*?)\.mp4$'
        match = re.match(unified_pattern, filename)
        if match and match.group(2) == pid:
            return VideoFileInfo(
                file_path="",
                image_path="",
                filename=filename,
                video_type=match.group(1),
                pid=pid,
                scenario_id=match.group(3),
                video_mode=match.group(4)
            )

        # Unified pattern for WS2VL, WS2VR, S2V, FS2V, PS2V - handle all video types
        unified_pattern = r'^(clip|narration|zero)_(.+)_([^_]+)_(WS2VL|WS2VR|S2V|FS2V|PS2V)_(.*?).*-audio(\.mp4)?$'
        match = re.match(unified_pattern, filename)
        if match and match.group(2) == pid:
            return VideoFileInfo(
                file_path="",
                image_path="",
                filename=filename,
                video_type=match.group(1),
                pid=pid,
                scenario_id=match.group(3),
                video_mode=match.group(4)
            )

        return None
    
    
    
    def _process_video_pair(self, left_video: VideoFileInfo, right_video: VideoFileInfo, gen_folder: str):
        temp_left_path = gen_folder + "/" + (left_video.filename.replace(".mp4", "_tmp.mp4"))
        right_work_path = gen_folder + "/" + right_video.filename
        
        safe_copy_overwrite(left_video.file_path, temp_left_path)
        safe_copy_overwrite(right_video.file_path, str(right_work_path))
        
        # Rename files with .bak.mp4 extension (replace .mp4 with .bak.mp4)
        left_bak_path = str(Path(left_video.file_path).with_suffix('.bak.mp4'))
        right_bak_path = str(Path(right_video.file_path).with_suffix('.bak.mp4'))
        os.replace(left_video.file_path, left_bak_path)
        os.replace(right_video.file_path, right_bak_path)

        print(f"Pair processing completed : {left_video.get_pair_key()}")

        self.ffmpeg_processor._combine_left_right_videos(temp_left_path, right_work_path, gen_folder + "/" + left_video.get_output_name())
        os.remove(temp_left_path)
        os.remove(right_work_path)


    def take_gen_video(self, gen_video, media_type, type_suffix, scene):
        gen_video = self.ffmpeg_processor.resize_video(gen_video, width=None, height=self.ffmpeg_processor.height)

        audio = get_file_path(scene, media_type + "_audio")
        if audio: # always cut to the same duration as the audio
            gen_video = self.ffmpeg_processor.add_audio_to_video(gen_video, audio, True)
        #else :
        #    audio = self.ffmpeg_audio_processor.extract_audio_from_video(enhanced_video)
        #    olda, audio = refresh_scene_media(scene, av_type + "_audio", ".wav", audio)

        if "_WS2VL" == type_suffix:
            #scene[av_type+"_left_input"] = original_gen_video
            refresh_scene_media(scene, media_type+"_left", ".mp4", gen_video, True)
        elif "_WS2VR" == type_suffix:
            #scene[av_type+"_right_input"] = original_gen_video
            refresh_scene_media(scene, media_type+"_right", ".mp4", gen_video, True)
        else:
            #scene[av_type+"_input"] = original_gen_video
            oldv, gen_video = refresh_scene_media(scene, media_type, ".mp4", gen_video, True)
            # refresh_scene_media(scene, "clip_image_last", ".webp", self.ffmpeg_processor.extract_last_frame(gen_video))
            # thread = threading.Thread(target=self.workflow.sd_processor._improve_image_as_webp, args=(scene, media_type))
            # thread.daemon = True
            # thread.start()