# Audio Transcription Tab

## Overview

The Audio Transcription tab is a new feature in the Magic Tools GUI that allows users to transcribe audio files directly using the Whisper model. This tab provides a user-friendly interface with drag & drop functionality and visual feedback.

## Features

### Visual Interface
- **Drop Zone**: A visually appealing drop zone featuring the `wave_sound.png` image from the media folder
- **Drag & Drop**: Support for dragging audio files directly onto the drop zone
- **Click Selection**: Fallback option to click the drop zone to select files manually
- **Visual Feedback**: The drop zone changes appearance when files are dragged over it

### File Support
Supported audio formats:
- MP3 (.mp3)
- WAV (.wav)
- M4A (.m4a)
- OGG (.ogg)
- FLAC (.flac)
- AAC (.aac)
- WMA (.wma)

### Language Support
- **Auto Detection**: Automatically detect the language in the audio
- **Manual Selection**: Choose from supported languages:
  - English (en)
  - Chinese Simplified (zh)
  - Chinese Traditional (tw)
  - Japanese (ja)
  - Korean (ko)
  - Spanish (es)
  - French (fr)
  - German (de)
  - Russian (ru)
  - Arabic (ar)
  - Hindi (hi)
  - Portuguese (pt)

### Output Files
The transcription process generates two output files in the `PUBLISH_PATH` directory:

1. **Subtitle File (.srt)**: Contains the transcribed text with timestamps in SRT format
   - Filename: `{audio_filename}.srt`
   - Format: Standard SRT subtitle format with numbered entries and timestamps

2. **Text File (.txt)**: Contains the transcribed text without timestamps
   - Filename: `{audio_filename}.txt`
   - Format: Plain text with line breaks for readability

## Usage

### Method 1: Drag & Drop
1. Open the "音频转录" (Audio Transcription) tab
2. Drag an audio file from your file explorer onto the drop zone
3. The file path will be displayed in the "音频文件" field
4. Select the language (or leave as "auto" for automatic detection)
5. Click "开始转录" to start the transcription process

### Method 2: Manual Selection
1. Open the "音频转录" (Audio Transcription) tab
2. Click on the drop zone or the "选择文件" button
3. Browse and select an audio file
4. Select the language (or leave as "auto" for automatic detection)
5. Click "开始转录" to start the transcription process

### Progress Monitoring
- Real-time logging in the output area shows:
  - File selection confirmation
  - Transcription progress
  - Completion status
  - Output file locations
  - Any errors that occur

## Technical Implementation

### Dependencies
- **tkinterdnd2**: For drag & drop functionality (optional, with fallback)
- **Pillow**: For image handling (wave_sound.png)
- **faster_whisper**: For audio transcription
- **pathlib**: For file path handling

### Core Components
- **MagicWorkflow**: Integrates with the existing workflow system
- **AudioTranscriber**: Uses the existing `transcribe_with_whisper` method
- **Threading**: Transcription runs in background thread to prevent GUI freezing
- **Error Handling**: Comprehensive error handling with user-friendly messages

### File Processing
```python
# Example of how files are processed
file_stem = Path(audio_path).stem
script_path = f"{config.PUBLISH_PATH}/{file_stem}.srt"
text_path = f"{config.PUBLISH_PATH}/{file_stem}.txt"

workflow.transcriber.transcribe_with_whisper(
    script_path, 
    text_path, 
    audio_path, 
    current_language
)
```

## Integration

The audio transcription tab integrates seamlessly with the existing Magic Tools GUI:

- **Language Settings**: Uses the global language setting from the top of the GUI
- **Workflow Integration**: Leverages the existing `MagicWorkflow` class
- **Consistent UI**: Follows the same design patterns as other tabs
- **Status Updates**: Updates the main status bar during transcription

## Error Handling

The tab includes comprehensive error handling:

- **File Validation**: Checks if selected files exist and are valid audio formats
- **Language Validation**: Ensures selected languages are supported
- **Transcription Errors**: Catches and displays transcription errors
- **File System Errors**: Handles permission and path issues
- **Dependency Errors**: Graceful fallback if tkinterdnd2 is not available

## Future Enhancements

Potential improvements for future versions:

1. **Batch Processing**: Support for multiple audio files
2. **Progress Bar**: Visual progress indicator for long transcriptions
3. **Preview**: Audio playback with transcription overlay
4. **Export Options**: Additional output formats (VTT, JSON, etc.)
5. **Custom Models**: Option to select different Whisper model sizes
6. **Post-processing**: Text correction and formatting options

## Troubleshooting

### Common Issues

1. **Drag & Drop Not Working**
   - Ensure tkinterdnd2 is installed: `pip install tkinterdnd2`
   - Use the "选择文件" button as a fallback

2. **Image Not Displaying**
   - Check that `media/wave_sound.png` exists
   - The interface will show a fallback emoji if the image is missing

3. **Transcription Fails**
   - Verify the audio file is not corrupted
   - Check that the file format is supported
   - Ensure sufficient disk space in the PUBLISH_PATH directory

4. **Language Detection Issues**
   - Try selecting a specific language instead of "auto"
   - Ensure the audio quality is good enough for transcription

### Performance Tips

- Use shorter audio files for faster processing
- Ensure good audio quality for better transcription accuracy
- Close other applications to free up system resources
- Use SSD storage for faster file I/O 