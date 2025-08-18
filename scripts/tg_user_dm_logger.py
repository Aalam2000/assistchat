import os
import sys
import asyncio
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, text as sql_text
from telethon import TelegramClient, events
from telethon.sessions import StringSession

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

async def main():
    phone = env_or_fail("TELEGRAM_PHONE_NUMBER")
    eng = create_engine(db_url(), future=True)

    # 1) берём активную учётку
    q = sql_text("""
        SELECT id, app_id, app_hash, string_session
        FROM tg_accounts
        WHERE phone_e164 = :phone AND status = 'active' AND length(string_session) > 0
        LIMIT 1
    """)
    with eng.begin() as conn:
        row = conn.execute(q, {"phone": phone}).mappings().first()
        if not row:
            print("[ERROR] Active account with session not found. Run onboard_tg_session.py first.", file=sys.stderr)
            sys.exit(2)

    account_id = row["id"]
    api_id = int(row["app_id"])
    api_hash = row["app_hash"]
    session_str = row["string_session"]

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    me = await client.get_me()
    print(f"[INFO] Logged in as @{getattr(me,'username', None)} (id={getattr(me, 'id', None)}). Listening for incoming DMs...")

    @client.on(events.NewMessage(incoming=True))
    async def on_new_message(event: events.NewMessage.Event):
        try:
            if not event.is_private or event.out:
                return

            msg = event.message
            telegram_msg_id = int(msg.id)
            peer_id = int(event.sender_id or 0)
            msg_text = msg.message or ""

            # антидубль
            sql_seen = sql_text("""
                INSERT INTO updates_seen (account_id, chat_id, message_id)
                VALUES (:acc, :chat, :mid)
                ON CONFLICT DO NOTHING
                RETURNING 1
            """)
            with eng.begin() as conn:
                inserted = conn.execute(sql_seen, {
                    "acc": account_id,
                    "chat": peer_id,
                    "mid": telegram_msg_id,
                }).first()

            if not inserted:
                return

            # запись в messages
            sql_msg = sql_text("""
                INSERT INTO messages (
                    id, account_id, peer_id, peer_type, chat_id, msg_id,
                    direction, msg_type, text, tokens_in, tokens_out, latency_ms, created_at
                ) VALUES (
                    :id, :acc, :peer, 'user', :chat, :mid,
                    'in', 'text', :text, NULL, NULL, NULL, :now
                )
            """)
            with eng.begin() as conn:
                conn.execute(sql_msg, {
                    "id": str(uuid.uuid4()),
                    "acc": account_id,
                    "peer": peer_id,
                    "chat": peer_id,
                    "mid": telegram_msg_id,
                    "text": msg_text,
                    "now": datetime.now(timezone.utc),
                })

            print(f"[IN] from {peer_id}: {msg_text[:80]!r} (msg_id={telegram_msg_id})")

        except Exception as e:
            print(f"[WARN] handler error: {e}", file=sys.stderr)

    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        sys.exit(2)
