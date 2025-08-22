# qr_with_logo_v2.py
# QR с логотипом в центре + "оздоровление" логотипа из TIFF/PNG (обрезка, чистка, сжатие).

from PIL import Image, ImageDraw, PngImagePlugin
import qrcode
from qrcode.constants import ERROR_CORRECT_H
import os

# ---------- Утилиты ----------

def mm_to_px(mm, dpi=300):
    return int(round(mm * dpi / 25.4))

def sanitize_transparent_pixels(img):
    """Убираем цвет под полностью прозрачными пикселями (RGB->0 там, где A=0),
    чтобы вокруг логотипа не проступал 'белый ореол' на печати."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                px[x, y] = (0, 0, 0, 0)
    return img

def trim_transparent_border(img, alpha_threshold=0):
    """Обрезаем пустые прозрачные поля по альфа-каналу."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.split()[-1]
    bbox = alpha.point(lambda a: 255 if a > alpha_threshold else 0).getbbox()
    return img.crop(bbox) if bbox else img

def drop_white_to_alpha(img, tolerance=10):
    """Опционально: превращаем почти-белый фон в прозрачный (если TIFF без альфы)."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    thr = 255 - int(tolerance)
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r >= thr and g >= thr and b >= thr:
                px[x, y] = (r, g, b, 0)
    return img

def save_png(img, path, dpi=300, compress_level=9):
    """Сохраняем PNG без лишних метаданных, с dpi и максимальным сжатием."""
    img = img.convert("RGBA")
    pnginfo = PngImagePlugin.PngInfo()
    # Чистим чужие профили/EXIF
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

# ---------- QR ----------

def build_qr_image(url: str,
                   target_size_mm: float = 30.0,
                   dpi: int = 300,
                   border_modules: int = 4,
                   error_correction=ERROR_CORRECT_H,
                   fill_color="#000000",
                   back_color="#FFFFFF"):
    """Генерируем QR точного нужного размера (с кратным масштабом без сглаживания)."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=error_correction,
        box_size=10,
        border=border_modules
    )
    qr.add_data(url)
    qr.make(fit=True)
    modules = getattr(qr, "modules_count", len(qr.get_matrix()))
    target_px = mm_to_px(target_size_mm, dpi)

    box_size = max(1, (target_px // (modules + 2 * border_modules)))
    qr2 = qrcode.QRCode(
        version=qr.version,
        error_correction=error_correction,
        box_size=box_size,
        border=border_modules
    )
    qr2.add_data(url)
    qr2.make(fit=False)
    img = qr2.make_image(fill_color=fill_color, back_color=back_color).convert("RGBA")

    if img.size[0] < target_px:
        scale = round(target_px / img.size[0])
        img = img.resize((img.size[0]*scale, img.size[1]*scale), resample=Image.NEAREST)
    return img, dpi

# ---------- ЛОГО ----------

def prepare_logo(logo_path: str,
                 dest_logo_w_px: int,
                 has_alpha=True,
                 try_knockout_white=False,
                 knockout_tolerance=10):
    """
    Приводим логотип к «здоровому» виду:
    - загружаем TIFF/PNG/SVG(rasterized by PIL) -> RGBA,
    - по желанию выбиваем белый фон,
    - обрезаем прозрачные поля,
    - чистим цвет под прозрачностью,
    - масштабируем в нужную ширину.
    Возвращает готовый RGBA.
    """
    logo = Image.open(logo_path).convert("RGBA")

    if try_knockout_white and not has_alpha:
        logo = drop_white_to_alpha(logo, tolerance=knockout_tolerance)

    # Обрезка лишних прозрачных краёв
    logo = trim_transparent_border(logo)

    # Чистим RGB под альфой
    logo = sanitize_transparent_pixels(logo)

    # Масштаб по ширине (высота по пропорции)
    w, h = logo.size
    if w != dest_logo_w_px:
        scale = dest_logo_w_px / float(w)
        logo = logo.resize((dest_logo_w_px, int(round(h * scale))), Image.LANCZOS)
    return logo

def paste_logo_center(qr_img: Image.Image,
                      logo_img: Image.Image,
                      white_pad_px: int = 24,
                      rounded=True):
    """Кладём подготовленный логотип в центр QR на белую подложку."""
    qr = qr_img.copy()
    W, H = qr.size
    lw, lh = logo_img.size
    cx, cy = W // 2, H // 2

    # Белая подложка под лого
    under = Image.new("RGBA", (lw + 2*white_pad_px, lh + 2*white_pad_px), (255, 255, 255, 0))
    draw = ImageDraw.Draw(under)
    if rounded:
        r = max(6, min(under.size) // 4)
        draw.rounded_rectangle([0, 0, under.size[0]-1, under.size[1]-1], radius=r, fill=(255,255,255,255))
    else:
        draw.rectangle([0, 0, under.size[0]-1, under.size[1]-1], fill=(255,255,255,255))

    ux, uy = cx - under.size[0]//2, cy - under.size[1]//2
    qr.alpha_composite(under, dest=(ux, uy))

    lx, ly = cx - lw//2, cy - lh//2
    qr.alpha_composite(logo_img, dest=(lx, ly))
    return qr

def save_png_and_pdf(img: Image.Image, out_base: str, dpi: int = 300):
    png_path = out_base + ".png"
    pdf_path = out_base + ".pdf"
    save_png(img, png_path, dpi=dpi, compress_level=9)
    img.convert("RGB").save(pdf_path, "PDF", resolution=dpi)  # PDF для типографии
    return png_path, pdf_path

# ---------- Пайплайн ----------

def generate_qr_with_logo(url: str,
                          logo_path: str,
                          out_dir: str = ".",
                          file_stem: str = "QR_Valentina",
                          qr_size_mm: float = 30.0,
                          dpi: int = 300,
                          logo_ratio: float = 0.20,
                          white_pad_mm: float = 2.0,
                          logo_has_alpha=True,
                          try_knockout_white=False):
    os.makedirs(out_dir, exist_ok=True)

    # 1) QR
    qr_img, dpi_used = build_qr_image(url, target_size_mm=qr_size_mm, dpi=dpi)

    # 2) Подготовка логотипа под точную ширину
    target_logo_w = int(round(qr_img.size[0] * logo_ratio))
    logo_img = prepare_logo(
        logo_path,
        dest_logo_w_px=target_logo_w,
        has_alpha=logo_has_alpha,
        try_knockout_white=try_knockout_white,
        knockout_tolerance=10
    )

    # 3) Белая подложка под логотип (в пикселях по физ. миллиметрам)
    white_pad_px = mm_to_px(white_pad_mm, dpi_used)

    # 4) Сборка
    qr_final = paste_logo_center(qr_img, logo_img, white_pad_px=white_pad_px, rounded=True)

    # 5) Сохранение
    out_base = os.path.join(out_dir, file_stem)
    return save_png_and_pdf(qr_final, out_base, dpi_used)

# ---------- Пример ----------

if __name__ == "__main__":
    URL = "https://amarant.world/cay-valentina/"
    LOGO = "C:\\DATA\\PROJECTS\\assistchat\\tmp\\logo_amarant.tiff"
    OUT_DIR = "C:\\DATA\\PROJECTS\\assistchat\\tmp"

    paths = generate_qr_with_logo(
        url=URL,
        logo_path=LOGO,
        out_dir=OUT_DIR,
        file_stem="QR_Valentina",
        qr_size_mm=30.0,      # сторона QR ~30 мм
        dpi=300,
        logo_ratio=0.20,      # ≤ 0.22 при ECC=H
        white_pad_mm=2.0,     # поля белой "таблички"
        logo_has_alpha=True,  # у тебя TIFF c альфой — оставляем True
        try_knockout_white=False  # если вдруг TIFF без альфы — поставить True
    )
    print("Saved:", paths)
