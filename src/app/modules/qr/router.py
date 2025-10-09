"""
QR-модуль: страница генерации QR и API-эндпойнт /api/qr/build.
Извлечено из main_legacy.py без изменения логики.
"""

import io
import tempfile
import zipfile
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session as SASession
from scripts.QR import generate_qr_with_logo
from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.app.core.templates import render_i18n

router = APIRouter(tags=["QR"])

# ---------------------------------------------------------------------------

@router.get("/qr", response_class=HTMLResponse)
async def qr_page(request: Request, db: SASession = Depends(get_db)):
    """Страница QR-генерации (доступ только авторизованным)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n("qr.html", request, "qr", {"username": user.username})

# ---------------------------------------------------------------------------

@router.post("/api/qr/build")
async def api_qr_build(text: str = Form(...), logo: UploadFile = File(...)):
    """Создание ZIP-архива с PNG и PDF QR-кода."""
    with tempfile.TemporaryDirectory() as tmp:
        logo_path = f"{tmp}/{logo.filename}"
        with open(logo_path, "wb") as f:
            f.write(await logo.read())

        png_path, pdf_path = generate_qr_with_logo(
            url=text,
            logo_path=logo_path,
            out_dir=tmp,
            file_stem="qr_with_logo",
            qr_size_mm=30.0,
            dpi=300,
            logo_ratio=0.1,
            white_pad_mm=1.0,
            logo_has_alpha=True,
            try_knockout_white=False,
        )

        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(png_path, arcname="qr_with_logo.png")
            z.write(pdf_path, arcname="qr_with_logo.pdf")
        mem.seek(0)

        return StreamingResponse(
            mem,
            media_type="application/zip",
            headers={"X-File-Name": "qr_with_logo.zip"},
        )
