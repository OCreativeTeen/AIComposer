"""Telegram CLI commands: plain-text LLM, Grok Imagine prepare / process.

ask       text  -> LLMApi (Strata by default, no GUI) -> reply + Windows clipboard
grokprep  image -> clipboard + Grok Imagine tab (CDP 9222), attached but NOT submitted
grokgo    prompt-> the prepared Imagine tab: paste, submit, wait -> image to clipboard + Telegram photo

Prompt syntax (ask / grokgo):  first line may hold the system prompt, separated from
the user prompt by a line containing only ``---`` (or ``|||``). No separator = everything
is the user prompt. ``ask`` accepts an optional model token first: ``@strata`` / ``@gemini``.

Telegram photos / image documents are downloaded by utility.telegram_cli and turned
into ``grokprep <path>`` automatically.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

INBOX_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AIComposer" / "telegram_inbox"
OUTBOX_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AIComposer" / "telegram_outbox"
TELEGRAM_TEXT_LIMIT = 3900

_SEP_RE = re.compile(r"^\s*(?:---+|\|\|\|)\s*$", re.M)
_MODEL_TOKENS = {"@strata": "strata", "@gemini": "gemini", "@simple": "strata"}


def split_system_user(text: str) -> tuple[str, str]:
    """``system\\n---\\nuser`` -> (system, user). No separator -> ("", text)."""
    text = (text or "").strip()
    m = _SEP_RE.search(text)
    if not m:
        return "", text
    return text[: m.start()].strip(), text[m.end():].strip()


def _model_from_token(value: str) -> tuple[str | None, str]:
    first, _, rest = (value or "").strip().partition(" ")
    key = first.strip().lower()
    if key in _MODEL_TOKENS:
        from utility import llm_api

        model = llm_api.GEMINI if _MODEL_TOKENS[key] == "gemini" else llm_api.MODEL_SIMPLE
        return model, rest.strip()
    return None, (value or "").strip()


def _first_line(exc) -> str:
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0][:200]


def _status_log(msg: str) -> None:
    print(f"[grok_tg] {msg}", flush=True)


def _notify_photo(path: str, caption: str) -> str:
    """Send a photo to the CLI chat. Returns '' on success, else the error text."""
    try:
        from utility.telegram import ROLE_CLI, send_photo
        from utility.telegram_cli import cli_allowed_chat_id

        chat = cli_allowed_chat_id()
        if not chat:
            return "TELEGRAM_CLI_CHAT_ID missing"
        send_photo(ROLE_CLI, chat, path, caption)
        return ""
    except Exception as exc:
        return str(exc)


def cmd_ask(value: str = "") -> tuple[bool, str]:
    """Plain-text LLM call (no GUI, no manual fallback); reply also goes to the clipboard."""
    model, rest = _model_from_token(value)
    system, user = split_system_user(rest)
    if not user:
        return False, "用法：ask [@strata|@gemini] 系统提示词\n---\n用户指令   （没有 --- 时整段都是用户指令）"
    from cli.browser_tasks import write_windows_clipboard
    from utility.llm_api import MODEL_SIMPLE, LLMApi

    api = LLMApi(model or MODEL_SIMPLE)
    api.manual_fallback = False  # never open a Tk window from the bot
    answer = api.generate_text(system, user)
    if not isinstance(answer, str) or not answer.strip():
        return False, f"LLM ({model or MODEL_SIMPLE}) 没有返回内容"
    answer = answer.strip()
    clip_note = "已拷到剪贴板"
    try:
        write_windows_clipboard(answer)
    except Exception as exc:
        clip_note = f"剪贴板失败: {_first_line(exc)}"
    if len(answer) > TELEGRAM_TEXT_LIMIT:
        answer = answer[:TELEGRAM_TEXT_LIMIT] + f"\n… (截断，全文 {len(answer)} 字在剪贴板)"
    return True, f"{answer}\n\n[{getattr(api, '_last_source', '') or model or MODEL_SIMPLE} · {clip_note}]"


def cmd_grok_prepare(value: str = "") -> tuple[bool, str]:
    """Image on clipboard + attach to Grok Imagine composer. Does not submit."""
    path = (value or "").strip().strip('"')
    if not path or not os.path.isfile(path):
        return False, "grokprep：先在 Telegram 发一张图片（照片或图片文件），或 grokprep <图片路径>"
    from cli.browser_tasks import copy_image_file_to_clipboard
    from utility import grok_cdp

    clip_note = "图片已在剪贴板"
    try:
        copy_image_file_to_clipboard(path)
    except Exception as exc:
        clip_note = f"剪贴板失败: {_first_line(exc)}"
    grok_cdp.prepare_imagine(path, status=_status_log)
    return True, (
        f"grokprep ok — {os.path.basename(path)} 已贴进 Grok Imagine（未提交）；{clip_note}。\n"
        "下一步发：grokgo 提示词   （可选：系统提示词 + 一行 --- + 提示词）"
    )


def cmd_grok_go(value: str = "") -> tuple[bool, str]:
    """Prompt into the prepared Imagine tab, submit, wait, image -> clipboard + Telegram photo."""
    system, user = split_system_user(value)
    prompt = "\n\n".join(p for p in (system, user) if p)
    if not prompt:
        return False, "用法：grokgo 提示词   （先发图片做 grokprep）"
    from cli.browser_tasks import copy_image_file_to_clipboard
    from utility import grok_cdp

    img = grok_cdp.run_imagine(prompt, status=_status_log)
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTBOX_DIR / f"grok_{time.strftime('%Y%m%d_%H%M%S')}.png"
    img.save(out, "PNG")
    notes = []
    try:
        copy_image_file_to_clipboard(str(out))
        notes.append("图片已在剪贴板")
    except Exception as exc:
        notes.append(f"剪贴板失败: {_first_line(exc)}")
    err = _notify_photo(str(out), f"grokgo · {prompt[:200]}")
    notes.append("已发到 Telegram" if not err else f"发图失败: {err}")
    return True, f"grokgo ok — {out}\n" + "；".join(notes)


def save_telegram_attachment(file_id: str, filename: str) -> str:
    """Download a Telegram photo/document into INBOX_DIR; returns the local path."""
    from utility.telegram import ROLE_CLI, download_file

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", filename or "image.jpg")
    dest = INBOX_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{safe}"
    download_file(ROLE_CLI, file_id, str(dest))
    return str(dest)


def image_file_from_message(msg: dict) -> tuple[str, str] | None:
    """(file_id, filename) for a Telegram photo or image document, else None."""
    photos = msg.get("photo") or []
    if photos:
        best = max(photos, key=lambda p: (p.get("width", 0) * p.get("height", 0), p.get("file_size", 0)))
        return best.get("file_id"), f"photo_{best.get('file_unique_id', 'x')}.jpg"
    doc = msg.get("document") or {}
    if doc and str(doc.get("mime_type") or "").startswith("image/"):
        return doc.get("file_id"), doc.get("file_name") or "image.png"
    return None
