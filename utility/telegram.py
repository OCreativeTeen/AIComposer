"""Shared Telegram Bot API — two independent bots, never mix tokens.

Publish bot (``.env`` ``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_IDS``)
    Outbound only: finished MP4 + YouTube copy after publish.
    Used by ``utility.telegram_notify``.

CLI bot (``.env`` ``TELEGRAM_CLI_BOT_TOKEN`` / ``TELEGRAM_CLI_CHAT_ID``)
    Inbound commands + reply. Used by ``utility.telegram_cli``.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import requests

import config

ROLE_PUBLISH = "publish"
ROLE_CLI = "cli"


def _publish_box() -> dict:
    box = getattr(config, "TELEGRAM_PUBLISH", None)
    return box if isinstance(box, dict) else {}


def _cli_box() -> dict:
    box = getattr(config, "TELEGRAM_CLI", None)
    return box if isinstance(box, dict) else {}


def token_for(role: str) -> str:
    if role == ROLE_PUBLISH:
        return (_publish_box().get("bot_token") or "").strip()
    if role == ROLE_CLI:
        return (_cli_box().get("bot_token") or "").strip()
    raise ValueError(f"unknown telegram role: {role!r} (use ROLE_PUBLISH or ROLE_CLI)")


def warn_if_tokens_overlap() -> None:
    pub = token_for(ROLE_PUBLISH)
    cli = token_for(ROLE_CLI)
    if pub and cli and pub == cli:
        print(
            "WARNING: TELEGRAM_BOT_TOKEN and TELEGRAM_CLI_BOT_TOKEN are identical. "
            "Publish and CLI bots must be different; getUpdates would collide.",
            file=sys.stderr,
            flush=True,
        )


def api_url(role: str, method: str) -> str:
    token = token_for(role)
    if not token:
        env = "TELEGRAM_BOT_TOKEN" if role == ROLE_PUBLISH else "TELEGRAM_CLI_BOT_TOKEN"
        raise RuntimeError(f"{env} is empty — cannot call Telegram {role} bot")
    return f"https://api.telegram.org/bot{token}/{method}"


def api_post(role: str, method: str, **kwargs: Any) -> requests.Response:
    return requests.post(api_url(role, method), **kwargs)


def api_get(role: str, method: str, **kwargs: Any) -> requests.Response:
    return requests.get(api_url(role, method), **kwargs)


def send_message(role: str, chat_id: str, text: str, *, timeout: int = 120) -> None:
    body = text or ""
    chunk = 4000
    if not body:
        body = "(empty)"
    for i in range(0, len(body), chunk):
        part = body[i : i + chunk]
        r = api_post(
            role,
            "sendMessage",
            data={"chat_id": chat_id, "text": part},
            timeout=timeout,
        )
        r.raise_for_status()
        payload = r.json()
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description") or str(payload))


def send_photo(
    role: str,
    chat_id: str,
    path: str,
    caption: str = "",
    *,
    timeout: int = 120,
) -> None:
    cap = (caption or "")[:1024]
    with open(path, "rb") as f:
        r = api_post(
            role,
            "sendPhoto",
            data={"chat_id": chat_id, "caption": cap},
            files={"photo": (os.path.basename(path), f)},
            timeout=timeout,
        )
    r.raise_for_status()
    payload = r.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or str(payload))


def send_video(
    role: str,
    chat_id: str,
    path: str,
    caption: str,
    *,
    timeout: int = 900,
) -> None:
    cap = (caption or "")[:1024]
    with open(path, "rb") as f:
        r = api_post(
            role,
            "sendVideo",
            data={"chat_id": chat_id, "caption": cap},
            files={"video": (os.path.basename(path), f)},
            timeout=timeout,
        )
    r.raise_for_status()
    payload = r.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or str(payload))


def get_updates(
    role: str,
    *,
    offset: int = 0,
    timeout: int = 30,
    request_timeout: int | None = None,
) -> list[dict]:
    if role != ROLE_CLI:
        raise ValueError("getUpdates is only allowed on the CLI bot (ROLE_CLI)")
    wait = request_timeout if request_timeout is not None else timeout + 20
    try:
        r = api_get(
            role,
            "getUpdates",
            params={"offset": offset, "timeout": timeout},
            timeout=wait,
        )
    except requests.exceptions.ReadTimeout:
        return []
    except requests.exceptions.ConnectionError:
        return []
    if r.status_code == 409:
        raise RuntimeError(
            "409 Conflict：另一个听筒已经在 getUpdates。关掉多余的「AIComposer CLI bot」窗口。"
        )
    try:
        r.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Telegram HTTP {r.status_code}") from exc
    payload = r.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or str(payload))
    result = payload.get("result") or []
    return result if isinstance(result, list) else []
