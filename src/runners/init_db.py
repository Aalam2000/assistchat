# src/runners/init_db.py
from src.common.db import engine, Base
import src.models  # важно: подтянет все модели, иначе таблицы не создадутся

def init_db():
    print("⏳ Создание таблиц...")
    Base.metadata.create_all(bind=engine)
    print("✅ Таблицы успешно созданы")

if __name__ == "__main__":
    init_db()
