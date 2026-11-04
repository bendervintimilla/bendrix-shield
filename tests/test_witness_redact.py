"""Redacción RGPD con imágenes sintéticas (nunca fotos reales)."""

from __future__ import annotations

import io

from PIL import Image

from shield.witness.redact import BORDER_RGB, FILL_RGB, redact, scale_box


def _checker(w: int = 900, h: int = 600, cell: int = 6) -> Image.Image:
    img = Image.new("RGB", (w, h), (0, 0, 0))
    px = img.load()
    for y in range(h):
        for x in range(w):
            if (x // cell + y // cell) % 2 == 0:
                px[x, y] = (255, 255, 255)
    return img


def _jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=95)
    return out.getvalue()


def _with_person(w: int = 900, h: int = 600) -> bytes:
    img = _checker(w, h)
    # "persona" roja en (300..400, 200..500) de píxeles reales
    for y in range(200, 500):
        for x in range(300, 400):
            img.putpixel((x, y), (220, 20, 20))
    return _jpeg(img)


def _decode(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    assert img.format == "JPEG"
    return img.convert("RGB")


def _close(a, b, tol=40) -> bool:
    return all(abs(int(x) - int(y)) <= tol for x, y in zip(a, b, strict=True))


def _edge_energy(img: Image.Image) -> float:
    g = img.convert("L")
    w, h = g.size
    px = g.load()
    total = 0
    for y in range(0, h, 3):
        for x in range(1, w):
            total += abs(px[x, y] - px[x - 1, y])
    return total / ((w - 1) * len(range(0, h, 3)))


# Caja SAM en espacio 450x300 (la mitad del cuadro real 900x600).
SAM_BOX = {"x1": 150.0, "y1": 100.0, "x2": 200.0, "y2": 250.0, "w": 450.0, "h": 300.0}


def test_scale_box_scales_to_real_size_with_margin():
    x1, y1, x2, y2 = scale_box(SAM_BOX, 900, 600)
    # real: 300..400 x 200..500; margen 15 % => 15 px en x, 45 px en y
    assert (x1, y1) == (285, 155)
    assert x2 >= 415 and y2 >= 545


def test_person_box_is_covered_by_opaque_silhouette():
    out = redact(_with_person(), [SAM_BOX], 900, 600)
    img = _decode(out)
    assert img.size == (900, 600)
    # Centro de la persona y zona de margen: tapados con gris neutro.
    for xy in [(350, 350), (300, 210), (395, 495), (294, 330)]:
        assert _close(img.getpixel(xy), FILL_RGB), xy
    # Ningún píxel rojo de la persona sobrevive.
    reds = sum(1 for y in range(200, 500, 5) for x in range(300, 400, 5)
               if img.getpixel((x, y))[0] > 180 and img.getpixel((x, y))[1] < 80)
    assert reds == 0
    # Borde ámbar presente.
    assert _close(img.getpixel((286, 350)), BORDER_RGB, tol=60)
    # Fuera de la caja el cuadro sigue nítido (no se difuminó todo).
    assert _edge_energy(img.crop((500, 0, 900, 600))) > 40


def test_label_person_is_drawn():
    out = redact(_with_person(), [SAM_BOX], 900, 600)
    img = _decode(out).crop((290, 160, 410, 230))
    amber = sum(1 for y in range(img.height) for x in range(img.width)
                if _close(img.getpixel((x, y)), BORDER_RGB, tol=70))
    assert amber > 50  # borde + texto 'person'


def test_wrong_src_size_uses_real_decoded_size():
    out = redact(_with_person(), [SAM_BOX], 1234, 99)
    assert _close(_decode(out).getpixel((350, 350)), FILL_RGB)


def _assert_heavily_blurred(original: bytes, out: bytes) -> None:
    assert out != original
    img = _decode(out)
    assert img.size == _decode(original).size
    assert _edge_energy(img) < 8 < _edge_energy(_decode(original))


def test_sam_failed_blurs_whole_frame():
    raw = _with_person()
    _assert_heavily_blurred(raw, redact(raw, None, 900, 600))


def test_zero_boxes_blurs_whole_frame():
    raw = _with_person()
    _assert_heavily_blurred(raw, redact(raw, [], 900, 600))


def test_unparseable_box_blurs_whole_frame():
    raw = _with_person()
    bad = [SAM_BOX, {"x1": 1, "y1": 2}]  # sin w/h ni x2/y2
    _assert_heavily_blurred(raw, redact(raw, bad, 900, 600))
    _assert_heavily_blurred(raw, redact(raw, [{**SAM_BOX, "w": 0}], 900, 600))
    _assert_heavily_blurred(raw, redact(raw, ["no-es-un-dict"], 900, 600))


def test_undecodable_input_returns_placeholder_never_original():
    garbage = b"\xff\xd8\xff" + b"no es una imagen" * 10
    out = redact(garbage, [SAM_BOX], 900, 600)
    assert out != garbage
    img = _decode(out)
    assert _close(img.getpixel((5, 5)), FILL_RGB)


def test_png_input_returns_jpeg_without_exif():
    buf = io.BytesIO()
    _checker(200, 100).save(buf, format="PNG")
    out = redact(buf.getvalue(), [{"x1": 10, "y1": 10, "x2": 50, "y2": 90,
                                   "w": 200, "h": 100}], 200, 100)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert not img.info.get("exif")
