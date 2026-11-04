"""observe() y registro del testigo con SAM falso (formato real de cajas, sin red)."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from shield.meta_client import CallResult
from shield.witness import WitnessRegistry, observe
from shield.witness.redact import FILL_RGB


def _rec(oid: int, x1: int, y1: int, x2: int, y2: int, w: int = 450, h: int = 300) -> str:
    # Mismo formato que la salida cruda real de SAM 3.1 (máscara sin decodificar).
    return (f"{oid}<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={w};h={h}|>"
            f"<|mask;x=0;y=0;data=12,10,~!!UM#K{{%*%WMzy|>")


def _frame(*recs: str) -> str:
    return "<0f>" + "".join(recs) if recs else ""


def _img() -> bytes:
    img = Image.new("RGB", (900, 600), (30, 120, 200))
    for y in range(200, 500):
        for x in range(300, 400):
            img.putpixel((x, y), (220, 20, 20))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    return out.getvalue()


def _fake(outputs: dict[str, str], calls: list | None = None):
    def sam_fn(concept, media):
        if calls is not None:
            calls.append((concept, media["kind"], media["url"][:22]))
        return outputs.get(concept, "")
    return sam_fn


NOW = datetime(2026, 11, 4, 20, 0, tzinfo=UTC)
KW = {"camera": "cocina1", "site": "madrid", "room": "cocina", "captured_at": NOW.isoformat()}


def test_observe_counts_people_door_cost_and_redacts():
    calls: list = []
    sam = _fake({"person": _frame(_rec(0, 150, 100, 200, 250), _rec(1, 10, 10, 40, 90)),
                 "open doorway": _frame(_rec(0, 300, 0, 400, 200)),
                 "closed door": ""}, calls)
    obs = observe(_img(), sam_fn=sam, **KW)
    assert [c[0] for c in calls] == ["person", "open doorway", "closed door"]
    assert calls[0][2] == "data:image/jpeg;base64"
    assert obs.people == 2 and obs.door_open is True and obs.ok
    assert len(obs.person_boxes) == 2 and obs.person_boxes[0]["w"] == 450.0
    assert obs.cost_usd == pytest.approx(3 * 0.0025)
    assert obs.model == "sam-3.1" and obs.source == "live_capture"
    red = Image.open(io.BytesIO(obs.redacted_image)).convert("RGB")
    assert all(abs(a - b) < 40 for a, b in zip(red.getpixel((350, 350)), FILL_RGB, strict=True))
    pub = obs.public()
    assert "redacted_image" not in pub and pub["has_redacted_image"] is True
    json.dumps(pub)  # serializable, sin bytes


@pytest.mark.parametrize("opened,closed,expected", [
    (_frame(_rec(0, 1, 1, 9, 9)), "", True),
    ("", _frame(_rec(0, 1, 1, 9, 9)), False),
    ("", "", None),
    (_frame(_rec(0, 1, 1, 9, 9)), _frame(_rec(0, 1, 1, 9, 9)), None),
])
def test_door_rule_open_doorway_vs_closed_door(opened, closed, expected):
    sam = _fake({"person": "", "open doorway": opened, "closed door": closed})
    assert observe(_img(), sam_fn=sam, **KW).door_open is expected


def test_no_door_concepts_means_unknown_door_and_one_call():
    calls: list = []
    obs = observe(_img(), sam_fn=_fake({"person": ""}, calls), door_concepts=(), **KW)
    assert obs.door_open is None and len(calls) == 1
    assert obs.people == 0 and obs.cost_usd == pytest.approx(0.0025)


def test_sam_failure_fails_closed_blurred_and_stale():
    def boom(concept, media):
        raise RuntimeError("upstream 503")
    raw = _img()
    obs = observe(raw, sam_fn=boom, **KW)
    assert not obs.ok and "upstream 503" in obs.error
    assert obs.people == 0 and obs.person_boxes == [] and obs.door_open is None
    assert obs.redacted_image and obs.redacted_image != raw
    red = Image.open(io.BytesIO(obs.redacted_image)).convert("RGB")
    # El borde nítido rojo/azul de x=300 quedó difuminado.
    left, right = red.getpixel((290, 350)), red.getpixel((310, 350))
    assert abs(left[0] - right[0]) < 120
    reg = WitnessRegistry()
    reg.update(obs)
    assert reg.is_stale("madrid", "cocina", NOW) and reg.presence("madrid", "cocina", NOW) is None


class _FakeClient:
    def __init__(self):
        self.prompts: list[str] = []
        self.closed = False

    def sam_segment_image(self, *, image_url, prompt):
        self.prompts.append(prompt)
        text = _frame(_rec(0, 150, 100, 200, 250)) if prompt == "person" else ""
        return CallResult(data={"id": f"resp_{prompt.replace(' ', '_')}", "output_text": text},
                          model="sam-3.1", cost_usd=0.0025, latency_ms=120.0)

    def close(self):
        self.closed = True


def test_meta_client_path_collects_response_ids_latency_cost():
    client = _FakeClient()
    obs = observe(_img(), meta_client=client, source="playback", **KW)
    assert client.prompts == ["person", "open doorway", "closed door"]
    assert not client.closed  # cliente ajeno: no se cierra
    assert obs.response_ids == ["resp_person", "resp_open_doorway", "resp_closed_door"]
    assert obs.latency_ms == pytest.approx(360.0)
    assert obs.cost_usd == pytest.approx(0.0075)
    assert obs.people == 1 and obs.door_open is None and obs.source == "playback"


def test_empty_image_rejected():
    with pytest.raises(ValueError):
        observe(b"", sam_fn=_fake({}), **KW)


def _obs(people: int, at: datetime, **kw):
    sam = _fake({"person": _frame(*[_rec(i, 1, 1, 9, 9) for i in range(people)])})
    return observe(_img(), sam_fn=sam, door_concepts=(),
                   **{**KW, "captured_at": at.isoformat(), **kw})


def test_registry_presence_staleness_and_latest_wins():
    reg = WitnessRegistry()
    assert reg.is_stale("madrid", "cocina", NOW) and not reg.watches("madrid", "cocina")
    reg.register("madrid", "sala")
    assert reg.watches("madrid", "sala") and reg.presence("madrid", "sala", NOW) is None
    reg.update(_obs(2, NOW))
    assert reg.latest("madrid", "cocina").redacted_image is None  # no guarda bytes
    assert reg.presence("madrid", "cocina", NOW + timedelta(seconds=60)) == 2
    assert reg.presence("Madrid", "Cocina", NOW + timedelta(seconds=60)) == 2
    assert reg.presence("", "cocina", NOW) == 2  # sin site: sala única
    assert reg.is_stale("madrid", "cocina", NOW + timedelta(seconds=121))
    assert reg.presence("madrid", "cocina", NOW + timedelta(seconds=121)) is None
    assert reg.is_stale("madrid", "cocina", NOW - timedelta(seconds=600))  # del futuro
    reg.update(_obs(0, NOW + timedelta(seconds=30)))
    reg.update(_obs(5, NOW - timedelta(seconds=30)))  # más vieja: no pisa
    assert reg.presence("madrid", "cocina", NOW + timedelta(seconds=40)) == 0
    assert reg.presence("madrid", "cocina", NOW + timedelta(seconds=40), max_age_s=5) is None


def test_module_level_registry_functions():
    from shield.witness import registry as r
    r.record(_obs(1, NOW, site="test-module", room="r1"))
    assert r.presence("test-module", "r1", NOW) == 1
    assert not r.is_stale("test-module", "r1", NOW)
