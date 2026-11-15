"""t426u: 档位提示词需要的全部输入，从生场视频对话框的选择打包成一个对象（模板只读这里）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class H3Context:
    profile: str
    style: str = ""
    camera: str = "none"
    text: str = "erase"  # 说明文字：keep / erase / keywords / express
    start_image: str = ""
    visual: str = ""  # 场景描述（勾了才有；可能是中文）
    story: str = ""  # 讲话当故事内容（可能是中文）
    fyi: str = ""  # 注意 / FYI（可能是中文）
    use_actor: bool = False
    cast: list = field(default_factory=list)  # 勾了人物：英文身份，如 "young woman"
    place: str = ""  # 勾了人物且勾了背景：英文地域 · 时代
    stage_line: str = ""  # 勾了人物且勾了背景：故事舞台（英文才用）

    def slots(self) -> dict:
        """要让 Strata 译成英文画面方向的几段（空的不算）。"""
        return {k: v for k, v in (("visual", self.visual), ("story", self.story), ("fyi", self.fyi)) if v.strip()}


def _clean_fyi(fyi: str) -> str:
    import config_prompt as cp

    text = cp.strip_caption_lines(fyi or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("注意")]
    return " ".join(" ".join(lines).split())


def make_h3_context(profile: str, scenes, *, style: str = "", camera: str = "none", text: str = "erase",
                    start_image: str = "", use_visual: bool = False, story_on: bool = False, fyi: str = "",
                    use_actor: bool = False, region: str = "", era: str = "", stage=None) -> H3Context:
    """M0 不用任何场景资料（只按图 + FYI）；M1 用场景描述 / 讲话当故事内容 / 人物（勾了才用）。
    地域 · 时代 · 舞台只在勾了人物时写（t424u），调用方没勾背景就传空。"""
    import config_prompt as cp
    from prompt_profiles.select import M0_FAITHFUL

    scs = [s for s in (scenes or []) if isinstance(s, dict)]
    ctx = H3Context(profile=profile, style=style or "", camera=camera or "none", text=text or "erase",
                    start_image=start_image or "", fyi=_clean_fyi(fyi))
    if profile == M0_FAITHFUL:
        return ctx
    if use_visual:
        ctx.visual = " ".join(str(s.get("visual") or "").strip() for s in scs).strip()
    if story_on:
        ctx.story = " ".join(t for t in (cp.speaking_story_text(s) for s in scs) if t).strip()
    ctx.use_actor = bool(use_actor)
    if use_actor:
        rows = cp._scene_speakers(scs[0]) if scs else []
        ctx.cast = [cp._speaker_identity(r)[1] or "person" for r in rows]
        place = cp.SETTING_PLACES.get((region or "").strip()) or {}
        reg_en = place.get("en") or ""
        era_en = next((en for name, en in place.get("eras", []) if name == (era or "").strip()), "")
        ctx.place = era_en if (reg_en and reg_en in era_en) else ", ".join(x for x in (era_en, reg_en) if x)
        try:
            from utility import story_stage as _ss

            line = _ss.short_line(stage) if stage else ""
        except Exception:  # noqa: BLE001
            line = ""
        from prompt_profiles.validate import has_cjk

        ctx.stage_line = line if (line and not has_cjk(line)) else ""
    return ctx
