# src/runners/init_db.py
def init_db():
    print("ℹ️ Схема БД управляется Alembic-миграциями. Используйте: `alembic upgrade head`")

if __name__ == "__main__":
    init_db()
