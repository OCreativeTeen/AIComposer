from utility.ffmeg_processor import FfmpegProcessor
from utility.ffmeg_audio_processor import FfmpegAudioProcessor
from config import channel_config
import config
import os


def main():
    pid = "project_20250707_1708"
    channel_id = "travel_zh"
    ffmpeg_processor = FfmpegProcessor(pid, "tw") 

    for i in range(0,3):
        v1 = f"{config.get_channel_path(channel_id)}/host_video/starting_china_{i}.mp4"
        v1 = ffmpeg_processor.reverse_video(v1)
        os.replace(v1, f"{config.get_channel_path(channel_id)}/host_video/starting_china_{i}_reverse.mp4")


def main_1():
    pid = "project_20250707_1708"
    channel_id = "travel_zh"
    ffmpeg_processor = FfmpegProcessor(pid, "tw") 

    for i in range(0,3):
        v1 = f"{config.get_channel_path(channel_id)}/host_video/P{i}_1.mp4"
        v2 = f"{config.get_channel_path(channel_id)}/host_video/P{i}_2.mp4"

        v1 = ffmpeg_processor.reverse_video(v1)
        v_concat = f"{config.get_channel_path(channel_id)}/host_video/P{i}_concat.mp4"
        ffmpeg_processor._concat_videos_demuxer(v_concat, [v1, v2], 1920, 1080, True)

    v1 = f"{config.get_channel_path(channel_id)}/host_video/P{i}_1.mp4"
    v2 = f"{config.get_channel_path(channel_id)}/host_video/P{i}_2.mp4"
    v = ffmpeg_processor._concat_videos_demuxer_simple([{"path":v1,"transition":"fade", "duration":1.0}, {"path":v2,"transition":"fade", "duration":1.0}])
    os.replace(v, f"{config.get_channel_path(channel_id)}/host_video/P{i}_concat_transition.mp4")

if __name__ == "__main__":
    main() 