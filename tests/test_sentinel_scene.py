"""M3 tarea 3: escena «Sentinel» — ola contenida por el autopiloto real."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.app import create_panel_app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("SHIELD_REPLAY_HOME", "1")
    monkeypatch.delenv("SHIELD_SENTINEL_HOME", raising=False)
    return TestClient(create_panel_app())


def test_pagina_sentinel_en_es_y_selector(client):
    en = client.get("/?scene=sentinel&lang=en")
    assert en.status_code == 200
    for needle in (
        "Replay this week's attacks",
        "Cold room",
        "Payments",
        "AI gateway",
        "POS / ERP",
        "detected → contained",
        "Legitimate operations still running:",
        "shutting everything down: 0/300",
        "Approve with 2nd factor",
        "simulated",
        "tomshardware.com",
        "euronews.com",
    ):
        assert needle in en.text, needle
    es = client.get("/?scene=sentinel&lang=es")
    assert "Repetir los ataques de esta semana" in es.text
    assert "detectado → contenido" in es.text
    # El selector de las escenas existentes enlaza a Sentinel sin romper otras.
    home = client.get("/?lang=es")
    assert "/?scene=sentinel&lang=es" in home.text
    assert "/?scene=physical&lang=es" in home.text


def test_sentinel_home_por_defecto_con_env(client, monkeypatch):
    assert "Replay this week's attacks" not in client.get("/").text
    monkeypatch.setenv("SHIELD_SENTINEL_HOME", "1")
    home = client.get("/")
    assert "Replay this week's attacks" in home.text


def test_estado_inicial_todo_en_verde(client):
    client.get("/?scene=sentinel")
    state = client.get("/sentinel/state").json()
    assert state["scene"] == "sentinel"
    assert state["simulated"] is True
    assert state["replayed"] is False
    assert [a["status"] for a in state["apps"]] == ["ok"] * 4
    assert state["legit_allowed"] == sum(state["legit_counters"].values())


def _replay(client) -> dict:
    r = client.post("/sentinel/replay")
    assert r.status_code == 200, r.text
    return r.json()


def test_replay_contiene_los_tres_ataques_con_motor_real(client):
    client.get("/?scene=sentinel")
    state = _replay(client)
    assert [t["app"] for t in state["timeline"]] == [
        "cold_room",
        "payments",
        "ai_gateway",
    ]
    assert all(t["simulated"] for t in state["timeline"])
    # Frío: el escudo físico bloquea y deja el último estado seguro.
    assert state["cold"]["decision"] == "block"
    assert state["cold"]["peak_product_c"] > 5.0
    assert state["cold"]["safe_setpoint_c"] == 3.0
    assert "<svg" in state["cold"]["svg"]
    # Gateway: 401 real del gateway en memoria tras rotar; el legítimo pasa.
    assert state["gateway"]["attacker_before"] == 200
    assert state["gateway"]["attacker_after"] == 401
    assert state["gateway"]["legit_after"] == 200
    assert state["gateway"]["rotated"] is True
    # Contador medido por el motor (no inventado).
    assert state["detect_to_contain_ms"] >= 0
    # Pagos: retenido y pendiente del dueño, nunca ejecutado solo.
    kinds = {(m["kind"], m["app"]) for m in state["measures"]}
    assert ("hold_payment", "payments") in kinds
    assert ("safe_state", "cold_room") in kinds
    assert state["scope_level"] == "global"
    # Aviso de negocio de M10, sin ids internos, en los dos idiomas.
    assert "wAIrrior stopped an attack" in state["notice"]["text_en"]
    assert "Acme Foods" in state["notice"]["text_en"]
    assert "second factor" in state["notice"]["text_en"]
    assert "wAIrrior detuvo un ataque" in state["notice"]["text_es"]
    assert state["pending_owner"]["en"] and state["pending_owner"]["es"]
    # Línea de tiempo localizada y en lenguaje de negocio (EN sin español).
    findings_en = " ".join(f for t in state["timeline"] for f in t["findings"])
    for forbidden in ("deshielo", "física (M1)", "supplier:acme", "0.0 h", "beneficiario"):
        assert forbidden not in findings_en, forbidden
    assert "seconds later" in findings_en
    assert "Acme Foods" in findings_en
    # Fila bajo el contador: número real del motor para la ola.
    assert 0 < state["legit_still_running"] < 300
    assert state["legit_total"] == 300
    # Las 4 apps conectadas quedan contenidas/marcadas, el fondo legítimo sigue.
    assert all(a["status"] == "contained" for a in state["apps"])
    assert state["legit_counters"]["payments_ok"] >= 3


def test_replay_en_espanol_linea_de_tiempo_localizada(client):
    client.get("/?scene=sentinel&lang=es")
    r = client.post("/sentinel/replay?lang=es")
    assert r.status_code == 200, r.text
    state = r.json()
    findings_es = " ".join(f for t in state["timeline"] for f in t["findings"])
    assert "segundos después" in findings_es
    assert "Acme Foods" in findings_es
    assert "supplier:" not in findings_es


def test_replay_idempotente_y_reset(client):
    client.get("/?scene=sentinel")
    first = _replay(client)
    second = _replay(client)
    assert second["run_id"] == first["run_id"]
    assert len(second["timeline"]) == 3
    reset = client.post("/sentinel/reset").json()
    assert reset["replayed"] is False


def test_undo_y_release_con_segundo_factor(client):
    client.get("/?scene=sentinel")
    state = _replay(client)
    measure = next(m for m in state["measures"] if m["kind"] == "hold_payment")
    undone = client.post("/sentinel/undo", data={"undo_id": measure["undo_id"]})
    assert undone.status_code == 200
    assert undone.json()["status"] == "ok"
    bad = client.post("/sentinel/release", data={"factor": "000000"})
    assert bad.status_code == 400
    good = client.post(
        "/sentinel/release", data={"factor": state["second_factor_demo"]}
    )
    assert good.status_code == 200
    assert good.json()["released"] is True


def test_pulido_etiquetas_por_app_y_posesivo(client):
    client.get("/?scene=sentinel")
    state = _replay(client)
    labels = {m["label_en"] for m in state["measures"]}
    assert "Cold room: blocked the 4-hour defrost" in labels
    assert "Payments: transfer of USD 4,800 to Acme Foods held" in labels
    assert any(lbl.startswith("AI gateway: stolen key replaced") for lbl in labels)
    assert "Blocked the malicious action" not in labels
    # Cada etiqueta dice la app: «App: qué cosa».
    assert all(": " in m["label_en"] and ": " in m["label_es"] for m in state["measures"])
    assert "Foods's" not in state["notice"]["text_en"]
    assert "Acme Foods' bank details" in state["notice"]["text_en"]


def test_desglose_de_operaciones_vivas_sale_del_motor(client):
    client.get("/?scene=sentinel")
    state = _replay(client)
    sb = state["still_breakdown"]
    assert sb["scope_level"] == "global"
    assert sb["total"] == 300
    assert sb["human_known_payments_kept"] + sb["other_kept"] == state["legit_still_running"]
    assert sb["agent_writes_paused"] + sb["human_paused"] + state["legit_still_running"] == 300
    page = client.get("/?scene=sentinel&lang=en").text
    assert "stillWhy" in page and "every AGENT write" in page


def test_deshacer_otro_agente_no_revive_la_llave_robada(client):
    client.get("/?scene=sentinel")
    state = _replay(client)
    other = next(m for m in state["measures"]
                 if m["kind"] == "revoke_tokens" and m["target"] == "payments-bot")
    assert client.post("/sentinel/undo", data={"undo_id": other["undo_id"]}).json()["status"] == "ok"
    store = client.app.state.sentinel_store
    run = next(r for _, r in store._items.values() if r.run_id == state["run_id"])
    assert run._gw_call(run._stolen_raw) == 401
