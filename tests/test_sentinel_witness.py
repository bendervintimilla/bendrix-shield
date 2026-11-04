"""Sección «Surveillance» de Sentinel con cámaras reales (datos sintéticos del test).

Nada de fotos reales: las «imágenes» son JPEG mínimos generados aquí mismo.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from web.app import create_panel_app
from web.sentinel_witness import eval_summary, load_observations, surveillance_state

# JPEG sintético mínimo (SOI + APP0 + relleno + EOI): no es una foto.
SYNTH_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + bytes(64) + b"\xff\xd9"
)
SYNTH_EMPTY = SYNTH_JPEG[:-2] + b"\x01\xff\xd9"


def _obs(camera="cocina1", at="2026-11-04T20:44:00+01:00", people=1, source="live_capture",
         **over):
    base = {
        "camera": camera, "site": "madrid", "room": camera, "captured_at": at,
        "people": people, "door_open": None, "person_boxes": [{"x": 1}] * people,
        "model": "sam-3.1", "response_ids": ["resp_test_abcdefghijklmnop"],
        "latency_ms": 812.4, "cost_usd": 0.0025, "has_redacted_image": True,
        "source": source, "ok": True, "error": None,
    }
    base.update(over)
    return base


def _img_name(camera, stamp):
    return f"{camera}_{stamp}.redacted.jpg"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("SHIELD_REPLAY_HOME", "1")
    monkeypatch.delenv("SHIELD_SENTINEL_HOME", raising=False)
    monkeypatch.delenv("SHIELD_WITNESS_DIR", raising=False)
    return TestClient(create_panel_app())


@pytest.fixture()
def wdir(tmp_path):
    obs = [
        _obs("cocina1", "2026-11-04T20:44:00+01:00", 1),
        _obs("pasillo", "2026-11-04T20:50:02+01:00", 7),
        _obs("cocina1-noche-0300", "2026-11-04T20:46:45+01:00", 0, "playback"),
    ]
    (tmp_path / "observations.json").write_text(json.dumps(obs))
    (tmp_path / _img_name("pasillo", "20261104-205002")).write_bytes(SYNTH_JPEG)
    (tmp_path / _img_name("cocina1-noche-0300", "20261104-204645")).write_bytes(SYNTH_JPEG)
    empty = "cocina1-noche-0300_20261104-204645.verified-empty.jpg"
    (tmp_path / empty).write_bytes(SYNTH_EMPTY)
    (tmp_path / "verified-empty.json").write_text(json.dumps(
        [{"file": empty, "people_human_verified": 0}]))
    return tmp_path


def test_sin_datos_todo_pending_y_la_ola_sigue_igual(client):
    page = client.get("/?scene=sentinel&lang=en").text
    assert "Surveillance · real cameras, Clara del Rey (Madrid)" in page
    img = client.get("/sentinel/surveillance/occupancy.jpg")
    assert img.headers["content-type"].startswith("image/svg+xml")
    state = client.post("/sentinel/replay").json()
    cards = state["surveillance"]["cards"]
    assert [c["key"] for c in cards] == [
        "occupancy", "after_hours", "stock_watch", "cash_desk", "security_log"]
    assert all(c["status"] == "pending" for c in cards)
    # La frase del testigo ya no entra en la ola (cambio de prioridad).
    assert not any("camera" in f.lower() for f in state["timeline"][0]["findings"])


def test_ocupacion_y_fuera_de_horario_con_datos_reales_en_formato(client, monkeypatch, wdir):
    monkeypatch.setenv("SHIELD_WITNESS_DIR", str(wdir))
    sv = client.get("/sentinel/state").json()["surveillance"]
    occ, ah = sv["cards"][0], sv["cards"][1]
    assert occ["status"] == "live"
    assert {r["room_en"]: r["people"] for r in occ["rooms"]} == {"Kitchen 1": 1, "Hallway": 7}
    assert occ["image_room_en"] == "Hallway" and occ["model"] == "SAM 3.1"
    assert occ["response_id_short"].endswith("…")
    assert ah["status"] == "all_clear" and ah["recorded_hhmm"] == "03:00"
    assert ah["people"] == 0 and ah["human_verified"] is True
    # La regla real del autopiloto se evalúa sobre la observación real.
    assert ah["engine"]["findings"] == ["unattended_remote_physical_command"]
    # Imágenes: la de ocupación es la redactada; la nocturna, la verificada vacía.
    occ_img = client.get("/sentinel/surveillance/occupancy.jpg")
    assert occ_img.headers["content-type"] == "image/jpeg" and occ_img.content == SYNTH_JPEG
    assert client.get("/sentinel/surveillance/after_hours.jpg").content == SYNTH_EMPTY
    assert client.get("/sentinel/surveillance/nope.jpg").status_code == 404
    dumped = json.dumps(sv)
    assert str(wdir) not in dumped and "person_boxes" not in dumped
    assert "redacted.jpg" not in dumped and "verified-empty" not in dumped


def test_personas_fuera_de_horario_es_alerta(monkeypatch, tmp_path):
    (tmp_path / "observations.json").write_text(json.dumps(
        [_obs("cocina1-noche-0300", people=2, source="playback")]))
    ah = surveillance_state(tmp_path)["cards"][1]
    assert ah["status"] == "alert" and ah["people"] == 2


def test_surveillance_json_alimenta_tarjetas_y_lo_que_falta_es_pending(tmp_path):
    (tmp_path / "observations.json").write_text("[]")
    (tmp_path / "almacen.redacted.jpg").write_bytes(SYNTH_JPEG)
    (tmp_path / "surveillance.json").write_text(json.dumps({
        "stock_watch": {"status": "ok", "summary": "Storeroom: 14 boxes",
                        "image": "almacen.redacted.jpg", "model": "sam-3.1"},
        "security_log": {"status": "ok", "text": "Shift report", "model": "muse-spark",
                         "image": "../fuera.jpg"},
    }))
    cards = {c["key"]: c for c in surveillance_state(tmp_path)["cards"]}
    assert cards["stock_watch"]["image"] == "/sentinel/surveillance/stock_watch.jpg"
    assert cards["stock_watch"]["summary"] == "Storeroom: 14 boxes"
    assert cards["security_log"]["image"] is None  # ruta fuera de la carpeta: ignorada
    assert cards["security_log"]["model"] == "Muse Spark"
    assert cards["cash_desk"]["status"] == "pending"


def test_observacion_fallida_o_fixture_no_cuenta_como_camara_real(tmp_path):
    (tmp_path / "observations.json").write_text(json.dumps([
        _obs(ok=False, error="sam timeout"),
        _obs(source="fixture"),
        {"captured_at": "ayer", "people": "muchos"},
    ]))
    obs = load_observations(tmp_path)
    assert len(obs) == 1 and obs[0]["is_fixture"] is True
    assert surveillance_state(tmp_path)["cards"][0]["status"] == "pending"


def test_precision_sale_del_eval_grabado():
    ev = eval_summary()
    assert ev is not None and ev["frames"] > 0
    assert ev["presence_ok"] <= ev["presence_n"]
    assert ev["kitchen_exact"] <= ev["kitchen_n"]
