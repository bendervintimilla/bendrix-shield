"""M5: escena «Physical» — replay determinista del escudo físico, sin red."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.app import create_panel_app
from web.physical_scene import PhysicalRun, trajectory_svg


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("SHIELD_REPLAY_HOME", "1")
    return TestClient(create_panel_app())


def _run_until_safe(c: TestClient) -> None:
    for step in ("normal", "document", "shield", "drift", "safe"):
        r = c.post(f"/physical/step/{step}")
        assert r.status_code == 200, (step, r.text)


def test_pagina_physical_en_es_y_selector(client):
    es = client.get("/?scene=physical&lang=es")
    assert es.status_code == 200
    for needle in (
        "El escudo simula la física",
        "Documento de proveedor con orden oculta",
        "Deriva lenta de setpoints",
        "sí, mantén el compresor encendido",
        "simulado",
    ):
        assert needle in es.text, needle
    en = client.get("/?scene=physical&lang=en")
    assert "Physical shield" in en.text or "physical shield" in en.text
    assert "yes, keep the compressor on" in en.text
    # El selector de las escenas existentes enlaza a Physical sin romper las otras.
    home = client.get("/?lang=es")
    assert "/?scene=physical&lang=es" in home.text
    assert "Cadena de frío" in home.text


def test_pasos_en_orden_y_fuera_de_orden(client):
    client.get("/?scene=physical")
    assert client.post("/physical/step/shield").status_code == 409
    _run_until_safe(client)
    state = client.get("/physical/state").json()
    assert state["scene"] == "physical"
    assert state["simulated"] is True
    assert state["total_cost_usd"] == 0
    assert list(state["results"]) == ["normal", "document", "shield", "drift", "safe"]


def test_documento_pasa_estaticas_y_escudo_bloquea_con_svg(client):
    client.get("/?scene=physical")
    client.post("/physical/step/normal")
    doc = client.post("/physical/step/document").json()
    assert doc["static"]["decision"] == "allow"
    assert doc["proposed_action"]["kind"] == "compressor_off"
    assert doc["proposed_action"]["duration_min"] == 300.0
    shield = client.post("/physical/step/shield").json()
    phys = shield["physical"]
    assert phys["decision"] == "block"
    assert phys["predicted_breach_min"] is not None
    assert phys["peak_product_c"] > 5.0
    assert phys["minutes_above_limit"] > 30
    assert shield["applied"] is False
    svg = shield["svg"]
    assert svg.startswith("<svg")
    assert "5 °C" in svg
    assert str(int(phys["predicted_breach_min"])) in svg
    assert "simulated" in svg


def test_deriva_en_rango_tambien_bloqueada(client):
    client.get("/?scene=physical")
    for step in ("normal", "document", "shield"):
        client.post(f"/physical/step/{step}")
    drift = client.post("/physical/step/drift").json()
    assert [s["static"]["decision"] for s in drift["drift_steps"]] == ["allow"] * 3
    assert [s["value_c"] for s in drift["drift_steps"]] == [4.0, 5.0, 6.0]
    assert drift["physical"]["decision"] == "block"
    assert drift["physical"]["predicted_breach_min"] is not None
    assert "<svg" in drift["svg"]


def test_aprobacion_escrita_de_un_solo_uso_y_ejecucion_segura(client):
    client.get("/?scene=physical")
    _run_until_safe(client)
    # Sin aprobar no se ejecuta la alternativa.
    assert client.post("/physical/step/execute").json()["status"] == "not_approved"
    unknown = client.post("/physical/voice", data={"typed": "hola"}).json()
    assert unknown["status"] == "unknown_command"
    ok = client.post(
        "/physical/voice", data={"typed": "sí, mantén el compresor encendido"}
    ).json()
    assert ok["status"] == "approved"
    again = client.post(
        "/physical/voice", data={"typed": "sí, mantén el compresor encendido"}
    ).json()
    assert again["status"] == "not_pending"
    done = client.post("/physical/step/execute").json()
    assert done["status"] == "ok"
    assert done["peak_product_c"] < 5.0
    assert "<svg" in done["svg"]


def test_determinismo_dos_corridas_iguales():
    a, b = PhysicalRun(), PhysicalRun()
    for step in ("normal", "document", "shield", "drift"):
        ra, rb = a.step(step, "es"), b.step(step, "es")
        assert ra == rb


def test_svg_sin_librerias_y_con_linea_de_5c():
    run = PhysicalRun()
    run.step("normal")
    run.step("document")
    out = run.step("shield", "en")
    svg = out["svg"]
    assert "<script" not in svg and "http" not in svg
    assert trajectory_svg.__module__ == "web.physical_scene"


def test_bodega_y_frio_no_se_rompen(client):
    assert client.get("/?lang=es").status_code == 200
    assert client.get("/?scene=frio&lang=en").status_code == 200
    assert client.post("/replay/step/invoice").status_code == 200


def test_origen_cruzado_se_rechaza(client):
    client.get("/?scene=physical")
    r = client.post("/physical/step/normal", headers={"origin": "https://otro.example"})
    assert r.status_code == 403
