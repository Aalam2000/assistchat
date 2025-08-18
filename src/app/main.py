from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from src.common.db import engine  # тут должен быть engine из твоего db.py/common/db.py

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="assistchat demo")

# Отдаём статику (папка static)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Подключаем шаблоны (папка templates)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    data = {}
    with engine.connect() as conn:
        for table in table_names:
            cols = [col["name"] for col in inspector.get_columns(table)]
            rows = conn.execute(text(f"SELECT * FROM {table}")).fetchall()
            data[table] = {"columns": cols, "rows": rows}

    return templates.TemplateResponse("index.html", {"request": request, "data": data})

@app.get("/health")
async def health():
    return "ok"
