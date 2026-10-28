"""SAM 3.1 para Bodega: conteo por concepto en imagen y video.

Doc oficial leída (no adivinada):
- ``POST /v1/responses`` con ``model="sam-3.1"``; un mensaje con
  ``input_text`` (frase nominal corta, **un concepto por pedido**) más
  ``input_image`` (``image_url``) o ``input_video`` (``video_url``/``file_id``).
- La salida llega en ``output_text`` con tokens especiales: una línea por
  frame ``<Nf>`` y, por objeto, ``id<|box;...|><|mask;...|>``. Imagen =
  una sola línea ``<0f>``. Cero coincidencias = texto vacío (válido).
- En video el ``id`` de objeto es **estable entre frames** (track ID):
  contar stock en video es contar IDs distintos, no sumar por frame.
- Costo (pricing oficial): USD 2,50 / 1.000 imágenes y USD 0,20 / 1.000
  frames de video, con mínimo de 50 frames por pedido de video.

Fuentes: https://dev.meta.ai/docs/sam/overview ,
https://dev.meta.ai/docs/media-segmentation ,
https://dev.meta.ai/docs/sam/segmenting ,
https://dev.meta.ai/docs/sam/reading-segmentation
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from shield.meta_client import MetaClient, compute_cost_usd

SAM_MODEL = "sam-3.1"
SAM_USD_PER_IMAGE = 2.50 / 1000
SAM_USD_PER_1000_FRAMES = 0.20
SAM_MIN_VIDEO_FRAMES = 50

SamFn = Callable[[str, dict[str, Any]], str]

_FRAME_RE = re.compile(r"<(\d+)f>")
_RECORD_RE = re.compile(r"(\d+)<\|box;([^|]*)\|\><\|mask;([^|]*)\|\>")


@dataclass
class SamRecord:
    object_id: int
    box: dict[str, float]
    mask: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SamFrame:
    frame: int
    records: list[SamRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"frame": self.frame, "records": [r.to_dict() for r in self.records]}


def _parse_fields(raw: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in raw.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            try:
                out[key.strip()] = float(value) if "." in value else int(value)
            except ValueError:
                out[key.strip()] = value
    return out


def _parse_mask(raw: str) -> dict[str, Any]:
    fields = _parse_fields(raw.split(";data=")[0]) if ";data=" in raw else _parse_fields(raw)
    data = raw.split(";data=", 1)[1] if ";data=" in raw else ""
    height = width = 0
    encoding = ""
    payload = data
    parts = data.split(",", 2)
    if len(parts) == 3:
        try:
            height, width = int(parts[0]), int(parts[1])
            encoding = parts[2][:1]
            payload = parts[2][1:]
        except ValueError:
            payload = data
    return {**fields, "height": height, "width": width, "encoding": encoding, "payload": payload}


def parse_sam_output(text: str) -> list[SamFrame]:
    """Parsea el texto ``output_text`` de SAM según la gramática oficial."""
    if not text or not text.strip():
        return []
    frames: list[SamFrame] = []
    # Cada delta de streaming es una línea; también aceptamos todo junto.
    chunks: list[tuple[int, str]] = []
    matches = list(_FRAME_RE.finditer(text))
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunks.append((int(match.group(1)), text[match.end() : end]))
    for frame_no, chunk in chunks:
        records = []
        for rec in _RECORD_RE.finditer(chunk):
            records.append(
                SamRecord(
                    object_id=int(rec.group(1)),
                    box={k: float(v) for k, v in _parse_fields(rec.group(2)).items()},
                    mask=_parse_mask(rec.group(3)),
                )
            )
        frames.append(SamFrame(frame=frame_no, records=records))
    return frames


def sam_cost_usd(*, media_kind: str, frames_processed: int | None = None) -> float:
    if media_kind == "video":
        frames = max(int(frames_processed or 0), SAM_MIN_VIDEO_FRAMES)
        return (frames / 1000) * SAM_USD_PER_1000_FRAMES
    return SAM_USD_PER_IMAGE


def count_from_output(text: str, *, prompt: str, media_kind: str) -> dict[str, Any]:
    """Cuenta instancias: imagen = registros; video = track IDs únicos."""
    frames = parse_sam_output(text)
    per_frame = {str(f.frame): len(f.records) for f in frames}
    track_ids = sorted({r.object_id for f in frames for r in f.records})
    if media_kind == "video":
        count = len(track_ids)
        frames_processed = (max((f.frame for f in frames), default=-1) + 1) if frames else 0
    else:
        count = len(frames[0].records) if frames else 0
        frames_processed = 1 if frames else 0
    return {
        "prompt": prompt,
        "media_kind": media_kind,
        "count": count,
        "track_ids": track_ids,
        "per_frame": per_frame,
        "frames": [f.to_dict() for f in frames],
        "cost_usd": sam_cost_usd(media_kind=media_kind, frames_processed=frames_processed),
    }


def output_text_of(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return str(data["output_text"])
    parts: list[str] = []
    for item in data.get("output") or []:
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                parts.append(str(part.get("text") or ""))
    return "\n".join(p for p in parts if p)


def make_meta_sam_fn(client: MetaClient) -> SamFn:
    """SamFn real sobre ``MetaClient.responses`` (ruta documentada)."""

    def _call(prompt: str, media: dict[str, Any]) -> str:
        kind = str(media.get("kind") or "image")
        if kind == "video":
            video_part: dict[str, Any] = {"type": "input_video"}
            if media.get("file_id"):
                video_part["file_id"] = media["file_id"]
            else:
                video_part["video_url"] = media.get("url") or media.get("video_url") or ""
            media_part = video_part
        else:
            media_part = {
                "type": "input_image",
                "image_url": media.get("url") or media.get("image_url") or "",
            }
        result = client.responses(
            model=SAM_MODEL,
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}, media_part],
                }
            ],
        )
        return output_text_of(result.data)

    return _call


def count_stock(
    media: dict[str, Any],
    prompts: list[str],
    *,
    sam_fn: SamFn | None = None,
    meta_client: MetaClient | None = None,
) -> dict[str, Any]:
    """Cuenta stock: un pedido SAM por concepto (doc: uno por request).

    ``media``: ``{kind: image|video, url|image_url|video_url|file_id}``.
    Sin ``sam_fn`` ni ``meta_client`` se puede pasar ``media["sam_output"]``
    (replay: texto ya obtenido, o dict prompt->texto).
    """
    kind = str(media.get("kind") or "image")
    results: list[dict[str, Any]] = []
    total_cost = 0.0
    for prompt in prompts:
        concept = str(prompt).strip()
        if not concept:
            continue
        replay = media.get("sam_output")
        if isinstance(replay, dict):
            text = str(replay.get(concept) or replay.get(concept.lower()) or "")
        elif isinstance(replay, str):
            text = replay
        elif sam_fn is not None:
            text = sam_fn(concept, media)
        elif meta_client is not None:
            text = make_meta_sam_fn(meta_client)(concept, media)
        else:
            from shield.meta_client import NeedsCredits

            raise NeedsCredits(0, "count_stock requiere sam_fn/meta_client o media['sam_output']")
        counted = count_from_output(text, prompt=concept, media_kind=kind)
        # Costo autoritativo si la API reportó frames procesados.
        usage_frames = media.get("video_frames_processed")
        if kind == "video" and usage_frames:
            counted["cost_usd"] = compute_cost_usd(
                SAM_MODEL, {"video_frames_processed": usage_frames}
            )
        total_cost += float(counted["cost_usd"])
        results.append(counted)
    return {
        "media_kind": kind,
        "counts": results,
        "total_count": sum(int(r["count"]) for r in results),
        "cost_usd": total_cost,
        "model": SAM_MODEL,
    }
