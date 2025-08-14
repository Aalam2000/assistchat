from pathlib import Path

from fastapi import FastAPI, Request, APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.common.db import SessionLocal
from src.models.message import Message

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="assistchat dev page")

# Статика (отдаёт /static/js/messages.js и др.)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health", response_class=HTMLResponse)
async def health():
    return "ok"


# ---------- API для messages ----------
class MessageCreate(BaseModel):
    author: str
    content: str
    status: str = "new"

class MessageOut(BaseModel):
    id: str
    author: str
    content: str
    status: str
    ts: str

router = APIRouter(prefix="/api", tags=["messages"])

def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/messages", response_model=List[MessageOut])
def list_messages(db: Session = Depends(get_session)):
    rows = db.execute(select(Message).order_by(Message.ts.desc())).scalars().all()
    return [
        MessageOut(
            id=str(m.id), author=m.author, content=m.content, status=m.status, ts=m.ts.isoformat()
        )
        for m in rows
    ]

@router.post("/messages", response_model=MessageOut)
def create_message(payload: MessageCreate, db: Session = Depends(get_session)):
    if not payload.author or not payload.content:
        raise HTTPException(status_code=400, detail="author and content required")
    m = Message(author=payload.author, content=payload.content, status=payload.status)
    db.add(m)
    db.commit()
    db.refresh(m)
    return MessageOut(id=str(m.id), author=m.author, content=m.content, status=m.status, ts=m.ts.isoformat())

app.include_router(router)
