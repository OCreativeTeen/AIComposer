"""t426u: 生场视频提示词按组合分档（prompt profiles）。

每个档位有自己的提示词模板、Strata 说明和校验，不再把所有组合塞进一个通用提示词。
现在只有 MiniMax 的两个无讲话档：
  M0 忠实动画（场景描述 / 讲话 / 讲话当故事内容 / 人物都没勾，只按 FYI）
  M1 无讲话场景（讲话没勾或勾了讲话当故事内容，场景音频不作为说话 / 唱歌）
别的组合仍走 config_prompt 里原来的构建函数，输出不变。PROMPT_PROFILES_ENABLED = False 时全部走旧代码。
"""
PROMPT_PROFILES_ENABLED = True

from prompt_profiles.select import M0_FAITHFUL, M1_SILENT, PROFILE_LABELS, select_h3_profile  # noqa: E402,F401
