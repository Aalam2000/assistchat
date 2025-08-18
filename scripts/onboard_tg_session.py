import os
import sys
import getpass
import asyncio
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

load_dotenv()

def env_or_fail(k: str) -> str:
    v = os.getenv(k)
    if not v:
        print(f"[ERROR] missing env {k}", file=sys.stderr)
        sys.exit(1)
    return v

def db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = env_or_fail("DB_USER")
    pwd  = env_or_fail("DB_PASSWORD")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    name = env_or_fail("DB_NAME")
    return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{name}"

async def run():
    phone = env_or_fail("TELEGRAM_PHONE_NUMBER")

    eng = create_engine(db_url(), future=True)
    # 1) читаем запись из БД по телефону
    q_sel = text("""
        SELECT id, app_id, app_hash, COALESCE(string_session, '') AS string_session
        FROM tg_accounts
        WHERE phone_e164 = :phone
        LIMIT 1
    """)
    with eng.begin() as conn:
        row = conn.execute(q_sel, {"phone": phone}).mappings().first()
        if not row:
            print("[ERROR] tg_accounts: запись с таким телефоном не найдена. Сначала выполните seed.", file=sys.stderr)
            sys.exit(2)

    api_id = int(row["app_id"])
    api_hash = row["app_hash"]

    print(f"[INFO] Starting Telegram login for {phone}")
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    twofa_used = False
    if not await client.is_user_authorized():
        await client.send_code_request(phone)
        code = input("Enter the login code from Telegram: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            pwd = getpass.getpass("Two-factor password: ")
            await client.sign_in(password=pwd)
            twofa_used = True

    me = await client.get_me()
    session_str = client.session.save()
    now = datetime.now(timezone.utc)

    # 3) сохраняем в БД
    q_upd = text("""
        UPDATE tg_accounts
        SET string_session = :sess,
            status = 'active',
            twofa_enabled = :twofa,
            tg_user_id = :uid,
            username = :uname,
            last_login_at = :now,
            session_updated_at = :now,
            updated_at = :now
        WHERE id = :id
        RETURNING id, phone_e164, status, username, tg_user_id, session_updated_at
    """)
    with eng.begin() as conn:
        saved = conn.execute(q_upd, {
            "sess": session_str,
            "twofa": twofa_used,
            "uid": int(me.id) if me and getattr(me, "id", None) else None,
            "uname": me.username if me else None,
            "now": now,
            "id": row["id"],
        }).mappings().first()

    print("[OK] session saved:")
    print(f" id={saved['id']}")
    print(f" phone={saved['phone_e164']}")
    print(f" status={saved['status']}, username={saved['username']}, tg_user_id={saved['tg_user_id']}")
    print(f" session_updated_at={saved['session_updated_at']}")

    await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[INFO] aborted by user")
        sys.exit(130)
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        sys.exit(2)
