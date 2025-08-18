# scripts/seed_tg_account.py
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def env_or_fail(key: str) -> str:
    v = os.getenv(key)
    if not v:
        print(f"[ERROR] Required env {key} is missing.", file=sys.stderr)
        sys.exit(1)
    return v

def build_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = env_or_fail("DB_USER")
    password = env_or_fail("DB_PASSWORD")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    name = env_or_fail("DB_NAME")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"

def main():
    db_url = build_db_url()

    phone = env_or_fail("TELEGRAM_PHONE_NUMBER")
    app_id = int(env_or_fail("TELEGRAM_API_ID"))
    app_hash = env_or_fail("TELEGRAM_API_HASH")

    label = (os.getenv("TG_ACCOUNT_LABEL") or "Main account").strip() or "Main account"
    reply_policy = (os.getenv("TG_REPLY_POLICY") or "dm_only").strip() or "dm_only"
    twofa_enabled = (os.getenv("TG_TWOFA_ENABLED", "true").strip().lower() in {"1", "true", "yes"})

    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    engine = create_engine(db_url, future=True)

    sql = text("""
        INSERT INTO tg_accounts (
            id, label, phone_e164, tg_user_id, username,
            app_id, app_hash, string_session,
            status, reply_policy, twofa_enabled,
            last_login_at, last_seen_at, session_updated_at,
            created_at, updated_at
        ) VALUES (
            :id, :label, :phone, NULL, NULL,
            :app_id, :app_hash, '',
            'new', :reply_policy, :twofa_enabled,
            :now, :now, :now,
            :now, :now
        )
        ON CONFLICT (phone_e164) DO UPDATE SET
            label = EXCLUDED.label,
            app_id = EXCLUDED.app_id,
            app_hash = EXCLUDED.app_hash,
            reply_policy = EXCLUDED.reply_policy,
            twofa_enabled = EXCLUDED.twofa_enabled,
            updated_at = EXCLUDED.updated_at
        RETURNING id, phone_e164, status, reply_policy, twofa_enabled, created_at, updated_at;
    """)

    with engine.begin() as conn:
        row = conn.execute(sql, {
            "id": record_id,
            "label": label,
            "phone": phone,
            "app_id": app_id,
            "app_hash": app_hash,
            "reply_policy": reply_policy,
            "twofa_enabled": twofa_enabled,
            "now": now,
        }).mappings().first()

    print("[OK] tg_accounts upserted:")
    print(f" id={row['id']}")
    print(f" phone={row['phone_e164']}")
    print(f" status={row['status']}, reply_policy={row['reply_policy']}, twofa_enabled={row['twofa_enabled']}")
    print(f" updated_at={row['updated_at']}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        sys.exit(2)
