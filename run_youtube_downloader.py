from utility.youtube_downloader import YoutubeDownloader
import os
from pathlib import Path
from config import channel_config
from utility.audio_transcriber import AudioTranscriber
from utility.ffmeg_processor import FfmpegProcessor
import sys
import config


def main():
    if len(sys.argv) != 2:
        print("Usage: python run_youtube_downloader.py <pid>")
        sys.exit(1)
    
    pid = sys.argv[1]
    
    publish_path = config.PUBLISH_PATH + "/"
    final_video_path = f"{publish_path}/{pid}_final.mp4"
    
    # 检查视频文件是否存在
    if not os.path.exists(final_video_path):
        print(f"Error: Video file not found at {final_video_path}")
        print("Please make sure the video generation process has completed successfully.")
        sys.exit(1)
    
    print(f"Found video file: {final_video_path}")
    
    # 检查字幕文件
    script_path = f"{publish_path}/{pid}.srt"
    script_path_fixed = f"{publish_path}/{pid}_fixed.srt"

    language = "tw"
    title = "聊斋新话 : 真心梨"
    description = "聊斋新话"
    channel = "strange_zh"

    program_path = f"{config.BASE_MEDIA_PATH}/program/{channel}"

    downloader = YoutubeDownloader(pid)


    ffmpeg_processor = FfmpegProcessor(pid, "tw")
    starting_video_length = ffmpeg_processor.get_duration(f"{program_path}/starting.mp4")
    

    transcriber = AudioTranscriber(pid, language, ffmpeg_processor, model_size="small", device="cuda")



    downloader.upload_video(final_video_path, title=title, description=description, language=language, script_path=script_path_fixed, secret_key=channel_config[channel]["channel_key"], categoryId="22", tags=None, privacy="unlisted")


if __name__ == "__main__":
    main() 