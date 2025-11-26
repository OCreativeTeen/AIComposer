from utility.audio_transcriber import AudioTranscriber
import os
from pathlib import Path


def main():
    pid = "20250601_18"
    language = "zh"
    audio_path =  os.path.abspath(f"data/{pid}/travel_banff_stereo.aac")

    transcriber = AudioTranscriber(pid, language, model_size="small", device="cuda")

    transcriber.transcribe_to_file(audio_path, language, 10, 26)

if __name__ == "__main__":
    main() 