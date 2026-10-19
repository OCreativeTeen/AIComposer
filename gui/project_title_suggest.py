"""项目名称建议：按场景内容用本机 Strata 生成 3 个项目名，再在一个小窗里选（当前名称在最前）。

STORY 窗（智能生成之后）和魔法工作流（双击「标题」）共用这里的 ``suggest_project_titles`` 和
``ask_project_title``。改名本身由调用方按各自原有的保存路径完成。
"""
from __future__ import annotations

import json
import queue
import re
import threading
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable

SCENE_TEXT_FIELDS = (
    "caption", "visual", "speaking", "voiceover", "scene_narration", "narration_content", "narration", "content",
)
SCENE_TEXT_MAX_CHARS = 6000
TITLE_MAX_CHARS = 60
_CJK = re.compile(r"[\u3400-\u9fff]")


def scenes_text_for_titles(scenes, max_chars: int = SCENE_TEXT_MAX_CHARS) -> str:
    """所有场景的文字内容（讲话、旁白、叙事、标题、描述），去掉 <N> 标记，截到 max_chars。"""
    parts: list[str] = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        for key in SCENE_TEXT_FIELDS:
            val = scene.get(key)
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            text = re.sub(r"<\s*\d+(?:\.\d+)?\s*>", " ", str(val or ""))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                parts.append(text)
    out = "\n".join(parts)
    return out[:max_chars].rstrip()


def content_is_chinese(text: str) -> bool:
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if _CJK.match(c)) / len(letters) >= 0.2


def _clean_title(raw: str) -> str:
    t = str(raw or "").strip()
    t = re.sub(r"^\s*(?:[-*•·]+|\(?\d+[.)、:：]|（\d+）|第[一二三1-3]个?[:：、]?)\s*", "", t)
    t = re.sub(r"^(?:标题|名称|项目名称?|title|name)\s*\d*\s*[:：]\s*", "", t, flags=re.I)
    t = t.strip().strip("\"'“”‘’「」『』《》【】*`").strip()
    t = re.sub(r"\s+", " ", t)
    return t


def parse_title_suggestions(text: str, n: int = 3, exclude: str = "") -> list[str]:
    """从 LLM 回答里取出项目名：JSON 数组 / {"titles": [...]} / 每行一个都行。去重、去掉和当前名称一样的。"""
    raw = str(text or "")
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"```(?:json)?", "", raw, flags=re.I).strip()
    items: list = []
    m = re.search(r"\[.*\]", raw, flags=re.S)
    candidates = [m.group(0)] if m else []
    m2 = re.search(r"\{.*\}", raw, flags=re.S)
    if m2:
        candidates.append(m2.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand)
        except ValueError:
            continue
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        if isinstance(data, list):
            for x in data:
                if isinstance(x, dict):
                    x = x.get("title") or x.get("name") or next((v for v in x.values() if isinstance(v, str)), "")
                if isinstance(x, str):
                    items.append(x)
        if items:
            break
    if not items:
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.endswith((":", "：")):
                continue
            items.extend(p for p in re.split(r"\s*[|｜/]\s*(?=\S)", line) if p) if line.count("|") >= 2 else items.append(line)
    out: list[str] = []
    seen = {(exclude or "").strip().casefold()} if exclude else set()
    for x in items:
        t = _clean_title(x)
        if not t or len(t) > TITLE_MAX_CHARS or t.casefold() in seen:
            continue
        seen.add(t.casefold())
        out.append(t)
        if len(out) >= n:
            break
    return out


def _title_prompt(chinese: bool) -> str:
    lang = "Chinese (简体中文)" if chinese else "the same language as the content"
    limit = "at most 16 Chinese characters" if chinese else "at most 8 words"
    return (
        "You name video projects. Read the scene content below and propose exactly 3 concise project titles "
        f"that match what it is about. Write them in {lang}. Each title is {limit}. "
        "Make the 3 titles different from each other. No numbering, no quotes, no explanation. "
        'Return only a JSON array of 3 strings, for example ["…", "…", "…"].'
    )


def suggest_project_titles(scenes, current: str = "", n: int = 3, source_text: str = "") -> list[str]:
    """本机 Strata（llm_api.MODEL_SIMPLE）出 n 个项目名。失败或没内容就抛 RuntimeError。不开手动窗口。

    给了 ``source_text``（分析报告）就用它，否则用场景内容。
    """
    text = (source_text or "").strip()
    if text:
        text = text[:SCENE_TEXT_MAX_CHARS].rstrip()
    else:
        text = scenes_text_for_titles(scenes)
    if not text:
        raise RuntimeError("没有场景内容，不能生成项目名称。")
    import utility.llm_api as llm_api

    api = llm_api.LLMApi(llm_api.MODEL_SIMPLE)
    api.manual_fallback = False
    answer = api.generate_text(_title_prompt(content_is_chinese(text)), text)
    titles = parse_title_suggestions(answer or "", n=n, exclude=current)
    if not titles:
        raise RuntimeError("Strata 没有返回可用的项目名称。")
    return titles


def ask_project_title(
    parent,
    *,
    current: str,
    scenes,
    on_chosen: Callable[[str], None],
    title: str = "项目名称建议",
    source_text: str = "",
) -> tk.Toplevel:
    """选项目名称的小窗：当前名称在最前（默认选中），后面是 3 个建议；可以直接改写。

    建议在后台线程生成，界面不卡；失败时只留当前名称并显示原因。选了和当前不同的名称才调用 ``on_chosen(name)``。
    """
    current = (current or "").strip()
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.resizable(True, False)
    main = ttk.Frame(dlg, padding=12)
    main.pack(fill=tk.BOTH, expand=True)
    ttk.Label(main, text="选一个项目名称，或者直接改写：").pack(anchor=tk.W)
    listbox = tk.Listbox(main, height=4, width=56, activestyle="dotbox", exportselection=False)
    listbox.pack(fill=tk.X, pady=(6, 6))
    choices = [current or "（当前没有名称）"]
    listbox.insert(tk.END, f"{choices[0]}  （当前）")
    listbox.selection_set(0)
    name_var = tk.StringVar(value=current)
    entry = ttk.Entry(main, textvariable=name_var, width=58)
    entry.pack(fill=tk.X)
    _from_report = bool((source_text or "").strip())
    status = tk.Label(
        main,
        text="正在根据分析报告生成建议…" if _from_report else "正在根据场景内容生成建议…",
        fg="#1a4fa0",
        anchor="w",
        justify=tk.LEFT,
    )
    status.pack(fill=tk.X, pady=(6, 0))
    bar = ttk.Frame(main)
    bar.pack(fill=tk.X, pady=(10, 0))
    done = [False]

    def _pick(_e=None):
        sel = listbox.curselection()
        if not sel:
            return
        i = sel[0]
        name_var.set(current if i == 0 else choices[i])

    def _ok(_e=None):
        name = (name_var.get() or "").strip()
        done[0] = True
        dlg.destroy()
        if name and name != current:
            on_chosen(name)

    def _cancel(_e=None):
        done[0] = True
        dlg.destroy()

    listbox.bind("<<ListboxSelect>>", _pick)
    listbox.bind("<Double-Button-1>", lambda e: (_pick(), _ok()))
    ttk.Button(bar, text="确定", command=_ok).pack(side=tk.RIGHT)
    ttk.Button(bar, text="取消", command=_cancel).pack(side=tk.RIGHT, padx=(0, 6))
    dlg.bind("<Return>", _ok)
    dlg.bind("<Escape>", _cancel)
    dlg.protocol("WM_DELETE_WINDOW", _cancel)
    try:
        dlg.config(cursor="watch")
    except tk.TclError:
        pass

    results: queue.Queue = queue.Queue()

    def _work():
        try:
            results.put(("ok", suggest_project_titles(scenes, current, source_text=source_text)))
        except Exception as exc:  # noqa: BLE001
            results.put(("err", str(exc)))

    def _poll():
        if done[0]:
            return
        try:
            kind, payload = results.get_nowait()
        except queue.Empty:
            dlg.after(150, _poll)
            return
        try:
            dlg.config(cursor="")
            if kind == "ok":
                for t in payload:
                    choices.append(t)
                    listbox.insert(tk.END, t)
                status.config(text=f"已生成 {len(payload)} 个建议（本机 Strata）。", fg="#0a6b0a")
            else:
                status.config(text=f"建议没有生成：{payload}\n可以保留当前名称，或直接改写。", fg="#b00020")
        except tk.TclError:
            pass

    threading.Thread(target=_work, daemon=True, name="title-suggest").start()
    dlg.after(150, _poll)
    try:
        dlg.update_idletasks()
        x = parent.winfo_rootx() + 120
        y = parent.winfo_rooty() + 120
        dlg.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass
    entry.focus_set()
    dlg._title_suggest = {"choices": choices, "name_var": name_var, "listbox": listbox, "pick": _pick, "ok": _ok, "cancel": _cancel, "status": status}
    return dlg
