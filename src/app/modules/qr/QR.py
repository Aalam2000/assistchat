# src/app/modules/qr/QR.py
from PIL import Image, ImageDraw, PngImagePlugin
import qrcode
from qrcode.constants import ERROR_CORRECT_H
import os

def mm_to_px(mm, dpi=300):
    return int(round(mm * dpi / 25.4))

def save_png(img, path, dpi=300, compress_level=9):
    print(f"💾 [QR] Сохранение PNG: {path}")
    img = img.convert("RGBA")
    pnginfo = PngImagePlugin.PngInfo()
    img.info.pop("icc_profile", None)
    img.info.pop("exif", None)
    img.save(
        path,
        format="PNG",
        optimize=True,
        compress_level=compress_level,
        dpi=(dpi, dpi),
        pnginfo=pnginfo,
    )

def build_qr_matrix(data: str, error_correction=ERROR_CORRECT_H, border_modules: int = 1):
    print(f"🧩 [QR] Генерация матрицы для данных длиной {len(data)}")
    qr = qrcode.QRCode(error_correction=error_correction, border=border_modules)
    qr.add_data(data)
    qr.make(fit=True)
    m = qr.get_matrix()
    n = len(m)
    print(f"✅ [QR] Матрица готова: {n}×{n}")
    return m, n, border_modules

def render_matrix_with_center_hole(
    matrix,
    modules_count: int,
    *,
    target_size_mm: float = 30.0,
    dpi: int = 300,
    border_modules: int = 1,
    hole_ratio: float = 0.80,
    fill_color="#000000",
    back_color="#FFFFFF",
) -> Image.Image:
    print(f"🎨 [QR] Рендеринг QR с отверстием {hole_ratio*100:.1f}%")
    target_px = mm_to_px(target_size_mm, dpi)
    box = max(1, target_px // (modules_count + 2 * border_modules))
    img_px = (modules_count + 2 * border_modules) * box
    img = Image.new("RGBA", (img_px, img_px), back_color)
    draw = ImageDraw.Draw(img)
    off = border_modules * box
    hole_px = int(round(img_px * float(hole_ratio)))
    cx0 = (img_px - hole_px) // 2
    cy0 = (img_px - hole_px) // 2
    cx1 = cx0 + hole_px
    cy1 = cy0 + hole_px

    for y in range(modules_count):
        row = matrix[y]
        for x in range(modules_count):
            if not row[x]:
                continue
            x0 = off + x * box
            y0 = off + y * box
            x1 = x0 + box
            y1 = y0 + box
            if (x0 >= cx0 and x1 <= cx1 and y0 >= cy0 and y1 <= cy1):
                continue
            draw.rectangle((x0, y0, x1, y1), fill=fill_color)
    return img

def save_png_and_pdf(img: Image.Image, out_base: str, dpi: int = 300):
    png_path = out_base + ".png"
    pdf_path = out_base + ".pdf"
    print(f"💾 [QR] Сохраняем в файлы: {png_path}, {pdf_path}")
    save_png(img, png_path, dpi=dpi, compress_level=9)
    img.convert("RGB").save(pdf_path, "PDF", resolution=dpi)
    print("✅ [QR] PNG и PDF сохранены")
    return png_path, pdf_path

def generate_qr_with_logo(
    url: str,
    logo_path: str = None,
    out_dir: str = ".",
    file_stem: str = "QR_with_logo",
    qr_size_mm: float = 30.0,
    dpi: int = 300,
    logo_ratio: float = 0.25,
    white_pad_mm: float = 1.0,
    logo_has_alpha=True,
    try_knockout_white=False,
):
    print(f"🚀 [QR] Запуск генерации QR для: {url}")
    os.makedirs(out_dir, exist_ok=True)
    matrix, modules_count, border_modules = build_qr_matrix(
        url, error_correction=ERROR_CORRECT_H, border_modules=1
    )
    qr_img = render_matrix_with_center_hole(
        matrix,
        modules_count,
        target_size_mm=qr_size_mm,
        dpi=dpi,
        border_modules=border_modules,
        hole_ratio=float(logo_ratio),
        fill_color="#000000",
        back_color="#FFFFFF",
    )

    if logo_path and os.path.exists(logo_path):
        try:
            print(f"🖼️ [QR] Вставляем логотип: {logo_path}")
            logo = Image.open(logo_path).convert("RGBA")
            qr_w, qr_h = qr_img.size
            side = int(qr_w * logo_ratio)
            logo = logo.resize((side, side), Image.LANCZOS)
            pad = int(side * 0.05)
            pad_img = Image.new("RGBA", (side + pad * 2, side + pad * 2), (255, 255, 255, 255))
            pad_img.paste(logo, (pad, pad), mask=logo if logo_has_alpha else None)
            pos = ((qr_w - pad_img.width) // 2, (qr_h - pad_img.height) // 2)
            qr_img.paste(pad_img, pos, mask=pad_img)
        except Exception as e:
            print("⚠️ [QR] Ошибка вставки логотипа:", e)
    else:
        print("ℹ️ [QR] Логотип не указан или не найден")

    out_base = os.path.join(out_dir, file_stem)
    print(f"💾 [QR] Сохраняем результат в {out_base}")
    result = save_png_and_pdf(qr_img, out_base, dpi)
    print(f"🏁 [QR] Генерация завершена: {result}")
    return result
