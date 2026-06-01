import os
import asyncio
from telethon import TelegramClient

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
PHONE = os.getenv("TG_PHONE", "")  # +994...

async def main():
    if not API_ID or not API_HASH or not PHONE:
        raise SystemExit("Missing env: TG_API_ID / TG_API_HASH / TG_PHONE")

    client = TelegramClient("probe_session", API_ID, API_HASH)
    await client.connect()

    r = await client.send_code_request(PHONE)
    print("OK: code requested")
    print("phone_code_hash:", r.phone_code_hash)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())