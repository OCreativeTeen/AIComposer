import os
import subprocess
import shutil
from pathlib import Path

from mpmath import rational
from config import ffmpeg_path, ffprobe_path, FONT_0, FONT_1, FONT_2, FONT_4, FONT_6, FONT_7, FONT_8
import config
from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.file_util import copy_file
import random
import unicodedata


class FfmpegProcessor:
    # Standardized framerate to prevent sync issues
    STANDARD_FPS = 60
    STANDARD_AUDIO_RATE = 44100
    STANDARD_AUDIO_CHANNELS = 2
    
    # NVENC limitations
    NVENC_MAX_WIDTH = 4096
    NVENC_MAX_HEIGHT = 4096
    NVENC_MAX_PIXELS = 8192 * 8192  # Maximum total pixels


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
            self.font_video = FONT_2
            self.font_size = 16
            self.font_title = FONT_8
        else:
            self.font_video = FONT_4
            self.font_size = 16
            self.font_title = FONT_0
        
        # 验证并修复字体路径
        self._validate_and_fix_font_path()


    def _is_nvenc_compatible(self, width=None, height=None):
        """Check if the given resolution is compatible with NVENC hardware encoder."""
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        
        # Check individual dimension limits
        if width > self.NVENC_MAX_WIDTH or height > self.NVENC_MAX_HEIGHT:
            return False
        
        # Check total pixel count
        if width * height > self.NVENC_MAX_PIXELS:
            return False
        
        return True

    def _check_nvenc_availability(self):
        """Check if NVENC encoder is available in the current FFmpeg build."""
        try:
            cmd = [self.ffmpeg_path, "-encoders"]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            return "h264_nvenc" in result.stdout
        except Exception as e:
            print(f"⚠️  Could not check NVENC availability: {e}")
            return False


    def _get_encoder_config(self, width=None, height=None):
        """Get encoder configuration based on resolution compatibility."""
        if self._is_nvenc_compatible(width, height) and self._check_nvenc_availability():
            return {
                "codec": "h264_nvenc",
                "preset": "fast",
                "quality": ["-cq", "18"],  # Use CQ for NVENC
                "hwaccel": ["-hwaccel", "cuda"]  # Specify GPU device
                #"hwaccel": ["-hwaccel_device", "0", "-hwaccel", "cuda"]  # Specify GPU device
            }
        else:
            if not self._check_nvenc_availability():
                print(f"⚠️  NVENC encoder not available in FFmpeg build, using software encoding")
            else:
                print(f"⚠️  Resolution {width or self.width}x{height or self.height} exceeds NVENC limits, falling back to software encoding")
            return {
                "codec": "libx264",
                "preset": "medium",
                "quality": ["-crf", "18"],  # Use CRF for x264
                "hwaccel": []  # No hardware acceleration for software encoding
            }


    def _get_input_args(self, width=None, height=None):
        """Get input arguments (like hardware acceleration) based on resolution."""
        config = self._get_encoder_config(width, height)
        return config["hwaccel"]


    def _get_output_args(self, width=None, height=None):
        """Get output arguments (codec, preset, quality) based on resolution."""
        config = self._get_encoder_config(width, height)
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
            fps = self.STANDARD_FPS
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        return f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}"


    def _get_simple_scale_filter(self, width=None, height=None, fps=None):
        """Generate simple scale filter string without padding but with standardized fps"""
        if fps is None:
            fps = self.STANDARD_FPS
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        return f"scale={width}:{height},fps={fps}"
   
    def _get_standardized_output_params(self):
        """
        Get standardized output parameters for video/audio encoding.
        These parameters ensure consistent output that can be concatenated without issues.
        
        Returns:
            List of FFmpeg arguments for standardized output
        """
        return [
            "-c:a", "aac",  # Audio codec
            "-b:a", "192k",  # Audio bitrate
            "-ac", str(self.STANDARD_AUDIO_CHANNELS),  # Audio channels
            "-ar", str(self.STANDARD_AUDIO_RATE),  # Audio sample rate
            "-r", str(self.STANDARD_FPS),  # Fixed frame rate
            "-pix_fmt", "yuv420p",  # Pixel format for compatibility
            "-g", str(self.STANDARD_FPS),  # GOP size (keyframe interval)
            "-keyint_min", str(self.STANDARD_FPS),  # Minimum keyframe interval
            "-sc_threshold", "0",  # Disable scene detection
            "-movflags", "+faststart",  # Optimize for streaming
            "-avoid_negative_ts", "make_zero",  # Avoid negative timestamps
            "-fflags", "+genpts",  # Regenerate timestamps
        ]
   

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
        
        # 如果没有找到有效路径，输出警告
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
            # Get dynamic encoder configuration
            input_args = self._get_input_args()
            output_args = self._get_output_args()
            
            cmd = [
                self.ffmpeg_path, "-y"
            ]
            cmd.extend(input_args)  # Add input args (like hwaccel)
            cmd.extend([
                "-i", input_path,
                "-vf", self._get_scale_filter()  # Add scaling to configured dimensions
            ])
            cmd.extend(output_args)  # Add output args (codec, preset, quality)
            cmd.extend([
                "-pix_fmt", "yuv420p",  # Pixel format for compatibility
                "-c:a", "aac",          # Audio codec
                "-b:a", "192k",         # Audio bitrate
                "-ac", "2",
                "-ar", "44100",
                "-r", str(self.STANDARD_FPS),  # Ensure consistent framerate
                "-movflags", "+faststart",
                output_path
            ])
            
            print(f"🔄 Converting to MP4 and resizing to {self.width}x{self.height}: {input_path}")
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            print(f"✅ Successfully converted and resized: {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg Error converting to MP4: {e.stderr}")

        return output_path


    def repeat_video_match_audio(self, video_path, audio_path):
        """if the video is longer than the audio, direct call video_audio_mix with match_audio_length=True"""
        """ else repeat the video to match the audio duration (final repeat need to cut to match the audio duration)"""
        
        try:
            # Get durations of both video and audio
            video_duration = self.get_duration(video_path)
            audio_duration = self.get_duration(audio_path)
            
            print(f"🎬 Video duration: {video_duration:.2f}s, Audio duration: {audio_duration:.2f}s")
            
            # Generate output path
            output_path = config.get_temp_file(self.pid, "mp4")
            
            if video_duration >= audio_duration:
                # Video is longer than or equal to audio, just mix directly
                print(f"🎬 Video is longer/equal, mixing directly with match_audio_length=True")
                return self.video_audio_mix(video_path, audio_path, volume=1.0, match_audio_length=True)
            else:
                # Video is shorter than audio, need to repeat the video
                print(f"🔄 Video is shorter, repeating video to match audio duration")
                
                # Calculate how many times we need to repeat the video
                repeat_count = int(audio_duration / video_duration) + 1  # +1 to ensure we have enough
                print(f"   Repeating video {repeat_count} times to cover {audio_duration:.2f}s")
                
                # Create a list of video segments for concatenation
                # Use the format expected by concat_videos method
                video_segments = []
                for i in range(repeat_count):
                    video_segments.append({
                        "path": video_path,
                        "transition": "fade" if i > 0 else "none",  # No transition for first video
                        "duration": 0.5 if i > 0 else 0.0  # Short transition for subsequent videos
                    })
                
                # Concatenate the repeated videos
                print(f"   📹 Concatenating {repeat_count} video copies...")
                repeated_video_path = self.concat_videos_demuxer(video_segments)
                
                if not repeated_video_path or not os.path.exists(repeated_video_path):
                    raise RuntimeError("Failed to create repeated video")
                
                # Verify the repeated video is long enough
                repeated_duration = self.get_duration(repeated_video_path)
                print(f"   ✅ Repeated video duration: {repeated_duration:.2f}s")
                
                if repeated_duration < audio_duration:
                    print(f"⚠️  Warning: Repeated video ({repeated_duration:.2f}s) is still shorter than audio ({audio_duration:.2f}s)")
                
                # Mix the repeated video with audio, cutting to match audio length exactly
                print(f"🎵 Mixing repeated video with audio (cutting to exact audio length)")
                return self.video_audio_mix(repeated_video_path, audio_path, volume=1.0, match_audio_length=True)
                
        except Exception as e:
            print(f"❌ Error in repeat_video_match_audio: {e}")
            return None


    # on top of the mp4 from base_video_path, 
    # if left_overlap is True, take the left half of the mp4 from second_video_path, to overlap the left half of the mp4 from base_video_path
    # if left_overlap is False, take the right half of the mp4 from second_video_path, to overlap the right half of the mp4 from base_video_path
    # audio only keep from base_video_path
    def overlap_half(self, base_video_path, second_video_path, left_overlap):
        """
        将第二个视频的左半部分或右半部分叠加到基础视频的对应位置
        
        Args:
            base_video_path: 基础视频路径
            second_video_path: 第二个视频路径（用作叠加层）
            left_overlap: True = 叠加左半部分，False = 叠加右半部分
            
        Returns:
            输出视频的路径
        """
        try:
            # 生成输出路径
            output_path = config.get_temp_file(self.pid, "mp4")
            
            # 获取基础视频的尺寸和时长
            base_width, base_height = self.get_resolution(base_video_path)
            base_duration = self.get_duration(base_video_path)
            
            # 获取第二个视频的尺寸
            second_width, second_height = self.get_resolution(second_video_path)
            
            if not all([base_width, base_height, second_width, second_height]):
                raise ValueError("无法获取视频尺寸信息")
            
            # 计算半宽
            half_width = base_width // 2
            
            # 构建滤镜链
            if left_overlap:
                # 叠加左半部分：从第二个视频裁剪左半部分，叠加到基础视频左半部分
                crop_filter = f"[1:v]scale={base_width}:{base_height},crop={half_width}:{base_height}:0:0[left_half]"
                overlay_filter = f"[0:v][left_half]overlay=0:0[vout]"
                position_desc = "左半部分"
            else:
                # 叠加右半部分：从第二个视频裁剪右半部分，叠加到基础视频右半部分
                crop_filter = f"[1:v]scale={base_width}:{base_height},crop={half_width}:{base_height}:{half_width}:0[right_half]"
                overlay_filter = f"[0:v][right_half]overlay={half_width}:0[vout]"
                position_desc = "右半部分"
            
            # 组合完整的滤镜链
            filter_complex = f"{crop_filter};{overlay_filter}"
            
            print(f"🎬 视频半屏叠加:")
            print(f"   基础视频: {base_width}x{base_height}")
            print(f"   叠加位置: {position_desc}")
            print(f"   输出尺寸: {base_width}x{base_height}")
            
            # 获取编码器配置
            encoder_config = self._get_encoder_config(base_width, base_height)
            
            # 构建FFmpeg命令
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", base_video_path,      # 输入0：基础视频
                "-i", second_video_path,    # 输入1：第二个视频
                "-filter_complex", filter_complex,
                "-map", "[vout]",           # 映射视频输出
                "-map", "0:a?",             # 只保留基础视频的音频
                "-c:a", "copy",             # 音频直接复制
                "-c:v", encoder_config["codec"]
            ]
            
            # 添加编码器特定参数
            if encoder_config["codec"] == "h264_nvenc":
                cmd.extend(["-preset", encoder_config["preset"]])
                cmd.extend(encoder_config["quality"])
            else:
                cmd.extend(["-preset", encoder_config["preset"], "-crf", "23"])
            
            # 添加其他参数
            cmd.extend([
                "-pix_fmt", "yuv420p",
                "-r", str(self.STANDARD_FPS),
                "-t", str(base_duration),   # 限制输出时长为基础视频时长
                output_path
            ])
            
            # 执行FFmpeg命令
            print(f"🔧 执行视频半屏叠加...")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            print(f"✅ 视频半屏叠加完成: {output_path}")
            return output_path
            
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg 半屏叠加失败: {e.stderr if e.stderr else str(e)}"
            print(f"❌ {error_msg}")
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"视频半屏叠加处理失败: {str(e)}"
            print(f"❌ {error_msg}")
            raise RuntimeError(error_msg)


    def refps_video(self, video_path, fps):
        try:
            output_path = config.get_temp_file(self.pid, "mp4")

            cmd = [
                self.ffmpeg_path,
                "-i", video_path,
                "-vf", "fps="+fps,
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "medium",
                "-c:a", "copy",
                output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error 1: {e.stderr}")


    def resize_video(self, video_path, width, height):
        try:
            crop_width, crop_height = self.get_resolution(video_path)
            x_y_ratio = (float(crop_width)/float(crop_height))

            if height is None and width is None:
                height = crop_height
                width = crop_width
            elif width is None:
                width = height * x_y_ratio
            elif height is None:
                height = crop_height / x_y_ratio

            need_scale = (crop_height != self.height or crop_width != self.width)
            
            output_path = config.get_temp_file(self.pid, "mp4")
            # Early exit if no changes needed
            if not need_scale:
                shutil.copy2(video_path, output_path)
                print(f"📋 No changes needed, copying file: {os.path.basename(video_path)}")
                return output_path
            
            # Build and execute FFmpeg command
            cmd = self._build_resize_command( video_path, output_path, crop_width, crop_height )
            
            print(f"🔧 Executing FFmpeg command for resize_video: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
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
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            return output_path
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg processing failed with exit code {e.returncode}: {e.stderr}")
            return None
        except Exception as e:
            print(f"❌ Error in trim_video: {e}")
            return None


    def _get_video_fps(self, video_path):
        """Get video FPS, returns None if unable to determine."""
        try:
            result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            fps_fraction = result.stdout.strip()
            if not fps_fraction:
                return None
                
            if '/' in fps_fraction:
                num, den = fps_fraction.split('/')
                fps = float(num) / float(den)
            else:
                fps = float(fps_fraction)
                
            return fps if fps > 0 else None
        except Exception as e:
            print(f"⚠️  Could not get input video FPS: {e}")
            return None


    def _build_resize_command(self, video_path, output_path, target_width, target_height):
        """Build FFmpeg command for video resizing."""
        cmd = [self.ffmpeg_path, "-y"]
        cmd.extend(self._get_input_args(None, None))
        cmd.extend(["-i", video_path])
        
        # Add video scaling filter
        cmd.extend(["-vf", f"scale={target_width}:{target_height}"])
        
        # Add video encoder configuration
        cmd.extend(["-c:v", "libx264"])
        
        cmd.extend(self._get_output_args(target_width, target_height))
        
        # Add audio configuration
        if self.has_audio_stream(video_path):
            cmd.extend(["-c:a", "copy"])
        
        # Add common output options
        cmd.extend([
            "-pix_fmt", "yuv420p",
        ])
        
        # Add frame rate if not using fps filter
        cmd.extend(["-r", str(self.STANDARD_FPS)])
        
        cmd.extend([
            "-sc_threshold", "0",
            "-vsync", "cfr",
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero",
            output_path
        ])
        
        return cmd


    def _build_trim_command(self, video_path, output_path, start_time, end_time, volume):
        cmd = [self.ffmpeg_path, "-y"]
        cmd.extend(self._get_input_args(None, None))
        cmd.extend(["-i", video_path])
        cmd.extend(["-ss", str(start_time), "-to", str(end_time)])
        cmd.extend(self._get_output_args(None, None))
        
        # Add audio configuration
        if self.has_audio_stream(video_path) and volume > 0.0:
            if volume != 1.0:
                cmd.extend(["-af", f"volume={volume}"])
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", str(self.STANDARD_AUDIO_RATE),
                "-ac", str(self.STANDARD_AUDIO_CHANNELS)
            ])
        
        # Add common output options
        cmd.extend([
            "-pix_fmt", "yuv420p",
            "-r", str(self.STANDARD_FPS),
            "-sc_threshold", "0",
            "-vsync", "cfr",
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero",
            output_path
        ])
        return cmd


    def image_audio_to_video(self, image_path, audio_path, animation_choice=1):
        # create video from image and audio, and save to video_path, keep full duration of audio
        # animation_choice: 1=still, 2=move left, 3=move right
        try:
            video_path = config.get_temp_file(self.pid, "mp4")

            img_width, img_height = self.get_resolution(image_path)
            
            # Get dynamic encoder configuration based on input image resolution
            input_args = self._get_input_args(img_width, img_height)
            output_args = self._get_output_args(img_width, img_height)
            
            # 根据动画选择构建视频滤镜
            vf_filter = self._build_animation_filter(animation_choice)
            
            cmd = [
                self.ffmpeg_path, "-y"
            ]
            cmd.extend(input_args)  # Add input args (like hwaccel)
            cmd.extend([
                "-loop", "1",
                "-i", image_path,
                "-i", audio_path,
                "-vf", vf_filter
            ])
            cmd.extend(output_args)  # Add output args (codec, preset, quality)
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-ac", str(self.STANDARD_AUDIO_CHANNELS),
                "-ar", str(self.STANDARD_AUDIO_RATE),
                "-pix_fmt", "yuv420p",  # Changed from yuva420p for better compatibility
                "-r", str(self.STANDARD_FPS),
                "-g", str(self.STANDARD_FPS),  # Keyframe interval
                "-keyint_min", str(self.STANDARD_FPS),
                "-sc_threshold", "0",
                "-shortest",  # Use shortest stream duration (audio duration)
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                "-vsync", "cfr",  # Constant frame rate to avoid timing issues
                video_path
            ])
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
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
                input_args = self._get_input_args()
                output_args = self._get_output_args()
                
                cmd = [
                    self.ffmpeg_path, "-y"
                ]
                cmd.extend(input_args)  # Add input args (like hwaccel)
                cmd.extend([
                    "-i", video_path,
                    "-i", audio_path
                ])
                
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
                
                cmd.extend(output_args)  # Add output args (codec, preset, quality)
                cmd.extend([
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ac", "2",
                    "-ar", "44100",
                    "-r", str(self.STANDARD_FPS),
                    "-pix_fmt", "yuv420p",
                    "-g", str(self.STANDARD_FPS),
                    "-keyint_min", str(self.STANDARD_FPS),
                    "-sc_threshold", "0",
                    "-shortest",
                    "-movflags", "+faststart",
                    "-avoid_negative_ts", "make_zero",
                    "-fflags", "+genpts",
                    output_path
                ])
            
                subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # Verify final duration
            final_duration = self.get_duration(output_path)
            print(f"✅ Video audio mix complete. Final duration: {final_duration:.2f}s")
            
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error 2: {e.stderr}")
            return None

        return output_path


    def to_webp(self, image_path):
        output_path = config.get_temp_file(self.pid, "webp")
        subprocess.run([
            self.ffmpeg_path, "-y",
            "-i", image_path,
            output_path
        ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
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
        video_filter = f"tpad=stop_duration={video_extend_duration}:stop_mode=clone"
        
        # Get dynamic encoder configuration
        input_args = self._get_input_args()
        output_args = self._get_output_args()
        
        cmd = [
            self.ffmpeg_path, "-y"
        ]
        cmd.extend(input_args)  # Add input args (like hwaccel)
        cmd.extend([
            "-i", video_path,
            "-i", audio_path,
            "-vf", video_filter,
            "-map", "0:v:0",
            "-map", "1:a:0"
        ])
        cmd.extend(output_args)  # Add output args (codec, preset, quality)
        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-ac", "2",
            "-ar", "44100",
            "-r", str(self.STANDARD_FPS),
            "-pix_fmt", "yuv420p",
            "-g", str(self.STANDARD_FPS),
            "-keyint_min", str(self.STANDARD_FPS),
            "-sc_threshold", "0",
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            output_path
        ])
        
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')


    def add_left_right_picture_in_picture(self, background_video, overlay_video_left, overlay_video_right, ratio, delay_time, edge_blur=20):
        """
        Add two overlay videos (left and right) on top of the background video.
        
        Args:
            background_video: Path to background video
            overlay_video_left: Path to left overlay video (optional, can be None)
            overlay_video_right: Path to right overlay video (optional, can be None)
            ratio: Scale ratio for overlay videos relative to background height
            delay_time: Delay in seconds before overlays appear (0 = no delay)
            edge_blur: Edge blur size in pixels for smooth blending (default: 20)
            
        Returns:
            Path to output video with picture-in-picture effect
            
        Features:
            - If both overlays are None, returns a copy of background video
            - If only left overlay is None, only adds right overlay
            - If only right overlay is None, only adds left overlay
            - Overlay videos are scaled based on ratio parameter of background height
            - Left overlay is positioned at bottom-left
            - Right overlay is positioned at bottom-right
            - Overlays appear after delay_time seconds
            - Output duration matches background video duration
            - Overlay edges are softly blurred for better visual blending
        """
        output_path = config.get_temp_file(self.pid, "mp4")
        
        # If both overlays are None, just copy the background video
        if overlay_video_left is None and overlay_video_right is None:
            input_args = self._get_input_args()
            output_args = self._get_output_args()
            cmd = [
                self.ffmpeg_path, "-y"
            ]
            cmd.extend(input_args)
            cmd.extend([
                "-i", background_video,
                "-c", "copy",
                output_path
            ])
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            return output_path
        
        # Get background video dimensions and duration
        bg_width, bg_height = self.get_resolution(background_video)
        bg_duration = self.get_duration(background_video)
        
        # Calculate target height for overlays
        overlay_height = int(bg_height * ratio)
        
        # Get dynamic encoder configuration
        input_args = self._get_input_args()
        output_args = self._get_output_args()
        
        cmd = [
            self.ffmpeg_path, "-y"
        ]
        cmd.extend(input_args)
        
        # Build input list and filter based on which overlays are present
        # IMPORTANT: Do NOT use fps filter in filter chain - it causes speed issues
        # Instead, use setpts for time adjustment and let output -r handle frame rate
        # This is the same approach used in add_169_video_to_916_background
        
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
                "-i", background_video,
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
                "-i", background_video,
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
                "-i", background_video,
                "-i", overlay_video_right,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-map", "0:a?",
            ])
        
        cmd.extend(output_args)
        # Use output parameters to handle frame rate conversion (not in filter chain)
        # This prevents speed issues and maintains proper sync
        cmd.extend([
            "-c:a", "aac",  # Audio codec
            "-b:a", "192k",  # Audio bitrate
            "-pix_fmt", "yuv420p",  # Pixel format for compatibility
            "-r", str(self.STANDARD_FPS),  # Output frame rate - handle fps conversion here
            "-t", str(bg_duration),  # CRITICAL: Limit output duration to background duration
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",  # Regenerate timestamps - critical for sync
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
        
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
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

            cmd = [
                self.ffmpeg_path, "-y",
                "-hwaccel", "cuda",
                "-i", video_path,
                "-i", audio_path,
                "-map", "0:v:0",  # use video stream
                "-map", "1:a:0",  # use new audio stream
                "-c:v", "copy",   # copy video, no re-encode
                "-c:a", "aac",    # re-encode audio only
                "-b:a", "192k",
                "-ac", "2",
                "-ar", "44100",
                "-t", str(video_duration),  # 明确指定输出时长等于音频时长
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                temp_file
            ]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # 检查生成的文件时长
            output_duration = self.get_duration(temp_file)
            print(f"🎬 生成文件时长: {output_duration:.2f}s (预期: 音频={audio_duration:.2f}s)")

        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error adding audio to video: {e.stderr}")

        return temp_file


    def has_audio_stream(self, video_path):
        """检测视频文件是否包含音频轨道"""
        try:
            result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                video_path
            ], capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # 如果命令执行成功且输出包含"audio"，则认为有音频流
            has_audio = result.returncode == 0 and result.stdout.strip() == "audio"
            print(f"音频检测 - 文件: {video_path}, 有音频: {has_audio}, 输出: '{result.stdout.strip()}', 错误码: {result.returncode}")
            return has_audio
        except Exception as e:
            print(f"音频检测异常 - 文件: {video_path}, 错误: {e}")
            return False

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
                
                cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", str(self.STANDARD_AUDIO_RATE), "-ac", str(self.STANDARD_AUDIO_CHANNELS)])
            
            # 使用标准的 H.264 编码，输出为 MP4 (不支持 alpha 通道)
            cmd.extend([
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "medium",
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                output_path
            ])

            print(f"🔧 FFmpeg命令: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
                    
                    cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", str(self.STANDARD_AUDIO_RATE), "-ac", str(self.STANDARD_AUDIO_CHANNELS)])
                else:
                    # 保持原始音频不变 - 不应用任何淡入淡出效果
                    cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", str(self.STANDARD_AUDIO_RATE), "-ac", str(self.STANDARD_AUDIO_CHANNELS)])
            
            # Use qtrle codec which supports alpha channel, in a .mov container
            cmd.extend([
                "-c:v", "qtrle",
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                output_path
            ])

            print(f"🔧 FFmpeg命令: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
            width_result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # Get height
            height_result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=height",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
        """
        Concatenate videos with transitions while preserving permanent effects
        
        VIDEO/AUDIO SYNC LOGIC:
        - video_segments[i]["duration"] = transition duration TO video i (from previous video)
        - Each video i is extended by video_segments[i+1]["duration"] (transition to NEXT video)
        - Last video is NOT extended (no next transition)
        - Audio from each video is trimmed by the SAME extension amount to maintain sync
        - Result: Audio and video are perfectly aligned throughout the entire output
        
        Example with 3 videos:
          Video 0: extended by T1 (transition to Video 1), audio keeps original length
          Video 1: extended by T2 (transition to Video 2), audio keeps original length  
          Video 2: not extended (last), audio keeps original length
        """
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
                video_filters.append(f"[{i}:v]fps={self.STANDARD_FPS}:round=near,{self._get_simple_scale_filter(self.width, self.height)}[v{i}]")
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
                        audio_filters.append(f"[{i}:a]aresample={self.STANDARD_AUDIO_RATE},aformat=sample_fmts=fltp:sample_rates={self.STANDARD_AUDIO_RATE}:channel_layouts=stereo,atrim=0:{audio_to_keep:.3f},asetpts=PTS-STARTPTS[a{i}]")
                    else:
                        # Video has no audio - create silent audio for trimmed duration
                        audio_filters.append(f"anullsrc=channel_layout=stereo:sample_rate={self.STANDARD_AUDIO_RATE}:duration={audio_to_keep:.3f}[a{i}]")
                    
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
                cmd.extend([
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ac", str(self.STANDARD_AUDIO_CHANNELS),
                    "-ar", str(self.STANDARD_AUDIO_RATE)
                ])
            
            # Use software encoding for complex filter operations to avoid hardware encoder issues
            # Hardware encoders can have problems with very long filter chains
            use_software_encoder = n_videos > 10  # Use software for >10 videos
            
            if use_software_encoder:
                print(f"      📝 Using software encoder (libx264) for {n_videos} videos to ensure stability")
                cmd.extend([
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "20",
                    "-r", str(self.STANDARD_FPS),
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", 
                    "-avoid_negative_ts", "make_zero",
                    "-fflags", "+genpts", 
                    video_out_path
                ])
            else:
                cmd.extend([
                    # HIGH QUALITY encoding to preserve baked effects
                    "-c:v", "h264_nvenc",
                    "-preset", "fast",
                    "-crf", "20",
                    "-r", str(self.STANDARD_FPS),
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", 
                    "-avoid_negative_ts", "make_zero",
                    "-fflags", "+genpts", 
                    video_out_path
                ])
            
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
            
            result = subprocess.run(cmd, check=False, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
            
            print(f"   📐 Duration analysis:")
            print(f"      Total input duration: {total_original_duration:.2f}s")
            print(f"      Total transitions: {total_transition_duration:.2f}s")
            print(f"      Expected output: {expected_duration:.2f}s")
            print(f"      Actual output: {final_duration:.2f}s")
            
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
            
        except subprocess.CalledProcessError as e:
            # Cleanup temporary files before raising
            for temp_file in temp_files_to_cleanup:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            print(f"❌ FFmpeg transition concatenation failed!")
            print(f"❌ Return code: {e.returncode}")
            print(f"❌ Stderr: {e.stderr}")
            print(f"❌ Stdout: {e.stdout}")
            raise RuntimeError(f"FFmpeg transition concatenation failed: {e.stderr}") from e
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
            result = subprocess.run(probe_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
            left_result = subprocess.run(left_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            right_result = subprocess.run(right_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            return left_image, right_image
            
        except Exception as e:
            print(f"❌ Error splitting image: {str(e)}")
            return None, None


    def concat_videos(self, video_paths, keep_audio):
        if len(video_paths) == 0:
            return None

        video_out_path = config.get_temp_file(self.pid, "mp4")
        if len(video_paths) == 1:
            copy_file(video_paths[0], video_out_path)
            return video_out_path
        
        try:
            concat_file_path = os.path.join(self.temp_dir, "chunk_concat_list.txt")
            with open(concat_file_path, "w", encoding="utf-8") as f:
                for video_path in video_paths:
                    abs_path = os.path.abspath(video_path).replace("\\", "/")
                    f.write(f"file '{abs_path}'\n")
            
            # build ffmpeg concat command
            concat_cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file_path,
                "-c", "copy"  # copy both audio & video
            ]

            if not keep_audio:
                concat_cmd.append("-an")  # drop audio completely

            concat_cmd.extend([
                "-movflags", "+faststart",
                video_out_path
            ])
            
            print(f"🔨 Executing FFmpeg concat command...")
            result = subprocess.run(concat_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
                "-c", "copy"  # Copy codec to preserve quality and avoid re-encoding
            ]
            
            # Handle audio based on availability and settings
            if not keep_audio_if_has:
                concat_cmd.append("-an")  # Remove audio stream
            
            concat_cmd.extend([
                "-movflags", "+faststart",
                video_out_path
            ])
            
            print(f"🔨 Executing FFmpeg concat command...")
            result = subprocess.run(concat_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
            result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filename
                ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
            return 0.0
        except Exception as e:
            print(f"FFmpeg Error: {e}")
            return 0.0


    def get_resolution(self, filename):
        """Get the resolution (width, height) of an image or video file"""
        try:
            result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filename
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
        subprocess.run([
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-vf", "hflip",
            "-c:v", "h264_nvenc",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-an",  # No audio
            "-movflags", "+faststart",
            output_file
        ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        print(f"✅ Video mirrored successfully: {output_file}")
        return output_file


    def reverse_video(self, video_path):
        output_file = config.get_temp_file(self.pid, "mp4")
        
        # Check if video has audio stream
        has_audio = self.has_audio_stream(video_path)
        
        try:
            if has_audio:
                # Video has audio - reverse only video, keep audio original
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", video_path,
                    "-vf", "reverse",
                    "-c:v", "h264_nvenc",
                    "-preset", "fast",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-movflags", "+faststart",
                    output_file
                ]
            else:
                # Video has no audio - reverse only video
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", video_path,
                    "-vf", "reverse",
                    "-c:v", "h264_nvenc",
                    "-preset", "fast",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-an",  # No audio
                    "-movflags", "+faststart",
                    output_file
                ]
            
            print(f"🔄 Reversing video: {os.path.basename(video_path)} (audio: {'yes' if has_audio else 'no'})")
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            print(f"✅ Video reversed successfully: {output_file}")
            return output_file
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg Error reversing video: {e.stderr}")
            # Fallback: try without audio reverse if the first attempt failed
            try:
                print(f"🔄 Fallback: Trying video-only reverse...")
                cmd_fallback = [
                    self.ffmpeg_path, "-y",
                    "-i", video_path,
                    "-vf", "reverse",
                    "-c:v", "h264_nvenc",
                    "-preset", "fast",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-an",  # No audio
                    "-movflags", "+faststart",
                    output_file
                ]
                subprocess.run(cmd_fallback, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                print(f"✅ Video reversed successfully (fallback): {output_file}")
                return output_file
            except subprocess.CalledProcessError as e2:
                print(f"❌ Fallback also failed: {e2.stderr}")
                raise RuntimeError(f"Failed to reverse video: {e2.stderr}") from e2
    

    def add_169_video_to_916_background(self, background_916_video, video_169, from_top_portion, fade=False, video_start_time=0.0):
        if fade:
            video_169 = self.video_fade(video_169, 2.0, 2.0, False)

        output_file = config.get_temp_file(self.pid, "mp4")
        
        """将16:9视频添加到9:16背景视频的顶部位置"""
        # Get duration of the upper video
        duration_upper_video = self.get_duration(video_169)
        duration_background_video = self.get_duration(background_916_video)
        
        # Calculate when the overlay should end (either when upper video ends or background ends)
        video_play_end_time = min(video_start_time + duration_upper_video, duration_background_video)
        
        # For 9:16 background video, calculate overlay dimensions
        # Background video width (for 9:16, this is the smaller dimension)
        bg_width, bg_height = self.check_video_size(background_916_video)
        if bg_width == 0 or bg_height == 0:
            # Fallback to default 9:16 dimensions if detection fails
            bg_width = 607  # Default 9:16 width from scroll_image method
            bg_height = 1080  # Default 9:16 height
        
        # Upper video overlay dimensions: width = bg_width, height = bg_width * 9/16 (to maintain 16:9 aspect)
        overlay_width = bg_width
        overlay_height = int(bg_width * 9 / 16)
        
        # Calculate vertical position based on from_top_portion
        overlay_x = 0  # Left aligned
        overlay_y = int(bg_height * from_top_portion)  # Position based on from_top_portion
        
        # Ensure overlay doesn't exceed background boundaries
        max_y = bg_height - overlay_height
        if overlay_y > max_y:
            overlay_y = max_y
            print(f"⚠️  Overlay position adjusted to fit within background: y={overlay_y}")
        elif overlay_y < 0:
            overlay_y = 0
            print(f"⚠️  Overlay position adjusted to non-negative: y={overlay_y}")
        
        print(f"🎬 Adding upper video overlay:")
        print(f"   Background: {bg_width}x{bg_height} (9:16)")
        print(f"   Overlay: {overlay_width}x{overlay_height} (16:9)")
        print(f"   Position: x={overlay_x}, y={overlay_y} ({from_top_portion*100:.1f}% from top)")
        print(f"   Duration: {video_start_time:.2f}s - {video_play_end_time:.2f}s")
        
        # Build video filter
        video_filter_part = (
            f"[1:v]scale={overlay_width}:{overlay_height},"
            f"setpts=PTS-STARTPTS+{video_start_time}/TB[fg_video];"
            f"[0:v][fg_video]overlay=x={overlay_x}:y={overlay_y}:enable='between(t,{video_start_time},{video_play_end_time})'[vout]"
        )

        # Check if upper video has audio and build audio filter accordingly
        has_upper_audio = self.has_audio_stream(video_169)
        has_background_audio = self.has_audio_stream(background_916_video)
        
        if has_upper_audio and has_background_audio:
            # Both videos have audio - mix them
            audio_filter_part = (
                f"[0:a]volume=0.7[bg_audio];"  # Lower background audio slightly
                f"[1:a]adelay={int(video_start_time*1000)}|{int(video_start_time*1000)},volume=1.0[delayed_upper_audio];"
                f"[bg_audio][delayed_upper_audio]amix=inputs=2:duration=longest:dropout_transition=0,volume=1.0[aout]"
            )
            audio_map = ["-map", "[aout]"]
        elif has_background_audio:
            # Only background has audio
            audio_filter_part = f"[0:a]volume=1.0[aout]"
            audio_map = ["-map", "[aout]"]
        elif has_upper_audio:
            # Only upper video has audio (delayed to match video start time)
            audio_filter_part = f"[1:a]adelay={int(video_start_time*1000)}|{int(video_start_time*1000)},volume=1.0[aout]"
            audio_map = ["-map", "[aout]"]
        else:
            # No audio in either video
            audio_filter_part = ""
            audio_map = []
        
        # Combine video and audio filters
        if audio_filter_part:
            overlay_filter = f"{video_filter_part};{audio_filter_part}"
        else:
            overlay_filter = video_filter_part
        
        try:
            # Get dynamic encoder configuration
            # Note: For complex filter operations, we avoid hardware decoding acceleration
            # but keep hardware encoding if compatible
            output_args = self._get_output_args()
            
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", background_916_video,
                "-i", video_169,
                "-filter_complex", overlay_filter,
                "-map", "[vout]"
            ]
            
            # Add audio mapping if needed
            cmd.extend(audio_map)
            
            # Add output encoding arguments
            cmd.extend(output_args)  # Add output args (codec, preset, quality)
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                output_file
            ])
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            print(f"✅ Successfully added upper video overlay: {output_file}")

        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg Error adding upper video: {e}")
            print(f"❌ FFmpeg stderr: {e.stderr}")

        return output_file


    def _extend_and_standardize_video(self, input_video_path, extension_duration, output_path):
        try:
            # Get input video properties
            input_duration = self.get_duration(input_video_path)
            width, height = self.get_resolution(input_video_path)
            
            # Get encoder configuration
            input_args = self._get_input_args(width, height)
            output_args = self._get_output_args(width, height)
            
            # Build ffmpeg command with tpad filter to extend
            # tpad adds padding at the end by repeating the last frame
            cmd = [
                self.ffmpeg_path, "-y"
            ]
            cmd.extend(input_args)
            cmd.extend([
                "-i", input_video_path,
                # Video filter: scale to target size, then extend with last frame
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,tpad=stop_mode=clone:stop_duration={extension_duration:.3f}"
            ])
            cmd.extend(output_args)
            
            # Add audio parameters if video has audio
            if self.has_audio_stream(input_video_path):
                cmd.extend([
                    # Extend audio with silence to match video
                    "-af", f"apad=pad_dur={extension_duration:.5f}",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", str(self.STANDARD_AUDIO_RATE),
                    "-ac", str(self.STANDARD_AUDIO_CHANNELS)
                ])
            
            # Add standard output parameters
            cmd.extend([
                "-pix_fmt", "yuv420p",
                "-r", str(self.STANDARD_FPS),
                "-g", str(self.STANDARD_FPS),
                "-keyint_min", str(self.STANDARD_FPS),
                "-sc_threshold", "0",
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                output_path
            ])
            
            # Execute command
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            if result.returncode != 0:
                print(f"❌ Extension failed: {result.stderr[:500]}")
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

    def extend_video(self, input_video_path, offset):
        output_video_path = config.get_temp_file(self.pid, "mp4")
        # extend the video for offset seconds, use the last frame to extend 
        # use self._extend_video_effect_preserving to extend the video
        if self._extend_video_effect_preserving(input_video_path, offset, output_video_path, offset):
            return output_video_path
        else:
            return input_video_path


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
            # Ensure temp directory exists
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
            
            extract_cmd = [
                self.ffmpeg_path, "-y",
                "-ss", str(safe_seek_time),  # Seek to 0.1s from end
                "-i", input_video_path,
                "-vframes", "1",      # Extract 1 frame
                "-q:v", "2",          # High quality
                "-update", "1",       # Update mode for single frame
                temp_last_image
            ]
            
            print(f"   📸 Extracting last frame from {video_duration:.2f}s video at {safe_seek_time:.2f}s...")
            result = subprocess.run(extract_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
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
            
            # Get dynamic encoder configuration based on input video resolution
            input_args = self._get_input_args(vid_width, vid_height)
            output_args = self._get_output_args(vid_width, vid_height)
            
            extension_cmd = [
                self.ffmpeg_path, "-y"
            ]
            extension_cmd.extend(input_args)  # Add input args (like hwaccel)
            extension_cmd.extend([
                "-loop", "1",
                "-t", f"{actual_extension_duration:.3f}",  # Format to 3 decimal places
                "-i", temp_last_image,
                # Ensure the extension video has the exact same resolution as input
                "-vf", f"scale={vid_width}:{vid_height}:force_original_aspect_ratio=decrease,pad={vid_width}:{vid_height}:(ow-iw)/2:(oh-ih)/2:black"
            ])
            extension_cmd.extend(output_args)  # Add output args (codec, preset, quality)
            extension_cmd.extend([
                "-pix_fmt", "yuv420p",
                "-r", str(self.STANDARD_FPS),
                "-g", str(self.STANDARD_FPS),  # Keyframe interval
                "-avoid_negative_ts", "make_zero",
                temp_extension_video
            ])
            
            print(f"   🎬 Creating extension video ({actual_extension_duration:.3f}s) with resolution {vid_width}x{vid_height}...")
            result = subprocess.run(extension_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
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
            
            print(f"   🔗 Concatenating original + extension...")
            
            # Try copy first (faster if compatible), fall back to re-encode if it fails
            concat_cmd_copy = [
                self.ffmpeg_path, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_file,
                "-c", "copy",  # Try copy first
                "-avoid_negative_ts", "make_zero",
                output_video_path
            ]
            
            result = subprocess.run(concat_cmd_copy, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # If copy failed or result duration is wrong, try re-encoding
            needs_reencode = False
            if result.returncode != 0:
                print(f"   ⚠️  Copy concat failed, trying re-encode...")
                needs_reencode = True
            else:
                # Check if duration is correct
                temp_duration = self.get_duration(output_video_path)
                expected_duration = self.get_duration(input_video_path) + actual_extension_duration
                if abs(temp_duration - expected_duration) > 0.2:
                    print(f"   ⚠️  Copy concat produced wrong duration ({temp_duration:.2f}s vs {expected_duration:.2f}s), re-encoding...")
                    needs_reencode = True
            
            if needs_reencode:
                # Re-encode with matching parameters
                output_args_concat = self._get_output_args(vid_width, vid_height)
                concat_cmd_encode = [
                    self.ffmpeg_path, "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_list_file
                ]
                concat_cmd_encode.extend(output_args_concat)
                concat_cmd_encode.extend([
                    "-r", str(self.STANDARD_FPS),
                    "-pix_fmt", "yuv420p",
                    "-avoid_negative_ts", "make_zero",
                    "-fflags", "+genpts",
                    output_video_path
                ])
                
                result = subprocess.run(concat_cmd_encode, capture_output=True, text=True, encoding='utf-8', errors='ignore')
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
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg Error in effect-preserving extension: {e}")
            print(f"❌ FFmpeg stderr: {e.stderr}")
            # Cleanup on failure
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
            return False
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


    def scroll_image(self, image_path, duration, portion=0.2, direction="left_to_right"):
        output_video_path = config.get_temp_file(self.pid, "mp4")
        try:
            # 调试信息：检查 image_path 的类型和内容
            print(f"🔍 DEBUG: scroll_image called with image_path type: {type(image_path)}")
            print(f"🔍 DEBUG: image_path content: {image_path}")
            
            # 检查并处理 image_path 参数类型
            if isinstance(image_path, dict):
                # If a dict is passed, try to extract the path from common dict keys
                if 'path' in image_path:
                    actual_image_path = image_path['path']
                    print(f"🔧 Fixed: Extracted path from dict: {actual_image_path}")
                elif 'file_path' in image_path:
                    actual_image_path = image_path['file_path']
                    print(f"🔧 Fixed: Extracted file_path from dict: {actual_image_path}")
                elif 'url' in image_path:
                    actual_image_path = image_path['url']
                    print(f"🔧 Fixed: Extracted url from dict: {actual_image_path}")
                else:
                    raise ValueError(f"❌ 无效的image_path参数: 传入了字典但找不到有效的路径键。字典内容: {image_path}")
            elif isinstance(image_path, str):
                actual_image_path = image_path
            else:
                raise ValueError(f"❌ 无效的image_path参数类型: {type(image_path)}。应该是字符串路径或包含路径的字典。")
            
            # 确保图片文件存在
            if not os.path.exists(actual_image_path):
                raise FileNotFoundError(f"图片文件不存在: {actual_image_path}")
            
            display_width = 607
            display_height = 1080
            
            # 原始图片是 1920x1080，我们需要将其缩放以适应显示高度
            # 保持原始图片的宽高比，将高度缩放到显示高度
            scaled_width = 1920
            scaled_height = 1080
            
            # 根据滚动方向计算起始和结束位置
            if direction.lower() == "left_to_right":
                # 从左到右滚动
                start_x = int(portion * scaled_width)
                end_x = int((1 - portion) * scaled_width - display_width)
            elif direction.lower() == "right_to_left":
                # 从右到左滚动
                start_x = int((1 - portion) * scaled_width - display_width)
                end_x = int(portion * scaled_width)
            else:
                raise ValueError(f"不支持的滚动方向: {direction}. 请使用 'left_to_right' 或 'right_to_left'")
            
            # 确保位置不超出范围
            max_x = scaled_width - display_width
            start_x = max(0, min(start_x, max_x))
            end_x = max(0, min(end_x, max_x))
            
            # 计算滚动距离
            scroll_distance = end_x - start_x
            
            # 计算总帧数和滚动表达式 - 使用基于帧数的计算，避免时间精度问题
            total_frames = int(duration * self.STANDARD_FPS)
            # 使用帧号(n)而不是时间(t)，确保精确控制
            # 当帧数达到总帧数时锁定在end_x位置
            crop_x_expr = f"if(gte(n,{total_frames}),{end_x},{start_x}+({end_x}-{start_x})*n/{total_frames})"
            
            # 构建滤镜 - 移除scroll_distance检查，支持双向滚动
            if abs(scroll_distance) > 1:  # 只有在有明显滚动距离时才添加动画
                video_filter = (
                    f"scale={scaled_width}:{scaled_height},"
                    f"crop={display_width}:{display_height}:'{crop_x_expr}':0,"
                    f"fps={self.STANDARD_FPS}"
                )
                print(f"🎬 滚动动画: 从 x={start_x} 到 x={end_x} (距离: {scroll_distance}px)")
            else:
                # 滚动距离太小，使用静态裁剪
                video_filter = (
                    f"scale={scaled_width}:{scaled_height},"
                    f"crop={display_width}:{display_height}:{start_x}:0,"
                    f"fps={self.STANDARD_FPS}"
                )
                print(f"📐 静态裁剪: x={start_x} (滚动距离太小: {scroll_distance}px)")
            
            cmd = [
                self.ffmpeg_path, "-y",
                "-loop", "1",
                "-i", actual_image_path,  # 使用处理后的路径
                "-vf", video_filter,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-r", str(self.STANDARD_FPS),
                "-t", str(duration),  # 严格控制输出时长
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                output_video_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            print(f"✅ 滚动图片视频创建成功: {direction}")
            print(f"   📐 视口移动: {start_x}px → {end_x}px (距离: {scroll_distance}px)")
            print(f"   🎬 FFmpeg表达式: {crop_x_expr}")

        except Exception as e:
            print(f"❌ 创建滚动图片视频时发生错误: {e}")

        return output_video_path
    

    def effect_image_to_video(self, image_path, duration=1, mode="still"):
        output_video_path = config.get_temp_file(self.pid, "mp4")

        if duration < 1:
            duration = 1.0
            
        # Simple algorithm to calculate enlarge_ratio based on duration
        # Base ratio of 1.05, scaling up to 1.3 for durations 20+ seconds
        enlarge_ratio = min(1.28, 1.03 + (min(duration, 20) / 20) * 0.25)

        temp_effect_video = os.path.join(self.temp_dir, f"temp_effect_{hash(image_path) % 10000}.mp4")
        
        try:
            # Ensure image file exists
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            # Handle random mode selection
            if mode.lower() == "random":
                available_modes = ["left", "right", "up", "down", "zoom in", "zoom out"]
                mode = random.choice(available_modes)
                print(f"🎲 Random mode selected: {mode}")
            
            # Calculate enlarged dimensions
            enlarged_width = int(self.width * enlarge_ratio)
            enlarged_height = int(self.height * enlarge_ratio)
            
            # Build the appropriate filter based on mode
            if mode.lower() == "left":
                # Scroll from left to right
                crop_x_start = enlarged_width - self.width
                crop_x_end = 0
                crop_x_expr = f"if(gte(t,{duration}),{crop_x_end},{crop_x_start}+({crop_x_end}-{crop_x_start})*t/{duration})"
                video_filter = (
                    f"scale={enlarged_width}:{enlarged_height},"
                    f"crop={self.width}:{self.height}:'{crop_x_expr}':0,"
                    f"fps={self.STANDARD_FPS}"
                )
                
            elif mode.lower() == "right":
                # Scroll from right to left
                crop_x_start = 0
                crop_x_end = enlarged_width - self.width
                crop_x_expr = f"if(gte(t,{duration}),{crop_x_end},{crop_x_start}+({crop_x_end}-{crop_x_start})*t/{duration})"
                video_filter = (
                    f"scale={enlarged_width}:{enlarged_height},"
                    f"crop={self.width}:{self.height}:'{crop_x_expr}':0,"
                    f"fps={self.STANDARD_FPS}"
                )
            
            elif mode.lower() == "still":
                video_filter = (
                    f"scale={enlarged_width}:{enlarged_height},"
                    f"crop={self.width}:{self.height},"
                    f"fps={self.STANDARD_FPS}"
                )

            elif mode.lower() == "up":
                # Scroll from top to bottom
                crop_y_start = enlarged_height - self.height
                crop_y_end = 0
                crop_y_expr = f"if(gte(t,{duration}),{crop_y_end},{crop_y_start}+({crop_y_end}-{crop_y_start})*t/{duration})"
                video_filter = (
                    f"scale={enlarged_width}:{enlarged_height},"
                    f"crop={self.width}:{self.height}:0:'{crop_y_expr}',"
                    f"fps={self.STANDARD_FPS}"
                )
            
            elif mode.lower() == "down":
                # Scroll from bottom to top
                crop_y_start = 0
                crop_y_end = enlarged_height - self.height
                crop_y_expr = f"if(gte(t,{duration}),{crop_y_end},{crop_y_start}+({crop_y_end}-{crop_y_start})*t/{duration})"
                video_filter = (
                    f"scale={enlarged_width}:{enlarged_height},"
                    f"crop={self.width}:{self.height}:0:'{crop_y_expr}',"
                    f"fps={self.STANDARD_FPS}"
                )
            
            elif mode.lower() == "zoom in":
                # Simple zoom in effect
                print(f"🔍 Creating zoom in effect: {enlarge_ratio} → 1.0 over {duration}s")
                temp_large = os.path.join(self.temp_dir, f"zoom_large_{hash(image_path) % 10000}.mp4")
                temp_small = os.path.join(self.temp_dir, f"zoom_small_{hash(image_path) % 10000}.mp4")
                
                # Create large version (zoomed in start)
                large_scale = int(self.width * enlarge_ratio)
                subprocess.run([
                    self.ffmpeg_path, "-y", 
                    "-hwaccel", "cuda",
                    "-loop", "1", 
                    "-t", str(duration), 
                    "-i", image_path,
                    "-vf", f"scale={large_scale}:{int(self.height * enlarge_ratio)},crop={self.width}:{self.height}:(iw-{self.width})/2:(ih-{self.height})/2,fps={self.STANDARD_FPS}",
                    "-c:v", "h264_nvenc", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", temp_large
                ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                # Create normal version (zoomed in end)
                subprocess.run([
                    self.ffmpeg_path, "-y", 
                    "-hwaccel", "cuda",
                    "-loop", "1", 
                    "-t", str(duration), 
                    "-i", image_path,
                    "-vf", f"scale={self.width}:{self.height},fps={self.STANDARD_FPS}",
                    "-c:v", "h264_nvenc", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", temp_small
                ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                # Blend between them
                subprocess.run([
                    self.ffmpeg_path, "-y", 
                    "-hwaccel", "cuda",
                    "-i", temp_large, 
                    "-i", temp_small,
                    "-filter_complex", f"[0:v][1:v]blend=all_expr='if(lt(T,{duration}),A*(1-T/{duration})+B*T/{duration},B)'",
                    "-c:v", "h264_nvenc", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", 
                    "-t", str(duration), temp_effect_video
                ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                # Clean up temp files
                for f in [temp_large, temp_small]:
                    if os.path.exists(f):
                        os.remove(f)
                
                # Use frame extraction/reassembly to burn effects
                self._burn_effects_with_frames(temp_effect_video, output_video_path)
                
                # Cleanup
                if os.path.exists(temp_effect_video):
                    os.remove(temp_effect_video)
                
                print(f"✅ Effect video created with BURNED-IN effects: {output_video_path}")
                return True
                
            elif mode.lower() == "zoom out":
                # Similar to zoom in but reversed
                print(f"🔍 Creating zoom out effect: 1.0 → {enlarge_ratio} over {duration}s")
                temp_small = os.path.join(self.temp_dir, f"zoom_small_{hash(image_path) % 10000}.mp4")
                temp_large = os.path.join(self.temp_dir, f"zoom_large_{hash(image_path) % 10000}.mp4")
                
                # Create normal version (zoom out start)
                subprocess.run([
                    self.ffmpeg_path, "-y", 
                    "-hwaccel", "cuda",
                    "-loop", "1", 
                    "-t", str(duration), 
                    "-i", image_path,
                    "-vf", f"scale={self.width}:{self.height},fps={self.STANDARD_FPS}",
                    "-c:v", "h264_nvenc", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", temp_small
                ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                # Create large version (zoom out end)
                large_scale = int(self.width * enlarge_ratio)
                subprocess.run([
                    self.ffmpeg_path, "-y", 
                    "-hwaccel", "cuda",
                    "-loop", "1", 
                    "-t", str(duration), 
                    "-i", image_path,
                    "-vf", f"scale={large_scale}:{int(self.height * enlarge_ratio)},crop={self.width}:{self.height}:(iw-{self.width})/2:(ih-{self.height})/2,fps={self.STANDARD_FPS}",
                    "-c:v", "h264_nvenc", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", temp_large
                ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                # Blend between them
                subprocess.run([
                    self.ffmpeg_path, "-y", 
                    "-hwaccel", "cuda",
                    "-i", temp_small, 
                    "-i", temp_large,
                    "-filter_complex", f"[0:v][1:v]blend=all_expr='if(lt(T,{duration}),A*(1-T/{duration})+B*T/{duration},B)'",
                    "-c:v", "h264_nvenc", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-t", str(duration), temp_effect_video
                ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                # Clean up temp files
                for f in [temp_small, temp_large]:
                    if os.path.exists(f):
                        os.remove(f)
                
                # Use frame extraction/reassembly to burn effects
                self._burn_effects_with_frames(temp_effect_video, output_video_path)
                
                # Cleanup
                if os.path.exists(temp_effect_video):
                    os.remove(temp_effect_video)
                
                print(f"✅ Effect video created with BURNED-IN effects: {output_video_path}")
                return True
                
            else:
                raise ValueError(f"Unsupported mode: {mode}")
            
            # For non-zoom effects, create video with the filter
            if mode.lower() not in ["zoom in", "zoom out"]:
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-hwaccel", "cuda",
                    "-loop", "1",
                    "-t", str(duration),
                    "-i", image_path,
                    "-vf", video_filter,
                    "-c:v", "h264_nvenc",
                    "-preset", "medium",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-r", str(self.STANDARD_FPS),
                    "-movflags", "+faststart",
                    "-avoid_negative_ts", "make_zero",
                    "-fflags", "+genpts",
                    temp_effect_video
                ]
                
                # Execute FFmpeg command to create temp effect video
                subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                # Use frame extraction/reassembly to burn effects
                self._burn_effects_with_frames(temp_effect_video, output_video_path)
                
                # Cleanup
                if os.path.exists(temp_effect_video):
                    os.remove(temp_effect_video)
            
            print(f"✅ Effect video created with BURNED-IN effects: {output_video_path}")
            return output_video_path
            
        except Exception as e:
            print(f"❌ Error creating effect video: {e}")
            return None


    def _burn_effects_with_frames(self, input_video_path, output_video_path):
        """
        Burn effects into pixels using fast format conversion (MP4 → MOV → MP4)
        
        This is much faster than frame extraction because:
        1. Convert MP4 to MOV forces re-encoding, burning effects into pixels
        2. Convert back to MP4 for compatibility
        3. Effects are now permanent pixel data, not filter instructions
        """
        temp_mov = os.path.join(self.temp_dir, f"temp_burn_{hash(input_video_path) % 10000}.mov")
        
        try:
            print(f"🔥 Burning effects into pixels (fast method): {input_video_path}")
            
            # Check if input file exists
            if not os.path.exists(input_video_path):
                raise FileNotFoundError(f"Input video file not found: {input_video_path}")
            
            # Step 1: Convert MP4 to MOV (this burns effects into pixels)
            print(f"   📹 Converting to MOV to burn effects...")
            mov_cmd = [
                self.ffmpeg_path, "-y",
                "-hwaccel", "cuda",
                "-i", input_video_path,
                "-c:v", "h264_nvenc",
                "-preset", "medium",
                "-crf", "18",     # High quality to preserve burned-in effects
                "-pix_fmt", "yuv420p",
                "-r", str(self.STANDARD_FPS),
                "-movflags", "+faststart",
                temp_mov
            ]
            
            subprocess.run(mov_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # Verify MOV was created
            if not os.path.exists(temp_mov):
                raise RuntimeError("Temporary MOV file was not created")
            
            # Step 2: Convert MOV back to MP4 (maintains burned effects)
            print(f"   📹 Converting back to MP4...")
            mp4_cmd = [
                self.ffmpeg_path, "-y",
                "-hwaccel", "cuda",
                "-i", temp_mov,
                "-c:v", "h264_nvenc",
                "-preset", "medium", 
                "-crf", "18",     # Maintain high quality
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_video_path
            ]
            
            subprocess.run(mp4_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # Verify output was created
            if os.path.exists(output_video_path):
                file_size_mb = os.path.getsize(output_video_path) / (1024 * 1024)
                print(f"   🔥 Effects BURNED into pixels: {output_video_path} ({file_size_mb:.1f}MB)")
                print(f"   🎨 Effects are now permanent pixel data - immune to processing!")
            else:
                raise RuntimeError("Output video was not created")
            
            # Cleanup temp MOV file
            if os.path.exists(temp_mov):
                os.remove(temp_mov)
                print(f"   🧹 Cleaned up temporary MOV file")
            
            return True
            
        except subprocess.CalledProcessError as e:
            # Cleanup on failure
            if os.path.exists(temp_mov):
                os.remove(temp_mov)
            raise RuntimeError(f"Failed to burn effects with format conversion: {e.stderr}") from e
        except Exception as e:
            # Cleanup on failure
            if os.path.exists(temp_mov):
                os.remove(temp_mov)
            raise RuntimeError(f"Failed to burn effects with format conversion: {e}") from e


    def add_combined_effects(self, input_video_path, output_video_path, target_duration=None, effects_config=None):
        """
        添加组合视觉效果并可选择性延长视频到目标时长
        
        Args:
            input_video_path: 输入视频路径
            output_video_path: 输出视频路径
            target_duration: 目标时长（秒），如果指定则会延长视频
            effects_config: 效果配置字典，例如:
                {
                    'floating': {'enabled': True, 'amplitude': 20, 'speed': 2.0},
                    'breathing': {'enabled': True, 'speed': 1.0, 'range': 0.3, 'base': 0.0}
                }
        """
        try:
            if effects_config is None:
                effects_config = {
                    'floating': {'enabled': False}, 
                    'breathing': {'enabled': False}
                }
            
            has_audio = self.has_audio_stream(input_video_path)
            current_video = input_video_path
            temp_files = []
            
            # 如果需要延长视频
            if target_duration:
                current_duration = self.get_duration(current_video)
                if current_duration < target_duration:
                    temp_extended = os.path.join(self.temp_dir, "temp_extended.mp4")
                    if self.extend_video_to_duration(current_video, target_duration, temp_extended):
                        current_video = temp_extended
                        temp_files.append(temp_extended)
                        print(f"✅ 视频已延长到 {target_duration:.2f} 秒")
            
            # 按顺序应用效果
            effect_count = 0
            
            # 1. 漂浮动画
            if effects_config.get('floating', {}).get('enabled', False):
                floating_config = effects_config['floating']
                temp_float = os.path.join(self.temp_dir, f"temp_effect_{effect_count}.mp4")
                if self.add_floating_animation(
                    current_video, temp_float,
                    floating_config.get('amplitude', 20),
                    floating_config.get('speed', 2.0)
                ):
                    current_video = temp_float
                    temp_files.append(temp_float)
                    effect_count += 1
            
            # 复制最终结果到输出路径
            if current_video != input_video_path:
                shutil.copy2(current_video, output_video_path)
                print(f"✅ 组合效果处理完成，共应用 {effect_count} 个效果: {output_video_path}")
            else:
                # 没有应用任何效果，直接复制原文件
                shutil.copy2(input_video_path, output_video_path)
                print(f"📋 没有应用任何效果，直接复制: {output_video_path}")
            
            # 清理临时文件
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            
            return True
            
        except Exception as e:
            print(f"❌ 组合效果处理失败: {e}")
            # 清理临时文件
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            return False



    def resize_image_smart(self, input_image):
        return self.resize_image(input_image, self.width, self.height)


    def resize_image(self, input_image, width, height):
        """Smart resize image to the specified dimensions with intelligent cropping."""
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



    def create_scroll_background_video_169(self, background_image, duration, repeat_duration):
        """
        Create 16:9 scrolling background video without title
        Alternates scroll direction every repeat_duration seconds
        SCROLLS THE WHOLE WIDTH OF THE ORIGINAL IMAGE (not resized version)
        """
        output_file = config.get_temp_file(self.pid, "mp4")
        
        # 16:9 mode dimensions - final output size
        output_width = self.width
        output_height = self.height
        
        # Get original image dimensions to work with full width
        original_width, original_height = self.get_resolution(background_image)
        if not original_width or not original_height:
            print(f"⚠️  Could not detect image resolution, falling back to resize method")
            # Fallback to original method if we can't detect resolution
            background_image = self.resize_image_smart(background_image)
            bg_scale_width = int(output_width * 1.5)
            max_scroll = bg_scale_width - output_width
        else:
            print(f"🖼️  Original image: {original_width}x{original_height}")
            
            # Check if image is very large and pre-resize it for better performance and compatibility
            max_processing_height = self.height  # Maximum dimension for direct processing
            if original_height > max_processing_height:
                scale_down_factor = max_processing_height / original_height
                intermediate_width = int(original_width * scale_down_factor)
                intermediate_height = int(original_height * scale_down_factor)
                
                print(f"   Pre-resizing to intermediate size: {intermediate_width}x{intermediate_height}")
                background_image = self.resize_image_smart(background_image, intermediate_width, intermediate_height)
                
                # Update dimensions for further processing
                original_width, original_height = intermediate_width, intermediate_height
                print(f"✅ Pre-resize complete, now processing: {original_width}x{original_height}")
            
            # Calculate scaling to fit height while preserving aspect ratio
            # Scale so the height fits our output height
            scale_factor = output_height / original_height
            scaled_width = int(original_width * scale_factor)
            scaled_height = output_height
            
            print(f"📐 Final scaled dimensions: {scaled_width}x{scaled_height}")
            
            # Ensure we have enough width for scrolling
            if scaled_width <= output_width:
                print(f"⚠️  Scaled width ({scaled_width}) not wider than output ({output_width}), using 1.5x method")
                # Fallback: use 1.5x scaling if original isn't wide enough
                bg_scale_width = int(output_width * 1.5)
                max_scroll = bg_scale_width - output_width
                # Resize the image to standard dimensions in this case
                background_image = self.resize_image_smart(background_image, self.width, self.height)
            else:
                # Use the full scaled width for maximum scroll effect
                bg_scale_width = scaled_width
                max_scroll = bg_scale_width - output_width
                print(f"✅ Using full image width: scroll range = {max_scroll} pixels")
        
        print(f"🎬 Full scroll range: 0 to {max_scroll} pixels ({max_scroll} pixel range)")
        
        # Calculate number of complete segments
        num_segments = int(duration / repeat_duration)
        
        # Build crop expression for alternating scroll directions
        if num_segments <= 1:
            # Simple case: single direction for entire duration (right to left)
            crop_expr = f"{max_scroll}*(1-t/{duration})"
        else:
            # Complex case: alternating directions every repeat_duration
            # Use modulo to determine current segment and direction
            crop_expr = (
                f"if(mod(floor(t/{repeat_duration}),2),"
                f"({max_scroll})*(mod(t,{repeat_duration})/{repeat_duration}),"
                f"({max_scroll})*(1-mod(t,{repeat_duration})/{repeat_duration}))"
            )

        filter_complex = (
            f"[0:v]scale={bg_scale_width}:{output_height},"
            f"trim=duration={duration},fps={self.STANDARD_FPS},"
            f"crop={output_width}:{output_height}:{crop_expr}:0[outv]"
        )


        print(f"🎬 Creating 16:9 scrolling background: {output_width}x{output_height}")
        print(f"   📐 Duration: {duration}s, Repeat every: {repeat_duration}s, Segments: {num_segments + 1}")
        print(f"   📐 Background scale: {bg_scale_width}x{output_height}")
        print(f"   📐 Full scroll from x=0 to x={max_scroll} ({max_scroll} pixels total)")
        
        try:
            # Get dynamic encoder configuration based on output resolution
            input_args = self._get_input_args(output_width, output_height)
            output_args = self._get_output_args(output_width, output_height)
            
            cmd = [
                self.ffmpeg_path, "-y"
            ]
            cmd.extend(input_args)

            cmd.extend([
                "-loop", "1",
                "-i", background_image,
                "-filter_complex", filter_complex,
                "-map", "[outv]"   # <--- map the filtered output, not 0:v
            ])

            cmd.extend(output_args)
            cmd.extend([
                "-pix_fmt", "yuv420p",
                "-t", str(duration),
                output_file
            ])
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
        except subprocess.CalledProcessError as e:
            print("FFmpeg failed:")
            print(e.stderr)
        
        return output_file


    def create_scroll_background_video_916(self, background_image, duration, repeat_duration):
        """
        Create 9:16 scrolling background video without title
        Alternates scroll direction every repeat_duration seconds
        SCROLLS THE WHOLE IMAGE END-TO-END
        """
        output_file = config.get_temp_file(self.pid, "mp4")
        
        # Portrait mode: 607x1080 with scrolling effect
        output_width = int(self.height*9/16)
        output_height = self.height
        
        # Detect background image resolution for encoder selection
        img_width, img_height = self.get_resolution(background_image)
        
        # Check if image is very large and pre-resize it for better performance and compatibility
        max_processing_height = self.height  # Maximum dimension for direct processing
        if img_height > max_processing_height:
            scale_down_factor = max_processing_height / img_height
            intermediate_width = int(img_width * scale_down_factor)
            intermediate_height = int(img_height * scale_down_factor)
            
            print(f"   Pre-resizing to intermediate size: {intermediate_width}x{intermediate_height}")
            background_image = self.resize_image_smart(background_image, intermediate_width, intermediate_height)
            
            # Update dimensions for further processing
            img_width, img_height = intermediate_width, intermediate_height
            print(f"✅ Pre-resize complete, now processing: {img_width}x{img_height}")
        
        # Scale image to height 1080 while maintaining aspect ratio
        scaled_height = self.height
        scaled_width = int(self.height * img_width / img_height)  # Convert to integer
        print(f"   Final scaling from {img_width}x{img_height} to {scaled_width}x{scaled_height}")
        
        # Ensure scaled_width is wide enough for scrolling
        if scaled_width <= output_width:
            print(f"⚠️  Warning: Scaled width ({scaled_width}) is not wider than output width ({output_width})")
            scaled_width = output_width + 200  # Add minimum scrolling space
            print(f"   Adjusted scaled_width to: {scaled_width}")
        
        # Calculate scrolling parameters for FULL END-TO-END scrolling
        start_x = 0  # Start from leftmost edge
        end_x = scaled_width - output_width  # End at rightmost edge
        
        print(f"🎬 Full end-to-end scroll range: {start_x} to {end_x} pixels ({end_x - start_x} pixel range)")
        
        # Calculate number of complete segments
        num_segments = int(duration / repeat_duration)
        
        # Build crop expression for alternating scroll directions
        # FIXED: Start from LEFT side and alternate properly
        if num_segments <= 1:
            # Simple case: single direction for entire duration (left to right)
            crop_expr = f"{start_x}+({end_x}-{start_x})*(t/{duration})"
        else:
            # Complex case: alternating directions every repeat_duration
            # FIXED: Start with left-to-right for segment 0
            crop_expr = (
                f"if(mod(floor(t/{repeat_duration}),2),"
                f"{end_x}-({end_x}-{start_x})*(mod(t,{repeat_duration})/{repeat_duration}),"
                f"{start_x}+({end_x}-{start_x})*(mod(t,{repeat_duration})/{repeat_duration}))"
            )
        
        # Build video filter chain (use -vf instead of -filter_complex for simple linear chain)
        video_filter = (
            f"scale={scaled_width}:{scaled_height},"
            f"fps={self.STANDARD_FPS},"
            f"crop={output_width}:{output_height}:'{crop_expr}':0"
        )
        
        print(f"🎬 Creating 9:16 scrolling background: {output_width}x{output_height}")
        print(f"   📐 Input: {img_width}x{img_height} → Scaled: {scaled_width}x{scaled_height} → Output: {output_width}x{output_height}")
        print(f"   📐 Duration: {duration}s, Repeat every: {repeat_duration}s, Segments: {num_segments + 1}")
        print(f"   📐 Scroll pattern: Segment 0 (LEFT→RIGHT), Segment 1 (RIGHT→LEFT), alternating...")
        print(f"   📐 Full scroll from x={start_x} to x={end_x} ({end_x - start_x} pixels total)")
        print(f"   🔧 Video filter: {video_filter}")
        
        try:
            # Get dynamic encoder configuration based on output resolution
            input_args = self._get_input_args(output_width, output_height)
            output_args = self._get_output_args(output_width, output_height)
            
            cmd = [
                self.ffmpeg_path, "-y"
            ]
            cmd.extend(input_args)
            cmd.extend([
                "-loop", "1",
                "-i", background_image,
                "-vf", video_filter,  # Use -vf instead of -filter_complex
                "-t", str(duration)   # Move duration control here for better reliability
            ])
            cmd.extend(output_args)
            cmd.extend([
                "-pix_fmt", "yuv420p",
                output_file
            ])
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            print(f"✅ Successfully created 9:16 scrolling background video: {output_file}")
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg failed creating scrolling background:")
            print(f"   Error: {e.stderr}")
            print(f"   Command attempted: scale={scaled_width}:{scaled_height}, crop={output_width}:{output_height}")
        
        return output_file


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
            font_size = 130
            position = "header"
            content = content[2:]   
        elif content.lower().startswith("bl_"):
            font_size = 130
            position = "body"
            content = content[3:]
        elif content.lower().startswith("fl_"):
            font_size = 130
            position = "footer"
            content = content[3:]
        elif content.lower().startswith("hs_"):
            position = "header"
            font_size = 60
            content = content[3:]
        elif content.lower().startswith("bs_"):
            position = "body"
            font_size = 60
            content = content[3:]
        elif content.lower().startswith("fs_"):
            position = "footer"
            font_size = 60
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
            
            # Get dynamic encoder configuration
            input_args = self._get_input_args(video_width, video_height)
            output_args = self._get_output_args(video_width, video_height)
            
            cmd = [
                self.ffmpeg_path, "-y"
            ]
            cmd.extend(input_args)  # Add input args (like hwaccel)
            cmd.extend([
                "-i", input_video_path,
                "-vf", drawtext_filter
            ])
            cmd.extend(output_args)  # Add output args (codec, preset, quality)
            cmd.extend([
                "-pix_fmt", "yuv420p"
            ])
            
            # Handle audio
            if has_audio:
                cmd.extend(["-c:a", "copy"])  # Copy audio without re-encoding
            
            cmd.extend([
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                output_file
            ])
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
            
            print(f"📝 Text wrapping: {available_width}px available width (from {img_width}px image), ~{chars_per_line} chars/line")
            print(f"📝 Script type: {script_type}, Font size: {font_size}px, Est char width: {estimated_char_width:.1f}px")
            print(f"📝 Original title: '{title}'")
            print(f"📝 Wrapped title: '{wrapped_title}'")
            
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
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            print(f"✅ Title successfully added to image: {output_file}")
            print(f"   📝 Text: '{wrapped_title}' at position '{position}' with font size {font_size}px")
            
            # Clean up temporary text file
            if os.path.exists(text_file_path):
                os.remove(text_file_path)
                
            return output_file
                

        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg Error adding title to image: {e.stderr}")
            # Clean up temporary text file on error
            text_file_path = os.path.join(self.temp_dir, f"txt_{self.pid}.txt")
            if os.path.exists(text_file_path):
                os.remove(text_file_path)
            return None
        except Exception as e:
            print(f"❌ Error adding title to image: {e}")
            # Clean up temporary text file on error
            text_file_path = os.path.join(self.temp_dir, f"txt_{self.pid}.txt")
            if os.path.exists(text_file_path):
                os.remove(text_file_path)
            return None

    def _detect_script_and_estimate_char_width(self, text, font_size):
        """
        Detect the primary script of the text and estimate character width accordingly
        
        Args:
            text: Input text to analyze
            font_size: Font size in pixels
            
        Returns:
            tuple: (script_type, estimated_char_width)
        """
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
            result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                input_video_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
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
            
            # Get dynamic encoder configuration
            input_args = self._get_input_args()
            output_args = self._get_output_args()
            
            cmd = [
                self.ffmpeg_path, "-y"
            ]
            cmd.extend(input_args)
            cmd.extend([
                "-i", input_video_path,
                "-vf", video_filter,
                "-an"  # Remove audio for now (can be adjusted later)
            ])
            cmd.extend(output_args)
            cmd.extend([
                "-pix_fmt", "yuv420p",
                "-g", str(self.STANDARD_FPS),
                "-keyint_min", str(self.STANDARD_FPS),
                output_video_path
            ])
            
            # 打印完整的FFmpeg命令用于调试
            print(f"🔧 FFmpeg command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            return output_video_path
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg command failed with exit code {e.returncode}")
            if e.stderr:
                print(f"   Error output: {e.stderr}")
            if e.stdout:
                print(f"   Standard output: {e.stdout}")
            return input_video_path
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
            
            cmd = [
                self.ffmpeg_path, "-y",
                "-hwaccel", "cuda",
                "-i", video_path,
                "-vf", vf_filter,
                "-c:v", "h264_nvenc",
                "-pix_fmt", "yuv420p",  # 改为yuv420p而不是yuva420p
                "-c:a", "copy",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                output_path
            ]
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
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
            
            # 构建ffmpeg命令
            inputs = ["-i", background_video, "-i", resized_video]
            
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
            cmd = [
                self.ffmpeg_path, "-y"
            ] + inputs + [
                "-filter_complex", filter_complex,
                "-map", "0:a",   # 使用背景视频的音频
                "-c:a", "copy",  # 保持音频不变
                "-c:v", "libx264",  # 视频编码
                output_path
            ]
            
            print(f"🎬 开始添加画中画效果...")
            print(f"📍 开始时间: {start_time}s, 结束时间: {pip_end_time}s")
            print(f"📐 PiP尺寸: {small_width}x{small_height}, 位置: {position}")
            print(f"✨ 边缘虚化: {edge_blur_size}像素")
            print(f"🔧 FFmpeg命令: {' '.join(cmd)}")
            
            # 执行ffmpeg命令
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
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

