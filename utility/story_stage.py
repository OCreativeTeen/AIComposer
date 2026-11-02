# -*- coding: utf-8 -*-
"""t191u: 故事舞台 —— 把要讨论的问题放进一部大家熟知的长篇经典里（红楼梦、水浒传、飘……）。

- 选了舞台（不是「不限」）时：先用本机 Strata 单独做一次「提炼舞台」，从这部作品里挑出能映照当前问题的
  人物、情节、场景和时代压力，写成 150–300 字的舞台概要（brief），另附一句英文画面说明（visual）。
- 概要存在项目配置（魔法工作流）或这一条故事（STORY 窗口）里：story_stage / story_stage_brief /
  story_stage_visual / story_stage_key（舞台名 + 主题内容的哈希，主题变了就重新提炼）。
- 场景生成、节目生成（NotebookLM 等）用完整的 STORY STAGE 段；图片 / 幻灯 / 视频提示只加一句短的。
- 「不限」= 没有舞台，什么都不加，和原来完全一样。
"""
import hashlib
import json
import re
import threading

NONE_LABEL = "不限"

# (界面名, 地域, 时代, 英文名)；地域 / 时代必须是 config_prompt.SETTING_PLACES 里的项
STAGES = [
    ("红楼梦", "中国", "清朝", "Dream of the Red Chamber (Hongloumeng)"),
    ("水浒传", "中国", "宋朝", "Water Margin (Shuihu Zhuan)"),
    ("三国演义", "中国", "东汉末三国", "Romance of the Three Kingdoms"),
    ("西游记", "中国", "唐朝", "Journey to the West"),
    ("儒林外史", "中国", "清朝", "The Scholars (Rulin Waishi)"),
    ("家（巴金）", "中国", "民国", "Family by Ba Jin"),
    ("围城", "中国", "民国", "Fortress Besieged by Qian Zhongshu"),
    ("源氏物语", "日本", "平安时代", "The Tale of Genji"),
    ("飘", "美国", "南北战争", "Gone with the Wind"),
    ("傲慢与偏见", "欧洲", "摄政时期英国", "Pride and Prejudice"),
    ("简·爱", "欧洲", "维多利亚时代", "Jane Eyre"),
    ("悲惨世界", "欧洲", "19世纪法国", "Les Misérables"),
]
_BY_NAME = {s[0]: s for s in STAGES}


def stage_names() -> list:
    return [NONE_LABEL] + [s[0] for s in STAGES]


def normalize(stage) -> str:
    s = str(stage or "").strip()
    return "" if s in ("", NONE_LABEL, "无", "none") else s


def stage_place(stage) -> tuple:
    """已知舞台 → (地域, 时代)；自己输入的作品返回 ("", "")。"""
    s = _BY_NAME.get(normalize(stage))
    return (s[1], s[2]) if s else ("", "")


def stage_en(stage) -> str:
    s = _BY_NAME.get(normalize(stage))
    return f"{s[0]} / {s[3]}" if s else normalize(stage)


def content_key(stage, topic, content="") -> str:
    h = hashlib.sha1((str(topic or "").strip() + "\n" + str(content or "").strip()[:4000]).encode("utf-8")).hexdigest()[:12]
    return f"{normalize(stage)}|{h}"


# ---------------- 取当前舞台 ----------------

def info_from(owner) -> dict:
    """owner = 项目配置 / 一条故事（也看它的 project profile）。没有舞台返回 {}。"""
    srcs = []
    if isinstance(owner, dict):
        srcs.append(owner)
        try:
            import project_manager

            pp = owner.get(project_manager.PROJECT_PROFILE_KEY)
            if isinstance(pp, dict):
                srcs.append(pp)
        except Exception:  # noqa: BLE001
            pass
    for src in srcs:
        st = normalize(src.get("story_stage"))
        if st:
            return {"stage": st, "brief": str(src.get("story_stage_brief") or "").strip(),
                    "visual": str(src.get("story_stage_visual") or "").strip(),
                    "region": str(src.get("setting_region") or "").strip(),
                    "era": str(src.get("setting_era") or "").strip()}
    return {}


def project_info() -> dict:
    try:
        import project_manager

        return info_from(project_manager.PROJECT_CONFIG)
    except Exception:  # noqa: BLE001
        return {}


# 图片 / 幻灯 / 视频提示窗口：get_place() 调用时记下来源（STORY 窗口的那一条 / 项目），窗口紧接着 capture()
_hint = {"set": False, "owner": None}


def hint(owner) -> None:
    _hint.update(set=True, owner=owner)


def capture() -> dict:
    """刚才 get_place() 来自哪里就取哪里的舞台；没有记就用当前项目。"""
    if _hint["set"]:
        owner = _hint["owner"]
        _hint.update(set=False, owner=None)
        return info_from(owner)
    return project_info()


# ---------------- 提示词里的段 ----------------

def full_block(info) -> str:
    """场景生成 / 节目生成用的 STORY STAGE 段。"""
    if not info or not info.get("stage"):
        return ""
    lines = [
        "*** STORY STAGE (chosen by the user; the whole program is staged inside this classic work)",
        f"    ** Stage: {stage_en(info['stage'])}" + (f", {info.get('era')}" if info.get("era") else "") + ".",
    ]
    if info.get("brief"):
        lines.append("    ** Stage brief (characters, episode, setting, and how it mirrors the topic):\n       "
                     + info["brief"].replace("\n", "\n       "))
    lines += [
        "    ** Discuss the topic by staging it inside this work: the problem is shown through these characters, "
        "their episodes, places and social world - the character's inner state, why they could not resolve it, "
        "and the pressures of their era - and then brought back to the viewer's life today.",
        "    ** Story people use their names from the work and stay consistent across all scenes. If a cast list is "
        "given above, keep its people and looks, and give them the roles from the stage brief.",
        "    ** Costumes, places, objects and manners belong to the world of the work. The visual style rules stay "
        "exactly as given.",
    ]
    return "\n".join(lines)


def short_line(info) -> str:
    """图片 / 视频提示里的一句（Strata 精简也要保留：以 Story stage: 开头）。"""
    if not info or not info.get("stage"):
        return ""
    vis = (info.get("visual") or "").replace(".", ",").strip(" ,;")
    era = info.get("era") or ""
    try:
        import config_prompt

        place = config_prompt.SETTING_PLACES.get(info.get("region") or "") or {}
        era = next((en for name, en in place.get("eras", []) if name == era), era)
    except Exception:  # noqa: BLE001
        pass
    # 一整句（中间不用句号），Strata 精简后 restore_direction_lines 能整句补回
    return (f"Story stage: the world of {stage_en(info['stage']).replace('.', '')}"
            + (f", {era}" if era else "") + "; "
            + (vis or "period costume, settings and manners of that work") + ".")


def label(info) -> str:
    return ("舞台：" + info["stage"]) if info and info.get("stage") else ""


# ---------------- 提炼舞台（Strata） ----------------

EXTRACT_SYSTEM = """你是心理咨询节目的编剧。用户要讨论一个心理问题 / 现象，并把它放进一部大家熟知的长篇经典作品（「舞台」）里来讲。
从这部作品里挑出最能映照这个问题的：1–3 个人物（用书里的名字）、1–2 段书里真实发生的具体情节 / 场景（写明回目或
事件，例如「黛玉葬花」「宝玉挨打」，说清谁、在哪里、做了什么、说了什么关键的话），当时的社会环境与时代压力，
并点出人物的心理状态、为什么他 / 她没能走出来、背后更深的心理根源。只用作品里真实存在的人物和情节，不要编造。回目 / 章节的序号没有把握就不写序号，只写回目名或事件名，绝不猜。
不能只写人物性格分析：情节要占一半以上的篇幅，后面拍场景、做图都要用这些情节。
输出 JSON：{"brief": "...", "visual": "..."}
- brief：150 到 300 字，用和「主题」文字相同的语言和字体（主题是简体就用简体，繁体就用繁体）。
  依次写：人物（名字 + 身份）、情节 / 场景 1–2 段（具体事件和地点）、时代与环境、它如何映照这个问题、深层心理根源。
- visual：一句英文（不超过 30 个词），写画面里人物的服装和主要场景，例如 "Qing-dynasty silk robes in the
  gardens and halls of the Jia mansion"。
只输出 JSON，不要解释。"""


def extract(stage, topic, content="", instruction="", language="", region="", era="") -> dict:
    """t193u: 先用 DeepSeek 提炼舞台概要，不可用 / 出错时退回本机 Strata；都失败抛异常。
    返回 {"brief", "visual", "key", "backend"}。"""
    st = normalize(stage)
    if not st:
        raise ValueError("没有选舞台")
    from utility import llm_api

    user = (f"舞台：{stage_en(st)}" + (f"（{region} · {era}）" if (region or era) else "") + "\n"
            + f"主题：{str(topic or '').strip()}\n"
            + (f"导向说明：{instruction.strip()}\n" if str(instruction or "").strip() else "")
            + (f"输出语言：{language}\n" if language else "")
            + ("内容摘录：\n" + str(content or "").strip()[:3000] if str(content or "").strip() else ""))
    out, backend, errs = "", "", []
    for model, name in ((llm_api.DEEPSEEK, "DeepSeek"), (llm_api.STRATA, "Strata")):
        try:
            api = llm_api.LLMApi(model)
            api.manual_fallback = False
            resp = api._chat_completions(model, [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": user},
            ])
            out = (resp.choices[0].message.content or "").strip() if resp and resp.choices else ""
            if not out:
                raise RuntimeError("返回空")
            backend = name
            break
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{name}：{exc}")
            print(f"⚠️ 提炼舞台 {name} 失败：{exc}" + ("，改用 Strata" if name == "DeepSeek" else ""))
    if not out:
        raise RuntimeError("提炼舞台失败（" + "；".join(errs) + "）")
    print(f"🎭 提炼舞台用的是 {backend}")
    brief, visual = out, ""
    m = re.search(r"\{.*\}", out, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            brief = str(d.get("brief") or "").strip() or out
            visual = str(d.get("visual") or "").strip()
        except ValueError:
            pass
    return {"brief": brief, "visual": visual, "key": content_key(st, topic, content), "backend": backend}


_KEYS = ("story_stage", "story_stage_brief", "story_stage_visual", "story_stage_key", "story_stage_source")


def _raw(owner) -> dict:
    srcs = [owner] if isinstance(owner, dict) else []
    try:
        import project_manager

        pp = owner.get(project_manager.PROJECT_PROFILE_KEY) if isinstance(owner, dict) else None
        if isinstance(pp, dict):
            srcs.append(pp)
    except Exception:  # noqa: BLE001
        pass
    for s in srcs:
        if normalize(s.get("story_stage")):
            return {k: s.get(k) or "" for k in _KEYS}
    return {}


def carry(src, dst) -> bool:
    """t191u: STORY 那一条的舞台带进项目配置。项目已有别的舞台（不是不限 / 空）就不动；返回是否改了。"""
    if not isinstance(dst, dict):
        return False
    s = _raw(src)
    if not s:
        return False
    cur = normalize(dst.get("story_stage"))
    if cur and cur != normalize(s["story_stage"]):
        return False
    if cur and dst.get("story_stage_brief") and not s.get("story_stage_brief"):
        return False
    if all((dst.get(k) or "") == s[k] for k in _KEYS):
        return False
    dst.update(s)
    return True


def store(owner, stage, result=None) -> None:
    """把舞台（和提炼结果）写进 owner；也写进它的 project profile（STORY 那一条有的话）。"""
    dests = [owner] if isinstance(owner, dict) else []
    try:
        import project_manager

        pp = owner.get(project_manager.PROJECT_PROFILE_KEY) if isinstance(owner, dict) else None
        if isinstance(pp, dict):
            dests.append(pp)
    except Exception:  # noqa: BLE001
        pass
    for d in dests:
        d["story_stage"] = normalize(stage) or NONE_LABEL
        if result is not None:
            d["story_stage_brief"] = result.get("brief", "")
            d["story_stage_visual"] = result.get("visual", "")
            d["story_stage_key"] = result.get("key", "")
            if "backend" in result:
                d["story_stage_source"] = result.get("backend", "")


# ---------------- 界面（魔法工作流「全场内容」和 STORY 窗口共用） ----------------

def build_controls(parent, *, get_owner, get_topic, persist, set_place=None, get_place=None, language=""):
    """在 parent 里（pack 到左边）放「舞台」下拉（可以自己打字）+「概要」按钮。返回 (combobox, sync)。

    get_owner() → dict；get_topic() → (topic, content, instruction)；persist() 保存 owner；
    set_place(region, era) 选了已知舞台时自动设地域 / 时代；get_place() → (region, era)。
    """
    import tkinter as tk
    from tkinter import ttk

    var = tk.StringVar(master=parent, value=NONE_LABEL)
    ttk.Label(parent, text="舞台").pack(side=tk.LEFT, padx=(8, 2))
    combo = ttk.Combobox(parent, textvariable=var, values=stage_names(), width=9)
    combo.pack(side=tk.LEFT)
    btn = ttk.Button(parent, text="概要", width=4)
    btn.pack(side=tk.LEFT, padx=(2, 0))
    st = {"busy": False, "last": None, "on_result": None}

    def sync() -> None:
        owner = get_owner() or {}
        var.set(normalize(owner.get("story_stage")) or NONE_LABEL)
        st["last"] = var.get()

    def _place():
        try:
            return get_place() if callable(get_place) else ("", "")
        except Exception:  # noqa: BLE001
            return "", ""

    def run_extract(force=False) -> None:
        owner = get_owner()
        stage = normalize(var.get())
        if not stage or not isinstance(owner, dict) or st["busy"]:
            return
        topic, content, instr = get_topic()
        key = content_key(stage, topic, content)
        if not force and owner.get("story_stage_key") == key and owner.get("story_stage_brief"):
            return
        st["busy"] = True
        btn.configure(text="提炼…")
        region, era = _place()
        box = {}

        def work():
            try:
                box["r"] = extract(stage, topic, content, instr, language, region, era)
            except Exception as exc:  # noqa: BLE001
                box["e"] = exc

        th = threading.Thread(target=work, daemon=True)
        th.start()

        def poll():
            if th.is_alive():
                parent.after(300, poll)
                return
            st["busy"] = False
            try:
                btn.configure(text="概要")
            except tk.TclError:
                return
            if "e" in box:
                print(f"⚠️ 提炼舞台失败（{stage}）：{box['e']}")
                if callable(st["on_result"]):
                    st["on_result"](None, str(box["e"]))
                return
            if normalize(var.get()) != stage:
                return  # 中途换了舞台
            store(owner, stage, box["r"])
            persist()
            print(f"🎭 舞台概要（{stage}，{box['r'].get('backend')}）：{box['r']['brief'][:80]}…")
            if callable(st["on_result"]):
                st["on_result"](box["r"], "")

        parent.after(300, poll)

    def commit(_e=None) -> None:
        stage = normalize(var.get())
        if (var.get() or "") == st["last"]:
            return
        st["last"] = var.get()
        owner = get_owner()
        if not isinstance(owner, dict):
            return
        store(owner, stage, {"brief": "", "visual": "", "key": ""})
        region, era = stage_place(stage)
        if region and callable(set_place):
            set_place(region, era)
        persist()
        if stage:
            run_extract()

    def open_brief() -> None:
        owner = get_owner()
        stage = normalize(var.get())
        if not stage or not isinstance(owner, dict):
            from tkinter import messagebox

            messagebox.showinfo("舞台概要", "先选一个故事舞台（「不限」没有概要）。", parent=parent)
            return
        win = tk.Toplevel(parent)
        win.title(f"舞台概要 · {stage}")
        win.transient(parent.winfo_toplevel())
        txt = tk.Text(win, width=64, height=10, wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
        txt.insert("1.0", owner.get("story_stage_brief") or "")
        ttk.Label(win, text="画面（英文一句，用在图片 / 视频提示里）").pack(anchor=tk.W, padx=8)
        vis = tk.StringVar(master=win, value=owner.get("story_stage_visual") or "")
        ttk.Entry(win, textvariable=vis, width=80).pack(fill=tk.X, padx=8)
        note = tk.StringVar(master=win, value="")
        topic, content, _i = get_topic()
        if owner.get("story_stage_key") and owner.get("story_stage_key") != content_key(stage, topic, content):
            note.set("主题内容已改，建议 Remix 重新提炼。")
        if not owner.get("story_stage_brief"):
            note.set("还没有概要：点 Remix 提炼（DeepSeek，不行就用 Strata）。" if not st["busy"] else "提炼中…")
        elif owner.get("story_stage_source") and not note.get():
            note.set("来源：" + str(owner.get("story_stage_source")))
        ttk.Label(win, textvariable=note, foreground="#b05a00").pack(anchor=tk.W, padx=8, pady=(4, 0))
        row = ttk.Frame(win)
        row.pack(fill=tk.X, padx=8, pady=8)

        def save():
            store(owner, stage, {"brief": txt.get("1.0", tk.END).strip(), "visual": vis.get().strip(),
                                 "key": owner.get("story_stage_key") or content_key(stage, topic, content)})
            persist()
            win.destroy()

        def on_result(r, err):
            try:
                if r:
                    txt.delete("1.0", tk.END)
                    txt.insert("1.0", r["brief"])
                    vis.set(r["visual"])
                    note.set(f"已重新提炼并保存。来源：{r.get('backend') or '?'}")
                else:
                    note.set(f"提炼失败：{err}")
            except tk.TclError:
                pass

        def remix():
            note.set("提炼中…（DeepSeek，不行就用 Strata）")
            st["on_result"] = on_result
            run_extract(force=True)

        ttk.Button(row, text="保存", command=save).pack(side=tk.LEFT)
        ttk.Button(row, text="Remix", command=remix).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="关闭", command=win.destroy).pack(side=tk.LEFT)
        win.bind("<Destroy>", lambda e: st.update(on_result=None) if e.widget is win else None)

    btn.configure(command=open_brief)
    combo.bind("<<ComboboxSelected>>", commit)
    combo.bind("<Return>", commit)
    combo.bind("<FocusOut>", commit)
    sync()
    return combo, sync
