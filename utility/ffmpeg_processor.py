import os
import subprocess
import shutil
from pathlib import Path

from mpmath import rational
from config import ffmpeg_path, ffprobe_path, FONT_0, FONT_1, FONT_3, FONT_4, FONT_7, FONT_8
import config
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.file_util import safe_copy_overwrite
import random
import unicodedata


# Standardized framerate to prevent sync issues
STANDARD_FPS = 60
STANDARD_AUDIO_RATE = 44100
STANDARD_AUDIO_CHANNELS = 2

# NVENC limitations
NVENC_MAX_WIDTH = 4096
NVENC_MAX_HEIGHT = 4096
NVENC_MAX_PIXELS = 8192 * 8192  # Maximum total pixels


class FfmpegProcessor:


    def __init__(self, pid, language, video_width=None, video_height=None):
        self.pid = pid
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        
        # Get video dimensions from parameters or use defaults (1920x1080)
        self.width = int(video_width) if video_width else 1920
        self.height = int(video_height) if video_height else 1080
        
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)

        # Calculate common overlay dimensions based on main dimensions
        self.overlay_width_large = self.width // 2  # For center video overlay
        self.overlay_height_large = self.height // 2
        self.overlay_width_small = int(self.width * 0.3)  # For sliding images
        self.overlay_height_small = int(self.height * 0.533)  # Maintain roughly square aspect
            
        self.language = language
        if language == "tw":
            self.font_video = FONT_7
            self.font_size = 16
            self.font_title = FONT_8
        else:
            self.font_video = FONT_4
            self.font_size = 16
            self.font_title = FONT_0
        
        # 验证并修复字体路径
        self._validate_and_fix_font_path()



    def run_ffmpeg_command(self, cmd):
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        print(f"------------\n{' '.join(cmd)}\n------------")
        return result



    nvenc_available = None
    def _check_nvenc_availability(self):
        if self.nvenc_available is not None:
            return self.nvenc_available

        try:
            cmd = [self.ffmpeg_path, "-encoders"]
            result = self.run_ffmpeg_command(cmd)
            self.nvenc_available = "h264_nvenc" in result.stdout
            return self.nvenc_available
        except Exception as e:
            print(f"⚠️  Could not check NVENC availability: {e}")
            self.nvenc_available = False
            return self.nvenc_available


    def _get_encoder_config(self):
        """Get encoder configuration based on resolution compatibility."""
        if self._check_nvenc_availability():
            return {
                "codec": "h264_nvenc",
                "preset": "fast",
                "quality": ["-cq", "18"],  # Use CQ for NVENC
                "hwaccel": ["-hwaccel", "cuda"]  # Specify GPU device
                #"hwaccel": ["-hwaccel_device", "0", "-hwaccel", "cuda"]  # Specify GPU device
            }
        else:
            return {
                "codec": "libx264",
                "preset": "medium",
                "quality": ["-crf", "18"],  # Use CRF for x264
                "hwaccel": []  # No hardware acceleration for software encoding
            }


    def _get_input_args(self):
        """Get input arguments (like hardware acceleration) based on resolution."""
        config = self._get_encoder_config()
        return config["hwaccel"]


    def _get_output_args(self):
        """Get output arguments (codec, preset, quality) based on resolution."""
        config = self._get_encoder_config()
        args = []
        
        # Add codec and quality settings
        args.extend(["-c:v", config["codec"]])
        args.extend(["-preset", config["preset"]])
        args.extend(config["quality"])
        
        return args


    def _build_encoder_args(self, width=None, height=None):
        """Build encoder arguments based on resolution - DEPRECATED, use _get_input_args and _get_output_args instead."""
        config = self._get_encoder_config(width, height)
        args = []
        
        # Add hardware acceleration if available
        args.extend(config["hwaccel"])
        
        # Add codec and quality settings
        args.extend(["-c:v", config["codec"]])
        args.extend(["-preset", config["preset"]])
        args.extend(config["quality"])
        
        return args

 
    def _get_scale_filter(self, width=None, height=None, fps=None):
        """Generate scale filter string with configurable dimensions and standardized fps"""
        if fps is None:
            fps = STANDARD_FPS
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        return f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}"


    def _get_simple_scale_filter(self, width=None, height=None, fps=None):
        """Generate simple scale filter string without padding but with standardized fps"""
        if fps is None:
            fps = STANDARD_FPS
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        return f"scale={width}:{height},fps={fps}"

    
    def _ffmpeg_input_args(self, input, input2=None, input3=None):
        args = [
            self.ffmpeg_path, "-y",
        ]
        args.extend(self._get_input_args())
        args.extend([
            "-i", input
        ])
        if input2:
            args.extend([
                "-i", input2
            ])
        if input3:
            args.extend([
                "-i", input3
            ])
        return args


    def _get_audio_encode_args(self, bitrate="192k", sample_rate=None, channels=None, volume=None):
        if bitrate is None:
            return [ "-an" ]
        else:
            return [
                "-c:a", "aac",
                "-b:a", bitrate,
                "-ar", str(sample_rate or STANDARD_AUDIO_RATE),
                "-ac", str(channels or STANDARD_AUDIO_CHANNELS)
            ]
    
    
    def _get_video_output_args(self, fps=None, pix_fmt="yuv420p", keyframe_interval=True):
        args = [
            "-pix_fmt", pix_fmt,
            "-r", str(fps or STANDARD_FPS)
        ]
        args.extend(self._get_output_args())
        
        if keyframe_interval:
            fps_val = fps or STANDARD_FPS
            args.extend([
                "-g", str(fps_val),  # GOP size (keyframe interval)
                "-keyint_min", str(fps_val),  # Minimum keyframe interval
                "-sc_threshold", "0"  # Disable scene detection
            ])
        
        return args


    def _get_output_optimization_args(self, vsync=None, faststart=True, avoid_negative_ts=True):
        args = []
        
        if vsync:
            args.extend(["-vsync", vsync])
        
        if faststart:
            args.extend(["-movflags", "+faststart"])
        
        if avoid_negative_ts:
            args.extend(["-avoid_negative_ts", "make_zero"])
        
        return args
    

    def _validate_and_fix_font_path(self):
        """验证并修复字体路径，确保字体文件存在"""
        original_path = self.font_video["path"]
        
        # 尝试多种路径格式
        possible_paths = [
            original_path,  # 原始路径
            original_path.replace("/", "\\"),  # 转换为 Windows 路径
            os.path.abspath(original_path),  # 绝对路径
            os.path.abspath(original_path.replace("/", "\\")),  # Windows 绝对路径
        ]
        
        # 检查哪个路径是有效的
        for path in possible_paths:
            if os.path.exists(path):
                if path != original_path:
                    print(f"✅ 找到有效字体路径: {path}")
                    # 更新字体路径
                    self.font_video = {
                        "name": self.font_video["name"],
                        "path": path
                    }
                else:
                    print(f"✅ 原始字体路径有效: {path}")
                return
        
        print(f"⚠️  警告: 未找到字体文件，尝试的路径:")
        for path in possible_paths:
            print(f"  ❌ {path}")
        print(f"  将尝试使用系统默认字体")


    @property
    def temp_dir(self):
        """动态获取临时目录路径，确保使用最新的 pid"""
        return os.path.abspath(config.get_temp_path(self.pid))


    def convert_to_mp4(self, input_path):
        output_path = config.get_temp_file(self.pid, "mp4")
        """Converts a video file to MP4 format and resizes to configured dimensions."""
        try:
            cmd = self._ffmpeg_input_args(input_path)
            cmd.extend(self._get_video_output_args())
            cmd.extend(self._get_audio_encode_args())
            cmd.extend(self._get_output_optimization_args())
            cmd.extend([
                "-vf", self._get_scale_filter(),
                output_path
            ])
            
            print(f"🔄 Converting to MP4 and resizing to {self.width}x{self.height}: {input_path}")
            self.run_ffmpeg_command(cmd)
            print(f"✅ Successfully converted and resized: {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg Error converting to MP4: {e.stderr}")

        return output_path



    def refps_video(self, video_path:str, fps:int) -> str:
        try:
            output_path = config.get_temp_file(self.pid, "mp4")

            cmd = [
                self.ffmpeg_path,
                "-i", video_path,
                "-vf", "fps="+str(fps),
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "medium",
            ]
            cmd.extend(self._get_audio_encode_args())
            cmd.append(output_path)
            
            self.run_ffmpeg_command(cmd)
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error 1: {e.stderr}")


    def resize_video(self, video_path, width, height, startx=None, starty=None):
        try:
            crop_width, crop_height = self.get_resolution(video_path)
            x_y_ratio = (float(crop_width)/float(crop_height))
            if x_y_ratio > 1.0:
                x_y_ratio = 16.0/9.0
            else:
                x_y_ratio = 9.0/16.0

            if height is None and width is None:
                height = crop_height
                width = crop_width
            elif width is None:
                width = int(height * x_y_ratio)
            elif height is None:
                height = int(width / x_y_ratio)

            # Check if cropping is needed
            need_crop = (startx is not None and startx != 0) or (starty is not None and starty != 0)
            need_scale = (crop_height != height or crop_width != width)
            
            output_path = config.get_temp_file(self.pid, "mp4")
            # Early exit if no changes needed
            if not need_scale and not need_crop:
                shutil.copy2(video_path, output_path)
                print(f"📋 No changes needed, copying file: {os.path.basename(video_path)}")
                return output_path
            
            # Normalize startx and starty (default to 0 if None)
            if startx is None:
                startx = 0
            if starty is None:
                starty = 0
            
            # Build and execute FFmpeg command
            cmd = self._build_resize_command( video_path, output_path, width, height, startx, starty )
            
            print(f"🔧 Executing FFmpeg command for resize_video: {' '.join(cmd)}")
            self.run_ffmpeg_command(cmd)
            return output_path
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg processing failed with exit code {e.returncode}: {e.stderr}")
            return None
        except Exception as e:
            print(f"❌ Error in resize_video: {e}")
            return None


    def trim_video(self, video_path, start_time=0, end_time=None, volume=1.0):
        """
        Resize a video with optional cropping from start_x, start_y.
        """
        try:
            duration = self.get_duration(video_path) or 0.0
            if end_time is None or end_time > duration:
                end_time = duration
            need_time_cut = (start_time > 0 or end_time < duration)

            # Early exit if no changes needed
            if not need_time_cut and volume == 1.0:
                output_path = config.get_temp_file(self.pid, "mp4")
                shutil.copy2(video_path, output_path)
                print(f"📋 No changes needed, copying file: {os.path.basename(video_path)}")
                return output_path
            
            # Build and execute FFmpeg command
            output_path = config.get_temp_file(self.pid, "mp4")
            cmd = self._build_trim_command( video_path, output_path, start_time, end_time, volume )
            
            print(f"🔧 Executing FFmpeg command for trim_video: {' '.join(cmd)}")
            self.run_ffmpeg_command(cmd)
            return output_path
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg processing failed with exit code {e.returncode}: {e.stderr}")
            return None
        except Exception as e:
            print(f"❌ Error in trim_video: {e}")
            return None


    def _build_resize_command(self, video_path, output_path, target_width, target_height, startx=0, starty=0):
        """Build FFmpeg command for video resizing with optional cropping."""
        cmd = self._ffmpeg_input_args(video_path)
        
        # Build video filter chain
        # If cropping is needed, combine crop and scale filters
        need_crop = (startx != 0 or starty != 0)
        
        if need_crop:
            # Get original video dimensions for crop calculation
            original_width, original_height = self.get_resolution(video_path)
            # Calculate crop width and height (crop to target size before scaling)
            crop_w = min(target_width, original_width - startx)
            crop_h = min(target_height, original_height - starty)
            # Build filter chain: crop first, then scale
            vf_filter = f"crop={crop_w}:{crop_h}:{startx}:{starty},scale={target_width}:{target_height}"
        else:
            # Only scale if no cropping needed
            vf_filter = f"scale={target_width}:{target_height}"
        
        # Add video encoder configuration
        cmd.extend(self._get_video_output_args(keyframe_interval=False))
        
        # Add audio configuration - re-encode to ensure consistency
        if self.has_audio_stream(video_path):
            cmd.extend(self._get_audio_encode_args())

        # Add common output options
        cmd.extend(self._get_video_output_args(keyframe_interval=False))
        cmd.extend(["-sc_threshold", "0"])
        cmd.extend(self._get_output_optimization_args())
        cmd.extend([
            "-vf", vf_filter,
            output_path
        ])
        
        return cmd


    def _build_trim_command(self, video_path, output_path, start_time, end_time, volume):
        cmd = self._ffmpeg_input_args(video_path)

        cmd.extend(self._get_video_output_args(keyframe_interval=False))
        
        if self.has_audio_stream(video_path) and volume > 0.0:
            if volume != 1.0:
                cmd.extend(["-af", f"volume={volume}"])
            cmd.extend(self._get_audio_encode_args())
        
        cmd.extend(self._get_output_optimization_args())
        #cmd.extend(["-sc_threshold", "0"])
        cmd.extend([
            "-ss", str(start_time), 
            "-to", str(end_time),
            output_path
            ])
        return cmd


    def image_audio_to_video(self, image_path, audio_path, animation_choice=1):
        # create video from image and audio, and save to video_path, keep full duration of audio
        # animation_choice: 1=still, 2=move left, 3=move right
        try:
            video_path = config.get_temp_file(self.pid, "mp4")

            # 根据动画选择构建视频滤镜
            vf_filter = self._build_animation_filter(animation_choice)
            
            cmd = self._ffmpeg_input_args(image_path, audio_path)
            cmd.extend(self._get_audio_encode_args())
            cmd.extend(self._get_video_output_args(keyframe_interval=True))
            cmd.extend(self._get_output_optimization_args())
            cmd.extend([
                "-shortest",  # Use shortest stream duration (audio duration)
                "-loop", "1",
                "-vf", vf_filter,
                video_path
            ])
            
            self.run_ffmpeg_command(cmd)
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error 1: {e.stderr}")

        return video_path
    

    def _build_animation_filter(self, animation_choice):
        """构建动画滤镜"""
        base_filter = self._get_scale_filter()
        
        if animation_choice == 1:  # 静止
            return base_filter
            
        elif animation_choice == 2:  # 向左移动
            # 创建图像放大并从右向左平移的效果
            return f"{base_filter},scale=iw*1.2:ih*1.2,crop={self.width}:{self.height}:(iw-ow)*(1-t/10):0"
            
        elif animation_choice == 3:  # 向右移动
            # 创建图像放大并从左向右平移的效果  
            return f"{base_filter},scale=iw*1.2:ih*1.2,crop={self.width}:{self.height}:(iw-ow)*(t/10):0"
            
        elif animation_choice == 4:  # 动画效果
            # 创建缓慢缩放效果
            return f"{base_filter},scale=iw*(1+0.1*sin(t*0.5)):ih*(1+0.1*sin(t*0.5))"
            
        else:  # 默认静止
            return base_filter


    def video_audio_mix(self, video_path, audio_path, volume=1.0, audio_mix_position=0.0, match_audio_length=False):
        try:
            output_path = config.get_temp_file(self.pid, "mp4")
            # Get durations to determine if we need to extend video
            video_duration = self.get_duration(video_path)
            audio_duration = self.get_duration(audio_path)
            
            # Check if video has audio stream
            has_audio = self.has_audio_stream(video_path)
            
            print(f"🎬 Video duration: {video_duration:.2f}s, Audio duration: {audio_duration:.2f}s")
            print(f"🔊 Video has audio: {has_audio}, Target volume: {volume}, Mix position: {audio_mix_position:.2f}s")
            
            # Special case: volume=0 means we want to keep only original video audio (mute the new audio)
            if volume == 0.0:
                if has_audio:
                    # Video has audio, volume=0 means don't add new audio at all, just copy video
                    print(f"⚠️  Volume is 0, copying video without adding new audio")
                    import shutil
                    shutil.copy2(video_path, output_path)
                    return output_path
                else:
                    # Video has no audio, volume=0 doesn't make sense, treat as volume=1.0
                    print(f"⚠️  Volume is 0 but video has no audio, treating as volume=1.0")
                    volume = 1.0
            
            if match_audio_length and audio_duration > video_duration:
                # Audio is longer, extend video to match audio duration
                self.extend_video_with_last_frame(video_path, audio_path, output_path)
            else:
                # Get dynamic encoder configuration
                cmd = self._ffmpeg_input_args(video_path, audio_path)
                
                if has_audio:
                    # Video has audio - mix both audio streams
                    if audio_mix_position != 0.0:
                        # Delay the new audio to start at audio_mix_position
                        delay_ms = int(audio_mix_position * 1000)
                        audio_filter = f"[0:a]volume=1.0[a0];[1:a]volume={volume},adelay={delay_ms}|{delay_ms}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2"
                    else:
                        # No delay - mix from start
                        audio_filter = f"[0:a]volume=1.0[a0];[1:a]volume={volume}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2"
                    
                    cmd.extend([
                        "-map", "0:v:0",      # Map video from first input
                        "-filter_complex", audio_filter,  # Mix audio streams
                    ])
                else:
                    # Video has no audio - add the audio with optional delay
                    if audio_mix_position != 0.0:
                        # Add audio from specified position
                        delay_ms = int(audio_mix_position * 1000)
                        if volume != 1.0:
                            audio_filter = f"[1:a]volume={volume},adelay={delay_ms}|{delay_ms}[a]"
                        else:
                            audio_filter = f"[1:a]adelay={delay_ms}|{delay_ms}[a]"
                        
                        cmd.extend([
                            "-map", "0:v:0",
                            "-filter_complex", audio_filter,
                            "-map", "[a]"
                        ])
                    else:
                        # No delay - add from start
                        if volume != 1.0:
                            cmd.extend([
                                "-map", "0:v:0",
                                "-filter:a", f"volume={volume}",
                                "-map", "1:a:0"
                            ])
                        else:
                            cmd.extend([
                                "-map", "0:v:0",
                                "-map", "1:a:0"
                            ])
                
                cmd.extend(self._get_audio_encode_args())
                cmd.extend(self._get_video_output_args(keyframe_interval=True))
                cmd.extend(self._get_output_optimization_args())
                cmd.extend([
                    "-shortest",
                    output_path
                ])
            
                self.run_ffmpeg_command(cmd)
            
            # Verify final duration
            final_duration = self.get_duration(output_path)
            print(f"✅ Video audio mix complete. Final duration: {final_duration:.2f}s")
            
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error 2: {e.stderr}")
            return None

        return output_path


    def to_webp(self, image_path):
        output_path = config.get_temp_file(self.pid, "webp")
        self.run_ffmpeg_command([
            self.ffmpeg_path, "-y",
            "-i", image_path,
            output_path
        ])
        return output_path


    def extend_video_with_last_frame(self, video_path, audio_path, output_path):
        """
        Extend video by cloning the last frame to match audio duration.
        
        Args:
            video_path: Path to input video file
            audio_path: Path to input audio file
            output_path: Path to output video file
        """
        # Get durations
        video_duration = self.get_duration(video_path)
        audio_duration = self.get_duration(audio_path)
        
        # Audio is significantly longer, extend video to match audio duration
        print(f"🔄 Extending video to match audio length ({audio_duration:.2f}s)")
        
        # Use tpad filter to extend video with last frame (requires re-encode)
        video_extend_duration = audio_duration - video_duration
        video_filter = f"tpad=stop_duration={video_extend_duration:.5f}:stop_mode=clone"

        cmd = self._ffmpeg_input_args(video_path, audio_path)
        cmd.extend(self._get_audio_encode_args(channels=2, sample_rate=44100))
        cmd.extend(self._get_video_output_args(keyframe_interval=True))
        cmd.extend(self._get_output_optimization_args())
        cmd.extend([
            "-vf", video_filter,
            "-map", "0:v:0",
            "-map", "1:a:0",
            output_path
        ])
        
        self.run_ffmpeg_command(cmd)


    def add_left_right_picture_in_picture(self, background_video, overlay_video_left, overlay_video_right, ratio, delay_time, edge_blur=20):
        output_path = config.get_temp_file(self.pid, "mp4")
        
        # If both overlays are None, re-encode to ensure consistency
        if overlay_video_left is None and overlay_video_right is None:
            cmd = self._ffmpeg_input_args(background_video)
            cmd.extend(self._get_video_output_args(keyframe_interval=False))
            cmd.extend(self._get_audio_encode_args())
            self.run_ffmpeg_command(cmd)
            return output_path
        
        # Get background video dimensions and duration
        bg_width, bg_height = self.get_resolution(background_video)
        bg_duration = self.get_duration(background_video)
        
        # Calculate target height for overlays
        overlay_height = int(bg_height * ratio)
        
        cmd = self._ffmpeg_input_args(background_video)
        
        # Calculate overlay end time for display purposes
        overlay_end_time = bg_duration  # Default to background duration
        
        if overlay_video_left is not None and overlay_video_right is not None:
            # Both overlays present
            # Get overlay durations
            left_duration = self.get_duration(overlay_video_left)
            right_duration = self.get_duration(overlay_video_right)
            # Calculate how long each overlay should actually play
            left_play_duration = min(left_duration, bg_duration - delay_time)
            right_play_duration = min(right_duration, bg_duration - delay_time)
            overlay_end_time = min(delay_time + min(left_play_duration, right_play_duration), bg_duration)
            
            # CRITICAL: Use trim to cut overlay videos to exactly the duration they should play
            # This prevents FFmpeg from processing extra frames that cause speed issues
            # Add edge blur effect to overlay videos for smooth blending (using yuva444p for full chroma resolution)
            filter_complex = (
                f"[1:v]trim=duration={left_play_duration},setpts=PTS-STARTPTS+{delay_time}/TB,scale=-1:{overlay_height},"
                f"format=yuva444p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                f"a='if(lt(X,{edge_blur}),255*X/{edge_blur},"
                f"if(lt(Y,{edge_blur}),255*Y/{edge_blur},"
                f"if(gt(X,W-{edge_blur}),255*(W-X)/{edge_blur},"
                f"if(gt(Y,H-{edge_blur}),255*(H-Y)/{edge_blur},255))))'[left];"
                f"[2:v]trim=duration={right_play_duration},setpts=PTS-STARTPTS+{delay_time}/TB,scale=-1:{overlay_height},"
                f"format=yuva444p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                f"a='if(lt(X,{edge_blur}),255*X/{edge_blur},"
                f"if(lt(Y,{edge_blur}),255*Y/{edge_blur},"
                f"if(gt(X,W-{edge_blur}),255*(W-X)/{edge_blur},"
                f"if(gt(Y,H-{edge_blur}),255*(H-Y)/{edge_blur},255))))'[right];"
                f"[0:v][left]overlay=10:H-h-10[tmp];"
                f"[tmp][right]overlay=W-w-10:H-h-10[out]"
            )
            cmd.extend([
                "-i", overlay_video_left,
                "-i", overlay_video_right,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-map", "0:a?",
            ])
        elif overlay_video_left is not None:
            # Only left overlay
            left_duration = self.get_duration(overlay_video_left)
            left_play_duration = min(left_duration, bg_duration - delay_time)
            overlay_end_time = delay_time + left_play_duration
            
            filter_complex = (
                f"[1:v]trim=duration={left_play_duration},setpts=PTS-STARTPTS+{delay_time}/TB,scale=-1:{overlay_height},"
                f"format=yuva444p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                f"a='if(lt(X,{edge_blur}),255*X/{edge_blur},"
                f"if(lt(Y,{edge_blur}),255*Y/{edge_blur},"
                f"if(gt(X,W-{edge_blur}),255*(W-X)/{edge_blur},"
                f"if(gt(Y,H-{edge_blur}),255*(H-Y)/{edge_blur},255))))'[left];"
                f"[0:v][left]overlay=10:H-h-10[out]"
            )
            cmd.extend([
                "-i", overlay_video_left,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-map", "0:a?",
            ])
        else:
            # Only right overlay
            right_duration = self.get_duration(overlay_video_right)
            right_play_duration = min(right_duration, bg_duration - delay_time)
            overlay_end_time = delay_time + right_play_duration
            
            filter_complex = (
                f"[1:v]trim=duration={right_play_duration},setpts=PTS-STARTPTS+{delay_time}/TB,scale=-1:{overlay_height},"
                f"format=yuva444p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
                f"a='if(lt(X,{edge_blur}),255*X/{edge_blur},"
                f"if(lt(Y,{edge_blur}),255*Y/{edge_blur},"
                f"if(gt(X,W-{edge_blur}),255*(W-X)/{edge_blur},"
                f"if(gt(Y,H-{edge_blur}),255*(H-Y)/{edge_blur},255))))'[right];"
                f"[0:v][right]overlay=W-w-10:H-h-10[out]"
            )
            cmd.extend([
                "-i", overlay_video_right,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-map", "0:a?",
            ])
        
        # Use output parameters to handle frame rate conversion (not in filter chain)
        # This prevents speed issues and maintains proper sync
        cmd.extend(self._get_audio_encode_args())
        cmd.extend(self._get_video_output_args(keyframe_interval=False))
        cmd.extend(self._get_output_optimization_args())
        cmd.extend([
            "-t", str(bg_duration),  # CRITICAL: Limit output duration to background duration
            output_path
        ])
        
        # Print detailed debug information
        print(f"🖼️ Adding Left-Right Picture-in-Picture overlays:")
        print(f"   📹 Background: {bg_width}x{bg_height}, duration={bg_duration:.2f}s")
        print(f"   ✨ Edge blur: {edge_blur}px")
        
        if overlay_video_left is not None:
            left_w, left_h = self.get_resolution(overlay_video_left)
            left_dur = self.get_duration(overlay_video_left)
            left_actual = min(left_dur, bg_duration - delay_time)
            print(f"   ⬅️  Left overlay: {left_w}x{left_h}, original={left_dur:.2f}s → trimmed to {left_actual:.2f}s")
        
        if overlay_video_right is not None:
            right_w, right_h = self.get_resolution(overlay_video_right)
            right_dur = self.get_duration(overlay_video_right)
            right_actual = min(right_dur, bg_duration - delay_time)
            print(f"   ➡️  Right overlay: {right_w}x{right_h}, original={right_dur:.2f}s → trimmed to {right_actual:.2f}s")
        
        print(f"   ⏱️  Delay: {delay_time:.2f}s")
        print(f"   ⏹️  Overlay display: {delay_time:.2f}s to {overlay_end_time:.2f}s (duration: {overlay_end_time - delay_time:.2f}s)")
        print(f"   📐 Overlay height: {overlay_height}px ({ratio*100:.1f}% of background)")
        print(f"   🎯 Output duration: {bg_duration:.2f}s (forced with -t)")
        
        self.run_ffmpeg_command(cmd)
        return output_path


    def add_audio_to_video(self, video_path, audio_path, match_audio_length=True, change_ratio_to_match_audio_length=False):
        temp_file = config.get_temp_file(self.pid, "mp4")
        
        try:
            video_duration = self.get_duration(video_path)
            audio_duration = self.get_duration(audio_path)

            if match_audio_length:
                # Use a small tolerance (0.1s) to handle floating-point precision issues
                duration_diff = audio_duration - video_duration
                
                if duration_diff > 0.1 or change_ratio_to_match_audio_length:
                    # Audio is significantly longer, or extend video to match audio duration
                    #self.extend_video_with_last_frame(video_path, audio_path, temp_file)
                    video_path = self.adjust_video_to_duration( video_path, audio_duration )
                video_duration = audio_duration

            cmd = self._ffmpeg_input_args(video_path, audio_path)

            cmd.extend(self._get_audio_encode_args())
            cmd.extend(self._get_video_output_args(keyframe_interval=False))
            cmd.extend(self._get_output_optimization_args())
            cmd.extend([
                "-t", str(video_duration),  # 明确指定输出时长等于音频时长
                temp_file
            ])
            self.run_ffmpeg_command(cmd)
            
            # 检查生成的文件时长
            output_duration = self.get_duration(temp_file)
            print(f"🎬 生成文件时长: {output_duration:.2f}s (预期: 音频={audio_duration:.2f}s)")

        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error adding audio to video: {e.stderr}")

        return temp_file


    def has_audio_stream(self, video_path):
        """检测视频文件是否包含音频轨道"""
        try:
            result = self.run_ffmpeg_command([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                video_path
            ])
            
            # 如果命令执行成功且输出包含"audio"，则认为有音频流
            has_audio = result.returncode == 0 and result.stdout.strip() == "audio"
            print(f"音频检测 - 文件: {video_path}, 有音频: {has_audio}, 输出: '{result.stdout.strip()}', 错误码: {result.returncode}")
            return has_audio
        except Exception as e:
            print(f"音频检测异常 - 文件: {video_path}, 错误: {e}")
            return False


    def get_video_fps(self, video_path: str) -> int:
        """Get the FPS of a video"""
        try:
            result = self.run_ffmpeg_command([
                self.ffprobe_path,
                "-v", "quiet",
                "-select_streams", "v",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ])

            fps_str = result.stdout.strip()
            
            # Handle fractional FPS like "30000/1001"  
            # '24/1\n90000/1'
            if '\n' in fps_str:
                fps_str = fps_str.split('\n')[0]
            if '/' in fps_str:
                numerator, denominator = fps_str.split('/')
                fps = float(numerator) / float(denominator)
            else:
                fps = float(fps_str)
            
            return int(round(fps))
        except Exception as e:
            print(f"Error getting video FPS: {e}")
            return None


    # to fade the video with fade_in_length and fade_out_length, without aLpha channel
    def fade_video(self, video_path, fade_in_length, fade_out_length):
        output_path = config.get_temp_file(self.pid, "mp4")
        video_length = self.get_duration(video_path)
        has_audio = self.has_audio_stream(video_path)

        try:
            fade_out_start = max(0, video_length - fade_out_length)
            
            # 构建视频滤镜链 (不使用 alpha 通道)
            vf_parts = []
            
            # 添加淡入效果 (不使用 alpha 通道)
            if fade_in_length > 0:
                vf_parts.append(f"fade=t=in:st=0:d={fade_in_length}")
                print(f"🎬 添加淡入效果(无alpha通道): fade_in_length={fade_in_length}")
                
                # 检查fade参数是否合理
                if fade_in_length >= video_length / 2:
                    print(f"⚠️ 警告：fade_in_length ({fade_in_length}) 太长，可能覆盖整个视频!")
            
            # 添加淡出效果 (不使用 alpha 通道)
            if fade_out_length > 0:
                vf_parts.append(f"fade=t=out:st={fade_out_start}:d={fade_out_length}")
                print(f"🎬 添加淡出效果(无alpha通道): fade_out_length={fade_out_length}, fade_out_start={fade_out_start}, video_length={video_length}")
                
                # 检查fade参数是否合理
                if fade_out_start >= video_length:
                    print(f"⚠️ 警告：fade_out_start ({fade_out_start}) >= video_length ({video_length})，fade out可能不会生效!")
                if fade_out_length >= video_length / 2:
                    print(f"⚠️ 警告：fade_out_length ({fade_out_length}) 太长，可能覆盖整个视频!")
            
            cmd = [
                self.ffmpeg_path, "-y",
                "-hwaccel", "cuda",
                "-i", video_path
            ]
            
            # 只在有滤镜时添加 -vf 参数
            if vf_parts:
                cmd.extend(["-vf", ",".join(vf_parts)])
            
            # 音频处理逻辑 - 对音频同样应用淡入淡出效果
            if has_audio:
                audio_filters = []
                if fade_in_length > 0:
                    audio_filters.append(f"afade=t=in:st=0:d={fade_in_length}")
                if fade_out_length > 0:
                    audio_fade_out_start = max(0, video_length - fade_out_length)
                    audio_filters.append(f"afade=t=out:st={audio_fade_out_start}:d={fade_out_length}")
                
                if audio_filters:
                    cmd.extend(["-af", ",".join(audio_filters)])
                    print(f"🎵 添加音频淡入淡出效果: {','.join(audio_filters)}")
                
                cmd.extend(self._get_audio_encode_args())
            
            # 使用标准的 H.264 编码，输出为 MP4 (不支持 alpha 通道)
            cmd.extend([
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "medium",
            ])
            cmd.extend(self._get_output_optimization_args())
            cmd.append(output_path)

            print(f"🔧 FFmpeg命令: {' '.join(cmd)}")
            self.run_ffmpeg_command(cmd)
            
            audio_info = ""
            if has_audio:
                audio_info = f"，音频: 淡入淡出 (淡入: {fade_in_length}s, 淡出: {fade_out_length}s)"
            else:
                audio_info = "，音频: 无"
            print(f"✅ 成功添加视频淡入淡出效果(无alpha通道) (淡入: {fade_in_length}s, 淡出: {fade_out_length}s){audio_info}")
            
        except Exception as e:
            print(f"❌ fade_video出错: {e}")

        return output_path


    def video_fade(self, video_path, fade_in_length, fade_out_length, audio_fade):
        output_path = config.get_temp_file(self.pid, "mov")
        video_length = self.get_duration(video_path)
        has_audio = self.has_audio_stream(video_path)

        try:
            fade_out_start = max(0, video_length - fade_out_length)
            
            # 构建视频滤镜链
            vf_parts = ["format=rgba"]
            
            # 添加淡入效果
            if fade_in_length > 0:
                vf_parts.append(f"fade=t=in:st=0:d={fade_in_length}:alpha=1")
                print(f"🎬 添加淡入效果(alpha通道): fade_in_length={fade_in_length}")
                
                # 检查fade参数是否合理
                if fade_in_length >= video_length / 2:
                    print(f"⚠️ 警告：fade_in_length ({fade_in_length}) 太长，可能覆盖整个视频!")
            
            # 添加淡出效果
            if fade_out_length > 0:
                vf_parts.append(f"fade=t=out:st={fade_out_start}:d={fade_out_length}:alpha=1")
                print(f"🎬 添加淡出效果(alpha通道): fade_out_length={fade_out_length}, fade_out_start={fade_out_start}, video_length={video_length}")
                
                # 检查fade参数是否合理
                if fade_out_start >= video_length:
                    print(f"⚠️ 警告：fade_out_start ({fade_out_start}) >= video_length ({video_length})，fade out可能不会生效!")
                if fade_out_length >= video_length / 2:
                    print(f"⚠️ 警告：fade_out_length ({fade_out_length}) 太长，可能覆盖整个视频!")
            
            cmd = [
                self.ffmpeg_path, "-y",
                "-hwaccel", "cuda",
                "-i", video_path,
                "-vf", ",".join(vf_parts)
            ]
            
            # 音频处理逻辑
            if has_audio:
                if audio_fade:
                    # 对音频应用淡入淡出效果
                    audio_filters = []
                    if fade_in_length > 0:
                        audio_filters.append(f"afade=t=in:st=0:d={fade_in_length}")
                    if fade_out_length > 0:
                        audio_fade_out_start = max(0, video_length - fade_out_length)
                        audio_filters.append(f"afade=t=out:st={audio_fade_out_start}:d={fade_out_length}")
                    
                    if audio_filters:
                        cmd.extend(["-af", ",".join(audio_filters)])
                        print(f"🎵 添加音频淡入淡出效果: {','.join(audio_filters)}")
                    
                    cmd.extend(self._get_audio_encode_args())
                else:
                    # 保持原始音频不变 - 不应用任何淡入淡出效果
                    cmd.extend(self._get_audio_encode_args())
            
            # Use qtrle codec which supports alpha channel, in a .mov container
            cmd.extend(["-c:v", "qtrle"])
            cmd.extend(self._get_output_optimization_args())
            cmd.append(output_path)

            print(f"🔧 FFmpeg命令: {' '.join(cmd)}")
            self.run_ffmpeg_command(cmd)
            
            audio_info = ""
            if has_audio:
                if audio_fade:
                    audio_info = f"，音频: 淡入淡出 (淡入: {fade_in_length}s, 淡出: {fade_out_length}s)"
                else:
                    audio_info = "，音频: 保持原始(无淡入淡出)"
            else:
                audio_info = "，音频: 无"
            print(f"✅ 成功添加视频淡入淡出效果 (淡入: {fade_in_length}s, 淡出: {fade_out_length}s){audio_info}")
            
        except Exception as e:
            print(f"❌ video_fade出错: {e}")

        return output_path


    def check_video_size(self, video_path):
        try:
            # Get width
            width_result = self.run_ffmpeg_command([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ])
            
            # Get height
            height_result = self.run_ffmpeg_command([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=height",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ])
            
            width = int(width_result.stdout.strip())
            height = int(height_result.stdout.strip())
            
            return (width, height)
            
        except Exception as e:
            print(f"FFprobe Error getting video size: {e}")
            return (0, 0)


    def _analyze_audio_availability(self, video_segments):
        """
        Analyze audio availability across all video segments
        
        Returns:
            dict: Audio analysis information
        """
        audio_analysis = {
            'has_audio': [],
            'audio_count': 0,
            'no_audio_count': 0,
            'summary': '',
            'all_have_audio': True,
            'none_have_audio': True
        }
        
        for i, video_seg in enumerate(video_segments):
            has_audio = self.has_audio_stream(video_seg["path"])
            audio_analysis['has_audio'].append(has_audio)
            
            if has_audio:
                audio_analysis['audio_count'] += 1
                audio_analysis['none_have_audio'] = False
            else:
                audio_analysis['no_audio_count'] += 1
                audio_analysis['all_have_audio'] = False
            
            print(f"   Video {i+1}: {'🔊' if has_audio else '🔇'} {os.path.basename(video_seg['path'])}")
        
        # Generate summary
        if audio_analysis['all_have_audio']:
            audio_analysis['summary'] = f"All {len(video_segments)} videos have audio"
        elif audio_analysis['none_have_audio']:
            audio_analysis['summary'] = f"None of the {len(video_segments)} videos have audio"
        else:
            audio_analysis['summary'] = f"Mixed audio: {audio_analysis['audio_count']} with audio, {audio_analysis['no_audio_count']} without"
        
        return audio_analysis


    def _concat_videos_with_transitions(self, video_segments, keep_audio_if_has):
        video_out_path = config.get_temp_file(self.pid, "mp4")

        n_videos = len(video_segments)
        
        # NEW APPROACH: Extend videos AND standardize in one step using filter
        extended_video_paths = []
        temp_files_to_cleanup = []
        extended_durations = []
        
        try:
            print(f"   🔄 Extending and standardizing {n_videos} videos...")
            for i, video_seg in enumerate(video_segments):
                try:
                    original_duration = self.get_duration(video_seg["path"])
                    
                    # CRITICAL FIX: Each video needs to be extended by the NEXT transition duration
                    # video_segments[i]["duration"] is the transition TO this video (from previous)
                    # But we need to extend for the transition FROM this video (to next)
                    if i < n_videos - 1:
                        # Not the last video - extend by next transition duration
                        extension_needed = video_segments[i + 1]["duration"]
                    else:
                        # Last video - no extension needed (no next transition)
                        extension_needed = 0
                    
                    target_duration = original_duration + extension_needed
                    temp_extended_path = os.path.join(self.temp_dir, f"ext_{i:03d}_{hash(video_seg['path']) % 10000}.mp4")
                    
                    print(f"      📹 Video {i+1}/{n_videos}: {original_duration:.2f}s + {extension_needed:.2f}s → {target_duration:.2f}s")
                    
                    # Extend AND standardize in one ffmpeg command
                    if extension_needed > 0:
                        # Need to extend video for transition
                        success = self._extend_and_standardize_video(
                            video_seg["path"], 
                            extension_needed-0.03334, 
                            temp_extended_path
                        )
                        
                        if not success:
                            raise RuntimeError(f"Failed to extend video {i+1}")
                    else:
                        # Last video - just standardize without extension
                        print(f"         (Last video - standardizing without extension)")
                        # Move to expected path
                        import shutil
                        shutil.copy2(video_seg["path"], temp_extended_path)
                    
                    # Verify extended video
                    if not os.path.exists(temp_extended_path):
                        raise RuntimeError(f"Extended video {i+1} was not created")
                    
                    verify_duration = self.get_duration(temp_extended_path)
                    if verify_duration <= 0:
                        raise RuntimeError(f"Extended video {i+1} has invalid duration: {verify_duration}")
                    
                    extended_video_paths.append(temp_extended_path)
                    temp_files_to_cleanup.append(temp_extended_path)
                    extended_durations.append(verify_duration)
                    
                    print(f"         ✅ Extended: {verify_duration:.2f}s")
                    
                except Exception as e:
                    print(f"❌ CRITICAL ERROR processing video {i+1}/{n_videos}: {str(e)}")
                    print(f"   Video path: {video_seg['path']}")
                    raise
            
            print(f"✅ All videos extended and standardized!")
            print(f"   Total videos: {len(extended_video_paths)} (expected: {n_videos})")
            print(f"   📊 Extension summary:")
            for i in range(n_videos):
                if i < n_videos - 1:
                    next_trans = video_segments[i + 1]["duration"]
                    print(f"      Video {i}: extended by {next_trans:.2f}s (for transition to Video {i+1})")
                else:
                    print(f"      Video {i}: no extension (last video)")
            
            # Verify we have all videos
            if len(extended_video_paths) != n_videos:
                raise RuntimeError(f"Video extension incomplete: got {len(extended_video_paths)} videos, expected {n_videos}")
            
            # Build input arguments using extended video paths
            input_args = []
            for video_path in extended_video_paths:
                input_args.extend(["-i", video_path])
            
            print(f"   Building FFmpeg command with {len(input_args)//2} input files...")
            
            # Build video filter chain - USE MINIMAL PROCESSING to preserve baked effects
            video_filters = []
            
            # CRITICAL: Apply both FPS and resolution standardization for xfade compatibility
            print(f"   📝 Building video scale filters for {n_videos} videos...")
            for i in range(n_videos):
                # xfade requires all videos to have the same resolution, so we must scale
                video_filters.append(f"[{i}:v]fps={STANDARD_FPS}:round=near,{self._get_simple_scale_filter(self.width, self.height)}[v{i}]")
            print(f"      ✅ Created {len(video_filters)} video scale filters")
            
            # Build audio filter chain if processing audio
            # CRITICAL: Audio must be trimmed to match video transitions
            audio_filters = []
            expected_audio_duration = 0  # Initialize
            if keep_audio_if_has:
                print(f"   📝 Building audio filters...")
                # Check which videos have audio streams
                has_audio = []
                for i, video_path in enumerate(extended_video_paths):
                    has_audio.append(self.has_audio_stream(video_path))
                
                audio_count = sum(has_audio)
                no_audio_count = len(has_audio) - audio_count
                print(f"      🔊 Audio analysis: {audio_count} videos with audio, {no_audio_count} without")
                
                # Process audio streams - TRIM to compensate for transitions
                # LOGIC: Each video was extended by NEXT transition duration
                #        So we trim by that same amount to get original audio length
                for i in range(n_videos):
                    if i < n_videos - 1:
                        # Not the last video - trim by the SAME amount it was extended
                        # Video i was extended by video_segments[i+1]["duration"]
                        # So we trim by video_segments[i+1]["duration"] to restore original length
                        transition_dur = video_segments[i + 1]["duration"]
                        audio_to_keep = extended_durations[i] - transition_dur
                    else:
                        # Last video - was not extended, keep all
                        audio_to_keep = extended_durations[i]
                    
                    if has_audio[i]:
                        # Video has audio - extract and trim
                        audio_filters.append(f"[{i}:a]aresample={STANDARD_AUDIO_RATE},aformat=sample_fmts=fltp:sample_rates={STANDARD_AUDIO_RATE}:channel_layouts=stereo,atrim=0:{audio_to_keep:.3f},asetpts=PTS-STARTPTS[a{i}]")
                    else:
                        # Video has no audio - create silent audio for trimmed duration
                        audio_filters.append(f"anullsrc=channel_layout=stereo:sample_rate={STANDARD_AUDIO_RATE}:duration={audio_to_keep:.3f}[a{i}]")
                    
                    print(f"         Audio {i}: keeping {audio_to_keep:.2f}s of {extended_durations[i]:.2f}s")
                
                # Concatenate all trimmed audio streams
                audio_inputs = "".join([f"[a{i}]" for i in range(n_videos)])
                audio_concat_filter = f"{audio_inputs}concat=n={n_videos}:v=0:a=1[audio_out]"
                audio_filters.append(audio_concat_filter)
                
                # Calculate expected audio duration
                expected_audio_duration = sum([
                    extended_durations[i] - (video_segments[i + 1]["duration"] if i < n_videos - 1 else 0)
                    for i in range(n_videos)
                ])
                print(f"      ✅ Created {len(audio_filters)} audio filters")
                print(f"      📊 Expected audio duration: {expected_audio_duration:.2f}s")
            
            # Chain xfade transitions with correct offset calculation using EXTENDED durations
            current_video_label = "v0"
            
            # Add detailed debugging for xfade chain construction
            print(f"   📝 Building xfade transition chain for {n_videos} videos...")
            print(f"      Extended video durations:")
            for i in range(n_videos):
                print(f"         Video {i}: {extended_durations[i]:.2f}s")
            
            xfade_count = 0
            # Calculate offset - for xfade, offset is in the first input stream's timeline
            current_offset = 0.0
            
            for i in range(1, n_videos):
                video_seg = video_segments[i]
                transition_duration = video_seg["duration"]
                transition_effect = video_seg["transition"]
                
                # For xfade: offset is where transition starts in the current output timeline
                # After previous transitions, we're at current_offset
                # The previous EXTENDED video contributes (extended_duration - transition_duration) to output
                # So next transition starts at: current_offset + (extended_durations[i-1] - transition_duration)
                current_offset += extended_durations[i-1] - transition_duration
                
                if transition_effect == "random":
                    effect_name = random.choice(config.TRANSITION_EFFECTS)
                else:
                    effect_name = transition_effect

                next_video_label = f"vx{i}"
                xfade_filter = f"[{current_video_label}][v{i}]xfade=transition={effect_name}:duration={transition_duration}:offset={current_offset}[{next_video_label}]"
                video_filters.append(xfade_filter)
                xfade_count += 1
                
                # Show ALL transitions for debugging
                print(f"      🔗 Transition {i}: {effect_name} at offset={current_offset:.2f}s (dur={transition_duration:.2f}s)")
                print(f"         Mixing video {i-1} (ext={extended_durations[i-1]:.2f}s) with video {i} (ext={extended_durations[i]:.2f}s)")
                
                current_video_label = next_video_label
            
            expected_final_duration = current_offset + extended_durations[-1]
            print(f"      ✅ Created {xfade_count} xfade transitions")
            print(f"      📐 Expected video duration from xfade chain: {expected_final_duration:.2f}s")
            
            # Verify audio and video durations match
            if keep_audio_if_has:
                duration_diff = abs(expected_final_duration - expected_audio_duration)
                if duration_diff > 0.5:
                    print(f"      ⚠️  WARNING: Audio/Video duration mismatch: {duration_diff:.2f}s difference!")
                    print(f"         Video: {expected_final_duration:.2f}s, Audio: {expected_audio_duration:.2f}s")
                else:
                    print(f"      ✅ Audio and Video durations match ({duration_diff:.2f}s diff)")
            
            # Combine all filters
            all_filters = video_filters + audio_filters
            filter_complex = ";".join(all_filters)
            
            print(f"   📊 Filter summary:")
            print(f"      Total filters: {len(all_filters)} ({len(video_filters)} video + {len(audio_filters)} audio)")
            print(f"      Filter complex length: {len(filter_complex)} characters")
            print(f"      Final video output: [{current_video_label}]")
            if keep_audio_if_has:
                print(f"      Final audio output: [audio_out]")
            
            # Build FFmpeg command with HIGH QUALITY settings
            cmd = [self.ffmpeg_path, "-y"] + input_args + [
                # NOTE: Removed "-hwaccel", "cuda" to avoid conflicts with filter_complex operations
                # GPU acceleration is still used via h264_nvenc encoder
                "-filter_complex", filter_complex,
                "-map", f"[{current_video_label}]"
            ]
            
            # Add audio mapping if processing audio
            if keep_audio_if_has:
                cmd.extend(["-map", "[audio_out]"])
                cmd.extend(self._get_audio_encode_args())
            
            # Use software encoding for complex filter operations to avoid hardware encoder issues
            # Hardware encoders can have problems with very long filter chains
            use_software_encoder = n_videos > 10  # Use software for >10 videos
            
            if use_software_encoder:
                print(f"      📝 Using software encoder (libx264) for {n_videos} videos to ensure stability")
                cmd.extend([
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "20",
                ])
                cmd.extend(self._get_video_output_args(keyframe_interval=False))
                cmd.extend(self._get_output_optimization_args())
                cmd.append(video_out_path)
            else:
                cmd.extend([
                    # HIGH QUALITY encoding to preserve baked effects
                    "-c:v", "h264_nvenc",
                    "-preset", "fast",
                    "-crf", "20",
                ])
                cmd.extend(self._get_video_output_args(keyframe_interval=False))
                cmd.extend(self._get_output_optimization_args())
                cmd.append(video_out_path)
            
            # Execute FFmpeg command
            print(f"   🎬 Executing FFmpeg concat with transitions...")
            print(f"      Input videos: {len(extended_video_paths)}")
            print(f"      Expected transitions: {n_videos - 1}")
            
            # Save filter_complex to file for debugging
            filter_debug_path = os.path.join(self.temp_dir, "filter_complex_debug.txt")
            with open(filter_debug_path, 'w', encoding='utf-8') as f:
                f.write(f"Number of videos: {n_videos}\n")
                f.write(f"Number of filters: {len(all_filters)}\n")
                f.write(f"Filter complex length: {len(filter_complex)} characters\n\n")
                f.write("Complete filter_complex:\n")
                f.write(filter_complex)
                f.write("\n\n")
                for i, filt in enumerate(all_filters):
                    f.write(f"Filter {i}: {filt}\n")
            print(f"      🔍 Filter complex saved to: {filter_debug_path}")
            
            result = self.run_ffmpeg_command(cmd)
            
            # Check if FFmpeg succeeded
            if result.returncode != 0:
                print(f"❌ FFmpeg failed with return code: {result.returncode}")
                print(f"❌ Error details:")
                # Try to find the actual error message
                if result.stderr:
                    stderr_lines = result.stderr.strip().split('\n')
                    # Look for error lines
                    for line in stderr_lines[-20:]:  # Check last 20 lines
                        if 'error' in line.lower() or 'fail' in line.lower() or 'invalid' in line.lower():
                            print(f"   {line}")
                print(f"❌ Full STDERR (first 2000 chars): {result.stderr[:2000]}")
                raise RuntimeError(f"FFmpeg concatenation failed: {result.stderr[:500]}")
            
            # Print FFmpeg output for debugging
            if result.stderr:
                # Show last few lines of stderr which usually contains progress info
                stderr_lines = result.stderr.strip().split('\n')
                if len(stderr_lines) > 5:
                    print(f"🔍 FFmpeg output (last 5 lines):")
                    for line in stderr_lines[-5:]:
                        print(f"   {line}")
            
            # Verify output file was created and has reasonable duration
            if not os.path.exists(video_out_path):
                raise RuntimeError(f"Output video was not created: {video_out_path}")
            
            final_duration = self.get_duration(video_out_path)
            if final_duration <= 0:
                raise RuntimeError(f"Output video has invalid duration: {final_duration}")
            
            # Calculate expected duration (sum of all original durations - transitions overlap)
            total_original_duration = sum([self.get_duration(video_seg["path"]) for video_seg in video_segments])
            total_transition_duration = sum([video_seg["duration"] for video_seg in video_segments[1:]])  # Exclude first video
            expected_duration = total_original_duration - total_transition_duration
            
            # Check if duration is significantly shorter than expected
            duration_diff = abs(final_duration - expected_duration)
            if duration_diff > 10.0:  # More than 10 seconds difference
                print(f"   ⚠️  WARNING: Output duration differs from expected by {duration_diff:.2f}s!")
                print(f"      This suggests only partial videos were concatenated.")
                # Don't raise error, just warn for now
            
            # Verify audio stream exists if we expected it
            if keep_audio_if_has:
                output_has_audio = self.has_audio_stream(video_out_path)
                if output_has_audio:
                    print(f"      ✅ Output video contains audio stream")
                else:
                    print(f"      ⚠️  Warning: Output video has no audio stream (expected audio)")
            
            # Cleanup temporary extended videos
            for temp_file in temp_files_to_cleanup:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            print(f"🧹 Cleaned up {len(temp_files_to_cleanup)} temporary extended videos")
            
            return video_out_path
            
        except Exception as e:
            # Cleanup temporary files before raising
            for temp_file in temp_files_to_cleanup:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            raise RuntimeError(f"Transition-based concatenation failed: {e}") from e


    # split image into left and right from center
    def split_image(self, image_path, vertical_line_position):
        """Split an image into left and right parts at the specified vertical line position"""
        try:
            # Get image dimensions first
            probe_cmd = [
                self.ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_streams", image_path
            ]
            result = self.run_ffmpeg_command(probe_cmd)
            
            if result.returncode != 0:
                print(f"❌ Error getting image dimensions: {result.stderr}")
                return None, None
            
            import json
            data = json.loads(result.stdout)
            width = data['streams'][0]['width']
            height = data['streams'][0]['height']
            
            # Validate vertical_line_position
            if vertical_line_position < 0 or vertical_line_position >= width:
                print(f"❌ Invalid vertical_line_position: {vertical_line_position}. Must be between 0 and {width-1}")
                return None, None
            
            # Calculate widths for left and right parts
            left_width = vertical_line_position
            right_width = width - vertical_line_position
            
            # Create temporary files for left and right images
            left_image = config.get_temp_file(self.pid, "png")
            right_image = config.get_temp_file(self.pid, "png")
            
            # Extract left part (from 0 to vertical_line_position)
            left_cmd = [
                self.ffmpeg_path, "-y",
                "-i", image_path,
                "-vf", f"crop={left_width}:{height}:0:0",
                left_image
            ]
            
            # Extract right part (from vertical_line_position to end)
            right_cmd = [
                self.ffmpeg_path, "-y",
                "-i", image_path,
                "-vf", f"crop={right_width}:{height}:{vertical_line_position}:0",
                right_image
            ]
            
            # Execute both commands
            left_result = self.run_ffmpeg_command(left_cmd)
            right_result = self.run_ffmpeg_command(right_cmd)
            
            return left_image, right_image
            
        except Exception as e:
            print(f"❌ Error splitting image: {str(e)}")
            return None, None


    def concat_videos(self, video_paths, keep_audio):
        if len(video_paths) == 0:
            return None

        video_out_path = config.get_temp_file(self.pid, "mp4")
        if len(video_paths) == 1:
            safe_copy_overwrite(video_paths[0], video_out_path)
            return video_out_path
        
        try:
            concat_file_path = os.path.join(self.temp_dir, "chunk_concat_list.txt")
            with open(concat_file_path, "w", encoding="utf-8") as f:
                for video_path in video_paths:
                    abs_path = os.path.abspath(video_path).replace("\\", "/")
                    f.write(f"file '{abs_path}'\n")
            
            # build ffmpeg concat command with re-encoding for consistency
            concat_cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file_path,
                "-c:v", "libx264",  # Re-encode video to ensure consistency
                "-preset", "medium",
                "-crf", "18",
            ]
            concat_cmd.extend(self._get_video_output_args(keyframe_interval=False))

            if not keep_audio:
                concat_cmd.append("-an")  # drop audio completely
            else:
                # Re-encode audio to ensure consistency
                concat_cmd.extend(self._get_audio_encode_args())

            concat_cmd.extend(self._get_output_optimization_args())
            concat_cmd.append(video_out_path)
            
            print(f"🔨 Executing FFmpeg concat command...")
            result = self.run_ffmpeg_command(concat_cmd)
            
            final_duration = self.get_duration(video_out_path)
            print(f"✅ Successfully concatenated {len(video_paths)} chunks : {video_out_path}")
            print(f"   📐 Final duration: {final_duration:.2f}s")
            # Cleanup concat file
            if os.path.exists(concat_file_path):
                os.remove(concat_file_path)
            
            return video_out_path
            
        except Exception as e:
            print(f"❌ Simple demuxer concatenation error: {e}")
            # Cleanup concat file
            concat_file_path = os.path.join(self.temp_dir, "chunk_concat_list.txt")
            if os.path.exists(concat_file_path):
                os.remove(concat_file_path)
            raise RuntimeError(f"Simple demuxer concatenation failed: {e}") from e


    def concat_videos_demuxer(self, video_segments, keep_audio_if_has=False):
        if len(video_segments) == 1:
            return video_segments[0]["path"]

        video_paths = [seg["path"] for seg in video_segments]

        video_out_path = config.get_temp_file(self.pid, "mp4")
        
        try:
            concat_file_path = os.path.join(self.temp_dir, "chunk_concat_list.txt")
            with open(concat_file_path, "w", encoding="utf-8") as f:
                for video_path in video_paths:
                    abs_path = os.path.abspath(video_path).replace("\\", "/")
                    f.write(f"file '{abs_path}'\n")
            
            concat_cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file_path,
                "-c:v", "libx264",  # Re-encode video to ensure consistency
                "-preset", "medium",
                "-crf", "18",
            ]
            concat_cmd.extend(self._get_video_output_args(keyframe_interval=False))
            
            # Handle audio based on availability and settings
            if not keep_audio_if_has:
                concat_cmd.append("-an")  # Remove audio stream
            else:
                # Re-encode audio to ensure consistency
                concat_cmd.extend(self._get_audio_encode_args())
            
            concat_cmd.extend(self._get_output_optimization_args())
            concat_cmd.append(video_out_path)
            
            print(f"🔨 Executing FFmpeg concat command...")
            result = self.run_ffmpeg_command(concat_cmd)
            
            final_duration = self.get_duration(video_out_path)
            print(f"✅ Successfully concatenated {len(video_paths)} chunks using simple demuxer : {video_out_path}")
            print(f"   📐 Final duration: {final_duration:.2f}s")
            
            # Cleanup concat file
            if os.path.exists(concat_file_path):
                os.remove(concat_file_path)
            
            return video_out_path
            
        except Exception as e:
            print(f"❌ Simple demuxer concatenation error: {e}")
            # Cleanup concat file
            concat_file_path = os.path.join(self.temp_dir, "chunk_concat_list.txt")
            if os.path.exists(concat_file_path):
                os.remove(concat_file_path)
            raise RuntimeError(f"Simple demuxer concatenation failed: {e}") from e


    def build_video_on_segments(self, scenes):
        video_segments = []
        audio_segments = []
        raw_scene_index = 0
        for scene in scenes:
            if scene.get("effect_audio", None):
                if os.path.exists(scene["effect_audio"]):
                    audio_segments.append(scene)
            if raw_scene_index != scene["raw_scene_index"]:
                video_segments.append({"path":scene["video"], "transition":"random", "duration":1.0})
            else:
                video_segments.append({"path":scene["video"], "transition":"fade", "duration":1.0})
            raw_scene_index = scene["raw_scene_index"]

        # Step 2: Group video segments into smaller chunks for stable transition processing  
        # Reduce chunk size to 8 videos max - transitions become unstable with too many videos
        chunk_size = 8
        video_chunks = [video_segments[i:i + chunk_size] for i in range(0, len(video_segments), chunk_size)]
        
        print(f"🎬 Processing {len(video_segments)} videos in {len(video_chunks)} chunks of up to {chunk_size} videos each (with transitions)")
        
        # Step 3: Process each chunk separately
        chunk_segs = []
        temp_files_to_cleanup = []
        
        for i, chunk in enumerate(video_chunks):
            print(f"   📹 Processing chunk {i+1}/{len(video_chunks)} with {len(chunk)} videos...")
            try:
                chunk_output = self.concat_videos_demuxer(chunk)
                
                # Verify chunk was created successfully
                if not os.path.exists(chunk_output):
                    raise RuntimeError(f"Chunk output file was not created: {chunk_output}")
                
                chunk_duration = self.get_duration(chunk_output)
                if chunk_duration <= 0:
                    raise RuntimeError(f"Chunk has invalid duration: {chunk_duration}")
                
                chunk_segs.append({"path":chunk_output, "transition":"fade", "duration":1.0})
                temp_files_to_cleanup.append(chunk_output)
                print(f"   ✅ Chunk {i+1} processed successfully: {chunk_duration:.2f}s")
                
            except Exception as chunk_error:
                print(f"❌ Error processing chunk {i+1}: {chunk_error}")
                print(f"   📹 Chunk videos: {[seg['path'] for seg in chunk]}")
                # Don't fail completely - try to continue with remaining chunks
                # But warn about missing content
                print(f"⚠️  Chunk {i+1} will be skipped - this may result in missing video content!")
        
        # Step 4: Final concatenation of all chunk videos
        if len(chunk_segs) == 0:
            raise RuntimeError("No chunks were successfully processed! All video segments failed.")
        elif len(chunk_segs) == 1:
            # Only one chunk, just copy it
            print(f"✅ Single chunk processed, copied to final video")
            return chunk_segs[0]["path"]

        else:
            # Multiple chunks, concatenate them with shorter transitions between chunks
            print(f"🔗 Final concatenation of {len(chunk_segs)} chunk videos...")
            # Add debugging to show chunk details
            total_chunk_duration = 0
            for i, chunk_seg in enumerate(chunk_segs):
                chunk_duration = self.get_duration(chunk_seg["path"])
                total_chunk_duration += chunk_duration
                print(f"   📹 Chunk {i+1}: {chunk_duration:.2f}s - {chunk_seg['path']}")
            print(f"   📐 Total expected duration: {total_chunk_duration:.2f}s")
            
            return self.concat_videos_demuxer(chunk_segs)


    # cmd = f'..\ffmpeg\\bin\\ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{filename}"'
    def get_duration(self, filename):
        if not filename:
            return 0.0
        
        try:    
            result = self.run_ffmpeg_command([
                self.ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filename
                ])
            
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
            return 0.0
        except Exception as e:
            print(f"FFmpeg Error: {e}")
            return 0.0


    def get_resolution(self, filename):
        """Get the resolution (width, height) of an image or video file"""
        try:
            result = self.run_ffmpeg_command([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filename
            ])
            
            if result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    width = int(lines[0])
                    height = int(lines[1])
                    return width, height
            return None, None
        except Exception as e:
            print(f"FFmpeg Error getting resolution: {e}")
            return None, None



    def mirror_video(self, video_path):
        output_file = config.get_temp_file(self.pid, "mp4")
        cmd = self._ffmpeg_input_args(video_path)
        cmd.extend(self._get_video_output_args())
        cmd.extend(self._get_audio_encode_args(bitrate=None))
        cmd.extend(self._get_output_optimization_args())
        cmd.extend([
            "-vf", "hflip",
            output_file
        ])
        self.run_ffmpeg_command(cmd)
        print(f"✅ Video mirrored successfully: {output_file}")
        return output_file


    def reverse_video(self, video_path):
        output_file = config.get_temp_file(self.pid, "mp4")
        
        # Check if video has audio stream
        has_audio = self.has_audio_stream(video_path)
        
        try:
            cmd = self._ffmpeg_input_args(video_path)
            cmd.extend(self._get_video_output_args())
            if not has_audio:
                cmd.extend(self._get_audio_encode_args(bitrate=None))
            cmd.extend(self._get_output_optimization_args())
            cmd.extend([
                "-vf", "reverse",
                output_file
            ])

            print(f"🔄 Reversing video: {os.path.basename(video_path)} (audio: {'yes' if has_audio else 'no'})")
            self.run_ffmpeg_command(cmd)
            print(f"✅ Video reversed successfully: {output_file}")
            return output_file
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg Error reversing video: {e.stderr}")
    


    def _extend_and_standardize_video(self, input_video_path, extension_duration, output_path):
        try:
            # Get input video properties
            input_duration = self.get_duration(input_video_path)
            width, height = self.get_resolution(input_video_path)
            
            # Build ffmpeg command with tpad filter to extend
            # tpad adds padding at the end by repeating the last frame
            cmd = self._ffmpeg_input_args(input_video_path)
            
            # Add audio parameters if video has audio
            if self.has_audio_stream(input_video_path):
                cmd.extend([
                    # Extend audio with silence to match video
                    "-af", f"apad=pad_dur={extension_duration:.5f}",
                ])
                cmd.extend(self._get_audio_encode_args())
            
            # Add standard output parameters
            cmd.extend(self._get_video_output_args(keyframe_interval=True))
            cmd.extend(self._get_output_optimization_args())
            cmd.extend([
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,tpad=stop_mode=clone:stop_duration={extension_duration:.3f}",
                output_path
            ])
            
            # Execute command
            result = self.run_ffmpeg_command(cmd)
            
            if result.returncode != 0:
                print(f"❌ Extension failed: {result.stderr[:500]}")
                print(f"{' '.join(cmd)}")
                return False
            
            # Verify output
            if not os.path.exists(output_path):
                print(f"❌ Output file not created")
                return False
            
            output_duration = self.get_duration(output_path)
            expected_duration = input_duration + extension_duration
            
            # Allow some tolerance for rounding
            if abs(output_duration - expected_duration) > 0.2:
                print(f"⚠️ Duration mismatch: got {output_duration:.2f}s, expected {expected_duration:.2f}s")
                # Don't fail, but warn
            
            return True
            
        except Exception as e:
            print(f"❌ Error in _extend_and_standardize_video: {str(e)}")
            return False


    def extend_video_to_duration(self, input_video_path, target_duration, output_video_path):
        """
        Extend video to target duration by:
        1. Adding 1 second of the first frame at the beginning
        2. If still need more duration, extend the end with the last frame (but 1 second less than before)
        
        EFFECT-PRESERVING VERSION: Uses copy operations instead of filters
        """
        try:
            # Get the duration of the input video
            input_duration = self.get_duration(input_video_path)
            
            if input_duration > target_duration:
                raise ValueError(f"Input video duration ({input_duration:.2f}s) is longer than target duration ({target_duration:.2f}s)")
            
            # Calculate total extension needed
            total_extension_needed = target_duration - input_duration
            
            if abs(total_extension_needed) < 0.1:  # If extension needed is very small (within 0.1s)
                # Just copy the file if extension is minimal
                shutil.copy2(input_video_path, output_video_path)
                return True
            
            print(f"🎬 Extending video (EFFECT-PRESERVING): {input_duration:.2f}s → {target_duration:.2f}s")
            
            # Verify input video resolution before proceeding
            vid_width, vid_height = self.get_resolution(input_video_path)
            if not vid_width or not vid_height:
                print(f"⚠️  Warning: Could not detect resolution of {input_video_path}, proceeding with defaults")
            else:
                print(f"📐 Input video resolution: {vid_width}x{vid_height}")
            
            # EFFECT-PRESERVING APPROACH: Create extension segments and concatenate using demuxer
            return self._extend_video_effect_preserving(input_video_path, target_duration, output_video_path, total_extension_needed)
            
        except Exception as e:
            print(f"Error extending video: {str(e)}")
            return False


    def _extend_video_effect_preserving(self, input_video_path, target_duration, output_video_path, extension_needed):
        """
        Extend video while preserving effects using segment concatenation
        Simple approach: just extend at the end with last frame
        """
        temp_files = []
        
        try:
            os.makedirs(self.temp_dir, exist_ok=True)
            
            # Simplified approach: just extend at the end with the needed duration
            print(f"   🔧 Creating {extension_needed:.2f}s extension from last frame...")
            
            # Step 1: Extract last frame as image
            temp_last_image = os.path.join(self.temp_dir, f"last_frame_{hash(input_video_path) % 100000}.png")
            temp_files.append(temp_last_image)
            
            # Extract the actual last frame using a more robust approach
            # First get the video duration, then seek to a safe position near the end
            video_duration = self.get_duration(input_video_path)
            safe_seek_time = max(0, video_duration - 0.1)  # 0.1s from end, but not negative
            
            extract_cmd = self._ffmpeg_input_args(input_video_path)
            extract_cmd.extend([
                "-ss", str(safe_seek_time),  # Seek to 0.1s from end
                "-vframes", "1",      # Extract 1 frame
                "-q:v", "2",          # High quality
                "-update", "1",       # Update mode for single frame
                temp_last_image
            ])
            result = self.run_ffmpeg_command(extract_cmd)
            if result.returncode != 0:
                print(f"❌ Last frame extraction failed!")
                print(f"   Command: {' '.join(extract_cmd)}")
                print(f"   Stderr: {result.stderr}")
                print(f"   Input video: {input_video_path}")
                return False
            
            # Verify image was created
            if not os.path.exists(temp_last_image):
                print(f"❌ Last frame image was not created: {temp_last_image}")
                return False
            
            # Step 2: Create extension video from last frame
            temp_extension_video = os.path.join(self.temp_dir, f"extension_{hash(input_video_path) % 100000}.mp4")
            temp_files.append(temp_extension_video)
            
            # Ensure extension duration is valid (minimum 0.1 seconds)
            actual_extension_duration = max(0.1, extension_needed)
            
            # Create extension video with same properties as input
            # Detect input video resolution for encoder selection
            vid_width, vid_height = self.get_resolution(input_video_path)
            if vid_width and vid_height:
                print(f"🎬 Input video resolution: {vid_width}x{vid_height}")
            else:
                # Fallback to default resolution if detection fails
                vid_width, vid_height = self.width, self.height
                print(f"⚠️  Could not detect video resolution, using default: {vid_width}x{vid_height}")
            
            extension_cmd = self._ffmpeg_input_args(temp_last_image)
            extension_cmd.extend(self._get_video_output_args())
            extension_cmd.extend(self._get_output_optimization_args())
            extension_cmd.extend([
                "-loop", "1",
                "-t", f"{actual_extension_duration:.3f}",
                "-vf", f"scale={vid_width}:{vid_height}:force_original_aspect_ratio=decrease,pad={vid_width}:{vid_height}:(ow-iw)/2:(oh-ih)/2:black",
                temp_extension_video
            ])
            
            print(f"   🎬 Creating extension video ({actual_extension_duration:.3f}s) with resolution {vid_width}x{vid_height}...")
            result = self.run_ffmpeg_command(extension_cmd)
            if result.returncode != 0:
                print(f"❌ Extension video creation failed!")
                print(f"   Command: {' '.join(extension_cmd)}")
                print(f"   Stderr: {result.stderr}")
                print(f"   Extension duration: {actual_extension_duration:.3f}s")
                print(f"   Target resolution: {vid_width}x{vid_height}")
                return False
            
            # Verify extension video was created
            if not os.path.exists(temp_extension_video):
                print(f"❌ Extension video was not created: {temp_extension_video}")
                return False
            
            # Step 3: Concatenate original + extension using demuxer
            concat_list_file = os.path.join(self.temp_dir, f"concat_list_{hash(input_video_path) % 100000}.txt")
            temp_files.append(concat_list_file)
            
            # Create concat list with absolute paths and proper escaping
            with open(concat_list_file, 'w', encoding='utf-8') as f:
                # Use forward slashes for cross-platform compatibility
                original_path = os.path.abspath(input_video_path).replace('\\', '/')
                extension_path = os.path.abspath(temp_extension_video).replace('\\', '/')
                f.write(f"file '{original_path}'\n")
                f.write(f"file '{extension_path}'\n")
            
            print(f"   🔗 Concatenating original + extension with re-encoding for consistency...")
            
            # Always re-encode to ensure consistency with other clips
            if True:
                # Re-encode with matching parameters
                concat_cmd_encode = self._ffmpeg_input_args(concat_list_file)
                concat_cmd_encode.extend(self._get_video_output_args(keyframe_interval=False))
                concat_cmd_encode.extend(self._get_output_optimization_args())
                concat_cmd_encode.extend([
                    "-f", "concat",
                    "-safe", "0",
                    output_video_path
                ])
                result = self.run_ffmpeg_command(concat_cmd_encode)
                if result.returncode != 0:
                    print(f"❌ Re-encode concat failed: {result.stderr}")
                    return False
            
            # Verify output video was created and has reasonable duration
            if not os.path.exists(output_video_path):
                print(f"❌ Output video was not created: {output_video_path}")
                return False
            
            final_duration = self.get_duration(output_video_path)
            if final_duration <= 0:
                print(f"❌ Output video has invalid duration: {final_duration}")
                return False
            
            # Verify duration is close to target (allow 0.2s tolerance for frame alignment)
            duration_diff = abs(final_duration - target_duration)
            if duration_diff > 0.2:  # More strict: only 0.2s tolerance
                print(f"❌ Extension failed: Final duration ({final_duration:.3f}s) differs from target ({target_duration:.3f}s) by {duration_diff:.3f}s")
                print(f"   This usually indicates codec mismatch in concat operation")
                # Don't cleanup - keep files for debugging
                return False
            
            # Cleanup temp files only on success
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as cleanup_error:
                    print(f"⚠️ Failed to cleanup temp file {temp_file}: {cleanup_error}")
            
            print(f"   ✅ Video extended successfully: {final_duration:.3f}s")
            return True
            
        except Exception as e:
            print(f"❌ Error in effect-preserving extension: {str(e)}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            # Cleanup on failure
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
            return False



    def resize_image_smart(self, input_image, width=None, height=None):
        if width is None:
            width = self.width
        if height is None:
            height = self.height

        output_image = config.get_temp_file(self.pid, "webp")

        from PIL import Image
        input_width, input_height = self.get_resolution(input_image)

        with Image.open(input_image) as img:
            # WEBP格式支持RGB和RGBA模式，只转换不支持的模式
            if img.mode not in ('RGB', 'RGBA'):
                # 对于LA模式（灰度+透明），转换为RGBA以保留透明信息
                if img.mode == 'LA':
                    img = img.convert('RGBA')
                else:
                    # 其他模式（如P模式、灰度图等）转换为RGB
                    img = img.convert('RGB')
            
            # 计算宽高比
            input_ratio = input_width / input_height
            target_ratio = width / height
            
            # 如果宽高比基本相同（误差小于1%），直接缩放
            if abs(input_ratio - target_ratio) < 0.01:
                img = img.resize((width, height), Image.Resampling.LANCZOS)
            else:
                # 宽高比不同，需要智能裁剪
                if input_ratio > target_ratio:
                    # 输入图像更宽，裁剪左右两侧，保留中间部分
                    new_width = int(input_height * target_ratio)
                    left = (input_width - new_width) // 2
                    img = img.crop((left, 0, left + new_width, input_height))
                else:
                    # 输入图像更高，裁剪上下两侧，保留中间部分
                    new_height = int(input_width / target_ratio)
                    top = (input_height - new_height) // 2
                    img = img.crop((0, top, input_width, top + new_height))
                
                # 裁剪后缩放到目标尺寸
                img = img.resize((width, height), Image.Resampling.LANCZOS)
            
            img.save(output_image, 'WEBP', quality=90, method=6)

        return output_image



    def countLineLength(self, line):
        sections = line.split(' ')
        total_length = 0
        
        for section in sections:
            if self.is_all_english(section):
                total_length += max(1, int(len(section) / 3))
            else:
                total_length += len(section)
        
        return total_length


    def is_all_english(self, text):
        if not text:
            return True
        return all(ord(char) < 128 for char in text)


    def add_script_to_video(self, input_video_path, content, font):
        position = "footer"
        font_size = 90
        if content.lower().startswith("h_"):
            position = "header"
            content = content[2:]   
        elif content.lower().startswith("b_"):
            position = "body"
            content = content[2:]
        elif content.lower().startswith("f_"):
            position = "footer"
            content = content[2:]
        elif content.lower().startswith("hm_"):
            position = "header"
            content = content[3:]
        elif content.lower().startswith("bm_"):
            position = "body"
            content = content[3:]
        elif content.lower().startswith("fm_"):
            position = "footer"
            content = content[3:]
        elif content.lower().startswith("hl_"):
            font_size = 150
            position = "header"
            content = content[2:]   
        elif content.lower().startswith("bl_"):
            font_size = 150
            position = "body"
            content = content[3:]
        elif content.lower().startswith("fl_"):
            font_size = 150
            position = "footer"
            content = content[3:]
        elif content.lower().startswith("hs_"):
            position = "header"
            font_size = 40
            content = content[3:]
        elif content.lower().startswith("bs_"):
            position = "body"
            font_size = 40
            content = content[3:]
        elif content.lower().startswith("fs_"):
            position = "footer"
            font_size = 40
            content = content[3:]

        content = content.replace("\r", "")
        total_length = len(content)
        lines = content.split("\n")
        
        start_pos = 0.0
        for line in lines:
            line_length = self.countLineLength(line)
            # separate the line by the space, if section is english, count length like : length = charaters / 3

            font_s = font_size
            if line_length > 20:
                font_s -= 20
            elif line_length > 15:
                font_s -= 15
            elif line_length > 10:
                font_s -= 10
            elif line_length > 6:
                font_s -= 5

            end_pos = start_pos + line_length / total_length
            if end_pos > 1.0:
                end_pos = 1.0
            input_video_path = self.add_title_to_video(input_video_path, line, font, font_s, (start_pos, end_pos), position)
            start_pos = end_pos

        return input_video_path



    def add_title_to_video(self, input_video_path, title, font, font_size, title_show_portion=(0.01, 0.99), position="header"):
        output_file = config.get_temp_file(self.pid, "mp4")
        
        lines = title.split("_")
        if len(lines) == 2:
            font_size = font_size - 15
        elif len(lines) == 3:
            font_size = font_size - 25
        elif len(lines) > 3:
            font_size = font_size - 35

        try:
            # Get video duration and dimensions
            video_duration = self.get_duration(input_video_path)
            video_width, video_height = self.check_video_size(input_video_path)
            
            if video_width == 0 or video_height == 0:
                # Fallback to default dimensions
                video_width, video_height = self.width, self.height
                print(f"⚠️  Could not detect video resolution, using default: {video_width}x{video_height}")
            
            print(f"🎬 Adding title to video: {video_width}x{video_height}, Duration: {video_duration:.2f}s")
            
            # Calculate fade times based on title_show_portion parameter
            start_portion, end_portion = title_show_portion
            fadein_start = start_portion * video_duration
            fadein_end = end_portion * video_duration
            
            # Calculate fade duration dynamically based on show duration (max 0.5s or 5% of show duration)
            show_duration = fadein_end - fadein_start
            fade_duration = min(0.5, show_duration * 0.05)  # Use 5% of show duration or max 0.5s
            fade_duration = max(0.1, fade_duration)  # Minimum 0.1s for smooth fade
            
            # Calculate actual fade start and end times
            fade_in_end_time = fadein_start + fade_duration
            fade_out_start_time = fadein_end - fade_duration
            
            print(f"   Title show portion: {start_portion:.2f} - {end_portion:.2f} ({show_duration:.2f}s)")
            print(f"   Fade duration: {fade_duration:.2f}s")
            print(f"   Fade in: {fadein_start:.2f}s - {fade_in_end_time:.2f}s")
            print(f"   Full display: {fade_in_end_time:.2f}s - {fade_out_start_time:.2f}s")
            print(f"   Fade out: {fade_out_start_time:.2f}s - {fadein_end:.2f}s")
            
            # Calculate available text width for wrapping based on video dimensions
            aspect_ratio = video_width / video_height
            if aspect_ratio < 1.0:
                available_width = int(video_width * 0.92)  # 90% of width for narrow screens
                #font_size = int(font_size * 0.7)
            else:
                available_width = int(video_width * 0.85)  # 75% of width for wider screens
            
            # Calculate text wrapping with language-aware character width estimation
            script_type, estimated_char_width = self._detect_script_and_estimate_char_width(title, font_size)
            chars_per_line = max(4, int(available_width / estimated_char_width))
            title = title.replace('#',' ')
            wrapped_title = self._wrap_text(title, chars_per_line)
            
            print(f"   Original title: '{title}'")
            print(f"   Wrapped title: '{wrapped_title}'")
            
            # 使用完整路径的中文字体文件
            font_path = os.path.abspath(font["path"]).replace('\\', '\\\\').replace(':', '\\:')
            
            # 创建临时文本文件以避免FFmpeg文本转义问题，使用wrapped文本
            text_file_path = config.get_temp_file(self.pid, f"txt_{self.pid}.txt")
            with open(text_file_path, "w", encoding="utf-8") as f:
                f.write(wrapped_title)
            
            escaped_text_file_path = text_file_path.replace('\\', '\\\\').replace(':', '\\:')
            
            # Set text position based on position parameter and aspect ratio
            position_lower = position.lower()
            if position_lower == "header":
                # Header position - top of video
                if aspect_ratio < 1.0:
                    text_y_pos = int(video_height * 0.06)  # Position text higher in portrait mode
                else:
                    text_y_pos = int(video_height * 0.12)  # Position text at 14% from top
            elif position_lower == "body":
                # Body position - center of video
                text_y_pos = "(h-text_h)/2"  # Center vertically
            elif position_lower == "footer":
                # Footer position - bottom of video
                if aspect_ratio < 1.0:
                    text_y_pos = f"h-text_h-{int(video_height * 0.06)}"  # 8% from bottom in portrait mode
                else:
                    text_y_pos = f"h-text_h-{int(video_height * 0.09)}"  # 14% from bottom in landscape mode
            else:
                # Default to header if position not recognized
                print(f"⚠️  Unrecognized position '{position}', using header position")
                if aspect_ratio < 1.0:
                    text_y_pos = int(video_height * 0.08)
                else:
                    text_y_pos = int(video_height * 0.14)
            
            # Calculate line spacing reduction for multi-line text
            # More aggressive reduction for portrait mode (9:16) to save vertical space
            if aspect_ratio < 1.0:
                # Portrait mode: reduce by 70% of font size for tighter spacing
                line_spacing_reduction = -int(font_size * 0.7)
            else:
                # Landscape mode: reduce by 50% of font size
                line_spacing_reduction = -int(font_size * 0.5)
            
            # Check if input video has audio
            has_audio = self.has_audio_stream(input_video_path)
            
            # Build drawtext filter for title overlay with fade effects and line spacing
            drawtext_filter = (
                f"drawtext=fontfile='{font_path}':textfile='{escaped_text_file_path}':"
                f"fontcolor=white:fontsize={font_size}:"
                f"line_spacing={line_spacing_reduction}:"  # Reduce spacing between lines
                f"x=(w-text_w)/2:y={text_y_pos}:"
                f"enable='between(t,{fadein_start},{fadein_end})':"
                f"alpha='if(lt(t,{fade_in_end_time}),(t-{fadein_start})/{fade_duration},"
                f"if(lt(t,{fade_out_start_time}),1,1-(t-{fade_out_start_time})/{fade_duration}))'"
            )
            
            spacing_percentage = 70 if aspect_ratio < 1.0 else 50
            print(f"📝 Line spacing reduced by {-line_spacing_reduction}px ({spacing_percentage}% of font size {font_size}px for {'portrait' if aspect_ratio < 1.0 else 'landscape'} mode)")
            
            cmd = self._ffmpeg_input_args(input_video_path)
            cmd.extend(self._get_video_output_args())
            # Handle audio - re-encode to ensure consistency
            if has_audio:
                cmd.extend(self._get_audio_encode_args())
            cmd.extend(self._get_output_optimization_args())
            cmd.extend([
                "-vf", drawtext_filter,
                output_file
            ])
            
            self.run_ffmpeg_command(cmd)
            
            print(f"✅ Title successfully added to video at {position} position: {output_file}")
            # Clean up temporary text file
            if os.path.exists(text_file_path):
                os.remove(text_file_path)
                
        except Exception as e:
            print(f"❌ Error adding title to video: {e}")
            # Clean up temporary text file on error
            text_file_path = os.path.join(self.temp_dir, "txt_title.txt")
            if os.path.exists(text_file_path):
                os.remove(text_file_path)
        
        return output_file


    def add_title_to_image(self, input_image_path, title, font, font_size, position, text_color, bold):
        output_file = config.get_temp_file(self.pid, "png")
        
        try:
            # Use default font if none specified
            if font is None:
                font = self.font_title
            
            # Get image dimensions
            img_width, img_height = self.get_resolution(input_image_path)
            
            if img_width is None or img_height is None:
                raise ValueError(f"Could not detect image dimensions for: {input_image_path}")
            
            print(f"🖼️  Adding title to image: {img_width}x{img_height}")
            
            # Auto-calculate font size if not provided
            if font_size is None:
                # Base font size on image dimensions - larger images get bigger text
                base_size = min(img_width, img_height)
                font_size = max(16, int(base_size / 25))  # Minimum 16px, scale with image size
                print(f"📝 Auto-calculated font size: {font_size}px")
            
            # Calculate available text width based on position (leave generous margins)
            # Use much more conservative approach to ensure text fits
            if position.lower() in ["top-left", "bottom-left", "top-right", "bottom-right"]:
                available_width = int(img_width * 0.8)  # 80% of image width for corner positions
            else:
                available_width = int(img_width * 0.75)  # 75% of image width for center positions to be safe
            
            # Wrap text with language-aware character width estimation
            script_type, estimated_char_width = self._detect_script_and_estimate_char_width(title, font_size)
            chars_per_line = max(4, int(available_width / estimated_char_width))
            wrapped_title = self._wrap_text(title, chars_per_line)
            
            # Prepare font path with proper escaping
            font_path = os.path.abspath(font["path"]).replace('\\', '\\\\').replace(':', '\\:')
            
            # Create temporary text file with wrapped text
            text_file_path = os.path.join(self.temp_dir, f"txt_{self.pid}.txt")
            with open(text_file_path, "w", encoding="utf-8") as f:
                f.write(wrapped_title)
            
            escaped_text_file_path = text_file_path.replace('\\', '\\\\').replace(':', '\\:')
            
            # Calculate text position based on position parameter
            if position.lower() == "center":
                x_pos = "(w-text_w)/2"
                y_pos = "(h-text_h)/2"
            elif position.lower() == "top":
                x_pos = "(w-text_w)/2"
                y_pos = f"{int(img_height * 0.1)}"  # 10% from top
            elif position.lower() == "bottom":
                x_pos = "(w-text_w)/2"
                y_pos = f"h-text_h-{int(img_height * 0.1)}"  # 10% from bottom, accounting for text height
            elif position.lower() == "top-left":
                x_pos = f"{int(img_width * 0.05)}"   # 5% from left
                y_pos = f"{int(img_height * 0.1)}"   # 10% from top
            elif position.lower() == "top-right":
                x_pos = f"w-text_w-{int(img_width * 0.05)}"  # 5% from right, accounting for text width
                y_pos = f"{int(img_height * 0.1)}"           # 10% from top
            elif position.lower() == "bottom-left":
                x_pos = f"{int(img_width * 0.05)}"              # 5% from left
                y_pos = f"h-text_h-{int(img_height * 0.1)}"     # 10% from bottom, accounting for text height
            elif position.lower() == "bottom-right":
                x_pos = f"w-text_w-{int(img_width * 0.05)}"     # 5% from right, accounting for text width
                y_pos = f"h-text_h-{int(img_height * 0.1)}"     # 10% from bottom, accounting for text height
            else:
                # Default to center if position not recognized
                x_pos = "(w-text_w)/2"
                y_pos = "(h-text_h)/2"
                print(f"⚠️  Unrecognized position '{position}', using center")
            
            # Build drawtext filter for title overlay with text wrapping support and tight line spacing
            # Reduce line spacing by 50% of font size to make lines much closer
            line_spacing_reduction = -int(font_size * 0.5)  # Negative value reduces default spacing
            
            # Add bold effect by drawing the text multiple times with slight offsets
            if bold:
                # Create multiple drawtext filters with small offsets for bold effect
                # Scale offset with font size but cap it for very large fonts
                bold_offset = min(3, max(1, int(font_size * 0.02)))  # Reduced from 0.03 to 0.02 and capped at 3
                drawtext_filters = []
                
                # Reduce the number of offset copies for large fonts
                # Use diagonal offsets only to maintain bold effect with fewer filters
                offsets = [(-bold_offset, -bold_offset), 
                         (bold_offset, -bold_offset),
                         (-bold_offset, bold_offset),
                         (bold_offset, bold_offset)]
                
                # Add the offset copies
                for x_offset, y_offset in offsets:
                    offset_x = f"({x_pos}+{x_offset})"
                    offset_y = f"({y_pos}+{y_offset})"
                    
                    filter_str = (
                        f"drawtext=fontfile='{font_path}':textfile='{escaped_text_file_path}':"
                        f"fontcolor={text_color}:fontsize={font_size}:"
                        f"line_spacing={line_spacing_reduction}:"
                        f"x={offset_x}:y={offset_y}:"
                        f"box=1:boxcolor=0x664d00@0.2:boxborderw=3"
                    )
                    drawtext_filters.append(filter_str)
                
                # Add the center text last
                drawtext_filters.append(
                    f"drawtext=fontfile='{font_path}':textfile='{escaped_text_file_path}':"
                    f"fontcolor={text_color}:fontsize={font_size}:"
                    f"line_spacing={line_spacing_reduction}:"
                    f"x={x_pos}:y={y_pos}:"
                    f"box=1:boxcolor=0x664d00@0.2:boxborderw=3"
                )
                
                # Combine all filters
                drawtext_filter = ','.join(drawtext_filters)
                
            else:
                # Original non-bold filter
                drawtext_filter = (
                    f"drawtext=fontfile='{font_path}':textfile='{escaped_text_file_path}':"
                    f"fontcolor={text_color}:fontsize={font_size}:"
                    f"line_spacing={line_spacing_reduction}:"
                    f"x={x_pos}:y={y_pos}:"
                    f"box=1:boxcolor=0x664d00@0.2:boxborderw=3"
                )
            
            print(f"📝 Line spacing reduced by {-line_spacing_reduction}px (50% of font size {font_size}px)")
            if bold:
                print(f"📝 Bold effect enabled with {bold_offset}px offset")
            
            # Build FFmpeg command
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", input_image_path,
                "-vf", drawtext_filter,
                "-q:v", "2",  # High quality for images
                output_file
            ]
            
            self.run_ffmpeg_command(cmd)
            
            print(f"✅ Title successfully added to image: {output_file}")
            print(f"   📝 Text: '{wrapped_title}' at position '{position}' with font size {font_size}px")
            
            # Clean up temporary text file
            if os.path.exists(text_file_path):
                os.remove(text_file_path)
                
            return output_file
                
        except Exception as e:
            print(f"❌ Error adding title to image: {e}")
            # Clean up temporary text file on error
            text_file_path = os.path.join(self.temp_dir, f"txt_{self.pid}.txt")
            if os.path.exists(text_file_path):
                os.remove(text_file_path)
            return None


    def _detect_script_and_estimate_char_width(self, text, font_size):
        # Count characters by script type
        cjk_count = 0
        latin_count = 0
        arabic_count = 0
        thai_count = 0
        other_count = 0
        
        for char in text:
            if char.isspace():
                continue
                
            # Get Unicode script information
            try:
                script_name = unicodedata.name(char, '').upper()
                
                # CJK characters (Chinese, Japanese, Korean)
                if ('CJK' in script_name or 
                    'CHINESE' in script_name or 
                    'JAPANESE' in script_name or 
                    'KOREAN' in script_name or
                    '\u4e00' <= char <= '\u9fff' or  # CJK Unified Ideographs
                    '\u3400' <= char <= '\u4dbf' or  # CJK Extension A
                    '\u3040' <= char <= '\u309f' or  # Hiragana
                    '\u30a0' <= char <= '\u30ff'):   # Katakana
                    cjk_count += 1
                    
                # Arabic characters
                elif ('ARABIC' in script_name or 
                      '\u0600' <= char <= '\u06ff' or  # Arabic block
                      '\u0750' <= char <= '\u077f'):   # Arabic Supplement
                    arabic_count += 1
                    
                # Thai characters
                elif ('THAI' in script_name or 
                      '\u0e00' <= char <= '\u0e7f'):   # Thai block
                    thai_count += 1
                    
                # Latin characters (English, European languages)
                elif ('LATIN' in script_name or 
                      char.isascii() or
                      '\u0000' <= char <= '\u007f' or  # Basic Latin
                      '\u0080' <= char <= '\u00ff' or  # Latin-1 Supplement
                      '\u0100' <= char <= '\u017f' or  # Latin Extended-A
                      '\u0180' <= char <= '\u024f'):   # Latin Extended-B
                    latin_count += 1
                    
                else:
                    other_count += 1
                    
            except:
                # If we can't determine the script, assume it's other
                other_count += 1
        
        total_chars = cjk_count + latin_count + arabic_count + thai_count + other_count
        
        if total_chars == 0:
            return "latin", font_size * 0.6  # Default fallback
        
        # Determine primary script based on highest count
        script_counts = {
            'cjk': cjk_count,
            'latin': latin_count, 
            'arabic': arabic_count,
            'thai': thai_count,
            'other': other_count
        }
        
        primary_script = max(script_counts, key=script_counts.get)
        
        # Estimate character width based on primary script
        if primary_script == 'cjk':
            # CJK characters are typically full-width (close to font size)
            estimated_width = font_size * 1.1
        elif primary_script == 'latin':
            # Latin characters are typically half-width or less
            estimated_width = font_size * 0.5  # More conservative for English
        elif primary_script == 'arabic':
            # Arabic characters vary but are generally narrower than CJK
            estimated_width = font_size * 0.85
        elif primary_script == 'thai':
            # Thai characters are typically narrower than CJK
            estimated_width = font_size * 0.6
        else:
            # Default for other scripts
            estimated_width = font_size * 1.1
        
        print(f"📝 Script analysis: CJK={cjk_count}, Latin={latin_count}, Arabic={arabic_count}, Thai={thai_count}, Other={other_count}")
        print(f"📝 Primary script: {primary_script}, Estimated char width: {estimated_width:.1f}px (font size: {font_size}px)")
        
        return primary_script, estimated_width


    def _wrap_text(self, text, max_chars_per_line):
        # First normalize different newline types to a consistent format
        # Handle both Windows (\r\n) and Unix (\n) newlines
        normalized_text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Split by newlines first to preserve original line structure
        original_lines = normalized_text.split('\n')
        all_processed_lines = []
        
        for line in original_lines:
            # Process each original line separately
            if not line.strip():  # Empty line - preserve it
                all_processed_lines.append("")
                continue
                
            # Split by underscores to create forced line breaks within this line
            segments = line.split('_')
            line_result = []
            
            for i, segment in enumerate(segments):
                # Skip empty segments (except the first one which might be intentionally empty)
                if not segment and i > 0:
                    continue
                    
                words = segment.split()
                current_line = ""
                
                for word in words:
                    # Check if adding this word would exceed the line limit
                    test_line = current_line + (" " if current_line else "") + word
                    
                    if len(test_line) <= max_chars_per_line:
                        current_line = test_line
                    else:
                        # If current line is not empty, finish it and start a new line
                        if current_line:
                            line_result.append(current_line)
                            current_line = word
                        else:
                            # Word itself is longer than max_chars_per_line, force break it
                            if len(word) > max_chars_per_line:
                                # Split long word
                                while len(word) > max_chars_per_line:
                                    line_result.append(word[:max_chars_per_line])
                                    word = word[max_chars_per_line:]
                                if word:
                                    current_line = word
                            else:
                                current_line = word
                
                # Add the last line of this segment if it exists
                if current_line:
                    line_result.append(current_line)
            
            # Add all processed lines from this original line
            all_processed_lines.extend(line_result)
        
        return "\n".join(all_processed_lines)  # Use actual newlines for text file


    def adjust_video_to_duration(self, input_video_path, target_duration):
        output_video_path = config.get_temp_file(self.pid, "mp4")

        segment_duration = self.get_duration(input_video_path)
        if target_duration <= 0.0 or abs(segment_duration - target_duration) < 0.1:
            os.replace(input_video_path, output_video_path)
            return output_video_path
        elif segment_duration > target_duration:
            new_clip_v = self.trim_video(input_video_path, 0, target_duration)
            os.replace(new_clip_v, output_video_path)
            return output_video_path

        try:
            speed_factor = segment_duration / target_duration
            print(f"🎬 Adjusting video speed, speed factor: {speed_factor:.3f}x")
            # Get original video framerate
            result = self.run_ffmpeg_command([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                input_video_path
            ])
            
            fps_fraction = result.stdout.strip()
            if '/' in fps_fraction:
                num, den = fps_fraction.split('/')
                original_fps = float(num) / float(den)
            else:
                original_fps = float(fps_fraction)
            
            if original_fps <= 0:
                original_fps = -original_fps
            
            setpts_multiplier = 1.0 / speed_factor
            video_filter = f"setpts={setpts_multiplier}*PTS,fps={original_fps}"
            
            cmd = self._ffmpeg_input_args(input_video_path)
            cmd.extend(self._get_audio_encode_args(bitrate=None))
            cmd.extend(self._get_video_output_args(keyframe_interval=False))
            cmd.extend([
                "-vf", video_filter,
                output_video_path
            ])
            
            # 打印完整的FFmpeg命令用于调试
            print(f"🔧 FFmpeg command: {' '.join(cmd)}")
            self.run_ffmpeg_command(cmd)
            return output_video_path
            
        except Exception as e:
            print(f"❌ Speed adjustment failed: {str(e)}")
            return input_video_path


    def add_subtitle(self, output_path, video_path, subtitle_path, font, font_size):
        subtitle_path = subtitle_path.replace("/", "\\")
        # 获取字体目录的绝对路径
        font_file_path = os.path.abspath(self.font_video["path"])
        font_dir = os.path.dirname(font_file_path)
        
        print(f"📝 字幕处理信息:")
        print(f"  字体名称: {font['name']}")
        print(f"  字体目录: {font_dir}")
        print(f"  字幕文件路径: {subtitle_path}")
        print(f"  字幕文件是否存在: {os.path.exists(subtitle_path)}")
        
        # 使用你之前工作的方法，但做适当的路径转义
        subtitle_path = subtitle_path.replace('\\', '\\\\').replace(':', '\\:')
        font_dir_escaped = font_dir.replace('\\', '\\\\').replace(':', '\\:')
        
        print(f"🔄 使用转义后的路径:")
        print(f"  字幕路径: {subtitle_path}")
        print(f"  字体目录: {font_dir_escaped}")
        
        try:
            # 使用你之前工作的滤镜格式
            vf_filter = (
                f"subtitles='{subtitle_path}':"
                f"fontsdir='{font_dir_escaped}':"
                f"force_style='FontName={font['name']},FontSize={font_size}'"
            )
            
            print(f"   滤镜: {vf_filter}")
            
            cmd = self._ffmpeg_input_args(video_path)
            cmd.extend(self._get_video_output_args())
            cmd.extend(self._get_audio_encode_args(bitrate=None))
            cmd.extend(self._get_output_optimization_args())
            cmd.extend([
                "-hwaccel", "cuda",
                "-vf", vf_filter,
                output_path
            ])
            self.run_ffmpeg_command(cmd)
            print(f"✅ 字幕添加成功: {output_path}")
            return
            
        except subprocess.CalledProcessError as e:
            print(f"❌ 字幕添加失败: {e.stderr}")
            return


    def add_picture_in_picture(self, background_video, slide_in_video, start_time=0, ratio=0.333, transition_duration=1.0, position="right", mask=None, edge_blur=20):
        try:
            # 计算小视频的尺寸，确保为偶数（FFmpeg要求）
            slide_in_width, slide_in_height = self.get_resolution(background_video)
            slide_in_width = int(slide_in_width * ratio)
            slide_in_height = int(slide_in_height * ratio)
            if slide_in_width % 2 != 0:
                slide_in_width -= 1
            if slide_in_height % 2 != 0:
                slide_in_height -= 1
            resized_video = self.resize_video(slide_in_video, width=slide_in_width, height=slide_in_height)
            
            # 添加淡入淡出效果和形状遮罩
            if transition_duration > 0:
                resized_video = self.video_fade(resized_video, transition_duration, transition_duration, False)
            
            # 生成输出文件路径
            output_path = config.get_temp_file(self.pid, "mp4")
            
            # 获取视频时长信息
            slide_in_duration = self.get_duration(slide_in_video)
            background_duration = self.get_duration(background_video)
            
            # 计算叠加位置
            if position == "right":
                # 右下角，距离边缘20像素
                overlay_position = f"W-w-20:H-h-20"
            elif position == "left":
                # 左下角，距离边缘20像素
                overlay_position = f"20:H-h-20"
            elif position == "center":
                # 中心位置
                overlay_position = f"(W-w)/2:(H-h)/2"
            else:
                # 默认右下角
                overlay_position = f"W-w-20:H-h-20"
            
            # 构建滤镜链
            filter_complex_parts = []
            
            # 计算PiP的结束时间
            pip_end_time = start_time + slide_in_duration
            
            # 确保PiP不超过背景视频的长度
            if pip_end_time > background_duration:
                pip_end_time = background_duration
                print(f"⚠️ PiP视频将在背景视频结束时停止 (背景时长: {background_duration}s)")
            
            # 处理PiP视频时间同步 - 关键修复
            # 使用setpts来延迟PiP视频的开始时间，让它与背景视频的时间轴同步
            pip_delay_filter = f"[1:v]setpts=PTS+{start_time}/TB[pip_delayed]"
            filter_complex_parts.append(pip_delay_filter)
            
            # 添加边缘虚化效果
            # 创建alpha遮罩：从边缘向内渐变
            edge_blur_size = edge_blur  # 边缘虚化的像素大小（可通过参数配置）
            
            # 使用geq滤镜创建边缘渐变遮罩
            # 计算每个像素到边缘的最小距离，然后根据距离设置alpha值
            # 使用 yuva444p 格式（全分辨率色度）避免边缘色彩失真
            edge_fade_filter = (
                f"[pip_delayed]format=yuva444p,"
                f"geq=lum='lum(X,Y)':"
                f"cb='cb(X,Y)':"
                f"cr='cr(X,Y)':"
                f"a='if(lt(X,{edge_blur_size}),255*X/{edge_blur_size},"
                f"if(lt(Y,{edge_blur_size}),255*Y/{edge_blur_size},"
                f"if(gt(X,W-{edge_blur_size}),255*(W-X)/{edge_blur_size},"
                f"if(gt(Y,H-{edge_blur_size}),255*(H-Y)/{edge_blur_size},255))))'[pip_edge_faded]"
            )
            filter_complex_parts.append(edge_fade_filter)
            
            # PiP视频已经添加了边缘虚化效果
            overlay_input = "[pip_edge_faded]"
            
            # 添加叠加滤镜 - 添加时间控制来防止静态图像残留
            enable_condition = f"between(t,{start_time},{pip_end_time})"
            filter_complex_parts.append(
                f"[0:v]{overlay_input}overlay={overlay_position}:enable='{enable_condition}'"
            )
            
            # 组合完整的滤镜链
            filter_complex = ";".join(filter_complex_parts)
            
            # 构建完整的ffmpeg命令
            cmd = self._ffmpeg_input_args(background_video, resized_video)
            cmd.extend(self._get_audio_encode_args())  # 音频重新编码以确保格式一致
            cmd.extend(self._get_video_output_args(keyframe_interval=False))
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "0:a",   # 使用背景视频的音频
                output_path
            ])
            
            print(f"🎬 开始添加画中画效果...")
            print(f"📍 开始时间: {start_time}s, 结束时间: {pip_end_time}s")
            print(f"✨ 边缘虚化: {edge_blur_size}像素")
            print(f"🔧 FFmpeg命令: {' '.join(cmd)}")
            
            # 执行ffmpeg命令
            result = self.run_ffmpeg_command(cmd)
            print(f"----------\n{' '.join(cmd)}\n------------")
            if result.returncode == 0:
                print(f"✅ 画中画添加成功: {output_path}")
                return output_path
            else:
                print(f"❌ 画中画添加失败: {result.stderr}")
                return None

        except Exception as e:
            print(f"❌ 画中画添加出错: {e}")
            return None
    
    

    # ffmpeg -ss 00:00:01 -to 00:00:50 -i %1 -c:v libx264 -c:a aac %~n1_.mp4
    def split_video(self, original_clip, position):
        first = self.trim_video( original_clip, start_time=0, end_time=position)
        second = self.trim_video( original_clip, start_time=position)
        return first, second



    def _combine_left_right_videos(self, left_video_path: str, right_video_path: str, output_video_path: str, quality: int = 18) -> bool:
        """Combine left and right videos into a single video horizontally with smart audio handling"""
        try:
            left_has_audio = self.has_audio_stream(left_video_path)
            right_has_audio = self.has_audio_stream(right_video_path)
            
            # Build ffmpeg command based on audio situation
            if not left_has_audio and not right_has_audio:
                cmd = f'ffmpeg -y -i "{left_video_path}" -i "{right_video_path}" -filter_complex "[0:v][1:v]hstack=inputs=2:shortest=1[v]" -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 18 "{output_video_path}"'
                
            elif left_has_audio and not right_has_audio:
                cmd = f'ffmpeg -y -i "{left_video_path}" -i "{right_video_path}" -filter_complex "[0:v][1:v]hstack=inputs=2:shortest=1[v]" -map "[v]" -map "0:a" -c:v libx264 -c:a aac -pix_fmt yuv420p -crf {quality} "{output_video_path}"'
                
            elif not left_has_audio and right_has_audio:
                cmd = f'ffmpeg -y -i "{left_video_path}" -i "{right_video_path}" -filter_complex "[0:v][1:v]hstack=inputs=2:shortest=1[v]" -map "[v]" -map "1:a" -c:v libx264 -c:a aac -pix_fmt yuv420p -crf {quality} "{output_video_path}"'
                
            else:
                cmd = f'ffmpeg -y -i "{left_video_path}" -i "{right_video_path}" -filter_complex "[0:v][1:v]hstack=inputs=2:shortest=1[v];[0:a][1:a]amix=inputs=2:duration=shortest:dropout_transition=2:normalize=0[a]" -map "[v]" -map "[a]" -c:v libx264 -c:a aac -pix_fmt yuv420p -crf {quality} "{output_video_path}"'
            
            result = self.run_ffmpeg_command(cmd)
            print("Video combination completed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Video combination failed, command: {cmd}")
            return False
        except Exception as e:
            print(f"Unexpected error combining left and right videos: {e}")
            return False

