"""t386u: 导入视频后，末帧接到下一场 zero_image_last 之前先按「尾帧增强」增强。

不管是全集生成、本集生成、生场视频（仅当前场景）还是「导入视频」手动导入，只要 clip 视频导进某一场、
而且有下一场，``MediaScanner.last_image_replacement`` 都会：

1. 先把原末帧（缩到项目尺寸）写进下一场 zero_image_last（立刻能用，和以前一样）；
2. 再在后台线程按项目记下的「尾帧增强」（video_prompt.last_frame_enhance：不增强 / MOSS / Qwen / Grok Image）
   用图片编辑「提高分辨率」（t377u 忠实还原：不改画风、不改颜色）；
3. 增强好了，且下一场 zero_image_last 还是第 1 步写的那张（期间没有更新的导入 / 项目没切换），
   就用 ``write_chained_next_zero_image_last`` 换成增强后的图；否则丢掉这次结果。
   增强失败 / 选了不增强：保留原末帧，打印警告。

生场视频动态分节（t370u）的克隆那一节：末帧由 ``_chain_video_segment`` 增强后写回原场景，
导入时就不再增强一遍（``mark_segment_chain_pending``）。

这里只放逻辑（可离线测）；增强器 / 写入 / 主线程调度都可注入。
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading

_LOCK = threading.Lock()
_PENDING_SEGMENTS: set = set()  # 分节克隆 id：末帧交给分节流程增强


def _sid(scene) -> str:
    if not isinstance(scene, dict) or scene.get("id") is None:
        return ""
    return str(scene.get("id"))


def mark_segment_chain_pending(clone) -> None:
    """分节克隆：导入它的视频时不再增强末帧（分节流程会增强并写回原场景）。"""
    sid = _sid(clone)
    if sid:
        with _LOCK:
            _PENDING_SEGMENTS.add(sid)


def clear_segment_chain_pending(clone) -> None:
    sid = _sid(clone)
    if sid:
        with _LOCK:
            _PENDING_SEGMENTS.discard(sid)


def is_segment_chain_pending(scene) -> bool:
    sid = _sid(scene)
    if not sid:
        return False
    with _LOCK:
        return sid in _PENDING_SEGMENTS


def saved_enhance_mode(project_config=None) -> str:
    """项目记下的「尾帧增强」（生场视频窗口里选的）→ none / moss / qn / grok；没记过 = 默认。"""
    from utility.video_segments import normalize_last_frame_enhance

    if project_config is None:
        try:
            import project_manager

            project_config = project_manager.PROJECT_CONFIG
        except Exception:  # noqa: BLE001
            project_config = None
    pc = project_config if isinstance(project_config, dict) else {}
    vp = pc.get("video_prompt") if isinstance(pc.get("video_prompt"), dict) else {}
    return normalize_last_frame_enhance(vp.get("last_frame_enhance"))


def saved_visual_style(project_config=None) -> str:
    if project_config is None:
        try:
            import project_manager

            project_config = project_manager.PROJECT_CONFIG
        except Exception:  # noqa: BLE001
            project_config = None
    pc = project_config if isinstance(project_config, dict) else {}
    return str(pc.get("visual_style") or "").strip()


def _remove(path) -> None:
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def apply_enhanced_result(next_scene: dict, raw_dest: str, path: str, enhanced: bool, note: str = "", *,
                          label: str = "", writer=None, still_valid=None, on_written=None) -> str:
    """增强结果 → 下一场 zero_image_last。只在它还是导入时写的那张原末帧时才换；返回新路径（没换 = ""）。"""
    from utility.scene_image_slots import FROZEN_SLOT

    if not enhanced or not path or not os.path.isfile(path):
        print(f"⚠️ 末帧「{label}」增强没成（{note}），下一场 zero_image_last 保留原末帧")
        return ""
    if writer is None:
        from utility.scene_image_slots import write_chained_next_zero_image_last as writer
    with _LOCK:
        if callable(still_valid) and not still_valid():
            print("ℹ️ 末帧增强好了，但下一场已不在当前项目里（换了项目 / 删了场景），这次结果不用")
            return ""
        if str(next_scene.get(FROZEN_SLOT) or "") != str(raw_dest or ""):
            print("ℹ️ 末帧增强好了，但下一场 zero_image_last 已被更新的导入换掉，这次结果不用")
            return ""
        try:
            written = writer(next_scene, path)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 增强后的末帧没写进下一场 zero_image_last（保留原末帧）：{exc}")
            return ""
    print(f"✨ 末帧用「{label}」增强后写进下一场（id={next_scene.get('id')}）zero_image_last")
    if callable(on_written):
        try:
            on_written(written)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 增强末帧写入后保存 / 刷新失败：{exc}")
    return written


def start_enhanced_chain(next_scene: dict, raw_dest: str, frame: str, *, mode, style: str = "", account: str = "",
                         enhancer=None, writer=None, dispatch=None, still_valid=None, on_written=None,
                         run_async: bool = True) -> bool:
    """后台增强 ``frame`` → 替换下一场 zero_image_last（见模块说明）。开始了返回 True；不增强 / 没法做返回 False。

    ``enhancer(path) -> (图路径, 是否增强了, 说明)``，默认 = ``video_segments.enhance_segment_last_frame``。
    ``dispatch(fn)``：把写入放回主线程（GUI 传 ``root.after(0, fn)``）；不给就在工作线程里写。
    """
    from utility import video_segments as vs

    m = vs.normalize_last_frame_enhance(mode)
    if m == "none":
        print("🔗 尾帧增强 = 不增强：下一场 zero_image_last 用原末帧")
        return False
    if not isinstance(next_scene, dict) or not raw_dest or not frame or not os.path.isfile(frame):
        return False
    label = vs.last_frame_enhance_label(m)
    ext = os.path.splitext(frame)[1].lower() or ".webp"
    fd, src = tempfile.mkstemp(suffix=ext, prefix="chain_lastframe_")
    os.close(fd)
    try:
        shutil.copyfile(frame, src)  # 自己的一份：原末帧临时文件被清掉也不影响
    except Exception:
        _remove(src)
        raise

    if enhancer is None:
        def _status(msg) -> None:
            print(f"🎞️ 导入末帧增强（{label}）：{msg}")

        def enhancer(p):
            return vs.enhance_segment_last_frame(p, mode=m, style=style, status=_status, account=account)

    def work() -> None:
        try:
            path, enhanced, note = enhancer(src)
        except Exception as exc:  # noqa: BLE001
            path, enhanced, note = "", False, str(exc)

        def finish() -> None:
            try:
                apply_enhanced_result(next_scene, raw_dest, path, enhanced, note, label=label, writer=writer,
                                      still_valid=still_valid, on_written=on_written)
            finally:
                if path and path != src:
                    _remove(path)
                _remove(src)

        if callable(dispatch):
            try:
                dispatch(finish)
                return
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 末帧增强结果没能交回主线程，直接写：{exc}")
        finish()

    print(f"🔗 下一场 zero_image_last 先放原末帧；后台用「{label}」增强，好了自动换上")
    if run_async:
        threading.Thread(target=work, daemon=True, name="lastframe-enhance").start()
    else:
        work()
    return True
