"""M3: percepción SAM 3.1 -> RoomState. Offline: respx y textos grabados."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from shield.meta_client import MetaClient
from shield.physics.contract import RoomState
from shield.physics.perception import (
    ASSUMPTION_KG_PER_BOX_LABEL,
    DEFAULT_KG_PER_BOX,
    interpret_counts,
    perceive_room,
    perception_from_outputs,
)


def _box(obj: int, x: int) -> str:
    return f"{obj}<|box;x1={x};y1=2;x2={x + 9};y2=20;w=100;h=100|><|mask;x=0;y=0;data=5,5,~p{obj}|>"


BOXES_3 = "<0f>" + ",".join(_box(i, i * 15) for i in range(3))
DOOR_1 = "<0f>" + _box(0, 5)
OPEN_OUTPUTS = {
    "cardboard box": BOXES_3,
    "open doorway": DOOR_1,
    "closed door": "",
    "door": DOOR_1,
}
CLOSED_OUTPUTS = {**OPEN_OUTPUTS, "open doorway": "", "closed door": DOOR_1}


def test_interpret_counts_convierte_cajas_a_kg_con_supuesto_rotulado():
    out = interpret_counts(box_count=4, open_door_count=1, door_count=1)
    assert out["box_count"] == 4
    assert out["product_kg"] == 4 * DEFAULT_KG_PER_BOX
    assert out["door_open"] is True
    assert out["door_visible"] is True
    assert out["kg_per_box_label"] == ASSUMPTION_KG_PER_BOX_LABEL


def test_interpret_counts_puerta_no_visible_conserva_estado_previo():
    out = interpret_counts(
        box_count=0, open_door_count=0, door_count=0, previous_door_open=True
    )
    assert out["door_visible"] is False
    assert out["door_open"] is True  # no se inventa un cierre que no se vio


def test_interpret_counts_puerta_visible_cerrada():
    out = interpret_counts(box_count=2, open_door_count=0, door_count=1, closed_door_count=1)
    assert out["door_open"] is False
    assert out["door_visible"] is True
    assert out["door_decided"] is True


def test_interpret_counts_senales_en_conflicto_conserva_estado_previo():
    # «open doorway» y «closed door» a la vez: no se decide, no se inventa.
    out = interpret_counts(
        box_count=1,
        open_door_count=1,
        door_count=1,
        closed_door_count=1,
        previous_door_open=False,
    )
    assert out["door_decided"] is False
    assert out["door_open"] is False


def test_interpret_counts_rechaza_kg_por_caja_no_positivo():
    with pytest.raises(ValueError):
        interpret_counts(box_count=1, open_door_count=0, door_count=0, kg_per_box=0)


def test_perception_from_outputs_actualiza_sin_mutar_estado():
    base = RoomState(product_kg=999.0, door_open=False, air_c=4.0)
    result = perception_from_outputs(
        OPEN_OUTPUTS,
        state=base,
        material_label="AI-generated test image",
    )
    assert result.state.product_kg == 3 * DEFAULT_KG_PER_BOX
    assert result.state.door_open is True
    assert result.state.air_c == 4.0
    assert base.product_kg == 999.0  # el estado de entrada no se muta
    pub = result.public()
    assert pub["box_count"] == 3
    assert pub["evidence"]["model"] == "sam-3.1"
    assert pub["evidence"]["material_label"] == "AI-generated test image"


def test_perception_from_outputs_sin_cajas_es_cero_no_error():
    result = perception_from_outputs(
        {"cardboard box": "", "open doorway": "", "closed door": "", "door": ""},
        state=RoomState(door_open=True),
    )
    assert result.box_count == 0
    assert result.state.product_kg == 0.0
    assert result.state.door_open is True  # puerta no visible: se conserva


def test_perceive_room_con_sam_fn_inyectada_no_toca_red():
    seen: list[str] = []

    def fake(prompt: str, media: dict) -> str:
        seen.append(prompt)
        return CLOSED_OUTPUTS[prompt]

    result = perceive_room(
        "https://example.test/room.png", sam_fn=fake, state=RoomState()
    )
    # Un concepto por pedido SAM.
    assert seen == ["cardboard box", "open doorway", "closed door", "door"]
    assert result.box_count == 3
    assert result.state.door_open is False
    assert result.evidence["total_cost_usd"] == pytest.approx(4 * 2.50 / 1000)
    assert result.evidence["calls"][0]["response_id"] is None  # replay/local


def test_perceive_room_replay_dict_sin_cliente():
    media = {
        "kind": "image",
        "url": "replay://room.png",
        "sam_output": OPEN_OUTPUTS,
    }
    result = perceive_room(media, state=RoomState())
    assert result.box_count == 3
    assert result.state.door_open is True


def test_perceive_room_imagen_vacia_es_error():
    with pytest.raises(ValueError):
        perceive_room("", sam_fn=lambda p, m: "")


def _sam_response(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    prompt = payload["input"][0]["content"][0]["text"]
    text = OPEN_OUTPUTS[prompt]
    return httpx.Response(
        200,
        json={"id": f"resp_{abs(hash(prompt)) % 9999}", "model": "sam-3.1", "output_text": text},
        headers={"x-request-id": "up-123"},
    )


def test_perceive_room_via_meta_client_con_respx(tmp_path):
    with respx.mock(base_url="https://api.meta.ai/v1") as router:
        router.post("/responses").mock(side_effect=_sam_response)
        client = MetaClient(api_key="test-key", replay_dir=tmp_path, fresh=True)
        result = perceive_room(
            "https://example.test/room.png",
            meta_client=client,
            state=RoomState(product_kg=1.0),
            material_label="AI-generated test image",
        )
        client.close()
    assert result.box_count == 3
    assert result.state.product_kg == 3 * DEFAULT_KG_PER_BOX
    assert result.state.door_open is True
    ev = result.evidence
    assert ev["total_cost_usd"] == pytest.approx(4 * 2.50 / 1000)
    assert ev["total_latency_ms"] >= 0
    assert all(c["response_id"] and c["response_id"].startswith("resp_") for c in ev["calls"])
    assert {c["prompt"] for c in ev["calls"]} == {
        "cardboard box",
        "open doorway",
        "closed door",
        "door",
    }
