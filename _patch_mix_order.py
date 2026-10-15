# -*- coding: utf-8 -*-
from pathlib import Path

path = Path("gui/workflow/wf_media_import.py")
text = path.read_text(encoding="utf-8")

# 1) Across scenes: fade first_video BEFORE the loop mix when audio_fade
old_across = '''        offset = 0.0
        written = 0
        for index, target in enumerate(targets):
            video = first_video if index == 0 else (target.get("clip") or "").strip()
'''
# Need more context - fade first_video before loop if audio_fade
old_setup = '''        offset = 0.0
        written = 0
        for index, target in enumerate(targets):
            video = first_video if index == 0 else (target.get("clip") or "").strip()
            if not video or not os.path.isfile(video):
                break
'''

new_setup = '''        # 混音+声音淡变：先把导入片的画面/原声淡好，再逐场混旁白。
        fi = float(audio.get("video_fade_in") or 0.0)
        fo = float(audio.get("video_fade_out") or 0.0)
        af = bool(audio.get("audio_fade", True))
        if af and (fi >= 0.05 or fo >= 0.05):
            first_video = self._fade_finished_clip(first_video, fi, fo, audio_fade=True)
            fi, fo, af = 0.0, 0.0, False
        offset = 0.0
        written = 0
        for index, target in enumerate(targets):
            video = first_video if index == 0 else (target.get("clip") or "").strip()
            if not video or not os.path.isfile(video):
                break
'''
if old_setup not in text:
    raise SystemExit("across setup not found")
text = text.replace(old_setup, new_setup, 1)

# After mix on index 0, only apply remaining video-only fade if any
old_post = '''            if index == 0:
                mixed = self._fade_finished_clip(
                    mixed,
                    float(audio.get("video_fade_in") or 0.0),
                    float(audio.get("video_fade_out") or 0.0),
                    audio_fade=bool(audio.get("audio_fade", True)),
                )
                raw = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(mixed) or raw
'''
new_post = '''            if index == 0 and (fi >= 0.05 or fo >= 0.05):
                # 仅剩画面淡变（声音已在混音前处理，或未勾选同时淡变声音）
                mixed = self._fade_finished_clip(mixed, fi, fo, audio_fade=False)
                raw = self.workflow.ffmpeg_audio_processor.extract_audio_from_video(mixed) or raw
'''
if old_post not in text:
    raise SystemExit("across post fade not found")
text = text.replace(old_post, new_post, 1)

# 2) Single-scene audio mix in apply_editor_pick: fade original before blend when audio_fade
old_audio_block = '''        if audio:
            if audio.get("use") == "mix":
                mp4, mixed_wav = self._blend_audio_into_video(mp4, audio)
            else:
                mp4, mixed_wav = self._mix_audio_onto_video(mp4, audio)
            if mixed_wav:
                wav = mixed_wav
        # 混音(overlay)：先淡导入原声(+画面)，再在 simple_replacement 里与场景声混合。
        # 配声：只淡画面（audio_fade=False）。原声：淡画面+原声。
        faded = self._fade_finished_clip(
            mp4,
            float(pick.get("video_fade_in") or 0.0),
            float(pick.get("video_fade_out") or 0.0),
            audio_fade=bool(pick.get("audio_fade")),
        )
'''

new_audio_block = '''        fi = float(pick.get("video_fade_in") or 0.0)
        fo = float(pick.get("video_fade_out") or 0.0)
        af = bool(pick.get("audio_fade"))
        if audio:
            if audio.get("use") == "mix":
                # 混音：先淡导入片原声(+画面)，再混入所选旁白；之后不再对混音结果 afade。
                if af and (fi >= 0.05 or fo >= 0.05):
                    pre = self._fade_finished_clip(mp4, fi, fo, audio_fade=True)
                    if pre and os.path.isfile(pre):
                        mp4 = pre
                    fi, fo, af = 0.0, 0.0, False
                mp4, mixed_wav = self._blend_audio_into_video(mp4, audio)
            else:
                # 配声替换：只允许画面淡变
                af = False
                mp4, mixed_wav = self._mix_audio_onto_video(mp4, audio)
            if mixed_wav:
                wav = mixed_wav
        # 导入视频原声/混音(radio)：此处先淡，再交给 simple_replacement 混合场景声。
        # 配声：audio_fade=False，只淡画面。
        faded = self._fade_finished_clip(mp4, fi, fo, audio_fade=af)
'''
if old_audio_block not in text:
    raise SystemExit("audio block not found")
text = text.replace(old_audio_block, new_audio_block, 1)

path.write_text(text, encoding="utf-8")
print("mix order patched")
