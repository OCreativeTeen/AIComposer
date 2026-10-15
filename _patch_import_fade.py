# -*- coding: utf-8 -*-
from pathlib import Path

path = Path("gui/workflow/wf_media_import.py")
text = path.read_text(encoding="utf-8")

old_fn = '''    def _fade_finished_clip(self, video_path: str, fade_in: float, fade_out: float) -> str:
        """成片写回之前的最后一步：画面和声音一起淡入、淡出。两项都没设就原样返回。"""
        fade_in = max(0.0, min(3.0, float(fade_in or 0.0)))
        fade_out = max(0.0, min(3.0, float(fade_out or 0.0)))
        if fade_in < 0.05 and fade_out < 0.05:
            return video_path
        if not video_path or not os.path.isfile(video_path) or not self.workflow:
            return video_path
        fp = self.workflow.ffmpeg_processor
        duration = float(fp.get_duration(video_path) or 0.0)
        if duration > 0.05 and fade_in + fade_out > duration:
            scale = duration / (fade_in + fade_out)
            fade_in *= scale
            fade_out *= scale
        faded = fp.fade_video(video_path, fade_in, fade_out)
        if faded and os.path.isfile(faded) and os.path.getsize(faded) > 0:
            return faded
        return video_path
'''

new_fn = '''    def _fade_finished_clip(
        self,
        video_path: str,
        fade_in: float,
        fade_out: float,
        audio_fade: bool = True,
    ) -> str:
        """成片写回之前：画面淡入/淡出；audio_fade 时同一时长也对音轨 afade。

        导入视频混音顺序：先对本段（导入原声）做淡变，再与旁白/场景声混合。
        配声模式应传 audio_fade=False，只淡画面。
        """
        fade_in = max(0.0, min(3.0, float(fade_in or 0.0)))
        fade_out = max(0.0, min(3.0, float(fade_out or 0.0)))
        if fade_in < 0.05 and fade_out < 0.05:
            return video_path
        if not video_path or not os.path.isfile(video_path) or not self.workflow:
            return video_path
        fp = self.workflow.ffmpeg_processor
        duration = float(fp.get_duration(video_path) or 0.0)
        if duration > 0.05:
            half = duration / 2.0
            fade_in = min(fade_in, half)
            fade_out = min(fade_out, half)
            if fade_in + fade_out > duration:
                scale = duration / (fade_in + fade_out)
                fade_in *= scale
                fade_out *= scale
        faded = fp.fade_video(video_path, fade_in, fade_out, audio_fade=bool(audio_fade))
        if faded and os.path.isfile(faded) and os.path.getsize(faded) > 0:
            return faded
        return video_path
'''

if old_fn not in text:
    # try softer match - print nearby
    i = text.find("def _fade_finished_clip")
    print(repr(text[i:i+600]))
    raise SystemExit("fn not found")
text = text.replace(old_fn, new_fn, 1)

# Update call sites to pass audio_fade from pick
# Site 1: blend across scenes
old1 = '''                mixed = self._fade_finished_clip(
                    mixed,
                    float(audio.get("video_fade_in") or 0.0),
                    float(audio.get("video_fade_out") or 0.0),
                )
'''
new1 = '''                mixed = self._fade_finished_clip(
                    mixed,
                    float(audio.get("video_fade_in") or 0.0),
                    float(audio.get("video_fade_out") or 0.0),
                    audio_fade=bool(audio.get("audio_fade", True)),
                )
'''
if old1 not in text:
    raise SystemExit("call site 1 not found")
text = text.replace(old1, new1, 1)

# Site 2: apply_editor_pick - also need to handle mix order for overlay
# Copy audio_fade onto audio dict when mix across scenes
old_copy = '''            audio["video_fade_in"] = pick.get("video_fade_in") or 0.0
            audio["video_fade_out"] = pick.get("video_fade_out") or 0.0
'''
new_copy = '''            audio["video_fade_in"] = pick.get("video_fade_in") or 0.0
            audio["video_fade_out"] = pick.get("video_fade_out") or 0.0
            audio["audio_fade"] = bool(pick.get("audio_fade"))
'''
if old_copy not in text:
    raise SystemExit("copy fades not found")
text = text.replace(old_copy, new_copy, 1)

old2 = '''        faded = self._fade_finished_clip(
            mp4,
            float(pick.get("video_fade_in") or 0.0),
            float(pick.get("video_fade_out") or 0.0),
        )
'''
new2 = '''        # 混音(overlay)：先淡导入原声(+画面)，再在 simple_replacement 里与场景声混合。
        # 配声：只淡画面（audio_fade=False）。原声：淡画面+原声。
        faded = self._fade_finished_clip(
            mp4,
            float(pick.get("video_fade_in") or 0.0),
            float(pick.get("video_fade_out") or 0.0),
            audio_fade=bool(pick.get("audio_fade")),
        )
'''
if old2 not in text:
    raise SystemExit("call site 2 not found")
text = text.replace(old2, new2, 1)

path.write_text(text, encoding="utf-8")
print("wf_media_import patched")
