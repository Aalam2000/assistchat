# scripts/QR.py
from PIL import Image, ImageDraw, PngImagePlugin
import qrcode
from qrcode.constants import ERROR_CORRECT_H
import os

def mm_to_px(mm, dpi=300):
    return int(round(mm * dpi / 25.4))

def save_png(img, path, dpi=300, compress_level=9):
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
    qr = qrcode.QRCode(error_correction=error_correction, border=border_modules)
    qr.add_data(data)
    qr.make(fit=True)
    m = qr.get_matrix()
    n = len(m)
    return m, n, border_modules

def render_matrix_with_center_hole(
    matrix,
    modules_count: int,
    *,
    target_size_mm: float = 30.0,
    dpi: int = 300,
    border_modules: int = 1,
    hole_ratio: float = 0.80,   # ~40% стороны → ≈ 16% площади
    fill_color="#000000",
    back_color="#FFFFFF",
) -> Image.Image:
    target_px = mm_to_px(target_size_mm, dpi)
    box = max(1, target_px // (modules_count + 2 * border_modules))
    img_px = (modules_count + 2 * border_modules) * box

    img = Image.new("RGBA", (img_px, img_px), back_color)
    draw = ImageDraw.Draw(img)

    inner_px = modules_count * box
    off = border_modules * box

    # размеры «окна» по центру — теперь считаем от всего изображения
    hole_px = int(round(img_px * float(hole_ratio)))
    hole_px = max(1, min(hole_px, img_px - 2 * off))  # страховка
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
    save_png(img, png_path, dpi=dpi, compress_level=9)
    img.convert("RGB").save(pdf_path, "PDF", resolution=dpi)
    return png_path, pdf_path

def generate_qr_with_logo(
    url: str,
    logo_path: str = None,
    out_dir: str = ".",
    file_stem: str = "QR_no_logo",
    qr_size_mm: float = 30.0,
    dpi: int = 300,
    logo_ratio: float = 0.40,     # трактуем как долю стороны QR для «дырки»
    white_pad_mm: float = 0.0,
    logo_has_alpha=True,
    try_knockout_white=False,
):
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

    out_base = os.path.join(out_dir, file_stem)
    return save_png_and_pdf(qr_img, out_base, dpi)
