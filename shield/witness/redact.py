"""Redacción RGPD del cuadro de la cámara: siluetas anónimas, falla cerrado.

Cada caja de persona que devuelve SAM 3.1 (coordenadas en el espacio
``w``/``h`` que SAM reporta en la propia caja) se escala al tamaño real
del cuadro, se agranda un 15 % por lado y se tapa con un rectángulo opaco
gris neutro, borde ámbar y la etiqueta ``person``.

Falla cerrado: si SAM falló (``person_boxes is None``), si no hay ninguna
caja parseable (incluido cero personas: un falso negativo de SAM no debe
dejar una cara a la vista) o ante cualquier excepción, se devuelve el
cuadro entero muy difuminado. Si ni siquiera se puede decodificar, se
devuelve un JPEG gris liso. Nunca se devuelve el cuadro original sin
tapar. Siempre se re-codifica: el EXIF original no sale.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

MARGIN = 0.15
FILL_RGB = (96, 96, 96)  # gris neutro opaco
BORDER_RGB = (255, 191, 0)  # ámbar
LABEL = "person"
PLACEHOLDER_SIZE = (320, 180)
JPEG_QUALITY = 85


def _to_jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def placeholder_jpeg(size: tuple[int, int] = PLACEHOLDER_SIZE) -> bytes:
    """JPEG gris liso: último recurso cuando ni se puede decodificar."""
    return _to_jpeg(Image.new("RGB", size, FILL_RGB))


def heavy_blur(img: Image.Image) -> Image.Image:
    """Difuminado fuerte: pixelado a ~1/40 y desenfoque gaussiano encima."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    small = rgb.resize((max(1, w // 40), max(1, h // 40)), Image.Resampling.BILINEAR)
    big = small.resize((w, h), Image.Resampling.BILINEAR)
    return big.filter(ImageFilter.GaussianBlur(radius=max(4, max(w, h) // 60)))


def blur_whole(image_bytes: bytes) -> bytes:
    """Cuadro entero difuminado; si no decodifica, placeholder gris."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.load()
            return _to_jpeg(heavy_blur(img))
    except Exception:  # noqa: BLE001 - falla cerrado
        return placeholder_jpeg()


def reencode_without_exif(image_bytes: bytes) -> bytes:
    """Re-codifica a JPEG sin EXIF ni metadatos. Solo para cuadros con revisión
    humana de sala vacía; ante cualquier fallo devuelve el placeholder gris."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.load()
            clean = Image.new("RGB", img.size)
            clean.paste(img.convert("RGB"))
            return _to_jpeg(clean)
    except Exception:  # noqa: BLE001
        return placeholder_jpeg()


def scale_box(
    box: dict[str, Any], src_w: int, src_h: int, *, margin: float = MARGIN
) -> tuple[int, int, int, int]:
    """Caja SAM (espacio w/h de SAM) -> píxeles reales con margen. Lanza si no es válida."""
    x1, y1, x2, y2 = (float(box[k]) for k in ("x1", "y1", "x2", "y2"))
    bw, bh = float(box["w"]), float(box["h"])
    if bw <= 0 or bh <= 0 or src_w <= 0 or src_h <= 0:
        raise ValueError("dimensiones no válidas")
    if x2 <= x1 or y2 <= y1:
        raise ValueError("caja vacía o invertida")
    sx, sy = src_w / bw, src_h / bh
    x1, x2, y1, y2 = x1 * sx, x2 * sx, y1 * sy, y2 * sy
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return (
        max(0, int(x1 - mx)),
        max(0, int(y1 - my)),
        min(src_w, int(round(x2 + mx + 0.5))),
        min(src_h, int(round(y2 + my + 0.5))),
    )


def _font(px: int) -> Any:
    try:
        return ImageFont.load_default(size=max(10, px))
    except Exception:  # noqa: BLE001 - Pillow antiguo
        return ImageFont.load_default()


def redact(
    image_bytes: bytes,
    person_boxes: Iterable[dict[str, Any]] | None,
    src_w: int | None = None,
    src_h: int | None = None,
) -> bytes:
    """Devuelve un JPEG con cada persona tapada; si algo falla, todo difuminado.

    ``person_boxes``: cajas SAM ``{x1,y1,x2,y2,w,h}``; ``None`` = SAM falló.
    ``src_w``/``src_h``: tamaño real del cuadro; si faltan se lee de la imagen
    (y si no coinciden con la imagen, se usa el de la imagen).
    """
    try:
        if person_boxes is None:
            return blur_whole(image_bytes)
        boxes = list(person_boxes)
        if not boxes:
            return blur_whole(image_bytes)
        with Image.open(io.BytesIO(image_bytes)) as src:
            src.load()
            img = src.convert("RGB")
        # Manda el tamaño decodificado: un src_w/src_h erróneo no debe
        # desalinear las siluetas.
        src_w, src_h = img.size
        rects = [scale_box(b, src_w, src_h) for b in boxes]  # lanza si alguna no parsea
        draw = ImageDraw.Draw(img)
        for x1, y1, x2, y2 in rects:
            border = max(2, min(x2 - x1, y2 - y1) // 25)
            draw.rectangle((x1, y1, x2, y2), fill=FILL_RGB, outline=BORDER_RGB, width=border)
            font = _font(max(10, (y2 - y1) // 12))
            draw.text((x1 + border * 2, y1 + border * 2), LABEL, fill=BORDER_RGB, font=font)
        return _to_jpeg(img)
    except Exception:  # noqa: BLE001 - falla cerrado: nunca el original
        return blur_whole(image_bytes)
