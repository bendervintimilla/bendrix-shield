"""La cámara como testigo físico: cuántas personas hay y si la puerta está abierta.

Un pedido SAM 3.1 por concepto (como ``crew/bodega/sam.py``). Personas =
mayor conteo entre los conceptos de persona; las cajas de todos se usan
para tapar (privacidad primero). Puerta con la regla descubierta en
``shield/physics/perception.py``: ``open door`` no discrimina; se exige ver
``open doorway`` y no ``closed door`` (o al revés). Si no se decide, la
puerta queda ``None``: no se inventa.

La observación sale con la imagen YA redactada (``redact.redact``) y si
SAM falla la observación queda con ``error`` y la imagen difuminada
entera: el registro la trata como testigo ausente (falla cerrado).
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from crew.bodega.sam import (
    SAM_MODEL,
    SamFn,
    count_from_output,
    output_text_of,
    parse_sam_output,
    sam_cost_usd,
)
from shield.meta_client import MetaClient
from shield.physics.perception import interpret_counts
from shield.witness.redact import redact

Source = Literal["live_capture", "playback", "fixture"]
DEFAULT_CONCEPTS = ("person",)
DEFAULT_DOOR_CONCEPTS = ("open doorway", "closed door")


@dataclass
class WitnessObservation:
    camera: str
    site: str
    room: str
    captured_at: str  # ISO 8601
    people: int
    door_open: bool | None
    person_boxes: list[dict[str, Any]] = field(default_factory=list)
    model: str = SAM_MODEL
    response_ids: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    redacted_image: bytes | None = None
    source: Source = "live_capture"
    error: str | None = None  # SAM falló: no hay testimonio válido

    @property
    def ok(self) -> bool:
        return self.error is None

    def captured_dt(self) -> datetime:
        from shield.autopilot.events import _parse_ts

        return _parse_ts(self.captured_at)

    def public(self) -> dict[str, Any]:
        """Vista serializable sin bytes de imagen."""
        return {
            "camera": self.camera,
            "site": self.site,
            "room": self.room,
            "captured_at": self.captured_at,
            "people": self.people,
            "door_open": self.door_open,
            "person_boxes": [dict(b) for b in self.person_boxes],
            "model": self.model,
            "response_ids": list(self.response_ids),
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "has_redacted_image": self.redacted_image is not None,
            "source": self.source,
            "ok": self.ok,
            "error": self.error,
        }


def _mime(image_bytes: bytes) -> str:
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def _image_size(image_bytes: bytes) -> tuple[int, int]:
    import io

    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as img:
        return img.size


def _boxes_of(text: str) -> list[dict[str, Any]]:
    frames = parse_sam_output(text)
    if not frames:
        return []
    return [dict(r.box) for r in frames[0].records]


def observe(
    image_bytes: bytes,
    *,
    camera: str,
    site: str,
    room: str,
    captured_at: str,
    sam_fn: SamFn | None = None,
    meta_client: MetaClient | None = None,
    concepts: tuple[str, ...] = DEFAULT_CONCEPTS,
    door_concepts: tuple[str, ...] = DEFAULT_DOOR_CONCEPTS,
    source: Source = "live_capture",
) -> WitnessObservation:
    """Observa un cuadro con SAM 3.1 y devuelve la observación ya redactada.

    Sin ``sam_fn`` ni ``meta_client`` crea un ``MetaClient`` por defecto
    (red real, la llave nunca se imprime). En tests se inyecta ``sam_fn``.
    ``door_concepts`` debe ser ``(abierta, cerrada)`` o vacío (sin puerta).
    """
    if not image_bytes:
        raise ValueError("imagen vacía")
    image_url = f"data:{_mime(image_bytes)};base64," + base64.b64encode(image_bytes).decode()
    media = {"kind": "image", "url": image_url}
    client = meta_client
    owns_client = sam_fn is None and client is None
    response_ids: list[str] = []
    latency_ms = 0.0
    cost = 0.0
    counts: dict[str, int] = {}
    boxes: list[dict[str, Any]] = []
    error: str | None = None
    person_concepts = [c for c in (str(x).strip() for x in concepts) if c]
    doors = [c for c in (str(x).strip() for x in door_concepts) if c]
    try:
        if owns_client:
            client = MetaClient()
        for concept in [*person_concepts, *doors]:
            started = time.perf_counter()
            if sam_fn is not None:
                text = sam_fn(concept, media)
                latency_ms += (time.perf_counter() - started) * 1000
                cost += sam_cost_usd(media_kind="image")
            else:
                assert client is not None
                result = client.sam_segment_image(image_url=image_url, prompt=concept)
                text = output_text_of(result.data)
                latency_ms += float(result.latency_ms) or (time.perf_counter() - started) * 1000
                cost += float(result.cost_usd)
                rid = (result.data or {}).get("id") or result.upstream_request_id
                if rid:
                    response_ids.append(str(rid))
            counts[concept] = int(count_from_output(text, prompt=concept, media_kind="image")[
                "count"])
            if concept in person_concepts:
                boxes.extend(_boxes_of(text))
    except Exception as exc:  # noqa: BLE001 - falla cerrado, se reporta como fallo técnico
        error = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if owns_client and client is not None:
            client.close()

    people = max((counts.get(c, 0) for c in person_concepts), default=0)
    door_open: bool | None = None
    if error is None and len(doors) >= 2:
        verdict = interpret_counts(
            box_count=0, door_count=0,
            open_door_count=counts.get(doors[0], 0),
            closed_door_count=counts.get(doors[1], 0),
        )
        door_open = bool(verdict["door_open"]) if verdict["door_decided"] else None

    try:
        src_w, src_h = _image_size(image_bytes)
    except Exception:  # noqa: BLE001
        src_w = src_h = 0
    redacted = redact(image_bytes, None if error else boxes, src_w, src_h)
    return WitnessObservation(
        camera=camera, site=site, room=room, captured_at=captured_at,
        people=0 if error else people, door_open=door_open,
        person_boxes=[] if error else boxes, model=SAM_MODEL,
        response_ids=response_ids, latency_ms=round(latency_ms, 3),
        cost_usd=round(cost, 6), redacted_image=redacted, source=source, error=error,
    )
