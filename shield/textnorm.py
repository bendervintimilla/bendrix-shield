"""Normalización determinista de texto no confiable antes de los detectores.

Tres capas, sin modelo ni red:

1. ``normalize``: NFKC, quita caracteres de formato invisibles (categoría
   Unicode ``Cf``: zero-width, BOM, guion suave…) y traduce un mapa pequeño
   de confusables cirílicos/griegos a su letra latina.
2. ``decode_base64_segments``: busca segmentos base64 plausibles (16 o más
   caracteres) que decodifiquen a UTF-8 imprimible con letras, y devuelve el
   texto decodificado para analizarlo también.
3. ``compact``: versión sin espacios ni separadores, para buscar secretos
   partidos con espacios, guiones o saltos.

Se usa en el motor de inyección (``shield.policy.injection``) y en el gate
(``shield.gate``). No reescribe lo que se envía: solo agrega vistas que los
detectores también revisan.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata

# Confusables más comunes (UTS #39) que pasan por letras latinas en
# palabras clave: solo cirílico y griego, en minúscula y mayúscula.
_CONFUSABLES: dict[str, str] = {
    # Cirílico
    "а": "a",
    "в": "b",
    "с": "c",
    "ԁ": "d",
    "е": "e",
    "ё": "e",
    "һ": "h",
    "і": "i",
    "ї": "i",
    "ј": "j",
    "к": "k",
    "ӏ": "l",
    "м": "m",
    "о": "o",
    "р": "p",
    "ԛ": "q",
    "ѕ": "s",
    "т": "t",
    "у": "y",
    "ѵ": "v",
    "ԝ": "w",
    "х": "x",
    "А": "A",
    "В": "B",
    "С": "C",
    "Е": "E",
    "Н": "H",
    "І": "I",
    "Ј": "J",
    "К": "K",
    "М": "M",
    "О": "O",
    "Р": "P",
    "Ѕ": "S",
    "Т": "T",
    "У": "Y",
    "Х": "X",
    # Griego
    "α": "a",
    "ε": "e",
    "ι": "i",
    "κ": "k",
    "ν": "v",
    "ο": "o",
    "ρ": "p",
    "τ": "t",
    "υ": "u",
    "χ": "x",
    "Α": "A",
    "Β": "B",
    "Ε": "E",
    "Ζ": "Z",
    "Η": "H",
    "Ι": "I",
    "Κ": "K",
    "Μ": "M",
    "Ν": "N",
    "Ο": "O",
    "Ρ": "P",
    "Τ": "T",
    "Υ": "Y",
    "Χ": "X",
}
_CONFUSABLE_TABLE = str.maketrans(_CONFUSABLES)

_B64_CANDIDATE = re.compile(r"[A-Za-z0-9+/_\-]{16,}={0,2}")
_MIN_B64_LEN = 16


def normalize(text: str) -> str:
    """NFKC + sin caracteres de formato invisibles + confusables a latín."""
    if not text:
        return text
    out = unicodedata.normalize("NFKC", text)
    out = "".join(c for c in out if unicodedata.category(c) != "Cf")
    return out.translate(_CONFUSABLE_TABLE)


def _plausible_text(raw: bytes) -> str | None:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not decoded or any(not (c.isprintable() or c in "\n\r\t") for c in decoded):
        return None
    # Al menos un tercio de letras: descarta números y símbolos sueltos.
    letters = sum(c.isalpha() for c in decoded)
    if letters < 4 or letters * 3 < len(decoded):
        return None
    return decoded


def _decode_one(candidate: str) -> str | None:
    body = candidate.rstrip("=")
    if len(body) < _MIN_B64_LEN:
        return None
    if len(body) % 4 == 1:  # longitud imposible en base64: se descarta el sobrante
        body = body[:-1]
    padded = body + "=" * (-len(body) % 4)
    urlsafe = "-" in body or "_" in body
    if urlsafe and ("+" in body or "/" in body):
        return None
    try:
        if urlsafe:
            raw = base64.urlsafe_b64decode(padded)
        else:
            raw = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        return None
    return _plausible_text(raw)


def decode_base64_segments(text: str) -> list[tuple[str, str]]:
    """Pares (segmento codificado, texto decodificado) plausibles en ``text``."""
    if not text:
        return []
    out: list[tuple[str, str]] = []
    for m in _B64_CANDIDATE.finditer(text):
        decoded = _decode_one(m.group(0))
        if decoded is not None:
            out.append((m.group(0), decoded))
    return out


def compact(text: str) -> str:
    """Solo letras y dígitos, en minúscula: para secretos partidos."""
    return "".join(c for c in text if c.isalnum()).casefold()


def views(text: str) -> list[tuple[str, str]]:
    """Vistas extra de ``text`` para los detectores: (nombre, texto).

    No incluye el texto original. ``normalizado`` solo aparece si cambia
    algo; ``base64`` trae cada segmento decodificado (ya normalizado).
    """
    out: list[tuple[str, str]] = []
    norm = normalize(text)
    if norm != text:
        out.append(("normalizado", norm))
    seen: set[str] = set()
    for source in (text, norm):
        for _, decoded in decode_base64_segments(source):
            decoded_norm = normalize(decoded)
            if decoded_norm not in seen:
                seen.add(decoded_norm)
                out.append(("base64", decoded_norm))
    return out
