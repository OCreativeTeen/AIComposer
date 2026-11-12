# -*- coding: utf-8 -*-
"""t406u: 图片对场景。

从材料里取图，按顺序对到 scene_content 的场景上：
- PDF：每页里有图的页抽出来（整页几乎就是一张图 → 渲染整页 pNNN.png；页里有几张较大的图 → 各自裁出 pNNN_K.png）；
  只有文字、没有像样图片的页跳过。
- 视频概览（NotebookLM 说明视频 = 幻灯片放映）：本机 OpenCV 逐帧比较，画面停稳且和上一张明显不同 → 一张新幻灯片，
  存 sNNN.png；几乎一样的重复画面去掉。
图都放在 working/<材料文件名>/ 下。

然后每张图用本机 Strata 看图：说了什么内容、图里的文字。结果按（路径 + 修改时间）缓存（内存 + 目录里的 _strata_desc.json）。

顺序匹配：图按页序 / 播放顺序走，场景也按顺序走。每张图只拿「当前场景起往后几场」给 Strata（文字模型）挑：
对上了就记到那一场、当前场景移到那一场（同一场可以挂多张图）；都对不上就跳过这张图，连续跳过时往后看的范围放宽。
结果记在每一场的 ``ref_images`` 列表里（追加、不重复），PDF 和视频的图可以挂在同一场。

这个模块不碰 Tk；GUI 在后台线程里调 ``run_match``，结束后在 Tk 线程里用 ``apply_matches`` 写回场景并保存。
"""
import json
import os
import re
import threading
import time

REF_FIELD = "ref_images"
DESC_CACHE_FILE = "_strata_desc.json"
VISION_TIMEOUT_S = 90.0
JUDGE_TIMEOUT_S = 60.0
WINDOW = 3  # 当前场景起往后看几场

# PDF：图占页面面积的比例
PDF_MIN_IMAGE_FRAC = 0.04   # 小于这个的图（图标、页眉 logo）不算
PDF_FULL_PAGE_FRAC = 0.60   # 一张图盖住这么多 → 整页渲染
PDF_DPI = 150

# 视频：缩略灰度图（96x54）上的平均差
SLIDE_SAMPLE_S = 0.5     # 每隔多少秒取一帧比较
SLIDE_STABLE_DIFF = 2.5  # 和上一帧差这么少 = 画面停稳了
SLIDE_NEW_DIFF = 10.0    # 和上一张幻灯片差这么多 = 新的一张
SLIDE_DUP_DIFF = 4.0     # 和以前任何一张差这么少 = 重复，不要
SLIDE_DARK_MEAN = 10.0   # 几乎全黑的帧不要

_CACHE = {}
_LOCK = threading.Lock()


def working_dir_for(material_path: str, base_dir: str = "") -> str:
    """working/<材料文件名（不带扩展名）>/。"""
    if not base_dir:
        import config

        base_dir = getattr(config, "WORKING_DIR", "") or os.path.abspath(getattr(config, "WORKING_MEDIA_PATH", "working"))
    stem = os.path.splitext(os.path.basename(str(material_path or "")))[0] or "material"
    stem = re.sub(r'[<>:"/\\|?*]+', "_", stem).strip(" .") or "material"
    return os.path.join(base_dir, stem)


def _clear_old_outputs(out_dir: str, pattern: str) -> None:
    rx = re.compile(pattern)
    for name in os.listdir(out_dir):
        if rx.match(name):
            try:
                os.remove(os.path.join(out_dir, name))
            except OSError:
                pass


# ---------------------------------------------------------------- PDF
def extract_pdf_images(pdf_path: str, out_dir: str = "", *, log=print) -> list:
    """PDF 里有图的页抽成 png。返回 [{"path", "source": "pdf", "page"}]（按页序）。"""
    import fitz  # PyMuPDF

    out_dir = out_dir or working_dir_for(pdf_path)
    os.makedirs(out_dir, exist_ok=True)
    _clear_old_outputs(out_dir, r"^p\d{3,}(_\d+)?\.png$")
    zoom = PDF_DPI / 72.0
    out = []
    skipped = 0
    with fitz.open(pdf_path) as doc:
        for pno in range(doc.page_count):
            page = doc[pno]
            prect = page.rect
            parea = max(1.0, prect.width * prect.height)
            rects = []
            try:
                infos = page.get_image_info()
            except Exception:  # noqa: BLE001
                infos = []
            for info in infos:
                r = fitz.Rect(info.get("bbox") or (0, 0, 0, 0)) & prect
                if r.is_empty:
                    continue
                if (r.width * r.height) / parea >= PDF_MIN_IMAGE_FRAC:
                    rects.append(r)
            if not rects:
                skipped += 1
                continue
            rects = _merge_rects(rects)
            n = pno + 1
            big = max(rects, key=lambda r: r.width * r.height)
            if (big.width * big.height) / parea >= PDF_FULL_PAGE_FRAC or len(rects) == 1 and (
                (big.width * big.height) / parea >= 0.35
            ):
                path = os.path.join(out_dir, f"p{n:03d}.png")
                page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(path)
                out.append({"path": path, "source": "pdf", "page": n})
                continue
            for k, r in enumerate(rects, 1):
                path = os.path.join(out_dir, f"p{n:03d}_{k}.png")
                page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=r).save(path)
                out.append({"path": path, "source": "pdf", "page": n})
    log(f"[图片对场景] PDF {os.path.basename(pdf_path)}：抽出 {len(out)} 张图，跳过只有文字的 {skipped} 页 → {out_dir}")
    return out


def _merge_rects(rects: list) -> list:
    """重叠的图框合成一个（同一张图被切成几块的情况）。"""
    rects = [r for r in rects]
    changed = True
    while changed:
        changed = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                if rects[i].intersects(rects[j]):
                    rects[i] = rects[i] | rects[j]
                    del rects[j]
                    changed = True
                    break
            if changed:
                break
    return sorted(rects, key=lambda r: (round(r.y0), round(r.x0)))


# ---------------------------------------------------------------- 视频
def _small(frame):
    import cv2

    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (96, 54), interpolation=cv2.INTER_AREA).astype("float32")


class SlidePicker:
    """一帧一帧喂缩略灰度图（numpy），feed() 返回这一帧要不要留成一张新幻灯片。"""

    def __init__(self):
        self.prev = None
        self.kept = []

    def feed(self, s) -> bool:
        import numpy as np

        stable = self.prev is not None and float(np.mean(np.abs(s - self.prev))) <= SLIDE_STABLE_DIFF
        self.prev = s
        if not stable or float(np.mean(s)) < SLIDE_DARK_MEAN:
            return False
        if self.kept and float(np.mean(np.abs(s - self.kept[-1]))) < SLIDE_NEW_DIFF:
            return False
        if any(float(np.mean(np.abs(s - k))) < SLIDE_DUP_DIFF for k in self.kept):
            return False
        self.kept.append(s)
        return True


def pick_slide_frames(smalls: list) -> list:
    """smalls = 依次取样的缩略灰度图。返回要留的取样下标（每张幻灯片一个，停稳后的那一帧）。"""
    picker = SlidePicker()
    return [i for i, s in enumerate(smalls) if picker.feed(s)]


def extract_video_slides(video_path: str, out_dir: str = "", *, log=print, progress=None) -> list:
    """幻灯片视频 → 每张幻灯片一张 png（sNNN.png，按播放顺序）。返回 [{"path", "source": "video", "index", "time"}]。"""
    import cv2

    out_dir = out_dir or working_dir_for(video_path)
    os.makedirs(out_dir, exist_ok=True)
    _clear_old_outputs(out_dir, r"^s\d{3,}\.png$")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"打不开视频：{video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps * SLIDE_SAMPLE_S)))
    out = []
    picker = SlidePicker()
    fno = -1
    try:
        while True:
            ok = cap.grab()
            if not ok:
                break
            fno += 1
            if fno % step:
                continue
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                continue
            if progress and total and (fno // step) % 120 == 0:
                progress(f"看视频 {fno * 100 // total}%")
            if not picker.feed(_small(frame)):
                continue
            idx = len(out) + 1
            path = os.path.join(out_dir, f"s{idx:03d}.png")
            ok_w, buf = cv2.imencode(".png", frame)
            if ok_w:
                buf.tofile(path)  # 路径里有中文时 cv2.imwrite 会失败
                out.append({"path": path, "source": "video", "index": idx, "time": round(fno / fps, 1)})
    finally:
        cap.release()
    log(f"[图片对场景] 视频 {os.path.basename(video_path)}：抽出 {len(out)} 张幻灯片 → {out_dir}")
    return out


# ---------------------------------------------------------------- Strata 看图
_VISION_SYS = """You look at one picture taken from a slide deck or a slide-show video.
Say in 1-3 short sentences what the picture shows and what idea it is about, and copy the readable text in it (titles, labels, sentences), keeping the original language.
Return only JSON: {"desc": "...", "text": "..."} (text is "" when there is no readable text)."""


def _strata_vision(image_path: str, timeout_s: float = VISION_TIMEOUT_S) -> str:
    from utility import llm_api
    from utility.prompt_polish import _clean, _image_data_url, _strata_client

    api = llm_api.LLMApi(llm_api.STRATA)
    api.manual_fallback = False
    content = [{"type": "text", "text": "The picture:"},
               {"type": "image_url", "image_url": {"url": _image_data_url(image_path, 1024)}}]
    req = api._strata_request(llm_api.STRATA, [{"role": "system", "content": _VISION_SYS},
                                                {"role": "user", "content": content}])
    req["max_tokens"] = 700
    resp = _strata_client(timeout_s).chat.completions.create(**req)
    return _clean(resp.choices[0].message.content if resp and resp.choices else "")


def _strata_text(system: str, user: str, timeout_s: float = JUDGE_TIMEOUT_S) -> str:
    from utility import llm_api
    from utility.prompt_polish import _clean, _strata_client

    api = llm_api.LLMApi(llm_api.STRATA)
    api.manual_fallback = False
    req = api._strata_request(llm_api.STRATA, [{"role": "system", "content": system},
                                                {"role": "user", "content": user}])
    req["max_tokens"] = 200
    resp = _strata_client(timeout_s).chat.completions.create(**req)
    return _clean(resp.choices[0].message.content if resp and resp.choices else "")


def _json_obj(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        raise ValueError(f"没有 JSON：{(raw or '')[:80]}")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError(f"JSON 格式不对：{(raw or '')[:80]}")
    return data


def image_cache_key(path: str) -> str:
    try:
        mt = os.path.getmtime(path)
    except OSError:
        mt = 0.0
    return f"{os.path.normcase(os.path.abspath(str(path or '')))}|{mt:.3f}"


def _load_disk_cache(out_dir: str) -> dict:
    try:
        with open(os.path.join(out_dir, DESC_CACHE_FILE), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_disk_cache(out_dir: str, data: dict) -> None:
    try:
        tmp = os.path.join(out_dir, DESC_CACHE_FILE + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(out_dir, DESC_CACHE_FILE))
    except OSError:
        pass


def describe_image(path: str, *, ask=None, disk: dict | None = None) -> dict:
    """{"desc", "text"}；失败返回 {"desc": "", "text": "", "error": 原因}。ask(path) -> 文字（测试换成假的）。"""
    key = image_cache_key(path)
    with _LOCK:
        if key in _CACHE:
            return dict(_CACHE[key])
    if isinstance(disk, dict) and isinstance(disk.get(key), dict):
        rec = dict(disk[key])
        with _LOCK:
            _CACHE[key] = rec
        return dict(rec)
    try:
        raw = (ask or _strata_vision)(path)
        data = _json_obj(raw)
        rec = {"desc": str(data.get("desc") or "").strip(), "text": str(data.get("text") or "").strip()}
    except Exception as exc:  # noqa: BLE001
        return {"desc": "", "text": "", "error": f"{type(exc).__name__}: {str(exc)[:100]}"}
    with _LOCK:
        _CACHE[key] = dict(rec)
    if isinstance(disk, dict):
        disk[key] = dict(rec)
    return rec


# ---------------------------------------------------------------- 顺序匹配
_JUDGE_SYS = """You match one picture to the scenes of a video script.
You get what the picture shows (and its text), then a few numbered scenes (what is seen, what is said).
Pick the one scene whose content the picture clearly illustrates or talks about: the same topic, idea, event or words. A loose general mood is not enough.
If none of the scenes fits, answer 0.
Return only JSON: {"scene": <number or 0>}"""


def _clip(text, n: int) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def scene_summary(scene: dict) -> str:
    parts = []
    for key, label in (("caption", "Caption"), ("visual", "Seen"), ("speaking", "Said"), ("story", "Story")):
        v = scene.get(key) if isinstance(scene, dict) else None
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        if v:
            parts.append(f"{label}: {_clip(v, 360)}")
    return " | ".join(parts) or "(empty scene)"


def judge_prompt(info: dict, candidates: list) -> str:
    lines = [f"Picture: {_clip(info.get('desc'), 500)}"]
    if info.get("text"):
        lines.append(f"Text in the picture: {_clip(info.get('text'), 500)}")
    lines.append("")
    lines.append("Scenes:")
    for idx, scene in candidates:
        lines.append(f"[{idx + 1}] {scene_summary(scene)}")
    return "\n".join(lines)


def make_strata_judge(ask=None):
    """返回 judge(info, candidates) -> 场景下标或 None。ask(system, user) -> 文字。"""
    ask = ask or _strata_text

    def judge(info: dict, candidates: list):
        ok_idx = {idx for idx, _s in candidates}
        raw = ask(_JUDGE_SYS, judge_prompt(info, candidates))
        data = _json_obj(raw)
        try:
            n = int(str(data.get("scene", 0)).strip() or 0)
        except ValueError:
            return None
        return (n - 1) if (n - 1) in ok_idx else None

    return judge


def sequential_match(images: list, scenes: list, judge, *, window: int = WINDOW, log=print) -> dict:
    """images = [{"path", ..., "desc", "text"}]（按顺序），scenes = 场景列表。
    judge(info, [(场景下标, 场景)]) -> 下标或 None。返回 {场景下标: [image, ...]}。
    当前场景只往前走不回头；每连续跳过一张图，往后看的场数多 ``window`` 场。"""
    result = {}
    if not scenes:
        return result
    cur = 0
    misses = 0
    for k, img in enumerate(images, 1):
        if not (img.get("desc") or img.get("text")):
            log(f"[图片对场景] 第 {k} 张没看出内容，跳过：{os.path.basename(img.get('path') or '')}")
            continue
        span = window * (1 + misses)
        cands = [(i, scenes[i]) for i in range(cur, min(len(scenes), cur + span))]
        if not cands:
            break
        try:
            hit = judge(img, cands)
        except Exception as exc:  # noqa: BLE001
            log(f"[图片对场景] 第 {k} 张判断失败（{type(exc).__name__}: {str(exc)[:80]}），跳过")
            hit = None
        name = os.path.basename(img.get("path") or "")
        if hit is None:
            misses += 1
            log(f"[图片对场景] {name} 对不上第 {cur + 1}–{cands[-1][0] + 1} 场，跳过")
            continue
        misses = 0
        cur = hit
        result.setdefault(hit, []).append(img)
        log(f"[图片对场景] {name} → 第 {hit + 1} 场")
    return result


def ref_entry(img: dict) -> dict:
    rec = {"path": img.get("path") or "", "source": img.get("source") or ""}
    if img.get("source") == "pdf" and img.get("page"):
        rec["page"] = int(img["page"])
    if img.get("source") == "video":
        if img.get("index"):
            rec["index"] = int(img["index"])
        if img.get("time") is not None:
            rec["time"] = img["time"]
    if img.get("material"):
        rec["material"] = os.path.basename(img["material"])
    desc = _clip(img.get("desc"), 160)
    if desc:
        rec["desc"] = desc
    return rec


def add_ref_images(scene: dict, imgs: list) -> int:
    """追加到 scene["ref_images"]，按路径去重。返回新加了几张。"""
    have = scene.get(REF_FIELD)
    if not isinstance(have, list):
        have = []
    seen = {os.path.normcase(os.path.abspath(str(r.get("path") or ""))) for r in have if isinstance(r, dict)}
    added = 0
    for img in imgs:
        rec = ref_entry(img)
        key = os.path.normcase(os.path.abspath(rec["path"]))
        if not rec["path"] or key in seen:
            continue
        seen.add(key)
        have.append(rec)
        added += 1
    if have:
        scene[REF_FIELD] = have
    return added


def scene_fingerprint(scene: dict) -> str:
    if not isinstance(scene, dict):
        return ""
    return "|".join(_clip(scene.get(k), 200) for k in ("episode", "caption", "visual", "speaking"))


def apply_matches(current: list, snapshot: list, matches: dict) -> tuple:
    """把 run_match 的结果写到 ``current``（Tk 线程里、此刻的场景列表）。
    场景数没变按下标；变了按场景内容指纹找。返回 (新加张数, 对不上而丢掉的场数)。"""
    added = 0
    lost = 0
    same = len(current) == len(snapshot)
    fps = {}
    if not same:
        for i, s in enumerate(current):
            fps.setdefault(scene_fingerprint(s), i)
    for idx, imgs in sorted(matches.items()):
        target = None
        if same and 0 <= idx < len(current):
            target = idx
        elif 0 <= idx < len(snapshot):
            target = fps.get(scene_fingerprint(snapshot[idx]))
        if target is None or not isinstance(current[target], dict):
            lost += 1
            continue
        added += add_ref_images(current[target], imgs)
    return added, lost


def run_match(material_path: str, source: str, scenes: list, *, out_dir: str = "", log=print, progress=None,
              vision_ask=None, judge=None, extract=None) -> dict:
    """后台线程里跑：抽图 → Strata 看图 → 顺序匹配。不改 ``scenes``。
    返回 {"images": [...], "matches": {下标: [image]}, "out_dir", "described", "failed"}。"""
    out_dir = out_dir or working_dir_for(material_path)
    progress = progress or (lambda _m: None)
    progress("抽图中…")
    if extract is not None:
        images = extract(material_path, out_dir)
    elif source == "pdf":
        images = extract_pdf_images(material_path, out_dir, log=log)
    else:
        images = extract_video_slides(material_path, out_dir, log=log, progress=progress)
    for img in images:
        img["material"] = material_path
    disk = _load_disk_cache(out_dir)
    failed = 0
    started = time.monotonic()
    for k, img in enumerate(images, 1):
        progress(f"Strata 看图 {k}/{len(images)}")
        info = describe_image(img["path"], ask=vision_ask, disk=disk)
        img["desc"], img["text"] = info.get("desc", ""), info.get("text", "")
        if info.get("error"):
            failed += 1
            log(f"[图片对场景] 看图失败 {os.path.basename(img['path'])}：{info['error']}")
        else:
            log(f"[图片对场景] {os.path.basename(img['path'])}：{_clip(img['desc'], 80)}")
        if k % 5 == 0:
            _save_disk_cache(out_dir, disk)
    _save_disk_cache(out_dir, disk)
    log(f"[图片对场景] 看图完成 {len(images)} 张（失败 {failed}），{time.monotonic() - started:.0f} 秒")
    progress("对场景中…")
    matches = sequential_match(images, scenes, judge or make_strata_judge(), log=log)
    return {"images": images, "matches": matches, "out_dir": out_dir,
            "described": len(images) - failed, "failed": failed}


def summary_text(result: dict, added: int, lost: int = 0) -> str:
    images = result.get("images") or []
    matches = result.get("matches") or {}
    n_matched = sum(len(v) for v in matches.values())
    lines = [f"抽出 {len(images)} 张图，对上 {n_matched} 张（新记上 {added} 张），跳过 {len(images) - n_matched} 张。"]
    if result.get("failed"):
        lines.append(f"Strata 看图失败 {result['failed']} 张（这些没参与匹配）。")
    for idx in sorted(matches):
        names = "、".join(os.path.basename(i.get("path") or "") for i in matches[idx])
        lines.append(f"第 {idx + 1} 场：{names}")
    if lost:
        lines.append(f"有 {lost} 场在跑的时候被改过 / 删掉，那几场的图没记上。")
    lines.append(f"图片在：{result.get('out_dir') or ''}")
    lines.append(f"记在每一场的「{REF_FIELD}」里。")
    return "\n".join(lines)
