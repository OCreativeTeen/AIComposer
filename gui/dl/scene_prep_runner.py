# -*- coding: utf-8 -*-
"""t436u: 「整理场景」（建项目时自动跑，预览窗口也有按钮）：后台跑 utility.scene_prep，带进度和取消。
Strata 出错或取消：返回 None，调用方照原来的场景继续。"""
from __future__ import annotations

import json
import threading


def scene_list_of(scene_content) -> list:
    """scene_content（list 或 JSON 文字）→ 场景 list；不是就 []。"""
    if isinstance(scene_content, list):
        return [s for s in scene_content if isinstance(s, dict)]
    if isinstance(scene_content, str) and scene_content.strip():
        try:
            data = json.loads(scene_content)
        except ValueError:
            return []
        return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []
    return []


def prep_inputs(video_detail: dict) -> dict:
    """这一条的场景来源（音频 / 视频带文字稿时间，视频取分镜画面）。"""
    import project_manager

    vd = video_detail if isinstance(video_detail, dict) else {}
    raw = str(vd.get("scene_source") or "").strip()
    kind = project_manager.normalize_scene_source(raw) if raw else ""
    path = str(vd.get("scene_source_path") or "").strip()
    transcript = ""
    if kind in (project_manager.SCENE_SOURCE_AUDIO, project_manager.SCENE_SOURCE_VIDEO):
        try:
            from utility.media_transcript import read_timed_transcript_text

            transcript = read_timed_transcript_text(path, vd)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 整理场景：文字稿没读到：{exc}")
    return {"source_kind": kind, "source_path": path, "transcript_text": transcript}


def run_scene_prep(scenes: list, video_detail: dict, language: str = "tw", *, progress=None, cancel=None,
                   log=print) -> tuple:
    """不带界面：返回 (新的场景列表 或 None, 说明)。"""
    import config
    from utility import scene_prep

    lang = (language or "tw").strip() or "tw"
    src = prep_inputs(video_detail)
    try:
        out, report = scene_prep.prepare_scenes(
            scenes,
            transcript_text=src["transcript_text"],
            source_kind=src["source_kind"],
            source_path=src["source_path"],
            language_label=config.llm_language_label(lang),
            convert=lambda t: config.chinese_convert(t, lang),
            progress=progress,
            cancel=cancel,
            log=log,
        )
    except scene_prep.PrepCancelled:
        return None, "整理场景取消了，用原来的场景"
    except scene_prep.PrepFailed as exc:
        return None, f"整理场景没做完（{exc}），用原来的场景"
    except Exception as exc:  # noqa: BLE001
        return None, f"整理场景出错（{type(exc).__name__}: {exc}），用原来的场景"
    return out, scene_prep.report_text(report, len(scenes), len(out))


def run_scene_prep_modal(parent, scenes: list, video_detail: dict, language: str = "tw",
                         title: str = "整理场景") -> tuple:
    """带进度窗口（可取消）跑整理，等它跑完。返回 (新的场景列表 或 None, 说明)。"""
    import tkinter as tk
    import tkinter.ttk as ttk

    if not scenes:
        return None, "没有场景"
    holder = {"done": False, "result": (None, ""), "cancel": False, "status": "开始整理…"}

    def _work():
        try:
            holder["result"] = run_scene_prep(
                scenes, video_detail, language,
                progress=lambda m: holder.__setitem__("status", m),
                cancel=lambda: holder["cancel"],
            )
        finally:
            holder["done"] = True

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.resizable(False, False)
    frm = ttk.Frame(dlg, padding=14)
    frm.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frm, text=f"Strata 正在整理 {len(scenes)} 个场景：改写视觉、拆长讲话、分镜视觉连贯。\n"
                        "取消 = 用原来的场景。").pack(anchor=tk.W)
    status = tk.StringVar(value=holder["status"])
    ttk.Label(frm, textvariable=status, width=48).pack(anchor=tk.W, pady=(8, 8))

    def _cancel():
        holder["cancel"] = True
        status.set("正在取消（等这一步做完）…")

    ttk.Button(frm, text="取消", command=_cancel).pack()
    dlg.protocol("WM_DELETE_WINDOW", _cancel)

    def _poll():
        if holder["done"]:
            try:
                dlg.destroy()
            except tk.TclError:
                pass
            return
        status.set(holder["status"])
        dlg.after(200, _poll)

    threading.Thread(target=_work, daemon=True).start()
    dlg.after(200, _poll)
    try:
        dlg.grab_set()
    except tk.TclError:
        pass
    dlg.wait_window()
    return holder["result"]
