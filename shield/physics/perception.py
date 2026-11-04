"""M3: percepción SAM 3.1 para el gemelo físico de la cámara de frío.

Lee una imagen de la cámara, cuenta cajas y detecta la puerta abierta con
SAM 3.1 (un concepto por pedido, como en ``crew/bodega/sam.py``) y convierte
eso en un :class:`RoomState` actualizado: ``product_kg`` y ``door_open``.

La llamada sale por :class:`shield.meta_client.MetaClient`, igual que
Bodega: todo payload pasa por el gate (``gate.check``) antes de salir y, si
el cliente apunta al gateway de Shield (``base_url`` del gateway), la
llamada queda registrada ahí con su costo. Sin cliente ni ``sam_fn`` se
crea un ``MetaClient`` por defecto; en tests se inyecta ``sam_fn``, un
``media`` con ``sam_output`` grabado o un ``MetaClient`` con transporte
mock (respx). Nada de esto toca red en los tests.

Supuestos rotulados (no mediciones):

- ``DEFAULT_KG_PER_BOX``: kg por caja usados para pasar de conteo a masa
  térmica. Es un supuesto de orden de magnitud, no un peso medido.
- Puerta: el prompt ``open door`` segmentó el panel de la puerta en las
  dos imágenes de prueba reales (abierta y cerrada, 2026-11-04), así que
  no discrimina. Sí discriminaron ``open doorway`` (1 abierta / 0 cerrada)
  y ``closed door`` (0 / 1). Por eso ``door_open`` exige ver
  ``open doorway`` y no ver ``closed door`` (y al revés para cerrada).
  Si no se ve ninguna puerta, o ambos conceptos aparecen, se conserva el
  ``door_open`` previo y la evidencia lo marca; no se inventa el estado.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any

from crew.bodega.sam import SamFn, count_from_output, output_text_of, sam_cost_usd
from shield.meta_client import MetaClient
from shield.physics.contract import RoomState

SAM_MODEL = "sam-3.1"
BOX_PROMPT = "cardboard box"
DOOR_OPEN_PROMPT = "open doorway"
DOOR_CLOSED_PROMPT = "closed door"
DOOR_PROMPT = "door"
PROMPTS = (BOX_PROMPT, DOOR_OPEN_PROMPT, DOOR_CLOSED_PROMPT, DOOR_PROMPT)

DEFAULT_KG_PER_BOX = 10.0
ASSUMPTION_KG_PER_BOX_LABEL = (
    "assumption (not measured): kg_per_box=10.0 kg per cardboard box, "
    "order-of-magnitude for a restaurant cold room"
)


def interpret_counts(
    *,
    box_count: int,
    open_door_count: int,
    door_count: int,
    closed_door_count: int = 0,
    kg_per_box: float = DEFAULT_KG_PER_BOX,
    previous_door_open: bool = False,
) -> dict[str, Any]:
    """Convierte conteos SAM en masa y estado de puerta (determinista)."""
    if kg_per_box <= 0:
        raise ValueError("kg_per_box debe ser positivo")
    if min(box_count, open_door_count, door_count, closed_door_count) < 0:
        raise ValueError("los conteos SAM no pueden ser negativos")
    door_visible = door_count > 0 or open_door_count > 0 or closed_door_count > 0
    # Abierta solo si se ve el vano abierto y no una puerta cerrada (y al revés).
    decided = (open_door_count > 0) != (closed_door_count > 0)
    if decided:
        door_open = open_door_count > 0
    else:  # no visible o señales en conflicto: se conserva lo previo
        door_open = bool(previous_door_open)
    return {
        "box_count": int(box_count),
        "open_door_count": int(open_door_count),
        "closed_door_count": int(closed_door_count),
        "door_count": int(door_count),
        "product_kg": round(int(box_count) * float(kg_per_box), 3),
        "kg_per_box": float(kg_per_box),
        "kg_per_box_label": ASSUMPTION_KG_PER_BOX_LABEL,
        "door_visible": door_visible,
        "door_decided": bool(decided and door_visible),
        "door_open": door_open,
    }


@dataclass
class PerceptionResult:
    """Estado actualizado más la evidencia de cada llamada SAM."""

    state: RoomState
    box_count: int
    product_kg: float
    door_open: bool
    door_visible: bool
    evidence: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        """Vista serializable para el gemelo, la demo y el recorded."""
        return {
            "box_count": self.box_count,
            "product_kg": self.product_kg,
            "door_open": self.door_open,
            "door_visible": self.door_visible,
            "state": {
                "t_min": self.state.t_min,
                "air_c": self.state.air_c,
                "product_c": self.state.product_c,
                "product_kg": self.state.product_kg,
                "setpoint_c": self.state.setpoint_c,
                "compressor_on": self.state.compressor_on,
                "door_open": self.state.door_open,
                "minutes_above_so_far": self.state.minutes_above_so_far,
            },
            "evidence": self.evidence,
        }


def _updated_state(base: RoomState, values: dict[str, Any]) -> RoomState:
    """Copia ``base`` con product_kg/door_open nuevos; no muta la entrada."""
    return RoomState(
        t_min=base.t_min,
        air_c=base.air_c,
        product_c=base.product_c,
        product_kg=float(values["product_kg"]),
        setpoint_c=base.setpoint_c,
        compressor_on=base.compressor_on,
        door_open=bool(values["door_open"]),
        minutes_above_so_far=base.minutes_above_so_far,
    )


def _build(
    counts: dict[str, int],
    calls: list[dict[str, Any]],
    *,
    state: RoomState | None,
    kg_per_box: float,
    material_label: str,
) -> PerceptionResult:
    base = state or RoomState()
    values = interpret_counts(
        box_count=counts[BOX_PROMPT],
        open_door_count=counts[DOOR_OPEN_PROMPT],
        closed_door_count=counts[DOOR_CLOSED_PROMPT],
        door_count=counts[DOOR_PROMPT],
        kg_per_box=kg_per_box,
        previous_door_open=base.door_open,
    )
    evidence = {
        "model": SAM_MODEL,
        "via": "shield-meta-client (gate.check; gateway si base_url es el gateway)",
        "material_label": material_label,
        "prompts": list(PROMPTS),
        "calls": calls,
        "total_cost_usd": round(sum(float(c["cost_usd"]) for c in calls), 6),
        "total_latency_ms": round(sum(float(c["latency_ms"]) for c in calls), 3),
        "box_count": values["box_count"],
        "open_door_count": values["open_door_count"],
        "closed_door_count": values["closed_door_count"],
        "door_count": values["door_count"],
        "door_visible": values["door_visible"],
        "door_decided": values["door_decided"],
        "kg_per_box": values["kg_per_box"],
        "kg_per_box_label": values["kg_per_box_label"],
        "assumptions": [ASSUMPTION_KG_PER_BOX_LABEL],
    }
    return PerceptionResult(
        state=_updated_state(base, values),
        box_count=values["box_count"],
        product_kg=float(values["product_kg"]),
        door_open=bool(values["door_open"]),
        door_visible=bool(values["door_visible"]),
        evidence=evidence,
    )


def perception_from_outputs(
    outputs: dict[str, str],
    *,
    state: RoomState | None = None,
    kg_per_box: float = DEFAULT_KG_PER_BOX,
    material_label: str = "",
) -> PerceptionResult:
    """Arma el resultado desde textos SAM ya obtenidos (replay grabado)."""
    counts: dict[str, int] = {}
    calls: list[dict[str, Any]] = []
    for prompt in PROMPTS:
        text = str(outputs.get(prompt) or "")
        counted = count_from_output(text, prompt=prompt, media_kind="image")
        counts[prompt] = int(counted["count"])
        calls.append(
            {
                "prompt": prompt,
                "response_id": None,
                "upstream_request_id": None,
                "latency_ms": 0.0,
                "cost_usd": float(counted["cost_usd"]),
                "count": int(counted["count"]),
                "track_ids": counted["track_ids"],
                "from_replay": True,
            }
        )
    return _build(counts, calls, state=state, kg_per_box=kg_per_box, material_label=material_label)


def _image_url_of(image: str | bytes | dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Normaliza la entrada a (image_url, media replay o None)."""
    if isinstance(image, bytes):
        if not image:
            raise ValueError("imagen vacía")
        return "data:image/png;base64," + base64.b64encode(image).decode(), None
    if isinstance(image, dict):
        url = str(image.get("url") or image.get("image_url") or "")
        if not url:
            raise ValueError("media sin url/image_url")
        return url, image
    url = str(image or "")
    if not url.strip():
        raise ValueError("imagen vacía: se espera URL, data URI, bytes o media dict")
    return url, None


def perceive_room(
    image: str | bytes | dict[str, Any],
    *,
    state: RoomState | None = None,
    meta_client: MetaClient | None = None,
    sam_fn: SamFn | None = None,
    kg_per_box: float = DEFAULT_KG_PER_BOX,
    material_label: str = "",
) -> PerceptionResult:
    """Percibe la cámara con SAM 3.1 y devuelve el RoomState actualizado.

    ``image``: URL, data URI, bytes PNG/JPEG o media dict de Bodega
    (``{kind, url, sam_output?}``). Un ``sam_output`` dict por prompt se
    usa como replay sin red. Con ``sam_fn`` inyectada tampoco hay red.
    """
    image_url, media = _image_url_of(image)
    if media is not None and isinstance(media.get("sam_output"), dict):
        replay = {str(k): str(v) for k, v in media["sam_output"].items()}
        return perception_from_outputs(
            replay, state=state, kg_per_box=kg_per_box, material_label=material_label
        )
    if media is not None and isinstance(media.get("sam_output"), str):
        only = str(media["sam_output"])
        return perception_from_outputs(
            dict.fromkeys(PROMPTS, only),
            state=state,
            kg_per_box=kg_per_box,
            material_label=material_label,
        )

    counts: dict[str, int] = {}
    calls: list[dict[str, Any]] = []
    client = meta_client
    owns_client = False
    if sam_fn is None and client is None:
        client = MetaClient()
        owns_client = True
    try:
        for prompt in PROMPTS:
            started = time.perf_counter()
            response_id = upstream_id = None
            from_replay = from_cache = False
            if sam_fn is not None:
                text = sam_fn(prompt, media or {"kind": "image", "url": image_url})
                cost = sam_cost_usd(media_kind="image")
                latency = (time.perf_counter() - started) * 1000
            else:
                assert client is not None
                result = client.sam_segment_image(image_url=image_url, prompt=prompt)
                text = output_text_of(result.data)
                cost = float(result.cost_usd)
                latency = float(result.latency_ms)
                response_id = (result.data or {}).get("id") or result.upstream_request_id
                upstream_id = result.upstream_request_id
                from_replay, from_cache = result.from_replay, result.from_cache
            counted = count_from_output(text, prompt=prompt, media_kind="image")
            counts[prompt] = int(counted["count"])
            calls.append(
                {
                    "prompt": prompt,
                    "response_id": response_id,
                    "upstream_request_id": upstream_id,
                    "latency_ms": round(latency, 3),
                    "cost_usd": float(cost),
                    "count": int(counted["count"]),
                    "track_ids": counted["track_ids"],
                    "from_replay": from_replay,
                    "from_cache": from_cache,
                }
            )
    finally:
        if owns_client and client is not None:
            client.close()
    return _build(counts, calls, state=state, kg_per_box=kg_per_box, material_label=material_label)
