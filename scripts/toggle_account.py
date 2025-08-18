import sys
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def db_url():
    return os.getenv("DATABASE_URL")

def toggle(phone, new_status):
    eng = create_engine(db_url(), future=True)
    sql = text("UPDATE tg_accounts SET status = :st WHERE phone_e164 = :ph")
    with eng.begin() as conn:
        conn.execute(sql, {"st": new_status, "ph": phone})
    print(f"[OK] {phone} -> {new_status}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python toggle_account.py <phone> <active|inactive>")
        sys.exit(1)
    toggle(sys.argv[1], sys.argv[2])
