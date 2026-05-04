"""WhisperX 转写器（与 ``audio_transcriber.py`` 的 simple Whisper 版接口对齐）。

特性：
    1. 使用 WhisperX 加载本地模型（faster-whisper 后端）转写。
    2. 词级对齐（``whisperx.align``），便于 diarize 与 NLP 重切。
    3. 可选 pyannote diarization，默认 ``min_speakers=2 / max_speakers=2``。
    4. 可选按句末标点（。！？!?…）的 NLP 重切超长片段；句末缺失时退回到「，；：」等软断点。
    5. 输出 JSON：``[{start, end, duration, caption, speaker?}]``，与现有管线兼容。

CLI 示例::

    python -m utility.audio_transcriber_x path/to/audio.mp3 -l zh \
        --diarize --min-speakers 2 --max-speakers 2 \
        --hf-token <HF_TOKEN>
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import whisperx  # type: ignore

    _WHISPERX_IMPORT_ERROR: Optional[BaseException] = None
except Exception as _e:  # noqa: BLE001 - 仅记录原因，运行时再抛
    whisperx = None  # type: ignore[assignment]
    _WHISPERX_IMPORT_ERROR = _e


_DEFAULT_MIN_SENTENCE_DURATION = 3.0
_DEFAULT_MAX_SENTENCE_DURATION = 22.0

# 句末标点（中英）：NLP 重切的硬断点
_SENTENCE_END_PUNCT = set("。！？!?…")
# 软断点：当一个超长片段内找不到句末标点时，退回到这些标点
_SOFT_BREAK_PUNCT = set("，,；;：:")


def resolve_whisperx_device_compute(device: str, compute_type: str) -> Tuple[str, str]:
    """若调用方写 ``device=\"cuda\"`` 但当前 PyTorch 未编 CUDA / 无 GPU，则回落 ``cpu`` + ``int8``。

    避免出现 ``AssertionError: Torch not compiled with CUDA enabled``。
    """
    raw_dev = (device or "cpu").strip()
    d = raw_dev.lower()
    ct = (compute_type or "int8").strip()
    if not d.startswith("cuda"):
        return raw_dev, ct
    try:
        import torch

        if torch.cuda.is_available():
            return raw_dev, ct
    except Exception:
        pass
    print(
        "[WARN] 已请求 CUDA，但当前 PyTorch 无可用 CUDA（常见：安装了 cpu 版 torch）。"
        "WhisperX 改用 CPU（较慢），compute_type=int8。"
    )
    return "cpu", "int8"


def remove_transcribe_cache_for_audio_path(audio_path: str) -> None:
    """删除与音频同名的 .srt.json 缓存，便于强制重新转写。"""
    if not audio_path:
        return
    if audio_path.endswith(".mp3"):
        cache_file = audio_path[: -len(".mp3")] + ".srt.json"
    elif audio_path.endswith(".wav"):
        cache_file = audio_path[: -len(".wav")] + ".srt.json"
    else:
        return
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
        except OSError:
            pass


class AudioTranscriberX:
    """WhisperX 转写器（带 diarization 与 NLP 重切）。"""

    def __init__(
        self,
        model_size: str = "medium",
        device: str = "cuda",
        compute_type: str = "float16",
        *,
        hf_token: Optional[str] = None,
        batch_size: int = 16,
    ) -> None:
        if whisperx is None:
            raise RuntimeError(
                f"whisperx 未安装：{_WHISPERX_IMPORT_ERROR!r}\n"
                "请先 `pip install whisperx`（依赖 pyannote.audio；diarization 需 HF token）。"
            )
        self.model_size = model_size
        device, compute_type = resolve_whisperx_device_compute(device, compute_type)
        self.device = device
        self.compute_type = compute_type
        self.batch_size = batch_size
        self.hf_token = (
            hf_token
            or os.environ.get("HUGGINGFACE_HUB_TOKEN")
            or os.environ.get("HF_TOKEN")
        )

        self.model = whisperx.load_model(
            model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        print(
            f"[OK] WhisperX 模型加载成功 "
            f"(model={model_size}, device={self.device}, compute_type={self.compute_type})"
        )

        # 对齐 / Diarize 模型按需懒加载
        self._align_cache: Dict[str, Tuple[Any, Any]] = {}
        self._diarize_pipeline = None

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    def transcribe(
        self,
        audio_path: str,
        language: str,
        *,
        diarize: bool = True,
        min_speakers: Optional[int] = 2,
        max_speakers: Optional[int] = 2,
        min_duration: float = _DEFAULT_MIN_SENTENCE_DURATION,
        max_duration: float = _DEFAULT_MAX_SENTENCE_DURATION,
        nlp_resplit: bool = True,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """转写 → 对齐 → 可选 diarize → NLP 重切 → 合并/规整 → 落盘 JSON。

        返回 ``(segments, transcribe_file)``。``segments`` 形如::

            [{"start": 0.0, "end": 3.2, "duration": 3.2, "caption": "...", "speaker": "SPEAKER_00"}, ...]
        """
        lang = self._normalize_language(language)
        root, _ = os.path.splitext(audio_path)
        transcribe_file = root + ".srt.json"

        try:
            print(f"[INFO] 开始转录 (language={lang}) — {audio_path}")
            audio = whisperx.load_audio(audio_path)
            result = self.model.transcribe(
                audio,
                batch_size=self.batch_size,
                language=lang,
            )
            detected_lang = result.get("language") or lang
            segments = result.get("segments") or []
            print(f"[INFO] 初步转写完成：{len(segments)} 段；language={detected_lang}")

            # 1) 词级对齐
            aligned = self._align(audio, segments, detected_lang)
            segments = aligned.get("segments") or segments
            word_segments = aligned.get("word_segments") or []

            # 2) 可选 diarization：min/max 默认都是 2，避免猜错说话人数
            if diarize:
                speaker_segments = self._diarize(
                    audio,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                )
                if speaker_segments is not None:
                    assigned = whisperx.assign_word_speakers(
                        speaker_segments, {"segments": segments}
                    )
                    segments = assigned.get("segments") or segments

            # 3) 转为内部 dict 列表
            srt_segments = self._to_srt_segments(segments)

            # 4) NLP 重切：把超长 segment 按句末标点拆开
            if nlp_resplit and word_segments:
                srt_segments = self._resplit_by_nlp_punct(
                    srt_segments, word_segments, max_duration
                )

            # 5) 合并过短/过长，规整 start/end
            srt_segments = self.merge_sentences(srt_segments, min_duration, max_duration)

            with open(transcribe_file, "w", encoding="utf-8") as f:
                json.dump(srt_segments, f, ensure_ascii=False, indent=2)
            print(f"[OK] 已写入 {transcribe_file}（{len(srt_segments)} 段）")
            return srt_segments, transcribe_file
        except Exception as e:  # noqa: BLE001 - 顶层兜底，保持与 simple 版同样的接口
            print(f"[ERROR] 转录失败: {type(e).__name__}: {e}")
        return [], ""

    # ------------------------------------------------------------------
    # 对齐 / diarize / NLP
    # ------------------------------------------------------------------
    def _align(self, audio: Any, segments: List[Dict[str, Any]], language: str) -> Dict[str, Any]:
        if not segments:
            return {"segments": [], "word_segments": []}
        try:
            if language not in self._align_cache:
                model_a, metadata = whisperx.load_align_model(
                    language_code=language, device=self.device
                )
                self._align_cache[language] = (model_a, metadata)
            model_a, metadata = self._align_cache[language]
            aligned = whisperx.align(
                segments,
                model_a,
                metadata,
                audio,
                self.device,
                return_char_alignments=False,
            )
            return aligned
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] 对齐失败，跳过：{type(e).__name__}: {e}")
            return {"segments": segments, "word_segments": []}

    def _diarize(
        self,
        audio: Any,
        *,
        min_speakers: Optional[int],
        max_speakers: Optional[int],
    ) -> Any:
        try:
            if self._diarize_pipeline is None:
                if not self.hf_token:
                    print("[WARN] 未提供 HuggingFace token（hf_token / HF_TOKEN），跳过 diarization")
                    return None
                # WhisperX 新版将 DiarizationPipeline 放在 whisperx.diarize，且参名为 token（旧版为 use_auth_token）
                dp_cls = getattr(whisperx, "DiarizationPipeline", None)
                if dp_cls is None:
                    dp_cls = importlib.import_module("whisperx.diarize").DiarizationPipeline
                try:
                    self._diarize_pipeline = dp_cls(
                        token=self.hf_token,
                        device=self.device,
                    )
                except TypeError:
                    self._diarize_pipeline = dp_cls(
                        use_auth_token=self.hf_token,
                        device=self.device,
                    )
            kwargs: Dict[str, Any] = {}
            if min_speakers is not None:
                kwargs["min_speakers"] = int(min_speakers)
            if max_speakers is not None:
                kwargs["max_speakers"] = int(max_speakers)
            print(f"[INFO] 运行 diarization（{kwargs or '自动'}）…")
            return self._diarize_pipeline(audio, **kwargs)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] diarization 失败：{type(e).__name__}: {e}")
            return None

    @staticmethod
    def _normalize_language(language: str) -> str:
        if language in ("zh-CN", "tw", "zh-TW", "zh-tw"):
            return "zh"
        return language or "en"

    @staticmethod
    def _to_srt_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            item: Dict[str, Any] = {
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "caption": text,
            }
            sp = seg.get("speaker")
            if sp:
                item["speaker"] = str(sp)
            out.append(item)
        return out

    # ------------------------------------------------------------------
    # NLP 重切：按词级标点切分超长片段
    # ------------------------------------------------------------------
    def _resplit_by_nlp_punct(
        self,
        segments: List[Dict[str, Any]],
        word_segments: List[Dict[str, Any]],
        max_duration: float,
    ) -> List[Dict[str, Any]]:
        if not segments or not word_segments:
            return segments

        new_segments: List[Dict[str, Any]] = []
        for seg in segments:
            seg_dur = float(seg.get("end", 0.0)) - float(seg.get("start", 0.0))
            if seg_dur <= max_duration:
                new_segments.append(seg)
                continue

            words = self._words_in_range(word_segments, seg["start"], seg["end"])
            if not words:
                new_segments.append(seg)
                continue

            hard_breaks = [i for i, w in enumerate(words) if self._has_punct(w, _SENTENCE_END_PUNCT)]
            break_indices = hard_breaks or [
                i for i, w in enumerate(words) if self._has_punct(w, _SOFT_BREAK_PUNCT)
            ]
            if not break_indices:
                new_segments.append(seg)
                continue

            speaker = seg.get("speaker")
            chunk_start_idx = 0
            chunk_started_t = float(seg["start"])

            for bi in break_indices:
                bi_end_t = float(
                    words[bi].get("end") or words[bi].get("start") or chunk_started_t
                )
                # 只有当前块已经撑到 max/2 才在此断开，避免切得太碎
                if bi_end_t - chunk_started_t < max_duration / 2.0:
                    continue

                text = self._join_words(words[chunk_start_idx : bi + 1])
                if not text:
                    chunk_start_idx = bi + 1
                    continue

                item: Dict[str, Any] = {
                    "start": chunk_started_t,
                    "end": bi_end_t,
                    "caption": text,
                }
                if speaker:
                    item["speaker"] = speaker
                new_segments.append(item)

                chunk_start_idx = bi + 1
                if chunk_start_idx >= len(words):
                    chunk_started_t = bi_end_t
                    break
                next_w = words[chunk_start_idx]
                chunk_started_t = float(next_w.get("start") or bi_end_t)

            # 收尾片段
            if chunk_start_idx < len(words):
                tail_text = self._join_words(words[chunk_start_idx:])
                if tail_text:
                    tail_item: Dict[str, Any] = {
                        "start": chunk_started_t,
                        "end": float(seg["end"]),
                        "caption": tail_text,
                    }
                    if speaker:
                        tail_item["speaker"] = speaker
                    new_segments.append(tail_item)
        return new_segments

    @staticmethod
    def _words_in_range(
        words: List[Dict[str, Any]], t0: float, t1: float
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for w in words:
            ws = w.get("start")
            we = w.get("end")
            if ws is None and we is None:
                continue
            ws_f = float(ws) if ws is not None else float(we)  # type: ignore[arg-type]
            we_f = float(we) if we is not None else ws_f
            mid = (ws_f + we_f) / 2.0
            if t0 - 0.05 <= mid <= t1 + 0.05:
                out.append(w)
        return out

    @staticmethod
    def _join_words(words: List[Dict[str, Any]]) -> str:
        return "".join((w.get("word") or "") for w in words).strip()

    @staticmethod
    def _has_punct(word: Dict[str, Any], punct_set: set) -> bool:
        s = (word.get("word") or "").strip()
        if not s:
            return False
        return s[-1] in punct_set

    # ------------------------------------------------------------------
    # 合并 / 规整 start/end（与 simple 版逻辑一致；同 speaker 才合并）
    # ------------------------------------------------------------------
    def merge_sentences(
        self,
        input_segments: List[Dict[str, Any]],
        min_sentence_duration: float,
        max_sentence_duration: float,
    ) -> List[Dict[str, Any]]:
        print("[INFO] 合并句子…")
        i = 0
        while i < len(input_segments):
            if i + 1 < len(input_segments):
                cur = input_segments[i]
                nxt = input_segments[i + 1]
                cur_dur = float(cur["end"]) - float(cur["start"])
                nxt_dur = float(nxt["end"]) - float(nxt["start"])
                # 同一发言人才合并；不同 speaker 不合并以保留 diarization 边界
                same_speaker = cur.get("speaker") == nxt.get("speaker")

                if cur_dur > max_sentence_duration:
                    i += 1
                    continue

                if same_speaker and (
                    cur_dur < min_sentence_duration or nxt_dur < min_sentence_duration
                ):
                    cur["caption"] = (cur.get("caption") or "") + (nxt.get("caption") or "")
                    cur["end"] = nxt["end"]
                    input_segments.pop(i + 1)
                    # 不递增 i：合并后的当前段可能继续与新的下一段合并
                else:
                    i += 1
            else:
                i += 1

        final_segments: List[Dict[str, Any]] = []
        for seg in input_segments:
            item: Dict[str, Any] = {
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "duration": float(seg["end"]) - float(seg["start"]),
                "caption": seg["caption"],
            }
            sp = seg.get("speaker")
            if sp:
                item["speaker"] = sp
            final_segments.append(item)

        if final_segments:
            if final_segments[0]["start"] != 0.0:
                final_segments[0]["start"] = 0.0
            end_time = 0.0
            for seg in final_segments:
                if end_time > 0 and seg["start"] != end_time:
                    seg["start"] = end_time
                seg["duration"] = seg["end"] - seg["start"]
                end_time = seg["end"]

        print(f"[OK] 合并完成，共 {len(final_segments)} 个片段")
        return final_segments


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WhisperX 音频转写（支持 diarization）")
    p.add_argument("audio_path", help="音频文件路径 (.mp3 / .wav)")
    p.add_argument("-l", "--language", default="zh", help="语言代码 (默认: zh)")
    p.add_argument(
        "--model-size",
        default="small",
        help="WhisperX 模型大小（如 tiny / small / medium / large-v3）",
    )
    p.add_argument("--device", default="cuda", help="设备：cuda / cpu (默认 cuda)")
    p.add_argument(
        "--compute-type",
        default="float16",
        help="cuda 推荐 float16；cpu 推荐 int8",
    )
    p.add_argument("--diarize", action="store_true", help="启用 pyannote diarization（需 HF token）")
    p.add_argument(
        "--min-speakers",
        type=int,
        default=2,
        help="diarization 最小说话人数 (默认 2，避免猜错)",
    )
    p.add_argument(
        "--max-speakers",
        type=int,
        default=2,
        help="diarization 最大说话人数 (默认 2)",
    )
    p.add_argument(
        "--min-duration",
        type=float,
        default=_DEFAULT_MIN_SENTENCE_DURATION,
        help="合并字幕片段时的最小时长 (秒)",
    )
    p.add_argument(
        "--max-duration",
        type=float,
        default=_DEFAULT_MAX_SENTENCE_DURATION,
        help="合并 / NLP 重切时的最大时长 (秒)",
    )
    p.add_argument(
        "--no-nlp-resplit",
        action="store_true",
        help="禁用按句末标点的 NLP 重切",
    )
    p.add_argument(
        "--hf-token",
        default=None,
        help="HuggingFace token（diarization 必需；亦可通过环境变量 HF_TOKEN 提供）",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    transcriber = AudioTranscriberX(
        model_size=args.model_size,
        device=args.device,
        compute_type=args.compute_type,
        hf_token=args.hf_token,
    )
    segments, out = transcriber.transcribe(
        args.audio_path,
        args.language,
        diarize=args.diarize,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        nlp_resplit=not args.no_nlp_resplit,
    )
    if not out:
        print("❌ 失败")
        return 1
    print(f"✅ 已写入: {out} ({len(segments)} 段)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
