import os, json
import subprocess
from pathlib import Path
from config import ffmpeg_path, ffprobe_path, FONT_0, FONT_1, FONT_2, FONT_4, FONT_6, FONT_7, FONT_8
import config
from utility.file_util import copy_file



class FfmpegAudioProcessor:


    def __init__(self, pid):
        self.pid = pid
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.effect_path = config.get_effect_path()


    def audio_change(self, audio_path, fade_in_length=0.0, fade_out_length=0.0, volume=1.0, extend_length=0.0):
        output_path = config.get_temp_file(self.pid, "wav")
        try:
            # Validate volume parameter
            if not (0.1 <= volume <= 5.0):
                raise ValueError(f'Volume must be between 0.1 and 5.0, got {volume}')
            
            # Debug output
            print(f'🔊 Converting to stereo with volume: {volume} (1.0=normal, <1.0=quieter, >1.0=louder)')
            if fade_in_length > 0.0 or fade_out_length > 0.0:
                print(f'🎵 Adding fade effects - In: {fade_in_length}s, Out: {fade_out_length}s')
            print(f'📁 Input: {audio_path}')
            print(f'📁 Output: {output_path}')
            
            # Build FFmpeg command
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", audio_path,
                "-vn",
                "-ac", "2",
                "-ar", "44100",
                "-c:a", "pcm_s16le"
            ]
            
            # Build audio filter string
            audio_filters = []
            
            # Add fade effects if fade_in_length or fade_out_length > 0
            if fade_in_length > 0.0 or fade_out_length > 0.0:
                # Get audio duration to calculate fade out start time
                duration = self.get_duration(audio_path)
                if duration is None:
                    print(f"⚠️ Could not determine audio duration, skipping fade effects")
                else:
                    print(f'🎵 Audio duration: {duration:.2f}s')
                    
                    # Add fade in filter if fade_in_length > 0
                    if fade_in_length > 0.0:
                        audio_filters.append(f"afade=t=in:st=0:d={fade_in_length}:curve=esin")
                        print(f'🎵 Adding fade in: {fade_in_length}s')
                    
                    # Add fade out filter if fade_out_length > 0
                    if fade_out_length > 0.0:
                        fade_out_start = max(0, duration - fade_out_length)
                        audio_filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out_length}:curve=esin")
                        print(f'🎵 Adding fade out: {fade_out_length}s starting at {fade_out_start:.2f}s')
            
            # Add volume filter if volume is not 1.0 (normal)
            if volume != 1.0:
                audio_filters.append(f"volume={volume}")
            
            # Add padding (silence extension) if extend_length > 0
            if extend_length > 0.0:
                audio_filters.append(f"apad=pad_dur={extend_length}")
                print(f'🔇 Extending audio with {extend_length} seconds of silence')
            
            # Apply audio filters if any exist
            if audio_filters:
                filter_string = ",".join(audio_filters)
                cmd.extend(["-af", filter_string])
                print(f'🔧 Audio filters applied: {filter_string}')

            cmd.append(output_path)
            
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # Verify the output file was created
            if os.path.exists(output_path):
                print(f'✅ Stereo conversion completed successfully: {output_path}')
                return output_path
            else:
                print(f'❌ Output file was not created: {output_path}')
                return None
                
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error in audio_to_stereo: {e.stderr}")
            return None
        except Exception as e:
            print(f"An error occurred in audio_to_stereo: {e}")
            return None


    def concat_audios(self, audio_list):
        output_path = config.get_temp_file(self.pid, "wav")
        if len(audio_list) == 0:
            return None
        if len(audio_list) == 1:
            copy_file(audio_list[0], output_path)
            return output_path

        try:
            audio_list_path = os.path.join(config.get_temp_path(self.pid), "concat_list.txt")
            with open(audio_list_path, "w", encoding='utf-8') as f:
                for audio in audio_list:
                    # Use forward slashes for cross-platform compatibility
                    audio_escaped = audio.replace('\\', '/')
                    f.write(f"file '{audio_escaped}'\n")

            # Step 3: Concatenate the normalized audio files
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
            print(f"Successfully concatenated {len(audio_list)} audio files to: {output_path}")

        except Exception as e:
            print(f"Error in concat_audios: {e}")

        return output_path


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
        
        # If only one audio file, return it directly
        if len(audio_list) == 1:
            return self.to_wav(audio_list[0])
        
        output_path = config.get_temp_file(self.pid, "wav")
        
        try:
            # Build FFmpeg command to mix multiple audio files
            cmd = ['ffmpeg', '-y']
            
            # Add input files
            for audio_file in audio_list:
                if audio_file and os.path.exists(audio_file):
                    cmd.extend(['-i', audio_file])
                else:
                    print(f"警告：音频文件不存在或为空: {audio_file}")
                    continue
            
            # If no valid audio files found
            valid_inputs = sum(1 for audio in audio_list if audio and os.path.exists(audio))
            if valid_inputs == 0:
                print("错误：没有找到有效的音频文件")
                return None
            elif valid_inputs == 1:
                # Only one valid file, copy it
                valid_file = next(audio for audio in audio_list if audio and os.path.exists(audio))
                return valid_file
            
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


    def extend_audio(self, audio_path, target_length):
        original_duration = self.get_duration(audio_path)
        if original_duration >= target_length:
            return audio_path
        
        try:
            output_path = config.get_temp_file(self.pid, "wav")
            
            silence_duration = target_length - original_duration
            
            subprocess.run([
                self.ffmpeg_path, "-y",
                "-i", audio_path,
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={silence_duration}",
                "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
                "-ac", "2",
                "-ar", "44100",
                "-c:a", "pcm_s16le",
                output_path
            ], check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            return output_path
        except Exception as e:
            print(f"An error occurred in extend_audio: {e}")
            return None

    def audio_cut_fade(self, raw_auddio_path, start_time, output_length, fade_in=0, fade_out=0, volume=1.0):
        output_path = config.get_temp_file(self.pid, "wav")

        raw_audio_length = self.get_duration(raw_auddio_path)
        if not output_length or output_length + start_time > raw_audio_length:
            output_length = raw_audio_length - start_time

        if (volume == 0.0 or volume == 1.0) and start_time==0 and fade_in==0 and fade_out==0 and output_length==raw_audio_length:
            copy_file(raw_auddio_path, output_path)
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
