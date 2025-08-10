from pathlib import Path

ROOT = Path(__file__).resolve().parent

files = {
    # Docker / App
    "docker/app/Dockerfile": """\
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src /app/src
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
""",

    # Compose (dev)
    "docker-compose.yml": """\
version: "3.9"
services:
  db:
    image: postgres:16.9
    restart: always
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    ports: ["5432:5432"]
    volumes: ["db_data:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build:
      context: .
    dockerfile: docker/app/Dockerfile
    env_file: [.env]
    ports: ["8000:8000"]
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./src:/app/src:ro

volumes:
  db_data:
""",

    # Env (dev)
    ".env": """\
DB_USER=assistuser
DB_PASSWORD=assistpass
DB_NAME=assistdb
DB_HOST=db
DB_PORT=5432
""",

    # Requirements
    "requirements.txt": """\
fastapi==0.115.0
uvicorn[standard]==0.30.6
SQLAlchemy==2.0.31
psycopg[binary]==3.1.19
alembic==1.13.2
pydantic-settings==2.4.0
""",

    # App code
    "src/app/__init__.py": "",
    "src/app/main.py": """\
from fastapi import FastAPI
from .db import check_db

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-ping")
def db_ping():
    return {"db": check_db()}
""",

    "src/app/db.py": """\
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, text

class Settings(BaseSettings):
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432

settings = Settings()  # читает значения из .env через env_file в docker-compose

DATABASE_URL = (
    f"postgresql+psycopg://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def check_db() -> str:
    with engine.connect() as conn:
        ver = conn.execute(text("select version();")).scalar_one()
    return ver
""",

    "src/app/models.py": """\
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
""",
}

def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print(f"SKIP  {path}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"WRITE {path}")

def main():
    for rel, content in files.items():
        write(ROOT / rel, content)
    print("\nScaffold done.")

if __name__ == "__main__":
    main()
