# src/app/resources/zoom/router.py
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter, Request, Depends, HTTPException,
    Query, UploadFile, File, Body
)
from fastapi.responses import JSONResponse, PlainTextResponse
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.app.resources.zoom.transcribe import transcribe_audio
from src.models.resource import Resource

# 🔹 создаём независимого клиента для Zoom
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set for Zoom module")

client = OpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────────────────────
# 1. ИНИЦИАЛИЗАЦИЯ И КОНСТАНТЫ
# ─────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/zoom", tags=["zoom"])
from fastapi import Form
from src.models.resource import Resource

@router.post("/create")
async def create_zoom_resource(
    label: str = Form(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    r = Resource(
        provider="zoom",
        user_id=user.id,
        label=label,
        status="new",
        meta_json={"creds": {}, "phase": "new", "error": None}
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": r.id}

BASE_STORAGE = Path(__file__).resolve().parents[3] / "storage"
AUDIO_EXTS = [".mp3", ".wav", ".m4a"]


# ─────────────────────────────────────────────────────────────
# 2. СЛУЖЕБНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────
def _get_resource_or_403(db: SASession, user, rid: str | UUID) -> Resource:
    try:
        rid_uuid = UUID(str(rid))
    except Exception:
        raise HTTPException(status_code=400, detail="BAD_RESOURCE_ID")

    row = db.execute(
        select(Resource).where(Resource.id == rid_uuid, Resource.user_id == user.id)
    ).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return row


def _storage_root_for(user_id: int, rid: str | UUID) -> Path:
    path = BASE_STORAGE / f"user_{user_id}" / f"resource_{rid}"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ─────────────────────────────────────────────────────────────
# 3. РАБОТА С ЗАДАЧАМИ РЕСУРСА (ЗАГРУЗКА / ТРАНСКРИПЦИЯ / ОТЧЁТ)
# ─────────────────────────────────────────────────────────────

@router.post("/{rid}/upload")
async def api_zoom_upload(
        request: Request,
        rid: str,
        file: UploadFile = File(...),
        db: SASession = Depends(get_db),
):
    """Загрузка аудиофайла в uploads/"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    _get_resource_or_403(db, user, rid)

    if not file.filename.lower().endswith(tuple(AUDIO_EXTS)):
        return JSONResponse({"ok": False, "error": "INVALID_FILE_TYPE"}, status_code=400)

    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "FILE_TOO_LARGE"}, status_code=400)

    uploads_dir = _storage_root_for(user.id, rid) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    dst = uploads_dir / file.filename
    with dst.open("wb") as f:
        f.write(contents)

    return {"ok": True, "filename": file.filename, "size": len(contents)}


@router.post("/{rid}/process")
async def api_zoom_process(
        request: Request,
        rid: str,
        payload: dict = Body(...),
        db: SASession = Depends(get_db),
):
    """Транскрибация аудио → текст"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    _get_resource_or_403(db, user, rid)

    filename = (payload.get("filename") or "").strip()
    if not filename:
        return JSONResponse({"ok": False, "error": "NO_FILENAME"}, status_code=400)

    root = _storage_root_for(user.id, rid)
    uploads_dir = root / "uploads"
    transcripts_dir = root / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)

    src = uploads_dir / filename
    if not src.exists():
        return JSONResponse({"ok": False, "error": "FILE_NOT_FOUND"}, status_code=404)

    try:
        text = transcribe_audio(str(src))
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"TRANSCRIBE_FAILED: {e}"}, status_code=500)

    out_path = transcripts_dir / f"{filename}.txt"
    out_path.write_text(text, encoding="utf-8")

    with (root / "status.log").open("a", encoding="utf-8") as log:
        log.write(f"{datetime.now().isoformat()} transcribed {filename}\n")

    return {"ok": True, "message": "Транскрипция завершена", "length": len(text)}


@router.post("/{rid}/report")
async def api_zoom_report(
        request: Request,
        rid: str,
        payload: dict = Body(...),
        db: SASession = Depends(get_db),
):
    """Создание отчёта по транскрипту через OpenAI"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    _get_resource_or_403(db, user, rid)

    filename = (payload.get("filename") or "").strip()
    prompt = (payload.get("prompt") or "").strip()
    if not filename:
        return JSONResponse({"ok": False, "error": "NO_FILENAME"}, status_code=400)

    root = _storage_root_for(user.id, rid)
    transcripts_dir = root / "transcripts"
    reports_dir = root / "reports"
    reports_dir.mkdir(exist_ok=True)

    t_name = filename if filename.endswith(".txt") else f"{filename}.txt"
    t_path = transcripts_dir / t_name
    if not t_path.exists():
        return JSONResponse({"ok": False, "error": "TRANSCRIPT_NOT_FOUND"}, status_code=404)

    text = t_path.read_text(encoding="utf-8")

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt or "Создай краткий отчёт по стенограмме."},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
        )
        report_text = resp.choices[0].message.content.strip()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"OPENAI_FAILED: {e}"}, status_code=500)

    out_name = t_name.replace(".txt", "_отчет.txt")
    (reports_dir / out_name).write_text(report_text, encoding="utf-8")

    return {"ok": True, "filename": out_name, "length": len(report_text)}


# ─────────────────────────────────────────────────────────────
# 4. ПРЕДСТАВЛЕНИЕ ДАННЫХ (СПИСКИ, ОТКРЫТИЕ, УДАЛЕНИЕ)
# ─────────────────────────────────────────────────────────────

@router.get("/{rid}/items")
async def api_zoom_items(request: Request, rid: str, db: SASession = Depends(get_db)):
    """Отдать фронту комплекс файлов: аудио, транскрипт, отчёт"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    _get_resource_or_403(db, user, rid)

    root = _storage_root_for(user.id, rid)
    uploads = root / "uploads"
    transcripts = root / "transcripts"
    reports = root / "reports"
    for p in (uploads, transcripts, reports):
        p.mkdir(exist_ok=True)

    items = []

    for audio in sorted(uploads.glob("*")):
        if not audio.is_file() or audio.suffix.lower() not in AUDIO_EXTS:
            continue
        t_name = f"{audio.name}.txt"
        r_name = t_name.replace(".txt", "_отчет.txt")
        t_path = transcripts / t_name
        r_path = reports / r_name
        items.append({
            "audio": {
                "filename": audio.name,
                "size": audio.stat().st_size,
                "uploaded": datetime.fromtimestamp(audio.stat().st_mtime).isoformat(),
            },
            "transcript": {
                "filename": t_name,
                "exists": t_path.exists(),
                "size": t_path.stat().st_size if t_path.exists() else 0,
            },
            "report": {
                "filename": r_name,
                "exists": r_path.exists(),
                "size": r_path.stat().st_size if r_path.exists() else 0,
            },
        })

    return {"ok": True, "items": items}


@router.get("/{rid}/transcript/open", response_class=PlainTextResponse)
async def api_zoom_transcript_open(
        request: Request,
        rid: str,
        filename: str = Query(...),
        db: SASession = Depends(get_db),
):
    """Открытие текста транскрипта"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    _get_resource_or_403(db, user, rid)

    path = _storage_root_for(user.id, rid) / "transcripts" / (
        filename if filename.endswith(".txt") else f"{filename}.txt"
    )
    if not path.exists():
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")

    return path.read_text(encoding="utf-8", errors="ignore")


@router.delete("/{rid}/transcript")
async def api_zoom_transcript_delete(
        request: Request,
        rid: str,
        filename: str = Query(...),
        db: SASession = Depends(get_db),
):
    """Удаление транскрипта"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    _get_resource_or_403(db, user, rid)

    path = _storage_root_for(user.id, rid) / "transcripts" / (
        filename if filename.endswith(".txt") else f"{filename}.txt"
    )
    if not path.exists():
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")

    path.unlink()
    return {"ok": True}

@router.delete("/{rid}/audio")
async def api_zoom_delete_audio(
    request: Request,
    rid: str,
    filename: str = Query(...),
    db: SASession = Depends(get_db),
):
    """Удаляет исходный аудиофайл"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    _get_resource_or_403(db, user, rid)
    file_path = _storage_root_for(user.id, rid) / "uploads" / filename
    if not file_path.exists():
        return JSONResponse({"ok": False, "error": "AUDIO_NOT_FOUND"}, status_code=404)

    file_path.unlink()
    return {"ok": True}



@router.get("/{rid}/report/open", response_class=PlainTextResponse)
async def api_zoom_report_open(
        request: Request,
        rid: str,
        filename: str = Query(...),
        db: SASession = Depends(get_db),
):
    """Открытие отчёта"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    _get_resource_or_403(db, user, rid)

    path = _storage_root_for(user.id, rid) / "reports" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="REPORT_NOT_FOUND")

    return path.read_text(encoding="utf-8", errors="ignore")


@router.delete("/{rid}/report")
async def api_zoom_report_delete(
        request: Request,
        rid: str,
        filename: str = Query(...),
        db: SASession = Depends(get_db),
):
    """Удаление отчёта"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    _get_resource_or_403(db, user, rid)

    path = _storage_root_for(user.id, rid) / "reports" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="REPORT_NOT_FOUND")

    path.unlink()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# 5. СПИСОК ГОТОВЫХ ОТЧЁТОВ (для блока loadReports)
# ─────────────────────────────────────────────────────────────
@router.get("/{rid}/reports")
async def api_zoom_reports(
        request: Request,
        rid: str,
        db: SASession = Depends(get_db),
):
    """Возвращает список готовых отчётов для ресурса"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    _get_resource_or_403(db, user, rid)

    reports_dir = _storage_root_for(user.id, rid) / "reports"
    reports_dir.mkdir(exist_ok=True)

    items = []
    for path in sorted(reports_dir.glob("*_отчет.txt")):
        try:
            text = path.read_text(encoding="utf-8")
            # извлекаем первые 300 символов как "summary"
            summary = text[:300].strip().replace("\n", " ")
            items.append({
                "filename": path.name,
                "summary": summary,
                "transcript": text,
            })
        except Exception as e:
            items.append({
                "filename": path.name,
                "summary": f"Ошибка чтения: {e}",
                "transcript": "",
            })

    return {"ok": True, "items": items}
