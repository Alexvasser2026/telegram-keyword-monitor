"""Create a Telegram StringSession using QR login (no phone number prompt)."""
import asyncio
import os
from pathlib import Path

import qrcode
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

ROOT = Path(__file__).resolve().parent


def create_qr(url: str, attempt: int) -> Path:
    path = ROOT / f"telegram_login_qr_{attempt}.png"
    image = qrcode.make(url)
    image.save(path)
    return path


def open_image(path: Path) -> None:
    try:
        os.startfile(str(path))  # Windows: open QR image in the default image viewer
    except Exception:
        print(f"Откройте изображение QR-кода вручную: {path}")


def main() -> None:
    try:
        api_id = int(input("API_ID (с https://my.telegram.org/apps): ").strip())
    except ValueError as exc:
        raise SystemExit("API_ID должен быть числом.") from exc

    api_hash = input("API_HASH (символы будут видны при вводе): ").strip()
    if not api_hash:
        raise SystemExit("API_HASH не может быть пустым.")

    async def do_login() -> None:
        client = TelegramClient(StringSession(), api_id, api_hash)
        qr_files = []
        try:
            await client.connect()
            if await client.is_user_authorized():
                print("Этот новый сеанс уже авторизован.")
            else:
                qr_login = await client.qr_login()
                attempt = 1
                while True:
                    qr_path = create_qr(qr_login.url, attempt)
                    qr_files.append(qr_path)
                    print("\nОткрылось изображение QR-кода.")
                    print("На телефоне откройте Telegram → Настройки → Устройства → Подключить устройство.")
                    print("Отсканируйте QR-код с экрана компьютера. Номер телефона вводить не нужно.")
                    open_image(qr_path)
                    try:
                        await qr_login.wait(timeout=60)
                        break
                    except asyncio.TimeoutError:
                        attempt += 1
                        print("QR-код истёк. Создаю новый код…")
                        await qr_login.recreate()
                    except errors.SessionPasswordNeededError:
                        password = input("Включена двухэтапная защита. Введите пароль Telegram: ")
                        await client.sign_in(password=password)
                        break

            me = await client.get_me()
            account = getattr(me, "username", None) or getattr(me, "first_name", None) or "Telegram account"
            session = client.session.save()
            print("\nУСПЕШНО АВТОРИЗОВАНО:", account)
            print("\n=== НАЧАЛО TELEGRAM_SESSION — скопируйте всю строку ниже ===")
            print(session)
            print("=== КОНЕЦ TELEGRAM_SESSION ===")
            print("\nХраните эту строку в секрете: она предоставляет доступ к вашему Telegram-аккаунту.")
        finally:
            await client.disconnect()
            for path in qr_files:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    asyncio.run(do_login())


if __name__ == "__main__":
    main()
