"""Extracción de texto de documentos externos: PDF (cuerpo, texto blanco,
metadatos) e imagen (chunk tEXt de PNG o visión Spark). Solo stdlib + Spark."""

from __future__ import annotations

import base64
import re
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Segment:
    location: str  # body | white_text | metadata:<key> | image:text | image:vision
    text: str


@dataclass
class ExtractedDoc:
    doc_id: str
    segments: list[Segment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(s.text for s in self.segments)


def _pdf_unescape(raw: bytes) -> str:
    out = raw.decode("latin-1", errors="ignore")
    return out.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\").replace("\\n", "\n")


def _pdf_streams(data: bytes) -> list[bytes]:
    streams: list[bytes] = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = m.group(1)
        try:
            streams.append(zlib.decompress(raw))
        except zlib.error:
            streams.append(raw)
    return streams


def extract_pdf(data: bytes, doc_id: str = "pdf") -> ExtractedDoc:
    doc = ExtractedDoc(doc_id=doc_id)
    # Metadatos: diccionario /Title (..) /Author (..) etc. y claves XMP simples.
    for key in (b"Title", b"Author", b"Subject", b"Keywords", b"Creator", b"Producer"):
        for m in re.finditer(rb"/" + key + rb"\s*\((.*?)\)", data, re.S):
            text = _pdf_unescape(m.group(1)).strip()
            if text:
                doc.segments.append(Segment(f"metadata:{key.decode()}", text))
    xmp = re.search(rb"<x:xmpmeta.*?</x:xmpmeta>", data, re.S)
    if xmp:
        plain = re.sub(rb"<[^>]+>", b" ", xmp.group(0)).decode("utf-8", errors="ignore")
        plain = " ".join(plain.split())
        if plain:
            doc.segments.append(Segment("metadata:xmp", plain))
    # Cuerpo: operadores Tj/TJ; texto blanco si el color activo es blanco.
    for stream in _pdf_streams(data):
        white = False
        for token in re.finditer(
            rb"(1\s+1\s+1\s+rg|1\s+g|0\s+0\s+0\s+rg|0\s+g)|\((?:\\.|[^\\()])*\)\s*(?:Tj|TJ|'|\")",
            stream,
        ):
            tok = token.group(0)
            if token.group(1):
                white = tok in (b"1 1 1 rg", b"1 g")
                continue
            text = _pdf_unescape(tok[1 : tok.rindex(b")")]).strip()
            # TJ con arreglo: quédate solo con el literal principal ya capturado.
            if text:
                doc.segments.append(Segment("white_text" if white else "body", text))
    if not doc.segments:
        # Último recurso: literales legibles sueltos.
        for m in re.finditer(rb"\(([ -~]{4,})\)", data):
            doc.segments.append(Segment("body", _pdf_unescape(m.group(1))))
    return doc


def extract_png_text(data: bytes, doc_id: str = "image") -> ExtractedDoc:
    doc = ExtractedDoc(doc_id=doc_id)
    if not data.startswith(b"\x89PNG"):
        return doc
    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        if tag == b"tEXt" and b"\x00" in chunk:
            key, value = chunk.split(b"\x00", 1)
            doc.segments.append(
                Segment(
                    f"image:text:{key.decode('latin-1')}",
                    value.decode("utf-8", errors="ignore"),
                )
            )
        elif tag == b"iTXt" and chunk:
            doc.segments.append(Segment("image:text", chunk.decode("utf-8", errors="ignore")))
        pos += 12 + length
        if tag == b"IEND":
            break
    return doc


VisionFn = Callable[[bytes, str], str]


def extract_image_with_vision(
    data: bytes, doc_id: str, vision_fn: VisionFn | None = None
) -> ExtractedDoc:
    doc = extract_png_text(data, doc_id)
    if vision_fn is not None:
        try:
            text = vision_fn(data, doc_id)
            if text:
                doc.segments.append(Segment("image:vision", text))
        except Exception as exc:  # visión es respaldo; el tEXt ya cubre fixtures
            doc.notes.append(f"vision_error:{type(exc).__name__}")
        return doc
    # Visión Spark por defecto (falla suave sin créditos).
    try:
        from shield.meta_client import MetaClient, NeedsCredits

        uri = "data:image/png;base64," + base64.b64encode(data).decode()
        client = MetaClient()
        try:
            result = client.chat_completions(
                model="muse-spark-1.3",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Transcribe todo el texto visible en la imagen, sin comentario. Solo el texto.",  # noqa: E501
                            },
                            {"type": "image_url", "image_url": {"url": uri}},
                        ],
                    }
                ],
            )
            choices = result.data.get("choices") or []
            text = ""
            if choices:
                text = (choices[0].get("message") or {}).get("content") or ""
            if text:
                doc.segments.append(Segment("image:vision", str(text)))
        except NeedsCredits:
            doc.notes.append("vision:needs_credits")
        finally:
            client.close()
    except Exception as exc:
        doc.notes.append(f"vision_unavailable:{type(exc).__name__}")
    return doc


def extract_any(raw: Any, doc_id: str = "doc", vision_fn: VisionFn | None = None) -> ExtractedDoc:
    if isinstance(raw, ExtractedDoc):
        return raw
    if isinstance(raw, (str, Path)) and str(raw) and Path(str(raw)).is_file():
        path = Path(str(raw))
        return extract_any(path.read_bytes(), doc_id=path.name, vision_fn=vision_fn)
    if isinstance(raw, bytes):
        if raw.startswith(b"%PDF"):
            return extract_pdf(raw, doc_id)
        if raw.startswith(b"\x89PNG") or raw[:3] == b"\xff\xd8\xff":
            return extract_image_with_vision(raw, doc_id, vision_fn)
        return ExtractedDoc(doc_id, [Segment("body", raw.decode("utf-8", errors="ignore"))])
    if isinstance(raw, dict):
        doc = ExtractedDoc(doc_id=doc_id)
        for key, value in raw.items():
            if isinstance(value, str) and value:
                loc = (
                    f"metadata:{key}" if key.lower() not in ("text", "body", "content") else "body"
                )
                if key.lower() in ("white_text", "hidden_text"):
                    loc = "white_text"
                doc.segments.append(Segment(loc, value))
            elif isinstance(value, (bytes, bytearray)):
                sub = extract_any(bytes(value), doc_id, vision_fn)
                doc.segments.extend(sub.segments)
        return doc
    return ExtractedDoc(doc_id, [Segment("body", str(raw))])
