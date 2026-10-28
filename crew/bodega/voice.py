"""Voz de Bodega: Muse Voice Transcribe -> [{item, qty, unit}].

La transcripción real va por ``MetaClient.transcribe_file``
(``POST /v1/asr/transcribe``, ver docs/MODELS.md). El parseo del dictado a
ítems es determinista y sin red, para que replay y tests no dependan de
créditos: acepta dígitos y números en palabras en español.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_UNITS = (
    "unidades",
    "unidad",
    "docenas",
    "docena",
    "paquetes",
    "paquete",
    "cajas",
    "caja",
    "litros",
    "litro",
    "kilos",
    "kilo",
    "kg",
    "ml",
    "l",
    "g",
)

_WORDS: dict[str, int] = {
    "cero": 0,
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "dieciséis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintiun": 21,
    "veintiún": 21,
    "veintidos": 22,
    "veintidós": 22,
    "veintitres": 23,
    "veintitrés": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintiséis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
    "cien": 100,
    "ciento": 100,
}


def _parse_number(tokens: list[str], start: int) -> tuple[float | None, int]:
    """Número en ``tokens[start:]``. Devuelve (valor, tokens consumidos)."""
    if start >= len(tokens):
        return None, 0
    token = tokens[start].strip(".,;:")
    if re.fullmatch(r"\d+(?:[.,]\d+)?", token):
        return float(token.replace(",", ".")), 1
    low = token.lower()
    if low in _WORDS:
        value = _WORDS[low]
        consumed = 1
        # "treinta y cinco", "ciento veinte"...
        if start + 2 < len(tokens) and tokens[start + 1].lower() == "y":
            nxt = tokens[start + 2].strip(".,;:").lower()
            if nxt in _WORDS and _WORDS[nxt] < 10:
                return float(value + _WORDS[nxt]), 3
        if low in ("ciento", "cien") and start + 1 < len(tokens):
            nxt = tokens[start + 1].strip(".,;:").lower()
            if nxt in _WORDS and nxt not in ("ciento", "cien"):
                extra, used = _parse_number(tokens, start + 1)
                if extra is not None:
                    return 100.0 + extra, 1 + used
        return float(value), consumed
    if low == "media":
        return 0.5, 1
    if low == "medio":
        return 0.5, 1
    return None, 0


def parse_stock_dictation(text: str) -> list[dict[str, Any]]:
    """``"doce huevos, 3 litros de leche"`` -> [{item, qty, unit}]."""
    items: list[dict[str, Any]] = []
    segments = re.split(r"[,;\n]", text)
    for segment in segments:
        tokens = segment.strip().split()
        if not tokens:
            continue
        qty, consumed = _parse_number(tokens, 0)
        if qty is None:
            continue
        rest = tokens[consumed:]
        unit = "unidad"
        if rest and rest[0].strip(".,;:").lower() in _UNITS:
            unit = rest[0].strip(".,;:").lower()
            rest = rest[1:]
            if rest and rest[0].lower() == "de":
                rest = rest[1:]
        elif rest and rest[0].lower() == "de":
            rest = rest[1:]
        item = " ".join(t.strip(".,;:") for t in rest).strip().lower()
        if item:
            items.append({"item": item, "qty": qty, "unit": unit})
    return items


def transcribe(
    audio_or_text: Any,
    *,
    meta_client: Any | None = None,
) -> dict[str, Any]:
    """Transcribe (Voice) y parsea el dictado de stock.

    - ``Path``/str de archivo existente + ``meta_client``: Voice real.
    - str que no es archivo: se trata como transcripción ya obtenida
      (replay) y solo se parsea. Sin red ni créditos.
    """
    transcript = ""
    if isinstance(audio_or_text, Path) or (
        isinstance(audio_or_text, str) and Path(audio_or_text).is_file()
    ):
        if meta_client is None:
            from shield.meta_client import NeedsCredits

            raise NeedsCredits(0, "transcribe de archivo requiere meta_client (Voice)")
        result = meta_client.transcribe_file(audio_or_text)
        transcript = str(result.data.get("transcript") or "")
    else:
        transcript = str(audio_or_text or "")
    return {"transcript": transcript, "items": parse_stock_dictation(transcript)}
