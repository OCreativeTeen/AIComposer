"""t447u: STORY 窗里的「内容主题 / FYI」（取代原来的「导向说明」）。

存在这一条（video_detail）里：
  * ``story_fyi``：当前这条 FYI 文字；
  * ``story_fyi_history``：历史（新的在前，最多 FYI_MAX 条，和图片 / 视频提示窗同一种）；
  * ``story_fyi_include``：「写入提示词」勾不勾。
场景生成用它填模板里的 ``{instruction}``；节目生成放在提示词最前面并写进 NotebookLM 的内容主题。
建项目时 ``story_fyi`` 跟着复制进项目配置。
"""

from __future__ import annotations

FYI_KEY = "story_fyi"
FYI_HISTORY_KEY = "story_fyi_history"
FYI_INCLUDE_KEY = "story_fyi_include"
FYI_MAX = 6
# 旧数据里可能存过的导向说明字段（CLI 工作流的 instruction）
LEGACY_KEYS = ("instruction", "scene_instruction", "guide_instruction")

def _clean(items) -> list:
    out = []
    for item in items or []:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s and s not in out:
            out.append(s)
    return out[:FYI_MAX]


def load_story_fyi(video_detail) -> tuple:
    """→ (history, include)。没存过 FYI 时把旧的导向说明（instruction）迁过来。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    hist = vd.get(FYI_HISTORY_KEY)
    hist = _clean(hist) if isinstance(hist, list) else []
    cur = str(vd.get(FYI_KEY) or "").strip()
    if cur:
        hist = _clean([cur] + hist)
    if not hist:
        pp = vd.get("project_profile") if isinstance(vd.get("project_profile"), dict) else {}
        for src in (vd, pp):
            for key in (FYI_KEY,) + LEGACY_KEYS:
                val = src.get(key) if isinstance(src, dict) else None
                if isinstance(val, str) and val.strip():
                    hist = [val.strip()]
                    break
            if hist:
                break
    inc = vd.get(FYI_INCLUDE_KEY)
    return hist, (True if inc is None else bool(inc))


def store_story_fyi(video_detail, text: str, history=None, include: bool = True) -> bool:
    """写回这一条（和 project_profile，若有）。返回有没有变化。"""
    if not isinstance(video_detail, dict):
        return False
    text = (text or "").strip()
    hist = _clean(([text] if text else []) + list(history or []))
    changed = (
        str(video_detail.get(FYI_KEY) or "") != text
        or _clean(video_detail.get(FYI_HISTORY_KEY) or []) != hist
        or video_detail.get(FYI_INCLUDE_KEY, True) != bool(include)
    )
    video_detail[FYI_KEY] = text
    video_detail[FYI_HISTORY_KEY] = hist
    video_detail[FYI_INCLUDE_KEY] = bool(include)
    pp = video_detail.get("project_profile")
    if isinstance(pp, dict):
        pp[FYI_KEY] = text
    return changed


def effective_fyi(video_detail) -> str:
    """勾了「写入提示词」才返回 FYI 文字。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    hist, inc = load_story_fyi(vd)
    if not inc:
        return ""
    return str(vd.get(FYI_KEY) or (hist[0] if hist else "")).strip()


class FyiTextAdapter:
    """让 FYI 控件看起来像原来的导向说明 Text：``get("1.0", END)`` / ``delete`` / ``insert``。

    get 只在勾了「写入提示词」时返回文字（场景生成 {instruction} 用）。"""

    def __init__(self, get_text, set_text, include_var=None):
        self._get_text = get_text
        self._set_text = set_text
        self._include_var = include_var

    def _included(self) -> bool:
        if self._include_var is None:
            return True
        try:
            return bool(self._include_var.get())
        except Exception:  # noqa: BLE001
            return True

    def get(self, *_args) -> str:
        if not self._included():
            return ""
        return (self._get_text() or "") + "\n"

    def delete(self, *_args) -> None:
        self._set_text("")

    def insert(self, _index, value) -> None:
        self._set_text(str(value or ""))
        if self._include_var is not None and str(value or "").strip():
            try:
                self._include_var.set(True)
            except Exception:  # noqa: BLE001
                pass
