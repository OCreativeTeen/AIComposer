"""t426u: 按生场视频对话框的选择挑提示词档位。没有对应档位返回 ""（走旧代码）。"""
from __future__ import annotations

M0_FAITHFUL = "minimax_m0_faithful"
M1_SILENT = "minimax_m1_silent"
PROFILE_LABELS = {M0_FAITHFUL: "MiniMax 无讲话 · 忠实动画", M1_SILENT: "MiniMax 无讲话 · 场景"}


def select_h3_profile(*, is_minimax: bool, fyi_only: bool, story_on: bool, use_speaking: bool,
                      audio_mode: str = "none", frames: str = "one", transition: bool = False,
                      enabled: bool | None = None) -> str:
    """MiniMax 单画面、不是过渡、场景音频不作为说话 / 唱歌送去时：
    什么内容都没勾 → M0；没有讲话（讲话没勾，或勾了讲话当故事内容）→ M1；有讲话 → ""（旧代码）。"""
    if enabled is None:
        from prompt_profiles import PROMPT_PROFILES_ENABLED as enabled  # noqa: N811
    if not enabled or not is_minimax or transition or frames == "two":
        return ""
    if str(audio_mode or "none") != "none":
        return ""
    if fyi_only:
        return M0_FAITHFUL
    if story_on or not use_speaking:
        return M1_SILENT
    return ""
