import os, json
import subprocess
from pathlib import Path
from config import ffmpeg_path, ffprobe_path, FONT_0, FONT_1, FONT_3, FONT_4, FONT_7, FONT_8
import config
from utility.file_util import safe_copy_overwrite



class FfmpegAudioProcessor:


    def __init__(self, pid):
        self.pid = pid
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.effect_path = config.get_effect_path()


    def make_silence(self, duration):
        noise_wav_path = config.get_background_music_path()+"/noise.wav"
        return self.audio_cut_fade(noise_wav_path, 0, duration, 0, 1.0)


    def split_audio(self, original_clip, position):
        first = config.get_temp_file(self.pid, "wav")
        second = config.get_temp_file(self.pid, "wav")
        try:
            # First part: from start (0) to position
            subprocess.run([
                self.ffmpeg_path, "-y",
                "-i", original_clip,
                "-t", str(position),   # duration = position seconds
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                first
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')

            # Second part: from position to end
            subprocess.run([
                self.ffmpeg_path, "-y",
                "-i", original_clip,
                "-ss", str(position),  # start from position
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                second
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')

            return first, second

        except Exception as e:
            print(f"❌ An error occurred in split_audio: {e}")
            return None, None


    def to_wav(self, input_audio_path):
        output_audio_path = config.get_temp_file(self.pid, "wav")
        try:
            subprocess.run([
                self.ffmpeg_path, "-y",
                "-i", input_audio_path,
                "-c:a", "pcm_s16le",
                "-ar", "44100", 
                "-ac", "2",
                output_audio_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            return output_audio_path
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error converting AAC to WAV: {e.stderr}")
            return None


    def extract_audio_from_video(self, video_path):
        output_audio_path = config.get_temp_file(self.pid, "wav")

        # if the video has no audio channel, return None
        try:
            # Check if video has audio streams using ffprobe
            result = subprocess.run([
                self.ffprobe_path,
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                video_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            if not result.stdout.strip():
                print(f"No audio streams found in video: {os.path.basename(video_path)}")
                return None
                
        except subprocess.CalledProcessError as e:
            print(f"FFprobe Error checking audio streams: {e.stderr}")
            return None

        try:
            subprocess.run([
                self.ffmpeg_path, "-y",
                "-i", video_path,
                "-vn",
                "-c:a", "pcm_s16le",    
                "-ar", "44100",
                "-ac", "2",
                output_audio_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            return output_audio_path
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error taking audio from video: {e.stderr}")
            return None

    # simply mix all audio files in the list, keep longest duration
    def audio_list_mix(self, audio_list):
        if not audio_list or len(audio_list) == 0:
            return None
        
        if len(audio_list) == 1:
            return self.to_wav(audio_list[0])
        
        output_path = config.get_temp_file(self.pid, "wav")
        
        try:
            cmd = [self.ffmpeg_path, '-y']
            
            for audio_file in audio_list:
                if audio_file and os.path.exists(audio_file):
                    cmd.extend(['-i', audio_file])
                else:
                    print(f"警告：音频文件不存在或为空: {audio_file}")
                    continue
            
            valid_inputs = sum(1 for audio in audio_list if audio and os.path.exists(audio))
            if valid_inputs == 0:
                print("错误：没有找到有效的音频文件")
                return None
            elif valid_inputs == 1:
                valid_file = next(audio for audio in audio_list if audio and os.path.exists(audio))
                return self.to_wav(valid_file)
            
            # Mix all inputs with equal volume, keep longest duration
            filter_complex = f"amix=inputs={valid_inputs}:duration=longest:normalize=0"
            
            cmd.extend([
                '-filter_complex', filter_complex,
                '-ac', '2',  # stereo output
                '-ar', '44100',  # sample rate
                '-f', 'wav',
                output_path
            ])
            
            print(f"🎵 混合 {valid_inputs} 个音频文件...")
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            if os.path.exists(output_path):
                print(f"✅ 音频混合完成: {output_path}")
                return output_path
            else:
                print("❌ 音频混合失败：输出文件未生成")
                return None
                
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg音频混合错误: {e.stderr}")
            return None
        except Exception as e:
            print(f"❌ 音频混合异常: {str(e)}")
            return None


    def concat_audios(self, audio_list):
        if not audio_list or len(audio_list) == 0:
            return None
        
        output_path = config.get_temp_file(self.pid, "wav")
        
        if len(audio_list) == 1:
            # Convert to wav for consistency
            return self.to_wav(audio_list[0])

        try:
            valid_audio_list = [audio for audio in audio_list if audio and os.path.exists(audio)]
            
            if len(valid_audio_list) == 0:
                print("错误：没有找到有效的音频文件")
                return None
            elif len(valid_audio_list) == 1:
                return self.to_wav(valid_audio_list[0])
            
            audio_list_path = os.path.join(config.get_temp_path(self.pid), "concat_list.txt")
            with open(audio_list_path, "w", encoding='utf-8') as f:
                for audio in valid_audio_list:
                    audio_escaped = audio.replace('\\', '/')
                    f.write(f"file '{audio_escaped}'\n")

            # Concatenate the audio files
            concat_cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", audio_list_path,
                "-c:a", "pcm_s16le",
                "-ac", "2",
                "-ar", "44100",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                output_path
            ]
            
            subprocess.run(concat_cmd, check=True, capture_output=True, 
                         text=True, encoding='utf-8', errors='ignore')
            
            if os.path.exists(output_path):
                print(f"✅ 成功连接 {len(valid_audio_list)} 个音频文件: {output_path}")
                return output_path
            else:
                print("❌ 音频连接失败：输出文件未生成")
                return None

        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg音频连接错误: {e.stderr}")
            return None
        except Exception as e:
            print(f"❌ 音频连接异常: {str(e)}")
            return None


    def audio_mix(self, audio_path, main_volume, start_time, mix_sound_path, mix_volume):
        try:
            temp_file = config.get_temp_file(self.pid, "wav")

            # Get the duration of the main audio
            main_audio_duration = self.get_duration(audio_path)
            if main_audio_duration == 0.0:
                print(f"无法获取主音频时长: {audio_path}")
                return None
            
            # Calculate remaining time from start_time to end of main audio
            remaining_time = main_audio_duration - float(start_time)
            if remaining_time <= 0:
                print(f"开始时间 {start_time} 超出了主音频长度 {main_audio_duration}")
                return None
            
            # Get the duration of the mix sound
            mix_sound_duration = self.get_duration(mix_sound_path)
            if mix_sound_duration == 0.0:
                print(f"无法获取混音文件时长: {mix_sound_path}")
                return None

            # Convert start_time from seconds to milliseconds for the adelay filter
            start_time_ms = int(float(start_time) * 1000)

            # Build filter complex based on whether mix sound needs to be trimmed
            if mix_sound_duration > remaining_time:
                # Mix sound is longer than remaining time, need to trim it
                print(f"混音文件长度 ({mix_sound_duration:.2f}s) 超过剩余时间 ({remaining_time:.2f}s)，将进行截断")
                filter_complex = (
                    f"[0:a]volume={main_volume}[a0];"
                    f"[1:a]atrim=end={remaining_time},adelay={start_time_ms}|{start_time_ms},volume={mix_volume}[a1];"
                    f"[a0][a1]amix=inputs=2:duration=first[aout]"
                )
            else:
                # Mix sound fits within remaining time, use original logic
                filter_complex = (
                    f"[0:a]volume={main_volume}[a0];"
                    f"[1:a]adelay={start_time_ms}|{start_time_ms},volume={mix_volume}[a1];"
                    f"[a0][a1]amix=inputs=2:duration=first[aout]"
                )
            
            print(f"主音频时长: {main_audio_duration:.2f}s, 主音量: {main_volume}, 开始时间: {start_time}s, 剩余时间: {remaining_time:.2f}s")
            print(f"混音文件时长: {mix_sound_duration:.2f}s, 混音音量: {mix_volume}")
            
            subprocess.run([
                self.ffmpeg_path, "-y",
                "-i", audio_path,
                "-i", mix_sound_path,
                "-filter_complex", filter_complex,
                "-map", "[aout]",
                "-ac", "2",
                "-ar", "44100",
                "-c:a", "pcm_s16le",
                temp_file
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error in audio_mix: {e.stderr}")
            return None
        except Exception as e:
            print(f"An error occurred in audio_mix: {e}")
            return None

        return temp_file


    def extend_audio(self, audio_path, start_time, target_length):
        """
        从指定开始时间扩展音频到目标长度。
        如果音频长度不足，会在末尾添加静音。
        如果音频长度已满足要求，会进行裁剪。
        
        Args:
            audio_path: 输入音频文件路径
            start_time: 开始时间（秒）
            target_length: 目标长度（秒）
            
        Returns:
            处理后的音频文件路径，失败时返回 None
        """
        # 参数验证
        if target_length <= 0:
            print(f"⚠️ 目标时长必须大于0: {target_length}")
            return None
            
        original_duration = self.get_duration(audio_path)
        if original_duration <= 0.0 or start_time < 0.0 or start_time >= original_duration:
            print(f"⚠️ 音频时长或开始时间不合法: {audio_path}, original_duration: {original_duration}, start_time: {start_time}")
            return None
        
        # 计算从开始时间到结尾的可用时长
        available_duration = original_duration - start_time
        
        # 如果音频长度已满足要求，直接裁剪
        if available_duration >= target_length:
            print(f"ℹ️ 音频时长 ({available_duration:.2f}s) 已满足目标时长 ({target_length:.2f}s)，进行裁剪")
            return self.audio_cut_fade(audio_path, start_time, target_length, 0, 1.0)
        
        # 需要扩展：先裁剪音频，然后添加静音
        try:
            # 裁剪音频（从 start_time 到结尾）
            cut_audio_path = self.audio_cut_fade(audio_path, start_time, available_duration, 0, 1.0)
            
            # 检查裁剪是否成功
            if not cut_audio_path or not os.path.exists(cut_audio_path):
                print(f"❌ 音频裁剪失败: {cut_audio_path}")
                return None
            
            # 计算需要添加的静音时长
            output_path = config.get_temp_file(self.pid, "wav")
            silence_duration = target_length - available_duration
            
            print(f'🔇 扩展音频: 原始时长 {available_duration:.2f}s -> 目标时长 {target_length:.2f}s (添加 {silence_duration:.2f}s 静音)')
            
            # 将裁剪后的音频与静音连接
            subprocess.run([
                self.ffmpeg_path, "-y",
                "-i", cut_audio_path,
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={silence_duration}",
                "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
                "-ac", "2",
                "-ar", "44100",
                "-c:a", "pcm_s16le",
                output_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # 验证输出文件是否生成
            if not os.path.exists(output_path):
                print(f"❌ 扩展音频失败：输出文件未生成")
                return None
            
            return output_path
                
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg 错误 (extend_audio): {e.stderr}")
            return None
        except Exception as e:
            print(f"❌ 扩展音频时发生错误: {e}")
            return None



    def audio_cut_fade(self, raw_auddio_path, start_time, output_length, fade_in=0, fade_out=0, volume=1.0):
        output_path = config.get_temp_file(self.pid, "wav")

        raw_audio_length = self.get_duration(raw_auddio_path)
        if not output_length or output_length + start_time > raw_audio_length:
            output_length = raw_audio_length - start_time

        if (volume == 0.0 or volume == 1.0) and start_time==0 and fade_in==0 and fade_out==0 and output_length==raw_audio_length:
            safe_copy_overwrite(raw_auddio_path, output_path)
            return output_path

        try:
            # Validate volume parameter
            if not (0.1 <= volume <= 5.0):
                raise ValueError(f'Volume must be between 0.1 and 5.0, got {volume}')
            
            # Build audio filter components conditionally
            filter_parts = []
            
            # Add fade effects only if fade_length > 0
            if fade_in > 0:
                filter_parts.append(f"afade=t=in:st=0:d={fade_in}:curve=esin")

            if fade_out > 0:
                fade_out_start = max(0, output_length - fade_in)
                filter_parts.append(f"afade=t=out:st={fade_out_start}:d={fade_out}:curve=esin")
            
            # Add volume adjustment only if volume != 1.0
            if volume != 1.0:
                filter_parts.append(f"volume={volume}")
                print(f'🔊 Volume adjustment applied: {volume} (1.0=normal, <1.0=quieter, >1.0=louder)')
            else:
                print(f'🔊 Volume adjustment skipped (volume={volume})')
            
            # Build FFmpeg command
            cmd = [
                self.ffmpeg_path, "-y",
                "-ss", str(start_time),      # Start from the specified time
                "-i", raw_auddio_path,       # Input audio file
                "-t", str(output_length),    # Trim the audio to the specified output length
            ]
            
            # Add audio filter only if there are filter parts to apply
            if filter_parts:
                audio_filter = ",".join(filter_parts)
                cmd.extend(["-af", audio_filter])
                print(f'🎵 Audio filter applied: {audio_filter}')
            else:
                print(f'🎵 No audio filters applied - using raw audio')
            
            cmd.extend([
                "-ac", "2",
                "-ar", "44100",
                "-c:a", "pcm_s16le",
                output_path
            ])
            
            print(f'⏱️  Audio timing: start={start_time}s, length={output_length}s, fade={fade_in}s')

            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            print(f'✅ Audio processing completed: {output_path}')
            
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error in fade_audio: {e.stderr}")
        except Exception as e:
            print(f"An error occurred in fade_audio: {e}")

        return output_path


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
