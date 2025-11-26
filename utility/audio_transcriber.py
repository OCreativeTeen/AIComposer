from faster_whisper import WhisperModel
from datetime import datetime, timedelta
import re
import os
import json
import textwrap
import zhconv
from .llm_api import LLMApi
import config
from pathlib import Path
from pyannote.audio import Pipeline
import torch
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any
from utility.file_util import safe_file, read_json, write_json


class AudioTranscriber:

    def __init__(self, pid, language, ffmpeg_audio_processor, model_size, device):
        self.pid = pid
        self.language = language
        
        self.ffmpeg_audio_processor = ffmpeg_audio_processor
        self.model_size = model_size
        self.device = device
        self.llm_small = LLMApi(model=LLMApi.GEMINI_2_0_FLASH)

        device = torch.device("cuda") 
        hf_token = os.getenv("HF_TOKEN", "")
        self.pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization",
            use_auth_token=hf_token
        )
        self.pipeline.to(device)


    def fetch_srt_from_json(self, script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        srt_content = ""
        for i, segment in enumerate(segments):
            srt_content += f"{i+1}\n{segment['start']} --> {segment['end']}\n{segment['content']}\n\n"
        return srt_content


    def fetch_text_from_json(self, script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
        text_content = "\n".join([segment["content"] for segment in segments])
        return text_content


    def transcribe_to_file(self, audio_path, language, min_sentence_duration, max_sentence_duration):
        script_json = self.transcribe_with_whisper(audio_path, language, min_sentence_duration, max_sentence_duration)

        script_path = f"{config.get_project_path(self.pid)}/{Path(audio_path).stem}.srt.json"
        write_json(script_path, script_json)  
        return script_path


    def transcribe_with_whisper(self, audio_path, language, min_sentence_duration, max_sentence_duration) -> List[Dict[str, Any]]:
        script_path = f"{config.get_project_path(self.pid)}/{self.pid}.srt.json"
        if safe_file(script_path):
            return read_json(script_path)

        start_time = datetime.now().strftime("%H:%M:%S")
        print(f"🔍 开始转录：{audio_path} ~ {start_time}")
        audio_duration = self.ffmpeg_audio_processor.get_duration(audio_path)

        #model = whisper.load_model(self.model_size, device="cuda") 
        #result = model.transcribe(mp3_path)
        model = WhisperModel(self.model_size, device=self.device, compute_type="int8_float16")
        lang = language
        if lang=="zh-CN" or lang=="tw":
            lang ="zh"
        srt_segments, _ = model.transcribe(audio_path, beam_size=5, language=lang)
        srt_segments = [obj.__dict__ for obj in srt_segments]  # ← 修复：生成器转列表，支持 len() 和索引、重复遍历

        char_time_pair = []
        text_content = ""
        end_time = 0.0
        for segment in srt_segments:
            if end_time > 0 and segment['start']!=end_time: # not the 1st item
                segment['start'] = end_time # fix start time (must == end of last item)
            segment_time = segment['end'] - segment['start']
            segment_text = self.chinese_convert(segment['text'], language)
            normalize_text = self.normalize_text(segment_text)
            # Distribute time evenly across characters
            if len(normalize_text) > 0:
                time_per_char = segment_time / len(normalize_text)
                for i, char in enumerate(normalize_text):
                    char_time_pair.append((char, segment['start'] + i * time_per_char))
            text_content += segment_text + " "
            end_time = segment['end']

        json_path = f"{config.get_project_path(self.pid)}/transcriber.debug.1.json"
        with open(json_path, 'w') as f:
            json.dump(srt_segments, f, indent=4)

        print(f"调试信息: char_time_pair数量={len(char_time_pair)}")

        sentences = self.reorganize_text_content(text_content, language)
        print(f"调试信息: 重组后句子数量={len(sentences)}")
        if len(sentences) == 0:
            return None

        reorganized = []
        current_char_index = 0
        
        content = ""
        for i, sentence in enumerate(sentences):
            print(f"处理句子 {i+1}/{len(sentences)}: {sentence[:50]}...")
            content += sentence + "\n"
            # Find best matching position for this sentence
            start_pos, end_pos = self.find_best_match_position(
                sentence, char_time_pair, current_char_index
            )
            
            # Get timing information
            if start_pos < len(char_time_pair):
                sentence_start_time = char_time_pair[start_pos][1]
            else:
                sentence_start_time = char_time_pair[-1][1] if char_time_pair else 0.0
            
            if end_pos < len(char_time_pair):
                sentence_end_time = char_time_pair[end_pos][1]
            else:
                sentence_end_time = char_time_pair[-1][1] if char_time_pair else sentence_start_time
            
            # Ensure time progression
            if reorganized:
                sentence_start_time = max(sentence_start_time, reorganized[-1]['end'])
            # Ensure end time is after start time
            if sentence_end_time <= sentence_start_time:
                sentence_end_time = sentence_start_time + 1.0  # Add 1 second as minimum
            
            reorganized_segment = {
                'start': sentence_start_time,
                'end': sentence_end_time,
                'content': sentence
            }
            reorganized.append(reorganized_segment)
            # Update search position for next sentence
            current_char_index = end_pos
            print(f"句子时间: {sentence_start_time:.2f}s - {sentence_end_time:.2f}s")

        with open(f"{config.get_temp_path(self.pid)}/transcribe_{Path(audio_path).stem}.txt", "w", encoding="utf-8") as f:
            f.write(content)

        print(f"调试信息: reorganized数量={len(reorganized)}")

        merged_segments = self.merge_sentences(reorganized, language, min_sentence_duration, max_sentence_duration)
        print(f"调试信息: merged数量={len(merged_segments)}")

        # 4. Run diarization
        diarization = self.pipeline(audio_path)
        merged_segments = self.assign_speakers(merged_segments, diarization)

        if len(merged_segments) > 0:
            if merged_segments[0]['start'] != 0.0:
                merged_segments[0]['start'] = 0.0
            if merged_segments[-1]['end'] != audio_duration:
                merged_segments[-1]['end'] = audio_duration
            end_time = 0.0
            for segment in merged_segments:
                if end_time > 0 and segment['start'] != end_time: # not the 1st item
                    segment['start'] = end_time # fix start time (must == end of last item)
                segment['duration'] = segment['end'] - segment['start']
                end_time = segment['end']
             
        write_json(script_path, merged_segments)  
        return merged_segments


    def merge_sentences(self, segments, language, min_sentence_duration, max_sentence_duration):
        system_prompt = config.SCENARIO_BUILD_SYSTEM_PROMPT.format(language=language, min_sentence_duration=min_sentence_duration, max_sentence_duration=max_sentence_duration)
        user_prompt = json.dumps(segments, ensure_ascii=False, indent=2)

        response = self.llm_small.openai_completion(
            messages=[
                self.llm_small.create_message("system", system_prompt),
                self.llm_small.create_message("user", user_prompt)
            ],
            temperature=0.1,
            max_tokens=8000,
            top_p=0.9,
            stream=False
        )

        content = self.llm_small.parse_response(response)
        if not content:
            raise Exception("翻译API返回了空内容")

        # 提取JSON数组
        merged_segments = self.llm_small.parse_json_response(content)

        return merged_segments


    def assign_speakers(self, segments, diarization) -> List[Dict[str, Any]]:
        output = []
        first_speaker = None

        diarization_list = []
        for turn, _, spk in diarization.itertracks(yield_label=True):
            diarization_list.append([turn.start, turn.end, spk])

        if len(diarization_list) > 0:
            diarization_list[0][0] = 0.0
            diarization_list[-1][1] = segments[-1]["end"]
            first_speaker = diarization_list[0][2]
        else:
            return segments

        for seg in segments:
            speaker = first_speaker
            for turn in diarization_list:
                if float(seg["start"])+0.5 >= float(turn[0]) and float(seg["end"])-0.5 <= float(turn[1]):
                    speaker = turn[2]
                    break

            output.append({
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "duration": float(seg["end"]) - float(seg["start"]),
                "speaker": speaker,
                "content": seg["content"]
            })

        return output


    def reorganize_text_content(self, text, language):
        system_prompt = config.SRT_REORGANIZATION_SYSTEM_PROMPT.format(language=language)
        prompt = config.SRT_REORGANIZATION_USER_PROMPT.format(text=text)

        response = self.llm_small.openai_completion(
            messages=[
                self.llm_small.create_message("system", system_prompt),
                self.llm_small.create_message("user", prompt)
            ],
            temperature=0.1,
            max_tokens=8000,
            top_p=0.9,
            stream=False
        )

        content = self.llm_small.parse_response(response)
        if not content:
            raise Exception("翻译API返回了空内容")

        content = self.chinese_convert(content, language)
        # 去掉开头和结尾的空格, 换行符
        content = content.strip()
        content = re.sub(r'\n+', ' ', content)

        sentences = self._split_text_into_sentences(content, language)
        return sentences


    def src_to_text(self, script_path, text_path):
        """
        从SRT字幕文件中提取纯文本，过滤掉时间戳和序号
        
        SRT格式示例:
        1
        00:00:01,000 --> 00:00:04,000
        Hello world
        
        2
        00:00:05,000 --> 00:00:08,000
        Another subtitle line
        """
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if not content.strip():
                print(f"⚠️ 字幕文件为空: {script_path}")
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write("")
                return
            
            content = content.strip()
            lines = content.split("\n")
            
            # Filter out lines that are:
            # 1. Empty lines
            # 2. Lines starting with [ or ( (special markers like [Music], (applause))
            # 3. Pure digit lines (sequence numbers like "1", "2", "3")
            # 4. Timestamp lines (containing --> like "00:00:01,000 --> 00:00:04,000")
            # 5. Lines that only contain punctuation or special characters
            filtered_content = []
            
            for line in lines:
                line = line.strip()
                
                # Skip empty lines
                if not line:
                    continue
                    
                # Skip lines starting with brackets or parentheses (sound effects, music notes, etc.)
                if line.startswith("[") or line.startswith("("):
                    continue
                    
                # Skip pure digit lines (sequence numbers)
                if line.isdigit():
                    continue
                    
                # Skip timestamp lines
                if "-->" in line:
                    continue
                    
                # Skip lines that only contain special characters or punctuation
                if all(not c.isalnum() for c in line):
                    continue
                
                # This is actual subtitle text
                filtered_content.append(line)
            
            # Write the filtered content
            with open(text_path, "w", encoding="utf-8") as f:
                f.write("\n".join(filtered_content))
            
            print(f"✅ 已提取字幕文本: {len(lines)}行 -> {len(filtered_content)}行文本 -> {text_path}")
            
        except Exception as e:
            print(f"❌ 提取字幕文本失败: {e}")
            # Create empty file on error
            with open(text_path, "w", encoding="utf-8") as f:
                f.write("")


    def _split_text_into_sentences(self, text_content, language):
        """将文本按句子分割"""
        # 根据语言设置不同的句子结束符
        sentence_endings = r'[。！？.!?]'
        
        # 按句子结束符分割
        sentences = re.split(f'({sentence_endings})', text_content)
        
        # 重新组合句子（包含标点符号）
        result = []
        for i in range(0, len(sentences) - 1, 2):
            if i + 1 < len(sentences):
                sentence = sentences[i].strip() + sentences[i + 1].strip()
                if sentence:
                    sentence = sentence.replace("」", "").replace("「", "").replace("：「", ":").replace("\n", " ").replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("  ", " ")
                    result.append(sentence.strip())
        
        return result
    
    
    def _find_sentence_start_time(self, sentence, char_time_pair, start_char_index):
        """
        模糊匹配句子开始位置，返回开始时间
        """
        if not sentence or not char_time_pair:
            return 0.0
        
        # 移除句子开头的空格和标点符号
        sentence_clean = sentence.strip()
        if not sentence_clean:
            return 0.0
        
        # 从start_char_index开始，最多向前看5个字符
        for offset in range(6):  # 0到5
            check_index = start_char_index + offset
            if check_index >= len(char_time_pair):
                break
            
            char, time = char_time_pair[check_index]
            # 检查是否匹配句子的第一个字符
            if char == sentence_clean[0]:
                return time
        
        # 如果没有找到匹配，返回当前位置的时间
        if start_char_index < len(char_time_pair):
            return char_time_pair[start_char_index][1]
        return 0.0
    
    def _find_sentence_end_time(self, sentence, char_time_pair, start_char_index):
        """
        模糊匹配句子结束位置，返回结束时间和新的字符索引位置
        """
        if not sentence or not char_time_pair:
            return 0.0, start_char_index
        
        sentence_clean = sentence.strip()
        if not sentence_clean:
            return 0.0, start_char_index
        
        # 计算句子长度（不包括空格）
        sentence_chars = [c for c in sentence_clean if not c.isspace()]
        
        # 从start_char_index开始寻找句子的结束位置
        current_char_index = start_char_index
        matched_chars = 0
        
        # 遍历char_time_pair，尝试匹配句子中的每个字符
        while current_char_index < len(char_time_pair) and matched_chars < len(sentence_chars):
            char, time = char_time_pair[current_char_index]
            
            # 跳过空格
            if char.isspace():
                current_char_index += 1
                continue
            
            # 检查是否匹配句子中的字符
            if matched_chars < len(sentence_chars) and char == sentence_chars[matched_chars]:
                matched_chars += 1
            else:
                # 模糊匹配：如果当前字符不匹配，尝试向前看最多5个字符
                fuzzy_matched = False
                for fuzzy_offset in range(1, 6):  # 向前看1-5个字符
                    fuzzy_index = current_char_index + fuzzy_offset
                    if fuzzy_index < len(char_time_pair):
                        fuzzy_char, _ = char_time_pair[fuzzy_index]
                        if not fuzzy_char.isspace() and matched_chars < len(sentence_chars) and fuzzy_char == sentence_chars[matched_chars]:
                            # 找到模糊匹配，更新当前索引
                            current_char_index = fuzzy_index
                            matched_chars += 1
                            fuzzy_matched = True
                            break
                
                # 如果没有找到模糊匹配，继续下一个字符
                if not fuzzy_matched:
                    current_char_index += 1
                    continue
            
            current_char_index += 1
            
            # 如果已经匹配了整个句子，返回当前位置的时间
            if matched_chars >= len(sentence_chars):
                if current_char_index <= len(char_time_pair):
                    return time, current_char_index
        
        # 如果没有完全匹配，返回估算的结束时间
        if current_char_index > 0 and current_char_index <= len(char_time_pair):
            return char_time_pair[min(current_char_index - 1, len(char_time_pair) - 1)][1], current_char_index
        
        return 0.0, start_char_index

    def _is_sentence_complete(self, target_sentence, accumulated_text):
        """检查累积的文本是否已包含完整句子"""
        # 移除标点符号和空格进行比较
        target_clean = re.sub(r'[^\w]', '', target_sentence.lower())
        accumulated_clean = re.sub(r'[^\w]', '', accumulated_text.lower())
        
        # 如果累积文本包含目标句子的80%以上内容，认为匹配
        if len(target_clean) == 0:
            return True
        
        # 计算相似度
        common_chars = 0
        for char in target_clean:
            if char in accumulated_clean:
                common_chars += 1
                accumulated_clean = accumulated_clean.replace(char, '', 1)
        
        similarity = common_chars / len(target_clean)
        return similarity >= 0.8
    

    def chinese_convert_file(self, output_path, source_path, language):
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = self.chinese_convert(content, language)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)


    def chinese_convert(self, text, language):
        if language == "zh":
            # Convert to simplified Chinese
            return zhconv.convert(text, 'zh-cn')
        elif language == "tw":
            # Convert to traditional Chinese
            return zhconv.convert(text, 'zh-tw')
        else:
            return text


    def translate_text(self, text, source_language, target_language):
        if source_language == target_language:
            return self.chinese_convert(text, target_language)
        
        if (source_language == "zh" or source_language == "tw") and (target_language == "zh" or target_language == "tw"):
            return self.chinese_convert(text, target_language)
        
        try:
            system_prompt = config.TRANSLATION_SYSTEM_PROMPT.format(
                source_language=config.LANGUAGES[source_language],
                target_language=config.LANGUAGES[target_language]
            )
            prompt = config.TRANSLATION_USER_PROMPT.format(
                source_language=config.LANGUAGES[source_language],
                target_language=config.LANGUAGES[target_language],
                text=text
            )

            response = self.llm_small.openai_completion(
                messages=[
                    self.llm_small.create_message("system", system_prompt),
                    self.llm_small.create_message("user", prompt)
                ],
                temperature=0.1,
                max_tokens=8000,
                top_p=0.9,
                stream=False
            )
            
            content = self.llm_small.parse_response(response)
            if not content:
                raise Exception("翻译API返回了空内容")
            return content.strip()
                
        except Exception as e:
            raise Exception(f"Translation failed: {e}")



    def translate_file(self, file_path, target_language, output_path=None):
        """
        Translate content of a file using Ollama's qwen2.5:7b model
        
        Args:
            file_path (str): Path to the input file
            target_language (str): Target language (e.g., 'English', 'Chinese', 'Spanish', etc.)
            output_path (str, optional): Path for the output file. If None, creates a new file with '_translated' suffix
            
        Returns:
            str: Path to the translated file
        """
        try:
            # Check if input file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Input file not found: {file_path}")
            
            # Read the input file
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            if not content.strip():
                raise ValueError("Input file is empty")
            
            # Translate the content
            translated_content = self.translate_text(content, target_language)
            
            # Determine output path
            if output_path is None:
                file_dir = os.path.dirname(file_path)
                file_name = os.path.basename(file_path)
                name, ext = os.path.splitext(file_name)
                output_path = os.path.join(file_dir, f"{name}_translated_{target_language.lower().replace(' ', '_')}{ext}")
            
            # Write translated content to output file
            with open(output_path, 'w', encoding='utf-8') as file:
                file.write(translated_content)
            
            return output_path
            
        except FileNotFoundError as e:
            raise e
        except Exception as e:
            raise Exception(f"File translation failed: {e}")



    def translate_srt_file(self, source_path, source_language, target_language, output_path):
        """
        Translates the text in an SRT file while preserving timestamps.
        """
        with open(source_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()

        if (source_language == "zh" or source_language == "tw") and (target_language == "zh" or target_language == "tw"):
            self.chinese_convert_file(output_path, source_path, target_language)
            return

        if source_language == target_language:
            return

        lines = re.split(r'\n', srt_content.strip())
        translated_blocks = []

        # Batch processing for translation efficiency
        accumulated_text = []
        accumulated_lines = []
        current_batch_length = 0
        
        for line in lines:
            if len(line) < 2:
                continue

            try:
                text_to_translate = line
                
                if text_to_translate.strip():
                    # Add to current batch
                    accumulated_text.append(text_to_translate.strip())
                    accumulated_lines.append(line)
                    current_batch_length += len(text_to_translate.strip())
                    
                    # Process batch when it exceeds 512 characters
                    if current_batch_length > 256:
                        # Translate the batch
                        batch_text = "\n".join(accumulated_text)
                        translated_batch = self.translate_text(batch_text, source_language, target_language)
                        
                        # Split translated result back into lines
                        translated_lines = translated_batch.split('\n')
                        
                        # Add translated lines to result
                        for i, translated_line in enumerate(translated_lines):
                            if i < len(accumulated_lines):
                                translated_blocks.append(f"\n{translated_line.strip()}")
                        
                        # Handle any extra translated lines
                        for i in range(len(accumulated_lines), len(translated_lines)):
                            translated_blocks.append(f"\n{translated_lines[i].strip()}")
                        
                        # Reset batch
                        accumulated_text = []
                        accumulated_lines = []
                        current_batch_length = 0
                else:
                    translated_blocks.append(f"\n{line}")
                    
            except Exception as e:
                translated_blocks.append(line) # keep original block on error
        
        # Process remaining batch if any
        if accumulated_text:
            try:
                batch_text = "\n".join(accumulated_text)
                translated_batch = self.translate_text(batch_text, source_language, target_language)
                translated_lines = translated_batch.split('\n')
                
                for i, translated_line in enumerate(translated_lines):
                    if i < len(accumulated_lines):
                        translated_blocks.append(f"\n{translated_line.strip()}")
                
                # Handle any extra translated lines
                for i in range(len(accumulated_lines), len(translated_lines)):
                    translated_blocks.append(f"\n{translated_lines[i].strip()}")
                    
            except Exception as e:
                # If batch translation fails, fall back to original lines
                for line in accumulated_lines:
                    translated_blocks.append(f"\n{line}")

        translated_srt = "\n\n".join(translated_blocks)

        if output_path is None:
            file_dir = os.path.dirname(source_path)
            file_name = os.path.basename(source_path)
            name, ext = os.path.splitext(file_name)
            output_path = os.path.join(file_dir, f"{name}_{target_language}{ext}")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(translated_srt)

        return output_path


    # ImprovedSentenceTiming 
    def normalize_text(self, text):
        """Normalize text by removing punctuation and extra spaces for matching"""
        # Remove both English and Chinese punctuation
        # Chinese punctuation: 。！？，、；：""''（）【】《》〈〉「」『』〔〕
        # English punctuation: .,!?;:"'()[]<>{}
        normalized = re.sub(r'[^\w\s\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', '', text)
        # Remove common punctuation explicitly (both English and Chinese)
        punctuation_pattern = r'[。！？，、；：""''（）【】《》〈〉「」『』〔〕\.!?;:"\'()\[\]<>{}，]'
        normalized = re.sub(punctuation_pattern, '', normalized)
        normalized = re.sub(r'\s+', '', normalized)  # Remove all whitespace
        return normalized.lower()


    def find_best_match_position(self, sentence, char_time_pair, start_search_index=0, match_length=5):
        """
        Find the best matching position for a sentence in char_time_pair using fuzzy matching
        """
        sentence_normalized = self.normalize_text(sentence)
        
        if not sentence_normalized:
            return start_search_index, start_search_index
        
        # Extract text from char_time_pair for comparison
        char_text = ''.join([char for char, time in char_time_pair])
        char_normalized = self.normalize_text(char_text)
        
        best_match_ratio = 0
        best_start_pos = start_search_index
        best_end_pos = start_search_index
        
        # Try different starting positions around the expected location
        search_window = min(50, len(char_time_pair) - start_search_index)
        
        for offset in range(max(0, start_search_index - 10), 
                          min(len(char_normalized), start_search_index + search_window)):
            
            # Try matching with different lengths
            for end_offset in range(offset + len(sentence_normalized) - 5,
                                  min(len(char_normalized), offset + len(sentence_normalized) + 5)):
                
                if end_offset <= offset:
                    continue
                    
                candidate = char_normalized[offset:end_offset]
                
                # Calculate similarity ratio
                ratio = SequenceMatcher(None, sentence_normalized, candidate).ratio()
                
                # Also check if we have good partial matches at start/end
                if len(sentence_normalized) >= match_length and len(candidate) >= match_length:
                    start_ratio = SequenceMatcher(None, 
                                                sentence_normalized[:match_length], 
                                                candidate[:match_length]).ratio()
                    end_ratio = SequenceMatcher(None, 
                                              sentence_normalized[-match_length:], 
                                              candidate[-match_length:]).ratio()
                    
                    # Weighted score considering overall match and start/end matches
                    combined_ratio = 0.5 * ratio + 0.25 * start_ratio + 0.25 * end_ratio
                else:
                    combined_ratio = ratio
                
                if combined_ratio > best_match_ratio:
                    best_match_ratio = combined_ratio
                    best_start_pos = self._map_normalized_to_original(char_text, offset)
                    best_end_pos = self._map_normalized_to_original(char_text, end_offset)
        
        # Fallback if no good match found
        if best_match_ratio < 0.6:
            print(f"警告: 句子匹配质量较低 (ratio={best_match_ratio:.2f}): {sentence[:30]}...")
            # Use approximate position based on character count
            estimated_end = min(len(char_time_pair), start_search_index + len(sentence))
            return start_search_index, estimated_end
        
        return best_start_pos, best_end_pos
    
    def _map_normalized_to_original(self, original_text, normalized_position):
        """Map position in normalized text back to original text position"""
        original_pos = 0
        normalized_pos = 0
        
        for i, char in enumerate(original_text):
            if normalized_pos >= normalized_position:
                return original_pos
            
            # Count non-punctuation, non-whitespace characters
            if re.match(r'\w', char):
                normalized_pos += 1
            
            original_pos += 1
        
        return min(original_pos, len(original_text))
    
