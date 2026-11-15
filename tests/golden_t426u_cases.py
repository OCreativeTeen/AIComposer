"""t426u: 旧路径（不走档位的组合）的金样本：这些输出在 t426u 前后必须一字不差。"""
from __future__ import annotations

SPEAK = "<1> 你今天怎麼來了？ <2> 想你了。"
STYLE = "三维卡通 (Pixar-Art-Cartoon)"


def cases():
    from tests.test_video_speaker_semantics import _install_stubs, _scene

    _install_stubs()
    import config_prompt as cp

    sc = _scene(SPEAK)
    return {
        "h3_speak_actor": lambda: cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none", text="keywords",
                                                     style=STYLE, region="中东", era="古巴比伦", seconds=9.0),
        "h3_speak_no_actor": lambda: cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="none",
                                                        text="erase", style=STYLE, use_actor=False, fyi="慢慢走过来"),
        "h3_talk_audio": lambda: cp.build_h3_prompt([_scene(SPEAK)], language="zh", audio_mode="talk", style=STYLE,
                                                    seconds=6.0),
        "flow_speak": lambda: cp.build_video_flow_prompt(
            frames="one", background="none", evolve="keep", visual_style=STYLE, scene_content=[_scene(SPEAK)],
            language="zh", narrative="story", text="keywords", use_visual=True, use_speaking=True, use_actor=True,
            story_style="story_speak"),
        "flow_story_no_actor": lambda: cp.build_video_flow_prompt(
            frames="one", background="none", evolve="keep", visual_style=STYLE, scene_content=[_scene(SPEAK)],
            language="zh", narrative="story", text="express", use_visual=True, use_speaking=False, use_actor=False,
            story_style="story_act", speaking_as_story=True),
        "fyi_only_grok": lambda: cp.build_video_fyi_only_prompt(frames="one", evolve="keep", visual_style=STYLE,
                                                                text="keywords", duration="12s", fyi="镜头可以移动"),
        "no_subtitle_first_line": lambda: cp.ensure_video_no_subtitle_first_line("integrated_multimodal_description: x"),
    }
