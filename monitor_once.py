"""Check Telegram group messages since the previous scheduled run.

Designed for GitHub Actions: no long-running process and no local session file.
The Telegram user session and checkpoint encryption key must be stored in Actions secrets.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import requests
from cryptography.fernet import Fernet, InvalidToken
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Chat, Channel

STATE_FILE = Path("state.enc")
API_ID = int(os.getenv("API_ID", "0") or "0")
API_HASH = os.getenv("API_HASH", "").strip()
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_CHAT_ID = os.getenv("BOT_CHAT_ID", "").strip()
STATE_ENCRYPTION_KEY = os.getenv("STATE_ENCRYPTION_KEY", "").strip().encode()
KEYWORDS = [x.strip() for x in os.getenv("KEYWORDS", "").split("|") if x.strip()]
if not KEYWORDS:
    KEYWORDS = [
        "РїРѕРјРѕС‡СЊ", "РїРѕРјРѕРіРё", "РїРѕРјРѕРіРёС‚Рµ", "РїРѕРјРѕС‡СЊ РїРѕР¶Р°Р»СѓР№СЃС‚Р°", "РЅСѓР¶РЅР° РїРѕРјРѕС‰СЊ",
        "РЅСѓР¶РЅР° РІР°С€Р° РїРѕРјРѕС‰СЊ", "РєС‚Рѕ РјРѕР¶РµС‚", "РєС‚Рѕ-РЅРёР±СѓРґСЊ РјРѕР¶РµС‚", "РєС‚Рѕ РЅРёР±СѓРґСЊ РјРѕР¶РµС‚",
        "РєС‚Рѕ Р·РЅР°РµС‚", "РїРѕРґСЃРєР°Р¶РёС‚Рµ", "РїРѕСЃРѕРІРµС‚СѓР№С‚Рµ", "РЅРµ РїРѕР»СѓС‡Р°РµС‚СЃСЏ", "РєР°Рє СЃРґРµР»Р°С‚СЊ",
        "РёС‰Сѓ РїРѕРјРѕС‰СЊ", "РµСЃС‚СЊ РєС‚Рѕ", "РєС‚Рѕ СЂР°Р·Р±РёСЂР°РµС‚СЃСЏ", "РїРѕРјРѕС‰СЊ РЅСѓР¶РЅР°", "РїРѕРјРѕРіРёС‚Рµ РїРѕР¶Р°Р»СѓР№СЃС‚Р°",
    ]
WATCH_GROUPS_RAW = [x.strip() for x in os.getenv("WATCH_GROUPS", "").split(",") if x.strip()]
MAX_TEXT_CHARS = 2600

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def norm(value: str) -> str:
    return (value or "").lower().replace("С‘", "Рµ").strip()


def is_group(entity: Any) -> bool:
    if isinstance(entity, Chat):
        return True
    return isinstance(entity, Channel) and bool(getattr(entity, "megagroup", False))


def matches_group(entity: Any) -> bool:
    if not WATCH_GROUPS_RAW:
        return True
    entity_id = int(getattr(entity, "id", 0) or 0)
    username = (getattr(entity, "username", None) or "").lstrip("@").lower()
    title = norm(getattr(entity, "title", None) or "")
    for item in WATCH_GROUPS_RAW:
        if re.fullmatch(r"-?\d+", item):
            numeric_id = int(item)
            if numeric_id == entity_id or numeric_id == int(f"-100{entity_id}"):
                return True
        elif item.lstrip("@").lower() == username or norm(item) == title:
            return True
    return False


def sender_label(sender: Any) -> str:
    if sender is None:
        return "РќРµ СѓРґР°Р»РѕСЃСЊ РѕРїСЂРµРґРµР»РёС‚СЊ"
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    full = f"{first} {last}".strip()
    username = getattr(sender, "username", None)
    if full and username:
        return f"{full} (@{username})"
    if full:
        return full
    if username:
        return f"@{username}"
    return getattr(sender, "title", None) or "РќРµРёР·РІРµСЃС‚РЅС‹Р№ Р°РІС‚РѕСЂ"


def make_message_link(entity: Any, message_id: int) -> str | None:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    if isinstance(entity, Channel) and bool(getattr(entity, "megagroup", False)):
        return f"https://t.me/c/{entity.id}/{message_id}"
    return None


def send_bot_notification(text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": BOT_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    # Telegram usually includes a useful JSON description even on HTTP 403.
    # Parse it before raising, otherwise requests only reports the generic status.
    try:
        payload = response.json()
    except ValueError:
        payload = {"description": response.text[:1000]}

    if not response.ok or not payload.get("ok"):
        description = payload.get("description") or response.text[:1000] or "Unknown Telegram Bot API error"
        error_code = payload.get("error_code", response.status_code)
        raise RuntimeError(
            f"Telegram Bot API error {error_code} (HTTP {response.status_code}): {description}"
        )


def read_state() -> dict[str, Any] | None:
    if not STATE_FILE.exists():
        return None
    if not STATE_ENCRYPTION_KEY:
        raise RuntimeError("Missing STATE_ENCRYPTION_KEY secret.")
    try:
        raw = Fernet(STATE_ENCRYPTION_KEY).decrypt(STATE_FILE.read_bytes())
        return json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Cannot decrypt state.enc. Do not delete it blindly: check that STATE_ENCRYPTION_KEY is unchanged."
        ) from exc


def write_state(state: dict[str, Any]) -> None:
    encrypted = Fernet(STATE_ENCRYPTION_KEY).encrypt(
        json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    STATE_FILE.write_bytes(encrypted)


async def main() -> None:
    missing = []
    if API_ID <= 0:
        missing.append("API_ID")
    if not API_HASH:
        missing.append("API_HASH")
    if not TELEGRAM_SESSION:
        missing.append("TELEGRAM_SESSION")
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not BOT_CHAT_ID:
        missing.append("BOT_CHAT_ID")
    if not STATE_ENCRYPTION_KEY:
        missing.append("STATE_ENCRYPTION_KEY")
    if missing:
        raise RuntimeError("Add these GitHub Actions secrets: " + ", ".join(missing))

    state = read_state()
    is_first_run = state is None or not state.get("initialized")
    if state is None:
        state = {"initialized": False, "groups": {}}
    groups_state: dict[str, int] = {
        str(k): int(v) for k, v in (state.get("groups") or {}).items()
    }
    changed = False

    client = TelegramClient(StringSession(TELEGRAM_SESSION), API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("TELEGRAM_SESSION is expired or invalid. Generate a new session and update the secret.")
        me = await client.get_me()
        name = getattr(me, "username", None) or getattr(me, "first_name", None) or "Р°РєРєР°СѓРЅС‚"
        logging.info("Connected to Telegram as %s", name)

        dialogs = []
        async for dialog in client.iter_dialogs(limit=None):
            entity = dialog.entity
            if is_group(entity) and matches_group(entity):
                dialogs.append(dialog)

        if is_first_run:
            for dialog in dialogs:
                entity = dialog.entity
                latest = getattr(dialog, "message", None)
                latest_id = int(getattr(latest, "id", 0) or 0)
                groups_state[str(entity.id)] = latest_id
            state = {"initialized": True, "groups": groups_state}
            write_state(state)
            await asyncio.to_thread(
                send_bot_notification,
                "вњ… <b>РњРѕРЅРёС‚РѕСЂРёРЅРі РІРєР»СЋС‡С‘РЅ.</b>\n"
                f"РђРєРєР°СѓРЅС‚: {html.escape(name)}\n"
                f"Р“СЂСѓРїРї РїРѕРґ РЅР°Р±Р»СЋРґРµРЅРёРµРј: {len(dialogs)}\n"
                "Р‘СѓРґСѓ РїСЂРѕРІРµСЂСЏС‚СЊ РЅРѕРІС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ РїСЂРёРјРµСЂРЅРѕ СЂР°Р· РІ 5 РјРёРЅСѓС‚. РЎС‚Р°СЂС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ РЅРµ РїСЂРѕРІРµСЂСЏСЋ.",
            )
            logging.info("Baseline saved for %d groups", len(dialogs))
            return

        scanned = 0
        for dialog in dialogs:
            entity = dialog.entity
            key = str(entity.id)
            latest = getattr(dialog, "message", None)
            latest_id = int(getattr(latest, "id", 0) or 0)
            previous_id = groups_state.get(key)

            # A newly discovered group starts from the current latest message to avoid alert floods.
            if previous_id is None:
                groups_state[key] = latest_id
                changed = True
                continue
            if latest_id <= previous_id:
                continue

            # Read all messages since the previous checkpoint, oldest first.
            async for message in client.iter_messages(entity, min_id=previous_id, reverse=True):
                if message.id <= previous_id or message.id > latest_id:
                    continue
                if getattr(message, "out", False):
                    continue
                body = message.message or ""
                if not body.strip():
                    continue
                normalized = norm(body)
                found = [word for word in KEYWORDS if norm(word) in normalized]
                if not found:
                    continue

                try:
                    sender = await message.get_sender()
                except Exception:
                    sender = None
                title = getattr(entity, "title", None) or "Р“СЂСѓРїРїР° Р±РµР· РЅР°Р·РІР°РЅРёСЏ"
                source_text = body[:MAX_TEXT_CHARS]
                if len(body) > MAX_TEXT_CHARS:
                    source_text += "вЂ¦"
                parts = [
                    "<b>рџ”” РќР°Р№РґРµРЅРѕ СЃРѕРѕР±С‰РµРЅРёРµ РїРѕ РєР»СЋС‡РµРІС‹Рј СЃР»РѕРІР°Рј</b>",
                    f"<b>Р“СЂСѓРїРїР°:</b> {html.escape(title)}",
                    f"<b>РђРІС‚РѕСЂ:</b> {html.escape(sender_label(sender))}",
                    f"<b>РЎРѕРІРїР°РґРµРЅРёСЏ:</b> {html.escape(', '.join(found))}",
                    "",
                    f"<b>РЎРѕРѕР±С‰РµРЅРёРµ:</b>\n{html.escape(source_text)}",
                ]
                link = make_message_link(entity, message.id)
                if link:
                    parts += ["", f'<a href="{html.escape(link, quote=True)}">РћС‚РєСЂС‹С‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ РІ Telegram</a>']
                await asyncio.to_thread(send_bot_notification, "\n".join(parts))
                logging.info("Alert sent: %s | %s", title, ", ".join(found))
            groups_state[key] = latest_id
            changed = True
            scanned += 1

        if changed:
            write_state({"initialized": True, "groups": groups_state})
        logging.info("Done. Groups with new messages checked: %d", scanned)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
