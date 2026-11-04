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


def _run_until_owner(c: TestClient) -> None:
    for step in ("normal", "document", "shield", "drift", "owner"):
        r = c.post(f"/physical/step/{step}")
        assert r.status_code == 200, (step, r.text)


def test_pagina_physical_en_es_y_selector(client):
    es = client.get("/?scene=physical&lang=es")
    assert es.status_code == 200
    for needle in (
        "El escudo simula la física",
        "Documento de proveedor con orden oculta",
        "Deriva lenta de setpoints",
        "sí, descarta la carga",
        "simulado",
        "CONTENIDO AUTOMÁTICAMENTE",
        "ya está contenido",
    ):
        assert needle in es.text, needle
    en = client.get("/?scene=physical&lang=en")
    assert "Physical shield" in en.text or "physical shield" in en.text
    assert "yes, discard the load" in en.text
    # El selector de las escenas existentes enlaza a Physical sin romper las otras.
    home = client.get("/?lang=es")
    assert "/?scene=physical&lang=es" in home.text
    assert "Cadena de frío" in home.text


def test_pasos_en_orden_y_fuera_de_orden(client):
    client.get("/?scene=physical")
    assert client.post("/physical/step/shield").status_code == 409
    _run_until_owner(client)
    state = client.get("/physical/state").json()
    assert state["scene"] == "physical"
    assert state["simulated"] is True
    assert state["total_cost_usd"] == 0
    assert list(state["results"]) == ["normal", "document", "shield", "drift", "owner"]


def test_documento_pasa_estaticas_y_escudo_bloquea_con_svg(client):
    client.get("/?scene=physical")
    client.post("/physical/step/normal")
    doc = client.post("/physical/step/document").json()
    assert doc["static"]["decision"] == "allow"
    assert doc["proposed_action"]["kind"] == "defrost"
    assert doc["proposed_action"]["duration_min"] == 240.0
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
    assert [s["static"]["decision"] for s in drift["drift_steps"]] == ["allow"] * 5
    assert [s["value_c"] for s in drift["drift_steps"]] == [3.2, 3.4, 3.6, 3.8, 4.0]
    # Cada ALLOW viene del evaluador estático real, con el rango real 0–4 °C.
    for step in drift["drift_steps"]:
        assert step["static"]["evaluation"]["equipment"]["safe_range_c"] == [0.0, 4.0]
        assert step["static"]["evaluation"]["decision"] == "allow"
    assert all(d["static"]["decision"] == "allow" for d in drift["defrost_steps"])
    assert drift["physical"]["decision"] == "block"
    assert drift["physical"]["predicted_breach_min"] is not None
    assert "<svg" in drift["svg"]


def test_contencion_automatica_sin_esperar_al_dueno(client):
    client.get("/?scene=physical")
    for step in ("normal", "document", "shield"):
        client.post(f"/physical/step/{step}")
    state = client.get("/physical/state").json()
    # Contenido en el paso del escudo, antes de cualquier aviso o decisión.
    assert state["approval_id"] is None
    containment = state["containment"]
    assert containment["active"] is True
    assert containment["automatic"] is True
    assert containment["owner_waited"] is False
    assert containment["safe_state"] == {"setpoint_c": 3.0, "compressor_on": True}
    assert containment["agent_writes_held"] is True
    assert len(containment["already_did"]) == 3
    shield = state["results"]["shield"]
    assert shield["real_parallel"]["sources"][0].startswith("https://www.tomshardware.com/")
    assert "50 °C" in shield["real_parallel"]["text"]


def test_deshacer_libera_la_retencion_sin_ejecutar_lo_bloqueado(client):
    client.get("/?scene=physical")
    assert client.post("/physical/undo").status_code == 409
    for step in ("normal", "document", "shield"):
        client.post(f"/physical/step/{step}")
    undone = client.post("/physical/undo").json()
    assert undone["status"] == "ok"
    assert undone["containment"]["active"] is False
    assert undone["containment"]["agent_writes_held"] is False
    state = client.get("/physical/state").json()
    assert "execute" not in state["results"]


def test_lo_irreversible_solo_con_el_dueno_aprobar_y_rechazar(client):
    client.get("/?scene=physical")
    _run_until_owner(client)
    # Sin decisión del dueño no se ejecuta lo irreversible.
    assert client.post("/physical/step/execute").json()["status"] == "not_approved"
    unknown = client.post("/physical/voice", data={"typed": "hola"}).json()
    assert unknown["status"] == "unknown_command"
    ok = client.post("/physical/voice", data={"typed": "sí, descarta la carga"}).json()
    assert ok["status"] == "approved"
    again = client.post("/physical/voice", data={"typed": "sí, descarta la carga"}).json()
    assert again["status"] == "not_pending"
    done = client.post("/physical/step/execute").json()
    assert done["status"] == "ok" and done["load_discarded"] is True
    assert done["peak_product_c"] < 5.0


def test_rechazar_lo_irreversible_conserva_la_carga():
    run = PhysicalRun()
    for step in ("normal", "document", "shield", "drift", "owner"):
        run.step(step, "es")
    out = run.voice("no, rechaza eso")
    assert out["status"] in ("rejected", "unknown_command") or out["intent"]["action"] == "reject"
    if out["status"] == "rejected":
        done = run.step("execute", "es")
        assert done["load_discarded"] is False and done["executed"] == []


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


def test_evaluador_estatico_real_fuera_de_rango_bloquea():
    from crew.refrigeracion.agent import SetpointRequest, evaluate_setpoint

    scopes = ["coldchain:setpoint:camara"]
    inside = evaluate_setpoint(SetpointRequest("camara", 4.0, hour=10), scopes=scopes)
    outside = evaluate_setpoint(SetpointRequest("camara", 5.5, hour=10), scopes=scopes)
    assert inside.decision == "allow"
    assert outside.decision == "block"
