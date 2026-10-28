"""Bodega H7: SAM imagen/video, voz y diferencia contra el teórico."""

from crew.bodega.agent import BodegaAgent
from crew.bodega.sam import count_stock, parse_sam_output, sam_cost_usd
from crew.bodega.voice import parse_stock_dictation
from crew.compras.ledger import Ledger
from shield.sdk.pending import PendingRegistry


def _box(obj: int, x: int) -> str:
    return f"{obj}<|box;x1={x};y1=2;x2={x + 9};y2=20;w=100;h=100|><|mask;x=0;y=0;data=5,5,~p{obj}|>"


def test_parse_sam_image_counts_records():
    frames = parse_sam_output("<0f>" + ",".join(_box(i, i * 15) for i in range(3)))
    assert len(frames) == 1
    assert [r.object_id for r in frames[0].records] == [0, 1, 2]
    assert frames[0].records[0].box["x1"] == 0.0
    assert frames[0].records[0].mask["height"] == 5


def test_video_counts_unique_track_ids_not_frames():
    text = "\n".join(
        [
            "<0f>" + ",".join([_box(0, 1), _box(1, 20)]),
            "<1f>" + _box(0, 2),
            "<2f>" + ",".join([_box(0, 3), _box(1, 22), _box(5, 40)]),
        ]
    )
    result = count_stock({"kind": "video", "url": "replay://v.mp4", "sam_output": text}, ["huevo"])
    counted = result["counts"][0]
    assert counted["count"] == 3  # IDs únicos 0, 1, 5 (no 2+1+3 por frame)
    assert counted["track_ids"] == [0, 1, 5]
    assert counted["per_frame"] == {"0": 2, "1": 1, "2": 3}


def test_empty_sam_output_is_zero_not_error():
    result = count_stock({"kind": "image", "sam_output": ""}, ["inexistente"])
    assert result["counts"][0]["count"] == 0
    assert result["total_count"] == 0


def test_sam_costs_match_official_pricing():
    assert sam_cost_usd(media_kind="image") == 2.50 / 1000
    # Mínimo de 50 frames por pedido de video.
    assert sam_cost_usd(media_kind="video", frames_processed=10) == (50 / 1000) * 0.20
    assert sam_cost_usd(media_kind="video", frames_processed=300) == (300 / 1000) * 0.20


def test_one_sam_request_per_concept():
    seen: list[str] = []

    def fake(prompt: str, media: dict) -> str:
        seen.append(prompt)
        return "<0f>" + _box(0, 1)

    agent = BodegaAgent(Ledger(), sam_fn=fake, registry=PendingRegistry())
    result = agent.count_stock({"kind": "image", "url": "replay://x.png"}, ["papa", "huevo"])
    assert seen == ["papa", "huevo"]
    assert result["total_count"] == 2


def test_dictation_to_items():
    items = parse_stock_dictation("doce huevos, 3 litros de leche, treinta y cinco papas")
    assert items == [
        {"item": "huevos", "qty": 12.0, "unit": "unidad"},
        {"item": "leche", "qty": 3.0, "unit": "litros"},
        {"item": "papas", "qty": 35.0, "unit": "unidad"},
    ]


def test_diff_against_theoretical():
    ledger = Ledger()
    ledger.record_purchase(
        supplier="A",
        lines=[{"sku": "papa", "qty": 10, "unit_price": 1.0, "line_total": 10.0}],
        subtotal=10,
        total=10,
    )
    bodega = BodegaAgent(ledger, registry=PendingRegistry())
    diff = bodega.diff_stock({"papa": 7.0})
    assert diff["rows"] == [
        {"item": "papa", "theoretical": 10.0, "counted": 7.0, "diff": -3.0, "status": "faltante"}
    ]
    assert diff["has_diff"] is True
