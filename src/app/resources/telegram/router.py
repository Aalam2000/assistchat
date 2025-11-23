"""
src/app/resources/telegram/router.py
────────────────────────────────────────────────────────────────────────────
REST API маршруты Telegram-провайдера.

Назначение:
    • Управляет Telegram-сессиями и их состояниями (activate, start, stop, status);
    • Поддерживает авторизацию Telethon по session_string;
    • Предоставляет интерфейс фронтенду для работы с ресурсом Telegram;
    • Поддерживает ручную отправку сообщений, проверку подключения и голосовую обработку.
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.app.core.db import get_db
from src.models.resource import Resource
from src.models.user import User
from src.app.core.auth import get_current_user

from src.app.resources.telegram.telegram import session_registry, TelegramWorker
from src.app.resources.telegram.openai_client import OpenAIClient
from src.app.providers import get_active_resources, import_worker

router = APIRouter(prefix="/api/telegram", tags=["Telegram Resource"])


# ─────────────────────────────────────────────────────────────────────────────
# 🔑 АКТИВАЦИЯ TELEGRAM СЕССИИ
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{rid}/activate")
async def activate_resource(rid: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Активирует Telegram-ресурс (создание воркера, запуск Telethon, проверка ключей).
    """
    r = db.get(Resource, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if r.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        worker_cls = import_worker("telegram")
        if not worker_cls:
            raise HTTPException(status_code=500, detail="Telegram worker not found")

        worker = await session_registry.ensure_started(r)
        r.status = "active"
        db.commit()
        return {"ok": True, "message": f"Telegram worker started for {rid}"}
    except Exception as e:
        print(f"[API][Telegram] activate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# ⏹️ ОСТАНОВКА СЕССИИ
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{rid}/stop")
async def stop_resource(rid: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.get(Resource, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if r.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    await session_registry.stop(rid)
    r.status = "pause"
    db.commit()
    return {"ok": True, "message": f"Telegram worker {rid} stopped"}


# ─────────────────────────────────────────────────────────────────────────────
# 🧠 ПРОВЕРКА СТАТУСА
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{rid}/status")
async def get_status(rid: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.get(Resource, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if r.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    sessions = session_registry.status()
    active = rid in sessions
    return {
        "ok": True,
        "active": active,
        "status": r.status,
        "provider": "telegram",
        "last_activity": str(r.last_activity) if r.last_activity else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 🗣️ ОТПРАВКА СООБЩЕНИЯ (из интерфейса)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{rid}/send")
async def send_message(
    rid: str,
    peer_id: int = Form(...),
    text: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = db.get(Resource, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if r.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    worker = session_registry._workers.get(rid)
    if not worker:
        raise HTTPException(status_code=400, detail="Worker not running")

    try:
        await worker.send_message(peer_id, text)
        return {"ok": True, "message": "Message sent"}
    except Exception as e:
        print(f"[API][Telegram] send_message error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 🎧 РАСПОЗНАВАНИЕ ГОЛОСА (upload voice)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{rid}/voice")
async def process_voice(
    rid: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Принимает голосовое сообщение, распознаёт его через OpenAI Whisper и возвращает текст.
    """
    r = db.get(Resource, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if r.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    audio_bytes = await file.read()
    oai = OpenAIClient(user)
    text = await oai.transcribe_audio(audio_bytes)
    return {"ok": True, "text": text}


# ─────────────────────────────────────────────────────────────────────────────
# 📜 ИСТОРИЯ СООБЩЕНИЙ (по peer_id)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{rid}/history")
async def get_history(
    rid: str,
    peer_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Возвращает историю сообщений Telegram (входящих и исходящих) для заданного peer_id.
    """
    from sqlalchemy import select
    from src.models.message import Message

    r = db.get(Resource, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if r.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    rows = (
        db.execute(
            select(Message)
            .where(Message.resource_id == rid, Message.peer_id == peer_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    result = [
        {
            "id": m.id,
            "direction": m.direction,
            "text": m.text,
            "msg_type": m.msg_type,
            "created_at": str(m.created_at),
        }
        for m in reversed(rows)
    ]
    return {"ok": True, "messages": result}


# ─────────────────────────────────────────────────────────────────────────────
# 🧩 ТЕСТ ПОДКЛЮЧЕНИЯ
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{rid}/test")
async def test_connection(rid: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Тестирует подключение OpenAI для данного ресурса.
    """
    r = db.get(Resource, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if r.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    oai = OpenAIClient(user)
    ok = await oai.test_connection()
    return {"ok": ok}
