"""Publish-bot only: send finished video + YouTube copy after upload.

Uses ``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_IDS`` via ``ROLE_PUBLISH``.
Never touches the CLI bot.
"""

from __future__ import annotations

import os

from utility.telegram import ROLE_PUBLISH, send_message, send_video, token_for

import config


def _tg_cfg() -> dict:
    tg = getattr(config, "TELEGRAM_PUBLISH", None)
    return tg if isinstance(tg, dict) else {}


def telegram_publish_enabled() -> bool:
    c = _tg_cfg()
    if not c.get("enabled"):
        return False
    return bool(token_for(ROLE_PUBLISH) and telegram_publish_chat_ids(c))


def telegram_publish_chat_ids(c: dict | None = None) -> list[str]:
    """接收方列表：优先 ``chat_ids``；否则兼容旧字段 ``chat_id``。"""
    box = c if isinstance(c, dict) else _tg_cfg()
    xs = box.get("chat_ids")
    if isinstance(xs, list):
        out = [str(x).strip() for x in xs if str(x).strip()]
        if out:
            return out
    legacy = (box.get("chat_id") or "").strip()
    return [legacy] if legacy else []


def notify_youtube_publish_extras(
    *,
    mp4_path: str,
    watch_url: str,
    title_line: str,
    summary: str,
) -> list[str]:
    """
    YouTube 已成功上传后的附加步骤：按配置发 Telegram（发布 Bot）。
    返回简短状态行列表，可供成功弹窗展示；失败不抛出到上层任务（仅记在列表里）。
    """
    lines: list[str] = []
    if not telegram_publish_enabled():
        return lines
    chat_ids = telegram_publish_chat_ids()
    try:
        max_mb = float(_tg_cfg().get("max_video_mb", 48))
    except (TypeError, ValueError):
        max_mb = 48.0
    max_bytes = int(max_mb * 1024 * 1024)

    caption = (title_line or "").strip() or "AIComposer 成片"
    if (watch_url or "").strip():
        caption = f"{caption}\n{watch_url.strip()}"

    vp = (mp4_path or "").strip()
    try:
        if vp and os.path.isfile(vp):
            sz = os.path.getsize(vp)
            if sz <= max_bytes:
                ok_v = 0
                errs_v: list[str] = []
                for cid in chat_ids:
                    try:
                        send_video(ROLE_PUBLISH, cid, vp, caption)
                        ok_v += 1
                    except Exception as e:
                        errs_v.append(f"{cid}: {e}")
                        try:
                            send_message(
                                ROLE_PUBLISH,
                                cid,
                                caption + f"\n\n（视频上传 Telegram 失败：{e}）",
                            )
                        except Exception:
                            pass
                if ok_v:
                    lines.append(
                        f"Telegram：已向 {ok_v}/{len(chat_ids)} 个会话发送视频"
                    )
                if errs_v:
                    lines.append(
                        "Telegram：部分会话视频失败 — "
                        + "; ".join(errs_v[:5])
                        + ("…" if len(errs_v) > 5 else "")
                    )
            else:
                mb = sz / (1024 * 1024)
                lines.append(
                    f"Telegram：跳过视频（约 {mb:.1f} MB，大于配置上限 {max_mb:.0f} MB）"
                )
                skip_txt = (
                    caption
                    + f"\n\n（成品约 {mb:.1f} MB，未通过 Bot 发送视频；Telegram Bot 硬性上限约 50MB。）"
                )
                for cid in chat_ids:
                    try:
                        send_message(ROLE_PUBLISH, cid, skip_txt)
                    except Exception as e:
                        lines.append(f"Telegram：会话 {cid} 文字通知失败 — {e}")
        else:
            miss = caption + "\n\n（本地未找到 mp4 路径，未发视频文件）"
            for cid in chat_ids:
                try:
                    send_message(ROLE_PUBLISH, cid, miss)
                except Exception as e:
                    lines.append(f"Telegram：会话 {cid} 文字通知失败 — {e}")

        body_msg = (summary or "").strip()
        if body_msg:
            full = "YouTube 发布文案（描述）\n\n" + body_msg
            ok_m = 0
            errs_m: list[str] = []
            for cid in chat_ids:
                try:
                    send_message(ROLE_PUBLISH, cid, full)
                    ok_m += 1
                except Exception as e:
                    errs_m.append(f"{cid}: {e}")
            if ok_m:
                lines.append(
                    f"Telegram：已向 {ok_m}/{len(chat_ids)} 个会话发送发布文案"
                )
            if errs_m:
                lines.append(
                    "Telegram：部分会话文案失败 — "
                    + "; ".join(errs_m[:5])
                    + ("…" if len(errs_m) > 5 else "")
                )

    except Exception as e:
        lines.append(f"Telegram：发送过程异常 — {e}")
    return lines
