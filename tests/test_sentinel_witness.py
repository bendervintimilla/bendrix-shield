"""Testigo de cámara real en la escena «Sentinel» (datos sintéticos del test).

Nada de fotos reales: la «imagen» es un JPEG mínimo generado aquí mismo.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from web.app import create_panel_app
from web.sentinel_witness import load_observations, night_finding, night_playback

# JPEG sintético mínimo (SOI + APP0 + relleno + EOI): no es una foto.
SYNTH_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + bytes(64) + b"\xff\xd9"
)


def _obs(**over):
    base = {
        "camera": "kitchen", "site": "Clara del Rey, Madrid", "room": "kitchen",
        "captured_at": "2026-11-04T03:04:12+01:00", "people": 0, "door_open": False,
        "person_boxes": [], "model": "SAM 3.1", "response_ids": ["resp_test_abcdefghijkl"],
        "latency_ms": 812.4, "cost_usd": 0.0021, "source": "playback",
    }
    base.update(over)
    return base


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("SHIELD_REPLAY_HOME", "1")
    monkeypatch.delenv("SHIELD_SENTINEL_HOME", raising=False)
    monkeypatch.delenv("SHIELD_WITNESS_DIR", raising=False)
    return TestClient(create_panel_app())


def _write(tmp_path, observations, image=SYNTH_JPEG):
    (tmp_path / "observations.json").write_text(json.dumps(observations))
    if image is not None:
        (tmp_path / "latest.jpg").write_bytes(image)
    return tmp_path


def test_sin_testigo_la_escena_sigue_como_hoy(client):
    page = client.get("/?scene=sentinel&lang=en").text
    assert "Real camera witness" in page and "Clara del Rey, Madrid" in page
    img = client.get("/sentinel/witness/latest.jpg")
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/svg+xml")
    assert b"<image" not in img.content  # placeholder neutro, sin foto
    state = client.post("/sentinel/replay").json()
    assert state["witness"]["available"] is False
    cold = state["timeline"][0]
    assert not any("camera" in f.lower() for f in cold["findings"])


def test_testigo_nocturno_entra_en_la_ola(client, monkeypatch, tmp_path):
    _write(tmp_path, [
        _obs(),
        _obs(captured_at="2026-11-04T21:10:05+01:00", people=2, door_open=True,
             source="live", response_ids=["resp_live_0123456789"]),
    ])
    monkeypatch.setenv("SHIELD_WITNESS_DIR", str(tmp_path))
    img = client.get("/sentinel/witness/latest.jpg")
    assert img.headers["content-type"] == "image/jpeg"
    assert img.content == SYNTH_JPEG
    assert img.headers["cache-control"] == "no-store"
    client.get("/?scene=sentinel")
    state = client.post("/sentinel/replay").json()
    w = state["witness"]
    assert w["available"] and w["has_image"]
    assert w["latest"]["people"] == 2 and w["latest"]["is_live"] is True
    assert w["latest"]["response_id_short"].endswith("…")
    assert len(w["latest"]["response_id_short"]) <= 12
    assert w["night"]["captured_hhmm"] == "03:04"
    cold = state["timeline"][0]
    assert cold["app"] == "cold_room"
    assert ("Kitchen camera (real, 03:04): 0 people on site — "
            "a remote defrost with nobody there") in cold["findings"]
    # Nada privado sale en el estado público: ni rutas ni bytes.
    dumped = json.dumps(state)
    assert str(tmp_path) not in dumped and "person_boxes" not in dumped


def test_frase_en_espanol(client, monkeypatch, tmp_path):
    _write(tmp_path, [_obs()])
    monkeypatch.setenv("SHIELD_WITNESS_DIR", str(tmp_path))
    client.get("/?scene=sentinel&lang=es")
    state = client.post("/sentinel/replay?lang=es").json()
    assert any(f.startswith("Cámara de cocina (real, 03:04): 0 personas")
               for f in state["timeline"][0]["findings"])


def test_sin_grabacion_nocturna_no_hay_frase(tmp_path):
    # En vivo, o de día, o con gente: no se afirma «nobody there».
    _write(tmp_path, [
        _obs(source="live"),
        _obs(captured_at="2026-11-04T14:00:00+01:00"),
        _obs(people=1),
    ])
    obs = load_observations(tmp_path)
    assert len(obs) == 3
    assert night_playback(obs) is None
    assert night_finding(None, "en") == ""


def test_datos_malos_o_imagen_no_jpeg_no_rompen(client, monkeypatch, tmp_path):
    (tmp_path / "observations.json").write_text("{no es json")
    (tmp_path / "latest.jpg").write_bytes(b"<svg>not a jpeg</svg>")
    monkeypatch.setenv("SHIELD_WITNESS_DIR", str(tmp_path))
    assert load_observations(tmp_path) == []
    img = client.get("/sentinel/witness/latest.jpg")
    assert img.headers["content-type"].startswith("image/svg+xml")
    state = client.post("/sentinel/replay").json()
    assert state["witness"]["available"] is False
    _write(tmp_path, [{"captured_at": "ayer", "people": "muchos"}, _obs(people=True)])
    assert load_observations(tmp_path) == []


def test_observacion_fallida_o_fixture_no_cuenta_como_testigo_real(tmp_path):
    # Formato real de WitnessObservation.public(): trae ok/error/has_redacted_image.
    _write(tmp_path, [
        _obs(ok=False, error="sam timeout", has_redacted_image=False),
        _obs(source="fixture", ok=True, error=None),
    ])
    obs = load_observations(tmp_path)
    assert len(obs) == 1 and obs[0]["is_fixture"] is True
    assert night_playback(obs) is None
