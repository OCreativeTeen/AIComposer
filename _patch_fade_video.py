# -*- coding: utf-8 -*-
from pathlib import Path

# --- fade_video: add audio_fade parameter ---
fp = Path("utility/ffmpeg_processor.py")
text = fp.read_text(encoding="utf-8")

old = '''    def fade_video(self, video_path, fade_in_length, fade_out_length):
        output_path = config.get_temp_file(self.pid, "mp4")
        video_length = self.get_duration(video_path)
        has_audio = self.has_audio_stream(video_path)

        try:
            fade_out_start = max(0, video_length - fade_out_length)
            
            # 构建视频滤镜 (不带 alpha 通道)
            vf_parts = []
            
            # 添加淡入效果 (不带 alpha 通道)
            if fade_in_length > 0:
                vf_parts.append(f"fade=t=in:st=0:d={fade_in_length}")
                print(f"🎬 添加淡入(无alpha通道): fade_in_length={fade_in_length}")
                
                # 检查fade时长是否合理
                if fade_in_length >= video_length / 2:
                    print(f"⚠️ 警告:fade_in_length ({fade_in_length}) 过长,可能影响效果!")
            
            # 添加淡出效果 (不带 alpha 通道)
            if fade_out_length > 0:
                vf_parts.append(f"fade=t=out:st={fade_out_start}:d={fade_out_length}")
                print(f"🎬 添加淡出(无alpha通道): fade_out_length={fade_out_length}, fade_out_start={fade_out_start}, video_length={video_length}")
                
                # 检查fade参数是否合理
                if fade_out_start >= video_length:
                    print(f"⚠️ 警告:fade_out_start ({fade_out_start}) >= video_length ({video_length}),fade out可能无效!")
                if fade_out_length >= video_length / 2:
                    print(f"⚠️ 警告:fade_out_length ({fade_out_length}) 过长,可能影响效果!")
            
            cmd = [
                ffmpeg_path, "-y",
                "-hwaccel", "cuda",
                "-i", video_path
            ]
            
            # 如果有视频滤镜就加 -vf 参数
            if vf_parts:
                cmd.extend(["-vf", ",".join(vf_parts)])
            
            # 处理音频淡变 - 有音轨时默认一起淡
            if has_audio:
                audio_filters = []
                if fade_in_length > 0:
                    audio_filters.append(f"afade=t=in:st=0:d={fade_in_length}")
                if fade_out_length > 0:
                    audio_fade_out_start = max(0, video_length - fade_out_length)
                    audio_filters.append(f"afade=t=out:st={audio_fade_out_start}:d={fade_out_length}")
                
                if audio_filters:
                    cmd.extend(["-af", ",".join(audio_filters)])
                    print(f"🔊 添加音频淡变滤镜: {','.join(audio_filters)}")
                
                cmd.extend(self._get_audio_encode_args())
'''

# The comments in the file may differ - read the actual function and replace more carefully
start = text.find("    def fade_video(self, video_path, fade_in_length, fade_out_length):")
if start < 0:
    raise SystemExit("fade_video def not found")
# Change signature
text2 = text[:start] + "    def fade_video(self, video_path, fade_in_length, fade_out_length, audio_fade=True):" + text[start + len("    def fade_video(self, video_path, fade_in_length, fade_out_length):"):]

# Find the audio handling block inside fade_video and wrap with audio_fade check
# Locate unique string after signature change
marker = "            # 处理音频"
# Find within fade_video only - between start and next def
next_def = text2.find("\n    def ", start + 10)
chunk = text2[start:next_def]
print("CHUNK audio section search...")
# Find has_audio block
idx = chunk.find("            if has_audio:")
if idx < 0:
    raise SystemExit("has_audio block not found in fade_video")
# Find the block end - look for cmd.extend H.264 after it
idx2 = chunk.find("            # 使用标准 H.264", idx)
if idx2 < 0:
    idx2 = chunk.find('            cmd.extend([\n                "-c:v", "libx264"', idx)
if idx2 < 0:
    # print surrounding
    print(repr(chunk[idx:idx+800]))
    raise SystemExit("end of audio block not found")

old_audio = chunk[idx:idx2]
print("OLD AUDIO BLOCK:")
print(old_audio[:500])
print("---")

new_audio = '''            if has_audio:
                if audio_fade and (float(fade_in_length or 0) > 0 or float(fade_out_length or 0) > 0):
                    audio_filters = []
                    if fade_in_length > 0:
                        audio_filters.append(f"afade=t=in:st=0:d={fade_in_length}")
                    if fade_out_length > 0:
                        audio_fade_out_start = max(0, video_length - fade_out_length)
                        audio_filters.append(f"afade=t=out:st={audio_fade_out_start}:d={fade_out_length}")
                    if audio_filters:
                        cmd.extend(["-af", ",".join(audio_filters)])
                        print(f"🔊 添加音频淡变滤镜: {','.join(audio_filters)}")
                    cmd.extend(self._get_audio_encode_args())
                else:
                    # 只淡画面：音轨原样重编码（配声模式或未勾选同时淡变声音）
                    cmd.extend(self._get_audio_encode_args())
                    print("🔊 保留原声音轨（不施加 afade）")

'''

chunk2 = chunk[:idx] + new_audio + chunk[idx2:]
text2 = text2[:start] + chunk2 + text2[next_def:]

# Also update the print at end that mentions audio
# Find audio_info block in fade_video
# Optional - leave as is if complex

fp.write_text(text2, encoding="utf-8")
print("ffmpeg_processor fade_video patched")
