"""One-time local helper: create a Telegram StringSession for GitHub Actions.
The session is printed only to the console and is not saved to a file.
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


def main():
    try:
        api_id = int(input("API_ID (from https://my.telegram.org/apps): ").strip())
    except ValueError as exc:
        raise SystemExit("API_ID must be a number") from exc
    api_hash = input("API_HASH (will be visible while typing): ").strip()
    phone = input("Phone number with country code, e.g. +31...: ").strip()

    async def do_login():
        client = TelegramClient(StringSession(), api_id, api_hash)
        try:
            await client.start(phone=phone)
            me = await client.get_me()
            account = getattr(me, "username", None) or getattr(me, "first_name", None) or "Telegram account"
            session = client.session.save()
            print("\nAUTHORIZED AS:", account)
            print("\n=== BEGIN TELEGRAM_SESSION (copy the whole next line) ===")
            print(session)
            print("=== END TELEGRAM_SESSION ===")
            print("\nIMPORTANT: Treat this value like your Telegram password. Do not send it to anyone.")
        finally:
            await client.disconnect()

    asyncio.run(do_login())


if __name__ == "__main__":
    main()
