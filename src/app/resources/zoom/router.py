"""
Модуль ресурсов: Zoom
Назначение:
    Обрабатывает загрузку, транскрипцию и отчёты по аудиофайлам.
    Каждый Zoom-ресурс хранит свои файлы и логи в каталоге пользователя.
"""

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request, Depends, File, UploadFile, Body, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session as SASession

from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.models import Resource
from src.app.core.config import BASE_STORAGE
from src.app.resources.zoom.transcribe import transcribe_audio
from openai import OpenAI

router = APIRouter()
client = OpenAI()

AUDIO_EXTS = {".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".webm"}


@router.post("/api/zoom/{rid}/upload")
async def api_zoom_upload(rid: str, request: Request, file: UploadFile = File(...), db: SASession = Depends(get_db)):
    """Загрузка аудиофайла в ресурс Zoom."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    if not file.filename.lower().endswith(".mp3"):
        return JSONResponse({"ok": False, "error": "ONLY_MP3_ALLOWED"}, status_code=400)

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "FILE_TOO_LARGE"}, status_code=400)

    user_dir = BASE_STORAGE / f"user_{user.id}" / f"resource_{rid}" / "uploads"
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / file.filename
    path.write_bytes(contents)
    return {"ok": True, "filename": file.filename}


@router.post("/api/zoom/{rid}/process")
async def api_zoom_process(rid: str, request: Request, payload: dict = Body(...), db: SASession = Depends(get_db)):
    """Транскрибирует выбранный аудиофайл через внутренний worker."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    filename = (payload.get("filename") or "").strip()
    if not filename:
        return JSONResponse({"ok": False, "error": "NO_FILENAME"}, status_code=400)

    user_dir = BASE_STORAGE / f"user_{user.id}" / f"resource_{rid}"
    uploads = user_dir / "uploads"
    transcripts = user_dir / "transcripts"
    transcripts.mkdir(parents=True, exist_ok=True)

    path = uploads / filename
    if not path.exists():
        return JSONResponse({"ok": False, "error": "FILE_NOT_FOUND"}, status_code=404)

    text = transcribe_audio(str(path))
    out = transcripts / f"{filename}.txt"
    out.write_text(text, encoding="utf-8")
    return {"ok": True, "message": "Транскрипция завершена", "length": len(text)}


@router.post("/api/zoom/{rid}/report")
async def api_zoom_report(rid: str, request: Request, payload: dict = Body(...), db: SASession = Depends(get_db)):
    """Создаёт отчёт на основе транскрипта с помощью OpenAI."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    filename = (payload.get("filename") or "").strip()
    prompt = (payload.get("prompt") or "").strip()
    if not filename:
        return JSONResponse({"ok": False, "error": "NO_FILENAME"}, status_code=400)

    user_dir = BASE_STORAGE / f"user_{user.id}" / f"resource_{rid}"
    transcripts = user_dir / "transcripts"
    reports = user_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    t_name = filename if filename.endswith(".txt") else f"{filename}.txt"
    t_path = transcripts / t_name
    if not t_path.exists():
        return JSONResponse({"ok": False, "error": "TRANSCRIPT_NOT_FOUND"}, status_code=404)

    text = t_path.read_text(encoding="utf-8")
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            temperature=0.3,
        )
        report = resp.choices[0].message.content.strip()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"OPENAI_FAILED: {e}"}, status_code=500)

    out_path = reports / t_name.replace(".txt", "_отчет.txt")
    out_path.write_text(report, encoding="utf-8")
    return {"ok": True, "filename": out_path.name, "length": len(report)}


@router.get("/api/zoom/{rid}/report/open", response_class=PlainTextResponse)
def api_zoom_report_open(rid: str, filename: str, request: Request, db: SASession = Depends(get_db)):
    """Возвращает текст отчёта в формате plain/text."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    row = db.get(Resource, UUID(rid))
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    path = BASE_STORAGE / f"user_{user.id}" / f"resource_{rid}" / "reports" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="REPORT_NOT_FOUND")
    return path.read_text(encoding="utf-8")


@router.get("/api/zoom/{rid}/items")
def api_zoom_items(rid: str, request: Request, db: SASession = Depends(get_db)):
    """Возвращает список аудио, транскриптов и отчётов для Zoom-ресурса."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    row = db.get(Resource, UUID(rid))
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    user_dir = BASE_STORAGE / f"user_{user.id}" / f"resource_{rid}"
    uploads_dir = user_dir / "uploads"
    transcripts_dir = user_dir / "transcripts"
    reports_dir = user_dir / "reports"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    items = []

    # пары аудио и транскриптов
    for p in sorted(uploads_dir.glob("*")):
        if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
            continue
        t_name = p.name + ".txt"
        t_path = transcripts_dir / t_name
        items.append({
            "audio": {
                "filename": p.name,
                "size": p.stat().st_size,
                "uploaded": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            },
            "transcript": {
                "filename": t_name,
                "exists": t_path.exists(),
                "size": (t_path.stat().st_size if t_path.exists() else 0),
            },
        })

    # транскрипты без исходников
    for t in sorted(transcripts_dir.glob("*.txt")):
        if not any(it["transcript"]["filename"] == t.name for it in items):
            items.append({
                "audio": None,
                "transcript": {
                    "filename": t.name,
                    "exists": True,
                    "size": t.stat().st_size,
                },
            })

    # отчёты
    for it in items:
        tr_name = it["transcript"]["filename"] if it.get("transcript") else None
        if tr_name:
            base = tr_name.replace(".txt", "_отчет.txt")
            r_path = reports_dir / base
            if r_path.exists():
                it["report"] = {
                    "filename": base,
                    "exists": True,
                    "size": r_path.stat().st_size,
                }
            else:
                it["report"] = {"exists": False}

    return {"ok": True, "items": items}


@router.get("/api/zoom/{rid}/reports")
async def api_zoom_reports(rid: str, request: Request, db: SASession = Depends(get_db)):
    """Возвращает список готовых отчётов для ресурса."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    row = db.get(Resource, UUID(rid))
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    reports_dir = BASE_STORAGE / f"user_{user.id}" / f"resource_{rid}" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    items = []
    for path in reports_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append({
                "filename": path.stem,
                "summary": data.get("summary", ""),
                "transcript": data.get("transcript", ""),
            })
        except Exception as e:
            items.append({
                "filename": path.stem,
                "summary": f"Ошибка чтения ({e})",
                "transcript": "",
            })

    return {"ok": True, "items": items}
